"""Listas de asistencia en PDF, varios grupos de una vez (Reportes → Listas de
asistencia).

Mismo formato que la hoja "LISTA GRADO ..." del Excel oficial "1 LISTA DE
ASISTENCIA INST. EDU. IETABA X GRADOS.xlsx": oficio horizontal (8,5 × 13 in,
el "Folio" de Excel), encabezado UNIPA / Gobernación / Secretaría / contrato
con los dos logos, establecimiento, sede, códigos DANE y mes, la tabla de
estudiantes con las 31 casillas de días y, al pie, el renglón para el
nombre y la identificación del docente.

A diferencia del Excel (que se imprime al 75 % y a veces se pasa a otra hoja),
aquí cada grupo va SIEMPRE en una sola hoja ya a la medida: si el grupo es
grande, las filas se achican hasta que quepa. Se imprime al 100 %.

Qué grupos: `parsear_grupos("10, 11, 2, 4-2")` — un número es el grado
completo (cada grupo en su hoja), "4-2" es ese grupo, "6 a 9" un rango de
grados y "todos" todos los grados de la sede.
"""

import re
from pathlib import Path

import fitz  # PyMuPDF
from sqlalchemy.orm import Session

from . import crud, models

RAIZ = Path(__file__).resolve().parent.parent.parent
LOGO_IZQ = RAIZ / "frontend" / "static" / "logos" / "logo1.jpg"  # UNIPA
LOGO_DER = RAIZ / "frontend" / "static" / "logos" / "logo2.jpeg"  # IETABA

INSTITUCION_NOMBRE = "INST. EDU. TECNICA AGROAMBIENTAL BILINGÜE AWÁ - IETABA"
INSTITUCION_CODIGO_DANE = "252079002045"
ENCABEZADO = [
    "UNIDAD INDIGENA DEL PUEBLO AWA",
    "GOBERNACION DE NARIÑO",
    "SECRETARIA DE EDUCACION DEPARTAMENTAL",
    "CONTRATO No. 1987 - 26 DEL 2025",
]
MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO",
         "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]

# Oficio colombiano = Folio de Excel (paperSize 14): 8,5 × 13 in, horizontal.
PAGINA = fitz.Rect(0, 0, 13 * 72, 8.5 * 72)
MARGEN_X, MARGEN_ARRIBA, MARGEN_ABAJO = 20, 22, 22
VERDE = (0, 0.69, 0.31)  # encabezado de la tabla, como el Excel
NEGRO = (0, 0, 0)

# (encabezado, ancho en puntos, alineación) — las columnas de datos que se
# ven en la hoja impresa del Excel; el resto del ancho es para los 31 días.
COLUMNAS = [
    ("No", 22, "c"), ("GRADO", 28, "c"), ("TIPO\nDOC.", 28, "c"), ("NRO DOCUMENTO", 62, "c"),
    ("PRIMER APELLIDO", 72, "i"), ("SEGUNDO APELLIDO", 64, "i"), ("PRIMER NOMBRE", 64, "i"),
    ("SEGUNDO NOMBRE", 64, "i"), ("FECHA\nNACIMIENTO", 54, "c"), ("GEN.", 24, "c"),
]
FILA_MAX, FILA_MIN = 14.5, 7.0


class GrupoInvalido(ValueError):
    pass


def parsear_grupos(texto: str) -> list[tuple[int, int | None, bool]]:
    """'10, 11, 2, 4-2' -> [(10, None, True), (11, None, True), (2, None, True), (4, 2, False)].
    (grado, curso, todo_el_grado). '6 a 9' = grados 6, 7, 8 y 9. 'todos' = 0..11."""
    pedidos: list[tuple[int, int | None, bool]] = []
    for trozo in re.split(r"[,;\n]+", (texto or "").strip().lower()):
        t = trozo.strip()
        if not t:
            continue
        if t in ("todos", "todo", "all"):
            pedidos += [(g, None, True) for g in range(0, 12)]
            continue
        m = re.fullmatch(r"(\d{1,2})\s*(?:a|al|hasta)\s*(\d{1,2})", t)
        if m:
            desde, hasta = int(m.group(1)), int(m.group(2))
            if desde > hasta:
                desde, hasta = hasta, desde
            pedidos += [(g, None, True) for g in range(desde, hasta + 1)]
            continue
        m = re.fullmatch(r"(\d{1,2})\s*-\s*(\d{1,2})", t)
        if m:
            pedidos.append((int(m.group(1)), int(m.group(2)), False))
            continue
        if re.fullmatch(r"\d{1,2}", t):
            pedidos.append((int(t), None, True))
            continue
        raise GrupoInvalido(f"No entiendo «{trozo.strip()}». Escriba grados (10), grupos (4-2) o rangos (6 a 9), separados por coma.")
    if any(g < 0 or g > 11 for g, _, _ in pedidos):
        raise GrupoInvalido("Los grados van de 0 (Preescolar) a 11 (Once).")
    if not pedidos:
        raise GrupoInvalido("Escriba al menos un grado o grupo (ej. 10, 11, 4-2).")
    return pedidos


