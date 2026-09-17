"""Importa la lista de profesores desde el PDF exportado de SAPRED.

Uso:
    python importar_docentes.py "C:\\Users\\sebastian\\Downloads\\lisProf20269000000954.pdf"

No borra la base de datos: solo agrega/actualiza docentes (por documento).
"""

import datetime as dt
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

from app import models
from app.database import Base, SessionLocal, engine

RUTA_POR_DEFECTO = r"C:\Users\sebastian\Downloads\lisProf20269000000954.pdf"


def parsear_fecha(valor: str | None) -> dt.date | None:
    if not valor:
        return None
    try:
        fecha = dt.datetime.strptime(valor.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None
    return fecha if fecha.year > 1900 else None


def extraer_docentes(ruta: Path) -> list[dict]:
    doc = fitz.open(ruta)
    texto_total = "".join(pagina.get_text() for pagina in doc)
    bloques = re.split(r"PROFESOR:\s*\n", texto_total)[1:]

    docentes = []
    for bloque in bloques:
        bloque = re.sub(r"\d+ de \d+\s*", "", bloque).strip()
        lineas = bloque.split("\n")
        datos = {
            "nombre_completo": lineas[0].strip(),
            "documento": None,
            "fecha_nacimiento": None,
            "telefono": None,
            "email": None,
            "direccion": None,
        }
        for i, linea in enumerate(lineas):
            bajo = linea.lower()
            siguiente = lineas[i + 1].strip() if i + 1 < len(lineas) else None
            if bajo.startswith("doc. identidad"):
                datos["documento"] = siguiente
            elif bajo.startswith("fec. nacimiento"):
                datos["fecha_nacimiento"] = siguiente
            elif "fono:" in bajo:
                datos["telefono"] = siguiente
            elif bajo.startswith("e-mail"):
                datos["email"] = siguiente
            elif bajo.startswith("direcci"):
                datos["direccion"] = siguiente
        if datos["documento"]:
            docentes.append(datos)
    return docentes


def main():
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(RUTA_POR_DEFECTO)
    if not ruta.exists():
        print(f"No se encontró el archivo: {ruta}")
        return

    Base.metadata.create_all(bind=engine)
    docentes = extraer_docentes(ruta)

    db = SessionLocal()
    nuevos = 0
    actualizados = 0
    try:
        for d in docentes:
            existente = db.query(models.Docente).filter_by(documento=d["documento"]).first()
            if existente is None:
                db.add(
                    models.Docente(
                        documento=d["documento"],
                        nombre_completo=d["nombre_completo"],
                        fecha_nacimiento=parsear_fecha(d["fecha_nacimiento"]),
                        telefono=d["telefono"],
                        email=d["email"],
                        direccion=d["direccion"],
                    )
                )
                nuevos += 1
            else:
                existente.nombre_completo = d["nombre_completo"]
                existente.fecha_nacimiento = parsear_fecha(d["fecha_nacimiento"])
                existente.telefono = d["telefono"]
                existente.email = d["email"]
                existente.direccion = d["direccion"]
                actualizados += 1
        db.commit()
        print(f"Docentes importados: {nuevos} nuevos, {actualizados} actualizados. Total en el archivo: {len(docentes)}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
