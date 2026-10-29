"""Genera la ficha de matrícula a partir de LAS 5 TABLAS REALES del formato
oficial (extraídas una sola vez del documento
"1 FICHA MATRICULA INST. EDUCA. TEC. AGRO. BILINGUE - IETABA.docx" hacia
plantillas/ficha_matricula.docx — mismo espíritu que certificados.py con
plantillas/constancia_estudio.docx): se abre la plantilla y se reemplaza
SOLO el texto de las celdas de dato, dejando las etiquetas y el formato
(bordes, fuentes, celdas fusionadas) exactamente como están en el original.

La plantilla se extrajo de un ejemplo real ya diligenciado (una estudiante
real, con su acudiente y su docente). Por eso cada campo que el sistema NO
tiene (resguardo, municipio de nacimiento, etnia, acudiente, docente,
promovido/repitente, discapacidad, etc.) hay que limpiarlo EXPLÍCITAMENTE
— si no, quedaría pegado el dato de la ficha original en la de otro
estudiante. Nunca se inventa un valor para estos campos: se deja en blanco
para que se complete a mano junto con la ficha oficial en papel."""

import datetime as dt
import io
from pathlib import Path

from docx import Document
from docx.table import Table, _Cell

from . import fechas
from .models import DIVISIONES_NOMBRES, GRADOS_NOMBRES

PLANTILLA = Path(__file__).resolve().parent.parent / "plantillas" / "ficha_matricula.docx"

MESES_TEXTO = {
    1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL", 5: "MAYO", 6: "JUNIO",
    7: "JULIO", 8: "AGOSTO", 9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE",
}


def _celdas_unicas(fila) -> list[_Cell]:
    """Una fila de una tabla con celdas fusionadas repite el mismo objeto
    Cell varias veces (una por cada posición de la cuadrícula que cubre);
    esto devuelve cada celda una sola vez, en orden, para poder indexarlas
    por posición visual real."""
    vistas: list[int] = []
    resultado: list[_Cell] = []
    for celda in fila.cells:
        clave = id(celda._tc)
        if clave in vistas:
            continue
        vistas.append(clave)
        resultado.append(celda)
    return resultado


def _poner_etiqueta(celda: _Cell, texto: str) -> None:
    """Cambia el texto de una etiqueta conservando su formato (negrita/tamaño)."""
    runs = celda.paragraphs[0].runs
    if not runs:
        celda.paragraphs[0].add_run(texto)
        return
    runs[0].text = texto
    for r in runs[1:]:
        r.text = ""


def _ajustar_pagina(doc) -> None:
    """Márgenes angostos para que las 5 tablas (7.5 in de ancho) quepan en la
    hoja y salgan en una sola página al imprimir o convertir a PDF."""
    from docx.shared import Inches, Pt

    for sec in doc.sections:
        sec.left_margin = sec.right_margin = Inches(0.4)
        sec.top_margin = sec.bottom_margin = Inches(0.35)
    for p in doc.paragraphs:  # los renglones vacíos entre tablas, casi sin altura
        p.paragraph_format.space_before = p.paragraph_format.space_after = Pt(0)
        for r in p.runs:
            r.font.size = Pt(2)
        p.paragraph_format.line_spacing = Pt(3)


def _filas(tabla: Table) -> list[list[_Cell]]:
    return [_celdas_unicas(f) for f in tabla.rows]


