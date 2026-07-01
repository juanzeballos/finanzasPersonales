# Navegación por fecha en "Registrar" (+ ajuste "El mes") — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** En la pantalla "Registrar", elegir un día (flechas + calendario nativo) para ver y cargar los gastos de ese día; más un cambio mínimo en "El mes".

**Architecture:** Se hilvana una `fecha` opcional por el mismo camino asíncrono que la `divisa`: `POST /gastos` → columna `Entrada.fecha_gasto` → worker → `procesar_texto(..., fecha=...)` que la usa al crear el `Gasto` (default `hoy_local()`). En el frontend (JS puro) se agrega `state.fechaSel` (default hoy), una barra `‹ fecha ›` con `<input type="date">` nativo, y el filtrado/carga por ese día.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2, pytest, SQLite (dev/test) / Postgres (prod), JS puro + CSS.

**Spec:** `docs/superpowers/specs/2026-06-30-navegacion-por-fecha-registrar-design.md`

## Global Constraints

- **Rama:** `gastos-fecha-divisa` (sale de `dev`; el trabajo de divisas ya está en `dev`).
- **Entorno:** Windows + PowerShell. Intérprete: `.\.venv\Scripts\python.exe`. Correr la app local: `.\run.ps1` (SQLite).
- **Fecha "hoy" del backend:** SIEMPRE `hoy_local()` (de `app/tiempo.py`), NUNCA `date.today()` (hay un fix de zona horaria de Argentina que depende de esto).
- **⚠️ Git en esta sesión es inestable** (devuelve estado inconsistente). Cada paso de commit está escrito como corresponde, pero **verificá el commit** (`git log --oneline -1`) tras cada uno; si el entorno no commitea confiable, hacé los commits en una terminal normal.
- **Tests backend:** el worker NO corre en tests; se prueban funciones (`procesar_texto`, `_procesar_una`) y endpoints directo. Fixtures en `tests/conftest.py`: `Session`, `client`, `auth_client`.
- **Front:** JS puro sin framework → verificación **manual** en el navegador.

---

## Task 1: Backend — columna `Entrada.fecha_gasto` + migración

**Files:**
- Modify: `app/models.py` (clase `Entrada`)
- Create: `scripts/migrate_fecha_gasto_sqlite.py`
- Test: `tests/test_fecha.py` (crear)

**Interfaces:**
- Produces: `models.Entrada.fecha_gasto: date | None` (columna nullable; `None` = usar hoy).

- [ ] **Step 1: Escribir el test que falla** — crear `tests/test_fecha.py`:

```python
from datetime import date

from app import models


def test_entrada_fecha_gasto_default_none(Session):
    db = Session()
    e = models.Entrada(usuario_id=1, texto="café 1500", divisa="ARS")
    db.add(e)
    db.commit()
    db.refresh(e)
    assert e.fecha_gasto is None


def test_entrada_fecha_gasto_explicita(Session):
    db = Session()
    e = models.Entrada(usuario_id=1, texto="hotel", divisa="ARS", fecha_gasto=date(2026, 1, 5))
    db.add(e)
    db.commit()
    db.refresh(e)
    assert e.fecha_gasto == date(2026, 1, 5)
```

- [ ] **Step 2: Correr para ver que falla**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_fecha.py -v`
Expected: FAIL (`TypeError: 'fecha_gasto' is an invalid keyword argument`).

- [ ] **Step 3: Agregar la columna en `app/models.py`** — en la clase `Entrada`, después de la línea de `divisa` (y antes de `creado_en`):

```python
    fecha_gasto: Mapped[date | None] = mapped_column(Date, nullable=True)  # fecha elegida al cargar; None = hoy
```

(`Date` y `date` ya están importados en el módulo.)

- [ ] **Step 4: Correr para verificar que pasa**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_fecha.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Crear `scripts/migrate_fecha_gasto_sqlite.py`:**

```python
"""Migración local (SQLite dev): agrega la columna fecha_gasto a entradas.

create_all no modifica tablas existentes. Idempotente: si ya existe, lo informa y sigue.
"""
import sqlite3

con = sqlite3.connect("gastos.db")
try:
    con.execute("ALTER TABLE entradas ADD COLUMN fecha_gasto DATE")
    print("entradas: columna fecha_gasto agregada")
except sqlite3.OperationalError as e:
    print(f"entradas: {e}")   # 'duplicate column name' si ya existía
