from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import crud, models, rbac, schemas
from ..database import get_db
from ..models import DIVISIONES_NOMBRES, GRADOS_NOMBRES

router = APIRouter(prefix="/api/sedes", tags=["sedes"])


@router.get("", response_model=list[schemas.SedeResumen])
def listar_sedes(
    _obs=Depends(rbac.observar("sedes.ver", tambien_servicio=True)), db: Session = Depends(get_db)
):
    # Fase 4A: observar() nunca bloquea. tambien_servicio=True porque los
    # scripts de SAPRED todavía llaman esta ruta con el token de servicio
    # (Fase 4.1) — si no, cada llamada real suya se vería como un rechazo.
    return crud.listar_sedes(db)


@router.get("/reporte", response_model=schemas.ReporteGeneral)
def reporte_general(
    solo_ietaba: bool = True,
    _obs=Depends(rbac.observar("reportes.ver")),
    db: Session = Depends(get_db),
):
    return crud.generar_reporte(db, solo_ietaba=solo_ietaba)


@router.patch("/{sede_id}", response_model=schemas.Sede)
def actualizar_sede(
    sede_id: int,
    cambios: schemas.SedeUpdate,
    _obs=Depends(rbac.observar("catalogos.gestionar")),
    db: Session = Depends(get_db),
):
    sede = crud.actualizar_sede(db, sede_id, cambios)
    if sede is None:
        raise HTTPException(status_code=404, detail="Sede no encontrada")
    return sede


@router.get("/{sede_id}/grados")
def listar_grados_de_sede(
    sede_id: int, _obs=Depends(rbac.observar("sedes.ver")), db: Session = Depends(get_db)
):
    sede = crud.obtener_sede(db, sede_id)
    if sede is None:
        raise HTTPException(status_code=404, detail="Sede no encontrada")

    grados = db.scalars(
        select(models.Estudiante.grado)
        .where(models.Estudiante.sede_id == sede_id)
        .distinct()
        .order_by(models.Estudiante.grado)
    ).all()

    resultado = []
    for g in grados:
        estudiantes = crud.listar_estudiantes(db, sede_id=sede_id, grado=g)
        activos = sum(1 for e in estudiantes if e.activo)
        divisiones = [
            {"numero": c, "nombre": DIVISIONES_NOMBRES.get(c, str(c))}
            for c in crud.listar_cursos_de_grado(db, sede_id, g)
        ]
        resultado.append(
            {
                "grado": g,
                "nombre_grado": GRADOS_NOMBRES.get(g, str(g)),
                "total_estudiantes": len(estudiantes),
                "total_activos": activos,
                "divisiones": divisiones,
            }
        )
    return resultado
