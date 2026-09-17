"""Reporte de notas para uso diario: a partir de lo que ya se importó de
SAPRED (NotaSapred), separa notas bajas, notas altas, y estudiantes en
riesgo (varias notas bajas). Los umbrales son parámetros, no reglas fijas
inventadas — la secretaría los ajusta según el criterio del colegio."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas


def reporte_notas(
    db: Session,
    periodo: int,
    anio_lectivo: int,
    sede_id: int | None = None,
    grado: int | None = None,
    umbral_bajo: float = 3.0,
    umbral_alto: float = 4.5,
    riesgo_minimo: int = 2,
) -> schemas.ReporteNotas:
    consulta = (
        select(models.NotaSapred, models.RevisionBoletin, models.Estudiante, models.Area)
        .join(models.RevisionBoletin, models.NotaSapred.revision_id == models.RevisionBoletin.id)
        .join(models.Estudiante, models.NotaSapred.estudiante_id == models.Estudiante.id)
        .join(models.Area, models.NotaSapred.area_id == models.Area.id)
        .where(
            models.RevisionBoletin.periodo == periodo,
            models.RevisionBoletin.anio_lectivo == anio_lectivo,
            models.Estudiante.estado == "ACTIVO",
        )
    )
    if sede_id is not None:
        consulta = consulta.where(models.RevisionBoletin.sede_id == sede_id)
    if grado is not None:
        consulta = consulta.where(models.RevisionBoletin.grado == grado)

    filas = db.execute(consulta).all()

    sedes = {s.id: s for s in db.scalars(select(models.Sede)).all()}
    asignaciones = {
        (a.sede_id, a.grado, a.curso): a
        for a in db.scalars(
            select(models.AsignacionDocente).where(
                models.AsignacionDocente.anio_lectivo == anio_lectivo,
                models.AsignacionDocente.area_id.is_(None),
            )
        ).all()
    }

    notas_bajas: list[schemas.NotaDestacada] = []
    notas_altas: list[schemas.NotaDestacada] = []
    notas_por_estudiante: dict[int, list[tuple[schemas.NotaDestacada, float]]] = {}
    total_evaluadas = 0

    for nota, revision, estudiante, area in filas:
        try:
            valor_num = float(nota.valor)
        except (TypeError, ValueError):
            continue  # valores no numéricos (ej. conceptos) no se evalúan en este reporte
        total_evaluadas += 1

        sede = sedes.get(revision.sede_id)
        asignacion = asignaciones.get((revision.sede_id, revision.grado, revision.curso))
        nombre_grado = models.GRADOS_NOMBRES.get(revision.grado, str(revision.grado))
        nombre_grupo = (
            f"{nombre_grado} - {models.DIVISIONES_NOMBRES.get(revision.curso, revision.curso)}"
            if revision.curso
            else nombre_grado
        )

        entrada = schemas.NotaDestacada(
            estudiante_id=estudiante.id,
            documento=estudiante.documento,
            nombre_completo=estudiante.nombre_completo,
            sede_id=revision.sede_id,
            sede_nombre=sede.nombre if sede else "",
            grado=revision.grado,
            nombre_grado=nombre_grado,
            curso=revision.curso,
            nombre_grupo=nombre_grupo,
            area_codigo=area.codigo,
            area_nombre=area.nombre,
            valor=valor_num,
            docente=asignacion.docente.nombre_completo if asignacion else None,
        )
        notas_por_estudiante.setdefault(estudiante.id, []).append((entrada, valor_num))

        if valor_num <= umbral_bajo:
            notas_bajas.append(entrada)
        elif valor_num >= umbral_alto:
            notas_altas.append(entrada)

    estudiantes_en_riesgo: list[schemas.EstudianteEnRiesgo] = []
    for entradas in notas_por_estudiante.values():
        bajas = [(e, v) for e, v in entradas if v <= umbral_bajo]
        if len(bajas) < riesgo_minimo:
            continue
        primero = entradas[0][0]
        promedio = round(sum(v for _, v in entradas) / len(entradas), 2)
        estudiantes_en_riesgo.append(
            schemas.EstudianteEnRiesgo(
                estudiante_id=primero.estudiante_id,
                documento=primero.documento,
                nombre_completo=primero.nombre_completo,
                sede_id=primero.sede_id,
                sede_nombre=primero.sede_nombre,
                grado=primero.grado,
                nombre_grado=primero.nombre_grado,
                curso=primero.curso,
                nombre_grupo=primero.nombre_grupo,
                cantidad_notas_bajas=len(bajas),
                areas_bajas=sorted({e.area_codigo for e, _ in bajas}),
                promedio=promedio,
            )
        )

    notas_bajas.sort(key=lambda n: n.valor)
    notas_altas.sort(key=lambda n: -n.valor)
    estudiantes_en_riesgo.sort(key=lambda e: (-e.cantidad_notas_bajas, e.promedio))

    return schemas.ReporteNotas(
        periodo=periodo,
        anio_lectivo=anio_lectivo,
        umbral_bajo=umbral_bajo,
        umbral_alto=umbral_alto,
        riesgo_minimo=riesgo_minimo,
        total_notas_evaluadas=total_evaluadas,
        notas_bajas=notas_bajas,
        notas_altas=notas_altas,
        estudiantes_en_riesgo=estudiantes_en_riesgo,
    )


def exportar_reporte_notas_excel(reporte: schemas.ReporteNotas) -> bytes:
    import io

    import openpyxl
    from openpyxl.styles import Font

    libro = openpyxl.Workbook()

    def _hoja_notas(hoja, titulo, notas):
        hoja.append([titulo])
        hoja.append([])
        hoja.append(["Sede", "Grupo", "Estudiante", "Documento", "Área", "Nota", "Docente"])
        for celda in hoja[3]:
            celda.font = Font(bold=True)
        for n in notas:
            hoja.append([
                n.sede_nombre, n.nombre_grupo, n.nombre_completo, n.documento,
                n.area_nombre, n.valor, n.docente or "Sin asignar",
            ])
        for columna, ancho in zip(hoja.columns, [22, 16, 30, 14, 24, 8, 26]):
            hoja.column_dimensions[columna[0].column_letter].width = ancho

    hoja_bajas = libro.active
    hoja_bajas.title = "Notas bajas"
    _hoja_notas(hoja_bajas, f"Notas <= {reporte.umbral_bajo} — Período {reporte.periodo}, {reporte.anio_lectivo}", reporte.notas_bajas)

    hoja_altas = libro.create_sheet("Notas altas")
    _hoja_notas(hoja_altas, f"Notas >= {reporte.umbral_alto} — Período {reporte.periodo}, {reporte.anio_lectivo}", reporte.notas_altas)

    hoja_riesgo = libro.create_sheet("Estudiantes en riesgo")
    hoja_riesgo.append([f"{reporte.riesgo_minimo}+ notas bajas (<= {reporte.umbral_bajo}) — Período {reporte.periodo}, {reporte.anio_lectivo}"])
    hoja_riesgo.append([])
    hoja_riesgo.append(["Sede", "Grupo", "Estudiante", "Documento", "Notas bajas", "Áreas bajas", "Promedio"])
    for celda in hoja_riesgo[3]:
        celda.font = Font(bold=True)
    for e in reporte.estudiantes_en_riesgo:
        hoja_riesgo.append([
            e.sede_nombre, e.nombre_grupo, e.nombre_completo, e.documento,
            e.cantidad_notas_bajas, ", ".join(e.areas_bajas), e.promedio,
        ])
    for columna, ancho in zip(hoja_riesgo.columns, [22, 16, 30, 14, 12, 30, 10]):
        hoja_riesgo.column_dimensions[columna[0].column_letter].width = ancho

    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()
