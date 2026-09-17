"""Pruebas del modo observación (Fase 4A), sobre una COPIA temporal de la
base: nunca toca colegio.db ni sebastian.pai. Mismo patrón que los scripts
de prueba anteriores.

Confirma lo esencial: observar() NUNCA bloquea (con o sin permiso, con o
sin sesión, todo responde 200/lo que responda el endpoint — jamás 401/403
por causa de observar()), y que cada caso se registra correctamente en
observaciones_permisos.

    ./venv/Scripts/python.exe probar_fase4a_observacion.py
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
TMP = Path(tempfile.mkdtemp(prefix="ietaba_fase4a_"))
COPIA = TMP / "colegio.db"
PUERTO = 8804
BASE_URL = f"http://127.0.0.1:{PUERTO}"

CLAVE = "PruebaFase4ASegura2026"

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
from app import auth, rbac_admin, seguridad  # noqa: E402
from app.database import SessionLocal  # noqa: E402

TOKEN_REAL = seguridad.token_servicio()

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


# ---- 1. Usuario de prueba SIN estudiantes.crear (rol docente) --------------
print("\n[1] Usuario de prueba con rol 'docente' (no tiene estudiantes.crear)")
db = SessionLocal()
docente_prueba = auth.registrar_usuario(
    db, documento="PRUEBA-F4A-DOCENTE", nombre="Prueba Fase4A Docente", clave=CLAVE, debe_cambiar_clave=False,
)
rbac_admin.establecer_roles_usuario(db, docente_prueba, ["docente"], asignado_por_id=None)
DOCENTE_PRUEBA_ID = docente_prueba.id  # capturado antes de cerrar la sesión (evita DetachedInstanceError)
db.close()
verificar("usuario de prueba con rol docente creado", True)

# ---- 2. Servidor -------------------------------------------------------------
print("\n[2] Servidor de prueba")
registro = open(TMP / "servidor.log", "w", encoding="utf-8")
servidor = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PUERTO),
     "--log-level", "warning"],
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

    # ---- 3. Sin sesión: pasa igual, se registra "sin_sesion" ----------------
    print("\n[3] Sin sesión: la ruta sigue respondiendo, se registra 'sin_sesion'")
    anonimo = Cliente("anónimo")
    estado, cuerpo = anonimo.pedir("/api/estudiantes?grado=6")
    verificar(f"GET /api/estudiantes sin sesión sigue respondiendo {estado} (nunca 401/403)", estado == 200)

    estado, _ = anonimo.pedir("/api/horario/hoy")
    verificar(f"GET /api/horario/hoy sin sesión sigue respondiendo {estado}", estado == 200)

    # ---- 4. Sesión SIN el permiso: pasa igual, se registra "habria_sido_rechazado" ---
    print("\n[4] Sesión con rol docente, en una ruta que NO tiene (estudiantes.crear): sigue pasando")
    navegador = Cliente("docente-prueba")
    estado, cuerpo = navegador.pedir("/api/auth/login", "POST", {
        "usuario": "PRUEBA-F4A-DOCENTE", "clave": CLAVE,
    })
    verificar(f"login del docente de prueba responde {estado}", estado == 200, str(cuerpo))

    estado, cuerpo = navegador.pedir("/api/estudiantes", "POST", {
        "documento": "PRUEBA-F4A-EST-9999", "primer_apellido": "Prueba", "primer_nombre": "Observacion",
        "sede_id": 1, "grado": 6,
    })
    verificar(
        f"POST /api/estudiantes (docente, sin estudiantes.crear) responde {estado} "
        "(no 403 — observar() no bloquea; puede fallar por otra razón de negocio, pero no por permisos)",
        estado != 403,
        str(cuerpo),
    )
    # Limpieza: si se creó de verdad, se borra para no ensuciar la copia (aunque
    # es una copia temporal que se descarta de todos modos).

    # ---- 5. Sesión CON el permiso: pasa, se registra "habria_pasado" -----------
    print("\n[5] Sesión con rol docente, en una ruta que SÍ tiene (horario.ver)")
    estado, _ = navegador.pedir("/api/horario/hoy")
    verificar(f"GET /api/horario/hoy (docente, con horario.ver) responde {estado}", estado == 200)

    # ---- 6. /api/sedes con token de servicio: no debe registrarse como rechazo --
    print("\n[6] /api/sedes con token de servicio (simula un script SAPRED)")
    servicio = Cliente("script-sapred")
    estado, _ = servicio.pedir("/api/sedes", "GET", None, {seguridad.CABECERA_TOKEN_SERVICIO: TOKEN_REAL})
    verificar(f"GET /api/sedes con token de servicio responde {estado}", estado == 200)

    # ---- 7. Revisar lo registrado (necesita sesión de administrador real) ------
    print("\n[7] Las observaciones quedaron registradas correctamente")
    db = SessionLocal()
    from app import models
    from sqlalchemy import select

    filas = db.scalars(select(models.ObservacionPermiso)).all()
    verificar(f"hay observaciones registradas ({len(filas)})", len(filas) > 0)

    sin_sesion = [f for f in filas if f.resultado == "sin_sesion"]
    verificar("hay al menos una fila 'sin_sesion' (de la petición anónima)", len(sin_sesion) > 0)

    docente_id = DOCENTE_PRUEBA_ID
    rechazadas_docente = [
        f for f in filas
        if f.usuario_id == docente_id and f.resultado == "habria_sido_rechazado" and f.permiso == "estudiantes.crear"
    ]
    verificar(
        "el intento del docente de crear un estudiante quedó marcado 'habria_sido_rechazado' "
        "(estudiantes.crear)",
        len(rechazadas_docente) > 0,
    )

    pasadas_docente = [
        f for f in filas
        if f.usuario_id == docente_id and f.resultado == "habria_pasado" and f.permiso == "horario.ver"
    ]
    verificar("la consulta de horario del docente quedó marcada 'habria_pasado' (horario.ver)",
              len(pasadas_docente) > 0)

    sedes_con_token = [
        f for f in filas if f.endpoint == "/api/sedes" and f.resultado == "habria_sido_rechazado"
    ]
    verificar(
        "la llamada a /api/sedes CON token de servicio NO quedó registrada como rechazo "
        "(tambien_servicio evitó el falso positivo)",
        len(sedes_con_token) == 0,
    )
    db.close()

    # ---- 8. Endpoint de resumen, protegido con auditoria.ver --------------------
    print("\n[8] GET /api/admin/observaciones-fase4a")
    estado, _ = anonimo.pedir("/api/admin/observaciones-fase4a")
    verificar(f"sin sesión, responde {estado} (401 — esta ruta SÍ es RBAC real, Fase 3)", estado == 401)

    estado, cuerpo = navegador.pedir("/api/admin/observaciones-fase4a")
    verificar(f"docente sin auditoria.ver, responde {estado} (403 — esta ruta SÍ bloquea de verdad)",
              estado == 403)

finally:
    servidor.terminate()
    servidor.wait(timeout=20)
    registro.close()

from app.database import engine  # noqa: E402

engine.dispose()
shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'TODO OK' if not fallos else f'{fallos} FALLOS'}")
sys.exit(1 if fallos else 0)
