"""Utilidades de texto compartidas."""

import unicodedata


def sin_tildes(valor) -> str:
    """Minúsculas y sin marcas diacríticas: 'PEÑA' -> 'pena', 'GUIGÜAY' ->
    'guiguay'. La ñ se conserva como n, que es justo lo que se quiere al buscar.

    Se registra también como función SQL (ver database.py) porque el lower()
    de SQLite solo pliega ASCII: deja la Ñ en mayúscula, así que 'BOLAÑOS' no
    coincidía ni con 'bolaños' escrito exacto. Es el mismo criterio que usa el
    frontend en normalizarTexto() (core.js) para las búsquedas del lado del
    cliente."""
    if valor is None:
        return ""
    descompuesto = unicodedata.normalize("NFD", str(valor))
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).lower()
