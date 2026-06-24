"""Endpoints de gastos en grupo (dividir cuentas). Ledger separado del gasto personal.

Auth: igual que el resto, `Depends(usuario_actual)`. El acceso a un grupo se valida con
`miembro_de_grupo` (403 si no es miembro) y `admin_de_grupo` (403 si no es el creador/admin).
"""

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import ia, models, schemas
from ..auth import usuario_actual
from ..database import get_db
from ..parsing import normalizar
from ..settlement import calcular_saldos, simplificar_deudas

router = APIRouter()

DIVISAS = {"ARS", "USD", "BRL", "EUR"}


# ----------------- Helpers -----------------

def _nuevo_code() -> str:
    return secrets.token_urlsafe(8)


def miembro_de_grupo(grupo_id: int, db: Session = Depends(get_db),
                     usuario: models.Usuario = Depends(usuario_actual)):
    """Devuelve (grupo, miembro) o corta con 404/403."""
    grupo = db.get(models.Grupo, grupo_id)
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    miembro = (db.query(models.GrupoMiembro)
               .filter_by(grupo_id=grupo_id, usuario_id=usuario.id).first())
    if not miembro:
        raise HTTPException(status_code=403, detail="No sos miembro de este grupo")
    return grupo, miembro


def admin_de_grupo(ctx=Depends(miembro_de_grupo)):
    grupo, miembro = ctx
    if miembro.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo el admin del grupo puede hacer esto")
    return ctx


def _miembros(db: Session, grupo_id: int):
    """Filas con .usuario_id, .nombre, .email, .rol."""
    return (db.query(models.GrupoMiembro.usuario_id, models.Usuario.nombre,
                     models.Usuario.email, models.GrupoMiembro.rol)
            .join(models.Usuario, models.Usuario.id == models.GrupoMiembro.usuario_id)
            .filter(models.GrupoMiembro.grupo_id == grupo_id).all())


def _ronda_abierta(db: Session, grupo_id: int) -> models.Ronda:
    ronda = (db.query(models.Ronda)
             .filter_by(grupo_id=grupo_id, estado="abierta")
             .order_by(models.Ronda.id.desc()).first())
    if not ronda:
        raise HTTPException(status_code=409, detail="El grupo no tiene una ronda abierta")
    return ronda


def _resolver_pagador(nombre: str | None, miembros, default_id: int) -> int:
    """Matchea el nombre devuelto por la IA contra un miembro (por nombre de pila normalizado).
    'yo'/sin nombre/sin match → default_id (quien está cargando)."""
    if not nombre:
        return default_id
    palabras = normalizar(nombre).split()
    if not palabras or palabras[0] in ("yo", "mi", "mio", "mia"):
        return default_id
    objetivo = palabras[0]
    for m in miembros:
        ref = normalizar(m.nombre or m.email).split()
        if ref and ref[0] == objetivo:
            return m.usuario_id
    return default_id


def _armar_detalle(db: Session, grupo: models.Grupo, miembro: models.GrupoMiembro) -> schemas.GrupoDetalleOut:
    ronda = _ronda_abierta(db, grupo.id)
    miembros = _miembros(db, grupo.id)
    presentes = [rp.usuario_id for rp in
                 db.query(models.RondaParticipante).filter_by(ronda_id=ronda.id).all()]
    gastos = (db.query(models.GastoGrupo).filter_by(ronda_id=ronda.id)
              .order_by(models.GastoGrupo.id.desc()).all())
    saldos = calcular_saldos(presentes, [(g.pagador_id, g.monto) for g in gastos])
    pagos = simplificar_deudas(saldos)
    return schemas.GrupoDetalleOut(
        grupo=schemas.GrupoOut.model_validate(grupo),
        miembros=[schemas.MiembroOut(usuario_id=m.usuario_id, nombre=m.nombre, email=m.email, rol=m.rol)
                  for m in miembros],
        ronda=schemas.RondaOut.model_validate(ronda),
        presentes=presentes,
        gastos=[schemas.GastoGrupoOut.model_validate(g) for g in gastos],
        saldos=[schemas.SaldoOut(usuario_id=u, **v) for u, v in saldos.items()],
        pagos=[schemas.PagoOut(**p) for p in pagos],
        invite_code=grupo.invite_code if miembro.rol == "admin" else None,
    )


# ----------------- Endpoints -----------------