# Campo del formulario en pantalla -> (tabla, fila, celda única) de la plantilla.
# "numero_documento" se maneja aparte (comparte celda con "TIPO ... DOC.").
MAPA_CAMPOS = {
    "sgp": (0, 0, 5), "resguardo": (0, 1, 3), "procedencia": (0, 1, 5), "nombres": (0, 3, 1),
    "primer_apellido": (0, 4, 1), "segundo_apellido": (0, 4, 3), "municipio_nacimiento": (0, 5, 1),
    "dia_nac": (0, 6, 3), "mes_nac": (0, 6, 4), "anio_nac": (0, 6, 5), "municipio_expedicion": (0, 7, 3),
    "sexo_m": (0, 8, 2), "sexo_f": (0, 8, 4), "direccion": (0, 8, 6),
    "ingreso_dia": (1, 1, 2), "ingreso_mes": (1, 1, 4), "ingreso_anio": (1, 1, 6),
    "grado_2025": (1, 1, 8), "grado_2026": (1, 1, 10),
    "madre_si": (1, 4, 1), "madre_no": (1, 4, 2), "awapit_si": (1, 4, 4), "awapit_no": (1, 4, 5),
    "etnia_indigena": (1, 4, 6), "etnia_afro": (1, 4, 7), "etnia_mestizo": (1, 4, 8),
    "est_nuevo": (1, 4, 11), "est_antiguo": (1, 4, 13),
    "horas": (2, 1, 2), "minutos": (2, 2, 2), "rios_si": (2, 2, 5), "rios_no": (2, 2, 6),
    "quebradas_si": (2, 4, 1), "quebradas_no": (2, 4, 2),
    "retiro_si": (3, 2, 1), "retiro_no": (3, 2, 2), "motivo_retiro": (3, 2, 4),
    "promovido_si": (3, 4, 1), "promovido_no": (3, 4, 2), "repitente_si": (3, 4, 4), "repitente_no": (3, 4, 5),
    "educ_esp_si": (3, 6, 1), "educ_esp_no": (3, 6, 2), "desplaz_si": (3, 6, 4), "desplaz_no": (3, 6, 5),
    "discap_no": (3, 8, 1), "discap_si": (3, 8, 2), "disc_ceguera": (3, 8, 4), "disc_sordera": (3, 8, 6),
    "disc_fisica": (3, 8, 8), "disc_down": (3, 9, 1), "disc_cognitiva": (3, 9, 3),
    "disc_multiple": (3, 9, 5), "disc_otras": (3, 9, 7),
    "parentesco": (4, 1, 1), "acudiente": (4, 1, 3), "firma_estudiante": (4, 3, 1),
    "firma_acudiente": (4, 2, 3), "documento_acudiente": (4, 3, 4), "docente": (4, 4, 1),
    "dilig_dia": (4, 5, 2), "dilig_mes": (4, 5, 4), "dilig_anio": (4, 5, 6),
}


