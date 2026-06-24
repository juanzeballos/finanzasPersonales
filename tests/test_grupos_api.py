from app import ia


def _registrar(cli, email, nombre):
    r = cli.post("/registro", json={"email": email, "password": "test123", "nombre": nombre})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _stub_ia(monkeypatch, items, missing=None):
    monkeypatch.setattr(ia, "clasificar_grupo",
                        lambda texto, nombres: {"items": items, "missing": missing or []})


def test_crear_grupo_y_detalle(client):
    uid = _registrar(client, "lucas@t.com", "Lucas")
    r = client.post("/grupos", json={"nombre": "Peña del viernes", "divisa": "ARS"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["grupo"]["nombre"] == "Peña del viernes"
    assert d["ronda"]["estado"] == "abierta"
    assert d["presentes"] == [uid]
    assert any(m["usuario_id"] == uid and m["rol"] == "admin" for m in d["miembros"])
    assert d["invite_code"]  # el admin ve el código


def test_join_y_no_miembro_403(client, client2):
    _registrar(client, "lucas@t.com", "Lucas")
    g = client.post("/grupos", json={"nombre": "Peña"}).json()
    gid, code = g["grupo"]["id"], g["invite_code"]
    _registrar(client2, "pedro@t.com", "Pedro")
    assert client2.get(f"/grupos/{gid}").status_code == 403       # todavía no es miembro
    assert client2.post("/grupos/join", json={"code": code}).status_code == 200
    assert client2.get(f"/grupos/{gid}").status_code == 200       # ahora sí


def test_pagador_por_nombre(client, client2, monkeypatch):
    _registrar(client, "lucas@t.com", "Lucas")
    g = client.post("/grupos", json={"nombre": "Peña"}).json()
    gid, code = g["grupo"]["id"], g["invite_code"]
    puid = _registrar(client2, "pedro@t.com", "Pedro")
    client2.post("/grupos/join", json={"code": code})
    # Lucas (quien tipea) carga, pero el texto dice que pagó Pedro
    _stub_ia(monkeypatch, [{"pagador": "Pedro", "description": "Carne", "amount": 13000, "emoji": "🥩"}])
    r = client.post(f"/grupos/{gid}/gastos", json={"texto": "Pedro pagó 13mil de carne"})
    assert r.status_code == 200, r.text
    assert r.json()["created"][0]["pagador_id"] == puid          # quedó a nombre de Pedro


def test_pagador_default_es_quien_carga(client, monkeypatch):
    luid = _registrar(client, "lucas@t.com", "Lucas")
    gid = client.post("/grupos", json={"nombre": "Peña"}).json()["grupo"]["id"]
    _stub_ia(monkeypatch, [{"pagador": None, "description": "Hielo", "amount": 2000, "emoji": "🧊"}])
    r = client.post(f"/grupos/{gid}/gastos", json={"texto": "hielo 2000"})
    assert r.json()["created"][0]["pagador_id"] == luid          # sin nombre → el que carga


def test_saldos_y_quien_paga_a_quien(client, client2, monkeypatch):
    luid = _registrar(client, "lucas@t.com", "Lucas")
    g = client.post("/grupos", json={"nombre": "Peña"}).json()
    gid, code = g["grupo"]["id"], g["invite_code"]
    puid = _registrar(client2, "pedro@t.com", "Pedro")
    client2.post("/grupos/join", json={"code": code})            # ambos presentes
    _stub_ia(monkeypatch, [{"pagador": None, "description": "Asado", "amount": 1000, "emoji": "🥩"}])
    client.post(f"/grupos/{gid}/gastos", json={"texto": "asado 1000"})   # Lucas paga 1000
    d = client.get(f"/grupos/{gid}").json()
    saldos = {s["usuario_id"]: s["saldo"] for s in d["saldos"]}
    assert saldos[luid] == 500.0 and saldos[puid] == -500.0
    assert d["pagos"] == [{"de": puid, "a": luid, "monto": 500.0}]


def test_cerrar_ronda_abre_nueva_y_archiva(client):
    _registrar(client, "lucas@t.com", "Lucas")
    g = client.post("/grupos", json={"nombre": "Peña"}).json()
    gid, ronda1 = g["grupo"]["id"], g["ronda"]["id"]
    r = client.post(f"/grupos/{gid}/cerrar-ronda")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ronda"]["id"] != ronda1 and d["ronda"]["estado"] == "abierta"   # nueva ronda abierta
    hist = client.get(f"/grupos/{gid}/historial").json()
    assert len(hist) == 1 and hist[0]["ronda_id"] == ronda1                   # la vieja, archivada


def test_borrar_gasto_permisos(client, client2, monkeypatch):
    _registrar(client, "lucas@t.com", "Lucas")
    g = client.post("/grupos", json={"nombre": "Peña"}).json()
    gid, code = g["grupo"]["id"], g["invite_code"]
    _registrar(client2, "pedro@t.com", "Pedro")
    client2.post("/grupos/join", json={"code": code})
    _stub_ia(monkeypatch, [{"pagador": None, "description": "Hielo", "amount": 2000, "emoji": "🧊"}])
    gasto_id = client.post(f"/grupos/{gid}/gastos", json={"texto": "hielo 2000"}).json()["created"][0]["id"]
    # Pedro (miembro, no admin, no pagador) NO puede borrarlo
    assert client2.delete(f"/grupos/{gid}/gastos/{gasto_id}").status_code == 403
    # Lucas (admin y pagador) sí
    assert client.delete(f"/grupos/{gid}/gastos/{gasto_id}").status_code == 204
