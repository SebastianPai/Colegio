"""RBAC: qué puede hacer cada usuario, calculado en el servidor.

Nada de esto lo decide el cliente. `permisos_efectivos()` es la unión de los
permisos de todos los roles ACTIVOS del usuario, se calcula con una consulta
por petición (sin caché) y solo cuenta permisos con `activo=True`: así una
edición del administrador surte efecto en la SIGUIENTE petición, sin
reiniciar el servidor.

`requiere(codigo)` es la dependencia que se cuelga de cada endpoint nuevo:
401 si no hay sesión, 403 si la sesión existe pero falta el permiso. Si el
código no está en el catálogo, falla al ARRANCAR (RuntimeError), no en
producción frente a un usuario — es el mismo principio que ya usa
`migraciones.ejecutar()` para las columnas y los índices.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth, models, seguridad
from . import permisos as catalogo
from .database import get_db

# Con estos dos permisos a la vez, un usuario puede: crear/editar roles
# (roles.gestionar) y decidir quién los tiene (usuarios.roles). Se exige que
# SIEMPRE quede al menos un usuario activo con ambos, para no dejar el
# sistema sin nadie que pueda administrarlo.
PERMISOS_CONTROL_TOTAL = {"roles.gestionar", "usuarios.roles"}


def permisos_efectivos(db: Session, usuario: models.Usuario) -> set[str]:
    """Unión de los permisos de todos los roles activos del usuario. Solo
    permisos con activo=True y roles con activo=True cuentan."""
    filas = db.execute(
        select(models.Permiso.codigo)
        .join(models.RolPermiso, models.RolPermiso.permiso_id == models.Permiso.id)
        .join(models.Rol, models.Rol.id == models.RolPermiso.rol_id)
        .join(models.UsuarioRol, models.UsuarioRol.rol_id == models.Rol.id)
        .where(
            models.UsuarioRol.usuario_id == usuario.id,
            models.Rol.activo.is_(True),
            models.Permiso.activo.is_(True),
        )
        .distinct()
    ).all()
    return {codigo for (codigo,) in filas}


def tiene_permiso(db: Session, usuario: models.Usuario, codigo: str) -> bool:
    return codigo in permisos_efectivos(db, usuario)


def roles_del_usuario(db: Session, usuario_id: int) -> list[models.Rol]:
    return list(
        db.scalars(
            select(models.Rol)
            .join(models.UsuarioRol, models.UsuarioRol.rol_id == models.Rol.id)
            .where(models.UsuarioRol.usuario_id == usuario_id)
            .order_by(models.Rol.nombre)
        ).all()
    )


def sedes_permitidas(db: Session, usuario: models.Usuario) -> set[int] | None:
    """None = sin restricción (todas las sedes). Un conjunto = solo esas.

    Preparación para limitar coordinadores por sede (aprobado, sin activar
    todavía): hoy NINGÚN endpoint llama a esta función para negar nada — la
    prueba de esta fase solo comprueba que devuelve lo que hay en
    usuario_sedes."""
    filas = db.scalars(
        select(models.UsuarioSede.sede_id).where(models.UsuarioSede.usuario_id == usuario.id)
    ).all()
    return set(filas) if filas else None


def requiere(codigo_permiso: str):
    """Dependencia de FastAPI para un endpoint: exige sesión (401) y el
    permiso indicado (403)."""
    if codigo_permiso not in catalogo.CODIGOS:
        # Error de programación, no del usuario: se detecta al importar el
        # router (FastAPI evalúa requiere(...) al definir la ruta), así que
        # nunca llega a producción.
        raise RuntimeError(f"Permiso desconocido citado por un endpoint: {codigo_permiso!r}")

    def _dependencia(
        identidad: auth.Identidad = Depends(auth.identidad_actual),
        db: Session = Depends(get_db),
    ) -> auth.Identidad:
        if not tiene_permiso(db, identidad.usuario, codigo_permiso):
            raise HTTPException(status_code=403, detail="No tienes permiso para realizar esta acción.")
        return identidad

    return _dependencia


# --- Modo observación (Fase 4A) ----------------------------------------------
# observar(codigo) es la contraparte de requiere(codigo) que NUNCA bloquea:
# calcula lo mismo (¿habría pasado o no?) pero solo lo registra en
# observaciones_permisos y deja pasar la petición igual, sin importar el
# resultado. Sirve para revisar el patrón real de uso antes de activar el
# bloqueo de verdad (Fase 4B) — no es protección, es solo instrumentación.


def _por_que_no_hay_identidad(request: Request) -> str:
    """Fase 4A': por qué esta petición llegó sin identidad. Antes todo esto
    se guardaba como "sin_sesion", y eso mezclaba dos cosas muy distintas al
    revisar los datos: a quien nunca inició sesión con quien la tiene abierta
    pero se le venció el token de acceso (15 min).

    La cookie de acceso es de SESIÓN DEL NAVEGADOR (no lleva max_age, ver
    routers/auth.py): sigue ahí aunque el token de adentro ya haya vencido,
    y el navegador la sigue enviando. Eso es justo lo que permite separar
    los tres casos sin consultar la base:

      · sin_sesion      → no hay cookie: nadie inició sesión en este
                          navegador (o es un script/curl).
      · sesion_vencida  → hay cookie pero su token no vale: casi siempre
                          pasaron los 15 minutos. Es RECUPERABLE solo con
                          refrescar, sin volver a pedir la contraseña.
      · sesion_revocada → el token está bien firmado y vigente, pero la
                          sesión ya no vive o el usuario no está activo
                          (logout desde otro equipo, revocación, usuario
                          desactivado). NO es recuperable con un refresh:
                          en Fase 4B esta persona debe volver a entrar.
    """
    cookie = request.cookies.get(seguridad.COOKIE_ACCESO) or ""
    if not cookie:
        return "sin_sesion"
    if seguridad.verificar_acceso(cookie) is None:
        return "sesion_vencida"
    return "sesion_revocada"


def _registrar_observacion(
    db: Session, request: Request, codigo_permiso: str, usuario_id: int | None, resultado: str
) -> None:
    try:
        db.add(
            models.ObservacionPermiso(
                endpoint=request.url.path,
                metodo=request.method,
                permiso=codigo_permiso,
                usuario_id=usuario_id,
                resultado=resultado,
                ip=request.client.host if request.client else None,
            )
        )
        db.commit()
    except Exception:
        # Registrar la observación NUNCA debe tumbar la petición real: si
        # falla (base ocupada, lo que sea), se descarta esta fila y sigue.
        db.rollback()


def observar(codigo_permiso: str, *, tambien_servicio: bool = False):
    """Dependencia de solo-observación: jamás lanza 401/403. `tambien_servicio`
    es para las pocas rutas (hoy solo /api/sedes) que los scripts de SAPRED
    todavía llaman con el token de servicio (Fase 4.1) — sin esto, cada
    llamada real de un script aparecería como "habría sido rechazada" y
    ensuciaría los datos."""
    if codigo_permiso not in catalogo.CODIGOS:
        raise RuntimeError(f"Permiso desconocido citado por un endpoint: {codigo_permiso!r}")

    def _dependencia(
        request: Request,
        identidad: auth.Identidad | None = Depends(auth.identidad_opcional),
        db: Session = Depends(get_db),
    ) -> auth.Identidad | None:
        if tambien_servicio and identidad is None:
            recibido = request.headers.get(seguridad.CABECERA_TOKEN_SERVICIO, "")
            if seguridad.verificar_token_servicio(recibido):
                return None  # llamada legítima de un script SAPRED: no se observa como rechazo

        if identidad is None:
            resultado = _por_que_no_hay_identidad(request)
            usuario_id = None
        elif tiene_permiso(db, identidad.usuario, codigo_permiso):
            resultado = "habria_pasado"
            usuario_id = identidad.usuario.id
        else:
            resultado = "habria_sido_rechazado"
            usuario_id = identidad.usuario.id

        _registrar_observacion(db, request, codigo_permiso, usuario_id, resultado)
        return identidad

    return _dependencia


# --- Reglas anti-bloqueo ------------------------------------------------------


def usuarios_con_control_total(db: Session, *, excluir_usuario_id: int | None = None) -> list[int]:
    """ids de usuarios ACTIVOS que hoy tienen los dos permisos de
    PERMISOS_CONTROL_TOTAL. `excluir_usuario_id` simula "si a este usuario le
    quitara todo" sin tocar la base: sirve para validar un cambio ANTES de
    aplicarlo (o, aplicado con flush pendiente, para revisar el estado
    resultante)."""
    usuarios = db.scalars(select(models.Usuario).where(models.Usuario.estado == "activo")).all()
    resultado = []
    for u in usuarios:
        if excluir_usuario_id is not None and u.id == excluir_usuario_id:
            continue
        if PERMISOS_CONTROL_TOTAL <= permisos_efectivos(db, u):
            resultado.append(u.id)
    return resultado


class ErrorBloqueoAdministrativo(Exception):
    """Se lanza cuando un cambio dejaría el sistema sin ningún usuario activo
    capaz de gestionar roles y usuarios."""

    def __init__(self) -> None:
        super().__init__(
            "Esta acción dejaría el sistema sin ningún usuario activo con permiso "
            "para gestionar roles y usuarios (roles.gestionar + usuarios.roles). "
            "Asigna esos permisos a otro usuario activo antes de continuar."
        )


def aplicar_si_no_bloquea(db: Session, aplicar_cambio) -> None:
    """Aplica `aplicar_cambio()` (que solo hace db.add/db.delete, SIN commit),
    hace flush para que la consulta de permisos vea el cambio, y comprueba
    que siga quedando al menos un administrador. Si no queda ninguno,
    deshace todo y lanza ErrorBloqueoAdministrativo; si queda alguno, hace
    commit. Así el cambio se valida ANTES de quedar guardado, nunca después."""
    aplicar_cambio()
    db.flush()
    if not usuarios_con_control_total(db):
        db.rollback()
        raise ErrorBloqueoAdministrativo()
    db.commit()
