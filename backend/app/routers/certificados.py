import datetime as dt
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from .. import certificados, crud, ficha_matricula, models, promocion, rbac, schemas
from ..database import get_db

router = APIRouter(prefix="/api/certificados", tags=["certificados"])

CARPETA_CONSTANCIAS = Path(__file__).resolve().parent.parent.parent / "uploads" / "constancias"
CARPETA_CONSTANCIAS.mkdir(parents=True, exist_ok=True)


@router.get("/opciones")
def opciones_certificado(_obs=Depends(rbac.observar("constancias.ver"))):
    return {
        "tipos_documento": list(certificados.TIPOS_DOCUMENTO_TEXTO.keys()),
        "propositos": certificados.PROPOSITOS,
        # Para filtrar el registro: además de los de la constancia de estudio,
        # el paz y salvo de grado 11 (que no es un "Válido para...").
        "propositos_registro": certificados.PROPOSITOS + [certificados.PROPOSITO_PAZ_Y_SALVO],
    }


@router.get("", response_model=list[schemas.ConstanciaRegistro])
def listar_constancias(
    q: str | None = None,
    desde: dt.date | None = None,
    hasta: dt.date | None = None,
    proposito: str | None = None,
    estudiante_id: int | None = None,
    _obs=Depends(rbac.observar("constancias.ver")),
    db: Session = Depends(get_db),
):
    return crud.listar_constancias(
        db, busqueda=q, desde=desde, hasta=hasta, proposito=proposito, estudiante_id=estudiante_id
    )


@router.post("/ficha-matricula")
def generar_ficha_matricula_endpoint(
    solicitud: schemas.FichaMatriculaSolicitud,
    _obs=Depends(rbac.observar("estudiantes.ver")),
    db: Session = Depends(get_db),
):
    """Ficha de apoyo generada sobre LA TABLA REAL del formato oficial (ver
    app/ficha_matricula.py). El grado/curso y los campos que el sistema no
    tiene (municipio de nacimiento, resguardo...) se pueden ajustar en el
    formulario antes de generar — nada de esto se guarda en el estudiante,
    solo se usa para esta ficha."""
    estudiante = crud.obtener_estudiante(db, solicitud.estudiante_id)
    if estudiante is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    # Regla de promoción (app/promocion.py): subir con materias perdidas,
    # saltar o bajar de grado necesita permiso APROBADO de coordinación. Sin
    # él la ficha no se genera con ese grado — lo verifica el backend, no
    # solo la pantalla. Un estudiante nuevo de este año no se promueve: viene
    # de otro colegio y su casilla del año es el grado en que entra.
    nuevo = estudiante.matricula_nueva_este_anio
    destino = None if nuevo else _grado_destino(solicitud.campos)
    if destino is not None:
        ev = promocion.evaluar(db, estudiante, destino)
        if not ev.puede_generar:
            estado = ev.solicitud.estado if ev.solicitud else None
            razon = {
                "pendiente": "El permiso ya se pidió y está pendiente: coordinación todavía no lo ha aprobado.",
                "rechazada": "Coordinación rechazó el permiso para ese grado.",
            }.get(estado, "Hace falta pedir permiso a coordinación.")
            raise HTTPException(
                status_code=409,
                detail=f"No se puede generar la ficha con el grado {destino}: "
                + "; ".join(promocion.MOTIVOS_TEXTO[m].lower() for m in ev.motivos) + f". {razon}",
                headers={"X-Requiere-Autorizacion": "1"},
            )

    contenido = ficha_matricula.generar_ficha_matricula(
        documento=estudiante.documento,
        tipo_documento=estudiante.tipo_documento,
        lugar_expedicion_documento=estudiante.lugar_expedicion_documento,
        primer_nombre=estudiante.primer_nombre,
        segundo_nombre=estudiante.segundo_nombre,
        primer_apellido=estudiante.primer_apellido,
        segundo_apellido=estudiante.segundo_apellido,
        fecha_nacimiento=estudiante.fecha_nacimiento,
        genero=estudiante.genero,
        grado=estudiante.grado,
        curso=estudiante.curso,
        campos=solicitud.campos,
        docente=_obs.usuario.nombre if _obs is not None else None,
        anio_matricula=estudiante.anio_ficha_matricula,
        nuevo=nuevo,
    )
    media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    extension = "docx"
    if solicitud.formato == "pdf":
        # Se convierte con Word (instalado en este PC), igual que las constancias.
        carpeta = Path(tempfile.mkdtemp(prefix="ficha_pdf_"))
        try:
            ruta_docx, ruta_pdf = carpeta / "ficha.docx", carpeta / "ficha.pdf"
            ruta_docx.write_bytes(contenido)
            if not certificados.convertir_a_pdf(ruta_docx, ruta_pdf):
                raise HTTPException(
                    status_code=503,
                    detail="No se pudo convertir a PDF (Word no respondió). Descarga el Word o usa Imprimir y elige «Guardar como PDF».",
                )
            contenido = ruta_pdf.read_bytes()
        finally:
            shutil.rmtree(carpeta, ignore_errors=True)
        media, extension = "application/pdf", "pdf"
    nombre_descarga = f"Ficha matricula - {estudiante.nombre_completo}.{extension}"
    autorizada = destino is not None and ev.requiere_autorizacion
    if autorizada:
        promocion.marcar_usada(db, estudiante.id, destino)
    return Response(
        content=contenido,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{nombre_descarga}"',
            "X-Promocion": "autorizada" if autorizada else "normal",
        },
    )


