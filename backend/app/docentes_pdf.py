"""Lista de docentes en PDF (Reportes → Lista de docentes).

Mismo patrón que lista_estudiantes_pdf.py: el frontend ya decidió QUÉ
docentes van, en qué orden y con qué columnas (dinámico — el usuario elige
si quiere todos los docentes o solo los que dirigen un grupo, y qué datos
mostrar de cada uno, incluida la columna "Director/responsable de"); aquí
se arma el informe formal en hoja carta con el mismo membrete y pie que la
lista de estudiantes.
"""

import datetime as dt
import html
import io
import re
import zipfile
from pathlib import Path

import fitz  # PyMuPDF
from sqlalchemy.orm import Session

from . import crud, fechas
from .certificados import PLANTILLA
from .lista_estudiantes_pdf import FUENTES_WINDOWS, LOGO_MEMBRETE, PIE_LEMA, PIE_LINEAS, _css, _fecha_larga
from .reporte_horario import LOGOS, MEMBRETE_LINEAS

# clave → (encabezado, cómo sacar el valor, ancho relativo)
COLUMNAS = {
    "nombre": ("Nombre completo", lambda d: d["nombre_completo"], 4.2),
    "documento": ("Documento", lambda d: d["documento"], 1.6),
    "telefono": ("Teléfono", lambda d: d["telefono"] or "", 1.5),
    "email": ("Correo", lambda d: d["email"] or "", 2.8),
    "direccion": ("Dirección", lambda d: d["direccion"] or "", 2.8),
    "fecha_nacimiento": (
        "Fecha de nacimiento",
        lambda d: d["fecha_nacimiento"].strftime("%d/%m/%Y") if d["fecha_nacimiento"] else "",
        1.9,
    ),
    "sede": ("Sede(s)", lambda d: ", ".join(sorted({a["sede_nombre"] for a in d["asignaciones"] if a["sede_nombre"]})), 2.6),
    "rol": ("Rol", lambda d: _rol_txt(d), 2.2),
    "director_de": ("Director/responsable de", lambda d: ", ".join(d["grupos_dirige"]) or "—", 3.2),
    "areas": (
        "Área(s) que dicta",
        lambda d: ", ".join(sorted({a["area_nombre"] for a in d["asignaciones"] if a["area_nombre"]})) or "—",
        2.8,
    ),
    "firma": ("Firma", lambda d: "", 3),
}


def _rol_txt(d: dict) -> str:
    tipos = {a["tipo"] for a in d["asignaciones"]}
    if "DIRECTOR" in tipos:
        return "Director de grupo"
    if "GRUPO" in tipos:
        return "Maestro único"
    if "AREA" in tipos:
        return "Docente de área"
    return "Sin asignación"


