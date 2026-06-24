"""Cálculo de saldos de una ronda de grupo + simplificación de deudas (quién le paga a quién).

Funciones puras (sin DB), fáciles de testear. El router arma `presentes` y `gastos`
desde la ronda abierta y llama a estas.
"""


def calcular_saldos(presentes: list[int], gastos: list[tuple[int, float]]) -> dict[int, dict]:
    """Saldos de la ronda.

    - `presentes`: ids de usuario entre los que se divide el costo (partes iguales).
    - `gastos`: lista de (pagador_id, monto).

    Devuelve {usuario_id: {"pagado": float, "le_toca": float, "saldo": pagado - le_toca}}.
    Incluye a un pagador aunque NO esté presente (le_toca = 0 → saldo positivo, le deben todo).
    saldo > 0 = le deben · saldo < 0 = debe.
    """
    n = len(presentes)
    total = sum(monto for _, monto in gastos)
    le_toca_cu = total / n if n else 0.0

    uids = set(presentes) | {pagador for pagador, _ in gastos}
    pagado = {u: 0.0 for u in uids}
    for pagador, monto in gastos:
        pagado[pagador] += monto

    saldos: dict[int, dict] = {}
    for u in uids:
        toca = le_toca_cu if u in presentes else 0.0
        saldos[u] = {"pagado": pagado[u], "le_toca": toca, "saldo": pagado[u] - toca}
    return saldos


def simplificar_deudas(saldos: dict[int, dict], eps: float = 0.01) -> list[dict]:
    """Devuelve un set mínimo de pagos [{de, a, monto}] que salda las deudas.

    Greedy: empareja el que más debe con el que más le deben, transfiere el mínimo de ambos,
    y avanza. `eps` ignora restos de centavos por redondeo de floats.
    """
    deudores = [[u, -d["saldo"]] for u, d in saldos.items() if d["saldo"] < -eps]   # cuánto deben (positivo)
    acreedores = [[u, d["saldo"]] for u, d in saldos.items() if d["saldo"] > eps]     # cuánto les deben
    deudores.sort(key=lambda x: x[1], reverse=True)
    acreedores.sort(key=lambda x: x[1], reverse=True)

    pagos: list[dict] = []
    i = j = 0
    while i < len(deudores) and j < len(acreedores):
        deudor, acreedor = deudores[i], acreedores[j]
        monto = min(deudor[1], acreedor[1])
        pagos.append({"de": deudor[0], "a": acreedor[0], "monto": round(monto, 2)})
        deudor[1] -= monto
        acreedor[1] -= monto
        if deudor[1] <= eps:
            i += 1
        if acreedor[1] <= eps:
            j += 1
    return pagos
