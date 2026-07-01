# Diseño — Navegación por fecha en "Registrar" (+ ajuste de "El mes")

> Fecha: 2026-06-30 · Rama de trabajo: `gastos-fecha-divisa` (sale de `dev`)
> Estado: aprobado por el usuario, listo para plan de implementación.

## Objetivo

En la pantalla **Registrar**, poder elegir un día y ver/cargar los gastos de ese día (no solo los de hoy). Más un cambio mínimo en "El mes".

- **A. Barra de fecha en Registrar:** arriba del chip de divisa, una barra `‹  📅 fecha  ›` con flechas para ir día a día y un calendario **nativo** al tocar la fecha.
- **B. Cargar en la fecha elegida:** los gastos nuevos se guardan con la fecha seleccionada, no con la de hoy.
- **C. Ajuste mínimo en "El mes":** el toggle "Por categoría" primero y seleccionado por defecto; "Por control" segundo.

## Contexto del código actual (lo relevante)

- **`static/app.js`** (JS puro, sin framework):
  - `renderRegistrar()`: hoy filtra `hoy = state.expenses.filter(e => e.fecha === todayStr())`, muestra el chip de divisa (`div.divisa-bar`), la lista de gastos del día y el composer. El total del día se arma agrupado por divisa (`totalHoyStr`) y se muestra con la etiqueta "Hoy llevás".
  - `renderMes()`: barra `month-nav` con `‹ [📅 MESES[m] año] ›` (acción `data-action="month" data-dir="±1"`). Tiene un toggle de vista (líneas ~404-426): `state.vista === "control"` → barras por tipo; si no, por categoría. Botones actuales: **"Por control"** (`data-vista="control"`) primero, **"Por categoría"** (`data-vista="categoria"`) segundo. Default `state.vista = "control"` (state, línea ~79).
  - Estado en `state`: `cursor {y,m}`, `divisa`, `divisaMes`, etc. Helpers: `todayStr()` → `YYYY-MM-DD`, `pad(n)`, `MESES` (nombres completos de meses), `fmt(monto, divisa)`.
  - Eventos delegados en `document` (click / keydown / input); dispatcher con cadena de `else if (a === "...")`.
- **Backend**: `POST /gastos` (`app/routers/gastos.py::crear_gasto`) guarda una `Entrada` `pendiente` con `texto` y `divisa`; responde al toque. El worker (`app/worker.py::_procesar_una`) llama `procesar_texto(db, entrada.texto, entrada.usuario_id, entrada.divisa)`. `procesar_texto` (`app/clasificador.py`) crea los `Gasto` con **`fecha=date.today()`** (fijo, en ambos caminos: atajo sin-IA y camino IA). `models.Entrada` ya tiene columnas `texto`, `estado`, `error`, `divisa`, `creado_en`. `schemas.GastoTexto` tiene `texto` y `divisa`.
- **Tests**: pytest montado en `tests/` (fixtures `Session`, `client`, `auth_client` en `conftest.py`). El worker no corre en tests; se prueban funciones/endpoints directo.

## A. Barra de fecha (UI en Registrar)

### Layout
Nueva barra **arriba del chip de divisa** (el chip pasa a ser el segundo elemento). Orden de arriba a abajo en Registrar: **barra de fecha → chip de divisa → lista de gastos del día → composer**.

```
‹        📅 mié 30 jun 2026        ›
```
- Flechas `‹` (`data-action="fecha-dia" data-dir="-1"`) y `›` (`data-dir="1"`): mueven **un día**.
- La fecha + ícono calendario son un botón que dispara el picker nativo.
- Formato de la etiqueta: `<día-semana abrev> <día> <mes abrev> <año>` (ej. "mié 30 jun 2026"). Se arma en JS con arrays `DIAS_SEM` y `MESES_ABREV` (nuevos), parseando `state.fechaSel` sin `new Date(str)` para evitar corrimientos de zona horaria (parsear los `YYYY-MM-DD` a mano).

### Calendario nativo
- Un `<input type="date">` **oculto** en el DOM con `value = state.fechaSel`.
- Al tocar la fecha/ícono: llamar `input.showPicker()` (soportado en navegadores modernos y móviles). Fallback si `showPicker` no existe: el input está posicionado sobre la etiqueta (opacity 0) y recibe el click igual.
- `change` del input → `setFecha(input.value)`.

### Estado y navegación
- Nuevo `state.fechaSel` (string `YYYY-MM-DD`), **default `todayStr()`**. No se persiste (al abrir la app siempre arranca en hoy).
- `setFecha(f)`: valida formato, setea `state.fechaSel`, `render()`.
- Navegación día a día: sumar/restar 1 día a `fechaSel` manipulando el string (parsear a componentes, usar `Date.UTC` o aritmética de días segura, re-formatear a `YYYY-MM-DD`). Evitar `new Date("YYYY-MM-DD")` directo (interpreta UTC y puede correr el día). Se permite cualquier fecha (pasado o futuro), sin límites.

