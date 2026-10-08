"""Lista de estudiantes en PDF (Reportes → Lista de estudiantes).

El frontend ya decidió QUÉ estudiantes van y en qué orden (desde Preescolar
hasta N cupos, sin posibles retiros, etc.); aquí se reciben esos ids, las
columnas elegidas y el criterio usado, y se arma un informe formal en hoja
carta VERTICAL:

  * membrete y pie de página iguales a los de la constancia oficial
    (plantillas/constancia_estudio.docx: mismo logo, textos y lema),
    repetidos en cada hoja;
  * explicación de qué es el listado, cuadro de datos (sede, año, fecha,
    total) y resumen por grado (hombres / mujeres / total);
  * detalle agrupado por grado y grupo, con el encabezado de la tabla
    repetido cuando un grupo continúa en la hoja siguiente;
  * firmas al final y "Página X de Y".
"""

import datetime as dt
import html
import io
import zipfile
from pathlib import Path

import fitz  # PyMuPDF
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import fechas, models
from .certificados import MESES_TEXTO, PLANTILLA
from .reporte_horario import LOGOS, MEMBRETE_LINEAS

FUENTES_WINDOWS = Path("C:/Windows/Fonts")
LOGO_MEMBRETE = "logo_membrete.jpeg"

PIE_LEMA = "Por la pervivencia e identidad del Pueblo Awá"
PIE_LINEAS = [
    "Unidad administrativa – Predio el Verde, resguardo el Gran Sábalo – El Diviso - Barbacoas Nariño",
    "E-mail: ietabaawa@yahoo.es",
]


def _edad(nacimiento: dt.date | None, hoy: dt.date) -> str:
    if not nacimiento:
        return ""
    años = hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))
    return str(años)


def _nombre_apellidos(e: models.Estudiante) -> str:
    partes = [e.primer_apellido, e.segundo_apellido, e.primer_nombre, e.segundo_nombre]
    return " ".join(p for p in partes if p)


# clave → (encabezado, cómo sacar el valor, ancho relativo)
COLUMNAS = {
    "nombre": ("Apellidos y nombres", lambda e, hoy: _nombre_apellidos(e), 5),
    "tipo_documento": ("Tipo doc.", lambda e, hoy: e.tipo_documento or "", 1.3),
    "documento": ("Documento", lambda e, hoy: e.documento, 2),
    "lugar_expedicion": ("Lugar de expedición", lambda e, hoy: e.lugar_expedicion_documento or "", 2.6),
    "fecha_nacimiento": (
        "Fecha de nacimiento",
        lambda e, hoy: e.fecha_nacimiento.strftime("%d/%m/%Y") if e.fecha_nacimiento else "",
        1.9,
    ),
    "edad": ("Edad", lambda e, hoy: _edad(e.fecha_nacimiento, hoy), 0.9),
    "genero": ("Género", lambda e, hoy: e.genero or "", 1),
    "grupo": ("Grado / Grupo", lambda e, hoy: e.grupo, 2.4),
    "sede": ("Sede", lambda e, hoy: e.sede.nombre if e.sede else "", 3.4),
    "estado": ("Estado", lambda e, hoy: e.estado or "", 1.5),
    "marca": (
        "Marca",
        lambda e, hoy: "Retirado" if e.retirado else ("Posible retiro" if e.posible_retirado else ""),
        1.8,
    ),
    "resguardo": ("Resguardo", lambda e, hoy: "Sí" if e.resguardo else "No", 1.6),
    "observaciones": ("Observaciones", lambda e, hoy: e.observaciones or "", 3.5),
    "firma": ("Firma", lambda e, hoy: "", 3),
}

AZUL = "#1f3a5f"


