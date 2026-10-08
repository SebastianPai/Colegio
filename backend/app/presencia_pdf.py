"""Reporte formal en PDF de presencia SIMAT ↔ SAPRED (Reportes →
Conciliación → Estudiantes): quién aparece en un solo lado (matriculado en
SIMAT pero SAPRED no le registra nada, o al revés). Es un problema distinto
al de "diferencia de grado" (ver hallazgos_pdf.py): aquí el estudiante ni
siquiera se encuentra al otro lado, no es que el grado no coincida.

A diferencia de los hallazgos de grado, esto NO se persiste — se recalcula
en vivo igual que el resto de conciliacion.py (ver ese docstring): un
estudiante "solo SIMAC" hoy puede dejar de estarlo apenas se importe su
nota, así que no tiene el mismo valor histórico que justificaría guardarlo.

Por defecto solo trae los que tienen problema (solo_simac / solo_sapred);
"incluir_coincide" es lo que pidió el usuario para poder marcar, cuando
quiera, que también salgan en el PDF los que sí coinciden."""

import html
import zipfile

import fitz  # PyMuPDF
from sqlalchemy.orm import Session

from . import conciliacion as conciliacion_mod
from . import fechas, models
from .certificados import PLANTILLA
from .lista_estudiantes_pdf import FUENTES_WINDOWS, LOGO_MEMBRETE, PIE_LEMA, PIE_LINEAS, _css, _fecha_larga
from .reporte_horario import LOGOS, MEMBRETE_LINEAS

ETIQUETAS_ESTADO = {
    "solo_simac": ("Solo SIMAT", "badge-solo-simat"),
    "solo_sapred": ("Solo SAPRED", "badge-solo-sapred"),
    "coincide": ("Coincide", "badge-coincide"),
}


