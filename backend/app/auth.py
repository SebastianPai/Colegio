"""Autenticación: usuarios, ingreso, sesiones por dispositivo, renovación con
rotación y revocación.

Esta capa NO decide qué puede hacer cada usuario (eso son los roles y
permisos, que llegan en la fase siguiente): solo responde "quién es" y
"su sesión sigue viva". Por eso, de momento, nada de la aplicación existente
exige sesión: la app sigue funcionando igual que antes.

Cómo se sostiene la sesión (persistente pero revocable):

    ingreso  ->  token de ACCESO (15 min, firmado)   + token de RENOVACIÓN
                 cookie ietaba_at (HttpOnly)           cookie ietaba_rt
                                                       (HttpOnly, solo /api/auth)

    cada petición  ->  se verifica la firma del token de acceso Y que la
                       sesión no esté revocada ni vencida (revocar surte
                       efecto de inmediato)

    token vencido  ->  POST /api/auth/refresh: el token de renovación se
                       cambia por uno nuevo (rotación). El anterior queda
                       como "anterior" para detectar robos.

    reutilización  ->  si alguien presenta un token ya rotado (fuera de la
                       ventana de gracia de 30 s), se asume robo y la sesión
                       completa se revoca.
"""

import datetime as dt
import time
import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import fechas, models, seguridad
from .database import get_db


class ErrorAutenticacion(Exception):
    """Error para mostrarle al usuario (mensaje en español, sin detalles
    técnicos ni pistas sobre si el usuario existe)."""

    def __init__(self, mensaje: str, codigo: int = 401):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


MENSAJE_CREDENCIALES = "Usuario o contraseña incorrectos."

# Token de renovación recién emitido, en memoria y por poco tiempo: si dos
# pestañas (o la página y el service worker, más adelante) renuevan a la vez,
# la segunda recibe el MISMO token nuevo en vez de que se la tome por un robo.
# Solo en RAM y solo 30 segundos; nunca llega a la base.
_rotaciones_recientes: dict[str, tuple[str, float]] = {}

# Intentos fallidos por IP, para frenar fuerza bruta desde la red.
_intentos_por_ip: dict[str, list[float]] = {}
MAX_FALLOS_POR_IP = 20
VENTANA_FALLOS_IP = 300  # segundos


# --- Usuarios ----------------------------------------------------------------


def buscar_usuario(db: Session, identificador: str) -> models.Usuario | None:
    """Por documento o por correo (lo que escriba la persona)."""
    texto = (identificador or "").strip()
    if not texto:
        return None
    return db.scalar(
        select(models.Usuario).where(
            (models.Usuario.documento == texto) | (models.Usuario.email == texto.lower())
        )
    )