def _grado_destino(campos: dict) -> int | None:
    """El grado que se escribió en la ficha (casilla grado_2026), si hay."""
    m = re.search(r"\d+", (campos or {}).get("grado_2026", ""))
    return int(m.group()) if m else None


#
# --- Paz y salvo de servicio social (grado 11) --------------------------------
# Van ANTES de /{constancia_id}/archivo para que "paz-y-salvo" nunca se lea
# como un id de constancia.

GRADO_PAZ_Y_SALVO = 11
_NOMBRE_ARCHIVO_PYS = re.compile(r"^paz_y_salvo_[0-9a-f]{32}$")


def _dict_paz_y_salvo(e, lugar: str | None = None) -> dict:
    return {
        "nombre_completo": e.nombre_completo,
        "documento": e.documento,
        "tipo_documento": e.tipo_documento,
        "lugar_expedicion": lugar if lugar is not None else e.lugar_expedicion_documento,
        "genero": e.genero,
    }


@router.get("/paz-y-salvo/estudiantes", response_model=list[schemas.PazYSalvoEstudiante])
def estudiantes_paz_y_salvo(
    sede_id: int | None = None,
    _obs=Depends(rbac.observar("constancias.ver")),
    db: Session = Depends(get_db),
):
    """Estudiantes activos de grado 11 (los que necesitan el paz y salvo de
    servicio social para graduarse)."""
    return [
        schemas.PazYSalvoEstudiante(
            id=e.id, nombre_completo=e.nombre_completo, documento=e.documento, tipo_documento=e.tipo_documento,
            lugar_expedicion=e.lugar_expedicion_documento, genero=e.genero,
            sede_id=e.sede_id, sede_nombre=e.sede.nombre if e.sede else "", grupo=e.grupo,
        )
        for e in crud.listar_estudiantes(db, sede_id=sede_id, grado=GRADO_PAZ_Y_SALVO, estado="ACTIVO")
    ]