@router.post("/grupos", response_model=schemas.GrupoDetalleOut)
def crear_grupo(payload: schemas.GrupoCrear, db: Session = Depends(get_db),
                usuario: models.Usuario = Depends(usuario_actual)):
    if payload.divisa not in DIVISAS:
        raise HTTPException(status_code=400, detail="Divisa no soportada")
    grupo = models.Grupo(nombre=(payload.nombre.strip() or "Grupo"), divisa=payload.divisa,
                         creador_id=usuario.id, invite_code=_nuevo_code())
    db.add(grupo)
    db.flush()
    db.add(models.GrupoMiembro(grupo_id=grupo.id, usuario_id=usuario.id, rol="admin"))
    ronda = models.Ronda(grupo_id=grupo.id, estado="abierta")
    db.add(ronda)
    db.flush()
    db.add(models.RondaParticipante(ronda_id=ronda.id, usuario_id=usuario.id))
    db.commit()
    db.refresh(grupo)
    miembro = db.query(models.GrupoMiembro).filter_by(grupo_id=grupo.id, usuario_id=usuario.id).first()
    return _armar_detalle(db, grupo, miembro)


@router.get("/grupos", response_model=list[schemas.GrupoOut])
def mis_grupos(db: Session = Depends(get_db), usuario: models.Usuario = Depends(usuario_actual)):
    return (db.query(models.Grupo)
            .join(models.GrupoMiembro, models.GrupoMiembro.grupo_id == models.Grupo.id)
            .filter(models.GrupoMiembro.usuario_id == usuario.id)
            .order_by(models.Grupo.id.desc()).all())


@router.get("/grupos/{grupo_id}", response_model=schemas.GrupoDetalleOut)
def detalle_grupo(grupo_id: int, db: Session = Depends(get_db),
                  usuario: models.Usuario = Depends(usuario_actual), ctx=Depends(miembro_de_grupo)):
    grupo, miembro = ctx
    return _armar_detalle(db, grupo, miembro)


@router.post("/grupos/{grupo_id}/invite/rotate")
def rotar_code(grupo_id: int, db: Session = Depends(get_db),
               usuario: models.Usuario = Depends(usuario_actual), ctx=Depends(admin_de_grupo)):
    grupo, _ = ctx
    grupo.invite_code = _nuevo_code()
    db.commit()
    return {"invite_code": grupo.invite_code}


@router.post("/grupos/join", response_model=schemas.GrupoOut)
def unirse(payload: schemas.JoinIn, db: Session = Depends(get_db),
           usuario: models.Usuario = Depends(usuario_actual)):
    grupo = db.query(models.Grupo).filter_by(invite_code=payload.code.strip()).first()
    if not grupo:
        raise HTTPException(status_code=404, detail="Código de invitación inválido")
    ya = db.query(models.GrupoMiembro).filter_by(grupo_id=grupo.id, usuario_id=usuario.id).first()
    if not ya:
        db.add(models.GrupoMiembro(grupo_id=grupo.id, usuario_id=usuario.id, rol="miembro"))
        ronda = db.query(models.Ronda).filter_by(grupo_id=grupo.id, estado="abierta").first()
        if ronda and not db.query(models.RondaParticipante).filter_by(
                ronda_id=ronda.id, usuario_id=usuario.id).first():
            db.add(models.RondaParticipante(ronda_id=ronda.id, usuario_id=usuario.id))
        db.commit()
    return schemas.GrupoOut.model_validate(grupo)


@router.post("/grupos/{grupo_id}/rondas/{ronda_id}/presentes", response_model=schemas.GrupoDetalleOut)
def set_presentes(grupo_id: int, ronda_id: int, payload: schemas.PresentesIn,
                  db: Session = Depends(get_db),
                  usuario: models.Usuario = Depends(usuario_actual), ctx=Depends(miembro_de_grupo)):
    grupo, miembro = ctx
    ronda = db.get(models.Ronda, ronda_id)
    if not ronda or ronda.grupo_id != grupo_id or ronda.estado != "abierta":
        raise HTTPException(status_code=400, detail="Ronda inválida o cerrada")
    ids_miembros = {m.usuario_id for m in _miembros(db, grupo_id)}
    nuevos = [uid for uid in payload.usuario_ids if uid in ids_miembros]
    db.query(models.RondaParticipante).filter_by(ronda_id=ronda_id).delete()
    for uid in nuevos:
        db.add(models.RondaParticipante(ronda_id=ronda_id, usuario_id=uid))
    db.commit()
    return _armar_detalle(db, grupo, miembro)


