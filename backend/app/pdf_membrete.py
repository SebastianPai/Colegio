"""Membrete oficial, pie de página y paginación para los PDF del sistema.

Sale de plantillas/constancia_estudio.docx (mismo logo, textos y lema) para
que un reporte impreso se vea igual que una constancia oficial. Lo usan
lista_estudiantes_pdf.py y reporte_horas_libres.py.

La paginación no usa el corte automático de fitz.Story: el llamador arma
"bloques" de HTML y aquí se van metiendo en cada hoja mientras quepan, así
el encabezado de una tabla se puede repetir al continuar en la hoja
siguiente.
"""

import datetime as dt
import html
import io
import zipfile
from pathlib import Path

import fitz  # PyMuPDF

from .certificados import MESES_TEXTO, PLANTILLA
from .reporte_horario import LOGOS, MEMBRETE_LINEAS

FUENTES_WINDOWS = Path("C:/Windows/Fonts")
LOGO_MEMBRETE = "logo_membrete.jpeg"
AZUL = "#1f3a5f"

PIE_LEMA = "Por la pervivencia e identidad del Pueblo Awá"
PIE_LINEAS = [
    "Unidad administrativa – Predio el Verde, resguardo el Gran Sábalo – El Diviso - Barbacoas Nariño",
    "E-mail: awa@ietaba.edu.co",
]

CSS_BASE = """
@font-face {{ font-family: magneto; src: url(MAGNETOB.TTF); }}
* {{ font-family: sans-serif; }}
body {{ font-size: 9.5pt; color: #111; }}
.m-tabla {{ width: 100%; border-collapse: collapse; }}
.m-tabla td {{ vertical-align: middle; }}
.m-texto {{ text-align: center; font-weight: bold; font-size: 7.6pt; margin: 0; line-height: 1.25; }}
.m-lema {{ text-align: center; font-family: {lema}; font-weight: bold; font-style: {estilo}; font-size: 10pt; margin: 1px 0 0 0; }}
.pie-linea {{ border-top: 1.2px solid #111; margin: 0; }}
.pie-lema {{ text-align: center; font-family: {lema}; font-style: {estilo}; font-size: 8pt; margin: 2px 0 0 0; }}
.pie-texto {{ text-align: center; font-size: 7pt; margin: 0; color: #333; }}
h1 {{ text-align: center; font-size: 13pt; color: {azul}; margin: 4px 0 0 0; letter-spacing: 0.5px; }}
.subtitulo {{ text-align: center; font-size: 9pt; color: #444; margin: 1px 0 10px 0; }}
.explicacion {{ text-align: justify; font-size: 9.5pt; line-height: 1.4; margin: 0 0 8px 0; }}
table.datos {{ width: 100%; border-collapse: collapse; margin: 0 0 10px 0; }}
table.datos td {{ border: 0.6px solid #9aa7b8; padding: 3px 6px; font-size: 8.8pt; }}
table.datos td.et {{ background-color: #eef2f7; font-weight: bold; color: {azul}; }}
h2 {{ font-size: 10.5pt; color: {azul}; margin: 8px 0 4px 0; border-bottom: 1px solid {azul}; }}
.nota {{ font-size: 8pt; color: #555; margin: 10px 0 0 0; }}
table.firmas {{ width: 100%; margin-top: 46px; }}
table.firmas td {{ text-align: center; font-size: 9pt; }}
"""

FIRMAS_HTML = """
<p class="nota">Documento generado por el sistema institucional de la IETABA.</p>
<table class="firmas"><tr>
  <td width="50%">______________________________<br/><b>Rector(a)</b></td>
  <td width="50%">______________________________<br/><b>Secretaría académica</b></td>
</tr></table>
"""


def fecha_larga(d: dt.date) -> str:
    return f"{d.day} de {MESES_TEXTO[d.month]} de {d.year}"


