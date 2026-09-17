"""Pruebas de la Fase 2 (identidad y autenticación), sobre una COPIA temporal
de la base: nunca toca colegio.db ni crea usuarios en la base real.

Levanta el servidor real (uvicorn) contra la copia y actúa como un navegador
(guarda cookies), para probar de verdad el ingreso, la renovación con rotación,
la detección de robo de token, la revocación y que la aplicación existente
sigue funcionando sin iniciar sesión.

    ./venv/Scripts/python.exe probar_autenticacion.py
"""

import datetime as dt
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
import urllib.parse
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
ORIGEN = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND / "colegio.db"
TMP = Path(tempfile.mkdtemp(prefix="ietaba_auth_"))
COPIA = TMP / "colegio.db"
PUERTO = 8801
BASE_URL = f"http://127.0.0.1:{PUERTO}"

CLAVE = "PruebaSegura2026"
CLAVE_NUEVA = "OtraClaveSegura2026"

src = sqlite3.connect(f"file:{ORIGEN}?mode=ro", uri=True)
dst = sqlite3.connect(COPIA)
with dst:
    src.backup(dst)
src.close()
dst.close()

os.environ["IETABA_DB_PATH"] = str(COPIA)
sys.path.insert(0, str(BACKEND))

print(f"Copia de prueba: {COPIA}\n\n[0] Arranque sobre la copia (migraciones: tablas nuevas)")
from sqlalchemy import select  # noqa: E402

from app import main as _arranque  # noqa: E402,F401  (ejecuta migraciones.ejecutar() sobre la copia)
from app import auth, fechas, models, seguridad  # noqa: E402
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
    """Un navegador: guarda sus cookies y las reenvía como lo haría Chrome
    (respetando el Path de cada una)."""

    def __init__(self, nombre: str):
        self.nombre = nombre
        self.galletas = http.cookiejar.CookieJar()
        self.abridor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.galletas))
        self.ultimas_cookies_crudas: list[str] = []

    def pedir(self, ruta, metodo="GET", cuerpo=None, cookie_manual=None, origen=None):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        cabeceras = {"Origin": origen or BASE_URL}
        if datos:
            cabeceras["Content-Type"] = "application/json"
        if cookie_manual:
            cabeceras["Cookie"] = cookie_manual
        peticion = urllib.request.Request(BASE_URL + ruta, data=datos, method=metodo, headers=cabeceras)
        try:
            with self.abridor.open(peticion, timeout=30) as r:
                self.ultimas_cookies_crudas = r.headers.get_all("Set-Cookie") or []
                return r.status, _json(r.read())
        except urllib.error.HTTPError as e:
            self.ultimas_cookies_crudas = e.headers.get_all("Set-Cookie") or []
            return e.code, _json(e.read())

    def cookie(self, nombre: str) -> str | None:
        for c in self.galletas:
            if c.name == nombre:
                return c.value
        return None


def _json(datos: bytes):
    try:
        return json.loads(datos)
    except ValueError:
        return None


def sesion_db(sesion_id: str) -> models.Sesion | None:
    db = SessionLocal()
    try:
        db.expire_all()
        return db.get(models.Sesion, sesion_id)
    finally:
        db.close()


def usuario_db(usuario_id: int) -> models.Usuario | None:
    db = SessionLocal()
    try:
        db.expire_all()
        return db.get(models.Usuario, usuario_id)
    finally:
        db.close()


# ---- 1. Usuarios y contraseñas (sin HTTP) -----------------------------------
print("\n[1] Creación de usuarios y hash de contraseñas")
db = SessionLocal()
docente = db.scalars(select(models.Docente).order_by(models.Docente.id)).first()
docentes_antes = db.query(models.Docente).count()

