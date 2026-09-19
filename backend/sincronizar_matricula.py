"""Sincroniza la base con un Excel de matrícula ACTUALIZADO, sin borrar nada.

A diferencia de `importar_matricula.py` (que borra `colegio.db` y la rehace
desde cero, pensado para la carga inicial), este script se puede correr cada
vez que la secretaría actualiza el Excel: solo crea los estudiantes nuevos,
corrige los datos que cambiaron y avisa de los que ya no aparecen. Las notas,
el horario, los pendientes de boletín, las fotos y las marcas se conservan.

Por defecto NO escribe: muestra lo que haría. Para aplicarlo:

    python sincronizar_matricula.py --aplicar
    python sincronizar_matricula.py "ruta\\otro.xlsx" --aplicar
    python sincronizar_matricula.py --aplicar --faltantes nada

Los que están en la base y ya NO aparecen en el Excel (`--faltantes`):
    retirado  = se marcan como "retirado" (sigue en el sistema, reversible) [por defecto]
    posible   = se marcan como "posible retiro"
    nada      = se dejan igual, solo se listan

Solo se comparan las sedes que vienen en el Excel: si el archivo es solo de la
Sede #01, las demás sedes no se tocan.
"""

import argparse
import datetime as dt
import shutil
import sqlite3
import sys
from pathlib import Path

import openpyxl

from app import models
from app.database import SessionLocal

RUTA_POR_DEFECTO = r"D:\ietaba\ARCHIVO INGENIERO\B.D. MATRICULA SEDE # 01 INST. IETABA - SEPT 15.xlsx"
HOJA = "B.D. ESTUDIANTES"
BASE = Path(__file__).resolve().parent / "colegio.db"

# columna del Excel -> campo del estudiante
CAMPOS = {
    "TIPO DOCUMENTO": "tipo_documento",
    "PRIMER APELLIDO": "primer_apellido",
    "SEGUNDO APELLIDO": "segundo_apellido",
    "PRIMER NOMBRE": "primer_nombre",
    "SEGUNDO NOMBRE": "segundo_nombre",
    "FECHA NACIMIENTO": "fecha_nacimiento",
    "GENERO": "genero",
    "GRADO": "grado",
    "CURSO IETABA": "curso",
}


def _texto(valor):
    if valor is None:
        return None
    return str(valor).strip() or None


def _entero(valor):
    if valor is None or str(valor).strip() == "":
        return None
    try:
        return int(float(str(valor).strip()))
    except ValueError:
        return None


def _fecha(valor):
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    return None


def leer_excel(ruta: Path) -> tuple[dict[str, dict], list[str]]:
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    if HOJA not in wb.sheetnames:
        raise SystemExit(f"El archivo no tiene la hoja «{HOJA}» (tiene: {wb.sheetnames})")
    filas = wb[HOJA].iter_rows(values_only=True)
    col = {str(n).strip().upper(): i for i, n in enumerate(next(filas)) if n}

    def valor(fila, nombre):
        return fila[col[nombre]] if nombre in col else None

    estudiantes: dict[str, dict] = {}
    repetidos: list[str] = []
    for fila in filas:
        documento = _texto(valor(fila, "NRO DOCUMENTO"))
        sede = _texto(valor(fila, "SEDE EDUCATIVA"))
        if not documento or not sede:
            continue
        if documento in estudiantes:
            repetidos.append(documento)
        datos = {"__sede": sede}
        for columna, campo in CAMPOS.items():
            bruto = valor(fila, columna)
            if campo in ("grado", "curso"):
                datos[campo] = _entero(bruto)
            elif campo == "fecha_nacimiento":
                datos[campo] = _fecha(bruto)
            else:
                datos[campo] = _texto(bruto)
        estudiantes[documento] = datos
    return estudiantes, repetidos


