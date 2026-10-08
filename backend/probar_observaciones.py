"""Prueba de observaciones y remisión a psicología: separación docente vs
orientación/psicología (punto 11 del encargo docente). Trabaja sobre una
COPIA de colegio.db, nunca toca la base real."""
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
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="ietaba_observaciones_"))
COPIA = TMP / "colegio.db"
PUERTO = 8809
BASE = f"http://127.0.0.1:{PUERTO}"
CLAVE = "PruebaObservaciones2026"

origen = sqlite3.connect(f"file:{BACKEND / 'colegio.db'}?mode=ro", uri=True)
destino = sqlite3.connect(COPIA)
with destino:
    origen.backup(destino)
origen.close()
destino.close()

os.environ["IETABA_DB_PATH"] = str(COPIA)
sys.path.insert(0, str(BACKEND))
from sqlalchemy import select  # noqa: E402

from app import auth, fechas, models, rbac_admin, seguridad  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app import migraciones  # noqa: E402

migraciones.ejecutar()

fallos = 0


def verificar(desc, cond, detalle=""):
    global fallos
    print(f"  {desc} -> {'OK' if cond else 'FALLO ' + str(detalle)}")
    if not cond:
        fallos += 1


anio = fechas.anio_lectivo_actual()
db = SessionLocal()

# Dos docentes de ÁREA distinta pero del MISMO grupo (sede+grado+curso): así
# ambos tienen acceso legítimo al mismo estudiante, y se puede probar que uno
# no ve lo confidencial que escribió el otro.
por_grupo = defaultdict(list)
for a in db.scalars(
    select(models.AsignacionDocente).where(
        models.AsignacionDocente.anio_lectivo == anio,
        models.AsignacionDocente.area_id.is_not(None),
    )
):
    por_grupo[(a.sede_id, a.grado, a.curso)].append(a)

grupo_compartido = next((g for g in por_grupo.values() if len({a.docente_id for a in g}) >= 2), None)
verificar("hay un grupo con 2+ docentes de área distinta (para probar confidencialidad cruzada)", grupo_compartido is not None)
asign_a, asign_b = grupo_compartido[0], next(a for a in grupo_compartido if a.docente_id != grupo_compartido[0].docente_id)

estudiante = db.scalar(
    select(models.Estudiante).where(
        models.Estudiante.sede_id == asign_a.sede_id, models.Estudiante.grado == asign_a.grado,
        (models.Estudiante.curso == asign_a.curso) if asign_a.curso is not None else models.Estudiante.curso.is_(None),
        models.Estudiante.estado == "ACTIVO",
    )
)
verificar("el grupo compartido tiene al menos un estudiante activo", estudiante is not None)
estudiante_id = estudiante.id


def _tomar_usuario(docente_id, roles):
    u = db.scalar(select(models.Usuario).where(models.Usuario.docente_id == docente_id))
    u.clave_hash = seguridad.hashear_clave(CLAVE)
    u.estado = "activo"
    u.debe_cambiar_clave = False
    u.intentos_fallidos = 0
    u.bloqueado_hasta = None
    db.flush()
    rbac_admin.establecer_roles_usuario(db, u, roles, asignado_por_id=None)
    return u


doc_a = _tomar_usuario(asign_a.docente_id, ["docente"])
doc_b = _tomar_usuario(asign_b.docente_id, ["docente"])
doc_a_documento, doc_b_documento = doc_a.documento, doc_b.documento

u_orientacion = auth.registrar_usuario(db, documento="PRUEBA-ORIENTACION", nombre="Prueba Orientación", clave=CLAVE, debe_cambiar_clave=False)
rbac_admin.establecer_roles_usuario(db, u_orientacion, ["orientacion"], asignado_por_id=None)

u_coord = auth.registrar_usuario(db, documento="PRUEBA-COORD-OBS", nombre="Prueba Coordinador", clave=CLAVE, debe_cambiar_clave=False)
rbac_admin.establecer_roles_usuario(db, u_coord, ["coordinador"], asignado_por_id=None)

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
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()


