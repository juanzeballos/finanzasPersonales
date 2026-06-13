from datetime import date

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


def _crear_gasto(Session, usuario_id, **kw):
    db = Session()
    defaults = dict(usuario_id=usuario_id, fecha=date.today(), descripcion="Café",
                    monto=1500, categoria="Café", tipo="prescindible", emoji="☕", divisa="ARS")
    defaults.update(kw)
    g = models.Gasto(**defaults)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g.id


def _uid(auth_client):
    return auth_client.get("/yo").json()["id"]


def test_patch_edita_monto_categoria_divisa(auth_client, Session):
    gid = _crear_gasto(Session, _uid(auth_client))
    r = auth_client.patch(f"/gastos/{gid}", json={"monto": 2000, "categoria": "Restaurante", "divisa": "USD"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["monto"] == 2000
    assert body["categoria"] == "Restaurante"
    assert body["divisa"] == "USD"


def test_patch_monto_invalido(auth_client, Session):
    gid = _crear_gasto(Session, _uid(auth_client))
    r = auth_client.patch(f"/gastos/{gid}", json={"monto": 0})
    assert r.status_code == 400


def test_patch_divisa_invalida(auth_client, Session):
    gid = _crear_gasto(Session, _uid(auth_client))
    r = auth_client.patch(f"/gastos/{gid}", json={"divisa": "GBP"})
    assert r.status_code == 400


def test_patch_categoria_aprende(auth_client, Session):
    gid = _crear_gasto(Session, _uid(auth_client))
    auth_client.patch(f"/gastos/{gid}", json={"categoria": "Restaurante"})
    db = Session()
    fila = db.query(models.ClasificacionAprendida).filter_by(usuario_id=_uid(auth_client), concepto="cafe").first()
    assert fila is not None and fila.categoria == "Restaurante"


def test_resumen_filtra_por_divisa(auth_client, Session):
    uid = _uid(auth_client)
    hoy = date.today()
    mes = hoy.strftime("%Y-%m")
    _crear_gasto(Session, uid, monto=1000, divisa="ARS", fecha=hoy)
    _crear_gasto(Session, uid, monto=50, divisa="USD", fecha=hoy)

    ars = auth_client.get(f"/resumen?mes={mes}").json()       # default ARS
    usd = auth_client.get(f"/resumen?mes={mes}&divisa=USD").json()
    assert ars["total"] == 1000
    assert usd["total"] == 50
    assert set(ars["monedas"]) == {"ARS", "USD"}
