import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth, fechas, models, rbac, schemas
from ..database import get_db

router = APIRouter(prefix="/api/alertas", tags=["alertas"])


def _salida(a: models.AlertaPromocion) -> schemas.AlertaPromocionOut:
    return schemas.AlertaPromocionOut(
        id=a.id, creado_en=a.creado_en, estudiante_id=a.estudiante_id,
        estudiante_nombre=a.estudiante.nombre_completo, estudiante_documento=a.estudiante.documento,
        usuario_nombre=a.usuario.nombre if a.usuario else None,
        anio_lectivo=a.anio_lectivo, grado_actual=a.grado_actual, grado_destino=a.grado_destino,
        materias_perdidas=a.materias_perdidas, detalle=json.loads(a.detalle or "[]"), estado=a.estado,
        atendida_por_nombre=a.atendida_por.nombre if a.atendida_por else None,
        atendida_en=a.atendida_en, nota_atencion=a.nota_atencion,
    )


@router.get("/promocion", response_model=list[schemas.AlertaPromocionOut])
def listar_alertas_promocion(
    estado: str | None = "pendiente",
    identidad: auth.Identidad = Depends(rbac.requiere("alertas.ver")),
    db: Session = Depends(get_db),
):
    consulta = select(models.AlertaPromocion).order_by(models.AlertaPromocion.creado_en.desc())
    if estado:
        consulta = consulta.where(models.AlertaPromocion.estado == estado)
    return [_salida(a) for a in db.scalars(consulta.limit(500)).all()]


@router.post("/promocion/{alerta_id}/atender", response_model=schemas.AlertaPromocionOut)
def atender_alerta_promocion(
    alerta_id: int,
    datos: schemas.AlertaAtender,
    identidad: auth.Identidad = Depends(rbac.requiere("alertas.atender")),
    db: Session = Depends(get_db),
):
    a = db.get(models.AlertaPromocion, alerta_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    a.estado = "atendida"
    a.atendida_por_id = identidad.usuario.id
    a.atendida_en = fechas.ahora_utc()
    a.nota_atencion = (datos.nota or "").strip() or None
    db.commit()
    return _salida(a)
