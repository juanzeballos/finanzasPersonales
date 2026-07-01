# Etapa 8 — Consolidar

## 🎯 Objetivo de la etapa

Cerrar el círculo. Usar todo lo aprendido en un **ejercicio mental de diseño** ("cómo agregaría un proveedor nuevo"), tener a mano un **mapa de troubleshooting** para los problemas típicos de un sistema event-driven, y un **glosario de una página** para repasar de un vistazo.

---

## 📖 Ejercicio de cierre: "¿Cómo agregaría un proveedor nuevo?"

Esta es **la** pregunta que demuestra si entendiste la arquitectura. Hoy GWP habla con MercadoPago. Imaginá que entra un proveedor nuevo — digamos "PagoYa". ¿Qué tocás?

Pensalo vos primero, en una hoja, antes de leer lo de abajo. Recorré los 4 servicios y preguntate "¿este se entera de que existe PagoYa?".

### La respuesta (y por qué la arquitectura te ayuda)

**1. api-gateway — casi sin cambios.** El endpoint de webhooks ya es genérico: `POST /api/v1/webhooks/{provider}/notifications`. El `{provider}` se vuelve la **routing key** (`providerCode`) en el exchange `on_new_webhook_notification` (topic). Para que las notificaciones de PagoYa ruteen a su adapter, alcanza con **agregar un binding** con la routing key de PagoYa. **No tocás el código del gateway.** ← *Acá ves por qué el exchange de webhook es `topic` y no `fanout`.*

**2. Un nuevo `pagoya-adapter` — el grueso del trabajo.** Nace un adapter hermano del `mercadopago-adapter`: consume las colas de PagoYa, traduce eventos GWP ↔ API de PagoYa, valida sus webhooks con **su** esquema de firma, maneja **sus** tokens/secrets por cliente, y sus reintentos/DLQ. Como el adapter **encapsula** todo lo del proveedor, el resto del sistema ni se entera del cambio.

**3. payment-service — poco o nada.** Es el *Aggregate Root* y razona en **eventos de dominio genéricos** ("orden creada", "pago confirmado"), no en MercadoPago. Mientras el `pagoya-adapter` emita/consuma los mismos eventos de dominio, el payment-service sigue igual. *(Acá ves el valor de hexagonal: el negocio no conoce al proveedor.)*

**4. notification-service — una Strategy nueva.** Recordá los **12 extractores de metadatos** (patrón Strategy). Si PagoYa mete la metadata distinto, agregás **una implementación más** del extractor para PagoYa. No tocás las otras 12. *(Acá ves el valor de Strategy.)*

> **La moraleja:** una arquitectura event-driven + hexagonal + Strategy hace que "agregar un proveedor" sea **sumar piezas**, no **editar el corazón**. Si tu respuesta hubiera sido "toco el payment-service para meter un `if (provider == pagoya)`", la arquitectura estaría mal — y justamente está diseñada para que no haga falta.

---

## 🔧 Troubleshooting típico

Tres síntomas clásicos de sistemas event-driven y cómo encararlos. **Regla general: el estado del sistema se lee en RabbitMQ (colas/DLQ) y en los logs de los pods.**

### Síntoma 1 — "Hay mensajes en la DLQ"

**Qué significa:** uno o más mensajes fallaron lo suficiente como para ser desviados (poison message, payload inesperado, bug que siempre explota, o un dependiente caído mucho tiempo).

**Cómo investigar:**
1. En la UI de Management → la **DLQ** → mirá un mensaje (payload + headers; suele venir el motivo del descarte en los headers `x-death`).
2. Cruzá con los **logs del consumidor** que la alimenta (`kubectl logs -n dev <pod> -f`) en la ventana de tiempo del fallo.
3. Decidí: ¿es un bug (fix + reproceso) o un dato inválido (descartar)? Reprocesar suele ser re-publicar el mensaje a la cola original una vez corregida la causa.

### Síntoma 2 — "Una cola crece y no baja" (consumidor caído/lento)

**Qué significa:** los mensajes entran pero no se consumen al mismo ritmo.

**Cómo investigar:**
1. UI de Management → **Queues** → mirá *messages ready* (encolados) vs *unacked* (en vuelo) y las tasas.
2. `kubectl get pods -n dev` → ¿el consumidor está `Running`? ¿`CrashLoopBackOff`?
3. `kubectl logs -n dev <pod>` → ¿está lanzando excepciones (nack en loop)? ¿está lento (esperando a un tercero)?
4. ¿`unacked` alto y estable? El consumidor tomó mensajes pero no ackea: está colgado procesando. ¿`ready` alto y `unacked` 0? No hay consumidor vivo.

### Síntoma 3 — "Un evento no llega / el flujo se cortó"

**Qué significa:** publicaste (o creés que publicaste) pero el siguiente servicio no reacciona.

**Cómo investigar (seguí el camino del mensaje):**
1. ¿El productor **publicó**? Mirá sus logs y, si aplica, la tabla **`outbox_events`**: ¿quedó un evento sin marcar como enviado? (entonces el problema es la publicación, no el consumo). El scheduler de respaldo (3s/máx 3) debería reintentar.
2. ¿El exchange tiene el **binding** correcto a la cola? Un binding mal armado (routing key equivocada en un topic) hace que el mensaje se publique **y se pierda** sin llegar a ninguna cola. Verificá en la UI → Exchanges → Bindings.
3. ¿La cola destino existe y tiene consumidor? (Síntoma 2.)
4. ¿Quedó en la **DLQ**? (Síntoma 1.)

