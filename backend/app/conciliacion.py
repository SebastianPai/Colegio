"""Conciliación SIMAC ↔ SAPRED: compara la base local de matrícula (lo que
en esta app se conoce como "SIMAC", la tabla Estudiante — ver el docstring
de EstudianteSapredSinCoincidencia en models.py) contra lo que SAPRED
reporta para el mismo año/período (NotaSapred/RevisionBoletin, ya sea
importado por PDF o por la auditoría de navegador, y
EstudianteSapredSinCoincidencia para los que SAPRED reporta pero no calzan
por documento).

No es una fuente de datos nueva: solo lee lo que ya existe y lo clasifica.
La clasificación en sí no se guarda — se recalcula cada vez que se pide, a
partir del estado actual de la base de datos.

La EXCEPCIÓN es la diferencia de grupo (SIMAC dice un grado/curso, SAPRED
dice otro): esa sí se registra en hallazgos_conciliacion (ver
_sincronizar_hallazgos), porque si solo viviera en el cálculo en vivo,
corregir el dato (o simplemente cambiar de filtro) haría desaparecer el
caso sin dejar rastro de que existió, cuándo se detectó o si alguien ya lo
revisó — justo lo que se necesita para planear promociones anticipadas de
un año a otro.
"""

import datetime as dt
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas
from .importador_sapred import normalizar as normalizar_texto


def normalizar_documento(documento: str | None) -> str:
    """Dos documentos como "12345678" y "12.345.678" (o con ceros a la
    izquierda) deben considerarse el mismo estudiante: se dejan solo los
    dígitos y se quitan los ceros iniciales. No es una regla inventada para
    esta función sola — es la falta que señala la regla 18 del pedido: hoy
    ningún otro punto de la app normaliza documento antes de compararlo."""
    if not documento:
        return ""
    solo_digitos = re.sub(r"\D", "", documento)
    return solo_digitos.lstrip("0") or solo_digitos


def _nombre_grupo(grado: int, curso: int | None) -> str:
    nombre_grado = models.GRADOS_NOMBRES.get(grado, str(grado))
    if curso:
        return f"{nombre_grado} - {models.DIVISIONES_NOMBRES.get(curso, curso)}"
    return nombre_grado


