# Documentación — Gastos IA

App personal para anotar gastos por chat en lenguaje natural; una IA los clasifica
(categoría + tipo), muestra el mes en barras y da consejos de recorte.

## Índice

1. **[01 — Proyecto e historial](01-proyecto-historial.md)**
   Contexto, decisiones que tomamos y por qué, y el estado actual. Es la "memoria"
   del proyecto: leélo para recordar de qué se trata y cómo llegamos hasta acá.

2. **[02 — Teoría del Backend](02-teoria-backend.md)**
   Clase paso a paso de la parte servidor (Python + FastAPI + base de datos + IA +
   worker asíncrono). Pensado para entenderlo y poder rehacerlo de cero.

3. **[03 — Teoría del Frontend](03-teoria-frontend.md)**
   Clase paso a paso de la parte visual (PWA en HTML/CSS/JS sin framework: estado,
   render, eventos, polling, tema claro/oscuro).

4. **[04 — Deploy a Fly.io](04-deploy-fly.md)**
   Cómo poner la app pública en internet (24/7) en Fly.io: contenedor, volumen
   persistente para los datos, secretos y comandos del día a día.

## Cómo correr el proyecto (resumen)

```powershell
cd F:\proyectos\gastos-ia
.\run.ps1            # arranca el backend (lee la config del registro)
```
Después abrí **http://localhost:8000** en el navegador.

- El proveedor de IA se elige con la variable `IA_PROVIDER` (`groq` | `deepseek` | `ollama`).
- Si usás `ollama`, además tiene que estar corriendo Ollama (la app de la bandeja).

## Mapa rápido de archivos

```
gastos-ia/
├── app/                  # BACKEND (Python)
│   ├── main.py           # arranque de la app + worker
│   ├── database.py       # conexión a la base (SQLite)
│   ├── models.py         # tablas (Gasto, Entrada, ClasificacionAprendida)
│   ├── schemas.py        # validación/forma de datos (Pydantic)
│   ├── ia.py             # cliente de IA (groq/deepseek/ollama)
│   ├── parsing.py        # parseo de montos y slang (sin IA)
│   ├── clasificador.py   # lógica de clasificar + memoria de aprendizaje
│   ├── worker.py         # proceso en segundo plano que clasifica
│   └── routers/
│       ├── gastos.py     # endpoints de gastos y entradas
│       └── informe.py    # endpoint del consejo
├── static/               # FRONTEND (PWA)
│   ├── index.html        # cáscara de la página
│   ├── style.css         # estilos + tema claro/oscuro
│   ├── app.js            # toda la lógica de la interfaz
│   ├── manifest.json     # metadatos PWA
│   └── sw.js             # service worker
├── run.ps1               # lanzador del backend
└── doc/                  # esta documentación
```
