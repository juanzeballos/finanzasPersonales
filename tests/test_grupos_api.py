from app import ia


def _registrar(cli, email, nombre):
    r = cli.post("/registro", json={"email": email, "password": "test123", "nombre": nombre})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _stub_ia(monkeypatch, items, missing=None):
    monkeypatch.setattr(ia, "clasificar_grupo",
                        lambda texto, nombres: {"items": items, "missing": missing or []})


def _pid(detalle, nombre):
    return next(p["id"] for p in detalle["participantes"] if p["nombre"] == nombre)


def test_crear_grupo_y_detalle(client):
    _registrar(client, "lucas@t.com", "Lucas")
    d = client.post("/grupos", json={"nombre": "Peña del viernes", "divisa": "ARS"})
    assert d.status_code == 200, d.text
    d = d.json()
    assert d["grupo"]["nombre"] == "Peña del viernes"
    assert d["ronda"]["estado"] == "abierta"
    yo = next(p for p in d["participantes"] if p["id"] == d["yo_id"])
    assert yo["nombre"] == "Lucas" and yo["rol"] == "admin" and yo["usuario_id"] is not None
    assert d["presentes"] == [d["yo_id"]]
    assert d["invite_code"]


def test_agregar_participante_por_nombre(client):
    _registrar(client, "lucas@t.com", "Lucas")
    gid = client.post("/grupos", json={"nombre": "Peña"}).json()["grupo"]["id"]
    d = client.post(f"/grupos/{gid}/participantes", json={"nombre": "Tomás"}).json()
    tomas = next(p for p in d["participantes"] if p["nombre"] == "Tomás")
    assert tomas["usuario_id"] is None          # placeholder, sin cuenta
    assert tomas["id"] in d["presentes"]         # presente por defecto


def test_pagador_placeholder_por_nombre(client, monkeypatch):
    _registrar(client, "lucas@t.com", "Lucas")
    gid = client.post("/grupos", json={"nombre": "Peña"}).json()["grupo"]["id"]
    d = client.post(f"/grupos/{gid}/participantes", json={"nombre": "Tomás"}).json()
    tomas_pid = _pid(d, "Tomás")
    _stub_ia(monkeypatch, [{"pagador": "Tomás", "description": "Carne", "amount": 13000, "emoji": "🥩"}])
    r = client.post(f"/grupos/{gid}/gastos", json={"texto": "Tomás pagó 13mil de carne"})
    assert r.json()["created"][0]["pagador_id"] == tomas_pid


def test_pagador_default_es_quien_carga(client, monkeypatch):
    _registrar(client, "lucas@t.com", "Lucas")
    d = client.post("/grupos", json={"nombre": "Peña"}).json()
    gid, yo = d["grupo"]["id"], d["yo_id"]
    _stub_ia(monkeypatch, [{"pagador": None, "description": "Hielo", "amount": 2000, "emoji": "🧊"}])
    r = client.post(f"/grupos/{gid}/gastos", json={"texto": "hielo 2000"})
    assert r.json()["created"][0]["pagador_id"] == yo


def test_join_reclamando_placeholder(client, client2):
    _registrar(client, "lucas@t.com", "Lucas")
    d = client.post("/grupos", json={"nombre": "Peña"}).json()
    gid, code = d["grupo"]["id"], d["invite_code"]
    d = client.post(f"/grupos/{gid}/participantes", json={"nombre": "Pedro"}).json()
    pedro_pid = _pid(d, "Pedro")
    puid = _registrar(client2, "pedro@t.com", "Pedro Gómez")
    # preview: Pedro aparece como libre
    prev = client2.get(f"/grupos/preview/{code}").json()
    assert any(p["id"] == pedro_pid for p in prev["participantes_libres"])
    # se une reclamando a Pedro
    assert client2.post("/grupos/join", json={"code": code, "participante_id": pedro_pid}).status_code == 200
    d3 = client2.get(f"/grupos/{gid}").json()
    assert d3["yo_id"] == pedro_pid                                   # ahora ES Pedro
    pedro = next(p for p in d3["participantes"] if p["id"] == pedro_pid)
    assert pedro["usuario_id"] == puid


def test_join_soy_nuevo(client, client2):
    _registrar(client, "lucas@t.com", "Lucas")
    d = client.post("/grupos", json={"nombre": "Peña"}).json()
    gid, code = d["grupo"]["id"], d["invite_code"]
    _registrar(client2, "ana@t.com", "Ana")
    assert client2.get(f"/grupos/{gid}").status_code == 403           # todavía no
    client2.post("/grupos/join", json={"code": code})                # sin participante_id = soy nuevo
    d3 = client2.get(f"/grupos/{gid}").json()
    ana = next(p for p in d3["participantes"] if p["id"] == d3["yo_id"])
    assert ana["nombre"] == "Ana" and ana["usuario_id"] is not None


def test_saldos_y_quien_paga_a_quien(client, client2, monkeypatch):
    _registrar(client, "lucas@t.com", "Lucas")
    d = client.post("/grupos", json={"nombre": "Peña"}).json()
    gid, code, luc_pid = d["grupo"]["id"], d["invite_code"], d["yo_id"]
    _registrar(client2, "pedro@t.com", "Pedro")
    client2.post("/grupos/join", json={"code": code})
    ped_pid = client2.get(f"/grupos/{gid}").json()["yo_id"]
    _stub_ia(monkeypatch, [{"pagador": None, "description": "Asado", "amount": 1000, "emoji": "🥩"}])
    client.post(f"/grupos/{gid}/gastos", json={"texto": "asado 1000"})   # Lucas paga 1000
    d2 = client.get(f"/grupos/{gid}").json()
    saldos = {s["participante_id"]: s["saldo"] for s in d2["saldos"]}
    assert saldos[luc_pid] == 500.0 and saldos[ped_pid] == -500.0
    assert d2["pagos"] == [{"de": ped_pid, "a": luc_pid, "monto": 500.0}]


def test_cerrar_ronda_abre_nueva_y_archiva(client):
    _registrar(client, "lucas@t.com", "Lucas")
    d = client.post("/grupos", json={"nombre": "Peña"}).json()
    gid, ronda1 = d["grupo"]["id"], d["ronda"]["id"]
    d2 = client.post(f"/grupos/{gid}/cerrar-ronda").json()
    assert d2["ronda"]["id"] != ronda1 and d2["ronda"]["estado"] == "abierta"
    hist = client.get(f"/grupos/{gid}/historial").json()
    assert len(hist) == 1 and hist[0]["ronda_id"] == ronda1


def test_borrar_gasto_permisos(client, client2, monkeypatch):
    _registrar(client, "lucas@t.com", "Lucas")
    d = client.post("/grupos", json={"nombre": "Peña"}).json()
    gid, code = d["grupo"]["id"], d["invite_code"]
    _registrar(client2, "pedro@t.com", "Pedro")
    client2.post("/grupos/join", json={"code": code})
    _stub_ia(monkeypatch, [{"pagador": None, "description": "Hielo", "amount": 2000, "emoji": "🧊"}])
    gasto_id = client.post(f"/grupos/{gid}/gastos", json={"texto": "hielo 2000"}).json()["created"][0]["id"]
    assert client2.delete(f"/grupos/{gid}/gastos/{gasto_id}").status_code == 403   # Pedro no
    assert client.delete(f"/grupos/{gid}/gastos/{gasto_id}").status_code == 204    # Lucas (admin+pagador) sí
