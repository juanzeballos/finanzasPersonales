from datetime import date

from app import models


def test_entrada_fecha_gasto_default_none(Session):
    db = Session()
    e = models.Entrada(usuario_id=1, texto="café 1500", divisa="ARS")
    db.add(e)
    db.commit()
    db.refresh(e)
    assert e.fecha_gasto is None


def test_entrada_fecha_gasto_explicita(Session):
    db = Session()
    e = models.Entrada(usuario_id=1, texto="hotel", divisa="ARS", fecha_gasto=date(2026, 1, 5))
    db.add(e)
    db.commit()
    db.refresh(e)
    assert e.fecha_gasto == date(2026, 1, 5)


from app import clasificador, schemas
from app.tiempo import hoy_local


def _stub_ia(monkeypatch, items):
    def fake(_texto):
        return schemas.ClasificacionIA(items=[schemas.ItemIA(**i) for i in items], missing=[])
    monkeypatch.setattr(clasificador.ia, "clasificar", fake)


def test_gastotexto_fecha_default_none():
    assert schemas.GastoTexto(texto="café 1500").fecha is None


def test_procesar_usa_fecha_dada(Session, monkeypatch):
    db = Session()
    _stub_ia(monkeypatch, [{"description": "Hotel", "amount": 120, "category": "Viajes",
                            "tipo": "prescindible", "emoji": "🏨"}])
    res = clasificador.procesar_texto(db, "hotel 120", usuario_id=1, fecha=date(2026, 1, 5))
    assert res["created"][0].fecha == date(2026, 1, 5)


def test_procesar_sin_fecha_usa_hoy(Session, monkeypatch):
    db = Session()
    _stub_ia(monkeypatch, [{"description": "Café", "amount": 1500, "category": "Café",
                            "tipo": "prescindible", "emoji": "☕"}])
    res = clasificador.procesar_texto(db, "café 1500", usuario_id=1)
    assert res["created"][0].fecha == hoy_local()


def test_post_guarda_fecha_en_entrada(auth_client, Session):
    r = auth_client.post("/gastos", json={"texto": "hotel 120", "divisa": "USD", "fecha": "2026-01-05"})
    assert r.status_code == 200, r.text
    db = Session()
    entrada = db.query(models.Entrada).order_by(models.Entrada.id.desc()).first()
    assert entrada.fecha_gasto == date(2026, 1, 5)


def test_post_sin_fecha_deja_none(auth_client, Session):
    r = auth_client.post("/gastos", json={"texto": "café 1500"})
    assert r.status_code == 200, r.text
    db = Session()
    entrada = db.query(models.Entrada).order_by(models.Entrada.id.desc()).first()
    assert entrada.fecha_gasto is None


def test_post_fecha_invalida_400(auth_client):
    r = auth_client.post("/gastos", json={"texto": "café 1500", "fecha": "no-es-fecha"})
    assert r.status_code == 400
