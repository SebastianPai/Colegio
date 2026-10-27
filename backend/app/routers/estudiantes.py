from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import auth, auth_servicio, crud, datos_ficha, fechas, models, rbac, reporte_notas, schemas
from ..database import get_db

router = APIRouter(prefix="/api/estudiantes", tags=["estudiantes"])


@router.get("", response_model=list[schemas.Estudiante])
def listar_estudiantes(
    sede_id: int | None = None,
    grado: int | None = None,
    curso: int | None = None,
    estado: str | None = None,
    q: str | None = None,
    sin_curso: bool = False,
    _obs=Depends(rbac.observar("estudiantes.ver")),
    db: Session = Depends(get_db),
):
    """Lista completa sin paginar: la usan la impresión de listas y otras
    consultas internas que necesitan todos los resultados de una vez."""
    return crud.listar_estudiantes(
        db, sede_id=sede_id, grado=grado, curso=curso, estado=estado, busqueda=q, sin_curso=sin_curso
    )


@router.get("/pagina", response_model=schemas.PaginaEstudiantes)
def listar_estudiantes_paginado(
    sede_id: int | None = None,
    grado: int | None = None,
    curso: int | None = None,
    estado: str | None = None,
    q: str | None = None,
    solo_no_verificados: bool = False,
    sin_curso: bool = False,
    pagina: int = 1,
    por_pagina: int = 50,
    _obs=Depends(rbac.observar("estudiantes.ver")),
    db: Session = Depends(get_db),
):
    items, total = crud.listar_estudiantes_paginado(
        db,
        sede_id=sede_id,
        grado=grado,
        curso=curso,
        estado=estado,
        busqueda=q,
        solo_no_verificados=solo_no_verificados,
        sin_curso=sin_curso,
        pagina=max(pagina, 1),
        por_pagina=por_pagina,
    )
    return schemas.PaginaEstudiantes(total=total, pagina=pagina, por_pagina=por_pagina, items=items)


@router.get("/verificar", response_model=schemas.VerificacionEstudiante)
def verificar_estudiante(
    documento: str, _obs=Depends(rbac.observar("estudiantes.ver")), db: Session = Depends(get_db)
):
    """Busca un documento en la base de datos ya importada (espejo del Excel
    oficial de matrícula), para saber si el estudiante ya está registrado
    antes de crearlo o de generarle un certificado."""
    estudiante = crud.buscar_por_documento(db, documento)
    return schemas.VerificacionEstudiante(existe=estudiante is not None, estudiante=estudiante)


@router.get("/conteo-por-sede")
def conteo_estudiantes_por_sede(
    grado: int | None = None,
    estado: str | None = None,
    _servicio: None = Depends(auth_servicio.exigir_token_servicio),
    db: Session = Depends(get_db),
):
    """Fase 4.1 — endpoint INTERNO, solo para los scripts de SAPRED (exige
    identidad de servicio, ver auth_servicio.py; nunca sesión humana). Es la
    alternativa reducida a GET /api/estudiantes: los scripts solo necesitan
    contar estudiantes activos por sede, nunca sus datos personales — esto
    nunca devuelve documento, nombre, fecha de nacimiento, género ni fotos.
    GET /api/estudiantes (el completo) sigue exactamente igual que antes."""
    return crud.conteo_estudiantes_por_sede(db, grado=grado, estado=estado)


@router.get("/tamano-descarga")
def tamano_descarga_sin_conexion(
    _obs=Depends(rbac.observar("estudiantes.ver")),
    db: Session = Depends(get_db),
):
    """Peso de «Descargar para usar sin wifi» (estudiantes activos): total y
    por sede, para mostrarlo antes de descargar."""
    activos = crud.listar_estudiantes(db, estado="ACTIVO")
    por_sede: dict[int, list] = {}
    for e in activos:
        por_sede.setdefault(e.sede_id, []).append(e)
    sedes = {s.id: s.nombre for s in db.query(models.Sede).all()}
    return {
        "total": crud.resumen_descarga_sin_conexion(db, activos),
        "sedes": [
            {"sede_id": sede_id, "nombre": sedes.get(sede_id, ""), **crud.resumen_descarga_sin_conexion(db, ests)}
            for sede_id, ests in sorted(por_sede.items(), key=lambda x: sedes.get(x[0], ""))
        ],
    }


@router.post("/matricula-nueva", response_model=schemas.Estudiante, status_code=201)
def matricular_estudiante_nuevo(
    solicitud: schemas.MatriculaNuevaSolicitud,
    identidad: auth.Identidad = Depends(rbac.requiere("estudiantes.crear")),
    db: Session = Depends(get_db),
):
    """Matricula un estudiante que todavía no está en el Excel oficial / SIMAT:
    lo crea con sus datos y su ficha de matrícula en un solo paso, marcado
    "pendiente SIMAT" y con quién lo matriculó (la sesión de esta petición)."""
    datos = solicitud.estudiante
    if crud.buscar_por_documento(db, datos.documento.strip()):
        raise HTTPException(status_code=409, detail="Ya existe un estudiante registrado con ese documento")
    if datos.sede_id is None or db.get(models.Sede, datos.sede_id) is None:
        raise HTTPException(status_code=400, detail="Escoja la sede del estudiante.")
    nuevo = models.Estudiante(**{**datos.model_dump(), "documento": datos.documento.strip()})
    nuevo.pendiente_simat = True
    nuevo.creado_por_id = identidad.usuario.id
    nuevo.creado_en = fechas.ahora_utc()
    db.add(nuevo)
    db.flush()
    ficha = models.DatosFichaEstudiante(estudiante_id=nuevo.id, actualizado_por_id=identidad.usuario.id)
    datos_ficha.campos_a_datos(solicitud.campos_ficha, ficha)
    db.add(ficha)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.post("/{estudiante_id}/confirmar-simat", response_model=schemas.Estudiante)
