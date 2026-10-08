"""Pruebas del Paso 1 (cimientos): fecha de Colombia, PRAGMAs de SQLite,
claves foráneas, índices, duplicados con curso NULL y borrados.

Trabaja SIEMPRE sobre una copia temporal de la base: nunca modifica
colegio.db. Al arrancar la app sobre la copia se ejecutan las migraciones, así
que la salida también muestra qué harán sobre la base real.

    ./venv/Scripts/python.exe probar_cimientos.py            # copia de colegio.db
    ./venv/Scripts/python.exe probar_cimientos.py otra.db    # copia de otra base
"""

import datetime as dt
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
ORIGEN = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND / "colegio.db"
TMP = Path(tempfile.mkdtemp(prefix="ietaba_cimientos_"))
COPIA = TMP / "colegio.db"


def _copiar(origen: Path, destino: Path) -> None:
    src = sqlite3.connect(f"file:{origen}?mode=ro", uri=True)
    dst = sqlite3.connect(destino)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()


_copiar(ORIGEN, COPIA)
os.environ["IETABA_DB_PATH"] = str(COPIA)
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

print(f"Copia de prueba: {COPIA}\n\n[0] Arranque de la app sobre la copia (migraciones)")
from app import main  # noqa: E402,F401  (ejecuta migraciones.ejecutar())
from app import crud, fechas, horario, migraciones, models  # noqa: E402
from app.database import DB_PATH, Base, SessionLocal, engine  # noqa: E402

OK = "  \033[92mOK\033[0m"
FALLO = "  \033[91mFALLO\033[0m"
fallos = 0


def verificar(descripcion: str, condicion: bool, detalle: str = "") -> None:
    global fallos
    if condicion:
        print(f"  {descripcion}{OK}")
    else:
        fallos += 1
        print(f"  {descripcion}{FALLO} {detalle}")


def utc(iso: str) -> dt.datetime:
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))


def rechaza(db, *objetos) -> bool:
    """True si la base rechaza (IntegrityError) guardar estos objetos."""
    for o in objetos:
        db.add(o)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return True
    return False


verificar("la app usa la copia, no colegio.db", Path(DB_PATH) == COPIA, str(DB_PATH))

# ---- 1. Fecha de Colombia ---------------------------------------------------
print("\n[1] Fecha de Colombia (el caso crítico es desde las 7:00 p. m.)")
CASOS = [
    ("2026-09-11T17:00:00Z", "12:00 m.        ", "2026-09-11"),
    ("2026-09-11T23:59:00Z", "6:59 p. m.      ", "2026-09-11"),
    ("2026-09-12T00:00:00Z", "7:00 p. m.      ", "2026-09-11"),
    ("2026-09-12T00:30:00Z", "7:30 p. m.      ", "2026-09-11"),
    ("2026-09-12T04:30:00Z", "11:30 p. m.     ", "2026-09-11"),
    ("2026-09-12T04:59:59Z", "11:59:59 p. m.  ", "2026-09-11"),
    ("2026-09-12T05:00:00Z", "12:00 a. m. (12)", "2026-09-12"),
]
for iso, hora, esperado in CASOS:
    instante = utc(iso)
    obtenido = fechas.hoy_colombia(instante=instante).isoformat()
    verificar(
        f"{hora} → {obtenido}   (recortando UTC daría {instante.date().isoformat()})",
        obtenido == esperado,
        f"esperado {esperado}",
    )
verificar("zona IANA America/Bogota cargada (tzdata)", str(fechas.ZONA_COLOMBIA) == "America/Bogota", str(fechas.ZONA_COLOMBIA))
verificar("desfase actual de Colombia = −05:00", fechas.ahora_colombia().utcoffset() == dt.timedelta(hours=-5))
verificar(
    "hoy_colombia() = fecha colombiana del instante UTC actual",
    fechas.hoy_colombia() == fechas.hoy_colombia(instante=fechas.ahora_utc()),
)
fr = horario.franja_actual(fechas.a_colombia(utc("2026-09-12T00:30:00Z")))
verificar(
    f"horario.franja_actual a las 7:30 p. m. → {fr['fecha']} {fr['dia_nombre']} ({fr['estado']})",
    fr["fecha"] == "2026-09-11" and fr["dia_nombre"] == "Viernes" and fr["estado"] == "fuera_jornada",
)
verificar(
    "default de Asistencia.fecha = hoy_colombia (no date.today del servidor)",
    models.Asistencia.__table__.c.fecha.default.arg.__name__ == "hoy_colombia",
)

