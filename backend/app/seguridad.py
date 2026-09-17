"""Contraseñas, tokens y cookies de sesión. Solo biblioteca estándar.

Decisiones (Fase 2 de la arquitectura acordada):

  · Contraseñas: scrypt de hashlib (no hace falta instalar nada). Nunca se
    guarda la contraseña, solo `scrypt$n$r$p$sal$hash`, y se compara en
    tiempo constante.
  · Token de ACCESO: corto (15 min), firmado con HMAC-SHA256 y guardado en
    una cookie HttpOnly. No se guarda en la base: se verifica con la firma y
    además se comprueba que su sesión siga viva, así revocar una sesión tiene
    efecto inmediato y no hay que esperar los 15 minutos.
  · Token de RENOVACIÓN: 32 bytes aleatorios. En la base solo queda su
    SHA-256 (si alguien lee la base, no puede usarlos). Rota en cada uso.
  · Cookies HttpOnly: JavaScript no puede leerlas, así que un XSS no puede
    robar la sesión. Nunca se guardan tokens en localStorage.
  · `Secure` se activa solo cuando la petición llega por HTTPS: en la red del
    colegio la app todavía se usa por HTTP en el puerto 8000, y una cookie
    Secure no viajaría por ahí. Ver la nota de riesgo del informe.
"""

import base64
import datetime as dt
import hashlib
import hmac
import os
import secrets
from pathlib import Path

from . import fechas

# --- Parámetros (se pueden ajustar después desde configuración) --------------

MINUTOS_TOKEN_ACCESO = 15
DIAS_SESION_CONFIABLE = 60          # sin usarla; cada uso la extiende
DIAS_SESION_CONFIABLE_MAXIMO = 180  # tope absoluto: después se pide la clave
HORAS_SESION_NO_CONFIABLE = 12      # equipos compartidos (secretaría, sala)
SEGUNDOS_GRACIA_ROTACION = 30       # dos pestañas renovando a la vez
MAX_INTENTOS_FALLIDOS = 5
MINUTOS_BLOQUEO = 15
LARGO_MINIMO_CLAVE = 8

COOKIE_ACCESO = "ietaba_at"
COOKIE_RENOVACION = "ietaba_rt"
# La cookie de renovación solo se envía a /api/auth/*: viaja lo menos posible.
RUTA_COOKIE_RENOVACION = "/api/auth"

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_LARGO = 32

ARCHIVO_SECRETO = Path(__file__).resolve().parent.parent / "certs" / "secreto_sesiones.key"

_secreto_cache: bytes | None = None


def secreto() -> bytes:
    """Clave con la que se firman los tokens de acceso. Sale de la variable
    IETABA_SECRETO_SESIONES o de backend/certs/secreto_sesiones.key (se crea
    sola la primera vez). Si se borra o se cambia, los tokens de acceso
    dejan de valer, pero las sesiones siguen vivas: los clientes renuevan y
    listo. NO debe compartirse ni versionarse."""
    global _secreto_cache
    if _secreto_cache is not None:
        return _secreto_cache
    del_entorno = os.environ.get("IETABA_SECRETO_SESIONES")
    if del_entorno:
        _secreto_cache = del_entorno.encode()
        return _secreto_cache
    if not ARCHIVO_SECRETO.exists():
        ARCHIVO_SECRETO.parent.mkdir(parents=True, exist_ok=True)
        ARCHIVO_SECRETO.write_bytes(secrets.token_bytes(32))
    _secreto_cache = ARCHIVO_SECRETO.read_bytes()
    return _secreto_cache


# --- Identidad de servicio SAPRED (Fase 4.1) ---------------------------------
# Un secreto estático y compartido, SIN relación con usuarios/roles/permisos:
# identifica "es la maquinaria interna de SAPRED" (los scripts Node/Playwright
# que jamás tienen ni pueden tener una cookie de sesión de navegador), no a
# una persona. Mismo patrón que secreto() de arriba, misma carpeta certs/.
#
# Protege contra llamadas desde la red (el servidor corre en 0.0.0.0, lo
# alcanza toda la red del colegio) y contra quien no lo conozca. NO protege
# contra alguien que ya tiene acceso al sistema de archivos de esta máquina:
# quien puede leer este archivo también podría leer colegio.db directamente
# — esa es la frontera de confianza real, no algo que un header HTTP pueda
# mover.

CABECERA_TOKEN_SERVICIO = "X-Ietaba-Sapred-Token"
ARCHIVO_TOKEN_SERVICIO = Path(__file__).resolve().parent.parent / "certs" / "token_servicio_sapred.key"

_token_servicio_cache: str | None = None