def generar_presencia_pdf(
    db: Session,
    anio_lectivo: int,
    periodo: int,
    sede_id: int | None = None,
    grado: int | None = None,
    sede_nombre: str = "",
    incluir_coincide: bool = False,
) -> bytes:
    resultado = conciliacion_mod.conciliar(db, anio_lectivo=anio_lectivo, periodo=periodo, sede_id=sede_id, grado=grado)
    estados = {"solo_simac", "solo_sapred"} | ({"coincide"} if incluir_coincide else set())
    estudiantes = [e for e in resultado.estudiantes if e.estado_conciliacion in estados]
    if not estudiantes:
        raise ValueError("No hay casos para este filtro.")
    hoy = fechas.hoy_colombia()

    # --- Recursos: logo de la plantilla oficial y fuente del lema -----------
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

    css = _css(8.2, hay_magneto) + """
    .badge { display: inline-block; padding: 1px 6px; border-radius: 9px; font-size: 7.2pt; font-weight: bold; }
    .badge-solo-simat { background: #fde8e8; color: #9b1c1c; }
    .badge-solo-sapred { background: #fff1e0; color: #92600a; }
    .badge-coincide { background: #e6f4ea; color: #1e7e34; }
    """

    # --- Membrete y pie (se dibujan en cada hoja) ---------------------------
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

    # --- Portada del informe -------------------------------------------------
    subtitulo = sede_nombre or "Todas las sedes IETABA"
    solo_simac_n = sum(1 for e in estudiantes if e.estado_conciliacion == "solo_simac")
    solo_sapred_n = sum(1 for e in estudiantes if e.estado_conciliacion == "solo_sapred")
    coincide_n = sum(1 for e in estudiantes if e.estado_conciliacion == "coincide")

    titulo = "REPORTE DE PRESENCIA — SIMAT vs SAPRED"
    explicacion = (
        f"El presente documento relaciona <b>{len(estudiantes)}</b> caso(s) en <b>{html.escape(subtitulo)}</b> "
        "donde un estudiante aparece matriculado en SIMAT pero SAPRED no le tiene ningún registro "
        "(<b>Solo SIMAT</b>), o al contrario, SAPRED reporta un estudiante que no se logra emparejar con la "
        "matrícula local (<b>Solo SAPRED</b>). Es un problema distinto al de diferencia de grado: aquí el "
        "estudiante no se encuentra del todo al otro lado, no es que el grado no coincida. "
        + (
            "También se incluyen, al final de cada grado, los que sí coinciden en ambos sistemas. "
            if incluir_coincide
            else ""
        )
        + f"Información con corte al {_fecha_larga(hoy)}."
    )
    filas_resumen = f"""
      <tr><td class="izq">Solo en SIMAT (matriculados, sin nada en SAPRED)</td><td>{solo_simac_n}</td></tr>
      <tr><td class="izq">Solo en SAPRED (sin matrícula local que les corresponda)</td><td>{solo_sapred_n}</td></tr>
      {f'<tr><td class="izq">Coinciden en ambos sistemas</td><td>{coincide_n}</td></tr>' if incluir_coincide else ''}
    """
    portada = f"""
    <h1>{html.escape(titulo)}</h1>
    <p class="subtitulo">{html.escape(subtitulo)}</p>
    <p class="explicacion">{explicacion}</p>
    <table class="datos">
      <tr><td class="et" width="22%">Sede</td><td width="28%">{html.escape(subtitulo)}</td>
          <td class="et" width="22%">Año lectivo / período</td><td width="28%">{anio_lectivo} / {periodo}</td></tr>
      <tr><td class="et">Total de casos</td><td><b>{len(estudiantes)}</b></td>
          <td class="et">Fecha de expedición</td><td>{hoy.strftime("%d/%m/%Y")}</td></tr>
    </table>
    <h2>Resumen</h2>
    <table class="resumen"><tbody>{filas_resumen}</tbody></table>
    <h2>Detalle por grado</h2>
    """

    # --- Detalle agrupado por grado ------------------------------------------
    peso = {"nombre": 4.2, "documento": 1.8, "grupo": 2.2, "docente": 3.2, "estado": 2.2}
    peso_total = 0.7 + sum(peso.values())
    ancho = lambda p: f"{100 * p / peso_total:.1f}%"  # noqa: E731
    encabezados = (
        f'<th width="{ancho(0.7)}">N°</th>'
        f'<th width="{ancho(peso["nombre"])}">Nombre</th>'
        f'<th width="{ancho(peso["documento"])}">Documento</th>'
        f'<th width="{ancho(peso["grupo"])}">Grupo</th>'
        f'<th width="{ancho(peso["docente"])}">Director / docente</th>'
        f'<th width="{ancho(peso["estado"])}">Estado</th>'
    )

    def celda_estado(e) -> str:
        texto, clase = ETIQUETAS_ESTADO.get(e.estado_conciliacion, (e.estado_conciliacion, ""))
        return f'<span class="badge {clase}">{html.escape(texto)}</span>'

    orden_estado = {"solo_simac": 0, "solo_sapred": 1, "coincide": 2}
    estudiantes_ordenados = sorted(
        estudiantes,
        key=lambda e: (e.grado if e.grado is not None else 99, orden_estado.get(e.estado_conciliacion, 9), e.nombre_completo),
    )

    grupos: list[tuple[str, list[str]]] = []
    clave_actual = object()
    for n, e in enumerate(estudiantes_ordenados, start=1):
        if e.grado != clave_actual:
            clave_actual = e.grado
            nombre_g = models.GRADOS_NOMBRES.get(e.grado, str(e.grado)) if e.grado is not None else "Sin grado"
            grupos.append((nombre_g, []))
        celdas = (
            f"<td>{html.escape(e.nombre_completo)}</td>"
            f"<td>{html.escape(e.documento)}</td>"
            f"<td>{html.escape(e.nombre_grupo)}</td>"
            f"<td>{html.escape(e.docente or 'Sin asignar')}</td>"
            f"<td>{celda_estado(e)}</td>"
        )
        clase = ' class="par"' if len(grupos[-1][1]) % 2 else ""
        grupos[-1][1].append(f'<tr{clase}><td class="num">{n}</td>{celdas}</tr>')

    firmas = """
    <p class="nota">Documento generado por el sistema institucional de la IETABA a partir de la conciliación
    SIMAT ↔ SAPRED.</p>
    <table class="firmas"><tr>
      <td width="50%">______________________________<br/><b>Coordinación académica</b></td>
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

    def tabla_grupo(titulo_g: str, filas: list[str], continuacion: bool, total: int) -> str:
        etiqueta = "continuación" if continuacion else f"{total} caso{'' if total == 1 else 's'}"
        return (
            f'<p class="grupo">{html.escape(titulo_g)} <span>({etiqueta})</span></p>'
            f'<table class="lista"><thead><tr>{encabezados}</tr></thead><tbody>{"".join(filas)}</tbody></table>'
        )

    paginas: list[str] = []
    actual = portada
    for titulo_g, filas in grupos:
        i = 0
        while i < len(filas):
            continuacion = i > 0
            resto = filas[i:]
            if cabe(actual + tabla_grupo(titulo_g, resto, continuacion, len(filas))):
                actual += tabla_grupo(titulo_g, resto, continuacion, len(filas))
                i = len(filas)
                continue
            lo, hi = 0, len(resto)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if cabe(actual + tabla_grupo(titulo_g, resto[:mid], continuacion, len(filas))):
                    lo = mid
                else:
                    hi = mid - 1
            minimo = min(3, len(resto))
            if lo >= minimo or (lo > 0 and actual == ""):
                actual += tabla_grupo(titulo_g, resto[:lo], continuacion, len(filas))
                i += lo
            elif actual == "":
                raise ValueError("Una fila no cabe en la hoja.")
            paginas.append(actual)
            actual = ""
    if cabe(actual + firmas):
        actual += firmas
    else:
        paginas.append(actual)
        actual = firmas
    paginas.append(actual)

    return _renderizar(paginas, rect_pagina, rect_membrete, rect_pie, area, membrete, pie, css, archivo, margen_x)


def _renderizar(paginas, rect_pagina, rect_membrete, rect_pie, area, membrete, pie, css, archivo, margen_x) -> bytes:
    import io

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