con.commit()
con.close()
```

- [ ] **Step 6: Correr la migración local**

Run: `.\.venv\Scripts\python.exe scripts/migrate_fecha_gasto_sqlite.py`
Expected: `entradas: columna fecha_gasto agregada` (o "duplicate column name").

> Deploy (Postgres, en Task 6): `ALTER TABLE entradas ADD COLUMN IF NOT EXISTS fecha_gasto DATE;`

- [ ] **Step 7: Commit**

```bash
git add app/models.py scripts/migrate_fecha_gasto_sqlite.py tests/test_fecha.py
git commit -m "feat: columna fecha_gasto en entradas + migracion sqlite"
```

---

## Task 2: Backend — `GastoTexto.fecha` + `procesar_texto` usa la fecha

**Files:**
- Modify: `app/schemas.py` (`GastoTexto`)
- Modify: `app/clasificador.py` (`procesar_texto`)
- Test: `tests/test_fecha.py` (ampliar)

**Interfaces:**
- Consumes: `models.Entrada.fecha_gasto` (Task 1).
- Produces: `schemas.GastoTexto.fecha: str | None = None`; `clasificador.procesar_texto(db, texto, usuario_id, divisa_chip="ARS", fecha=None)` — `fecha` es un `date | None`; los `Gasto` se crean con `fecha or hoy_local()`.

- [ ] **Step 1: Escribir los tests que fallan** — agregar a `tests/test_fecha.py`:

```python
from app import clasificador, schemas
from app.tiempo import hoy_local


def _stub_ia(monkeypatch, items):
    def fake(_texto):
        return schemas.ClasificacionIA(items=[schemas.ItemIA(**i) for i in items], missing=[])
    monkeypatch.setattr(clasificador.ia, "clasificar", fake)


def test_gastotexto_fecha_default_none():
    assert schemas.GastoTexto(texto="café 1500").fecha is None


def test_procesar_usa_fecha_dada(Session, monkeypatch):
    db = Session()
    _stub_ia(monkeypatch, [{"description": "Hotel", "amount": 120, "category": "Viajes",
                            "tipo": "prescindible", "emoji": "🏨"}])
    res = clasificador.procesar_texto(db, "hotel 120", usuario_id=1, fecha=date(2026, 1, 5))
    assert res["created"][0].fecha == date(2026, 1, 5)


def test_procesar_sin_fecha_usa_hoy(Session, monkeypatch):
    db = Session()
    _stub_ia(monkeypatch, [{"description": "Café", "amount": 1500, "category": "Café",
                            "tipo": "prescindible", "emoji": "☕"}])
    res = clasificador.procesar_texto(db, "café 1500", usuario_id=1)
    assert res["created"][0].fecha == hoy_local()
```

- [ ] **Step 2: Correr para ver que falla**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_fecha.py -v`
Expected: FAIL (`GastoTexto` sin `fecha`; `procesar_texto` sin arg `fecha`).

- [ ] **Step 3: Editar `app/schemas.py`** — en `GastoTexto`, agregar el campo:

```python
class GastoTexto(BaseModel):
    """Lo que manda el chat: texto libre (puede tener varios gastos)."""
    texto: str
    divisa: str = "ARS"   # divisa elegida en el chip (el texto puede pisarla)
    fecha: str | None = None   # YYYY-MM-DD; None = hoy
```

- [ ] **Step 4: Editar `app/clasificador.py`** — cambiar la firma de `procesar_texto` y usar la fecha en AMBOS constructores de `Gasto`:

Firma (línea ~62):
```python
def procesar_texto(db: Session, texto: str, usuario_id: int, divisa_chip: str = "ARS", fecha=None) -> dict:
```
Al inicio del cuerpo, después de `divisa = detectar_divisa(texto) or divisa_chip`, agregar:
```python
    fecha = fecha or hoy_local()
```
Y en los dos `models.Gasto(...)`, cambiar `fecha=hoy_local()` por `fecha=fecha`. (Atajo sin-IA línea ~75 y camino IA línea ~101.)

