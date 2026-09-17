"""Importa el horario de la Sede #01 I.E.T.A.B.A. a la tabla BloqueHorario.

Fuentes:
  · HORARIO DOCENTES FINAL 20 DE ABRIL DE 2026.docx  (un cuadro por docente)
  · HORARIOS DOCENTES NUEVOS.xlsx                     (docentes agregados después)

Uso:
    ./venv/Scripts/python.exe importar_horario.py
    ./venv/Scripts/python.exe importar_horario.py --anio 2026
    ./venv/Scripts/python.exe importar_horario.py --docx "ruta.docx" --xlsx "ruta.xlsx"
    ./venv/Scripts/python.exe importar_horario.py --sin-xlsx      (solo el Word)

No crea docentes ni áreas: empareja cada nombre/rótulo con los registros ya
existentes. Lo que no empareje se imprime al final para revisarlo a mano. Es
idempotente: borra el horario del año en la Sede #01 y lo reinserta.
"""

import argparse
import datetime as dt
import re
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl
from sqlalchemy import select
from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from app import models
from app.database import Base, SessionLocal, engine
from app.horario import (
    FRANJAS,
    SEDE_HORARIO_ID,
    etiqueta_grupo,
    matchear_area,
    matchear_docente,
    normalizar,
    soltar_reemplazos_de_bloques,
)

CARPETA = Path(
    r"D:\ietaba\ARCHIVO INGENIERO\HORARIO ULTIMO ultimo AJUSTE 21 DE ABRIL 2026\VD"
)
# Última versión entregada (carpeta VD). Las anteriores quedan como referencia:
#   ..\HORARIO DOCENTES FINAL 20 DE ABRIL DE 2026.docx  /  ..\HORARIOS DOCENTES NUEVOS.xlsx
RUTA_DOCX = CARPETA / "horario 2026 Docente (2).docx 15 de abril-1.docx"
RUTA_XLSX = CARPETA / "HORARIOS GRADO NUEVOS(1)-1.xlsx"
ORIGEN_DOCX = "horario 2026 Docente (VD)"
ORIGEN_XLSX = "HORARIOS GRADO NUEVOS (VD)"

# Correcciones confirmadas con el colegio de errores de rótulo en los archivos.
# El cuadro que el Word (VD) titula "ARTEAGA CAROLINA" es, celda por celda, el
# horario que en el archivo anterior era de JONATHAN VILLOTA; el horario real de
# ARTEAGA está en el Excel. Clave = nombre del cuadro normalizado.
CORRECCION_NOMBRE_CUADRO = {
    "ARTEAGA CAROLINA": "JONATHAN VILLOTA",
}

# Grupo en la celda: "6-2" suelto (Word) o "GRADO 6-6" (Excel), o solo el grado.
RE_GRUPO_WORD = re.compile(r"^\s*(\d{1,2})(?:\s*-\s*(\d))?\s*$")
RE_GRUPO_GRADO = re.compile(r"\bGRADO\s+(\d{1,2})\s*-\s*(\d)\b")
RE_GRUPO_XY = re.compile(r"\b(\d{1,2})\s*-\s*(\d)\b")
RE_GRUPO_BARE = re.compile(r"(\d{1,2})\s*$")


def _limpiar(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").replace("\n", " ")).strip()


# --- Fuente 1: el Word (un cuadro por docente) ----------------------------


def iter_block_items(doc):
    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, doc)
        elif isinstance(child, CT_Tbl):
            yield Table(child, doc)


def parsear_celda_word(texto: str):
    """'COMUNICACION\\n\\n6-2' -> ('COMUNICACION', 6, 2). None si vacía/ilegible."""
    partes = [p.strip() for p in re.split(r"[\n\r]+", texto) if p.strip()]
    if not partes:
        return None
    for i in range(len(partes) - 1, -1, -1):
        m = RE_GRUPO_WORD.match(partes[i])
        if m:
            grado = int(m.group(1))
            curso = int(m.group(2)) if m.group(2) else None
            resto = partes[:i] + partes[i + 1 :]
            return (normalizar(" ".join(resto)) if resto else ""), grado, curso
    return None


