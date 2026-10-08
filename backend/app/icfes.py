"""Resultados Saber 11 del ICFES: importación y análisis entre años.

Los datos vienen de PRISMA (Publicación de Resultados → Consulta Plantel) y los
trae backend/importar_icfes.py. Aquí solo se guardan y se analizan:

- panorama(): una fila por año (promedios, niveles de desempeño, percentil
  nacional) + cambios año a año por prueba + hallazgos en palabras.
- estudiantes_anio(): la lista de un año, con puesto y prueba más débil.
- ficha(): un estudiante frente al promedio del colegio en su año.

Un año junta todos sus períodos de aplicación (el ICFES publica la aplicación
principal y, aparte, unas pocas pruebas tardías o de validantes).
"""

import json
import statistics as st
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .texto import sin_tildes

PRUEBAS = ["lc", "mat", "syc", "cn", "ing"]
NOMBRE_PRUEBA = {
    "lc": "Lectura crítica",
    "mat": "Matemáticas",
    "syc": "Sociales y ciudadanas",
    "cn": "Ciencias naturales",
    "ing": "Inglés",
}
# Encabezados de la tabla del ICFES → columna
COLUMNA_ICFES = {"LC": "lc", "MAT": "mat", "SYC": "syc", "CN": "cn", "ING": "ing"}

# Niveles de desempeño del ICFES para Saber 11 (escala 0-100 por prueba).
# Inglés usa los niveles del Marco Común Europeo.
NIVELES = {
    "lc": [(0, 35, "1"), (36, 50, "2"), (51, 65, "3"), (66, 100, "4")],
    "mat": [(0, 35, "1"), (36, 50, "2"), (51, 70, "3"), (71, 100, "4")],
    "syc": [(0, 40, "1"), (41, 55, "2"), (56, 70, "3"), (71, 100, "4")],
    "cn": [(0, 40, "1"), (41, 55, "2"), (56, 70, "3"), (71, 100, "4")],
    "ing": [(0, 47, "A-"), (48, 57, "A1"), (58, 67, "A2"), (68, 78, "B1"), (79, 100, "B+")],
}
NIVEL_MAS_BAJO = {p: NIVELES[p][0][2] for p in PRUEBAS}

# Cambio entre años que se considera real y no ruido (puntos de la escala).
TENDENCIA_PRUEBA = 1.0      # por prueba, escala 0-100
TENDENCIA_GLOBAL = 5.0      # puntaje global, escala 0-500
# Con menos estudiantes que esto un año no se compara (un puñado de validantes
# no dice nada del colegio).
MIN_ESTUDIANTES_ANIO = 10


def nivel(prueba: str, puntaje: int | None) -> str | None:
    if puntaje is None:
        return None
    for desde, hasta, n in NIVELES[prueba]:
        if desde <= puntaje <= hasta:
            return n
    return None


def _media(valores):
    v = [x for x in valores if x is not None]
    return round(st.mean(v), 1) if v else None


def _nombre_normalizado(texto: str) -> str:
    return " ".join(sin_tildes(texto).split())


# --- Importación ------------------------------------------------------------


def importar(db: Session, filas: list[dict]) -> dict:
    """Inserta o actualiza por número de registro. `filas` es la salida del
    extractor: {anio, periodo, registro, nombre, puntajes{LC..}, percentil_nacional{..},
    percentil_especial{..}, percentil_global, puntaje_global}."""
    existentes = {r.registro: r for r in db.scalars(select(models.ResultadoIcfes))}
    nuevos = actualizados = 0
    for f in filas:
        r = existentes.get(f["registro"])
        if r is None:
            r = models.ResultadoIcfes(registro=f["registro"])
            db.add(r)
            existentes[f["registro"]] = r
            nuevos += 1
        else:
            actualizados += 1
        r.anio, r.periodo, r.nombre = int(f["anio"]), int(f["periodo"]), f["nombre"].strip()
        for icfes, col in COLUMNA_ICFES.items():
            setattr(r, col, f["puntajes"].get(icfes))
            setattr(r, "pct_" + col, f["percentil_nacional"].get(icfes))
        r.puntaje_global = f.get("puntaje_global")
        r.percentil_global = f.get("percentil_global")
        especiales = {k: v for k, v in (f.get("percentil_especial") or {}).items() if v is not None}
        r.percentiles_especiales = json.dumps(especiales) if especiales else None
    db.flush()
    vinculados = vincular_estudiantes(db)
    db.commit()
    return {"nuevos": nuevos, "actualizados": actualizados, "vinculados": vinculados}


def vincular_estudiantes(db: Session) -> int:
    """Une cada resultado con su estudiante por nombre completo (nombres +
    apellidos, sin tildes). Solo si hay exactamente UNA coincidencia: un nombre
    repetido en la base queda sin vincular antes que vincularse mal."""
    por_nombre = defaultdict(list)
    for e in db.scalars(select(models.Estudiante)):
        completo = " ".join(x for x in (e.primer_nombre, e.segundo_nombre, e.primer_apellido, e.segundo_apellido) if x)
        por_nombre[_nombre_normalizado(completo)].append(e.id)
    n = 0
    for r in db.scalars(select(models.ResultadoIcfes)):
        ids = por_nombre.get(_nombre_normalizado(r.nombre), [])
        r.estudiante_id = ids[0] if len(ids) == 1 else None
        n += r.estudiante_id is not None
    return n


