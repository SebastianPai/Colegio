"""PDF imprimible del módulo de orientación escolar:
  · el diagnóstico de un grado (el formulario importado del Excel, ver
    diagnostico_import.py) — tal cual la maqueta numerada 1-11;
  · el INFORME DEL GRUPO (resumen de orientación de un grupo de matrícula);
  · el INFORME GENERAL de la sede (toda la IETABA);
  · el informe de un estudiante y el de un caso puntual.
Mismo membrete/pie institucional que el resto de reportes (ver
pdf_membrete.py) — este archivo NO define ningún membrete propio.

Son documentos institucionales para archivar/imprimir, no una vista de
trabajo: por eso NUNCA aparece aquí nada administrativo (badges de "sin
vincular", ids, botones, confianza de extracción). Cuando una mención no
tiene un estudiante vinculado con confianza, simplemente se imprime el
nombre tal como quedó escrito en el Excel — nunca se inventa a quién
pertenece. Los números son conteos directos (de lo importado y de los casos
registrados), nunca estimados.

Todo informe de orientación lo firman los dos orientadores escolares de la
institución (ORIENTADORES, abajo) — decisión de la institución.

Las tablas largas se paginan fila por fila (binary search de cuántas filas
caben, igual que hallazgos_pdf.py) en vez de tratarse como un bloque
todo-o-nada: así no quedan páginas con media hoja vacía ni se recorta
información que no cupo entera."""

import datetime as dt
import html

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import crud, fechas, models, pdf_membrete

# Los dos orientadores escolares que firman todos los informes de este módulo.
ORIENTADORES = [
    ("ROCÍO RIASCOS MUÑOZ", "Orientadora escolar"),
    ("LUIS ALEJANDRO ORTEGA PARDO", "Orientador escolar"),
]

CSS_DX = """
table.dx-datos { width: 100%; border-collapse: collapse; margin: 0 0 10px 0; }
table.dx-datos td { border: 0.6px solid #9aa7b8; padding: 3px 6px; font-size: 8.8pt; }
table.dx-datos td.et { background-color: #eef2f7; font-weight: bold; color: #1f3a5f; }
.dx-campo { font-size: 9pt; line-height: 1.4; margin: 0 0 6px 0; text-align: justify; }
.dx-campo b.dx-etq { color: #1f3a5f; }
.dx-vacio { color: #777; font-style: italic; }
table.dx-menciones { width: 100%; border-collapse: collapse; margin: 4px 0 8px 0; }
table.dx-menciones th { background-color: #1f3a5f; color: #fff; font-size: 7.8pt; padding: 3px 4px; border: 0.6px solid #1f3a5f; text-align: left; }
table.dx-menciones td { font-size: 7.8pt; padding: 2px 4px; border: 0.6px solid #9aa7b8; vertical-align: top; }
table.dx-menciones tr.par td { background-color: #f5f7fa; }
table.dx-menciones tr.nuevo-estudiante td { border-top: 1.4px solid #1f3a5f; }
table.dx-menciones td.num { text-align: center; }
table.dx-menciones th.num { text-align: center; }
table.dx-menciones tr.total td { background-color: #eef2f7; font-weight: bold; color: #1f3a5f; }
table.dx-2col { width: 100%; border-collapse: collapse; }
table.dx-2col td { width: 50%; vertical-align: top; padding: 0 10px 0 0; }
.dx-obs-item, .dx-nota-item { margin: 0 0 6px 0; font-size: 8.6pt; }
.dx-obs-meta { color: #555; font-size: 7.6pt; }
.dx-caso-cab { font-size: 9pt; font-weight: bold; color: #1f3a5f; margin: 0 0 2px 0; }
.dx-caso-meta { font-size: 7.6pt; color: #555; margin: 0 0 4px 0; }

.conf { font-size: 7.4pt; color: #7a2e0e; background-color: #fdf3e7; border: 0.6px solid #e8c9a4;
        padding: 3px 6px; margin: 0 0 10px 0; text-align: center; }
table.kpis { width: 100%; border-collapse: separate; border-spacing: 5px 0; margin: 0 0 10px 0; }
table.kpis td { border: 0.7px solid #c9d3e0; background-color: #f4f7fb; padding: 5px 7px; vertical-align: top; }
table.kpis td.alerta { background-color: #fdecec; border-color: #f0b4b4; }
.kn { font-size: 15pt; font-weight: bold; color: #1f3a5f; margin: 0; }
td.alerta .kn { color: #b91c1c; }
.kl { font-size: 7.2pt; color: #555; margin: 0; }
table.barra { width: 100%; border-collapse: collapse; }
table.dx-menciones table.barra td, table.dx-menciones tr.par table.barra td { border: none; padding: 0; font-size: 5pt; background-color: transparent; }
table.dx-menciones table.barra td.lleno, table.dx-menciones tr.par table.barra td.lleno { background-color: #1f3a5f; }
td.vencido { color: #b91c1c; font-weight: bold; }
table.caso-cab { width: 100%; border-collapse: collapse; margin: 6px 0 0 0; }
table.caso-cab td { background-color: #1f3a5f; color: #fff; font-size: 9pt; font-weight: bold; padding: 4px 7px; }
table.caso-cab td.estado { text-align: right; font-size: 8pt; width: 30%; }
.fuente { font-size: 7.4pt; color: #555; margin: 2px 0 8px 0; text-align: justify; }
"""

CATEGORIAS_TITULOS = {
    "no_asiste": "No asiste", "intermitencia": "Intermitencia",
    "desplazado": "Desplazado", "embarazada": "Embarazada",
    "victima_conflicto": "Víctima de conflicto armado",
    "dificultad_academica": "Dificultad académica",
    "dificultad_comportamiento": "Dificultad de comportamiento",
    "llamado_atencion": "Llamado de atención", "salud": "Salud",
}

TIPOS_CASO_TITULOS = {
    "academica": "Académico", "comportamiento": "Comportamiento", "inasistencia": "Inasistencia",
    "intermitencia": "Intermitencia", "familiar": "Familiar", "salud": "Salud",
    "convivencia": "Convivencia", "orientacion": "Orientación", "riesgo": "Riesgo", "otra": "Otra",
}
ESTADOS_CASO_TITULOS = {"abierto": "Abierto", "en_seguimiento": "En seguimiento", "cerrado": "Cerrado"}

# Columnas del informe general: categorías del Excel agrupadas por tema. Se
# cuentan PERSONAS distintas (una que aparece en dos categorías del mismo
# tema cuenta una vez).
TEMAS_INFORME_GENERAL = [
    ("Asistencia", ("no_asiste", "intermitencia")),
    ("Académico", ("dificultad_academica",)),
    ("Comport.", ("dificultad_comportamiento", "llamado_atencion")),
    ("Riesgo", ("desplazado", "victima_conflicto")),
    ("Salud", ("salud", "embarazada")),
]

