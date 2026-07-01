# Etapa 0 — Por qué eventos

## 🎯 Objetivo de la etapa

Entender **por qué** un sistema de pagos como GWP se construye orientado a eventos en lugar de como un monolito sincrónico. Que al terminar puedas explicarle a otro las cuatro razones de fondo: **acoplamiento, escalado, tolerancia a fallos y asincronía**.

---

## 📖 Teoría

Pensá en cómo resolverías esto con lo que ya sabés. Te piden: "cuando llega una solicitud de pago, generá una orden QR en MercadoPago, guardá todo en la base, y cuando MercadoPago confirme el pago, avisale al cliente por su webhook".

### Cómo lo harías en un monolito Spring clásico

Un `@RestController` recibe el `POST`, llama a un `@Service`, que dentro de la **misma transacción y el mismo hilo**:

```java
// Monolito sincrónico clásico — todo en un request
@PostMapping("/payments")
public PaymentResponse crear(@RequestBody PaymentRequest req) {
    Order order = orderService.crear(req);           // 1. lógica de negocio
    MpOrder mpOrder = mercadoPagoClient.crearOrden(order); // 2. llamada REST bloqueante
    order.setQr(mpOrder.getQr());
    orderRepository.save(order);                      // 3. persistencia
    return PaymentResponse.from(order);               // 4. respondo YA, con todo resuelto
}
```

Esto funciona, lo hiciste mil veces, y para muchos sistemas está perfecto. Pero mirá las costuras cuando el sistema crece:

**1. Acoplamiento temporal.** El paso 2 es una llamada HTTP bloqueante a MercadoPago. Si MercadoPago tarda 4 segundos, tu request tarda 4 segundos. Si MercadoPago está caído, **tu endpoint falla**, aunque la solicitud del cliente era perfectamente válida y la podrías haber procesado más tarde. Tu disponibilidad quedó atada a la de un tercero.

**2. Escalado en bloque.** Si te llueven webhooks de confirmación pero pocas solicitudes nuevas, no podés escalar "solo la parte de webhooks": escalás el monolito entero. Pagás CPU y memoria de todo para resolver el cuello de botella de una parte.

**3. Tolerancia a fallos.** Si el paso 4 (notificar al cliente) falla, ¿qué hacés? ¿Rollback de todo el pago que ya está confirmado en MercadoPago? No podés: el dinero ya se movió. Mezclar "cobrar" con "avisar" en una sola transacción te deja en estados imposibles.

**4. Asincronía forzada a mano.** Para no bloquear, terminás metiendo `@Async`, `ExecutorService`, `CompletableFuture`, colas en memoria con `BlockingQueue`… y reinventás, mal y sin durabilidad, lo que un broker de mensajería te da hecho. Si el proceso se cae, tu `BlockingQueue` en memoria se perdió.

### El cambio de mentalidad: del "llamar" al "avisar"

En event-driven dejás de **llamar** a quien sigue y pasás a **avisar que pasó algo**. El api-gateway no le dice al payment-service "hacé esto"; **publica un hecho**: *"se recibió una solicitud de pago"* (`OnPaymentRequestReceivedEvent`). Quién lo escucha, cuándo y qué hace con eso, es problema del consumidor.

> **Analogía:** en el monolito sos un gerente que llama por teléfono a cada empleado y espera en la línea hasta que termina. En event-driven dejás una **nota en un casillero** (la cola) y seguís con lo tuyo. El empleado la toma cuando puede. Si está de licencia, la nota lo espera. Si hay mucho trabajo, ponés tres empleados a vaciar el mismo casillero.

Esa "nota en el casillero" es **durable** (sobrevive a reinicios), **desacoplada** (el que avisa no conoce al que procesa) y permite **escalar por casillero** (agregás consumidores donde se acumula trabajo).

### Lo que ganás, punto por punto

