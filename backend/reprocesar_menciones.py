"""Vuelve a generar las MENCIONES (DiagnosticoMencion) de los diagnósticos ya
importados, sin tocar el resto del diagnóstico ni crear una versión nueva.

Existe porque el algoritmo de extracción de menciones (diagnostico_import.
construir_menciones) puede mejorar con el tiempo — la corrección del
23/09/2026 fue justo así: antes, si un mismo texto mencionaba a 5
estudiantes, a los 5 se les copiaba el párrafo completo como si fuera SU
detalle. Reimportar el Excel entero no sirve para esto porque el contenido
de los CAMPOS no cambió (mismo texto de siempre), solo cómo se interpreta
— así que `importar_diagnostico.py` lo saltaría por "sin cambios". Este
script SÍ vuelve a correr la extracción sobre el texto ya guardado en cada
diagnóstico vigente, y reemplaza solo sus menciones.

Protección: si un diagnóstico ya tiene alguna mención vinculada A MANO
(vinculo_automatico=False, es decir alguien ya la revisó desde la app), se
salta por defecto — no se pisa trabajo humano. Usa --forzar para
reprocesar de todas formas (perdiendo esas vinculaciones manuales).

Por defecto NO escribe: muestra lo que haría. Para aplicarlo:

    python reprocesar_menciones.py --aplicar
    python reprocesar_menciones.py --aplicar --grado 0        (solo un grado)
    python reprocesar_menciones.py --aplicar --forzar         (aunque haya vinculaciones manuales)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select  # noqa: E402

from app import diagnostico_import, migraciones, models  # noqa: E402
from app.database import SessionLocal  # noqa: E402

migraciones.ejecutar()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--grado", type=int, help="solo reprocesar este grado (0=Preescolar..11=Once)")
    parser.add_argument("--forzar", action="store_true", help="reprocesar aunque ya existan vinculaciones manuales (se pierden)")
    parser.add_argument("--aplicar", action="store_true", help="sin esto solo se muestra un resumen, no se guarda nada")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        stmt = select(models.DiagnosticoGrado).order_by(
            models.DiagnosticoGrado.sede_id, models.DiagnosticoGrado.grado, models.DiagnosticoGrado.curso,
            models.DiagnosticoGrado.importado_en.desc(),
        )
        if args.grado is not None:
            stmt = stmt.where(models.DiagnosticoGrado.grado == args.grado)
        vistos: set[tuple[int, int, int | None]] = set()
        actuales: list[models.DiagnosticoGrado] = []
        for d in db.scalars(stmt):
            clave = (d.sede_id, d.grado, d.curso)
            if clave in vistos:
                continue
            vistos.add(clave)
            actuales.append(d)

        cache_hojas: dict[str, dict[str, diagnostico_import.HojaDiagnostico]] = {}
        saltados_manual = []
        procesados = []
        for d in actuales:
            manuales = [m for m in d.menciones if not m.vinculo_automatico and m.estudiante_id is not None]
            if manuales and not args.forzar:
                saltados_manual.append((d, len(manuales)))
                continue
            if not d.archivo_origen:
                print(f"  ! {d.hoja_excel}: sin archivo_origen guardado, no se puede reprocesar")
                continue
            if d.archivo_origen not in cache_hojas:
                cache_hojas[d.archivo_origen] = {
                    h.hoja_excel: h for h in diagnostico_import.leer_libro(d.archivo_origen)
                }
            hoja = cache_hojas[d.archivo_origen].get(d.hoja_excel)
            if hoja is None:
                print(f"  ! {d.hoja_excel}: ya no se encuentra esa hoja en {d.archivo_origen}")
                continue

            antes = len(d.menciones)
            antes_vinculadas = sum(1 for m in d.menciones if m.estudiante_id is not None)
            nuevas = diagnostico_import.construir_menciones(db, hoja, d.sede_id)
            procesados.append((d, antes, antes_vinculadas, nuevas))

        print(f"Diagnósticos vigentes: {len(actuales)}")
        if saltados_manual:
            print(f"\nSaltados por tener vinculaciones manuales (usa --forzar para reprocesar igual):")
            for d, n in saltados_manual:
                print(f"    - {d.hoja_excel}: {n} vinculación(es) manual(es)")

        print(f"\nSe reprocesan {len(procesados)} diagnóstico(s):")
        for d, antes, antes_vinc, nuevas in procesados:
            despues_vinc = sum(1 for m in nuevas if m.estudiante_id is not None)
            grado_txt = f"{d.grado}.{d.curso}" if d.curso is not None else str(d.grado)
            print(
                f"  · {d.hoja_excel:<14} grado {grado_txt:<6} "
                f"menciones: {antes:>3} -> {len(nuevas):>3}   vinculadas: {antes_vinc:>3} -> {despues_vinc:>3}"
            )

        if not args.aplicar:
            print("\n(No se guardó nada: corre de nuevo con --aplicar)")
            return

        for d, _antes, _antes_vinc, nuevas in procesados:
            d.menciones.clear()
            db.flush()
            d.menciones = nuevas
        db.commit()
        print("\nGuardado.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
