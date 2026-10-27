"""Reporte GENERAL de horas libres de los docentes (Sede #01).

Una sola mirada para toda la planta, en dos formatos: el cuadro por día
(todos los docentes por las 6 franjas, con lo que dictan y sus LIBRE) o una
fila por hora con el nombre de los que están libres. No es una hoja por
profesor: es el cuadro general.

Sale del horario oficial ya importado (BloqueHorario activo del año), así
que "libre" = esa franja no tiene ninguna clase asignada. No mira permisos
ni ausencias de un día puntual (eso es el panel "Hoy" del módulo Horarios).
"""

import html

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import fechas, horario, models, pdf_membrete, schemas

CSS_HORAS = """
table.hl { width: 100%; border-collapse: collapse; }
table.hl th { background-color: #1f3a5f; color: #fff; font-size: 6.6pt; padding: 3px; border: 0.6px solid #1f3a5f; text-align: center; }
table.hl th.doc { text-align: left; }
table.hl td { font-size: 6.6pt; padding: 2px 3px; border: 0.6px solid #9aa7b8; text-align: center; color: #333; }
table.hl td.doc { text-align: left; font-size: 6.8pt; }
table.hl td.libre { background-color: #dcfce7; color: #166534; font-weight: bold; }
table.hl td.tot { background-color: #eef2f7; font-weight: bold; color: #1f3a5f; }
table.hl tr.par td { background-color: #f5f7fa; }
table.hl tr.par td.libre { background-color: #cdf0d8; }
table.hl tr.par td.tot { background-color: #e5eaf2; }
.dia { font-size: 10pt; font-weight: bold; color: #1f3a5f; margin: 9px 0 3px 0; }
.dia span { font-weight: normal; color: #555; font-size: 8pt; }
.leyenda { font-size: 7.5pt; color: #555; margin: 2px 0 6px 0; }

/* Formato "una fila por hora": cada hora es UNA banda. Las celdas no llevan
   líneas entre sí; solo una raya arriba y otra abajo cierran el bloque, y el
   fondo alterna hora por hora. Así no se confunden las filas cuando los
   nombres siguen en el renglón de abajo. */
table.hl td.h { border: none; background-color: #ffffff; text-align: left; font-size: 7pt; padding: 2px 5px; color: #333; }
table.hl tr.par td.h { background-color: #eef3f8; }
table.hl td.ini { border-top: 0.9px solid #8fa0b6; }
table.hl td.fin { border-bottom: 0.9px solid #8fa0b6; }
table.hl td.franja { font-weight: bold; color: #1f3a5f; font-size: 7.2pt; border-right: 0.6px solid #c6cedb; }
table.hl td.franja .chico { font-weight: normal; color: #555; font-size: 6.4pt; }
table.hl td.conteo { text-align: center; font-weight: bold; color: #1f3a5f; border-right: 0.6px solid #c6cedb; }
table.hl td.nadie { border: none; text-align: left; font-size: 7pt; color: #9a3412; font-style: italic; }
table.hl .niv { color: #64748b; font-size: 5.8pt; }
"""


def _etiqueta_clase(b: models.BloqueHorario) -> str:
    """'6-2 COE': el grupo y el código del área, que es lo que cabe en la celda."""
    grupo = horario.nombre_grupo(b.grado, b.curso)
    area = b.area.codigo if b.area else (b.area_label or "")
    return f"{grupo} {area}".strip()