def _css(tam_tabla: float, hay_magneto: bool) -> str:
    fuente_lema = "magneto" if hay_magneto else "serif"
    return f"""
@font-face {{ font-family: magneto; src: url(MAGNETOB.TTF); }}
* {{ font-family: sans-serif; }}
body {{ font-size: 9.5pt; color: #111; }}
.m-tabla {{ width: 100%; border-collapse: collapse; }}
.m-tabla td {{ vertical-align: middle; }}
.m-texto {{ text-align: center; font-weight: bold; font-size: 7.6pt; margin: 0; line-height: 1.25; }}
.m-lema {{ text-align: center; font-family: {fuente_lema}; font-weight: bold; font-style: {'normal' if hay_magneto else 'italic'}; font-size: 10pt; margin: 1px 0 0 0; }}
.pie-linea {{ border-top: 1.2px solid #111; margin: 0; }}
.pie-lema {{ text-align: center; font-family: {fuente_lema}; font-style: {'normal' if hay_magneto else 'italic'}; font-size: 8pt; margin: 2px 0 0 0; }}
.pie-texto {{ text-align: center; font-size: 7pt; margin: 0; color: #333; }}
h1 {{ text-align: center; font-size: 13pt; color: {AZUL}; margin: 4px 0 0 0; letter-spacing: 0.5px; }}
.subtitulo {{ text-align: center; font-size: 9pt; color: #444; margin: 1px 0 10px 0; }}
.explicacion {{ text-align: justify; font-size: 9.5pt; line-height: 1.4; margin: 0 0 8px 0; }}
table.datos {{ width: 100%; border-collapse: collapse; margin: 0 0 10px 0; }}
table.datos td {{ border: 0.6px solid #9aa7b8; padding: 3px 6px; font-size: 8.8pt; }}
table.datos td.et {{ background-color: #eef2f7; font-weight: bold; color: {AZUL}; }}
h2 {{ font-size: 10.5pt; color: {AZUL}; margin: 8px 0 4px 0; border-bottom: 1px solid {AZUL}; }}
table.resumen {{ width: 70%; border-collapse: collapse; margin: 0 0 8px 0; }}
table.resumen th {{ background-color: {AZUL}; color: #fff; font-size: 8.5pt; padding: 3px 5px; border: 0.6px solid {AZUL}; }}
table.resumen td {{ font-size: 8.5pt; padding: 2px 5px; border: 0.6px solid #9aa7b8; text-align: center; }}
table.resumen td.izq {{ text-align: left; }}
table.resumen tr.total td {{ font-weight: bold; background-color: #eef2f7; }}
.grupo {{ font-size: 9.5pt; font-weight: bold; color: {AZUL}; margin: 9px 0 3px 0; }}
.grupo span {{ font-weight: normal; color: #555; font-size: 8.5pt; }}
table.lista {{ width: 100%; border-collapse: collapse; }}
table.lista th {{ background-color: {AZUL}; color: #fff; font-size: {tam_tabla}pt; padding: 3px 4px; border: 0.6px solid {AZUL}; text-align: left; }}
table.lista td {{ font-size: {tam_tabla}pt; padding: 2px 4px; border: 0.6px solid #9aa7b8; }}
table.lista tr.par td {{ background-color: #f5f7fa; }}
td.num {{ text-align: right; color: #444; }}
.nota {{ font-size: 8pt; color: #555; margin: 10px 0 0 0; }}
table.firmas {{ width: 100%; margin-top: 46px; }}
table.firmas td {{ text-align: center; font-size: 9pt; }}
"""


def _fecha_larga(d: dt.date) -> str:
    return f"{d.day} de {MESES_TEXTO[d.month]} de {d.year}"