NIVELES = [
    ("Preescolar", lambda g: g == 0),
    ("Básica primaria", lambda g: 1 <= g <= 5),
    ("Básica secundaria", lambda g: 6 <= g <= 9),
    ("Media", lambda g: g >= 10),
]

# Lo GENERAL que reporta el director de cada grupo (no de un estudiante).
# Mismo orden que OR_GENERALES en orientacion.js; se imprime siempre, con
# "Sin respuesta" si quedó en blanco en el Excel.
GENERALES = [
    ("Temáticas para trabajar con los estudiantes", "tematicas_trabajar"),
    ("Estrategias para solucionar conflictos", "estrategias_conflicto"),
    ("Estrategias para fortalecer el aprendizaje", "estrategias_aprendizaje"),
    ("Resguardos que se atienden", "resguardos_atendidos"),
    ("Recomendaciones de los docentes", "recomendaciones_docentes"),
    ("Orientación que se ha brindado", "orientacion_brindada"),
    ("Acompañamiento de los padres de familia", "acompanamiento_padres"),
]

NOTA_CONFIDENCIAL = (
    '<p class="conf">DOCUMENTO CONFIDENCIAL — Contiene información sensible de estudiantes menores de edad. '
    "Uso exclusivo de orientación escolar y directivos de la institución.</p>"
)


# fitz.Story IGNORA los anchos en porcentaje (y el atributo width): solo
# respeta un ancho absoluto en pt puesto en el style de CADA celda. Todos los
# anchos de este archivo se escriben en % y se convierten aquí a pt sobre el
# ancho útil de la hoja carta vertical, descontando el relleno+borde de cada
# celda (si la suma se pasa del ancho útil, la tabla se sale de la hoja).
ANCHO_UTIL = pdf_membrete.medidas(horizontal=False)[2].width
RELLENO_CELDA = 13  # padding horizontal 4+4 + bordes, con margen (tablas dx-menciones)


def _anchos_pt(porcentajes: list[float | None], disponible: float = ANCHO_UTIL, relleno: float = RELLENO_CELDA) -> list[float]:
    """% → pt. Las columnas con None se reparten lo que sobre. `relleno` =
    padding horizontal + bordes de UNA celda de esa tabla."""
    util = disponible - relleno * len(porcentajes) - 4
    conocidos = sum(x for x in porcentajes if x)
    libres = [x for x in porcentajes if not x]
    resto = max(0.0, 100 - conocidos) / len(libres) if libres else 0
    return [util * (x or resto) / 100 for x in porcentajes]


def _w(pt: float) -> str:
    return f'style="width:{pt:.1f}pt"'


# Columna de barras de las tablas "situaciones por categoría" (34/13/12/41 %),
# menos el padding de la celda que la contiene.
ANCHO_BARRA = _anchos_pt([34, 13, 12, 41])[3] - 8


def _grado_nombre(grado: int, curso: int | None) -> str:
    nombre = models.GRADOS_NOMBRES.get(grado, str(grado))
    if not curso:
        return nombre
    division = models.DIVISIONES_NOMBRES.get(curso, str(curso))
    return f"{nombre} - {division}"


def _f(d: dt.date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def _e(texto) -> str:
    return html.escape(str(texto)) if texto not in (None, "") else "—"


def _sub(etiqueta: str, valor: str | None) -> str:
    if not (valor or "").strip():
        return ""
    return f'<p class="dx-campo"><b class="dx-etq">{html.escape(etiqueta)}:</b> {html.escape(valor.strip())}</p>'


def _seccion(numero: int, titulo: str, contenido: str) -> str:
    if not contenido.strip():
        return ""
    return f"<h2>{numero}. {html.escape(titulo.upper())}</h2>{contenido}"


def _quien_mencion(estudiante, nombre_detectado: str | None) -> str:
    if estudiante is not None:
        return html.escape(estudiante.nombre_completo)
    return html.escape(nombre_detectado or "—")


def _edad(nacimiento: dt.date | None, hoy: dt.date) -> int | None:
    if not nacimiento:
        return None
    edad = hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))
    return edad if 0 <= edad < 100 else None


def _ficha(filas: list[tuple[str, str, str, str]]) -> str:
    """Tabla de datos de 4 columnas (etiqueta, valor, etiqueta, valor). Los
    valores ya vienen escapados."""
    w1, w2, w3, w4 = _anchos_pt([22, 28, 22, 28], relleno=17)  # dx-datos: padding 6+6
    cuerpo = "".join(
        f'<tr><td class="et" {_w(w1)}>{html.escape(a)}</td><td {_w(w2)}>{b}</td>'
        f'<td class="et" {_w(w3)}>{html.escape(c)}</td><td {_w(w4)}>{d}</td></tr>'
        for a, b, c, d in filas
    )
    return f'<table class="dx-datos" style="width:100%">{cuerpo}</table>'


def _kpis(items: list[tuple]) -> str:
    """items: (valor, etiqueta[, alerta: bool])."""
    # border-spacing 5pt entre tarjetas + padding 7+7 + bordes
    ancho = (ANCHO_UTIL - 5 * (len(items) + 1) - 20 * len(items)) / len(items)
    celdas = "".join(
        f'<td {_w(ancho)}{" class=alerta" if len(it) > 2 and it[2] else ""}>'
        f'<p class="kn">{html.escape(str(it[0]))}</p><p class="kl">{html.escape(it[1])}</p></td>'
        for it in items
    )
    return f'<table class="kpis" style="width:100%"><tr>{celdas}</tr></table>'


def _barra(valor: int, maximo: int, ancho_pt: float) -> str:
    """Barra horizontal proporcional dentro de una celda de `ancho_pt`."""
    if maximo <= 0 or valor <= 0:
        return ""
    lleno = max(3.0, ancho_pt * valor / maximo)
    resto = f'<td {_w(ancho_pt - lleno)}>&#160;</td>' if ancho_pt - lleno > 1 else ""
    return f'<table class="barra"><tr><td class="lleno" {_w(lleno)}>&#160;</td>{resto}</tr></table>'


def _firmas(hoy: dt.date, elaborado_por: str | None, nota: str = "") -> str:
    elaboro = f" Generado por {html.escape(elaborado_por)}" if elaborado_por else " Generado"
    celdas = "".join(
        f'<td {_w(ANCHO_UTIL / 2 - 14)}>______________________________<br/><b>{html.escape(nombre)}</b><br/>{html.escape(cargo)}</td>'
        for nombre, cargo in ORIENTADORES
    )
    return (
        f'<p class="nota">{nota}{elaboro} en el sistema institucional de la IETABA el {pdf_membrete.fecha_larga(hoy)}.</p>'
        f'<table class="firmas" style="width:100%"><tr>{celdas}</tr></table>'
    )


