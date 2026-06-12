"""Cliente de IA: clasifica gastos y genera el consejo.

Soporta varios proveedores, elegidos con la variable de entorno IA_PROVIDER:
  - "groq"    : nube, gratis, rapidísimo (modelos open tipo Llama). Necesita GROQ_API_KEY.
  - "deepseek": nube, pago por uso, barato. Necesita DEEPSEEK_API_KEY.
  - "ollama"  : modelo local (offline, privado, más lento). Por defecto.

deepseek y groq comparten la API compatible-con-OpenAI (/chat/completions).

  - clasificar(texto): texto libre -> {items:[...], missing:[...]} estructurado.
  - generar_informe(resumen): números YA agregados -> consejo en texto.
"""

import json
import os

import httpx

from .schemas import CATEGORIAS, ClasificacionIA

PROVIDER = os.getenv("IA_PROVIDER", "ollama").lower()

# --- Ollama (local) ---
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# --- Proveedores compatibles con OpenAI (url, api_key, modelo) ---
_OPENAI_COMPAT = {
    "deepseek": (
        "https://api.deepseek.com/chat/completions",
        os.getenv("DEEPSEEK_API_KEY", ""),
        os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    ),
    "groq": (
        "https://api.groq.com/openai/v1/chat/completions",
        os.getenv("GROQ_API_KEY", ""),
        os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
    ),
}

_CATS = ", ".join(CATEGORIAS)

PROMPT_CLASIFICAR = """Sos un clasificador de gastos personales para una persona en Argentina.
Te paso un texto con uno o más gastos. Devolvé EXCLUSIVAMENTE un JSON válido con esta forma exacta:
{{"items":[{{"description":"texto corto y claro","amount":123,"category":"...","tipo":"fijo|necesario|prescindible","emoji":"un emoji"}}],"missing":["..."]}}

Reglas:
- "description": un resumen CORTO del gasto (ej: "Luz", "Supermercado", "Nafta"). NO copies el texto entero.
- "amount": entero en pesos, sin símbolos ni separadores. Interpretá slang argentino:
  "luca"/"k" = mil ("5 lucas" y "5k" = 5000, "30 lucas" = 30000, "media luca" = 500),
  "palo" = millón ("2 palos" = 2000000), "$3.500" = 3500.
- "missing": SOLO para gastos que la persona mencionó SIN decir el monto. Si TODOS los gastos
  mencionados tienen monto, "missing" DEBE ser []. NUNCA inventes datos faltantes ni preguntes
  por gastos que la persona no nombró.
- "category": la más adecuada de esta lista: {cats}. Elegí bien (ej: luz/gas/agua = Servicios;
  farmacia/médico = Salud; nafta = Nafta). Podés crear otra solo si ninguna encaja.
- "tipo":
  - "fijo": recurrente y estable mes a mes (alquiler, expensas, servicios, impuestos, cuotas, suscripciones, gimnasio mensual).
  - "necesario": indispensable pero variable (supermercado, comida, transporte, nafta, salud).
  - "prescindible": se podría evitar (salidas, delivery por gusto, caprichos, entretenimiento, ropa no esencial).
- "emoji": un único emoji que represente el gasto.
- Un mismo mensaje puede tener VARIOS gastos: separalos en items distintos, uno por gasto.
- IMPORTANTE: clasificá ÚNICAMENTE el texto de abajo. No inventes gastos.

Texto del gasto: "{texto}"
"""

PROMPT_INFORME = """Sos un asesor financiero personal, directo y concreto. Te paso el resumen
del mes de una persona (en pesos argentinos), con los porcentajes YA calculados.

{resumen}

Escribí un consejo breve (en español rioplatense, máximo 7 líneas) sobre dónde recortar.
Prioritá lo "prescindible" y los "fijos" más altos. Sé específico con las categorías y montos
que ves. NO recalcules porcentajes ni inventes gastos que no estén en el resumen.
"""


# ----------------- Backends -----------------

def _ollama(prompt: str, json_mode: bool) -> str:
    cuerpo = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    if json_mode:
        cuerpo["format"] = "json"
    # Timeout amplio: la 1ra llamada (o tras inactividad) recarga el modelo en RAM (~150s en CPU).
    resp = httpx.post(OLLAMA_URL, json=cuerpo, timeout=600)
    resp.raise_for_status()
    return resp.json()["response"]


def _openai_compat(prompt: str, json_mode: bool) -> str:
    """Llama a un proveedor compatible con OpenAI (deepseek/groq)."""
    url, api_key, modelo = _OPENAI_COMPAT[PROVIDER]
    if not api_key:
        raise RuntimeError(f"Falta la API key para el proveedor '{PROVIDER}'.")
    cuerpo = {
        "model": modelo,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    if json_mode:
        cuerpo["response_format"] = {"type": "json_object"}  # garantiza JSON parseable
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=cuerpo,
        timeout=120,  # la nube responde en segundos; sin recarga de modelo
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _generar(prompt: str, json_mode: bool) -> str:
    """Despacha al proveedor activo."""
    if PROVIDER in _OPENAI_COMPAT:
        return _openai_compat(prompt, json_mode)
    return _ollama(prompt, json_mode)


# ----------------- API pública (no cambia para el resto de la app) -----------------

def clasificar(texto: str) -> ClasificacionIA:
    """Texto libre -> clasificación validada (items + missing)."""
    prompt = PROMPT_CLASIFICAR.format(cats=_CATS, texto=texto)
    raw = _generar(prompt, json_mode=True)
    datos = json.loads(raw)
    return ClasificacionIA(**datos)


def generar_informe(resumen_texto: str) -> str:
    """Resumen (ya con porcentajes) -> consejo en texto."""
    prompt = PROMPT_INFORME.format(resumen=resumen_texto)
    return _generar(prompt, json_mode=False).strip()