def conciliar(
    db: Session,
    anio_lectivo: int,
    periodo: int,
    sede_id: int | None = None,
    grado: int | None = None,
) -> schemas.ConciliacionResultado:
    sedes = {s.id: s for s in db.scalars(select(models.Sede)).all()}
    sedes_ietaba_ids = {s.id for s in sedes.values() if s.pertenece_ietaba}

    # Una sola lectura de toda la tabla de estudiantes: sirve tanto para el
    # lado SIMAC (filtrado) como para el índice por documento normalizado
    # que se usa más abajo, evitando una segunda consulta idéntica.
    todos_estudiantes = db.scalars(select(models.Estudiante)).all()
    documentos_simac_norm: dict[str, models.Estudiante] = {}
    for e in todos_estudiantes:
        documentos_simac_norm.setdefault(normalizar_documento(e.documento), e)

    estudiantes_simac = [
        e
        for e in todos_estudiantes
        if e.estado == "ACTIVO"
        and e.sede_id in sedes_ietaba_ids
        and (sede_id is None or e.sede_id == sede_id)
        and (grado is None or e.grado == grado)
    ]

    # --- Evidencia SAPRED: revisiones de este año/período, con sus notas ---
    # OJO: no se filtra por "grado" aquí aunque el reporte lo esté mirando —
    # un estudiante puede estar mal matriculado en SIMAC (ej. figura en Sexto
    # cuando SAPRED, la fuente oficial, lo tiene en Séptimo). Si la evidencia
    # SAPRED se restringiera al mismo grado que se está filtrando, ese caso
    # nunca se encontraría (la nota vive en la revisión de Séptimo) y el
    # estudiante saldría como "solo_simac" en vez de "diferencia" — ocultando
    # justo el dato que se necesita (a qué grupo pertenece según SAPRED).
    consulta_revisiones = select(models.RevisionBoletin).where(
        models.RevisionBoletin.anio_lectivo == anio_lectivo,
        models.RevisionBoletin.periodo == periodo,
    )
    if sede_id is not None:
        consulta_revisiones = consulta_revisiones.where(models.RevisionBoletin.sede_id == sede_id)
    revisiones = {r.id: r for r in db.scalars(consulta_revisiones).all()}

    evidencia_sapred: dict[int, dict] = {}  # estudiante_id -> {revision, nombre_sapred, actualizado_en}
    if revisiones:
        notas = db.scalars(
            select(models.NotaSapred).where(models.NotaSapred.revision_id.in_(revisiones.keys()))
        ).all()
        for n in notas:
            actual = evidencia_sapred.get(n.estudiante_id)
            if actual is None or n.actualizado_en >= actual["actualizado_en"]:
                evidencia_sapred[n.estudiante_id] = {
                    "revision": revisiones[n.revision_id],
                    "nombre_sapred": n.nombre_sapred,
                    "actualizado_en": n.actualizado_en,
                }

    # --- Director de grupo: asignación de TODO el grupo (area_id NULL) ----
    asignaciones = {
        (a.sede_id, a.grado, a.curso): a
        for a in db.scalars(
            select(models.AsignacionDocente).where(
                models.AsignacionDocente.anio_lectivo == anio_lectivo,
                models.AsignacionDocente.area_id.is_(None),
            )
        ).all()
    }

    grupos_acc: dict[tuple[int, int, int | None], dict] = {}

    def _acc_grupo(sede_id_: int, grado_: int, curso_: int | None) -> dict:
        clave = (sede_id_, grado_, curso_)
        if clave not in grupos_acc:
            asignacion = asignaciones.get(clave)
            sede = sedes.get(sede_id_)
            grupos_acc[clave] = {
                "sede_id": sede_id_,
                "sede_nombre": sede.nombre if sede else "",
                "grado": grado_,
                "curso": curso_,
                "docente": asignacion.docente if asignacion else None,
                "total_simac": 0, "total_sapred": 0,
                "coinciden": 0, "solo_simac": 0, "solo_sapred": 0, "diferencias": 0,
            }
        return grupos_acc[clave]

    estudiantes_resultado: list[schemas.ConciliacionEstudiante] = []
    # Diferencias de grupo encontradas en esta corrida: alimentan el
    # historial persistente de hallazgos_conciliacion (ver
    # _sincronizar_hallazgos más abajo) — la conciliación en sí no guarda
    # nada, pero esto sí, para no perder de vista casos como este aunque se
    # corrija el dato o cambie el filtro con el que se mira el reporte.
    hallazgos_grupo: list[dict] = []

    for e in estudiantes_simac:
        grupo = _acc_grupo(e.sede_id, e.grado, e.curso)
        grupo["total_simac"] += 1
        docente_nombre = grupo["docente"].nombre_completo if grupo["docente"] else None
        info = evidencia_sapred.get(e.id)

        if info is None:
            grupo["solo_simac"] += 1
            estudiantes_resultado.append(
                schemas.ConciliacionEstudiante(
                    estudiante_id=e.id, documento=e.documento, nombre_completo=e.nombre_completo,
                    sede_id=e.sede_id, sede_nombre=grupo["sede_nombre"],
                    grado=e.grado, nombre_grado=models.GRADOS_NOMBRES.get(e.grado, str(e.grado)),
                    curso=e.curso, nombre_grupo=_nombre_grupo(e.grado, e.curso),
                    docente=docente_nombre, estado_conciliacion="solo_simac", diferencias=[],
                )
            )
            continue

        grupo["total_sapred"] += 1
        revision = info["revision"]
        diferencias: list[schemas.ConciliacionDiferencia] = []
        candidato_promocion = False
        if revision.grado != e.grado or revision.curso != e.curso:
            diferencias.append(
                schemas.ConciliacionDiferencia(
                    campo="grupo",
                    valor_simac=_nombre_grupo(e.grado, e.curso),
                    valor_sapred=_nombre_grupo(revision.grado, revision.curso),
                )
            )
            # SAPRED refleja el grupo donde el estudiante realmente está
            # tomando clase (el profesor le pone notas ahí); si ese grado es
            # MAYOR al que tiene SIMAC, no es un simple error de digitación —
            # es un caso de promoción ya ocurrida en la práctica que la
            # matrícula (SIMAC) todavía no refleja, y hay que corregirla en
            # la matrícula del siguiente año (promoción anticipada), no solo
            # actualizar el dato.
            candidato_promocion = revision.grado > e.grado
            hallazgos_grupo.append(
                {
                    "estudiante_id": e.id,
                    "sede_id": e.sede_id,
                    "grado_simac": e.grado,
                    "curso_simac": e.curso,
                    "grado_sapred": revision.grado,
                    "curso_sapred": revision.curso,
                    "es_promocion_anticipada": candidato_promocion,
                }
            )
        nombre_sapred = info["nombre_sapred"]
        if nombre_sapred and normalizar_texto(nombre_sapred) != normalizar_texto(e.nombre_completo):
            diferencias.append(
                schemas.ConciliacionDiferencia(
                    campo="nombre", valor_simac=e.nombre_completo, valor_sapred=nombre_sapred,
                )
            )

        if diferencias:
            grupo["diferencias"] += 1
        else:
            grupo["coinciden"] += 1

        estudiantes_resultado.append(
            schemas.ConciliacionEstudiante(
                estudiante_id=e.id, documento=e.documento, nombre_completo=e.nombre_completo,
                sede_id=e.sede_id, sede_nombre=grupo["sede_nombre"],
                grado=e.grado, nombre_grado=models.GRADOS_NOMBRES.get(e.grado, str(e.grado)),
                curso=e.curso, nombre_grupo=_nombre_grupo(e.grado, e.curso),
                docente=docente_nombre,
                estado_conciliacion="diferencia" if diferencias else "coincide",
                diferencias=diferencias,
                candidato_promocion_anticipada=candidato_promocion,
            )
        )

    # --- Solo SAPRED: documentos que SAPRED reporta y no calzan en SIMAC ---
    # (ya detectado y guardado por el importador en EstudianteSapredSinCoincidencia;
    # aquí solo se revalida con el documento normalizado para no marcar como
    # huérfano a alguien que sí existe pero con el documento en otro formato).
    consulta_sin_coincidencia = select(models.EstudianteSapredSinCoincidencia).where(
        models.EstudianteSapredSinCoincidencia.anio_lectivo == anio_lectivo,
        models.EstudianteSapredSinCoincidencia.periodo == periodo,
    )
    if sede_id is not None:
        consulta_sin_coincidencia = consulta_sin_coincidencia.where(
            models.EstudianteSapredSinCoincidencia.sede_id == sede_id
        )
    if grado is not None:
        consulta_sin_coincidencia = consulta_sin_coincidencia.where(
            models.EstudianteSapredSinCoincidencia.grado == grado
        )

    for s in db.scalars(consulta_sin_coincidencia).all():
        sede = sedes.get(s.sede_id)
        if sede is None or not sede.pertenece_ietaba:
            continue
        grupo = _acc_grupo(s.sede_id, s.grado, s.curso)
        docente_nombre = grupo["docente"].nombre_completo if grupo["docente"] else None

        posible_local = documentos_simac_norm.get(normalizar_documento(s.documento))
        if posible_local is not None and posible_local.sede_id == s.sede_id:
            # Mismo estudiante, documento con formato distinto (puntos,
            # ceros a la izquierda) — es una diferencia, no un huérfano real.
            grupo["total_sapred"] += 1
            grupo["diferencias"] += 1
            estudiantes_resultado.append(
                schemas.ConciliacionEstudiante(
                    estudiante_id=posible_local.id, documento=posible_local.documento,
                    nombre_completo=posible_local.nombre_completo,
                    sede_id=posible_local.sede_id, sede_nombre=grupo["sede_nombre"],
                    grado=posible_local.grado,
                    nombre_grado=models.GRADOS_NOMBRES.get(posible_local.grado, str(posible_local.grado)),
                    curso=posible_local.curso, nombre_grupo=_nombre_grupo(posible_local.grado, posible_local.curso),
                    docente=docente_nombre, estado_conciliacion="diferencia",
                    diferencias=[
                        schemas.ConciliacionDiferencia(
                            campo="documento", valor_simac=posible_local.documento, valor_sapred=s.documento,
                        )
                    ],
                )
            )
            continue

        grupo["total_sapred"] += 1
        grupo["solo_sapred"] += 1
        estudiantes_resultado.append(
            schemas.ConciliacionEstudiante(
                estudiante_id=None, documento=s.documento, nombre_completo=s.nombre_sapred,
                sede_id=s.sede_id, sede_nombre=grupo["sede_nombre"],
                grado=s.grado, nombre_grado=models.GRADOS_NOMBRES.get(s.grado, str(s.grado)),
                curso=s.curso, nombre_grupo=_nombre_grupo(s.grado, s.curso),
                docente=docente_nombre, estado_conciliacion="solo_sapred", diferencias=[],
            )
        )

    estudiantes_resultado.sort(key=lambda r: (r.sede_nombre, r.grado or 0, r.curso or 0, r.nombre_completo))

    grupos: list[schemas.ConciliacionGrupo] = []
    for (sede_id_, grado_, curso_), g in grupos_acc.items():
        requiere_revision = g["solo_simac"] > 0 or g["solo_sapred"] > 0 or g["diferencias"] > 0
        grupos.append(
            schemas.ConciliacionGrupo(
                sede_id=sede_id_, sede_nombre=g["sede_nombre"], grado=grado_,
                nombre_grado=models.GRADOS_NOMBRES.get(grado_, str(grado_)), curso=curso_,
                nombre_grupo=_nombre_grupo(grado_, curso_),
                docente=g["docente"].nombre_completo if g["docente"] else None,
                total_simac=g["total_simac"], total_sapred=g["total_sapred"],
                coinciden=g["coinciden"], solo_simac=g["solo_simac"], solo_sapred=g["solo_sapred"],
                diferencias=g["diferencias"],
                estado="requiere_revision" if requiere_revision else "correcto",
            )
        )
    grupos.sort(key=lambda g: (g.sede_nombre, g.grado, g.curso or 0))

    docentes_map: dict[int | None, dict] = {}
    for clave_grupo, g in grupos_acc.items():
        docente = g["docente"]
        clave_docente = docente.id if docente else None
        bucket = docentes_map.setdefault(
            clave_docente, {"nombre": docente.nombre_completo if docente else "Sin director asignado", "grupos": []}
        )
        bucket["grupos"].append(clave_grupo)

    grupos_por_clave = {(g.sede_id, g.grado, g.curso): g for g in grupos}
    docentes: list[schemas.ConciliacionDocente] = []
    for docente_id, info in docentes_map.items():
        grupos_docente = [grupos_por_clave[c] for c in info["grupos"]]
        docentes.append(
            schemas.ConciliacionDocente(
                docente_id=docente_id, nombre_completo=info["nombre"], grupos=grupos_docente,
                total_diferencias=sum(gr.diferencias + gr.solo_simac + gr.solo_sapred for gr in grupos_docente),
            )
        )
    docentes.sort(key=lambda d: (-d.total_diferencias, d.nombre_completo))

    coinciden = sum(1 for r in estudiantes_resultado if r.estado_conciliacion == "coincide")
    solo_simac = sum(1 for r in estudiantes_resultado if r.estado_conciliacion == "solo_simac")
    solo_sapred = sum(1 for r in estudiantes_resultado if r.estado_conciliacion == "solo_sapred")
    diferencias_total = sum(1 for r in estudiantes_resultado if r.estado_conciliacion == "diferencia")
    base = coinciden + solo_simac + solo_sapred + diferencias_total
    calidad_pct = round((coinciden / base) * 100, 1) if base else 0.0

    resumen = schemas.ConciliacionResumen(
        anio_lectivo=anio_lectivo, periodo=periodo,
        total_simac=len(estudiantes_simac),
        total_sapred=sum(g.total_sapred for g in grupos),
        coinciden=coinciden, solo_simac=solo_simac, solo_sapred=solo_sapred, diferencias=diferencias_total,
        grupos_con_inconsistencias=sum(1 for g in grupos if g.estado == "requiere_revision"),
        docentes_pendientes=sum(1 for d in docentes if d.total_diferencias > 0),
        calidad_pct=calidad_pct,
        candidatos_promocion_anticipada=sum(1 for r in estudiantes_resultado if r.candidato_promocion_anticipada),
    )

    _sincronizar_hallazgos(
        db, anio_lectivo, periodo,
        hallazgos_actuales=hallazgos_grupo,
        ids_en_alcance={e.id for e in estudiantes_simac},
    )

    return schemas.ConciliacionResultado(
        generado_en=dt.datetime.now(), resumen=resumen,
        estudiantes=estudiantes_resultado, grupos=grupos, docentes=docentes,
    )


