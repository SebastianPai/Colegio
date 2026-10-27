import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import conciliacion, crud, docentes_pdf, hallazgos_pdf, lista_asistencia_pdf, lista_estudiantes_pdf, models, presencia_pdf, rbac, schemas
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


def _grados_de_texto(grados: str) -> list[int]:
    try:
        lista = sorted({int(g) for g in grados.split(",") if g.strip()})
    except ValueError:
        raise HTTPException(status_code=400, detail="Grados no válidos (ej. grados=10,11).")
    if not lista or any(g < 0 or g > 11 for g in lista):
        raise HTTPException(status_code=400, detail="Escoge grados entre 0 (Transición) y 11 (Once).")
    return lista


@router.get("/docentes-por-grado")
def docentes_por_grado(
    grados: str,
    sede_id: int | None = None,
    anio_lectivo: int | None = None,
    _obs=Depends(rbac.observar("reportes.ver")),
    db: Session = Depends(get_db),
):
    """Docentes que dictan en esos grados (ej. grados=10,11), con materias y
    grupos: asignaciones del año + horario vigente."""
    return crud.docentes_por_grados(db, anio_lectivo or dt.date.today().year, _grados_de_texto(grados), sede_id)


@router.get("/docentes-por-grado/pdf")
def docentes_por_grado_pdf(
    grados: str,
    sede_id: int | None = None,
    anio_lectivo: int | None = None,
    _obs=Depends(rbac.observar("reportes.exportar")),
    db: Session = Depends(get_db),
):
    lista = _grados_de_texto(grados)
    sede = db.get(models.Sede, sede_id) if sede_id else None
    try:
        datos = docentes_pdf.generar_docentes_por_grado_pdf(
            db, lista, anio_lectivo or dt.date.today().year, sede_id=sede_id, sede_nombre=sede.nombre if sede else "",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    nombre_archivo = f"docentes_grados_{'_'.join(map(str, lista))}_{dt.date.today().isoformat()}.pdf"
    return Response(
        content=datos,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre_archivo}"'},
    )


@router.get("/lista-asistencia/grupos")
def grupos_lista_asistencia(
    sede_id: int,
    grupos: str,
    _obs=Depends(rbac.observar("reportes.ver")),
    db: Session = Depends(get_db),
):
    """Qué hojas van a salir con lo escrito (ej. "10, 11, 2, 4-2"), antes de
    generar el PDF: [{grado, curso, nombre, estudiantes}]."""
    try:
        hojas = lista_asistencia_pdf.grupos_a_imprimir(db, sede_id, grupos)
    except lista_asistencia_pdf.GrupoInvalido as e:
        raise HTTPException(status_code=400, detail=str(e))
    return [
        {"grado": h["grado"], "curso": h["curso"], "nombre": lista_asistencia_pdf.nombre_grupo(h["grado"], h["curso"]),
         "estudiantes": len(h["estudiantes"])}
        for h in hojas
    ]


@router.get("/lista-asistencia/pdf")
def lista_asistencia_pdf_endpoint(
    sede_id: int,
    grupos: str,
    mes: int,
    _obs=Depends(rbac.observar("reportes.exportar")),
    db: Session = Depends(get_db),
):
    """Listas de asistencia de varios grupos en un solo PDF: oficio
    horizontal, una hoja por grupo, para imprimir al 100 %."""
    try:
        datos, hojas = lista_asistencia_pdf.generar_listas_asistencia_pdf(db, sede_id, grupos, mes)
    except lista_asistencia_pdf.GrupoInvalido as e:
        raise HTTPException(status_code=400, detail=str(e))
    etiqueta = "_".join(f"{h['grado']}-{h['curso']}" if h["curso"] is not None else str(h["grado"]) for h in hojas[:8])
    nombre = f"Listas_asistencia_{etiqueta}{'_y_mas' if len(hojas) > 8 else ''}_{lista_asistencia_pdf.MESES[mes - 1].lower()}.pdf"
    return Response(content=datos, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nombre}"'})


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