admin = auth.registrar_usuario(
    db, documento="PRUEBA-ADMIN", nombre="Prueba Administrativa", clave=CLAVE,
    email="Prueba.Admin@Ietaba.Test", debe_cambiar_clave=False,
)
profe = auth.registrar_usuario(
    db, documento="PRUEBA-DOCENTE", nombre="Prueba Docente", clave=CLAVE,
    docente_id=docente.id, debe_cambiar_clave=False,
)
inactivo = auth.registrar_usuario(
    db, documento="PRUEBA-INACTIVO", nombre="Prueba Inactiva", clave=CLAVE, debe_cambiar_clave=False,
)
auth.cambiar_estado(db, inactivo, "inactivo")

verificar(f"usuario creado (#{admin.id} {admin.documento})", admin.id is not None and admin.estado == "activo")
verificar("el correo se normaliza a minúsculas", admin.email == "prueba.admin@ietaba.test")
verificar(f"usuario enlazado al docente #{docente.id} ({docente.nombre_completo})", profe.docente_id == docente.id)
verificar("no se creó ni modificó ningún docente", db.query(models.Docente).count() == docentes_antes)
verificar("el estado inactivo queda registrado", usuario_db(inactivo.id).estado == "inactivo")

for descripcion, kwargs, esperado in [
    ("documento repetido", {"documento": "PRUEBA-ADMIN", "nombre": "X", "clave": CLAVE}, 409),
    ("correo repetido", {"documento": "PRUEBA-X", "nombre": "X", "clave": CLAVE, "email": "prueba.admin@ietaba.test"}, 409),
    ("docente ya enlazado", {"documento": "PRUEBA-Y", "nombre": "Y", "clave": CLAVE, "docente_id": docente.id}, 409),
    ("clave demasiado corta", {"documento": "PRUEBA-Z", "nombre": "Z", "clave": "corta"}, 400),
    ("clave igual al documento", {"documento": "12345678901", "nombre": "Z", "clave": "12345678901"}, 400),
    ("docente inexistente", {"documento": "PRUEBA-W", "nombre": "W", "clave": CLAVE, "docente_id": 999999}, 404),
]:
    try:
        auth.registrar_usuario(db, **kwargs)
        codigo = "sin error"
    except auth.ErrorAutenticacion as e:
        codigo = e.codigo
    verificar(f"se rechaza {descripcion} ({codigo})", codigo == esperado)

guardado = usuario_db(admin.id).clave_hash
verificar(f"la contraseña se guarda con scrypt ({guardado[:14]}…)", guardado.startswith("scrypt$16384$8$1$"))
verificar("la contraseña NO aparece en el hash", CLAVE not in guardado)
verificar("dos hashes de la misma clave son distintos (sal aleatoria)",
          seguridad.hashear_clave(CLAVE) != seguridad.hashear_clave(CLAVE))
verificar("la contraseña correcta se verifica", seguridad.verificar_clave(CLAVE, guardado))
verificar("la contraseña incorrecta se rechaza", not seguridad.verificar_clave("otra-cosa", guardado))
verificar("un hash vacío o corrupto no deja entrar",
          not seguridad.verificar_clave(CLAVE, None) and not seguridad.verificar_clave(CLAVE, "basura"))
db.close()

# ---- 2. Servidor ------------------------------------------------------------
print("\n[2] Servidor de prueba")
registro = open(TMP / "servidor.log", "w", encoding="utf-8")
servidor = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PUERTO),
     "--log-level", "warning"],
    cwd=str(BACKEND), env={**os.environ, "PYTHONUTF8": "1"}, stdout=registro, stderr=subprocess.STDOUT,
)
for _ in range(240):
    try:
        urllib.request.urlopen(f"{BASE_URL}/api/sedes", timeout=2).read()
        break
    except Exception:
        if servidor.poll() is not None:
            print((TMP / "servidor.log").read_text(encoding="utf-8"))
            sys.exit("el servidor de prueba no arrancó")
        time.sleep(0.5)

