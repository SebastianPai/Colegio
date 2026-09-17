"""Endpoints de autenticación. Son los ÚNICOS que exigen sesión por ahora
(/yo, /sesiones, /logout, /cambiar-clave); el resto de la aplicación sigue
funcionando sin login, igual que antes."""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .. import auth, models, rbac, schemas, seguridad
from ..database import get_db

router = APIRouter(prefix="/api/auth", tags=["autenticacion"])


# --- Utilidades de la petición ----------------------------------------------


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _comprobar_origen(request: Request) -> None:
    """Defensa CSRF sencilla: si el navegador manda Origin (lo hace en toda
    petición con datos), su host debe ser el mismo del servidor. Junto con
    SameSite=Strict, evita que otra página dispare estas acciones."""
    origen = request.headers.get("origin")
    if not origen:
        return
    host_peticion = request.headers.get("host", "")
    host_origen = origen.split("//", 1)[-1]
    if host_origen != host_peticion:
        raise HTTPException(status_code=403, detail="Origen no permitido.")


def _poner_cookies(
    request: Request,
    respuesta: Response,
    *,
    token_acceso: str,
    expira_acceso: dt.datetime,
    token_renovacion: str,
    sesion: models.Sesion,
) -> None:
    segura = seguridad.conexion_segura(dict(request.headers), request.url.scheme)
    # Cookie de acceso: de sesión del navegador (no queda en disco). Si el
    # navegador se cierra, la de renovación reabre la sesión sin pedir clave.
    respuesta.set_cookie(
        seguridad.COOKIE_ACCESO, token_acceso,
        httponly=True, samesite="strict", secure=segura, path="/",
    )
    # Cookie de renovación: persiste solo si el usuario confió en el equipo.
    duracion = None
    if sesion.confiable:
        # ultimo_uso es "ahora" (se acaba de crear o renovar la sesión).
        duracion = max(60, int((sesion.expira_absoluta_en - sesion.ultimo_uso).total_seconds()))
    respuesta.set_cookie(
        seguridad.COOKIE_RENOVACION, token_renovacion,
        max_age=duracion, httponly=True, samesite="strict", secure=segura,
        path=seguridad.RUTA_COOKIE_RENOVACION,
    )


def _borrar_cookies(request: Request, respuesta: Response) -> None:
    segura = seguridad.conexion_segura(dict(request.headers), request.url.scheme)
    respuesta.delete_cookie(seguridad.COOKIE_ACCESO, path="/", httponly=True, samesite="strict", secure=segura)
    respuesta.delete_cookie(
        seguridad.COOKIE_RENOVACION, path=seguridad.RUTA_COOKIE_RENOVACION,
        httponly=True, samesite="strict", secure=segura,
    )


def _respuesta_sesion(
    usuario: models.Usuario, sesion: models.Sesion, expira_acceso: dt.datetime, db: Session
) -> schemas.SesionActual:
    dispositivo = db.get(models.Dispositivo, sesion.dispositivo_id)
    # roles/permisos son solo para que el menú del frontend muestre lo que
    # corresponde: no son columnas de Usuario, se calculan aparte (Fase 3) y
    # el backend vuelve a validar cada permiso en su propio endpoint.
    usuario_actual = schemas.UsuarioActual.model_validate(usuario).model_copy(
        update={
            "roles": [r.codigo for r in rbac.roles_del_usuario(db, usuario.id)],
            "permisos": sorted(rbac.permisos_efectivos(db, usuario)),
        }
    )
    return schemas.SesionActual(
        usuario=usuario_actual,
        sesion=schemas.SesionResumen(
            id=sesion.id,
            dispositivo_id=sesion.dispositivo_id,
            dispositivo_nombre=dispositivo.nombre if dispositivo else None,
            confiable=sesion.confiable,
            creada_en=sesion.creada_en,
            ultimo_uso=sesion.ultimo_uso,
            expira_en=sesion.expira_en,
            expira_absoluta_en=sesion.expira_absoluta_en,
        ),
        expira_acceso_en=expira_acceso,
    )


# --- Endpoints ---------------------------------------------------------------


@router.post("/login", response_model=schemas.SesionActual)
def login(
    datos: schemas.LoginSolicitud, request: Request, respuesta: Response, db: Session = Depends(get_db)
):
    _comprobar_origen(request)
    try:
        usuario = auth.autenticar(db, datos.usuario, datos.clave, ip=_ip(request))
        sesion, token_renovacion, token_acceso, expira_acceso = auth.iniciar_sesion(
            db, usuario,
            dispositivo_id=datos.dispositivo_id,
            nombre_dispositivo=datos.nombre_dispositivo,
            confiar=datos.confiar_en_dispositivo,
            ip=_ip(request),
            user_agent=request.headers.get("user-agent", ""),
        )
    except auth.ErrorAutenticacion as e:
        raise HTTPException(status_code=e.codigo, detail=e.mensaje)
    _poner_cookies(
        request, respuesta,
        token_acceso=token_acceso, expira_acceso=expira_acceso,
        token_renovacion=token_renovacion, sesion=sesion,
    )
    return _respuesta_sesion(usuario, sesion, expira_acceso, db)


