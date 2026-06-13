# Edición de gastos, multi-divisa y pedido de monto faltante — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir editar monto/categoría/divisa de un gasto guardado, elegir la divisa (ARS/USD/BRL/EUR) con un chip manual (con override por texto), y mostrar un aviso amable cuando falta el monto.

**Architecture:** Backend FastAPI + SQLAlchemy: se agrega columna `divisa` a `gastos` y `entradas`, se detecta moneda explícita por regex, y el `PATCH` se generaliza. El worker pasa la divisa del chip (guardada en la `Entrada`) a `procesar_texto`. Frontend JS puro (`static/app.js`): chip de divisa con persistencia en localStorage, controles de edición en la card, selector de moneda en "El mes" y render del estado `falta_monto`.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2, pytest + FastAPI TestClient (nuevo), SQLite (dev/test) / Postgres (prod), JS puro + CSS.

**Spec:** `docs/superpowers/specs/2026-06-13-edicion-gastos-divisas-monto-faltante-design.md`

**Convención de trabajo:** probar local con `.\run.ps1` (SQLite) → `git push origin oracle` → en el server `cd /opt/gastos && git pull && <ALTER TABLE> && docker compose up -d --build`.

---

## File Structure

| Archivo | Responsabilidad / cambio |
|---|---|
| `requirements-dev.txt` (crear) | pytest para la suite de backend |
| `tests/__init__.py` (crear) | paquete de tests |
| `tests/conftest.py` (crear) | fixtures: DB de test aislada, `client`, `auth_client`, stub de IA |
| `tests/test_parsing.py` (crear) | tests de `detectar_divisa` |
| `tests/test_clasificador.py` (crear) | tests de `procesar_texto` con divisa |
| `tests/test_worker.py` (crear) | test del estado `falta_monto` |
| `tests/test_gastos_api.py` (crear) | tests de POST/PATCH/resumen |
| `app/models.py` | columnas `Gasto.divisa`, `Entrada.divisa` |
| `app/parsing.py` | función `detectar_divisa(texto)` |
| `app/schemas.py` | `GastoUpdate`, `GastoTexto.divisa`, `GastoOut.divisa`, ampliar `CATEGORIAS` |
| `app/clasificador.py` | `procesar_texto(..., divisa_chip)` setea `divisa` |
| `app/worker.py` | pasa `entrada.divisa`; estado `falta_monto` + mensaje |
| `app/routers/gastos.py` | POST guarda divisa en Entrada; PATCH generalizado; `calcular_resumen(divisa)` + monedas |
| `app/routers/informe.py` | endpoint resumen acepta `?divisa=` |
| `app/ia.py` | aflojar "entero en pesos" (permitir decimales) |
| `static/app.js` | chip de divisa, edición en card, `fmt(monto,divisa)`, selector de mes, render `falta_monto` |
| `static/style.css` | estilos del chip, edición, aviso `falta_monto` |
| `static/index.html` | bump de versión `?v=` de css/js (cache-busting) |

---

## Task 0: Montar pytest (infra de tests del backend)

**Files:**
- Create: `requirements-dev.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py` (se borra al final del task)

- [ ] **Step 1: Crear `requirements-dev.txt`**

```
pytest==8.3.4
```

- [ ] **Step 2: Instalar pytest en el venv**

Run: `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`
Expected: instala pytest sin errores.

- [ ] **Step 3: Crear `tests/__init__.py` (vacío)**

```python
```

- [ ] **Step 4: Crear `tests/conftest.py`**

```python
"""Fixtures de test: base SQLite aislada en memoria + TestClient sin worker.

OJO: usamos TestClient SIN `with` a propósito. El `with` dispararía el lifespan
de la app (que hace create_all sobre la base real ./gastos.db y arranca el worker).
Sin el context manager, el lifespan NO corre: los tests quedan aislados.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_db


@pytest.fixture()
def Session():
    """SessionLocal de test, bound a una SQLite en memoria compartida entre conexiones."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield TestingSession
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(Session):
    """TestClient con get_db apuntando a la base de test. Sin lifespan (sin worker)."""
    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_get_db
    c = TestClient(main.app)
    yield c
    main.app.dependency_overrides.clear()


@pytest.fixture()
def auth_client(client):
    """Client ya logueado (la cookie de sesión queda guardada en el client)."""
    r = client.post("/registro", json={"email": "t@t.com", "password": "test123", "nombre": "T"})
    assert r.status_code == 200, r.text
    return client
```

- [ ] **Step 5: Crear `tests/test_smoke.py`**

```python
def test_ping(client):
    r = client.get("/ping")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_registro_y_yo(auth_client):
    r = auth_client.get("/yo")
    assert r.status_code == 200
    assert r.json()["email"] == "t@t.com"
```

- [ ] **Step 6: Correr el smoke test**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_smoke.py -v`
Expected: PASS (2 passed).

- [ ] **Step 7: Borrar el smoke test y commitear la infra**

```bash
rm tests/test_smoke.py
git add requirements-dev.txt tests/__init__.py tests/conftest.py
git commit -m "test: montar pytest con TestClient y base SQLite aislada"
```

---

## Task 1: Columna `divisa` en los modelos + migración

**Files:**
- Modify: `app/models.py`
- Test: `tests/test_clasificador.py` (se crea acá un test mínimo de modelo; se amplía en Task 4)

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_clasificador.py`:

```python
from datetime import date

from app import models


def test_gasto_divisa_default_ars(Session):
    db = Session()
    g = models.Gasto(usuario_id=1, fecha=date.today(), descripcion="Café",
                      monto=1500, categoria="Café", tipo="prescindible", emoji="☕")
    db.add(g)
    db.commit()
    db.refresh(g)
    assert g.divisa == "ARS"


def test_entrada_divisa_explicita(Session):
    db = Session()
    e = models.Entrada(usuario_id=1, texto="120 usd hotel", divisa="USD")
    db.add(e)
    db.commit()
    db.refresh(e)
    assert e.divisa == "USD"
```

- [ ] **Step 2: Correr para verque falla**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_clasificador.py -v`
Expected: FAIL (`TypeError: 'divisa' is an invalid keyword argument` o `AttributeError`).

- [ ] **Step 3: Agregar la columna en `app/models.py`**

En la clase `Gasto`, después de `tipo` (línea ~34):

```python
    divisa: Mapped[str] = mapped_column(String, nullable=False, default="ARS")  # ARS|USD|BRL|EUR
```

En la clase `Entrada`, después de `estado` (línea ~47):

```python
    divisa: Mapped[str] = mapped_column(String, nullable=False, default="ARS")  # divisa elegida en el chip al cargar
