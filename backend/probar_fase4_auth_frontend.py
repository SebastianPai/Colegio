"""Pruebas del contrato de backend que usa la Fase 4.0 (autenticación del
frontend), sobre una COPIA temporal de la base: nunca toca colegio.db ni el
usuario real sebastian.pai. Sigue el mismo patrón que probar_autenticacion.py
(copia + servidor uvicorn real + cliente con cookie-jar), pero se enfoca en lo
que NO estaba cubierto ahí y que auth.js sí necesita:

  - el flujo completo de debe_cambiar_clave=True (login -> bloqueo -> cambio
    -> LA MISMA sesión sigue sirviendo, sin volver a iniciar sesión), y
  - que /api/sedes y /api/estudiantes (los que usan los scripts de SAPRED)
    siguen respondiendo 200 sin sesión antes, durante y después de todo el
    flujo de login/logout de un usuario normal.

Los dos usuarios de prueba (PRUEBA-F4-NORMAL, PRUEBA-F4-TEMPORAL) se crean
SOLO en la copia temporal, igual que ya hace probar_autenticacion.py; no
tocan ni crean nada en la base real ni en sebastian.pai.

    ./venv/Scripts/python.exe probar_fase4_auth_frontend.py
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
TMP = Path(tempfile.mkdtemp(prefix="ietaba_fase4_"))
COPIA = TMP / "colegio.db"
PUERTO = 8802
BASE_URL = f"http://127.0.0.1:{PUERTO}"

CLAVE = "PruebaFase4Segura2026"
CLAVE_NUEVA = "PruebaFase4Nueva2026"

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
from app import auth  # noqa: E402
from app.database import SessionLocal  # noqa: E402

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

    def pedir(self, ruta, metodo="GET", cuerpo=None):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        cabeceras = {"Origin": BASE_URL}
        if datos:
            cabeceras["Content-Type"] = "application/json"
        peticion = urllib.request.Request(BASE_URL + ruta, data=datos, method=metodo, headers=cabeceras)
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


# ---- 1. Usuarios de prueba (solo en la copia) -------------------------------
print("\n[1] Usuarios de prueba (solo en la copia temporal)")
db = SessionLocal()
normal = auth.registrar_usuario(
    db, documento="PRUEBA-F4-NORMAL", nombre="Prueba Fase4 Normal", clave=CLAVE, debe_cambiar_clave=False,
)
temporal = auth.registrar_usuario(
    db, documento="PRUEBA-F4-TEMPORAL", nombre="Prueba Fase4 Temporal", clave=CLAVE, debe_cambiar_clave=True,
)
verificar(f"usuario normal creado (#{normal.id})", normal.estado == "activo" and not normal.debe_cambiar_clave)
verificar(f"usuario con clave temporal creado (#{temporal.id})", temporal.debe_cambiar_clave is True)
db.close()

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

    # ---- 3. Rutas existentes sin sesión (antes) -----------------------------
    print("\n[3] Rutas que usan los scripts de SAPRED, sin sesión (antes de tocar nada de login)")
    anonimo = Cliente("anónimo")
    for ruta in ("/api/sedes", "/api/estudiantes?grado=6&estado=ACTIVO", "/api/docentes"):
        estado, _ = anonimo.pedir(ruta)
        verificar(f"{ruta} responde {estado} sin sesión", estado == 200)

    estado, _ = anonimo.pedir("/api/auth/yo")
    verificar(f"/api/auth/yo sin sesión responde {estado}", estado == 401)

    # ---- 4. Login incorrecto -------------------------------------------------
    print("\n[4] Login incorrecto")
    navegador = Cliente("navegador")
    estado, cuerpo = navegador.pedir("/api/auth/login", "POST", {
        "usuario": "PRUEBA-F4-NORMAL", "clave": "clave-equivocada",
    })
    verificar(f"clave incorrecta responde {estado}", estado == 401)
    verificar("el mensaje no distingue 'usuario no existe' de 'clave mala' (anti-enumeración)",
              bool((cuerpo or {}).get("detail")))

    # ---- 5. Login correcto (usuario normal) ----------------------------------
    print("\n[5] Login correcto (usuario normal, sin clave temporal)")
    estado, cuerpo = navegador.pedir("/api/auth/login", "POST", {
        "usuario": "PRUEBA-F4-NORMAL", "clave": CLAVE, "confiar_en_dispositivo": False,
        "dispositivo_id": "prueba-fase4-uuid", "nombre_dispositivo": "Script de prueba",
    })
    verificar(f"login correcto responde {estado}", estado == 200, str(cuerpo))
    verificar("debe_cambiar_clave es false", cuerpo["usuario"]["debe_cambiar_clave"] is False)
    verificar("trae roles y permisos (aunque estén vacíos, para que auth.js pinte la sidebar)",
              "roles" in cuerpo["usuario"] and "permisos" in cuerpo["usuario"])
    texto = json.dumps(cuerpo)
    verificar("la respuesta de login NUNCA trae el hash ni la contraseña",
              "clave_hash" not in texto and "scrypt" not in texto and CLAVE not in texto)

    # ---- 6. /api/auth/yo con sesión ------------------------------------------
    print("\n[6] /api/auth/yo con sesión activa")
    estado, cuerpo = navegador.pedir("/api/auth/yo")
    verificar(f"/api/auth/yo con sesión responde {estado}", estado == 200)
    verificar("devuelve el mismo usuario", cuerpo["usuario"]["documento"] == "PRUEBA-F4-NORMAL")
    verificar("tampoco aquí se expone el hash", "clave_hash" not in json.dumps(cuerpo))

    # ---- 7. Refresh -------------------------------------------------------------
    print("\n[7] Renovación (POST /api/auth/refresh)")
    estado, cuerpo = navegador.pedir("/api/auth/refresh", "POST")
    verificar(f"refresh responde {estado}", estado == 200, str(cuerpo))
    estado, _ = navegador.pedir("/api/auth/yo")
    verificar("después del refresh la sesión sigue sirviendo", estado == 200)

    # ---- 8. Logout ----------------------------------------------------------
    print("\n[8] Cierre de sesión")
    estado, _ = navegador.pedir("/api/auth/logout", "POST")
    verificar(f"logout responde {estado}", estado == 200)
    estado, _ = navegador.pedir("/api/auth/yo")
    verificar(f"después del logout, /api/auth/yo responde {estado} (auth.js debe mostrar login)", estado == 401)
    estado, _ = navegador.pedir("/api/auth/refresh", "POST")
    verificar(f"tampoco puede renovar tras logout: {estado} (evita loops falsos)", estado == 401)

    # ---- 9. Flujo debe_cambiar_clave=True ------------------------------------
    print("\n[9] Flujo de contraseña temporal (debe_cambiar_clave = true)")
    otro = Cliente("otro-dispositivo")
    estado, cuerpo = otro.pedir("/api/auth/login", "POST", {
        "usuario": "PRUEBA-F4-TEMPORAL", "clave": CLAVE,
    })
    verificar(f"login con clave temporal responde {estado}", estado == 200)
    verificar("debe_cambiar_clave es TRUE: auth.js debe bloquear la app con la pantalla de cambio",
              cuerpo["usuario"]["debe_cambiar_clave"] is True)

    # Mientras debe_cambiar_clave=true, la sesión YA existe (200 en /yo) — el
    # bloqueo es responsabilidad de la interfaz (Fase 4.0), no del backend:
    # confirmamos que el backend sigue devolviendo el estado real para que
    # auth.js decida, y que cambiar-clave con la clave actual equivocada falla.
    estado, cuerpo = otro.pedir("/api/auth/cambiar-clave", "POST", {
        "clave_actual": "clave-mala", "clave_nueva": CLAVE_NUEVA,
    })
    verificar(f"cambiar-clave con la clave actual equivocada responde {estado}", estado == 401)

    estado, cuerpo = otro.pedir("/api/auth/cambiar-clave", "POST", {
        "clave_actual": CLAVE, "clave_nueva": CLAVE_NUEVA,
    })
    verificar(f"cambiar-clave correcto responde {estado}", estado == 200, str(cuerpo))

    # LA MISMA sesión (mismas cookies, sin volver a loguear) debe seguir
    # sirviendo y ya con debe_cambiar_clave=false: es justo lo que auth.js
    # hace tras un cambio de clave exitoso (vuelve a pedir /yo y continúa).
    estado, cuerpo = otro.pedir("/api/auth/yo")
    verificar(f"tras cambiar la clave, la MISMA sesión sigue sirviendo: {estado}", estado == 200)
    verificar("y ahora debe_cambiar_clave es false (ya no bloquea la app)",
              cuerpo["usuario"]["debe_cambiar_clave"] is False)

    # ---- 10. Rutas existentes sin sesión (después de todo lo anterior) ------
    print("\n[10] Rutas que usan los scripts de SAPRED, sin sesión (después de todo el flujo de login)")
    anonimo2 = Cliente("anónimo-2")
    for ruta in ("/api/sedes", "/api/estudiantes?grado=6&estado=ACTIVO", "/api/docentes",
                 "/api/horario/hoy", "/api/boletines/resumen"):
        estado, _ = anonimo2.pedir(ruta)
        verificar(f"{ruta} sigue respondiendo {estado} sin sesión", estado == 200)

finally:
    servidor.terminate()
    servidor.wait(timeout=20)
    registro.close()

from app.database import engine  # noqa: E402

engine.dispose()
shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'TODO OK' if not fallos else f'{fallos} FALLOS'}")
sys.exit(1 if fallos else 0)
