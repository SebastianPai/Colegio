"""Módulo docente: mis cursos, mis estudiantes, y el registro de asistencia
de sus propios bloques. El alcance de cada docente sale SIEMPRE de sus
propias asignaciones (AsignacionDocente/BloqueHorario) resueltas en el
backend — nunca de lo que mande la URL o el body (ver crud.py y
asistencia.py, sección "Módulo docente")."""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import asistencia as asistencia_logica
from .. import auth, configuracion, crud, datos_ficha, fechas, models, rbac, schemas
from ..database import get_db

router = APIRouter(prefix="/api/docente", tags=["docente"])


def _docente_id_o_error(identidad: auth.Identidad) -> int:
    if identidad.usuario.docente_id is None:
        raise HTTPException(
            status_code=409,
            detail="Tu usuario no está vinculado a un docente. Pídele a administración que lo enlace.",
        )
    return identidad.usuario.docente_id


@router.get("/inicio", response_model=schemas.InicioDocente)
def inicio(
    identidad: auth.Identidad = Depends(rbac.requiere("asistencia.registrar")),
    db: Session = Depends(get_db),
):
    docente_id = _docente_id_o_error(identidad)
    return asistencia_logica.clases_de_hoy_docente(db, docente_id)


@router.get("/historial", response_model=list[schemas.HistorialAsistenciaItem])
def historial(
    dias: int = 30,
    identidad: auth.Identidad = Depends(rbac.requiere("asistencia.ver_propia")),
    db: Session = Depends(get_db),
):
    docente_id = _docente_id_o_error(identidad)
    return asistencia_logica.historial_resumen_docente(db, docente_id, dias=min(max(dias, 1), 90))


@router.get("/mis-cursos", response_model=list[schemas.CursoDocente])
def mis_cursos(
    anio_lectivo: int | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("asistencia.registrar")),
    db: Session = Depends(get_db),
):
    docente_id = _docente_id_o_error(identidad)
    return crud.mis_cursos_docente(db, docente_id, anio_lectivo or fechas.anio_lectivo_actual())


@router.get("/grupo/estudiantes", response_model=list[schemas.EstudianteDocentePerfil])
def estudiantes_del_grupo(
    sede_id: int, grado: int, curso: int | None = None, anio_lectivo: int | None = None,
    # asistencia.registrar (no estudiantes.ver) a propósito: estudiantes.ver
    # es el permiso del Listado ADMINISTRATIVO completo (los ~970 de toda la
    # institución) — usarlo aquí acoplaba "ver mi propio grupo" con "ver el
    # listado entero", y hacía que la pestaña Listado le apareciera a
    # cualquier docente. El alcance real ya lo valida
    # docente_tiene_acceso_grupo() más abajo, no este permiso.
    identidad: auth.Identidad = Depends(rbac.requiere("asistencia.registrar")),
    db: Session = Depends(get_db),
):
    docente_id = _docente_id_o_error(identidad)
    anio = anio_lectivo or fechas.anio_lectivo_actual()
    if not crud.docente_tiene_acceso_grupo(db, docente_id, sede_id, grado, curso, anio):
        raise HTTPException(status_code=403, detail="No tienes ese grupo asignado.")
    estudiantes = crud.estudiantes_de_grupo_docente(db, sede_id, grado, curso)
    return [crud.estudiante_a_perfil_docente(e) for e in estudiantes]


@router.get("/grupo/seguimiento", response_model=schemas.SeguimientoGrupoDocente)
def seguimiento_del_grupo(
    sede_id: int, grado: int, curso: int | None = None, area_id: int | None = None, anio_lectivo: int | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("asistencia.registrar")),  # ver nota en estudiantes_del_grupo
    db: Session = Depends(get_db),
):
    """Mis estudiantes con cómo van (notas en mi materia, faltas recientes y,
    si soy director de grupo, las materias que cada uno va perdiendo)."""
    docente_id = _docente_id_o_error(identidad)
    anio = anio_lectivo or fechas.anio_lectivo_actual()
    if not crud.docente_tiene_acceso_grupo(db, docente_id, sede_id, grado, curso, anio):
        raise HTTPException(status_code=403, detail="No tienes ese grupo asignado.")
    return crud.seguimiento_grupo_docente(db, docente_id, sede_id, grado, curso, area_id, anio)