```

- [ ] **Step 4: Correr para verificar que pasa**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_clasificador.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Crear el script de migración local `scripts/migrate_divisa_sqlite.py`**

```python
"""Migración local (SQLite dev): agrega la columna divisa a gastos y entradas.

create_all no modifica tablas existentes, así que esta columna hay que agregarla a mano.
Idempotente: si la columna ya existe, lo informa y sigue.
"""
import sqlite3

con = sqlite3.connect("gastos.db")
for tabla in ("gastos", "entradas"):
    try:
        con.execute(f"ALTER TABLE {tabla} ADD COLUMN divisa VARCHAR NOT NULL DEFAULT 'ARS'")
        print(f"{tabla}: columna divisa agregada")
    except sqlite3.OperationalError as e:
        print(f"{tabla}: {e}")   # 'duplicate column name' si ya existía
con.commit()
con.close()
```

- [ ] **Step 6: Correr la migración local**

Run: `.\.venv\Scripts\python.exe scripts/migrate_divisa_sqlite.py`
Expected: `gastos: columna divisa agregada` / `entradas: columna divisa agregada` (o "duplicate column name" si ya estaban).

> Nota deploy (Postgres en el server): el `git pull` no agrega columnas. Antes del `up -d --build` correr el ALTER en Postgres (ver Task 16, Step 4).

- [ ] **Step 7: Commit**

```bash
git add app/models.py tests/test_clasificador.py scripts/migrate_divisa_sqlite.py
git commit -m "feat: columna divisa en gastos y entradas (default ARS) + migracion sqlite"
```

---

## Task 2: `detectar_divisa` (regex de moneda explícita)

**Files:**
- Modify: `app/parsing.py`
- Test: `tests/test_parsing.py` (crear)

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_parsing.py`:

```python
import pytest

from app.parsing import detectar_divisa


@pytest.mark.parametrize("texto,esperado", [
    ("3 dolares de propina", "USD"),
    ("120 usd hotel", "USD"),
    ("pagué 50 us$ en el aeropuerto", "USD"),
    ("u$s 200 ahorro", "USD"),
    ("30 euros del museo", "EUR"),
    ("€10 cafe", "EUR"),
    ("50 reales el taxi", "BRL"),
    ("R$ 20 agua", "BRL"),
    ("café 1500", None),
    ("8 lucas de super", None),
    ("algo doloroso", None),   # no debe confundir 'dolor' con 'dolar'
])
def test_detectar_divisa(texto, esperado):
    assert detectar_divisa(texto) == esperado
```

- [ ] **Step 2: Correr para ver que falla**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_parsing.py -v`
Expected: FAIL (`ImportError: cannot import name 'detectar_divisa'`).

- [ ] **Step 3: Implementar en `app/parsing.py`**

Al final del archivo:

```python
# Monedas explícitas en el texto. El orden no importa (no se solapan).
# Símbolos ($,€) y abreviaturas no llevan \b porque $ y € no son caracteres de palabra.
_DIVISAS = [
    ("USD", re.compile(r"(?<![a-z])(usd|u\$s|us\$|d[oó]lares?)(?![a-z])", re.IGNORECASE)),
    ("EUR", re.compile(r"(?<![a-z])(eur|euros?)(?![a-z])|€", re.IGNORECASE)),
    ("BRL", re.compile(r"(?<![a-z])(brl|reales?)(?![a-z])|r\$", re.IGNORECASE)),
]


def detectar_divisa(texto: str) -> str | None:
    """Devuelve la moneda explícita mencionada en el texto, o None si no hay ninguna."""
    for codigo, patron in _DIVISAS:
        if patron.search(texto):
            return codigo
    return None
```

- [ ] **Step 4: Correr para verificar que pasa**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_parsing.py -v`
Expected: PASS (12 passed).

- [ ] **Step 5: Commit**

```bash
git add app/parsing.py tests/test_parsing.py
git commit -m "feat: detectar_divisa (USD/EUR/BRL por texto)"
```

---

## Task 3: Schemas (GastoUpdate, divisa en GastoTexto/GastoOut, categorías)

**Files:**
- Modify: `app/schemas.py`
- Test: `tests/test_gastos_api.py` (crear con un test de schema; se amplía en Tasks 6-8)

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_gastos_api.py`:

```python
from app import schemas


def test_gastotexto_divisa_default():
    assert schemas.GastoTexto(texto="café 1500").divisa == "ARS"


def test_gastoupdate_todos_opcionales():
    u = schemas.GastoUpdate()
    assert u.monto is None and u.categoria is None and u.tipo is None and u.divisa is None


def test_categorias_incluye_restaurante():
    assert "Restaurante" in schemas.CATEGORIAS
```

- [ ] **Step 2: Correr para ver que falla**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gastos_api.py -v`
Expected: FAIL (`AttributeError: ... 'divisa'` y `GastoUpdate` no existe).

- [ ] **Step 3: Editar `app/schemas.py`**

Ampliar `CATEGORIAS` (sumar al final, antes de "Otros"):

```python
CATEGORIAS = [
    "Supermercado", "Comida y delivery", "Restaurante", "Café", "Transporte", "Nafta",
    "Servicios", "Impuestos", "Alquiler", "Salud", "Educación", "Gimnasio",
    "Entretenimiento", "Ropa", "Hogar", "Suscripciones", "Viajes", "Otros",
]
```

En `GastoTexto`, agregar el campo:

```python
class GastoTexto(BaseModel):
    """Lo que manda el chat: texto libre (puede tener varios gastos)."""
    texto: str
    divisa: str = "ARS"   # divisa elegida en el chip (el texto puede pisarla)
```

Reemplazar `TipoUpdate` por `GastoUpdate` (mantener `TipoUpdate` NO hace falta; se usa solo en el PATCH):

```python
class GastoUpdate(BaseModel):
    """Body del PATCH: cualquier subconjunto de campos editables."""
    monto: float | None = None
    categoria: str | None = None
    tipo: str | None = None
    divisa: str | None = None
```

En `GastoOut`, agregar `divisa` después de `tipo`:

```python
    divisa: str
```

- [ ] **Step 4: Correr para verificar que pasa**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gastos_api.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add app/schemas.py tests/test_gastos_api.py
git commit -m "feat: GastoUpdate, divisa en schemas, mas categorias"
```

---

## Task 4: `procesar_texto` setea la divisa

**Files:**
- Modify: `app/clasificador.py`
- Test: `tests/test_clasificador.py` (ampliar)

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_clasificador.py`:

