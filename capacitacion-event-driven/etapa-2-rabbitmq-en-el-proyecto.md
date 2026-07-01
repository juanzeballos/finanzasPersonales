# Etapa 2 — RabbitMQ en este proyecto

## 🎯 Objetivo de la etapa

Bajar el vocabulario de la Etapa 1 a **cómo se ve en Spring**: cómo se declaran exchanges/colas/bindings, cómo un método se vuelve consumidor con `@RabbitListener`, cómo viaja el JSON, y cómo **ver todo esto funcionando** en la UI de Management de RabbitMQ.

> Recordá: los snippets son **ilustrativos**. El código real de GWP puede diferir en nombres y detalles; lo confirmás cuando tengas el repo.

---

## 📖 Teoría

### Declarar la topología desde Spring

En Spring AMQP (`spring-boot-starter-amqp`), la topología — exchanges, colas, bindings — se declara como **beans**. Cuando la app arranca, un `RabbitAdmin` los crea en el broker si no existen. Esto es lindo: la infraestructura de mensajería vive **en el código**, versionada, no en clicks manuales en la UI.

```java
// Ejemplo ILUSTRATIVO — el código real puede variar
@Configuration
public class RabbitConfig {

    // Un exchange fanout: difunde a todas las colas atadas
    @Bean
    FanoutExchange onNewPaymentRequestExchange() {
        return new FanoutExchange("on_new_payment_request");
    }

    // Una cola durable (sobrevive reinicios del broker)
    @Bean
    Queue paymentRequestQueue() {
        return QueueBuilder.durable("payment_request_queue").build();
    }

    // El binding: conecta la cola al exchange.
    // En fanout no hace falta routing key.
    @Bean
    Binding bindPaymentRequest(Queue paymentRequestQueue,
                               FanoutExchange onNewPaymentRequestExchange) {
        return BindingBuilder.bind(paymentRequestQueue)
                             .to(onNewPaymentRequestExchange);
    }
}
```

Para un **topic exchange** el binding lleva un patrón de routing key:

```java
// Ejemplo ILUSTRATIVO de topic — webhook por proveedor
@Bean TopicExchange webhookExchange() {
    return new TopicExchange("on_new_webhook_notification");
}

@Bean Binding bindMercadoPagoWebhook(Queue mpWebhookQueue, TopicExchange webhookExchange) {
    // routing key = providerCode; acá matchea exactamente el de MercadoPago
    return BindingBuilder.bind(mpWebhookQueue).to(webhookExchange).with("mercadopago");
}
```

> **Mentalidad:** declarar un `Queue`/`Exchange`/`Binding` bean es como registrar la "cañería". No procesa nada; solo dice *cómo está conectado el sistema de correo*. El procesamiento viene aparte, con el listener.

### Publicar un mensaje

El productor usa `RabbitTemplate`. Le das **exchange + routing key + payload**:

```java
// Ejemplo ILUSTRATIVO — publicar el evento
rabbitTemplate.convertAndSend(
    "on_new_payment_request",   // exchange
    "",                         // routing key (vacía: es fanout)
    event                       // objeto -> se serializa a JSON (ver más abajo)
);
```

`convertAndSend` aplica un **MessageConverter** para transformar tu objeto Java en bytes. El gateway hace exactamente esto: arma el `OnPaymentRequestReceivedEvent` y lo manda al exchange.

### Consumir: `@RabbitListener`

Un método anotado con `@RabbitListener` se ata a una cola. Spring levanta un *listener container* (con su pool de hilos) que **escucha la cola y entrega los mensajes a tu método**. Cuando el método retorna normalmente, Spring hace **ack**; si lanza excepción, hace **nack** (y según config, re-encola o manda a DLQ).

```java
// Ejemplo ILUSTRATIVO — un consumidor
@RabbitListener(queues = "payment_request_queue")
public void onPaymentRequest(OnPaymentRequestReceivedEvent event) {
    // el JSON ya se deserializó al record/clase del evento
    paymentUseCase.handle(event);
    // si retorna sin excepción -> ACK automático
    // si lanza -> NACK -> reintento o DLQ
}
```

> **La analogía clave:** el *listener container* es tu `Executor` dedicado, la cola es tu `BlockingQueue` — pero durable y fuera del proceso —, y el `@RabbitListener` es el `Runnable` que corre por cada ítem. La diferencia enorme: el **ack** te da entrega garantizada. Con un `BlockingQueue`, si el worker explota a mitad, el ítem se perdió. Acá vuelve a la cola.

### Serialización: JSON por el medio

Los servicios no comparten objetos Java en memoria: comparten **JSON** por el cable. Se configura un `MessageConverter` (típicamente `Jackson2JsonMessageConverter`) como bean, y a partir de ahí `convertAndSend` serializa a JSON al publicar y `@RabbitListener` deserializa de JSON al consumir.

