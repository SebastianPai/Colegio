"""Pruebas de la identidad de servicio SAPRED (Fase 4.1), sobre una COPIA
temporal de la base: nunca toca colegio.db ni sebastian.pai. Mismo patrón
que probar_autenticacion.py / probar_fase4_auth_frontend.py.

Cubre específicamente lo que un curl suelto no puede probar limpio:
  - una sesión HUMANA real (con un usuario de prueba, nunca sebastian.pai)
    sin el token de servicio, contra los endpoints internos -> 403;
  - que el token de servicio nunca aparece en ningún archivo de log.

El archivo del token (backend/certs/token_servicio_sapred.key) NO es parte
de la copia de base de datos: es un archivo compartido por toda la
instalación (igual que certs/secreto_sesiones.key), así que este script usa
el mismo que ya esté generado (o lo genera si es la primera vez).

    ./venv/Scripts/python.exe probar_fase41_identidad_servicio.py
"""

import http.cookiejar
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
ORIGEN = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND / "colegio.db"
TMP = Path(tempfile.mkdtemp(prefix="ietaba_fase41_"))
COPIA = TMP / "colegio.db"
PUERTO = 8803
BASE_URL = f"http://127.0.0.1:{PUERTO}"

CLAVE = "PruebaFase41Segura2026"

src = sqlite3.connect(f"file:{ORIGEN}?mode=ro", uri=True)
dst = sqlite3.connect(COPIA)
with dst:
    src.backup(dst)
src.close()
dst.close()

os.environ["IETABA_DB_PATH"] = str(COPIA)
sys.path.insert(0, str(BACKEND))

print(f"Copia de prueba: {COPIA}\n\n[0] Arranque sobre la copia")
from app import main as _arranque  # noqa: E402,F401
from app import auth, seguridad  # noqa: E402
from app.database import SessionLocal  # noqa: E402

TOKEN_REAL = seguridad.token_servicio()  # el mismo que usa la instalación real

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


class Cliente:
    def __init__(self, nombre: str):
        self.nombre = nombre
        self.galletas = http.cookiejar.CookieJar()
        self.abridor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.galletas))

    def pedir(self, ruta, metodo="GET", cuerpo=None, cabeceras=None):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        cab = {"Origin": BASE_URL, **(cabeceras or {})}
        if datos:
            cab["Content-Type"] = "application/json"
        peticion = urllib.request.Request(BASE_URL + ruta, data=datos, method=metodo, headers=cab)
        try:
            with self.abridor.open(peticion, timeout=30) as r:
                return r.status, _json(r.read())
        except urllib.error.HTTPError as e:
            return e.code, _json(e.read())


def _json(datos: bytes):
    try:
        return json.loads(datos)
    except ValueError:
        return None


# ---- 1. Usuario de prueba (solo en la copia) --------------------------------
print("\n[1] Usuario administrador de prueba (solo en la copia temporal)")
db = SessionLocal()
admin = auth.registrar_usuario(
    db, documento="PRUEBA-F41-ADMIN", nombre="Prueba Fase41 Admin", clave=CLAVE, debe_cambiar_clave=False,
)
verificar(f"usuario de prueba creado (#{admin.id}) — NO es sebastian.pai", admin.documento != "sebastian.pai")
db.close()