```python
from app import clasificador, schemas


def _stub_ia(monkeypatch, items, missing=None):
    """Reemplaza ia.clasificar por una respuesta fija."""
    def fake(_texto):
        return schemas.ClasificacionIA(
            items=[schemas.ItemIA(**i) for i in items],
            missing=missing or [],
        )
    monkeypatch.setattr(clasificador.ia, "clasificar", fake)


def test_procesar_usa_divisa_del_chip(Session, monkeypatch):
    db = Session()
    _stub_ia(monkeypatch, [{"description": "Hotel", "amount": 120, "category": "Viajes",
                            "tipo": "prescindible", "emoji": "🏨"}])
    res = clasificador.procesar_texto(db, "hotel 120", usuario_id=1, divisa_chip="USD")
    assert res["created"][0].divisa == "USD"


def test_procesar_texto_pisa_al_chip(Session, monkeypatch):
    db = Session()
    _stub_ia(monkeypatch, [{"description": "Taxi", "amount": 50, "category": "Transporte",
                            "tipo": "necesario", "emoji": "🚕"}])
    # chip en ARS, pero el texto dice "reales" -> BRL
    res = clasificador.procesar_texto(db, "50 reales el taxi", usuario_id=1, divisa_chip="ARS")
    assert res["created"][0].divisa == "BRL"
```

- [ ] **Step 2: Correr para ver que falla**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_clasificador.py -v`
Expected: FAIL (`procesar_texto() got an unexpected keyword argument 'divisa_chip'`).

- [ ] **Step 3: Editar `app/clasificador.py`**

Importar `detectar_divisa` (línea 13):

```python
from .parsing import detectar_divisa, extraer_montos, normalizar
```

Cambiar la firma y resolver la divisa al inicio de `procesar_texto`:

```python
def procesar_texto(db: Session, texto: str, usuario_id: int, divisa_chip: str = "ARS") -> dict:
    """Clasifica el texto y agrega el/los Gasto(s) del usuario a la sesión (sin commit).

    La divisa = mención explícita en el texto, si la hay; si no, la del chip.
    Devuelve {"created": [Gasto], "missing": [str]}. Puede lanzar excepción si la IA falla.
    """
    divisa = detectar_divisa(texto) or divisa_chip
```

En el atajo sin-IA, agregar `divisa=divisa` al crear el `Gasto`:

```python
            gasto = models.Gasto(
                usuario_id=usuario_id, fecha=date.today(), descripcion=fila.descripcion,
                monto=montos[0], categoria=fila.categoria, tipo=fila.tipo, emoji=fila.emoji,
                divisa=divisa,
            )
```

En el camino con IA, agregar `divisa=divisa` al crear el `Gasto`:

```python
        gasto = models.Gasto(
            usuario_id=usuario_id, fecha=date.today(), descripcion=descripcion,
            monto=float(item.amount), categoria=categoria, tipo=tipo, emoji=emoji,
            divisa=divisa,
        )
```

- [ ] **Step 4: Correr para verificar que pasa**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_clasificador.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add app/clasificador.py tests/test_clasificador.py
git commit -m "feat: procesar_texto setea divisa (texto pisa al chip)"
```

---

## Task 5: Worker — estado `falta_monto` con mensaje amable

**Files:**
- Modify: `app/worker.py`
- Test: `tests/test_worker.py` (crear)

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_worker.py`:

```python
from app import clasificador, models, schemas, worker


def test_falta_monto(Session, monkeypatch):
    db = Session()
    # IA: detecta "café" pero sin monto -> missing
    def fake(_texto):
        return schemas.ClasificacionIA(items=[], missing=["café"])
    monkeypatch.setattr(clasificador.ia, "clasificar", fake)

    entrada = models.Entrada(usuario_id=1, texto="café", divisa="ARS")
    db.add(entrada)
    db.commit()

    worker._procesar_una(db, entrada.id)
    db.refresh(entrada)

    assert entrada.estado == "falta_monto"
    assert "monto" in entrada.error.lower()
    assert "café" in entrada.error
```

- [ ] **Step 2: Correr para ver que falla**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_worker.py -v`
Expected: FAIL (`assert 'error' == 'falta_monto'`).

- [ ] **Step 3: Editar `app/worker.py`**

Importar la divisa al llamar y reordenar la lógica en `_procesar_una`. Reemplazar el bloque `try:` (líneas ~23-34):

```python
    try:
        res = procesar_texto(db, entrada.texto, entrada.usuario_id, entrada.divisa)
        if res["missing"]:
            faltan = ", ".join(f"«{m}»" for m in res["missing"])
            entrada.estado = "falta_monto"
            entrada.error = f"Te faltó el monto de {faltan}. Reescribilo con el importe, ej. «café 1500»."
        elif res["created"]:
            entrada.estado = "procesado"
            entrada.error = None
        else:
            entrada.estado = "error"
            entrada.error = "No pude leer ningún gasto ahí."
        db.commit()
```

> Nota: si un mismo texto crea gastos Y deja otros sin monto, los creados quedan guardados igual (ya se agregaron a la sesión) y el aviso nombra los que faltaron.

- [ ] **Step 4: Correr para verificar que pasa**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_worker.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add app/worker.py tests/test_worker.py
git commit -m "feat: worker pasa divisa y marca falta_monto con mensaje amable"
```

---

## Task 6: `POST /gastos` guarda la divisa del chip en la Entrada

**Files:**
- Modify: `app/routers/gastos.py`
- Test: `tests/test_gastos_api.py` (ampliar)

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_gastos_api.py`:

```python
def test_post_gasto_guarda_divisa_en_entrada(auth_client):
    r = auth_client.post("/gastos", json={"texto": "hotel 120", "divisa": "USD"})
    assert r.status_code == 200, r.text
    # la entrada queda pendiente; la leemos por /entradas
    entradas = auth_client.get("/entradas").json()
    assert entradas[-1]["estado"] == "pendiente"
```

> (No hay worker en los tests, así que la entrada queda "pendiente"; verificamos que el POST acepta `divisa` y crea la entrada.)

- [ ] **Step 2: Correr para ver que falla**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gastos_api.py::test_post_gasto_guarda_divisa_en_entrada -v`
Expected: FAIL (422 si el body no acepta `divisa`, o la entrada no se crea con divisa).

- [ ] **Step 3: Editar `crear_gasto` en `app/routers/gastos.py`** (líneas ~60-68)

```python
@router.post("/gastos", response_model=schemas.EntradaOut)
def crear_gasto(payload: schemas.GastoTexto, db: Session = Depends(get_db),
                usuario: models.Usuario = Depends(usuario_actual)):
    """Guarda el texto como entrada 'pendiente' del usuario y responde al instante."""
    entrada = models.Entrada(usuario_id=usuario.id, texto=payload.texto.strip(),
                             estado="pendiente", divisa=payload.divisa)
    db.add(entrada)
    db.commit()
    db.refresh(entrada)
    return entrada