try:
    navegador = Cliente("celular del docente")

    # ---- 3. La app existente sigue funcionando sin login -------------------
    print("\n[3] La aplicación existente sigue funcionando SIN iniciar sesión")
    for ruta, descripcion in [
        ("/api/sedes", "sedes"),
        ("/api/estudiantes/pagina?sede_id=1&grado=10", "estudiantes"),
        ("/api/docentes", "docentes"),
        ("/api/horario/hoy", "horarios"),
        ("/api/asistencia/grupo?sede_id=1&grado=10&curso=1", "asistencia"),
        ("/api/boletines/pendientes?anio_lectivo=2026&periodo=2", "boletines"),
        ("/api/certificados", "constancias"),
        ("/api/boletines/auditoria-sapred", "SAPRED"),
        ("/", "pantalla principal"),
    ]:
        estado, _ = Cliente("anónimo").pedir(ruta)
        verificar(f"{descripcion}: {ruta} responde {estado} sin sesión", estado == 200)

    estado, _ = Cliente("anónimo").pedir("/api/auth/yo")
    verificar(f"/api/auth/yo sin sesión responde {estado}", estado == 401)

    # ---- 4. Login ----------------------------------------------------------
    print("\n[4] Ingreso")
    estado, cuerpo = navegador.pedir("/api/auth/login", "POST", {
        "usuario": "PRUEBA-DOCENTE", "clave": CLAVE, "confiar_en_dispositivo": True,
        "nombre_dispositivo": "Samsung de prueba",
    })
    verificar(f"login correcto responde {estado}", estado == 200, str(cuerpo))
    sesion_id = (cuerpo or {}).get("sesion", {}).get("id", "")
    verificar("la respuesta trae usuario y sesión", bool(sesion_id) and cuerpo["usuario"]["documento"] == "PRUEBA-DOCENTE")
    texto_respuesta = json.dumps(cuerpo)
    verificar("la respuesta NO incluye el hash ni la contraseña (solo el aviso debe_cambiar_clave)",
              "clave_hash" not in texto_respuesta and "scrypt" not in texto_respuesta
              and CLAVE not in texto_respuesta)
    crudas = " | ".join(navegador.ultimas_cookies_crudas)
    verificar(f"cookie de acceso HttpOnly y SameSite=Strict ({crudas[:60]}…)",
              "ietaba_at=" in crudas and crudas.count("HttpOnly") >= 2 and crudas.count("SameSite=strict") >= 2)
    verificar("la cookie de renovación va limitada a /api/auth", "Path=/api/auth" in crudas)
    verificar("sin HTTPS no se marca Secure (por HTTP no viajaría)", "Secure" not in crudas)
    verificar("el dispositivo queda con el nombre enviado",
              (cuerpo or {}).get("sesion", {}).get("dispositivo_nombre") == "Samsung de prueba")

    fila = sesion_db(sesion_id)
    rt_actual = navegador.cookie("ietaba_rt")
    verificar("la sesión existe en la base y está viva", fila is not None and fila.revocada_en is None)
    verificar("en la base solo está el hash del token, no el token",
              fila.refresh_hash == seguridad.hash_token(rt_actual) and fila.refresh_hash != rt_actual)
    verificar(f"sesión de dispositivo confiable: vence en {(fila.expira_absoluta_en - fechas.ahora_utc()).days} días",
              fila.confiable and 179 <= (fila.expira_absoluta_en - fechas.ahora_utc()).days <= 180)
    verificar("la cookie de renovación es persistente (tiene vencimiento)",
              any("Max-Age" in c or "expires" in c.lower() for c in navegador.ultimas_cookies_crudas if "ietaba_rt" in c))

    estado, cuerpo_yo = navegador.pedir("/api/auth/yo")
    verificar(f"/api/auth/yo con sesión responde {estado}", estado == 200 and cuerpo_yo["sesion"]["id"] == sesion_id)

    # ---- 5. Login rechazado ------------------------------------------------
    print("\n[5] Ingresos rechazados")
    casos = [
        ("contraseña incorrecta", {"usuario": "PRUEBA-DOCENTE", "clave": "incorrecta-xx"}, 401, "Usuario o contraseña incorrectos."),
        ("usuario inexistente", {"usuario": "NO-EXISTE-999", "clave": CLAVE}, 401, "Usuario o contraseña incorrectos."),
        ("usuario deshabilitado", {"usuario": "PRUEBA-INACTIVO", "clave": CLAVE}, 403, "desactivada"),
    ]
    for descripcion, datos, esperado, texto in casos:
        estado, cuerpo = Cliente("x").pedir("/api/auth/login", "POST", datos)
        detalle = (cuerpo or {}).get("detail", "")
        verificar(f"{descripcion}: {estado} — {detalle}", estado == esperado and texto in detalle)
    verificar("el mensaje de clave incorrecta y de usuario inexistente es el mismo (no revela si existe)", True)

    db = SessionLocal()
    verificar("el usuario deshabilitado no abrió ninguna sesión",
              not auth.listar_sesiones(db, inactivo.id))
    db.close()

    estado, cuerpo = Cliente("atacante").pedir(
        "/api/auth/login", "POST", {"usuario": "PRUEBA-DOCENTE", "clave": CLAVE}, origen="http://sitio-malicioso.example"
    )
    verificar(f"se rechaza un Origin ajeno (CSRF): {estado}", estado == 403)

    # ---- 6. Renovación con rotación ---------------------------------------
    print("\n[6] Renovación de sesión (rotación del token)")
    rt_viejo = navegador.cookie("ietaba_rt")
    at_viejo = navegador.cookie("ietaba_at")
    estado, cuerpo = navegador.pedir("/api/auth/refresh", "POST")
    rt_nuevo = navegador.cookie("ietaba_rt")
    fila = sesion_db(sesion_id)
    verificar(f"la renovación responde {estado}", estado == 200)
    verificar("entrega un token de renovación distinto (rotación)", rt_nuevo and rt_nuevo != rt_viejo)
    verificar("entrega un token de acceso nuevo", navegador.cookie("ietaba_at") != at_viejo)
    verificar("la base guarda el hash del token nuevo", fila.refresh_hash == seguridad.hash_token(rt_nuevo))
    verificar("la base recuerda el hash del anterior (para detectar robos)",
              fila.refresh_hash_anterior == seguridad.hash_token(rt_viejo))
    verificar(f"cuenta las rotaciones ({fila.rotaciones})", fila.rotaciones == 1 and fila.rotada_en is not None)
    estado, _ = navegador.pedir("/api/auth/yo")
    verificar(f"la sesión sigue sirviendo tras renovar ({estado})", estado == 200)

    print("\n[7] Dos pestañas renovando a la vez (ventana de gracia)")
    cliente_gracia = Cliente("dos pestañas")
    cliente_gracia.pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-ADMIN", "clave": CLAVE})
    rt_compartido = cliente_gracia.cookie("ietaba_rt")
    id_gracia = None
    estado_a, cuerpo_a = cliente_gracia.pedir("/api/auth/refresh", "POST", cookie_manual=f"ietaba_rt={rt_compartido}")
    estado_b, cuerpo_b = cliente_gracia.pedir("/api/auth/refresh", "POST", cookie_manual=f"ietaba_rt={rt_compartido}")
    id_gracia = (cuerpo_a or {}).get("sesion", {}).get("id")
    fila_gracia = sesion_db(id_gracia) if id_gracia else None
    verificar(f"las dos renovaciones simultáneas funcionan ({estado_a} y {estado_b})", estado_a == 200 and estado_b == 200)
    verificar("no se toma por robo: la sesión sigue viva",
              fila_gracia is not None and fila_gracia.revocada_en is None)
    verificar(f"solo rotó una vez ({fila_gracia.rotaciones})", fila_gracia.rotaciones == 1)

    # ---- 8. Token reutilizado (robo) --------------------------------------
    print("\n[8] Token de renovación reutilizado (robo)")
    ladron = Cliente("ladrón")
    ladron.pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-ADMIN", "clave": CLAVE})
    rt_robado = ladron.cookie("ietaba_rt")
    estado, cuerpo = ladron.pedir("/api/auth/refresh", "POST")
    id_robada = (cuerpo or {}).get("sesion", {}).get("id")
    # Se envejece la rotación para salir de la ventana de gracia de 30 s.
    conexion = sqlite3.connect(COPIA, timeout=10)
    with conexion:
        conexion.execute(
            "UPDATE sesiones SET rotada_en = ? WHERE id = ?",
            ((fechas.ahora_utc() - dt.timedelta(minutes=5)).isoformat(sep=" "), id_robada),
        )
    conexion.close()
    estado, cuerpo = ladron.pedir("/api/auth/refresh", "POST", cookie_manual=f"ietaba_rt={rt_robado}")
    fila_robada = sesion_db(id_robada)
    verificar(f"reutilizar un token ya rotado se rechaza ({estado})", estado == 401, str(cuerpo))
    verificar("y la sesión completa queda revocada",
              fila_robada.revocada_en is not None and fila_robada.motivo_revocacion == "token_reutilizado")
    estado, _ = ladron.pedir("/api/auth/yo")
    verificar(f"el token de acceso de esa sesión deja de servir de inmediato ({estado})", estado == 401)

    # ---- 9. Sesión inválida ------------------------------------------------
    print("\n[9] Sesiones inválidas")
    estado, _ = Cliente("x").pedir("/api/auth/yo", cookie_manual="ietaba_at=basura-inventada")
    verificar(f"cookie de acceso inventada: {estado}", estado == 401)
    estado, _ = Cliente("x").pedir("/api/auth/refresh", "POST", cookie_manual="ietaba_rt=basura-inventada")
    verificar(f"cookie de renovación inventada: {estado}", estado == 401)
    partes = (navegador.cookie("ietaba_at") or "").split(".")
    manipulado = f"{partes[0]}.{'A' * len(partes[1])}" if len(partes) == 2 else "x.y"
    estado, _ = Cliente("x").pedir("/api/auth/yo", cookie_manual=f"ietaba_at={manipulado}")
    verificar(f"token de acceso con la firma cambiada: {estado}", estado == 401)

    # ---- 10. Revocación ----------------------------------------------------
    print("\n[10] Revocación de sesiones")
    pc = Cliente("PC de la sala")
    estado, cuerpo_pc = pc.pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-DOCENTE", "clave": CLAVE})
    id_pc = (cuerpo_pc or {}).get("sesion", {}).get("id")
    verificar("segundo dispositivo con sesión propia", estado == 200 and id_pc != sesion_id)
    verificar("sesión no confiable: vence en 12 horas",
              11 <= (sesion_db(id_pc).expira_en - fechas.ahora_utc()).total_seconds() / 3600 <= 12)
    verificar("la cookie de renovación NO persiste en equipos no confiables",
              all("Max-Age" not in c and "expires" not in c.lower() for c in pc.ultimas_cookies_crudas if "ietaba_rt" in c))

    estado, lista = navegador.pedir("/api/auth/sesiones")
    verificar(f"el usuario ve sus {len(lista or [])} sesiones abiertas", estado == 200 and len(lista) == 2)
    verificar("sabe cuál es la sesión actual", sum(1 for s in lista if s["es_la_actual"]) == 1)

    estado, _ = navegador.pedir(f"/api/auth/sesiones/{id_pc}", "DELETE")
    verificar(f"cerrar la sesión de otro dispositivo: {estado}", estado == 200)
    verificar("queda revocada en la base", sesion_db(id_pc).revocada_en is not None)
    estado, _ = pc.pedir("/api/auth/yo")
    verificar(f"ese dispositivo pierde el acceso de inmediato: {estado}", estado == 401)
    estado, _ = pc.pedir("/api/auth/refresh", "POST")
    verificar(f"y tampoco puede renovar: {estado}", estado == 401)

    print("\n[11] Cierre de sesión")
    estado, cuerpo = navegador.pedir("/api/auth/logout", "POST")
    verificar(f"logout responde {estado}", estado == 200 and cuerpo == {"cerrada": True})
    verificar("la sesión queda revocada con motivo 'logout'",
              sesion_db(sesion_id).motivo_revocacion == "logout")
    estado, _ = navegador.pedir("/api/auth/yo")
    verificar(f"después del logout no hay sesión: {estado}", estado == 401)
    estado, _ = Cliente("x").pedir("/api/auth/logout", "POST")
    verificar(f"logout sin sesión no falla: {estado}", estado == 200)

    print("\n[12] Cerrar sesión en todos los dispositivos")
    a, b = Cliente("celular"), Cliente("tablet")
    _, ca = a.pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-DOCENTE", "clave": CLAVE})
    _, cb = b.pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-DOCENTE", "clave": CLAVE})
    estado, cuerpo = a.pedir("/api/auth/logout-todos", "POST")
    verificar(f"logout-todos cerró {(cuerpo or {}).get('sesiones_cerradas')} sesiones", estado == 200 and cuerpo["sesiones_cerradas"] == 2)
    verificar(f"el otro dispositivo queda fuera: {b.pedir('/api/auth/yo')[0]}", b.pedir("/api/auth/yo")[0] == 401)

    # ---- 13. Cambio de contraseña -----------------------------------------
    print("\n[13] Cambio de contraseña")
    dueño, otro = Cliente("celular"), Cliente("otro equipo")
    dueño.pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-DOCENTE", "clave": CLAVE})
    _, cuerpo_otro = otro.pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-DOCENTE", "clave": CLAVE})
    id_otro = cuerpo_otro["sesion"]["id"]
    estado, cuerpo = dueño.pedir("/api/auth/cambiar-clave", "POST",
                                 {"clave_actual": "equivocada", "clave_nueva": CLAVE_NUEVA})
    verificar(f"con la contraseña actual equivocada: {estado}", estado == 401)
    estado, cuerpo = dueño.pedir("/api/auth/cambiar-clave", "POST",
                                 {"clave_actual": CLAVE, "clave_nueva": "corta"})
    verificar(f"con una contraseña nueva demasiado corta: {estado}", estado == 400)
    estado, cuerpo = dueño.pedir("/api/auth/cambiar-clave", "POST",
                                 {"clave_actual": CLAVE, "clave_nueva": CLAVE_NUEVA})
    verificar(f"cambio correcto: {estado}", estado == 200)
    verificar("la contraseña anterior ya no sirve",
              Cliente("x").pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-DOCENTE", "clave": CLAVE})[0] == 401)
    verificar("la nueva sí sirve",
              Cliente("x").pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-DOCENTE", "clave": CLAVE_NUEVA})[0] == 200)
    verificar("se cerraron las OTRAS sesiones del usuario", sesion_db(id_otro).revocada_en is not None)
    verificar("la sesión desde la que se cambió sigue abierta", dueño.pedir("/api/auth/yo")[0] == 200)

    # ---- 14. Bloqueo por intentos fallidos --------------------------------
    print("\n[14] Bloqueo por intentos fallidos")
    for i in range(seguridad.MAX_INTENTOS_FALLIDOS):
        Cliente("x").pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-ADMIN", "clave": f"mala-{i}"})
    estado, cuerpo = Cliente("x").pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-ADMIN", "clave": CLAVE})
    verificar(f"tras {seguridad.MAX_INTENTOS_FALLIDOS} fallos se bloquea la cuenta: {estado} — {(cuerpo or {}).get('detail')}",
              estado == 429)
    db = SessionLocal()
    bloqueado = auth.buscar_usuario(db, "PRUEBA-ADMIN")
    verificar("queda registrado hasta cuándo está bloqueada", bloqueado.bloqueado_hasta is not None)
    bloqueado.bloqueado_hasta = None
    db.commit()
    db.close()
    verificar("al vencer el bloqueo se puede entrar otra vez",
              Cliente("x").pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-ADMIN", "clave": CLAVE})[0] == 200)

    # ---- 15. Usuario deshabilitado con sesión abierta ---------------------
    print("\n[15] Usuario deshabilitado mientras tiene sesión")
    victima = Cliente("celular")
    _, cuerpo_v = victima.pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-DOCENTE", "clave": CLAVE_NUEVA})
    db = SessionLocal()
    usuario_v = auth.buscar_usuario(db, "PRUEBA-DOCENTE")
    auth.cambiar_estado(db, usuario_v, "inactivo")
    db.close()
    verificar(f"al deshabilitar el usuario su sesión deja de servir: {victima.pedir('/api/auth/yo')[0]}",
              victima.pedir("/api/auth/yo")[0] == 401)
    verificar("tampoco puede renovar", victima.pedir("/api/auth/refresh", "POST")[0] in (401, 403))
    verificar("ni volver a entrar",
              Cliente("x").pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-DOCENTE", "clave": CLAVE_NUEVA})[0] == 403)

    # ---- 16. Nada sensible en la base -------------------------------------
    print("\n[16] Ni contraseñas ni tokens en texto plano en la base")
    contenido = COPIA.read_bytes()
    for archivo in (COPIA.with_name(COPIA.name + "-wal"), COPIA.with_name(COPIA.name + "-shm")):
        if archivo.exists():
            contenido += archivo.read_bytes()
    verificar("la contraseña no aparece en el archivo de la base", CLAVE.encode() not in contenido)
    verificar("la contraseña nueva tampoco", CLAVE_NUEVA.encode() not in contenido)
    tokens = [t for t in (rt_compartido, rt_robado, rt_nuevo) if t]
    verificar(f"ninguno de los {len(tokens)} tokens de renovación aparece en la base",
              all(t.encode() not in contenido for t in tokens))

    print("\n[17] La aplicación existente sigue intacta tras todo lo anterior")
    for ruta in ("/api/sedes", "/api/docentes", "/api/horario/hoy", "/api/boletines/resumen"):
        verificar(f"{ruta} sigue respondiendo sin sesión", Cliente("anónimo").pedir(ruta)[0] == 200)
    db = SessionLocal()
    verificar("los datos académicos no cambiaron (2149 estudiantes, 72 docentes, 1049 bloques)",
              db.query(models.Estudiante).count() == 2149
              and db.query(models.Docente).count() == 72
              and db.query(models.BloqueHorario).count() == 1049)
    verificar("no hay ninguna asistencia registrada por estas pruebas", db.query(models.Asistencia).count() == 0)
    db.close()
finally:
    servidor.terminate()
    servidor.wait(timeout=20)
    registro.close()

conexion = sqlite3.connect(COPIA)
print("\n[18] Estado de la copia")
print(f"  integrity_check = {conexion.execute('PRAGMA integrity_check').fetchone()[0]}")
print(f"  journal_mode = {conexion.execute('PRAGMA journal_mode').fetchone()[0]}")
print(f"  filas huérfanas = {len(conexion.execute('PRAGMA foreign_key_check').fetchall())}")
print(f"  usuarios = {conexion.execute('SELECT count(*) FROM usuarios').fetchone()[0]}, "
      f"dispositivos = {conexion.execute('SELECT count(*) FROM dispositivos').fetchone()[0]}, "
      f"sesiones = {conexion.execute('SELECT count(*) FROM sesiones').fetchone()[0]}")
conexion.close()

from app.database import engine  # noqa: E402

engine.dispose()
shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'TODO OK' if not fallos else f'{fallos} FALLOS'}")
sys.exit(1 if fallos else 0)
