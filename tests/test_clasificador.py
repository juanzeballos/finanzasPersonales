from datetime import date

from app import models


def test_gasto_divisa_default_ars(Session):
    db = Session()
    g = models.Gasto(usuario_id=1, fecha=date.today(), descripcion="Café",
                      monto=1500, categoria="Café", tipo="prescindible", emoji="☕")
    db.add(g)
    db.commit()
    db.refresh(g)
    assert g.divisa == "ARS"


def test_entrada_divisa_explicita(Session):
    db = Session()
    e = models.Entrada(usuario_id=1, texto="120 usd hotel", divisa="USD")
    db.add(e)
    db.commit()
    db.refresh(e)
    assert e.divisa == "USD"


from app import clasificador, schemas


def _stub_ia(monkeypatch, items, missing=None):
    """Reemplaza ia.clasificar por una respuesta fija."""
    def fake(_texto):
        return schemas.ClasificacionIA(
            items=[schemas.ItemIA(**i) for i in items],
            missing=missing or [],
        )
    monkeypatch.setattr(clasificador.ia, "clasificar", fake)


def test_procesar_usa_divisa_del_chip(Session, monkeypatch):
    db = Session()
    _stub_ia(monkeypatch, [{"description": "Hotel", "amount": 120, "category": "Viajes",
                            "tipo": "prescindible", "emoji": "🏨"}])
    res = clasificador.procesar_texto(db, "hotel 120", usuario_id=1, divisa_chip="USD")
    assert res["created"][0].divisa == "USD"


def test_procesar_texto_pisa_al_chip(Session, monkeypatch):
    db = Session()
    _stub_ia(monkeypatch, [{"description": "Taxi", "amount": 50, "category": "Transporte",
                            "tipo": "necesario", "emoji": "🚕"}])
    # chip en ARS, pero el texto dice "reales" -> BRL
    res = clasificador.procesar_texto(db, "50 reales el taxi", usuario_id=1, divisa_chip="ARS")
    assert res["created"][0].divisa == "BRL"


def test_monto_determinstico_pisa_conversion_de_la_ia(Session, monkeypatch):
    """La IA a veces convierte monedas (ej. "20 usd" -> 1800 pesos). Con un único monto
    detectable en el texto, mandamos el número literal, no lo que devuelve la IA."""
    db = Session()
    _stub_ia(monkeypatch, [{"description": "Cerveza", "amount": 1800, "category": "Restaurante",
                            "tipo": "prescindible", "emoji": "🍺"}])
    res = clasificador.procesar_texto(db, "20 usd de cerveza", usuario_id=1, divisa_chip="USD")
    assert res["created"][0].monto == 20.0
    assert res["created"][0].divisa == "USD"


def test_monto_determinstico_multiples_gastos(Session, monkeypatch):
    """Con varios gastos y misma cantidad de montos detectables, cada uno toma su número literal
    (en orden), aunque la IA los haya convertido."""
    db = Session()
    _stub_ia(monkeypatch, [
        {"description": "Cerveza", "amount": 1800, "category": "Restaurante", "tipo": "prescindible", "emoji": "🍺"},
        {"description": "Maní", "amount": 450, "category": "Comida y delivery", "tipo": "prescindible", "emoji": "🥜"},
    ])
    res = clasificador.procesar_texto(db, "20 usd de cerveza y 5 usd de mani", usuario_id=1, divisa_chip="USD")
    montos = [g.monto for g in res["created"]]
    assert montos == [20.0, 5.0]   # cerveza=20, maní=5 (orden del texto), no 1800/450