```

- [ ] **Step 4: Correr para verificar que pasa**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gastos_api.py::test_post_gasto_guarda_divisa_en_entrada -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/routers/gastos.py tests/test_gastos_api.py
git commit -m "feat: POST /gastos guarda la divisa del chip en la entrada"
```

---

## Task 7: `PATCH /gastos/{id}` generalizado (monto/categoría/tipo/divisa)

**Files:**
- Modify: `app/routers/gastos.py`
- Test: `tests/test_gastos_api.py` (ampliar)

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_gastos_api.py` un helper para insertar un gasto directo en la base y los tests del PATCH:

```python
from datetime import date

from app import models


def _crear_gasto(Session, usuario_id, **kw):
    db = Session()
    defaults = dict(usuario_id=usuario_id, fecha=date.today(), descripcion="Café",
                    monto=1500, categoria="Café", tipo="prescindible", emoji="☕", divisa="ARS")
    defaults.update(kw)
    g = models.Gasto(**defaults)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g.id


def _uid(auth_client):
    return auth_client.get("/yo").json()["id"]


def test_patch_edita_monto_categoria_divisa(auth_client, Session):
    gid = _crear_gasto(Session, _uid(auth_client))
    r = auth_client.patch(f"/gastos/{gid}", json={"monto": 2000, "categoria": "Restaurante", "divisa": "USD"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["monto"] == 2000
    assert body["categoria"] == "Restaurante"
    assert body["divisa"] == "USD"


def test_patch_monto_invalido(auth_client, Session):
    gid = _crear_gasto(Session, _uid(auth_client))
    r = auth_client.patch(f"/gastos/{gid}", json={"monto": 0})
    assert r.status_code == 400


def test_patch_divisa_invalida(auth_client, Session):
    gid = _crear_gasto(Session, _uid(auth_client))
    r = auth_client.patch(f"/gastos/{gid}", json={"divisa": "GBP"})
    assert r.status_code == 400


def test_patch_categoria_aprende(auth_client, Session):
    gid = _crear_gasto(Session, _uid(auth_client))
    auth_client.patch(f"/gastos/{gid}", json={"categoria": "Restaurante"})
    # el concepto "café" debe quedar aprendido como Restaurante
    db = Session()
    fila = db.query(models.ClasificacionAprendida).filter_by(usuario_id=_uid(auth_client), concepto="cafe").first()
    assert fila is not None and fila.categoria == "Restaurante"
```

- [ ] **Step 2: Correr para ver que falla**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gastos_api.py -k patch -v`
Expected: FAIL (el PATCH actual solo entiende `tipo`).

- [ ] **Step 3: Editar `app/routers/gastos.py`**

Agregar la constante de divisas válidas cerca del tope (después de `router = APIRouter()`):

```python
DIVISAS = {"ARS", "USD", "BRL", "EUR"}
```

Reemplazar el endpoint `reclasificar_gasto` (líneas ~104-114) por:

```python
@router.patch("/gastos/{gasto_id}", response_model=schemas.GastoOut)
def editar_gasto(gasto_id: int, payload: schemas.GastoUpdate, db: Session = Depends(get_db),
                 usuario: models.Usuario = Depends(usuario_actual)):
    """Edita un gasto: monto, categoría, tipo y/o divisa (cualquier subconjunto)."""
    gasto = db.get(models.Gasto, gasto_id)
    if not gasto or gasto.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")

    cambio_clasificacion = False
    if payload.monto is not None:
        if payload.monto <= 0:
            raise HTTPException(status_code=400, detail="El monto tiene que ser mayor a 0")
        gasto.monto = payload.monto
    if payload.categoria is not None:
        cat = payload.categoria.strip()
        if not cat:
            raise HTTPException(status_code=400, detail="La categoría no puede estar vacía")
        gasto.categoria = cat
        cambio_clasificacion = True
    if payload.tipo is not None:
        gasto.tipo = normalizar_tipo(payload.tipo)
        cambio_clasificacion = True
    if payload.divisa is not None:
        if payload.divisa not in DIVISAS:
            raise HTTPException(status_code=400, detail="Divisa no soportada")
        gasto.divisa = payload.divisa

    if cambio_clasificacion:
        aprender(db, usuario.id, gasto.descripcion, gasto.categoria, gasto.tipo, gasto.emoji)
    db.commit()
    db.refresh(gasto)
    return gasto
```

- [ ] **Step 4: Correr para verificar que pasa**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gastos_api.py -k patch -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add app/routers/gastos.py tests/test_gastos_api.py
git commit -m "feat: PATCH /gastos generalizado (monto/categoria/tipo/divisa) + validacion"
```

---

## Task 8: Resumen por moneda (`calcular_resumen` + endpoint `?divisa=`)

**Files:**
- Modify: `app/routers/gastos.py`
- Modify: `app/routers/informe.py`
- Test: `tests/test_gastos_api.py` (ampliar)

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_gastos_api.py`:

```python
def test_resumen_filtra_por_divisa(auth_client, Session):
    uid = _uid(auth_client)
    hoy = date.today()
    mes = hoy.strftime("%Y-%m")
    _crear_gasto(Session, uid, monto=1000, divisa="ARS", fecha=hoy)
    _crear_gasto(Session, uid, monto=50, divisa="USD", fecha=hoy)

    ars = auth_client.get(f"/resumen?mes={mes}").json()       # default ARS
    usd = auth_client.get(f"/resumen?mes={mes}&divisa=USD").json()
    assert ars["total"] == 1000
    assert usd["total"] == 50
    assert set(ars["monedas"]) == {"ARS", "USD"}
```

- [ ] **Step 2: Correr para ver que falla**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gastos_api.py::test_resumen_filtra_por_divisa -v`
Expected: FAIL (`KeyError: 'monedas'` / total mezcla monedas).

- [ ] **Step 3: Editar `calcular_resumen` en `app/routers/gastos.py`** (líneas ~31-55)

```python
def calcular_resumen(db: Session, mes: str, usuario_id: int, divisa: str = "ARS") -> dict:
    """Totales del mes por categoría y por tipo, de ese usuario y esa divisa."""
    inicio, fin = rango_mes(mes)
    base = (
        (models.Gasto.usuario_id == usuario_id)
        & (models.Gasto.fecha >= inicio)
        & (models.Gasto.fecha < fin)
    )
    filtro = base & (models.Gasto.divisa == divisa)

    por_categoria = (
        db.query(models.Gasto.categoria, func.sum(models.Gasto.monto))
        .filter(filtro).group_by(models.Gasto.categoria).all()
    )
    por_tipo = (
        db.query(models.Gasto.tipo, func.sum(models.Gasto.monto))
        .filter(filtro).group_by(models.Gasto.tipo).all()
    )
    total = db.query(func.coalesce(func.sum(models.Gasto.monto), 0.0)).filter(filtro).scalar()
    monedas = [d for (d,) in db.query(models.Gasto.divisa).filter(base).distinct().all()]

    return {
        "mes": mes,
        "divisa": divisa,
        "monedas": sorted(monedas) or ["ARS"],
        "total": round(total or 0.0, 2),
        "por_categoria": [{"categoria": c, "total": round(t, 2)} for c, t in por_categoria],
        "por_tipo": [{"tipo": tp, "total": round(t, 2)} for tp, t in por_tipo],
    }
```

Editar el endpoint `resumen` (líneas ~127-130):

```python
@router.get("/resumen")
def resumen(mes: str = Query(..., description="Mes en formato YYYY-MM"),
            divisa: str = Query("ARS"), db: Session = Depends(get_db),
            usuario: models.Usuario = Depends(usuario_actual)):
    return calcular_resumen(db, mes, usuario.id, divisa)
```

- [ ] **Step 4: Editar el endpoint del informe en `app/routers/informe.py`** (líneas ~33-43)

```python
@router.post("/informe")
def generar_informe(mes: str = Query(..., description="Mes en formato YYYY-MM"),
                    divisa: str = Query("ARS"), db: Session = Depends(get_db),
                    usuario: models.Usuario = Depends(usuario_actual)):
    resumen = calcular_resumen(db, mes, usuario.id, divisa)
    if resumen["total"] == 0:
        return {"mes": mes, "consejo": "Todavía no hay gastos cargados en este mes."}
    try:
        consejo = ia.generar_informe(_formatear_resumen(resumen))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error de la IA: {e}")
    return {"mes": mes, "consejo": consejo, "resumen": resumen}
```

> Único cambio: se agrega el parámetro `divisa: str = Query("ARS")` y se pasa a `calcular_resumen`. El `try/except` y el resto quedan igual. (El texto del consejo sigue usando `$` y "pesos" en el prompt; es solo etiqueta — los números ya vienen filtrados por la divisa elegida. Mejorarlo queda fuera de alcance.)

- [ ] **Step 5: Correr para verificar que pasa**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gastos_api.py -v`
Expected: PASS (todos).

- [ ] **Step 6: Commit**

```bash
git add app/routers/gastos.py app/routers/informe.py tests/test_gastos_api.py
git commit -m "feat: resumen e informe filtran por divisa + lista de monedas del mes"
```

---

## Task 9: IA — permitir decimales (no forzar "entero en pesos")

**Files:**
- Modify: `app/ia.py`

(Sin test automatizado: depende del modelo. Cambio chico de prompt; se valida en la prueba manual de Task 15.)

- [ ] **Step 1: Editar `PROMPT_CLASIFICAR` en `app/ia.py`** (línea ~49)

Reemplazar la regla de "amount":

```python
- "amount": número del gasto, sin símbolos de moneda ni separadores de miles. Puede tener decimales
  (ej. 12.50). Interpretá slang argentino: "luca"/"k" = mil ("5 lucas" y "5k" = 5000,
  "30 lucas" = 30000, "media luca" = 500), "palo" = millón ("2 palos" = 2000000), "$3.500" = 3500.
```

- [ ] **Step 2: Commit**

```bash
git add app/ia.py
git commit -m "chore: prompt IA permite montos con decimales"
```

---

## Task 10: Front — `fmt(monto, divisa)` y formato por moneda

**Files:**
- Modify: `static/app.js`

(Front JS puro: verificación manual en el navegador con `.\run.ps1`.)

- [ ] **Step 1: Agregar la tabla de monedas y reescribir `fmt`** en `static/app.js` (reemplazar línea ~47)

```javascript
const CURRENCIES = {
  ARS: { sym: "$",   dec: 0 },
  USD: { sym: "US$", dec: 2 },
  BRL: { sym: "R$",  dec: 2 },
  EUR: { sym: "€",   dec: 2 },
};
const CUR_LIST = ["ARS", "USD", "BRL", "EUR"];
const fmt = (n, divisa = "ARS") => {
  const c = CURRENCIES[divisa] || CURRENCIES.ARS;
  return c.sym + (Number(n) || 0).toLocaleString("es-AR", {
    minimumFractionDigits: c.dec, maximumFractionDigits: c.dec,
  });
};
```

- [ ] **Step 2: Usar la divisa de cada gasto en `cardHTML`** (línea ~240)

```javascript
        <span class="card-amount num">${fmt(e.monto, e.divisa)}</span>
```

- [ ] **Step 3: Total del día por moneda en `renderRegistrar`** (línea ~286)

Reemplazar el cálculo de `totalHoy` y su línea. Cambiar la línea ~255:

```javascript
  const totalHoy = hoy.reduce((s, e) => s + e.monto, 0);
```

por un total agrupado por divisa, y la línea de display (~286):

```javascript
  const totalesHoy = {};
  hoy.forEach((e) => { totalesHoy[e.divisa] = (totalesHoy[e.divisa] || 0) + e.monto; });
  const totalHoyStr = Object.entries(totalesHoy).map(([d, m]) => fmt(m, d)).join(" · ");
```

Display (línea ~286):

```javascript
      ${hoy.length > 0 ? `<div class="total-line"><span class="lbl">Hoy llevás</span><span class="num" style="font-weight:600">${totalHoyStr}</span></div>` : ""}
```

- [ ] **Step 4: Incluir `divisa` en el snapshot anti-parpadeo** (línea ~89)

```javascript
    g: state.expenses.map((e) => [e.id, e.tipo, e.monto, e.descripcion, e.categoria, e.emoji, e.fecha, e.divisa]),
```

- [ ] **Step 5: Verificación manual**

Run: `.\run.ps1` y abrir http://localhost:8000
- Cargar "café 1500" → debe mostrarse `$1.500` (ARS, sin decimales).
- (La parte de otras monedas se prueba completa en Task 15.)

- [ ] **Step 6: Commit**

```bash
git add static/app.js
git commit -m "feat(front): fmt por divisa y total del dia agrupado por moneda"
```

---

## Task 11: Front — chip de divisa en la pantalla Registrar

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Estado del chip + clave de persistencia** (cerca de `THEME_KEY`, línea ~15)

```javascript
const DIVISA_KEY = "gastos-divisa-v1";
```

En `state` (objeto, ~línea 60) agregar:

```javascript
  divisa: "ARS",          // moneda elegida en el chip (Registrar)
  divisaOpen: false,      // chip desplegado o no
```

- [ ] **Step 2: Setter del chip con persistencia** (junto a `setTheme`, ~línea 494)

```javascript
function setDivisa(d) {
  state.divisa = d;
  state.divisaOpen = false;
  try { localStorage.setItem(DIVISA_KEY, d); } catch (e) {}
  render();
}
```

- [ ] **Step 3: Leer la divisa guardada en `init`** (dentro del IIFE init, ~línea 622, junto al theme)

```javascript
  try {
    const sd = localStorage.getItem(DIVISA_KEY);
    if (sd && CUR_LIST.includes(sd)) state.divisa = sd;
  } catch (e) {}
```

- [ ] **Step 4: Renderizar el chip entre las tabs y la lista** en `renderRegistrar`

El return de `renderRegistrar` (línea ~283) arranca con `<div class="scroll" id="scroll">${chat}</div>`. Insertar el chip ANTES del scroll:

```javascript
  const chip = `
    <div class="divisa-bar">
      <button class="divisa-chip ${state.divisaOpen ? "open" : ""}" data-action="divisa-toggle">${state.divisa}</button>
      ${state.divisaOpen ? `<div class="divisa-pop">
        ${CUR_LIST.map((d) => `<button class="divisa-opt ${d === state.divisa ? "active" : ""}" data-action="divisa-set" data-divisa="${d}">${d}</button>`).join("")}
      </div>` : ""}
    </div>`;

  return `
    ${chip}
    <div class="scroll" id="scroll">${chat}</div>
    <div class="composer">
      ${hoy.length > 0 ? `<div class="total-line"><span class="lbl">Hoy llevás</span><span class="num" style="font-weight:600">${totalHoyStr}</span></div>` : ""}
      <div class="row">
        <input id="composer-input" placeholder="Anotá un gasto…" autocomplete="off" value="${esc(state.draft)}" />
        <button class="send-btn" data-action="send">${icon("send", 17)}</button>
      </div>
    </div>`;
```

- [ ] **Step 5: Handlers del chip** en el dispatcher de click (línea ~567, junto a los `else if`)

```javascript
  else if (a === "divisa-toggle") { state.divisaOpen = !state.divisaOpen; render(); }
  else if (a === "divisa-set") { setDivisa(el.dataset.divisa); }
```

- [ ] **Step 6: Mandar la divisa del chip en `postGasto`** (línea ~116)

```javascript
const postGasto = (texto, divisa) =>
  api("/gastos", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ texto, divisa }) });
```

Y en `enviar` (donde llama `postGasto`, ~línea 444):

```javascript
    const entrada = await postGasto(texto, state.divisa);   // responde al instante (pendiente)
```

- [ ] **Step 7: Verificación manual**

Run: `.\run.ps1` → abrir Registrar.
- Aparece el chip "ARS" centrado entre las pestañas y los gastos, sin flecha.
- Al tocarlo se despliegan ARS/USD/BRL/EUR; elegir USD lo deja en "USD".
- Recargar la página → sigue en "USD" (localStorage).

- [ ] **Step 8: Commit**

```bash
git add static/app.js
git commit -m "feat(front): chip de divisa en Registrar con persistencia"
```

---

## Task 12: Front — editar monto, categoría y divisa en la card

**Files:**
- Modify: `static/app.js`

- [ ] **Step 0: Estado transitorio para "Otra…"** — en `state` (~línea 60) agregar:

```javascript
  editLibre: new Set(),   // ids de gastos cuyo select de categoría está en modo "Otra…" (texto libre)
```

- [ ] **Step 1: Helpers de PATCH** (junto a `patchTipo`, línea ~118)

```javascript
const patchGasto = (id, campos) =>
  api(`/gastos/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(campos) });