def _explicacion(
    vista: str,
    n: int,
    sede: str,
    desde: str,
    hasta: str,
    hasta_grado_nombre: str,
    cantidad: int | None,
    completo: bool,
    hoy: dt.date,
    sin_grupo: int = 0,
    grupos_txt: str = "",
    incluye_posibles: bool = False,
    incluye_retirados: bool = False,
) -> str:
    fuente = (
        "La información se toma de la base de datos de matrícula del sistema institucional de la "
        f"IETABA, con corte al {_fecha_larga(hoy)}."
    )
    if vista == "posibles":
        return (
            f"El presente documento relaciona los <b>{n}</b> estudiantes de <b>{sede}</b> que se "
            "encuentran marcados en el sistema como <b>posible retiro</b>; es decir, estudiantes que "
            "siguen matriculados pero cuya continuidad está pendiente de validación. " + fuente
        )
    if vista == "retirados":
        return (
            f"El presente documento relaciona los <b>{n}</b> estudiantes de <b>{sede}</b> que se "
            "encuentran marcados en el sistema como <b>retirados</b>. " + fuente
        )
    alcance = (
        f"correspondientes a los grupos <b>{grupos_txt}</b>"
        if grupos_txt
        else f"organizados por grado y grupo, tomados en orden desde <b>{desde}</b> hasta <b>{hasta_grado_nombre}</b>"
    )
    cupo = ""
    if cantidad and not completo:
        cupo = f" El listado corresponde a un cupo de <b>{cantidad}</b> estudiantes, que alcanza hasta el grupo <b>{hasta}</b>."

    incluidos = []
    if incluye_posibles:
        incluidos.append("marcados como posible retiro")
    if incluye_retirados:
        incluidos.append("como retirados" if incluidos else "marcados como retirados")
    excluidos = []
    if not incluye_posibles:
        excluidos.append("marcados como posible retiro")
    if not incluye_retirados:
        excluidos.append("como retirados" if excluidos else "marcados como retirados")
    if sin_grupo:
        excluidos.append(
            f"{sin_grupo} que aún no tiene{'' if sin_grupo == 1 else 'n'} grupo asignado"
        )
    criterios = ""
    if incluidos:
        criterios += f" Se incluyen los estudiantes {' y '.join(incluidos)}."
    if excluidos:
        criterios += f" No se incluyen los estudiantes {' ni '.join(excluidos)}."

    return (
        f"El presente documento relaciona <b>{n}</b> estudiantes con matrícula activa en <b>{sede}</b>, "
        f"{alcance}.{cupo}{criterios} " + fuente
    )