def _sincronizar_hallazgos(
    db: Session,
    anio_lectivo: int,
    periodo: int,
    hallazgos_actuales: list[dict],
    ids_en_alcance: set[int],
) -> None:
    """Registra cada diferencia de grupo detectada AHORA (crea el hallazgo
    la primera vez, o le actualiza "visto_en" y los valores si seguía sin
    resolver) y cierra solos los que ya no aplican porque el dato se
    corrigió — sin borrarlos, para que quede el historial.

    "ids_en_alcance" son los estudiantes que esta corrida realmente revisó
    (respeta los filtros de sede/grado con los que se pidió la
    conciliación): un hallazgo de un estudiante FUERA de ese alcance no se
    toca, para no cerrarlo por error solo porque el reporte se miró filtrado
    a otro grado."""
    actuales_por_id = {h["estudiante_id"]: h for h in hallazgos_actuales}
    existentes = {
        h.estudiante_id: h
        for h in db.scalars(
            select(models.HallazgoConciliacion).where(
                models.HallazgoConciliacion.anio_lectivo == anio_lectivo,
                models.HallazgoConciliacion.periodo == periodo,
                models.HallazgoConciliacion.estudiante_id.in_(ids_en_alcance),
            )
        ).all()
    }
    ahora = dt.datetime.utcnow()

    for estudiante_id, datos in actuales_por_id.items():
        existente = existentes.get(estudiante_id)
        if existente is None:
            db.add(
                models.HallazgoConciliacion(
                    estudiante_id=estudiante_id, anio_lectivo=anio_lectivo, periodo=periodo,
                    sede_id=datos["sede_id"], grado_simac=datos["grado_simac"], curso_simac=datos["curso_simac"],
                    grado_sapred=datos["grado_sapred"], curso_sapred=datos["curso_sapred"],
                    es_promocion_anticipada=datos["es_promocion_anticipada"],
                    detectado_en=ahora, visto_en=ahora,
                )
            )
        elif not existente.resuelto:
            existente.visto_en = ahora
            existente.sede_id = datos["sede_id"]
            existente.grado_simac, existente.curso_simac = datos["grado_simac"], datos["curso_simac"]
            existente.grado_sapred, existente.curso_sapred = datos["grado_sapred"], datos["curso_sapred"]
            existente.es_promocion_anticipada = datos["es_promocion_anticipada"]
        # si ya estaba resuelto y la diferencia reapareció, se deja como
        # historial cerrado — no se reabre sola, eso lo decide una persona.

    for estudiante_id, h in existentes.items():
        if not h.resuelto and estudiante_id not in actuales_por_id:
            h.resuelto = True
            h.resuelto_en = ahora
            h.resuelto_por = "Automático"
            nota_cierre = "Cerrado automáticamente: SIMAC y SAPRED ya coinciden."
            h.nota = f"{h.nota} · {nota_cierre}" if h.nota else nota_cierre

    db.commit()


