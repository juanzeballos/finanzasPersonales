# 02 — Teoría del Backend (clase paso a paso)

Esta es una clase para entender **cómo funciona el servidor** y poder rehacerlo de cero.
Vas a ver muchas analogías con **Java/Spring** porque venís de ahí.

> **Idea base:** el backend es un programa que está siempre escuchando pedidos por HTTP
> (como un `@RestController` de Spring), guarda datos en una base, y le pide a una IA que
> clasifique los gastos. El frontend (el navegador) le habla a este backend.

---

## Paso 0 — Las herramientas

| Herramienta | Qué es | Equivalente en Java |
|---|---|---|
| **Python** | El lenguaje | Java |
| **FastAPI** | Framework web (define endpoints) | Spring Boot / Spring MVC |
| **uvicorn** | El servidor que corre FastAPI | Tomcat |
| **SQLAlchemy** | ORM (mapea clases ↔ tablas) | Hibernate / JPA |
| **SQLite** | Base de datos en un solo archivo | H2 embebido |
| **Pydantic** | Validación y forma de los datos (DTOs) | Bean Validation + DTOs |
| **httpx** | Cliente HTTP (para llamar a la IA) | RestTemplate / HttpClient |

### Setup de cero
```powershell
mkdir gastos-ia; cd gastos-ia
python -m venv .venv                  # entorno virtual (como un classpath aislado)
.\.venv\Scripts\Activate.ps1
pip install fastapi uvicorn sqlalchemy pydantic httpx
```
Un **venv** es una carpeta con su propio Python y sus librerías, aislado del sistema
(parecido a tener las dependencias del proyecto separadas, como el `target/` con su classpath).

---

## Paso 1 — La conexión a la base (`database.py`)

Antes de guardar nada, hay que configurar la base. Tres piezas:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = "sqlite:///./gastos.db"           # un archivo gastos.db
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30})
SessionLocal = sessionmaker(bind=engine)         # fábrica de sesiones

class Base(DeclarativeBase):                       # clase base de las "entidades"
    pass

def get_db():                                      # provee una sesión por pedido
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

| Concepto | Qué es | Java |
|---|---|---|
| `engine` | El pool de conexiones a la base | DataSource |
| `SessionLocal` | Fábrica de sesiones | SessionFactory |
| `Base` | Clase madre de las entidades | `@MappedSuperclass` |
| `get_db` | Da una sesión y la cierra sola | `@Transactional` / try-with-resources |

El `yield db` es el truco de **inyección de dependencias** de FastAPI: te presta la sesión
y, pase lo que pase, ejecuta el `finally` (cierra). `check_same_thread=False` permite usar la
base desde varios hilos (lo necesitamos por el worker).

---

## Paso 2 — Las tablas (`models.py`)

Una clase = una tabla. Es como una `@Entity` de JPA.

```python
class Gasto(Base):
    __tablename__ = "gastos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column(Date)
    descripcion: Mapped[str] = mapped_column(String)
    monto: Mapped[float] = mapped_column(Float)
    categoria: Mapped[str] = mapped_column(String)
    tipo: Mapped[str] = mapped_column(String)        # fijo|necesario|prescindible
    emoji: Mapped[str] = mapped_column(String, default="💸")
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

Tenemos **tres tablas**:
- **`Gasto`** — cada gasto ya clasificado.
- **`Entrada`** — la "bandeja de entrada": el texto crudo que escribís, con un `estado`
  (`pendiente` / `procesado` / `error`). Es la cola que alimenta al worker.
- **`ClasificacionAprendida`** — la memoria: `concepto` (ej. "netflix") → categoría/tipo/emoji.

`mapped_column` ~ `@Column`. `primary_key=True` ~ `@Id`. SQLAlchemy crea las tablas solas
(lo hacemos en el arranque con `Base.metadata.create_all`).

---

## Paso 3 — La forma de los datos (`schemas.py`)

Los **schemas** de Pydantic definen qué entra y sale por la API, con validación automática.
Son los **DTOs**. No confundir con los `models` (esos son las tablas).

```python
class GastoTexto(BaseModel):       # lo que llega del chat
    texto: str

class GastoOut(BaseModel):         # lo que devolvemos al cliente
    id: int
    descripcion: str
    monto: float
    categoria: str
    tipo: str
    emoji: str
    model_config = {"from_attributes": True}   # permite crearlo desde un objeto ORM