@router.get("/estudiante/{estudiante_id}/rendimiento", response_model=schemas.RendimientoEstudianteDocente)
def rendimiento_estudiante(
    estudiante_id: int, anio_lectivo: int | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("asistencia.registrar")),
    db: Session = Depends(get_db),
):
    """Todas las materias (con su docente) y las faltas recientes: solo para
    el director de grupo, igual que el perfil."""
    docente_id = _docente_id_o_error(identidad)
    anio = anio_lectivo or fechas.anio_lectivo_actual()
    e = crud.estudiante_completo_si_es_director(db, docente_id, estudiante_id, anio)
    if e is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    return crud.rendimiento_estudiante_docente(db, e, anio)


@router.get("/estudiante/{estudiante_id}", response_model=schemas.EstudianteDocentePerfil)
def perfil_estudiante(
    estudiante_id: int, anio_lectivo: int | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("asistencia.registrar")),  # ver nota arriba
    db: Session = Depends(get_db),
):
    docente_id = _docente_id_o_error(identidad)
    anio = anio_lectivo or fechas.anio_lectivo_actual()
    perfil = crud.perfil_estudiante_para_docente(db, docente_id, estudiante_id, anio)
    if perfil is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    return perfil


@router.get("/asistencia/bloque", response_model=schemas.AsistenciaBloqueVista)
def vista_bloque_asistencia(
    sede_id: int, grado: int, curso: int | None = None, area_id: int | None = None,
    bloque_horario_id: int | None = None, fecha: dt.date | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("asistencia.registrar")),
    db: Session = Depends(get_db),
):
    try:
        return asistencia_logica.vista_bloque(
            db, usuario=identidad.usuario, tiene_permiso_amplio=False,
            sede_id=sede_id, grado=grado, curso=curso, area_id=area_id,
            bloque_horario_id=bloque_horario_id, fecha=fecha or fechas.hoy_colombia(),
        )
    except asistencia_logica.DatosInvalidos as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/asistencia", response_model=list[schemas.AsistenciaRegistroResultado])
def registrar_asistencia(
    datos: schemas.AsistenciaRegistroLote,
    identidad: auth.Identidad = Depends(rbac.requiere("asistencia.registrar")),
    db: Session = Depends(get_db),
):
    try:
        registros = asistencia_logica.registrar_lote(
            db, usuario=identidad.usuario, tiene_permiso_amplio=False, datos=datos,
        )
    except asistencia_logica.SinAutorizacion as e:
        raise HTTPException(status_code=403, detail=str(e))
    except asistencia_logica.DatosInvalidos as e:
        raise HTTPException(status_code=400, detail=str(e))
    return [
        schemas.AsistenciaRegistroResultado(
            estudiante_id=r.estudiante_id, estado=r.estado,
            registrado_en=r.registrado_en, en_conflicto=r.en_conflicto,
        )
        for r in registros
    ]


# --- Ficha de matrícula completa (solo director de grupo) --------------------
# El director de grupo (AsignacionDocente con area_id IS NULL) puede ver y
# editar la ficha de matrícula OFICIAL completa de sus estudiantes — el mismo
# documento/formulario que hoy usa Secretaría (ver frontend/static/js/ficha.js
# y frontend/static/ficha_matricula.html). Un profesor de área que no sea
# director sigue viendo solo el listado y el perfil acotado de arriba.


@router.get("/estudiante/{estudiante_id}/completo", response_model=schemas.Estudiante)
def estudiante_completo(
    estudiante_id: int, anio_lectivo: int | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("asistencia.registrar")),
    db: Session = Depends(get_db),
):
    docente_id = _docente_id_o_error(identidad)
    anio = anio_lectivo or fechas.anio_lectivo_actual()
    estudiante = crud.estudiante_completo_si_es_director(db, docente_id, estudiante_id, anio)
    if estudiante is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    return estudiante