Esto importa por dos razones prácticas:
1. **Contrato entre servicios:** el evento es un contrato. Si cambiás un campo de un `record` de evento en un servicio, todos los que lo consumen tienen que entender la nueva forma. Versionar eventos es un tema real.
2. **`record` inmutables:** GWP usa `record` para commands/events. Jackson sabe deserializar `record` desde Java 16+, así que el evento viaja como JSON y revive como `record` inmutable del otro lado.

### Concurrencia y prefetch en Spring

En el `application.yml` se ajusta cuántos consumidores concurrentes hay por listener y el prefetch:

```yaml
# Ejemplo ILUSTRATIVO
spring:
  rabbitmq:
    listener:
      simple:
        concurrency: 1          # consumidores mínimos por listener
        max-concurrency: 5      # máximo si hay backlog
        prefetch: 10            # mensajes en vuelo por consumidor
        acknowledge-mode: auto  # ack/nack según retorno/excepción del método
```

---

## 🔍 En nuestro sistema

- El **api-gateway** es el productor de los 4 exchanges de entrada: publica con `RabbitTemplate` (o equivalente) hacia `on_new_payment_request`, `on_new_webhook_notification`, `on_new_cancel_order_request`, `on_new_refund_order_request`.
- El **payment-service** tiene **9 métodos consumidores** (una cola cada uno, conceptualmente) y publica a **6 exchanges**. Es el que más topología toca.
- El **mercadopago-adapter** consume 6 colas y publica 5 exchanges; además declara **DLQ** para las fallas contra MercadoPago.
- El **notification-service** consume 2 colas y publica 1 exchange de auditoría (`on_notification_attempt_completed`).
- El broker es **RabbitMQ** sobre AMQP (`5672`), con **UI de Management en `15672`**, corriendo como `StatefulSet rabbitmq-0` en Kubernetes.

### Ver todo esto en la UI de Management

La UI de Management (puerto `15672`) es tu mejor amiga para entender el sistema sin leer una línea de código:

- **Exchanges:** ves los 6+ exchanges, su **tipo** (fanout/topic/direct) y sus bindings. Acá confirmás de un vistazo que `on_new_payment_request` es fanout.
- **Queues:** ves cada cola, **cuántos mensajes tiene encolados**, cuántos están "en vuelo" (unacked), y la tasa de entrada/salida. Si una cola crece y no baja → consumidor caído o lento.
- **Bindings:** ves qué cola está atada a qué exchange con qué routing key.
- Podés incluso **publicar un mensaje a mano** desde la UI para probar un consumidor.

Para llegar ahí en el entorno de GWP (lo retomamos en la Etapa 7):

```bash
kubectl port-forward -n dev svc/rabbitmq-service 15672:15672
# luego abrís http://localhost:15672 en el navegador
```

---

## 📂 Qué buscar en el código (para la semana)

- La **clase de configuración de RabbitMQ** de cada servicio: los `@Bean` de `Exchange`, `Queue`, `Binding`. Es el mapa de la topología.
- El **bean del `MessageConverter`** (buscá `Jackson2JsonMessageConverter` o similar): confirma que el transporte es JSON.
- Los **métodos `@RabbitListener`**: son los puntos de entrada reales de los servicios event-driven. Contá cuántos hay en el payment-service (deberían ser ~9).
- Dónde se usa el **`RabbitTemplate`** (o un wrapper): ahí está la publicación de eventos.
- El **`application.yml`/`.properties`**: `concurrency`, `prefetch`, `acknowledge-mode`, y la conexión al broker.

---

## ❓ Preguntas para verificar que entendiste

1. ¿Qué hace un `@Bean` de tipo `Queue`/`Exchange`/`Binding` cuando arranca la app, y por qué conviene declarar la topología en código y no a mano en la UI?
2. ¿Quién hace el **ack** cuando usás `@RabbitListener` con `acknowledge-mode: auto`, y qué pasa si tu método lanza una excepción?
3. ¿Por qué los servicios intercambian **JSON** y no objetos Java directamente? ¿Qué implica eso para cambiar un campo de un evento?
4. Si entrás a la UI de Management y ves una cola con 5.000 mensajes encolados y 0 unacked, ¿qué sospechás?
5. ¿Para qué sirve `max-concurrency` y cómo se relaciona con el escalado que vimos en la Etapa 0?

---

## ✍️ Mini-ejercicio

Tomá el snippet ilustrativo del `@RabbitListener` de arriba. Anotá, paso a paso, **el ciclo de vida de un mensaje** desde que está en la cola hasta que desaparece: (1) el container lo toma, (2) se deserializa el JSON, (3) corre tu método, (4) ack/nack. En cada paso, escribí **qué pasaría si el servicio se cae justo ahí**. ¿En qué paso(s) el mensaje se reprocesaría y por qué?

---

**Siguiente:** `etapa-3-hexagonal-clean-cqrs.md`
