"""Prueba manual del lector del "Boletín informativo" de SAPRED.

Uso:
    ./venv/Scripts/python.exe probar_boletin.py muestras/boletin_informativo_p2.pdf
    ./venv/Scripts/python.exe probar_boletin.py muestras/boletin_informativo_p2_muestra.txt
    ./venv/Scripts/python.exe probar_boletin.py <archivo> --importar

Acepta un PDF (Reportes > Reportes y Resultados Académicos > Boletín
informativo, exportado) o un .txt con el texto ya extraído (útil para afinar
el parser sin PDF). Sin --importar solo imprime lo que el parser entendió.
Con --importar, además llama a crud.importar_bloque_boletin contra la base
de datos real (colegio.db).
"""

import sys
from pathlib import Path

from app.importador_boletin import parsear_pdf_boletin, parsear_texto_boletin


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    importar = "--importar" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)

    ruta = Path(args[0])
    if not ruta.exists():
        print(f"No existe: {ruta}")
        sys.exit(1)

    if ruta.suffix.lower() == ".txt":
        # Útil para afinar el parser sin un PDF (texto ya extraído).
        bloques = parsear_texto_boletin(ruta.read_text(encoding="utf-8"))
    else:
        bloques = parsear_pdf_boletin(ruta.read_bytes())
    print(f"\n=== {len(bloques)} bloque(s) (grupo sede+grado+curso+periodo) ===\n")
    for b in bloques:
        print(
            f"- Sede '{b['sede_corta']}'  grado {b['grado']}  curso {b['curso']}  "
            f"P{b['periodo']}  año {b['anio_lectivo']}  director: {b['director_grupo']}"
        )
        print(f"  Áreas ({len(b['areas'])}):")
        for a in b["areas"]:
            print(f"    {a['codigo']:6} {a['nombre'][:45]:45}  PROFESOR: {a['docente']}")
        print(f"  Estudiantes ({len(b['estudiantes'])}):")
        for e in b["estudiantes"][:5]:
            con = [c for c, d in e["areas"].items() if d.get("concepto")]
            sin = [c for c, d in e["areas"].items() if not d.get("concepto")]
            print(f"    {e['documento']:12} {e['nombre'][:35]:35}")
            print(f"      concepto SÍ: {con}")
            print(f"      concepto NO: {sin}")
            print(f"      observación: {(e['observacion'] or '(vacía)')[:80]}")
        if len(b["estudiantes"]) > 5:
            print(f"    ... y {len(b['estudiantes']) - 5} más")
        print()

    if not importar:
        return

    from app.database import SessionLocal
    from app import crud

    db = SessionLocal()
    try:
        for b in bloques:
            r = crud.importar_bloque_boletin(db, b)
            print(
                f"IMPORTADO {r.sede_nombre} g{r.grado} c{r.curso}: "
                f"reconocido={r.reconocido}  conceptos +{r.conceptos_pendientes_creados} "
                f"(ya {r.conceptos_pendientes_ya_existian})  observaciones "
                f"+{r.observaciones_pendientes_creadas} (ya {r.observaciones_pendientes_ya_existian})  "
                f"docentes por materia: {r.docentes_area_asignados}  "
                f"director: {r.docente_grupo_asignado}  "
                f"no encontrados: {r.estudiantes_no_encontrados}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
