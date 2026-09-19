import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import conciliacion, lista_estudiantes_pdf, rbac, schemas
from ..database import get_db

router = APIRouter(prefix="/api/reportes", tags=["reportes"])


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
