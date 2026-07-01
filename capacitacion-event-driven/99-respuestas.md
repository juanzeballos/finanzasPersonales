# Respuestas a las preguntas de verificación

> Leé estas respuestas **después** de intentar las preguntas vos. Son guías, no dogma: si tu redacción dice lo mismo con otras palabras, está perfecto.

---

## Etapa 0 — Por qué eventos

1. **Disponibilidad atada a MercadoPago.** Porque en el monolito la llamada a MercadoPago es **sincrónica y bloqueante** dentro del request: si MercadoPago tarda o está caído, tu endpoint tarda o falla, aunque la solicitud era válida. GWP rompe la atadura porque el gateway **publica un evento y responde `202` al instante**; hablar con MercadoPago pasa a ser tarea asíncrona del adapter, que reintenta cuando el proveedor vuelve. La disponibilidad del gateway ya no depende de la de MercadoPago.

2. **`202` vs `200`.** `200 OK` dice "terminé, acá está el resultado". `202 Accepted` dice "**recibí tu pedido y me hago cargo**, pero todavía no terminé". Es honesto con la naturaleza asíncrona: el resultado (el QR, la confirmación) llega después, por el webhook del cliente.

3. **Los cuatro problemas:** acoplamiento temporal, escalado en bloque, fallos en cascada y asincronía artesanal (a mano con `BlockingQueue`/`Executor`, sin durabilidad).

4. **El costo principal** es la **consistencia eventual** (más debugging distribuido y complejidad operativa). Vale la pena en pagos porque **no perder un mensaje** y **no caerse cuando un proveedor se cae** importan más que la simplicidad de un monolito; el sistema converge a un estado correcto sin perder información.

5. **`BlockingQueue` ≠ RabbitMQ** porque la `BlockingQueue` vive en el **heap de tu proceso**: si el proceso muere, los ítems se pierden, no hay ack/nack ni reintento garantizado, no es compartible entre servicios ni durable. RabbitMQ es externo, durable, con entrega garantizada (at-least-once) y DLQ.

---

## Etapa 1 — Vocabulario de mensajería

1. **Productor → exchange (no a la cola)** para **desacoplar** al productor de los consumidores: no necesita saber cuántas colas hay ni quién consume. Agregás/quitás consumidores cambiando bindings, sin tocar al productor. La indirección es lo que da la flexibilidad de ruteo.

2. **`fanout` con rk `""`:** en fanout la routing key **se ignora** (por eso va vacía); el mensaje se copia a todas las colas atadas. Para sumar un consumidor nuevo, **atás otra cola** al exchange y listo — el gateway ni se entera.

3. **ack vs nack:** ack = "procesado OK, el broker borra el mensaje"; nack = "falló, se re-encola o va a DLQ según config". Si el consumidor **se cae antes de ack o nack**, el broker detecta la conexión muerta y **redan** el mensaje a otro consumidor (no se pierde).

4. **at-least-once ⇒ idempotencia** porque, como un mensaje puede entregarse **más de una vez** (caída antes del ack, redelivery, reintentos, Outbox que republica), procesarlo dos veces no debe duplicar efectos. La única forma segura es que el procesamiento sea idempotente.

5. **DLQ** aísla los mensajes que fallan repetidamente para que **un poison message no gire infinito bloqueando la cola** ni se pierda. Quedan apartados y visibles para inspección humana.

---

## Etapa 2 — RabbitMQ en este proyecto

1. **Beans de topología:** al arrancar, un `RabbitAdmin` **crea en el broker** los exchanges/colas/bindings declarados (si no existen). Conviene en código porque la topología queda **versionada, reproducible y revisable**, no dependiente de clicks manuales que nadie recuerda.

2. **Ack con `auto`:** lo hace **Spring** (el listener container) automáticamente: si el método retorna sin excepción → **ack**; si lanza excepción → **nack** (y según config, re-encola o DLQ).

3. **JSON, no objetos Java**, porque los servicios son **procesos/contenedores separados** que no comparten memoria; el contrato común es el JSON sobre el cable. Implica que cambiar un campo de un evento es un **cambio de contrato**: todos los consumidores tienen que entender la nueva forma (versionado de eventos).

