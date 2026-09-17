"""Importa la base de datos real de estudiantes del IETABA.

La fuente AUTORITATIVA es el Excel de matrÃ­cula (B.D. MATRICULA), porque es
la base de datos oficial de la secretarÃ­a. La "LISTA DE ASISTENCIA" es solo
un formato/reporte derivado y puede tener errores, asÃ­ que:

  1. Todo lo que venga de B.D. MATRICULA manda (y queda marcado como
     verificado).
  2. La LISTA DE ASISTENCIA solo se usa para completar las sedes que NO
     tienen un Excel de matrÃ­cula propio todavÃ­a (las 47 sedes rurales
     ademÃ¡s de la sede principal).
  3. Si un estudiante aparece en la lista de asistencia de una sede que SÃ
     tiene Excel de matrÃ­cula (hoy, la sede principal) pero no estÃ¡ en ese
     Excel, se importa igual pero queda marcado como NO verificado, y se
     reporta al final como posible error de la lista de asistencia.

Uso:
    python importar_matricula.py

(las rutas de los dos archivos estÃ¡n fijas abajo; edÃ­talas si cambian de
carpeta)
"""

import datetime as dt
from pathlib import Path

import openpyxl

from app import models
from app.database import Base, SessionLocal, engine

RUTA_MATRICULA = (
    r"D:\ietaba\ARCHIVO INGENIERO\B.D. MATRICULA INST. IETABA - última Actualización ABRIL 22.xlsx"
)
HOJA_MATRICULA = "B.D. ESTUDIANTES"

RUTA_ASISTENCIA = (
    r"D:\ietaba\ARCHIVO INGENIERO\1 LISTA DE ASISTENCIA INST. EDU. IETABA X GRADOS.xlsx"
)
HOJA_ASISTENCIA = "B.D. ORIGNAL"


def parsear_fecha(valor) -> dt.date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    if isinstance(valor, str):
        for formato in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return dt.datetime.strptime(valor.strip(), formato).date()
            except ValueError:
                continue
    return None


def texto(valor) -> str | None:
    if valor is None:
        return None
    texto_limpio = str(valor).strip()
    return texto_limpio or None


def pertenece_a_ietaba(institucion: str | None) -> bool:
    if not institucion:
        return True
    institucion_normalizada = institucion.upper()
    return "IETABA" in institucion_normalizada or "AGROAMBIENTAL BILING" in institucion_normalizada


def leer_filas(ruta: Path, hoja: str):
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    ws = wb[hoja]
    filas = ws.iter_rows(values_only=True)
    encabezado = next(filas)
    col = {nombre: i for i, nombre in enumerate(encabezado)}
    return col, list(filas)


def columna_por_texto(col: dict, texto_buscado: str) -> int:
    texto_buscado = texto_buscado.upper()
    for nombre, indice in col.items():
        if texto_buscado in str(nombre).upper():
            return indice
    raise KeyError(texto_buscado)


def obtener_o_crear_sede(db, sedes_cache, nombre_sede, **campos) -> models.Sede:
    sede = sedes_cache.get(nombre_sede)
    if sede is None:
        sede = db.query(models.Sede).filter_by(nombre=nombre_sede).first()
    if sede is None:
        sede = models.Sede(nombre=nombre_sede, **campos)
        db.add(sede)
        db.flush()
    else:
        # Completa metadatos de la sede si nos llegan por primera vez (la
        # hoja de matrÃ­cula, por ejemplo, no trae resguardo/instituciÃ³n).
        for campo, valor in campos.items():
            if valor and not getattr(sede, campo):
                setattr(sede, campo, valor)
    sedes_cache[nombre_sede] = sede
    return sede


