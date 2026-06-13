# Diseño — Edición de gastos, multi-divisa y pedido de monto faltante

> Fecha: 2026-06-13 · Rama: `oracle`
> Estado: aprobado por el usuario, listo para plan de implementación.

## Objetivo

Tres mejoras sobre la app de gastos, a probar **local (SQLite)** y después subir al server (Hetzner/Postgres):

- **A. Editar un gasto guardado:** poder cambiar **monto**, **categoría** y **divisa** (el **tipo** ya se edita hoy).
- **B. Multi-divisa con chip manual:** elegir la moneda (ARS/USD/BRL/EUR) desde un chip en la pantalla Registrar; el chip manda salvo que el texto nombre otra moneda explícitamente.
- **C. Pedir el monto cuando falta:** si se carga un gasto sin importe (ej. "café"), mostrar un aviso amable en vez del error actual.

## Contexto del código actual (lo relevante)

- **Modelo `Gasto`** (`app/models.py`): `descripcion`, `monto: float`, `categoria`, `tipo`, `emoji`. No hay divisa.
- **`ClasificacionAprendida`**: memoria por usuario (concepto → categoría/tipo/emoji). Es lo que "aprende".
- **`PATCH /gastos/{id}`** (`app/routers/gastos.py`): hoy **solo** cambia `tipo` (body `TipoUpdate`) y llama `aprender(...)`.
- **`DELETE /gastos/{id}`** ya existe.
- **`POST /gastos`**: guarda el texto como `Entrada` "pendiente" y responde al instante. Body actual: `{texto}`.
- **Worker** (`app/worker.py`): hilo que toma pendientes y llama `procesar_texto`. Si hay `created` → `procesado`; si hay `missing` → `error` con el texto del missing (mensaje pobre); si nada → `error` "No pude leer…".
- **`procesar_texto`** (`app/clasificador.py`): atajo sin-IA para conceptos ya aprendidos + 1 monto detectable; si no, llama a la IA. Los items sin `amount` se **descartan** (`if not item.amount: continue`) y van a `missing`.
- **IA** (`app/ia.py`): prompt fuerza "amount entero en pesos". `CATEGORIAS` (lista fija) vive en `app/schemas.py` y la usa el prompt.
- **Resumen** (`calcular_resumen` en `app/routers/gastos.py`): suma `monto` por tipo/categoría del mes, sin distinguir moneda.
- **Front** (`static/app.js`, JS puro, sin framework):
  - `cardHTML(e)`: card del gasto; al abrir muestra pastillas de tipo + borrar.
  - `renderRegistrar()`: lista de gastos del día + `composer` (input "Anotá un gasto…") abajo.
  - `renderMes()`: barras por tipo/categoría + total + consejo IA.
  - Tabs **Registrar / El mes** en el **header (arriba)**.
  - `fmt(n)` formatea `$` + locale es-AR, redondeando a entero.
  - `patchTipo`, `deleteGasto`, `api(...)`.

## A. Editar un gasto

### Backend
- **`schemas.GastoUpdate`** (reemplaza/extiende `TipoUpdate`): todos opcionales.
  ```python
  class GastoUpdate(BaseModel):
      monto: float | None = None
      categoria: str | None = None
      tipo: str | None = None
      divisa: str | None = None
  ```
- **`PATCH /gastos/{id}`** aplica solo los campos presentes:
  - `monto`: validar `> 0`.
  - `tipo`: `normalizar_tipo(...)`.
  - `categoria`: string no vacío (trim).
  - `divisa`: validar contra `{ARS, USD, BRL, EUR}`.
  - **Aprende** (`aprender(db, usuario_id, descripcion, categoria, tipo, emoji)`) **solo si cambió categoría o tipo**. Monto y divisa **no** se aprenden.
- `GastoOut` y `ItemIA`/modelo suman `divisa` (ver sección B).

### Frontend (`cardHTML` + handlers)
Al abrir la card, además de pastillas de tipo + borrar:
- **Monto:** campo numérico editable (valor actual). Guarda al `blur`/Enter vía `PATCH {monto}`.
- **Categoría:** `<select>` con `CATEGORIAS` + opción **"Otra…"** que muestra un input de texto libre. `PATCH {categoria}`.
- **Divisa:** selector compacto ARS/USD/BRL/EUR. `PATCH {divisa}`.
- Tras el PATCH, refrescar el estado local del gasto (como hace `setTipo` hoy).

