"""Permisos de coordinación para promociones fuera de la regla normal (ver
app/promocion.py). Quien genera la ficha (secretaría o el director de grupo)
evalúa y, si hace falta, pide el permiso; coordinación/administración
(promocion.autorizar) lo aprueba o rechaza. Todo queda registrado."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth, crud, models, promocion, rbac, schemas
from ..database import get_db

router = APIRouter(prefix="/api/promocion", tags=["promocion"])


def _estudiante(db: Session, estudiante_id: int) -> models.Estudiante:
    e = crud.obtener_estudiante(db, estudiante_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    return e


@router.get("/evaluar", response_model=schemas.EvaluacionPromocion)
def evaluar(
    estudiante_id: int,
    grado_destino: int,
    _obs=Depends(rbac.observar("estudiantes.ver")),
    db: Session = Depends(get_db),
):
    return promocion.evaluar(db, _estudiante(db, estudiante_id), grado_destino)


@router.post("/solicitudes", response_model=schemas.SolicitudPromocionOut)
def solicitar(
    datos: schemas.SolicitudPromocionCrear,
    _obs=Depends(rbac.observar("estudiantes.ver")),
    db: Session = Depends(get_db),
):
    # Pedir permiso exige saber QUIÉN lo pide: sin sesión no se registra.
    if _obs is None:
        raise HTTPException(status_code=401, detail="Inicia sesión para pedir el permiso a coordinación.")
    if len((datos.justificacion or "").strip()) < 10:
        raise HTTPException(status_code=400, detail="Explica el motivo (al menos una frase): coordinación decide con base en esto.")
    s, error = promocion.crear_solicitud(
        db, _estudiante(db, datos.estudiante_id), datos.grado_destino, datos.justificacion, _obs.usuario.id
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return promocion.solicitud_a_salida(s)


@router.get("/solicitudes", response_model=list[schemas.SolicitudPromocionOut])
def listar(
    estado: str | None = "pendiente",
    identidad: auth.Identidad = Depends(rbac.requiere("alertas.ver")),
    db: Session = Depends(get_db),
):
    consulta = select(models.SolicitudPromocion).order_by(models.SolicitudPromocion.solicitado_en.desc())
    if estado:
        consulta = consulta.where(models.SolicitudPromocion.estado == estado)
    return [promocion.solicitud_a_salida(s) for s in db.scalars(consulta.limit(500))]


@router.post("/solicitudes/{solicitud_id}/decidir", response_model=schemas.SolicitudPromocionOut)
def decidir(
    solicitud_id: int,
    datos: schemas.SolicitudPromocionDecidir,
    identidad: auth.Identidad = Depends(rbac.requiere("promocion.autorizar")),
    db: Session = Depends(get_db),
):
    s = db.get(models.SolicitudPromocion, solicitud_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    error = promocion.decidir(db, s, datos.aprobar, datos.nota, identidad.usuario.id)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return promocion.solicitud_a_salida(s)


@router.post("/solicitudes/{solicitud_id}/anular", response_model=schemas.SolicitudPromocionOut)
def anular(
    solicitud_id: int,
    identidad: auth.Identidad = Depends(auth.identidad_actual),
    db: Session = Depends(get_db),
):
    """Retirar una solicitud pendiente: solo quien la pidió o quien puede autorizar."""
    s = db.get(models.SolicitudPromocion, solicitud_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if s.estado != "pendiente":
        raise HTTPException(status_code=400, detail=f"Esta solicitud ya está {s.estado}.")
    if s.solicitado_por_id != identidad.usuario.id and not rbac.tiene_permiso(db, identidad.usuario, "promocion.autorizar"):
        raise HTTPException(status_code=403, detail="Solo quien pidió el permiso o coordinación pueden retirarlo.")
    s.estado = "anulada"
    db.commit()
    return promocion.solicitud_a_salida(s)