### Lista y total del día
- `renderRegistrar` filtra por `state.fechaSel` en vez de `todayStr()`.
- El total del día: etiqueta **"Hoy llevás"** cuando `fechaSel === todayStr()`, y **"Ese día llevás"** (o similar) cuando es otro día.
- El empty-state ("Contame tu primer gasto del día") se mantiene; para un día pasado sin gastos alcanza con el mismo texto (o "No anotaste gastos ese día" — decisión menor, dejar el texto genérico).

## B. Cargar en la fecha elegida (backend)

Hilvanar la fecha igual que se hizo con `divisa`:

1. **`schemas.GastoTexto`**: agregar `fecha: str | None = None` (YYYY-MM-DD; si no viene, hoy).
2. **`models.Entrada`**: nueva columna `fecha_gasto: Mapped[date | None]` (nullable; null = hoy). **Migración** `ALTER TABLE entradas ADD COLUMN fecha_gasto DATE` (local SQLite + Postgres del server).
3. **`POST /gastos` (`crear_gasto`)**: parsear `payload.fecha` (si viene) a `date` y guardarla en `entrada.fecha_gasto`. Si el formato es inválido → 400.
4. **Worker (`_procesar_una`)**: pasar `entrada.fecha_gasto` a `procesar_texto`.
5. **`procesar_texto`**: nueva firma `procesar_texto(db, texto, usuario_id, divisa_chip="ARS", fecha=None)`; usar `fecha or date.today()` al crear los `Gasto` (ambos caminos), en vez de `date.today()` fijo.
6. **Front**: `postGasto(texto, divisa, fecha)` manda también `state.fechaSel`. En `enviar()`, pasar `state.fechaSel`.

> Nota: la clasificación es asíncrona (worker), por eso la fecha viaja en la `Entrada` (igual que la divisa), no se resuelve en el POST.

## C. Ajuste mínimo en "El mes"

- Cambiar el default: `state.vista = "categoria"` (en vez de `"control"`).
- Reordenar los dos botones del toggle en `renderMes`: **"Por categoría"** primero, **"Por control"** segundo. (Solo cambia el orden de las dos líneas de `<button>` y el default; la lógica `state.vista === "control" ? barras-por-tipo : barras-por-categoria` no cambia.)

## Resumen de cambios por archivo

| Archivo | Cambio |
|---|---|
| `app/models.py` | `Entrada.fecha_gasto` (Date, nullable) |
| `app/schemas.py` | `GastoTexto.fecha: str \| None = None` |
| `app/routers/gastos.py` | `crear_gasto` parsea/guarda `fecha_gasto` (400 si inválida) |
| `app/worker.py` | pasa `entrada.fecha_gasto` a `procesar_texto` |
| `app/clasificador.py` | `procesar_texto(..., fecha=None)`; `Gasto(fecha=fecha or date.today())` en ambos caminos |
| `static/app.js` | `state.fechaSel`; barra de fecha + picker nativo + navegación día a día; filtrar Registrar por `fechaSel`; etiqueta del total; `postGasto` manda fecha; **default `state.vista="categoria"` + reordenar toggle El mes** |
| `static/style.css` | estilos de la barra de fecha (reutilizar lo de `month-nav` / `divisa-bar`) |
| `static/index.html` | bump `?v=` de css/js (cache-busting) |
| migración | `ALTER TABLE entradas ADD COLUMN fecha_gasto DATE` (local + server) |

## Testing / verificación

- **Backend (pytest)**:
  - `POST /gastos` con `fecha` explícita → la `Entrada` guarda ese `fecha_gasto`.
  - `procesar_texto(..., fecha=date(2026,1,5))` → el `Gasto` creado tiene esa fecha; sin `fecha` → `date.today()`.
- **Front (manual, `.\run.ps1`)**:
  - Flechas ‹ › cambian el día; la lista muestra los gastos de ese día.
  - Tocar la fecha abre el calendario nativo; elegir un día salta a él.
  - Cargar un gasto en un día pasado → aparece en ese día (y no en hoy).
  - "El mes" abre en "Por categoría" seleccionado; el toggle sigue funcionando.

## Fuera de alcance (YAGNI)

- Calendario propio/custom (se eligió el nativo).
- Persistir la fecha seleccionada entre recargas (siempre arranca en hoy).
- Restringir fechas futuras.
- Editar la fecha de un gasto ya guardado (esto es solo para la carga; la edición de fecha podría ser otra feature).