# --- Paginación: bloques sueltos y listas de ítems -------------------------


def _agregar(papeleria, area, actual: str, paginas: list[str], bloque: str) -> str:
    """Mete `bloque` en la hoja actual si cabe; si no, cierra la hoja y lo
    pone al inicio de una nueva."""
    if not bloque:
        return actual
    if papeleria.cabe(actual + bloque, area):
        return actual + bloque
    if actual:
        paginas.append(actual)
    return bloque


def _paginar_items(papeleria, area, actual: str, paginas: list[str], items: list[str], envolver) -> str:
    """`envolver(items_parciales, continuacion) -> html`. Coloca tantos
    `items` como quepan en lo que resta de hoja; si no caben todos, corta
    (binary search) y sigue en hojas nuevas, repitiendo encabezado con
    "(continuación)". Si ni uno solo cabe en una hoja vacía, lo coloca
    igual recortado — nunca se descarta un ítem por no caber."""
    i, n = 0, len(items)
    while i < n:
        continuacion = i > 0
        resto = items[i:]
        bloque = envolver(resto, continuacion)
        if papeleria.cabe(actual + bloque, area):
            actual += bloque
            i = n
            continue
        lo, hi = 0, len(resto)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if papeleria.cabe(actual + envolver(resto[:mid], continuacion), area):
                lo = mid
            else:
                hi = mid - 1
        minimo = min(3, len(resto))
        if lo == 0:
            if actual:
                # No cupo ni una fila en lo que queda de hoja: se pasa a una
                # hoja nueva en vez de meterla igual (se recortaría).
                paginas.append(actual)
                actual = ""
                continue
            lo = 1  # ni una fila cabe en una hoja vacía: se coloca igual para no atascarse
        if lo < minimo and actual:
            paginas.append(actual)
            actual = ""
            continue
        actual += envolver(resto[:lo], continuacion)
        i += lo
        paginas.append(actual)
        actual = ""
    return actual


def _tabla(titulo: str, columnas: list[tuple[str, str, bool]], intro: str = ""):
    """Devuelve un `envolver` para _paginar_items: h2 + encabezado de tabla
    (repetido con "(continuación)") + las filas `<tr>` ya armadas.
    columnas: (título, ancho, numérica).

    fitz.Story solo respeta el ancho puesto en CADA celda (style en el
    <td>; ni el <th>, ni <col>, ni el atributo width) — por eso aquí se le
    pone a cada celda de primer nivel de las filas (marcadas por _fila)."""
    anchos = _anchos_pt([float(a.rstrip("%")) if a else None for _, a, _ in columnas])
    cab = "".join(
        f'<th{" class=num" if num else ""} {_w(anchos[j])}>{html.escape(t)}</th>'
        for j, (t, _, num) in enumerate(columnas)
    )

    def con_anchos(fila: str) -> str:
        partes = fila.split(_CELDA)
        salida = partes[0]
        for j, resto in enumerate(partes[1:]):
            salida += (f"<td {_w(anchos[j])}" if j < len(anchos) else "<td") + resto
        return salida

    def envolver(filas: list[str], continuacion: bool) -> str:
        filas = [con_anchos(f) for f in filas]
        h2 = f"<h2>{html.escape(titulo)}{' (continuación)' if continuacion else ''}</h2>" if titulo else ""
        if intro and not continuacion:
            h2 += intro
        return f'{h2}<table class="dx-menciones" style="width:100%"><thead><tr>{cab}</tr></thead><tbody>{"".join(filas)}</tbody></table>'

    return envolver


_CELDA = "<td data-celda"  # marca de celda de primer nivel; _tabla la cambia por <td style="width:...">


def _fila(celdas: list[str], i: int, clase: str = "", numericas: set[int] = frozenset()) -> str:
    clases = " ".join(c for c in ["par" if i % 2 else "", clase] if c)
    tds = "".join(f'{_CELDA}{" class=num" if j in numericas else ""}>{c}</td>' for j, c in enumerate(celdas))
    return f'<tr{f" class={chr(34)}{clases}{chr(34)}" if clases else ""}>{tds}</tr>'


def _estado_caso_txt(c: models.Caso) -> str:
    return ESTADOS_CASO_TITULOS.get(c.estado, c.estado)


def _proximo_html(c: models.Caso, hoy: dt.date) -> str:
    if c.estado == "cerrado" or not c.proximo_seguimiento:
        return "—"
    if c.proximo_seguimiento < hoy:
        return f'<span class="vencido">Vencido ({_f(c.proximo_seguimiento)})</span>'
    return _f(c.proximo_seguimiento)


# =============================================================================
# Diagnóstico de un grado (el formulario del Excel, maqueta numerada 1-11)
# =============================================================================


def _tabla_situaciones_html(menciones: list[models.DiagnosticoMencion], continuacion: bool) -> str:
    """Agrupadas por estudiante (consecutivas): el nombre se repite en cada
    fila (más robusto para partir la tabla entre hojas que un rowspan), pero
    una raya marca dónde empieza cada estudiante nuevo."""
    if not menciones:
        return ""
    filas = []
    anterior = None
    w1, w2, w3 = _anchos_pt([22, 16, 62])
    for i, m in enumerate(menciones):
        quien = _quien_mencion(m.estudiante, m.nombre_detectado)
        nuevo = quien != anterior
        anterior = quien
        clases = " ".join(c for c in [("par" if i % 2 else ""), ("nuevo-estudiante" if nuevo else "")] if c)
        filas.append(
            f'<tr{f" class=\"{clases}\"" if clases else ""}>'
            f'<td {_w(w1)}>{quien}</td>'
            f'<td {_w(w2)}>{html.escape(CATEGORIAS_TITULOS.get(m.categoria, m.categoria))}</td>'
            f'<td {_w(w3)}>{html.escape(m.texto)}</td></tr>'
        )
    titulo = "3. SITUACIONES IDENTIFICADAS EN ESTUDIANTES" + (" (continuación)" if continuacion else "")
    return (
        f"<h2>{titulo}</h2>"
        '<table class="dx-menciones" style="width:100%"><thead><tr>'
        f'<th {_w(w1)}>Estudiante</th><th {_w(w2)}>Situación</th><th {_w(w3)}>Detalle</th>'
        f'</tr></thead><tbody>{"".join(filas)}</tbody></table>'
    )