@router.post("/paz-y-salvo", response_model=schemas.PazYSalvoResultado)
def generar_paz_y_salvo(
    solicitud: schemas.PazYSalvoSolicitud,
    _obs=Depends(rbac.observar("constancias.generar")),
    db: Session = Depends(get_db),
):
    """Un solo Word (y PDF si Word está instalado) con una página por
    estudiante, para imprimir de una vez. Además queda una constancia por
    estudiante en el registro (pestaña Constancias), con su propio Word."""
    if not solicitud.estudiante_ids:
        raise HTTPException(status_code=400, detail="Escoge al menos un estudiante.")
    estudiantes = []
    for estudiante_id in dict.fromkeys(solicitud.estudiante_ids):
        e = crud.obtener_estudiante(db, estudiante_id)
        if e is None:
            raise HTTPException(status_code=404, detail=f"No existe el estudiante #{estudiante_id}.")
        if e.grado != GRADO_PAZ_Y_SALVO:
            raise HTTPException(status_code=400, detail=f"{e.nombre_completo} no está en grado 11.")
        estudiantes.append(e)
    lugares = {
        e.id: (solicitud.lugares.get(e.id) or e.lugar_expedicion_documento or "").strip() for e in estudiantes
    }

    fecha = solicitud.fecha_expedicion
    identificador = f"paz_y_salvo_{uuid.uuid4().hex}"
    ruta_docx = CARPETA_CONSTANCIAS / f"{identificador}.docx"
    ruta_docx.write_bytes(certificados.generar_paz_y_salvo([_dict_paz_y_salvo(e, lugares[e.id]) for e in estudiantes], fecha))
    pdf = certificados.convertir_a_pdf(ruta_docx, CARPETA_CONSTANCIAS / f"{identificador}.pdf")

    for e in estudiantes:
        nombre_individual = f"{uuid.uuid4().hex}.docx"
        (CARPETA_CONSTANCIAS / nombre_individual).write_bytes(
            certificados.generar_paz_y_salvo([_dict_paz_y_salvo(e, lugares[e.id])], fecha)
        )
        if lugares[e.id] and not e.lugar_expedicion_documento:
            e.lugar_expedicion_documento = lugares[e.id]
        db.add(
            models.ConstanciaGenerada(
                estudiante_id=e.id, fecha_expedicion=fecha, proposito=certificados.PROPOSITO_PAZ_Y_SALVO,
                jornada="", anio_escolar=fecha.year, lugar_expedicion=lugares[e.id],
                tipo_documento_usado=e.tipo_documento, archivo_docx=nombre_individual, archivo_pdf=None,
            )
        )
    db.commit()
    return schemas.PazYSalvoResultado(estudiantes=len(estudiantes), archivo=identificador, pdf=pdf)


