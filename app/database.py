"""Conexión a la base de datos (SQLite vía SQLAlchemy).

Analogía Java: esto es el equivalente a configurar el DataSource + SessionFactory
de Hibernate. 'engine' = el pool de conexiones; 'SessionLocal' = la fábrica de
sesiones (como sessionFactory.openSession()); 'Base' = la clase base de las
entidades (como una @Entity con su mapeo).
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Por defecto un archivo local; en la nube se setea DATABASE_URL apuntando al volumen
# persistente (ej. "sqlite:////data/gastos.db"). Así los datos sobreviven a los redeploys.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gastos.db")

# check_same_thread=False: SQLite por defecto ata la conexión a un solo hilo;
# FastAPI usa varios, así que lo desactivamos (es seguro con SessionLocal por request).
# timeout=30: si el worker y el web escriben a la vez, esperar hasta 30s por el lock
# en vez de fallar al toque ("database is locked").
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30})

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