def generar_lista_docentes_pdf(
    db: Session,
    ids: list[int],
    columnas: list[str],
    anio_lectivo: int,
    sede_nombre: str = "",
    solo_responsables_grupo: bool = False,
) -> bytes:
    columnas = [c for c in dict.fromkeys(columnas) if c in COLUMNAS]
    if not columnas:
        raise ValueError("Escoge al menos una columna para el PDF.")
    if not ids:
        raise ValueError("La lista no tiene docentes.")

    todos = crud.listar_docentes_reporte(db, anio_lectivo)
    por_id = {d["id"]: d for d in todos}
    docentes = [por_id[i] for i in ids if i in por_id]
    if not docentes:
        raise ValueError("La lista no tiene docentes.")
    hoy = fechas.hoy_colombia()

    archivo, logo_html, hay_magneto = _recursos()
    peso_total = 0.7 + sum(COLUMNAS[c][2] for c in columnas)
    tam_tabla = 8.2 if peso_total <= 13 else 7.2 if peso_total <= 19 else 6.3
    css = _css(tam_tabla, hay_magneto)
    ancho = lambda p: f"{100 * p / peso_total:.1f}%"  # noqa: E731

    # --- Portada del informe ------------------------------------------------
    titulo = "LISTADO DE DOCENTES RESPONSABLES DE GRUPO" if solo_responsables_grupo else "LISTADO DE DOCENTES"
    subtitulo = sede_nombre or "Todas las sedes IETABA"
    n_directores = sum(1 for d in docentes if d["es_responsable_grupo"])
    explicacion = (
        f"El presente documento relaciona <b>{len(docentes)}</b> docente(s) de <b>{html.escape(subtitulo)}</b>"
        + (
            ", que dirigen o responden por un grupo completo (director de grupo o maestro único)."
            if solo_responsables_grupo
            else f", de los cuales <b>{n_directores}</b> dirige(n) o responde(n) por un grupo completo."
        )
        + " La información se toma de la base de datos institucional de la IETABA, con corte al "
        f"{_fecha_larga(hoy)}."
    )
    portada = f"""
    <h1>{html.escape(titulo)}</h1>
    <p class="subtitulo">{html.escape(subtitulo)}</p>
    <p class="explicacion">{explicacion}</p>
    <table class="datos">
      <tr><td class="et" width="22%">Sede</td><td width="28%">{html.escape(subtitulo)}</td>
          <td class="et" width="22%">Año lectivo</td><td width="28%">{anio_lectivo}</td></tr>
      <tr><td class="et">Total de docentes</td><td><b>{len(docentes)}</b></td>
          <td class="et">Fecha de expedición</td><td>{hoy.strftime("%d/%m/%Y")}</td></tr>
    </table>
    <h2>Detalle de docentes</h2>
    """

    # --- Detalle: tabla plana con encabezado repetido -----------------------
    encabezados = f'<th width="{ancho(0.7)}">N°</th>' + "".join(
        f'<th width="{ancho(COLUMNAS[c][2])}">{html.escape(COLUMNAS[c][0])}</th>' for c in columnas
    )
    filas = []
    for n, d in enumerate(docentes, start=1):
        celdas = "".join(f"<td>{html.escape(str(COLUMNAS[c][1](d)))}</td>" for c in columnas)
        clase = ' class="par"' if n % 2 == 0 else ""
        filas.append(f'<tr{clase}><td class="num">{n}</td>{celdas}</tr>')

    return _componer_pdf(portada, encabezados, filas, css, archivo, logo_html)


def _recursos() -> tuple["fitz.Archive", str, bool]:
    """Logo de la plantilla oficial y fuente del lema, para el membrete."""
    archivo = fitz.Archive()
    logo_html = ""
    try:
        with zipfile.ZipFile(PLANTILLA) as z:
            archivo.add((z.read("word/media/image2.jpeg"), LOGO_MEMBRETE))
        logo_html = f'<img src="{LOGO_MEMBRETE}" width="66"/>'
    except (OSError, KeyError, zipfile.BadZipFile):
        if (LOGOS / "logo2.jpeg").exists():
            archivo.add(str(LOGOS))
            logo_html = '<img src="logo2.jpeg" width="66"/>'
    hay_magneto = (FUENTES_WINDOWS / "MAGNETOB.TTF").exists()
    if hay_magneto:
        archivo.add(((FUENTES_WINDOWS / "MAGNETOB.TTF").read_bytes(), "MAGNETOB.TTF"))
    return archivo, logo_html, hay_magneto