# ---- 2. PRAGMAs --------------------------------------------------------------
print("\n[2] SQLite: WAL, busy_timeout, foreign_keys")
with engine.connect() as conn:
    jm = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
    bt = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
    fk = conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
verificar(f"journal_mode = {jm}", jm == "wal")
verificar(f"busy_timeout = {bt} ms", bt == 5000)
verificar(f"foreign_keys = {fk}", fk == 1)
crudo = sqlite3.connect(COPIA)
verificar("WAL quedó guardado en el archivo (conexión sin la app)", crudo.execute("PRAGMA journal_mode").fetchone()[0] == "wal")
crudo.close()

bloqueo = sqlite3.connect(COPIA, isolation_level=None, check_same_thread=False)
bloqueo.execute("BEGIN IMMEDIATE")
bloqueo.execute("UPDATE sedes SET nombre = nombre WHERE id = 1")
t0 = time.perf_counter()
with engine.connect() as conn:
    conn.exec_driver_sql("SELECT count(*) FROM estudiantes").scalar()
lectura = time.perf_counter() - t0
verificar(f"una lectura no espera a una escritura en curso (WAL): {lectura * 1000:.0f} ms", lectura < 0.5)
threading.Timer(1.5, lambda: bloqueo.execute("COMMIT")).start()
t0 = time.perf_counter()
db = SessionLocal()
db.execute(text("UPDATE sedes SET nombre = nombre WHERE id = 1"))
db.commit()
espera = time.perf_counter() - t0
verificar(f"una escritura concurrente espera el bloqueo ({espera:.1f} s) y se completa sin 'database is locked'", 1.0 <= espera < 5)
bloqueo.close()

# ---- 3. Claves foráneas -------------------------------------------------------------
print("\n[3] Claves foráneas")
crudo = sqlite3.connect(COPIA)
tablas = {r[0] for r in crudo.execute("SELECT name FROM sqlite_master WHERE type='table'")}
rotas = [
    f"{t}.{fk[3]} → {fk[2]}"
    for t in sorted(tablas)
    for fk in crudo.execute(f'PRAGMA foreign_key_list("{t}")')
    if fk[2] not in tablas
]
verificar("ninguna clave foránea apunta a una tabla inexistente", not rotas, str(rotas))
destino_pend = {fk[2] for fk in crudo.execute("PRAGMA foreign_key_list(pendientes_boletin)")}
verificar(f"pendientes_boletin apunta a {sorted(destino_pend)}", "revisiones_boletin" in destino_pend and "revisiones_boletin_old" not in destino_pend)
violaciones = crudo.execute("PRAGMA foreign_key_check").fetchall()
verificar(f"foreign_key_check: {len(violaciones)} filas huérfanas", not violaciones)
n_pend = crudo.execute("SELECT count(*) FROM pendientes_boletin").fetchone()[0]
n_pend_origen = sqlite3.connect(f"file:{ORIGEN}?mode=ro", uri=True).execute("SELECT count(*) FROM pendientes_boletin").fetchone()[0]
verificar(f"pendientes_boletin conserva sus filas ({n_pend} de {n_pend_origen})", n_pend == n_pend_origen)

