import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, fechas, schemas
from ..database import get_db
from ..models import GRADOS_NOMBRES

router = APIRouter(prefix="/api/asistencia", tags=["asistencia"])


@router.post("", response_model=schemas.Asistencia)
def marcar_asistencia(datos: schemas.AsistenciaMarcar, db: Session = Depends(get_db)):
    if crud.obtener_estudiante(db, datos.estudiante_id) is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    return crud.marcar_asistencia(db, datos)


@router.get("/grupo")
def asistencia_del_grupo(
    sede_id: int,
    grado: int,
    curso: int | None = None,
    fecha: dt.date | None = None,
    db: Session = Depends(get_db),
):
    sede = crud.obtener_sede(db, sede_id)
    if sede is None:
        raise HTTPException(status_code=404, detail="Sede no encontrada")

    fecha_consulta = fecha or fechas.hoy_colombia()
    estudiantes = crud.listar_estudiantes(
        db, sede_id=sede_id, grado=grado, curso=curso, estado="ACTIVO"
    )
    registros = crud.asistencia_por_grupo_y_fecha(db, sede_id, grado, fecha_consulta, curso=curso)

    return {
        "sede": schemas.Sede.model_validate(sede),
        "grado": grado,
        "curso": curso,
        "nombre_grado": GRADOS_NOMBRES.get(grado, str(grado)),
        "fecha": fecha_consulta,
        "estudiantes": [
            {
                "id": e.id,
                "nombres": f"{e.primer_nombre} {e.segundo_nombre or ''}".strip(),
                "apellidos": f"{e.primer_apellido} {e.segundo_apellido or ''}".strip(),
                "documento": e.documento,
                "presente": registros[e.id].presente if e.id in registros else None,
            }
            for e in estudiantes
        ],
    }