4. **5.000 ready, 0 unacked:** no hay **consumidor vivo** tomando mensajes (o todos están desconectados). Los mensajes entran y se acumulan porque nadie los consume.

5. **`max-concurrency`** define cuántos consumidores concurrentes puede levantar un listener cuando hay backlog. Se relaciona con el escalado de la Etapa 0: permite **procesar más rápido la cola saturada** sumando consumidores, sin escalar el resto.

---

## Etapa 3 — Hexagonal + Clean + CQRS

1. **Dominio sin Spring/JPA/RabbitMQ** para que la **lógica de negocio sea pura y testeable sin infraestructura** (le pasás mocks de los puertos) y para poder **cambiar base/broker/proveedor sin tocar el negocio**. Ganás testeo rápido y resistencia al cambio.

2. **Puerto de entrada:** cómo el mundo externo dispara el negocio — en el payment-service, los `@RabbitListener` que reciben eventos. **Puerto de salida:** lo que el negocio necesita del mundo — el repositorio PostgreSQL y el publicador de eventos. (Los adapters los implementan.)

3. **Command / Event / Query:** command = "hacé esto" (puede rechazarse, imperativo); event = "esto ya pasó" (hecho inmutable, pasado); query = "decime esto" (sin efectos). `OnPaymentRequestReceivedEvent` es un **evento** porque describe un **hecho consumado** (se recibió la solicitud), no una orden que alguien pueda rechazar.

4. **Dependencias:** `adapters → application → domain`, **nunca al revés**. Así el dominio no conoce detalles externos y se mantiene puro y estable; lo volátil (frameworks, proveedores) queda en los bordes.

5. **Commands `record` inmutables** porque se **serializan y pasan entre hilos/servicios**: la inmutabilidad los hace seguros para concurrencia (no hay estado mutable compartido) y predecibles (una vez creado el command, su contenido no cambia).

---

## Etapa 4 — Recorrido de los 4 microservicios

1. **Gateway sin BD, payment-service con BD:** el gateway solo **traduce HTTP→evento** y no es dueño de ningún estado, así que no necesita base (es stateless y escalable trivialmente). El payment-service es el **Aggregate Root**: dueño de la verdad del estado de cada pago, por eso necesita persistencia (PostgreSQL).

2. **Cómo le llegan cosas al payment-service:** (a) por **mensajes** de las 9 colas que consume, y (b) por sus **schedulers internos** (`ExpiredOrdersScheduler` 5s, `RefundInProgressScheduler` 60s) — el tiempo como disparador.

3. **El adapter encapsula** lo del proveedor: por ejemplo, el **formato de la API REST de MercadoPago** (endpoints, payloads), la **autenticación con token/secret por cliente**, la **validación de firma HMAC**, y los **reintentos/DLQ**. El resto del sistema no debería conocer nada de eso.

4. **Strategy de los 12 extractores:** evita un `switch`/`if-else` gigante por proveedor. Cada proveedor tiene **su implementación** de la interfaz "extractor de metadatos", elegida en runtime. Agregar un proveedor = **una clase nueva**, sin tocar las otras ni arriesgar regresiones.

5. **`on_notification_attempt_completed`** es **auditoría**: registra el resultado de cada intento de notificación (exitoso o no). No hace falta para el "happy path", pero da trazabilidad, métricas y soporte (¿le avisamos al cliente?, ¿cuántos reintentos?, ¿falló?).

---

## Etapa 5 — Patrones

1. **Dual write:** hay que escribir a **dos sistemas** (PostgreSQL + RabbitMQ) que no comparten transacción. Un `@Transactional` solo cubre la base; si la app cae **entre el commit y el publish**, guardaste el estado pero **perdiste el evento** (o publicaste un evento sobre algo que no se commiteó). No hay atomicidad entre los dos sistemas.

2. **Outbox = single write:** el evento se inserta en `outbox_events` **en la misma transacción** que la entidad → una sola escritura atómica. La publicación real se hace después (publish inmediato vía `ApplicationEvent`); si falla, el **scheduler de respaldo (3s, máx 3 intentos)** publica los pendientes desde la tabla. El evento **nunca se pierde**.