```

`from_attributes` = "podés construir este DTO leyendo los atributos de la entidad" (como
mapear una Entity a un DTO). Pydantic valida tipos solo: si mandan `monto: "hola"`, lo rechaza
con un 422, sin que escribas validaciones a mano.

---

## Paso 4 — Los endpoints (`routers/gastos.py`)

Un **router** agrupa endpoints, como un `@RestController`.

```python
router = APIRouter()

@router.get("/gastos", response_model=list[GastoOut])
def listar_gastos(mes: str | None = Query(None), db: Session = Depends(get_db)):
    q = db.query(models.Gasto)
    if mes:
        q = q.filter(func.strftime("%Y-%m", models.Gasto.fecha) == mes)
    return q.order_by(models.Gasto.id.desc()).all()
```

| Pieza | Java |
|---|---|
| `@router.get("/gastos")` | `@GetMapping("/gastos")` |
| `Depends(get_db)` | inyección de un bean (la sesión) |
| `response_model=...` | el tipo de retorno serializado |
| `Query(None)` | `@RequestParam(required=false)` |

Endpoints que tenemos:
- `POST /gastos` → guarda una **Entrada** pendiente y responde al toque (no clasifica acá).
- `GET /entradas` → lista las pendientes/con error (para mostrar "clasificando…").
- `DELETE /entradas/{id}` → descartar una entrada con error.
- `GET /gastos?mes=YYYY-MM` → lista gastos clasificados.
- `PATCH /gastos/{id}` → reclasificar el tipo (y **aprende** la corrección).
- `DELETE /gastos/{id}` → borrar.
- `GET /resumen?mes=...` y `POST /informe?mes=...` → totales y consejo.

---

## Paso 5 — Hablarle a la IA (`ia.py`)

Una IA (un modelo de lenguaje) vive en un servidor (local o en la nube) y se le habla por
**HTTP**. Le mandás un **prompt** (instrucciones + el texto) y te devuelve texto.

### El prompt
Le explicamos exactamente qué queremos y en qué formato (JSON):
```
Sos un clasificador de gastos... Devolvé EXCLUSIVAMENTE un JSON con esta forma:
{"items":[{"description":"...","amount":123,"category":"...","tipo":"...","emoji":"..."}],"missing":[...]}
Reglas: [slang, categorías sugeridas, etc.]
Texto del gasto: "gasté 8500 en el súper"
```
A esto se le llama **prompt engineering**: la calidad de la respuesta depende de qué tan claras
y específicas sean las instrucciones y las reglas.

### Conmutable entre proveedores (patrón Strategy)
Soportamos 3 IAs y elegimos una con la variable `IA_PROVIDER`:
```python
def _generar(prompt, json_mode):
    if PROVIDER in _OPENAI_COMPAT:     # groq, deepseek
        return _openai_compat(prompt, json_mode)
    return _ollama(prompt, json_mode) # local
```
Es el **patrón Strategy**: misma "interfaz" (`clasificar`), varias implementaciones, se elige
por configuración. En Java sería una interfaz `Clasificador` con 3 implementaciones y un
`@Profile`/property para elegir cuál inyectar.

- **Ollama** (local): HTTP a `localhost:11434`. El modelo vive en tu PC.
- **Groq / DeepSeek** (nube): HTTP a su API (compatible con OpenAI), con `Authorization: Bearer <key>`.
  El modelo vive en sus servidores.

> **Clave:** el backend no "tiene" la IA adentro; solo sabe **cómo pedirle**. La key viaja en
> una variable de entorno, nunca hardcodeada.

El "JSON mode" (`response_format`/`format: json`) le pide al modelo que devuelva JSON válido sí
o sí, que después validamos con Pydantic (`ClasificacionIA(**datos)`).

---

## Paso 6 — Lo que NO necesita IA (`parsing.py`)

No todo requiere un modelo. Entender un **monto** es matemática, no lenguaje:
```python
extraer_montos("45 lucas de luz y 3200 el delivery")  # -> [45000, 3200]
```
`parsing.py` interpreta el slang ("luca"=mil, "palo"=millón, "8.500"=8500) con **expresiones
regulares**, de forma determinística. Esto es gratis, instantáneo y **no se equivoca** (a
diferencia del modelo, que leía "45 lucas" como 4500).

Lección: **usá código para lo que es regla; usá IA solo para lo que requiere entender.**

---

## Paso 7 — Clasificar + memoria (`clasificador.py`)

`procesar_texto(db, texto)` es el cerebro de la clasificación:

1. **Atajo sin IA:** si hay un solo monto y el texto contiene un **concepto ya aprendido**
   (ej. "netflix"), arma el gasto con lo aprendido y listo. **No llama al modelo.**
2. **Camino con IA:** si no, le pregunta al modelo, y después **pisa** la categoría/tipo con
   lo aprendido (si existe) y **guarda** el resultado para la próxima.

La **memoria** (`aprender`) se actualiza en cada clasificación y —lo más importante— en cada
**corrección manual** (cuando reclasificás una tarjeta). Así, la próxima vez que aparezca ese
concepto, se respeta tu decisión sin volver a preguntar.

```
Gasto → ¿lo conozco?
          ├── sí → clasifico con CÓDIGO (rápido, gratis)
          └── no → le pregunto a la IA y lo aprendo
