"""Lógica de clasificación de un texto en uno o varios gastos.

La usa el WORKER en segundo plano (no el endpoint HTTP). Combina:
  1) Atajo sin IA: si hay un único monto y un concepto ya aprendido -> instantáneo.
  2) IA (Ollama): clasifica, después PISA categoría/tipo con lo aprendido y aprende.

Importante: estas funciones NO hacen commit — lo hace el worker, así una entrada se
procesa en una sola transacción.
"""

import re
from datetime import date

from sqlalchemy.orm import Session

from . import ia, models, schemas
from .parsing import extraer_montos, normalizar


def normalizar_tipo(tipo: str) -> str:
    """Forzamos a un tipo válido (fijo/necesario/prescindible)."""
    return tipo if tipo in schemas.TIPOS else "necesario"


# ----------------- Memoria de clasificaciones (aprendizaje) -----------------

def aprender(db: Session, descripcion: str, categoria: str, tipo: str, emoji: str) -> None:
    """Guarda/actualiza cómo se clasificó un concepto. No hace commit."""
    concepto = normalizar(descripcion)
    if not concepto:
        return
    fila = db.get(models.ClasificacionAprendida, concepto)
    if fila:
        fila.descripcion, fila.categoria, fila.tipo, fila.emoji = descripcion, categoria, tipo, emoji
        fila.usos += 1
    else:
        db.add(models.ClasificacionAprendida(
            concepto=concepto, descripcion=descripcion,
            categoria=categoria, tipo=tipo, emoji=emoji,
        ))


def _aprendido_por_descripcion(db: Session, descripcion: str):
    """Busca un concepto exacto (por descripción normalizada). Para pisar lo que dijo la IA."""
    return db.get(models.ClasificacionAprendida, normalizar(descripcion))


def _buscar_concepto_en_texto(db: Session, texto: str):
    """Busca si algún concepto aprendido aparece (como palabra) en el texto libre.
    Devuelve el más largo (más específico). Para el atajo sin IA.
    """
    t = normalizar(texto)
    candidatos = [
        f for f in db.query(models.ClasificacionAprendida).all()
        if re.search(rf"\b{re.escape(f.concepto)}\b", t)
    ]
    return max(candidatos, key=lambda f: len(f.concepto)) if candidatos else None


def procesar_texto(db: Session, texto: str) -> dict:
    """Clasifica el texto y agrega el/los Gasto(s) a la sesión (sin commit).

    Devuelve {"created": [Gasto], "missing": [str]}.
    Puede lanzar excepción si la IA falla (lo maneja el worker).
    """
    # --- 1) Atajo: concepto conocido + un único monto detectable -> sin IA ---
    montos = extraer_montos(texto)
    if len(montos) == 1:
        fila = _buscar_concepto_en_texto(db, texto)
        if fila:
            gasto = models.Gasto(
                fecha=date.today(), descripcion=fila.descripcion, monto=montos[0],
                categoria=fila.categoria, tipo=fila.tipo, emoji=fila.emoji,
            )
            db.add(gasto)
            fila.usos += 1
            return {"created": [gasto], "missing": []}

    # --- 2) Camino con IA ---
    clasificado = ia.clasificar(texto)

    creados = []
    for item in clasificado.items:
        if not item.amount:  # sin monto no se guarda (va en 'missing')
            continue
        descripcion = item.description or "Gasto"
        categoria = item.category or "Otros"
        tipo = normalizar_tipo(item.tipo)
        emoji = item.emoji or "💸"

        # override: si ya aprendimos este concepto, mandamos lo aprendido
        aprendido = _aprendido_por_descripcion(db, descripcion)
        if aprendido:
            categoria, tipo, emoji = aprendido.categoria, aprendido.tipo, aprendido.emoji

        gasto = models.Gasto(
            fecha=date.today(), descripcion=descripcion, monto=float(item.amount),
            categoria=categoria, tipo=tipo, emoji=emoji,
        )
        db.add(gasto)
        creados.append(gasto)
        aprender(db, descripcion, categoria, tipo, emoji)

    return {"created": creados, "missing": clasificado.missing}
