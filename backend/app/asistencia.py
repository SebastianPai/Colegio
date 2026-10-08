"""Asistencia por bloque de horario (o toma general del director de grupo
cuando area_id es None — misma convención que ya usan AsignacionDocente y
BloqueHorario). Sigue el mismo estilo que horario.py: la lógica de negocio
vive aquí, el router solo la expone.

Quién puede registrar un bloque en una fecha dada: el docente que el
horario tiene asignado ese día, salvo que haya un reemplazo YA ASIGNADO
para ese bloque ese día (docente_autorizado_para_bloque) — la misma fuente
que ya usa horario.clases_afectadas. Alguien con asistencia.corregir puede
saltarse esta regla (coordinación/administración).

Ventana de corrección propia: no está definida por el colegio hoy (el
encargo original lo señala explícitamente como algo a decidir). Se usa un
valor razonable y ajustable en un solo lugar (VENTANA_CORRECCION_PROPIA_DIAS
más abajo): el propio docente puede corregir su registro mientras la fecha
de la clase tenga como máximo esa antigüedad; pasada esa ventana, hace falta
asistencia.corregir.
"""

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import crud, fechas, horario, models, schemas

VENTANA_CORRECCION_PROPIA_DIAS = 2


class SinAutorizacion(Exception):
    """El usuario no está autorizado a hacer esta operación de asistencia
    (no es error de datos: el router la traduce a 403)."""


class DatosInvalidos(Exception):
    """El body pide algo que no tiene sentido (estudiante que no pertenece
    al grupo, estado inválido...): el router la traduce a 400."""


class NoEncontrado(Exception):
    """El registro de asistencia indicado no existe: el router la traduce
    a 404."""


def _director_de_grupo(
    db: Session, sede_id: int, grado: int, curso: int | None, anio_lectivo: int
) -> models.AsignacionDocente | None:
    return db.scalar(
        select(models.AsignacionDocente).where(
            models.AsignacionDocente.sede_id == sede_id,
            models.AsignacionDocente.grado == grado,
            (models.AsignacionDocente.curso == curso)
            if curso is not None
            else models.AsignacionDocente.curso.is_(None),
            models.AsignacionDocente.area_id.is_(None),
            models.AsignacionDocente.anio_lectivo == anio_lectivo,
        )
    )


def bloque_vigente(
    db: Session, sede_id: int, grado: int, curso: int | None, area_id: int | None, fecha: dt.date
) -> models.BloqueHorario | None:
    """El BloqueHorario 'activo' de ese grupo+área para el día de la semana
    de `fecha`. Puede no haber ninguno (horario no cargado todavía, área sin
    bloque fijo...) — eso no impide tomar asistencia, solo que no queda
    ligada a un bloque concreto."""
    dia = horario.dia_de_fecha(fecha)
    if dia is None:
        return None
    stmt = (
        select(models.BloqueHorario)
        .where(
            models.BloqueHorario.anio_lectivo == fecha.year,
            models.BloqueHorario.sede_id == sede_id,
            models.BloqueHorario.grado == grado,
            (models.BloqueHorario.curso == curso)
            if curso is not None
            else models.BloqueHorario.curso.is_(None),
            (models.BloqueHorario.area_id == area_id)
            if area_id is not None
            else models.BloqueHorario.area_id.is_(None),
            models.BloqueHorario.dia == dia,
            models.BloqueHorario.estado == "activo",
        )
        .order_by(models.BloqueHorario.hora)
    )
    return db.scalars(stmt).first()


def docente_autorizado_para_bloque(db: Session, bloque: models.BloqueHorario, fecha: dt.date) -> int:
    """El docente del bloque, salvo que haya un reemplazo YA ASIGNADO ese día
    para ese bloque: ahí manda el reemplazo (misma fuente que
    horario.clases_afectadas)."""
    reemplazo = db.scalar(
        select(models.Reemplazo).where(
            models.Reemplazo.fecha == fecha,
            models.Reemplazo.bloque_horario_id == bloque.id,
            models.Reemplazo.estado == "asignado",
        )
    )
    if reemplazo and reemplazo.docente_reemplazo_id:
        return reemplazo.docente_reemplazo_id
    return bloque.docente_id


def _docente_autorizado(
    db: Session, sede_id: int, grado: int, curso: int | None, area_id: int | None,
    bloque: models.BloqueHorario | None, fecha: dt.date,
) -> int | None:
    if bloque is not None:
        return docente_autorizado_para_bloque(db, bloque, fecha)
    if area_id is None:
        director = _director_de_grupo(db, sede_id, grado, curso, fecha.year)
        return director.docente_id if director else None
    return None  # área sin bloque de horario cargado: nadie queda pre-autorizado


