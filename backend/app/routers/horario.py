import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import fechas, horario, rbac, reporte_horario, reporte_horas_libres, schemas
from ..database import get_db

router = APIRouter(prefix="/api/horario", tags=["horario"])


def _anio(anio_lectivo: int | None) -> int:
    return anio_lectivo or fechas.anio_lectivo_actual()


def _fecha(fecha: dt.date | None) -> dt.date:
    return fecha or fechas.hoy_colombia()


# --- Consulta -------------------------------------------------------------


@router.get("/bloques", response_model=list[schemas.BloqueHorario])
def listar_bloques(
    anio_lectivo: int | None = None,
    docente_id: int | None = None,
    grado: int | None = None,
    curso: int | None = None,
    dia: int | None = None,
    area_id: int | None = None,
    _obs=Depends(rbac.observar("horario.ver")),
    db: Session = Depends(get_db),
):
    return horario.listar_bloques(
        db, _anio(anio_lectivo), docente_id=docente_id, grado=grado, curso=curso, dia=dia, area_id=area_id
    )


@router.get("/docente/{docente_id}", response_model=schemas.HorarioDocenteSemana)
def horario_de_docente(
    docente_id: int,
    anio_lectivo: int | None = None,
    _obs=Depends(rbac.observar("horario.ver")),
    db: Session = Depends(get_db),
):
    try:
        return horario.horario_docente(db, docente_id, _anio(anio_lectivo))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/grupo", response_model=schemas.HorarioGrupo)
def horario_de_grupo(
    grado: int,
    curso: int | None = None,
    anio_lectivo: int | None = None,
    dia: int | None = None,
    _obs=Depends(rbac.observar("horario.ver")),
    db: Session = Depends(get_db),
):
    return horario.horario_grupo(db, grado, curso, _anio(anio_lectivo), dia=dia)


@router.get("/dia/{dia}", response_model=list[schemas.BloqueHorario])
def horario_de_dia(
    dia: int,
    anio_lectivo: int | None = None,
    _obs=Depends(rbac.observar("horario.ver")),
    db: Session = Depends(get_db),
):
    return horario.listar_bloques(db, _anio(anio_lectivo), dia=dia)