def token_servicio() -> str:
    """Sale de IETABA_SAPRED_TOKEN o de backend/certs/token_servicio_sapred.key
    (se crea solo la primera vez). Para rotarlo: borrar el archivo (o
    cambiar la variable de entorno) y REINICIAR el backend — se cachea en
    memoria por proceso, igual que secreto(). Los scripts Node no necesitan
    reiniciarse: son procesos nuevos en cada corrida, así que leen el valor
    vigente solos."""
    global _token_servicio_cache
    if _token_servicio_cache is not None:
        return _token_servicio_cache
    del_entorno = os.environ.get("IETABA_SAPRED_TOKEN")
    if del_entorno:
        _token_servicio_cache = del_entorno
        return _token_servicio_cache
    if not ARCHIVO_TOKEN_SERVICIO.exists():
        ARCHIVO_TOKEN_SERVICIO.parent.mkdir(parents=True, exist_ok=True)
        ARCHIVO_TOKEN_SERVICIO.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    _token_servicio_cache = ARCHIVO_TOKEN_SERVICIO.read_text(encoding="utf-8").strip()
    return _token_servicio_cache


def verificar_token_servicio(recibido: str) -> bool:
    """Compara en tiempo constante. Nunca registra ni el valor recibido ni
    el esperado — solo el resultado (ver auth_servicio.py)."""
    if not recibido:
        return False
    return hmac.compare_digest(recibido, token_servicio())


# --- Contraseñas -------------------------------------------------------------


def hashear_clave(clave: str) -> str:
    sal = secrets.token_bytes(16)
    derivada = hashlib.scrypt(
        clave.encode(), salt=sal, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_LARGO
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _b64(sal), _b64(derivada)
    )


def verificar_clave(clave: str, guardado: str | None) -> bool:
    """Compara en tiempo constante. Si el hash guardado está vacío o con un
    formato desconocido, devuelve False (nunca deja entrar por error)."""
    if not guardado:
        return False
    try:
        etiqueta, n, r, p, sal, esperado = guardado.split("$")
        if etiqueta != "scrypt":
            return False
        derivada = hashlib.scrypt(
            clave.encode(), salt=_de_b64(sal), n=int(n), r=int(r), p=int(p),
            dklen=len(_de_b64(esperado)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derivada, _de_b64(esperado))


def problema_con_la_clave(clave: str, documento: str = "") -> str | None:
    """Mensaje de error si la contraseña no sirve, o None si está bien."""
    if len(clave or "") < LARGO_MINIMO_CLAVE:
        return f"La contraseña debe tener al menos {LARGO_MINIMO_CLAVE} caracteres."
    if clave.strip() != clave:
        return "La contraseña no debe empezar ni terminar con espacios."
    if documento and clave == documento:
        return "La contraseña no puede ser igual al número de documento."
    return None


def clave_temporal() -> str:
    """Contraseña temporal legible para entregar a un docente; se le exige
    cambiarla en el primer ingreso."""
    return secrets.token_urlsafe(9)


# --- Token de renovación -----------------------------------------------------


def generar_token_renovacion() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- Token de acceso (firmado, no se guarda en la base) ----------------------


def firmar_acceso(usuario_id: int, sesion_id: str, expira_en: dt.datetime) -> str:
    cuerpo = f"v1.{usuario_id}.{sesion_id}.{int(expira_en.replace(tzinfo=dt.timezone.utc).timestamp())}"
    firma = hmac.new(secreto(), cuerpo.encode(), hashlib.sha256).digest()
    return f"{_b64(cuerpo.encode())}.{_b64(firma)}"


def verificar_acceso(token: str) -> dict | None:
    """Devuelve {'usuario_id', 'sesion_id', 'expira_en'} si la firma es válida
    y no expiró. None en cualquier otro caso (token ausente, manipulado o
    vencido)."""
    if not token or "." not in token:
        return None
    try:
        cuerpo_b64, firma_b64 = token.split(".", 1)
        cuerpo = _de_b64(cuerpo_b64)
        firma = _de_b64(firma_b64)
    except (ValueError, TypeError):
        return None
    esperada = hmac.new(secreto(), cuerpo, hashlib.sha256).digest()
    if not hmac.compare_digest(firma, esperada):
        return None
    try:
        version, usuario_id, sesion_id, expira = cuerpo.decode().split(".")
    except ValueError:
        return None
    if version != "v1":
        return None
    if int(expira) <= int(fechas.ahora_utc().replace(tzinfo=dt.timezone.utc).timestamp()):
        return None
    return {
        "usuario_id": int(usuario_id),
        "sesion_id": sesion_id,
        "expira_en": dt.datetime.fromtimestamp(int(expira), dt.timezone.utc).replace(tzinfo=None),
    }


# --- Cookies -----------------------------------------------------------------


def conexion_segura(cabeceras: dict, esquema: str) -> bool:
    """True si la petición llegó por HTTPS (directo o detrás de un proxy)."""
    return esquema == "https" or cabeceras.get("x-forwarded-proto", "").split(",")[0].strip() == "https"


# --- Utilidades --------------------------------------------------------------


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode().rstrip("=")


def _de_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))