def registrar_usuario(
    db: Session,
    *,
    documento: str,
    nombre: str,
    clave: str,
    email: str | None = None,
    docente_id: int | None = None,
    debe_cambiar_clave: bool = True,
) -> models.Usuario:
    """Crea el usuario. No asigna roles (todavía no existen): solo identidad.
    `docente_id` enlaza con el Docente que YA existe, no crea otro registro
    de profesor ni duplica sus datos."""
    documento = (documento or "").strip()
    if not documento:
        raise ErrorAutenticacion("El documento es obligatorio.", 400)
    if not (nombre or "").strip():
        raise ErrorAutenticacion("El nombre es obligatorio.", 400)
    problema = seguridad.problema_con_la_clave(clave, documento)
    if problema:
        raise ErrorAutenticacion(problema, 400)
    if buscar_usuario(db, documento):
        raise ErrorAutenticacion("Ya existe un usuario con ese documento.", 409)
    email = (email or "").strip().lower() or None
    if email and db.scalar(select(models.Usuario).where(models.Usuario.email == email)):
        raise ErrorAutenticacion("Ya existe un usuario con ese correo.", 409)
    if docente_id is not None:
        if db.get(models.Docente, docente_id) is None:
            raise ErrorAutenticacion("Ese docente no existe.", 404)
        if db.scalar(select(models.Usuario).where(models.Usuario.docente_id == docente_id)):
            raise ErrorAutenticacion("Ese docente ya tiene un usuario.", 409)

    usuario = models.Usuario(
        documento=documento,
        nombre=nombre.strip(),
        email=email,
        clave_hash=seguridad.hashear_clave(clave),
        docente_id=docente_id,
        debe_cambiar_clave=debe_cambiar_clave,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def cambiar_clave(
    db: Session, usuario: models.Usuario, clave_actual: str, clave_nueva: str, sesion_actual_id: str | None = None
) -> None:
    """Cambia la contraseña y cierra las OTRAS sesiones del usuario (si la
    contraseña se cambió porque alguien más la conocía, esas sesiones no
    deben sobrevivir)."""
    if not seguridad.verificar_clave(clave_actual, usuario.clave_hash):
        raise ErrorAutenticacion("La contraseña actual no es correcta.")
    problema = seguridad.problema_con_la_clave(clave_nueva, usuario.documento)
    if problema:
        raise ErrorAutenticacion(problema, 400)
    usuario.clave_hash = seguridad.hashear_clave(clave_nueva)
    usuario.debe_cambiar_clave = False
    usuario.actualizado_en = fechas.ahora_utc()
    revocar_sesiones_del_usuario(db, usuario.id, motivo="cambio_de_clave", excepto=sesion_actual_id)
    db.commit()


def establecer_clave(db: Session, usuario: models.Usuario, clave_nueva: str, *, exigir_cambio: bool = True) -> None:
    """Restablecimiento administrativo (desde crear_usuario.py). Cierra TODAS
    las sesiones del usuario."""
    problema = seguridad.problema_con_la_clave(clave_nueva, usuario.documento)
    if problema:
        raise ErrorAutenticacion(problema, 400)
    usuario.clave_hash = seguridad.hashear_clave(clave_nueva)
    usuario.debe_cambiar_clave = exigir_cambio
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.actualizado_en = fechas.ahora_utc()
    revocar_sesiones_del_usuario(db, usuario.id, motivo="clave_restablecida")
    db.commit()


def cambiar_estado(db: Session, usuario: models.Usuario, estado: str) -> None:
    """activo | inactivo | bloqueado. Al desactivar se revocan sus sesiones."""
    if estado not in ("activo", "inactivo", "bloqueado"):
        raise ErrorAutenticacion("Estado no válido.", 400)
    usuario.estado = estado
    usuario.actualizado_en = fechas.ahora_utc()
    usuario.desactivado_en = None if estado == "activo" else fechas.ahora_utc()
    if estado != "activo":
        revocar_sesiones_del_usuario(db, usuario.id, motivo=f"usuario_{estado}")
    db.commit()


# --- Ingreso -----------------------------------------------------------------


def _registrar_fallo_ip(ip: str) -> None:
    ahora = time.time()
    fallos = [t for t in _intentos_por_ip.get(ip, []) if ahora - t < VENTANA_FALLOS_IP]
    fallos.append(ahora)
    _intentos_por_ip[ip] = fallos


def _ip_bloqueada(ip: str) -> bool:
    ahora = time.time()
    fallos = [t for t in _intentos_por_ip.get(ip, []) if ahora - t < VENTANA_FALLOS_IP]
    _intentos_por_ip[ip] = fallos
    return len(fallos) >= MAX_FALLOS_POR_IP


def autenticar(db: Session, identificador: str, clave: str, ip: str = "") -> models.Usuario:
    """Devuelve el usuario si las credenciales son correctas. Los mensajes no
    revelan si el usuario existe; el de cuenta desactivada solo aparece
    cuando la contraseña ERA correcta, así no sirve para averiguar usuarios."""
    if ip and _ip_bloqueada(ip):
        raise ErrorAutenticacion("Demasiados intentos fallidos desde este equipo. Espera unos minutos.", 429)

    usuario = buscar_usuario(db, identificador)
    ahora = fechas.ahora_utc()

    if usuario is None:
        if ip:
            _registrar_fallo_ip(ip)
        # Se gasta el mismo tiempo que con un usuario real para no delatar
        # por la demora que el documento no existe.
        seguridad.verificar_clave(clave or "", seguridad.hashear_clave("comparacion-ficticia"))
        raise ErrorAutenticacion(MENSAJE_CREDENCIALES)

    if usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora:
        minutos = max(1, int((usuario.bloqueado_hasta - ahora).total_seconds() // 60) + 1)
        raise ErrorAutenticacion(f"Cuenta bloqueada por intentos fallidos. Intenta en {minutos} minutos.", 429)

    if not seguridad.verificar_clave(clave or "", usuario.clave_hash):
        if ip:
            _registrar_fallo_ip(ip)
        usuario.intentos_fallidos = (usuario.intentos_fallidos or 0) + 1
        if usuario.intentos_fallidos >= seguridad.MAX_INTENTOS_FALLIDOS:
            usuario.bloqueado_hasta = ahora + dt.timedelta(minutes=seguridad.MINUTOS_BLOQUEO)
            usuario.intentos_fallidos = 0
        db.commit()
        raise ErrorAutenticacion(MENSAJE_CREDENCIALES)

    if usuario.estado != "activo":
        raise ErrorAutenticacion(
            "Esta cuenta está desactivada. Comunícate con la administración del colegio.", 403
        )

    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.ultimo_acceso = ahora
    db.commit()
    return usuario


def _nombre_de_dispositivo(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if "android" in ua:
        sistema = "Android"
    elif "iphone" in ua or "ipad" in ua or "ios" in ua:
        sistema = "iPhone/iPad"
    elif "windows" in ua:
        sistema = "Windows"
    elif "mac os" in ua or "macintosh" in ua:
        sistema = "Mac"
    elif "linux" in ua:
        sistema = "Linux"
    else:
        sistema = "Dispositivo"
    if "edg/" in ua:
        navegador = "Edge"
    elif "chrome" in ua and "chromium" not in ua:
        navegador = "Chrome"
    elif "firefox" in ua:
        navegador = "Firefox"
    elif "safari" in ua:
        navegador = "Safari"
    else:
        navegador = "Navegador"
    return f"{navegador} · {sistema}"


def iniciar_sesion(
    db: Session,
    usuario: models.Usuario,
    *,
    dispositivo_id: str | None = None,
    nombre_dispositivo: str | None = None,
    confiar: bool = False,
    ip: str = "",
    user_agent: str = "",
) -> tuple[models.Sesion, str, str, dt.datetime]:
    """Crea (o reutiliza) el dispositivo y abre una sesión.
    Devuelve (sesion, token_renovacion, token_acceso, expira_acceso)."""
    ahora = fechas.ahora_utc()

    dispositivo = None
    if dispositivo_id:
        dispositivo = db.get(models.Dispositivo, dispositivo_id)
        if dispositivo is not None and dispositivo.usuario_id != usuario.id:
            dispositivo = None  # ese id es de otra persona: se genera uno nuevo
    if dispositivo is None:
        dispositivo = models.Dispositivo(
            id=dispositivo_id if dispositivo_id and len(dispositivo_id) <= 64 else str(uuid.uuid4()),
            usuario_id=usuario.id,
            nombre=(nombre_dispositivo or "").strip() or _nombre_de_dispositivo(user_agent),
            confiable=confiar,
            ultima_ip=ip or None,
            ultimo_acceso=ahora,
        )
        db.add(dispositivo)
    else:
        dispositivo.ultimo_acceso = ahora
        dispositivo.ultima_ip = ip or dispositivo.ultima_ip
        dispositivo.confiable = bool(confiar)
        dispositivo.revocado_en = None
        if nombre_dispositivo:
            dispositivo.nombre = nombre_dispositivo.strip()

    if confiar:
        expira = ahora + dt.timedelta(days=seguridad.DIAS_SESION_CONFIABLE)
        expira_absoluta = ahora + dt.timedelta(days=seguridad.DIAS_SESION_CONFIABLE_MAXIMO)
    else:
        expira = expira_absoluta = ahora + dt.timedelta(hours=seguridad.HORAS_SESION_NO_CONFIABLE)

    token_renovacion = seguridad.generar_token_renovacion()
    sesion = models.Sesion(
        id=str(uuid.uuid4()),
        usuario_id=usuario.id,
        dispositivo_id=dispositivo.id,
        refresh_hash=seguridad.hash_token(token_renovacion),
        creada_en=ahora,
        ultimo_uso=ahora,
        expira_en=expira,
        expira_absoluta_en=expira_absoluta,
        confiable=bool(confiar),
        ip=ip or None,
        user_agent=(user_agent or "")[:300] or None,
    )
    db.add(sesion)
    db.commit()
    db.refresh(sesion)

    token_acceso, expira_acceso = _emitir_acceso(usuario.id, sesion.id)
    return sesion, token_renovacion, token_acceso, expira_acceso


def _emitir_acceso(usuario_id: int, sesion_id: str) -> tuple[str, dt.datetime]:
    expira = fechas.ahora_utc() + dt.timedelta(minutes=seguridad.MINUTOS_TOKEN_ACCESO)
    return seguridad.firmar_acceso(usuario_id, sesion_id, expira), expira


def renovar_sesion(db: Session, token_renovacion: str, *, ip: str = "") -> tuple[models.Sesion, str, str, dt.datetime]:
    """Cambia el token de renovación por uno nuevo (rotación) y entrega un
    token de acceso fresco. Detecta la reutilización de un token ya rotado:
    eso significa que alguien se lo copió, así que revoca la sesión."""
    if not token_renovacion:
        raise ErrorAutenticacion("No hay sesión para renovar.")
    ahora = fechas.ahora_utc()
    huella = seguridad.hash_token(token_renovacion)

    sesion = db.scalar(select(models.Sesion).where(models.Sesion.refresh_hash == huella))
    if sesion is None:
        # ¿Es un token ya rotado? (robo, o una carrera entre dos pestañas)
        sesion_previa = db.scalar(select(models.Sesion).where(models.Sesion.refresh_hash_anterior == huella))
        if sesion_previa is not None:
            en_gracia = (
                sesion_previa.rotada_en is not None
                and (ahora - sesion_previa.rotada_en).total_seconds() <= seguridad.SEGUNDOS_GRACIA_ROTACION
            )
            guardado = _rotaciones_recientes.get(sesion_previa.id)
            if en_gracia and guardado and guardado[1] > time.time() and sesion_previa.revocada_en is None:
                # Carrera legítima: se devuelve el MISMO token nuevo que ya se
                # entregó hace un momento, no se rota otra vez.
                token_acceso, expira_acceso = _emitir_acceso(sesion_previa.usuario_id, sesion_previa.id)
                return sesion_previa, guardado[0], token_acceso, expira_acceso
            revocar_sesion(db, sesion_previa, motivo="token_reutilizado")
            raise ErrorAutenticacion(
                "Tu sesión se cerró por seguridad (se detectó un uso indebido). Vuelve a iniciar sesión."
            )
        raise ErrorAutenticacion("Sesión no válida. Vuelve a iniciar sesión.")

    if sesion.revocada_en is not None:
        raise ErrorAutenticacion("La sesión fue cerrada. Vuelve a iniciar sesión.")
    if sesion.expira_en <= ahora or sesion.expira_absoluta_en <= ahora:
        revocar_sesion(db, sesion, motivo="expirada")
        raise ErrorAutenticacion("La sesión venció. Vuelve a iniciar sesión.")

    usuario = db.get(models.Usuario, sesion.usuario_id)
    if usuario is None or usuario.estado != "activo":
        revocar_sesion(db, sesion, motivo="usuario_no_activo")
        raise ErrorAutenticacion("Esta cuenta está desactivada. Comunícate con la administración del colegio.", 403)

    nuevo = seguridad.generar_token_renovacion()
    sesion.refresh_hash_anterior = sesion.refresh_hash
    sesion.refresh_hash = seguridad.hash_token(nuevo)
    sesion.rotada_en = ahora
    sesion.rotaciones = (sesion.rotaciones or 0) + 1
    sesion.ultimo_uso = ahora
    sesion.ip = ip or sesion.ip
    if sesion.confiable:
        sesion.expira_en = min(
            ahora + dt.timedelta(days=seguridad.DIAS_SESION_CONFIABLE), sesion.expira_absoluta_en
        )
    dispositivo = db.get(models.Dispositivo, sesion.dispositivo_id)
    if dispositivo is not None:
        dispositivo.ultimo_acceso = ahora
        dispositivo.ultima_ip = ip or dispositivo.ultima_ip
    db.commit()

    _rotaciones_recientes[sesion.id] = (nuevo, time.time() + seguridad.SEGUNDOS_GRACIA_ROTACION)
    _limpiar_rotaciones()

    token_acceso, expira_acceso = _emitir_acceso(sesion.usuario_id, sesion.id)
    return sesion, nuevo, token_acceso, expira_acceso


def _limpiar_rotaciones() -> None:
    ahora = time.time()
    for sesion_id in [k for k, (_, hasta) in _rotaciones_recientes.items() if hasta < ahora]:
        _rotaciones_recientes.pop(sesion_id, None)


# --- Revocación --------------------------------------------------------------


def revocar_sesion(db: Session, sesion: models.Sesion, motivo: str = "logout") -> None:
    if sesion.revocada_en is None:
        sesion.revocada_en = fechas.ahora_utc()
        sesion.motivo_revocacion = motivo
    _rotaciones_recientes.pop(sesion.id, None)
    db.commit()


def revocar_sesiones_del_usuario(
    db: Session, usuario_id: int, motivo: str = "logout_todos", excepto: str | None = None
) -> int:
    condiciones = [models.Sesion.usuario_id == usuario_id, models.Sesion.revocada_en.is_(None)]
    if excepto:
        condiciones.append(models.Sesion.id != excepto)
    afectadas = db.scalars(select(models.Sesion.id).where(*condiciones)).all()
    if afectadas:
        db.execute(
            update(models.Sesion)
            .where(models.Sesion.id.in_(afectadas))
            .values(revocada_en=fechas.ahora_utc(), motivo_revocacion=motivo)
            .execution_options(synchronize_session=False)
        )
        db.commit()
    for sesion_id in afectadas:
        _rotaciones_recientes.pop(sesion_id, None)
    return len(afectadas)


def sesion_viva(db: Session, sesion_id: str) -> models.Sesion | None:
    sesion = db.get(models.Sesion, sesion_id)
    if sesion is None or sesion.revocada_en is not None:
        return None
    if sesion.expira_en <= fechas.ahora_utc() or sesion.expira_absoluta_en <= fechas.ahora_utc():
        return None
    return sesion


def listar_sesiones(db: Session, usuario_id: int, incluir_cerradas: bool = False) -> list[models.Sesion]:
    condiciones = [models.Sesion.usuario_id == usuario_id]
    if not incluir_cerradas:
        condiciones.append(models.Sesion.revocada_en.is_(None))
    return list(
        db.scalars(select(models.Sesion).where(*condiciones).order_by(models.Sesion.ultimo_uso.desc())).all()
    )


# --- Quién es el usuario de esta petición ------------------------------------


class Identidad:
    """Usuario, sesión y vencimiento del token de acceso de esta petición."""

    def __init__(self, usuario: models.Usuario, sesion: models.Sesion, expira_acceso: dt.datetime):
        self.usuario = usuario
        self.sesion = sesion
        self.expira_acceso = expira_acceso


def identidad_opcional(request: Request, db: Session = Depends(get_db)) -> Identidad | None:
    """Identifica al usuario si trae una sesión válida; None si no. Es la que
    se usará más adelante para ir protegiendo pantallas sin romper nada."""
    datos = seguridad.verificar_acceso(request.cookies.get(seguridad.COOKIE_ACCESO) or "")
    if datos is None:
        return None
    sesion = sesion_viva(db, datos["sesion_id"])
    if sesion is None or sesion.usuario_id != datos["usuario_id"]:
        return None
    usuario = db.get(models.Usuario, datos["usuario_id"])
    if usuario is None or usuario.estado != "activo":
        return None
    return Identidad(usuario, sesion, datos["expira_en"])


def identidad_actual(identidad: Identidad | None = Depends(identidad_opcional)) -> Identidad:
    """Exige sesión válida. 401 si no hay."""
    if identidad is None:
        raise HTTPException(status_code=401, detail="Necesitas iniciar sesión.")
    return identidad


def usuario_actual(identidad: Identidad = Depends(identidad_actual)) -> models.Usuario:
    return identidad.usuario
