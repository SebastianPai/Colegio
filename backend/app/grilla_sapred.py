"""Vista de notas tipo SAPRED: estudiante por fila, área por columna, la
nota real (o un marcador claro de qué falta) en cada celda — el mismo
formato que ya conoce la secretaría del reporte de SAPRED, pero navegable
desde la app y con acción directa sobre lo que falta.

No reemplaza nada de lo que ya existe (PendienteBoletin, NotaSapred,
RevisionBoletin): solo los lee y los organiza en forma de tabla. No inventa
estudiantes, áreas ni notas — si una combinación no se ha auditado contra
SAPRED, la fila queda marcada "sin_auditar", nunca con una nota o falta
supuesta.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas


def grilla_notas(
    db: Session,
    sede_id: int,
    grado: int,
    periodo: int,
    anio_lectivo: int,
    curso: int | None = None,
) -> list[schemas.GrillaGrupo]:
    sede = db.get(models.Sede, sede_id)
    if sede is None:
        raise ValueError(f"Sede {sede_id} no encontrada")

    consulta_estudiantes = select(models.Estudiante).where(
        models.Estudiante.sede_id == sede_id,
        models.Estudiante.grado == grado,
        models.Estudiante.estado == "ACTIVO",
    )
    if curso is not None:
        consulta_estudiantes = consulta_estudiantes.where(models.Estudiante.curso == curso)
    estudiantes = db.scalars(consulta_estudiantes).all()

    estudiantes_por_curso: dict[int | None, list[models.Estudiante]] = {}
    for e in estudiantes:
        estudiantes_por_curso.setdefault(e.curso, []).append(e)

    nombre_grado = models.GRADOS_NOMBRES.get(grado, str(grado))

    todas_asignaciones = db.scalars(
        select(models.AsignacionDocente).where(
            models.AsignacionDocente.sede_id == sede_id,
            models.AsignacionDocente.grado == grado,
            models.AsignacionDocente.anio_lectivo == anio_lectivo,
        )
    ).all()
    asignaciones = {
        (a.sede_id, a.grado, a.curso): a for a in todas_asignaciones if a.area_id is None
    }
    # Profesor por materia (del "Boletín informativo"): (curso, area_id) -> docente
    docente_por_area = {
        (a.curso, a.area_id): a.docente for a in todas_asignaciones if a.area_id is not None
    }

    def _grilla_area(area: models.Area, curso_valor: int | None) -> schemas.GrillaArea:
        docente = docente_por_area.get((curso_valor, area.id))
        return schemas.GrillaArea(
            id=area.id, codigo=area.codigo, nombre=area.nombre,
            docente=schemas.Docente.model_validate(docente) if docente else None,
        )

    # OJO: antes esto traía TODAS las áreas configuradas para el grado a
    # nivel de todo el colegio (AreaGrado es una tabla global, no por sede).
    # Cada sede rural arma su propio currículo en SAPRED a su manera — dos
    # sedes pueden usar códigos de área distintos para lo mismo (ej. una
    # usa "COG" y otra "DICOG" para la misma dimensión de preescolar), y no
    # hay forma confiable de saber automáticamente que son "la misma
    # materia" sin adivinar. Mezclar la lista global hacía que el grid de
    # una sede mostrara columnas vacías de materias que en realidad son de
    # OTRA sede — pareciendo pendientes que no existen ahí.
    #
    # Por eso ahora se arma la lista de áreas de forma específica a este
    # sede+grado: lo que este sede+grado ha usado alguna vez (cualquier
    # período/año, vía notas o pendientes ya generados) más lo que tenga
    # asignación de docente por materia (secundaria departamentalizada). No
    # se inventa nada que este sede+grado no haya tenido nunca.
    ids_areas_historicas_sede: set[int] = set(
        a
        for (a,) in db.execute(
            select(models.NotaSapred.area_id)
            .join(models.RevisionBoletin, models.RevisionBoletin.id == models.NotaSapred.revision_id)
            .where(models.RevisionBoletin.sede_id == sede_id, models.RevisionBoletin.grado == grado)
            .distinct()
        ).all()
    ) | set(
        a
        for (a,) in db.execute(
            select(models.PendienteBoletin.area_id)
            .join(models.RevisionBoletin, models.RevisionBoletin.id == models.PendienteBoletin.revision_id)
            .where(
                models.RevisionBoletin.sede_id == sede_id,
                models.RevisionBoletin.grado == grado,
                models.PendienteBoletin.area_id.is_not(None),
            )
            .distinct()
        ).all()
    )

    grupos: list[schemas.GrillaGrupo] = []
    for curso_valor in sorted(estudiantes_por_curso.keys(), key=lambda c: (c is None, c)):
        lista_estudiantes = sorted(
            estudiantes_por_curso[curso_valor],
            key=lambda e: (e.primer_apellido, e.segundo_apellido or "", e.primer_nombre),
        )

        revision = db.scalar(
            select(models.RevisionBoletin).where(
                models.RevisionBoletin.sede_id == sede_id,
                models.RevisionBoletin.grado == grado,
                models.RevisionBoletin.curso == curso_valor,
                models.RevisionBoletin.anio_lectivo == anio_lectivo,
                models.RevisionBoletin.periodo == periodo,
            )
        )

        notas: dict[tuple[int, int], str] = {}
        pendientes_individuales: dict[tuple[int, int], models.PendienteBoletin] = {}
        pendientes_grupales: dict[int, models.PendienteBoletin] = {}
        ids_areas_con_actividad: set[int] = set()

        # Boletín informativo: texto y pendientes de concepto (por área) y de
        # observación (por estudiante, sin área).
        conceptos_texto: dict[tuple[int, int], str | None] = {}
        conceptos_fila_existe: set[tuple[int, int]] = set()
        conceptos_pend_individual: dict[tuple[int, int], models.PendienteBoletin] = {}
        conceptos_pend_grupal: dict[int, models.PendienteBoletin] = {}
        observ_texto: dict[int, str | None] = {}
        observ_fila_existe: set[int] = set()
        observ_pend: dict[int, models.PendienteBoletin] = {}
        boletin_importado = False

        if revision is not None:
            for revision_id, area_id, estudiante_id, valor in db.execute(
                select(
                    models.NotaSapred.revision_id,
                    models.NotaSapred.area_id,
                    models.NotaSapred.estudiante_id,
                    models.NotaSapred.valor,
                ).where(models.NotaSapred.revision_id == revision.id)
            ).all():
                notas[(estudiante_id, area_id)] = valor
                ids_areas_con_actividad.add(area_id)

            for pendiente in db.scalars(
                select(models.PendienteBoletin).where(
                    models.PendienteBoletin.revision_id == revision.id,
                )
            ).all():
                if pendiente.tipo == "nota" and pendiente.area_id is not None:
                    ids_areas_con_actividad.add(pendiente.area_id)
                    if pendiente.estudiante_id is not None:
                        pendientes_individuales[(pendiente.estudiante_id, pendiente.area_id)] = pendiente
                    else:
                        pendientes_grupales[pendiente.area_id] = pendiente
                elif pendiente.tipo == "concepto" and pendiente.area_id is not None:
                    boletin_importado = True
                    ids_areas_con_actividad.add(pendiente.area_id)
                    if pendiente.estudiante_id is not None:
                        conceptos_pend_individual[(pendiente.estudiante_id, pendiente.area_id)] = pendiente
                    else:
                        conceptos_pend_grupal[pendiente.area_id] = pendiente
                elif pendiente.tipo == "observacion" and pendiente.estudiante_id is not None:
                    boletin_importado = True
                    observ_pend[pendiente.estudiante_id] = pendiente

            for t in db.scalars(
                select(models.TextoBoletin).where(models.TextoBoletin.revision_id == revision.id)
            ).all():
                boletin_importado = True
                if t.tipo == "concepto" and t.area_id is not None:
                    ids_areas_con_actividad.add(t.area_id)
                    conceptos_texto[(t.estudiante_id, t.area_id)] = t.texto
                    conceptos_fila_existe.add((t.estudiante_id, t.area_id))
                elif t.tipo == "observacion":
                    observ_texto[t.estudiante_id] = t.texto
                    observ_fila_existe.add(t.estudiante_id)

        # Columnas: lo que este sede+grado ha usado alguna vez (histórico),
        # más las materias con docente asignado por área en este grupo
        # puntual, más cualquier área con actividad en la revisión actual —
        # todo específico a este sede+grado, nunca la lista global de otras
        # sedes (ver comentario más arriba).
        ids_areas_asignadas_grupo = {
            area_id for (curso_asig, area_id) in docente_por_area if curso_asig == curso_valor
        }
        ids_areas_grupo = ids_areas_historicas_sede | ids_areas_asignadas_grupo | ids_areas_con_actividad
        areas_grupo: dict[int, schemas.GrillaArea] = {}
        for area_id in ids_areas_grupo:
            area = db.get(models.Area, area_id)
            if area is not None:
                areas_grupo[area_id] = _grilla_area(area, curso_valor)
        lista_areas = sorted(areas_grupo.values(), key=lambda a: a.codigo)

        def _estado_concepto(estudiante_id: int, area_id: int) -> tuple[str, str | None, int | None]:
            if revision is None or not boletin_importado:
                return "sin_auditar", None, None
            texto = conceptos_texto.get((estudiante_id, area_id))
            if texto:
                return "tiene", texto, None
            pend = conceptos_pend_individual.get((estudiante_id, area_id)) or conceptos_pend_grupal.get(area_id)
            if pend is not None:
                return ("revisado" if pend.resuelto else "falta"), None, pend.id
            if (estudiante_id, area_id) in conceptos_fila_existe:
                return "falta", None, None
            return "sin_dato", None, None

        filas: list[schemas.GrillaFila] = []
        for e in lista_estudiantes:
            celdas: dict[int, schemas.GrillaCelda] = {}
            for area in lista_areas:
                if revision is None:
                    celdas[area.id] = schemas.GrillaCelda(estado="sin_auditar")
                    continue
                c_estado, c_texto, c_pend = _estado_concepto(e.id, area.id)
                base = dict(concepto_estado=c_estado, concepto_texto=c_texto, concepto_pendiente_id=c_pend)
                valor = notas.get((e.id, area.id))
                if valor is not None:
                    celdas[area.id] = schemas.GrillaCelda(valor=valor, estado="nota", **base)
                    continue
                pendiente = pendientes_individuales.get((e.id, area.id)) or pendientes_grupales.get(area.id)
                if pendiente is not None:
                    celdas[area.id] = schemas.GrillaCelda(
                        estado="revisado" if pendiente.resuelto else "falta",
                        pendiente_id=pendiente.id, **base,
                    )
                    continue
                celdas[area.id] = schemas.GrillaCelda(estado="sin_dato", **base)

            if revision is None or not boletin_importado:
                o_estado, o_texto, o_pend = "sin_auditar", None, None
            elif observ_texto.get(e.id):
                o_estado, o_texto, o_pend = "tiene", observ_texto[e.id], None
            elif e.id in observ_pend:
                pend = observ_pend[e.id]
                o_estado, o_texto, o_pend = ("revisado" if pend.resuelto else "falta"), None, pend.id
            elif e.id in observ_fila_existe:
                o_estado, o_texto, o_pend = "falta", None, None
            else:
                o_estado, o_texto, o_pend = "sin_dato", None, None

            filas.append(
                schemas.GrillaFila(
                    estudiante_id=e.id,
                    documento=e.documento,
                    nombre_completo=e.nombre_completo,
                    posible_retirado=bool(e.posible_retirado),
                    retirado=bool(e.retirado),
                    celdas=celdas,
                    observacion_estado=o_estado,
                    observacion_texto=o_texto,
                    observacion_pendiente_id=o_pend,
                )
            )

        asignacion = asignaciones.get((sede_id, grado, curso_valor))
        nombre_grupo = (
            f"{nombre_grado} - {models.DIVISIONES_NOMBRES.get(curso_valor, curso_valor)}"
            if curso_valor
            else nombre_grado
        )

        grupos.append(
            schemas.GrillaGrupo(
                sede_id=sede_id,
                sede_nombre=sede.nombre,
                grado=grado,
                nombre_grado=nombre_grado,
                curso=curso_valor,
                nombre_grupo=nombre_grupo,
                periodo=periodo,
                anio_lectivo=anio_lectivo,
                auditado=revision is not None,
                docente=schemas.Docente.model_validate(asignacion.docente) if asignacion else None,
                areas=lista_areas,
                filas=filas,
            )
        )

    return grupos
