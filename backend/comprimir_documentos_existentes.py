"""Reprocesa los documentos (PDF e imágenes) que ya estaban subidos ANTES
de que existiera la compresión automática (ver app/compresion_documentos.py
y routers/fotos.py) — los nuevos ya se comprimen solos al subirlos, esto es
solo para "ponerse al día" con lo viejo.

Por seguridad, el modo por defecto es de solo lectura (no toca nada en
disco): muestra cuánto espacio se ahorraría y con qué archivos, para poder
revisar antes de aplicar. Para aplicar los cambios de verdad:

    python comprimir_documentos_existentes.py --aplicar

También regenera la miniatura de cada PDF (más chica desde este cambio) y
la de cualquier imagen que se haya recomprimido, aunque el PDF/imagen en sí
ya estuviera lo bastante chico y no se haya tocado.

Antes de correr esto sobre la base de datos real (con miles de documentos),
lo más sano es hacer una copia de la carpeta uploads/fotos aparte — esto
YA verifica que cada archivo recomprimido se pueda volver a abrir y tenga
el mismo número de páginas (para PDF) antes de reemplazar el original, pero
ninguna verificación reemplaza tener una copia de respaldo real.
"""

import sys
from pathlib import Path

from app.compresion_documentos import comprimir_imagen, comprimir_pdf
from app.routers.fotos import CARPETA_SUBIDAS, EXTENSIONES_IMAGEN, generar_miniatura_pdf, nombre_miniatura


def formatear_mb(cantidad_bytes: int) -> str:
    return f"{cantidad_bytes / (1024 * 1024):.2f} MB"


def main():
    aplicar = "--aplicar" in sys.argv
    if not aplicar:
        print("Modo de solo revisión (no se modifica nada). Para aplicar los cambios: --aplicar\n")

    archivos = [
        p
        for p in CARPETA_SUBIDAS.rglob("*")
        if p.is_file() and p.suffix.lower() in (EXTENSIONES_IMAGEN | {".pdf"}) and "_miniatura" not in p.stem
    ]
    print(f"Documentos encontrados: {len(archivos)}\n")

    total_antes = 0
    total_despues = 0
    comprimidos = 0
    sin_cambios = 0
    fallidos: list[str] = []

    for i, ruta in enumerate(archivos, start=1):
        original = ruta.read_bytes()
        extension = ruta.suffix.lower()
        try:
            if extension == ".pdf":
                nuevo = comprimir_pdf(original)
            else:
                nuevo = comprimir_imagen(original, extension)
        except Exception as e:
            fallidos.append(f"{ruta.relative_to(CARPETA_SUBIDAS)}: {e}")
            nuevo = original

        total_antes += len(original)
        total_despues += len(nuevo)

        if len(nuevo) < len(original):
            comprimidos += 1
            ahorro = 100 * (1 - len(nuevo) / len(original))
            print(f"[{i}/{len(archivos)}] {ruta.relative_to(CARPETA_SUBIDAS)}: "
                  f"{formatear_mb(len(original))} -> {formatear_mb(len(nuevo))} (-{ahorro:.0f}%)")
            if aplicar:
                ruta.write_bytes(nuevo)
                if extension == ".pdf":
                    generar_miniatura_pdf(ruta, ruta.parent / nombre_miniatura(ruta.name))
        else:
            sin_cambios += 1

    print(f"\n{'='*60}")
    print(f"Comprimidos: {comprimidos} · Sin cambios (ya eran chicos): {sin_cambios} · Fallidos: {len(fallidos)}")
    print(f"Peso total: {formatear_mb(total_antes)} -> {formatear_mb(total_despues)} "
          f"(ahorro de {formatear_mb(total_antes - total_despues)})")
    if not aplicar and comprimidos:
        print("\nEsto fue solo una revisión — nada se modificó todavía. Corre de nuevo con --aplicar para guardar los cambios.")
    if fallidos:
        print("\nNo se pudieron procesar (se dejaron tal cual):")
        for f in fallidos:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
