"""Conexión a la base de datos (SQLite vía SQLAlchemy).

Analogía Java: esto es el equivalente a configurar el DataSource + SessionFactory
de Hibernate. 'engine' = el pool de conexiones; 'SessionLocal' = la fábrica de
sesiones (como sessionFactory.openSession()); 'Base' = la clase base de las
entidades (como una @Entity con su mapeo).
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Por defecto SQLite local; en producción se setea DATABASE_URL a Postgres
# (ej. "postgresql+psycopg://usuario:pass@db:5432/gastos").
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gastos.db")

if DATABASE_URL.startswith("sqlite"):
    # SQLite: permitir varios hilos (FastAPI usa varios) y esperar el lock hasta 30s
    # en vez de fallar al toque ("database is locked").
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30})
else:
    # Postgres u otros: pool_pre_ping evita usar conexiones que el servidor ya cerró.
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Clase base para los modelos ORM (las 'entidades')."""
    pass


def get_db():
    """Provee una sesión de DB por request y la cierra al terminar.

    El 'yield' hace que FastAPI inyecte la sesión y, pase lo que pase, ejecute
    el 'finally' (cerrar). Es el patrón de inyección de dependencias de FastAPI,
    parecido a un @Transactional / try-with-resources de Java.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