def generar_diagnostico_grado_pdf(db: Session, d: models.DiagnosticoGrado, elaborado_por: str | None = None) -> bytes:
    hoy = fechas.hoy_colombia()
    papeleria = pdf_membrete.Papeleria(CSS_DX)
    _, _, area, _, _ = pdf_membrete.medidas(horizontal=False)

    grado_txt = _grado_nombre(d.grado, d.curso)
    periodo = crud.periodo_de_fecha(d.fecha_diligenciado)
    fecha_txt = pdf_membrete.fecha_larga(d.fecha_diligenciado) if d.fecha_diligenciado else "—"

    portada = f"""
    <h1>DIAGNÓSTICO DE ORIENTACIÓN ESCOLAR</h1>
    <p class="subtitulo">{html.escape(grado_txt)}{f" · {html.escape(periodo)}" if periodo else ""}</p>
    {NOTA_CONFIDENCIAL}
    """ + _ficha([
        ("Grado", _e(grado_txt), "Periodo", _e(periodo)),
        ("Fecha del diagnóstico", fecha_txt, "Sede", _e(d.sede.nombre if d.sede else None)),
        ("Director(a) de grupo", _e(d.director_grado_nombre), "Orientador(a) escolar", _e(d.orientador_escolar_nombre)),
    ])

    casos = crud.listar_casos_grupo(db, d.sede_id, d.grado, d.curso)

    secciones_previas = [
        _seccion(1, "Información general del grupo", "".join([
            _sub("Estudiantes en lista", str(d.n_en_lista) if d.n_en_lista is not None else None),
            _sub("Estudiantes asistiendo", str(d.n_asisten) if d.n_asisten is not None else None),
            _sub("Estudiantes desplazados", d.desplazados_texto),
            _sub("Estudiantes embarazadas", d.embarazadas_texto),
            _sub("Estudiantes víctimas de conflicto armado", d.victimas_conflicto_texto),
        ])),
        _seccion(2, "Asistencia e intermitencia", _sub("Detalle", d.no_asisten_texto)),
    ]

    secciones_posteriores = [
        _seccion(4, "Dificultades académicas", _sub("Detalle", d.dificultades_academicas)),
        _seccion(5, "Dificultades de comportamiento", _sub("Detalle", d.dificultades_comportamiento)),
        _seccion(6, "Acompañamiento familiar", _sub("Detalle", d.acompanamiento_padres)),
        _seccion(7, "Salud", _sub("Detalle", d.problemas_salud)),
        _seccion(8, "Temáticas y estrategias", (
            f'<table class="dx-2col"><tr><td {_w(ANCHO_UTIL / 2 - 10)}>'
            + _sub("Temáticas para trabajar", d.tematicas_trabajar)
            + _sub("Estrategias para solucionar conflictos", d.estrategias_conflicto)
            + f'</td><td {_w(ANCHO_UTIL / 2 - 10)}>'
            + _sub("Estrategias para fortalecer el aprendizaje", d.estrategias_aprendizaje)
            + _sub("Resguardos atendidos", d.resguardos_atendidos)
            + '</td></tr></table>'
        ) if any([d.tematicas_trabajar, d.estrategias_conflicto, d.estrategias_aprendizaje, d.resguardos_atendidos]) else ""),
        _seccion(9, "Recomendaciones", "".join([
            _sub("Recomendaciones de los docentes", d.recomendaciones_docentes),
            _sub("Estudiantes con llamados de atención", d.llamados_atencion),
            _sub("Estudiantes a los que se ha brindado orientación", d.orientacion_brindada),
            _sub("Transporte escolar", d.transporte_escolar),
        ])),
        _seccion(10, "Seguimiento", _seccion_seguimiento_html(d.seguimiento_nota, casos)),
        _seccion(11, "Observaciones generales", _sub("Detalle", d.observaciones_generales)),
    ]

    paginas: list[str] = []
    actual = portada
    for bloque in secciones_previas:
        actual = _agregar(papeleria, area, actual, paginas, bloque)
    if d.menciones:
        actual = _paginar_items(papeleria, area, actual, paginas, list(d.menciones), _tabla_situaciones_html)
    for bloque in secciones_posteriores:
        actual = _agregar(papeleria, area, actual, paginas, bloque)
    actual = _agregar(papeleria, area, actual, paginas, _firmas(
        hoy, elaborado_por, "Diagnóstico diligenciado por el director(a) de grupo e importado del formulario institucional."
    ))
    paginas.append(actual)
    return pdf_membrete.escribir_pdf(papeleria, paginas)


def _seccion_seguimiento_html(seguimiento_nota: str | None, casos: list[models.Caso]) -> str:
    partes = [_sub("Del formulario", seguimiento_nota)]
    if casos:
        for c in casos:
            partes.append(_caso_resumen_html(c))
    elif not seguimiento_nota:
        partes.append('<p class="dx-campo dx-vacio">Sin registros de seguimiento en este diagnóstico.</p>')
    return "".join(partes)


def _caso_resumen_html(c: models.Caso) -> str:
    tipo = TIPOS_CASO_TITULOS.get(c.tipo, c.tipo)
    ultimo = c.seguimientos[0] if c.seguimientos else None
    linea_ultimo = f" · último seguimiento {_f(ultimo.fecha)}" if ultimo else ""
    return (
        f'<p class="dx-caso-cab">{html.escape(c.estudiante.nombre_completo)} — {html.escape(tipo)}</p>'
        f'<p class="dx-caso-meta">Estado: {html.escape(_estado_caso_txt(c))} · abierto {_f(c.fecha_apertura)}'
        f"{linea_ultimo}</p>"
        f'<p class="dx-campo">{html.escape(c.descripcion)}</p>'
    )


# =============================================================================
# Caso: bloque completo (cabecera + datos + seguimientos en tabla)
# =============================================================================


def _caso_cabecera_html(c: models.Caso, hoy: dt.date, con_estudiante: bool = False) -> str:
    tipo = TIPOS_CASO_TITULOS.get(c.tipo, c.tipo)
    titulo = c.titulo or tipo
    if con_estudiante:
        titulo = f"{c.estudiante.nombre_completo} — {titulo}"
    cierre = _f(c.cerrado_en.date()) if c.cerrado_en else "—"
    return (
        f'<table class="caso-cab"><tr><td {_w(_anchos_pt([72, 28], relleno=19)[0])}>{html.escape(titulo)}</td>'
        f'<td class="estado" {_w(_anchos_pt([72, 28], relleno=19)[1])}>{html.escape(_estado_caso_txt(c).upper())}</td></tr></table>'
        + _ficha([
            ("Tipo de caso", _e(tipo), "Fecha de apertura", _f(c.fecha_apertura)),
            ("Próximo seguimiento", _proximo_html(c, hoy), "Fecha de cierre", cierre),
        ])
        + _sub("Situación", c.descripcion)
        + _sub("Acciones realizadas", c.acciones)
        + _sub("Observaciones", c.observaciones)
    )