```

---

## Paso 8 — El patrón asíncrono (`worker.py`) — ⭐ el concepto más importante

**Problema:** clasificar tarda (segundos). Si lo hacés dentro del `POST /gastos`, el usuario
espera con la pantalla colgada.

**Solución:** separar "recibir" de "procesar".

- **Síncrono (lo que evitamos):** pedido → clasifica → responde (el usuario espera todo).
- **Asíncrono (lo que hicimos):** pedido → guarda "pendiente" → responde YA. Un **worker**
  (proceso en segundo plano) agarra las pendientes y las clasifica aparte.

```python
def _loop():
    while True:
        for entrada in pendientes():
            procesar_texto(...)        # crea el Gasto
            entrada.estado = "procesado"
        time.sleep(2)                  # POLLING: revisa cada 2 segundos
```

El worker corre en un **hilo** dentro del mismo proceso del backend (lo arranca `main.py` al
iniciar). Hace **polling**: cada 2s pregunta "¿hay pendientes?". El frontend, por su lado,
también sondea para mostrar cuándo cada gasto quedó listo.

> **Importante de entender:** el worker es **plomería** (código que mueve datos y decide
> *cuándo* clasificar). El que *entiende* sigue siendo el modelo. El worker no reemplaza a la
> IA; solo desacopla la espera.

---

## Paso 9 — El informe (`routers/informe.py`)

El consejo del mes. Truco clave: **los porcentajes los calcula Python**, no el modelo:
```python
resumen = calcular_resumen(db, mes)          # totales por tipo y categoría (SQL GROUP BY)
texto = _formatear_resumen(resumen)          # arma el texto con los % ya hechos
consejo = ia.generar_informe(texto)          # el modelo solo redacta
```
Los modelos chicos se equivocan con matemática, así que la app hace los números y la IA solo
escribe el consejo en lindo. (La app hace lo que sabe hacer; la IA hace lo que sabe hacer.)

---

## Paso 10 — El arranque (`main.py`)

Es el `main` de la app. Crea las tablas, lanza el worker y monta todo:
```python
@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(bind=engine)   # crea tablas si faltan
    iniciar_worker()                         # arranca el hilo del worker
    yield                                    # acá la app vive

app = FastAPI(lifespan=lifespan)
app.include_router(gastos.router)
app.include_router(informe.router)
app.mount("/static", StaticFiles(directory="static"))   # sirve la PWA
```
`lifespan` es el lugar para "cosas al arrancar / al apagar" (como `@PostConstruct`).

### Correr
```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
(Usamos `run.ps1` que además setea las variables de entorno desde el registro.)

---

## Receta: hacerlo de cero, en orden

1. `venv` + `pip install fastapi uvicorn sqlalchemy pydantic httpx`.
2. `database.py` (engine, SessionLocal, Base, get_db).
3. `models.py` (empezá solo con `Gasto`).
4. `schemas.py` (`GastoTexto`, `GastoOut`).
5. `main.py` con un endpoint `GET /ping` → probá que el servidor levanta.
6. CRUD de gastos **síncrono y sin IA** (guardá categoría/tipo a mano) → probá la base.
7. `ia.py` con UN solo proveedor (Ollama o Groq) → conectá la clasificación dentro del POST.
8. `parsing.py` + `clasificador.py` (atajo + memoria de aprendizaje).
9. Convertí a **asíncrono**: tabla `Entrada` + `worker.py` + el POST que solo encola.
10. `informe.py` con los porcentajes calculados en Python.
11. Hacé el proveedor **conmutable** (`IA_PROVIDER`).

Construir en este orden te deja **algo funcionando en cada paso**, que es la mejor forma de
aprender (y de no perderte).