def _resolver_bloque(
    db: Session, sede_id: int, grado: int, curso: int | None, area_id: int | None,
    bloque_horario_id: int | None, fecha: dt.date,
) -> models.BloqueHorario | None:
    if bloque_horario_id is not None:
        bloque = db.get(models.BloqueHorario, bloque_horario_id)
        if bloque is None:
            raise DatosInvalidos("El bloque de horario indicado no existe.")
        return bloque
    return bloque_vigente(db, sede_id, grado, curso, area_id, fecha)


def vista_bloque(
    db: Session, *, usuario: models.Usuario, tiene_permiso_amplio: bool,
    sede_id: int, grado: int, curso: int | None, area_id: int | None,
    bloque_horario_id: int | None, fecha: dt.date,
) -> schemas.AsistenciaBloqueVista:
    bloque = _resolver_bloque(db, sede_id, grado, curso, area_id, bloque_horario_id, fecha)
    docente_autorizado_id = _docente_autorizado(db, sede_id, grado, curso, area_id, bloque, fecha)

    puede_registrar = tiene_permiso_amplio or (
        usuario.docente_id is not None and usuario.docente_id == docente_autorizado_id
    )
    motivo = None
    if not puede_registrar:
        motivo = (
            "No hay un docente autorizado para este bloque hoy."
            if docente_autorizado_id is None
            else "No eres el docente asignado a este bloque hoy (ni su reemplazo)."
        )

    estudiantes = crud.estudiantes_de_grupo_docente(db, sede_id, grado, curso)
    registros = {
        a.estudiante_id: a
        for a in db.scalars(
            select(models.Asistencia).where(
                models.Asistencia.sede_id == sede_id,
                models.Asistencia.grado == grado,
                (models.Asistencia.curso == curso) if curso is not None else models.Asistencia.curso.is_(None),
                (models.Asistencia.area_id == area_id) if area_id is not None else models.Asistencia.area_id.is_(None),
                models.Asistencia.fecha == fecha,
                models.Asistencia.anulado.is_(False),
            )
        ).all()
    }
    return schemas.AsistenciaBloqueVista(
        sede_id=sede_id, grado=grado, curso=curso, area_id=area_id,
        area_nombre=(bloque.area.nombre if bloque and bloque.area else (bloque.area_label if bloque else None)),
        bloque_horario_id=bloque.id if bloque else None,
        fecha=fecha, puede_registrar=puede_registrar, motivo_solo_lectura=motivo,
        estudiantes=[
            schemas.AsistenciaEstudianteVista(
                estudiante_id=e.id, nombres=f"{e.primer_nombre} {e.segundo_nombre or ''}".strip(),
                apellidos=f"{e.primer_apellido} {e.segundo_apellido or ''}".strip(), documento=e.documento,
                estado=registros[e.id].estado if e.id in registros else None,
                observacion=registros[e.id].observacion if e.id in registros else None,
                registrado_en=registros[e.id].registrado_en if e.id in registros else None,
                en_conflicto=registros[e.id].en_conflicto if e.id in registros else False,
            )
            for e in estudiantes
        ],
    )


def _dentro_de_ventana_propia(existente: models.Asistencia) -> bool:
    return (fechas.hoy_colombia() - existente.fecha).days <= VENTANA_CORRECCION_PROPIA_DIAS


