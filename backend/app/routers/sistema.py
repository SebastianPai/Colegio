"""Parámetros generales del sistema (app/configuracion.py). Hoy: activar o
desactivar el módulo de Orientación (solo administración:
configuracion.gestionar). Cualquier usuario con sesión puede CONSULTAR qué
módulos están activos, para que la interfaz oculte lo que está apagado."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import auth, configuracion, models, rbac
from ..database import get_db

router = APIRouter(prefix="/api/sistema", tags=["sistema"])


class EstadoModulos(BaseModel):
    orientacion: bool
    orientacion_cambiado_por: str | None = None
    orientacion_cambiado_en: str | None = None


class CambiarModulo(BaseModel):
    activo: bool


def _estado(db: Session) -> EstadoModulos:
    fila = db.get(models.ConfiguracionSistema, configuracion.ORIENTACION_ACTIVA)
    return EstadoModulos(
        orientacion=configuracion.orientacion_activa(db),
        orientacion_cambiado_por=fila.actualizado_por.nombre if fila and fila.actualizado_por else None,
        orientacion_cambiado_en=fila.actualizado_en.isoformat() + "Z" if fila else None,
    )


@router.get("/modulos", response_model=EstadoModulos)
def modulos(identidad: auth.Identidad = Depends(auth.identidad_actual), db: Session = Depends(get_db)):
    return _estado(db)


@router.put("/modulos/orientacion", response_model=EstadoModulos)
def cambiar_orientacion(
    datos: CambiarModulo,
    identidad: auth.Identidad = Depends(rbac.requiere("configuracion.gestionar")),
    db: Session = Depends(get_db),
):
    configuracion.guardar_bool(db, configuracion.ORIENTACION_ACTIVA, datos.activo, identidad.usuario.id)
    return _estado(db)
