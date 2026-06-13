"""Endpoints de gastos y de la bandeja de entradas — TODOS protegidos por login y
filtrados por usuario (cada uno ve solo lo suyo).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import usuario_actual
from ..clasificador import aprender, normalizar_tipo
from ..database import get_db

router = APIRouter()

DIVISAS = {"ARS", "USD", "BRL", "EUR"}


def rango_mes(mes: str) -> tuple[date, date]:
    """'YYYY-MM' -> (primer día del mes, primer día del mes siguiente).

    Sirve para filtrar por mes con un rango de fechas, que funciona IGUAL en SQLite y
    Postgres (evitamos func.strftime, que es solo de SQLite).
    """
    anio, m = int(mes[:4]), int(mes[5:7])
    inicio = date(anio, m, 1)
    fin = date(anio + 1, 1, 1) if m == 12 else date(anio, m + 1, 1)
    return inicio, fin


def calcular_resumen(db: Session, mes: str, usuario_id: int) -> dict:
    """Totales del mes por categoría y por tipo, SOLO de ese usuario."""
    inicio, fin = rango_mes(mes)
    filtro = (
        (models.Gasto.usuario_id == usuario_id)
        & (models.Gasto.fecha >= inicio)
        & (models.Gasto.fecha < fin)
    )

    por_categoria = (
        db.query(models.Gasto.categoria, func.sum(models.Gasto.monto))
        .filter(filtro).group_by(models.Gasto.categoria).all()
    )
    por_tipo = (
        db.query(models.Gasto.tipo, func.sum(models.Gasto.monto))
        .filter(filtro).group_by(models.Gasto.tipo).all()
    )
    total = db.query(func.coalesce(func.sum(models.Gasto.monto), 0.0)).filter(filtro).scalar()

    return {
        "mes": mes,
        "total": round(total or 0.0, 2),
        "por_categoria": [{"categoria": c, "total": round(t, 2)} for c, t in por_categoria],
        "por_tipo": [{"tipo": tp, "total": round(t, 2)} for tp, t in por_tipo],
    }


# ----------------- Bandeja de entradas -----------------

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


@router.get("/entradas", response_model=list[schemas.EntradaOut])
def listar_entradas(db: Session = Depends(get_db), usuario: models.Usuario = Depends(usuario_actual)):
    """Entradas del usuario todavía visibles: pendientes y con error."""
    return (
        db.query(models.Entrada)
        .filter(models.Entrada.usuario_id == usuario.id, models.Entrada.estado != "procesado")
        .order_by(models.Entrada.id)
        .all()
    )


@router.delete("/entradas/{entrada_id}", status_code=204)
def borrar_entrada(entrada_id: int, db: Session = Depends(get_db),
                   usuario: models.Usuario = Depends(usuario_actual)):
    entrada = db.get(models.Entrada, entrada_id)
    if not entrada or entrada.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    db.delete(entrada)
    db.commit()


# ----------------- Gastos -----------------

@router.get("/gastos", response_model=list[schemas.GastoOut])
def listar_gastos(mes: str | None = Query(default=None), db: Session = Depends(get_db),
                  usuario: models.Usuario = Depends(usuario_actual)):
    q = db.query(models.Gasto).filter(models.Gasto.usuario_id == usuario.id)
    if mes:
        inicio, fin = rango_mes(mes)
        q = q.filter(models.Gasto.fecha >= inicio, models.Gasto.fecha < fin)
    return q.order_by(models.Gasto.fecha.desc(), models.Gasto.id.desc()).all()


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


@router.delete("/gastos/{gasto_id}", status_code=204)
def borrar_gasto(gasto_id: int, db: Session = Depends(get_db),
                 usuario: models.Usuario = Depends(usuario_actual)):
    gasto = db.get(models.Gasto, gasto_id)
    if not gasto or gasto.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")
    db.delete(gasto)
    db.commit()


@router.get("/resumen")
def resumen(mes: str = Query(..., description="Mes en formato YYYY-MM"), db: Session = Depends(get_db),
            usuario: models.Usuario = Depends(usuario_actual)):
    return calcular_resumen(db, mes, usuario.id)
