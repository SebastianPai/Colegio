import datetime as dt

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from .. import (
    auditoria_continuidad,
    auth_servicio,
    crud,
    generacion_boletines,
    grilla_sapred,
    rbac,
    reporte_notas,
    sapred_auditoria,
    schemas,
)
from ..database import get_db

router = APIRouter(prefix="/api", tags=["academico"])


@router.get("/docentes", response_model=list[schemas.Docente])
def listar_docentes(_obs=Depends(rbac.observar("docentes.ver")), db: Session = Depends(get_db)):
    return crud.listar_docentes(db)


@router.get("/grupos", response_model=list[schemas.GrupoAcademico])
def listar_grupos(
    anio_lectivo: int | None = None,
    periodo: int = 1,
    _obs=Depends(rbac.observar("grupos.ver")),
    db: Session = Depends(get_db),
):
    return crud.listar_grupos_academicos(
        db, anio_lectivo=anio_lectivo or dt.date.today().year, periodo=periodo
    )


@router.post("/asignaciones")
def asignar_docente(
    datos: schemas.AsignacionDocenteCrear,
    _obs=Depends(rbac.observar("grupos.gestionar")),
    db: Session = Depends(get_db),
):
    asignacion = crud.asignar_docente(db, datos)
    if asignacion is None:
        return {"asignado": False}
    return {"asignado": True, "docente_id": asignacion.docente_id}


@router.post("/revisiones-boletin", response_model=schemas.RevisionBoletin)
def guardar_revision(
    datos: schemas.RevisionBoletinGuardar,
    _obs=Depends(rbac.observar("boletines.gestionar")),
    db: Session = Depends(get_db),
):
    return crud.guardar_revision_boletin(db, datos)


@router.get("/areas", response_model=list[schemas.AreaConGrados])
def listar_areas(_obs=Depends(rbac.observar("catalogos.ver")), db: Session = Depends(get_db)):
    return crud.listar_areas(db)


@router.get("/boletines/pendientes", response_model=list[schemas.PendienteConGrupo])
def listar_pendientes(
    anio_lectivo: int | None = None,
    periodo: int | None = None,
    sede_id: int | None = None,
    grado: int | None = None,
    curso: int | None = None,
    docente_id: int | None = None,
    area_id: int | None = None,
    solo_no_resueltos: bool = True,
    solo_ietaba: bool = True,
    incluir_posibles_retirados: bool = False,
    _obs=Depends(rbac.observar("boletines.ver")),
    db: Session = Depends(get_db),
):
    return crud.listar_pendientes(
        db,
        anio_lectivo=anio_lectivo or dt.date.today().year,
        periodo=periodo,
        sede_id=sede_id,
        grado=grado,
        curso=curso,
        docente_id=docente_id,
        area_id=area_id,
        solo_no_resueltos=solo_no_resueltos,
        solo_ietaba=solo_ietaba,
        incluir_posibles_retirados=incluir_posibles_retirados,
    )


@router.get("/boletines/por-docente", response_model=schemas.PendientesPorDocente)
def pendientes_por_docente(
    anio_lectivo: int | None = None,
    periodo: int | None = None,
    solo_ietaba: bool = True,
    _obs=Depends(rbac.observar("boletines.ver")),
    db: Session = Depends(get_db),
):
    return crud.pendientes_por_docente(
        db,
        anio_lectivo=anio_lectivo or dt.date.today().year,
        periodo=periodo,
        solo_ietaba=solo_ietaba,
    )


@router.get("/boletines/por-docente/reporte", response_model=schemas.ReporteFaltantes)
def reporte_faltantes_por_docente(
    anio_lectivo: int | None = None,
    periodo: int | None = None,
    docente_id: int | None = None,
    solo_ietaba: bool = True,
    _obs=Depends(rbac.observar("boletines.ver")),
    db: Session = Depends(get_db),
):
    return crud.reporte_faltantes_por_docente(
        db,
        anio_lectivo=anio_lectivo or dt.date.today().year,
        periodo=periodo,
        docente_id=docente_id,
        solo_ietaba=solo_ietaba,
    )


