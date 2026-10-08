"""Prueba del módulo docente: asistencia por bloque (permisos, ventana de
corrección, idempotencia, auditoría). Trabaja sobre una COPIA de colegio.db
en un servidor aparte: no toca la base real. Sigue el mismo patrón que
probar_alertas_promocion.py."""
import http.cookiejar
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="ietaba_asistencia_"))
COPIA = TMP / "colegio.db"
PUERTO = 8807
BASE = f"http://127.0.0.1:{PUERTO}"
CLAVE = "PruebaAsistencia2026"

origen = sqlite3.connect(f"file:{BACKEND / 'colegio.db'}?mode=ro", uri=True)
destino = sqlite3.connect(COPIA)
with destino:
    origen.backup(destino)
origen.close()
destino.close()

os.environ["IETABA_DB_PATH"] = str(COPIA)
sys.path.insert(0, str(BACKEND))
from sqlalchemy import select  # noqa: E402

from app import auth, fechas, models, rbac_admin  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app import migraciones  # noqa: E402

# Valida, sobre la base real copiada, que la migración de 'asistencias'
# (esquema viejo -> por bloque) corre limpio: es el riesgo más importante de
# este cambio.
migraciones.ejecutar()

fallos = 0


def verificar(desc, cond, detalle=""):
    global fallos
    print(f"  {desc} -> {'OK' if cond else 'FALLO ' + str(detalle)}")
    if not cond:
        fallos += 1


anio = fechas.anio_lectivo_actual()
db = SessionLocal()

# --- Datos reales para las pruebas -------------------------------------------
# Los 72 docentes reales YA tienen usuario (Usuario.docente_id es único, no
# se puede enlazar dos veces), así que en vez de crear usuarios PRUEBA-*
# nuevos se REUTILIZA el usuario real de cada docente elegido, pisándole la
# clave en esta COPIA desechable de la base (nunca en la real) — ver
# _tomar_usuario_de_prueba más abajo.

# Director de grupo (area_id NULL): la asignación que NO depende de que haya
# un BloqueHorario cargado ese día — la fuente de verdad más simple.
asignacion_director = db.scalar(
    select(models.AsignacionDocente).where(
        models.AsignacionDocente.anio_lectivo == anio,
        models.AsignacionDocente.area_id.is_(None),
    )
)
verificar("hay al menos una asignación de director de grupo en la base real", asignacion_director is not None)

# Profesor de área: para probar el flujo "por bloque" de verdad se inserta un
# BloqueHorario sintético (en la COPIA, nunca en la base real) para hoy.
asignacion_area = db.scalar(
    select(models.AsignacionDocente).where(
        models.AsignacionDocente.anio_lectivo == anio,
        models.AsignacionDocente.area_id.is_not(None),
        models.AsignacionDocente.docente_id != (asignacion_director.docente_id if asignacion_director else -1),
    )
)
verificar("hay al menos una asignación por área de OTRO docente", asignacion_area is not None)

hoy = fechas.hoy_colombia()
from app import horario as horario_logica  # noqa: E402
dia_hoy = horario_logica.dia_de_fecha(hoy)
if dia_hoy is None:
    # Fin de semana: se fija la fecha de prueba al lunes más próximo para
    # poder probar el flujo por bloque (BloqueHorario.dia es 1..5).
    import datetime as _dt
    hoy = hoy + _dt.timedelta(days=(7 - hoy.weekday()))
    dia_hoy = 1

horas_ocupadas = set(db.scalars(
    select(models.BloqueHorario.hora).where(
        models.BloqueHorario.anio_lectivo == anio,
        models.BloqueHorario.docente_id == asignacion_area.docente_id,
        models.BloqueHorario.dia == dia_hoy,
    )
).all())
hora_libre = next(h for h in range(1, 20) if h not in horas_ocupadas)

bloque_area = models.BloqueHorario(
    anio_lectivo=anio, docente_id=asignacion_area.docente_id, sede_id=asignacion_area.sede_id,
    grado=asignacion_area.grado, curso=asignacion_area.curso, area_id=asignacion_area.area_id,
    area_label="PRUEBA", dia=dia_hoy, hora=hora_libre, origen="prueba_asistencia", estado="activo",
)
db.add(bloque_area)
db.flush()

estudiantes_director = list(db.scalars(
    select(models.Estudiante).where(
        models.Estudiante.sede_id == asignacion_director.sede_id,
        models.Estudiante.grado == asignacion_director.grado,
        (models.Estudiante.curso == asignacion_director.curso)
        if asignacion_director.curso is not None else models.Estudiante.curso.is_(None),
        models.Estudiante.estado == "ACTIVO",
    ).limit(5)
))
verificar("el grupo del director tiene al menos 2 estudiantes activos", len(estudiantes_director) >= 2, len(estudiantes_director))