def _componer_pdf(
    portada: str, encabezados: str, filas: list[str], css: str, archivo, logo_html: str, nota_final: str = "",
) -> bytes:
    """Hoja carta con membrete y pie en cada página; la tabla se parte entre
    hojas repitiendo el encabezado, y al final van las firmas."""
    textos = [t for t, tipo in MEMBRETE_LINEAS if tipo != "lema"]
    lema = next((t for t, tipo in MEMBRETE_LINEAS if tipo == "lema"), "")
    membrete = (
        '<table class="m-tabla"><tr>'
        f'<td width="16%">{logo_html}</td>'
        '<td width="84%">'
        + "".join(f'<p class="m-texto">{html.escape(t)}</p>' for t in textos)
        + f'<p class="m-lema">{html.escape(lema)}</p>'
        + '</td></tr></table>'
    )
    pie = (
        '<p class="pie-linea"></p>'
        f'<p class="pie-lema">{html.escape(PIE_LEMA)}</p>'
        + "".join(f'<p class="pie-texto">{html.escape(t)}</p>' for t in PIE_LINEAS)
    )
    firmas = nota_final + """
    <p class="nota">Documento generado por el sistema institucional de la IETABA.</p>
    <table class="firmas"><tr>
      <td width="50%">______________________________<br/><b>Rector(a)</b></td>
      <td width="50%">______________________________<br/><b>Secretaría académica</b></td>
    </tr></table>
    """

    # --- Paginación ----------------------------------------------------------
    rect_pagina = fitz.paper_rect("letter")
    margen_x = 42
    rect_membrete = fitz.Rect(margen_x, 24, rect_pagina.width - margen_x, 110)
    rect_pie = fitz.Rect(margen_x, rect_pagina.height - 64, rect_pagina.width - margen_x, rect_pagina.height - 14)
    area = fitz.Rect(margen_x, 116, rect_pagina.width - margen_x, rect_pagina.height - 72)

    def cabe(contenido: str) -> bool:
        sobra, _ = fitz.Story(html=contenido, user_css=css, archive=archivo).place(area)
        return not sobra

    def tabla(filas_tabla: list[str]) -> str:
        return f'<table class="lista" width="100%"><thead><tr>{encabezados}</tr></thead><tbody>{"".join(filas_tabla)}{relleno}</tbody></table>'

    # MuPDF ignora width:100% (y no respeta colspan al medir): encoge la tabla
    # a su contenido, y una hoja con pocas filas cortas salía angosta. Una fila
    # invisible con, en cada columna, un relleno que no se parte y mide lo que
    # le toca según su % del encabezado, la obliga a ocupar el ancho de la hoja.
    ancho_espacio = fitz.get_text_length(" ", fontsize=1) or 0.28
    relleno = "<tr>" + "".join(
        f'<td style="border:0;padding:0;color:#fff;font-size:1pt;line-height:1pt">'
        f'{"&#160;" * int(0.97 * area.width * float(pct) / 100 / ancho_espacio)}</td>'
        for pct in re.findall(r'width="([\d.]+)%"', encabezados)
    ) + "</tr>"

    paginas: list[str] = []
    actual = portada
    i = 0
    while i < len(filas):
        resto = filas[i:]
        if cabe(actual + tabla(resto)):
            actual += tabla(resto)
            i = len(filas)
            continue
        lo, hi = 0, len(resto)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if cabe(actual + tabla(resto[:mid])):
                lo = mid
            else:
                hi = mid - 1
        if lo == 0 and actual == "":
            raise ValueError("Una fila no cabe en la hoja; quita algunas columnas.")
        if lo == 0:
            paginas.append(actual)
            actual = ""
            continue
        actual += tabla(resto[:lo])
        i += lo
        paginas.append(actual)
        actual = ""
    if cabe(actual + firmas):
        actual += firmas
    else:
        paginas.append(actual)
        actual = firmas
    paginas.append(actual)

    salida = io.BytesIO()
    escritor = fitz.DocumentWriter(salida)
    for contenido in paginas:
        dispositivo = escritor.begin_page(rect_pagina)
        for texto, rect in ((membrete, rect_membrete), (contenido, area), (pie, rect_pie)):
            story = fitz.Story(html=texto, user_css=css, archive=archivo)
            story.place(rect)
            story.draw(dispositivo)
        escritor.end_page()
    escritor.close()

    doc = fitz.open("pdf", salida.getvalue())
    for i, pagina in enumerate(doc, start=1):
        pagina.insert_text(
            (rect_pagina.width - margen_x - 52, rect_pagina.height - 18),
            f"Página {i} de {doc.page_count}",
            fontsize=7,
            color=(0.35, 0.35, 0.35),
        )
    return doc.tobytes(garbage=3, deflate=True)