def extraer_bloques_word(ruta: Path):
    doc = Document(str(ruta))
    bloques, avisos = [], []
    ultimo_nombre = None
    for bloque in iter_block_items(doc):
        if isinstance(bloque, Paragraph):
            t = bloque.text.strip()
            if t:
                ultimo_nombre = t
            continue
        if ultimo_nombre is None:
            avisos.append("Tabla sin nombre de docente antes: se omite")
            continue
        nombre_docente = ultimo_nombre
        ultimo_nombre = None
        corregido = CORRECCION_NOMBRE_CUADRO.get(normalizar(nombre_docente))
        if corregido:
            avisos.append(
                f"cuadro '{nombre_docente}' se importa como '{corregido}' "
                f"(error de rótulo confirmado — es el horario de VILLOTA)"
            )
            nombre_docente = corregido
        filas = bloque.rows
        if len(filas) < 2:
            avisos.append(f"{nombre_docente}: tabla demasiado corta, se omite")
            continue
        hora = 0
        for fila in filas[1:]:
            celdas = fila.cells
            if celdas and normalizar(celdas[0].text).startswith("DESCANSO"):
                continue
            hora += 1
            if hora > len(FRANJAS):
                break
            for col in range(1, min(6, len(celdas))):
                parsed = parsear_celda_word(celdas[col].text)
                if parsed is None:
                    continue
                area_label, grado, curso = parsed
                bloques.append(
                    {
                        "nombre_docente": nombre_docente,
                        "area_label": area_label,
                        "grado": grado,
                        "curso": curso,
                        "dia": col,
                        "hora": hora,
                    }
                )
    return bloques, avisos


# --- Fuente 2: el Excel "HORARIOS DOCENTES NUEVOS" -----------------------


def parsear_celda_xlsx(texto: str):
    """'ETICA GRADO 8-1' -> ('ETICA', 8, 1). 'TALENTO 6-6' -> ('TALENTO', 6, 6)."""
    t = _limpiar(texto).upper()
    if not t:
        return None
    for rx in (RE_GRUPO_GRADO, RE_GRUPO_XY):
        m = rx.search(t)
        if m:
            area = re.sub(r"\bGRADO\b\s*$", "", t[: m.start()]).strip()
            return area, int(m.group(1)), int(m.group(2))
    m = RE_GRUPO_BARE.search(t)
    if m and not t[: m.start()].strip().endswith("-"):
        area = re.sub(r"\bGRADO\b\s*$", "", t[: m.start()]).strip()
        if area:  # evita celdas que son solo un número suelto
            return area, int(m.group(1)), None
    return None


def extraer_bloques_xlsx(ruta: Path):
    wb = openpyxl.load_workbook(str(ruta), data_only=True)
    bloques, avisos = [], []
    for nombre_hoja in wb.sheetnames:
        filas = [
            [("" if c is None else str(c)) for c in row]
            for row in wb[nombre_hoja].iter_rows(values_only=True)
        ]
        idx_encab = next(
            (i for i, f in enumerate(filas) if f and _limpiar(f[0]).upper() == "HORA"), None
        )
        if idx_encab is None:
            avisos.append(f"hoja '{nombre_hoja}': sin encabezado HORA, se omite")
            continue

        docente_cel = ""
        for f in filas[:idx_encab]:
            for j, c in enumerate(f):
                if "HORARIO DE CLASES" in _limpiar(c).upper() and j + 1 < len(f):
                    docente_cel = _limpiar(f[j + 1])
                    break
            if docente_cel:
                break
        nombre_docente = re.sub(r"^\s*DOCENTE\s*:?\s*", "", docente_cel, flags=re.I).strip()

        if (
            re.match(r"^\s*HOJA\s*\d", nombre_hoja, re.I)
            or not nombre_docente
            or nombre_docente.upper().startswith("GRADO")
        ):
            avisos.append(
                f"hoja '{nombre_hoja}' (docente '{docente_cel or '?'}'): borrador o vista por "
                f"grupo — NO se importa, revisar a mano"
            )
            continue

        hora = 0
        for f in filas[idx_encab + 1 :]:
            if f and _limpiar(f[0]).upper().startswith("DESCANSO"):
                continue
            hora += 1
            if hora > len(FRANJAS):
                break
            for col in range(1, min(6, len(f))):
                parsed = parsear_celda_xlsx(f[col])
                if parsed is None:
                    continue
                area_label, grado, curso = parsed
                bloques.append(
                    {
                        "nombre_docente": nombre_docente,
                        "nombre_hoja": nombre_hoja.strip(),
                        "area_label": area_label,
                        "grado": grado,
                        "curso": curso,
                        "dia": col,
                        "hora": hora,
                    }
                )
    return bloques, avisos


