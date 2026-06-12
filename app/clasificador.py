"""Lógica de clasificación de un texto en uno o varios gastos, AHORA por usuario.

Cada gasto creado y cada concepto aprendido quedan atados a un `usuario_id`.
La usa el worker en segundo plano. NO hace commit (lo hace el worker).
"""

import re
from datetime import date

from sqlalchemy.orm import Session

from . import ia, models, schemas
from .parsing import extraer_montos, normalizar


def normalizar_tipo(tipo: str) -> str:
    """Forzamos a un tipo válido (fijo/necesario/prescindible)."""
    return tipo if tipo in schemas.TIPOS else "necesario"


# ----------------- Memoria de clasificaciones (por usuario) -----------------

def aprender(db: Session, usuario_id: int, descripcion: str, categoria: str, tipo: str, emoji: str) -> None:
    """Guarda/actualiza cómo ESE usuario clasificó un concepto. No hace commit."""
    concepto = normalizar(descripcion)
    if not concepto:
        return
    fila = (
        db.query(models.ClasificacionAprendida)
        .filter_by(usuario_id=usuario_id, concepto=concepto)
        .first()
    )
    if fila:
        fila.descripcion, fila.categoria, fila.tipo, fila.emoji = descripcion, categoria, tipo, emoji
        fila.usos += 1
    else:
        db.add(models.ClasificacionAprendida(
            usuario_id=usuario_id, concepto=concepto, descripcion=descripcion,
            categoria=categoria, tipo=tipo, emoji=emoji,
        ))


def _aprendido_por_descripcion(db: Session, usuario_id: int, descripcion: str):
    """Busca un concepto exacto del usuario (por descripción normalizada)."""
    return (
        db.query(models.ClasificacionAprendida)
        .filter_by(usuario_id=usuario_id, concepto=normalizar(descripcion))
        .first()
    )


def _buscar_concepto_en_texto(db: Session, usuario_id: int, texto: str):
    """Busca si algún concepto aprendido por el usuario aparece (como palabra) en el texto."""
    t = normalizar(texto)
    candidatos = [
        f for f in db.query(models.ClasificacionAprendida).filter_by(usuario_id=usuario_id).all()
        if re.search(rf"\b{re.escape(f.concepto)}\b", t)
    ]
    return max(candidatos, key=lambda f: len(f.concepto)) if candidatos else None


def procesar_texto(db: Session, texto: str, usuario_id: int) -> dict:
    """Clasifica el texto y agrega el/los Gasto(s) del usuario a la sesión (sin commit).

    Devuelve {"created": [Gasto], "missing": [str]}. Puede lanzar excepción si la IA falla.
    """
    # --- 1) Atajo: concepto conocido + un único monto detectable -> sin IA ---
    montos = extraer_montos(texto)
    if len(montos) == 1:
        fila = _buscar_concepto_en_texto(db, usuario_id, texto)
        if fila:
            gasto = models.Gasto(
                usuario_id=usuario_id, fecha=date.today(), descripcion=fila.descripcion,
                monto=montos[0], categoria=fila.categoria, tipo=fila.tipo, emoji=fila.emoji,
            )
            db.add(gasto)
            fila.usos += 1
            return {"created": [gasto], "missing": []}

    # --- 2) Camino con IA ---
    clasificado = ia.clasificar(texto)

    creados = []
    for item in clasificado.items:
        if not item.amount:
            continue
        descripcion = item.description or "Gasto"
        categoria = item.category or "Otros"
        tipo = normalizar_tipo(item.tipo)
        emoji = item.emoji or "💸"

        # override: si el usuario ya aprendió este concepto, mandamos lo aprendido
        aprendido = _aprendido_por_descripcion(db, usuario_id, descripcion)
        if aprendido:
            categoria, tipo, emoji = aprendido.categoria, aprendido.tipo, aprendido.emoji

        gasto = models.Gasto(
            usuario_id=usuario_id, fecha=date.today(), descripcion=descripcion,
            monto=float(item.amount), categoria=categoria, tipo=tipo, emoji=emoji,
        )
        db.add(gasto)
        creados.append(gasto)
        aprender(db, usuario_id, descripcion, categoria, tipo, emoji)

    return {"created": creados, "missing": clasificado.missing}