# --- Docentes por grado (Reportes → Lista de docentes → Por grado) -------------


def generar_docentes_por_grado_pdf(
    db: Session, grados: list[int], anio_lectivo: int, sede_id: int | None = None, sede_nombre: str = "",
) -> bytes:
    """Quién dicta en los grados pedidos (ej. Décimo y Once): cada docente con
    sus materias y grupos y de qué grupo es director.
    Datos: crud.docentes_por_grados (asignaciones + horario)."""
    from .models import GRADOS_NOMBRES

    if not grados:
        raise ValueError("Escoge al menos un grado.")
    docentes = crud.docentes_por_grados(db, anio_lectivo, grados, sede_id)
    if not docentes:
        raise ValueError("No hay docentes asignados ni en el horario para esos grados.")
    hoy = fechas.hoy_colombia()
    archivo, logo_html, hay_magneto = _recursos()
    css = _css(8.0, hay_magneto)

    nombres = [GRADOS_NOMBRES.get(g, str(g)) for g in sorted(grados)]
    grados_txt = nombres[0] if len(nombres) == 1 else f"{', '.join(nombres[:-1])} y {nombres[-1]}"
    sede_txt = sede_nombre or "Todas las sedes IETABA"
    n_materias = len({m["area"] for d in docentes for m in d["materias"]})
    hay_solo_horario = any(g["solo_horario"] for d in docentes for m in d["materias"] for g in m["grupos"])
    portada = f"""
    <h1>DOCENTES DE {html.escape(grados_txt.upper())}</h1>
    <p class="subtitulo">{html.escape(sede_txt)}</p>
    <p class="explicacion">En {html.escape(grados_txt)} dictan clase <b>{len(docentes)}</b> docente(s), en <b>{n_materias}</b> materia(s).
      La información se toma de las asignaciones y del horario institucional de la IETABA, con corte al {_fecha_larga(hoy)}.</p>
    <table class="datos">
      <tr><td class="et" width="22%">Grados</td><td width="28%">{html.escape(grados_txt)}</td>
          <td class="et" width="22%">Año lectivo</td><td width="28%">{anio_lectivo}</td></tr>
      <tr><td class="et">Total de docentes</td><td><b>{len(docentes)}</b></td>
          <td class="et">Fecha de expedición</td><td>{hoy.strftime("%d/%m/%Y")}</td></tr>
    </table>
    <h2>Detalle de docentes</h2>
    """
    pesos = [0.9, 3.6, 1.7, 7.2, 1.7]
    total = sum(pesos)
    titulos = ["#", "Docente", "Documento", "Materias y grupos", "Director de grupo"]
    encabezados = "".join(f'<th width="{100 * p / total:.1f}%">{t}</th>' for p, t in zip(pesos, titulos))
    filas = []
    for n, d in enumerate(docentes, start=1):
        materias = "<br/>".join(
            f"<b>{html.escape(m['area'])}:</b> "
            + ", ".join(html.escape(g["grupo"]) + ("*" if g["solo_horario"] else "") for g in m["grupos"])
            for m in d["materias"]
        ) or "—"
        clase = ' class="par"' if n % 2 == 0 else ""
        filas.append(
            f'<tr{clase}><td class="num">{n}</td><td>{html.escape(d["nombre_completo"])}</td>'
            f'<td>{html.escape(d["documento"] or "")}</td><td>{materias}</td>'
            f'<td>{html.escape(", ".join(d["director_de"]) or "NO")}</td></tr>'
        )
    nota = (
        '<p class="nota">* Grupo que figura en el horario pero no tiene la asignación registrada en el sistema.</p>'
        if hay_solo_horario else ""
    )
    return _componer_pdf(portada, encabezados, filas, css, archivo, logo_html, nota_final=nota)
