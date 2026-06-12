"""Schemas Pydantic = validación y forma de los datos que entran y salen por la API.

Analogía Java: son como DTOs con validación automática (tipo Bean Validation).
'Literal[...]' restringe a valores fijos (como un enum).
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

# Categorías sugeridas (la IA puede crear otra si hace falta). Un único lugar de verdad,
# usado también por el prompt de clasificación.
CATEGORIAS = [
    "Supermercado", "Comida y delivery", "Transporte", "Nafta", "Servicios",
    "Impuestos", "Alquiler", "Salud", "Educación", "Gimnasio",
    "Entretenimiento", "Ropa", "Hogar", "Suscripciones", "Otros",
]

# El orden importa: de "sin control" a "todo el control".
TIPOS = ["fijo", "necesario", "prescindible"]


class GastoTexto(BaseModel):
    """Lo que manda el chat: texto libre (puede tener varios gastos)."""
    texto: str


class ItemIA(BaseModel):
    """Un gasto detectado por la IA dentro del texto."""
    description: str = "Gasto"
    amount: float = 0
    category: str = "Otros"
    tipo: str = "necesario"     # se normaliza en el router a fijo|necesario|prescindible
    emoji: str = "💸"


class ClasificacionIA(BaseModel):
    """Respuesta completa de la IA: gastos detectados + datos que faltan."""
    items: list[ItemIA] = []
    missing: list[str] = []


class TipoUpdate(BaseModel):
    """Body del PATCH para reclasificar el tipo de un gasto."""
    tipo: str


class GastoOut(BaseModel):
    """Lo que la API devuelve al cliente."""
    id: int
    fecha: date
    descripcion: str
    monto: float
    categoria: str
    tipo: str
    emoji: str
    creado_en: datetime

    model_config = {"from_attributes": True}


class AltaResponse(BaseModel):
    """Respuesta del POST /gastos: lo creado + avisos de lo que faltó."""
    created: list[GastoOut] = []
    missing: list[str] = []


class EntradaOut(BaseModel):
    """Una entrada de la bandeja (texto pendiente/clasificado/con error)."""
    id: int
    texto: str
    estado: str
    error: str | None = None
    creado_en: datetime

    model_config = {"from_attributes": True}


class UsuarioCrear(BaseModel):
    """Lo que llega en registro/login (nombre solo se usa en el registro)."""
    email: str
    password: str = Field(min_length=4)
    nombre: str | None = None


class UsuarioOut(BaseModel):
    """Datos públicos del usuario (sin la contraseña)."""
    id: int
    email: str
    nombre: str | None = None

    model_config = {"from_attributes": True}
