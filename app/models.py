"""Modelos ORM = las tablas de la base.

Analogía Java: esta clase Gasto es como una @Entity de JPA/Hibernate. Cada
'mapped_column' es como una @Column. SQLAlchemy crea/lee la tabla 'gastos'.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Gasto(Base):
    __tablename__ = "gastos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    descripcion: Mapped[str] = mapped_column(String, nullable=False)
    monto: Mapped[float] = mapped_column(Float, nullable=False)
    categoria: Mapped[str] = mapped_column(String, nullable=False)
    # tipo: "fijo" | "necesario" | "prescindible"
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    emoji: Mapped[str] = mapped_column(String, nullable=False, default="💸")
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ClasificacionAprendida(Base):
    """Memoria de clasificaciones: aprende cómo se clasificó cada 'concepto' (ej. "netflix")
    y, sobre todo, las correcciones manuales del usuario. Se reusa para clasificar más rápido
    y de forma consistente. La clave es el concepto normalizado (sin acentos, en minúsculas).
    """

    __tablename__ = "clasificacion_aprendida"

    concepto: Mapped[str] = mapped_column(String, primary_key=True)  # "netflix", "supermercado"
    descripcion: Mapped[str] = mapped_column(String, nullable=False)  # display lindo: "Netflix"
    categoria: Mapped[str] = mapped_column(String, nullable=False)
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    emoji: Mapped[str] = mapped_column(String, nullable=False, default="💸")
    usos: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Entrada(Base):
    """Bandeja de entrada: cada texto que carga el usuario entra acá como 'pendiente'.
    El worker en segundo plano lo agarra, lo clasifica (creando Gasto(s)) y lo marca
    'procesado'. Si la IA falla o no hay monto, queda 'error' con el mensaje.
    Es lo que desacopla la clasificación lenta del pedido HTTP del usuario.
    """

    __tablename__ = "entradas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    texto: Mapped[str] = mapped_column(String, nullable=False)
    # "pendiente" | "procesado" | "error"
    estado: Mapped[str] = mapped_column(String, nullable=False, default="pendiente")
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
