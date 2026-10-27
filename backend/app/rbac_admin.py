"""Lógica de administración de roles, permisos y usuarios (Fase 3).

Separado de `rbac.py` (que es de solo lectura y lo importa todo el mundo
mediante `requiere()`) porque esto solo lo usan los endpoints de
`routers/admin.py`: son las operaciones de escritura, con sus validaciones y
las reglas anti-bloqueo.

Todo cambio que pueda afectar quién administra el sistema (desactivar un
rol, quitarle permisos, cambiar los roles de un usuario, desactivar una
cuenta) pasa por `rbac.aplicar_si_no_bloquea`: se aplica, se comprueba que
siga quedando al menos un administrador, y solo entonces se guarda de
verdad. Si no queda ninguno, se deshace y se avisa con un mensaje claro.
"""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import auth, fechas, models, rbac, schemas, seguridad
from . import permisos as catalogo


class ErrorRBAC(Exception):
    """Error de validación o de negocio, con el mismo `.mensaje`/`.codigo`
    que auth.ErrorAutenticacion para que el router los capture igual."""

    def __init__(self, mensaje: str, codigo: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


# --- Permisos (solo lectura: el catálogo lo define app/permisos.py) ----------


def listar_permisos(db: Session) -> list[models.Permiso]:
    return list(db.scalars(select(models.Permiso).order_by(models.Permiso.modulo, models.Permiso.codigo)).all())


def _validar_codigos_permisos(db: Session, codigos: list[str]) -> list[models.Permiso]:
    unicos = list(dict.fromkeys(codigos))  # sin duplicados, conserva el orden
    filas = db.scalars(select(models.Permiso).where(models.Permiso.codigo.in_(unicos))).all()
    encontrados = {p.codigo for p in filas}
    faltan = [c for c in unicos if c not in encontrados]
    if faltan:
        raise ErrorRBAC(f"Permiso(s) inexistente(s): {', '.join(faltan)}", 400)
    return list(filas)


# --- Roles --------------------------------------------------------------------


def _rol_a_resumen(db: Session, rol: models.Rol) -> schemas.RolResumen:
    total_usuarios = db.scalar(
        select(func.count()).select_from(models.UsuarioRol).where(models.UsuarioRol.rol_id == rol.id)
    ) or 0
    total_permisos = db.scalar(
        select(func.count()).select_from(models.RolPermiso).where(models.RolPermiso.rol_id == rol.id)
    ) or 0
    return schemas.RolResumen(
        id=rol.id, codigo=rol.codigo, nombre=rol.nombre, descripcion=rol.descripcion,
        es_sistema=rol.es_sistema, activo=rol.activo,
        total_usuarios=total_usuarios, total_permisos=total_permisos,
    )


def listar_roles(db: Session) -> list[schemas.RolResumen]:
    roles = db.scalars(select(models.Rol).order_by(models.Rol.nombre)).all()
    return [_rol_a_resumen(db, r) for r in roles]


def obtener_rol_detalle(db: Session, rol_id: int) -> schemas.RolDetalle | None:
    rol = db.get(models.Rol, rol_id)
    if rol is None:
        return None
    codigos = list(
        db.scalars(
            select(models.Permiso.codigo)
            .join(models.RolPermiso, models.RolPermiso.permiso_id == models.Permiso.id)
            .where(models.RolPermiso.rol_id == rol.id)
            .order_by(models.Permiso.codigo)
        ).all()
    )
    resumen = _rol_a_resumen(db, rol)
    return schemas.RolDetalle(**resumen.model_dump(), permisos=codigos)


def crear_rol(db: Session, datos: schemas.RolCrear) -> models.Rol:
    """Un rol creado por el administrador nace SIN permisos (incluidos los
    sensibles): se asignan aparte con PUT .../permisos."""
    codigo = datos.codigo.strip().lower().replace(" ", "_")
    if not codigo:
        raise ErrorRBAC("El código del rol es obligatorio.", 400)
    if not datos.nombre.strip():
        raise ErrorRBAC("El nombre del rol es obligatorio.", 400)
    if db.scalar(select(models.Rol).where(models.Rol.codigo == codigo)):
        raise ErrorRBAC("Ya existe un rol con ese código.", 409)
    rol = models.Rol(
        codigo=codigo, nombre=datos.nombre.strip(), descripcion=datos.descripcion,
        es_sistema=False, activo=True,
    )
    db.add(rol)
    db.commit()
    db.refresh(rol)
    return rol


def actualizar_rol(db: Session, rol: models.Rol, datos: schemas.RolActualizar) -> models.Rol:
    if datos.activo is False and rol.es_sistema:
        raise ErrorRBAC("Los roles del sistema no se pueden desactivar.", 400)

    def aplicar() -> None:
        if datos.nombre is not None:
            if not datos.nombre.strip():
                raise ErrorRBAC("El nombre del rol no puede quedar vacío.", 400)
            rol.nombre = datos.nombre.strip()
        if datos.descripcion is not None:
            rol.descripcion = datos.descripcion
        if datos.activo is not None:
            rol.activo = datos.activo
        rol.actualizado_en = fechas.ahora_utc()

    if datos.activo is False:
        # Desactivar un rol puede dejar sin permisos a quien lo tenía: pasa
        # por la comprobación anti-bloqueo.
        rbac.aplicar_si_no_bloquea(db, aplicar)
    else:
        aplicar()
        db.commit()
    db.refresh(rol)
    return rol


def establecer_permisos_rol(db: Session, rol: models.Rol, codigos: list[str]) -> list[str]:
    permisos_validos = _validar_codigos_permisos(db, codigos)
    if rol.codigo == catalogo.ROL_TODOS_LOS_PERMISOS:
        todos = set(db.scalars(select(models.Permiso.codigo)))
        if {p.codigo for p in permisos_validos} != todos:
            raise ErrorRBAC("El rol Administrador siempre tiene todos los permisos: no se le pueden quitar.", 400)

    def aplicar() -> None:
        db.execute(delete(models.RolPermiso).where(models.RolPermiso.rol_id == rol.id))
        ahora = fechas.ahora_utc()
        for permiso in permisos_validos:
            db.add(models.RolPermiso(rol_id=rol.id, permiso_id=permiso.id, asignado_en=ahora))

    rbac.aplicar_si_no_bloquea(db, aplicar)
    return sorted(p.codigo for p in permisos_validos)


def eliminar_rol(db: Session, rol: models.Rol) -> None:
    if rol.es_sistema:
        raise ErrorRBAC("Los roles del sistema no se pueden eliminar.", 400)
    en_uso = db.scalar(
        select(func.count()).select_from(models.UsuarioRol).where(models.UsuarioRol.rol_id == rol.id)
    ) or 0
    if en_uso:
        raise ErrorRBAC(f"No se puede eliminar: {en_uso} usuario(s) todavía tienen este rol.", 409)
    db.execute(delete(models.RolPermiso).where(models.RolPermiso.rol_id == rol.id))
    db.delete(rol)
    db.commit()


def _validar_codigos_roles(db: Session, codigos: list[str]) -> list[models.Rol]:
    unicos = list(dict.fromkeys(codigos))
    filas = db.scalars(select(models.Rol).where(models.Rol.codigo.in_(unicos))).all()
    encontrados = {r.codigo for r in filas}
    faltan = [c for c in unicos if c not in encontrados]
    if faltan:
        raise ErrorRBAC(f"Rol(es) inexistente(s): {', '.join(faltan)}", 400)
    return list(filas)


# --- Usuarios --------------------------------------------------------------------


def _usuario_a_resumen(db: Session, usuario: models.Usuario) -> schemas.UsuarioAdminResumen:
    roles = [r.codigo for r in rbac.roles_del_usuario(db, usuario.id)]
    sesiones_activas = len(auth.listar_sesiones(db, usuario.id))
    return schemas.UsuarioAdminResumen(
        id=usuario.id, documento=usuario.documento, nombre=usuario.nombre, email=usuario.email,
        estado=usuario.estado, docente_id=usuario.docente_id, debe_cambiar_clave=usuario.debe_cambiar_clave,
        ultimo_acceso=usuario.ultimo_acceso, creado_en=usuario.creado_en,
        roles=roles, sesiones_activas=sesiones_activas,
    )


def listar_usuarios(db: Session) -> list[schemas.UsuarioAdminResumen]:
    usuarios = db.scalars(select(models.Usuario).order_by(models.Usuario.id)).all()
    return [_usuario_a_resumen(db, u) for u in usuarios]


def obtener_usuario_detalle(db: Session, usuario_id: int) -> schemas.UsuarioAdminDetalle | None:
    usuario = db.get(models.Usuario, usuario_id)
    if usuario is None:
        return None
    resumen = _usuario_a_resumen(db, usuario)
    sedes = sorted(
        db.scalars(select(models.UsuarioSede.sede_id).where(models.UsuarioSede.usuario_id == usuario.id)).all()
    )
    return schemas.UsuarioAdminDetalle(**resumen.model_dump(), sedes=sedes)


def crear_usuario_admin(
    db: Session, datos: schemas.UsuarioCrear, creado_por_id: int | None
) -> tuple[models.Usuario, str]:
    """Crea el usuario con una contraseña temporal (no hay forma de teclearla
    por HTTP como en crear_usuario.py) y le asigna los roles indicados.
    Devuelve (usuario, clave_temporal) para mostrarla UNA sola vez."""
    roles = _validar_codigos_roles(db, datos.roles) if datos.roles else []
    clave = seguridad.clave_temporal()
    # auth.registrar_usuario ya valida documento/correo/docente duplicados y
    # hace su propio commit; lanza auth.ErrorAutenticacion si algo falla.
    usuario = auth.registrar_usuario(
        db, documento=datos.documento, nombre=datos.nombre, clave=clave,
        email=datos.email, docente_id=datos.docente_id, debe_cambiar_clave=True,
    )
    if roles:
        ahora = fechas.ahora_utc()
        for rol in roles:
            db.add(models.UsuarioRol(usuario_id=usuario.id, rol_id=rol.id, asignado_por=creado_por_id, asignado_en=ahora))
        db.commit()
    return usuario, clave


def actualizar_usuario(db: Session, usuario: models.Usuario, datos: schemas.UsuarioEditar) -> models.Usuario:
    if datos.documento is not None:
        nuevo_doc = datos.documento.strip()
        if not nuevo_doc:
            raise ErrorRBAC("El documento no puede quedar vacío.", 400)
        otro = auth.buscar_usuario(db, nuevo_doc)
        if otro is not None and otro.id != usuario.id:
            raise ErrorRBAC("Ya existe un usuario con ese documento.", 409)
        usuario.documento = nuevo_doc
    if datos.email is not None:
        nuevo_email = datos.email.strip().lower() or None
        if nuevo_email:
            otro = db.scalar(
                select(models.Usuario).where(models.Usuario.email == nuevo_email, models.Usuario.id != usuario.id)
            )
            if otro is not None:
                raise ErrorRBAC("Ya existe un usuario con ese correo.", 409)
        usuario.email = nuevo_email
    if datos.nombre is not None:
        if not datos.nombre.strip():
            raise ErrorRBAC("El nombre no puede quedar vacío.", 400)
        usuario.nombre = datos.nombre.strip()
    if datos.quitar_docente:
        usuario.docente_id = None
    elif datos.docente_id is not None:
        if db.get(models.Docente, datos.docente_id) is None:
            raise ErrorRBAC("Ese docente no existe.", 404)
        otro = db.scalar(
            select(models.Usuario).where(models.Usuario.docente_id == datos.docente_id, models.Usuario.id != usuario.id)
        )
        if otro is not None:
            raise ErrorRBAC("Ese docente ya tiene un usuario.", 409)
        usuario.docente_id = datos.docente_id
    usuario.actualizado_en = fechas.ahora_utc()
    db.commit()
    db.refresh(usuario)
    return usuario


def restablecer_clave_admin(db: Session, usuario: models.Usuario) -> str:
    """Contraseña temporal de un solo uso; auth.establecer_clave ya revoca
    todas las sesiones del usuario y exige cambiarla al ingresar."""
    clave = seguridad.clave_temporal()
    auth.establecer_clave(db, usuario, clave, exigir_cambio=True)
    return clave


def cambiar_estado_usuario(
    db: Session, usuario: models.Usuario, nuevo_estado: str, *, actor_id: int
) -> models.Usuario:
    if nuevo_estado not in ("activo", "inactivo", "bloqueado"):
        raise ErrorRBAC("Estado no válido.", 400)
    if usuario.id == actor_id and nuevo_estado != "activo":
        raise ErrorRBAC("No puedes desactivar tu propia cuenta.", 400)

    def aplicar() -> None:
        usuario.estado = nuevo_estado
        usuario.actualizado_en = fechas.ahora_utc()
        usuario.desactivado_en = None if nuevo_estado == "activo" else fechas.ahora_utc()

    rbac.aplicar_si_no_bloquea(db, aplicar)
    if nuevo_estado != "activo":
        auth.revocar_sesiones_del_usuario(db, usuario.id, motivo=f"usuario_{nuevo_estado}")
    db.refresh(usuario)
    return usuario


def establecer_roles_usuario(
    db: Session, usuario: models.Usuario, codigos: list[str], *, asignado_por_id: int | None
) -> list[str]:
    roles = _validar_codigos_roles(db, codigos)

    def aplicar() -> None:
        db.execute(delete(models.UsuarioRol).where(models.UsuarioRol.usuario_id == usuario.id))
        ahora = fechas.ahora_utc()
        for rol in roles:
            db.add(
                models.UsuarioRol(
                    usuario_id=usuario.id, rol_id=rol.id, asignado_por=asignado_por_id, asignado_en=ahora
                )
            )

    rbac.aplicar_si_no_bloquea(db, aplicar)
    return sorted(r.codigo for r in roles)


def establecer_sedes_usuario(db: Session, usuario: models.Usuario, sede_ids: list[int]) -> list[int]:
    """Guarda usuario_sedes. Sin efecto en los permisos (no pasa por
    aplicar_si_no_bloquea): hoy ningún endpoint restringe por sede."""
    ids_unicos = sorted(set(sede_ids))
    if ids_unicos:
        encontrados = set(
            db.scalars(select(models.Sede.id).where(models.Sede.id.in_(ids_unicos))).all()
        )
        faltan = [i for i in ids_unicos if i not in encontrados]
        if faltan:
            raise ErrorRBAC(f"Sede(s) inexistente(s): {faltan}", 400)
    db.execute(delete(models.UsuarioSede).where(models.UsuarioSede.usuario_id == usuario.id))
    ahora = fechas.ahora_utc()
    for sede_id in ids_unicos:
        db.add(models.UsuarioSede(usuario_id=usuario.id, sede_id=sede_id, creado_en=ahora))
    db.commit()
    return ids_unicos


def revocar_sesiones_usuario_admin(db: Session, usuario: models.Usuario) -> int:
    return auth.revocar_sesiones_del_usuario(db, usuario.id, motivo="revocado_por_administrador")