def calcular(db: Session, anio_lectivo: int) -> schemas.HorasLibresReporte:
    bloques = db.scalars(
        select(models.BloqueHorario)
        .where(
            models.BloqueHorario.anio_lectivo == anio_lectivo,
            models.BloqueHorario.estado == "activo",
        )
        .options(selectinload(models.BloqueHorario.area), selectinload(models.BloqueHorario.docente))
    ).all()

    horas = [f["hora"] for f in horario.FRANJAS]
    docentes: dict[int, models.Docente] = {}
    ocupadas: dict[int, dict[str, list[str]]] = {}
    niveles: dict[int, set[str]] = {}
    for b in bloques:
        if b.docente is None:
            continue
        docentes[b.docente.id] = b.docente
        niveles.setdefault(b.docente.id, set()).add(horario.nivel_de_grado(b.grado))
        # Dos clases a la misma hora = conflicto sin resolver: se muestran las dos.
        clase = ocupadas.setdefault(b.docente.id, {}).setdefault(f"{b.dia}-{b.hora}", [])
        etiqueta = _etiqueta_clase(b)
        if etiqueta not in clase:
            clase.append(etiqueta)

    filas = []
    for did, d in docentes.items():
        celdas = {k: " / ".join(v) for k, v in ocupadas.get(did, {}).items()}
        libres_por_dia = {
            dia: sum(1 for h in horas if f"{dia}-{h}" not in celdas) for dia in horario.DIAS_NOMBRES
        }
        filas.append(
            schemas.HorasLibresDocente(
                docente_id=did,
                nombre_completo=d.nombre_completo,
                celdas=celdas,
                libres_por_dia=libres_por_dia,
                niveles=sorted(niveles.get(did, [])),
                total_libres=sum(libres_por_dia.values()),
                total_clases=len(celdas),
            )
        )
    filas.sort(key=lambda f: f.nombre_completo)
    return schemas.HorasLibresReporte(
        anio_lectivo=anio_lectivo,
        franjas=[dict(f) for f in horario.FRANJAS],
        docentes=filas,
    )


def _tabla_dia(dia: int, filas: list[schemas.HorasLibresDocente], solo_libres: bool) -> list[str]:
    """Un día: todos los docentes por 6 franjas; qué dicta o LIBRE."""
    horas = [f["hora"] for f in horario.FRANJAS]
    ancho_hora = f"{70 / len(horas):.1f}%"
    encabezado = (
        '<th class="doc" width="20%">Docente</th>'
        + "".join(
            f'<th width="{ancho_hora}">{f["hora"]}a &nbsp;{f["inicio"]}-{f["fin"]}</th>'
            for f in horario.FRANJAS
        )
        + '<th width="10%">Horas libres</th>'
    )
    cuerpo = []
    for i, f in enumerate(filas):
        if solo_libres and not f.libres_por_dia.get(dia):
            continue
        celdas = ""
        for h in horas:
            texto = f.celdas.get(f"{dia}-{h}", "")
            celdas += '<td class="libre">LIBRE</td>' if not texto else f"<td>{html.escape(texto)}</td>"
        cuerpo.append(
            f'<tr{" class=par" if i % 2 else ""}>'
            f'<td class="doc">{html.escape(f.nombre_completo)}</td>{celdas}'
            f'<td class="tot">{f.libres_por_dia.get(dia, 0)}</td></tr>'
        )
    return [encabezado] + cuerpo


def _etiqueta_nivel(niveles: list[str]) -> str:
    """P = primaria, S = secundaria, P·S = dicta en los dos niveles."""
    if len(niveles) > 1:
        return "P·S"
    if niveles == ["primaria"]:
        return "P"
    if niveles == ["secundaria"]:
        return "S"
    return ""