estudiantes_area = list(db.scalars(
    select(models.Estudiante).where(
        models.Estudiante.sede_id == asignacion_area.sede_id,
        models.Estudiante.grado == asignacion_area.grado,
        (models.Estudiante.curso == asignacion_area.curso)
        if asignacion_area.curso is not None else models.Estudiante.curso.is_(None),
        models.Estudiante.estado == "ACTIVO",
    ).limit(5)
))
verificar("el grupo del profesor de área tiene al menos 2 estudiantes activos", len(estudiantes_area) >= 2, len(estudiantes_area))

# Un tercer docente, SIN relación con ninguno de los dos grupos anteriores
# (para probar que no ve estudiantes ajenos).
excluidos = {asignacion_director.docente_id, asignacion_area.docente_id}
otro_docente = db.scalar(
    select(models.AsignacionDocente).where(
        models.AsignacionDocente.anio_lectivo == anio,
        models.AsignacionDocente.docente_id.not_in(excluidos),
    )
)
verificar("hay un tercer docente sin relación con los dos grupos anteriores", otro_docente is not None)


def _tomar_usuario_de_prueba(docente_id: int) -> models.Usuario:
    """Reutiliza el usuario REAL ya enlazado a este docente (los 72 ya
    existen) pisándole clave/estado/roles SOLO en esta copia desechable de
    la base — la base real nunca se toca."""
    u = db.scalar(select(models.Usuario).where(models.Usuario.docente_id == docente_id))
    if u is None:
        u = auth.registrar_usuario(
            db, documento=f"PRUEBA-DOC-{docente_id}", nombre="Prueba Docente", clave=CLAVE,
            debe_cambiar_clave=False, docente_id=docente_id,
        )
    from app import seguridad
    u.clave_hash = seguridad.hashear_clave(CLAVE)
    u.estado = "activo"
    u.debe_cambiar_clave = False
    u.intentos_fallidos = 0
    u.bloqueado_hasta = None
    db.flush()
    rbac_admin.establecer_roles_usuario(db, u, ["docente"], asignado_por_id=None)
    return u


doc_director = _tomar_usuario_de_prueba(asignacion_director.docente_id)
doc_area = _tomar_usuario_de_prueba(asignacion_area.docente_id)
doc_ajeno = _tomar_usuario_de_prueba(otro_docente.docente_id)

u_coord = auth.registrar_usuario(db, documento="PRUEBA-COORD-ASIST", nombre="Prueba Coordinador", clave=CLAVE, debe_cambiar_clave=False)
rbac_admin.establecer_roles_usuario(db, u_coord, ["coordinador"], asignado_por_id=None)

doc_director_documento = doc_director.documento
doc_area_documento = doc_area.documento
doc_ajeno_documento = doc_ajeno.documento

# Snapshot a valores planos ANTES de cerrar la sesión: los objetos ORM
# quedan "detached" al cerrar y no se pueden volver a leer.
dir_sede_id, dir_grado, dir_curso = asignacion_director.sede_id, asignacion_director.grado, asignacion_director.curso
area_sede_id, area_grado, area_curso, area_area_id = (
    asignacion_area.sede_id, asignacion_area.grado, asignacion_area.curso, asignacion_area.area_id
)
bloque_area_id = bloque_area.id
ids_director = [e.id for e in estudiantes_director]
ids_area = [e.id for e in estudiantes_area]

db.commit()
db.close()

log = open(TMP / "servidor.log", "w", encoding="utf-8")
servidor = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PUERTO), "--log-level", "warning"],
    cwd=str(BACKEND), env={**os.environ, "PYTHONUTF8": "1"}, stdout=log, stderr=subprocess.STDOUT,
)


class Cliente:
    def __init__(self):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def pedir(self, ruta, metodo="GET", cuerpo=None):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        cab = {"Origin": BASE}
        if datos:
            cab["Content-Type"] = "application/json"
        req = urllib.request.Request(BASE + ruta, data=datos, method=metodo, headers=cab)
        try:
            with self.op.open(req, timeout=20) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)


