"""Resultados Saber 11 (ICFES) entre años: resumen general, lista por año y
ficha individual. Los datos los carga backend/importar_icfes.py (ver app/icfes.py).

Mismo permiso que Análisis académico (boletines.ver, en modo observación como
el resto de rutas de negocio), y además exige sesión: son resultados de
estudiantes con nombre."""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import auth, icfes, icfes_pdf, rbac
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


@router.get("/grupo")
def grupo(
    sede_id: int,
    grado: int,
    curso: int | None = None,
    identidad: auth.Identidad = Depends(auth.identidad_actual),
    _obs=Depends(rbac.observar("boletines.ver")),
    db: Session = Depends(get_db),
):
    """Reporte de un curso actual (ej. 11-2) con el ICFES de cada estudiante."""
    return icfes.resultados_por_grupo(db, sede_id, grado, curso)


@router.get("/grupo.pdf")
def grupo_pdf(
    sede_id: int,
    grado: int,
    curso: int | None = None,
    formato: str = "curso",  # curso = reporte consolidado | individual = una hoja por estudiante
    estudiante_id: int | None = None,  # solo con formato=individual: la hoja de un estudiante
    identidad: auth.Identidad = Depends(auth.identidad_actual),
    _obs=Depends(rbac.observar("boletines.ver")),
    db: Session = Depends(get_db),
):
    """PDF con el membrete oficial: reporte del curso o reportes individuales."""
    try:
        if formato == "individual":
            datos = icfes_pdf.generar_individuales_pdf(db, sede_id, grado, curso, estudiante_id)
        else:
            datos = icfes_pdf.generar_reporte_grupo_pdf(db, sede_id, grado, curso)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    grupo = f"{grado}-{curso}" if curso else str(grado)
    tipo = "individuales" if formato == "individual" else "curso"
    nombre = f"icfes_{grupo}_{tipo}_{dt.date.today().isoformat()}.pdf"
    return Response(
        content=datos,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )


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