def generar_lista_pdf(
    db: Session,
    ids: list[int],
    columnas: list[str],
    vista: str = "activos",
    sede_nombre: str = "",
    desde_grado: int = 0,
    hasta_grado: int = 11,
    grupos_txt: str = "",
    incluye_posibles: bool = False,
    incluye_retirados: bool = False,
    cantidad: int | None = None,
    completo: bool = False,
    sin_grupo_excluidos: int = 0,
) -> bytes:
    columnas = [c for c in dict.fromkeys(columnas) if c in COLUMNAS]
    if not columnas:
        raise ValueError("Escoge al menos una columna para el PDF.")
    if not ids:
        raise ValueError("La lista no tiene estudiantes.")

    por_id = {
        e.id: e
        for e in db.scalars(
            select(models.Estudiante)
            .where(models.Estudiante.id.in_(ids))
            .options(selectinload(models.Estudiante.sede))
        ).all()
    }
    estudiantes = [por_id[i] for i in ids if i in por_id]
    if not estudiantes:
        raise ValueError("La lista no tiene estudiantes.")
    hoy = fechas.hoy_colombia()
    varias_sedes = len({e.sede_id for e in estudiantes}) > 1

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

    peso_total = 0.7 + sum(COLUMNAS[c][2] for c in columnas)
    tam_tabla = 8.2 if peso_total <= 13 else 7.2 if peso_total <= 19 else 6.3
    css = _css(tam_tabla, hay_magneto)
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

    # --- Portada del informe: título, explicación, datos, resumen -----------
    nombre_desde = models.GRADOS_NOMBRES.get(desde_grado, str(desde_grado))
    hasta = estudiantes[-1].grupo
    titulo = {
        "posibles": "LISTADO DE ESTUDIANTES MARCADOS COMO POSIBLE RETIRO",
        "retirados": "LISTADO DE ESTUDIANTES MARCADOS COMO RETIRADOS",
    }.get(vista, "LISTADO DE ESTUDIANTES MATRICULADOS")
    nombre_hasta = models.GRADOS_NOMBRES.get(hasta_grado, str(hasta_grado))
    if vista != "activos":
        subtitulo = "Seguimiento de matrícula"
    elif grupos_txt:
        subtitulo = f"Grupos: {grupos_txt}"
    else:
        subtitulo = f"De {nombre_desde} a {nombre_hasta}"

    sede_txt = sede_nombre or (estudiantes[0].sede.nombre if estudiantes[0].sede else "")

    resumen: dict[int, dict] = {}
    for e in estudiantes:
        r = resumen.setdefault(e.grado, {"grupos": set(), "M": 0, "F": 0, "total": 0})
        r["grupos"].add((e.sede_id, e.curso))
        r["total"] += 1
        if (e.genero or "").upper() in ("M", "F"):
            r[(e.genero or "").upper()] += 1
    filas_resumen = "".join(
        f'<tr><td class="izq">{models.GRADOS_NOMBRES.get(g, g)}</td><td>{len(r["grupos"])}</td>'
        f'<td>{r["M"]}</td><td>{r["F"]}</td><td>{r["total"]}</td></tr>'
        for g, r in sorted(resumen.items())
    )
    tot_m = sum(r["M"] for r in resumen.values())
    tot_f = sum(r["F"] for r in resumen.values())
    tot_grupos = sum(len(r["grupos"]) for r in resumen.values())

    portada = f"""
    <h1>{html.escape(titulo)}</h1>
    <p class="subtitulo">{html.escape(subtitulo)}</p>
    <p class="explicacion">{_explicacion(vista, len(estudiantes), html.escape(sede_txt), nombre_desde,
                                         html.escape(hasta), nombre_hasta, cantidad, completo, hoy,
                                         max(sin_grupo_excluidos, 0), html.escape(grupos_txt),
                                         incluye_posibles, incluye_retirados)}</p>
    <table class="datos">
      <tr><td class="et" width="22%">Sede</td><td width="28%">{html.escape(sede_txt)}</td>
          <td class="et" width="22%">Año lectivo</td><td width="28%">{fechas.anio_lectivo_actual()}</td></tr>
      <tr><td class="et">Total de estudiantes</td><td><b>{len(estudiantes)}</b></td>
          <td class="et">Fecha de expedición</td><td>{hoy.strftime("%d/%m/%Y")}</td></tr>
    </table>
    <h2>Resumen por grado</h2>
    <table class="resumen">
      <thead><tr><th>Grado</th><th>Grupos</th><th>Hombres</th><th>Mujeres</th><th>Total</th></tr></thead>
      <tbody>{filas_resumen}
        <tr class="total"><td class="izq">TOTAL</td><td>{tot_grupos}</td><td>{tot_m}</td><td>{tot_f}</td><td>{len(estudiantes)}</td></tr>
      </tbody>
    </table>
    <h2>Detalle de estudiantes</h2>
    """

    # --- Detalle agrupado por grado / grupo ---------------------------------
    encabezados = f'<th width="{ancho(0.7)}">N°</th>' + "".join(
        f'<th width="{ancho(COLUMNAS[c][2])}">{html.escape(COLUMNAS[c][0])}</th>' for c in columnas
    )
    grupos: list[tuple[str, list[str]]] = []
    clave_actual = None
    for n, e in enumerate(estudiantes, start=1):
        clave = (e.sede_id, e.grado, e.curso)
        if clave != clave_actual:
            clave_actual = clave
            titulo_grupo = e.grupo + (f" · {e.sede.nombre}" if varias_sedes and e.sede else "")
            grupos.append((titulo_grupo, []))
        celdas = "".join(f"<td>{html.escape(COLUMNAS[c][1](e, hoy))}</td>" for c in columnas)
        clase = ' class="par"' if len(grupos[-1][1]) % 2 else ""
        grupos[-1][1].append(f'<tr{clase}><td class="num">{n}</td>{celdas}</tr>')

    firmas = """
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

    def tabla_grupo(titulo_g: str, filas: list[str], continuacion: bool, total: int) -> str:
        etiqueta = "continuación" if continuacion else f"{total} estudiante{'' if total == 1 else 's'}"
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
            # búsqueda binaria de cuántas filas de este grupo caben en la hoja
            lo, hi = 0, len(resto)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if cabe(actual + tabla_grupo(titulo_g, resto[:mid], continuacion, len(filas))):
                    lo = mid
                else:
                    hi = mid - 1
            minimo = min(3, len(resto))  # no dejar un título de grupo con 1-2 filas sueltas
            if lo >= minimo or (lo > 0 and actual == ""):
                actual += tabla_grupo(titulo_g, resto[:lo], continuacion, len(filas))
                i += lo
            elif actual == "":
                raise ValueError("Una fila no cabe en la hoja; quita algunas columnas.")
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
