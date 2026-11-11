"""PDF con membrete: estudiantes del resguardo (censo del Ministerio del
Interior) por grado, de Preescolar a Once. Reportes → Censo Gran Sábalo →
«PDF con membrete».

Solo la sede principal I.E.T.A.B.A. y sin los «Nuevo · pendiente SIMAT» (ver censo._cuenta).
Hoja carta vertical: portada con explicación, cuadro de datos y resumen por
grado; luego el detalle por grado y grupo (el encabezado de la
tabla se repite si un grupo sigue en la hoja siguiente) y firmas al final.
"""

import html

import fitz  # PyMuPDF

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import censo, fechas, models
from .pdf_membrete import FIRMAS_HTML, AZUL, Papeleria, escribir_pdf, fecha_larga, medidas

CSS = f"""
table.resumen {{ width: 100%; border-collapse: collapse; margin: 0 0 8px 0; }}
table.resumen th {{ background-color: {AZUL}; color: #fff; font-size: 8.3pt; padding: 3px 5px; border: 0.6px solid {AZUL}; }}
table.resumen td {{ font-size: 8.3pt; padding: 2px 5px; border: 0.6px solid #9aa7b8; text-align: center; }}
table.resumen td.izq {{ text-align: left; }}
table.resumen tr.total td {{ font-weight: bold; background-color: #eef2f7; }}
.grado {{ font-size: 11pt; font-weight: bold; color: {AZUL}; margin: 10px 0 2px 0; border-bottom: 1px solid {AZUL}; }}
.grado span {{ font-weight: normal; color: #555; font-size: 8.5pt; }}
.grupo {{ font-size: 10pt; font-weight: bold; color: {AZUL}; margin: 12px 0 3px 0; }}
.grupo span {{ font-weight: normal; color: #555; font-size: 8.3pt; }}
table.lista {{ width: 100%; border-collapse: collapse; }}
table.lista th {{ background-color: {AZUL}; color: #fff; font-size: 8pt; padding: 3px 4px; border: 0.6px solid {AZUL}; text-align: left; }}
table.lista td {{ font-size: 8pt; padding: 2px 4px; border: 0.6px solid #9aa7b8; }}
table.lista tr.par td {{ background-color: #f5f7fa; }}
td.num {{ text-align: right; color: #444; }}
td.c {{ text-align: center; }}
"""

# (encabezado, ancho en puntos). fitz.Story ignora width/width:% en tablas y
# las encoge a su contenido; para que TODAS las tablas tengan el mismo ancho
# (la hoja completa) cada encabezado lleva una imagen transparente de ese
# ancho (ver _espaciador).
COLUMNAS = [("N°", 16), ("Apellidos y nombres", 166), ("Documento", 60), ("Edad", 22), ("Sexo", 22),
            ("Comunidad", 100), ("Familia", 34)]
ANCHOS_RESUMEN = (170, 58, 58, 58, 58)


def _espaciador(papeleria, puntos: int) -> str:
    """Imagen transparente de `puntos` de ancho y 1 px de alto (1 px = 0,75 pt)."""
    nombre = f"esp_{puntos}.png"
    if nombre not in papeleria.espaciadores:
        pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, round(puntos / 0.75), 1), 1)
        pm.set_alpha(bytes(pm.width))  # totalmente transparente
        papeleria.archivo.add((pm.tobytes("png"), nombre))
        papeleria.espaciadores.add(nombre)
    return f'<br/><img src="{nombre}"/>'


def _apellidos_nombres(e: models.Estudiante) -> str:
    return " ".join(p for p in (e.primer_apellido, e.segundo_apellido, e.primer_nombre, e.segundo_nombre) if p)


def _sede_corta(nombre: str | None) -> str:
    # "SEDE # 01  I.E.T.A.B.A." → "01 I.E.T.A.B.A."
    return " ".join((nombre or "").replace("SEDE #", "").split())


