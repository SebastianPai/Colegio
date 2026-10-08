"""Bandeja de orientación/psicología: observaciones confidenciales y
remisiones que llegan de los docentes, más el seguimiento interno del caso
(SeguimientoObservacion) — nunca visible para quien remitió."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth, configuracion, crud, models, rbac, schemas
from ..database import get_db

# Apagado por el administrador (configuracion.py): todas estas rutas responden 423.
router = APIRouter(prefix="/api/orientacion", tags=["orientacion"], dependencies=[Depends(configuracion.exigir_orientacion_activa)])


@router.get("/observaciones", response_model=list[schemas.ObservacionVista])
def bandeja(
    estado: str | None = None, tipo: str | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("observaciones.ver_confidenciales")),
    db: Session = Depends(get_db),
):
    stmt = select(models.Observacion).order_by(models.Observacion.creado_en.desc())
    if estado:
        stmt = stmt.where(models.Observacion.estado == estado)
    if tipo:
        stmt = stmt.where(models.Observacion.tipo == tipo)
    observaciones = db.scalars(stmt.limit(500)).all()
    return [crud.observacion_a_vista(o, incluir_seguimientos=True) for o in observaciones]


@router.post("/observaciones/{observacion_id}/seguimiento", response_model=schemas.ObservacionVista)
def agregar_seguimiento(
    observacion_id: int, datos: schemas.SeguimientoCrear,
    identidad: auth.Identidad = Depends(rbac.requiere("seguimientos.gestionar")),
    db: Session = Depends(get_db),
):
    o = db.get(models.Observacion, observacion_id)
    if o is None:
        raise HTTPException(status_code=404, detail="Observación no encontrada")
    if not (datos.nota or "").strip():
        raise HTTPException(status_code=400, detail="La nota no puede estar vacía.")
    crud.agregar_seguimiento(db, observacion_id, identidad.usuario.id, datos.nota.strip())
    db.refresh(o)
    return crud.observacion_a_vista(o, incluir_seguimientos=True)


@router.patch("/observaciones/{observacion_id}/estado", response_model=schemas.ObservacionVista)
def cambiar_estado(
    observacion_id: int, datos: schemas.ObservacionEstado,
    identidad: auth.Identidad = Depends(rbac.requiere("observaciones.ver_confidenciales")),
    db: Session = Depends(get_db),
):
    if datos.estado not in ("abierta", "atendida", "cerrada"):
        raise HTTPException(status_code=400, detail=f"Estado inválido: {datos.estado!r}")
    o = crud.cambiar_estado_observacion(db, observacion_id, identidad.usuario.id, datos)
    if o is None:
        raise HTTPException(status_code=404, detail="Observación no encontrada")
    return crud.observacion_a_vista(o, incluir_seguimientos=True)
