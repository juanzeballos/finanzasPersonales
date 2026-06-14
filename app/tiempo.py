"""Fecha 'de hoy' en la zona horaria local de la app (Argentina por defecto).

El contenedor corre en UTC. Sin esto, los gastos cargados de noche en Argentina
(p.ej. 22:00 ART = 01:00 UTC del día siguiente) quedaban con la fecha de "mañana"
en UTC y NO aparecían en la pantalla Registrar (que muestra los de "hoy"), aunque
sí se veían en "El mes". Calculamos la fecha en la zona local para que coincida.

Requiere el paquete `tzdata` (zoneinfo no trae la base de zonas en imágenes slim).
"""
import os
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

TZ_LOCAL = ZoneInfo(os.getenv("APP_TZ", "America/Argentina/Buenos_Aires"))


def hoy_local(ahora: datetime | None = None) -> date:
    """Fecha actual en la zona local. `ahora` (UTC-aware) es inyectable para tests."""
    ahora = ahora or datetime.now(timezone.utc)
    return ahora.astimezone(TZ_LOCAL).date()
