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


def reporte_tendencia(
    db: Session,
    anio_lectivo: int,
    sede_id: int | None = None,
    grado: int | None = None,
    umbral_bajo: float = 3.0,
    periodos_minimo: int = 2,
) -> schemas.ReporteTendencia:
    """A diferencia de reporte_notas() (que mira UN período), esto mira TODOS
    los períodos del año para el mismo estudiante+área: el caso que describe
    la secretaría es notas altas y estables (4.0, 4.2...) que no preocupan,
    frente a notas sostenidamente bajas (2.5, 2.4...) que si aparecen en
    TODOS los períodos evaluados sí ameritan avisar. NO decide "perdió el
    año" — eso es una nota de comportamiento/promoción que define el
    colegio con reglas propias (áreas obligatorias, recuperaciones, etc.);
    esto solo señala el patrón para que un humano lo revise, con umbral y
    cantidad mínima de períodos configurables, igual que reporte_notas()."""
    consulta = (
        select(models.NotaSapred, models.RevisionBoletin, models.Estudiante, models.Area)
        .join(models.RevisionBoletin, models.NotaSapred.revision_id == models.RevisionBoletin.id)
        .join(models.Estudiante, models.NotaSapred.estudiante_id == models.Estudiante.id)
        .join(models.Area, models.NotaSapred.area_id == models.Area.id)
        .where(
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

    # (estudiante_id, area_id) -> lista de (periodo, valor, info del grupo)
    por_combinacion: dict[tuple[int, int], list] = {}
    for nota, revision, estudiante, area in filas:
        try:
            valor_num = float(nota.valor)
        except (TypeError, ValueError):
            continue
        clave = (estudiante.id, area.id)
        por_combinacion.setdefault(clave, []).append((revision.periodo, valor_num, revision, estudiante, area))

    resultado: list[schemas.TendenciaAreaEstudiante] = []
    for entradas in por_combinacion.values():
        entradas.sort(key=lambda t: t[0])  # por período
        # Un período puede tener más de una revisión (reimportaciones); nos
        # quedamos con el último valor visto de cada período, no lo duplicamos.
        por_periodo: dict[int, float] = {}
        for periodo, valor, *_ in entradas:
            por_periodo[periodo] = valor
        if len(por_periodo) < periodos_minimo:
            continue
        valores = list(por_periodo.values())
        if not all(v <= umbral_bajo for v in valores):
            continue

        _, _, revision, estudiante, area = entradas[-1]
        sede = sedes.get(revision.sede_id)
        asignacion = asignaciones.get((revision.sede_id, revision.grado, revision.curso))
        nombre_grado = models.GRADOS_NOMBRES.get(revision.grado, str(revision.grado))
        nombre_grupo = (
            f"{nombre_grado} - {models.DIVISIONES_NOMBRES.get(revision.curso, revision.curso)}"
            if revision.curso
            else nombre_grado
        )
        resultado.append(
            schemas.TendenciaAreaEstudiante(
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
                docente=asignacion.docente.nombre_completo if asignacion else None,
                notas=[schemas.NotaPorPeriodo(periodo=p, valor=v) for p, v in sorted(por_periodo.items())],
                riesgo_sostenido=True,
            )
        )

    resultado.sort(key=lambda t: (t.nombre_completo, t.area_codigo))

    return schemas.ReporteTendencia(
        anio_lectivo=anio_lectivo,
        umbral_bajo=umbral_bajo,
        periodos_minimo=periodos_minimo,
        total_combinaciones_evaluadas=len(por_combinacion),
        en_riesgo_sostenido=resultado,
    )


def riesgo_promocion(
    db: Session, estudiante_id: int, anio_lectivo: int, nota_minima: float = 3.0
) -> schemas.RiesgoPromocion:
    """Materias que un estudiante lleva perdidas en el año: las áreas cuyo
    PROMEDIO de los períodos con nota queda por debajo de `nota_minima`
    (3.0 = mínimo de desempeño básico). Regla del colegio: una sola materia
    perdida significa año perdido. Solo mira lo que ya se importó de SAPRED;
    si aún no hay notas devuelve todo vacío (no es lo mismo que "no pierde")."""
    filas = db.execute(
        select(models.NotaSapred, models.RevisionBoletin, models.Area)
        .join(models.RevisionBoletin, models.NotaSapred.revision_id == models.RevisionBoletin.id)
        .join(models.Area, models.NotaSapred.area_id == models.Area.id)
        .where(
            models.NotaSapred.estudiante_id == estudiante_id,
            models.RevisionBoletin.anio_lectivo == anio_lectivo,
        )
    ).all()

    por_area: dict[int, dict] = {}
    periodos: set[int] = set()
    for nota, revision, area in filas:
        try:
            valor = float(nota.valor)
        except (TypeError, ValueError):
            continue
        periodos.add(revision.periodo)
        entrada = por_area.setdefault(area.id, {"area": area, "por_periodo": {}})
        entrada["por_periodo"][revision.periodo] = valor  # la última importación de cada período

    estudiante = db.get(models.Estudiante, estudiante_id)
    docentes = (
        docentes_por_area(db, estudiante.sede_id, estudiante.grado, estudiante.curso, anio_lectivo)
        if estudiante is not None and estudiante.sede_id else {}
    )
    materias = materias_desde_notas(por_area, nota_minima, docentes)
    return schemas.RiesgoPromocion(
        estudiante_id=estudiante_id,
        anio_lectivo=anio_lectivo,
        nota_minima=nota_minima,
        periodos_con_notas=sorted(periodos),
        areas_evaluadas=len(por_area),
        perdidas=[m for m in materias if m.estado == "perdida"],
        materias=materias,
    )


def estado_materia(promedio: float, nota_minima: float = 3.0) -> str:
    """perdida (< mínima) | en_riesgo (< mínima + 0.5) | aprobada."""
    return "perdida" if promedio < nota_minima else "en_riesgo" if promedio < nota_minima + 0.5 else "aprobada"


def materias_desde_notas(por_area: dict[int, dict], nota_minima: float, docentes: dict[int, str]) -> list[schemas.MateriaPerdida]:
    """por_area: {area_id: {"area": Area, "por_periodo": {periodo: valor}}} →
    materias con promedio, estado y docente, de la peor a la mejor."""
    materias: list[schemas.MateriaPerdida] = []
    for area_id, entrada in por_area.items():
        valores = list(entrada["por_periodo"].values())
        promedio = sum(valores) / len(valores)
        materias.append(
            schemas.MateriaPerdida(
                area_codigo=entrada["area"].codigo,
                area_nombre=entrada["area"].nombre,
                notas=[schemas.NotaPorPeriodo(periodo=p, valor=v) for p, v in sorted(entrada["por_periodo"].items())],
                promedio=round(promedio, 2),
                docente_nombre=docentes.get(area_id),
                estado=estado_materia(promedio, nota_minima),
            )
        )
    materias.sort(key=lambda m: m.promedio)
    return materias


def rendimiento_de_estudiantes(
    db: Session, estudiante_ids: list[int], anio_lectivo: int
) -> tuple[dict[int, dict[int, dict]], list[int]]:
    """Notas del año de VARIOS estudiantes en una sola consulta:
    ({estudiante_id: {area_id: {"area", "por_periodo"}}}, periodos con nota)."""
    if not estudiante_ids:
        return {}, []
    filas = db.execute(
        select(models.NotaSapred, models.RevisionBoletin.periodo, models.Area)
        .join(models.RevisionBoletin, models.NotaSapred.revision_id == models.RevisionBoletin.id)
        .join(models.Area, models.NotaSapred.area_id == models.Area.id)
        .where(models.NotaSapred.estudiante_id.in_(estudiante_ids), models.RevisionBoletin.anio_lectivo == anio_lectivo)
    ).all()
    resultado: dict[int, dict[int, dict]] = {}
    periodos: set[int] = set()
    for nota, periodo, area in filas:
        try:
            valor = float(nota.valor)
        except (TypeError, ValueError):
            continue
        periodos.add(periodo)
        entrada = resultado.setdefault(nota.estudiante_id, {}).setdefault(area.id, {"area": area, "por_periodo": {}})
        entrada["por_periodo"][periodo] = valor
    return resultado, sorted(periodos)


def docentes_por_area(db: Session, sede_id: int, grado: int, curso: int | None, anio_lectivo: int) -> dict[int, str]:
    """area_id -> nombre del docente que la dicta en ese grupo ese año
    (AsignacionDocente). Si hay una asignación del curso exacto, gana sobre
    una del grado completo (curso=None)."""
    filas = db.execute(
        select(models.AsignacionDocente.area_id, models.AsignacionDocente.curso, models.Docente.nombre_completo)
        .join(models.Docente, models.AsignacionDocente.docente_id == models.Docente.id)
        .where(
            models.AsignacionDocente.sede_id == sede_id,
            models.AsignacionDocente.grado == grado,
            models.AsignacionDocente.anio_lectivo == anio_lectivo,
            models.AsignacionDocente.area_id.is_not(None),
        )
    ).all()
    resultado: dict[int, str] = {}
    for area_id, curso_asig, nombre in sorted(filas, key=lambda f: f[1] is not None):
        if curso_asig is None or curso_asig == curso:
            resultado[area_id] = nombre  # las del curso exacto van al final y pisan a las del grado
    return resultado
