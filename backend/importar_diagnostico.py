"""Importa el Excel "DIAGNOSTICO IETABA" (orientación/psicología, una hoja
por grado) hacia DiagnosticoGrado + DiagnosticoMencion, para que el rol
Orientación/Psicología lo vea y lo imprima desde la app en vez de abrir el
Excel.

Se puede correr las veces que haga falta: cada corrida crea una VERSIÓN
nueva por grado (nunca borra una anterior) salvo que el contenido sea
idéntico al de la última versión guardada, caso en el que se omite. Por
defecto NO escribe: muestra lo que haría. Para aplicarlo:

    python importar_diagnostico.py --aplicar
    python importar_diagnostico.py "ruta\\otro.xlsx" --aplicar --usuario sebastian.pai

    # Si alguna hoja no trae su propia fecha (pasa en unas pocas), se le
    # asigna el primer día del mes/año indicado en vez de dejarla en blanco:
    python importar_diagnostico.py --aplicar --periodo 2026-04
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select  # noqa: E402

from app import auth, diagnostico_import, models  # noqa: E402
from app.database import SessionLocal  # noqa: E402

RUTA_POR_DEFECTO = r"D:\sebas\DIAGNOSTICO IETABA 2026...xlsx"
NOMBRE_SEDE_CONTIENE = "I.E.T.A.B.A."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archivo", nargs="?", default=RUTA_POR_DEFECTO)
    parser.add_argument("--usuario", help="documento del usuario que queda como 'importado por' (opcional)")
    parser.add_argument("--periodo", help="AAAA-MM: respaldo para las hojas que no traen su propia fecha (opcional)")
    parser.add_argument("--aplicar", action="store_true", help="sin esto solo se muestra un resumen, no se guarda nada")
    args = parser.parse_args()

    ruta = Path(args.archivo)
    if not ruta.exists():
        sys.exit(f"No existe el archivo: {ruta}")

    fecha_respaldo = None
    if args.periodo:
        try:
            anio, mes = (int(p) for p in args.periodo.split("-", 1))
            fecha_respaldo = dt.date(anio, mes, 1)
        except ValueError:
            sys.exit("--periodo debe tener el formato AAAA-MM, ej: 2026-04")

    db = SessionLocal()
    try:
        sede = db.scalar(select(models.Sede).where(models.Sede.nombre.contains(NOMBRE_SEDE_CONTIENE)))
        if sede is None:
            sys.exit(f"No se encontró una sede cuyo nombre contenga '{NOMBRE_SEDE_CONTIENE}'.")

        importado_por_id = None
        if args.usuario:
            usuario = auth.buscar_usuario(db, args.usuario)
            if usuario is None:
                sys.exit(f"No existe un usuario con documento o correo {args.usuario}.")
            importado_por_id = usuario.id

        resultado = diagnostico_import.importar(db, ruta, sede.id, importado_por_id, fecha_respaldo)

        print(f"Archivo: {ruta}")
        print(f"Sede: {sede.nombre} (#{sede.id})")
        print(f"Hojas de diagnóstico leídas: {resultado['hojas_leidas']}")
        print(f"Versiones nuevas: {len(resultado['creados'])}")
        if resultado["omitidos_sin_cambios"]:
            print(f"Sin cambios respecto a la última versión (omitidas): {len(resultado['omitidos_sin_cambios'])}")
            for nombre in resultado["omitidos_sin_cambios"]:
                print(f"    - {nombre}")

        total_menciones = 0
        total_vinculadas = 0
        for d in resultado["creados"]:
            n = len(d.menciones)
            v = sum(1 for m in d.menciones if m.estudiante_id is not None)
            total_menciones += n
            total_vinculadas += v
            grado_txt = f"{d.grado}.{d.curso}" if d.curso is not None else str(d.grado)
            print(f"  · {d.hoja_excel:<14} grado {grado_txt:<6} menciones: {n:>3}  vinculadas automáticamente: {v:>3}")
        if resultado["creados"]:
            print(f"\nTotal menciones detectadas: {total_menciones}  ·  vinculadas automáticamente: {total_vinculadas}  ·  pendientes de revisar: {total_menciones - total_vinculadas}")

        if not args.aplicar:
            print("\n(No se guardó nada: corre de nuevo con --aplicar)")
            db.rollback()
            return

        db.commit()
        print("\nGuardado.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