def main():
    ruta_matricula = Path(RUTA_MATRICULA)
    ruta_asistencia = Path(RUTA_ASISTENCIA)
    if not ruta_matricula.exists():
        print(f"No se encontrÃ³ el archivo de matrÃ­cula: {ruta_matricula}")
        return
    if not ruta_asistencia.exists():
        print(f"No se encontrÃ³ el archivo de lista de asistencia: {ruta_asistencia}")
        return

    db_path = Path(__file__).resolve().parent / "colegio.db"
    if db_path.exists():
        db_path.unlink()
        print("Base de datos anterior eliminada, se recrearÃ¡ desde cero.")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    sedes_cache: dict[str, models.Sede] = {}

    try:
        # --- 1. Fuente autoritativa: B.D. MATRICULA -------------------------
        col_m, filas_m = leer_filas(ruta_matricula, HOJA_MATRICULA)
        documentos_matricula: set[str] = set()
        sedes_con_matricula: set[str] = set()
        importados_matricula = 0

        for fila in filas_m:
            nombre_sede = texto(fila[col_m["SEDE EDUCATIVA"]])
            documento = texto(fila[col_m["NRO DOCUMENTO"]])
            if not nombre_sede or not documento:
                continue
            sedes_con_matricula.add(nombre_sede)

            sede = obtener_o_crear_sede(
                db,
                sedes_cache,
                nombre_sede,
                codigo_dane_sede=texto(fila[col_m["CODIGO DANE SEDE"]]),
                pertenece_ietaba=True,
            )

            grado_valor = fila[col_m["GRADO"]]
            curso_valor = fila[col_m["CURSO IETABA"]]

            estudiante = models.Estudiante(
                id_estud=texto(fila[col_m["ID ESTUD"]]),
                documento=documento,
                tipo_documento=texto(fila[col_m["TIPO DOCUMENTO"]]),
                primer_apellido=texto(fila[col_m["PRIMER APELLIDO"]]) or "",
                segundo_apellido=texto(fila[col_m["SEGUNDO APELLIDO"]]),
                primer_nombre=texto(fila[col_m["PRIMER NOMBRE"]]) or "",
                segundo_nombre=texto(fila[col_m["SEGUNDO NOMBRE"]]),
                fecha_nacimiento=parsear_fecha(fila[col_m["FECHA NACIMIENTO"]]),
                genero=texto(fila[col_m["GENERO"]]),
                grado=int(grado_valor) if grado_valor is not None else 0,
                curso=int(curso_valor) if curso_valor is not None else None,
                estado="ACTIVO",
                verificado_matricula=True,
                sede_id=sede.id,
            )
            db.add(estudiante)
            documentos_matricula.add(documento)
            importados_matricula += 1

        db.flush()
        print(
            f"B.D. MATRICULA (fuente autoritativa): {importados_matricula} estudiantes "
            f"en {len(sedes_con_matricula)} sede(s)."
        )

        # --- 2. Completar con la LISTA DE ASISTENCIA -------------------------
        col_a, filas_a = leer_filas(ruta_asistencia, HOJA_ASISTENCIA)
        col_institucion = columna_por_texto(col_a, "CENTRO EDUCATIVO")
        agregados_desde_asistencia = 0
        sin_verificar = []

        for fila in filas_a:
            nombre_sede = texto(fila[col_a["SEDE EDUCATIVA"]])
            documento = texto(fila[col_a["NRO DOCUMENTO"]])
            if not nombre_sede or not documento:
                continue
            institucion = texto(fila[col_institucion])

            sede = obtener_o_crear_sede(
                db,
                sedes_cache,
                nombre_sede,
                codigo_dane_sede=texto(fila[col_a["CODIGO DANE SEDE"]]),
                codigo_dane_consecutivo=texto(fila[col_a["CODIGO DANE CONSECUTIVO"]]),
                institucion_centro_educativo=institucion,
                resguardo=texto(fila[col_a["RESGUARDO"]]),
                pertenece_ietaba=pertenece_a_ietaba(institucion),
            )
            if documento in documentos_matricula:
                continue  # Ya lo trajimos, con prioridad, desde B.D. MATRICULA.

            grado_valor = fila[col_a["MATRICULA VIGENCIA 2026"]]
            # Si la sede sÃ­ tiene Excel de matrÃ­cula pero este documento no
            # apareciÃ³ allÃ­, es una inconsistencia real: se importa pero se
            # marca como NO verificado para poder avisar.
            verificado = False if nombre_sede in sedes_con_matricula else None

            estudiante = models.Estudiante(
                id_estud=texto(fila[col_a["ID ESTUD"]]),
                documento=documento,
                tipo_documento=texto(fila[col_a["TIPO DOCUMENTO"]]),
                primer_apellido=texto(fila[col_a["PRIMER APELLIDO"]]) or "",
                segundo_apellido=texto(fila[col_a["SEGUNDO APELLIDO"]]),
                primer_nombre=texto(fila[col_a["PRIMER NOMBRE"]]) or "",
                segundo_nombre=texto(fila[col_a["SEGUNDO NOMBRE"]]),
                fecha_nacimiento=parsear_fecha(fila[col_a["FECHA NACIMIENTO"]]),
                genero=texto(fila[col_a["GENERO"]]),
                grado=int(grado_valor) if grado_valor is not None else 0,
                estado=texto(fila[col_a["ESTADO 2026"]]) or "ACTIVO",
                verificado_matricula=verificado,
                sede_id=sede.id,
            )
            db.add(estudiante)
            agregados_desde_asistencia += 1
            if verificado is False:
                sin_verificar.append(estudiante)

        db.commit()
        print(
            f"LISTA DE ASISTENCIA (relleno de sedes sin matrÃ­cula propia): "
            f"{agregados_desde_asistencia} estudiantes agregados."
        )
        print(f"Total en la base de datos: {importados_matricula + agregados_desde_asistencia} estudiantes.")

        if sin_verificar:
            print()
            print(
                f"âš  ADVERTENCIA: {len(sin_verificar)} estudiante(s) estÃ¡n en la LISTA DE "
                "ASISTENCIA de una sede que sÃ­ tiene Excel de matrÃ­cula, pero NO aparecen "
                "en ese Excel de matrÃ­cula (posible error en la lista de asistencia):"
            )
            for e in sin_verificar:
                print(f"  - {e.documento}  {e.primer_apellido} {e.primer_nombre}  ({e.sede.nombre})")
        else:
            print("Sin inconsistencias: todos los estudiantes de sedes con matrÃ­cula propia cuadran.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

