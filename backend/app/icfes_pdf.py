"""PDF imprimible de los resultados Saber 11 (ICFES) de un curso actual (ej. 11-2).

Dos documentos, ambos con el membrete y pie oficiales (pdf_membrete.py: mismo
logo, textos y lema de la constancia oficial) — este archivo NO define ningún
membrete propio:

  · REPORTE DEL CURSO (carta vertical): portada con datos del grupo, resumen
    por prueba frente al promedio del colegio, la tabla de los estudiantes con
    resultado (puntaje global, puesto, puntaje y nivel en cada prueba) y, aparte,
    los estudiantes activos que no tienen resultado.
  · REPORTES INDIVIDUALES (carta vertical): una hoja por estudiante con
    resultado, para entregar al estudiante o al acudiente.

Los datos salen de icfes.resultados_por_grupo(). Las coincidencias por nombre
aproximado (el ICFES escribió el nombre distinto) se imprimen con el nombre
tal como figura en el ICFES, para que quien lea pueda verificarlo.

Con la versión de PyMuPDF instalada, fitz.Story ajusta cada columna a su
contenido (no respeta anchos en %, pt ni atributos): por eso los encabezados
largos van partidos en dos líneas, para que las columnas queden parejas."""

import html

from sqlalchemy.orm import Session

from . import fechas, icfes, pdf_membrete

AZUL = pdf_membrete.AZUL
# Niveles de desempeño: tonos claros para imprimir (naranja = bajo, azul = alto),
# mismo sentido que la escala de la pantalla.
FONDO_NIVEL_4 = ["#f9c9ad", "#fde4cf", "#d9e5f7", "#b5cdf1"]
FONDO_NIVEL_5 = ["#f9c9ad", "#fde4cf", "#eef3fb", "#d9e5f7", "#b5cdf1"]
DESCRIPCION_NIVELES = (
    "Niveles de desempeño del ICFES: Nivel 1, desempeño mínimo; Nivel 2, resuelve preguntas sencillas; "
    "Nivel 3, resuelve preguntas de complejidad media; Nivel 4, resuelve las preguntas de mayor complejidad. "
    "En Inglés los niveles siguen el Marco Común Europeo: A-, A1, A2, B1 y B+."
)
ENCABEZADO_PRUEBA = {
    "lc": "Lectura<br/>crítica", "mat": "Matemá-<br/>ticas", "syc": "Sociales y<br/>ciudadanas",
    "cn": "Ciencias<br/>naturales", "ing": "Inglés<br/>&#160;",
}

CSS_ICFES = f"""
table.ic {{ border-collapse: collapse; margin: 0 0 4px 0; }}
table.ic th {{ background-color: {AZUL}; color: #fff; font-size: 7.6pt; padding: 3px 5px; border: 0.6px solid {AZUL}; text-align: center; }}
table.ic th.izq {{ text-align: left; }}
table.ic td {{ font-size: 7.8pt; padding: 2px 5px; border: 0.6px solid #9aa7b8; text-align: center; }}
table.ic td.izq {{ text-align: left; }}
table.ic td.glob {{ font-weight: bold; color: {AZUL}; font-size: 8.4pt; }}
table.ic td.niv span {{ font-size: 6.6pt; color: #333; }}
table.ic tr.par td {{ background-color: #f5f7fa; }}
table.ic td.mas {{ color: #166534; font-weight: bold; }}
table.ic td.menos {{ color: #b91c1c; font-weight: bold; }}
.ap {{ color: #9a3412; font-size: 6.4pt; }}
.leyenda {{ font-size: 7.4pt; color: #444; margin: 5px 0 0 0; }}
table.kpi {{ border-collapse: collapse; margin: 2px 0 10px 0; }}
table.kpi td {{ border: 0.8px solid #9aa7b8; padding: 5px 12px; text-align: center; vertical-align: top; }}
.kpi-etq {{ font-size: 7.6pt; color: #555; margin: 0; }}
.kpi-val {{ font-size: 17pt; font-weight: bold; color: {AZUL}; margin: 1px 0 0 0; }}
.kpi-sub {{ font-size: 7.2pt; color: #555; margin: 0; }}
.lectura {{ font-size: 9pt; line-height: 1.4; margin: 0 0 4px 0; text-align: justify; }}
"""


def _e(v) -> str:
    return "—" if v is None or v == "" else html.escape(str(v))


def _f(v, d: int = 1) -> str:
    return "—" if v is None else f"{v:.{d}f}"


