"""Orientación escolar / diagnóstico. Tres capas separadas a propósito
(ver models.py): DiagnosticoGrado/DiagnosticoMencion son la fotografía
importada del Excel (solo lectura, nunca se editan); Caso es el trabajo
ACTIVO de orientación sobre un estudiante puntual (nace de una mención o se
crea a mano); CasoSeguimiento es el historial de un caso. Mismo nivel de
protección que /api/orientacion (datos sensibles: salud, embarazos,
desplazamiento, conflicto armado) — requiere() bloquea, no solo observa."""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth, configuracion, crud, diagnostico_pdf, models, rbac, schemas
from ..database import get_db

# Apagado por el administrador (configuracion.py): todas estas rutas responden 423.
router = APIRouter(prefix="/api/diagnosticos", tags=["diagnosticos"], dependencies=[Depends(configuracion.exigir_orientacion_activa)])


@router.get("/resumen", response_model=schemas.OrientacionResumen)
def resumen(
    sede_id: int | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.ver")),
    db: Session = Depends(get_db),
):
    return crud.resumen_orientacion(db, sede_id=sede_id)


@router.get("/grados", response_model=list[schemas.DiagnosticoGradoResumen])
def listar_grados(
    sede_id: int | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.ver")),
    db: Session = Depends(get_db),
):
    return crud.listar_diagnosticos_actuales(db, sede_id=sede_id)


@router.get("/grupos", response_model=list[schemas.GrupoOrientacion])
def listar_grupos(
    sede_id: int,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.ver")),
    db: Session = Depends(get_db),
):
    """Grupos de la sede según matrícula, con su diagnóstico vigente si
    existe — la entrada de "Orientación por grado"."""
    if db.get(models.Sede, sede_id) is None:
        raise HTTPException(status_code=404, detail="Sede no encontrada")
    return crud.listar_grupos_orientacion(db, sede_id)


@router.get("/generales", response_model=list[schemas.GeneralesGrupo])
def generales(
    sede_id: int,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.ver")),
    db: Session = Depends(get_db),
):
    """Lo general de cada grupo (temáticas, estrategias, resguardos...), todos juntos."""
    return crud.generales_por_grupo(db, sede_id)


@router.get("/grupos/{sede_id}/{grado}", response_model=schemas.GrupoOrientacionDetalle)
def detalle_grupo(
    sede_id: int,
    grado: int,
    curso: int | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.ver")),
    db: Session = Depends(get_db),
):
    detalle = crud.detalle_grupo_orientacion(db, sede_id, grado, curso)
    if detalle is None:
        raise HTTPException(status_code=404, detail="Sede no encontrada")
    return detalle


def _respuesta_pdf(datos: bytes, nombre: str) -> Response:
    return Response(
        content=datos, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )


@router.get("/grupos/{sede_id}/{grado}/pdf")
def pdf_grupo(
    sede_id: int,
    grado: int,
    curso: int | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.exportar")),
    db: Session = Depends(get_db),
):
    """Informe de orientación del grupo (resumen, estudiantes con novedades
    y casos) — distinto del PDF del diagnóstico del Excel (/grados/{id}/pdf)."""
    datos = diagnostico_pdf.generar_informe_grupo_pdf(db, sede_id, grado, curso, elaborado_por=identidad.usuario.nombre)
    if datos is None:
        raise HTTPException(status_code=404, detail="Sede no encontrada")
    sufijo = f"{grado}-{curso}" if curso is not None else str(grado)
    return _respuesta_pdf(datos, f"orientacion_grupo_{sufijo}_{dt.date.today().isoformat()}.pdf")


@router.get("/institucional/pdf")
def pdf_institucional(
    sede_id: int,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.exportar")),
    db: Session = Depends(get_db),
):
    """Informe general de orientación de toda la sede."""
    datos = diagnostico_pdf.generar_informe_institucional_pdf(db, sede_id, elaborado_por=identidad.usuario.nombre)
    if datos is None:
        raise HTTPException(status_code=404, detail="Sede no encontrada")
    return _respuesta_pdf(datos, f"orientacion_informe_general_{dt.date.today().isoformat()}.pdf")