```

- [ ] **Step 2: Función genérica de edición** (junto a `setTipo`, ~línea 453)

```javascript
async function editarGasto(id, campos) {
  try {
    const upd = await patchGasto(id, campos);
    const i = state.expenses.findIndex((e) => e.id === id);
    if (i >= 0) state.expenses[i] = upd;
  } catch (e) { state.error = e.message || "No pude guardar el cambio."; }
  render();
}
```

- [ ] **Step 3: Controles de edición en el pie de la card** (`cardHTML`, dentro del `${abierto ? ...}`, línea ~242)

Reemplazar el bloque `card-foot` por (define `enLibre` al inicio de `cardHTML`, junto a `const abierto = ...`):

```javascript
  const enLibre = state.editLibre.has(e.id) || !CATEGORIAS.includes(e.categoria);
```

```javascript
      ${abierto ? `
      <div class="card-foot">
        <div class="type-pills">${pills}</div>
        <div class="edit-row">
          <input class="edit-monto num" type="number" step="0.01" min="0" value="${e.monto}" data-id="${e.id}" />
          <select class="edit-divisa" data-id="${e.id}">
            ${CUR_LIST.map((d) => `<option value="${d}" ${d === e.divisa ? "selected" : ""}>${d}</option>`).join("")}
          </select>
          <select class="edit-cat" data-id="${e.id}">
            ${CATEGORIAS.map((c) => `<option value="${esc(c)}" ${(!enLibre && c === e.categoria) ? "selected" : ""}>${esc(c)}</option>`).join("")}
            <option value="__otra__" ${enLibre ? "selected" : ""}>Otra…</option>
          </select>
          ${enLibre ? `<input class="edit-cat-libre" value="${esc(CATEGORIAS.includes(e.categoria) ? "" : e.categoria)}" data-id="${e.id}" placeholder="Categoría propia" />` : ""}
        </div>
        <button class="icon-btn" data-action="del" data-id="${e.id}" title="Eliminar">${icon("trash", 15)}</button>
      </div>` : ""}