def _s(v) -> str:
    return "—" if v is None else f"{v:+.1f}"


def _pct(v) -> str:
    return "—" if v is None else f"{v:.0f}%"


def _par(i: int) -> str:
    return ' class="par"' if i % 2 else ""


def _nombre_nivel(prueba: str, nivel: str | None) -> str:
    if not nivel:
        return "—"
    return nivel if prueba == "ing" else f"Nivel {nivel}"


def _nivel_corto(prueba: str, nivel: str | None) -> str:
    """«N2» (o el nivel de inglés tal cual): cabe en la misma línea del puntaje."""
    if not nivel:
        return ""
    return nivel if prueba == "ing" else f"N{nivel}"


def _fondo_nivel(prueba: str, nivel: str | None) -> str:
    niveles = [n for *_, n in icfes.NIVELES[prueba]]
    if nivel not in niveles:
        return ""
    paleta = FONDO_NIVEL_5 if len(niveles) == 5 else FONDO_NIVEL_4
    return f' style="background-color:{paleta[niveles.index(nivel)]}"'


def _celda_nivel(prueba: str, v: dict) -> str:
    if v["puntaje"] is None:
        return "<td>—</td>"
    return (f'<td class="niv"{_fondo_nivel(prueba, v["nivel"])}>'
            f'<b>{v["puntaje"]}</b> <span>{_nivel_corto(prueba, v["nivel"])}</span></td>')


def _clase_dif(dif: float | None, umbral: float) -> str:
    if dif is None:
        return ""
    return ' class="mas"' if dif >= umbral else ' class="menos"' if dif <= -umbral else ""


def _anio_txt(d: dict) -> str:
    return ", ".join(str(a) for a in d["anios"]) or "—"


def _paginar(papeleria, area, actual: str, paginas: list[str], filas: list[str], tabla) -> str:
    """Mete las filas en la hoja mientras quepan; al cambiar de hoja repite el
    encabezado de la tabla (tabla(filas, continuacion) arma el HTML)."""
    i = 0
    while i < len(filas):
        resto = filas[i:]
        if papeleria.cabe(actual + tabla(resto, i > 0), area):
            return actual + tabla(resto, i > 0)
        lo, hi = 0, len(resto)
        while lo < hi:  # cuántas filas caben en lo que queda de hoja
            mitad = (lo + hi + 1) // 2
            if papeleria.cabe(actual + tabla(resto[:mitad], i > 0), area):
                lo = mitad
            else:
                hi = mitad - 1
        if lo >= 3 or (not actual and lo > 0):  # no dejar un título con 1-2 filas sueltas
            actual += tabla(resto[:lo], i > 0)
            i += lo
        elif not actual:
            raise ValueError("La tabla no cabe en la hoja.")
        paginas.append(actual)
        actual = ""
    return actual


def _agregar(papeleria, area, actual: str, paginas: list[str], bloque: str) -> str:
    if papeleria.cabe(actual + bloque, area):
        return actual + bloque
    paginas.append(actual)
    return bloque


# --- Reporte del curso ---------------------------------------------------------


def _resumen_pruebas_html(d: dict) -> str:
    filas = []
    for i, p in enumerate(icfes.PRUEBAS):
        r = d["resumen_pruebas"][p]
        dif = round(r["promedio"] - r["colegio"], 1) if r["promedio"] is not None and r["colegio"] is not None else None
        filas.append(
            f'<tr{_par(i)}><td class="izq"><b>{icfes.NOMBRE_PRUEBA[p]}</b></td>'
            f'<td class="glob">{_f(r["promedio"])}</td><td>{_f(r["colegio"])}</td>'
            f"<td{_clase_dif(dif, 1)}>{_s(dif)}</td><td>{_pct(r['percentil'])}</td><td>{_pct(r['pct_nivel_bajo'])}</td></tr>"
        )
    return (
        "<h2>Resumen del grupo por prueba</h2>"
        '<table class="ic"><thead><tr><th class="izq">Prueba</th><th>Promedio<br/>del grupo</th>'
        f'<th>Promedio del<br/>colegio {_e(d["colegio_anio"])}</th><th>Diferencia<br/>&#160;</th>'
        "<th>Percentil nacional<br/>promedio</th><th>Estudiantes en el<br/>nivel más bajo</th></tr></thead>"
        f'<tbody>{"".join(filas)}</tbody></table>'
        '<p class="leyenda">Puntajes de 0 a 100. Diferencia: promedio del grupo menos el del colegio en el mismo año. '
        "Percentil nacional: porcentaje de estudiantes del país que el estudiante típico del grupo supera.</p>"
    )