@router.get("/boletines/pendientes/exportar")
def exportar_pendientes(
    anio_lectivo: int | None = None,
    periodo: int | None = None,
    sede_id: int | None = None,
    grado: int | None = None,
    curso: int | None = None,
    docente_id: int | None = None,
    area_id: int | None = None,
    solo_no_resueltos: bool = True,
    solo_ietaba: bool = True,
    ids: str | None = None,
    _obs=Depends(rbac.observar("boletines.exportar")),
    db: Session = Depends(get_db),
):
    lista_ids = [int(i) for i in ids.split(",") if i.strip()] if ids else None
    datos = crud.exportar_pendientes_excel(
        db,
        anio_lectivo=anio_lectivo or dt.date.today().year,
        periodo=periodo, sede_id=sede_id, grado=grado, curso=curso, docente_id=docente_id, area_id=area_id,
        solo_no_resueltos=solo_no_resueltos, solo_ietaba=solo_ietaba, ids=lista_ids,
    )
    nombre_archivo = f"pendientes_boletines_{dt.date.today().isoformat()}.xlsx"
    return Response(
        content=datos,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


@router.post("/boletines/pendientes", response_model=schemas.Pendiente)
def crear_pendiente(
    datos: schemas.PendienteCrear,
    _obs=Depends(rbac.observar("boletines.gestionar")),
    db: Session = Depends(get_db),
):
    return crud.crear_pendiente(db, datos)


@router.patch("/boletines/pendientes/{pendiente_id}", response_model=schemas.Pendiente)
def actualizar_pendiente(
    pendiente_id: int,
    cambios: schemas.PendienteActualizar,
    _obs=Depends(rbac.observar("boletines.gestionar")),
    db: Session = Depends(get_db),
):
    pendiente = crud.actualizar_pendiente(db, pendiente_id, cambios)
    if pendiente is None:
        raise HTTPException(status_code=404, detail="Pendiente no encontrado")
    return pendiente


@router.post("/boletines/pendientes/resolver-lote")
def resolver_pendientes_lote(
    datos: schemas.PendientesLote,
    _obs=Depends(rbac.observar("boletines.gestionar")),
    db: Session = Depends(get_db),
):
    return {"actualizados": crud.resolver_pendientes_lote(db, datos.ids, datos.resuelto)}


@router.post("/boletines/pendientes/depurar-obsoletos")
def depurar_pendientes_obsoletos(
    anio_lectivo: int | None = None,
    periodo: int | None = None,
    _obs=Depends(rbac.observar("boletines.gestionar")),
    db: Session = Depends(get_db),
):
    """Cierra los pendientes que ya no aplican porque el dato SÍ está cargado
    en SAPRED (nota/concepto/observación por estudiante o de todo el grupo).
    Deja el reporte para los docentes limpio sin tener que reimportar."""
    n = crud.depurar_pendientes_obsoletos(db, anio_lectivo or dt.date.today().year, periodo)
    return {"cerrados": n}


@router.delete("/boletines/pendientes/{pendiente_id}")
def eliminar_pendiente(
    pendiente_id: int, _obs=Depends(rbac.observar("boletines.gestionar")), db: Session = Depends(get_db)
):
    if not crud.eliminar_pendiente(db, pendiente_id):
        raise HTTPException(status_code=404, detail="Pendiente no encontrado")
    return {"eliminado": True}


@router.post("/boletines/importar-sapred", response_model=schemas.ImportarSapredResultado)
async def importar_sapred(
    archivo: UploadFile = File(...),
    _obs=Depends(rbac.observar("sapred.importar")),
    db: Session = Depends(get_db),
):
    if not archivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Debe ser un PDF (el reporte de SAPRED exportado como PDF)")
    datos = await archivo.read()
    try:
        resultado = crud.importar_pdf_sapred(db, datos)
    except Exception as e:
        crud.registrar_importacion_pdf_sapred(db, archivo.filename, None, error=str(e))
        raise HTTPException(status_code=400, detail=f"No se pudo leer el PDF: {e}")
    crud.registrar_importacion_pdf_sapred(db, archivo.filename, resultado)
    return resultado


@router.get("/boletines/importaciones-sapred-pdf", response_model=list[schemas.ImportacionSapredPdfHistorial])
def listar_importaciones_pdf_sapred(
    limite: int = 20, _obs=Depends(rbac.observar("boletines.ver")), db: Session = Depends(get_db)
):
    return crud.listar_importaciones_pdf_sapred(db, limite=limite)


@router.post("/boletines/importar-sapred-bloques", response_model=schemas.ImportarSapredResultado)
def importar_sapred_bloques(
    bloques: list[schemas.SapredBloqueEntrada],
    _servicio: None = Depends(auth_servicio.exigir_token_servicio),
    db: Session = Depends(get_db),
):
    """Igual que /importar-sapred pero recibe los bloques ya extraídos
    (ej. desde el reporte HTML en vivo, vía automatización de navegador) en
    vez de un PDF — reutiliza la misma lógica de importación por bloque.

    Fase 4.1 — endpoint INTERNO: solo lo llaman los scripts de SAPRED (sin
    sesión de navegador posible), exige identidad de servicio."""
    resultados = [crud.importar_bloque_sapred(db, b.model_dump()) for b in bloques]
    return schemas.ImportarSapredResultado(
        bloques=resultados,
        total_pendientes_creados=sum(r.pendientes_creados for r in resultados),
        total_pendientes_resueltos_auto=sum(r.pendientes_resueltos_auto for r in resultados),
        total_estudiantes_no_encontrados=len({n for r in resultados for n in r.estudiantes_no_encontrados}),
    )


@router.post("/boletines/importar-boletin", response_model=schemas.ImportarBoletinResultado)
async def importar_boletin(
    archivo: UploadFile = File(...),
    _obs=Depends(rbac.observar("sapred.importar")),
    db: Session = Depends(get_db),
):
    if not archivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Debe ser un PDF (el reporte 'Boletín informativo' de SAPRED exportado como PDF)")
    datos = await archivo.read()
    try:
        resultado = crud.importar_pdf_boletin(db, datos)
    except Exception as e:
        crud.registrar_importacion_pdf_boletin(db, archivo.filename, None, error=str(e))
        raise HTTPException(status_code=400, detail=f"No se pudo leer el PDF: {e}")
    crud.registrar_importacion_pdf_boletin(db, archivo.filename, resultado)
    return resultado


@router.post("/boletines/importar-boletin-bloques", response_model=schemas.ImportarBoletinResultado)
def importar_boletin_bloques(
    bloques: list[schemas.BoletinBloqueEntrada],
    _servicio: None = Depends(auth_servicio.exigir_token_servicio),
    db: Session = Depends(get_db),
):
    """Igual que /importar-boletin pero recibe los bloques ya extraídos (ej.
    desde el reporte HTML en vivo, vía automatización de navegador).

    Fase 4.1 — endpoint INTERNO: solo lo llaman los scripts de SAPRED (sin
    sesión de navegador posible), exige identidad de servicio."""
    resultados = [crud.importar_bloque_boletin(db, b.model_dump()) for b in bloques]
    return schemas.ImportarBoletinResultado(
        bloques=resultados,
        total_conceptos_pendientes=sum(r.conceptos_pendientes_creados for r in resultados),
        total_notas_pendientes=sum(r.notas_pendientes_creados for r in resultados),
        total_observaciones_pendientes=sum(r.observaciones_pendientes_creadas for r in resultados),
        total_pendientes_resueltos_auto=sum(r.pendientes_resueltos_auto for r in resultados),
        total_estudiantes_no_encontrados=len({n for r in resultados for n in r.estudiantes_no_encontrados}),
    )


@router.get("/boletines/importaciones-boletin-pdf", response_model=list[schemas.ImportacionBoletinPdfHistorial])
def listar_importaciones_pdf_boletin(
    limite: int = 20, _obs=Depends(rbac.observar("boletines.ver")), db: Session = Depends(get_db)
):
    return crud.listar_importaciones_pdf_boletin(db, limite=limite)


@router.post("/boletines/auditoria-sapred", response_model=schemas.AuditoriaSapred)
def iniciar_auditoria_sapred(
    datos: schemas.AuditoriaSapredCrear,
    tareas: BackgroundTasks,
    _obs=Depends(rbac.observar("sapred.ejecutar")),
    db: Session = Depends(get_db),
):
    """Arranca una auditoría contra SAPRED: crea el registro de progreso y
    lanza el navegador en segundo plano (la persona todavía tiene que
    iniciar sesión a mano en la ventana que se abre)."""
    en_curso = sapred_auditoria.hay_auditoria_en_curso(db)
    if en_curso is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Ya hay una auditoría en curso (#{en_curso.id}, estado: {en_curso.estado}). Espera a que termine.",
        )
    auditoria = sapred_auditoria.crear_auditoria(db, datos)
    # Las credenciales (si las hay) NO se guardan: solo se pasan al
    # subproceso en memoria para esta corrida.
    credenciales = (
        {"usuario": datos.usuario, "clave": datos.clave}
        if (datos.usuario and datos.clave)
        else None
    )
    tareas.add_task(sapred_auditoria.lanzar_proceso, auditoria, credenciales)
    return sapred_auditoria.a_schema(auditoria)


@router.get("/boletines/auditoria-sapred", response_model=list[schemas.AuditoriaSapred])
def listar_auditorias_sapred(
    limite: int = 20,
    incluir_generacion: bool = False,
    _obs=Depends(rbac.observar("boletines.ver")),
    db: Session = Depends(get_db),
):
    # Las corridas de 'boletin_pdf' (generar el boletín general de cada sede)
    # tienen su propio panel/historial; por defecto no ensucian el de la
    # auditoría de notas.
    excluir = None if incluir_generacion else {"boletin_pdf"}
    return [
        sapred_auditoria.a_schema(a)
        for a in sapred_auditoria.listar_auditorias(db, limite=limite, excluir_tipos=excluir)
    ]


@router.get("/boletines/auditoria-sapred/{auditoria_id}", response_model=schemas.AuditoriaSapred)
def obtener_auditoria_sapred(
    auditoria_id: int, _obs=Depends(rbac.observar("boletines.ver")), db: Session = Depends(get_db)
):
    auditoria = sapred_auditoria.obtener_auditoria(db, auditoria_id)
    if auditoria is None:
        raise HTTPException(status_code=404, detail="Auditoría no encontrada")
    return sapred_auditoria.a_schema(auditoria)


@router.post(
    "/boletines/auditoria-sapred/{auditoria_id}/reintentar",
    response_model=schemas.AuditoriaSapred,
)
def reintentar_auditoria_sapred(
    auditoria_id: int,
    tareas: BackgroundTasks,
    datos: schemas.ReintentoAuditoriaSapred | None = None,
    _obs=Depends(rbac.observar("sapred.ejecutar")),
    db: Session = Depends(get_db),
):
    """Crea y lanza una auditoría nueva acotada SOLO a las sedes/grados que en
    la corrida `auditoria_id` quedaron en advertencia o error."""
    fuente = sapred_auditoria.obtener_auditoria(db, auditoria_id)
    if fuente is None:
        raise HTTPException(status_code=404, detail="Auditoría no encontrada")
    if fuente.estado not in sapred_auditoria.ESTADOS_TERMINALES:
        raise HTTPException(status_code=409, detail="Esa auditoría todavía no ha terminado.")

    try:
        scope = sapred_auditoria.scope_reintento(db, fuente)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if scope is None:
        raise HTTPException(
            status_code=400,
            detail="Esa auditoría no dejó sedes ni grados fallidos: no hay nada que reintentar.",
        )

    en_curso = sapred_auditoria.hay_auditoria_en_curso(db)
    if en_curso is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Ya hay una auditoría en curso (#{en_curso.id}, estado: {en_curso.estado}). Espera a que termine.",
        )

    auditoria = sapred_auditoria.crear_auditoria(
        db,
        schemas.AuditoriaSapredCrear(
            anio_lectivo=scope["anio_lectivo"],
            periodo=scope["periodo"],
            grado=scope["grado"],
            sede_ids=scope["sede_ids"],
            tipo=scope["tipo"],
        ),
    )
    credenciales = (
        {"usuario": datos.usuario, "clave": datos.clave}
        if (datos and datos.usuario and datos.clave)
        else None
    )
    tareas.add_task(sapred_auditoria.lanzar_proceso, auditoria, credenciales)
    return sapred_auditoria.a_schema(auditoria)


@router.post("/boletines/auditoria-sapred/{auditoria_id}/cancelar", response_model=schemas.AuditoriaSapred)
def cancelar_auditoria_sapred(
    auditoria_id: int, _obs=Depends(rbac.observar("sapred.ejecutar")), db: Session = Depends(get_db)
):
    """Marca una corrida trabada como terminada, para poder empezar otra."""
    auditoria = sapred_auditoria.obtener_auditoria(db, auditoria_id)
    if auditoria is None:
        raise HTTPException(status_code=404, detail="Corrida no encontrada")
    if auditoria.estado in sapred_auditoria.ESTADOS_TERMINALES:
        return sapred_auditoria.a_schema(auditoria)
    return sapred_auditoria.a_schema(sapred_auditoria.cancelar_auditoria(db, auditoria))


@router.post("/boletines/auditoria-sapred/{auditoria_id}/progreso", response_model=schemas.AuditoriaSapred)
def reportar_progreso_auditoria_sapred(
    auditoria_id: int,
    datos: schemas.AuditoriaSapredProgreso,
    _servicio: None = Depends(auth_servicio.exigir_token_servicio),
    db: Session = Depends(get_db),
):
    """Endpoint INTERNO (Fase 4.1: exige identidad de servicio): lo llama el
    propio proceso de Playwright para reportar su avance. No lo usa la
    interfaz."""
    auditoria = sapred_auditoria.actualizar_progreso(db, auditoria_id, datos)
    if auditoria is None:
        raise HTTPException(status_code=404, detail="Auditoría no encontrada")
    return sapred_auditoria.a_schema(auditoria)


# --- Generar el boletín general (PDF) de cada sede ------------------------
# Reutiliza AuditoriaSapred (tipo='boletin_pdf') para el progreso, el
# historial y el "reintentar solo lo que falló". No importa nada: solo deja
# un PDF por sede en disco, ordenado por grado.


@router.post("/boletines/generar-pdf", response_model=schemas.AuditoriaSapred)
def iniciar_generacion_boletines(
    datos: schemas.AuditoriaSapredCrear,
    tareas: BackgroundTasks,
    _obs=Depends(rbac.observar("sapred.ejecutar")),
    db: Session = Depends(get_db),
):
    """Arranca la generación del boletín general por sede: abre SAPRED, genera
    el boletín de cada grado de cada sede seleccionada (con 'Mostrar Sede' e
    'Incluir Puesto' activados en Opciones de impresión) y los une en un PDF
    por sede."""
    en_curso = sapred_auditoria.hay_auditoria_en_curso(db)
    if en_curso is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Ya hay un proceso de SAPRED en curso (#{en_curso.id}, estado: {en_curso.estado}). Espera a que termine.",
        )
    datos.tipo = "boletin_pdf"
    auditoria = sapred_auditoria.crear_auditoria(db, datos)
    credenciales = (
        {"usuario": datos.usuario, "clave": datos.clave}
        if (datos.usuario and datos.clave)
        else None
    )
    tareas.add_task(sapred_auditoria.lanzar_proceso, auditoria, credenciales)
    return sapred_auditoria.a_schema(auditoria)


@router.get("/boletines/generar-pdf", response_model=list[schemas.AuditoriaSapred])
def listar_generaciones_boletines(
    limite: int = 20, _obs=Depends(rbac.observar("boletines.ver")), db: Session = Depends(get_db)
):
    return [
        sapred_auditoria.a_schema(a)
        for a in sapred_auditoria.listar_auditorias(db, limite=limite, tipos={"boletin_pdf"})
    ]


@router.post(
    "/boletines/generar-pdf/{auditoria_id}/ensamblar-sede",
    response_model=schemas.EnsamblarBoletinSedeResultado,
)
def ensamblar_sede_boletines(
    auditoria_id: int,
    datos: schemas.EnsamblarBoletinSede,
    _servicio: None = Depends(auth_servicio.exigir_token_servicio),
    db: Session = Depends(get_db),
):
    """Endpoint INTERNO (Fase 4.1: exige identidad de servicio): lo llama el
    proceso de Playwright cuando ya generó todos los PDF por grado de una
    sede. Los une en orden de grado y devuelve el nombre del archivo final."""
    auditoria = sapred_auditoria.obtener_auditoria(db, auditoria_id)
    if auditoria is None:
        raise HTTPException(status_code=404, detail="Corrida no encontrada")
    try:
        return generacion_boletines.ensamblar_sede(auditoria, datos)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/boletines/unir-pdfs")
def unir_pdfs_boletines(
    datos: schemas.UnirPdfs, _servicio: None = Depends(auth_servicio.exigir_token_servicio)
):
    """Endpoint INTERNO (Fase 4.1: exige identidad de servicio): lo usa la
    captura manual del boletín para unir los PDF de una sede en uno solo,
    ordenado."""
    try:
        return {"n_paginas": generacion_boletines.unir_pdfs(datos.archivos, datos.salida)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/boletines/separar-por-seccion", response_model=schemas.SepararPorSeccionResultado)
def separar_boletin_por_seccion(
    datos: schemas.SepararPorSeccion, _servicio: None = Depends(auth_servicio.exigir_token_servicio)
):
    """Endpoint INTERNO (Fase 4.1: exige identidad de servicio): divide el
    PDF de un grado (generado con 'todas las secciones') en un PDF por
    sección, dentro de una carpeta (p. ej. '4/' con '4-1.pdf', '4-2.pdf'...).
    Dinámico: sirve para cualquier sede/grado."""
    try:
        return generacion_boletines.separar_por_seccion(datos)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/boletines/generar-pdf/{auditoria_id}/archivo")
def descargar_boletin_sede(
    auditoria_id: int,
    nombre: str,
    _obs=Depends(rbac.observar("boletines.ver")),
    db: Session = Depends(get_db),
):
    auditoria = sapred_auditoria.obtener_auditoria(db, auditoria_id)
    if auditoria is None or not auditoria.carpeta_salida:
        raise HTTPException(status_code=404, detail="Corrida no encontrada")
    try:
        ruta = generacion_boletines.ruta_pdf_sede(auditoria.carpeta_salida, nombre)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ruta.exists():
        raise HTTPException(status_code=404, detail="El archivo ya no está en el disco")
    return FileResponse(ruta, media_type="application/pdf", filename=nombre)


@router.get("/boletines/resumen", response_model=schemas.ResumenBoletines)
def resumen_boletines(
    anio_lectivo: int | None = None,
    periodo: int = 1,
    solo_ietaba: bool = True,
    _obs=Depends(rbac.observar("boletines.ver")),
    db: Session = Depends(get_db),
):
    return crud.resumen_boletines(
        db, anio_lectivo=anio_lectivo or dt.date.today().year, periodo=periodo, solo_ietaba=solo_ietaba
    )


@router.get("/boletines/continuidad", response_model=schemas.ResumenContinuidad)
def obtener_continuidad_academica(
    sede_id: int,
    anio_lectivo: int | None = None,
    _obs=Depends(rbac.observar("boletines.ver")),
    db: Session = Depends(get_db),
):
    try:
        return auditoria_continuidad.auditoria_continuidad(
            db, sede_id=sede_id, anio_lectivo=anio_lectivo or dt.date.today().year
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/boletines/grilla", response_model=list[schemas.GrillaGrupo])
def obtener_grilla_notas(
    sede_id: int,
    grado: int,
    periodo: int,
    curso: int | None = None,
    anio_lectivo: int | None = None,
    _obs=Depends(rbac.observar("boletines.ver")),
    db: Session = Depends(get_db),
):
    try:
        return grilla_sapred.grilla_notas(
            db,
            sede_id=sede_id,
            grado=grado,
            periodo=periodo,
            curso=curso,
            anio_lectivo=anio_lectivo or dt.date.today().year,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/boletines/reporte-notas", response_model=schemas.ReporteNotas)
def obtener_reporte_notas(
    periodo: int,
    anio_lectivo: int | None = None,
    sede_id: int | None = None,
    grado: int | None = None,
    umbral_bajo: float = 3.0,
    umbral_alto: float = 4.5,
    riesgo_minimo: int = 2,
    _obs=Depends(rbac.observar("boletines.ver")),
    db: Session = Depends(get_db),
):
    return reporte_notas.reporte_notas(
        db, periodo=periodo, anio_lectivo=anio_lectivo or dt.date.today().year,
        sede_id=sede_id, grado=grado, umbral_bajo=umbral_bajo, umbral_alto=umbral_alto,
        riesgo_minimo=riesgo_minimo,
    )


@router.get("/boletines/reporte-notas/exportar")
def exportar_reporte_notas(
    periodo: int,
    anio_lectivo: int | None = None,
    sede_id: int | None = None,
    grado: int | None = None,
    umbral_bajo: float = 3.0,
    umbral_alto: float = 4.5,
    riesgo_minimo: int = 2,
    _obs=Depends(rbac.observar("boletines.exportar")),
    db: Session = Depends(get_db),
):
    reporte = reporte_notas.reporte_notas(
        db, periodo=periodo, anio_lectivo=anio_lectivo or dt.date.today().year,
        sede_id=sede_id, grado=grado, umbral_bajo=umbral_bajo, umbral_alto=umbral_alto,
        riesgo_minimo=riesgo_minimo,
    )
    datos = reporte_notas.exportar_reporte_notas_excel(reporte)
    nombre_archivo = f"reporte_notas_p{periodo}_{dt.date.today().isoformat()}.xlsx"
    return Response(
        content=datos,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


@router.get("/boletines/sapred-sin-coincidencia", response_model=list[schemas.SapredSinCoincidencia])
def listar_sapred_sin_coincidencia(
    anio_lectivo: int | None = None,
    periodo: int | None = None,
    sede_id: int | None = None,
    solo_no_resueltos: bool = True,
    _obs=Depends(rbac.observar("boletines.ver")),
    db: Session = Depends(get_db),
):
    return crud.listar_sapred_sin_coincidencia(
        db, anio_lectivo=anio_lectivo or dt.date.today().year, periodo=periodo,
        sede_id=sede_id, solo_no_resueltos=solo_no_resueltos,
    )


@router.patch("/boletines/sapred-sin-coincidencia/{id_}", response_model=schemas.SapredSinCoincidencia)
def actualizar_sapred_sin_coincidencia(
    id_: int,
    cambios: schemas.SapredSinCoincidenciaActualizar,
    _obs=Depends(rbac.observar("boletines.gestionar")),
    db: Session = Depends(get_db),
):
    fila = crud.actualizar_sapred_sin_coincidencia(db, id_, cambios)
    if fila is None:
        raise HTTPException(status_code=404, detail="No encontrado")
    return fila


@router.get("/boletines/continuidad/exportar")
def exportar_continuidad_academica(
    sede_id: int,
    anio_lectivo: int | None = None,
    _obs=Depends(rbac.observar("boletines.exportar")),
    db: Session = Depends(get_db),
):
    try:
        resumen = auditoria_continuidad.auditoria_continuidad(
            db, sede_id=sede_id, anio_lectivo=anio_lectivo or dt.date.today().year
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    datos = auditoria_continuidad.exportar_continuidad_excel(resumen)
    nombre_archivo = f"continuidad_academica_{resumen.sede_nombre.strip().replace(' ', '_')}_{dt.date.today().isoformat()}.xlsx"
    return Response(
        content=datos,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )
