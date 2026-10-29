"""Genera la hoja del LIBRO DE REGISTRO DE MATRÍCULAS sobre el Word oficial
del colegio (plantillas/libro_matricula.docx, sacada del original con
crear_plantilla_libro.py: una sola hoja, sin datos). Solo se reemplazan los
marcadores «campo»; membrete, pie de página y textos fijos quedan intactos."""

import io
import re
from pathlib import Path

from docx import Document

PLANTILLA = Path(__file__).resolve().parent.parent / "plantillas" / "libro_matricula.docx"

# Casillas de marca: en la plantilla van como "SI_«campo»_"; vacías quedan
# "SI___" igual que en el libro original.
MARCAS = {
    "desplaz_si", "desplaz_no", "huerfano_si", "huerfano_no", "albergue_si", "albergue_no",
    "disc_cognitiva", "disc_sordera", "disc_fisica", "disc_ceguera", "est_antiguo", "est_nuevo",
}
VACIO_TEXTO = "____________________"
_MARCADOR = re.compile(r"«(\w+)»")


def _valor(nombre: str, campos: dict[str, str]) -> str:
    v = str(campos.get(nombre) or "").strip()
    if nombre in MARCAS:
        return "X" if v else "_"
    return v or VACIO_TEXTO


def generar_libro_matricula(campos: dict[str, str]) -> bytes:
    doc = Document(PLANTILLA)
    for p in doc.paragraphs:
        for r in p.runs:
            if "«" in r.text:
                r.text = _MARCADOR.sub(lambda m: _valor(m.group(1), campos), r.text)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