def grupos_a_imprimir(db: Session, sede_id: int, texto: str) -> list[dict]:
    """Cada hoja que va a salir, en orden: {grado, curso, estudiantes}. Un
    grado completo se parte en sus grupos reales (los estudiantes sin grupo
    asignado van en una hoja aparte, curso=None). No repite un grupo pedido
    dos veces."""
    activos = crud.listar_estudiantes(db, sede_id=sede_id, estado="ACTIVO")
    por_grupo: dict[tuple[int, int | None], list] = {}
    for e in activos:
        por_grupo.setdefault((e.grado, e.curso), []).append(e)
    orden = lambda k: (k[0], k[1] is None, k[1] or 0)  # noqa: E731
    hojas, vistos, faltan = [], set(), []
    for grado, curso, todo in parsear_grupos(texto):
        claves = sorted((k for k in por_grupo if k[0] == grado), key=orden) if todo else [(grado, curso)]
        if not claves or not all(k in por_grupo for k in claves):
            faltan.append(f"{grado}" if todo else f"{grado}-{curso}")
            continue
        for k in claves:
            if k not in vistos:
                vistos.add(k)
                hojas.append({"grado": k[0], "curso": k[1], "estudiantes": por_grupo[k]})
    if faltan:
        raise GrupoInvalido(f"Esta sede no tiene estudiantes activos en: {', '.join(faltan)}.")
    return hojas


def nombre_grupo(grado: int, curso: int | None) -> str:
    nombre = models.GRADOS_NOMBRES.get(grado, str(grado))
    return f"{nombre} - {curso}" if curso is not None else f"{nombre} (sin grupo asignado)"


# --- Dibujo --------------------------------------------------------------------


def _ajustar(texto: str, ancho: float, tam: float, fuente: str) -> float:
    """Tamaño de letra para que `texto` quepa en `ancho` (nunca más grande que `tam`)."""
    largo = fitz.get_text_length(texto, fontname=fuente, fontsize=tam)
    return tam if largo <= ancho else max(3.5, tam * ancho / largo)


def _texto(pagina, rect: fitz.Rect, texto: str, tam: float, fuente="helv", alin="c", color=NEGRO):
    """Una línea dentro de `rect`, centrada en vertical, achicada si no cabe.
    `pagina` es el fitz.Shape de la hoja: todo se escribe ahí y se guarda una
    sola vez al final (guardar texto por texto hacía cada hoja ~1 s más lenta)."""
    texto = str(texto or "")
    if not texto:
        return
    tam = _ajustar(texto, rect.width - 4, tam, fuente)
    largo = fitz.get_text_length(texto, fontname=fuente, fontsize=tam)
    x = rect.x0 + 2 if alin == "i" else rect.x0 + (rect.width - largo) / 2
    y = rect.y0 + (rect.height + tam * 0.72) / 2
    pagina.insert_text((x, y), texto, fontsize=tam, fontname=fuente, color=color)


def _campo(pagina, x: float, y: float, etiqueta: str, valor: str, ancho_et: float, ancho_valor: float):
    _texto(pagina, fitz.Rect(x, y, x + ancho_et, y + 14), etiqueta, 8, "hebo", "i")
    rect = fitz.Rect(x + ancho_et, y, x + ancho_et + ancho_valor, y + 14)
    _texto(pagina, rect, valor, 8)
    pagina.draw_line((rect.x0, rect.y1), (rect.x1, rect.y1))
    pagina.finish(color=NEGRO, width=1.2)


def _fecha(f) -> str:
    return f.strftime("%d/%m/%Y") if f else ""