@router.get("/estudiante/{estudiante_id}/datos-ficha", response_model=schemas.DatosFichaCampos)
def datos_ficha_estudiante(
    estudiante_id: int, anio_lectivo: int | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("asistencia.registrar")),
    db: Session = Depends(get_db),
):
    docente_id = _docente_id_o_error(identidad)
    anio = anio_lectivo or fechas.anio_lectivo_actual()
    estudiante = crud.estudiante_completo_si_es_director(db, docente_id, estudiante_id, anio)
    if estudiante is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    fila = db.query(models.DatosFichaEstudiante).filter_by(estudiante_id=estudiante_id).one_or_none()
    return {"campos": datos_ficha.datos_a_campos(fila, estudiante)}


@router.put("/estudiante/{estudiante_id}/datos-ficha", response_model=schemas.DatosFichaCampos)
def guardar_datos_ficha_estudiante(
    estudiante_id: int,
    datos: schemas.DatosFichaCampos,
    anio_lectivo: int | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("estudiantes.editar_ficha_grupo")),
    db: Session = Depends(get_db),
):
    docente_id = _docente_id_o_error(identidad)
    anio = anio_lectivo or fechas.anio_lectivo_actual()
    estudiante = crud.estudiante_completo_si_es_director(db, docente_id, estudiante_id, anio)
    if estudiante is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    fila = db.query(models.DatosFichaEstudiante).filter_by(estudiante_id=estudiante_id).one_or_none()
    if fila is None:
        fila = models.DatosFichaEstudiante(estudiante_id=estudiante_id)
        db.add(fila)
    datos_ficha.campos_a_datos(datos.campos, fila)
    fila.actualizado_por_id = identidad.usuario.id
    lugar = (datos.campos.get("municipio_expedicion") or "").strip()
    if lugar:
        estudiante.lugar_expedicion_documento = lugar
    db.commit()
    return {"campos": datos_ficha.datos_a_campos(fila, estudiante)}


# --- Observaciones -------------------------------------------------------------
# Cualquier docente asignado al grupo (de área o director) puede registrar y
# ver observaciones de sus estudiantes — a diferencia del perfil/ficha
# completo (arriba), que sí queda solo para el director de grupo. Por eso
# aquí se usa estudiante_si_docente_tiene_acceso(), no
# perfil_estudiante_para_docente().


@router.get("/observaciones", response_model=list[schemas.ObservacionVista])
def observaciones_del_estudiante(
    estudiante_id: int, anio_lectivo: int | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("observaciones.ver")),
    db: Session = Depends(get_db),
):
    docente_id = _docente_id_o_error(identidad)
    anio = anio_lectivo or fechas.anio_lectivo_actual()
    if crud.estudiante_si_docente_tiene_acceso(db, docente_id, estudiante_id, anio) is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    ve_confidenciales = rbac.tiene_permiso(db, identidad.usuario, "observaciones.ver_confidenciales")
    observaciones = crud.listar_observaciones_estudiante(
        db, estudiante_id, usuario_id=identidad.usuario.id, ve_confidenciales=ve_confidenciales
    )
    return [crud.observacion_a_vista(o, incluir_seguimientos=False) for o in observaciones]


@router.post("/observaciones", response_model=schemas.ObservacionVista)
def crear_observacion_docente(
    datos: schemas.ObservacionCrear,
    identidad: auth.Identidad = Depends(rbac.requiere("observaciones.crear")),
    db: Session = Depends(get_db),
):
    if datos.tipo not in schemas.TIPOS_OBSERVACION:
        raise HTTPException(status_code=400, detail=f"Tipo de observación inválido: {datos.tipo!r}")
    if datos.tipo == "psicologia" and not configuracion.orientacion_activa(db):
        # Con Orientación apagada nadie vería la remisión: mejor decirlo que perderla.
        raise HTTPException(status_code=400, detail="Orientación está desactivada por ahora: la remisión a psicología no se puede enviar. Avísale a coordinación.")
    docente_id = _docente_id_o_error(identidad)
    anio = fechas.anio_lectivo_actual()
    estudiante = crud.estudiante_si_docente_tiene_acceso(db, docente_id, datos.estudiante_id, anio)
    if estudiante is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    o = crud.crear_observacion(db, estudiante, identidad.usuario.id, datos)
    return crud.observacion_a_vista(o, incluir_seguimientos=False)
