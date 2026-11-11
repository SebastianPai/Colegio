"""Censo indígena del resguardo (Ministerio del Interior): reporte de los
estudiantes que pertenecen al resguardo, su PDF con membrete y lo que dice el
censo de cada estudiante. Los datos los carga backend/importar_censo.py (ver
app/censo.py y app/censo_pdf.py)."""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import censo, censo_pdf, rbac
from ..database import get_db

router = APIRouter(prefix="/api/censo", tags=["censo"])


@router.get("/reporte")
def reporte(
    resguardo: str | None = None,
    solo_ietaba: bool = False,
    _obs=Depends(rbac.observar("reportes.ver")),
    db: Session = Depends(get_db),
):
    return censo.reporte(db, resguardo, solo_ietaba)


@router.get("/reporte.pdf")
def reporte_pdf(
    desde: int = 0,
    hasta: int = 11,
    _obs=Depends(rbac.observar("reportes.exportar")),
    db: Session = Depends(get_db),
):
    """Estudiantes del resguardo por grado (solo sedes IETABA), con membrete."""
    try:
        datos = censo_pdf.generar_pdf(db, desde, hasta)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    nombre = f"censo_gran_sabalo_grados_{desde}-{hasta}_{dt.date.today().isoformat()}.pdf"
    return Response(content=datos, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{nombre}"'})


@router.get("/estudiantes/{estudiante_id}")
def del_estudiante(
    estudiante_id: int,
    _obs=Depends(rbac.observar("estudiantes.ver")),
    db: Session = Depends(get_db),
):
    return censo.del_estudiante(db, estudiante_id)
