from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import auth_servicio, crud, rbac, schemas
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