@router.post("/refresh", response_model=schemas.SesionActual)
def renovar(request: Request, respuesta: Response, db: Session = Depends(get_db)):
    _comprobar_origen(request)
    try:
        sesion, token_renovacion, token_acceso, expira_acceso = auth.renovar_sesion(
            db, request.cookies.get(seguridad.COOKIE_RENOVACION) or "", ip=_ip(request)
        )
    except auth.ErrorAutenticacion as e:
        _borrar_cookies(request, respuesta)
        raise HTTPException(status_code=e.codigo, detail=e.mensaje)
    usuario = db.get(models.Usuario, sesion.usuario_id)
    _poner_cookies(
        request, respuesta,
        token_acceso=token_acceso, expira_acceso=expira_acceso,
        token_renovacion=token_renovacion, sesion=sesion,
    )
    return _respuesta_sesion(usuario, sesion, expira_acceso, db)


@router.post("/logout")
def logout(request: Request, respuesta: Response, db: Session = Depends(get_db)):
    """Cierra la sesión de ESTE dispositivo. Responde igual aunque no haya
    sesión (así el cliente siempre puede 'salir')."""
    _comprobar_origen(request)
    identidad = auth.identidad_opcional(request, db)
    if identidad is not None:
        auth.revocar_sesion(db, identidad.sesion, motivo="logout")
    _borrar_cookies(request, respuesta)
    return {"cerrada": identidad is not None}


@router.post("/logout-todos")
def logout_todos(
    request: Request, respuesta: Response,
    identidad: auth.Identidad = Depends(auth.identidad_actual),
    db: Session = Depends(get_db),
):
    """Cierra la sesión en TODOS los dispositivos del usuario, incluido este."""
    _comprobar_origen(request)
    cerradas = auth.revocar_sesiones_del_usuario(db, identidad.usuario.id, motivo="logout_todos")
    _borrar_cookies(request, respuesta)
    return {"sesiones_cerradas": cerradas}


@router.get("/yo", response_model=schemas.SesionActual)
def sesion_actual(
    identidad: auth.Identidad = Depends(auth.identidad_actual), db: Session = Depends(get_db)
):
    # expira_acceso viene del token que trajo la petición: así el cliente sabe
    # exactamente cuándo debe renovar.
    return _respuesta_sesion(identidad.usuario, identidad.sesion, identidad.expira_acceso, db)


@router.post("/cambiar-clave")
def cambiar_clave(
    datos: schemas.CambiarClave, request: Request,
    identidad: auth.Identidad = Depends(auth.identidad_actual),
    db: Session = Depends(get_db),
):
    """Cambia la contraseña propia y cierra las demás sesiones del usuario."""
    _comprobar_origen(request)
    try:
        auth.cambiar_clave(
            db, identidad.usuario, datos.clave_actual, datos.clave_nueva,
            sesion_actual_id=identidad.sesion.id,
        )
    except auth.ErrorAutenticacion as e:
        raise HTTPException(status_code=e.codigo, detail=e.mensaje)
    return {"cambiada": True}


@router.get("/sesiones", response_model=list[schemas.SesionListada])
def mis_sesiones(
    identidad: auth.Identidad = Depends(auth.identidad_actual), db: Session = Depends(get_db)
):
    """Sesiones abiertas del usuario (sus dispositivos)."""
    salida = []
    for s in auth.listar_sesiones(db, identidad.usuario.id):
        dispositivo = db.get(models.Dispositivo, s.dispositivo_id)
        salida.append(
            schemas.SesionListada(
                id=s.id,
                dispositivo_nombre=dispositivo.nombre if dispositivo else None,
                confiable=s.confiable,
                creada_en=s.creada_en,
                ultimo_uso=s.ultimo_uso,
                expira_en=s.expira_en,
                ip=s.ip,
                es_la_actual=s.id == identidad.sesion.id,
            )
        )
    return salida


@router.delete("/sesiones/{sesion_id}")
def cerrar_sesion(
    sesion_id: str, request: Request, respuesta: Response,
    identidad: auth.Identidad = Depends(auth.identidad_actual),
    db: Session = Depends(get_db),
):
    """Cierra una sesión propia (por ejemplo, un celular perdido)."""
    _comprobar_origen(request)
    sesion = db.get(models.Sesion, sesion_id)
    if sesion is None or sesion.usuario_id != identidad.usuario.id:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")
    auth.revocar_sesion(db, sesion, motivo="cerrada_por_el_usuario")
    if sesion.id == identidad.sesion.id:
        _borrar_cookies(request, respuesta)
    return {"cerrada": True}