def _upsert_registro(
    db: Session, *, usuario: models.Usuario, bloque: models.BloqueHorario | None, docente_id: int,
    tiene_permiso_amplio: bool, datos: schemas.AsistenciaRegistroLote, item: schemas.AsistenciaRegistroItem,
) -> models.Asistencia:
    if item.estado not in schemas.ESTADOS_ASISTENCIA:
        raise DatosInvalidos(f"Estado de asistencia inválido: {item.estado!r}")

    existente = None
    if item.uuid_cliente:
        existente = db.scalar(
            select(models.Asistencia).where(models.Asistencia.uuid_cliente == item.uuid_cliente)
        )
    if existente is None:
        existente = db.scalar(
            select(models.Asistencia).where(
                models.Asistencia.estudiante_id == item.estudiante_id,
                models.Asistencia.fecha == datos.fecha,
                (models.Asistencia.area_id == datos.area_id)
                if datos.area_id is not None
                else models.Asistencia.area_id.is_(None),
            )
        )

    ahora = fechas.ahora_utc()

    if existente is None:
        nuevo = models.Asistencia(
            uuid_cliente=item.uuid_cliente, estudiante_id=item.estudiante_id,
            sede_id=datos.sede_id, grado=datos.grado, curso=datos.curso, area_id=datos.area_id,
            bloque_horario_id=bloque.id if bloque else None,
            fecha=datos.fecha, estado=item.estado, observacion=item.observacion,
            docente_id=docente_id, registrado_por_usuario_id=usuario.id, registrado_en=ahora,
        )
        db.add(nuevo)
        db.flush()
        return nuevo

    if existente.anulado:
        raise SinAutorizacion("Este registro fue anulado; no se puede reescribir directamente.")

    es_propio_reciente = existente.registrado_por_usuario_id == usuario.id and _dentro_de_ventana_propia(existente)
    if not tiene_permiso_amplio and not es_propio_reciente:
        raise SinAutorizacion(
            f"Este registro tiene más de {VENTANA_CORRECCION_PROPIA_DIAS} día(s): pídele a "
            "coordinación que lo corrija."
        )

    if existente.estado != item.estado:
        db.add(models.AuditoriaCambio(
            entidad="asistencia", entidad_id=existente.id, campo="estado",
            valor_anterior=existente.estado, valor_nuevo=item.estado,
            usuario_id=usuario.id, creado_en=ahora,
        ))
        existente.estado = item.estado
    if (existente.observacion or None) != (item.observacion or None):
        existente.observacion = item.observacion

    existente.modificado_por_usuario_id = usuario.id
    existente.modificado_en = ahora
    return existente


def registrar_lote(
    db: Session, *, usuario: models.Usuario, tiene_permiso_amplio: bool, datos: schemas.AsistenciaRegistroLote,
) -> list[models.Asistencia]:
    if usuario.docente_id is None and not tiene_permiso_amplio:
        raise SinAutorizacion("Tu usuario no está vinculado a un docente.")

    bloque = _resolver_bloque(db, datos.sede_id, datos.grado, datos.curso, datos.area_id, datos.bloque_horario_id, datos.fecha)
    docente_autorizado_id = _docente_autorizado(db, datos.sede_id, datos.grado, datos.curso, datos.area_id, bloque, datos.fecha)

    if not tiene_permiso_amplio:
        if docente_autorizado_id is None or usuario.docente_id != docente_autorizado_id:
            raise SinAutorizacion("No estás autorizado a registrar la asistencia de este grupo/bloque hoy.")

    docente_id_registro = docente_autorizado_id if docente_autorizado_id is not None else usuario.docente_id
    if docente_id_registro is None:
        raise SinAutorizacion("No se pudo determinar el docente responsable de este registro.")

    validos = {
        e.id for e in crud.estudiantes_de_grupo_docente(db, datos.sede_id, datos.grado, datos.curso)
    }
    ajenos = [item.estudiante_id for item in datos.registros if item.estudiante_id not in validos]
    if ajenos:
        raise DatosInvalidos(f"Estos estudiantes no pertenecen a ese grupo: {ajenos}")

    resultado = [
        _upsert_registro(
            db, usuario=usuario, bloque=bloque, docente_id=docente_id_registro,
            tiene_permiso_amplio=tiene_permiso_amplio, datos=datos, item=item,
        )
        for item in datos.registros
    ]
    db.commit()
    return resultado


def corregir_registro(
    db: Session, *, usuario: models.Usuario, asistencia_id: int, datos: schemas.AsistenciaCorregir
) -> models.Asistencia:
    """Solo para quien tiene asistencia.corregir (coordinación/administración
    saltándose la ventana de corrección propia) — el router es quien exige
    ese permiso antes de llegar aquí."""
    a = db.get(models.Asistencia, asistencia_id)
    if a is None or a.anulado:
        raise NoEncontrado("Registro no encontrado.")
    if datos.estado not in schemas.ESTADOS_ASISTENCIA:
        raise DatosInvalidos(f"Estado de asistencia inválido: {datos.estado!r}")

    ahora = fechas.ahora_utc()
    if a.estado != datos.estado:
        db.add(models.AuditoriaCambio(
            entidad="asistencia", entidad_id=a.id, campo="estado",
            valor_anterior=a.estado, valor_nuevo=datos.estado,
            usuario_id=usuario.id, motivo=datos.motivo, creado_en=ahora,
        ))
    a.estado = datos.estado
    a.observacion = datos.observacion
    a.modificado_por_usuario_id = usuario.id
    a.modificado_en = ahora
    a.motivo_modificacion = datos.motivo
    db.commit()
    return a


