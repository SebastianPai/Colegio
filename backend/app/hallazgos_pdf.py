"""Reporte formal en PDF de diferencias de grado SIMAT ↔ SAPRED (Reportes →
Conciliación → Grilla). Mismo patrón que lista_estudiantes_pdf.py y
docentes_pdf.py: membrete y pie institucionales, portada con explicación y
resumen, detalle agrupado por grado (como la lista de estudiantes), firmas.

A diferencia de esos dos, la fuente de datos es el historial persistente
(hallazgos_conciliacion, ver conciliacion.py) y no un cálculo en vivo: el
reporte impreso conserva los casos aunque ya se hayan corregido, si se pide
incluirlos — es justamente lo que hace falta para no perder de un año a
otro a quién hay que hacerle una promoción anticipada."""

import html
import zipfile

import fitz  # PyMuPDF
from sqlalchemy.orm import Session

from . import conciliacion, fechas, models
from .certificados import PLANTILLA
from .lista_estudiantes_pdf import FUENTES_WINDOWS, LOGO_MEMBRETE, PIE_LEMA, PIE_LINEAS, _css, _fecha_larga
from .reporte_horario import LOGOS, MEMBRETE_LINEAS


def generar_hallazgos_pdf(
    db: Session,
    ids: list[int],
    anio_lectivo: int,
    periodo: int,
    sede_nombre: str = "",
    incluir_resueltos: bool = False,
) -> bytes:
    if not ids:
        raise ValueError("La lista no tiene casos para el PDF.")

    todos = conciliacion.listar_hallazgos(db, incluir_resueltos=True)
    por_id = {h.id: h for h in todos}
    hallazgos = [por_id[i] for i in ids if i in por_id]
    if not hallazgos:
        raise ValueError("La lista no tiene casos para el PDF.")
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
    .badge-pendiente { background: #fde8e8; color: #9b1c1c; }
    .badge-resuelto { background: #e6f4ea; color: #1e7e34; }
    .badge-promocion { background: #fff4e0; color: #92600a; margin-left: 3px; }
    td.grado-cambio { font-weight: bold; color: #1f3a5f; }
    """

    def celda_estado(h) -> str:
        promo = ' <span class="badge badge-promocion">⬆ Promoción anticipada</span>' if h.es_promocion_anticipada else ""
        if h.resuelto:
            quien = html.escape(h.resuelto_por or "")
            cuando = h.resuelto_en.strftime("%d/%m/%Y") if h.resuelto_en else ""
            return f'<span class="badge badge-resuelto">✓ Resuelto</span><br/>{quien} · {cuando}'
        return f'<span class="badge badge-pendiente">Pendiente</span>{promo}'

    # clave → (encabezado, cómo sacar el valor, ancho relativo). "sede" se
    # excluye cuando el reporte ya está acotado a una sola sede (ya sale una
    # vez en el título/tabla de datos — repetirla en cada fila sería ruido,
    # el mismo ajuste que se hizo en la lista de docentes).
    una_sola_sede = bool(sede_nombre) and sede_nombre != "Todas las sedes IETABA"
    COLUMNAS = [
        ("estudiante", "Estudiante", lambda h: html.escape(h.nombre_completo), 3.8),
        ("documento", "Documento", lambda h: html.escape(h.documento), 1.6),
        ("sede", "Sede", lambda h: html.escape(h.sede_nombre), 2.6),
        ("simat", "SIMAT dice", lambda h: html.escape(h.nombre_grupo_simac), 1.8),
        ("sapred", "SAPRED dice", lambda h: html.escape(h.nombre_grupo_sapred), 1.8),
        ("detectado", "Detectado", lambda h: h.detectado_en.strftime("%d/%m/%Y"), 1.5),
        ("estado", "Estado", celda_estado, 2.2),
    ]
    if una_sola_sede:
        COLUMNAS = [c for c in COLUMNAS if c[0] != "sede"]
        COLUMNAS[0] = (COLUMNAS[0][0], COLUMNAS[0][1], COLUMNAS[0][2], COLUMNAS[0][3] + 2.0)  # ensancha "Estudiante"
    peso_total = 0.7 + sum(c[3] for c in COLUMNAS)
    ancho = lambda p: f"{100 * p / peso_total:.1f}%"  # noqa: E731

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

    # --- Portada del informe: título, explicación, datos, resumen ----------
    subtitulo = sede_nombre or "Todas las sedes IETABA"
    pendientes = [h for h in hallazgos if not h.resuelto]
    resueltos = [h for h in hallazgos if h.resuelto]
    candidatos = [h for h in hallazgos if h.es_promocion_anticipada and not h.resuelto]

    titulo = "REPORTE DE DIFERENCIAS DE GRADO — SIMAT vs SAPRED"
    explicacion = (
        f"El presente documento relaciona <b>{len(hallazgos)}</b> caso(s) en <b>{html.escape(subtitulo)}</b> "
        "en los que el grado o grupo registrado en la matrícula (SIMAT) no coincide con el que reporta SAPRED "
        "para el mismo estudiante en el período indicado. SAPRED refleja el grupo donde el docente realmente "
        "le registra notas al estudiante, así que una diferencia no siempre es un error de digitación: cuando "
        "el grado de SAPRED es MAYOR al de SIMAT, corresponde a una promoción que ya ocurrió en la práctica y "
        "que la matrícula del siguiente año debe corregir (marcada abajo como <b>posible promoción "
        "anticipada</b>). Cada caso queda registrado desde que se detecta y solo se cierra cuando el dato se "
        "corrige o alguien lo marca como resuelto — no desaparece del historial institucional. "
        f"Información con corte al {_fecha_larga(hoy)}."
    )
    filas_resumen = f"""
      <tr><td class="izq">Pendientes por revisar</td><td>{len(pendientes)}</td></tr>
      <tr><td class="izq">De los pendientes, posible promoción anticipada</td><td>{len(candidatos)}</td></tr>
      <tr><td class="izq">Ya resueltos (incluidos en este reporte)</td><td>{len(resueltos)}</td></tr>
    """
    portada = f"""
    <h1>{html.escape(titulo)}</h1>
    <p class="subtitulo">{html.escape(subtitulo)}</p>
    <p class="explicacion">{explicacion}</p>
    <table class="datos">
      <tr><td class="et" width="22%">Sede</td><td width="28%">{html.escape(subtitulo)}</td>
          <td class="et" width="22%">Año lectivo / período</td><td width="28%">{anio_lectivo} / {periodo}</td></tr>
      <tr><td class="et">Total de casos</td><td><b>{len(hallazgos)}</b></td>
          <td class="et">Fecha de expedición</td><td>{hoy.strftime("%d/%m/%Y")}</td></tr>
    </table>
    <h2>Resumen</h2>
    <table class="resumen"><tbody>{filas_resumen}</tbody></table>
    <h2>Detalle por grado (según SIMAT)</h2>
    """

    # --- Detalle agrupado por grado (según SIMAT) ---------------------------
    encabezados = f'<th width="{ancho(0.7)}">N°</th>' + "".join(
        f'<th width="{ancho(peso)}">{html.escape(titulo_col)}</th>' for _, titulo_col, _, peso in COLUMNAS
    )

    grupos: list[tuple[str, list[str]]] = []
    clave_actual = None
    for n, h in enumerate(hallazgos, start=1):
        if h.grado_simac != clave_actual:
            clave_actual = h.grado_simac
            grupos.append((models.GRADOS_NOMBRES.get(h.grado_simac, str(h.grado_simac)), []))
        celdas = "".join(
            f'<td class="grado-cambio">{valor(h)}</td>' if clave in ("simat", "sapred") else f"<td>{valor(h)}</td>"
            for clave, _, valor, _ in COLUMNAS
        )
        clase = ' class="par"' if len(grupos[-1][1]) % 2 else ""
        grupos[-1][1].append(f'<tr{clase}><td class="num">{n}</td>{celdas}</tr>')

    firmas = """
    <p class="nota">Documento generado por el sistema institucional de la IETABA a partir del historial de
    conciliación SIMAT ↔ SAPRED.</p>
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

    salida_bytes = _renderizar(paginas, rect_pagina, rect_membrete, rect_pie, area, membrete, pie, css, archivo, margen_x)
    return salida_bytes


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