try:
    for _ in range(120):
        try:
            urllib.request.urlopen(f"{BASE}/api/sedes", timeout=2).read()
            break
        except Exception:
            time.sleep(0.25)

    a, b, orientacion, coord = Cliente(), Cliente(), Cliente(), Cliente()
    print("\n[1] Login")
    verificar("docente A entra", a.pedir("/api/auth/login", "POST", {"usuario": doc_a_documento, "clave": CLAVE})[0] == 200)
    verificar("docente B entra", b.pedir("/api/auth/login", "POST", {"usuario": doc_b_documento, "clave": CLAVE})[0] == 200)
    verificar("orientación entra", orientacion.pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-ORIENTACION", "clave": CLAVE})[0] == 200)
    verificar("coordinador entra", coord.pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-COORD-OBS", "clave": CLAVE})[0] == 200)

    print("\n[2] Docente A crea una observación académica (no confidencial)")
    est, cuerpo = a.pedir("/api/docente/observaciones", "POST", {
        "estudiante_id": estudiante_id, "tipo": "academica", "detalle": "Le cuesta la comprensión lectora.",
        "uuid_cliente": "obs-academica-1",
    })
    verificar("se crea (200)", est == 200, cuerpo[:300])
    obs_academica = json.loads(cuerpo) if est == 200 else {}
    verificar("no queda marcada confidencial", obs_academica.get("confidencial") is False)

    est, cuerpo = b.pedir(f"/api/docente/observaciones?estudiante_id={estudiante_id}")
    verificar("el docente B (mismo grupo, otra área) SÍ ve la académica", est == 200 and any(o["id"] == obs_academica["id"] for o in json.loads(cuerpo)), cuerpo[:300])

    print("\n[3] Docente A remite a psicología (tipo=psicologia)")
    est, cuerpo = a.pedir("/api/docente/observaciones", "POST", {
        "estudiante_id": estudiante_id, "tipo": "psicologia",
        "detalle": "Situación observada durante la clase, solicito valoración.",
        "uuid_cliente": "obs-remision-1",
    })
    verificar("se crea (200)", est == 200, cuerpo[:300])
    remision = json.loads(cuerpo) if est == 200 else {}
    verificar("queda marcada confidencial AUNQUE el body no lo pidió", remision.get("confidencial") is True, remision)
    verificar("no trae seguimientos en la respuesta de creación", remision.get("seguimientos") == [])

    print("\n[4] Confidencialidad: quién ve la remisión")
    est, cuerpo = a.pedir(f"/api/docente/observaciones?estudiante_id={estudiante_id}")
    ids_a = {o["id"] for o in json.loads(cuerpo)}
    verificar("el autor (docente A) SIGUE viendo su propia remisión", remision["id"] in ids_a, ids_a)

    est, cuerpo = b.pedir(f"/api/docente/observaciones?estudiante_id={estudiante_id}")
    ids_b = {o["id"] for o in json.loads(cuerpo)}
    verificar("el docente B (mismo grupo, NO autor) NO ve la remisión confidencial", remision["id"] not in ids_b, ids_b)

    est, cuerpo = coord.pedir(f"/api/docente/observaciones?estudiante_id={estudiante_id}")
    verificar("coordinación no está vinculada a un docente (409, no 403: sí tiene el permiso)", est == 409, (est, cuerpo[:200]))

    print("\n[5] Bandeja de orientación")
    verificar("un docente NO puede abrir la bandeja de orientación (403)", a.pedir("/api/orientacion/observaciones")[0] == 403)
    verificar("coordinación (sin ver_confidenciales) tampoco (403)", coord.pedir("/api/orientacion/observaciones")[0] == 403)
    est, cuerpo = orientacion.pedir("/api/orientacion/observaciones?tipo=psicologia")
    bandeja = json.loads(cuerpo)
    verificar("orientación SÍ ve la remisión en su bandeja", est == 200 and any(o["id"] == remision["id"] for o in bandeja), cuerpo[:300])
    verificar("la bandeja trae el nombre del estudiante (para triage sin abrir cada una)", bandeja and bandeja[0].get("estudiante_nombre"), bandeja[:1])

    print("\n[6] Seguimiento interno (psicología gestiona el caso)")
    est, cuerpo = a.pedir(f"/api/orientacion/observaciones/{remision['id']}/seguimiento", "POST", {"nota": "x"})
    verificar("el docente autor NO puede agregar seguimiento (403, sin seguimientos.gestionar)", est == 403)
    est, cuerpo = orientacion.pedir(f"/api/orientacion/observaciones/{remision['id']}/seguimiento", "POST", {"nota": "Se citó a la familia."})
    verificar("orientación sí puede agregar seguimiento (200)", est == 200, cuerpo[:300])
    con_seguimiento = json.loads(cuerpo)
    verificar("el seguimiento queda en la respuesta de orientación", len(con_seguimiento.get("seguimientos", [])) == 1, con_seguimiento)

    est, cuerpo = a.pedir(f"/api/docente/observaciones?estudiante_id={estudiante_id}")
    verificar("el docente autor NUNCA ve el seguimiento interno (lista de docente no lo incluye)", "seguimientos" not in json.dumps(json.loads(cuerpo)) or all(o.get("seguimientos") == [] for o in json.loads(cuerpo)))

    print("\n[7] Cerrar el caso")
    est, cuerpo = orientacion.pedir(f"/api/orientacion/observaciones/{remision['id']}/estado", "PATCH", {"estado": "atendida", "nota_atencion": "Valorada, seguimiento mensual."})
    verificar("orientación marca atendida (200)", est == 200 and json.loads(cuerpo)["estado"] == "atendida", cuerpo[:300])

    print("\n[8] Idempotencia por uuid_cliente")
    est, cuerpo = a.pedir("/api/docente/observaciones", "POST", {
        "estudiante_id": estudiante_id, "tipo": "psicologia", "detalle": "TEXTO DISTINTO QUE NO DEBE GUARDARSE",
        "uuid_cliente": "obs-remision-1",
    })
    verificar("reenviar el mismo uuid_cliente responde 200 y devuelve la MISMA fila (no la pisa)", est == 200 and json.loads(cuerpo)["id"] == remision["id"] and json.loads(cuerpo)["detalle"] != "TEXTO DISTINTO QUE NO DEBE GUARDARSE", cuerpo[:300])
    with sqlite3.connect(COPIA) as con:
        total = con.execute("SELECT COUNT(*) FROM observaciones WHERE uuid_cliente='obs-remision-1'").fetchone()[0]
    verificar("no hay fila duplicada en la base", total == 1, total)

    print("\n[9] Seguridad: tipo inválido")
    est, cuerpo = a.pedir("/api/docente/observaciones", "POST", {"estudiante_id": estudiante_id, "tipo": "inventado", "detalle": "x"})
    verificar("un tipo que no existe se rechaza (400)", est == 400, (est, cuerpo[:200]))
finally:
    servidor.terminate()
    servidor.wait(timeout=15)
    log.close()

engine.dispose()
shutil.rmtree(TMP, ignore_errors=True)
print("\nTODO OK" if not fallos else f"\n{fallos} FALLOS")
sys.exit(1 if fallos else 0)
