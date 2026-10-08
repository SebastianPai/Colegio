"""Resultados Saber 11 (ICFES) entre años: resumen general, lista por año y
ficha individual. Los datos los carga backend/importar_icfes.py (ver app/icfes.py).

Mismo permiso que Análisis académico (boletines.ver, en modo observación como
el resto de rutas de negocio), y además exige sesión: son resultados de
estudiantes con nombre."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import auth, icfes, rbac
from ..database import get_db

router = APIRouter(prefix="/api/icfes", tags=["icfes"])


@router.get("/panorama")
def panorama(
    identidad: auth.Identidad = Depends(auth.identidad_actual),
    _obs=Depends(rbac.observar("boletines.ver")),
    db: Session = Depends(get_db),
):
    return icfes.panorama(db)


@router.get("/anios/{anio}/estudiantes")
def estudiantes_anio(
    anio: int,
    identidad: auth.Identidad = Depends(auth.identidad_actual),
    _obs=Depends(rbac.observar("boletines.ver")),
    db: Session = Depends(get_db),
):
    return icfes.estudiantes_anio(db, anio)


@router.get("/resultados/{resultado_id}")
def ficha(
    resultado_id: int,
    identidad: auth.Identidad = Depends(auth.identidad_actual),
    _obs=Depends(rbac.observar("boletines.ver")),
    db: Session = Depends(get_db),
):
    datos = icfes.ficha(db, resultado_id)
    if datos is None:
        raise HTTPException(status_code=404, detail="Resultado no encontrado")
    return datos