def generar_reporte_grupo_pdf(db: Session, sede_id: int, grado: int, curso: int | None) -> bytes:
    d = icfes.resultados_por_grupo(db, sede_id, grado, curso)
    if not d["total"]:
        raise ValueError("No hay estudiantes activos en ese grupo.")
    hoy = fechas.hoy_colombia()
    papeleria = pdf_membrete.Papeleria(CSS_ICFES)
    _, _, area, _, _ = pdf_membrete.medidas(horizontal=False)
    grupo, sede = d["nombre_grupo"], d["sede_nombre"].strip()

    explicacion = (
        "El presente documento relaciona los resultados de las <b>Pruebas Saber 11°</b> del ICFES de los "
        f"<b>{d['total']}</b> estudiantes con matrícula activa en el grupo <b>{html.escape(grupo)}</b> de "
        f"<b>{html.escape(sede)}</b>. De ellos, <b>{d['con_resultado']}</b> tienen resultado publicado por el "
        f"ICFES y <b>{d['sin_resultado']}</b> no registran resultado en el sistema. Cada prueba se califica de "
        "0 a 100 y el puntaje global de 0 a 500. La información se toma de los resultados publicados en la "
        f"plataforma PRISMA del ICFES, con corte al {pdf_membrete.fecha_larga(hoy)}."
    )
    datos = (
        '<table class="datos">'
        f'<tr><td class="et">Sede</td><td>{_e(sede)}</td><td class="et">Grupo</td><td><b>{_e(grupo)}</b></td></tr>'
        f'<tr><td class="et">Estudiantes activos</td><td>{d["total"]} ({d["con_resultado"]} con resultado, '
        f'{d["sin_resultado"]} sin resultado)</td><td class="et">Aplicación ICFES</td><td>{_anio_txt(d)}</td></tr>'
        f'<tr><td class="et">Puntaje global promedio del grupo</td><td><b>{_f(d["promedio_global"])}</b> '
        f'(más alto {_e(d["global_max"])} · más bajo {_e(d["global_min"])})</td>'
        f'<td class="et">Promedio del colegio {_e(d["colegio_anio"])}</td>'
        f'<td>{_f(d["colegio_global"])} ({_e(d["colegio_n"])} estudiantes)</td></tr>'
        "</table>"
    )
    portada = (
        "<h1>REPORTE DE RESULTADOS PRUEBAS SABER 11° (ICFES)</h1>"
        f'<p class="subtitulo">Grupo {html.escape(grupo)} · {html.escape(sede)} · Aplicación {_anio_txt(d)}</p>'
        f'<p class="explicacion">{explicacion}</p>{datos}{_resumen_pruebas_html(d)}'
    )

    con = [f for f in d["estudiantes"] if f["resultado"]]
    sin = [f for f in d["estudiantes"] if not f["resultado"]]

    encabezado = (
        '<th>Puesto</th><th class="izq">Estudiante</th><th>Documento</th><th>Puntaje<br/>global</th>'
        + "".join(f"<th>{ENCABEZADO_PRUEBA[p]}</th>" for p in icfes.PRUEBAS)
    )
    filas = []
    for i, f in enumerate(con):
        r = f["resultado"]
        nombre = f"<b>{html.escape(f['nombre'])}</b>"
        if f["aproximada"]:
            nombre += f'<br/><span class="ap">* En el ICFES: {html.escape(r["nombre_icfes"])}</span>'
        filas.append(
            f'<tr{_par(i)}><td>{_e(f.get("puesto"))}</td><td class="izq">{nombre}</td><td>{_e(f["documento"])}</td>'
            f'<td class="glob">{_e(r["puntaje_global"])}</td>'
            + "".join(_celda_nivel(p, r["pruebas"][p]) for p in icfes.PRUEBAS)
            + "</tr>"
        )

    def tabla(filas_hoja: list[str], continuacion: bool) -> str:
        titulo = "Resultados por estudiante" + (" (continuación)" if continuacion else "")
        return (f'<h2>{titulo}</h2><table class="ic"><thead><tr>{encabezado}</tr></thead>'
                f'<tbody>{"".join(filas_hoja)}</tbody></table>')

    notas = [
        "Puesto: posición dentro del grupo según el puntaje global. En cada prueba va el puntaje (0 a 100) y el "
        "nivel de desempeño: N1 a N4 (N1 = el más bajo); el color también lo indica (naranja = niveles bajos, "
        "azul = niveles altos). " + DESCRIPCION_NIVELES
    ]
    if d["aproximadas"]:
        notas.append("* El nombre del estudiante figura escrito de otra forma en los resultados del ICFES; el "
                     "resultado se asoció por similitud del nombre completo y debe verificarse con el registro ICFES.")
    leyenda = "".join(f'<p class="leyenda">{t}</p>' for t in notas)

    paginas: list[str] = []
    actual = portada
    if filas:
        actual = _paginar(papeleria, area, actual, paginas, filas, tabla) + leyenda
    if sin:
        filas_sin = [f'<tr{_par(i)}><td>{i + 1}</td><td class="izq"><b>{html.escape(f["nombre"])}</b></td>'
                     f'<td>{_e(f["documento"])}</td></tr>' for i, f in enumerate(sin)]

        def tabla_sin(filas_hoja: list[str], continuacion: bool) -> str:
            titulo = f"Estudiantes sin resultado ICFES registrado ({len(sin)})" + (" (continuación)" if continuacion else "")
            return (f'<h2>{titulo}</h2><table class="ic"><thead><tr><th>No.</th><th class="izq">Estudiante</th>'
                    f'<th>Documento</th></tr></thead><tbody>{"".join(filas_hoja)}</tbody></table>')

        actual = _paginar(papeleria, area, actual, paginas, filas_sin, tabla_sin)
        actual += ('<p class="leyenda">No se encontró en los resultados del ICFES un registro con el nombre de estos '
                   "estudiantes: puede que no hayan presentado la prueba o que su nombre figure escrito de otra forma.</p>")
    actual = _agregar(papeleria, area, actual, paginas, pdf_membrete.FIRMAS_HTML)
    paginas.append(actual)
    return pdf_membrete.escribir_pdf(papeleria, paginas)