- [ ] **Step 5: Correr para verificar que pasa**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_fecha.py -v`
Expected: PASS (5 passed en total en el archivo).

- [ ] **Step 6: Commit**

```bash
git add app/schemas.py app/clasificador.py tests/test_fecha.py
git commit -m "feat: procesar_texto usa la fecha elegida (default hoy_local)"
```

---

## Task 3: Backend — `POST /gastos` parsea la fecha + worker la pasa

**Files:**
- Modify: `app/routers/gastos.py` (`crear_gasto`)
- Modify: `app/worker.py` (`_procesar_una`)
- Test: `tests/test_fecha.py` (ampliar)

**Interfaces:**
- Consumes: `GastoTexto.fecha` (Task 2), `Entrada.fecha_gasto` (Task 1), `procesar_texto(..., fecha=)` (Task 2).

- [ ] **Step 1: Escribir los tests que fallan** — agregar a `tests/test_fecha.py`:

```python
def test_post_guarda_fecha_en_entrada(auth_client, Session):
    r = auth_client.post("/gastos", json={"texto": "hotel 120", "divisa": "USD", "fecha": "2026-01-05"})
    assert r.status_code == 200, r.text
    db = Session()
    entrada = db.query(models.Entrada).order_by(models.Entrada.id.desc()).first()
    assert entrada.fecha_gasto == date(2026, 1, 5)


def test_post_sin_fecha_deja_none(auth_client, Session):
    r = auth_client.post("/gastos", json={"texto": "café 1500"})
    assert r.status_code == 200, r.text
    db = Session()
    entrada = db.query(models.Entrada).order_by(models.Entrada.id.desc()).first()
    assert entrada.fecha_gasto is None


def test_post_fecha_invalida_400(auth_client):
    r = auth_client.post("/gastos", json={"texto": "café 1500", "fecha": "no-es-fecha"})
    assert r.status_code == 400
```

- [ ] **Step 2: Correr para ver que falla**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_fecha.py -k post -v`
Expected: FAIL (la fecha no se guarda; no hay validación).

- [ ] **Step 3: Editar `crear_gasto` en `app/routers/gastos.py`** (líneas ~66-75):

```python
@router.post("/gastos", response_model=schemas.EntradaOut)
def crear_gasto(payload: schemas.GastoTexto, db: Session = Depends(get_db),
                usuario: models.Usuario = Depends(usuario_actual)):
    """Guarda el texto como entrada 'pendiente' del usuario y responde al instante."""
    fecha_gasto = None
    if payload.fecha:
        try:
            fecha_gasto = date.fromisoformat(payload.fecha)
        except ValueError:
            raise HTTPException(status_code=400, detail="Fecha inválida (usá YYYY-MM-DD)")
    entrada = models.Entrada(usuario_id=usuario.id, texto=payload.texto.strip(),
                             estado="pendiente", divisa=payload.divisa, fecha_gasto=fecha_gasto)
    db.add(entrada)
    db.commit()
    db.refresh(entrada)
    return entrada
```

Asegurate de que `date` esté importado en el archivo. Arriba dice `from datetime import date` — si no está, agregalo.

- [ ] **Step 4: Editar `_procesar_una` en `app/worker.py`** (línea ~24) — pasar la fecha:

```python
        res = procesar_texto(db, entrada.texto, entrada.usuario_id, entrada.divisa, entrada.fecha_gasto)
```

- [ ] **Step 5: Correr para verificar que pasa (y toda la suite)**

Run: `.\.venv\Scripts\python.exe -m pytest -v`
Expected: todos PASS.

- [ ] **Step 6: Commit**

```bash
git add app/routers/gastos.py app/worker.py tests/test_fecha.py
git commit -m "feat: POST /gastos parsea fecha y el worker la propaga"
```

---

## Task 4: Frontend — ajuste "El mes" (Por categoría primero y por defecto)

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Cambiar el default de vista** (línea ~79 en `state`):

```javascript
  vista: "categoria",
```

- [ ] **Step 2: Reordenar los botones del toggle** en `renderMes` (líneas ~424-427) — "Por categoría" primero:

```javascript
      <div class="seg-toggle">
        <button class="${state.vista === "categoria" ? "active" : ""}" data-action="vista" data-vista="categoria">Por categoría</button>
        <button class="${state.vista === "control" ? "active" : ""}" data-action="vista" data-vista="control">Por control</button>
      </div>
```

- [ ] **Step 3: Verificación manual**

Run: `.\run.ps1`, abrir http://localhost:8000, ir a "El mes":
- Abre con **"Por categoría"** activo (barras por categoría) y el botón "Por categoría" a la izquierda.
- Tocar "Por control" sigue funcionando (barras por tipo).

- [ ] **Step 4: Commit**

```bash
git add static/app.js
git commit -m "feat(front): El mes abre en Por categoria por defecto"
```

---

## Task 5: Frontend — barra de fecha, navegación, calendario nativo y carga por día

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Agregar `state.fechaSel`** (en `state`, junto a `divisa`, ~línea 86):

