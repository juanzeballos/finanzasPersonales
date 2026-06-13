"""Fixtures de test: base SQLite aislada en memoria + TestClient sin worker.

OJO: usamos TestClient SIN `with` a propósito. El `with` dispararía el lifespan
de la app (que hace create_all sobre la base real ./gastos.db y arranca el worker).
Sin el context manager, el lifespan NO corre: los tests quedan aislados.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.routers import auth as router_auth
from app.database import Base, get_db


@pytest.fixture()
def Session():
    """SessionLocal de test, bound a una SQLite en memoria compartida entre conexiones."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield TestingSession
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(Session):
    """TestClient con get_db apuntando a la base de test. Sin lifespan (sin worker)."""
    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_get_db
    # Desactivar Secure en la cookie para que funcione sobre HTTP en tests
    original_secure = router_auth.COOKIE_SECURE
    router_auth.COOKIE_SECURE = False
    c = TestClient(main.app)
    yield c
    router_auth.COOKIE_SECURE = original_secure
    main.app.dependency_overrides.clear()


@pytest.fixture()
def auth_client(client):
    """Client ya logueado (la cookie de sesión queda guardada en el client)."""
    r = client.post("/registro", json={"email": "t@t.com", "password": "test123", "nombre": "T"})
    assert r.status_code == 200, r.text
    return client