def _filas_seguimientos(c: models.Caso) -> list[str]:
    filas = []
    for i, s in enumerate(sorted(c.seguimientos, key=lambda s: (s.fecha, s.id))):
        detalle = html.escape(s.situacion)
        if s.accion_realizada:
            detalle += f"<br/><i>Acción:</i> {html.escape(s.accion_realizada)}"
        if s.compromisos:
            detalle += f"<br/><i>Compromisos:</i> {html.escape(s.compromisos)}"
        if s.observaciones:
            detalle += f"<br/><i>Observaciones:</i> {html.escape(s.observaciones)}"
        filas.append(_fila([
            _f(s.fecha), _e(s.tipo_atencion), detalle, _f(s.proxima_fecha), _e(s.autor.nombre if s.autor else None),
        ], i))
    return filas


def _agregar_caso(papeleria, area, actual, paginas, c: models.Caso, hoy: dt.date, con_estudiante=False, prefijo="") -> str:
    """`prefijo` (ej. el título de la sección) va pegado a la cabecera del
    caso para que nunca quede solo al pie de una hoja."""
    actual = _agregar(papeleria, area, actual, paginas, prefijo + _caso_cabecera_html(c, hoy, con_estudiante))
    if not c.seguimientos:
        return _agregar(papeleria, area, actual, paginas,
                        '<p class="dx-campo dx-vacio">Sin seguimientos registrados todavía.</p>')
    envolver = _tabla("", [("Fecha", "12%", False), ("Atención", "16%", False), ("Situación encontrada y acciones", "46%", False),
                           ("Próxima", "11%", False), ("Registró", "15%", False)])
    return _paginar_items(papeleria, area, actual, paginas, _filas_seguimientos(c), envolver)


# =============================================================================
# Informe de un estudiante
# =============================================================================


def generar_diagnostico_estudiante_pdf(
    db: Session,
    estudiante: models.Estudiante,
    menciones: list[models.DiagnosticoMencion],
    casos: list[models.Caso] | None = None,
    elaborado_por: str | None = None,
) -> bytes:
    hoy = fechas.hoy_colombia()
    casos = casos or []
    papeleria = pdf_membrete.Papeleria(CSS_DX)
    _, _, area, _, _ = pdf_membrete.medidas(horizontal=False)

    diag_grupo = (
        crud.diagnostico_vigente_de_grupo(db, estudiante.sede_id, estudiante.grado, estudiante.curso)
        if estudiante.sede_id else None
    )
    edad = _edad(estudiante.fecha_nacimiento, hoy)
    nacimiento = _f(estudiante.fecha_nacimiento) + (f" ({edad} años)" if edad is not None else "")
    documento = f"{estudiante.tipo_documento or ''} {estudiante.documento}".strip()
    activos = [c for c in casos if c.estado != "cerrado"]

    portada = (
        f'<h1>INFORME DE ORIENTACIÓN ESCOLAR</h1><p class="subtitulo">{html.escape(estudiante.nombre_completo)}</p>'
        + NOTA_CONFIDENCIAL
        + "<h2>1. DATOS DEL ESTUDIANTE</h2>"
        + _ficha([
            ("Estudiante", _e(estudiante.nombre_completo), "Documento", _e(documento)),
            ("Fecha de nacimiento", nacimiento, "Género", {"F": "Femenino", "M": "Masculino"}.get(estudiante.genero or "", "—")),
            ("Grado / grupo", _e(estudiante.grupo), "Sede", _e(estudiante.sede.nombre if estudiante.sede else None)),
            ("Director(a) de grupo", _e(diag_grupo.director_grado_nombre if diag_grupo else None),
             "Estado en matrícula", _e(estudiante.estado.capitalize())),
        ])
        + "<h2>2. RESUMEN</h2>"
        + _kpis([
            (len(activos), "Casos activos"),
            (len(casos) - len(activos), "Casos cerrados"),
            (sum(len(c.seguimientos) for c in casos), "Seguimientos registrados"),
            (len(menciones), "Situaciones en el diagnóstico"),
        ])
    )

    paginas: list[str] = []
    actual = portada
    titulo = "<h2>3. CASOS DE ORIENTACIÓN</h2>"
    if casos:
        for i, c in enumerate(sorted(casos, key=lambda c: (c.estado == "cerrado", c.fecha_apertura))):
            actual = _agregar_caso(papeleria, area, actual, paginas, c, hoy, prefijo=titulo if i == 0 else "")
    else:
        actual = _agregar(papeleria, area, actual, paginas,
                          titulo + '<p class="dx-campo dx-vacio">No hay casos de orientación registrados para este estudiante.</p>')

    if menciones:
        filas = []
        for i, m in enumerate(menciones):
            d = m.diagnostico
            origen = _grado_nombre(d.grado, d.curso) + (f" · {crud.periodo_de_fecha(d.fecha_diligenciado)}" if d.fecha_diligenciado else "")
            filas.append(_fila([html.escape(origen), html.escape(CATEGORIAS_TITULOS.get(m.categoria, m.categoria)), html.escape(m.texto)], i))
        actual = _paginar_items(papeleria, area, actual, paginas, filas, _tabla(
            "4. SITUACIONES REGISTRADAS EN EL DIAGNÓSTICO DEL GRUPO",
            [("Diagnóstico", "22%", False), ("Situación", "18%", False), ("Detalle (tal como lo escribió el director de grupo)", "60%", False)],
        ))
    else:
        actual = _agregar(papeleria, area, actual, paginas,
                          "<h2>4. SITUACIONES REGISTRADAS EN EL DIAGNÓSTICO DEL GRUPO</h2>"
                          '<p class="dx-campo dx-vacio">El diagnóstico del director(a) de grupo no registra situaciones de este estudiante.</p>')

    actual = _agregar(papeleria, area, actual, paginas, _firmas(hoy, elaborado_por))
    paginas.append(actual)
    return pdf_membrete.escribir_pdf(papeleria, paginas)


# =============================================================================
# Informe del GRUPO (resumen de orientación de un grupo de matrícula)
# =============================================================================


