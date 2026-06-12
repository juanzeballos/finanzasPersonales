"""Endpoints de gastos y de la bandeja de entradas.

El alta (POST /gastos) ya NO clasifica: solo guarda el texto como 'pendiente' y
responde al instante. La clasificación la hace el worker en segundo plano. Así el
usuario nunca espera los ~50s del modelo.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..clasificador import aprender, normalizar_tipo
from ..database import get_db

router = APIRouter()


def calcular_resumen(db: Session, mes: str) -> dict:
    """Totales del mes por categoría y por tipo. 'mes' con formato 'YYYY-MM'."""
    filtro_mes = func.strftime("%Y-%m", models.Gasto.fecha) == mes

    por_categoria = (
        db.query(models.Gasto.categoria, func.sum(models.Gasto.monto))
        .filter(filtro_mes)
        .group_by(models.Gasto.categoria)
        .all()
    )
    por_tipo = (
        db.query(models.Gasto.tipo, func.sum(models.Gasto.monto))
        .filter(filtro_mes)
        .group_by(models.Gasto.tipo)
        .all()
    )
    total = db.query(func.coalesce(func.sum(models.Gasto.monto), 0.0)).filter(filtro_mes).scalar()

    return {
        "mes": mes,
        "total": round(total or 0.0, 2),
        "por_categoria": [{"categoria": c, "total": round(t, 2)} for c, t in por_categoria],
        "por_tipo": [{"tipo": tp, "total": round(t, 2)} for tp, t in por_tipo],
    }


# ----------------- Bandeja de entradas (lo nuevo, asíncrono) -----------------

@router.post("/gastos", response_model=schemas.EntradaOut)
def crear_gasto(payload: schemas.GastoTexto, db: Session = Depends(get_db)):
    """Guarda el texto como entrada 'pendiente' y responde YA. El worker la clasifica."""
    entrada = models.Entrada(texto=payload.texto.strip(), estado="pendiente")
    db.add(entrada)
    db.commit()
    db.refresh(entrada)
    return entrada


@router.get("/entradas", response_model=list[schemas.EntradaOut])
def listar_entradas(db: Session = Depends(get_db)):
    """Entradas todavía visibles: pendientes (clasificando…) y con error."""
    return (
        db.query(models.Entrada)
        .filter(models.Entrada.estado != "procesado")
        .order_by(models.Entrada.id)
        .all()
    )


@router.delete("/entradas/{entrada_id}", status_code=204)
def borrar_entrada(entrada_id: int, db: Session = Depends(get_db)):
    """Descartar una entrada (típicamente una con error)."""
    entrada = db.get(models.Entrada, entrada_id)
    if not entrada:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    db.delete(entrada)
    db.commit()


# ----------------- Gastos ya clasificados -----------------

@router.get("/gastos", response_model=list[schemas.GastoOut])
def listar_gastos(mes: str | None = Query(default=None), db: Session = Depends(get_db)):
    """Lista los gastos; si se pasa 'mes' (YYYY-MM), filtra por ese mes."""
    q = db.query(models.Gasto)
    if mes:
        q = q.filter(func.strftime("%Y-%m", models.Gasto.fecha) == mes)
    return q.order_by(models.Gasto.fecha.desc(), models.Gasto.id.desc()).all()


@router.patch("/gastos/{gasto_id}", response_model=schemas.GastoOut)
def reclasificar_gasto(gasto_id: int, payload: schemas.TipoUpdate, db: Session = Depends(get_db)):
    """Cambia el tipo (fijo/necesario/prescindible) de un gasto existente."""
    gasto = db.get(models.Gasto, gasto_id)
    if not gasto:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")
    gasto.tipo = normalizar_tipo(payload.tipo)
    # Aprender la corrección: la próxima vez que aparezca este concepto, se respeta.
    aprender(db, gasto.descripcion, gasto.categoria, gasto.tipo, gasto.emoji)
    db.commit()
    db.refresh(gasto)
    return gasto


@router.delete("/gastos/{gasto_id}", status_code=204)
def borrar_gasto(gasto_id: int, db: Session = Depends(get_db)):
    """Elimina un gasto."""
    gasto = db.get(models.Gasto, gasto_id)
    if not gasto:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")
    db.delete(gasto)
    db.commit()


@router.get("/resumen")
def resumen(mes: str = Query(..., description="Mes en formato YYYY-MM"), db: Session = Depends(get_db)):
    """Totales agregados para alimentar la vista del mes."""
    return calcular_resumen(db, mes)