def clases_de_hoy_docente(db: Session, docente_id: int, *, ahora: dt.datetime | None = None) -> dict:
    """Las clases de HOY de este docente según su horario real (BloqueHorario),
    con cuál es la de la hora actual (si hay alguna en curso) y si ya se le
    tomó asistencia. Es el "estás en 5°-1, marca asistencia" del inicio."""
    info = horario.franja_actual(ahora)
    fecha = dt.date.fromisoformat(info["fecha"])
    dia = info["dia"]

    bloques: list[models.BloqueHorario] = []
    if dia is not None:
        bloques = list(db.scalars(
            select(models.BloqueHorario)
            .where(
                models.BloqueHorario.anio_lectivo == fecha.year,
                models.BloqueHorario.docente_id == docente_id,
                models.BloqueHorario.dia == dia,
                models.BloqueHorario.estado == "activo",
            )
            .order_by(models.BloqueHorario.hora)
        ))

    tomadas: set[int] = set()
    if bloques:
        tomadas = set(db.scalars(
            select(models.Asistencia.bloque_horario_id).where(
                models.Asistencia.bloque_horario_id.in_([b.id for b in bloques]),
                models.Asistencia.fecha == fecha,
                models.Asistencia.anulado.is_(False),
            ).distinct()
        ).all())

    clases = [
        {
            "bloque_horario_id": b.id, "hora": b.hora,
            "sede_id": b.sede_id, "grado": b.grado, "curso": b.curso, "area_id": b.area_id,
            "area_nombre": b.area.nombre if b.area else b.area_label,
            "nombre_grupo": horario.nombre_grupo(b.grado, b.curso),
            "es_ahora": info["estado"] == "en_franja" and info["hora"] == b.hora,
            "asistencia_tomada": b.id in tomadas,
        }
        for b in bloques
    ]
    return {
        "fecha": fecha, "dia_nombre": info["dia_nombre"],
        "estado_jornada": info["estado"], "hora_actual": info["hora"], "clases": clases,
    }


def historial_resumen_docente(db: Session, docente_id: int, *, dias: int = 30) -> list[dict]:
    """Un renglón por (fecha, grupo, área) con el conteo de cada estado —
    no una fila por estudiante, para que sea legible de un vistazo."""
    desde = fechas.hoy_colombia() - dt.timedelta(days=dias)
    filas = db.execute(
        select(
            models.Asistencia.fecha, models.Asistencia.sede_id, models.Asistencia.grado,
            models.Asistencia.curso, models.Asistencia.area_id, models.Asistencia.estado,
            func.count(),
        )
        .where(
            models.Asistencia.docente_id == docente_id,
            models.Asistencia.fecha >= desde,
            models.Asistencia.anulado.is_(False),
        )
        .group_by(
            models.Asistencia.fecha, models.Asistencia.sede_id, models.Asistencia.grado,
            models.Asistencia.curso, models.Asistencia.area_id, models.Asistencia.estado,
        )
    ).all()

    areas = {a.id: a.nombre for a in db.scalars(select(models.Area)).all()}
    resumen: dict[tuple, dict] = {}
    for fecha, sede_id, grado, curso, area_id, estado, cnt in filas:
        clave = (fecha, sede_id, grado, curso, area_id)
        item = resumen.setdefault(clave, {
            "fecha": fecha, "sede_id": sede_id, "grado": grado, "curso": curso, "area_id": area_id,
            "nombre_grupo": horario.nombre_grupo(grado, curso),
            "area_nombre": areas.get(area_id, "Director de grupo") if area_id else "Director de grupo",
            "presentes": 0, "ausentes": 0, "tardanzas": 0, "excusas": 0, "total": 0,
        })
        item["total"] += cnt
        if estado == "presente":
            item["presentes"] += cnt
        elif estado == "ausente":
            item["ausentes"] += cnt
        elif estado == "tardanza":
            item["tardanzas"] += cnt
        elif estado == "excusa":
            item["excusas"] += cnt
    return sorted(resumen.values(), key=lambda r: (r["fecha"], r["nombre_grupo"]), reverse=True)


