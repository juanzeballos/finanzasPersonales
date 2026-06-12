"""Worker en segundo plano: vigila la bandeja de entradas y clasifica las pendientes.

Corre en un HILO daemon dentro del proceso del backend (no es un proceso aparte).
Hace POLLING: cada INTERVALO segundos busca entradas 'pendiente', las clasifica
(creando Gasto(s)) y las marca 'procesado' o 'error'. Así el pedido HTTP del
usuario responde al instante y la parte lenta (la IA) ocurre acá, desacoplada.
"""

import threading
import time

from . import models
from .clasificador import procesar_texto
from .database import SessionLocal

INTERVALO = 2  # segundos entre sondeos


def _procesar_una(db, entrada_id: int) -> None:
    entrada = db.get(models.Entrada, entrada_id)
    if not entrada or entrada.estado != "pendiente":
        return
    try:
        res = procesar_texto(db, entrada.texto)
        if res["created"]:
            entrada.estado = "procesado"
            entrada.error = None
        elif res["missing"]:
            entrada.estado = "error"
            entrada.error = " ".join(res["missing"])
        else:
            entrada.estado = "error"
            entrada.error = "No pude leer ningún gasto ahí."
        db.commit()
    except Exception as e:
        # IA caída / inválida: dejamos la entrada como error con el mensaje.
        db.rollback()
        entrada = db.get(models.Entrada, entrada_id)
        if entrada:
            entrada.estado = "error"
            entrada.error = f"Error de la IA: {e}"[:300]
            db.commit()


def _procesar_pendientes() -> None:
    db = SessionLocal()
    try:
        ids = [
            e.id for e in db.query(models.Entrada)
            .filter(models.Entrada.estado == "pendiente")
            .order_by(models.Entrada.id)
            .all()
        ]
        for entrada_id in ids:
            _procesar_una(db, entrada_id)
    finally:
        db.close()


def _loop() -> None:
    while True:
        try:
            _procesar_pendientes()
        except Exception:
            pass  # nunca dejamos morir el loop por un error puntual
        time.sleep(INTERVALO)


def iniciar_worker() -> threading.Thread:
    """Arranca el hilo del worker (daemon: muere con el proceso). Lo llama main.py."""
    hilo = threading.Thread(target=_loop, daemon=True, name="clasificador-worker")
    hilo.start()
    return hilo