# --- Procesamiento común ------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docx", default=str(RUTA_DOCX))
    parser.add_argument("--xlsx", default=str(RUTA_XLSX))
    parser.add_argument("--sin-xlsx", action="store_true", help="importar solo el Word")
    parser.add_argument("--anio", type=int, default=dt.date.today().year)
    args = parser.parse_args()

    fuentes = []  # (origen, ruta, extractor)
    if Path(args.docx).exists():
        fuentes.append((ORIGEN_DOCX, Path(args.docx), extraer_bloques_word))
    else:
        print(f"AVISO: no se encontró el Word: {args.docx}")
    if not args.sin_xlsx:
        if Path(args.xlsx).exists():
            fuentes.append((ORIGEN_XLSX, Path(args.xlsx), extraer_bloques_xlsx))
        else:
            print(f"AVISO: no se encontró el Excel: {args.xlsx}")
    if not fuentes:
        print("No hay ningún archivo de horario para importar.")
        sys.exit(1)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        docentes = list(db.query(models.Docente).all())
        areas = list(db.query(models.Area).all())
        cache_doc: dict[str, models.Docente | None] = {}
        cache_area: dict[str, models.Area | None] = {}

        por_docente_slot: dict[tuple, dict] = {}  # (docente_id, dia, hora) -> bloque
        por_slot: dict[tuple, set[int]] = defaultdict(set)  # (grado, curso, dia, hora) -> docente_ids
        no_encontrados: dict[str, set[str]] = defaultdict(set)  # origen -> nombres
        areas_no_mapeadas: set[str] = set()
        conflictos_fuentes: list[str] = []
        avisos_todos: list[str] = []
        leidas: dict[str, int] = {}
        insertadas: dict[str, int] = defaultdict(int)
        # (docente_id) -> {origen: {"nombre_archivo": str, "celdas": int}}
        docente_por_origen: dict[int, dict] = defaultdict(dict)

        for origen, ruta, extractor in fuentes:
            crudos, avisos = extractor(ruta)
            leidas[origen] = len(crudos)
            avisos_todos += [f"[{origen}] {a}" for a in avisos]

            for c in crudos:
                nom = c["nombre_docente"]
                clave_doc = (origen, nom)
                if clave_doc not in cache_doc:
                    d = matchear_docente(nom, docentes)
                    # El nombre del recuadro no siempre casa (p. ej. el cuadro
                    # dice "LUIS ANTONIO RODRIGUEZ" pero la hoja se llama "JESUS
                    # ANTONIO RODRIGUEZ"): se prueba también el nombre de la hoja.
                    if d is None and c.get("nombre_hoja"):
                        d = matchear_docente(c["nombre_hoja"], docentes)
                    cache_doc[clave_doc] = d
                docente = cache_doc[clave_doc]
                if docente is None:
                    etq = nom + (f" / hoja '{c['nombre_hoja']}'" if c.get("nombre_hoja") else "")
                    no_encontrados[origen].add(etq)
                    continue

                reg = docente_por_origen[docente.id].setdefault(
                    origen, {"nombre_archivo": nom, "celdas": 0}
                )
                reg["celdas"] += 1

                label = c["area_label"]
                if label not in cache_area:
                    cache_area[label] = matchear_area(label, areas)
                area = cache_area[label]
                if area is None and label:
                    areas_no_mapeadas.add(label)

                por_slot[(c["grado"], c["curso"], c["dia"], c["hora"])].add(docente.id)
                clave = (docente.id, c["dia"], c["hora"])
                nuevo = {
                    "docente_id": docente.id,
                    "area_id": area.id if area else None,
                    "area_label": label,
                    "grado": c["grado"],
                    "curso": c["curso"],
                    "dia": c["dia"],
                    "hora": c["hora"],
                    "origen": origen,
                }
                previo = por_docente_slot.get(clave)
                if previo and previo["origen"] != origen:
                    conflictos_fuentes.append(
                        f"{docente.nombre_completo} día {c['dia']} hora {c['hora']}: "
                        f"'{previo['origen']}' dice {previo['area_label']} "
                        f"{etiqueta_grupo(previo['grado'], previo['curso'])}, "
                        f"'{origen}' dice {label} {etiqueta_grupo(c['grado'], c['curso'])} "
                        f"(se mantiene el primero)"
                    )
                    continue
                por_docente_slot[clave] = nuevo

        for b in por_docente_slot.values():
            insertadas[b["origen"]] += 1

        # Docentes que tenían horario ANTES de esta importación (para avisar si
        # alguno se quedó sin clases con los archivos nuevos).
        _ids_previos = set(
            db.scalars(
                select(models.BloqueHorario.docente_id)
                .where(
                    models.BloqueHorario.anio_lectivo == args.anio,
                    models.BloqueHorario.sede_id == SEDE_HORARIO_ID,
                )
                .distinct()
            ).all()
        )

        # Idempotencia: borra el horario de ese año/sede y reinserta. Los
        # reemplazos sueltan antes su enlace al bloque viejo (si no, las
        # claves foráneas impiden el borrado) y se re-enlazan justo abajo.
        soltar_reemplazos_de_bloques(
            db,
            select(models.BloqueHorario.id).where(
                models.BloqueHorario.anio_lectivo == args.anio,
                models.BloqueHorario.sede_id == SEDE_HORARIO_ID,
            ),
        )
        borrados = (
            db.query(models.BloqueHorario)
            .filter(
                models.BloqueHorario.anio_lectivo == args.anio,
                models.BloqueHorario.sede_id == SEDE_HORARIO_ID,
            )
            .delete()
        )
        for b in por_docente_slot.values():
            db.add(models.BloqueHorario(anio_lectivo=args.anio, sede_id=SEDE_HORARIO_ID, **b))
        db.flush()

        # Re-enlaza ausencias/reemplazos existentes al bloque equivalente del
        # horario nuevo (mismo docente ausente, día y hora); si esa clase ya no
        # existe, el reemplazo queda huérfano y se cuenta para avisar.
        nuevos_por_slot = {
            (bl.docente_id, bl.dia, bl.hora): bl.id
            for bl in db.scalars(
                select(models.BloqueHorario).where(
                    models.BloqueHorario.anio_lectivo == args.anio,
                    models.BloqueHorario.sede_id == SEDE_HORARIO_ID,
                )
            )
        }
        reemplazos_relinkeados = reemplazos_huerfanos = 0
        for r in db.scalars(select(models.Reemplazo)):
            nuevo_id = nuevos_por_slot.get((r.docente_ausente_id, r.dia, r.hora))
            if nuevo_id:
                if r.bloque_horario_id != nuevo_id:
                    r.bloque_horario_id = nuevo_id
                    reemplazos_relinkeados += 1
            elif r.estado != "cancelado":
                reemplazos_huerfanos += 1
        db.commit()

        choques = {s: ids for s, ids in por_slot.items() if len(ids) > 1}
        grupos_horario = {(b["grado"], b["curso"]) for b in por_docente_slot.values()}
        grupos_sin_estudiantes = []
        for grado, curso in sorted(grupos_horario):
            q = db.query(models.Estudiante).filter(
                models.Estudiante.sede_id == SEDE_HORARIO_ID,
                models.Estudiante.grado == grado,
                models.Estudiante.estado == "ACTIVO",
            )
            if curso is not None:
                q = q.filter(models.Estudiante.curso == curso)
            if q.count() == 0:
                grupos_sin_estudiantes.append(etiqueta_grupo(grado, curso))

        print(f"\nAño lectivo {args.anio} · Sede #01 · bloques borrados: {borrados}")
        for origen in leidas:
            emparejados = len({d.id for (o, _), d in cache_doc.items() if o == origen and d})
            print(
                f"  · {origen}: {leidas[origen]} celdas leidas -> {insertadas[origen]} bloques, "
                f"{emparejados} docentes emparejados"
            )
        print(f"  TOTAL insertado: {len(por_docente_slot)} bloques")
        if reemplazos_relinkeados or reemplazos_huerfanos:
            print(
                f"  Reemplazos re-enlazados al horario nuevo: {reemplazos_relinkeados}"
                + (f" · huérfanos (esa clase ya no existe): {reemplazos_huerfanos}" if reemplazos_huerfanos else "")
            )

        if avisos_todos:
            print(f"\n--- Avisos de estructura / hojas omitidas ({len(avisos_todos)}) ---")
            for a in avisos_todos:
                print(f"  · {a}")
        for origen, nombres in no_encontrados.items():
            print(f"\n--- [{origen}] Docentes NO emparejados ({len(nombres)}) — revisar a mano ---")
            for n in sorted(nombres):
                print(f"  · {n}")
        if areas_no_mapeadas:
            print(f"\n--- Áreas sin código de catálogo ({len(areas_no_mapeadas)}) — se guardan con el rótulo crudo ---")
            for a in sorted(areas_no_mapeadas):
                print(f"  · {a}")
        en_ambos = {did: v for did, v in docente_por_origen.items() if len(v) > 1}
        if en_ambos:
            print(f"\n--- Docentes que aparecen en LOS DOS archivos ({len(en_ambos)}) ---")
            for did, v in sorted(en_ambos.items()):
                d = db.get(models.Docente, did)
                partes = ", ".join(
                    f"'{o}' ({info['nombre_archivo']}, {info['celdas']} celdas)"
                    for o, info in v.items()
                )
                print(f"  · {d.nombre_completo}: {partes}")
        if conflictos_fuentes:
            print(f"\n--- Choque directo: un docente con clases distintas en la MISMA franja entre archivos ({len(conflictos_fuentes)}) ---")
            for c in conflictos_fuentes:
                print(f"  · {c}")

        # Docentes que tenían horario y ahora quedaron sin ningún bloque.
        ids_con_bloque = {b["docente_id"] for b in por_docente_slot.values()}
        perdieron = sorted(
            db.get(models.Docente, i).nombre_completo for i in _ids_previos - ids_con_bloque
        )
        if perdieron:
            print(f"\n--- Docentes que TENÍAN horario y ahora quedaron SIN clases ({len(perdieron)}) ---")
            for n in perdieron:
                print(f"  · {n}")

        if choques:
            print(f"\n--- Choques (mismo grupo, dos docentes a la misma hora) ({len(choques)}) ---")
            for (grado, curso, dia, hora), ids in sorted(choques.items()):
                nombres = [db.get(models.Docente, i).nombre_completo for i in ids]
                print(f"  · {etiqueta_grupo(grado, curso)} día {dia} hora {hora}: {', '.join(nombres)}")
        if grupos_sin_estudiantes:
            print(f"\n--- Grupos del horario sin estudiantes activos en Sede #01 ({len(grupos_sin_estudiantes)}) ---")
            print("  " + ", ".join(grupos_sin_estudiantes))
        print("\nListo.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
