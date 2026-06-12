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
    emoji: Mapped[str] = mapped_column(String, nullable=False, default="💸")
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Entrada(Base):
    """Bandeja de entrada: cada texto entra como 'pendiente'; el worker lo clasifica."""

    __tablename__ = "entradas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=False)
    texto: Mapped[str] = mapped_column(String, nullable=False)
    estado: Mapped[str] = mapped_column(String, nullable=False, default="pendiente")  # pendiente|procesado|error
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
