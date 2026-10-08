import datetime as dt
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import conciliacion, fechas, models, schemas
from .certificados import MESES_TEXTO
from .texto import sin_tildes

# SAPRED usa códigos de área inconsistentes según el grado: en noveno el
# "Consolidado" / "Boletín" trae LENGUA EXTRANJERA INGLÉS con el código
# "INGL" en vez de "LEI", lo que creaba un área duplicada (y una columna
# vacía en la grilla). Se normaliza al código canónico antes de resolver
# el área, así el importador reusa la de siempre y no vuelve a duplicar.
ALIAS_CODIGOS_AREA = {"INGL": "LEI"}


def _codigo_area_canonico(codigo: str) -> str:
    return ALIAS_CODIGOS_AREA.get((codigo or "").strip().upper(), codigo)


# --- Sedes -----------------------------------------------------------


def listar_sedes(db: Session) -> list[schemas.SedeResumen]:
    sedes = db.scalars(select(models.Sede).order_by(models.Sede.nombre)).all()
    resultado = []
    for s in sedes:
        total = len(s.estudiantes)
        activos = sum(1 for e in s.estudiantes if e.activo)
        resultado.append(
            schemas.SedeResumen(
                id=s.id,
                nombre=s.nombre,
                codigo_dane_sede=s.codigo_dane_sede,
                codigo_dane_consecutivo=s.codigo_dane_consecutivo,
                institucion_centro_educativo=s.institucion_centro_educativo,
                resguardo=s.resguardo,
                pertenece_ietaba=s.pertenece_ietaba,
                total_estudiantes=total,
                total_activos=activos,
            )
        )
    return resultado


def obtener_sede(db: Session, sede_id: int) -> models.Sede | None:
    return db.get(models.Sede, sede_id)


def actualizar_sede(db: Session, sede_id: int, cambios: schemas.SedeUpdate) -> models.Sede | None:
    sede = db.get(models.Sede, sede_id)
    if sede is None:
        return None
    for campo, valor in cambios.model_dump(exclude_unset=True).items():
        setattr(sede, campo, valor)
    db.commit()
    db.refresh(sede)
    return sede


def generar_reporte(db: Session, solo_ietaba: bool = True) -> schemas.ReporteGeneral:
    stmt = select(models.Sede).order_by(models.Sede.nombre)
    if solo_ietaba:
        stmt = stmt.where(models.Sede.pertenece_ietaba.is_(True))
    sedes = db.scalars(stmt).all()

    por_sede = []
    total_h = total_m = total = 0
    for s in sedes:
        activos = [e for e in s.estudiantes if e.activo]
        hombres = sum(1 for e in activos if (e.genero or "").upper() == "M")
        mujeres = sum(1 for e in activos if (e.genero or "").upper() == "F")
        por_sede.append(
            schemas.ReporteSede(
                id=s.id, nombre=s.nombre, total_estudiantes=len(activos), hombres=hombres, mujeres=mujeres
            )
        )
        total += len(activos)
        total_h += hombres
        total_m += mujeres

    return schemas.ReporteGeneral(
        total_sedes=len(sedes), total_estudiantes=total, hombres=total_h, mujeres=total_m, por_sede=por_sede
    )


def obtener_o_crear_sede(db: Session, datos: schemas.SedeCreate) -> models.Sede:
    existente = db.scalar(select(models.Sede).where(models.Sede.nombre == datos.nombre))
    if existente:
        return existente
    nueva = models.Sede(**datos.model_dump())
    db.add(nueva)
    db.flush()
    return nueva


# --- Estudiantes ---------------------------------------------------------


def _filtrar_estudiantes(
    stmt,
    sede_id: int | None = None,
    grado: int | None = None,
    curso: int | None = None,
    estado: str | None = None,
    busqueda: str | None = None,
    solo_no_verificados: bool = False,
    sin_curso: bool = False,
):
    if sede_id is not None:
        stmt = stmt.where(models.Estudiante.sede_id == sede_id)
    if grado is not None:
        stmt = stmt.where(models.Estudiante.grado == grado)
    if curso is not None:
        stmt = stmt.where(models.Estudiante.curso == curso)
    # Los estudiantes importados desde la LISTA DE ASISTENCIA (las 47 sedes
    # rurales sin Excel de matrícula propio) no traen sección/curso — se
    # quedan con curso=NULL. Este filtro los encuentra para poder
    # completarlos a mano.
    if sin_curso:
        stmt = stmt.where(models.Estudiante.curso.is_(None))
    if estado is not None:
        stmt = stmt.where(func.upper(models.Estudiante.estado) == estado.upper())
    if solo_no_verificados:
        stmt = stmt.where(models.Estudiante.verificado_matricula.is_(False))
    if busqueda:
        # Sin tildes y sin distinguir mayúsculas de ambos lados: "bolanos",
        # "BOLAÑOS" y "Bolaños" encuentran a los mismos. (El lower() de SQLite
        # no pliega la Ñ, por eso no bastaba con pasar el patrón a minúscula.)
        patron = f"%{sin_tildes(busqueda)}%"
        nombre_completo = func.sin_tildes(
            models.Estudiante.primer_nombre
            + " "
            + func.coalesce(models.Estudiante.segundo_nombre, "")
            + " "
            + models.Estudiante.primer_apellido
            + " "
            + func.coalesce(models.Estudiante.segundo_apellido, "")
        )
        stmt = stmt.where(
            nombre_completo.like(patron) | func.sin_tildes(models.Estudiante.documento).like(patron)
        )
    return stmt


def listar_estudiantes(
    db: Session,
    sede_id: int | None = None,
    grado: int | None = None,
    curso: int | None = None,
    estado: str | None = None,
    busqueda: str | None = None,
    sin_curso: bool = False,
) -> list[models.Estudiante]:
    stmt = _filtrar_estudiantes(
        select(models.Estudiante), sede_id, grado, curso, estado, busqueda, sin_curso=sin_curso
    ).order_by(
        models.Estudiante.grado,
        models.Estudiante.curso,
        models.Estudiante.primer_apellido,
        models.Estudiante.primer_nombre,
    )
    return list(db.scalars(stmt).all())


def conteo_estudiantes_por_sede(
    db: Session, grado: int | None = None, estado: str | None = None
) -> list[dict]:
    """Fase 4.1: lo único que en realidad necesitan los scripts de SAPRED
    (cuántos estudiantes activos hay por sede, para un grado) — sin ningún
    dato personal. No reutiliza listar_estudiantes(): esa trae el estudiante
    completo (documento, nombre, fotos, historial de documentos...) que aquí
    sobra por completo; esto es un COUNT/GROUP BY, nada más."""
    stmt = _filtrar_estudiantes(
        select(models.Estudiante.sede_id, func.count(models.Estudiante.id)),
        grado=grado, estado=estado,
    ).group_by(models.Estudiante.sede_id)
    return [{"sede_id": sede_id, "cantidad": cantidad} for sede_id, cantidad in db.execute(stmt).all()]


