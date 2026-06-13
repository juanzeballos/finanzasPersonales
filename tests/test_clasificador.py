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
