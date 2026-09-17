"""Comprime documentos (PDF e imágenes) al estilo "Comprimir PDF" de
iLovePDF: los documentos que suben los profes son fotos de cédulas, fichas
de matrícula, boletines, etc. — no hace falta guardarlos al tamaño con el
que salió la cámara. Con ~10.000 documentos esperados, la diferencia entre
guardar cada uno a full resolución (varios MB) o comprimido (unos cientos
de KB) es la diferencia entre que el servidor tenga espacio o no.

Se usa en dos lugares:
  - Al subir un documento nuevo (routers/fotos.py) — automático, sin que el
    usuario tenga que hacer nada aparte.
  - Al reprocesar los documentos que ya estaban subidos antes de que esto
    existiera (ver comprimir_documentos_existentes.py en la raíz de backend/).

Nunca revienta la subida por esto: si algo sale mal comprimiendo, se
devuelven los bytes originales tal cual — comprimir es una mejora, no un
requisito para poder guardar el documento.
"""

import io

import fitz  # PyMuPDF
from PIL import Image

# 150 DPI es el mismo estándar que usa Ghostscript en su perfil "ebook":
# se sigue leyendo perfectamente un documento de identidad o una ficha con
# letra normal, pero pesa una fracción de lo que pesa un escaneo a 300 DPI.
DPI_OBJETIVO_PDF = 150
CALIDAD_JPEG_PDF = 72
TAMANO_MINIMO_PARA_COMPRIMIR_PDF = 700_000  # bytes; un PDF ya chico no vale la pena tocarlo

LADO_MAXIMO_IMAGEN = 2000  # px — como en el escáner (scanner.js), no hace falta más para leer un documento
CALIDAD_JPEG_IMAGEN = 82
TAMANO_MINIMO_PARA_COMPRIMIR_IMAGEN = 400_000


def comprimir_pdf(datos: bytes) -> bytes:
    """Vuelve a generar el PDF renderizando cada página como una imagen más
    liviana (mismo enfoque que un "comprimir PDF" normal para documentos
    escaneados: la pérdida de nitidez es imperceptible a simple vista, pero
    el peso baja muchísimo — en la práctica, 70-80% menos)."""
    if len(datos) < TAMANO_MINIMO_PARA_COMPRIMIR_PDF:
        return datos
    try:
        origen = fitz.open(stream=datos, filetype="pdf")
        destino = fitz.open()
        escala = DPI_OBJETIVO_PDF / 72  # el PDF trabaja en puntos (72 por pulgada)
        for pagina in origen:
            pix = pagina.get_pixmap(matrix=fitz.Matrix(escala, escala))
            jpeg_bytes = pix.tobytes("jpeg", jpg_quality=CALIDAD_JPEG_PDF)
            nueva = destino.new_page(width=pagina.rect.width, height=pagina.rect.height)
            nueva.insert_image(nueva.rect, stream=jpeg_bytes, alpha=0)
        resultado = destino.tobytes(garbage=4, deflate=True)
        origen_paginas = origen.page_count
        origen.close()
        destino_paginas = fitz.open(stream=resultado, filetype="pdf").page_count
        destino.close()
        # Verificación mínima antes de confiar en el resultado: mismo número
        # de páginas y realmente más liviano (si no, algo salió raro — mejor
        # quedarse con el original que arriesgar un documento roto o más pesado).
        if destino_paginas == origen_paginas and len(resultado) < len(datos):
            return resultado
        return datos
    except Exception:
        return datos


def comprimir_imagen(datos: bytes, extension: str) -> bytes:
    """Igual que comprimir_pdf pero para una foto suelta (JPG/PNG): la
    reduce a un tamaño razonable para leer un documento y la reencoda —
    siempre en el mismo formato del archivo original (nunca cambia la
    extensión, para no desajustar el nombre de archivo ya guardado en la
    base de datos). Si la imagen tiene transparencia (poco común en una
    foto de documento) se conserva sin tocar, para no romperla."""
    if len(datos) < TAMANO_MINIMO_PARA_COMPRIMIR_IMAGEN:
        return datos
    es_png = extension.lower() == ".png"
    try:
        with Image.open(io.BytesIO(datos)) as img:
            if img.mode in ("RGBA", "LA", "P") and img.info.get("transparency") is not None:
                return datos
            img = img.convert("RGB")
            ancho, alto = img.size
            lado_mayor = max(ancho, alto)
            if lado_mayor > LADO_MAXIMO_IMAGEN:
                factor = LADO_MAXIMO_IMAGEN / lado_mayor
                img = img.resize((round(ancho * factor), round(alto * factor)), Image.LANCZOS)
            salida = io.BytesIO()
            if es_png:
                img.save(salida, format="PNG", optimize=True)
            else:
                img.save(salida, format="JPEG", quality=CALIDAD_JPEG_IMAGEN, optimize=True)
            resultado = salida.getvalue()
        if len(resultado) < len(datos):
            return resultado
        return datos
    except Exception:
        return datos
