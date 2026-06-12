"""Endpoints de autenticación: registro, login, logout y /yo."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import COOKIE, COOKIE_SECURE, TOKEN_DIAS, crear_token, hashear, usuario_actual, verificar
from ..database import get_db

router = APIRouter()


def _poner_cookie(resp: Response, usuario_id: int) -> None:
    """Mete el token en una cookie HttpOnly (el navegador la manda sola en cada request)."""
    resp.set_cookie(
        COOKIE, crear_token(usuario_id),
        httponly=True, secure=COOKIE_SECURE, samesite="lax",
        max_age=TOKEN_DIAS * 24 * 3600,
    )


@router.post("/registro", response_model=schemas.UsuarioOut)
def registro(payload: schemas.UsuarioCrear, resp: Response, db: Session = Depends(get_db)):
    """Crea una cuenta nueva y deja al usuario logueado."""
    email = payload.email.strip().lower()
    if db.query(models.Usuario).filter(models.Usuario.email == email).first():
        raise HTTPException(status_code=400, detail="Ya existe una cuenta con ese email")
    usuario = models.Usuario(email=email, password_hash=hashear(payload.password))
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    _poner_cookie(resp, usuario.id)
    return usuario


@router.post("/login", response_model=schemas.UsuarioOut)
def login(payload: schemas.UsuarioCrear, resp: Response, db: Session = Depends(get_db)):
    """Verifica email + contraseña y deja la cookie de sesión."""
    email = payload.email.strip().lower()
    usuario = db.query(models.Usuario).filter(models.Usuario.email == email).first()
    if not usuario or not verificar(payload.password, usuario.password_hash):
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    _poner_cookie(resp, usuario.id)
    return usuario


@router.post("/logout")
def logout(resp: Response):
    """Borra la cookie de sesión."""
    resp.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/yo", response_model=schemas.UsuarioOut)
def yo(usuario: models.Usuario = Depends(usuario_actual)):
    """Devuelve el usuario logueado (para que el front sepa si hay sesión)."""
    return usuario