3. **at-least-once ⇒ idempotencia:** porque el mismo mensaje puede llegar varias veces. Idempotente: "confirmar la orden #123" (queda confirmada una vez, lleguen 1 o 3 avisos). No idempotente: "sumar $100 al saldo" (3 entregas = +$300). En pagos, lo segundo sería cobrar de más.

4. **Consistencia eventual:** el sistema no está coherente en *todo instante*, pero **converge** al rato. Es aceptable porque a cambio ganás desacople y disponibilidad sin transacciones distribuidas. Se nota, por ejemplo, en la ventana entre que el payment-service **confirma** el pago y el notification-service **avisa** al cliente.

5. **A la DLQ** llega un mensaje que **falla repetidamente** (se agotan reintentos) o se rechaza sin re-encolar. Una DLQ que **crece es alarma** porque significa que hay mensajes que ningún reintento pudo procesar: bug, dato inválido o dependiente caído — requiere intervención humana.

---

## Etapa 6 — Flujos end-to-end

1. **Flujo 1, respuesta al cliente:** el cliente recibe **`202` en el paso 1**, apenas el gateway publica el evento (mucho antes de que el QR exista). Se entera de que el QR está listo **por su webhook**, cuando el notification-service le manda el POST firmado.

2. **`GET /v1/orders/{id}` en vez de confiar en el webhook:** porque el webhook es solo un **aviso** (puede ser falsificado, llegar duplicado o estar incompleto). El adapter **valida la firma HMAC** y luego **consulta el estado real** a MercadoPago para actuar sobre el dato autoritativo, no sobre el aviso.

3. **Flujo 3 lo dispara un scheduler** del payment-service (`ExpiredOrdersScheduler` 5s / `RefundInProgressScheduler` 60s): el disparador es **el tiempo**, no un request HTTP. Eso lo distingue de los demás, que arrancan con una acción del cliente o de MercadoPago.

4. **`RefundInProgressScheduler` (60s):** MercadoPago puede procesar reembolsos de forma **asíncrona**, dejándolos "en progreso". El scheduler hace un **loop de consulta** periódica del estado hasta que el reembolso se cierra, para que el sistema no quede esperando indefinidamente un aviso que quizá no llega.

5. **Los 5 casilleros de cualquier salto:** (1) **evento** emitido, (2) **exchange**, (3) **routing key**, (4) **cola** destino, (5) **caso de uso/consumidor** que lo procesa.

---

## Etapa 7 — Infraestructura

1. **StatefulSets** porque RabbitMQ y PostgreSQL tienen **estado e identidad estable**: necesitan nombre fijo (`rabbitmq-0`, `postgres-0`) y **almacenamiento persistente** que sobreviva reinicios. Un Deployment común trata a los pods como intercambiables y efímeros, lo que rompería una base o un broker.

2. **NodePort vs ClusterIP:** NodePort **expone un puerto hacia afuera** del cluster (accesible desde el nodo); ClusterIP es **solo interno**. El api-gateway usa NodePort (`:30000`→`:8080`) porque es el **único punto de entrada HTTP** y tiene que ser alcanzable desde afuera (vía Nginx).

3. **`port-forward 15672`** abre un túnel desde tu `localhost:15672` a la UI de Management de RabbitMQ. Una vez conectado, mirás **exchanges (tipos/bindings)** y **colas (profundidad, ready/unacked)** para ver el sistema en vivo y diagnosticar.

4. **Cola del payment-service crece, la del adapter en 0:** el **payment-service no está consumiendo** (caído, en `CrashLoopBackOff`, o lanzando excepciones en loop). Confirmás con `kubectl get pods -n dev` y `kubectl logs -n dev <pod-payment-service>`.

5. **Tokens y webhook secrets por cliente** viven en **Secrets** de Kubernetes (no en ConfigMaps) porque son **datos sensibles**; los Secrets están pensados para credenciales (control de acceso, no se exponen como config plana).

---

## Etapa 8 — Consolidar

1. **Agregar "PagoYa":** el que **más cambia** es un **nuevo adapter** (`pagoya-adapter`) que encapsula todo lo del proveedor. El **api-gateway** casi no cambia (solo un **binding** nuevo por la routing key del proveedor en el exchange topic). El **payment-service** casi no cambia (razona en eventos de dominio genéricos). El **notification-service** suma **una Strategy** (un extractor) si la metadata difiere.

