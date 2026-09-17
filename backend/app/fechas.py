"""Fechas y horas oficiales de la institución (Colombia).

Única fuente de "hoy" y "ahora" en el backend. Colombia está en UTC−5 todo
el año (sin horario de verano), pero se usa la zona IANA para no depender de
la configuración del PC servidor: si mañana la app corre en un VPS en UTC,
"hoy" sigue siendo el día de Colombia.

Convenciones del proyecto:
  · Una fecha de negocio (asistencia, ausencia, expedición…) es un dt.date
    del calendario colombiano: se obtiene con hoy_colombia(), nunca
    recortando un instante UTC (a las 7:00 p. m. de Colombia, en UTC ya es
    el día siguiente).
  · Un instante (creado_en, registrado_en…) se guarda en UTC sin zona, como
    ya hacen las tablas existentes: ahora_utc(). Para mostrarlo en hora
    local: a_colombia().
"""

import datetime as dt

try:
    from zoneinfo import ZoneInfo

    ZONA_COLOMBIA: dt.tzinfo = ZoneInfo("America/Bogota")
except Exception:  # sin base IANA (Windows sin el paquete tzdata)
    ZONA_COLOMBIA = dt.timezone(dt.timedelta(hours=-5), "COT")


def a_colombia(instante: dt.datetime) -> dt.datetime:
    """Convierte un instante a hora de Colombia. Sin zona se asume UTC (así
    se guardan los instantes en la base)."""
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=dt.timezone.utc)
    return instante.astimezone(ZONA_COLOMBIA)


def ahora_colombia() -> dt.datetime:
    """Fecha y hora actuales en Colombia (con zona)."""
    return dt.datetime.now(ZONA_COLOMBIA)


def hoy_colombia(*, instante: dt.datetime | None = None) -> dt.date:
    """La fecha de calendario en Colombia: ahora, o en `instante` si se da.
    (Parámetro solo por nombre: SQLAlchemy la usa como default de columna y
    no debe confundirla con una función que recibe el contexto.)"""
    return (a_colombia(instante) if instante is not None else ahora_colombia()).date()


def anio_lectivo_actual() -> int:
    return hoy_colombia().year


def ahora_utc() -> dt.datetime:
    """Instante actual en UTC sin zona: el mismo formato que
    dt.datetime.utcnow() (obsoleto desde Python 3.12) que usan las columnas
    existentes."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
