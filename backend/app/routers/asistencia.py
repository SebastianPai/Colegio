"""Consulta y corrección de asistencia para coordinación/administración
(asistencia.ver / asistencia.corregir / asistencia.anular). El registro en
sí (lo que hace un docente en su propio bloque) vive en routers/docente.py:
este router es para quien supervisa, no para quien dicta clase."""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import asistencia as asistencia_logica
from .. import auth, fechas, rbac, schemas
from ..database import get_db

router = APIRouter(prefix="/api/asistencia", tags=["asistencia"])


@router.get("/bloque", response_model=schemas.AsistenciaBloqueVista)
def ver_bloque(
    sede_id: int, grado: int, curso: int | None = None, area_id: int | None = None,
    bloque_horario_id: int | None = None, fecha: dt.date | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("asistencia.ver")),
    db: Session = Depends(get_db),
):
    try:
        return asistencia_logica.vista_bloque(
            db, usuario=identidad.usuario, tiene_permiso_amplio=True,
            sede_id=sede_id, grado=grado, curso=curso, area_id=area_id,
            bloque_horario_id=bloque_horario_id, fecha=fecha or fechas.hoy_colombia(),
        )
    except asistencia_logica.DatosInvalidos as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/panel-dia", response_model=list[schemas.PanelAsistenciaGrupo])
def panel_dia(
    sede_id: int | None = None, fecha: dt.date | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("asistencia.cumplimiento")),
    db: Session = Depends(get_db),
):
    return asistencia_logica.panel_dia(db, fecha or fechas.hoy_colombia(), sede_id=sede_id)


@router.get("/alertas-estudiantes", response_model=list[schemas.AlertaAsistenciaEstudiante])
def alertas_estudiantes(
    sede_id: int | None = None, grado: int | None = None, dias: int = 21, umbral_racha: int = 3,
    identidad: auth.Identidad = Depends(rbac.requiere("asistencia.estadisticas")),
    db: Session = Depends(get_db),
):
    return asistencia_logica.alertas_estudiantes(
        db, sede_id=sede_id, grado=grado, dias=dias, umbral_racha=umbral_racha
    )


@router.patch("/{asistencia_id}/corregir", response_model=schemas.AsistenciaRegistroResultado)
def corregir(
    asistencia_id: int, datos: schemas.AsistenciaCorregir,
    identidad: auth.Identidad = Depends(rbac.requiere("asistencia.corregir")),
    db: Session = Depends(get_db),
):
    try:
        a = asistencia_logica.corregir_registro(db, usuario=identidad.usuario, asistencia_id=asistencia_id, datos=datos)
    except asistencia_logica.NoEncontrado as e:
        raise HTTPException(status_code=404, detail=str(e))
    except asistencia_logica.DatosInvalidos as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.AsistenciaRegistroResultado(
        estudiante_id=a.estudiante_id, estado=a.estado, registrado_en=a.registrado_en, en_conflicto=a.en_conflicto,
    )


@router.post("/{asistencia_id}/anular", response_model=schemas.AsistenciaRegistroResultado)
def anular(
    asistencia_id: int, datos: schemas.AsistenciaAnular,
    identidad: auth.Identidad = Depends(rbac.requiere("asistencia.anular")),
    db: Session = Depends(get_db),
):
    try:
        a = asistencia_logica.anular_registro(db, usuario=identidad.usuario, asistencia_id=asistencia_id, motivo=datos.motivo)
    except asistencia_logica.NoEncontrado as e:
        raise HTTPException(status_code=404, detail=str(e))
    return schemas.AsistenciaRegistroResultado(
        estudiante_id=a.estudiante_id, estado=a.estado, registrado_en=a.registrado_en, en_conflicto=a.en_conflicto,
    )
