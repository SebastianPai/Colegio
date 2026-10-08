"""Pruebas del Análisis académico rediseñado (comparacion_academica.py):
panorama, población, evolución, hallazgos, lista de estudiantes y los
arreglos de datos. Solo LEE colegio.db (nunca escribe).

Cada número se verifica contra un cálculo independiente en SQL/Python puro
sobre las tablas, no contra el mismo motor: si el motor se equivoca, las dos
cuentas no coinciden.

Uso: venv/Scripts/python.exe probar_analisis_academico.py
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app import comparacion_academica as motor, schemas  # noqa: E402
from app.database import SessionLocal  # noqa: E402

BASE, COMP = (2026, 1), (2026, 2)
fallos = []


def ok(cond, texto):
    print(("  OK   " if cond else "  FALLA ") + texto)
    if not cond:
        fallos.append(texto)


def params(**extra):
    p = dict(base=BASE, comparado=COMP, sede_id=None, grado=None, curso=None, area_id=None,
             docente_id=None, estado="ACTIVO", config=schemas.ConfigComparacion())
    p.update(extra)
    return p


# --- Cálculo independiente (SQL + Python, sin el motor) ----------------------

con = sqlite3.connect(Path(__file__).parent / "colegio.db")


def notas_sql(anio, periodo, sede_id=None, area_id=None):
    q = """select n.estudiante_id, n.area_id, cast(n.valor as real)
           from notas_sapred n join revisiones_boletin r on r.id = n.revision_id
           join areas a on a.id = n.area_id join estudiantes e on e.id = n.estudiante_id
           where r.anio_lectivo = ? and r.periodo = ? and a.codigo <> 'DESM' and e.estado = 'ACTIVO'"""
    args = [anio, periodo]
    if sede_id is not None:
        q += " and r.sede_id = ?"
        args.append(sede_id)
    if area_id is not None:
        q += " and n.area_id = ?"
        args.append(area_id)
    d = defaultdict(dict)
    for e, a, v in con.execute(q, args):
        d[e][a] = v
    return d


def independiente(sede_id=None):
    b, c = notas_sql(*BASE, sede_id), notas_sql(*COMP, sede_id)
    comparables = {}
    for e in set(b) & set(c):
        comunes = set(b[e]) & set(c[e])
        if comunes:
            pb = round(sum(b[e][a] for a in comunes) / len(comunes), 2)
            pc = round(sum(c[e][a] for a in comunes) / len(comunes), 2)
            comparables[e] = (pb, pc)
    actual = {e: round(sum(v.values()) / len(v), 2) for e, v in c.items()}
    return b, c, comparables, actual


print("\n1. Resumen y población contra SQL independiente")
db = SessionLocal()
for sede in (None, 1):
    P = motor.panorama(db, params(sede_id=sede))
    r = P.resumen
    b, c, comp, actual = independiente(sede)
    n = len(comp)
    etq = f"[sede={sede}]"
    ok(r.estudiantes_comparables == n, f"{etq} comparables {r.estudiantes_comparables} == SQL {n}")
    ok(r.actual_evaluados == len(actual), f"{etq} evaluados hoy {r.actual_evaluados} == SQL {len(actual)}")
    pb = round(sum(x[0] for x in comp.values()) / n, 2)
    pc = round(sum(x[1] for x in comp.values()) / n, 2)
    ok((r.promedio_base, r.promedio_comparado) == (pb, pc), f"{etq} promedio {r.promedio_base}->{r.promedio_comparado} == SQL {pb}->{pc}")
    ok(r.actual_promedio == round(sum(actual.values()) / len(actual), 2), f"{etq} promedio de hoy == SQL")
    bajo_hoy = sum(1 for v in actual.values() if v < 3.0)
    ok(r.actual_n_bajo == bajo_hoy, f"{etq} en bajo hoy {r.actual_n_bajo} == SQL (<3.0) {bajo_hoy}")
    mej = sum(1 for x in comp.values() if round(x[1] - x[0], 2) >= 0.3)
    emp = sum(1 for x in comp.values() if round(x[1] - x[0], 2) <= -0.3)
    ok((r.mejoraron, r.empeoraron, r.estables) == (mej, emp, n - mej - emp), f"{etq} mejoraron/empeoraron/estables {r.mejoraron}/{r.empeoraron}/{r.estables} == SQL {mej}/{emp}/{n - mej - emp}")
    ok(r.mejoraron + r.empeoraron + r.estables == r.estudiantes_comparables, f"{etq} las tres categorías suman el total comparado (sin huecos ni dobles)")
    entraron = sum(1 for x in comp.values() if x[0] >= 3.0 and x[1] < 3.0)
    ok(r.entraron_a_bajo == entraron, f"{etq} pasaron a bajo {r.entraron_a_bajo} == SQL {entraron}")
    ok(sum(r.distribucion_comparado.values()) == n and sum(r.actual_distribucion.values()) == len(actual), f"{etq} las distribuciones suman su población")
    solo_hoy = sum(1 for e in c if e not in comp)
    ok(r.solo_en_comparado == solo_hoy, f"{etq} solo con el período actual {r.solo_en_comparado} == SQL {solo_hoy}")

print("\n2. Evolución: la cohorte de 2 períodos == el resumen")
P = motor.panorama(db, params())
pts = P.evolucion.puntos
ok(len(pts) == 2 and P.evolucion.cohorte == P.resumen.estudiantes_comparables, f"cohorte {P.evolucion.cohorte} == comparables {P.resumen.estudiantes_comparables}")
ok((pts[0].promedio_cohorte, pts[1].promedio_cohorte) == (P.resumen.promedio_base, P.resumen.promedio_comparado), "línea de tendencia == promedios del resumen")
ok(pts[1].evaluados_todos == P.resumen.actual_evaluados and pts[1].promedio_todos == P.resumen.actual_promedio, "punto 'todos' del período actual == 'hoy' del resumen")
ok(P.evolucion.descenso_consecutivo is None, "con 2 períodos NO se inventa 'descenso consecutivo' (None, no 0)")

print("\n3. Por área contra SQL (Matemáticas, todas las sedes)")
mate = next(a for a in P.areas if a.area_codigo == "MATE")
b, c = notas_sql(*BASE, area_id=mate.area_id), notas_sql(*COMP, area_id=mate.area_id)
pares = [(b[e][mate.area_id], c[e][mate.area_id]) for e in set(b) & set(c)]
ok(mate.total_evaluados == len(pares), f"notas comparables {mate.total_evaluados} == SQL {len(pares)}")
ok(mate.variacion == round(sum(y for _, y in pares) / len(pares) - sum(x for x, _ in pares) / len(pares), 2), f"variación {mate.variacion} == SQL")
ok(mate.actual_evaluados == len(c) and mate.actual_n_bajo == sum(1 for v in c.values() if v[mate.area_id] < 3.0), "notas de hoy y en bajo == SQL")
ok(any(a.variacion is None and a.actual_evaluados for a in motor.panorama(db, params(sede_id=36)).areas), "sede sin período base: sus áreas salen con 'hoy' y cambio None (no 0)")

print("\n4. Grados: sumar grados == colegio")
comp_grados = sum(g.estudiantes_comparables for g in P.grados)
hoy_grados = sum(g.actual_evaluados for g in P.grados)
ok(comp_grados == P.resumen.estudiantes_comparables, f"comparables por grado suman {comp_grados}")
ok(hoy_grados == P.resumen.actual_evaluados, f"evaluados hoy por grado suman {hoy_grados}")
ok(any(g.grado not in range(0, 12) for g in P.grados) and P.resumen.avisos_datos, "el grado inválido (2026) se AVISA, no se esconde")

print("\n5. Lista de estudiantes == cada número del resumen")
filas = motor.comparar(db, **params())
cfg = schemas.ConfigComparacion()
r = P.resumen
for cambio, esperado in [
    ("mejoraron", r.mejoraron), ("empeoraron", r.empeoraron), ("estables", r.estables),
    ("entraron_bajo", r.entraron_a_bajo), ("salieron_bajo", r.salieron_de_bajo), ("permanecen_bajo", r.permanecen_en_bajo),
    ("bajo_actual", r.actual_n_bajo), ("sin_comparar", r.total_estudiantes - r.estudiantes_comparables),
]:
    n = len(motor.estudiantes_comparacion(filas, cfg, cambio))
    ok(n == esperado, f"'{cambio}': lista de {n} == número en pantalla {esperado}")
atencion = motor.estudiantes_comparacion(filas, cfg, "atencion")
ok(all(e.nivel_comparado == "BAJO" or e.categoria_variacion == "DESCENSO_SIGNIFICATIVO" for e in atencion), "'atención' solo trae bajo o descenso significativo")
deltas = [e.delta for e in motor.estudiantes_comparacion(filas, cfg, "empeoraron")]
ok(deltas == sorted(deltas), "ordenados del que más bajó al que menos")

print("\n6. Hallazgos: cada uno cuadra con su dato")
for h in P.hallazgos:
    a = h.accion
    if a.get("cambio") and a["cambio"] != "bajo_actual":
        n = len(motor.estudiantes_comparacion(filas, cfg, a["cambio"]))
        ok(str(n) in h.titulo, f"'{h.titulo}' -> la lista tiene {n}")
    if a.get("filtro") == "area_id":
        ok(any(x.area_id == a["valor"] for x in P.areas), f"'{h.titulo}' apunta a un área que existe")
print(f"  ({len(P.hallazgos)} hallazgos)")

print("\n7. Bordes: nivel de promedios en el límite")
ok(motor.nivel_desempeno(2.95, cfg) == "BAJO" and motor.nivel_desempeno(3.0, cfg) == "BASICO", "2.95 = Bajo, 3.0 = Básico (antes 2.95 salía Básico)")
ok(motor.nivel_desempeno(2.9, cfg) == "BAJO" and motor.nivel_desempeno(4.5, cfg) == "ALTO" and motor.nivel_desempeno(4.6, cfg) == "SUPERIOR", "notas de una décima: igual que antes")
vacio = motor.panorama(db, params(sede_id=36))
ok(vacio.resumen.estudiantes_comparables == 0 and vacio.lectura.tendencia == "sin_datos", "sede sin período base: lectura 'no hay con qué comparar' (no un falso 'estable')")
ok(vacio.resumen.pct_mejoraron == 0.0 and vacio.resumen.promedio_base is None, "sin comparables: sin división por cero, promedios en None")

print("\n8. API (servidor de prueba en otro puerto, sobre una COPIA de la base)")
BACKEND = Path(__file__).parent
TMP = Path(tempfile.mkdtemp(prefix="anz_"))
shutil.copy(BACKEND / "colegio.db", TMP / "colegio.db")
PUERTO = 8803
servidor = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PUERTO), "--log-level", "warning"],
    cwd=str(BACKEND), env={**os.environ, "PYTHONUTF8": "1", "IETABA_DB_PATH": str(TMP / "colegio.db")},
    stdout=open(TMP / "servidor.log", "w", encoding="utf-8"), stderr=subprocess.STDOUT,
)


def pedir(ruta):
    """Con curl.exe y no con urllib: en Windows, si el MISMO proceso que lanzó
    el servidor hace de cliente, las respuestas grandes a veces se cortan
    (ConnectionResetError) aunque el servidor responda 200; con curl, el
    navegador u otro proceso no pasa (verificado)."""
    salida = subprocess.run(
        ["curl.exe", "-s", "-w", "\n%{http_code}", f"http://127.0.0.1:{PUERTO}{ruta}"],
        capture_output=True, timeout=120,
    ).stdout.decode("utf-8")
    cuerpo, _, codigo = salida.rpartition("\n")
    try:
        return int(codigo), json.loads(cuerpo)
    except ValueError:
        return int(codigo or 0), None


try:
    for _ in range(240):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}/api/sedes", timeout=2).read()
            break
        except Exception:
            time.sleep(0.25)
    q = "anio_base=2026&periodo_base=1&anio_comparado=2026&periodo_comparado=2"
    for ruta in ("panorama", "estudiantes?cambio=atencion", "estudiantes?cambio=posible_retiro", "por-area", "por-docente", "detalle?tipo_cambio=mejora&limite=5", "resumen", "matriz-transicion"):
        sep = "&" if "?" in ruta else "?"
        estado, _ = pedir(f"/api/boletines/comparacion/{ruta}{sep}{q}")
        ok(estado == 200, f"GET {ruta.split('?')[0]} -> {estado}")
    estado, _ = pedir(f"/api/boletines/comparacion/estudiantes?cambio=inventado&{q}")
    ok(estado == 400, f"cambio desconocido -> 400 ({estado})")
    _, filas_mejora = pedir(f"/api/boletines/comparacion/detalle?tipo_cambio=mejora&limite=5000&{q}")
    ok(bool(filas_mejora) and all(f["categoria_variacion"] in ("MEJORA", "MEJORA_SIGNIFICATIVA") for f in filas_mejora), "detalle tipo_cambio=mejora agrupa mejora + significativa")
    _, todos = pedir(f"/api/boletines/comparacion/resumen?estado=TODOS&{q}")
    _, activos = pedir(f"/api/boletines/comparacion/resumen?{q}")
    ok(todos["total_estudiantes"] >= activos["total_estudiantes"] > 0, f"estado=TODOS ya no deja la pantalla vacía ({todos['total_estudiantes']} >= {activos['total_estudiantes']})")
    _, pan = pedir(f"/api/boletines/comparacion/panorama?{q}")
    ok(pan["resumen"]["estudiantes_comparables"] == P.resumen.estudiantes_comparables, "la API devuelve lo mismo que el motor")
    estado, areas_sin_sede = pedir(f"/api/boletines/comparacion/por-area?{q}")
    ok(estado == 200 and len(areas_sin_sede) > 5, "por-area ya no exige sede (las sedes comparten códigos de área)")
finally:
    servidor.terminate()
    servidor.wait(timeout=10)
    if fallos or sys.exc_info()[0]:
        print((TMP / "servidor.log").read_text(encoding="utf-8")[-3000:])
    shutil.rmtree(TMP, ignore_errors=True)

print()
if fallos:
    print(f"{len(fallos)} FALLA(S):")
    for f in fallos:
        print(" -", f)
    sys.exit(1)
print("Todo OK.")