```

Agregar la constante `CATEGORIAS` en el front (junto a `TIPOS`, ~línea 9):

```javascript
const CATEGORIAS = ["Supermercado","Comida y delivery","Restaurante","Café","Transporte","Nafta","Servicios","Impuestos","Alquiler","Salud","Educación","Gimnasio","Entretenimiento","Ropa","Hogar","Suscripciones","Viajes","Otros"];
```

- [ ] **Step 4: Listeners de los controles** (en el listener `change` y `blur`)

Agregar al final de la sección de eventos (después del listener `input`, ~línea 616):

```javascript
document.addEventListener("change", (ev) => {
  const t = ev.target;
  const id = t.dataset.id ? Number(t.dataset.id) : null;
  if (t.classList.contains("edit-divisa")) editarGasto(id, { divisa: t.value });
  else if (t.classList.contains("edit-cat")) {
    if (t.value === "__otra__") { state.editLibre.add(id); render(); }   // muestra el input libre
    else { state.editLibre.delete(id); editarGasto(id, { categoria: t.value }); }
  }
});

document.addEventListener("blur", (ev) => {
  const t = ev.target;
  const id = t.dataset.id ? Number(t.dataset.id) : null;
  if (t.classList.contains("edit-monto")) {
    const v = parseFloat(t.value);
    if (v > 0 && v !== state.expenses.find((e) => e.id === id)?.monto) editarGasto(id, { monto: v });
  } else if (t.classList.contains("edit-cat-libre")) {
    const v = t.value.trim();
    if (v) { state.editLibre.delete(id); editarGasto(id, { categoria: v }); }
  }
}, true);  // capture: el evento blur no burbujea
```

> Cómo funciona "Otra…": al elegirla, se agrega el id a `state.editLibre` y el `render()` muestra el `input.edit-cat-libre` (porque `enLibre` ahora es true). Al escribir la categoría y salir del input, se guarda y se saca el id del set. Elegir una categoría de la lista también limpia el set.

- [ ] **Step 5: Verificación manual**

Run: `.\run.ps1`
- Cargar "café 1500", abrir la card.
- Cambiar el monto a 1800 y salir del campo → se guarda (recargar y sigue 1800).
- Cambiar divisa a USD → la card muestra `US$`.
- Cambiar categoría a "Restaurante" desde el select → se guarda.
- Elegir "Otra…" → aparece el input libre; escribir "Bar" y salir → se guarda "Bar".

- [ ] **Step 6: Commit**

```bash
git add static/app.js
git commit -m "feat(front): editar monto/categoria/divisa en la card"
```

---

## Task 13: Front — selector de moneda en "El mes"

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Estado de la divisa del mes** en `state` (~línea 60)

```javascript
  divisaMes: "ARS",       // moneda seleccionada en la vista El mes