@router.post("/paz-y-salvo/estudiante", response_model=schemas.ConstanciaRegistro)
def generar_paz_y_salvo_estudiante(
    solicitud: schemas.PazYSalvoEstudianteSolicitud,
    _obs=Depends(rbac.observar("constancias.generar")),
    db: Session = Depends(get_db),
):
    """El paz y salvo de UN estudiante desde su ficha (igual que la constancia
    de estudio): Word + PDF, guardado en el registro de constancias."""
    e = crud.obtener_estudiante(db, solicitud.estudiante_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Ese estudiante no existe en la base de datos.")
    if e.grado != GRADO_PAZ_Y_SALVO:
        raise HTTPException(status_code=400, detail="El paz y salvo de servicio social es para estudiantes de grado 11.")
    lugar = (solicitud.lugar_expedicion or e.lugar_expedicion_documento or "").strip()
    datos = _dict_paz_y_salvo(e, lugar)
    if solicitud.tipo_documento:
        datos["tipo_documento"] = solicitud.tipo_documento

    identificador = uuid.uuid4().hex
    ruta_docx = CARPETA_CONSTANCIAS / f"{identificador}.docx"
    ruta_docx.write_bytes(certificados.generar_paz_y_salvo([datos], solicitud.fecha_expedicion))
    ruta_pdf = CARPETA_CONSTANCIAS / f"{identificador}.pdf"
    pdf = certificados.convertir_a_pdf(ruta_docx, ruta_pdf)

    if lugar and not e.lugar_expedicion_documento:
        e.lugar_expedicion_documento = lugar
    return crud.registrar_constancia(
        db,
        estudiante_id=e.id, fecha_expedicion=solicitud.fecha_expedicion, proposito=certificados.PROPOSITO_PAZ_Y_SALVO,
        jornada="", anio_escolar=solicitud.fecha_expedicion.year, lugar_expedicion=lugar,
        tipo_documento_usado=datos["tipo_documento"], archivo_docx=ruta_docx.name, archivo_pdf=ruta_pdf.name if pdf else None,
    )


@router.get("/paz-y-salvo/descargar/{archivo}")
def descargar_paz_y_salvo(
    archivo: str,
    formato: str = "docx",
    _obs=Depends(rbac.observar("constancias.ver")),
    db: Session = Depends(get_db),
):
    if not _NOMBRE_ARCHIVO_PYS.match(archivo) or formato not in ("docx", "pdf"):
        raise HTTPException(status_code=400, detail="Archivo no válido")
    ruta = CARPETA_CONSTANCIAS / f"{archivo}.{formato}"
    if not ruta.exists():
        raise HTTPException(status_code=404, detail="Ese archivo ya no está en el disco")
    return FileResponse(ruta, filename=f"Paz y salvo servicio social grado 11.{formato}")


@router.get("/{constancia_id}/archivo")
def obtener_archivo_constancia(
    constancia_id: int,
    formato: str = "docx",
    _obs=Depends(rbac.observar("constancias.ver")),
    db: Session = Depends(get_db),
):
    constancia = crud.obtener_constancia(db, constancia_id)
    if constancia is None:
        raise HTTPException(status_code=404, detail="Constancia no encontrada")

    nombre_archivo = constancia.archivo_pdf if formato == "pdf" else constancia.archivo_docx
    if not nombre_archivo:
        raise HTTPException(status_code=404, detail="Esa constancia no tiene ese formato disponible")

    ruta = CARPETA_CONSTANCIAS / nombre_archivo
    if not ruta.exists():
        raise HTTPException(status_code=404, detail="El archivo ya no está en el disco")

    tipo = "Paz y salvo" if constancia.proposito == certificados.PROPOSITO_PAZ_Y_SALVO else "Constancia"
    nombre_descarga = f"{tipo} - {constancia.estudiante.nombre_completo}.{formato}"
    return FileResponse(ruta, filename=nombre_descarga)


@router.post("/constancia", response_model=schemas.ConstanciaRegistro)
def generar_constancia(
    solicitud: schemas.ConstanciaSolicitud,
    _obs=Depends(rbac.observar("constancias.generar")),
    db: Session = Depends(get_db),
):
    estudiante = crud.obtener_estudiante(db, solicitud.estudiante_id)
    if estudiante is None:
        raise HTTPException(
            status_code=404,
            detail="Ese estudiante no existe en la base de datos, no se puede generar la constancia.",
        )

    tipo_documento_usado = solicitud.tipo_documento or estudiante.tipo_documento
    contenido = certificados.generar_constancia(
        nombre_completo=estudiante.nombre_completo,
        tipo_documento=tipo_documento_usado,
        documento=estudiante.documento,
        lugar_expedicion=solicitud.lugar_expedicion,
        grado=estudiante.grado,
        jornada=solicitud.jornada,
        anio_escolar=solicitud.anio_escolar,
        fecha_expedicion=solicitud.fecha_expedicion,
        proposito=solicitud.proposito,
    )

    identificador = uuid.uuid4().hex
    nombre_docx = f"{identificador}.docx"
    ruta_docx = CARPETA_CONSTANCIAS / nombre_docx
    ruta_docx.write_bytes(contenido)

    nombre_pdf = f"{identificador}.pdf"
    ruta_pdf = CARPETA_CONSTANCIAS / nombre_pdf
    pdf_generado = certificados.convertir_a_pdf(ruta_docx, ruta_pdf)

    # Guardamos el lugar de expedición para no tener que volver a escribirlo
    # la próxima vez que se genere una constancia para este estudiante.
    if solicitud.lugar_expedicion and not estudiante.lugar_expedicion_documento:
        estudiante.lugar_expedicion_documento = solicitud.lugar_expedicion
        db.commit()

    constancia = crud.registrar_constancia(
        db,
        estudiante_id=estudiante.id,
        fecha_expedicion=solicitud.fecha_expedicion,
        proposito=solicitud.proposito,
        jornada=solicitud.jornada,
        anio_escolar=solicitud.anio_escolar,
        lugar_expedicion=solicitud.lugar_expedicion,
        tipo_documento_usado=tipo_documento_usado,
        archivo_docx=nombre_docx,
        archivo_pdf=nombre_pdf if pdf_generado else None,
    )
    return constancia