def listar_estudiantes_paginado(
    db: Session,
    sede_id: int | None = None,
    grado: int | None = None,
    curso: int | None = None,
    estado: str | None = None,
    busqueda: str | None = None,
    solo_no_verificados: bool = False,
    sin_curso: bool = False,
    pagina: int = 1,
    por_pagina: int = 50,
) -> tuple[list[models.Estudiante], int]:
    base = _filtrar_estudiantes(
        select(models.Estudiante), sede_id, grado, curso, estado, busqueda, solo_no_verificados, sin_curso
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    stmt = base.order_by(
        models.Estudiante.grado,
        models.Estudiante.curso,
        models.Estudiante.primer_apellido,
        models.Estudiante.primer_nombre,
    )
    if por_pagina > 0:
        stmt = stmt.limit(por_pagina).offset((pagina - 1) * por_pagina)
    items = list(db.scalars(stmt).all())
    return items, total


def crear_estudiante(db: Session, estudiante: schemas.EstudianteCreate) -> models.Estudiante:
    db_estudiante = models.Estudiante(**estudiante.model_dump())
    db.add(db_estudiante)
    db.commit()
    db.refresh(db_estudiante)
    return db_estudiante


def obtener_estudiante(db: Session, estudiante_id: int) -> models.Estudiante | None:
    return db.get(models.Estudiante, estudiante_id)


def buscar_por_documento(db: Session, documento: str) -> models.Estudiante | None:
    return db.scalar(select(models.Estudiante).where(models.Estudiante.documento == documento))


def actualizar_estudiante(
    db: Session, estudiante_id: int, cambios: schemas.EstudianteUpdate
) -> models.Estudiante | None:
    db_estudiante = db.get(models.Estudiante, estudiante_id)
    if db_estudiante is None:
        return None

    datos = cambios.model_dump(exclude_unset=True)
    # Si cambia el tipo o el número de documento (ej. de Registro Civil a
    # Tarjeta de Identidad, o de T.I. a Cédula al cumplir la mayoría de
    # edad), el valor anterior no se pierde: queda guardado en el
    # historial, porque constancias/certificados previos se expidieron con
    # ese dato.
    cambia_tipo = "tipo_documento" in datos and datos["tipo_documento"] != db_estudiante.tipo_documento
    cambia_numero = "documento" in datos and datos["documento"] != db_estudiante.documento
    if cambia_tipo or cambia_numero:
        db.add(
            models.HistorialDocumentoEstudiante(
                estudiante_id=db_estudiante.id,
                tipo_documento=db_estudiante.tipo_documento,
                documento=db_estudiante.documento,
            )
        )

    # "retirado" es una marca más fuerte que "posible retirado" y siempre va
    # con ella (así sigue fuera de los pendientes); quitar el posible retiro
    # quita también la de retirado.
    if datos.get("retirado") is True:
        datos["posible_retirado"] = True
    if datos.get("posible_retirado") is False:
        datos["retirado"] = False

    for campo, valor in datos.items():
        setattr(db_estudiante, campo, valor)
    db.commit()
    db.refresh(db_estudiante)
    return db_estudiante


def eliminar_estudiante(db: Session, estudiante_id: int) -> bool:
    """Fotos, historial de documento y asistencia se borran con el estudiante
    (cascade del modelo). Si tiene constancias, notas o pendientes de boletín,
    las claves foráneas no dejan borrarlo (antes quedaban esas filas
    huérfanas): se lanza ValueError para que se cambie su estado a RETIRADO."""
    from sqlalchemy.exc import IntegrityError

    db_estudiante = db.get(models.Estudiante, estudiante_id)
    if db_estudiante is None:
        return False
    db.delete(db_estudiante)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError(
            "No se puede eliminar: el estudiante tiene constancias, notas o pendientes de boletín "
            "registrados. Cambia su estado a RETIRADO."
        )
    return True


# --- Fotos del estudiante ---------------------------------------------------


def agregar_foto(
    db: Session, estudiante_id: int, etiqueta: str, anio_lectivo: int | None, nombre_archivo: str
) -> models.FotoEstudiante:
    orden_actual = db.scalar(
        select(func.count()).where(models.FotoEstudiante.estudiante_id == estudiante_id)
    ) or 0
    foto = models.FotoEstudiante(
        estudiante_id=estudiante_id,
        etiqueta=etiqueta,
        anio_lectivo=anio_lectivo,
        nombre_archivo=nombre_archivo,
        orden=orden_actual,
    )
    db.add(foto)
    db.commit()
    db.refresh(foto)
    return foto


def obtener_foto(db: Session, foto_id: int) -> models.FotoEstudiante | None:
    return db.get(models.FotoEstudiante, foto_id)


def eliminar_foto(db: Session, foto_id: int) -> models.FotoEstudiante | None:
    foto = db.get(models.FotoEstudiante, foto_id)
    if foto is None:
        return None
    db.delete(foto)
    db.commit()
    return foto


# --- Registro de constancias generadas --------------------------------------


def registrar_constancia(db: Session, **campos) -> models.ConstanciaGenerada:
    constancia = models.ConstanciaGenerada(**campos)
    db.add(constancia)
    db.commit()
    db.refresh(constancia)
    return constancia


def obtener_constancia(db: Session, constancia_id: int) -> models.ConstanciaGenerada | None:
    return db.get(models.ConstanciaGenerada, constancia_id)


def listar_constancias(
    db: Session,
    busqueda: str | None = None,
    desde: dt.date | None = None,
    hasta: dt.date | None = None,
    proposito: str | None = None,
) -> list[models.ConstanciaGenerada]:
    stmt = select(models.ConstanciaGenerada).join(models.Estudiante)
    if busqueda:
        patron = f"%{busqueda.lower()}%"
        nombre_completo = func.lower(
            models.Estudiante.primer_nombre
            + " "
            + func.coalesce(models.Estudiante.segundo_nombre, "")
            + " "
            + models.Estudiante.primer_apellido
            + " "
            + func.coalesce(models.Estudiante.segundo_apellido, "")
        )
        stmt = stmt.where(
            nombre_completo.like(patron) | func.lower(models.Estudiante.documento).like(patron)
        )
    if desde:
        stmt = stmt.where(models.ConstanciaGenerada.fecha_expedicion >= desde)
    if hasta:
        stmt = stmt.where(models.ConstanciaGenerada.fecha_expedicion <= hasta)
    if proposito:
        stmt = stmt.where(models.ConstanciaGenerada.proposito == proposito)
    stmt = stmt.order_by(models.ConstanciaGenerada.generado_en.desc())
    return list(db.scalars(stmt).all())


# --- Docentes, asignaciones y revisión de boletines --------------------------


def listar_docentes(db: Session) -> list[models.Docente]:
    return list(db.scalars(select(models.Docente).order_by(models.Docente.nombre_completo)).all())


def _grupo_label(grado: int, curso: int | None) -> str:
    grado_txt = models.GRADOS_NOMBRES.get(grado, str(grado))
    return f"{grado_txt} - {curso}" if curso else grado_txt


def listar_docentes_reporte(
    db: Session, anio_lectivo: int, sede_id: int | None = None
) -> list[dict]:
    """Docentes con sus asignaciones del año, para el reporte dinámico de
    Reportes → Lista de docentes. Un docente puede tener varias filas (una
    por grupo/área); aquí se agrupan por docente y cada asignación se marca
    con su "tipo": AREA (dicta una materia puntual), DIRECTOR (responde por
    todo un grupo que también tiene profesores de área) o GRUPO (maestro
    único de un grupo, típico rural). "Responsable de grupo" (es_responsable_
    grupo) agrupa DIRECTOR y GRUPO: son los docentes que, en la práctica,
    dirigen un grupo completo — la distinción que pidió el usuario entre
    "todos" y "solo directores"."""
    asignaciones = list(
        db.scalars(
            select(models.AsignacionDocente)
            .where(models.AsignacionDocente.anio_lectivo == anio_lectivo)
            .options(
                selectinload(models.AsignacionDocente.docente),
                selectinload(models.AsignacionDocente.sede),
                selectinload(models.AsignacionDocente.area),
            )
        ).all()
    )
    grupos_con_area = {(a.sede_id, a.grado, a.curso) for a in asignaciones if a.area_id is not None}

    por_docente: dict[int, dict] = {}
    for a in asignaciones:
        if sede_id and a.sede_id != sede_id:
            continue
        d = por_docente.setdefault(
            a.docente_id,
            {
                "id": a.docente.id,
                "documento": a.docente.documento,
                "nombre_completo": a.docente.nombre_completo,
                "fecha_nacimiento": a.docente.fecha_nacimiento,
                "telefono": a.docente.telefono,
                "email": a.docente.email,
                "direccion": a.docente.direccion,
                "asignaciones": [],
                "grupos_dirige": [],
                "es_responsable_grupo": False,
            },
        )
        sede_nombre = a.sede.nombre if a.sede else ""
        label = _grupo_label(a.grado, a.curso)
        if a.area_id is not None:
            tipo = "AREA"
        elif (a.sede_id, a.grado, a.curso) in grupos_con_area:
            tipo = "DIRECTOR"
        else:
            tipo = "GRUPO"
        d["asignaciones"].append(
            {
                "sede_id": a.sede_id,
                "sede_nombre": sede_nombre,
                "grado": a.grado,
                "grado_nombre": models.GRADOS_NOMBRES.get(a.grado, str(a.grado)),
                "curso": a.curso,
                "grupo_label": label,
                "area_id": a.area_id,
                "area_nombre": a.area.nombre if a.area else None,
                "tipo": tipo,
            }
        )
        if tipo in ("DIRECTOR", "GRUPO"):
            d["es_responsable_grupo"] = True
            if (label, sede_nombre) not in d["grupos_dirige"]:
                d["grupos_dirige"].append((label, sede_nombre))

    # Docentes sin ninguna asignación este año (recién importados, por ej.)
    # también deben poder salir listados en "todos".
    if not sede_id:
        ids_con_asignacion = set(por_docente)
        for doc in db.scalars(select(models.Docente).order_by(models.Docente.nombre_completo)).all():
            if doc.id not in ids_con_asignacion:
                por_docente[doc.id] = {
                    "id": doc.id,
                    "documento": doc.documento,
                    "nombre_completo": doc.nombre_completo,
                    "fecha_nacimiento": doc.fecha_nacimiento,
                    "telefono": doc.telefono,
                    "email": doc.email,
                    "direccion": doc.direccion,
                    "asignaciones": [],
                    "grupos_dirige": [],
                    "es_responsable_grupo": False,
                }

    # El nombre de la sede solo se agrega a la etiqueta si el docente
    # realmente dirige grupos en más de una sede (raro); si es una sola, ya
    # sale en la columna "Sede(s)" y repetirla ahí es puro ruido.
    for d in por_docente.values():
        sedes_distintas = {s for _, s in d["grupos_dirige"] if s}
        d["grupos_dirige"] = [
            f"{label} ({sede})" if len(sedes_distintas) > 1 and sede else label
            for label, sede in d["grupos_dirige"]
        ]

    return sorted(por_docente.values(), key=lambda d: d["nombre_completo"])


def obtener_o_crear_docente(db: Session, documento: str, **campos) -> models.Docente:
    docente = db.scalar(select(models.Docente).where(models.Docente.documento == documento))
    if docente is None:
        docente = models.Docente(documento=documento, **campos)
        db.add(docente)
        db.flush()
    else:
        for campo, valor in campos.items():
            if valor:
                setattr(docente, campo, valor)
    return docente


def asignar_docente(db: Session, datos: schemas.AsignacionDocenteCrear) -> models.AsignacionDocente | None:
    existente = db.scalar(
        select(models.AsignacionDocente).where(
            models.AsignacionDocente.sede_id == datos.sede_id,
            models.AsignacionDocente.grado == datos.grado,
            models.AsignacionDocente.curso == datos.curso,
            models.AsignacionDocente.area_id == datos.area_id,
            models.AsignacionDocente.anio_lectivo == datos.anio_lectivo,
        )
    )
    if datos.docente_id is None:
        if existente:
            db.delete(existente)
            db.commit()
        return None

    if existente:
        existente.docente_id = datos.docente_id
    else:
        existente = models.AsignacionDocente(
            docente_id=datos.docente_id,
            sede_id=datos.sede_id,
            grado=datos.grado,
            curso=datos.curso,
            area_id=datos.area_id,
            anio_lectivo=datos.anio_lectivo,
        )
        db.add(existente)
    db.commit()
    db.refresh(existente)
    return existente


def listar_areas(db: Session) -> list[schemas.AreaConGrados]:
    areas = db.scalars(select(models.Area).order_by(models.Area.nombre)).all()
    grados_por_area: dict[int, list[int]] = {}
    for ag in db.scalars(select(models.AreaGrado)).all():
        grados_por_area.setdefault(ag.area_id, []).append(ag.grado)
    return [
        schemas.AreaConGrados(
            id=a.id, codigo=a.codigo, nombre=a.nombre, grados=sorted(grados_por_area.get(a.id, []))
        )
        for a in areas
    ]


def calcular_estado_grupo(revision: models.RevisionBoletin | None, pendientes_abiertos: int) -> str:
    if revision is None:
        return "sin_informacion"
    if pendientes_abiertos > 0:
        return "pendiente"
    if revision.completo and revision.observaciones_completas:
        return "completo"
    return "en_proceso"


def _obtener_o_crear_revision(
    db: Session, sede_id: int, grado: int, curso: int | None, anio_lectivo: int, periodo: int
) -> models.RevisionBoletin:
    existente = db.scalar(
        select(models.RevisionBoletin).where(
            models.RevisionBoletin.sede_id == sede_id,
            models.RevisionBoletin.grado == grado,
            models.RevisionBoletin.curso == curso,
            models.RevisionBoletin.anio_lectivo == anio_lectivo,
            models.RevisionBoletin.periodo == periodo,
        )
    )
    if existente:
        return existente
    nueva = models.RevisionBoletin(sede_id=sede_id, grado=grado, curso=curso, anio_lectivo=anio_lectivo, periodo=periodo)
    db.add(nueva)
    db.flush()
    return nueva


def crear_pendiente(db: Session, datos: schemas.PendienteCrear) -> models.PendienteBoletin:
    revision = _obtener_o_crear_revision(
        db, datos.sede_id, datos.grado, datos.curso, datos.anio_lectivo, datos.periodo
    )
    if datos.revisado_por:
        revision.revisado_por = datos.revisado_por
    pendiente = models.PendienteBoletin(
        revision_id=revision.id,
        area_id=datos.area_id,
        estudiante_id=datos.estudiante_id,
        tipo=datos.tipo,
        detalle=datos.detalle,
    )
    db.add(pendiente)
    db.commit()
    db.refresh(pendiente)
    return pendiente


def actualizar_pendiente(
    db: Session, pendiente_id: int, cambios: schemas.PendienteActualizar
) -> models.PendienteBoletin | None:
    pendiente = db.get(models.PendienteBoletin, pendiente_id)
    if pendiente is None:
        return None
    datos = cambios.model_dump(exclude_unset=True)
    if "resuelto" in datos:
        pendiente.resuelto = datos["resuelto"]
        pendiente.resuelto_en = dt.datetime.utcnow() if datos["resuelto"] else None
    if "detalle" in datos:
        pendiente.detalle = datos["detalle"]
    if datos.get("revisado_por"):
        pendiente.revision.revisado_por = datos["revisado_por"]
    db.commit()
    db.refresh(pendiente)
    return pendiente


def resolver_pendientes_lote(db: Session, ids: list[int], resuelto: bool = True) -> int:
    """Marca (o desmarca) como resuelto un conjunto de pendientes de una sola
    vez — para 'marcar revisado todo lo que le falta a estos estudiantes'
    desde la grilla de notas. Devuelve cuántos cambió."""
    if not ids:
        return 0
    ahora = dt.datetime.utcnow()
    filas = db.scalars(
        select(models.PendienteBoletin).where(models.PendienteBoletin.id.in_(ids))
    ).all()
    n = 0
    for p in filas:
        if p.resuelto == resuelto:
            continue
        p.resuelto = resuelto
        p.resuelto_en = ahora if resuelto else None
        n += 1
    db.commit()
    return n


def eliminar_pendiente(db: Session, pendiente_id: int) -> bool:
    pendiente = db.get(models.PendienteBoletin, pendiente_id)
    if pendiente is None:
        return False
    db.delete(pendiente)
    db.commit()
    return True


# Área del "desempeño actitudinal" / nota de comportamiento — es del director
# de grupo, no de un profesor de asignatura. Se resuelve por código.
CODIGO_AREA_COMPORTAMIENTO = "DESM"


def _area_comportamiento_id(db: Session) -> int | None:
    a = db.scalar(select(models.Area).where(models.Area.codigo == CODIGO_AREA_COMPORTAMIENTO))
    return a.id if a else None


_MARCA_AUTO = " · Cerrado automáticamente por la auditoría (ya estaba cargado en SAPRED)"


def _detalle_cerrado_auto(detalle: str | None) -> str:
    base = (detalle or "").split(_MARCA_AUTO)[0].rstrip()
    return f"{base}{_MARCA_AUTO}"


def _conciliar_pendientes(
    db: Session,
    revision_id: int,
    tipos: set[str],
    satisfechos: set[tuple[int | None, int | None, str]],
) -> int:
    """Cierra los PendienteBoletin abiertos de esta revisión y de estos tipos
    cuya (area_id, estudiante_id, tipo) esté en `satisfechos` — es decir, lo
    que en la corrida anterior faltaba y AHORA ya viene cargado en SAPRED.
    Así el reporte '¿qué falta?' no arrastra pendientes viejos ya resueltos."""
    if not satisfechos:
        return 0
    abiertos = db.scalars(
        select(models.PendienteBoletin).where(
            models.PendienteBoletin.revision_id == revision_id,
            models.PendienteBoletin.resuelto.is_(False),
            models.PendienteBoletin.tipo.in_(tipos),
        )
    ).all()
    ahora = dt.datetime.utcnow()
    cerrados = 0
    for p in abiertos:
        if (p.area_id, p.estudiante_id, p.tipo) in satisfechos:
            p.resuelto = True
            p.resuelto_en = ahora
            p.detalle = _detalle_cerrado_auto(p.detalle)
            cerrados += 1
    return cerrados


_MARCA_GRUPAL_OBSOLETO = " · Cerrado: el dato SÍ está cargado en SAPRED (pendiente viejo)"


def _ids_pendientes_obsoletos(
    db: Session, anio_lectivo: int, periodo: int | None = None
) -> set[int]:
    """IDs de pendientes abiertos que YA NO aplican porque el dato sí está
    cargado: hay NotaSapred (tipo 'nota') o TextoBoletin con texto ('concepto'
    / 'observacion') para ese estudiante+área (o para cualquiera del grupo, si
    el pendiente es grupal con estudiante_id NULL — p. ej. el viejo
    'Observaciones del grupo pendientes por completar'). No modifica nada; es
    para que los reportes a los docentes no arrastren pendientes ya resueltos
    que nunca se reconciliaron."""
    rev_stmt = select(models.RevisionBoletin.id).where(
        models.RevisionBoletin.anio_lectivo == anio_lectivo
    )
    if periodo is not None:
        rev_stmt = rev_stmt.where(models.RevisionBoletin.periodo == periodo)
    rev_ids = set(db.scalars(rev_stmt).all())
    if not rev_ids:
        return set()

    pend = db.scalars(
        select(models.PendienteBoletin).where(
            models.PendienteBoletin.revision_id.in_(rev_ids),
            models.PendienteBoletin.resuelto.is_(False),
            models.PendienteBoletin.tipo.in_(["nota", "concepto", "observacion"]),
        )
    ).all()
    if not pend:
        return set()

    notas_est: set = set()
    notas_area: set = set()
    for n in db.scalars(select(models.NotaSapred).where(models.NotaSapred.revision_id.in_(rev_ids))).all():
        notas_est.add((n.revision_id, n.area_id, n.estudiante_id))
        notas_area.add((n.revision_id, n.area_id))

    tex_est: set = set()
    tex_area: set = set()
    for t in db.scalars(select(models.TextoBoletin).where(models.TextoBoletin.revision_id.in_(rev_ids))).all():
        if not (t.texto or "").strip():
            continue
        tex_est.add((t.revision_id, t.area_id, t.estudiante_id, t.tipo))
        tex_area.add((t.revision_id, t.area_id, t.tipo))

    obsoletos: set[int] = set()
    for p in pend:
        if p.tipo == "nota":
            hay = (
                (p.revision_id, p.area_id) in notas_area
                if p.estudiante_id is None
                else (p.revision_id, p.area_id, p.estudiante_id) in notas_est
            )
        else:  # concepto | observacion
            hay = (
                (p.revision_id, p.area_id, p.tipo) in tex_area
                if p.estudiante_id is None
                else (p.revision_id, p.area_id, p.estudiante_id, p.tipo) in tex_est
            )
        if hay:
            obsoletos.add(p.id)
    return obsoletos


def depurar_pendientes_obsoletos(
    db: Session, anio_lectivo: int, periodo: int | None = None
) -> int:
    """Igual que `_ids_pendientes_obsoletos` pero los CIERRA de verdad
    (resuelto=True). Se usa al reimportar / desde el botón de mantenimiento."""
    ids = _ids_pendientes_obsoletos(db, anio_lectivo, periodo)
    if not ids:
        return 0
    ahora = dt.datetime.utcnow()
    for p in db.scalars(
        select(models.PendienteBoletin).where(models.PendienteBoletin.id.in_(ids))
    ).all():
        p.resuelto = True
        p.resuelto_en = ahora
        p.detalle = (p.detalle or "").split(_MARCA_GRUPAL_OBSOLETO)[0].rstrip() + _MARCA_GRUPAL_OBSOLETO
    db.commit()
    return len(ids)


def _cobertura_docentes(db: Session, anio_lectivo: int) -> dict[int, set]:
    """docente_id -> conjunto de:
      · (sede_id, grado, curso, area_id)      — dicta ESA área en ese grupo
      · ("GRUPO", sede_id, grado, curso)      — maestro de TODO el grupo (rural)
      · ("DIRECTOR", sede_id, grado, curso)   — director de grupo: responde por
                                                la observación de cada estudiante
                                                Y por la nota de comportamiento
                                                (Desempeño Actitudinal), no por
                                                las notas de las otras áreas
    Se arma con AsignacionDocente y con el horario (BloqueHorario). Un bloque
    del horario cuya área no se pudo mapear NO aporta cobertura (sería
    demasiado amplio). Una AsignacionDocente sin área es "todo el grupo" solo
    si ese grupo no tiene NINGÚN profesor por área (ni en asignaciones ni en
    el horario); si lo tiene, esa asignación es "director de grupo"."""
    comportamiento_id = _area_comportamiento_id(db)
    asignaciones = list(
        db.scalars(
            select(models.AsignacionDocente).where(models.AsignacionDocente.anio_lectivo == anio_lectivo)
        ).all()
    )
    bloques = list(
        db.scalars(
            select(models.BloqueHorario).where(
                models.BloqueHorario.anio_lectivo == anio_lectivo,
                models.BloqueHorario.estado == "activo",
                models.BloqueHorario.area_id.is_not(None),
            )
        ).all()
    )
    grupos_con_area = {(a.sede_id, a.grado, a.curso) for a in asignaciones if a.area_id is not None}
    grupos_con_area |= {(b.sede_id, b.grado, b.curso) for b in bloques}

    cob: dict[int, set] = {}
    for a in asignaciones:
        if a.area_id is not None:
            cob.setdefault(a.docente_id, set()).add((a.sede_id, a.grado, a.curso, a.area_id))
        elif (a.sede_id, a.grado, a.curso) in grupos_con_area:
            s = cob.setdefault(a.docente_id, set())
            s.add(("DIRECTOR", a.sede_id, a.grado, a.curso))
            if comportamiento_id is not None:
                s.add((a.sede_id, a.grado, a.curso, comportamiento_id))  # nota de comportamiento
        else:
            cob.setdefault(a.docente_id, set()).add(("GRUPO", a.sede_id, a.grado, a.curso))
    for b in bloques:
        cob.setdefault(b.docente_id, set()).add((b.sede_id, b.grado, b.curso, b.area_id))
    return cob


def _docente_cubre(cob: set, sede_id: int, grado: int, curso: int | None, area_id: int | None) -> bool:
    if ("GRUPO", sede_id, grado, curso) in cob:
        return True
    if area_id is None:  # observación del director de grupo
        return ("DIRECTOR", sede_id, grado, curso) in cob
    return (sede_id, grado, curso, area_id) in cob


def listar_pendientes(
    db: Session,
    anio_lectivo: int,
    periodo: int | None = None,
    sede_id: int | None = None,
    grado: int | None = None,
    curso: int | None = None,
    docente_id: int | None = None,
    area_id: int | None = None,
    solo_no_resueltos: bool = True,
    solo_ietaba: bool = True,
    incluir_posibles_retirados: bool = False,
    incluir_obsoletos: bool = False,
) -> list[schemas.PendienteConGrupo]:
    stmt = (
        select(models.PendienteBoletin)
        .join(models.RevisionBoletin, models.PendienteBoletin.revision_id == models.RevisionBoletin.id)
        .where(models.RevisionBoletin.anio_lectivo == anio_lectivo)
    )
    if periodo is not None:
        stmt = stmt.where(models.RevisionBoletin.periodo == periodo)
    if sede_id is not None:
        stmt = stmt.where(models.RevisionBoletin.sede_id == sede_id)
    if grado is not None:
        stmt = stmt.where(models.RevisionBoletin.grado == grado)
    if curso is not None:
        stmt = stmt.where(models.RevisionBoletin.curso == curso)
    if area_id is not None:
        stmt = stmt.where(models.PendienteBoletin.area_id == area_id)
    if solo_no_resueltos:
        stmt = stmt.where(models.PendienteBoletin.resuelto.is_(False))

    pendientes = db.scalars(stmt).all()

    sedes = {s.id: s for s in db.scalars(select(models.Sede)).all()}
    if solo_ietaba:
        pendientes = [p for p in pendientes if (sedes.get(p.revision.sede_id) or models.Sede()).pertenece_ietaba]
    if not incluir_posibles_retirados:
        pendientes = [p for p in pendientes if not (p.estudiante and p.estudiante.posible_retirado)]
    if solo_no_resueltos and not incluir_obsoletos:
        obsoletos = _ids_pendientes_obsoletos(db, anio_lectivo, periodo)
        if obsoletos:
            pendientes = [p for p in pendientes if p.id not in obsoletos]

    asignaciones = db.scalars(
        select(models.AsignacionDocente).where(models.AsignacionDocente.anio_lectivo == anio_lectivo)
    ).all()
    por_area_docente: dict[tuple[int, int, int | None, int], models.AsignacionDocente] = {}
    por_grupo_docente: dict[tuple[int, int, int | None], models.AsignacionDocente] = {}
    for a in asignaciones:
        if a.area_id is not None:
            por_area_docente[(a.sede_id, a.grado, a.curso, a.area_id)] = a
        else:
            por_grupo_docente[(a.sede_id, a.grado, a.curso)] = a

    cobertura = _cobertura_docentes(db, anio_lectivo) if docente_id is not None else {}

    resultado = []
    for p in pendientes:
        r = p.revision
        sede = sedes.get(r.sede_id)
        asign = None
        if p.area_id is not None:
            asign = por_area_docente.get((r.sede_id, r.grado, r.curso, p.area_id))
        if asign is None:
            asign = por_grupo_docente.get((r.sede_id, r.grado, r.curso))
        if docente_id is not None:
            # Coincide por AsignacionDocente o por el horario (BloqueHorario).
            por_asign = asign is not None and asign.docente_id == docente_id
            por_horario = _docente_cubre(
                cobertura.get(docente_id, set()), r.sede_id, r.grado, r.curso, p.area_id
            )
            if not (por_asign or por_horario):
                continue
            if asign is None and por_horario:
                asign = None  # no hay AsignacionDocente, pero sí lo cubre el horario

        nombre_grado = models.GRADOS_NOMBRES.get(r.grado, str(r.grado))
        nombre_grupo = (
            f"{nombre_grado} - {models.DIVISIONES_NOMBRES.get(r.curso, r.curso)}" if r.curso else nombre_grado
        )
        resultado.append(
            schemas.PendienteConGrupo(
                id=p.id,
                tipo=p.tipo,
                detalle=p.detalle,
                resuelto=p.resuelto,
                creado_en=p.creado_en,
                resuelto_en=p.resuelto_en,
                area=schemas.Area.model_validate(p.area) if p.area else None,
                estudiante=schemas.EstudianteMini.model_validate(p.estudiante) if p.estudiante else None,
                sede_id=r.sede_id,
                sede_nombre=sede.nombre if sede else "",
                grado=r.grado,
                curso=r.curso,
                nombre_grupo=nombre_grupo,
                periodo=r.periodo,
                anio_lectivo=r.anio_lectivo,
                docente=schemas.Docente.model_validate(asign.docente) if asign else None,
            )
        )
    resultado.sort(key=lambda p: (p.sede_nombre, p.grado, p.nombre_grupo))
    return resultado


def pendientes_por_docente(
    db: Session,
    anio_lectivo: int,
    periodo: int | None = None,
    solo_ietaba: bool = True,
) -> schemas.PendientesPorDocente:
    """Por cada docente: qué grupos tiene a cargo y cuántos pendientes de
    boletín (notas / conceptos / observaciones) tiene abiertos. Responde a
    '¿al profesor X le falta algo?'. La cobertura sale de AsignacionDocente y
    del horario importado."""
    obsoletos = _ids_pendientes_obsoletos(db, anio_lectivo, periodo)
    cobertura = _cobertura_docentes(db, anio_lectivo)

    rev_stmt = select(func.count()).select_from(models.RevisionBoletin).where(
        models.RevisionBoletin.anio_lectivo == anio_lectivo
    )
    if periodo is not None:
        rev_stmt = rev_stmt.where(models.RevisionBoletin.periodo == periodo)
    hay_auditoria = (db.scalar(rev_stmt) or 0) > 0

    if not cobertura:
        return schemas.PendientesPorDocente(periodo=periodo, hay_auditoria=hay_auditoria, docentes=[])

    sedes = {s.id: s for s in db.scalars(select(models.Sede)).all()}
    areas = {a.id: a for a in db.scalars(select(models.Area)).all()}
    docentes = {d.id: d for d in db.scalars(select(models.Docente)).all()}

    stmt = (
        select(models.PendienteBoletin)
        .join(models.RevisionBoletin, models.PendienteBoletin.revision_id == models.RevisionBoletin.id)
        .where(
            models.RevisionBoletin.anio_lectivo == anio_lectivo,
            models.PendienteBoletin.resuelto.is_(False),
        )
    )
    if periodo is not None:
        stmt = stmt.where(models.RevisionBoletin.periodo == periodo)
    pendientes = [p for p in db.scalars(stmt).all() if p.id not in obsoletos]

    def _es_ietaba(sede_id: int) -> bool:
        s = sedes.get(sede_id)
        return bool(s and s.pertenece_ietaba)

    # Acumulador por docente
    acc: dict[int, dict] = {}
    for did, cob in cobertura.items():
        grupos = set()
        dirige = set()
        areas_dic = set()
        sedes_dic = set()
        for item in cob:
            es_director = False
            if isinstance(item[0], str):  # ("GRUPO"|"DIRECTOR", sede, grado, curso)
                marca, sede_id, grado, curso = item
                area_id = None
                es_director = marca == "DIRECTOR"
            else:
                sede_id, grado, curso, area_id = item
            if solo_ietaba and not _es_ietaba(sede_id):
                continue
            nombre_grado = models.GRADOS_NOMBRES.get(grado, str(grado))
            etq = f"{nombre_grado} - {models.DIVISIONES_NOMBRES.get(curso, curso)}" if curso else nombre_grado
            grupos.add(etq)
            if es_director:
                dirige.add(etq)
            if area_id and area_id in areas:
                areas_dic.add(areas[area_id].nombre)
            s = sedes.get(sede_id)
            if s:
                sedes_dic.add(s.nombre)
        if not grupos:
            continue
        acc[did] = {
            "grupos": sorted(grupos),
            "dirige": sorted(dirige),
            "areas": sorted(areas_dic),
            "sedes": sorted(sedes_dic),
            "abiertos": 0,
            "por_tipo": {"nota": 0, "concepto": 0, "observacion": 0},
        }

    for p in pendientes:
        r = p.revision
        if solo_ietaba and not _es_ietaba(r.sede_id):
            continue
        if p.estudiante and p.estudiante.posible_retirado:
            continue  # no cuenta: la secretaría lo marcó como posible retirado
        for did, cob in cobertura.items():
            if did not in acc:
                continue
            if _docente_cubre(cob, r.sede_id, r.grado, r.curso, p.area_id):
                acc[did]["abiertos"] += 1
                acc[did]["por_tipo"][p.tipo] = acc[did]["por_tipo"].get(p.tipo, 0) + 1

    salida = [
        schemas.DocentePendientesResumen(
            docente=schemas.Docente.model_validate(docentes[did]),
            grupos=v["grupos"],
            dirige=v["dirige"],
            areas=v["areas"],
            sedes=v["sedes"],
            abiertos=v["abiertos"],
            por_tipo=v["por_tipo"],
            al_dia=v["abiertos"] == 0,
        )
        for did, v in acc.items()
        if did in docentes
    ]
    salida.sort(key=lambda x: (-x.abiertos, x.docente.nombre_completo))
    return schemas.PendientesPorDocente(
        periodo=periodo, hay_auditoria=hay_auditoria, docentes=salida
    )


def reporte_faltantes_por_docente(
    db: Session,
    anio_lectivo: int,
    periodo: int | None = None,
    docente_id: int | None = None,
    solo_ietaba: bool = True,
) -> schemas.ReporteFaltantes:
    """Arma el reporte imprimible '¿qué le falta a cada profesor?'. Regla que
    pidió el usuario: si a TODO el grupo le falta lo mismo (p. ej. la
    observación), no se listan los nombres uno por uno — se marca 'todo el
    grupo'. Si solo a algunos les falta, se listan esos nombres."""
    obsoletos = _ids_pendientes_obsoletos(db, anio_lectivo, periodo)
    cobertura = _cobertura_docentes(db, anio_lectivo)
    sedes = {s.id: s for s in db.scalars(select(models.Sede)).all()}
    areas = {a.id: a for a in db.scalars(select(models.Area)).all()}
    docentes = {d.id: d for d in db.scalars(select(models.Docente)).all()}

    def _es_ietaba(sede_id: int) -> bool:
        s = sedes.get(sede_id)
        return bool(s and s.pertenece_ietaba)

    # Matrícula activa por (sede, grado, curso) — sin los "posible retirado".
    roster: dict[tuple[int, int, int | None], int] = {}
    for sede_id, grado, curso, n in db.execute(
        select(
            models.Estudiante.sede_id,
            models.Estudiante.grado,
            models.Estudiante.curso,
            func.count(),
        )
        .where(
            models.Estudiante.estado == "ACTIVO",
            models.Estudiante.posible_retirado.is_(False),
        )
        .group_by(models.Estudiante.sede_id, models.Estudiante.grado, models.Estudiante.curso)
    ).all():
        roster[(sede_id, grado, curso)] = n

    stmt = (
        select(models.PendienteBoletin)
        .join(models.RevisionBoletin, models.PendienteBoletin.revision_id == models.RevisionBoletin.id)
        .where(
            models.RevisionBoletin.anio_lectivo == anio_lectivo,
            models.PendienteBoletin.resuelto.is_(False),
        )
    )
    if periodo is not None:
        stmt = stmt.where(models.RevisionBoletin.periodo == periodo)
    pendientes = [p for p in db.scalars(stmt).all() if p.id not in obsoletos]

    # docente_id | None ("sin docente")  ->  clave de bucket  ->  acumulador
    Clave = tuple  # (sede_id, grado, curso, periodo, area_id, tipo)
    buckets: dict[int | None, dict[Clave, dict]] = {}

    def _bucket(did: int | None, clave: Clave) -> dict:
        return buckets.setdefault(did, {}).setdefault(
            clave, {"nombres": set(), "grupo_flag": False}
        )

    for p in pendientes:
        r = p.revision
        if solo_ietaba and not _es_ietaba(r.sede_id):
            continue
        if p.estudiante and p.estudiante.posible_retirado:
            continue
        clave = (r.sede_id, r.grado, r.curso, r.periodo, p.area_id, p.tipo)
        dids = [
            did
            for did, cob in cobertura.items()
            if _docente_cubre(cob, r.sede_id, r.grado, r.curso, p.area_id)
        ]
        if docente_id is not None:
            dids = [d for d in dids if d == docente_id]
        destinos = dids if dids else ([] if docente_id is not None else [None])
        for d in destinos:
            b = _bucket(d, clave)
            if p.estudiante_id is None:
                b["grupo_flag"] = True
            elif p.estudiante:
                b["nombres"].add(p.estudiante.nombre_completo)

    def _item(clave: Clave, b: dict) -> schemas.ReporteFaltanteItem:
        sede_id, grado, curso, per, area_id, tipo = clave
        total = roster.get((sede_id, grado, curso), 0)
        n_faltan = len(b["nombres"])
        es_grupo = bool(b["grupo_flag"]) or (total > 0 and n_faltan >= total)
        nombre_grado = models.GRADOS_NOMBRES.get(grado, str(grado))
        nombre_grupo = (
            f"{nombre_grado} - {models.DIVISIONES_NOMBRES.get(curso, curso)}" if curso else nombre_grado
        )
        area_nombre = (
            "Observación (director de grupo)"
            if area_id is None
            else (areas[area_id].nombre if area_id in areas else "—")
        )
        return schemas.ReporteFaltanteItem(
            sede_nombre=sedes[sede_id].nombre if sede_id in sedes else "",
            grado=grado,
            curso=curso,
            nombre_grupo=nombre_grupo,
            periodo=per,
            area_id=area_id,
            area_nombre=area_nombre,
            tipo=tipo,
            alcance="grupo" if es_grupo else "parcial",
            n_faltan=(total if es_grupo and total else max(n_faltan, 1)),
            total_grupo=total,
            estudiantes=[] if es_grupo else sorted(b["nombres"]),
        )

    def _etq_grupo(g: int, c: int | None) -> str:
        ng = models.GRADOS_NOMBRES.get(g, str(g))
        return f"{ng} - {models.DIVISIONES_NOMBRES.get(c, c)}" if c else ng

    docentes_salida: list[schemas.ReporteFaltantesDocente] = []
    for did, clave_map in buckets.items():
        if did is None:
            continue
        if did not in docentes:
            continue
        items = [_item(k, b) for k, b in clave_map.items()]
        items.sort(key=lambda it: (it.sede_nombre, it.grado, it.curso or 0, it.area_nombre, it.tipo))

        grupos_todos: set[str] = set()
        dirige: set[str] = set()
        sedes_docente: set[str] = set()
        for item in cobertura.get(did, set()):
            if isinstance(item[0], str):  # ("GRUPO"|"DIRECTOR", sede, grado, curso)
                marca, sede_id, grado, curso = item
                if marca == "DIRECTOR":
                    dirige.add(_etq_grupo(grado, curso))
            else:
                sede_id, grado, curso, _area = item
            if solo_ietaba and not _es_ietaba(sede_id):
                continue
            grupos_todos.add(_etq_grupo(grado, curso))
            if sede_id in sedes:
                sedes_docente.add(sedes[sede_id].nombre)
        grupos_con_falta = {it.nombre_grupo for it in items}
        grupos_ok = sorted(grupos_todos - grupos_con_falta)

        docentes_salida.append(
            schemas.ReporteFaltantesDocente(
                docente=schemas.Docente.model_validate(docentes[did]),
                dirige=sorted(dirige),
                sedes=sorted(sedes_docente),
                grupos=sorted(grupos_todos),
                grupos_ok=grupos_ok,
                total_faltantes=sum(it.n_faltan for it in items),
                items=items,
            )
        )
    docentes_salida.sort(key=lambda d: (-d.total_faltantes, d.docente.nombre_completo))

    sin_docente = [_item(k, b) for k, b in buckets.get(None, {}).items()]
    sin_docente.sort(key=lambda it: (it.sede_nombre, it.grado, it.curso or 0, it.area_nombre, it.tipo))

    return schemas.ReporteFaltantes(
        anio_lectivo=anio_lectivo,
        periodo=periodo,
        generado_en=dt.datetime.utcnow(),
        docentes=docentes_salida,
        sin_docente=sin_docente,
    )


def exportar_pendientes_excel(
    db: Session,
    anio_lectivo: int,
    periodo: int | None = None,
    sede_id: int | None = None,
    grado: int | None = None,
    curso: int | None = None,
    docente_id: int | None = None,
    area_id: int | None = None,
    solo_no_resueltos: bool = True,
    solo_ietaba: bool = True,
    ids: list[int] | None = None,
) -> bytes:
    """Genera el Excel de la tabla de pendientes directamente desde la base
    de datos (no desde una captura de la pantalla ni de un PDF), con los
    mismos filtros que la vista "¿Qué me falta?". Si se pasan ids, exporta
    exactamente esas filas (para "Exportar seleccionados")."""
    import io

    import openpyxl
    from openpyxl.styles import Font

    pendientes = listar_pendientes(
        db, anio_lectivo=anio_lectivo, periodo=periodo, sede_id=sede_id, grado=grado, curso=curso,
        docente_id=docente_id, area_id=area_id, solo_no_resueltos=solo_no_resueltos, solo_ietaba=solo_ietaba,
    )
    if ids is not None:
        ids_set = set(ids)
        pendientes = [p for p in pendientes if p.id in ids_set]

    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "Pendientes"

    encabezados = [
        "Sede", "Grupo", "Grado", "Año", "Período", "Área", "Estudiante", "Documento",
        "Tipo", "Detalle", "Docente", "Resuelto", "Creado en",
    ]
    hoja.append(encabezados)
    for celda in hoja[1]:
        celda.font = Font(bold=True)

    for p in pendientes:
        hoja.append([
            p.sede_nombre,
            p.nombre_grupo,
            p.grado,
            p.anio_lectivo,
            p.periodo,
            p.area.nombre if p.area else "General (todo el grupo)",
            p.estudiante.nombre_completo if p.estudiante else "Todo el grupo",
            p.estudiante.documento if p.estudiante else "",
            p.tipo,
            p.detalle or "",
            p.docente.nombre_completo if p.docente else "Sin asignar",
            "Sí" if p.resuelto else "No",
            p.creado_en.strftime("%Y-%m-%d %H:%M"),
        ])

    for columna, ancho in zip(hoja.columns, [28, 16, 8, 6, 8, 26, 30, 14, 12, 40, 26, 9, 16]):
        hoja.column_dimensions[columna[0].column_letter].width = ancho

    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def resumen_boletines(db: Session, anio_lectivo: int, periodo: int, solo_ietaba: bool = True) -> schemas.ResumenBoletines:
    grupos = listar_grupos_academicos(db, anio_lectivo, periodo)
    if solo_ietaba:
        sedes_ietaba = {
            s.id for s in db.scalars(select(models.Sede).where(models.Sede.pertenece_ietaba.is_(True))).all()
        }
        grupos = [g for g in grupos if g.sede_id in sedes_ietaba]

    total = len(grupos)
    completos = sum(1 for g in grupos if g.estado == "completo")
    en_proceso = sum(1 for g in grupos if g.estado == "en_proceso")
    pendientes = sum(1 for g in grupos if g.estado == "pendiente")
    sin_info = sum(1 for g in grupos if g.estado == "sin_informacion")
    total_pendientes_individuales = sum(g.pendientes_abiertos for g in grupos)
    porcentaje = round((completos / total * 100), 1) if total else 0.0

    def _agrupar(clave_fn, nombre_fn) -> list[schemas.ResumenPorClave]:
        acumulado: dict[int, dict] = {}
        for g in grupos:
            clave = clave_fn(g)
            if clave is None:
                continue
            entrada = acumulado.setdefault(
                clave, {"nombre": nombre_fn(g), "total": 0, "completos": 0, "pendientes": 0}
            )
            entrada["total"] += 1
            if g.estado == "completo":
                entrada["completos"] += 1
            elif g.estado == "pendiente":
                entrada["pendientes"] += 1
        return [
            schemas.ResumenPorClave(
                id=k, nombre=v["nombre"], total_grupos=v["total"], completos=v["completos"], pendientes=v["pendientes"]
            )
            for k, v in sorted(acumulado.items(), key=lambda kv: kv[1]["nombre"])
        ]

    por_sede = _agrupar(lambda g: g.sede_id, lambda g: g.sede_nombre)
    por_docente = _agrupar(
        lambda g: g.docente.id if g.docente else None,
        lambda g: g.docente.nombre_completo if g.docente else "",
    )

    # Por área se arma desde los pendientes puntuales (no desde "docente de
    # todo el grupo"), porque en secundaria una misma grupo tiene varias
    # áreas con distinto profesor cada una.
    areas = {a.id: a for a in db.scalars(select(models.Area)).all()}
    asignaciones_area = db.scalars(
        select(models.AsignacionDocente).where(
            models.AsignacionDocente.anio_lectivo == anio_lectivo,
            models.AsignacionDocente.area_id.is_not(None),
        )
    ).all()
    grupos_por_area: dict[int, set[tuple[int, int, int | None]]] = {}
    for a in asignaciones_area:
        grupos_por_area.setdefault(a.area_id, set()).add((a.sede_id, a.grado, a.curso))

    ids_grupos_scope = {(g.sede_id, g.grado, g.curso) for g in grupos}

    filas_pend_area = db.execute(
        select(
            models.PendienteBoletin.area_id,
            models.RevisionBoletin.sede_id,
            models.RevisionBoletin.grado,
            models.RevisionBoletin.curso,
        )
        .join(models.RevisionBoletin, models.PendienteBoletin.revision_id == models.RevisionBoletin.id)
        .where(
            models.RevisionBoletin.anio_lectivo == anio_lectivo,
            models.RevisionBoletin.periodo == periodo,
            models.PendienteBoletin.resuelto.is_(False),
            models.PendienteBoletin.area_id.is_not(None),
        )
    ).all()
    pendientes_por_area: dict[int, set[tuple[int, int, int | None]]] = {}
    for area_id, sede_id, grado, curso in filas_pend_area:
        pendientes_por_area.setdefault(area_id, set()).add((sede_id, grado, curso))

    por_area = []
    for area_id, grupos_area in grupos_por_area.items():
        grupos_area_en_scope = grupos_area & ids_grupos_scope
        if not grupos_area_en_scope:
            continue
        area = areas.get(area_id)
        pend = len(pendientes_por_area.get(area_id, set()) & grupos_area_en_scope)
        por_area.append(
            schemas.ResumenPorClave(
                id=area_id,
                nombre=area.nombre if area else "",
                total_grupos=len(grupos_area_en_scope),
                completos=len(grupos_area_en_scope) - pend,
                pendientes=pend,
            )
        )
    por_area.sort(key=lambda r: r.nombre)

    return schemas.ResumenBoletines(
        anio_lectivo=anio_lectivo,
        periodo=periodo,
        total_grupos=total,
        completos=completos,
        en_proceso=en_proceso,
        pendientes=pendientes,
        sin_informacion=sin_info,
        porcentaje_completo=porcentaje,
        total_pendientes_individuales=total_pendientes_individuales,
        por_sede=por_sede,
        por_docente=por_docente,
        por_area=por_area,
    )


def guardar_revision_boletin(db: Session, datos: schemas.RevisionBoletinGuardar) -> models.RevisionBoletin:
    existente = db.scalar(
        select(models.RevisionBoletin).where(
            models.RevisionBoletin.sede_id == datos.sede_id,
            models.RevisionBoletin.grado == datos.grado,
            models.RevisionBoletin.curso == datos.curso,
            models.RevisionBoletin.anio_lectivo == datos.anio_lectivo,
            models.RevisionBoletin.periodo == datos.periodo,
        )
    )
    campos = datos.model_dump()
    if existente:
        for campo, valor in campos.items():
            setattr(existente, campo, valor)
        existente.revisado_en = dt.datetime.utcnow()
    else:
        existente = models.RevisionBoletin(**campos, revisado_en=dt.datetime.utcnow())
        db.add(existente)
    db.commit()
    db.refresh(existente)
    return existente


def listar_grupos_academicos(db: Session, anio_lectivo: int, periodo: int = 1) -> list[schemas.GrupoAcademico]:
    stmt = (
        select(
            models.Estudiante.sede_id,
            models.Estudiante.grado,
            models.Estudiante.curso,
            func.count().label("total"),
        )
        .where(models.Estudiante.estado == "ACTIVO", models.Estudiante.sede_id.is_not(None))
        .group_by(models.Estudiante.sede_id, models.Estudiante.grado, models.Estudiante.curso)
    )
    filas = db.execute(stmt).all()

    # Solo las asignaciones de TODO el grupo (area_id None, típico de sedes
    # rurales con un solo maestro) alimentan el campo "docente" del grupo.
    # Las asignaciones por área (secundaria, un profesor por materia) no
    # tienen un único "docente del grupo" que mostrar aquí.
    asignaciones = {
        (a.sede_id, a.grado, a.curso): a
        for a in db.scalars(
            select(models.AsignacionDocente).where(
                models.AsignacionDocente.anio_lectivo == anio_lectivo,
                models.AsignacionDocente.area_id.is_(None),
            )
        ).all()
    }
    revisiones = {
        (r.sede_id, r.grado, r.curso): r
        for r in db.scalars(
            select(models.RevisionBoletin).where(
                models.RevisionBoletin.anio_lectivo == anio_lectivo,
                models.RevisionBoletin.periodo == periodo,
            )
        ).all()
    }
    sedes = {s.id: s for s in db.scalars(select(models.Sede)).all()}

    pendientes_abiertos_por_revision: dict[int, int] = {}
    if revisiones:
        ids_revision = [r.id for r in revisiones.values()]
        filas_pend = db.execute(
            select(models.PendienteBoletin.revision_id, func.count())
            .where(
                models.PendienteBoletin.revision_id.in_(ids_revision),
                models.PendienteBoletin.resuelto.is_(False),
            )
            .group_by(models.PendienteBoletin.revision_id)
        ).all()
        pendientes_abiertos_por_revision = {rid: cnt for rid, cnt in filas_pend}

    resultado = []
    for sede_id, grado, curso, total in filas:
        sede = sedes.get(sede_id)
        nombre_grado = models.GRADOS_NOMBRES.get(grado, str(grado))
        nombre_grupo = (
            f"{nombre_grado} - {models.DIVISIONES_NOMBRES.get(curso, curso)}" if curso else nombre_grado
        )
        asignacion = asignaciones.get((sede_id, grado, curso))
        revision = revisiones.get((sede_id, grado, curso))
        abiertos = pendientes_abiertos_por_revision.get(revision.id, 0) if revision else 0
        resultado.append(
            schemas.GrupoAcademico(
                sede_id=sede_id,
                sede_nombre=sede.nombre if sede else "",
                grado=grado,
                nombre_grado=nombre_grado,
                curso=curso,
                nombre_grupo=nombre_grupo,
                total_estudiantes=total,
                docente=schemas.Docente.model_validate(asignacion.docente) if asignacion else None,
                revision=schemas.RevisionBoletin.model_validate(revision) if revision else None,
                estado=calcular_estado_grupo(revision, abiertos),
                pendientes_abiertos=abiertos,
            )
        )
    resultado.sort(key=lambda g: (g.sede_nombre, g.grado, g.curso or 0))
    return resultado


# --- Módulo docente: mis cursos / mis estudiantes ----------------------------
# El alcance de un docente sale de SUS PROPIAS asignaciones (AsignacionDocente),
# nunca de lo que mande la URL/querystring — así un docente no puede ver
# estudiantes de un grupo ajeno con solo cambiar el id en la petición.


def mis_cursos_docente(db: Session, docente_id: int, anio_lectivo: int) -> list[schemas.CursoDocente]:
    asignaciones = db.scalars(
        select(models.AsignacionDocente).where(
            models.AsignacionDocente.docente_id == docente_id,
            models.AsignacionDocente.anio_lectivo == anio_lectivo,
        )
    ).all()
    resultado = []
    for a in asignaciones:
        total = db.scalar(
            select(func.count(models.Estudiante.id)).where(
                models.Estudiante.sede_id == a.sede_id,
                models.Estudiante.grado == a.grado,
                (models.Estudiante.curso == a.curso) if a.curso is not None else models.Estudiante.curso.is_(None),
                models.Estudiante.estado == "ACTIVO",
            )
        ) or 0
        nombre_grado = models.GRADOS_NOMBRES.get(a.grado, str(a.grado))
        nombre_grupo = (
            f"{nombre_grado} - {models.DIVISIONES_NOMBRES.get(a.curso, a.curso)}" if a.curso else nombre_grado
        )
        resultado.append(
            schemas.CursoDocente(
                sede_id=a.sede_id, sede_nombre=a.sede.nombre,
                grado=a.grado, nombre_grado=nombre_grado,
                curso=a.curso, nombre_grupo=nombre_grupo,
                area_id=a.area_id, area_nombre=a.area.nombre if a.area else "Director de grupo",
                total_estudiantes=total,
            )
        )
    resultado.sort(key=lambda c: (c.sede_nombre, c.grado, c.curso or 0, c.area_nombre))
    return resultado


def docente_tiene_acceso_grupo(
    db: Session, docente_id: int, sede_id: int, grado: int, curso: int | None, anio_lectivo: int
) -> bool:
    """True si el docente tiene alguna asignación (de área, o de todo el
    grupo) sobre ese grupo este año. Es la comprobación de seguridad real:
    el frontend nunca decide esto, solo lo refleja."""
    existe = db.scalar(
        select(models.AsignacionDocente.id).where(
            models.AsignacionDocente.docente_id == docente_id,
            models.AsignacionDocente.sede_id == sede_id,
            models.AsignacionDocente.grado == grado,
            (models.AsignacionDocente.curso == curso) if curso is not None else models.AsignacionDocente.curso.is_(None),
            models.AsignacionDocente.anio_lectivo == anio_lectivo,
        )
    )
    return existe is not None


def docente_es_director_del_grupo(
    db: Session, docente_id: int, sede_id: int, grado: int, curso: int | None, anio_lectivo: int
) -> bool:
    """True solo si la asignación del docente sobre ese grupo es de TODO el
    grupo (area_id NULL: director de grupo, o maestro único de sede rural).
    Decisión del colegio (22/09/2026): la ficha/perfil completo del
    estudiante la ve el director de grupo, no cualquier profesor de área que
    también le dicte una materia — ellos siguen viendo el listado del grupo
    para pasar asistencia, pero no el detalle del estudiante."""
    existe = db.scalar(
        select(models.AsignacionDocente.id).where(
            models.AsignacionDocente.docente_id == docente_id,
            models.AsignacionDocente.sede_id == sede_id,
            models.AsignacionDocente.grado == grado,
            (models.AsignacionDocente.curso == curso) if curso is not None else models.AsignacionDocente.curso.is_(None),
            models.AsignacionDocente.anio_lectivo == anio_lectivo,
            models.AsignacionDocente.area_id.is_(None),
        )
    )
    return existe is not None


def estudiantes_de_grupo_docente(
    db: Session, sede_id: int, grado: int, curso: int | None
) -> list[models.Estudiante]:
    return listar_estudiantes(db, sede_id=sede_id, grado=grado, curso=curso, estado="ACTIVO")


def estudiante_a_perfil_docente(e: models.Estudiante) -> schemas.EstudianteDocentePerfil:
    nombre_grado = models.GRADOS_NOMBRES.get(e.grado, str(e.grado))
    return schemas.EstudianteDocentePerfil(
        id=e.id, documento=e.documento, nombre_completo=e.nombre_completo,
        genero=e.genero, fecha_nacimiento=e.fecha_nacimiento,
        grado=e.grado, nombre_grado=nombre_grado, curso=e.curso, nombre_grupo=e.grupo,
        sede_id=e.sede_id, sede_nombre=e.sede.nombre if e.sede else "", estado=e.estado,
    )


DIAS_ASISTENCIA_DOCENTE = 30


def _resumen_asistencia(
    db: Session, estudiante_ids: list[int], area_id: int | None, solo_area: bool
) -> dict[int, schemas.AsistenciaResumen]:
    """Ausencias/tardanzas/excusas de los últimos 30 días por estudiante. Un
    profesor de área ve solo las de SUS clases (solo_area); el director de
    grupo, todas."""
    desde = fechas.hoy_colombia() - dt.timedelta(days=DIAS_ASISTENCIA_DOCENTE)
    stmt = (
        select(models.Asistencia.estudiante_id, models.Asistencia.estado, func.count())
        .where(
            models.Asistencia.estudiante_id.in_(estudiante_ids),
            models.Asistencia.fecha >= desde,
            models.Asistencia.anulado.is_(False),
            models.Asistencia.estado.in_(("ausente", "tardanza", "excusa")),
        )
        .group_by(models.Asistencia.estudiante_id, models.Asistencia.estado)
    )
    if solo_area:
        stmt = stmt.where(models.Asistencia.area_id == area_id)
    conteo: dict[int, dict[str, int]] = {}
    for est_id, estado, n in db.execute(stmt) if estudiante_ids else []:
        conteo.setdefault(est_id, {})[estado] = n
    return {
        i: schemas.AsistenciaResumen(
            dias=DIAS_ASISTENCIA_DOCENTE, ausencias=conteo.get(i, {}).get("ausente", 0),
            tardanzas=conteo.get(i, {}).get("tardanza", 0), excusas=conteo.get(i, {}).get("excusa", 0),
        )
        for i in estudiante_ids
    }


def seguimiento_grupo_docente(
    db: Session, docente_id: int, sede_id: int, grado: int, curso: int | None, area_id: int | None, anio: int
) -> schemas.SeguimientoGrupoDocente:
    """"Mis estudiantes" con cómo van: el profesor de área ve sus notas en SU
    materia y las faltas en SUS clases; el director de grupo ve además las
    materias que cada uno va perdiendo (todas) y con quién. El área solo se
    acepta si el docente de verdad la dicta en ese grupo — nunca por lo que
    diga la URL."""
    from . import reporte_notas

    es_director = docente_es_director_del_grupo(db, docente_id, sede_id, grado, curso, anio)
    area = None
    if area_id is not None:
        dicta = db.scalar(
            select(models.AsignacionDocente.id).where(
                models.AsignacionDocente.docente_id == docente_id,
                models.AsignacionDocente.sede_id == sede_id,
                models.AsignacionDocente.grado == grado,
                (models.AsignacionDocente.curso == curso) if curso is not None else models.AsignacionDocente.curso.is_(None),
                models.AsignacionDocente.area_id == area_id,
                models.AsignacionDocente.anio_lectivo == anio,
            )
        )
        area = db.get(models.Area, area_id) if dicta else None

    estudiantes = estudiantes_de_grupo_docente(db, sede_id, grado, curso)
    ids = [e.id for e in estudiantes]
    notas, periodos = reporte_notas.rendimiento_de_estudiantes(db, ids, anio)
    docentes = reporte_notas.docentes_por_area(db, sede_id, grado, curso, anio) if es_director else {}
    asistencia = _resumen_asistencia(db, ids, area.id if area else None, solo_area=area is not None and not es_director)
    nota_minima = 3.0

    filas = []
    for e in estudiantes:
        suyas = notas.get(e.id, {})
        fila = schemas.EstudianteSeguimientoDocente(
            id=e.id, documento=e.documento, nombre_completo=e.nombre_completo, genero=e.genero,
            asistencia=asistencia[e.id],
        )
        if area is not None and area.id in suyas:
            por_periodo = suyas[area.id]["por_periodo"]
            promedio = sum(por_periodo.values()) / len(por_periodo)
            fila.notas_area = [schemas.NotaPorPeriodo(periodo=p, valor=v) for p, v in sorted(por_periodo.items())]
            fila.promedio_area = round(promedio, 2)
            fila.estado_area = reporte_notas.estado_materia(promedio, nota_minima)
        if es_director:
            materias = reporte_notas.materias_desde_notas(suyas, nota_minima, docentes)
            fila.materias_perdidas = [m for m in materias if m.estado == "perdida"]
            fila.materias_en_riesgo = sum(1 for m in materias if m.estado == "en_riesgo")
        filas.append(fila)
    return schemas.SeguimientoGrupoDocente(
        es_director=es_director, area_id=area.id if area else None, area_nombre=area.nombre if area else None,
        anio_lectivo=anio, nota_minima=nota_minima, periodos=periodos, estudiantes=filas,
    )


def rendimiento_estudiante_docente(db: Session, e: models.Estudiante, anio: int) -> schemas.RendimientoEstudianteDocente:
    from . import reporte_notas

    desde = fechas.hoy_colombia() - dt.timedelta(days=DIAS_ASISTENCIA_DOCENTE)
    faltas = db.execute(
        select(models.Asistencia.fecha, models.Asistencia.estado, models.Area.nombre)
        .outerjoin(models.Area, models.Asistencia.area_id == models.Area.id)
        .where(
            models.Asistencia.estudiante_id == e.id, models.Asistencia.fecha >= desde,
            models.Asistencia.anulado.is_(False), models.Asistencia.estado.in_(("ausente", "tardanza", "excusa")),
        )
        .order_by(models.Asistencia.fecha.desc())
        .limit(15)
    ).all()
    return schemas.RendimientoEstudianteDocente(
        riesgo=reporte_notas.riesgo_promocion(db, e.id, anio),
        asistencia=_resumen_asistencia(db, [e.id], None, solo_area=False)[e.id],
        ultimas_faltas=[{"fecha": f.isoformat(), "estado": est, "area": area} for f, est, area in faltas],
    )


def estudiante_si_docente_tiene_acceso(
    db: Session, docente_id: int, estudiante_id: int, anio_lectivo: int
) -> models.Estudiante | None:
    """Para lo que SÍ puede hacer cualquier docente asignado al grupo (no
    solo el director): observaciones, asistencia. None si el estudiante no
    existe o no está en ningún grupo del docente — mismo criterio de 404
    "silencioso" que perfil_estudiante_para_docente."""
    e = obtener_estudiante(db, estudiante_id)
    if e is None or e.sede_id is None:
        return None
    if not docente_tiene_acceso_grupo(db, docente_id, e.sede_id, e.grado, e.curso, anio_lectivo):
        return None
    return e


def perfil_estudiante_para_docente(
    db: Session, docente_id: int, estudiante_id: int, anio_lectivo: int
) -> schemas.EstudianteDocentePerfil | None:
    """None si el estudiante no existe, si no está en ningún grupo del
    docente, O si el docente le dicta una materia pero NO es el director de
    ese grupo (ver docente_es_director_del_grupo) — en los tres casos se
    responde igual a propósito, para no revelar por el código de error si el
    id de estudiante existe o a qué grupo pertenece."""
    e = obtener_estudiante(db, estudiante_id)
    if e is None or e.sede_id is None:
        return None
    if not docente_es_director_del_grupo(db, docente_id, e.sede_id, e.grado, e.curso, anio_lectivo):
        return None
    return estudiante_a_perfil_docente(e)


def estudiante_completo_si_es_director(
    db: Session, docente_id: int, estudiante_id: int, anio_lectivo: int
) -> models.Estudiante | None:
    """Igual criterio que perfil_estudiante_para_docente (None si no existe,
    no es su grupo, o le dicta un área pero no es el director), pero devuelve
    el modelo COMPLETO (mismo que usa el módulo administrativo en
    obtener_estudiante) para que el director de grupo pueda abrir la ficha de
    matrícula oficial completa — no solo el perfil acotado."""
    e = obtener_estudiante(db, estudiante_id)
    if e is None or e.sede_id is None:
        return None
    if not docente_es_director_del_grupo(db, docente_id, e.sede_id, e.grado, e.curso, anio_lectivo):
        return None
    return e


# --- Observaciones (académica/convivencia/general/remisión a psicología) ----
# confidencial se decide SIEMPRE aquí (tipo=="psicologia" => True), nunca se
# confía en lo que mande el cliente. Los seguimientos (SeguimientoObservacion)
# solo se incluyen en la salida para quien tiene ver_confidenciales o
# seguimientos.gestionar — es lo que separa "el docente remite" de
# "psicología gestiona el caso" (punto 11 del encargo docente).


def crear_observacion(
    db: Session, estudiante: models.Estudiante, autor_usuario_id: int, datos: schemas.ObservacionCrear
) -> models.Observacion:
    if datos.uuid_cliente:
        existente = db.scalar(
            select(models.Observacion).where(models.Observacion.uuid_cliente == datos.uuid_cliente)
        )
        if existente is not None:
            return existente
    o = models.Observacion(
        uuid_cliente=datos.uuid_cliente, estudiante_id=estudiante.id,
        sede_id=estudiante.sede_id, grado=estudiante.grado, curso=estudiante.curso,
        tipo=datos.tipo, confidencial=(datos.tipo == "psicologia"),
        titulo=(datos.titulo or None), detalle=datos.detalle,
        autor_usuario_id=autor_usuario_id, fecha=datos.fecha or fechas.hoy_colombia(),
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def listar_observaciones_estudiante(
    db: Session, estudiante_id: int, *, usuario_id: int, ve_confidenciales: bool
) -> list[models.Observacion]:
    stmt = select(models.Observacion).where(models.Observacion.estudiante_id == estudiante_id)
    if not ve_confidenciales:
        # Lo confidencial se oculta, salvo lo que el propio usuario escribió
        # (el autor de una remisión sigue viendo su propio texto original).
        stmt = stmt.where(
            models.Observacion.confidencial.is_(False) | (models.Observacion.autor_usuario_id == usuario_id)
        )
    stmt = stmt.order_by(models.Observacion.creado_en.desc())
    return list(db.scalars(stmt).all())


def agregar_seguimiento(db: Session, observacion_id: int, autor_usuario_id: int, nota: str) -> models.SeguimientoObservacion:
    s = models.SeguimientoObservacion(observacion_id=observacion_id, autor_usuario_id=autor_usuario_id, nota=nota)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def cambiar_estado_observacion(
    db: Session, observacion_id: int, usuario_id: int, datos: schemas.ObservacionEstado
) -> models.Observacion | None:
    o = db.get(models.Observacion, observacion_id)
    if o is None:
        return None
    o.estado = datos.estado
    if datos.estado in ("atendida", "cerrada"):
        o.atendida_por_usuario_id = usuario_id
        o.atendida_en = fechas.ahora_utc()
    if datos.nota_atencion is not None:
        o.nota_atencion = datos.nota_atencion
    db.commit()
    db.refresh(o)
    return o


def observacion_a_vista(o: models.Observacion, *, incluir_seguimientos: bool) -> schemas.ObservacionVista:
    return schemas.ObservacionVista(
        id=o.id, estudiante_id=o.estudiante_id,
        estudiante_nombre=o.estudiante.nombre_completo, estudiante_documento=o.estudiante.documento,
        nombre_grupo=o.estudiante.grupo,
        tipo=o.tipo, confidencial=o.confidencial, titulo=o.titulo, detalle=o.detalle,
        autor_nombre=o.autor.nombre if o.autor else "", fecha=o.fecha, creado_en=o.creado_en, estado=o.estado,
        atendida_por_nombre=o.atendida_por.nombre if o.atendida_por else None,
        atendida_en=o.atendida_en, nota_atencion=o.nota_atencion,
        seguimientos=(
            [
                schemas.SeguimientoVista(id=s.id, autor_nombre=s.autor.nombre, nota=s.nota, creado_en=s.creado_en)
                for s in o.seguimientos
            ]
            if incluir_seguimientos
            else []
        ),
    )


# --- Diagnóstico de orientación/psicología (Excel por grado) ---------------


def _grado_nombre(grado: int, curso: int | None) -> str:
    nombre = models.GRADOS_NOMBRES.get(grado, str(grado))
    if not curso:
        return nombre
    division = models.DIVISIONES_NOMBRES.get(curso, str(curso))
    return f"{nombre} - {division}"


def periodo_de_fecha(fecha: dt.date | None) -> str | None:
    """'Marzo 2026' a partir de la fecha real del diagnóstico. None si no se
    pudo determinar la fecha — nunca se inventa un período."""
    if fecha is None:
        return None
    return f"{MESES_TEXTO[fecha.month].capitalize()} {fecha.year}"


def _contar_estudiantes_mencionados(menciones: list[models.DiagnosticoMencion]) -> int:
    """Personas DISTINTAS detrás de una lista de menciones — un mismo
    estudiante puede tener varias situaciones y cuenta una sola vez. Mismo
    criterio de agrupación que usa el frontend (orGruposSituaciones)."""
    claves = {
        f"e{m.estudiante_id}" if m.estudiante_id else f"n{(m.nombre_detectado or m.texto or '').strip().lower()}"
        for m in menciones
    }
    return len(claves)


def mencion_a_vista(db: Session, m: models.DiagnosticoMencion) -> schemas.DiagnosticoMencionVista:
    candidatos = []
    if m.candidatos_json:
        ids = json.loads(m.candidatos_json)
        estudiantes = db.scalars(select(models.Estudiante).where(models.Estudiante.id.in_(ids))) if ids else []
        por_id = {e.id: e for e in estudiantes}
        candidatos = [
            schemas.CandidatoVinculo(id=eid, nombre_completo=por_id[eid].nombre_completo)
            for eid in ids if eid in por_id
        ]
    caso_id = db.scalar(select(models.Caso.id).where(models.Caso.mencion_origen_id == m.id))
    return schemas.DiagnosticoMencionVista(
        id=m.id, categoria=m.categoria, texto=m.texto, nombre_detectado=m.nombre_detectado,
        estudiante_id=m.estudiante_id,
        estudiante_nombre=m.estudiante.nombre_completo if m.estudiante else None,
        estudiante_documento=m.estudiante.documento if m.estudiante else None,
        vinculo_automatico=m.vinculo_automatico,
        confianza=m.confianza, texto_compartido=m.texto_compartido, candidatos=candidatos,
        caso_id=caso_id,
    )


def diagnostico_a_resumen(
    db: Session, d: models.DiagnosticoGrado, *, es_version_actual: bool
) -> schemas.DiagnosticoGradoResumen:
    pendientes = sum(1 for m in d.menciones if m.estudiante_id is None)
    casos = listar_casos_grupo(db, d.sede_id, d.grado, d.curso)
    hoy = fechas.hoy_colombia()
    return schemas.DiagnosticoGradoResumen(
        id=d.id, sede_id=d.sede_id, grado=d.grado, curso=d.curso, grado_nombre=_grado_nombre(d.grado, d.curso),
        hoja_excel=d.hoja_excel, fecha_diligenciado=d.fecha_diligenciado, periodo=periodo_de_fecha(d.fecha_diligenciado),
        importado_en=d.importado_en,
        n_en_lista=d.n_en_lista, n_asisten=d.n_asisten,
        total_menciones=len(d.menciones), estudiantes_mencionados=_contar_estudiantes_mencionados(d.menciones),
        menciones_pendientes=pendientes,
        casos_abiertos=sum(1 for c in casos if c.estado == "abierto"),
        casos_en_seguimiento=sum(1 for c in casos if c.estado == "en_seguimiento"),
        seguimientos_pendientes=sum(
            1 for c in casos if c.estado != "cerrado" and c.proximo_seguimiento and c.proximo_seguimiento <= hoy
        ),
        es_version_actual=es_version_actual,
    )


def listar_diagnosticos_actuales(db: Session, sede_id: int | None = None) -> list[schemas.DiagnosticoGradoResumen]:
    """La última versión de cada grado (por sede+grado+curso), la que ve
    orientación al entrar. Las versiones anteriores quedan disponibles como
    historial dentro del detalle de cada una."""
    stmt = select(models.DiagnosticoGrado).order_by(models.DiagnosticoGrado.importado_en.desc())
    if sede_id is not None:
        stmt = stmt.where(models.DiagnosticoGrado.sede_id == sede_id)
    todos = db.scalars(stmt).all()
    vistos: set[tuple[int, int, int | None]] = set()
    actuales: list[schemas.DiagnosticoGradoResumen] = []
    for d in todos:
        clave = (d.sede_id, d.grado, d.curso)
        if clave in vistos:
            continue
        vistos.add(clave)
        actuales.append(diagnostico_a_resumen(db, d, es_version_actual=True))
    actuales.sort(key=lambda r: (r.grado, r.curso or 0))
    return actuales


def diagnostico_a_detalle(db: Session, d: models.DiagnosticoGrado) -> schemas.DiagnosticoGradoDetalle:
    otras_versiones = db.scalars(
        select(models.DiagnosticoGrado)
        .where(
            models.DiagnosticoGrado.sede_id == d.sede_id,
            models.DiagnosticoGrado.grado == d.grado,
            models.DiagnosticoGrado.curso == d.curso,
        )
        .order_by(models.DiagnosticoGrado.importado_en.desc())
    ).all()
    es_actual = otras_versiones[0].id == d.id if otras_versiones else True
    historial = [diagnostico_a_resumen(db, v, es_version_actual=(v.id == otras_versiones[0].id)) for v in otras_versiones]

    resumen = diagnostico_a_resumen(db, d, es_version_actual=es_actual)
    return schemas.DiagnosticoGradoDetalle(
        **resumen.model_dump(),
        no_asisten_texto=d.no_asisten_texto, desplazados_texto=d.desplazados_texto,
        embarazadas_texto=d.embarazadas_texto, victimas_conflicto_texto=d.victimas_conflicto_texto,
        dificultades_academicas=d.dificultades_academicas, dificultades_comportamiento=d.dificultades_comportamiento,
        acompanamiento_padres=d.acompanamiento_padres, problemas_salud=d.problemas_salud,
        tematicas_trabajar=d.tematicas_trabajar, estrategias_conflicto=d.estrategias_conflicto,
        estrategias_aprendizaje=d.estrategias_aprendizaje, resguardos_atendidos=d.resguardos_atendidos,
        recomendaciones_docentes=d.recomendaciones_docentes, llamados_atencion=d.llamados_atencion,
        orientacion_brindada=d.orientacion_brindada, transporte_escolar=d.transporte_escolar,
        observaciones_generales=d.observaciones_generales, director_grado_nombre=d.director_grado_nombre,
        orientador_escolar_nombre=d.orientador_escolar_nombre, seguimiento_nota=d.seguimiento_nota,
        texto_crudo=d.texto_crudo,
        menciones=[mencion_a_vista(db, m) for m in d.menciones],
        historial=historial,
        casos=[caso_a_vista(c) for c in listar_casos_grupo(db, d.sede_id, d.grado, d.curso)],
    )


def listar_menciones_estudiante(db: Session, estudiante_id: int) -> list[schemas.DiagnosticoEstudianteMencion]:
    menciones = db.scalars(
        select(models.DiagnosticoMencion)
        .join(models.DiagnosticoGrado)
        .where(models.DiagnosticoMencion.estudiante_id == estudiante_id)
        .order_by(models.DiagnosticoGrado.importado_en.desc())
    ).all()
    resultado = []
    for m in menciones:
        d = m.diagnostico
        base = mencion_a_vista(db, m)
        resultado.append(
            schemas.DiagnosticoEstudianteMencion(
                **base.model_dump(), diagnostico_id=d.id, grado=d.grado, curso=d.curso,
                grado_nombre=_grado_nombre(d.grado, d.curso),
                fecha_diligenciado=d.fecha_diligenciado, periodo=periodo_de_fecha(d.fecha_diligenciado),
                importado_en=d.importado_en,
            )
        )
    return resultado


def resumen_estudiante_diagnostico(db: Session, estudiante_id: int) -> schemas.DiagnosticoEstudianteResumen:
    e = db.get(models.Estudiante, estudiante_id)
    basico = None
    if e is not None:
        basico = schemas.EstudianteBasicoOrientacion(
            id=e.id, documento=e.documento, tipo_documento=e.tipo_documento, nombre_completo=e.nombre_completo,
            genero=e.genero, fecha_nacimiento=e.fecha_nacimiento, estado=e.estado, retirado=e.retirado,
            grado=e.grado, curso=e.curso, grupo=e.grupo, sede_id=e.sede_id,
            sede_nombre=e.sede.nombre if e.sede else None,
        )
    return schemas.DiagnosticoEstudianteResumen(
        menciones=listar_menciones_estudiante(db, estudiante_id),
        casos=[caso_a_vista(c) for c in listar_casos_estudiante(db, estudiante_id)],
        estudiante=basico,
    )


def vincular_mencion(
    db: Session, mencion_id: int, estudiante_id: int | None, usuario_id: int
) -> models.DiagnosticoMencion | None:
    m = db.get(models.DiagnosticoMencion, mencion_id)
    if m is None:
        return None
    m.estudiante_id = estudiante_id
    m.vinculo_automatico = False
    m.vinculado_por_usuario_id = usuario_id
    m.vinculado_en = fechas.ahora_utc()
    db.commit()
    db.refresh(m)
    return m


# --- Casos de orientación (trabajo activo sobre un estudiante) -------------
# Nace de "Abrir caso" desde una mención del Excel, o creado a mano. Un caso
# acumula CasoSeguimiento (ver más abajo) — nunca se crea un caso nuevo por
# cada seguimiento, se agrega al historial del mismo caso.

CASO_TIPOS = {
    "academica", "comportamiento", "inasistencia", "intermitencia",
    "familiar", "salud", "convivencia", "orientacion", "riesgo", "otra",
}
CASO_ESTADOS = {"abierto", "en_seguimiento", "cerrado"}

# Categoría detectada en el Excel -> tipo de caso sugerido al "Abrir caso"
# (la orientadora la ve y puede cambiarla antes de guardar; nunca se asigna
# a ciegas sin que ella confirme el formulario).
CATEGORIA_A_TIPO_CASO = {
    "no_asiste": "inasistencia", "intermitencia": "intermitencia",
    "desplazado": "riesgo", "embarazada": "salud", "victima_conflicto": "riesgo",
    "dificultad_academica": "academica", "dificultad_comportamiento": "comportamiento",
    "llamado_atencion": "comportamiento", "salud": "salud",
}


def caso_a_vista(c: models.Caso) -> schemas.CasoVista:
    return schemas.CasoVista(
        id=c.id, estudiante_id=c.estudiante_id, estudiante_nombre=c.estudiante.nombre_completo,
        estudiante_documento=c.estudiante.documento, grado_nombre=_grado_nombre(c.grado, c.curso),
        tipo=c.tipo, titulo=c.titulo, estado=c.estado, fecha_apertura=c.fecha_apertura,
        proximo_seguimiento=c.proximo_seguimiento, origen=c.origen,
        autor_nombre=c.autor.nombre if c.autor else "", creado_en=c.creado_en,
        total_seguimientos=len(c.seguimientos),
    )


def seguimiento_caso_a_vista(s: models.CasoSeguimiento) -> schemas.CasoSeguimientoVista:
    return schemas.CasoSeguimientoVista(
        id=s.id, fecha=s.fecha, tipo_atencion=s.tipo_atencion, situacion=s.situacion,
        accion_realizada=s.accion_realizada, compromisos=s.compromisos, observaciones=s.observaciones,
        proxima_fecha=s.proxima_fecha, autor_nombre=s.autor.nombre if s.autor else "", creado_en=s.creado_en,
    )


def caso_a_detalle(c: models.Caso) -> schemas.CasoDetalle:
    base = caso_a_vista(c)
    return schemas.CasoDetalle(
        **base.model_dump(), sede_id=c.sede_id, grado=c.grado, curso=c.curso,
        descripcion=c.descripcion, acciones=c.acciones, observaciones=c.observaciones,
        cerrado_en=c.cerrado_en, cerrado_por_nombre=c.cerrado_por.nombre if c.cerrado_por else None,
        mencion_origen_id=c.mencion_origen_id,
        seguimientos=[seguimiento_caso_a_vista(s) for s in c.seguimientos],
    )


def listar_casos_grupo(db: Session, sede_id: int, grado: int, curso: int | None) -> list[models.Caso]:
    """Casos del grupo de un diagnóstico. Si el diagnóstico no distingue
    sección (curso=None — pasa con Preescolar: el Excel trae una sola hoja
    combinada aunque la matrícula real tenga dos secciones), se muestran los
    casos de TODO el grado sin filtrar por curso — igual que ya hace
    vincular_estudiante() al buscar candidatos, para no dejar casos reales
    invisibles solo porque el Excel es menos granular que la matrícula."""
    stmt = select(models.Caso).where(models.Caso.sede_id == sede_id, models.Caso.grado == grado)
    if curso is not None:
        stmt = stmt.where(models.Caso.curso == curso)
    return list(db.scalars(stmt.order_by(models.Caso.creado_en.desc())))


def listar_casos_estudiante(db: Session, estudiante_id: int) -> list[models.Caso]:
    return list(
        db.scalars(
            select(models.Caso).where(models.Caso.estudiante_id == estudiante_id).order_by(models.Caso.creado_en.desc())
        )
    )


def crear_caso(db: Session, datos: schemas.CasoCrear, autor_usuario_id: int) -> models.Caso:
    estudiante = db.get(models.Estudiante, datos.estudiante_id)
    c = models.Caso(
        sede_id=estudiante.sede_id, grado=estudiante.grado, curso=estudiante.curso,
        estudiante_id=datos.estudiante_id, tipo=datos.tipo, titulo=(datos.titulo or None),
        descripcion=datos.descripcion, acciones=(datos.acciones or None),
        observaciones=(datos.observaciones or None),
        fecha_apertura=datos.fecha_apertura or fechas.hoy_colombia(),
        proximo_seguimiento=datos.proximo_seguimiento,
        origen="importado" if datos.mencion_origen_id else "manual",
        mencion_origen_id=datos.mencion_origen_id, autor_usuario_id=autor_usuario_id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def cambiar_estado_caso(db: Session, caso_id: int, estado: str, usuario_id: int) -> models.Caso | None:
    c = db.get(models.Caso, caso_id)
    if c is None:
        return None
    c.estado = estado
    if estado == "cerrado":
        c.cerrado_en = fechas.ahora_utc()
        c.cerrado_por_usuario_id = usuario_id
    else:
        c.cerrado_en = None
        c.cerrado_por_usuario_id = None
    db.commit()
    db.refresh(c)
    return c


def agregar_seguimiento_caso(
    db: Session, caso_id: int, datos: schemas.CasoSeguimientoCrear, autor_usuario_id: int
) -> models.Caso | None:
    c = db.get(models.Caso, caso_id)
    if c is None:
        return None
    s = models.CasoSeguimiento(
        caso_id=caso_id, fecha=datos.fecha or fechas.hoy_colombia(),
        tipo_atencion=(datos.tipo_atencion or None), situacion=datos.situacion,
        accion_realizada=(datos.accion_realizada or None), compromisos=(datos.compromisos or None),
        observaciones=(datos.observaciones or None), proxima_fecha=datos.proxima_fecha,
        autor_usuario_id=autor_usuario_id,
    )
    db.add(s)
    # Un seguimiento nuevo indica que el caso ya no está "recién abierto"
    # (salvo que ya estuviera cerrado, eso lo decide un cambio de estado
    # explícito, no un seguimiento) y actualiza cuándo toca el próximo.
    if c.estado != "cerrado":
        c.estado = "en_seguimiento"
    c.proximo_seguimiento = datos.proxima_fecha
    db.commit()
    db.refresh(c)
    return c


def listar_casos_filtrados(
    db: Session, *, sede_id: int | None = None, grado: int | None = None, curso: int | None = None,
    estado: str | None = None, tipo: str | None = None, estudiante_id: int | None = None,
) -> list[models.Caso]:
    stmt = select(models.Caso).order_by(models.Caso.creado_en.desc())
    if sede_id is not None:
        stmt = stmt.where(models.Caso.sede_id == sede_id)
    if grado is not None:
        stmt = stmt.where(models.Caso.grado == grado)
    if curso is not None:
        stmt = stmt.where(models.Caso.curso == curso)
    if estado is not None:
        stmt = stmt.where(models.Caso.estado == estado)
    if tipo is not None:
        stmt = stmt.where(models.Caso.tipo == tipo)
    if estudiante_id is not None:
        stmt = stmt.where(models.Caso.estudiante_id == estudiante_id)
    return list(db.scalars(stmt))


def resumen_orientacion(db: Session, sede_id: int | None = None) -> schemas.OrientacionResumen:
    stmt = select(models.Caso)
    if sede_id is not None:
        stmt = stmt.where(models.Caso.sede_id == sede_id)
    casos = list(db.scalars(stmt))
    hoy = fechas.hoy_colombia()
    return schemas.OrientacionResumen(
        diagnosticos=len(listar_diagnosticos_actuales(db, sede_id=sede_id)),
        casos_abiertos=sum(1 for c in casos if c.estado == "abierto"),
        casos_en_seguimiento=sum(1 for c in casos if c.estado == "en_seguimiento"),
        seguimientos_pendientes=sum(
            1 for c in casos if c.estado != "cerrado" and c.proximo_seguimiento and c.proximo_seguimiento <= hoy
        ),
    )


# --- Grupos de orientación (matrícula real + diagnóstico vigente) ----------
# La lista "por grado" sale de la MATRÍCULA, no solo de las hojas del Excel:
# un grupo sin hoja (ej. 6-6) igual se tiene que poder trabajar. Cuando el
# Excel trae una sola hoja para todo el grado (curso=None, pasa con
# Preescolar), las secciones de ese grado se juntan en una sola fila —
# mismo criterio que listar_casos_grupo() y vincular_estudiante().


def _diagnosticos_vigentes(db: Session, sede_id: int) -> dict[tuple[int, int | None], models.DiagnosticoGrado]:
    vigentes: dict[tuple[int, int | None], models.DiagnosticoGrado] = {}
    stmt = (
        select(models.DiagnosticoGrado)
        .where(models.DiagnosticoGrado.sede_id == sede_id)
        .order_by(models.DiagnosticoGrado.importado_en.desc())
    )
    for d in db.scalars(stmt):
        vigentes.setdefault((d.grado, d.curso), d)
    return vigentes


def _grados_completos(vigentes: dict[tuple[int, int | None], models.DiagnosticoGrado]) -> set[int]:
    """Grados cuyo diagnóstico es UNA sola hoja para todo el grado (y no hay
    hojas por sección que lo contradigan)."""
    con_hoja_general = {g for (g, c) in vigentes if c is None}
    con_hoja_por_seccion = {g for (g, c) in vigentes if c is not None}
    return con_hoja_general - con_hoja_por_seccion


def _clave_grupo(grado: int, curso: int | None, completos: set[int]) -> tuple[int, int | None]:
    return (grado, None) if grado in completos else (grado, curso)


def _resumen_grupo(
    sede_id: int, clave: tuple[int, int | None], completos: set[int], n_estudiantes: int,
    diag: models.DiagnosticoGrado | None, casos: list[models.Caso], hoy: dt.date,
) -> dict:
    grado, curso = clave
    menciones = diag.menciones if diag else []
    nombre = _grado_nombre(grado, curso)
    if curso is None and grado not in completos:
        nombre += " (sin curso asignado)"
    return dict(
        sede_id=sede_id, grado=grado, curso=curso, grado_nombre=nombre,
        grado_completo=grado in completos, n_estudiantes=n_estudiantes,
        diagnostico_id=diag.id if diag else None,
        periodo=periodo_de_fecha(diag.fecha_diligenciado) if diag else None,
        fecha_diligenciado=diag.fecha_diligenciado if diag else None,
        estudiantes_mencionados=_contar_estudiantes_mencionados(menciones),
        menciones_pendientes=sum(1 for m in menciones if m.estudiante_id is None),
        casos_abiertos=sum(1 for c in casos if c.estado == "abierto"),
        casos_en_seguimiento=sum(1 for c in casos if c.estado == "en_seguimiento"),
        seguimientos_vencidos=sum(
            1 for c in casos if c.estado != "cerrado" and c.proximo_seguimiento and c.proximo_seguimiento <= hoy
        ),
    )


def listar_grupos_orientacion(db: Session, sede_id: int) -> list[schemas.GrupoOrientacion]:
    vigentes = _diagnosticos_vigentes(db, sede_id)
    completos = _grados_completos(vigentes)

    conteos: dict[tuple[int, int | None], int] = {}
    filas = db.execute(
        select(models.Estudiante.grado, models.Estudiante.curso, func.count())
        .where(models.Estudiante.sede_id == sede_id, models.Estudiante.estado == "ACTIVO")
        .group_by(models.Estudiante.grado, models.Estudiante.curso)
    ).all()
    for grado, curso, n in filas:
        clave = _clave_grupo(grado, curso, completos)
        conteos[clave] = conteos.get(clave, 0) + n
    for clave in vigentes:
        conteos.setdefault(clave, 0)

    casos_por_grupo: dict[tuple[int, int | None], list[models.Caso]] = {}
    for c in db.scalars(select(models.Caso).where(models.Caso.sede_id == sede_id)):
        clave = _clave_grupo(c.grado, c.curso, completos)
        casos_por_grupo.setdefault(clave, []).append(c)
        conteos.setdefault(clave, 0)

    hoy = fechas.hoy_colombia()
    grupos = [
        schemas.GrupoOrientacion(
            **_resumen_grupo(sede_id, clave, completos, n, vigentes.get(clave), casos_por_grupo.get(clave, []), hoy)
        )
        for clave, n in conteos.items()
    ]
    # Sin curso al final de su grado (son estudiantes pendientes de ubicar).
    grupos.sort(key=lambda g: (g.grado, g.curso is None and not g.grado_completo, g.curso or 0))
    return grupos


def generales_por_grupo(db: Session, sede_id: int) -> list[schemas.GeneralesGrupo]:
    """Temáticas, estrategias, resguardos... del diagnóstico VIGENTE de cada
    grupo de la sede, para verlos todos juntos."""
    resultado = [
        schemas.GeneralesGrupo(
            diagnostico_id=d.id, sede_id=d.sede_id, grado=d.grado, curso=d.curso,
            grado_nombre=_grado_nombre(d.grado, d.curso), periodo=periodo_de_fecha(d.fecha_diligenciado),
            director_grado_nombre=d.director_grado_nombre,
            tematicas_trabajar=d.tematicas_trabajar, estrategias_conflicto=d.estrategias_conflicto,
            estrategias_aprendizaje=d.estrategias_aprendizaje, resguardos_atendidos=d.resguardos_atendidos,
            recomendaciones_docentes=d.recomendaciones_docentes, orientacion_brindada=d.orientacion_brindada,
            acompanamiento_padres=d.acompanamiento_padres,
        )
        for d in _diagnosticos_vigentes(db, sede_id).values()
    ]
    resultado.sort(key=lambda g: (g.grado, g.curso or 0))
    return resultado


def diagnostico_vigente_de_grupo(
    db: Session, sede_id: int, grado: int, curso: int | None
) -> models.DiagnosticoGrado | None:
    """El diagnóstico vigente que cubre a ese grupo (la hoja del curso, o la
    hoja única del grado si el Excel no distingue secciones)."""
    vigentes = _diagnosticos_vigentes(db, sede_id)
    return vigentes.get(_clave_grupo(grado, curso, _grados_completos(vigentes)))


def clave_persona_mencion(m: models.DiagnosticoMencion) -> str:
    """Quién está detrás de una mención — mismo criterio que
    _contar_estudiantes_mencionados (un estudiante vinculado, o el nombre tal
    cual lo escribió el Excel)."""
    return f"e{m.estudiante_id}" if m.estudiante_id else f"n{(m.nombre_detectado or m.texto or '').strip().lower()}"


def situaciones_por_grupo(db: Session, sede_id: int) -> dict[tuple[int, int | None], dict[str, dict]]:
    """Por grupo (misma clave que listar_grupos_orientacion) y por categoría:
    cuántas situaciones registra el diagnóstico vigente y QUIÉNES (claves de
    persona, para poder unir categorías sin contar dos veces a alguien) —
    conteos directos de lo importado, nunca estimados."""
    resultado: dict[tuple[int, int | None], dict[str, dict]] = {}
    for clave, d in _diagnosticos_vigentes(db, sede_id).items():
        por_categoria: dict[str, dict] = {}
        for m in d.menciones:
            c = por_categoria.setdefault(m.categoria, {"situaciones": 0, "personas": set()})
            c["situaciones"] += 1
            c["personas"].add(clave_persona_mencion(m))
        resultado[clave] = por_categoria
    return resultado


def detalle_grupo_orientacion(
    db: Session, sede_id: int, grado: int, curso: int | None
) -> schemas.GrupoOrientacionDetalle | None:
    sede = db.get(models.Sede, sede_id)
    if sede is None:
        return None
    vigentes = _diagnosticos_vigentes(db, sede_id)
    completos = _grados_completos(vigentes)
    clave = _clave_grupo(grado, curso, completos)
    diag = vigentes.get(clave)

    def filtrar(stmt, col_grado, col_curso):
        stmt = stmt.where(col_grado == grado)
        if grado in completos:
            return stmt
        return stmt.where(col_curso.is_(None) if curso is None else col_curso == curso)

    activos = list(db.scalars(filtrar(
        select(models.Estudiante).where(models.Estudiante.sede_id == sede_id, models.Estudiante.estado == "ACTIVO"),
        models.Estudiante.grado, models.Estudiante.curso,
    )))
    casos = list(db.scalars(filtrar(
        select(models.Caso).where(models.Caso.sede_id == sede_id).order_by(models.Caso.creado_en.desc()),
        models.Caso.grado, models.Caso.curso,
    )))
    menciones = diag.menciones if diag else []

    # Quien el Excel menciona o tiene caso aquí, aunque ya no esté activo en
    # el grupo, se muestra igual (marcado) para no esconder trabajo real.
    ids_activos = {e.id for e in activos}
    ids_extra = ({m.estudiante_id for m in menciones if m.estudiante_id} | {c.estudiante_id for c in casos}) - ids_activos
    extra = list(db.scalars(select(models.Estudiante).where(models.Estudiante.id.in_(ids_extra)))) if ids_extra else []

    hoy = fechas.hoy_colombia()
    estudiantes = []
    for e in activos + extra:
        suyas = [m for m in menciones if m.estudiante_id == e.id]
        suyos = [c for c in casos if c.estudiante_id == e.id]
        abiertos = [c for c in suyos if c.estado != "cerrado"]
        proximos = [c.proximo_seguimiento for c in abiertos if c.proximo_seguimiento]
        estudiantes.append(schemas.EstudianteOrientacion(
            id=e.id, documento=e.documento, nombre_completo=e.nombre_completo, genero=e.genero,
            estado=e.estado, grupo=e.grupo, en_matricula_del_grupo=e.id in ids_activos,
            situaciones=sorted({m.categoria for m in suyas}), total_situaciones=len(suyas),
            casos_activos=len(abiertos), casos_total=len(suyos),
            proximo_seguimiento=min(proximos) if proximos else None,
        ))
    estudiantes.sort(key=lambda x: (not x.en_matricula_del_grupo, x.nombre_completo))

    return schemas.GrupoOrientacionDetalle(
        **_resumen_grupo(sede_id, clave, completos, len(activos), diag, casos, hoy),
        sede_nombre=sede.nombre,
        director_grado_nombre=diag.director_grado_nombre if diag else None,
        estudiantes=estudiantes,
        casos=[caso_a_vista(c) for c in casos],
    )


# --- Importación de notas desde el PDF de SAPRED ----------------------------


def _matchear_sede_sapred(db: Session, sede_corta: str) -> models.Sede | None:
    from .importador_sapred import normalizar

    objetivo = normalizar(sede_corta)
    if not objetivo:
        return None
    coincidencias = [s for s in db.scalars(select(models.Sede)).all() if objetivo in normalizar(s.nombre)]
    return coincidencias[0] if len(coincidencias) == 1 else None


def _matchear_docente_por_nombre(db: Session, nombre: str) -> models.Docente | None:
    """Empareja el "Director de Grupo" del reporte de SAPRED con un docente
    ya existente en nuestra base (importados antes desde el listado real de
    profesores) por nombre completo, sin acentos ni mayúsculas. No crea un
    docente nuevo con datos inventados: si no hay coincidencia exacta, se
    deja sin asignar para que se revise a mano."""
    from .importador_sapred import normalizar

    objetivo = normalizar(nombre)
    if not objetivo:
        return None
    for d in db.scalars(select(models.Docente)).all():
        if normalizar(d.nombre_completo) == objetivo:
            return d
    return None


def importar_bloque_sapred(db: Session, bloque: dict) -> schemas.ImportarSapredResultadoBloque:
    """Aplica UN bloque (un curso) ya parseado del PDF de SAPRED: reconoce
    la sede, completa el catálogo de áreas si hace falta, y crea un
    PendienteBoletin por cada nota que falte — sin duplicar los que ya
    existan (no resueltos) de una importación o registro manual anterior."""
    anio_lectivo = bloque["anio_lectivo"] or dt.date.today().year
    grado, curso, periodo = bloque["grado"], bloque["curso"], bloque["periodo"]

    sede = db.get(models.Sede, bloque["sede_id"]) if bloque.get("sede_id") else None
    if sede is None:
        sede = _matchear_sede_sapred(db, bloque["sede_corta"])
    if sede is None:
        return schemas.ImportarSapredResultadoBloque(
            grado=grado, curso=curso, sede_corta=bloque["sede_corta"],
            periodo=periodo, anio_lectivo=anio_lectivo, reconocido=False,
            motivo_no_reconocido=f'No se encontró (o es ambigua) una sede que coincida con "{bloque["sede_corta"]}"',
        )

    # SAPRED le pone número de sección ("1-1") incluso a sedes rurales que en
    # nuestra base son un solo grupo sin secciones (curso=None). Se manda a
    # ajustar por el roster real: si en nuestra base ese sede+grado tiene un
    # único curso, se usa ese (aunque sea None) en vez de confiar en el
    # número de SAPRED — si no, el pendiente queda huérfano de su grupo real.
    cursos_reales = {
        c
        for c, in db.execute(
            select(models.Estudiante.curso).where(
                models.Estudiante.sede_id == sede.id,
                models.Estudiante.grado == grado,
                models.Estudiante.estado == "ACTIVO",
            )
        ).all()
    }
    if len(cursos_reales) == 1:
        curso = next(iter(cursos_reales))

    areas_por_codigo = {a.codigo: a for a in db.scalars(select(models.Area)).all()}
    areas_grado_existentes = {(ag.area_id, ag.grado) for ag in db.scalars(select(models.AreaGrado)).all()}
    areas_nuevas = []
    for a in bloque["areas"]:
        cod = _codigo_area_canonico(a["codigo"])
        area = areas_por_codigo.get(cod)
        if area is None:
            area = models.Area(codigo=cod, nombre=a["nombre"] or cod)
            db.add(area)
            db.flush()
            areas_por_codigo[cod] = area
            areas_nuevas.append(cod)
        # El resto del importador vuelve a buscar el área por el código crudo
        # de SAPRED ("INGL"); se registra el alias para que apunte a la misma.
        areas_por_codigo[a["codigo"]] = area
        if (area.id, grado) not in areas_grado_existentes:
            db.add(models.AreaGrado(area_id=area.id, grado=grado))
            areas_grado_existentes.add((area.id, grado))

    revision = _obtener_o_crear_revision(db, sede.id, grado, curso, anio_lectivo, periodo)

    # Si SAPRED trae el "Director de Grupo" y todavía no hay nadie asignado
    # a este grupo (whole-group, area_id=None), se asigna automáticamente —
    # sin pisar una asignación que ya exista (pudo haberse puesto a mano).
    docente_asignado = None
    if bloque.get("director_grupo"):
        ya_asignado = db.scalar(
            select(models.AsignacionDocente).where(
                models.AsignacionDocente.sede_id == sede.id,
                models.AsignacionDocente.grado == grado,
                models.AsignacionDocente.curso == curso,
                models.AsignacionDocente.area_id.is_(None),
                models.AsignacionDocente.anio_lectivo == anio_lectivo,
            )
        )
        if ya_asignado is None:
            docente = _matchear_docente_por_nombre(db, bloque["director_grupo"])
            if docente is not None:
                db.add(
                    models.AsignacionDocente(
                        docente_id=docente.id, sede_id=sede.id, grado=grado, curso=curso,
                        area_id=None, anio_lectivo=anio_lectivo,
                    )
                )
                docente_asignado = docente.nombre_completo

    # Clave por (area, estudiante, tipo): así los pendientes de concepto/
    # observación del "Boletín informativo" no bloquean la creación de los
    # pendientes de nota de este importador (comparten RevisionBoletin).
    ya_marcado = {
        (p.area_id, p.estudiante_id, p.tipo)
        for p in db.scalars(
            select(models.PendienteBoletin).where(
                models.PendienteBoletin.revision_id == revision.id,
                models.PendienteBoletin.resuelto.is_(False),
            )
        ).all()
    }

    documentos_bloque = {est["documento"] for est in bloque["estudiantes"]}
    estudiantes_doc = {
        e.documento: e for e in db.scalars(select(models.Estudiante)).all() if e.documento in documentos_bloque
    }

    notas_existentes = {
        (n.area_id, n.estudiante_id): n
        for n in db.scalars(select(models.NotaSapred).where(models.NotaSapred.revision_id == revision.id)).all()
    }

    pendientes_creados = 0
    pendientes_ya_existian = 0
    no_encontrados: list[str] = []
    # (area_id, estudiante_id|None, "nota") de lo que en esta corrida SÍ vino
    # con nota — sirve para cerrar pendientes viejos ya resueltos.
    satisfechos: set[tuple[int | None, int | None, str]] = set()

    def _es_posible_retirado(documento: str) -> bool:
        e = estudiantes_doc.get(documento)
        return bool(e and e.posible_retirado)

    for a in bloque["areas"]:
        codigo = a["codigo"]
        area = areas_por_codigo[codigo]
        con_nota = [e for e in bloque["estudiantes"] if e["notas"].get(codigo)]
        sin_nota = [
            e
            for e in bloque["estudiantes"]
            if not e["notas"].get(codigo) and not _es_posible_retirado(e["documento"])
        ]

        # Guarda el valor real de las notas que SÍ existen (aparte de los
        # pendientes, que solo registran lo que falta) — no cambia nada de
        # la lógica de pendientes de arriba/abajo, solo se suma.
        for est in con_nota:
            estudiante = estudiantes_doc.get(est["documento"])
            if estudiante is None:
                continue
            valor = est["notas"][codigo]
            existente = notas_existentes.get((area.id, estudiante.id))
            if existente:
                existente.valor = valor
                existente.actualizado_en = dt.datetime.utcnow()
                existente.nombre_sapred = est["nombre"]
            else:
                nueva = models.NotaSapred(
                    revision_id=revision.id, area_id=area.id, estudiante_id=estudiante.id, valor=valor,
                    nombre_sapred=est["nombre"],
                )
                db.add(nueva)
                notas_existentes[(area.id, estudiante.id)] = nueva
            satisfechos.add((area.id, estudiante.id, "nota"))

        if con_nota:
            # Al menos alguien ya tiene nota en el área -> el pendiente grupal
            # "nadie tiene nota" (si existía) queda obsoleto.
            satisfechos.add((area.id, None, "nota"))

        if not con_nota and sin_nota:
            # Nadie tiene nota todavía en esta área: un solo pendiente para
            # todo el curso, en vez de uno por cada estudiante.
            if (area.id, None, "nota") in ya_marcado:
                pendientes_ya_existian += 1
            else:
                db.add(
                    models.PendienteBoletin(
                        revision_id=revision.id,
                        area_id=area.id,
                        tipo="nota",
                        detalle="Sin ninguna nota registrada en SAPRED para todo el curso (importado)",
                    )
                )
                ya_marcado.add((area.id, None, "nota"))
                pendientes_creados += 1
            continue

        for est in sin_nota:
            estudiante = estudiantes_doc.get(est["documento"])
            if estudiante is None:
                no_encontrados.append(f"{est['documento']} {est['nombre']}")
                continue
            if (area.id, estudiante.id, "nota") in ya_marcado:
                pendientes_ya_existian += 1
                continue
            # Si ESTE estudiante ya tiene una nota registrada para el área
            # (de una importación anterior), no se crea un pendiente aunque
            # este PDF traiga la celda vacía — puede ser un export parcial o
            # una vista distinta. No se pisa lo que ya está.
            if (area.id, estudiante.id) in notas_existentes:
                pendientes_ya_existian += 1
                continue
            db.add(
                models.PendienteBoletin(
                    revision_id=revision.id,
                    area_id=area.id,
                    estudiante_id=estudiante.id,
                    tipo="nota",
                    detalle="Falta la nota en SAPRED (importado)",
                )
            )
            ya_marcado.add((area.id, estudiante.id, "nota"))
            pendientes_creados += 1

    # Estudiantes que SAPRED reporta en este curso pero que no existen en
    # nuestra base local, con nota o sin ella — se deja como observación
    # consultable (nunca se crea el estudiante ni se inventa nada).
    existentes_sin_coincidencia = {
        (r.documento, r.grado, r.curso, r.periodo, r.anio_lectivo): r
        for r in db.scalars(
            select(models.EstudianteSapredSinCoincidencia).where(
                models.EstudianteSapredSinCoincidencia.sede_id == sede.id,
                models.EstudianteSapredSinCoincidencia.grado == grado,
                models.EstudianteSapredSinCoincidencia.curso == curso,
                models.EstudianteSapredSinCoincidencia.periodo == periodo,
                models.EstudianteSapredSinCoincidencia.anio_lectivo == anio_lectivo,
            )
        ).all()
    }
    for est in bloque["estudiantes"]:
        if est["documento"] in estudiantes_doc:
            continue
        tiene_notas = any(est["notas"].get(a["codigo"]) for a in bloque["areas"])
        clave = (est["documento"], grado, curso, periodo, anio_lectivo)
        existente = existentes_sin_coincidencia.get(clave)
        if existente:
            existente.ultima_vez_visto = dt.datetime.utcnow()
            existente.nombre_sapred = est["nombre"]
            existente.tiene_notas = existente.tiene_notas or tiene_notas
        else:
            db.add(
                models.EstudianteSapredSinCoincidencia(
                    documento=est["documento"], nombre_sapred=est["nombre"], sede_id=sede.id,
                    grado=grado, curso=curso, periodo=periodo, anio_lectivo=anio_lectivo,
                    tiene_notas=tiene_notas,
                )
            )

    resueltos_auto = _conciliar_pendientes(db, revision.id, {"nota"}, satisfechos)

    db.commit()

    # Mismo motivo que en importar_bloque_boletin: esta es evidencia SAPRED
    # nueva (aquí, del Consolidado de notas) — que el hallazgo de grado
    # distinto quede registrado desde que se importa, no solo cuando alguien
    # abra el reporte de Conciliación.
    conciliacion.conciliar(db, anio_lectivo=anio_lectivo, periodo=periodo, sede_id=sede.id, grado=None)

    return schemas.ImportarSapredResultadoBloque(
        grado=grado, curso=curso, sede_corta=bloque["sede_corta"], sede_id=sede.id, sede_nombre=sede.nombre,
        periodo=periodo, anio_lectivo=anio_lectivo, reconocido=True,
        areas_nuevas=areas_nuevas, pendientes_creados=pendientes_creados,
        pendientes_ya_existian=pendientes_ya_existian,
        pendientes_resueltos_auto=resueltos_auto,
        estudiantes_no_encontrados=sorted(set(no_encontrados)),
        docente_asignado=docente_asignado,
    )


def importar_pdf_sapred(db: Session, datos_pdf: bytes) -> schemas.ImportarSapredResultado:
    from .importador_sapred import parsear_pdf_notas

    bloques = parsear_pdf_notas(datos_pdf)
    resultados = [importar_bloque_sapred(db, b) for b in bloques]
    return schemas.ImportarSapredResultado(
        bloques=resultados,
        total_pendientes_creados=sum(r.pendientes_creados for r in resultados),
        total_pendientes_resueltos_auto=sum(r.pendientes_resueltos_auto for r in resultados),
        total_estudiantes_no_encontrados=len({n for r in resultados for n in r.estudiantes_no_encontrados}),
    )


def registrar_importacion_pdf_sapred(
    db: Session,
    nombre_archivo: str,
    resultado: schemas.ImportarSapredResultado | None,
    error: str | None = None,
) -> models.ImportacionSapredPdf:
    """Deja constancia de un intento de importación manual de PDF (éxito o
    error), para que se pueda consultar después aunque se cierre el aviso o
    se recargue la página — antes no quedaba ningún rastro de esto."""
    registro = models.ImportacionSapredPdf(
        nombre_archivo=nombre_archivo,
        total_pendientes_creados=resultado.total_pendientes_creados if resultado else 0,
        total_estudiantes_no_encontrados=resultado.total_estudiantes_no_encontrados if resultado else 0,
        detalle_bloques=json.dumps([b.model_dump() for b in resultado.bloques], ensure_ascii=False) if resultado else None,
        error=error,
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def listar_importaciones_pdf_sapred(db: Session, limite: int = 20) -> list[schemas.ImportacionSapredPdfHistorial]:
    registros = db.scalars(
        select(models.ImportacionSapredPdf).order_by(models.ImportacionSapredPdf.importado_en.desc()).limit(limite)
    ).all()
    return [
        schemas.ImportacionSapredPdfHistorial(
            id=r.id,
            nombre_archivo=r.nombre_archivo,
            importado_en=r.importado_en,
            total_pendientes_creados=r.total_pendientes_creados,
            total_estudiantes_no_encontrados=r.total_estudiantes_no_encontrados,
            bloques=[schemas.ImportarSapredResultadoBloque(**b) for b in json.loads(r.detalle_bloques)] if r.detalle_bloques else [],
            error=r.error,
        )
        for r in registros
    ]


# --- Importación desde el "Boletín informativo" de SAPRED ------------------
# Flujo paralelo al del Consolidado (arriba): en vez de notas numéricas,
# alimenta el profesor de cada materia, el concepto de cada área y la
# observación del director de grupo — y crea PendienteBoletin (tipo concepto
# / observacion) por lo que falte.


def _matchear_docente_por_tokens(db: Session, nombre: str) -> models.Docente | None:
    """Empareja un nombre de profesor con un Docente existente comparando el
    CONJUNTO de palabras (sin acentos ni mayúsculas), sin importar el orden —
    el boletín lo trae como "APELLIDOS NOMBRES" y la base lo tiene como
    "NOMBRES APELLIDOS". Si hay 0 o más de 1 coincidencia, devuelve None (no
    se inventa ni se elige al azar)."""
    from .importador_sapred import normalizar

    objetivo = frozenset(t for t in (normalizar(p) for p in nombre.split()) if t)
    if not objetivo:
        return None
    coincidencias = [
        d
        for d in db.scalars(select(models.Docente)).all()
        if frozenset(t for t in (normalizar(p) for p in d.nombre_completo.split()) if t) == objetivo
    ]
    return coincidencias[0] if len(coincidencias) == 1 else None


def _upsert_texto_boletin(
    db: Session,
    cache: dict,
    revision_id: int,
    area_id: int | None,
    estudiante_id: int,
    tipo: str,
    texto: str | None,
    nombre_sapred: str | None,
) -> None:
    texto = (texto or "").strip() or None
    clave = (area_id, estudiante_id, tipo)
    existente = cache.get(clave)
    if existente is not None:
        existente.texto = texto
        existente.nombre_sapred = nombre_sapred
        existente.actualizado_en = dt.datetime.utcnow()
        return
    nuevo = models.TextoBoletin(
        revision_id=revision_id, area_id=area_id, estudiante_id=estudiante_id,
        tipo=tipo, texto=texto, nombre_sapred=nombre_sapred,
    )
    db.add(nuevo)
    cache[clave] = nuevo


def importar_bloque_boletin(db: Session, bloque: dict) -> schemas.ImportarBoletinResultadoBloque:
    """Aplica UN bloque (un curso) del reporte "Boletín informativo": reconoce
    la sede, completa el catálogo de áreas, asigna el profesor de cada materia
    y el director de grupo (sin pisar asignaciones ya hechas), guarda el texto
    de conceptos/observaciones y crea un PendienteBoletin por cada
    concepto/observación que falte (sin duplicar los que ya existan)."""
    anio_lectivo = bloque["anio_lectivo"] or dt.date.today().year
    grado, curso, periodo = bloque["grado"], bloque["curso"], bloque["periodo"]

    sede = db.get(models.Sede, bloque["sede_id"]) if bloque.get("sede_id") else None
    if sede is None:
        sede = _matchear_sede_sapred(db, bloque["sede_corta"])
    if sede is None:
        return schemas.ImportarBoletinResultadoBloque(
            grado=grado, curso=curso, sede_corta=bloque["sede_corta"],
            periodo=periodo, anio_lectivo=anio_lectivo, reconocido=False,
            motivo_no_reconocido=f'No se encontró (o es ambigua) una sede que coincida con "{bloque["sede_corta"]}"',
        )

    # SAPRED numera secciones ("1-1") aunque en nuestra base la sede sea un
    # solo grupo (curso=None) — se ajusta por el roster real (igual que el
    # importador del Consolidado).
    cursos_reales = {
        c
        for c, in db.execute(
            select(models.Estudiante.curso).where(
                models.Estudiante.sede_id == sede.id,
                models.Estudiante.grado == grado,
                models.Estudiante.estado == "ACTIVO",
            )
        ).all()
    }
    if len(cursos_reales) == 1:
        curso = next(iter(cursos_reales))

    areas_por_codigo = {a.codigo: a for a in db.scalars(select(models.Area)).all()}
    areas_grado_existentes = {(ag.area_id, ag.grado) for ag in db.scalars(select(models.AreaGrado)).all()}
    areas_nuevas: list[str] = []
    for a in bloque["areas"]:
        cod = _codigo_area_canonico(a["codigo"])
        area = areas_por_codigo.get(cod)
        if area is None:
            area = models.Area(codigo=cod, nombre=a["nombre"] or cod)
            db.add(area)
            db.flush()
            areas_por_codigo[cod] = area
            areas_nuevas.append(cod)
        # El resto del importador vuelve a buscar el área por el código crudo
        # de SAPRED ("INGL"); se registra el alias para que apunte a la misma.
        areas_por_codigo[a["codigo"]] = area
        if (area.id, grado) not in areas_grado_existentes:
            db.add(models.AreaGrado(area_id=area.id, grado=grado))
            areas_grado_existentes.add((area.id, grado))

    revision = _obtener_o_crear_revision(db, sede.id, grado, curso, anio_lectivo, periodo)

    # --- Profesor de cada materia (asignación por área) ------------------
    asignaciones_grupo = db.scalars(
        select(models.AsignacionDocente).where(
            models.AsignacionDocente.sede_id == sede.id,
            models.AsignacionDocente.grado == grado,
            models.AsignacionDocente.curso == curso,
            models.AsignacionDocente.anio_lectivo == anio_lectivo,
        )
    ).all()
    area_ids_ya_asignadas = {a.area_id for a in asignaciones_grupo if a.area_id is not None}
    tiene_asignacion_grupo = any(a.area_id is None for a in asignaciones_grupo)

    docentes_area_asignados: list[str] = []
    for a in bloque["areas"]:
        if not a.get("docente"):
            continue
        area = areas_por_codigo[a["codigo"]]
        if area.id in area_ids_ya_asignadas:
            continue
        docente = _matchear_docente_por_tokens(db, a["docente"])
        if docente is None:
            continue
        db.add(
            models.AsignacionDocente(
                docente_id=docente.id, sede_id=sede.id, grado=grado, curso=curso,
                area_id=area.id, anio_lectivo=anio_lectivo,
            )
        )
        area_ids_ya_asignadas.add(area.id)
        docentes_area_asignados.append(f"{a['codigo']}: {docente.nombre_completo}")

    # --- Director de grupo (asignación de todo el grupo, area_id=None) ---
    docente_grupo_asignado = None
    if bloque.get("director_grupo") and not tiene_asignacion_grupo:
        docente = _matchear_docente_por_tokens(db, bloque["director_grupo"]) or _matchear_docente_por_nombre(
            db, bloque["director_grupo"]
        )
        if docente is not None:
            db.add(
                models.AsignacionDocente(
                    docente_id=docente.id, sede_id=sede.id, grado=grado, curso=curso,
                    area_id=None, anio_lectivo=anio_lectivo,
                )
            )
            docente_grupo_asignado = docente.nombre_completo

    # --- Conceptos y observaciones -------------------------------------
    documentos_bloque = {e["documento"] for e in bloque["estudiantes"]}
    estudiantes_doc = {
        e.documento: e for e in db.scalars(select(models.Estudiante)).all() if e.documento in documentos_bloque
    }

    textos_existentes = {
        (t.area_id, t.estudiante_id, t.tipo): t
        for t in db.scalars(select(models.TextoBoletin).where(models.TextoBoletin.revision_id == revision.id)).all()
    }
    notas_existentes = {
        (n.area_id, n.estudiante_id)
        for n in db.scalars(select(models.NotaSapred).where(models.NotaSapred.revision_id == revision.id)).all()
    }
    ya_marcado = {
        (p.area_id, p.estudiante_id, p.tipo)
        for p in db.scalars(
            select(models.PendienteBoletin).where(
                models.PendienteBoletin.revision_id == revision.id,
                models.PendienteBoletin.resuelto.is_(False),
            )
        ).all()
    }

    conceptos_creados = conceptos_ya = 0
    notas_creadas = notas_ya = 0
    observaciones_creadas = observaciones_ya = 0
    no_encontrados: list[str] = []
    no_encontrados_set: set[str] = set()
    # (area_id, estudiante_id|None, tipo) de lo que AHORA sí viene cargado —
    # cierra pendientes viejos ya resueltos en SAPRED.
    satisfechos: set[tuple[int | None, int | None, str]] = set()

    def _datos_area(est: dict, codigo: str) -> dict:
        return est["areas"].get(codigo) or {}

    def _pendiente(tipo: str, area_id: int, estudiante_id: int | None, detalle: str) -> bool:
        """Crea el pendiente si no existe uno equivalente sin resolver. True
        si lo creó. Nunca crea pendientes para un estudiante marcado como
        'posible retirado'."""
        clave = (area_id, estudiante_id, tipo)
        if clave in ya_marcado:
            return False
        if estudiante_id is not None:
            e = db.get(models.Estudiante, estudiante_id)
            if e is not None and e.posible_retirado:
                return False
        db.add(
            models.PendienteBoletin(
                revision_id=revision.id, area_id=area_id, estudiante_id=estudiante_id,
                tipo=tipo, detalle=detalle,
            )
        )
        ya_marcado.add(clave)
        return True

    for a in bloque["areas"]:
        codigo = a["codigo"]
        area = areas_por_codigo[codigo]
        # ¿Alguien del curso tiene concepto en esta área? Si NADIE lo tiene,
        # se deja un solo pendiente grupal en vez de uno por estudiante
        # (mismo criterio que el importador del Consolidado con las notas).
        nadie_con_concepto = not any(_datos_area(e, codigo).get("concepto") for e in bloque["estudiantes"])

        if nadie_con_concepto:
            if _pendiente("concepto", area.id, None, "Sin ningún concepto registrado en el boletín para todo el curso (importado)"):
                conceptos_creados += 1
            else:
                conceptos_ya += 1
        else:
            # Ya hay conceptos en el área -> obsoleto el pendiente grupal.
            satisfechos.add((area.id, None, "concepto"))

        for est in bloque["estudiantes"]:
            estudiante = estudiantes_doc.get(est["documento"])
            datos = _datos_area(est, codigo)
            if estudiante is None:
                if est["documento"] not in no_encontrados_set:
                    no_encontrados_set.add(est["documento"])
                    no_encontrados.append(f"{est['documento']} {est['nombre']}")
                continue

            # Concepto: guarda el texto (o deja la fila vacía) y marca lo que falta.
            _upsert_texto_boletin(
                db, textos_existentes, revision.id, area.id, estudiante.id, "concepto",
                datos.get("concepto"), est["nombre"],
            )
            if datos.get("concepto"):
                satisfechos.add((area.id, estudiante.id, "concepto"))
            elif not nadie_con_concepto:
                if _pendiente("concepto", area.id, estudiante.id, "Falta el concepto en el boletín (importado)"):
                    conceptos_creados += 1
                else:
                    conceptos_ya += 1

            # Nota del período: si viene, se guarda sin pisar la del Consolidado;
            # si falta, se deja como pendiente de nota (para el boletín solo).
            if datos.get("nota"):
                if (area.id, estudiante.id) not in notas_existentes:
                    db.add(
                        models.NotaSapred(
                            revision_id=revision.id, area_id=area.id, estudiante_id=estudiante.id,
                            valor=datos["nota"], nombre_sapred=est["nombre"],
                        )
                    )
                    notas_existentes.add((area.id, estudiante.id))
                satisfechos.add((area.id, estudiante.id, "nota"))
            elif (area.id, estudiante.id) not in notas_existentes:
                if _pendiente("nota", area.id, estudiante.id, "Falta la nota en el boletín (importado)"):
                    notas_creadas += 1
                else:
                    notas_ya += 1

    faltan_observaciones = False
    for est in bloque["estudiantes"]:
        estudiante = estudiantes_doc.get(est["documento"])
        if estudiante is None:
            continue
        _upsert_texto_boletin(
            db, textos_existentes, revision.id, None, estudiante.id, "observacion",
            est.get("observacion"), est["nombre"],
        )
        if est.get("observacion"):
            satisfechos.add((None, estudiante.id, "observacion"))
            continue
        if estudiante.posible_retirado:
            continue
        faltan_observaciones = True
        if (None, estudiante.id, "observacion") in ya_marcado:
            observaciones_ya += 1
            continue
        db.add(
            models.PendienteBoletin(
                revision_id=revision.id, estudiante_id=estudiante.id, tipo="observacion",
                detalle="Falta la observación del director de grupo (importado)",
            )
        )
        ya_marcado.add((None, estudiante.id, "observacion"))
        observaciones_creadas += 1

    # Pendiente grupal viejo ("Observaciones del grupo pendientes por
    # completar", sin área ni estudiante): si ya nadie tiene la observación
    # sin llenar, se cierra.
    if not faltan_observaciones and bloque["estudiantes"]:
        satisfechos.add((None, None, "observacion"))

    # Estudiantes que el boletín reporta y que no existen en la base local
    # (mismo tratamiento que el importador del Consolidado).
    existentes_sin_coincidencia = {
        (r.documento, r.grado, r.curso, r.periodo, r.anio_lectivo): r
        for r in db.scalars(
            select(models.EstudianteSapredSinCoincidencia).where(
                models.EstudianteSapredSinCoincidencia.sede_id == sede.id,
                models.EstudianteSapredSinCoincidencia.grado == grado,
                models.EstudianteSapredSinCoincidencia.curso == curso,
                models.EstudianteSapredSinCoincidencia.periodo == periodo,
                models.EstudianteSapredSinCoincidencia.anio_lectivo == anio_lectivo,
            )
        ).all()
    }
    for est in bloque["estudiantes"]:
        if est["documento"] in estudiantes_doc:
            continue
        tiene_notas = any(_datos_area(est, a["codigo"]).get("nota") for a in bloque["areas"])
        clave = (est["documento"], grado, curso, periodo, anio_lectivo)
        existente = existentes_sin_coincidencia.get(clave)
        if existente:
            existente.ultima_vez_visto = dt.datetime.utcnow()
            existente.nombre_sapred = est["nombre"]
            existente.tiene_notas = existente.tiene_notas or tiene_notas
        else:
            db.add(
                models.EstudianteSapredSinCoincidencia(
                    documento=est["documento"], nombre_sapred=est["nombre"], sede_id=sede.id,
                    grado=grado, curso=curso, periodo=periodo, anio_lectivo=anio_lectivo,
                    tiene_notas=tiene_notas,
                )
            )

    resueltos_auto = _conciliar_pendientes(
        db, revision.id, {"concepto", "nota", "observacion"}, satisfechos
    )

    db.commit()

    # Esta es la evidencia SAPRED entrando al sistema: si algún estudiante de
    # esta sede quedó con el grado/curso distinto entre SIMAC y SAPRED (ver
    # conciliacion.py), que quede registrado en el historial de hallazgos
    # DESDE que se importa, no solo cuando alguien abra el reporte de
    # Conciliación a mirar.
    conciliacion.conciliar(db, anio_lectivo=anio_lectivo, periodo=periodo, sede_id=sede.id, grado=None)

    return schemas.ImportarBoletinResultadoBloque(
        grado=grado, curso=curso, sede_corta=bloque["sede_corta"], sede_id=sede.id, sede_nombre=sede.nombre,
        periodo=periodo, anio_lectivo=anio_lectivo, reconocido=True,
        areas_nuevas=areas_nuevas,
        conceptos_pendientes_creados=conceptos_creados,
        conceptos_pendientes_ya_existian=conceptos_ya,
        notas_pendientes_creados=notas_creadas,
        notas_pendientes_ya_existian=notas_ya,
        observaciones_pendientes_creadas=observaciones_creadas,
        observaciones_pendientes_ya_existian=observaciones_ya,
        pendientes_resueltos_auto=resueltos_auto,
        docentes_area_asignados=docentes_area_asignados,
        docente_grupo_asignado=docente_grupo_asignado,
        estudiantes_no_encontrados=sorted(set(no_encontrados)),
    )


def importar_pdf_boletin(db: Session, datos_pdf: bytes) -> schemas.ImportarBoletinResultado:
    from .importador_boletin import parsear_pdf_boletin

    bloques = parsear_pdf_boletin(datos_pdf)
    resultados = [importar_bloque_boletin(db, b) for b in bloques]
    return schemas.ImportarBoletinResultado(
        bloques=resultados,
        total_conceptos_pendientes=sum(r.conceptos_pendientes_creados for r in resultados),
        total_notas_pendientes=sum(r.notas_pendientes_creados for r in resultados),
        total_observaciones_pendientes=sum(r.observaciones_pendientes_creadas for r in resultados),
        total_pendientes_resueltos_auto=sum(r.pendientes_resueltos_auto for r in resultados),
        total_estudiantes_no_encontrados=len({n for r in resultados for n in r.estudiantes_no_encontrados}),
    )


def registrar_importacion_pdf_boletin(
    db: Session,
    nombre_archivo: str,
    resultado: schemas.ImportarBoletinResultado | None,
    error: str | None = None,
) -> models.ImportacionBoletinPdf:
    registro = models.ImportacionBoletinPdf(
        nombre_archivo=nombre_archivo,
        total_conceptos_pendientes=resultado.total_conceptos_pendientes if resultado else 0,
        total_observaciones_pendientes=resultado.total_observaciones_pendientes if resultado else 0,
        total_estudiantes_no_encontrados=resultado.total_estudiantes_no_encontrados if resultado else 0,
        detalle_bloques=json.dumps([b.model_dump() for b in resultado.bloques], ensure_ascii=False) if resultado else None,
        error=error,
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def listar_importaciones_pdf_boletin(db: Session, limite: int = 20) -> list[schemas.ImportacionBoletinPdfHistorial]:
    registros = db.scalars(
        select(models.ImportacionBoletinPdf).order_by(models.ImportacionBoletinPdf.importado_en.desc()).limit(limite)
    ).all()
    return [
        schemas.ImportacionBoletinPdfHistorial(
            id=r.id,
            nombre_archivo=r.nombre_archivo,
            importado_en=r.importado_en,
            total_conceptos_pendientes=r.total_conceptos_pendientes,
            total_observaciones_pendientes=r.total_observaciones_pendientes,
            total_estudiantes_no_encontrados=r.total_estudiantes_no_encontrados,
            bloques=[schemas.ImportarBoletinResultadoBloque(**b) for b in json.loads(r.detalle_bloques)] if r.detalle_bloques else [],
            error=r.error,
        )
        for r in registros
    ]


def listar_sapred_sin_coincidencia(
    db: Session,
    anio_lectivo: int,
    periodo: int | None = None,
    sede_id: int | None = None,
    solo_no_resueltos: bool = True,
) -> list[schemas.SapredSinCoincidencia]:
    stmt = select(models.EstudianteSapredSinCoincidencia).where(
        models.EstudianteSapredSinCoincidencia.anio_lectivo == anio_lectivo
    )
    if periodo is not None:
        stmt = stmt.where(models.EstudianteSapredSinCoincidencia.periodo == periodo)
    if sede_id is not None:
        stmt = stmt.where(models.EstudianteSapredSinCoincidencia.sede_id == sede_id)
    if solo_no_resueltos:
        stmt = stmt.where(models.EstudianteSapredSinCoincidencia.resuelto.is_(False))
    filas = db.scalars(stmt).all()

    sedes = {s.id: s for s in db.scalars(select(models.Sede)).all()}
    resultado = []
    for f in filas:
        sede = sedes.get(f.sede_id)
        resultado.append(
            schemas.SapredSinCoincidencia(
                id=f.id, documento=f.documento, nombre_sapred=f.nombre_sapred,
                sede_id=f.sede_id, sede_nombre=sede.nombre if sede else "",
                grado=f.grado, nombre_grado=models.GRADOS_NOMBRES.get(f.grado, str(f.grado)),
                curso=f.curso, periodo=f.periodo, anio_lectivo=f.anio_lectivo,
                tiene_notas=f.tiene_notas, primera_vez_visto=f.primera_vez_visto,
                ultima_vez_visto=f.ultima_vez_visto, resuelto=f.resuelto,
            )
        )
    resultado.sort(key=lambda r: (not r.tiene_notas, r.sede_nombre, r.grado))
    return resultado


def actualizar_sapred_sin_coincidencia(
    db: Session, id_: int, cambios: schemas.SapredSinCoincidenciaActualizar
) -> schemas.SapredSinCoincidencia | None:
    fila = db.get(models.EstudianteSapredSinCoincidencia, id_)
    if fila is None:
        return None
    fila.resuelto = cambios.resuelto
    db.commit()
    db.refresh(fila)
    sede = db.get(models.Sede, fila.sede_id)
    return schemas.SapredSinCoincidencia(
        id=fila.id, documento=fila.documento, nombre_sapred=fila.nombre_sapred,
        sede_id=fila.sede_id, sede_nombre=sede.nombre if sede else "",
        grado=fila.grado, nombre_grado=models.GRADOS_NOMBRES.get(fila.grado, str(fila.grado)),
        curso=fila.curso, periodo=fila.periodo, anio_lectivo=fila.anio_lectivo,
        tiene_notas=fila.tiene_notas, primera_vez_visto=fila.primera_vez_visto,
        ultima_vez_visto=fila.ultima_vez_visto, resuelto=fila.resuelto,
    )


# --- Asistencia ------------------------------------------------------------
# La lógica de asistencia por bloque (autorización, registro en lote,
# auditoría) vive en app/asistencia.py, no aquí — igual que el horario tiene
# su propio módulo separado de crud.py.


def listar_cursos_de_grado(db: Session, sede_id: int, grado: int) -> list[int]:
    stmt = (
        select(models.Estudiante.curso)
        .where(
            models.Estudiante.sede_id == sede_id,
            models.Estudiante.grado == grado,
            models.Estudiante.curso.is_not(None),
        )
        .distinct()
        .order_by(models.Estudiante.curso)
    )
    return list(db.scalars(stmt).all())
