import datetime as dt
import io
import uuid
from pathlib import Path

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy.orm import Session

from .. import crud, rbac
from ..compresion_documentos import comprimir_imagen, comprimir_pdf
from ..database import get_db

router = APIRouter(prefix="/api", tags=["fotos"])

CARPETA_SUBIDAS = Path(__file__).resolve().parent.parent.parent / "uploads" / "fotos"
CARPETA_SUBIDAS.mkdir(parents=True, exist_ok=True)

EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png"}
EXTENSIONES_PERMITIDAS = EXTENSIONES_IMAGEN | {".pdf"}
TAMANO_MAXIMO_MB = 15


def nombre_miniatura(nombre_archivo: str) -> str:
    return nombre_archivo.rsplit(".", 1)[0] + "_miniatura.jpg"


def generar_miniatura_pdf(ruta_pdf: Path, ruta_miniatura: Path) -> bool:
    """Renderiza solo la primera página del PDF como imagen, para poder
    mostrarla en la galería igual que una foto (sin abrir el PDF completo).
    Es una miniatura para una tarjeta de vista previa (a lo sumo ~400px de
    ancho en pantalla) — no hace falta ni la resolución ni la calidad JPEG
    por defecto de PyMuPDF (95), que llegaban a pesar más que el propio PDF
    ya comprimido."""
    try:
        with fitz.open(ruta_pdf) as doc:
            pagina = doc[0]
            pix = pagina.get_pixmap(matrix=fitz.Matrix(0.9, 0.9))
            pix.save(str(ruta_miniatura), jpg_quality=70)
        return True
    except Exception:
        return False


def borrar_documento(db: Session, foto) -> None:
    """Borra la fila y el archivo (y su miniatura) del disco."""
    crud.eliminar_foto(db, foto.id)
    (CARPETA_SUBIDAS / foto.nombre_archivo).unlink(missing_ok=True)
    (CARPETA_SUBIDAS / nombre_miniatura(foto.nombre_archivo)).unlink(missing_ok=True)


async def guardar_documento(
    db: Session,
    estudiante_id: int,
    etiqueta: str,
    anio_lectivo: int,
    permanente: bool,
    archivo: UploadFile,
    uuid_cliente: str | None = None,
    reemplaza_id: int | None = None,
) -> dict:
    """Lógica común de subida (Secretaría y director de grupo, ver
    routers/docente.py). `uuid_cliente` hace la subida idempotente: el
    celular lo manda desde su cola sin conexión y, si reintenta una subida
    que sí había llegado, recibe la misma respuesta sin duplicar nada.
    `reemplaza_id` borra el documento anterior DESPUÉS de guardar el nuevo,
    y solo si es del mismo estudiante."""
    uuid_cliente = (uuid_cliente or "").strip()[:36] or None
    if uuid_cliente:
        previa = crud.foto_por_uuid_cliente(db, estudiante_id, uuid_cliente)
        if previa is not None:
            return {"id": previa.id, "etiqueta": previa.etiqueta, "anio_lectivo": previa.anio_lectivo, "orden": previa.orden}

    extension = Path(archivo.filename or "").suffix.lower()
    if extension not in EXTENSIONES_PERMITIDAS:
        raise HTTPException(
            status_code=400,
            detail="Solo se aceptan imágenes (JPG/PNG) o PDF (si escaneaste el documento).",
        )

    contenido = await archivo.read()
    if len(contenido) > TAMANO_MAXIMO_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"El archivo supera los {TAMANO_MAXIMO_MB} MB.")

    # Se valida y comprime en memoria ANTES de escribir a disco — así nunca
    # queda un archivo a medio guardar, y solo se escribe una vez (con el
    # tamaño ya reducido) en vez de escribir el original y luego reemplazarlo.
    if extension in EXTENSIONES_IMAGEN:
        try:
            with Image.open(io.BytesIO(contenido)) as img:
                img.verify()
        except Exception:
            raise HTTPException(status_code=400, detail="El archivo no es una imagen válida.")
        contenido = comprimir_imagen(contenido, extension)
    else:
        if not contenido.startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail="El archivo no es un PDF válido.")
        contenido = comprimir_pdf(contenido)

    carpeta_estudiante = CARPETA_SUBIDAS / str(estudiante_id)
    carpeta_estudiante.mkdir(parents=True, exist_ok=True)
    nombre_archivo = f"{uuid.uuid4().hex}{extension}"
    ruta = carpeta_estudiante / nombre_archivo
    ruta.write_bytes(contenido)

    if extension not in EXTENSIONES_IMAGEN:
        generar_miniatura_pdf(ruta, carpeta_estudiante / nombre_miniatura(nombre_archivo))

    foto = crud.agregar_foto(
        db,
        estudiante_id,
        etiqueta,
        None if permanente else anio_lectivo,
        f"{estudiante_id}/{nombre_archivo}",
        uuid_cliente=uuid_cliente,
    )
    if reemplaza_id:
        anterior = crud.obtener_foto(db, reemplaza_id)
        if anterior is not None and anterior.estudiante_id == estudiante_id and anterior.id != foto.id:
            borrar_documento(db, anterior)
    return {"id": foto.id, "etiqueta": foto.etiqueta, "anio_lectivo": foto.anio_lectivo, "orden": foto.orden}