def anular_registro(db: Session, *, usuario: models.Usuario, asistencia_id: int, motivo: str) -> models.Asistencia:
    a = db.get(models.Asistencia, asistencia_id)
    if a is None:
        raise NoEncontrado("Registro no encontrado.")
    ahora = fechas.ahora_utc()
    db.add(models.AuditoriaCambio(
        entidad="asistencia", entidad_id=a.id, campo="anulado",
        valor_anterior="False", valor_nuevo="True",
        usuario_id=usuario.id, motivo=motivo, creado_en=ahora,
    ))
    a.anulado = True
    a.anulado_por_usuario_id = usuario.id
    a.anulado_en = ahora
    a.motivo_anulacion = motivo
    db.commit()
    return a


# --- Panel de coordinación (asistencia.cumplimiento / asistencia.estadisticas) ---
# La asistencia se registra por (grupo, área, día): la Sede #01 tiene un
# docente por materia (bloques de horario, area_id con valor) y las sedes
# rurales tienen un solo maestro por grupo (AsignacionDocente area_id=None,
# sin horario por franjas — ver README). Las dos funciones de abajo combinan
# ambas fuentes para saber qué se espera hoy en cada grupo, en vez de asumir
# una sola convención.


def _grupos_esperados_hoy(db: Session, fecha: dt.date, sede_id: int | None = None) -> dict[tuple, dict]:
    """Claves (sede_id, grado, curso, area_id) que 'deberían' tener asistencia
    hoy, con quién es el responsable: los bloques de horario del día (Sede
    #01, uno por área) más los grupos de un solo maestro sin horario cargado
    (sedes rurales, area_id=None, todos los días hábiles)."""
    esperados: dict[tuple, dict] = {}

    dia = horario.dia_de_fecha(fecha)
    if dia is not None:
        q = select(models.BloqueHorario).where(
            models.BloqueHorario.anio_lectivo == fecha.year,
            models.BloqueHorario.dia == dia,
            models.BloqueHorario.estado == "activo",
        )
        if sede_id is not None:
            q = q.where(models.BloqueHorario.sede_id == sede_id)
        for b in db.scalars(q).all():
            clave = (b.sede_id, b.grado, b.curso, b.area_id)
            if clave not in esperados:
                esperados[clave] = {
                    "sede_id": b.sede_id, "grado": b.grado, "curso": b.curso, "area_id": b.area_id,
                    "area_nombre": b.area.nombre if b.area else b.area_label,
                    "docente_id": docente_autorizado_para_bloque(db, b, fecha),
                }

    q2 = select(models.AsignacionDocente).where(
        models.AsignacionDocente.anio_lectivo == fecha.year,
        models.AsignacionDocente.area_id.is_(None),
    )
    if sede_id is not None:
        q2 = q2.where(models.AsignacionDocente.sede_id == sede_id)
    for asig in db.scalars(q2).all():
        clave = (asig.sede_id, asig.grado, asig.curso, None)
        if clave not in esperados:  # el horario, si existe, ya manda para esta clave
            esperados[clave] = {
                "sede_id": asig.sede_id, "grado": asig.grado, "curso": asig.curso, "area_id": None,
                "area_nombre": "Director de grupo",
                "docente_id": asig.docente_id,
            }

    return esperados


def panel_dia(db: Session, fecha: dt.date, sede_id: int | None = None) -> list[dict]:
    """Un renglón por (grupo, área) esperado hoy: si ya se tomó, con qué
    conteos, o si sigue pendiente."""
    esperados = _grupos_esperados_hoy(db, fecha, sede_id)
    docentes = {
        d.id: d.nombre_completo
        for d in db.scalars(select(models.Docente)).all()
    }
    sedes = {s.id: s.nombre for s in db.scalars(select(models.Sede)).all()}

    filas = []
    for (sede_id_, grado, curso, area_id), info in esperados.items():
        registros = db.scalars(
            select(models.Asistencia).where(
                models.Asistencia.sede_id == sede_id_,
                models.Asistencia.grado == grado,
                (models.Asistencia.curso == curso) if curso is not None else models.Asistencia.curso.is_(None),
                (models.Asistencia.area_id == area_id) if area_id is not None else models.Asistencia.area_id.is_(None),
                models.Asistencia.fecha == fecha,
                models.Asistencia.anulado.is_(False),
            )
        ).all()
        total = len(crud.estudiantes_de_grupo_docente(db, sede_id_, grado, curso))
        conteos = {"presente": 0, "ausente": 0, "tardanza": 0, "excusa": 0}
        ultimo = None
        for r in registros:
            conteos[r.estado] = conteos.get(r.estado, 0) + 1
            if ultimo is None or r.registrado_en > ultimo:
                ultimo = r.registrado_en

        if not registros:
            estado = "pendiente"
        elif len(registros) < total:
            estado = "parcial"
        else:
            estado = "completo"

        filas.append({
            "sede_id": sede_id_, "sede_nombre": sedes.get(sede_id_, ""),
            "grado": grado, "curso": curso,
            "nombre_grupo": f"{horario.nombre_grupo(grado, curso)} · {info['area_nombre']}",
            "docente_id": info["docente_id"], "docente_nombre": docentes.get(info["docente_id"], ""),
            "total_estudiantes": total, "registrados": len(registros),
            "presentes": conteos["presente"], "ausentes": conteos["ausente"],
            "tardanzas": conteos["tardanza"], "excusas": conteos["excusa"],
            "estado": estado, "ultimo_registro": ultimo,
        })

    orden_estado = {"pendiente": 0, "parcial": 1, "completo": 2}
    filas.sort(key=lambda f: (orden_estado[f["estado"]], f["sede_nombre"], f["grado"], f["curso"] or 0))
    return filas