# ---- 2. Servidor -------------------------------------------------------------
print("\n[2] Servidor de prueba")
registro = open(TMP / "servidor.log", "w", encoding="utf-8")
servidor = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PUERTO),
     "--log-level", "info"],
    cwd=str(BACKEND), env={**os.environ, "PYTHONUTF8": "1"}, stdout=registro, stderr=subprocess.STDOUT,
)
try:
    for _ in range(240):
        try:
            urllib.request.urlopen(f"{BASE_URL}/api/sedes", timeout=2).read()
            break
        except Exception:
            import time as _t
            _t.sleep(0.25)
    else:
        raise RuntimeError("el servidor de prueba no respondió a tiempo")

    ENDPOINTS_INTERNOS = [
        ("POST", "/api/boletines/auditoria-sapred/999999/progreso", {"estado": "en_proceso"}),
        ("POST", "/api/boletines/generar-pdf/999999/ensamblar-sede", {"sede_id": 1, "sede_nombre": "x", "archivos": []}),
        ("POST", "/api/boletines/unir-pdfs", {"archivos": [], "salida": "x.pdf"}),
        ("POST", "/api/boletines/separar-por-seccion", {"archivo": "x.pdf", "carpeta_salida": "x"}),
        ("POST", "/api/boletines/importar-sapred-bloques", []),
        ("POST", "/api/boletines/importar-boletin-bloques", []),
        ("GET", "/api/estudiantes/conteo-por-sede?grado=6", None),
    ]
    CABECERA = seguridad.CABECERA_TOKEN_SERVICIO

    # ---- 3. Sin nada -------------------------------------------------------
    print("\n[3] Los 7 endpoints internos, SIN token y SIN sesión -> 403")
    anonimo = Cliente("anónimo")
    for metodo, ruta, cuerpo in ENDPOINTS_INTERNOS:
        estado, _ = anonimo.pedir(ruta, metodo, cuerpo)
        verificar(f"{metodo} {ruta} sin nada -> {estado}", estado == 403)

    # ---- 4. Con token correcto ----------------------------------------------
    print("\n[4] Los 7 endpoints internos, CON el token correcto (desde loopback)")
    servicio = Cliente("proceso-sapred")
    for metodo, ruta, cuerpo in ENDPOINTS_INTERNOS:
        estado, cuerpo_resp = servicio.pedir(ruta, metodo, cuerpo, {CABECERA: TOKEN_REAL})
        # 403 = el token fue rechazado (mal). Cualquier otra cosa (200, 404,
        # 400, 409...) significa que la identidad de servicio SÍ pasó y lo
        # que sigue es la lógica de negocio normal de cada endpoint (p. ej.
        # "auditoría 999999 no existe").
        verificar(f"{metodo} {ruta} con token -> {estado} (no 403)", estado != 403, str(cuerpo_resp))

    # ---- 5. Token incorrecto -------------------------------------------------
    print("\n[5] Token incorrecto, desde loopback -> 403")
    malicioso = Cliente("token-falso")
    estado, _ = malicioso.pedir(
        "/api/estudiantes/conteo-por-sede?grado=6", "GET", None, {CABECERA: "esto-no-es-el-token"}
    )
    verificar(f"token inventado -> {estado}", estado == 403)

    # ---- 6. Sesión HUMANA real (usuario de prueba, no sebastian.pai) --------
    print("\n[6] Sesión humana (usuario de prueba), SIN el token -> 403 en internos")
    navegador = Cliente("navegador-humano")
    estado, cuerpo = navegador.pedir("/api/auth/login", "POST", {
        "usuario": "PRUEBA-F41-ADMIN", "clave": CLAVE,
    })
    verificar(f"login del usuario de prueba responde {estado}", estado == 200, str(cuerpo))
    for metodo, ruta, cuerpo_datos in ENDPOINTS_INTERNOS:
        estado, _ = navegador.pedir(ruta, metodo, cuerpo_datos)  # con cookie, SIN el header de servicio
        verificar(
            f"{metodo} {ruta} con sesión humana pero sin token -> {estado} "
            "(ni el administrador de la app sirve aquí)",
            estado == 403,
        )

    # ---- 7. El token contra rutas humanas: rechazado -------------------------
    print("\n[7] El token de servicio contra rutas humanas")
    estado, _ = anonimo.pedir("/api/admin/usuarios", "GET", None, {CABECERA: TOKEN_REAL})
    verificar(f"GET /api/admin/usuarios con token SAPRED -> {estado} (rechazado igual, no mira el header)",
              estado in (401, 403))

    estado_con, cuerpo_con = anonimo.pedir("/api/estudiantes?grado=6", "GET", None, {CABECERA: TOKEN_REAL})
    estado_sin, cuerpo_sin = anonimo.pedir("/api/estudiantes?grado=6")
    verificar("GET /api/estudiantes completo: el token no cambia nada (misma respuesta con o sin él)",
              estado_con == estado_sin == 200)
    if cuerpo_con:
        verificar("...y sigue trayendo PII completa (no cambió de comportamiento en esta fase)",
                  "documento" in cuerpo_con[0] and "primer_nombre" in cuerpo_con[0])

    # ---- 8. Ruta reducida: solo sede_id + cantidad ---------------------------
    print("\n[8] Ruta reducida de conteo: solo sede_id y cantidad, nunca PII")
    estado, cuerpo = servicio.pedir("/api/estudiantes/conteo-por-sede?grado=6", "GET", None, {CABECERA: TOKEN_REAL})
    verificar(f"responde {estado}", estado == 200)
    if cuerpo:
        campos = set(cuerpo[0].keys())
        verificar(f"cada fila trae EXACTAMENTE sede_id y cantidad ({campos}), nada de PII",
                  campos == {"sede_id", "cantidad"})

    # ---- 9. El token nunca aparece en el log del servidor --------------------
    print("\n[9] El token no aparece en el log del servidor de prueba")

finally:
    servidor.terminate()
    servidor.wait(timeout=20)
    registro.close()

texto_log = (TMP / "servidor.log").read_text(encoding="utf-8", errors="replace")
verificar("el token de servicio no aparece en ningún lado del log", TOKEN_REAL not in texto_log)

from app.database import engine  # noqa: E402

engine.dispose()
shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'TODO OK' if not fallos else f'{fallos} FALLOS'}")
sys.exit(1 if fallos else 0)