# --- Reportes individuales -------------------------------------------------------


def _hoja_individual(d: dict, f: dict, hoy) -> tuple[str, str]:
    """(cuerpo, cierre) de la hoja de un estudiante; el cierre (leyenda y
    firmas) pasa a la hoja siguiente si no alcanza."""
    r = f["resultado"]
    R = d["resumen_pruebas"]
    grupo = d["nombre_grupo"]
    con_puesto = sum(1 for x in d["estudiantes"] if x.get("puesto"))

    datos = (
        '<table class="datos">'
        f'<tr><td class="et">Estudiante</td><td><b>{_e(f["nombre"])}</b></td>'
        f'<td class="et">Documento</td><td>{_e(f["documento"])}</td></tr>'
        f'<tr><td class="et">Grupo</td><td>{_e(grupo)}</td><td class="et">Registro ICFES</td><td>{_e(r["registro"])}</td></tr>'
        f'<tr><td class="et">Sede</td><td>{_e(d["sede_nombre"].strip())}</td>'
        f'<td class="et">Aplicación</td><td>{r["anio"]} · período {r["periodo"]}</td></tr>'
        "</table>"
    )
    aviso = ""
    if f["aproximada"]:
        aviso = (f'<p class="leyenda">* En los resultados del ICFES el nombre figura como '
                 f'<b>{html.escape(r["nombre_icfes"])}</b>; verifíquese con el registro ICFES.</p>')

    def kpi(etq: str, val: str, sub: str) -> str:
        return f'<td><p class="kpi-etq">{etq}</p><p class="kpi-val">{val}</p><p class="kpi-sub">{sub}</p></td>'

    cuarto = (kpi("Percentil nacional", _pct(r["percentil_global"]), "supera a ese % del país")
              if r["percentil_global"] is not None else
              kpi(f"Promedio del colegio {_e(d['colegio_anio'])}", _f(d["colegio_global"]), "puntaje global"))
    kpis = (
        '<table class="kpi"><tr>'
        + kpi("Puntaje global", _e(r["puntaje_global"]), "de 500 puntos")
        + kpi("Puesto en el grupo", _e(f.get("puesto")), f"de {con_puesto} con resultado")
        + kpi("Promedio del grupo", _f(d["promedio_global"]), "puntaje global")
        + cuarto
        + "</tr></table>"
    )

    filas = []
    fuertes, debiles, bajos = [], [], []
    for i, p in enumerate(icfes.PRUEBAS):
        v = r["pruebas"][p]
        prom = R[p]["promedio"]
        dif = round(v["puntaje"] - prom, 1) if v["puntaje"] is not None and prom is not None else None
        nombre = icfes.NOMBRE_PRUEBA[p]
        if dif is not None and dif >= 3:
            fuertes.append(nombre)
        if dif is not None and dif <= -3:
            debiles.append(nombre)
        if v["nivel"] == icfes.NIVEL_MAS_BAJO[p]:
            bajos.append(nombre)
        filas.append(
            f'<tr{_par(i)}><td class="izq"><b>{nombre}</b></td><td class="glob">{_e(v["puntaje"])}</td>'
            f'<td{_fondo_nivel(p, v["nivel"])}><b>{_nombre_nivel(p, v["nivel"])}</b></td>'
            f'<td>{_pct(v["percentil"])}</td><td>{_f(prom)}</td><td>{_f(R[p]["colegio"])}</td>'
            f"<td{_clase_dif(dif, 3)}>{_s(dif)}</td></tr>"
        )
    tabla = (
        "<h2>Resultados por prueba</h2>"
        '<table class="ic"><thead><tr><th class="izq">Prueba</th><th>Puntaje<br/>(0 a 100)</th>'
        "<th>Nivel de<br/>desempeño</th><th>Percentil<br/>nacional</th><th>Promedio<br/>del grupo</th>"
        "<th>Promedio<br/>del colegio</th><th>Frente al<br/>grupo</th></tr></thead>"
        f'<tbody>{"".join(filas)}</tbody></table>'
    )

    lectura = []
    if r["puntaje_global"] is not None and d["promedio_global"] is not None:
        dg = r["puntaje_global"] - d["promedio_global"]
        lectura.append(f"Su puntaje global ({r['puntaje_global']}) está {abs(dg):.1f} puntos "
                       f"{'por encima' if dg >= 0 else 'por debajo'} del promedio del grupo ({d['promedio_global']:.1f}).")
    if fuertes:
        lectura.append("Fortalezas frente al grupo: " + ", ".join(fuertes) + ".")
    if debiles:
        lectura.append("Aspectos por reforzar frente al grupo: " + ", ".join(debiles) + ".")
    if bajos:
        lectura.append("Quedó en el nivel más bajo del ICFES en: " + ", ".join(bajos) + ".")
    lectura_html = ("<h2>Lectura de los resultados</h2>"
                    + "".join(f'<p class="lectura">• {html.escape(t)}</p>' for t in lectura)) if lectura else ""

    cuerpo = (
        "<h1>REPORTE INDIVIDUAL DE RESULTADOS SABER 11°</h1>"
        f'<p class="subtitulo">{html.escape(grupo)} · Aplicación {r["anio"]} · expedido el {pdf_membrete.fecha_larga(hoy)}</p>'
        f"{datos}{aviso}{kpis}{tabla}{lectura_html}"
    )
    leyenda = (
        f'<p class="leyenda">{DESCRIPCION_NIVELES} «Frente al grupo» es el puntaje del estudiante menos el promedio '
        "de su grupo; diferencias de 3 puntos o más se señalan en color. Percentil nacional: porcentaje de "
        "estudiantes del país que el estudiante supera.</p>"
    )
    return cuerpo, leyenda + pdf_membrete.FIRMAS_HTML


def generar_individuales_pdf(db: Session, sede_id: int, grado: int, curso: int | None,
                             estudiante_id: int | None = None) -> bytes:
    d = icfes.resultados_por_grupo(db, sede_id, grado, curso)
    con = [f for f in d["estudiantes"] if f["resultado"] and (estudiante_id is None or f["estudiante_id"] == estudiante_id)]
    if not con:
        raise ValueError("Ningún estudiante de ese grupo tiene resultado ICFES para imprimir.")
    hoy = fechas.hoy_colombia()
    papeleria = pdf_membrete.Papeleria(CSS_ICFES)
    _, _, area, _, _ = pdf_membrete.medidas(horizontal=False)
    paginas = []
    for f in con:
        cuerpo, cierre = _hoja_individual(d, f, hoy)
        # Cada estudiante en su propia hoja; si no alcanza, la leyenda y las firmas pasan a la siguiente.
        paginas.extend([cuerpo + cierre] if papeleria.cabe(cuerpo + cierre, area) else [cuerpo, cierre])
    return pdf_membrete.escribir_pdf(papeleria, paginas)
