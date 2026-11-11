"""Carga el censo indígena del Ministerio del Interior (Excel del resguardo) y
lo une con los estudiantes del colegio.

Uso (desde backend/):

    ./venv/Scripts/python.exe importar_censo.py "C:/ruta/CENSO MININTERIOR GRAN SABALO.xlsx"
    ./venv/Scripts/python.exe importar_censo.py --revincular   # solo vuelve a unir (p. ej. tras matricular)

Lee la hoja FORMATO_CENSOS (las de fallecidos y retiro voluntario no). Cada
carga REEMPLAZA el censo de ese resguardo: cuando llegue la actualización del
año, se vuelve a correr con el Excel nuevo. Ver app/censo.py.
"""

import sys
from pathlib import Path

from app import censo, migraciones
from app.database import SessionLocal


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    migraciones.ejecutar()  # crea la tabla si la base todavía no la tiene
    db = SessionLocal()
    try:
        if args[0] == "--revincular":
            r = censo.vincular_estudiantes(db)
            db.commit()
            print(f"Vinculados por documento: {r['vinculados_documento']} · por nombre: {r['vinculados_nombre']}")
            return
        ruta = Path(args[0])
        if not ruta.exists():
            sys.exit(f"No existe el archivo: {ruta}")
        personas = censo.leer_excel(ruta)
        r = censo.importar(db, personas)
        print(f"Censo cargado: {r['personas']} personas · resguardo(s): {', '.join(r['resguardos'])}")
        print(f"Estudiantes vinculados por documento: {r['vinculados_documento']} · solo por nombre (verificar): {r['vinculados_nombre']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
