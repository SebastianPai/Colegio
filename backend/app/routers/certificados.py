import datetime as dt
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import certificados, crud, rbac, schemas
from ..database import get_db

router = APIRouter(prefix="/api/certificados", tags=["certificados"])

CARPETA_CONSTANCIAS = Path(__file__).resolve().parent.parent.parent / "uploads" / "constancias"
CARPETA_CONSTANCIAS.mkdir(parents=True, exist_ok=True)


@router.get("/opciones")
def opciones_certificado(_obs=Depends(rbac.observar("constancias.ver"))):
    return {
        "tipos_documento": list(certificados.TIPOS_DOCUMENTO_TEXTO.keys()),
        "propositos": certificados.PROPOSITOS,
    }


@router.get("", response_model=list[schemas.ConstanciaRegistro])
def listar_constancias(
    q: str | None = None,
    desde: dt.date | None = None,
    hasta: dt.date | None = None,
    proposito: str | None = None,
    _obs=Depends(rbac.observar("constancias.ver")),
    db: Session = Depends(get_db),
):
    return crud.listar_constancias(db, busqueda=q, desde=desde, hasta=hasta, proposito=proposito)


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

    nombre_descarga = f"Constancia - {constancia.estudiante.nombre_completo}.{formato}"
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