2. **El webhook debe ser `topic`** porque la routing key es el `providerCode`: con topic podés **agregar un binding** para rutear las notificaciones del proveedor nuevo a su propia cola **sin tocar el gateway**. Con `fanout` todas las colas recibirían todo (no podrías separar por proveedor) y con `direct` igual sirve por key exacta, pero `topic` da la flexibilidad de patrones por si mañana querés agrupar proveedores.

3. **Investigar la DLQ:** (1) abrir un mensaje en la UI (payload + headers `x-death` con el motivo), (2) cruzar con los **logs del consumidor** en la ventana del fallo, (3) decidir bug (fix + reproceso) vs dato inválido (descartar).

4. **`ready` alto + `unacked` 0:** no hay consumidor vivo tomando mensajes. **`unacked` alto y estable:** el consumidor **tomó** mensajes pero **no ackea** — está colgado/lento procesando (probablemente esperando a un tercero o trabado).

5. **Evento que no llega — el camino:** recorrer **productor → exchange → binding → cola → consumidor**, preguntando en cada salto "¿llegó hasta acá?". Chequear: ¿publicó? (logs / `outbox_events`), ¿el binding/routing key es correcto? (UI Exchanges), ¿la cola tiene consumidor? (Síntoma 2), ¿terminó en la DLQ? (Síntoma 1). El primer "no" marca el problema.

---

## Apéndice A — Fundamentos de Docker y Kubernetes

1. **Imagen / contenedor / registry:** la **imagen** es la plantilla inmutable (como el `.jar` empaquetado con la JVM y el SO mínimo: el plato servido entero); el **contenedor** es esa imagen **en ejecución** (el `.jar` corriendo); el **registry** es el repositorio de imágenes (tu Nexus/Artifactory, pero de imágenes). El **multi-stage** separa el build del runtime: la primera etapa (pesada: GraalVM + toolchain) **compila el binario nativo**, la segunda **copia solo el binario** a una imagen mínima → imagen chica que arranca en milisegundos.

2. **Cómo el Service encuentra a sus pods:** por **labels y selectors**, no por IP. El Service tiene un `selector` (ej. `app=payment-service`) y rutea dinámicamente a **todo pod que matchee ese label**. Cuando un pod muere y nace otro con el mismo label, entra solo a la rotación: por eso el sistema es *self-healing* y nadie toca IPs.

3. **Cómo encuentra el payment-service a Postgres/RabbitMQ:** por el **DNS interno** del cluster. En su config no hay IPs sino **nombres de Service** (`postgres-service:5432`, `rabbitmq-service:5672`); el DNS resuelve ese nombre a la IP del Service, que reparte a los pods.

4. **Falso.** Un Secret está en **base64**, que es solo *codificación* (se decodifica trivialmente, no es cifrado). La diferencia real con un ConfigMap es de **manejo y control de acceso** (RBAC, no se loguea, se puede cifrar en reposo si el cluster lo habilita), no de ocultamiento. Por eso los tokens/webhook secrets van en Secret: para tratarlos con cuidado, no porque base64 los proteja.

5. **Postgres como StatefulSet:** un Pod es **efímero** — si muere, nace otro con otra IP y **su disco se pierde**. Una base no puede perder datos en cada reinicio. El **StatefulSet** le da al pod **identidad estable** (`postgres-0`) y un **PVC** propio atado a él: si `postgres-0` se recrea, **se reconecta al mismo PVC/disco** y recupera los datos. Un Deployment trata a los pods como intercambiables y sin disco propio, así que no sirve para estado.

6. **`ImagePullBackOff` en Minikube:** porque Minikube corre en su **propia VM/contenedor con su propio almacén de imágenes**, separado del Docker de tu host. Construiste la imagen en *tu* Docker; Minikube la busca en *el suyo* (o en un registry remoto) y no la encuentra. Se resuelve **cargándola** (`minikube image load <img>`), **construyéndola dentro del Docker de Minikube** (`minikube docker-env` + `docker build`), y poniendo `imagePullPolicy: IfNotPresent`/`Never` para que no intente bajarla de internet.
