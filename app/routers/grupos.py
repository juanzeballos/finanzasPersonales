"""Endpoints de gastos en grupo (dividir cuentas). Ledger separado del gasto personal.

Un grupo tiene `Participante`s: pueden ser usuarios reales (usuario_id seteado) o
placeholders por nombre (usuario_id NULL) hasta que alguien los reclame al unirse.
Auth: `miembro_de_grupo` exige un Participante con tu usuario_id; `admin_de_grupo`, rol admin.
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


def _participantes(db: Session, grupo_id: int) -> list[models.Participante]:
    return db.query(models.Participante).filter_by(grupo_id=grupo_id).order_by(models.Participante.id).all()


def _mi_participante(db: Session, grupo_id: int, usuario_id: int) -> models.Participante | None:
    return db.query(models.Participante).filter_by(grupo_id=grupo_id, usuario_id=usuario_id).first()


def miembro_de_grupo(grupo_id: int, db: Session = Depends(get_db),
                     usuario: models.Usuario = Depends(usuario_actual)):
    """Devuelve (grupo, mi_participante) o corta con 404/403."""
    grupo = db.get(models.Grupo, grupo_id)
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    mio = _mi_participante(db, grupo_id, usuario.id)
    if not mio:
        raise HTTPException(status_code=403, detail="No sos miembro de este grupo")
    return grupo, mio


def admin_de_grupo(ctx=Depends(miembro_de_grupo)):
    grupo, mio = ctx
    if mio.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo el admin del grupo puede hacer esto")
    return ctx


def _ronda_abierta(db: Session, grupo_id: int) -> models.Ronda:
    ronda = (db.query(models.Ronda).filter_by(grupo_id=grupo_id, estado="abierta")
             .order_by(models.Ronda.id.desc()).first())
    if not ronda:
        raise HTTPException(status_code=409, detail="El grupo no tiene una ronda abierta")
    return ronda


def _resolver_pagador(nombre: str | None, participantes: list[models.Participante], default_id: int) -> int:
    """Matchea el nombre devuelto por la IA contra un participante (por nombre de pila normalizado).
    'yo'/sin nombre/sin match → default_id (el participante de quien está cargando)."""
    if not nombre:
        return default_id
    palabras = normalizar(nombre).split()
    if not palabras or palabras[0] in ("yo", "mi", "mio", "mia"):
        return default_id
    objetivo = palabras[0]
    for p in participantes:
        ref = normalizar(p.nombre).split()
        if ref and ref[0] == objetivo:
            return p.id
    return default_id


def _armar_detalle(db: Session, grupo: models.Grupo, mio: models.Participante) -> schemas.GrupoDetalleOut:
    ronda = _ronda_abierta(db, grupo.id)
    participantes = _participantes(db, grupo.id)
    presentes = [rp.participante_id for rp in
                 db.query(models.RondaParticipante).filter_by(ronda_id=ronda.id).all()]
    gastos = (db.query(models.GastoGrupo).filter_by(ronda_id=ronda.id)
              .order_by(models.GastoGrupo.id.desc()).all())
    saldos = calcular_saldos(presentes, [(g.pagador_id, g.monto) for g in gastos])
    pagos = simplificar_deudas(saldos)
    return schemas.GrupoDetalleOut(
        grupo=schemas.GrupoOut.model_validate(grupo),
        participantes=[schemas.ParticipanteOut.model_validate(p) for p in participantes],
        ronda=schemas.RondaOut.model_validate(ronda),
        presentes=presentes,
        gastos=[schemas.GastoGrupoOut.model_validate(g) for g in gastos],
        saldos=[schemas.SaldoOut(participante_id=pid, **v) for pid, v in saldos.items()],
        pagos=[schemas.PagoOut(**p) for p in pagos],
        yo_id=mio.id,
        invite_code=grupo.invite_code if mio.rol == "admin" else None,
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
    mio = models.Participante(grupo_id=grupo.id, usuario_id=usuario.id,
                              nombre=(usuario.nombre or usuario.email), rol="admin")
    db.add(mio)
    ronda = models.Ronda(grupo_id=grupo.id, estado="abierta")
    db.add(ronda)
    db.flush()
    db.add(models.RondaParticipante(ronda_id=ronda.id, participante_id=mio.id))
    db.commit()
    db.refresh(grupo)
    db.refresh(mio)
    return _armar_detalle(db, grupo, mio)


@router.get("/grupos", response_model=list[schemas.GrupoOut])
def mis_grupos(db: Session = Depends(get_db), usuario: models.Usuario = Depends(usuario_actual)):
    return (db.query(models.Grupo)
            .join(models.Participante, models.Participante.grupo_id == models.Grupo.id)
            .filter(models.Participante.usuario_id == usuario.id)
            .order_by(models.Grupo.id.desc()).all())


@router.get("/grupos/preview/{code}")
def preview_grupo(code: str, db: Session = Depends(get_db),
                  usuario: models.Usuario = Depends(usuario_actual)):
    """Antes de unirse: datos del grupo + participantes libres (placeholders) para elegir cuál sos."""
    grupo = db.query(models.Grupo).filter_by(invite_code=code.strip()).first()
    if not grupo:
        raise HTTPException(status_code=404, detail="Código de invitación inválido")
    ya = _mi_participante(db, grupo.id, usuario.id)
    libres = (db.query(models.Participante)
              .filter_by(grupo_id=grupo.id, usuario_id=None).order_by(models.Participante.nombre).all())
    return {
        "grupo": {"id": grupo.id, "nombre": grupo.nombre, "divisa": grupo.divisa},
        "ya_miembro": ya is not None,
        "participantes_libres": [{"id": p.id, "nombre": p.nombre} for p in libres],
    }


@router.post("/grupos/join", response_model=schemas.GrupoOut)
def unirse(payload: schemas.JoinIn, db: Session = Depends(get_db),
           usuario: models.Usuario = Depends(usuario_actual)):
    grupo = db.query(models.Grupo).filter_by(invite_code=payload.code.strip()).first()
    if not grupo:
        raise HTTPException(status_code=404, detail="Código de invitación inválido")
    ya = _mi_participante(db, grupo.id, usuario.id)
    if ya:
        return schemas.GrupoOut.model_validate(grupo)

    ronda = db.query(models.Ronda).filter_by(grupo_id=grupo.id, estado="abierta").first()
    if payload.participante_id is not None:
        # reclamar un placeholder existente
        p = db.get(models.Participante, payload.participante_id)
        if not p or p.grupo_id != grupo.id or p.usuario_id is not None:
            raise HTTPException(status_code=400, detail="Ese integrante no está disponible")
        p.usuario_id = usuario.id
        nuevo = p
    else:
        # soy nuevo: crear mi participante
        nuevo = models.Participante(grupo_id=grupo.id, usuario_id=usuario.id,
                                    nombre=(usuario.nombre or usuario.email), rol="miembro")
        db.add(nuevo)
        db.flush()
        if ronda and not db.query(models.RondaParticipante).filter_by(
                ronda_id=ronda.id, participante_id=nuevo.id).first():
            db.add(models.RondaParticipante(ronda_id=ronda.id, participante_id=nuevo.id))
    db.commit()
    return schemas.GrupoOut.model_validate(grupo)


@router.get("/grupos/{grupo_id}", response_model=schemas.GrupoDetalleOut)
def detalle_grupo(grupo_id: int, db: Session = Depends(get_db),
                  usuario: models.Usuario = Depends(usuario_actual), ctx=Depends(miembro_de_grupo)):
    grupo, mio = ctx
    return _armar_detalle(db, grupo, mio)


@router.post("/grupos/{grupo_id}/participantes", response_model=schemas.GrupoDetalleOut)
def agregar_participante(grupo_id: int, payload: schemas.AgregarParticipanteIn,
                         db: Session = Depends(get_db),
                         usuario: models.Usuario = Depends(usuario_actual), ctx=Depends(miembro_de_grupo)):
    """Agrega un integrante por nombre (placeholder, sin cuenta). Cualquier miembro puede."""
    grupo, mio = ctx
    nombre = payload.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    p = models.Participante(grupo_id=grupo_id, usuario_id=None, nombre=nombre, rol="miembro")
    db.add(p)
    db.flush()
    ronda = _ronda_abierta(db, grupo_id)
    db.add(models.RondaParticipante(ronda_id=ronda.id, participante_id=p.id))   # presente por defecto
    db.commit()
    return _armar_detalle(db, grupo, mio)


@router.post("/grupos/{grupo_id}/invite/rotate")
def rotar_code(grupo_id: int, db: Session = Depends(get_db),
               usuario: models.Usuario = Depends(usuario_actual), ctx=Depends(admin_de_grupo)):
    grupo, _ = ctx
    grupo.invite_code = _nuevo_code()
    db.commit()
    return {"invite_code": grupo.invite_code}


@router.post("/grupos/{grupo_id}/rondas/{ronda_id}/presentes", response_model=schemas.GrupoDetalleOut)
def set_presentes(grupo_id: int, ronda_id: int, payload: schemas.PresentesIn,
                  db: Session = Depends(get_db),
                  usuario: models.Usuario = Depends(usuario_actual), ctx=Depends(miembro_de_grupo)):
    grupo, mio = ctx
    ronda = db.get(models.Ronda, ronda_id)
    if not ronda or ronda.grupo_id != grupo_id or ronda.estado != "abierta":
        raise HTTPException(status_code=400, detail="Ronda inválida o cerrada")
    ids_ok = {p.id for p in _participantes(db, grupo_id)}
    nuevos = [pid for pid in payload.participante_ids if pid in ids_ok]
    db.query(models.RondaParticipante).filter_by(ronda_id=ronda_id).delete()
    for pid in nuevos:
        db.add(models.RondaParticipante(ronda_id=ronda_id, participante_id=pid))
    db.commit()
    return _armar_detalle(db, grupo, mio)


@router.post("/grupos/{grupo_id}/cerrar-ronda", response_model=schemas.GrupoDetalleOut)
def cerrar_ronda(grupo_id: int, db: Session = Depends(get_db),
                 usuario: models.Usuario = Depends(usuario_actual), ctx=Depends(admin_de_grupo)):
    grupo, mio = ctx
    ronda = _ronda_abierta(db, grupo_id)
    presentes = [rp.participante_id for rp in
                 db.query(models.RondaParticipante).filter_by(ronda_id=ronda.id).all()]
    ronda.estado = "cerrada"
    ronda.cerrada_en = datetime.now(timezone.utc)
    nueva = models.Ronda(grupo_id=grupo_id, estado="abierta")
    db.add(nueva)
    db.flush()
    for pid in presentes:   # la nueva ronda hereda los presentes
        db.add(models.RondaParticipante(ronda_id=nueva.id, participante_id=pid))
    db.commit()
    return _armar_detalle(db, grupo, mio)


@router.post("/grupos/{grupo_id}/gastos")
def crear_gasto_grupo(grupo_id: int, payload: schemas.GastoGrupoTexto, db: Session = Depends(get_db),
                      usuario: models.Usuario = Depends(usuario_actual), ctx=Depends(miembro_de_grupo)):
    grupo, mio = ctx
    ronda = _ronda_abierta(db, grupo_id)
    participantes = _participantes(db, grupo_id)
    nombres = [p.nombre for p in participantes]
    try:
        res = ia.clasificar_grupo(payload.texto.strip(), nombres)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error de la IA: {e}")

    creados = []
    for item in res["items"]:
        amount = item.get("amount")
        if not amount:
            continue
        pagador_id = _resolver_pagador(item.get("pagador"), participantes, default_id=mio.id)
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
    grupo, mio = ctx
    gasto = db.get(models.GastoGrupo, gasto_id)
    if not gasto:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")
    ronda = db.get(models.Ronda, gasto.ronda_id)
    if not ronda or ronda.grupo_id != grupo_id:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")
    if mio.rol != "admin" and gasto.pagador_id != mio.id:
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
        presentes = [rp.participante_id for rp in
                     db.query(models.RondaParticipante).filter_by(ronda_id=r.id).all()]
        gastos = db.query(models.GastoGrupo).filter_by(ronda_id=r.id).all()
        saldos = calcular_saldos(presentes, [(g.pagador_id, g.monto) for g in gastos])
        salida.append({
            "ronda_id": r.id,
            "nombre": r.nombre,
            "cerrada_en": r.cerrada_en.isoformat() if r.cerrada_en else None,
            "total": round(sum(g.monto for g in gastos), 2),
            "saldos": [{"participante_id": pid, **v} for pid, v in saldos.items()],
            "pagos": simplificar_deudas(saldos),
        })
    return salida