```javascript
  fechaSel: null,   // YYYY-MM-DD; se inicializa a hoy en init()
```

- [ ] **Step 2: Agregar constantes y helpers de fecha** (junto a `MESES`, cerca del tope, ~línea 14):

```javascript
const DIAS_SEM = ["dom","lun","mar","mié","jue","vie","sáb"];
const MESES_ABREV = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];
// f = "YYYY-MM-DD". Construir Date con componentes explícitos evita el corrimiento por UTC.
function fmtFechaBar(f) {
  const [y, m, d] = f.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  return `${DIAS_SEM[dt.getDay()]} ${d} ${MESES_ABREV[m - 1]} ${y}`;
}
function addDias(f, n) {
  const [y, m, d] = f.split("-").map(Number);
  const dt = new Date(y, m - 1, d + n);   // JS normaliza el desborde de días/meses
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
}
```

- [ ] **Step 3: Inicializar `fechaSel` a hoy en `init()`** — en el IIFE `init` (junto a la lectura de la divisa guardada, ~línea 745), agregar:

```javascript
  state.fechaSel = todayStr();
```

- [ ] **Step 4: Filtrar Registrar por `fechaSel` y ajustar el total** — en `renderRegistrar` (líneas ~285-291):

Reemplazar el filtro de `hoy` y el label. La línea del filtro (`.filter((e) => e.fecha === todayStr())`) pasa a:
```javascript
  const esHoy = state.fechaSel === todayStr();
  const hoy = state.expenses
    .filter((e) => e.fecha === state.fechaSel)
    .sort((a, b) => a.id - b.id);
```
La línea del total (dentro del composer, ~línea 336) cambia el label:
```javascript
      ${hoy.length > 0 ? `<div class="total-line"><span class="lbl">${esHoy ? "Hoy llevás" : "Ese día llevás"}</span><span class="num" style="font-weight:600">${totalHoyStr}</span></div>` : ""}
```

- [ ] **Step 5: Renderizar la barra de fecha arriba del chip** — en `renderRegistrar`, antes del `const chip = ...` (~línea 325), agregar:

```javascript
  const barraFecha = `
    <div class="fecha-bar">
      <button class="fecha-arrow" data-action="fecha-dia" data-dir="-1" aria-label="Día anterior">${icon("left", 16)}</button>
      <div class="fecha-label">
        ${icon("calendar", 15)}<span>${fmtFechaBar(state.fechaSel)}</span>
        <input type="date" id="fecha-input" value="${state.fechaSel}" aria-label="Elegir fecha" />
      </div>
      <button class="fecha-arrow" data-action="fecha-dia" data-dir="1" aria-label="Día siguiente">${icon("right", 16)}</button>
    </div>`;
```

Y en el `return` de `renderRegistrar`, anteponer la barra al chip:
```javascript
  return `${barraFecha}${chip}
    <div class="scroll" id="scroll">${chat}</div>
```
(el resto del `return` — composer — queda igual.)

> El `<input type="date">` se posiciona (con CSS de Task 6) transparente sobre `.fecha-label`, así tocar la fecha abre el calendario nativo directamente, sin depender de `showPicker()`.

- [ ] **Step 6: Setter y handler de flechas** — agregar `setFecha` junto a `setDivisa` (~línea 573):

```javascript
function setFecha(f) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(f)) return;
  state.fechaSel = f;
  render();
}
```

En el dispatcher de click (junto a `else if (a === "month")`, ~línea 660), agregar:
```javascript
  else if (a === "fecha-dia") { setFecha(addDias(state.fechaSel, Number(el.dataset.dir))); }
```

- [ ] **Step 7: Escuchar el cambio del input de fecha** — en el listener `document.addEventListener("change", ...)` existente (el de `edit-divisa`/`edit-cat`), agregar al inicio del handler:

```javascript
  if (t.id === "fecha-input") { if (t.value) setFecha(t.value); return; }
```

- [ ] **Step 8: Mandar la fecha al crear el gasto** — `postGasto` (línea ~136):

```javascript
const postGasto = (texto, divisa, fecha) =>
  api("/gastos", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ texto, divisa, fecha }) });
```
Y en `enviar` (línea ~512):
```javascript
    const entrada = await postGasto(texto, state.divisa, state.fechaSel);   // responde al instante (pendiente)