def _hallazgo_a_schema(h: models.HallazgoConciliacion) -> schemas.HallazgoConciliacion:
    return schemas.HallazgoConciliacion(
        id=h.id, estudiante_id=h.estudiante_id,
        documento=h.estudiante.documento, nombre_completo=h.estudiante.nombre_completo,
        sede_id=h.sede_id, sede_nombre=h.sede.nombre if h.sede else "",
        anio_lectivo=h.anio_lectivo, periodo=h.periodo,
        grado_simac=h.grado_simac, curso_simac=h.curso_simac,
        nombre_grupo_simac=_nombre_grupo(h.grado_simac, h.curso_simac),
        grado_sapred=h.grado_sapred, curso_sapred=h.curso_sapred,
        nombre_grupo_sapred=_nombre_grupo(h.grado_sapred, h.curso_sapred),
        es_promocion_anticipada=h.es_promocion_anticipada,
        detectado_en=h.detectado_en, visto_en=h.visto_en,
        resuelto=h.resuelto, resuelto_en=h.resuelto_en, resuelto_por=h.resuelto_por, nota=h.nota,
    )


def listar_hallazgos(
    db: Session,
    anio_lectivo: int | None = None,
    periodo: int | None = None,
    sede_id: int | None = None,
    grado: int | None = None,
    incluir_resueltos: bool = False,
) -> list[schemas.HallazgoConciliacion]:
    """Grilla de hallazgos de grupo (SIMAC ↔ SAPRED) para Reportes →
    Conciliación → Grilla: a diferencia de conciliar(), esto SÍ lee del
    historial persistente (hallazgos_conciliacion), así que sigue mostrando
    los casos ya corregidos si se pide "incluir resueltos", en vez de que
    desaparezcan sin dejar rastro."""
    consulta = select(models.HallazgoConciliacion)
    if anio_lectivo is not None:
        consulta = consulta.where(models.HallazgoConciliacion.anio_lectivo == anio_lectivo)
    if periodo is not None:
        consulta = consulta.where(models.HallazgoConciliacion.periodo == periodo)
    if sede_id is not None:
        consulta = consulta.where(models.HallazgoConciliacion.sede_id == sede_id)
    if grado is not None:
        consulta = consulta.where(models.HallazgoConciliacion.grado_simac == grado)
    if not incluir_resueltos:
        consulta = consulta.where(models.HallazgoConciliacion.resuelto.is_(False))

    resultado = [_hallazgo_a_schema(h) for h in db.scalars(consulta).all()]
    resultado.sort(key=lambda h: (h.sede_nombre, h.grado_simac, h.curso_simac or 0, h.nombre_completo))
    return resultado


