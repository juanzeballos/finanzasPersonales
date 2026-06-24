"""Modelos ORM = las tablas de la base.

Analogía Java: cada clase es una @Entity de JPA. 'usuario_id' es la clave foránea
(@ManyToOne) que ata cada dato a su dueño, para que cada usuario vea solo lo suyo.
"""

from datetime import date, datetime

from sqlalchemy import DateTime, Date, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    nombre: Mapped[str | None] = mapped_column(String, nullable=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)  # NUNCA la contraseña en texto plano
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Gasto(Base):
    __tablename__ = "gastos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    descripcion: Mapped[str] = mapped_column(String, nullable=False)
    monto: Mapped[float] = mapped_column(Float, nullable=False)
    categoria: Mapped[str] = mapped_column(String, nullable=False)
    tipo: Mapped[str] = mapped_column(String, nullable=False)  # fijo | necesario | prescindible
    divisa: Mapped[str] = mapped_column(String, nullable=False, default="ARS")  # ARS|USD|BRL|EUR
    emoji: Mapped[str] = mapped_column(String, nullable=False, default="💸")
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Entrada(Base):
    """Bandeja de entrada: cada texto entra como 'pendiente'; el worker lo clasifica."""

    __tablename__ = "entradas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=False)
    texto: Mapped[str] = mapped_column(String, nullable=False)
    estado: Mapped[str] = mapped_column(String, nullable=False, default="pendiente")  # pendiente|procesado|error
    divisa: Mapped[str] = mapped_column(String, nullable=False, default="ARS")  # divisa elegida en el chip al cargar
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ClasificacionAprendida(Base):
    """Memoria de clasificaciones, AHORA por usuario: cada uno aprende sus propios conceptos."""

    __tablename__ = "clasificacion_aprendida"
    __table_args__ = (UniqueConstraint("usuario_id", "concepto", name="uq_usuario_concepto"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=False)
    concepto: Mapped[str] = mapped_column(String, nullable=False)  # "netflix", "supermercado"
    descripcion: Mapped[str] = mapped_column(String, nullable=False)
    categoria: Mapped[str] = mapped_column(String, nullable=False)
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    emoji: Mapped[str] = mapped_column(String, nullable=False, default="💸")
    usos: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ============================================================
#  Gastos en grupo (dividir cuentas estilo Splitwise)
#  Ledger SEPARADO del gasto personal.
# ============================================================

class Grupo(Base):
    """Un grupo (peña, vacaciones, etc.). Tiene miembros y una secuencia de rondas."""

    __tablename__ = "grupos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    divisa: Mapped[str] = mapped_column(String, nullable=False, default="ARS")  # ARS|USD|BRL|EUR
    creador_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    invite_code: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class GrupoMiembro(Base):
    """Pertenencia de un usuario a un grupo, con rol (admin = el creador)."""

    __tablename__ = "grupo_miembros"
    __table_args__ = (UniqueConstraint("grupo_id", "usuario_id", name="uq_grupo_usuario"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos.id"), index=True, nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=False)
    rol: Mapped[str] = mapped_column(String, nullable=False, default="miembro")  # admin|miembro
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Ronda(Base):
    """Una ronda del grupo. Siempre hay UNA 'abierta' (se garantiza en código)."""

    __tablename__ = "rondas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos.id"), index=True, nullable=False)
    nombre: Mapped[str | None] = mapped_column(String, nullable=True)
    estado: Mapped[str] = mapped_column(String, nullable=False, default="abierta")  # abierta|cerrada
    abierta_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    cerrada_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RondaParticipante(Base):
    """Los 'presentes' de una ronda: entre quiénes se divide cada gasto de esa ronda."""

    __tablename__ = "ronda_participantes"
    __table_args__ = (UniqueConstraint("ronda_id", "usuario_id", name="uq_ronda_usuario"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ronda_id: Mapped[int] = mapped_column(ForeignKey("rondas.id"), index=True, nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)


class GastoGrupo(Base):
    """Un gasto de una ronda. `pagador_id` = quién pagó (puede no ser quien lo cargó)."""

    __tablename__ = "gastos_grupo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ronda_id: Mapped[int] = mapped_column(ForeignKey("rondas.id"), index=True, nullable=False)
    pagador_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    descripcion: Mapped[str] = mapped_column(String, nullable=False)
    monto: Mapped[float] = mapped_column(Float, nullable=False)
    emoji: Mapped[str] = mapped_column(String, nullable=False, default="💸")
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
