"""Traduce entre las casillas de la ficha de matrícula en pantalla (texto, con
"X" en los Si/No) y los datos guardados del estudiante (campos reales,
True/False/None). Así lo que se escribe en la ficha alimenta al programa y
vuelve a aparecer el próximo año."""

import datetime as dt
import json

from . import models

MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO",
         "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]

DISCAPACIDAD_CAMPOS = {
    "disc_ceguera": "Ceguera (visual)", "disc_sordera": "Sordera (auditiva)", "disc_fisica": "Dificultad para moverse (física)",
    "disc_down": "Síndrome Down", "disc_cognitiva": "Cognitiva", "disc_multiple": "Múltiple", "disc_otras": "Otras",
}
TEXTOS = {  # campo de la ficha -> columna
    "municipio_nacimiento": "municipio_nacimiento", "resguardo": "resguardo", "procedencia": "procedencia",
    "direccion": "direccion", "horas": "traslado_horas", "minutos": "traslado_minutos",
    "acudiente": "acudiente_nombre", "parentesco": "acudiente_parentesco", "documento_acudiente": "acudiente_documento",
}
SI_NO = {  # columna -> (casilla Si, casilla No)
    "habla_awapit": ("awapit_si", "awapit_no"), "madre_cabeza": ("madre_si", "madre_no"),
    "educacion_especial": ("educ_esp_si", "educ_esp_no"), "desplazamiento": ("desplaz_si", "desplaz_no"),
    "cruza_rios": ("rios_si", "rios_no"), "cruza_quebradas": ("quebradas_si", "quebradas_no"),
}
ETNIAS = {"etnia_indigena": "INDIGENA", "etnia_afro": "AFRO", "etnia_mestizo": "MESTIZO"}


def _marcada(v) -> bool:
    return bool(str(v or "").strip())


def _limpio(v) -> str | None:
    v = str(v or "").strip()
    return v or None


def _fecha(dia, mes, anio) -> dt.date | None:
    try:
        m = str(mes).strip().upper()
        mes_n = MESES.index(m) + 1 if m in MESES else int(m)
        return dt.date(int(str(anio).strip()), mes_n, int(str(dia).strip()))
    except (ValueError, TypeError):
        return None


def campos_a_datos(campos: dict[str, str], fila: models.DatosFichaEstudiante) -> None:
    """Copia a `fila` lo que trae el formulario. Un campo que llega vacío
    borra el dato guardado (la ficha en pantalla es la fuente de verdad)."""
    for campo, col in TEXTOS.items():
        setattr(fila, col, _limpio(campos.get(campo)))
    for col, (si, no) in SI_NO.items():
        setattr(fila, col, True if _marcada(campos.get(si)) else False if _marcada(campos.get(no)) else None)
    fila.etnia = next((v for k, v in ETNIAS.items() if _marcada(campos.get(k))), None)
    fila.estudiante_sgp = True if _marcada(campos.get("sgp")) else None
    fila.fecha_ingreso = _fecha(campos.get("ingreso_dia"), campos.get("ingreso_mes"), campos.get("ingreso_anio"))
    detalle = {k: str(campos.get(k) or "").strip() for k in [*DISCAPACIDAD_CAMPOS, "discap_si", "discap_no"] if _marcada(campos.get(k))}
    tipos = [f"{DISCAPACIDAD_CAMPOS[k]}{': ' + detalle[k] if k == 'disc_otras' and detalle[k].upper() != 'X' else ''}"
             for k in DISCAPACIDAD_CAMPOS if k in detalle]
    fila.discapacidad_detalle = json.dumps(detalle, ensure_ascii=False) if detalle else None
    fila.discapacidad = "; ".join(tipos) if tipos or "discap_si" in detalle else ("NINGUNA" if "discap_no" in detalle else None)


def datos_a_campos(fila: models.DatosFichaEstudiante | None, estudiante: models.Estudiante) -> dict[str, str]:
    """Casillas de la ficha que se pueden llenar con lo ya guardado."""
    campos: dict[str, str] = {}
    if estudiante.lugar_expedicion_documento:
        campos["municipio_expedicion"] = estudiante.lugar_expedicion_documento
    if fila is None:
        return campos
    for campo, col in TEXTOS.items():
        if getattr(fila, col):
            campos[campo] = getattr(fila, col)
    for col, (si, no) in SI_NO.items():
        v = getattr(fila, col)
        if v is True:
            campos[si] = "X"
        elif v is False:
            campos[no] = "X"
    for k, v in ETNIAS.items():
        if fila.etnia == v:
            campos[k] = "X"
    if fila.estudiante_sgp:
        campos["sgp"] = "X"
    if fila.fecha_ingreso:
        campos["ingreso_dia"] = str(fila.fecha_ingreso.day)
        campos["ingreso_mes"] = MESES[fila.fecha_ingreso.month - 1]
        campos["ingreso_anio"] = str(fila.fecha_ingreso.year)
    if fila.discapacidad_detalle:
        campos.update(json.loads(fila.discapacidad_detalle))
    return campos