rev = db.scalar(select(models.RevisionBoletin).order_by(models.RevisionBoletin.id))
p = models.PendienteBoletin(revision_id=rev.id, tipo="nota", detalle="prueba paso 1")
verificar("crear un pendiente de boletín con revisión válida funciona", not rechaza(db, p))
db.delete(p)
db.commit()
verificar("pendiente con revisión inexistente → rechazado", rechaza(db, models.PendienteBoletin(revision_id=999_999_999, tipo="nota")))
sede_valida = db.scalar(select(models.Sede.id))
docente_valido = db.scalar(select(models.Docente.id))
usuario_valido = db.scalar(select(models.Usuario.id))
# El módulo de asistencia por bloque (permisos, ventana de corrección,
# idempotencia, auditoría) tiene su propia prueba dedicada:
# probar_asistencia_observaciones.py. Aquí solo se confirma el cimiento: la
# FK asistencias.estudiante_id sigue protegida a nivel de base.
verificar(
    "asistencia de un estudiante inexistente → rechazada",
    rechaza(db, models.Asistencia(
        estudiante_id=999_999_999, sede_id=sede_valida, grado=6, curso=None,
        fecha=dt.date(2026, 9, 10), estado="presente",
        docente_id=docente_valido, registrado_por_usuario_id=usuario_valido,
    )),
)
crudo.close()

# ---- 4. Índices -----------------------------------------------------------------------
print("\n[4] Índices")
crudo = sqlite3.connect(COPIA)
en_bd = {r[0] for r in crudo.execute("SELECT name FROM sqlite_master WHERE type='index'")}
declarados = sorted(i.name for t in Base.metadata.sorted_tables for i in t.indexes)
faltan = [n for n in declarados if n not in en_bd]
verificar(f"los {len(declarados)} índices declarados en models.py existen en la base", not faltan, str(faltan))
plan = " ".join(
    str(r[-1]) for r in crudo.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM estudiantes WHERE sede_id = 1 AND grado = 8 AND curso = 1"
    )
)
verificar(f"consulta por grupo usa ix_estudiantes_grupo ({plan})", "ix_estudiantes_grupo" in plan)
crudo.close()

# ---- 5. Duplicados con curso / área NULL --------------------------------------
print("\n[5] Duplicados con curso = NULL (y área = NULL)")
crudo = sqlite3.connect(COPIA)
CONSULTAS = {
    "revisiones_boletin": "SELECT count(*) FROM (SELECT 1 FROM revisiones_boletin GROUP BY sede_id, grado, ifnull(curso,-1), anio_lectivo, periodo HAVING count(*) > 1)",
    "sapred_sin_coincidencia": "SELECT count(*) FROM (SELECT 1 FROM sapred_sin_coincidencia GROUP BY documento, sede_id, grado, ifnull(curso,-1), periodo, anio_lectivo HAVING count(*) > 1)",
    "textos_boletin": "SELECT count(*) FROM (SELECT 1 FROM textos_boletin GROUP BY revision_id, ifnull(area_id,-1), estudiante_id, tipo HAVING count(*) > 1)",
    "asignaciones_docente": "SELECT count(*) FROM (SELECT 1 FROM asignaciones_docente GROUP BY sede_id, grado, ifnull(curso,-1), ifnull(area_id,-1), anio_lectivo HAVING count(*) > 1)",
}
for tabla, sql in CONSULTAS.items():
    n = crudo.execute(sql).fetchone()[0]
    verificar(f"{tabla}: {n} grupos duplicados", n == 0)
crudo.close()

r0 = db.scalar(select(models.RevisionBoletin).where(models.RevisionBoletin.curso.is_(None)))
verificar(
    f"revisión duplicada con curso NULL (sede {r0.sede_id}, grado {r0.grado}) → rechazada",
    rechaza(db, models.RevisionBoletin(sede_id=r0.sede_id, grado=r0.grado, curso=None, anio_lectivo=r0.anio_lectivo, periodo=r0.periodo)),
)
s0 = db.scalar(select(models.EstudianteSapredSinCoincidencia).where(models.EstudianteSapredSinCoincidencia.curso.is_(None)))
verificar(
    "estudiante SAPRED sin coincidencia duplicado con curso NULL → rechazado",
    rechaza(db, models.EstudianteSapredSinCoincidencia(
        documento=s0.documento, nombre_sapred="duplicado", sede_id=s0.sede_id, grado=s0.grado,
        curso=None, periodo=s0.periodo, anio_lectivo=s0.anio_lectivo,
    )),
)
t0_ = db.scalar(select(models.TextoBoletin).where(models.TextoBoletin.area_id.is_(None)))
verificar(
    "observación del director duplicada (área NULL) → rechazada",
    rechaza(db, models.TextoBoletin(revision_id=t0_.revision_id, area_id=None, estudiante_id=t0_.estudiante_id, tipo=t0_.tipo, texto="dup")),
)