def generar_pdf(db: Session, desde: int = 0, hasta: int = 11) -> bytes:
    if not (0 <= desde <= hasta <= 11):
        raise ValueError("Escoge un rango de grados entre Preescolar (0) y Once (11).")
    hoy = fechas.hoy_colombia()
    resguardos = censo.resguardos_cargados(db)
    if not resguardos:
        raise ValueError("Todavía no se ha cargado el censo.")
    resguardo = resguardos[0]
    personas = list(db.scalars(
        select(models.PersonaCenso)
        .where(models.PersonaCenso.resguardo == resguardo, models.PersonaCenso.estudiante_id.is_not(None))
        .options(selectinload(models.PersonaCenso.estudiante).selectinload(models.Estudiante.sede))
    ))
    vigencia = max((p.vigencia for p in personas if p.vigencia), default=None)
    filas = []
    sin_seccion = 0  # sin grupo asignado (ej. «Primero» sin «- Uno»): no salen en el PDF
    for p in personas:
        e = p.estudiante
        if e and censo._cuenta(e, solo_ietaba=True) and desde <= e.grado <= hasta:
            if e.curso is None:
                sin_seccion += 1
                continue
            filas.append((e, p))
    if not filas:
        raise ValueError("No hay estudiantes del resguardo en la sede principal I.E.T.A.B.A. para esos grados.")
    filas.sort(key=lambda t: (t[0].grado, t[0].curso or 0, _sede_corta(t[0].sede.nombre if t[0].sede else ""),
                              _apellidos_nombres(t[0])))

    def genero(e, p):
        return (e.genero or p.sexo or "").upper()

    total = len(filas)
    hombres = sum(genero(e, p) == "M" for e, p in filas)
    mujeres = sum(genero(e, p) == "F" for e, p in filas)

    papeleria = Papeleria(CSS)
    papeleria.espaciadores = set()

    # --- Resúmenes -------------------------------------------------------------
    por_grado: dict[int, dict] = {}
    por_comunidad: dict[str, dict] = {}
    for e, p in filas:
        for clave, destino in ((e.grado, por_grado), (p.comunidad or "Sin comunidad", por_comunidad)):
            r = destino.setdefault(clave, {"M": 0, "F": 0, "total": 0})
            r["total"] += 1
            if genero(e, p) in ("M", "F"):
                r[genero(e, p)] += 1

    def fila_resumen(nombre, r):
        pct = f"{100 * r['total'] / total:.1f}%"
        return (f'<tr><td class="izq">{html.escape(str(nombre))}</td><td>{r["M"]}</td><td>{r["F"]}</td>'
                f'<td><b>{r["total"]}</b></td><td>{pct}</td></tr>')

    cab_resumen = "<tr>" + "".join(
        f"<th>{t}{_espaciador(papeleria, w)}</th>"
        for t, w in zip(("{}", "Hombres", "Mujeres", "Total", "%"), ANCHOS_RESUMEN)
    ) + "</tr>"
    total_resumen = (f'<tr class="total"><td class="izq">TOTAL</td><td>{hombres}</td><td>{mujeres}</td>'
                     f"<td>{total}</td><td>100%</td></tr>")
    resumen_grados = "".join(
        fila_resumen(models.GRADOS_NOMBRES.get(g, g), por_grado.get(g, {"M": 0, "F": 0, "total": 0}))
        for g in range(desde, hasta + 1)
    )

    nombre_desde = models.GRADOS_NOMBRES.get(desde, str(desde))
    nombre_hasta = models.GRADOS_NOMBRES.get(hasta, str(hasta))
    resguardo_txt = resguardo.title()
    portada = f"""
    <h1>ESTUDIANTES DEL RESGUARDO {html.escape(resguardo.upper())}</h1>
    <p class="subtitulo">Según el censo indígena del Ministerio del Interior · De {nombre_desde} a {nombre_hasta}</p>
    <p class="explicacion">El presente documento relaciona los <b>{total}</b> estudiantes con matrícula activa en la
      sede principal de la IETABA (Sede N.° 01 I.E.T.A.B.A.), de {nombre_desde} a {nombre_hasta}, que figuran en el censo indígena del resguardo
      <b>{html.escape(resguardo_txt)}</b>{f" (vigencia {vigencia})" if vigencia else ""}, organizados por grado y grupo.
      La pertenencia se establece por el número de documento y, cuando este no coincide, por el nombre completo.
      No se incluyen los estudiantes nuevos pendientes de registro en SIMAT{
        f" ni {sin_seccion} estudiante{'' if sin_seccion == 1 else 's'} sin grupo asignado" if sin_seccion else ""}. La información se toma de la base de
      datos de matrícula del sistema institucional de la IETABA, con corte al {fecha_larga(hoy)}.</p>
    <table class="datos">
      <tr><td class="et" width="22%">Resguardo</td><td width="28%">{html.escape(resguardo_txt)}</td>
          <td class="et" width="22%">Vigencia del censo</td><td width="28%">{vigencia or ""}</td></tr>
      <tr><td class="et">Total de estudiantes</td><td><b>{total}</b></td>
          <td class="et">Hombres / Mujeres</td><td>{hombres} / {mujeres}</td></tr>
      <tr><td class="et">Comunidades</td><td>{len(por_comunidad)}</td>
          <td class="et">Fecha de expedición</td><td>{hoy.strftime("%d/%m/%Y")}</td></tr>
    </table>
    <h2>Resumen por grado</h2>
    <table class="resumen" width="100%"><thead>{cab_resumen.format("Grado")}</thead>
      <tbody>{resumen_grados}{total_resumen}</tbody></table>
    """

    # --- Detalle por grado y grupo ------------------------------------------------
    encabezados = "".join(f"<th>{html.escape(t)}{_espaciador(papeleria, w)}</th>" for t, w in COLUMNAS)
    # Una tabla por grupo (ej. «SEXTO - UNO»), numerada desde 1 en cada grupo.
    grupos_pdf: dict[tuple, list] = {}
    for e, p in filas:
        grupos_pdf.setdefault((e.grado, e.curso or 0), []).append((e, p))
    bloques: list[tuple[str, str, list[str], int]] = []  # ("", título del grupo con conteos, filas, total)
    for (_, _), miembros in grupos_pdf.items():
        e0 = miembros[0][0]
        h = sum(genero(e, p) == "M" for e, p in miembros)
        m = sum(genero(e, p) == "F" for e, p in miembros)
        titulo_grupo = (f"{e0.grupo.upper()}|{len(miembros)} estudiante{'' if len(miembros) == 1 else 's'}: "
                        f"{h} hombre{'' if h == 1 else 's'}, {m} mujer{'' if m == 1 else 'es'}")
        filas_html = []
        for i, (e, p) in enumerate(miembros, start=1):
            clase = ' class="par"' if i % 2 == 0 else ""
            celdas = [
                f'<td class="num">{i}</td>',
                f"<td>{html.escape(_apellidos_nombres(e))}</td>",
                f"<td>{html.escape(e.documento)}</td>",
                f'<td class="c">{censo.edad(e.fecha_nacimiento or p.fecha_nacimiento, hoy) or ""}</td>',
                f'<td class="c">{html.escape(genero(e, p))}</td>',
                f"<td>{html.escape(p.comunidad or '')}</td>",
                f'<td class="c">{html.escape(p.familia or "")}</td>',
            ]
            filas_html.append(f"<tr{clase}>{''.join(celdas)}</tr>")
        bloques.append(("", titulo_grupo, filas_html, len(miembros)))

    _, _, area, _, _ = medidas(False)

    def cabe(contenido: str) -> bool:
        return papeleria.cabe(contenido, area)

    def tabla(_: str, titulo_grupo: str, filas_html: list[str], continuacion: bool, total_g: int) -> str:
        nombre, conteo = titulo_grupo.split("|")
        etiqueta = "continuación" if continuacion else conteo
        return (
            f'<p class="grupo">{html.escape(nombre)} <span>({html.escape(etiqueta)})</span></p>'
            f'<table class="lista" width="100%"><thead><tr>{encabezados}</tr></thead>'
            f'<tbody>{"".join(filas_html)}</tbody></table>'
        )

    paginas: list[str] = []
    # Portada, resumen por comunidad y el detalle empiezan donde quepan.
    actual = portada
    for extra in ("<h2>Detalle de estudiantes por grado</h2>",):
        if not cabe(actual + extra):
            paginas.append(actual)
            actual = ""
        actual += extra
    for titulo_grado, titulo_grupo, filas_html, total_g in bloques:
        i = 0
        while i < len(filas_html):
            cont = i > 0
            resto = filas_html[i:]
            completo = tabla(titulo_grado, titulo_grupo, resto, cont, total_g)
            if cabe(actual + completo):
                actual += completo
                break
            lo, hi = 0, len(resto)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if cabe(actual + tabla(titulo_grado, titulo_grupo, resto[:mid], cont, total_g)):
                    lo = mid
                else:
                    hi = mid - 1
            minimo = min(3, len(resto))  # no dejar un título con 1-2 filas sueltas al pie
            if lo >= minimo or (lo > 0 and actual == ""):
                actual += tabla(titulo_grado, titulo_grupo, resto[:lo], cont, total_g)
                i += lo
            elif actual == "":
                raise ValueError("Una fila no cabe en la hoja.")
            paginas.append(actual)
            actual = ""
    if actual and cabe(actual + FIRMAS_HTML):
        actual += FIRMAS_HTML
    else:
        if actual:
            paginas.append(actual)
        actual = FIRMAS_HTML
    paginas.append(actual)
    return escribir_pdf(papeleria, paginas)
