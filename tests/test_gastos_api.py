from app import schemas


def test_gastotexto_divisa_default():
    assert schemas.GastoTexto(texto="café 1500").divisa == "ARS"


def test_gastoupdate_todos_opcionales():
    u = schemas.GastoUpdate()
    assert u.monto is None and u.categoria is None and u.tipo is None and u.divisa is None


def test_categorias_incluye_restaurante():
    assert "Restaurante" in schemas.CATEGORIAS
