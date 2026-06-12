"""Autenticación: hash de contraseñas (bcrypt), tokens JWT y la dependencia
`usuario_actual` que protege los endpoints.

Analogía Java: esto es el corazón de "Spring Security" hecho a mano —
- hashear/verificar ≈ PasswordEncoder (BCrypt)
- crear_token/usuario_actual ≈ el filtro JWT que valida la sesión en cada request.

El token viaja en una COOKIE HttpOnly (el navegador la manda sola; el JS no puede leerla,
así que es más seguro contra robo de token por XSS).
"""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import models
from .database import get_db

# Clave para firmar los tokens. En Fly se setea como secreto (fly secrets set SECRET_KEY=...).
SECRET_KEY = os.getenv("SECRET_KEY", "dev-inseguro-cambiar-en-produccion")
ALGORITMO = "HS256"
TOKEN_DIAS = 30
COOKIE = "token"
# En producción (HTTPS) la cookie va como Secure. En local (http) hay que ponerla en "false".
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"


def hashear(password: str) -> str:
    """Devuelve el hash bcrypt de la contraseña (irreversible)."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verificar(password: str, hash_guardado: str) -> bool:
    """Compara una contraseña con su hash."""
    try:
        return bcrypt.checkpw(password.encode(), hash_guardado.encode())
    except ValueError:
        return False


def crear_token(usuario_id: int) -> str:
    """Genera un JWT firmado que identifica al usuario, con vencimiento."""
    expira = datetime.now(timezone.utc) + timedelta(days=TOKEN_DIAS)
    return jwt.encode({"sub": str(usuario_id), "exp": expira}, SECRET_KEY, algorithm=ALGORITMO)


def usuario_actual(request: Request, db: Session = Depends(get_db)) -> models.Usuario:
    """Dependencia: lee la cookie, valida el token y devuelve el usuario. Si no, 401."""
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITMO])
        usuario_id = int(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Sesión inválida o vencida")
    usuario = db.get(models.Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=401, detail="Usuario inexistente")
    return usuario