def _sedes_del_excel(db, nombres: set[str]) -> dict[str, models.Sede]:
    """Las sedes del Excel se buscan por nombre exacto y, si no, comparando
    solo el 'SEDE # NN' (el Excel y la base escriben el resto distinto)."""
    todas = db.query(models.Sede).all()
    por_nombre = {s.nombre.strip().upper(): s for s in todas}

    def numero(texto: str) -> str | None:
        partes = texto.upper().replace("#", "# ").split()
        for i, p in enumerate(partes):
            if p == "#" and i + 1 < len(partes):
                return partes[i + 1].lstrip("0") or "0"
        return None

    por_numero: dict[str, list[models.Sede]] = {}
    for s in todas:
        n = numero(s.nombre)
        if n:
            por_numero.setdefault(n, []).append(s)

    encontradas = {}
    for nombre in nombres:
        sede = por_nombre.get(nombre.strip().upper())
        if sede is None:
            candidatas = [
                s for s in por_numero.get(numero(nombre) or "", []) if s.pertenece_ietaba
            ]
            # "SEDE # 01" existe en varias instituciones: se prefiere IETABA.
            candidatas.sort(key=lambda s: 0 if "I.E.T.A.B.A" in s.nombre.upper() else 1)
            sede = candidatas[0] if candidatas else None
        if sede is None:
            raise SystemExit(f"No se encontró en la base la sede «{nombre}»")
        encontradas[nombre] = sede
    return encontradas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("excel", nargs="?", default=RUTA_POR_DEFECTO)
    parser.add_argument("--aplicar", action="store_true", help="escribe los cambios (si no, solo simula)")
    parser.add_argument(
        "--faltantes",
        choices=["retirado", "posible", "nada"],
        default="retirado",
        help="qué hacer con los que ya no aparecen en el Excel",
    )
    args = parser.parse_args()

    ruta = Path(args.excel)
    if not ruta.exists():
        raise SystemExit(f"No se encontró el Excel: {ruta}")

    excel, repetidos = leer_excel(ruta)
    print(f"Excel: {ruta.name}")
    print(f"  {len(excel)} estudiantes" + (f" ({len(repetidos)} documentos repetidos)" if repetidos else ""))

    db = SessionLocal()
    sedes = _sedes_del_excel(db, {d["__sede"] for d in excel.values()})
    ids_sedes = {s.id for s in sedes.values()}
    print("  sedes del archivo: " + ", ".join(sorted(s.nombre for s in sedes.values())))

    en_base = {
        e.documento: e
        for e in db.query(models.Estudiante).filter(models.Estudiante.sede_id.in_(ids_sedes)).all()
    }
    otras_sedes = {
        e.documento: e
        for e in db.query(models.Estudiante).filter(~models.Estudiante.sede_id.in_(ids_sedes)).all()
    }

    nuevos, movidos, actualizados, faltantes = [], [], [], []
    for documento, datos in excel.items():
        sede = sedes[datos["__sede"]]
        est = en_base.get(documento) or otras_sedes.get(documento)
        if est is None:
            nuevos.append((documento, datos, sede))
            continue
        cambios = {}
        if est.sede_id != sede.id:
            cambios["sede_id"] = sede.id
            movidos.append((est, sede))
        for campo in CAMPOS.values():
            nuevo = datos[campo]
            if nuevo is None and campo in ("segundo_apellido", "segundo_nombre", "curso"):
                pass  # el Excel puede venir vacío en estos; se respeta lo que trae
            if (getattr(est, campo) or None) != (nuevo or None):
                cambios[campo] = nuevo
        if cambios:
            actualizados.append((est, cambios))

    for documento, est in en_base.items():
        if documento not in excel:
            faltantes.append(est)

    # Si un "nuevo" del Excel tiene el MISMO nombre que uno que "ya no está",
    # casi siempre es el mismo estudiante con el documento corregido (un dígito
    # cambiado). Se trata como cambio de documento —así conserva notas, fotos y
    # boletines— y no como uno nuevo más otro retirado.
    def _clave_nombre(*partes):
        return " ".join(p.upper() for p in partes if p)

    por_nombre_faltante = {
        _clave_nombre(e.primer_nombre, e.segundo_nombre, e.primer_apellido, e.segundo_apellido): e
        for e in faltantes
    }
    cambios_documento = []
    for entrada in list(nuevos):
        documento, datos, sede = entrada
        clave = _clave_nombre(
            datos["primer_nombre"], datos["segundo_nombre"], datos["primer_apellido"], datos["segundo_apellido"]
        )
        est = por_nombre_faltante.get(clave)
        if est is None:
            continue
        cambios_documento.append((est, documento, datos))
        nuevos.remove(entrada)
        faltantes.remove(est)
        del por_nombre_faltante[clave]

    print(f"\nNUEVOS (se crean): {len(nuevos)}")
    for documento, datos, sede in nuevos:
        nombre = " ".join(
            p for p in (datos["primer_nombre"], datos["segundo_nombre"], datos["primer_apellido"], datos["segundo_apellido"]) if p
        )
        grado = models.GRADOS_NOMBRES.get(datos["grado"], datos["grado"])
        print(f"   + {documento} {nombre} · {grado} - {datos['curso']} · {sede.nombre}")

    print(f"\nCON CAMBIOS (se corrigen): {len(actualizados)}")
    for est, cambios in actualizados:
        detalle = ", ".join(f"{c}: {getattr(est, c)!r} -> {v!r}" for c, v in cambios.items())
        print(f"   ~ {est.documento} {est.nombre_completo}: {detalle}")

    print(f"\nYA NO ESTAN EN EL EXCEL: {len(faltantes)}  (--faltantes {args.faltantes})")
    for est in faltantes:
        marca = " [ya marcado]" if est.retirado else ""
        print(f"   ? {est.documento} {est.nombre_completo} · {est.grupo}{marca}")

    if not args.aplicar:
        print("\n(simulación: no se escribió nada. Agrega --aplicar para guardarlo)")
        return

    if not (nuevos or actualizados or cambios_documento or (faltantes and args.faltantes != "nada")):
        print("\nNo hay nada que cambiar.")
        return

    sello = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    respaldo = BASE.with_name(f"{BASE.name}.bak_antes_sync_matricula_{sello}")
    origen = sqlite3.connect(BASE)
    destino = sqlite3.connect(respaldo)
    origen.backup(destino)
    destino.close()
    origen.close()
    print(f"\nRespaldo: {respaldo.name}")

    for documento, datos, sede in nuevos:
        db.add(
            models.Estudiante(
                documento=documento,
                sede_id=sede.id,
                estado="ACTIVO",
                verificado_matricula=True,
                **{c: datos[c] for c in CAMPOS.values()},
            )
        )
    for est, cambios in actualizados:
        for campo, valor in cambios.items():
            setattr(est, campo, valor)
        est.verificado_matricula = True
    for est, documento, datos in cambios_documento:
        # El documento viejo queda en el historial (constancias ya expedidas).
        db.add(
            models.HistorialDocumentoEstudiante(
                estudiante_id=est.id, tipo_documento=est.tipo_documento, documento=est.documento
            )
        )
        est.documento = documento
        for campo in CAMPOS.values():
            setattr(est, campo, datos[campo])
        est.verificado_matricula = True
    if args.faltantes != "nada":
        for est in faltantes:
            est.posible_retirado = True
            est.retirado = args.faltantes == "retirado"
    db.commit()
    print(
        f"Listo: {len(nuevos)} creados, {len(actualizados)} actualizados, "
        f"{len(cambios_documento)} con documento corregido, "
        f"{0 if args.faltantes == 'nada' else len(faltantes)} marcados como "
        f"{'retirado' if args.faltantes == 'retirado' else 'posible retiro'}."
    )


if __name__ == "__main__":
    sys.exit(main())