```

- [ ] **Step 2: Filtrar `renderMes` por la divisa del mes y calcular monedas presentes** (línea ~297)

Reemplazar el cálculo de `delMes` y `total`:

```javascript
  const delMesTodos = state.expenses.filter((e) => monthKey(e.fecha) === key);
  const monedasMes = [...new Set(delMesTodos.map((e) => e.divisa))];
  const divMes = monedasMes.includes(state.divisaMes) ? state.divisaMes : (monedasMes[0] || "ARS");
  const delMes = delMesTodos.filter((e) => e.divisa === divMes).sort((a, b) => b.id - a.id);
  const total = delMes.reduce((s, e) => s + e.monto, 0);
```

- [ ] **Step 3: Usar `divMes` en los `fmt` de la vista mes**

En `renderMes`, todos los `fmt(monto)` / `fmt(total)` de los importes del mes pasan a `fmt(x, divMes)`. En particular las líneas ~340 y ~354:

```javascript
        <div class="bar-right"><span class="bar-pct">${Math.round(pct)}%</span><span class="num" style="font-weight:600">${fmt(monto, divMes)}</span></div>
```
```javascript
        <div class="big num">${fmt(total, divMes)}</div>
```
Y la línea del insight prescindible (~360): `${fmt(prescindible.monto, divMes)}`.

- [ ] **Step 4: Render del selector (solo si hay >1 moneda)** — insertarlo junto al `nav` del mes (después de la línea ~319)

```javascript
  const selMoneda = monedasMes.length > 1 ? `
    <div class="mes-monedas">
      ${CUR_LIST.filter((d) => monedasMes.includes(d)).map((d) =>
        `<button class="moneda-tab ${d === divMes ? "active" : ""}" data-action="divisa-mes" data-divisa="${d}">${d}</button>`).join("")}
    </div>` : "";
```

Y meter `${selMoneda}` en el render, justo después de `${nav}` (donde se arma el `scroll` de la vista mes).

- [ ] **Step 5: Handler del selector** (dispatcher de click, ~línea 570)

```javascript
  else if (a === "divisa-mes") { state.divisaMes = el.dataset.divisa; state.consejo = null; render(); }
```

- [ ] **Step 6: Pasar la divisa al pedir consejo** — `postInforme` (línea ~122) y `pedirConsejo` (~línea 479)

```javascript
const postInforme = (mes, divisa) => api(`/informe?mes=${mes}&divisa=${divisa}`, { method: "POST" });
```

En `pedirConsejo`, calcular la divisa del mes actual y pasarla:

```javascript
async function pedirConsejo() {
  const key = `${state.cursor.y}-${pad(state.cursor.m + 1)}`;
  const monedasMes = [...new Set(state.expenses.filter((e) => monthKey(e.fecha) === key).map((e) => e.divisa))];
  const divMes = monedasMes.includes(state.divisaMes) ? state.divisaMes : (monedasMes[0] || "ARS");
  state.consejoLoading = true;
  render();
  try {
    const out = await postInforme(key, divMes);
    state.consejo = out.consejo;
  } catch (e) {
    state.consejo = "No pude generar el consejo. ¿Está el servidor corriendo?";
  } finally {
    state.consejoLoading = false;
    render();
  }
}
```

- [ ] **Step 7: Verificación manual**

Run: `.\run.ps1`
- Cargar un gasto en ARS y otro en USD (chip en USD) en el mes actual.
- Ir a "El mes": aparece el selector ARS/USD. Cambiar entre ellos → barras, total y consejo cambian según la moneda.
- Un mes con una sola moneda no muestra el selector.

- [ ] **Step 8: Commit**

```bash
git add static/app.js
git commit -m "feat(front): selector de moneda en El mes + consejo por divisa"
```

---

## Task 14: Front — render del estado `falta_monto`

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Separar `falta_monto` de los errores en `renderRegistrar`** (líneas ~257-279)

Después de `const errores = state.entradas.filter((e) => e.estado === "error");` agregar:

```javascript
  const faltaMonto = state.entradas.filter((e) => e.estado === "falta_monto");
```

Y en el array `chat` (donde se mapean `pendientes` y `errores`), agregar el render de `faltaMonto` como aviso suave (antes de `errores`):

```javascript
        ...faltaMonto.map((p) => `<div class="aviso info ${popOnce("fm" + p.id)}">${icon("alert", 15)}
               <span>${esc(p.error || "Te faltó el monto.")}</span>
               <button class="icon-btn" data-action="del-entrada" data-id="${p.id}" title="Descartar">${icon("trash", 14)}</button>
             </div>`),