@router.post("/grupos/{grupo_id}/cerrar-ronda", response_model=schemas.GrupoDetalleOut)
def cerrar_ronda(grupo_id: int, db: Session = Depends(get_db),
                 usuario: models.Usuario = Depends(usuario_actual), ctx=Depends(admin_de_grupo)):
    grupo, miembro = ctx
    ronda = _ronda_abierta(db, grupo_id)
    presentes = [rp.usuario_id for rp in
                 db.query(models.RondaParticipante).filter_by(ronda_id=ronda.id).all()]
    ronda.estado = "cerrada"
    ronda.cerrada_en = datetime.now(timezone.utc)
    nueva = models.Ronda(grupo_id=grupo_id, estado="abierta")
    db.add(nueva)
    db.flush()
    for uid in presentes:   # la nueva ronda hereda los presentes de la que se cerró
        db.add(models.RondaParticipante(ronda_id=nueva.id, usuario_id=uid))
    db.commit()
    return _armar_detalle(db, grupo, miembro)


@router.post("/grupos/{grupo_id}/gastos")
def crear_gasto_grupo(grupo_id: int, payload: schemas.GastoGrupoTexto, db: Session = Depends(get_db),
                      usuario: models.Usuario = Depends(usuario_actual), ctx=Depends(miembro_de_grupo)):
    grupo, _ = ctx
    ronda = _ronda_abierta(db, grupo_id)
    miembros = _miembros(db, grupo_id)
    nombres = [m.nombre or m.email for m in miembros]
    try:
        res = ia.clasificar_grupo(payload.texto.strip(), nombres)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error de la IA: {e}")

    creados = []
    for item in res["items"]:
        amount = item.get("amount")
        if not amount:
            continue
        pagador_id = _resolver_pagador(item.get("pagador"), miembros, default_id=usuario.id)
        gasto = models.GastoGrupo(
            ronda_id=ronda.id, pagador_id=pagador_id,
            descripcion=(item.get("description") or "Gasto"),
            monto=float(amount), emoji=(item.get("emoji") or "💸"),
        )
        db.add(gasto)
        creados.append(gasto)
    db.commit()
    for g in creados:
        db.refresh(g)
    return {
        "created": [schemas.GastoGrupoOut.model_validate(g).model_dump() for g in creados],
        "missing": res["missing"],
    }


@router.get("/grupos/{grupo_id}/gastos", response_model=list[schemas.GastoGrupoOut])
def listar_gastos_grupo(grupo_id: int, db: Session = Depends(get_db),
                        usuario: models.Usuario = Depends(usuario_actual), ctx=Depends(miembro_de_grupo)):
    ronda = _ronda_abierta(db, grupo_id)
    return (db.query(models.GastoGrupo).filter_by(ronda_id=ronda.id)
            .order_by(models.GastoGrupo.id.desc()).all())


@router.delete("/grupos/{grupo_id}/gastos/{gasto_id}", status_code=204)
def borrar_gasto_grupo(grupo_id: int, gasto_id: int, db: Session = Depends(get_db),
                       usuario: models.Usuario = Depends(usuario_actual), ctx=Depends(miembro_de_grupo)):
    grupo, miembro = ctx
    gasto = db.get(models.GastoGrupo, gasto_id)
    if not gasto:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")
    ronda = db.get(models.Ronda, gasto.ronda_id)
    if not ronda or ronda.grupo_id != grupo_id:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")
    if miembro.rol != "admin" and gasto.pagador_id != usuario.id:
        raise HTTPException(status_code=403, detail="Solo el admin o quien pagó puede borrarlo")
    db.delete(gasto)
    db.commit()


@router.get("/grupos/{grupo_id}/historial")
def historial_grupo(grupo_id: int, db: Session = Depends(get_db),
                    usuario: models.Usuario = Depends(usuario_actual), ctx=Depends(miembro_de_grupo)):
    cerradas = (db.query(models.Ronda).filter_by(grupo_id=grupo_id, estado="cerrada")
                .order_by(models.Ronda.id.desc()).all())
    salida = []
    for r in cerradas:
        presentes = [rp.usuario_id for rp in
                     db.query(models.RondaParticipante).filter_by(ronda_id=r.id).all()]
        gastos = db.query(models.GastoGrupo).filter_by(ronda_id=r.id).all()
        saldos = calcular_saldos(presentes, [(g.pagador_id, g.monto) for g in gastos])
        salida.append({
            "ronda_id": r.id,
            "nombre": r.nombre,
            "cerrada_en": r.cerrada_en.isoformat() if r.cerrada_en else None,
            "total": round(sum(g.monto for g in gastos), 2),
            "saldos": [{"usuario_id": u, **v} for u, v in saldos.items()],
            "pagos": simplificar_deudas(saldos),
        })
    return salida
