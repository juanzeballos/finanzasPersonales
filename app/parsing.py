"""Funciones puras de parseo de texto: normalización de conceptos y extracción de montos.

Hacer esto en Python (no en la IA) es más rápido y determinístico — además arregla el bug
de "lucas" del modelo, porque el cálculo del monto ya no depende de él.
"""

import re
import unicodedata

# Unidades de slang argentino -> multiplicador
_UNIDADES = {
    "millon": 1_000_000, "millones": 1_000_000, "palo": 1_000_000, "palos": 1_000_000,
    "luca": 1000, "lucas": 1000, "k": 1000, "mil": 1000,
}

# número (miles tipo 8.500, o decimal 8,5, o entero) + unidad opcional
_PATRON_MONTO = re.compile(
    r"(\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)\s*"
    r"(millones|millon|palos|palo|lucas|luca|mil|k)?\b",
    re.IGNORECASE,
)


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos, sin espacios de más. Para usar como clave de concepto."""
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def extraer_montos(texto: str) -> list[float]:
    """Devuelve los montos detectados en el texto, interpretando slang argentino.

    Ejemplos: "8.500" -> 8500, "45 lucas" -> 45000, "2 millones" -> 2000000,
    "media luca" -> 500, "8 mil" -> 8000.
    """
    t = re.sub(r"media\s+luca", "500", texto, flags=re.IGNORECASE)
    montos = []
    for m in _PATRON_MONTO.finditer(t):
        num_str, unidad = m.group(1), m.group(2)
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", num_str):
            valor = float(num_str.replace(".", ""))   # 8.500 -> 8500 (separador de miles)
        else:
            valor = float(num_str.replace(",", "."))  # 8,5 -> 8.5 (decimal)
        if unidad:
            valor *= _UNIDADES[unidad.lower()]
        montos.append(valor)
    return montos


# Monedas explícitas en el texto. El orden no importa (no se solapan).
# Símbolos ($,€) y abreviaturas no llevan \b porque $ y € no son caracteres de palabra.
_DIVISAS = [
    ("USD", re.compile(r"(?<![a-z])(usd|u\$s|us\$|d[oó]lares?)(?![a-z])", re.IGNORECASE)),
    ("EUR", re.compile(r"(?<![a-z])(eur|euros?)(?![a-z])|€", re.IGNORECASE)),
    ("BRL", re.compile(r"(?<![a-z])(brl|reales?)(?![a-z])|r\$", re.IGNORECASE)),
]


def detectar_divisa(texto: str) -> str | None:
    """Devuelve la moneda explícita mencionada en el texto, o None si no hay ninguna."""
    for codigo, patron in _DIVISAS:
        if patron.search(texto):
            return codigo
    return None