@router.get("/reporte.docx")
def reporte_horario_word(
    b: list[str] = Query(default=[], description="Bloques: DIA-GRADO-HORAS, p. ej. ju-11-2-3-4"),
    anio_lectivo: int | None = None,
    fecha: dt.date | None = None,
    _obs=Depends(rbac.observar("horario.exportar")),
    db: Session = Depends(get_db),
):
    """Reporte de horario en Word con membrete oficial: por cada bloque
    (día + grado + horas), una tabla por división activa del grado en la
    Sede #01 con Hora · Docente · Materia."""
    try:
        contenido = reporte_horario.generar_reporte_horario_docx(
            db, b, _anio(anio_lectivo), _fecha(fecha)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    nombre = f"reporte_horario_{dt.date.today().isoformat()}.docx"
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


# --- Abrir hueco / asignar una clase nueva --------------------------------


@router.get("/horas-libres", response_model=schemas.HorasLibresReporte)
def horas_libres(
    anio_lectivo: int | None = None,
    _obs=Depends(rbac.observar("horario.ver")),
    db: Session = Depends(get_db),
):
    """Cuadro general: cada docente, hora por hora, qué dicta o si está libre."""
    return reporte_horas_libres.calcular(db, anio_lectivo or fechas.anio_lectivo_actual())


@router.get("/horas-libres.pdf")
def horas_libres_pdf(
    anio_lectivo: int | None = None,
    dias: str = "",  # "1,2,3" — vacío = toda la semana
    solo_libres: bool = False,
    formato: str = "cuadro",  # cuadro | por_hora
    _obs=Depends(rbac.observar("horario.ver")),
    db: Session = Depends(get_db),
):
    lista_dias = [int(d) for d in dias.split(",") if d.strip().isdigit()] or None
    try:
        datos = reporte_horas_libres.generar_pdf(
            db,
            anio_lectivo or fechas.anio_lectivo_actual(),
            dias=lista_dias,
            solo_libres=solo_libres,
            formato=formato,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    nombre = f"horas_libres_docentes_{dt.date.today().isoformat()}.pdf"
    return Response(
        content=datos,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )


@router.get("/huecos", response_model=schemas.HuecosRespuesta)
def huecos_para_asignar(
    docente_id: int,
    grado: int,
    curso: int | None = None,
    area_id: int | None = None,
    horas: int = 1,
    anio_lectivo: int | None = None,
    _obs=Depends(rbac.observar("horario.ver")),
    db: Session = Depends(get_db),
):
    try:
        return horario.huecos_para_asignar(
            db, docente_id, grado, curso, area_id, _anio(anio_lectivo), horas=horas
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/bloques", response_model=list[schemas.BloqueHorario])
def crear_bloque_horario(
    datos: schemas.CrearBloqueHorario,
    _obs=Depends(rbac.observar("horario.gestionar")),
    db: Session = Depends(get_db),
):
    try:
        return horario.crear_bloque_horario(db, datos)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/bloques/{bloque_id}")
def eliminar_bloque_horario(
    bloque_id: int, _obs=Depends(rbac.observar("horario.gestionar")), db: Session = Depends(get_db)
):
    if not horario.eliminar_bloque_horario(db, bloque_id):
        raise HTTPException(status_code=404, detail="Bloque no encontrado")
    return {"eliminado": True}


# --- Disponibilidad ----------------------------------------------------------


@router.get("/ahora")
def franja_ahora(_obs=Depends(rbac.observar("horario.ver"))):
    return horario.franja_actual()


@router.get("/libres", response_model=list[schemas.DocenteLibre])
def libres(
    dia: int | None = None,
    hora: int | None = None,
    hora_fin: int | None = None,  # rango: libres en TODAS las horas [hora..hora_fin]
    fecha: dt.date | None = None,
    anio_lectivo: int | None = None,
    _obs=Depends(rbac.observar("horario.ver")),
    db: Session = Depends(get_db),
):
    fecha = _fecha(fecha)
    if dia is None or hora is None:
        fr = horario.franja_actual()
        if fr["estado"] != "en_franja":
            return []
        dia, hora = fr["dia"], fr["hora"]
    return horario.docentes_libres(db, dia, hora, fecha, _anio(anio_lectivo), hora_fin=hora_fin)


@router.get("/estado-docentes", response_model=list[schemas.EstadoDocente])
def estado_docentes(
    fecha: dt.date | None = None, _obs=Depends(rbac.observar("horario.ver")), db: Session = Depends(get_db)
):
    return horario.estado_docentes(db, _fecha(fecha))


@router.get("/hoy", response_model=schemas.PanelHoy)
def panel_hoy(
    fecha: dt.date | None = None, _obs=Depends(rbac.observar("horario.ver")), db: Session = Depends(get_db)
):
    return horario.panel_hoy(db, _fecha(fecha))


# --- Conflictos (dos docentes para el mismo grupo+hora) -----------------


@router.get("/conflictos", response_model=list[schemas.ConflictoHorario])
def listar_conflictos(
    anio_lectivo: int | None = None,
    _obs=Depends(rbac.observar("horario.ver")),
    db: Session = Depends(get_db),
):
    return horario.conflictos_horario(db, _anio(anio_lectivo))


@router.post("/conflictos/resolver")
def resolver_conflicto(
    datos: schemas.ResolverConflicto,
    _obs=Depends(rbac.observar("horario.gestionar")),
    db: Session = Depends(get_db),
):
    try:
        return horario.resolver_conflicto(db, datos)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


# --- Ausencias -------------------------------------------------------------


@router.post("/ausencias", response_model=schemas.Ausencia)
def registrar_ausencia(
    datos: schemas.AusenciaCrear,
    _obs=Depends(rbac.observar("horario.gestionar")),
    db: Session = Depends(get_db),
):
    return horario.registrar_ausencia(db, datos)


@router.get("/ausencias", response_model=list[schemas.Ausencia])
def listar_ausencias(
    fecha: dt.date | None = None, _obs=Depends(rbac.observar("horario.ver")), db: Session = Depends(get_db)
):
    return horario.listar_ausencias(db, _fecha(fecha))


@router.delete("/ausencias/{ausencia_id}")
def eliminar_ausencia(
    ausencia_id: int, _obs=Depends(rbac.observar("horario.gestionar")), db: Session = Depends(get_db)
):
    if not horario.eliminar_ausencia(db, ausencia_id):
        raise HTTPException(status_code=404, detail="Ausencia no encontrada")
    return {"eliminada": True}


# --- Reemplazos -----------------------------------------------------------


@router.get("/reemplazos/candidatos", response_model=schemas.RespuestaCandidatos)
def candidatos_reemplazo(
    bloque_id: int,
    fecha: dt.date | None = None,
    _obs=Depends(rbac.observar("horario.ver")),
    db: Session = Depends(get_db),
):
    try:
        return horario.candidatos_reemplazo(db, bloque_id, _fecha(fecha))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/reemplazos", response_model=list[schemas.Reemplazo])
def listar_reemplazos(
    fecha: dt.date | None = None, _obs=Depends(rbac.observar("horario.ver")), db: Session = Depends(get_db)
):
    return horario.listar_reemplazos(db, _fecha(fecha))


@router.post("/reemplazos", response_model=schemas.Reemplazo)
def asignar_reemplazo(
    datos: schemas.ReemplazoAsignar,
    _obs=Depends(rbac.observar("horario.gestionar")),
    db: Session = Depends(get_db),
):
    try:
        return horario.asignar_reemplazo(db, datos)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.patch("/reemplazos/{reemplazo_id}", response_model=schemas.Reemplazo)
def actualizar_reemplazo(
    reemplazo_id: int,
    datos: schemas.ReemplazoActualizar,
    _obs=Depends(rbac.observar("horario.gestionar")),
    db: Session = Depends(get_db),
):
    try:
        return horario.actualizar_reemplazo(db, reemplazo_id, datos)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/reemplazos/{reemplazo_id}")
def eliminar_reemplazo(
    reemplazo_id: int, _obs=Depends(rbac.observar("horario.gestionar")), db: Session = Depends(get_db)
):
    if not horario.eliminar_reemplazo(db, reemplazo_id):
        raise HTTPException(status_code=404, detail="Reemplazo no encontrado")
    return {"eliminado": True}


# --- Búsqueda rápida -------------------------------------------------------


@router.get("/buscar", response_model=schemas.ResultadoBusqueda)
def buscar(
    q: str,
    anio_lectivo: int | None = None,
    _obs=Depends(rbac.observar("horario.ver")),
    db: Session = Depends(get_db),
):
    return horario.buscar(db, q, _anio(anio_lectivo))
