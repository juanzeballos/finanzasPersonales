import pytest

from app.parsing import detectar_divisa


@pytest.mark.parametrize("texto,esperado", [
    ("3 dolares de propina", "USD"),
    ("120 usd hotel", "USD"),
    ("pagué 50 us$ en el aeropuerto", "USD"),
    ("u$s 200 ahorro", "USD"),
    ("30 euros del museo", "EUR"),
    ("€10 cafe", "EUR"),
    ("50 reales el taxi", "BRL"),
    ("R$ 20 agua", "BRL"),
    ("café 1500", None),
    ("8 lucas de super", None),
    ("algo doloroso", None),   # no debe confundir 'dolor' con 'dolar'
])
def test_detectar_divisa(texto, esperado):
    assert detectar_divisa(texto) == esperado