| Problema del monolito | Cómo lo resuelve event-driven |
|---|---|
| Acoplamiento temporal | El gateway publica y responde `202` al instante; no espera a MercadoPago |
| Escalado en bloque | Escalás el servicio (o los consumidores de una cola) que está saturado |
| Fallos en cascada | Si un servicio se cae, los mensajes esperan en la cola; nada se pierde |
| Asincronía artesanal | El broker te da durabilidad, reintentos y entrega garantizada |

### Lo que pagás a cambio (que no te mientan)

No es gratis. Aceptás **consistencia eventual** (el estado no es coherente en todos lados *en el mismo instante*, sino *al rato*), **debugging distribuido** (un flujo cruza 4 servicios y RabbitMQ), y **complejidad operativa** (K8s, broker, observabilidad). GWP asume ese costo a propósito: en pagos, **no perder un mensaje** y **no quedar atado a la caída de un proveedor** vale más que la simplicidad de un monolito.

---

## 🔍 En nuestro sistema

GWP lleva esta idea al extremo sano:

- El **api-gateway** no tiene base de datos ni lógica de negocio pesada. Recibe el `POST /api/v1/payments`, valida, lo transforma en `OnPaymentRequestReceivedEvent`, lo publica al exchange `on_new_payment_request` y responde **`202 Accepted`** sin esperar nada más. Le dijo al sistema "esto pasó" y se desentendió.
- El **payment-service** consume ese evento *cuando puede*, decide qué hacer, persiste, y emite **nuevos eventos** para que el `mercadopago-adapter` cree la orden y el `notification-service` avise al cliente. Nadie llama a nadie: **todos reaccionan a hechos**.
- Si MercadoPago está caído, el evento queda en la cola del adapter y se reintenta (con DLQ). El cliente que pidió el pago **ya recibió su `202`** hace rato.

Ese `202` es la diferencia filosófica con tu monolito: **"recibí tu pedido y me hago cargo"**, en vez de **"esperá en la línea que lo resuelvo entero ahora"**.

---

## 📂 Qué buscar en el código (para la semana)

Todavía no necesitás el repo, pero anotá para después:

- En el **api-gateway**, los controllers de entrada: fijate que los métodos **no devuelven el resultado del negocio**, sino un `202`/`200` casi inmediato. Eso confirma el desacople.
- Buscá dónde el gateway **publica** a RabbitMQ en vez de llamar a otro servicio por REST. Ese es el corazón del cambio.
- En el **payment-service**, fijate que **no hay controllers HTTP**: toda su entrada son métodos que reaccionan a mensajes. Un servicio que "no tiene puerta HTTP" es algo que en tu mundo monolítico no existía.

---

## ❓ Preguntas para verificar que entendiste

1. En el monolito, ¿por qué la disponibilidad de tu endpoint de pagos queda atada a la de MercadoPago? ¿Cómo rompe GWP esa atadura?
2. ¿Qué significa que el api-gateway responda `202 Accepted` en lugar de `200 OK` con el pago ya resuelto?
3. Nombrá los cuatro problemas del monolito sincrónico que el enfoque event-driven ataca.
4. ¿Cuál es el principal **costo** que aceptás al irte a event-driven, y por qué en un sistema de pagos vale la pena?
5. ¿Por qué una `BlockingQueue` en memoria con un `Executor` **no** es equivalente a usar RabbitMQ?

---

## ✍️ Mini-ejercicio

Tomá el código del monolito de arriba (`crear(...)`). En una hoja, **marcá con una cruz cada punto donde una falla dejaría el sistema en un estado inconsistente o indisponible** (ej.: MercadoPago caído, la base no responde, el cliente no recibe el aviso). Después, al lado de cada cruz, escribí en una línea **quién se haría cargo de ese paso en GWP** (qué servicio) y **qué pasaría con el mensaje si ese servicio estuviera caído**. No escribas código: es trazado mental.

---

**Siguiente:** `etapa-1-vocabulario-mensajeria.md`