def alertas_estudiantes(
    db: Session, *, sede_id: int | None = None, grado: int | None = None,
    fecha: dt.date | None = None, dias: int = 21, umbral_racha: int = 3,
) -> list[dict]:
    """Estudiantes con racha de días consecutivos 'faltó todo el día' (en
    TODAS sus áreas registradas ese día salió ausente) de al menos
    umbral_racha, o con alguna excusa en la ventana. Ordenados por racha
    descendente: lo más urgente primero."""
    fecha = fecha or fechas.hoy_colombia()
    desde = fecha - dt.timedelta(days=dias)
    q = select(models.Asistencia).where(
        models.Asistencia.fecha >= desde,
        models.Asistencia.fecha <= fecha,
        models.Asistencia.anulado.is_(False),
    )
    if sede_id is not None:
        q = q.where(models.Asistencia.sede_id == sede_id)
    if grado is not None:
        q = q.where(models.Asistencia.grado == grado)

    por_estudiante_dia: dict[tuple[int, dt.date], list[models.Asistencia]] = {}
    for r in db.scalars(q).all():
        por_estudiante_dia.setdefault((r.estudiante_id, r.fecha), []).append(r)

    # Un renglón por (estudiante, día): ausente_completo si NINGÚN registro
    # de ese día fue presente/tardanza; el resto de datos vienen del último
    # registro de ese día (todos comparten estudiante/grupo).
    dias_por_estudiante: dict[int, list[tuple[dt.date, bool, int, models.Asistencia]]] = {}
    for (est_id, fecha_r), regs in por_estudiante_dia.items():
        ausente_completo = all(r.estado == "ausente" for r in regs)
        excusas_ese_dia = sum(1 for r in regs if r.estado == "excusa")
        dias_por_estudiante.setdefault(est_id, []).append((fecha_r, ausente_completo, excusas_ese_dia, regs[-1]))

    ids = list(dias_por_estudiante.keys())
    estudiantes = (
        {e.id: e for e in db.scalars(select(models.Estudiante).where(models.Estudiante.id.in_(ids)))}
        if ids
        else {}
    )

    resultado = []
    for est_id, dias_lista in dias_por_estudiante.items():
        dias_lista.sort(key=lambda t: t[0])
        racha = 0
        for _, ausente_completo, _, _ in reversed(dias_lista):
            if not ausente_completo:
                break
            racha += 1
        excusas_recientes = sum(t[2] for t in dias_lista)
        if racha < umbral_racha and excusas_recientes == 0:
            continue

        ultima_fecha, ultimo_ausente_completo, _, ultimo_reg = dias_lista[-1]
        e = estudiantes.get(est_id)
        resultado.append({
            "estudiante_id": est_id,
            "nombre_completo": e.nombre_completo if e else "—",
            "documento": e.documento if e else "",
            "sede_id": ultimo_reg.sede_id, "grado": ultimo_reg.grado, "curso": ultimo_reg.curso,
            "nombre_grupo": horario.nombre_grupo(ultimo_reg.grado, ultimo_reg.curso),
            "racha_ausente": racha, "excusas_recientes": excusas_recientes,
            "ultima_fecha": ultima_fecha,
            "ultimo_estado": "ausente" if ultimo_ausente_completo else ultimo_reg.estado,
        })

    resultado.sort(key=lambda r: (-r["racha_ausente"], -r["excusas_recientes"]))
    return resultado