def generar_ficha_matricula(
    *,
    documento: str,
    tipo_documento: str | None,
    lugar_expedicion_documento: str | None,
    primer_nombre: str,
    segundo_nombre: str | None,
    primer_apellido: str,
    segundo_apellido: str | None,
    fecha_nacimiento: dt.date | None,
    genero: str | None,
    municipio_nacimiento: str | None = None,
    resguardo: str | None = None,
    grado: int,
    curso: int | None,
    fecha_diligenciamiento: dt.date | None = None,
    campos: dict[str, str] | None = None,
    docente: str | None = None,
    anio_matricula: int | None = None,
    nuevo: bool = False,
) -> bytes:
    doc = Document(PLANTILLA)
    _ajustar_pagina(doc)
    t0, t1, t2, t3, t4 = doc.tables[:5]
    f0, f1, f2, f3, f4 = _filas(t0), _filas(t1), _filas(t2), _filas(t3), _filas(t4)

    nombres = " ".join(n for n in (primer_nombre, segundo_nombre) if n)
    fecha_dilig = fecha_diligenciamiento or dt.date.today()

    # --- Tabla 0: identidad --------------------------------------------------
    f0[0][1].text = "X"       # Municipio Barbacoas (todas nuestras sedes quedan ahí)
    f0[0][3].text = ""        # Tumaco
    f0[0][5].text = ""        # Estudiante SGP: no se rastrea, a marcar a mano

    f0[1][3].text = resguardo or ""
    f0[1][5].text = ""        # C.E. de donde proviene: no se rastrea

    f0[3][1].text = nombres
    f0[4][1].text = primer_apellido or ""
    f0[4][3].text = segundo_apellido or ""

    f0[5][1].text = municipio_nacimiento or ""
    if fecha_nacimiento:
        f0[6][3].text = str(fecha_nacimiento.day)
        f0[6][4].text = MESES_TEXTO.get(fecha_nacimiento.month, "")
        f0[6][5].text = str(fecha_nacimiento.year)
    else:
        f0[6][3].text = ""
        f0[6][4].text = ""
        f0[6][5].text = ""

    tipo_texto = f"TIPO {tipo_documento or '____'}"
    f0[7][1].text = f"{tipo_texto}          {documento}\nDOC."
    f0[7][3].text = lugar_expedicion_documento or ""

    if genero == "M":
        f0[8][2].text, f0[8][4].text = "X", ""
    elif genero == "F":
        f0[8][2].text, f0[8][4].text = "", "X"
    else:
        f0[8][2].text, f0[8][4].text = "", ""
    f0[8][6].text = ""  # dirección/comunidad: no se rastrea

    # --- Tabla 1: condición actual --------------------------------------------
    # Fecha de ingreso a la institución: no se rastrea (no es lo mismo que la
    # fecha en que se genera esta ficha).
    f1[1][2].text, f1[1][4].text, f1[1][6].text = "", "", ""
    # Renovación (antiguos), ficha del año siguiente: "GRADO AÑO <actual>" = el
    # grado que tiene hoy en el sistema (número; Preescolar = 0, sin
    # secciones) y "GRADO AÑO <siguiente>" queda en blanco (a qué grado pasa
    # es otra decisión). Estudiante nuevo de este año: la ficha es de ESTE
    # año, su grado va en "GRADO AÑO <actual>" y el del año anterior (otro
    # colegio) en blanco.
    anio = anio_matricula or fechas.anio_lectivo_actual() + 1
    _poner_etiqueta(f1[1][7], f"GRADO AÑO {anio - 1}")
    _poner_etiqueta(f1[1][9], f"GRADO AÑO {anio}")
    f1[1][8].text = "" if nuevo else str(grado)
    f1[1][10].text = str(grado) if nuevo else ""
    # Fila 4 = los valores reales (alumna madre / habla awapit / etnia /
    # situación de antigüedad): ninguno se rastrea, se limpian los que la
    # plantilla trae marcados con "X".
    for idx in (1, 2, 4, 5, 6, 7, 8, 11, 13):
        if idx < len(f1[4]):
            f1[4][idx].text = ""
    # Todo estudiante que ya está en el sistema es ANTIGUO para el año
    # siguiente; el recién matriculado este año es NUEVO.
    if len(f1[4]) > 13:
        f1[4][11 if nuevo else 13].text = "X"

    # --- Tabla 2: condiciones de traslado --------------------------------------
    # Ya viene en blanco en la plantilla (nadie marcó nada para el ejemplo
    # original) — no se toca, pero se confirma explícitamente por claridad.

    # --- Tabla 3: situación académica/social ------------------------------------
    for idx in (1, 2):  # SE RETIRÓ EN EL AÑO ANTERIOR: no se rastrea
        if idx < len(f3[2]):
            f3[2][idx].text = ""
    for idx in (1, 2, 4, 5):  # PROMOVIDO / REPITENTE: no se decide aquí
        if idx < len(f3[4]):
            f3[4][idx].text = ""
    if len(f3[6]) > 2:
        f3[6][2].text = ""  # "Necesita educación especial": limpiar marca de ejemplo
    if len(f3[8]) > 1:
        f3[8][1].text = ""  # "Tiene discapacidad": limpiar marca de ejemplo

    # --- Tabla 4: anotaciones principales (acudiente/docente/firma) ------------
    f4[1][1].text = ""  # Parentesco del acudiente: no se rastrea
    f4[1][3].text = ""  # Nombres y apellidos del acudiente: no se rastrea
    if len(f4[3]) > 4:
        f4[3][4].text = ""  # No. Documento del acudiente
    # Renglón de las firmas: en la plantilla quedaba tan bajo que la firma del
    # acudiente no cabía.
    from docx.enum.table import WD_ROW_HEIGHT_RULE
    from docx.shared import Inches
    t4.rows[2].height, t4.rows[2].height_rule = Inches(0.6), WD_ROW_HEIGHT_RULE.AT_LEAST
    f4[4][1].text = docente or ""  # quien tiene la sesión abierta
    f4[5][2].text = str(fecha_dilig.day)
    f4[5][4].text = MESES_TEXTO.get(fecha_dilig.month, "")
    f4[5][6].text = str(fecha_dilig.year)

    # Lo que la persona escribió/ajustó en el formulario en pantalla manda
    # sobre los valores por defecto de arriba.
    tablas = [f0, f1, f2, f3, f4]
    for nombre, valor in (campos or {}).items():
        if nombre == "numero_documento":
            f0[7][1].text = f"TIPO {tipo_documento or '____'}          {valor}\nDOC."
            continue
        pos = MAPA_CAMPOS.get(nombre)
        if pos is None:
            continue
        t, fila, celda = pos
        if fila < len(tablas[t]) and celda < len(tablas[t][fila]):
            tablas[t][fila][celda].text = str(valor)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