def generar_informe_grupo_pdf(
    db: Session, sede_id: int, grado: int, curso: int | None, elaborado_por: str | None = None
) -> bytes | None:
    detalle = crud.detalle_grupo_orientacion(db, sede_id, grado, curso)
    if detalle is None:
        return None
    hoy = fechas.hoy_colombia()
    papeleria = pdf_membrete.Papeleria(CSS_DX)
    _, _, area, _, _ = pdf_membrete.medidas(horizontal=False)
    diag = crud.diagnostico_vigente_de_grupo(db, sede_id, grado, curso)
    casos = [db.get(models.Caso, c.id) for c in detalle.casos]
    activos = [c for c in casos if c.estado != "cerrado"]
    vencidos = [c for c in activos if c.proximo_seguimiento and c.proximo_seguimiento < hoy]

    portada = (
        f'<h1>INFORME DE ORIENTACIÓN DEL GRUPO</h1><p class="subtitulo">{html.escape(detalle.grado_nombre)}'
        f'{f" · Diagnóstico de {html.escape(detalle.periodo)}" if detalle.periodo else ""}</p>'
        + NOTA_CONFIDENCIAL
        + _ficha([
            ("Grupo", _e(detalle.grado_nombre), "Sede", _e(detalle.sede_nombre)),
            ("Director(a) de grupo", _e(detalle.director_grado_nombre), "Estudiantes activos", str(detalle.n_estudiantes)),
            ("Diagnóstico del grupo", _e(pdf_membrete.fecha_larga(diag.fecha_diligenciado) if diag and diag.fecha_diligenciado
                                         else ("Sin fecha" if diag else "Sin diagnóstico importado")),
             "Corte del informe", pdf_membrete.fecha_larga(hoy)),
        ])
        + "<h2>1. RESUMEN</h2>"
        + _kpis([
            (detalle.n_estudiantes, "Estudiantes activos"),
            (detalle.estudiantes_mencionados, "Mencionados en el diagnóstico"),
            (len(activos), "Casos activos"),
            (len(casos) - len(activos), "Casos cerrados"),
            (len(vencidos), "Seguimientos vencidos", bool(vencidos)),
        ])
    )
    paginas: list[str] = []
    actual = portada

    # --- 2. Lo que se trabaja con el grupo (general, del director) ---
    if diag:
        filas_gen = [
            _fila([f"<b>{html.escape(t)}</b>", html.escape((getattr(diag, c) or "").strip())
                   or '<span class="dx-vacio">Sin respuesta del director de grupo</span>'], i)
            for i, (t, c) in enumerate(GENERALES)
        ]
        actual = _paginar_items(papeleria, area, actual, paginas, filas_gen, _tabla(
            "2. LO QUE SE TRABAJA CON EL GRUPO", [("Punto del diagnóstico", "30%", False), ("Lo que reporta el director de grupo", "70%", False)],
        ))
    else:
        actual = _agregar(papeleria, area, actual, paginas, "<h2>2. LO QUE SE TRABAJA CON EL GRUPO</h2>"
                          '<p class="dx-campo dx-vacio">Este grupo no tiene diagnóstico importado.</p>')

    # --- 3. Situaciones por categoría ---
    if diag and diag.menciones:
        por_cat: dict[str, dict] = {}
        for m in diag.menciones:
            c = por_cat.setdefault(m.categoria, {"situaciones": 0, "personas": set()})
            c["situaciones"] += 1
            c["personas"].add(crud.clave_persona_mencion(m))
        maximo = max(len(v["personas"]) for v in por_cat.values())
        filas = [
            _fila([html.escape(CATEGORIAS_TITULOS.get(cat, cat)), str(len(v["personas"])), str(v["situaciones"]),
                   _barra(len(v["personas"]), maximo, ANCHO_BARRA)], i, numericas={1, 2})
            for i, (cat, v) in enumerate(sorted(por_cat.items(), key=lambda kv: -len(kv[1]["personas"])))
        ]
        actual = _paginar_items(papeleria, area, actual, paginas, filas, _tabla(
            "3. SITUACIONES REGISTRADAS EN EL DIAGNÓSTICO",
            [("Situación", "34%", False), ("Estudiantes", "13%", True), ("Registros", "12%", True), ("", "41%", False)],
        ))
    else:
        actual = _agregar(papeleria, area, actual, paginas,
                          "<h2>3. SITUACIONES REGISTRADAS EN EL DIAGNÓSTICO</h2>"
                          '<p class="dx-campo dx-vacio">Este grupo no tiene diagnóstico importado o el diagnóstico no nombra estudiantes.</p>')

    # --- 3. Estudiantes con novedades ---
    casos_por_est: dict[int, list[models.Caso]] = {}
    for c in casos:
        casos_por_est.setdefault(c.estudiante_id, []).append(c)
    renglones: list[tuple[str, str, str, str]] = []  # (nombre, situaciones, orientación, próximo)
    for e in detalle.estudiantes:
        if not e.total_situaciones and not e.casos_total:
            continue
        suyos = casos_por_est.get(e.id, [])
        orientacion = "<br/>".join(
            f"{html.escape(TIPOS_CASO_TITULOS.get(c.tipo, c.tipo))} ({html.escape(_estado_caso_txt(c).lower())})" for c in suyos
        ) or "—"
        proximos = [c for c in suyos if c.estado != "cerrado" and c.proximo_seguimiento]
        proximo = _proximo_html(min(proximos, key=lambda c: c.proximo_seguimiento), hoy) if proximos else "—"
        nombre = html.escape(e.nombre_completo) + ("" if e.en_matricula_del_grupo else f"<br/><i>Hoy: {html.escape(e.grupo)}</i>")
        situaciones = ", ".join(CATEGORIAS_TITULOS.get(s, s) for s in e.situaciones) or "—"
        renglones.append((nombre, html.escape(situaciones), orientacion, proximo))
    # Nombres del Excel que no corresponden a un estudiante identificado: se
    # imprimen tal cual quedaron escritos (nunca se inventa a quién son).
    if diag:
        sin_estudiante: dict[str, set[str]] = {}
        for m in diag.menciones:
            if m.estudiante_id is None:
                sin_estudiante.setdefault((m.nombre_detectado or "—").strip(), set()).add(m.categoria)
        for nombre, cats in sin_estudiante.items():
            renglones.append((html.escape(nombre), html.escape(", ".join(CATEGORIAS_TITULOS.get(c, c) for c in sorted(cats))), "—", "—"))
    renglones.sort(key=lambda r: r[0].lower())
    if renglones:
        filas = [_fila([str(i + 1), *r], i, numericas={0}) for i, r in enumerate(renglones)]
        actual = _paginar_items(papeleria, area, actual, paginas, filas, _tabla(
            "4. ESTUDIANTES CON NOVEDADES",
            [("#", "5%", True), ("Estudiante", "30%", False), ("Situaciones en el diagnóstico", "28%", False),
             ("Orientación", "22%", False), ("Próximo seguimiento", "15%", False)],
        ))
    sin_novedad = sum(1 for e in detalle.estudiantes if e.en_matricula_del_grupo and not e.total_situaciones and not e.casos_total)
    actual = _agregar(papeleria, area, actual, paginas,
                      ("" if renglones else "<h2>4. ESTUDIANTES CON NOVEDADES</h2>")
                      + f'<p class="fuente">{sin_novedad} estudiante(s) activo(s) del grupo no tienen situaciones en el diagnóstico ni casos de orientación.</p>')

    # --- 4. Casos del grupo ---
    titulo = "<h2>5. CASOS DE ORIENTACIÓN DEL GRUPO</h2>"
    if casos:
        for i, c in enumerate(sorted(casos, key=lambda c: (c.estado == "cerrado", c.estudiante.nombre_completo))):
            actual = _agregar_caso(papeleria, area, actual, paginas, c, hoy, con_estudiante=True, prefijo=titulo if i == 0 else "")
    else:
        actual = _agregar(papeleria, area, actual, paginas,
                          titulo + '<p class="dx-campo dx-vacio">No hay casos de orientación registrados en este grupo.</p>')

    actual = _agregar(papeleria, area, actual, paginas, _firmas(hoy, elaborado_por))
    paginas.append(actual)
    return pdf_membrete.escribir_pdf(papeleria, paginas)