def _obtener_diagnostico(db: Session, diagnostico_id: int) -> models.DiagnosticoGrado:
    d = db.get(models.DiagnosticoGrado, diagnostico_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Diagnóstico no encontrado")
    return d


@router.get("/grados/{diagnostico_id}", response_model=schemas.DiagnosticoGradoDetalle)
def detalle_grado(
    diagnostico_id: int,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.ver")),
    db: Session = Depends(get_db),
):
    d = _obtener_diagnostico(db, diagnostico_id)
    return crud.diagnostico_a_detalle(db, d)


@router.get("/grados/{diagnostico_id}/pdf")
def pdf_grado(
    diagnostico_id: int,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.exportar")),
    db: Session = Depends(get_db),
):
    d = _obtener_diagnostico(db, diagnostico_id)
    datos = diagnostico_pdf.generar_diagnostico_grado_pdf(db, d, elaborado_por=identidad.usuario.nombre)
    nombre = f"diagnostico_{d.hoja_excel.strip().replace(' ', '_')}_{dt.date.today().isoformat()}.pdf"
    return Response(
        content=datos, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )


@router.get("/estudiantes/{estudiante_id}", response_model=schemas.DiagnosticoEstudianteResumen)
def resumen_estudiante(
    estudiante_id: int,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.ver")),
    db: Session = Depends(get_db),
):
    if db.get(models.Estudiante, estudiante_id) is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    return crud.resumen_estudiante_diagnostico(db, estudiante_id)


@router.get("/estudiantes/{estudiante_id}/pdf")
def pdf_estudiante(
    estudiante_id: int,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.exportar")),
    db: Session = Depends(get_db),
):
    estudiante = db.get(models.Estudiante, estudiante_id)
    if estudiante is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    menciones = db.scalars(
        select(models.DiagnosticoMencion)
        .join(models.DiagnosticoGrado)
        .where(models.DiagnosticoMencion.estudiante_id == estudiante_id)
        .order_by(models.DiagnosticoGrado.importado_en.desc())
    ).all()
    casos = crud.listar_casos_estudiante(db, estudiante_id)
    datos = diagnostico_pdf.generar_diagnostico_estudiante_pdf(
        db, estudiante, list(menciones), casos, elaborado_por=identidad.usuario.nombre
    )
    nombre = f"diagnostico_{estudiante.documento}_{dt.date.today().isoformat()}.pdf"
    return Response(
        content=datos, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )


@router.patch("/menciones/{mencion_id}", response_model=schemas.DiagnosticoMencionVista)
def vincular_mencion(
    mencion_id: int,
    datos: schemas.DiagnosticoVincular,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.vincular")),
    db: Session = Depends(get_db),
):
    if datos.estudiante_id is not None and db.get(models.Estudiante, datos.estudiante_id) is None:
        raise HTTPException(status_code=400, detail="El estudiante indicado no existe")
    m = crud.vincular_mencion(db, mencion_id, datos.estudiante_id, identidad.usuario.id)
    if m is None:
        raise HTTPException(status_code=404, detail="Mención no encontrada")
    return crud.mencion_a_vista(db, m)


# --- Casos de orientación ----------------------------------------------------


@router.get("/casos", response_model=list[schemas.CasoVista])
def listar_casos(
    sede_id: int | None = None, grado: int | None = None, curso: int | None = None,
    estado: str | None = None, tipo: str | None = None, estudiante_id: int | None = None,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.ver")),
    db: Session = Depends(get_db),
):
    casos = crud.listar_casos_filtrados(
        db, sede_id=sede_id, grado=grado, curso=curso, estado=estado, tipo=tipo, estudiante_id=estudiante_id
    )
    return [crud.caso_a_vista(c) for c in casos]


@router.post("/casos", response_model=schemas.CasoDetalle)
def crear_caso(
    datos: schemas.CasoCrear,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.observar")),
    db: Session = Depends(get_db),
):
    if datos.tipo not in crud.CASO_TIPOS:
        raise HTTPException(status_code=400, detail=f"Tipo de caso inválido: {datos.tipo!r}")
    if not datos.descripcion.strip():
        raise HTTPException(status_code=400, detail="La descripción no puede estar vacía.")
    if db.get(models.Estudiante, datos.estudiante_id) is None:
        raise HTTPException(status_code=400, detail="El estudiante indicado no existe")
    if datos.mencion_origen_id is not None and db.get(models.DiagnosticoMencion, datos.mencion_origen_id) is None:
        raise HTTPException(status_code=400, detail="La mención de origen no existe")
    c = crud.crear_caso(db, datos, identidad.usuario.id)
    return crud.caso_a_detalle(c)


def _obtener_caso(db: Session, caso_id: int) -> models.Caso:
    c = db.get(models.Caso, caso_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    return c


@router.get("/casos/{caso_id}", response_model=schemas.CasoDetalle)
def detalle_caso(
    caso_id: int,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.ver")),
    db: Session = Depends(get_db),
):
    return crud.caso_a_detalle(_obtener_caso(db, caso_id))


@router.patch("/casos/{caso_id}/estado", response_model=schemas.CasoDetalle)
def cambiar_estado_caso(
    caso_id: int,
    datos: schemas.CasoEstadoCambiar,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.observar")),
    db: Session = Depends(get_db),
):
    if datos.estado not in crud.CASO_ESTADOS:
        raise HTTPException(status_code=400, detail=f"Estado inválido: {datos.estado!r}")
    c = crud.cambiar_estado_caso(db, caso_id, datos.estado, identidad.usuario.id)
    if c is None:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    return crud.caso_a_detalle(c)


@router.post("/casos/{caso_id}/seguimientos", response_model=schemas.CasoDetalle)
def agregar_seguimiento(
    caso_id: int,
    datos: schemas.CasoSeguimientoCrear,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.observar")),
    db: Session = Depends(get_db),
):
    if not datos.situacion.strip():
        raise HTTPException(status_code=400, detail="La situación no puede estar vacía.")
    c = crud.agregar_seguimiento_caso(db, caso_id, datos, identidad.usuario.id)
    if c is None:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    return crud.caso_a_detalle(c)


@router.get("/casos/{caso_id}/pdf")
def pdf_caso(
    caso_id: int,
    identidad: auth.Identidad = Depends(rbac.requiere("diagnosticos.exportar")),
    db: Session = Depends(get_db),
):
    c = _obtener_caso(db, caso_id)
    datos = diagnostico_pdf.generar_informe_caso_pdf(db, c, elaborado_por=identidad.usuario.nombre)
    nombre = f"caso_{c.estudiante.documento}_{c.id}_{dt.date.today().isoformat()}.pdf"
    return Response(
        content=datos, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )
