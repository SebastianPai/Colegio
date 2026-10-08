import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import conciliacion, crud, docentes_pdf, hallazgos_pdf, lista_estudiantes_pdf, presencia_pdf, rbac, schemas
from ..database import get_db

router = APIRouter(prefix="/api/reportes", tags=["reportes"])


@router.get("/docentes", response_model=list[schemas.DocenteReporte])
def listar_docentes_reporte(
    anio_lectivo: int | None = None,
    sede_id: int | None = None,
    _obs=Depends(rbac.observar("reportes.ver")),
    db: Session = Depends(get_db),
):
    return crud.listar_docentes_reporte(db, anio_lectivo or dt.date.today().year, sede_id=sede_id)


class ListaEstudiantesPdfSolicitud(BaseModel):
    ids: list[int]  # en el orden en que deben salir
    columnas: list[str]
    vista: str = "activos"  # activos | posibles | retirados
    sede_nombre: str = ""
    desde_grado: int = 0
    hasta_grado: int = 11
    grupos_txt: str = ""  # "Cuarto - Dos, Sexto - Cuatro" si se escogieron grupos
    incluye_posibles: bool = False
    incluye_retirados: bool = False
    cantidad: int | None = None  # cupo pedido (solo vista activos)
    completo: bool = False  # True = alcanzaron todos, el cupo no cortó la lista
    sin_grupo_excluidos: int = 0  # cuántos se dejaron fuera por no tener grupo


@router.post("/lista-estudiantes/pdf")
def lista_estudiantes_pdf_endpoint(
    solicitud: ListaEstudiantesPdfSolicitud,
    _obs=Depends(rbac.observar("reportes.exportar")),
    db: Session = Depends(get_db),
):
    try:
        datos = lista_estudiantes_pdf.generar_lista_pdf(
            db,
            solicitud.ids,
            solicitud.columnas,
            vista=solicitud.vista,
            sede_nombre=solicitud.sede_nombre,
            desde_grado=solicitud.desde_grado,
            hasta_grado=solicitud.hasta_grado,
            grupos_txt=solicitud.grupos_txt,
            incluye_posibles=solicitud.incluye_posibles,
            incluye_retirados=solicitud.incluye_retirados,
            cantidad=solicitud.cantidad,
            completo=solicitud.completo,
            sin_grupo_excluidos=solicitud.sin_grupo_excluidos,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    nombre_archivo = f"lista_estudiantes_{dt.date.today().isoformat()}.pdf"
    return Response(
        content=datos,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre_archivo}"'},
    )


class ListaDocentesPdfSolicitud(BaseModel):
    ids: list[int]  # en el orden en que deben salir
    columnas: list[str]
    anio_lectivo: int | None = None
    sede_nombre: str = ""
    solo_responsables_grupo: bool = False


@router.post("/lista-docentes/pdf")
def lista_docentes_pdf_endpoint(
    solicitud: ListaDocentesPdfSolicitud,
    _obs=Depends(rbac.observar("reportes.exportar")),
    db: Session = Depends(get_db),
):
    try:
        datos = docentes_pdf.generar_lista_docentes_pdf(
            db,
            solicitud.ids,
            solicitud.columnas,
            anio_lectivo=solicitud.anio_lectivo or dt.date.today().year,
            sede_nombre=solicitud.sede_nombre,
            solo_responsables_grupo=solicitud.solo_responsables_grupo,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    nombre_archivo = f"lista_docentes_{dt.date.today().isoformat()}.pdf"
    return Response(
        content=datos,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre_archivo}"'},
    )


class PresenciaPdfSolicitud(BaseModel):
    anio_lectivo: int | None = None
    periodo: int = 1
    sede_id: int | None = None
    grado: int | None = None
    sede_nombre: str = ""
    incluir_coincide: bool = False


@router.post("/conciliacion/presencia/pdf")
def presencia_pdf_endpoint(
    solicitud: PresenciaPdfSolicitud,
    _obs=Depends(rbac.observar("reportes.exportar")),
    db: Session = Depends(get_db),
):
    try:
        datos = presencia_pdf.generar_presencia_pdf(
            db,
            anio_lectivo=solicitud.anio_lectivo or dt.date.today().year,
            periodo=solicitud.periodo,
            sede_id=solicitud.sede_id,
            grado=solicitud.grado,
            sede_nombre=solicitud.sede_nombre,
            incluir_coincide=solicitud.incluir_coincide,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    nombre_archivo = f"presencia_simat_sapred_{dt.date.today().isoformat()}.pdf"
    return Response(
        content=datos,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre_archivo}"'},
    )