def _tabla_por_hora(dia: int, filas: list[schemas.HorasLibresDocente]) -> list[str]:
    """Un día: cada hora es una banda con los docentes libres en 3 columnas.

    Los nombres son columnas de la MISMA tabla (no una tabla dentro de la
    celda), así quedan alineados de arriba a abajo igual que en pantalla. Si
    no caben en un renglón siguen en el de abajo, dentro de la misma banda:
    mismo fondo, sin líneas internas y con una raya que la cierra.
    """
    ancho_nombre = "25.6%"
    encabezado = (
        '<th class="doc" width="16%">HORA</th>'
        '<th width="7%">LIBRES</th>'
        f'<th class="doc" width="{ancho_nombre}" colspan="3">DOCENTES LIBRES EN ESA HORA</th>'
        f'<th class="doc" width="{ancho_nombre}"> </th>'
        f'<th class="doc" width="{ancho_nombre}"> </th>'
    )
    cuerpo = []
    for i, f in enumerate(horario.FRANJAS):
        clase_fila = ' class="par"' if i % 2 else ""
        libres = sorted(
            (d.nombre_completo, _etiqueta_nivel(d.niveles))
            for d in filas
            if f"{dia}-{f['hora']}" not in d.celdas
        )
        renglones = [libres[j : j + 3] for j in range(0, len(libres), 3)] or [[]]
        for k, trio in enumerate(renglones):
            bordes = (" ini" if k == 0 else "") + (" fin" if k == len(renglones) - 1 else "")
            if k == 0:
                izquierda = (
                    f'<td class="h franja{bordes}">{f["hora"]}a hora '
                    f'<span class="chico">{f["inicio"]}-{f["fin"]}</span></td>'
                    f'<td class="h conteo{bordes}">{len(libres)}</td>'
                )
            else:
                izquierda = f'<td class="h franja{bordes}"> </td><td class="h conteo{bordes}"> </td>'
            if not trio:
                celdas = f'<td class="h nadie{bordes}" colspan="3">Ningún docente libre en esta hora</td>'
            else:
                celdas = "".join(
                    f'<td class="h{bordes}">{html.escape(n)} <span class="niv">{niv}</span></td>'
                    for n, niv in trio
                )
                celdas += f'<td class="h{bordes}"> </td>' * (3 - len(trio))
            cuerpo.append(f"<tr{clase_fila}>{izquierda}{celdas}</tr>")
    return [encabezado] + cuerpo


def _portada(reporte: schemas.HorasLibresReporte, dias: list[int], hoy, formato: str) -> str:
    total_libres = sum(f.total_libres for f in reporte.docentes)
    total_franjas = len(reporte.docentes) * len(horario.FRANJAS) * len(horario.DIAS_NOMBRES)
    dias_txt = ", ".join(horario.DIAS_NOMBRES[d] for d in dias)
    return f"""
    <h1>REPORTE DE HORAS LIBRES DE LOS DOCENTES</h1>
    <p class="subtitulo">Sede #01 I.E.T.A.B.A. · Año lectivo {reporte.anio_lectivo} · {dias_txt}</p>
    <p class="explicacion">El presente documento muestra, para toda la planta docente de la Sede #01,
    en qué franjas tiene clase cada docente y en cuáles está <b>libre</b>, según el horario oficial
    vigente. Se relacionan <b>{len(reporte.docentes)}</b> docentes con horario asignado y un total de
    <b>{total_libres}</b> horas libres a la semana sobre {total_franjas} franjas posibles
    ({len(horario.FRANJAS)} horas diarias por {len(horario.DIAS_NOMBRES)} días). Una franja se
    considera libre cuando no tiene ninguna clase asignada en el horario; no contempla permisos ni
    ausencias de un día puntual. La información se toma del horario institucional cargado en el
    sistema, con corte al {pdf_membrete.fecha_larga(hoy)}.</p>
    {'<p class="explicacion">Se presenta <b>una fila por cada hora de clase</b>, con el nombre de los docentes que están libres en esa franja. Al lado de cada nombre va el nivel en el que dicta: <b>P</b> = primaria, <b>S</b> = secundaria, <b>P·S</b> = en los dos.</p>' if formato == "por_hora" else ""}
    <table class="datos">
      <tr><td class="et" width="22%">Sede</td><td width="28%">SEDE # 01 I.E.T.A.B.A.</td>
          <td class="et" width="22%">Año lectivo</td><td width="28%">{reporte.anio_lectivo}</td></tr>
      <tr><td class="et">Docentes con horario</td><td><b>{len(reporte.docentes)}</b></td>
          <td class="et">Fecha de expedición</td><td>{hoy.strftime("%d/%m/%Y")}</td></tr>
      <tr><td class="et">Jornada</td>
          <td>{horario.JORNADA.capitalize()} ({horario.FRANJAS[0]["inicio"]} a {horario.FRANJAS[-1]["fin"]})</td>
          <td class="et">Descanso</td>
          <td>{horario.DESCANSO["inicio"]} a {horario.DESCANSO["fin"]}</td></tr>
    </table>
    """


def generar_pdf(
    db: Session,
    anio_lectivo: int,
    dias: list[int] | None = None,
    solo_libres: bool = False,
    formato: str = "cuadro",  # cuadro = tabla por día | por_hora = una fila por franja
) -> bytes:
    reporte = calcular(db, anio_lectivo)
    if not reporte.docentes:
        raise ValueError("No hay horario cargado para ese año lectivo.")
    dias = [d for d in (dias or list(horario.DIAS_NOMBRES)) if d in horario.DIAS_NOMBRES]
    if not dias:
        raise ValueError("Escoge al menos un día.")

    hoy = fechas.hoy_colombia()
    papeleria = pdf_membrete.Papeleria(CSS_HORAS)
    _, _, area, _, _ = pdf_membrete.medidas(horizontal=True)

    # Cada sección es (lo que va antes de la tabla, [encabezado, filas...]).
    secciones = []
    for dia in dias:
        libres_dia = sum(f.libres_por_dia.get(dia, 0) for f in reporte.docentes)
        titulo = (
            f'<p class="dia">{horario.DIAS_NOMBRES[dia].upper()} '
            f"<span>({libres_dia} horas libres en total)</span></p>"
        )
        if formato == "por_hora":
            bloque = _tabla_por_hora(dia, reporte.docentes)
        else:
            titulo += (
                '<p class="leyenda">Cada celda dice el grupo y el área que dicta esa hora; '
                "<b>LIBRE</b> = no tiene clase asignada.</p>"
            )
            bloque = _tabla_dia(dia, reporte.docentes, solo_libres)
        secciones.append((titulo, bloque, horario.DIAS_NOMBRES[dia]))
    portada = _portada(reporte, dias, hoy, formato)

    def tabla(encabezado: str, filas: list[str], continuacion: str) -> str:
        # Al partir una tabla entre hojas, la parte de abajo dice de qué día viene.
        cont = (
            f'<p class="dia">{continuacion.upper()} <span>(continuación)</span></p>'
            if continuacion
            else ""
        )
        return (
            f'{cont}<table class="hl"><thead><tr>{encabezado}</tr></thead>'
            f'<tbody>{"".join(filas)}</tbody></table>'
        )

    # Las filas se van metiendo en la hoja mientras quepan; al cambiar de hoja
    # se repite el encabezado de la tabla (y el título si la sección empieza).
    paginas: list[str] = []
    actual = portada  # la portada abre la primera hoja
    for cabecera, bloque, nombre_dia in secciones:
        encabezado, filas = bloque[0], bloque[1:]
        if not filas:
            continue
        # CADA DÍA EMPIEZA EN HOJA NUEVA: la portada queda sola en la primera y
        # ningún día sigue debajo de otro. Solo se parte si el día no cabe en
        # una hoja vacía — ahí sí va "(continuación)".
        if actual:
            paginas.append(actual)
            actual = ""
        i = 0
        while i < len(filas):
            cab = cabecera if i == 0 else ""
            resto = filas[i:]
            cont = "" if i == 0 else nombre_dia
            if papeleria.cabe(actual + cab + tabla(encabezado, resto, cont), area):
                actual += cab + tabla(encabezado, resto, cont)
                break
            lo, hi = 0, len(resto)
            while lo < hi:  # cuántas filas caben en lo que queda de hoja
                mitad = (lo + hi + 1) // 2
                if papeleria.cabe(actual + cab + tabla(encabezado, resto[:mitad], cont), area):
                    lo = mitad
                else:
                    hi = mitad - 1
            if lo >= 3 or (not actual and lo > 0):
                actual += cab + tabla(encabezado, resto[:lo], cont)
                i += lo
            elif not actual:
                raise ValueError("La tabla no cabe en la hoja; prueba con menos días.")
            paginas.append(actual)
            actual = ""

    if papeleria.cabe(actual + pdf_membrete.FIRMAS_HTML, area):
        actual += pdf_membrete.FIRMAS_HTML
    else:
        paginas.append(actual)
        actual = pdf_membrete.FIRMAS_HTML
    paginas.append(actual)
    return pdf_membrete.escribir_pdf(papeleria, paginas, horizontal=True)