```

- [ ] **Step 2: Incluir `falta_monto` en el snapshot** (ya cubierto: el snapshot usa `x.estado`, línea ~90, no requiere cambios).

- [ ] **Step 3: Verificación manual**

Run: `.\run.ps1`
- Escribir solo "café" (sin monto) → tras la clasificación aparece un aviso **suave** (no rojo) "Te faltó el monto de «café». Reescribilo con el importe…", con botón para descartar.
- Escribir "café 1500" → se guarda normal.

- [ ] **Step 4: Commit**

```bash
git add static/app.js
git commit -m "feat(front): aviso amable cuando falta el monto"
```

---

## Task 15: Estilos (chip, edición, aviso info) + cache-busting

**Files:**
- Modify: `static/style.css`
- Modify: `static/index.html`

- [ ] **Step 1: Agregar estilos al final de `static/style.css`**

```css
/* --- Chip de divisa (Registrar) --- */
.divisa-bar { position: relative; display: flex; justify-content: center; margin: 8px 0; }
.divisa-chip {
  font: inherit; font-weight: 700; font-size: 13px; letter-spacing: .5px;
  padding: 5px 16px; border-radius: 999px; cursor: pointer;
  background: var(--card, #fff); color: var(--text, #222);
  border: 1px solid var(--border, #e3e1da);
}
.divisa-chip.open { border-color: var(--accent, #5b8def); }
.divisa-pop {
  position: absolute; top: 110%; left: 50%; transform: translateX(-50%);
  display: flex; gap: 4px; padding: 5px; z-index: 10;
  background: var(--card, #fff); border: 1px solid var(--border, #e3e1da);
  border-radius: 12px; box-shadow: 0 6px 20px rgba(0,0,0,.12);
}
.divisa-opt {
  font: inherit; font-weight: 600; font-size: 13px; padding: 5px 12px;
  border: none; border-radius: 8px; cursor: pointer; background: transparent; color: var(--text, #222);
}
.divisa-opt.active { background: var(--accent, #5b8def); color: #fff; }

/* --- Controles de edición en la card --- */
.edit-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; }
.edit-row .edit-monto { width: 110px; }
.edit-row input, .edit-row select {
  font: inherit; padding: 6px 8px; border-radius: 8px;
  border: 1px solid var(--border, #e3e1da); background: var(--card, #fff); color: var(--text, #222);
}

/* --- Aviso suave (falta_monto) --- */
.aviso.info {
  background: var(--info-bg, #eef4ff); color: var(--info-fg, #2c4a8a);
  border: 1px solid var(--info-border, #cfe0ff);
}

/* --- Selector de moneda en El mes --- */
.mes-monedas { display: flex; justify-content: center; gap: 6px; margin: 8px 0; }
.moneda-tab {
  font: inherit; font-weight: 600; font-size: 13px; padding: 5px 14px;
  border-radius: 999px; cursor: pointer; background: transparent; color: var(--muted, #888);
  border: 1px solid var(--border, #e3e1da);
}
.moneda-tab.active { background: var(--accent, #5b8def); color: #fff; border-color: var(--accent, #5b8def); }
```

> Si `style.css` define variables de tema (`--card`, `--accent`, etc.) con otros nombres, ajustá los `var(--…)` a los reales. Los fallbacks tras la coma evitan que se rompa si falta alguna.

- [ ] **Step 2: Bump de versión en `static/index.html`** (cache-busting; subir `?v=6` → `?v=7` en css y js)

```html
  <link rel="stylesheet" href="/static/style.css?v=7" />
```
```html
  <script src="/static/app.js?v=7"></script>
```

- [ ] **Step 3: Verificación manual**

Run: `.\run.ps1` y recargar con Ctrl+F5.
- El chip, los controles de edición, el aviso info y el selector de mes se ven prolijos en modo claro y oscuro.

- [ ] **Step 4: Commit**

```bash
git add static/style.css static/index.html
git commit -m "style(front): chip de divisa, edicion, aviso info, selector de mes"
```

---

## Task 16: Prueba integral local + deploy al server

**Files:** ninguno (verificación + deploy)

- [ ] **Step 1: Correr toda la suite de backend**

Run: `.\.venv\Scripts\python.exe -m pytest -v`
Expected: todos PASS.

- [ ] **Step 2: Prueba integral manual** (`.\run.ps1`, IA_PROVIDER=groq en el entorno)

- [ ] Chip en ARS: "café 1500" → ARS; abrir card, cambiar monto/categoría (incl. "Otra…")/divisa, verificar persistencia y aprendizaje (próximo "café" entra con la categoría nueva).
- [ ] Chip en USD: "hotel 120" → se guarda en USD.
- [ ] Override: chip en ARS, "50 reales taxi" → BRL.
- [ ] "café" solo → aviso suave de falta de monto (no error rojo).
- [ ] "El mes" con ARS+USD → aparece selector; barras/total/consejo cambian por moneda.

- [ ] **Step 3: Push de la rama**

```bash
git push origin oracle
```

- [ ] **Step 4: Migrar Postgres en el server (ANTES del build)**

Run (PowerShell):
```
ssh -i $HOME\.ssh\hetzner -o IdentitiesOnly=yes root@135.181.34.126 "cd /opt/gastos && docker compose exec -T db psql -U gastos -d gastos -c \`"ALTER TABLE gastos ADD COLUMN IF NOT EXISTS divisa VARCHAR NOT NULL DEFAULT 'ARS';\`" -c \`"ALTER TABLE entradas ADD COLUMN IF NOT EXISTS divisa VARCHAR NOT NULL DEFAULT 'ARS';\`""
```
Expected: `ALTER TABLE` (x2).

- [ ] **Step 5: Deploy (pull + build)**

Run:
```
ssh -i $HOME\.ssh\hetzner -o IdentitiesOnly=yes root@135.181.34.126 "cd /opt/gastos && git pull && docker compose up -d --build"
```

- [ ] **Step 6: Verificar en producción**

Abrir https://gastos-ia.duckdns.org (Ctrl+F5), repetir un par de checks del Step 2 contra el server. `curl https://gastos-ia.duckdns.org/ping` → `{"status":"ok"}`.

- [ ] **Step 7: Actualizar el handoff** (`doc/05-handoff-hetzner.md`): anotar las features nuevas y la migración de la columna `divisa`. Commit + push.

---

## Notas de implementación

- **Worker en tests:** los tests usan `TestClient` sin `with`, así que el worker no corre; las funciones del worker se prueban llamándolas directo. No testeamos el flujo asíncrono POST→worker end-to-end (eso va en la prueba manual).
- **Una divisa por mensaje:** `detectar_divisa` mira todo el texto; si hay mención explícita, aplica a todos los gastos de ese mensaje (limitación aceptada en el spec).
- **Aprendizaje:** solo categoría/tipo alimentan `aprender`; monto y divisa no.
- **Migración:** imprescindible correr el `ALTER TABLE` antes de levantar la app nueva contra una base existente (local y prod).
