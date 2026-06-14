from datetime import date, datetime, timezone

from app.tiempo import hoy_local


def test_noche_argentina_sigue_siendo_el_mismo_dia():
    # 01:00 UTC del 14 = 22:00 ART del 13 -> en Argentina todavía es el 13
    assert hoy_local(datetime(2026, 6, 14, 1, 0, tzinfo=timezone.utc)) == date(2026, 6, 13)


def test_mediodia_utc_y_art_coinciden():
    # 15:00 UTC = 12:00 ART, mismo día
    assert hoy_local(datetime(2026, 6, 14, 15, 0, tzinfo=timezone.utc)) == date(2026, 6, 14)


def test_sin_argumento_devuelve_un_date():
    assert isinstance(hoy_local(), date)