def _hoja(doc: fitz.Document, sede: models.Sede, mes: int, grado: int, curso: int | None, estudiantes: list,
          logos: dict) -> None:
    pagina = doc.new_page(width=PAGINA.width, height=PAGINA.height)
    x0, x1 = MARGEN_X, PAGINA.width - MARGEN_X

    # Encabezado con los dos logos (la imagen se guarda una vez en el PDF y
    # las demás hojas la reutilizan por su xref).
    for logo, rect in ((LOGO_IZQ, fitz.Rect(x0 + 6, 16, x0 + 76, 86)), (LOGO_DER, fitz.Rect(x1 - 76, 16, x1 - 6, 86))):
        if logo in logos:
            pagina.insert_image(rect, xref=logos[logo], keep_proportion=True)
        elif logo.exists():
            logos[logo] = pagina.insert_image(rect, filename=str(logo), keep_proportion=True)
    p = pagina.new_shape()
    y = MARGEN_ARRIBA
    for linea in ENCABEZADO:
        _texto(p, fitz.Rect(x0, y, x1, y + 14), linea, 12)
        y += 14
    _texto(p, fitz.Rect(x0, y + 1, x1, y + 12), "LISTA DE ASISTENCIA", 8, "hebo")
    y += 18

    # Datos del establecimiento, sede, mes y grupo (dos columnas, como el Excel)
    mitad = (x0 + x1) / 2 + 40
    _campo(p, x0, y, "ESTABLECIMIENTO EDUCATIVO:", INSTITUCION_NOMBRE, 120, 300)
    _campo(p, mitad, y, "CODIGO DANE E.E:", INSTITUCION_CODIGO_DANE, 120, x1 - mitad - 120)
    y += 17
    _campo(p, x0, y, "MES:", MESES[mes - 1], 120, 300)
    _campo(p, mitad, y, "NOMBRE DE LA SEDE:", sede.nombre, 120, x1 - mitad - 120)
    y += 17
    _campo(p, x0, y, "CODIGO DANE SEDE:", sede.codigo_dane_sede or "", 120, 300)
    _campo(p, mitad, y, "GRADO / GRUPO:", nombre_grupo(grado, curso).upper(), 120, x1 - mitad - 120)
    y += 24

    # Tabla: columnas de datos + 31 días que llenan el resto del ancho
    anchos = [c[1] for c in COLUMNAS]
    ancho_dia = (x1 - x0 - sum(anchos)) / 31
    xs = [x0]
    for a in anchos + [ancho_dia] * 31:
        xs.append(xs[-1] + a)
    alto_cab = 24
    pie = 30  # renglón del docente
    n = max(len(estudiantes), 1)
    alto_fila = max(FILA_MIN, min(FILA_MAX, (PAGINA.height - MARGEN_ABAJO - pie - y - alto_cab) / n))
    tam = min(7.5, alto_fila * 0.62)

    cab = fitz.Rect(x0, y, x1, y + alto_cab)
    p.draw_rect(cab)
    p.finish(color=NEGRO, fill=VERDE, width=0.6)
    titulos = [c[0] for c in COLUMNAS] + [str(d) for d in range(1, 32)]
    for i, t in enumerate(titulos):
        celda = fitz.Rect(xs[i], y, xs[i + 1], y + alto_cab)
        lineas = t.split("\n")
        for j, linea in enumerate(lineas):
            alto_linea = alto_cab / len(lineas)
            _texto(p, fitz.Rect(celda.x0, celda.y0 + j * alto_linea, celda.x1, celda.y0 + (j + 1) * alto_linea),
                   linea, 5.6 if i < len(COLUMNAS) else 5.2, "hebo", color=(1, 1, 1))
    y += alto_cab

    for n_fila, e in enumerate(estudiantes, start=1):
        valores = [n_fila, e.grado, e.tipo_documento or "", e.documento, e.primer_apellido, e.segundo_apellido or "",
                   e.primer_nombre, e.segundo_nombre or "", _fecha(e.fecha_nacimiento), e.genero or ""]
        for i, v in enumerate(valores):
            _texto(p, fitz.Rect(xs[i], y, xs[i + 1], y + alto_fila), v, tam, alin=COLUMNAS[i][2])
        y += alto_fila

    # Cuadrícula (todas las celdas, incluidos los 31 días)
    y_tabla = cab.y1
    for yy in [y_tabla + k * alto_fila for k in range(len(estudiantes) + 1)]:
        p.draw_line((x0, yy), (x1, yy))
    for xx in xs:
        p.draw_line((xx, cab.y0), (xx, y))
    p.finish(color=NEGRO, width=0.5)

    # Pie: docente(s) e identificación, como la última fila del Excel
    y += 12
    _campo(p, x0, y, "NOMBRE(S) DE DOCENTE(S):", "", 120, 330)
    _campo(p, mitad, y, "No. DE IDENTIFICACIÓN(ES):", "", 120, x1 - mitad - 120)
    p.commit()


def generar_listas_asistencia_pdf(db: Session, sede_id: int, grupos: str, mes: int) -> tuple[bytes, list[dict]]:
    """Un PDF con una hoja oficio horizontal por grupo. Devuelve también qué
    grupos salieron (para el nombre del archivo y el aviso en pantalla)."""
    sede = db.get(models.Sede, sede_id)
    if sede is None:
        raise GrupoInvalido("Sede no encontrada.")
    if not 1 <= mes <= 12:
        raise GrupoInvalido("Mes no válido.")
    hojas = grupos_a_imprimir(db, sede_id, grupos)
    doc = fitz.open()
    logos: dict = {}
    for h in hojas:
        _hoja(doc, sede, mes, h["grado"], h["curso"], h["estudiantes"], logos)
    return doc.tobytes(garbage=3, deflate=True), hojas