def confirmar_en_simat(
    estudiante_id: int,
    _identidad: auth.Identidad = Depends(rbac.requiere("estudiantes.editar")),
    db: Session = Depends(get_db),
):
    """Quita el aviso "pendiente SIMAT": ya se confirmó que el estudiante
    nuevo quedó registrado en SIMAT."""
    e = crud.obtener_estudiante(db, estudiante_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    e.pendiente_simat = False
    db.commit()
    db.refresh(e)
    return e


@router.post("", response_model=schemas.Estudiante, status_code=201)
def crear_estudiante(
    estudiante: schemas.EstudianteCreate,
    _obs=Depends(rbac.observar("estudiantes.crear")),
    db: Session = Depends(get_db),
):
    if crud.buscar_por_documento(db, estudiante.documento):
        raise HTTPException(
            status_code=409, detail="Ya existe un estudiante registrado con ese documento"
        )
    return crud.crear_estudiante(db, estudiante)


@router.get("/{estudiante_id}/datos-ficha", response_model=schemas.DatosFichaCampos)
def obtener_datos_ficha(
    estudiante_id: int, _obs=Depends(rbac.observar("estudiantes.ver")), db: Session = Depends(get_db)
):
    """Lo ya guardado del estudiante, en forma de casillas de la ficha de matrícula."""
    est = crud.obtener_estudiante(db, estudiante_id)
    if est is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    fila = db.query(models.DatosFichaEstudiante).filter_by(estudiante_id=estudiante_id).one_or_none()
    return {"campos": datos_ficha.datos_a_campos(fila, est)}


@router.put("/{estudiante_id}/datos-ficha", response_model=schemas.DatosFichaCampos)
def guardar_datos_ficha(
    estudiante_id: int,
    datos: schemas.DatosFichaCampos,
    _obs=Depends(rbac.observar("estudiantes.editar")),
    db: Session = Depends(get_db),
):
    """Guarda en el estudiante lo escrito en la ficha (acudiente, comunidad,
    etnia, discapacidad, lugar de expedición...). Nombres, documento, fecha de
    nacimiento y grado NO se tocan desde aquí: esos se editan en su lugar."""
    est = crud.obtener_estudiante(db, estudiante_id)
    if est is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    fila = db.query(models.DatosFichaEstudiante).filter_by(estudiante_id=estudiante_id).one_or_none()
    if fila is None:
        fila = models.DatosFichaEstudiante(estudiante_id=estudiante_id)
        db.add(fila)
    datos_ficha.campos_a_datos(datos.campos, fila)
    fila.actualizado_por_id = _obs.usuario.id if _obs is not None else None
    lugar = (datos.campos.get("municipio_expedicion") or "").strip()
    if lugar:
        est.lugar_expedicion_documento = lugar
    db.commit()
    return {"campos": datos_ficha.datos_a_campos(fila, est)}


@router.get("/{estudiante_id}/riesgo-promocion", response_model=schemas.RiesgoPromocion)
def riesgo_promocion_estudiante(
    estudiante_id: int,
    anio_lectivo: int | None = None,
    _obs=Depends(rbac.observar("estudiantes.ver")),
    db: Session = Depends(get_db),
):
    if crud.obtener_estudiante(db, estudiante_id) is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    return reporte_notas.riesgo_promocion(db, estudiante_id, anio_lectivo or fechas.anio_lectivo_actual())


@router.get("/{estudiante_id}", response_model=schemas.Estudiante)
def obtener_estudiante(
    estudiante_id: int, _obs=Depends(rbac.observar("estudiantes.ver")), db: Session = Depends(get_db)
):
    estudiante = crud.obtener_estudiante(db, estudiante_id)
    if estudiante is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    return estudiante


@router.patch("/{estudiante_id}", response_model=schemas.Estudiante)
def actualizar_estudiante(
    estudiante_id: int,
    cambios: schemas.EstudianteUpdate,
    _obs=Depends(rbac.observar("estudiantes.editar")),
    db: Session = Depends(get_db),
):
    estudiante = crud.actualizar_estudiante(db, estudiante_id, cambios)
    if estudiante is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    return estudiante


@router.delete("/{estudiante_id}", status_code=204)
def eliminar_estudiante(
    estudiante_id: int, _obs=Depends(rbac.observar("estudiantes.eliminar")), db: Session = Depends(get_db)
):
    try:
        eliminado = crud.eliminar_estudiante(db, estudiante_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not eliminado:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
