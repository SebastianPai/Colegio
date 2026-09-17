"""Administración de roles, permisos y usuarios (Fase 3: RBAC).

Todos estos endpoints son NUEVOS y quedan protegidos desde el primer día
(nadie los usa todavía: no hay pantalla). Las rutas EXISTENTES de la
aplicación (estudiantes, boletines, horarios, SAPRED, constancias...) no se
tocan en esta fase — eso es la fase siguiente."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import auth, models, rbac, rbac_admin, schemas
from ..database import get_db

router = APIRouter(prefix="/api/admin", tags=["administracion"])


def _atrapar(fn, *args, **kwargs):
    """Ejecuta fn(...) traduciendo los errores de negocio a HTTPException,
    para no repetir el mismo try/except en cada endpoint."""
    try:
        return fn(*args, **kwargs)
    except (auth.ErrorAutenticacion, rbac_admin.ErrorRBAC) as e:
        raise HTTPException(status_code=e.codigo, detail=e.mensaje)
    except rbac.ErrorBloqueoAdministrativo as e:
        raise HTTPException(status_code=409, detail=str(e))


def _rol_o_404(db: Session, rol_id: int) -> models.Rol:
    rol = db.get(models.Rol, rol_id)
    if rol is None:
        raise HTTPException(status_code=404, detail="Rol no encontrado.")
    return rol


def _usuario_o_404(db: Session, usuario_id: int) -> models.Usuario:
    usuario = db.get(models.Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return usuario


# --- Permisos (catálogo, solo lectura) ---------------------------------------


@router.get("/permisos", response_model=list[schemas.PermisoInfo])
def listar_permisos(
    identidad: auth.Identidad = Depends(rbac.requiere("roles.ver")), db: Session = Depends(get_db)
):
    return rbac_admin.listar_permisos(db)


# --- Roles ---------------------------------------------------------------------


@router.get("/roles", response_model=list[schemas.RolResumen])
def listar_roles(
    identidad: auth.Identidad = Depends(rbac.requiere("roles.ver")), db: Session = Depends(get_db)
):
    return rbac_admin.listar_roles(db)


@router.get("/roles/{rol_id}", response_model=schemas.RolDetalle)
def obtener_rol(
    rol_id: int, identidad: auth.Identidad = Depends(rbac.requiere("roles.ver")), db: Session = Depends(get_db)
):
    detalle = rbac_admin.obtener_rol_detalle(db, rol_id)
    if detalle is None:
        raise HTTPException(status_code=404, detail="Rol no encontrado.")
    return detalle


@router.post("/roles", response_model=schemas.RolResumen, status_code=201)
def crear_rol(
    datos: schemas.RolCrear,
    identidad: auth.Identidad = Depends(rbac.requiere("roles.gestionar")),
    db: Session = Depends(get_db),
):
    rol = _atrapar(rbac_admin.crear_rol, db, datos)
    return rbac_admin._rol_a_resumen(db, rol)


@router.patch("/roles/{rol_id}", response_model=schemas.RolResumen)
def actualizar_rol(
    rol_id: int, datos: schemas.RolActualizar,
    identidad: auth.Identidad = Depends(rbac.requiere("roles.gestionar")),
    db: Session = Depends(get_db),
):
    rol = _rol_o_404(db, rol_id)
    rol = _atrapar(rbac_admin.actualizar_rol, db, rol, datos)
    return rbac_admin._rol_a_resumen(db, rol)


@router.put("/roles/{rol_id}/permisos", response_model=schemas.RolDetalle)
def establecer_permisos_rol(
    rol_id: int, datos: schemas.RolPermisosActualizar,
    identidad: auth.Identidad = Depends(rbac.requiere("roles.gestionar")),
    db: Session = Depends(get_db),
):
    rol = _rol_o_404(db, rol_id)
    _atrapar(rbac_admin.establecer_permisos_rol, db, rol, datos.permisos)
    return rbac_admin.obtener_rol_detalle(db, rol_id)


@router.delete("/roles/{rol_id}")
def eliminar_rol(
    rol_id: int, identidad: auth.Identidad = Depends(rbac.requiere("roles.gestionar")), db: Session = Depends(get_db)
):
    rol = _rol_o_404(db, rol_id)
    _atrapar(rbac_admin.eliminar_rol, db, rol)
    return {"eliminado": True}


# --- Usuarios ------------------------------------------------------------------


@router.get("/usuarios", response_model=list[schemas.UsuarioAdminResumen])
def listar_usuarios(
    identidad: auth.Identidad = Depends(rbac.requiere("usuarios.ver")), db: Session = Depends(get_db)
):
    return rbac_admin.listar_usuarios(db)


@router.get("/usuarios/{usuario_id}", response_model=schemas.UsuarioAdminDetalle)
def obtener_usuario(
    usuario_id: int, identidad: auth.Identidad = Depends(rbac.requiere("usuarios.ver")), db: Session = Depends(get_db)
):
    detalle = rbac_admin.obtener_usuario_detalle(db, usuario_id)
    if detalle is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return detalle


@router.post("/usuarios", response_model=schemas.UsuarioCreado, status_code=201)
def crear_usuario(
    datos: schemas.UsuarioCrear,
    identidad: auth.Identidad = Depends(rbac.requiere("usuarios.crear")),
    db: Session = Depends(get_db),
):
    usuario, clave = _atrapar(rbac_admin.crear_usuario_admin, db, datos, identidad.usuario.id)
    return schemas.UsuarioCreado(usuario=rbac_admin._usuario_a_resumen(db, usuario), clave_temporal=clave)


@router.patch("/usuarios/{usuario_id}", response_model=schemas.UsuarioAdminResumen)
def actualizar_usuario(
    usuario_id: int, datos: schemas.UsuarioEditar,
    identidad: auth.Identidad = Depends(rbac.requiere("usuarios.editar")),
    db: Session = Depends(get_db),
):
    usuario = _usuario_o_404(db, usuario_id)
    usuario = _atrapar(rbac_admin.actualizar_usuario, db, usuario, datos)
    return rbac_admin._usuario_a_resumen(db, usuario)


@router.post("/usuarios/{usuario_id}/estado", response_model=schemas.UsuarioAdminResumen)
def cambiar_estado_usuario(
    usuario_id: int, datos: schemas.UsuarioEstado,
    identidad: auth.Identidad = Depends(rbac.requiere("usuarios.estado")),
    db: Session = Depends(get_db),
):
    usuario = _usuario_o_404(db, usuario_id)
    usuario = _atrapar(
        rbac_admin.cambiar_estado_usuario, db, usuario, datos.estado, actor_id=identidad.usuario.id
    )
    return rbac_admin._usuario_a_resumen(db, usuario)


@router.post("/usuarios/{usuario_id}/restablecer-clave", response_model=schemas.ClaveTemporalRespuesta)
def restablecer_clave(
    usuario_id: int,
    identidad: auth.Identidad = Depends(rbac.requiere("usuarios.restablecer_clave")),
    db: Session = Depends(get_db),
):
    usuario = _usuario_o_404(db, usuario_id)
    clave = _atrapar(rbac_admin.restablecer_clave_admin, db, usuario)
    return schemas.ClaveTemporalRespuesta(clave_temporal=clave)


@router.put("/usuarios/{usuario_id}/roles", response_model=schemas.UsuarioAdminResumen)
def establecer_roles_usuario(
    usuario_id: int, datos: schemas.UsuarioRolesActualizar,
    identidad: auth.Identidad = Depends(rbac.requiere("usuarios.roles")),
    db: Session = Depends(get_db),
):
    usuario = _usuario_o_404(db, usuario_id)
    _atrapar(
        rbac_admin.establecer_roles_usuario, db, usuario, datos.roles, asignado_por_id=identidad.usuario.id
    )
    return rbac_admin._usuario_a_resumen(db, usuario)


@router.put("/usuarios/{usuario_id}/sedes", response_model=schemas.UsuarioAdminDetalle)
def establecer_sedes_usuario(
    usuario_id: int, datos: schemas.UsuarioSedesActualizar,
    # Permiso propio (usuarios.sedes), separado de usuarios.roles: ver
    # app/permisos.py y el informe de la Fase 3 para la justificación.
    identidad: auth.Identidad = Depends(rbac.requiere("usuarios.sedes")),
    db: Session = Depends(get_db),
):
    usuario = _usuario_o_404(db, usuario_id)
    _atrapar(rbac_admin.establecer_sedes_usuario, db, usuario, datos.sedes)
    return rbac_admin.obtener_usuario_detalle(db, usuario_id)


@router.get("/usuarios/{usuario_id}/sesiones", response_model=list[schemas.SesionListada])
def sesiones_de_usuario(
    usuario_id: int, identidad: auth.Identidad = Depends(rbac.requiere("sesiones.ver")), db: Session = Depends(get_db)
):
    usuario = _usuario_o_404(db, usuario_id)
    salida = []
    for s in auth.listar_sesiones(db, usuario.id):
        dispositivo = db.get(models.Dispositivo, s.dispositivo_id)
        salida.append(
            schemas.SesionListada(
                id=s.id, dispositivo_nombre=dispositivo.nombre if dispositivo else None,
                confiable=s.confiable, creada_en=s.creada_en, ultimo_uso=s.ultimo_uso,
                expira_en=s.expira_en, ip=s.ip, es_la_actual=False,
            )
        )
    return salida


@router.post("/usuarios/{usuario_id}/revocar-sesiones")
def revocar_sesiones_usuario(
    usuario_id: int,
    identidad: auth.Identidad = Depends(rbac.requiere("sesiones.revocar")),
    db: Session = Depends(get_db),
):
    usuario = _usuario_o_404(db, usuario_id)
    cerradas = rbac_admin.revocar_sesiones_usuario_admin(db, usuario)
    return {"sesiones_cerradas": cerradas}


# --- Observaciones (Fase 4A: modo observación, solo lectura) -----------------


@router.get("/observaciones-fase4a")
def resumen_observaciones_fase4a(
    limite: int = 500,
    identidad: auth.Identidad = Depends(rbac.requiere("auditoria.ver")),
    db: Session = Depends(get_db),
):
    """Agrupado por endpoint+método+permiso+usuario+resultado: cuántas veces
    cada combinación habría pasado, habría sido rechazada, o llegó sin
    sesión, desde que se activó el modo observación. Nunca bloqueó nada —
    ver rbac.observar()."""
    filas = db.execute(
        select(
            models.ObservacionPermiso.endpoint,
            models.ObservacionPermiso.metodo,
            models.ObservacionPermiso.permiso,
            models.ObservacionPermiso.usuario_id,
            models.Usuario.documento,
            models.ObservacionPermiso.resultado,
            func.count().label("veces"),
            func.max(models.ObservacionPermiso.creado_en).label("ultima_vez"),
        )
        .outerjoin(models.Usuario, models.Usuario.id == models.ObservacionPermiso.usuario_id)
        .group_by(
            models.ObservacionPermiso.endpoint,
            models.ObservacionPermiso.metodo,
            models.ObservacionPermiso.permiso,
            models.ObservacionPermiso.usuario_id,
            models.ObservacionPermiso.resultado,
        )
        .order_by(func.count().desc())
        .limit(limite)
    ).all()
    return [
        {
            "endpoint": endpoint, "metodo": metodo, "permiso": permiso,
            "usuario_id": usuario_id, "usuario_documento": documento,
            "resultado": resultado, "veces": veces, "ultima_vez": ultima_vez,
        }
        for endpoint, metodo, permiso, usuario_id, documento, resultado, veces, ultima_vez in filas
    ]
