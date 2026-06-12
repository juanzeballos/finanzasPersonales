"""Punto de entrada de la app FastAPI.

- Crea las tablas si no existen.
- Arranca el worker de clasificación en segundo plano (un hilo dentro de este proceso).
- Monta los routers y sirve la PWA.

Correr con:  uvicorn app.main:app --host 0.0.0.0 --port 8000
(desde F:\\proyectos\\gastos-ia, sin --reload para no duplicar el worker).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (importa para registrar las tablas en Base)
from .database import Base, engine
from .routers import auth, gastos, informe
from .worker import iniciar_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Al arrancar: crear tablas y lanzar el worker que clasifica las entradas pendientes.
    Base.metadata.create_all(bind=engine)
    iniciar_worker()
    yield
    # (al apagar no hace falta nada: el worker es un hilo daemon, muere con el proceso)


app = FastAPI(title="Gastos IA", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(gastos.router)
app.include_router(informe.router)


@app.get("/ping")
def ping():
    return {"status": "ok"}


# --- PWA / archivos estáticos ---
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/app")
def app_alias():
    # Compatibilidad: la PWA instalada vieja abría en /app → la mandamos a "/" (una sola pantalla).
    return RedirectResponse("/")


@app.get("/download")
def download():
    return FileResponse("static/landing.html")


@app.get("/manifest.json")
def manifest():
    return FileResponse("static/manifest.json", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse("static/sw.js", media_type="application/javascript")