# ---- 6. Borrados con claves foráneas activas ---------------------------------
print("\n[6] Borrados con claves foráneas activas")
bloque = db.scalar(select(models.BloqueHorario).order_by(models.BloqueHorario.id))
ausencia = models.AusenciaDocente(docente_id=bloque.docente_id, fecha=dt.date(2030, 1, 7), motivo="prueba paso 1")
db.add(ausencia)
db.flush()
reemplazo = models.Reemplazo(
    fecha=ausencia.fecha, dia=bloque.dia, hora=bloque.hora, grado=bloque.grado, curso=bloque.curso,
    area_label=bloque.area_label, docente_ausente_id=bloque.docente_id,
    bloque_horario_id=bloque.id, ausencia_id=ausencia.id,
)
db.add(reemplazo)
db.commit()
rid, aid, bid = reemplazo.id, ausencia.id, bloque.id
verificar("borrar un bloque de horario que tiene un reemplazo funciona", horario.eliminar_bloque_horario(db, bid))
db.expire_all()
r = db.get(models.Reemplazo, rid)
verificar(
    "…el reemplazo se conserva y solo pierde el enlace al bloque",
    r is not None and r.bloque_horario_id is None and db.get(models.BloqueHorario, bid) is None,
)
verificar("borrar una ausencia con reemplazos funciona", horario.eliminar_ausencia(db, aid))
db.expire_all()
verificar("…y sus reemplazos se borran con ella", db.get(models.Reemplazo, rid) is None)

eid = db.scalar(select(models.NotaSapred.estudiante_id))
try:
    crud.eliminar_estudiante(db, eid)
    resultado = "se borró"
except ValueError as e:
    resultado = str(e)
db.expire_all()
verificar(
    "borrar un estudiante con notas → se rechaza con mensaje y el estudiante sigue",
    resultado.startswith("No se puede eliminar") and db.get(models.Estudiante, eid) is not None,
    resultado,
)
nuevo = models.Estudiante(documento="PRUEBA-PASO1", primer_apellido="PRUEBA", primer_nombre="PASO", grado=1, sede_id=1)
db.add(nuevo)
db.flush()
db.add(models.Asistencia(
    estudiante_id=nuevo.id, sede_id=sede_valida, grado=1, curso=None,
    fecha=dt.date(2026, 9, 10), estado="ausente",
    docente_id=docente_valido, registrado_por_usuario_id=usuario_valido,
))
db.commit()
nid = nuevo.id
verificar("borrar un estudiante sin historial funciona", crud.eliminar_estudiante(db, nid))
queda = db.scalar(select(models.Asistencia).where(models.Asistencia.estudiante_id == nid))
verificar("…y su asistencia se borra con él (cascade)", queda is None)
db.close()

# ---- 7. Idempotencia -------------------------------------------------------
print("\n[7] Migraciones idempotentes (segunda ejecución)")
resultado = migraciones.ejecutar()
verificar(
    f"segunda ejecución no cambia nada: {resultado}",
    resultado == {
        "tablas_reparadas": [], "indices_creados": [],
        "permisos_sincronizados": [], "roles_sembrados": [],
    },
)
crudo = sqlite3.connect(COPIA)
ic = crudo.execute("PRAGMA integrity_check").fetchone()[0]
verificar(f"integrity_check = {ic}", ic == "ok")
crudo.close()

engine.dispose()
shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'TODO OK' if not fallos else f'{fallos} FALLOS'}")
sys.exit(1 if fallos else 0)