@router.get("/conciliacion", response_model=schemas.ConciliacionResultado)
def obtener_conciliacion(
    anio_lectivo: int | None = None,
    periodo: int = 1,
    sede_id: int | None = None,
    grado: int | None = None,
    _obs=Depends(rbac.observar("reportes.ver")),
    db: Session = Depends(get_db),
):
    return conciliacion.conciliar(
        db,
        anio_lectivo=anio_lectivo or dt.date.today().year,
        periodo=periodo,
        sede_id=sede_id,
        grado=grado,
    )


@router.get("/conciliacion/exportar")
def exportar_conciliacion(
    anio_lectivo: int | None = None,
    periodo: int = 1,
    sede_id: int | None = None,
    grado: int | None = None,
    _obs=Depends(rbac.observar("reportes.exportar")),
    db: Session = Depends(get_db),
):
    resultado = conciliacion.conciliar(
        db,
        anio_lectivo=anio_lectivo or dt.date.today().year,
        periodo=periodo,
        sede_id=sede_id,
        grado=grado,
    )
    datos = conciliacion.exportar_conciliacion_excel(resultado)
    nombre_archivo = f"conciliacion_simac_sapred_p{periodo}_{dt.date.today().isoformat()}.xlsx"
    return Response(
        content=datos,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


@router.get("/conciliacion/hallazgos", response_model=list[schemas.HallazgoConciliacion])
def listar_hallazgos_conciliacion(
    anio_lectivo: int | None = None,
    periodo: int | None = None,
    sede_id: int | None = None,
    grado: int | None = None,
    incluir_resueltos: bool = False,
    _obs=Depends(rbac.observar("reportes.ver")),
    db: Session = Depends(get_db),
):
    return conciliacion.listar_hallazgos(
        db, anio_lectivo=anio_lectivo, periodo=periodo, sede_id=sede_id, grado=grado,
        incluir_resueltos=incluir_resueltos,
    )


@router.post("/conciliacion/hallazgos/{hallazgo_id}/resolver", response_model=schemas.HallazgoConciliacion)
def resolver_hallazgo_conciliacion(
    hallazgo_id: int,
    datos: schemas.HallazgoConciliacionResolver,
    _obs=Depends(rbac.observar("reportes.exportar")),
    db: Session = Depends(get_db),
):
    hallazgo = conciliacion.resolver_hallazgo(db, hallazgo_id, datos.resuelto_por, datos.nota)
    if hallazgo is None:
        raise HTTPException(status_code=404, detail="Hallazgo no encontrado")
    return hallazgo


@router.post("/conciliacion/hallazgos/{hallazgo_id}/reabrir", response_model=schemas.HallazgoConciliacion)
def reabrir_hallazgo_conciliacion(
    hallazgo_id: int,
    _obs=Depends(rbac.observar("reportes.exportar")),
    db: Session = Depends(get_db),
):
    hallazgo = conciliacion.reabrir_hallazgo(db, hallazgo_id)
    if hallazgo is None:
        raise HTTPException(status_code=404, detail="Hallazgo no encontrado")
    return hallazgo


class HallazgosPdfSolicitud(BaseModel):
    ids: list[int]  # en el orden en que deben salir
    anio_lectivo: int
    periodo: int
    sede_nombre: str = ""
    incluir_resueltos: bool = False


@router.post("/conciliacion/hallazgos/pdf")
def hallazgos_pdf_endpoint(
    solicitud: HallazgosPdfSolicitud,
    _obs=Depends(rbac.observar("reportes.exportar")),
    db: Session = Depends(get_db),
):
    try:
        datos = hallazgos_pdf.generar_hallazgos_pdf(
            db,
            solicitud.ids,
            anio_lectivo=solicitud.anio_lectivo,
            periodo=solicitud.periodo,
            sede_nombre=solicitud.sede_nombre,
            incluir_resueltos=solicitud.incluir_resueltos,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    nombre_archivo = f"diferencias_grado_simat_sapred_{dt.date.today().isoformat()}.pdf"
    return Response(
        content=datos,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre_archivo}"'},
    )