### Categorías
Sumar a `CATEGORIAS` (en `app/schemas.py`, fuente única usada también por el prompt): **"Restaurante"**, **"Café"**, **"Viajes"** (las que falten y sean obvias). El texto libre cubre el resto.

## B. Multi-divisa (chip manual + override por texto)

### Reglas
- Monedas soportadas: **ARS, USD, BRL, EUR**. Una por gasto. Default **ARS**.
- **El chip define la divisa por defecto** de lo que se registra.
- **Si el texto nombra una moneda explícita, esa pisa al chip** para ese mensaje: `usd`/`u$s`/`US$`/`dólares`/`dolares` → USD; `reales`/`R$` → BRL; `euros`/`€` → EUR. Si no hay mención → divisa del chip.
- La divisa **no se aprende** (es por transacción).

### Backend
- **Modelo:** `Gasto.divisa: Mapped[str] = mapped_column(String, nullable=False, default="ARS")`.
- **Migración:** `ALTER TABLE gastos ADD COLUMN divisa VARCHAR NOT NULL DEFAULT 'ARS';`
  - `create_all` **no** agrega columnas a tablas existentes. Correr el ALTER a mano:
    - **Local (SQLite):** sobre `gastos.db` (SQLite soporta `ADD COLUMN` con default).
    - **Server (Postgres):** la base está vacía; el ALTER es instantáneo. (Igual sirve si hubiera datos.)
  - Documentar el comando en el handoff para no olvidarlo al deployar.
- **`parsing.detectar_divisa(texto) -> str | None`:** regex que devuelve la moneda explícita o `None`. Case-insensitive, con límites de palabra para no matchear de más.
- **`schemas.GastoTexto`** suma `divisa: str = "ARS"` (la del chip, que manda el front).
- **`schemas.GastoOut`** suma `divisa: str`.
- **`procesar_texto(db, texto, usuario_id, divisa_chip="ARS")`:**
  - `divisa = detectar_divisa(texto) or divisa_chip`.
  - Se asigna esa `divisa` a **todos** los `Gasto` creados de ese texto (tanto en el atajo sin-IA como en el camino IA). (Limitación aceptada: una sola divisa por mensaje; mezclar monedas en un mismo texto es caso raro.)
- **`POST /gastos`** pasa `payload.divisa` al worker. Como el worker procesa la `Entrada` de forma diferida, **guardar la divisa del chip en la `Entrada`**:
  - `Entrada.divisa: Mapped[str]` (default "ARS") + su ALTER, y el worker la pasa a `procesar_texto`. (Alternativa descartada: procesar sincrónico.)
- El **prompt de la IA no cambia** por divisa (la moneda sale del regex + chip, no de la IA). Sí conviene aflojar el "entero en pesos" para permitir decimales (ver formato).

### Frontend
- **Chip de divisa** en `renderRegistrar()`, **centrado, entre las tabs (header) y la lista de gastos** — es decir, arriba del `scroll`/lista del día.
  - Muestra la moneda actual (`ARS` por defecto), **sin flecha de desplegable**.
  - Al tocarlo, despliega las 4 opciones (ARS/USD/BRL/EUR). Elegir una la fija y cierra.
  - Recuerda la última elección en `localStorage` (patrón del theme, `THEME_KEY`).
  - Estado en `state` (ej. `state.divisa`), default ARS.
- **`POST /gastos`** manda `{texto, divisa: state.divisa}`.
- **Formato:** `fmt(monto, divisa)` (ver sección F). Las cards y totales del día usan la divisa de cada gasto.

## C. Resumen del mes por moneda

- **`calcular_resumen(db, mes, usuario_id, divisa="ARS")`** filtra por `Gasto.divisa == divisa`. Devolver además **la lista de monedas presentes** en el mes (`monedas: [..]`) para que el front sepa si mostrar el selector.
- **Endpoint resumen/informe** acepta `?divisa=` (default ARS) y lo pasa.
- **Front (`renderMes`):**
  - Calcular las monedas presentes en el mes.
  - Si hay **> 1 moneda**, mostrar un **selector ARS/USD/BRL/EUR** (default ARS) que filtra barras + total + consejo. Si hay una sola, no mostrarlo.
  - El consejo IA del mes se pide con `?divisa=` seleccionada.