try:
    for _ in range(120):
        try:
            urllib.request.urlopen(f"{BASE}/api/sedes", timeout=2).read()
            break
        except Exception:
            time.sleep(0.25)

    director, area, ajeno, coord = Cliente(), Cliente(), Cliente(), Cliente()
    print("\n[1] Login")
    verificar("director entra", director.pedir("/api/auth/login", "POST", {"usuario": doc_director_documento, "clave": CLAVE})[0] == 200)
    verificar("profesor de área entra", area.pedir("/api/auth/login", "POST", {"usuario": doc_area_documento, "clave": CLAVE})[0] == 200)
    verificar("docente ajeno entra", ajeno.pedir("/api/auth/login", "POST", {"usuario": doc_ajeno_documento, "clave": CLAVE})[0] == 200)
    verificar("coordinador entra", coord.pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-COORD-ASIST", "clave": CLAVE})[0] == 200)

    print("\n[2] Mis cursos")
    est, cuerpo, _ = director.pedir(f"/api/docente/mis-cursos?anio_lectivo={anio}")
    cursos_director = json.loads(cuerpo)
    verificar("el director ve al menos su grupo", est == 200 and any(
        c["sede_id"] == dir_sede_id and c["grado"] == dir_grado and c["area_id"] is None
        for c in cursos_director
    ), cuerpo[:300])

    print("\n[3] Mis estudiantes: alcance real")
    q_director = f"/api/docente/grupo/estudiantes?sede_id={dir_sede_id}&grado={dir_grado}" + (
        f"&curso={dir_curso}" if dir_curso is not None else ""
    )
    est, cuerpo, _ = director.pedir(q_director)
    verificar("el director ve su propio grupo (200)", est == 200 and len(json.loads(cuerpo)) >= 2, cuerpo[:200])
    est, cuerpo, _ = ajeno.pedir(q_director)
    verificar("un docente SIN esa asignación NO ve ese grupo (403)", est == 403, (est, cuerpo[:200]))

    q_area = f"/api/docente/grupo/estudiantes?sede_id={area_sede_id}&grado={area_grado}" + (
        f"&curso={area_curso}" if area_curso is not None else ""
    )
    est, cuerpo, _ = area.pedir(q_area)
    verificar("el profesor de área ve su propio grupo (200)", est == 200 and len(json.loads(cuerpo)) >= 2, cuerpo[:200])

    print("\n[4] Vista del bloque (director, area_id=None)")
    fecha_str = hoy.isoformat()
    ruta_bloque_dir = (
        f"/api/docente/asistencia/bloque?sede_id={dir_sede_id}&grado={dir_grado}"
        + (f"&curso={dir_curso}" if dir_curso is not None else "")
        + f"&fecha={fecha_str}"
    )
    est, cuerpo, _ = director.pedir(ruta_bloque_dir)
    v = json.loads(cuerpo)
    verificar("el director puede registrar la toma general (puede_registrar=True)", est == 200 and v["puede_registrar"] is True, cuerpo[:300])

    print("\n[5] Registrar asistencia en lote: todos presentes + 2 excepciones")
    registros = [{"estudiante_id": i, "estado": "presente", "uuid_cliente": f"t-dir-{i}"} for i in ids_director]
    registros[0]["estado"] = "ausente"
    if len(registros) > 1:
        registros[1]["estado"] = "tardanza"
    cuerpo_post = {
        "sede_id": dir_sede_id, "grado": dir_grado,
        "curso": dir_curso, "area_id": None, "fecha": fecha_str, "registros": registros,
    }
    est, cuerpo, _ = director.pedir("/api/docente/asistencia", "POST", cuerpo_post)
    verificar("se registra el lote (200)", est == 200, cuerpo[:300])
    resultado = json.loads(cuerpo) if est == 200 else []
    verificar("todos los estados se guardaron como se enviaron", est == 200 and {r["estudiante_id"]: r["estado"] for r in resultado} == {r["estudiante_id"]: r["estado"] for r in registros}, resultado)

    print("\n[6] Idempotencia: reenviar el mismo uuid_cliente no duplica")
    est2, cuerpo2, _ = director.pedir("/api/docente/asistencia", "POST", cuerpo_post)
    verificar("reenviar el mismo lote responde 200", est2 == 200, cuerpo2[:200])
    with sqlite3.connect(COPIA) as con:
        total = con.execute(
            "SELECT COUNT(*) FROM asistencias WHERE fecha=? AND sede_id=? AND grado=? AND area_id IS NULL",
            (fecha_str, dir_sede_id, dir_grado),
        ).fetchone()[0]
    verificar("no hay filas duplicadas tras reenviar (upsert por uuid)", total == len(ids_director), total)

    print("\n[7] Seguridad: el docente ajeno no puede registrar el grupo del director")
    est, cuerpo, _ = ajeno.pedir("/api/docente/asistencia", "POST", cuerpo_post)
    verificar("403 al intentar registrar un grupo ajeno", est == 403, (est, cuerpo[:200]))

    print("\n[8] Flujo por bloque (profesor de área, con BloqueHorario real)")
    ruta_bloque_area = (
        f"/api/docente/asistencia/bloque?sede_id={area_sede_id}&grado={area_grado}"
        + (f"&curso={area_curso}" if area_curso is not None else "")
        + f"&area_id={area_area_id}&fecha={fecha_str}"
    )
    est, cuerpo, _ = area.pedir(ruta_bloque_area)
    v = json.loads(cuerpo)
    verificar("el profesor de esa área puede registrar su bloque de hoy", est == 200 and v["puede_registrar"] is True, cuerpo[:300])
    est, cuerpo, _ = director.pedir(ruta_bloque_area)
    v2 = json.loads(cuerpo)
    verificar("el director de grupo NO puede registrar el bloque de otra área", est == 200 and v2["puede_registrar"] is False, cuerpo[:300])

    cuerpo_post_area = {
        "sede_id": area_sede_id, "grado": area_grado, "curso": area_curso,
        "area_id": area_area_id, "bloque_horario_id": bloque_area_id, "fecha": fecha_str,
        "registros": [{"estudiante_id": i, "estado": "presente", "uuid_cliente": f"t-area-{i}"} for i in ids_area],
    }
    est, cuerpo, _ = area.pedir("/api/docente/asistencia", "POST", cuerpo_post_area)
    verificar("el profesor de área registra su bloque (200)", est == 200, cuerpo[:300])

    print("\n[9] Ventana de corrección propia y corrección de coordinación")
    asistencia_id = resultado[0]["estudiante_id"] if resultado else None
    with sqlite3.connect(COPIA) as con:
        fila = con.execute(
            "SELECT id FROM asistencias WHERE estudiante_id=? AND fecha=? AND area_id IS NULL",
            (ids_director[0], fecha_str),
        ).fetchone()
        id_registro = fila[0] if fila else None
        # Se envejece el registro más allá de la ventana para forzar el caso.
        con.execute(
            "UPDATE asistencias SET fecha=date(?, '-10 days') WHERE id=?", (fecha_str, id_registro)
        )
        con.commit()

    est, cuerpo, _ = director.pedir("/api/docente/asistencia", "POST", {
        "sede_id": dir_sede_id, "grado": dir_grado, "curso": dir_curso,
        "area_id": None, "fecha": fecha_str,
        "registros": [{"estudiante_id": ids_director[0], "estado": "presente", "uuid_cliente": f"t-dir-{ids_director[0]}"}],
    })
    verificar("pasada la ventana, el propio docente NO puede corregir (403)", est == 403, (est, cuerpo[:200]))

    est, cuerpo, _ = coord.pedir(f"/api/asistencia/{id_registro}/corregir", "PATCH", {"estado": "tardanza", "motivo": "corrección de coordinación en prueba"})
    verificar("coordinación SÍ puede corregirlo (200)", est == 200 and json.loads(cuerpo)["estado"] == "tardanza", cuerpo[:200])
    verificar("el docente sin asistencia.corregir NO puede usar ese endpoint (403)", director.pedir(f"/api/asistencia/{id_registro}/corregir", "PATCH", {"estado": "presente", "motivo": "x"})[0] == 403)

    with sqlite3.connect(COPIA) as con:
        aud = con.execute(
            "SELECT valor_anterior, valor_nuevo FROM auditoria_cambios WHERE entidad='asistencia' AND entidad_id=? AND campo='estado'",
            (id_registro,),
        ).fetchall()
    verificar("la corrección quedó en la auditoría con valor anterior y nuevo", len(aud) >= 1, aud)

    print("\n[10] Anular")
    est, cuerpo, _ = coord.pedir(f"/api/asistencia/{id_registro}/anular", "POST", {"motivo": "prueba de anulación"})
    verificar("coordinación puede anular (200)", est == 200, cuerpo[:200])
    with sqlite3.connect(COPIA) as con:
        anulado = con.execute("SELECT anulado FROM asistencias WHERE id=?", (id_registro,)).fetchone()[0]
    verificar("el registro quedó anulado en la base (no borrado)", anulado == 1, anulado)
finally:
    servidor.terminate()
    servidor.wait(timeout=15)
    log.close()

engine.dispose()
shutil.rmtree(TMP, ignore_errors=True)
print("\nTODO OK" if not fallos else f"\n{fallos} FALLOS")
sys.exit(1 if fallos else 0)