# =============================================================================
# Informe GENERAL de la sede (toda la IETABA)
# =============================================================================


def generar_informe_institucional_pdf(db: Session, sede_id: int, elaborado_por: str | None = None) -> bytes | None:
    sede = db.get(models.Sede, sede_id)
    if sede is None:
        return None
    hoy = fechas.hoy_colombia()
    papeleria = pdf_membrete.Papeleria(CSS_DX)
    _, _, area, _, _ = pdf_membrete.medidas(horizontal=False)

    grupos = crud.listar_grupos_orientacion(db, sede_id)
    situaciones = crud.situaciones_por_grupo(db, sede_id)
    casos = list(db.scalars(select(models.Caso).where(models.Caso.sede_id == sede_id)))
    activos = [c for c in casos if c.estado != "cerrado"]
    vencidos = [c for c in activos if c.proximo_seguimiento and c.proximo_seguimiento < hoy]
    total_est = sum(g.n_estudiantes for g in grupos)
    con_diag = sum(1 for g in grupos if g.diagnostico_id)
    mencionados = sum(g.estudiantes_mencionados for g in grupos)

    portada = (
        f'<h1>INFORME GENERAL DE ORIENTACIÓN ESCOLAR</h1><p class="subtitulo">{html.escape(sede.nombre)} · corte al {pdf_membrete.fecha_larga(hoy)}</p>'
        + NOTA_CONFIDENCIAL
        + _ficha([
            ("Sede", _e(sede.nombre), "Corte del informe", pdf_membrete.fecha_larga(hoy)),
            ("Grupos", f"{len(grupos)} ({con_diag} con diagnóstico)", "Estudiantes activos", str(total_est)),
        ])
        + '<p class="fuente"><b>Fuentes:</b> las situaciones salen del diagnóstico vigente que diligenció cada director(a) de grupo '
          "(formulario institucional de diagnóstico de orientación); los casos y seguimientos son los que orientación registró "
          "en el sistema. Todas las cifras son conteos directos.</p>"
        + "<h2>1. RESUMEN GENERAL</h2>"
        + _kpis([
            (total_est, "Estudiantes activos"),
            (f"{con_diag}/{len(grupos)}", "Grupos con diagnóstico"),
            (mencionados, "Mencionados en diagnósticos"),
            (len(activos), "Casos activos"),
            (len(casos) - len(activos), "Casos cerrados"),
            (len(vencidos), "Seguimientos vencidos", bool(vencidos)),
        ])
    )
    paginas: list[str] = []
    actual = portada

    # --- 2. Situaciones por categoría (toda la sede) ---
    por_cat: dict[str, dict] = {}
    for cats in situaciones.values():
        for cat, v in cats.items():
            t = por_cat.setdefault(cat, {"situaciones": 0, "personas": 0})
            t["situaciones"] += v["situaciones"]
            t["personas"] += len(v["personas"])  # personas distintas dentro de cada grupo
    if por_cat:
        maximo = max(v["personas"] for v in por_cat.values())
        filas = [
            _fila([html.escape(CATEGORIAS_TITULOS.get(cat, cat)), str(v["personas"]), str(v["situaciones"]),
                   _barra(v["personas"], maximo, ANCHO_BARRA)], i, numericas={1, 2})
            for i, (cat, v) in enumerate(sorted(por_cat.items(), key=lambda kv: -kv[1]["personas"]))
        ]
        actual = _paginar_items(papeleria, area, actual, paginas, filas, _tabla(
            "2. SITUACIONES REGISTRADAS EN LOS DIAGNÓSTICOS",
            [("Situación", "34%", False), ("Estudiantes", "13%", True), ("Registros", "12%", True), ("", "41%", False)],
        ))

    # --- 3. Por nivel ---
    filas_nivel = []
    for i, (nombre, cumple) in enumerate(NIVELES):
        gs = [g for g in grupos if cumple(g.grado)]
        if not gs:
            continue
        filas_nivel.append(_fila([
            html.escape(nombre), str(len(gs)), str(sum(g.n_estudiantes for g in gs)),
            str(sum(g.estudiantes_mencionados for g in gs)),
            str(sum(g.casos_abiertos + g.casos_en_seguimiento for g in gs)), str(sum(g.seguimientos_vencidos for g in gs)),
        ], len(filas_nivel), numericas={1, 2, 3, 4, 5}))
    filas_nivel.append(_fila([
        "TOTAL", str(len(grupos)), str(total_est), str(mencionados), str(len(activos)), str(len(vencidos)),
    ], 0, clase="total", numericas={1, 2, 3, 4, 5}))
    actual = _paginar_items(papeleria, area, actual, paginas, filas_nivel, _tabla(
        "3. RESUMEN POR NIVEL",
        [("Nivel", "30%", False), ("Grupos", "12%", True), ("Estudiantes", "14%", True),
         ("Mencionados", "15%", True), ("Casos activos", "15%", True), ("Vencidos", "14%", True)],
    ))

    # --- 4. Por grupo ---
    filas_grupo = []
    for i, g in enumerate(grupos):
        cats = situaciones.get((g.grado, g.curso), {})
        temas = []
        for _, categorias in TEMAS_INFORME_GENERAL:
            personas = set().union(*(cats[c]["personas"] for c in categorias if c in cats)) if cats else set()
            temas.append(str(len(personas)) if personas else "·")
        activos_g = g.casos_abiertos + g.casos_en_seguimiento
        filas_grupo.append(_fila([
            html.escape(g.grado_nombre), str(g.n_estudiantes), html.escape(g.periodo or ("s/f" if g.diagnostico_id else "No")),
            str(g.estudiantes_mencionados) if g.diagnostico_id else "·", *temas,
            str(activos_g) if activos_g else "·",
            f'<span class="vencido">{g.seguimientos_vencidos}</span>' if g.seguimientos_vencidos else "·",
        ], i, numericas={1, 3, 4, 5, 6, 7, 8, 9, 10}))
    intro_grupos = ('<p class="fuente">Columnas de situaciones: número de estudiantes distintos del grupo con al menos una situación de ese tema '
                      "en el diagnóstico (Asistencia = no asiste o intermitencia; Comport. = comportamiento o llamados de atención; "
                      "Riesgo = desplazamiento o víctima del conflicto armado; Salud = salud o embarazo). "
                    "«·» = ninguno.</p>")
    actual = _paginar_items(papeleria, area, actual, paginas, filas_grupo, _tabla(
        "4. RESUMEN POR GRUPO",
        [("Grupo", "17%", False), ("Est.", "6%", True), ("Diagnóstico", "12%", False), ("Menc.", "7%", True),
         *[(t, "8%", True) for t, _ in TEMAS_INFORME_GENERAL], ("Casos", "7%", True), ("Venc.", "7%", True)],
        intro=intro_grupos,
    ))

    # --- 5. Casos por tipo ---
    if casos:
        por_tipo: dict[str, dict[str, int]] = {}
        for c in casos:
            t = por_tipo.setdefault(c.tipo, {"abierto": 0, "en_seguimiento": 0, "cerrado": 0})
            t[c.estado] = t.get(c.estado, 0) + 1
        filas_tipo = [
            _fila([html.escape(TIPOS_CASO_TITULOS.get(tipo, tipo)), str(v["abierto"]), str(v["en_seguimiento"]),
                   str(v["cerrado"]), str(sum(v.values()))], i, numericas={1, 2, 3, 4})
            for i, (tipo, v) in enumerate(sorted(por_tipo.items(), key=lambda kv: -sum(kv[1].values())))
        ]
        filas_tipo.append(_fila([
            "TOTAL", str(sum(1 for c in casos if c.estado == "abierto")), str(sum(1 for c in casos if c.estado == "en_seguimiento")),
            str(sum(1 for c in casos if c.estado == "cerrado")), str(len(casos)),
        ], 0, clase="total", numericas={1, 2, 3, 4}))
        actual = _paginar_items(papeleria, area, actual, paginas, filas_tipo, _tabla(
            "5. CASOS DE ORIENTACIÓN POR TIPO",
            [("Tipo de caso", "36%", False), ("Abiertos", "16%", True), ("En seguimiento", "16%", True),
             ("Cerrados", "16%", True), ("Total", "16%", True)],
        ))
    else:
        actual = _agregar(papeleria, area, actual, paginas, "<h2>5. CASOS DE ORIENTACIÓN POR TIPO</h2>"
                          '<p class="dx-campo dx-vacio">Todavía no hay casos de orientación registrados en esta sede.</p>')

    # --- 6. Casos activos (vencidos primero) ---
    if activos:
        orden = sorted(activos, key=lambda c: (c.proximo_seguimiento is None, c.proximo_seguimiento or hoy, c.estudiante.nombre_completo))
        filas_act = [
            _fila([
                html.escape(c.estudiante.nombre_completo), html.escape(_grado_nombre(c.grado, c.curso)),
                html.escape(c.titulo or TIPOS_CASO_TITULOS.get(c.tipo, c.tipo)), _f(c.fecha_apertura),
                html.escape(_estado_caso_txt(c)), str(len(c.seguimientos)), _proximo_html(c, hoy),
            ], i, numericas={5})
            for i, c in enumerate(orden)
        ]
        actual = _paginar_items(papeleria, area, actual, paginas, filas_act, _tabla(
            "6. CASOS ACTIVOS",
            [("Estudiante", "24%", False), ("Grupo", "13%", False), ("Tipo / motivo", "20%", False), ("Apertura", "10%", False),
             ("Estado", "11%", False), ("Seg.", "5%", True), ("Próximo seguimiento", "17%", False)],
        ))

    # --- 7. Lo que se trabaja en cada grupo (general, del director) ---
    generales = crud.generales_por_grupo(db, sede_id)
    if generales:
        vacio = '<span class="dx-vacio">Sin respuesta</span>'
        filas_gen = [
            _fila([
                f"<b>{html.escape(g.grado_nombre)}</b>",
                html.escape(g.tematicas_trabajar or "") or vacio,
                html.escape(g.estrategias_conflicto or "") or vacio,
                html.escape(g.estrategias_aprendizaje or "") or vacio,
                html.escape(g.resguardos_atendidos or "") or vacio,
            ], i)
            for i, g in enumerate(generales)
        ]
        respondieron = sum(1 for g in generales if (g.tematicas_trabajar or "").strip())
        actual = _paginar_items(papeleria, area, actual, paginas, filas_gen, _tabla(
            "7. TEMÁTICAS Y ESTRATEGIAS POR GRUPO",
            [("Grupo", "11%", False), ("Temáticas para trabajar", "24%", False), ("Estrategias para conflictos", "24%", False),
             ("Estrategias de aprendizaje", "24%", False), ("Resguardos", "17%", False)],
            intro=f'<p class="fuente">Lo general que reporta el director de cada grupo en el diagnóstico. {respondieron} de {len(generales)} grupos reportaron temáticas para trabajar.</p>',
        ))

    actual = _agregar(papeleria, area, actual, paginas, _firmas(hoy, elaborado_por))
    paginas.append(actual)
    return pdf_membrete.escribir_pdf(papeleria, paginas)