class Papeleria:
    """Logo, fuente del lema, CSS, membrete y pie ya armados."""

    def __init__(self, css_extra: str = ""):
        self.archivo = fitz.Archive()
        logo_html = ""
        try:
            with zipfile.ZipFile(PLANTILLA) as z:
                self.archivo.add((z.read("word/media/image2.jpeg"), LOGO_MEMBRETE))
            logo_html = f'<img src="{LOGO_MEMBRETE}" width="66"/>'
        except (OSError, KeyError, zipfile.BadZipFile):
            if (LOGOS / "logo2.jpeg").exists():
                self.archivo.add(str(LOGOS))
                logo_html = '<img src="logo2.jpeg" width="66"/>'

        hay_magneto = (FUENTES_WINDOWS / "MAGNETOB.TTF").exists()
        if hay_magneto:
            self.archivo.add(((FUENTES_WINDOWS / "MAGNETOB.TTF").read_bytes(), "MAGNETOB.TTF"))

        self.css = (
            CSS_BASE.format(
                lema="magneto" if hay_magneto else "serif",
                estilo="normal" if hay_magneto else "italic",
                azul=AZUL,
            )
            + css_extra
        )

        textos = [t for t, tipo in MEMBRETE_LINEAS if tipo != "lema"]
        lema = next((t for t, tipo in MEMBRETE_LINEAS if tipo == "lema"), "")
        self.membrete = (
            '<table class="m-tabla"><tr>'
            f'<td width="16%">{logo_html}</td>'
            '<td width="84%">'
            + "".join(f'<p class="m-texto">{html.escape(t)}</p>' for t in textos)
            + f'<p class="m-lema">{html.escape(lema)}</p>'
            + "</td></tr></table>"
        )
        self.pie = (
            '<p class="pie-linea"></p>'
            f'<p class="pie-lema">{html.escape(PIE_LEMA)}</p>'
            + "".join(f'<p class="pie-texto">{html.escape(t)}</p>' for t in PIE_LINEAS)
        )

    def cabe(self, contenido: str, area: fitz.Rect) -> bool:
        sobra, lleno = fitz.Story(html=contenido, user_css=self.css, archive=self.archivo).place(area)
        # Con algunas tablas place() dice que no sobra nada aunque lo colocado
        # se pase del borde de abajo (y eso al dibujar se pierde): también se
        # mira hasta dónde llegó.
        return not sobra and lleno[3] <= area.y1 + 0.5


def medidas(horizontal: bool) -> tuple[fitz.Rect, fitz.Rect, fitz.Rect, fitz.Rect, int]:
    """(hoja, zona del membrete, zona del contenido, zona del pie, margen)."""
    hoja = fitz.paper_rect("letter-l" if horizontal else "letter")
    margen = 42 if not horizontal else 34
    return (
        hoja,
        fitz.Rect(margen, 24, hoja.width - margen, 110),
        fitz.Rect(margen, 116, hoja.width - margen, hoja.height - 72),
        fitz.Rect(margen, hoja.height - 64, hoja.width - margen, hoja.height - 14),
        margen,
    )


def escribir_pdf(papeleria: Papeleria, paginas: list[str], horizontal: bool = False) -> bytes:
    """Dibuja membrete + contenido + pie en cada hoja y numera las páginas."""
    hoja, rect_membrete, area, rect_pie, margen = medidas(horizontal)
    salida = io.BytesIO()
    escritor = fitz.DocumentWriter(salida)
    for contenido in paginas:
        dispositivo = escritor.begin_page(hoja)
        for texto, rect in (
            (papeleria.membrete, rect_membrete),
            (contenido, area),
            (papeleria.pie, rect_pie),
        ):
            story = fitz.Story(html=texto, user_css=papeleria.css, archive=papeleria.archivo)
            story.place(rect)
            story.draw(dispositivo)
        escritor.end_page()
    escritor.close()

    doc = fitz.open("pdf", salida.getvalue())
    for i, pagina in enumerate(doc, start=1):
        pagina.insert_text(
            (hoja.width - margen - 52, hoja.height - 18),
            f"Página {i} de {doc.page_count}",
            fontsize=7,
            color=(0.35, 0.35, 0.35),
        )
    return doc.tobytes(garbage=3, deflate=True)
