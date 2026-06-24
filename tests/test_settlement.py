from app.settlement import calcular_saldos, simplificar_deudas


def test_split_parejo_dos_personas():
    # 1 pagó 100, ambos presentes -> le toca 50 a cada uno
    saldos = calcular_saldos([1, 2], [(1, 100.0)])
    assert saldos[1]["le_toca"] == 50.0
    assert saldos[1]["saldo"] == 50.0      # pagó 100, le tocaba 50 -> le deben 50
    assert saldos[2]["saldo"] == -50.0     # no pagó, le tocaba 50 -> debe 50


def test_pagador_no_presente():
    # user 3 pagó pero NO comparte (no está entre los presentes)
    saldos = calcular_saldos([1, 2], [(3, 100.0)])
    assert saldos[3]["le_toca"] == 0.0
    assert saldos[3]["saldo"] == 100.0
    assert saldos[1]["saldo"] == -50.0
    assert saldos[2]["saldo"] == -50.0


def test_simplificar_deudas_basico():
    saldos = calcular_saldos([1, 2], [(1, 100.0)])
    pagos = simplificar_deudas(saldos)
    assert pagos == [{"de": 2, "a": 1, "monto": 50.0}]


def test_simplificar_varios_deudores():
    # 3 presentes, total 300 (le toca 100 c/u), 1 pagó todo
    saldos = calcular_saldos([1, 2, 3], [(1, 300.0)])
    pagos = simplificar_deudas(saldos)
    triples = [(p["de"], p["a"], p["monto"]) for p in pagos]
    assert (2, 1, 100.0) in triples
    assert (3, 1, 100.0) in triples
    assert sum(p["monto"] for p in pagos) == 200.0


def test_sin_gastos():
    saldos = calcular_saldos([1, 2], [])
    assert all(s["saldo"] == 0 for s in saldos.values())
    assert simplificar_deudas(saldos) == []
