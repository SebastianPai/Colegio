"""Prueba de que lo escrito en la ficha de matrícula se guarda en el estudiante
y vuelve a aparecer. Trabaja sobre una COPIA de colegio.db: no toca la real."""
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
TMP = Path(tempfile.mkdtemp(prefix="ietaba_datosficha_"))
COPIA = TMP / "colegio.db"
PUERTO = 8807
BASE = f"http://127.0.0.1:{PUERTO}"
CLAVE = "PruebaFicha2026"

origen = sqlite3.connect(f"file:{BACKEND / 'colegio.db'}?mode=ro", uri=True)
destino = sqlite3.connect(COPIA)
with destino:
    origen.backup(destino)
origen.close()
destino.close()

os.environ["IETABA_DB_PATH"] = str(COPIA)
sys.path.insert(0, str(BACKEND))
from app import auth, migraciones, rbac_admin  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402

migraciones.ejecutar()

fallos = 0


def verificar(desc, cond, detalle=""):
    global fallos
    print(f"  {desc} -> {'OK' if cond else 'FALLO ' + str(detalle)}")
    if not cond:
        fallos += 1


db = SessionLocal()
u = auth.registrar_usuario(db, documento="PRUEBA-SEC-FICHA", nombre="Prueba secretaria", clave=CLAVE, debe_cambiar_clave=False)
rbac_admin.establecer_roles_usuario(db, u, ["secretaria"], asignado_por_id=None)
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


EST = 5
try:
    for _ in range(120):
        try:
            urllib.request.urlopen(f"{BASE}/api/sedes", timeout=2).read()
            break
        except Exception:
            time.sleep(0.25)
    c = Cliente()
    verificar("secretaria entra", c.pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-SEC-FICHA", "clave": CLAVE})[0] == 200)

    est, cuerpo, _ = c.pedir(f"/api/estudiantes/{EST}/datos-ficha")
    verificar("antes de guardar no hay acudiente", est == 200 and "acudiente" not in json.loads(cuerpo)["campos"])

    campos = {
        "acudiente": "MARIA PRUEBA PAI", "parentesco": "MADRE", "documento_acudiente": "123456", "direccion": "COROZAL",
        "municipio_nacimiento": "BARBACOAS", "municipio_expedicion": "TUMACO", "etnia_indigena": "X", "awapit_si": "X",
        "madre_no": "X", "discap_si": "X", "disc_ceguera": "X", "disc_otras": "Asma", "ingreso_dia": "23",
        "ingreso_mes": "OCTUBRE", "ingreso_anio": "2025", "nombres": "NO DEBE GUARDARSE", "grado_2026": "9",
    }
    est, cuerpo, _ = c.pedir(f"/api/estudiantes/{EST}/datos-ficha", "PUT", {"campos": campos})
    verificar("guardar responde 200", est == 200, cuerpo[:200])
    g = json.loads(c.pedir(f"/api/estudiantes/{EST}/datos-ficha")[1])["campos"]
    verificar("acudiente, parentesco y documento vuelven",
              g.get("acudiente") == "MARIA PRUEBA PAI" and g.get("parentesco") == "MADRE" and g.get("documento_acudiente") == "123456", g)
    verificar("comunidad y municipio de nacimiento vuelven", g.get("direccion") == "COROZAL" and g.get("municipio_nacimiento") == "BARBACOAS")
    verificar("etnia y Si/No vuelven como X", g.get("etnia_indigena") == "X" and g.get("awapit_si") == "X" and g.get("madre_no") == "X")
    verificar("lo NO marcado sigue sin decirse (no se vuelve 'No')",
              "educ_esp_no" not in g and "educ_esp_si" not in g and "rios_no" not in g)
    verificar("discapacidad vuelve con su detalle",
              g.get("discap_si") == "X" and g.get("disc_ceguera") == "X" and g.get("disc_otras") == "Asma")
    verificar("fecha de ingreso vuelve",
              (g.get("ingreso_dia"), g.get("ingreso_mes"), g.get("ingreso_anio")) == ("23", "OCTUBRE", "2025"), g)
    verificar("nombres y grado NO se guardan desde la ficha", "nombres" not in g and "grado_2026" not in g)
    est_json = json.loads(c.pedir(f"/api/estudiantes/{EST}")[1])
    verificar("el lugar de expedición actualiza al estudiante", est_json.get("lugar_expedicion_documento") == "TUMACO",
              est_json.get("lugar_expedicion_documento"))
    verificar("el nombre del estudiante no cambió", "NO DEBE" not in est_json.get("primer_nombre", ""))

    c.pedir(f"/api/estudiantes/{EST}/datos-ficha", "PUT", {"campos": {"acudiente": "", "discap_no": "X"}})
    g = json.loads(c.pedir(f"/api/estudiantes/{EST}/datos-ficha")[1])["campos"]
    verificar("vaciar un campo lo borra y discapacidad pasa a 'No'",
              "acudiente" not in g and g.get("discap_no") == "X" and "disc_ceguera" not in g, g)
    verificar("estudiante inexistente da 404", c.pedir("/api/estudiantes/99999999/datos-ficha", "PUT", {"campos": {}})[0] == 404)
finally:
    servidor.terminate()
    servidor.wait(timeout=15)
    log.close()

engine.dispose()
shutil.rmtree(TMP, ignore_errors=True)
print("\nTODO OK" if not fallos else f"\n{fallos} FALLOS")
sys.exit(1 if fallos else 0)
