from app import models, schemas


def test_gastotexto_divisa_default():
    assert schemas.GastoTexto(texto="café 1500").divisa == "ARS"


def test_gastoupdate_todos_opcionales():
    u = schemas.GastoUpdate()
    assert u.monto is None and u.categoria is None and u.tipo is None and u.divisa is None


def test_categorias_incluye_restaurante():
    assert "Restaurante" in schemas.CATEGORIAS


def test_post_gasto_guarda_divisa_en_entrada(auth_client, Session):
    r = auth_client.post("/gastos", json={"texto": "hotel 120", "divisa": "USD"})
    assert r.status_code == 200, r.text
    db = Session()
    entrada = db.query(models.Entrada).order_by(models.Entrada.id.desc()).first()
    assert entrada.estado == "pendiente"
    assert entrada.divisa == "USD"