def resolver_hallazgo(
    db: Session, hallazgo_id: int, resuelto_por: str | None, nota: str | None
) -> schemas.HallazgoConciliacion | None:
    hallazgo = db.get(models.HallazgoConciliacion, hallazgo_id)
    if hallazgo is None:
        return None
    hallazgo.resuelto = True
    hallazgo.resuelto_en = dt.datetime.utcnow()
    hallazgo.resuelto_por = resuelto_por or "Sin especificar"
    if nota:
        hallazgo.nota = nota
    db.commit()
    return _hallazgo_a_schema(hallazgo)


def reabrir_hallazgo(db: Session, hallazgo_id: int) -> schemas.HallazgoConciliacion | None:
    hallazgo = db.get(models.HallazgoConciliacion, hallazgo_id)
    if hallazgo is None:
        return None
    hallazgo.resuelto = False
    hallazgo.resuelto_en = None
    hallazgo.resuelto_por = None
    db.commit()
    return _hallazgo_a_schema(hallazgo)


def exportar_conciliacion_excel(resultado: schemas.ConciliacionResultado) -> bytes:
    import io

    import openpyxl
    from openpyxl.styles import Font

    ETIQUETAS_ESTADO = {
        "solo_simac": "Solo SIMAC",
        "solo_sapred": "Solo SAPRED",
        "diferencia": "Diferencia",
    }

    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "Inconsistencias"
    hoja.append([
        f"Conciliación SIMAC ↔ SAPRED — Período {resultado.resumen.periodo}, {resultado.resumen.anio_lectivo}"
    ])
    hoja.append([f"Calidad de conciliación: {resultado.resumen.calidad_pct}%"])
    hoja.append([])
    encabezados = [
        "Estado", "Documento", "Estudiante", "Grado", "Grupo", "Director",
        "Dato diferente", "Valor SIMAC", "Valor SAPRED", "Posible promoción anticipada",
    ]
    hoja.append(encabezados)
    for celda in hoja[hoja.max_row]:
        celda.font = Font(bold=True)

    for e in resultado.estudiantes:
        if e.estado_conciliacion == "coincide":
            continue
        etiqueta = ETIQUETAS_ESTADO.get(e.estado_conciliacion, e.estado_conciliacion)
        promocion = "Sí — corregir en la matrícula del siguiente año" if e.candidato_promocion_anticipada else ""
        if e.diferencias:
            for d in e.diferencias:
                hoja.append([
                    etiqueta, e.documento, e.nombre_completo, e.nombre_grado, e.nombre_grupo,
                    e.docente or "Sin asignar", d.campo, d.valor_simac, d.valor_sapred, promocion,
                ])
        else:
            hoja.append([
                etiqueta, e.documento, e.nombre_completo, e.nombre_grado, e.nombre_grupo,
                e.docente or "Sin asignar", "-", "-", "-", promocion,
            ])

    for columna, ancho in zip(hoja.columns, [14, 14, 30, 12, 16, 26, 14, 20, 20, 34]):
        hoja.column_dimensions[columna[0].column_letter].width = ancho

    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()