@router.post("/estudiantes/{estudiante_id}/fotos")
async def subir_foto(
    estudiante_id: int,
    etiqueta: str = Form("Documento"),
    anio_lectivo: int = Form(default_factory=lambda: dt.date.today().year),
    permanente: bool = Form(False),
    archivo: UploadFile = File(...),
    uuid_cliente: str | None = Form(None),
    reemplaza_id: int | None = Form(None),
    _obs=Depends(rbac.observar("estudiantes.documentos_gestionar")),
    db: Session = Depends(get_db),
):
    if crud.obtener_estudiante(db, estudiante_id) is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    return await guardar_documento(
        db, estudiante_id, etiqueta, anio_lectivo, permanente, archivo, uuid_cliente, reemplaza_id
    )


@router.get("/fotos/{foto_id}/archivo")
def obtener_archivo_foto(
    foto_id: int,
    descargar: bool = False,
    _obs=Depends(rbac.observar("estudiantes.ver_documentos")),
    db: Session = Depends(get_db),
):
    foto = crud.obtener_foto(db, foto_id)
    if foto is None:
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    ruta = CARPETA_SUBIDAS / foto.nombre_archivo
    if not ruta.exists():
        raise HTTPException(status_code=404, detail="El archivo ya no está en el disco")
    if descargar:
        return FileResponse(ruta, filename=foto.nombre_descarga)
    return FileResponse(ruta)


@router.get("/fotos/{foto_id}/miniatura")
def obtener_miniatura_foto(
    foto_id: int, _obs=Depends(rbac.observar("estudiantes.ver_documentos")), db: Session = Depends(get_db)
):
    """Para PDFs, sirve la miniatura de la primera página (si se pudo
    generar). Para imágenes, sirve la foto tal cual — el navegador ya la
    encoge con CSS, no hace falta una miniatura aparte."""
    foto = crud.obtener_foto(db, foto_id)
    if foto is None:
        raise HTTPException(status_code=404, detail="Foto no encontrada")

    if foto.es_pdf:
        ruta_miniatura = CARPETA_SUBIDAS / nombre_miniatura(foto.nombre_archivo)
        if ruta_miniatura.exists():
            return FileResponse(ruta_miniatura)
        raise HTTPException(status_code=404, detail="No hay miniatura disponible para este PDF")

    ruta = CARPETA_SUBIDAS / foto.nombre_archivo
    if not ruta.exists():
        raise HTTPException(status_code=404, detail="El archivo ya no está en el disco")
    return FileResponse(ruta)


@router.delete("/fotos/{foto_id}", status_code=204)
def eliminar_foto(
    foto_id: int, _obs=Depends(rbac.observar("estudiantes.documentos_gestionar")), db: Session = Depends(get_db)
):
    foto = crud.obtener_foto(db, foto_id)
    if foto is None:
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    borrar_documento(db, foto)