# --- Análisis ---------------------------------------------------------------


def _resultados(db: Session) -> list[models.ResultadoIcfes]:
    return list(db.scalars(select(models.ResultadoIcfes).order_by(models.ResultadoIcfes.anio)))


def _resumen_anio(anio: int, filas: list[models.ResultadoIcfes]) -> dict:
    globales = [r.puntaje_global for r in filas if r.puntaje_global is not None]
    res = {
        "anio": anio,
        "n": len(filas),
        "periodos": sorted({r.periodo for r in filas}),
        "comparable": len(filas) >= MIN_ESTUDIANTES_ANIO,
        "global": _media(globales),
        "global_de": round(st.pstdev(globales), 1) if len(globales) > 1 else None,
        "global_max": max(globales) if globales else None,
        "global_min": min(globales) if globales else None,
        "pruebas": {},
    }
    for p in PRUEBAS:
        punt = [getattr(r, p) for r in filas if getattr(r, p) is not None]
        pct = [getattr(r, "pct_" + p) for r in filas if getattr(r, "pct_" + p) is not None]
        conteo = defaultdict(int)
        for x in punt:
            conteo[nivel(p, x)] += 1
        res["pruebas"][p] = {
            "n": len(punt),
            "promedio": _media(punt),
            "percentil": _media(pct),
            "niveles": {n: (round(100 * conteo[n] / len(punt)) if punt else None) for *_, n in NIVELES[p]},
            "pct_nivel_bajo": round(100 * conteo[NIVEL_MAS_BAJO[p]] / len(punt)) if punt else None,
        }
    return res


def _tendencia(delta: float | None, umbral: float) -> str | None:
    if delta is None:
        return None
    return "mejoro" if delta >= umbral else "empeoro" if delta <= -umbral else "estable"


def panorama(db: Session) -> dict:
    por_anio = defaultdict(list)
    for r in _resultados(db):
        por_anio[r.anio].append(r)
    anios = [_resumen_anio(a, por_anio[a]) for a in sorted(por_anio)]

    # Cambios entre años comparables consecutivos (se saltan los años con muy pocos estudiantes)
    comparables = [a for a in anios if a["comparable"]]
    cambios = []
    for ant, act in zip(comparables, comparables[1:]):
        c = {"desde": ant["anio"], "hasta": act["anio"], "pruebas": {}}
        dg = round(act["global"] - ant["global"], 1) if act["global"] is not None and ant["global"] is not None else None
        c["global"] = {"delta": dg, "tendencia": _tendencia(dg, TENDENCIA_GLOBAL)}
        for p in PRUEBAS:
            a, b = ant["pruebas"][p], act["pruebas"][p]
            d = round(b["promedio"] - a["promedio"], 1) if a["promedio"] is not None and b["promedio"] is not None else None
            dp = round(b["percentil"] - a["percentil"], 1) if a["percentil"] is not None and b["percentil"] is not None else None
            db_ = (b["pct_nivel_bajo"] - a["pct_nivel_bajo"]) if a["pct_nivel_bajo"] is not None and b["pct_nivel_bajo"] is not None else None
            c["pruebas"][p] = {"delta": d, "delta_percentil": dp, "delta_nivel_bajo": db_,
                               "tendencia": _tendencia(d, TENDENCIA_PRUEBA)}
        cambios.append(c)

    return {
        "anios": anios,
        "cambios": cambios,
        "hallazgos": _hallazgos(comparables, cambios),
        "pruebas": [{"codigo": p, "nombre": NOMBRE_PRUEBA[p], "niveles": [n for *_, n in NIVELES[p]],
                     "nivel_bajo": NIVEL_MAS_BAJO[p]} for p in PRUEBAS],
        "umbrales": {"prueba": TENDENCIA_PRUEBA, "global": TENDENCIA_GLOBAL, "min_estudiantes": MIN_ESTUDIANTES_ANIO},
        "excluidos": [{"anio": a["anio"], "n": a["n"]} for a in anios if not a["comparable"]],
    }