```

- [ ] **Step 9: Verificación manual**

Run: `.\run.ps1`
- En "Registrar" aparece la barra `‹ 📅 <hoy> ›` arriba del chip de divisa.
- Flecha `‹` va al día anterior, `›` al siguiente; la lista muestra los gastos de ese día (y el label dice "Ese día llevás" cuando no es hoy, "Hoy llevás" cuando sí).
- Tocar la fecha abre el calendario nativo; elegir un día salta a él.
- Con un día pasado seleccionado, cargar "café 1500" → el gasto queda en ESE día (navegá a hoy y no está; volvé al día elegido y sí está; verificá también en "El mes").

- [ ] **Step 10: Commit**

```bash
git add static/app.js
git commit -m "feat(front): barra de fecha en Registrar (navegar dias, calendario nativo, cargar por dia)"
```

---

## Task 6: Estilos + cache-busting + prueba integral + deploy

**Files:**
- Modify: `static/style.css`
- Modify: `static/index.html`

- [ ] **Step 1: Estilos de la barra de fecha** — agregar al final de `static/style.css` (reutiliza el look de `.month-nav`/`.divisa-bar`):

```css
/* --- Barra de fecha (Registrar) --- */
.fecha-bar { display: flex; align-items: center; justify-content: center; gap: 8px; margin: 8px 0; }
.fecha-arrow {
  font: inherit; display: flex; padding: 6px; cursor: pointer;
  border: 1px solid var(--border, #e3e1da); border-radius: 999px;
  background: var(--card, #fff); color: var(--text, #222);
}
.fecha-label {
  position: relative; display: flex; align-items: center; gap: 6px;
  padding: 6px 16px; border-radius: 999px; cursor: pointer;
  border: 1px solid var(--border, #e3e1da); background: var(--card, #fff);
  color: var(--text, #222); font-size: 14px; font-weight: 500;
}
/* input nativo transparente encima de la etiqueta: al tocarla abre el calendario del sistema */
.fecha-label input[type="date"] {
  position: absolute; inset: 0; width: 100%; height: 100%;
  opacity: 0; border: none; padding: 0; margin: 0; cursor: pointer;
}
```

> Si `style.css` usa otros nombres de variables de tema, ajustá los `var(--…)` a los reales (los fallbacks tras la coma evitan que se rompa).

- [ ] **Step 2: Bump de versión en `static/index.html`** (cache-busting; subir el `?v=` actual de css y js en uno):

```html
  <link rel="stylesheet" href="/static/style.css?v=8" />
```
```html
  <script src="/static/app.js?v=8"></script>
```
(Usá el número siguiente al que esté; si está en `?v=7`, poné `?v=8`.)

- [ ] **Step 3: Verificación manual (Ctrl+F5)**

Run: `.\run.ps1`
- La barra de fecha se ve prolija en modo claro y oscuro; el input nativo no se ve pero al tocar la fecha abre el calendario.
- Repaso integral: navegar días, elegir por calendario, cargar en un día pasado, y "El mes" abre en "Por categoría".

- [ ] **Step 4: Correr toda la suite de backend**

Run: `.\.venv\Scripts\python.exe -m pytest -v`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add static/style.css static/index.html
git commit -m "style(front): barra de fecha + cache-busting"
```

- [ ] **Step 6: Deploy al server** (cuando esté probado local)

```bash
git push origin gastos-fecha-divisa   # o el flujo de merge a dev/main que uses
```
En el server, ANTES de levantar la app nueva, migrar Postgres:
```
ssh -i $HOME\.ssh\hetzner -o IdentitiesOnly=yes root@135.181.34.126 "cd /opt/gastos && docker compose exec -T db psql -U gastos -d gastos -c \`"ALTER TABLE entradas ADD COLUMN IF NOT EXISTS fecha_gasto DATE;\`""
```
Y luego:
```
ssh -i $HOME\.ssh\hetzner -o IdentitiesOnly=yes root@135.181.34.126 "cd /opt/gastos && git pull && docker compose up -d --build"
```
Verificar en https://gastos-ia.duckdns.org.

---

## Notas de implementación

- **Zona horaria:** el backend usa `hoy_local()` (Argentina) como default de fecha; el front manda `state.fechaSel` que ya es una fecha civil `YYYY-MM-DD`, así que se guarda tal cual (sin conversión UTC). Los helpers de fecha del front construyen `Date` con componentes explícitos (`new Date(y, m-1, d)`) para no correr el día.
- **Asíncrono:** la fecha viaja en la `Entrada` (como la divisa) porque la clasificación la hace el worker después del POST.
- **YAGNI:** sin calendario custom, sin persistir la fecha entre recargas, sin límite de fechas futuras, sin editar la fecha de un gasto ya guardado.
