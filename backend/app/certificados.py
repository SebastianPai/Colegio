"""Genera constancias de estudio a partir de la plantilla oficial del colegio
(plantillas/constancia_estudio.docx), sin tocar su formato: solo se
reemplaza el texto de los "runs" (fragmentos de texto con estilo) que
contienen los datos variables, dejando el resto del documento intacto
(membrete, logos, firma del rector).
"""

import datetime as dt
import io
from pathlib import Path

from docx import Document

from .models import GRADOS_NOMBRES

PLANTILLA = Path(__file__).resolve().parent.parent / "plantillas" / "constancia_estudio.docx"


def convertir_a_pdf(ruta_docx: Path, ruta_pdf: Path) -> bool:
    """Convierte usando Word (instalado en este PC). Si Word no está
    disponible, devuelve False y el sistema sigue funcionando solo con
    Word (.docx) — la conversión a PDF es un extra, no un requisito."""
    try:
        from docx2pdf import convert

        convert(str(ruta_docx), str(ruta_pdf))
        return ruta_pdf.exists()
    except Exception:
        return False

NIVELES_POR_GRADO = {
    0: "preescolar",
    1: "básica primaria",
    2: "básica primaria",
    3: "básica primaria",
    4: "básica primaria",
    5: "básica primaria",
    6: "básica secundaria",
    7: "básica secundaria",
    8: "básica secundaria",
    9: "básica secundaria",
    10: "media",
    11: "media",
}

DIAS_TEXTO = {
    1: "uno", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis", 7: "siete",
    8: "ocho", 9: "nueve", 10: "diez", 11: "once", 12: "doce", 13: "trece",
    14: "catorce", 15: "quince", 16: "dieciséis", 17: "diecisiete", 18: "dieciocho",
    19: "diecinueve", 20: "veinte", 21: "veintiuno", 22: "veintidós", 23: "veintitrés",
    24: "veinticuatro", 25: "veinticinco", 26: "veintiséis", 27: "veintisiete",
    28: "veintiocho", 29: "veintinueve", 30: "treinta", 31: "treinta y uno",
}

MESES_TEXTO = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre",
    12: "diciembre",
}

TIPOS_DOCUMENTO_TEXTO = {
    "C.C.": "Cédula de ciudadanía",
    "T.I.": "Tarjeta de identidad",
    "R.C.": "Registro civil de nacimiento",
}

PROPOSITOS = [
    "Trámite de libreta militar",
    "Trámite ante el ICBF",
    "Trámite bancario",
    "Solicitud de subsidio o beneficio del gobierno",
    "Constancia de estudio general",
]


def _texto_tipo_documento(tipo_documento: str | None) -> str:
    if not tipo_documento:
        return "Cédula de ciudadanía"
    return TIPOS_DOCUMENTO_TEXTO.get(tipo_documento, tipo_documento)


def _fusionar_runs(paragraph, inicio: int, fin: int, texto_nuevo: str) -> None:
    """Pone `texto_nuevo` en el run `inicio` (conservando su formato) y
    vacía los runs desde `inicio+1` hasta `fin` (inclusive)."""
    runs = paragraph.runs
    runs[inicio].text = texto_nuevo
    for i in range(inicio + 1, fin + 1):
        runs[i].text = ""


def generar_constancia(
    *,
    nombre_completo: str,
    tipo_documento: str | None,
    documento: str,
    lugar_expedicion: str,
    grado: int,
    jornada: str,
    anio_escolar: int,
    fecha_expedicion: dt.date,
    proposito: str,
) -> bytes:
    doc = Document(PLANTILLA)
    parrafos = doc.paragraphs

    nombre_grado = GRADOS_NOMBRES.get(grado, str(grado)).lower()
    nivel = NIVELES_POR_GRADO.get(grado, "básica")

    # Párrafo del cuerpo: "Que el estudiante: NOMBRE, identificado(a) con
    # TIPO_DOC No. DOCUMENTO de LUGAR se encuentra matriculado... en el
    # Grado PALABRA (NUMERO) de la Educación NIVEL, jornada JORNADA,
    # Calendario A, año escolar AÑO."
    p_cuerpo = parrafos[6]
    _fusionar_runs(p_cuerpo, 1, 1, nombre_completo)
    _fusionar_runs(p_cuerpo, 3, 3, _texto_tipo_documento(tipo_documento))
    _fusionar_runs(p_cuerpo, 7, 7, documento)
    _fusionar_runs(p_cuerpo, 9, 11, f"de {lugar_expedicion}")
    _fusionar_runs(p_cuerpo, 26, 26, nombre_grado)
    _fusionar_runs(p_cuerpo, 28, 28, str(grado))
    _fusionar_runs(p_cuerpo, 30, 30, nivel)
    _fusionar_runs(p_cuerpo, 34, 34, f" {jornada}")
    _fusionar_runs(p_cuerpo, 35, 36, f", Calendario A, año escolar {anio_escolar}")

    # Párrafo de la fecha: "...a los DIA (NUMERO) días del mes de MES del
    # año AÑO."
    p_fecha = parrafos[8]
    _fusionar_runs(p_fecha, 4, 4, DIAS_TEXTO.get(fecha_expedicion.day, str(fecha_expedicion.day)))
    _fusionar_runs(p_fecha, 6, 8, f"({fecha_expedicion.day}) día")
    _fusionar_runs(p_fecha, 11, 11, MESES_TEXTO.get(fecha_expedicion.month, ""))
    _fusionar_runs(p_fecha, 12, 13, f" del año {fecha_expedicion.year}")

    # Párrafo "Válido para ..."
    p_valido = parrafos[11]
    _fusionar_runs(p_valido, 0, 3, f"Válido para {proposito}.")

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