def _hallazgos(comparables: list[dict], cambios: list[dict]) -> list[dict]:
    """Frases calculadas (nunca a mano): qué cambió en el último año, en todo el
    período y cuál es hoy la prueba más débil."""
    h = []
    if not comparables:
        return h
    if cambios:
        c = cambios[-1]
        sube = sorted([(p, v["delta"]) for p, v in c["pruebas"].items() if v["tendencia"] == "mejoro"], key=lambda x: -x[1])
        baja = sorted([(p, v["delta"]) for p, v in c["pruebas"].items() if v["tendencia"] == "empeoro"], key=lambda x: x[1])
        g = c["global"]
        if g["delta"] is not None:
            verbo = {"mejoro": "subió", "empeoro": "bajó", "estable": "se mantuvo"}[g["tendencia"]]
            h.append({"tipo": g["tendencia"], "texto": f"De {c['desde']} a {c['hasta']} el puntaje global promedio {verbo} "
                      f"({g['delta']:+.1f} puntos)."})
        if sube:
            h.append({"tipo": "mejoro", "texto": f"Mejoró en {c['hasta']}: " + ", ".join(f"{NOMBRE_PRUEBA[p]} ({d:+.1f})" for p, d in sube) + "."})
        if baja:
            h.append({"tipo": "empeoro", "texto": f"Empeoró en {c['hasta']}: " + ", ".join(f"{NOMBRE_PRUEBA[p]} ({d:+.1f})" for p, d in baja) + "."})
    if len(comparables) >= 3:
        pri, ult = comparables[0], comparables[-1]
        largos = []
        for p in PRUEBAS:
            a, b = pri["pruebas"][p]["promedio"], ult["pruebas"][p]["promedio"]
            if a is not None and b is not None:
                largos.append((p, round(b - a, 1)))
        if largos:
            mejor = max(largos, key=lambda x: x[1])
            peor = min(largos, key=lambda x: x[1])
            h.append({"tipo": "info", "texto": f"Desde {pri['anio']} hasta {ult['anio']}: lo que más avanzó fue "
                      f"{NOMBRE_PRUEBA[mejor[0]]} ({mejor[1]:+.1f}) y lo que más retrocedió fue {NOMBRE_PRUEBA[peor[0]]} ({peor[1]:+.1f})."})
    ult = comparables[-1]
    con_datos = [(p, v) for p, v in ult["pruebas"].items() if v["percentil"] is not None]
    if con_datos:
        p, v = min(con_datos, key=lambda x: x[1]["percentil"])
        h.append({"tipo": "atencion", "texto": f"En {ult['anio']} la prueba más débil frente al país es {NOMBRE_PRUEBA[p]}: "
                  f"el estudiante típico supera solo al {v['percentil']:.0f}% del país y el {v['pct_nivel_bajo']}% quedó en el nivel más bajo."})
    return h


def _fila_estudiante(r: models.ResultadoIcfes) -> dict:
    return {
        "id": r.id, "registro": r.registro, "anio": r.anio, "periodo": r.periodo, "nombre": r.nombre,
        "estudiante_id": r.estudiante_id,
        "puntaje_global": r.puntaje_global, "percentil_global": r.percentil_global,
        "pruebas": {p: {"puntaje": getattr(r, p), "percentil": getattr(r, "pct_" + p), "nivel": nivel(p, getattr(r, p))}
                    for p in PRUEBAS},
    }


def estudiantes_anio(db: Session, anio: int) -> dict:
    filas = [r for r in _resultados(db) if r.anio == anio]
    resumen = _resumen_anio(anio, filas)
    orden = sorted(filas, key=lambda r: -(r.puntaje_global or -1))
    lista = []
    for puesto, r in enumerate(orden, 1):
        f = _fila_estudiante(r)
        f["puesto"] = puesto if r.puntaje_global is not None else None
        # Prueba más débil RELATIVA al colegio: la que más se aleja hacia abajo del promedio del año
        difs = [(p, f["pruebas"][p]["puntaje"] - resumen["pruebas"][p]["promedio"])
                for p in PRUEBAS if f["pruebas"][p]["puntaje"] is not None and resumen["pruebas"][p]["promedio"] is not None]
        f["mas_debil"] = min(difs, key=lambda x: x[1])[0] if difs else None
        f["mas_fuerte"] = max(difs, key=lambda x: x[1])[0] if difs else None
        f["en_nivel_bajo"] = [p for p in PRUEBAS if f["pruebas"][p]["nivel"] == NIVEL_MAS_BAJO[p]]
        lista.append(f)
    return {"resumen": resumen, "estudiantes": lista}


def ficha(db: Session, resultado_id: int) -> dict | None:
    r = db.get(models.ResultadoIcfes, resultado_id)
    if r is None:
        return None
    datos = estudiantes_anio(db, r.anio)
    yo = next(f for f in datos["estudiantes"] if f["id"] == r.id)
    res = datos["resumen"]
    yo["comparacion"] = {
        p: {
            "colegio": res["pruebas"][p]["promedio"],
            "diferencia": (round(yo["pruebas"][p]["puntaje"] - res["pruebas"][p]["promedio"], 1)
                           if yo["pruebas"][p]["puntaje"] is not None and res["pruebas"][p]["promedio"] is not None else None),
        }
        for p in PRUEBAS
    }
    yo["colegio_global"] = res["global"]
    yo["total_anio"] = res["n"]
    # Otros resultados del mismo estudiante (si presentó más de una vez)
    yo["otros"] = [
        {"id": o.id, "anio": o.anio, "periodo": o.periodo, "puntaje_global": o.puntaje_global}
        for o in _resultados(db)
        if o.id != r.id and ((r.estudiante_id and o.estudiante_id == r.estudiante_id)
                             or _nombre_normalizado(o.nombre) == _nombre_normalizado(r.nombre))
    ]
    return yo
