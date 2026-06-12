# 01 — Proyecto e historial

Este documento es la **memoria** del proyecto: qué es, qué decisiones tomamos, por qué,
y cómo quedó. Sirve para recuperar el contexto completo en cualquier momento.

---

## 1. Qué es la app

Una app **personal** para llevar los gastos del mes. La idea central:

> En vez de cargar gastos en un formulario aburrido, los **escribís en lenguaje natural**
> ("gasté 8500 en el súper", "pagué 45 lucas de luz") y una **IA los clasifica** sola.

Cada gasto se clasifica en dos ejes:
- **Categoría:** Supermercado, Servicios, Nafta, Salud, etc.
- **Tipo (control):** `fijo` (se repite cada mes) → `necesario` (indispensable pero variable)
  → `prescindible` (se podría recortar).

A fin de mes ves el total, cuánto fue prescindible (lo recortable), barras por tipo y por
categoría, y un **consejo de la IA** sobre dónde ajustar.

Es un proyecto para **aprender** (el dueño viene de Java/Spring y está aprendiendo Python e IA),
así que se priorizó entender el porqué de cada parte.

---

## 2. Stack y arquitectura final

- **Backend:** Python 3.13 + FastAPI + SQLAlchemy (ORM) + SQLite (base de datos en un archivo).
- **IA:** conmutable entre 3 proveedores (Groq / DeepSeek / Ollama) con una variable de entorno.
- **Frontend:** PWA en HTML + CSS + JavaScript puro (sin React ni build).
- **Ubicación:** `F:\proyectos\gastos-ia\`.

Flujo de un gasto, de punta a punta:

```
Escribís "8500 en el súper"
        │
        ▼
[Frontend] POST /gastos ──────────► [Backend] guarda "entrada pendiente", responde YA
                                              │
                                              ▼ (en segundo plano)
                                     [Worker] agarra la pendiente
                                              │
                                  ¿concepto conocido + monto? 
                                     ├── sí → clasifica con CÓDIGO (sin IA)
                                     └── no → le pregunta a la IA (Groq/Ollama/...)
                                              │
                                     crea el Gasto, aprende el concepto
        ┌─────────────────────────────────────┘
        ▼
[Frontend] sondea cada 2s y muestra el gasto ya clasificado
```

---

## 3. Historial: cómo llegamos hasta acá (y por qué)

### Etapa A — Base funcionando con IA local
- Armamos el backend (FastAPI), la base (SQLite), los endpoints y la PWA.
- Conectamos **Ollama** (IA local, gratis y privada) para clasificar.
- **Mañas de la PC que descubrimos:** el antivirus corporativo cortaba descargas de `.exe`
  a los 125 MB (lo esquivamos bajando como `.bin` a disco `F:`), y Maven crasheaba por heap.
  Ollama e instaló en `F:\Ollama` y los modelos en `F:\Ollama\models`.

### Etapa B — Rediseño del front (estilo de referencia `gastos.jsx`)
- Pasamos de una pantalla apilada a una con **dos pestañas** (Registrar / El mes).
- **Tema claro/oscuro**, tarjetas de gasto que se despliegan para reclasificar o borrar,
  vista del mes con barra apilada y el dato de "prescindible".
- Renombramos el tipo "innecesario" → **prescindible** (idea de "margen de maniobra").
- Soporte de **varios gastos en un mensaje** y **slang argentino** ("lucas", "palos").

### Etapa C — Mejor calidad de IA
- El modelo `llama3.2:3b` clasificaba mal (categorías erradas, slang, multi-gasto).
- Probamos **`qwen2.5:7b`**: mucho mejor. Pero seguía lento (~50s en esta CPU) y con el
  bug de "lucas" (lo leía ×10 mal).
- Mejora clave del informe: los **porcentajes los calcula Python**, no el modelo (los
  modelos chicos se equivocan con números).

### Etapa D — Memoria de clasificaciones + parseo determinístico
- Agregamos una tabla `clasificacion_aprendida`: aprende cómo se clasificó cada concepto
  y, sobre todo, **aprende de las correcciones manuales**.
- Para conceptos conocidos + un monto detectable, clasifica **sin llamar a la IA** (atajo).
- El **parseo de montos/slang** se hace en código (`parsing.py`), determinístico → arregla
  el bug de "lucas" para siempre.

### Etapa E — Clasificación asíncrona (worker)
- Problema: el usuario esperaba ~50s con la pantalla colgada.
- Solución: el `POST /gastos` solo **guarda el texto como "pendiente" y responde al instante**.
  Un **worker** en segundo plano lo clasifica y el front **sondea** para mostrar el resultado.
- Bonus: arreglamos el **parpadeo** del sondeo (solo re-renderiza si algo cambió) y que la
  animación de cada tarjeta corra una sola vez.

### Etapa F — IA en la nube + conmutable (patrón Strategy)
- Para resolver la lentitud de fondo, hicimos el clasificador **conmutable** por la variable
  `IA_PROVIDER`:
  - **Ollama** (local, offline, gratis, lento).
  - **DeepSeek** (nube, barato, pero sin saldo da error 402 — quedó sin usar).
  - **Groq** (nube, gratis, rapidísimo) → quedó **activo**. Clasifica en 1-3s y bien.
- Las API keys viven en **variables de entorno**, nunca en el código.

### Etapa G — Lanzador y la maña de las variables de entorno
- Descubrimos que las variables de entorno **no llegan a terminales ya abiertas** (por eso el
  backend seguía usando Ollama y daba "conexión rechazada" / WinError 10061).
- Solución: el script **`run.ps1`** lee las variables del registro al arrancar, así no
  depende de si la terminal es vieja o nueva.

---

## 4. Estado actual (2026-06)

- ✅ Funcionando end-to-end con **Groq**, clasificación asíncrona, rápida y de buena calidad.
- ✅ Memoria de clasificaciones (aprende de correcciones), parseo de slang determinístico.
- ✅ Front rediseñado con tema claro/oscuro, pestañas, barras del mes y consejo IA.
- ⚠️ La API key de Groq usada era **temporal (24h)** — al vencer hay que poner otra o volver a Ollama.

### Cómo correr
```powershell
cd F:\proyectos\gastos-ia
.\run.ps1
```
Abrir **http://localhost:8000**. Para cambiar de IA: cambiar `IA_PROVIDER` (variable de usuario) y reiniciar con `run.ps1`.

---

## 5. Pendientes / próximos pasos (etapa 2)

- Exponer la app a internet con **login + HTTPS** (hoy es solo local).
- Migrar de SQLite a **PostgreSQL**.
- Hacer la **PWA instalable** en el celular (requiere HTTPS).
- Reintentos automáticos de entradas en error; UI para editar monto/categoría.

---

## 6. Glosario de decisiones clave (el "por qué")

| Decisión | Por qué |
|---|---|
| IA por **una sola llamada**, no "agentes" | Clasificar es una tarea de un paso; un agente sería sobre-ingeniería. |
| **Worker** asíncrono | Para que el usuario no espere los segundos que tarda la IA. |
| **Memoria** de clasificaciones | Consistencia + velocidad: lo conocido no vuelve a pasar por la IA. |
| Parseo de montos en **Python** | Determinístico y gratis; arregla errores del modelo con el slang. |
| Proveedor **conmutable** | No casarse con una IA: cambiar = cambiar una variable. |
| Porcentajes del informe en **Python** | Los modelos chicos se equivocan con la matemática. |