## D. Pedir el monto cuando falta

- **Worker (`_procesar_una`)** cambia la prioridad:
  ```
  if res["missing"]:
      entrada.estado = "falta_monto"
      entrada.error  = mensaje_amable(res["missing"])   # ej: "Te faltó el monto de «café». Reescribilo con el importe, ej. «café 1500»."
  elif res["created"]:
      entrada.estado = "procesado"
  else:
      entrada.estado = "error"; entrada.error = "No pude leer ningún gasto ahí."
  ```
  (Si un mismo texto crea algunos gastos y deja otros sin monto, los creados se guardan igual y el aviso nombra los que faltaron.)
- **`/entradas`** ya devuelve `estado != "procesado"`, así que `falta_monto` se incluye.
- **Front (`renderRegistrar`)**: render de `falta_monto` como un **aviso suave/informativo** (no rojo de error), con el mensaje y botón de descartar (`del-entrada`). Distinto estilo que `error`.

## E. Resumen de cambios por archivo

| Archivo | Cambio |
|---|---|
| `app/models.py` | `Gasto.divisa`, `Entrada.divisa` (default "ARS") |
| `app/schemas.py` | `GastoUpdate`; `GastoTexto.divisa`; `GastoOut.divisa`; sumar categorías a `CATEGORIAS` |
| `app/parsing.py` | `detectar_divisa(texto)` |
| `app/clasificador.py` | `procesar_texto(..., divisa_chip)`; setear `divisa` en los `Gasto` |
| `app/worker.py` | pasar `entrada.divisa` a `procesar_texto`; estado `falta_monto` + mensaje amable |
| `app/routers/gastos.py` | `POST` guarda divisa en `Entrada`; `PATCH` generalizado; `calcular_resumen(divisa)` + monedas presentes |
| `app/routers/informe.py` | endpoint resumen acepta `?divisa=` |
| `app/ia.py` | aflojar "entero en pesos" (permitir decimales); el prompt no detecta moneda |
| `static/app.js` | chip de divisa + persistencia; edición de monto/categoría/divisa en card; `fmt(monto,divisa)`; selector de moneda en El mes; render `falta_monto` |
| `static/style.css` | estilos del chip, controles de edición, aviso `falta_monto` |
| migración | `ALTER TABLE gastos ADD COLUMN divisa ...`; idem `entradas` |

## F. Formato por moneda

- `ARS` → `$` sin decimales (locale es-AR, como hoy).
- `USD` → `US$` con 2 decimales.
- `BRL` → `R$` con 2 decimales.
- `EUR` → `€` con 2 decimales.
- `fmt(monto, divisa)` centraliza esto.

## Testing / verificación

1. **Local (`.\run.ps1`, SQLite):** correr la migración local primero.
2. **Edición:** cargar "café 1500", abrir la card, cambiar monto, categoría (incl. "Otra…" → "Restaurante") y divisa; verificar que persiste y que cambiar categoría/tipo "aprende" (el próximo "café" entra con la nueva categoría).
3. **Divisa chip:** poner chip en USD, escribir "hotel 120" → se guarda en USD; escribir "50 reales taxi" → se guarda en BRL (override por texto) aunque el chip esté en USD/ARS.
4. **Resumen por moneda:** mes con ARS + USD → aparece el selector; barras/total/consejo cambian según la moneda.
5. **Falta monto:** escribir solo "café" → aviso amable (no error rojo); el resto de un mensaje mixto se guarda.
6. **Deploy:** `git push origin oracle` → en el server `cd /opt/gastos && git pull && <ALTER TABLE> && docker compose up -d --build`.

## Fuera de alcance (YAGNI)

- Conversión entre monedas / cotizaciones.
- Varias monedas dentro de un mismo mensaje.
- Completar el monto faltante con campo inline o flujo conversacional (se eligió el aviso simple).
- Editar la fecha del gasto.