# =============================================================================
# Informe de un caso puntual
# =============================================================================


def generar_informe_caso_pdf(db: Session, c: models.Caso, elaborado_por: str | None = None) -> bytes:
    hoy = fechas.hoy_colombia()
    papeleria = pdf_membrete.Papeleria(CSS_DX)
    _, _, area, _, _ = pdf_membrete.medidas(horizontal=False)
    tipo = TIPOS_CASO_TITULOS.get(c.tipo, c.tipo)
    e = c.estudiante
    documento = f"{e.tipo_documento or ''} {e.documento}".strip()

    portada = (
        f'<h1>INFORME DE SEGUIMIENTO DE ORIENTACIÓN</h1>'
        f'<p class="subtitulo">{html.escape(e.nombre_completo)} · {html.escape(c.titulo or tipo)}</p>'
        + NOTA_CONFIDENCIAL
        + _ficha([
            ("Estudiante", _e(e.nombre_completo), "Documento", _e(documento)),
            ("Grado / grupo", _e(_grado_nombre(c.grado, c.curso)), "Sede", _e(c.sede.nombre if c.sede else None)),
        ])
        + "<h2>CASO</h2>"
    )
    paginas: list[str] = []
    actual = portada
    actual = _agregar(papeleria, area, actual, paginas, _caso_cabecera_html(c, hoy))
    if c.seguimientos:
        envolver = _tabla(f"SEGUIMIENTOS ({len(c.seguimientos)})",
                          [("Fecha", "12%", False), ("Atención", "16%", False), ("Situación encontrada y acciones", "46%", False),
                           ("Próxima", "11%", False), ("Registró", "15%", False)])
        actual = _paginar_items(papeleria, area, actual, paginas, _filas_seguimientos(c), envolver)
    else:
        actual = _agregar(papeleria, area, actual, paginas,
                          '<h2>SEGUIMIENTOS</h2><p class="dx-campo dx-vacio">Sin seguimientos registrados todavía.</p>')
    actual = _agregar(papeleria, area, actual, paginas, _firmas(hoy, elaborado_por))
    paginas.append(actual)
    return pdf_membrete.escribir_pdf(papeleria, paginas)