> **El reflejo correcto:** ante cualquier problema, recorré el camino que dibujaste en la Etapa 6 — productor → exchange → binding → cola → consumidor — y en cada salto preguntá "¿llegó hasta acá?". El primer salto donde la respuesta es "no" es tu problema.

---

## 📖 Glosario de una página (para imprimir y pegar al lado del monitor)

| Término | En una línea |
|---|---|
| **Evento** | Hecho de negocio que ya pasó; inmutable, en pasado (`OnPaymentRequestReceivedEvent`). |
| **Command** | Orden de "hacé esto"; puede rechazarse. En GWP, `record` inmutable. |
| **Query** | Pregunta sin efectos; lee estado. |
| **Mensaje** | El "sobre" (JSON + metadatos) que transporta un evento por el broker. |
| **Exchange** | La central de correo: recibe del productor y rutea a colas. |
| **Queue (cola)** | Casillero durable donde el mensaje espera al consumidor. |
| **Binding** | Regla que conecta exchange ↔ cola (con o sin patrón de routing key). |
| **Routing key** | Etiqueta del mensaje que el exchange usa para rutear (en webhook = `providerCode`). |
| **fanout** | Exchange que copia a TODAS las colas atadas; ignora routing key. |
| **topic** | Exchange que rutea por patrón de routing key (`*`, `#`). |
| **direct** | Exchange que rutea por routing key exacta. |
| **Productor / Consumidor** | Quien publica / quien lee mensajes. |
| **ack / nack** | "Procesado OK, borralo" / "falló, re-encolá o mandá a DLQ". |
| **Prefetch** | Cuántos mensajes sin-ack tiene un consumidor en vuelo a la vez. |
| **DLQ** | Cola de descarte para mensajes que fallan repetidamente; red de seguridad. |
| **at-least-once** | Garantía: el mensaje llega ≥1 vez (puede duplicarse). |
| **Idempotencia** | Procesar N veces = mismo efecto que 1 vez. Contramedida del at-least-once. |
| **Consistencia eventual** | El sistema converge a un estado coherente *al rato*, no al instante. |
| **Transactional Outbox** | Persistir el evento en la misma TX que la entidad; publicar después (con reintento). |
| **Dual write** | El problema de escribir a base + broker sin atomicidad; lo resuelve el Outbox. |
| **Backoff exponencial** | Reintentar esperando cada vez más (1s, 2s, 4s…). |
| **Hexagonal (Ports & Adapters)** | El dominio define puertos; el mundo exterior los implementa. Dependencias hacia adentro. |
| **Puerto / Adapter** | Interface que el negocio necesita / implementación concreta (JPA, HTTP, RabbitMQ). |
| **CQRS** | Separar comandos (escriben) de queries (leen). |
| **Aggregate Root** | Dueño de la consistencia de un agregado; en GWP, el payment-service. |
| **Strategy** | Una interfaz, muchas implementaciones intercambiables (los 12 extractores). |
| **StatefulSet** | Recurso K8s para pods con identidad/almacenamiento estable (`rabbitmq-0`, `postgres-0`). |
| **NodePort / ClusterIP / Headless** | Service expuesto al nodo / interno al cluster / sin IP (para StatefulSet). |
| **ConfigMap / Secret** | Config no sensible / sensible inyectada a los pods. |

---

## 📂 Qué buscar en el código (para la semana)

- Para validar el ejercicio del proveedor nuevo: compará la **estructura del `mercadopago-adapter`** con cómo se conectan los **eventos de dominio** en el payment-service. Confirmá que el payment-service **no menciona "mercadopago"** en su lógica de negocio.
- Ubicá la **interfaz del extractor de metadatos** y contá sus implementaciones (deberían ser 12). Ese es el punto de extensión por proveedor en el notification-service.
- Revisá la config de **DLQ** y de **`outbox_events`** otra vez, ahora con la mira puesta en *cómo investigarías* un problema real.

---

## ❓ Preguntas para verificar que entendiste

1. Para agregar el proveedor "PagoYa", ¿qué tocás en cada uno de los 4 servicios? ¿Cuál es el que más cambia y cuál casi no cambia, y por qué?
2. ¿Por qué el exchange de webhooks **tiene que ser `topic`** (y no `fanout`) para que el ejercicio del proveedor nuevo funcione limpio?
3. Ves mensajes en la DLQ. Enumerá los pasos para investigar la causa.
4. Una cola tiene `ready` alto y `unacked` en 0. ¿Qué está pasando? ¿Y si fuera `unacked` alto y estable?
5. Un evento "no llega" al siguiente servicio. ¿Cuál es el camino que recorrés salto por salto para encontrar dónde se cortó?

---

## ✍️ Mini-ejercicio (cierre del curso)

Sin mirar el documento, dibujá el **sistema completo** en una hoja: los 4 servicios, RabbitMQ en el medio, PostgreSQL colgando del payment-service, MercadoPago a la derecha del adapter, y el cliente arriba. Dibujá las flechas de **un** flujo completo a elección (el que más te costó) con sus exchanges y colas. Después abrí la Etapa 6 y **corregite**. Lo que te falte o equivoques es exactamente lo que conviene repasar primero cuando entres al código.

---

**Fin de las etapas.** Las respuestas a todas las preguntas de verificación están en `99-respuestas.md`.
