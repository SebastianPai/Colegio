"""Pruebas de la Fase 3 (RBAC: roles y permisos), sobre una COPIA temporal de
la base: nunca toca colegio.db.

Sección A: catálogo, siembra, permisos efectivos, alcance y reglas
anti-bloqueo, todo por acceso directo a la base (rápido, sin HTTP).

Sección B: el servidor real (uvicorn) levantado sobre la copia, con clientes
que actúan como navegadores (guardan cookies), para probar de verdad los 17
endpoints de administración: 401 sin sesión, 403 sin permiso, 200/201 con
permiso, que un cambio de permisos surte efecto en la SIGUIENTE petición sin
reiniciar el servidor, la unión de permisos de dos roles, y las reglas
anti-bloqueo por HTTP.

    ./venv/Scripts/python.exe probar_rbac.py
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
ORIGEN = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND / "colegio.db"
TMP = Path(tempfile.mkdtemp(prefix="ietaba_rbac_"))
COPIA = TMP / "colegio.db"
PUERTO = 8811
BASE_URL = f"http://127.0.0.1:{PUERTO}"
CLAVE = "PruebaSeguraRBAC2026"

src = sqlite3.connect(f"file:{ORIGEN}?mode=ro", uri=True)
dst = sqlite3.connect(COPIA)
with dst:
    src.backup(dst)
src.close()
dst.close()

os.environ["IETABA_DB_PATH"] = str(COPIA)
sys.path.insert(0, str(BACKEND))

print(f"Copia de prueba: {COPIA}\n\n[0] Arranque sobre la copia (migraciones: RBAC)")
from sqlalchemy import delete, select  # noqa: E402

from app import main as _arranque  # noqa: E402,F401  (ejecuta migraciones.ejecutar() sobre la copia)
from app import auth, migraciones, models, permisos as catalogo, rbac, rbac_admin  # noqa: E402
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


def _usuario_con_rol(db, documento: str, *codigos_rol: str) -> models.Usuario:
    u = auth.registrar_usuario(db, documento=documento, nombre=f"Prueba {documento}", clave=CLAVE, debe_cambiar_clave=False)
    if codigos_rol:
        rbac_admin.establecer_roles_usuario(db, u, list(codigos_rol), asignado_por_id=None)
    return u


# =============================================================================
# SECCIÓN A: catálogo, siembra, permisos y anti-bloqueo (sin HTTP)
# =============================================================================
print("\n[A1] Catálogo de permisos")
verificar(f"{len(catalogo.CATALOGO)} permisos, sin códigos repetidos", len(catalogo.CODIGOS) == len(catalogo.CATALOGO))
faltantes = [
    codigo for definicion in catalogo.ROLES_SISTEMA for codigo in definicion.permisos if codigo not in catalogo.CODIGOS
]
verificar("todos los permisos citados por ROLES_SISTEMA existen en el catálogo", not faltantes, str(faltantes))

print("\n[A2] Siembra en la base (primera ejecución, ya ocurrió al importar app.main)")
db = SessionLocal()
verificar(
    f"tabla permisos = {db.query(models.Permiso).count()} filas (== catálogo)",
    db.query(models.Permiso).count() == len(catalogo.CATALOGO),
)
roles_bd = {r.codigo: r for r in db.scalars(select(models.Rol)).all()}
verificar(f"los 5 roles del sistema existen: {sorted(roles_bd)}", set(roles_bd) == {d.codigo for d in catalogo.ROLES_SISTEMA})
verificar("los 5 son es_sistema=True y activo=True", all(r.es_sistema and r.activo for r in roles_bd.values()))
db.close()

print("\n[A3] Segunda y tercera ejecución: idempotente")
r2 = migraciones.ejecutar()
r3 = migraciones.ejecutar()
verificar(f"2ª ejecución no crea nada nuevo: {r2}", r2["permisos_sincronizados"] == [] and r2["roles_sembrados"] == [])
verificar(f"3ª ejecución tampoco: {r3}", r3 == r2)

print("\n[A4] Bootstrap: en una base fresca, cero usuarios ⇒ cero administradores")
db = SessionLocal()
verificar("con la base recién migrada (0 usuarios), control total = []", rbac.usuarios_con_control_total(db) == [])
# A partir de aquí se necesita un administrador para poder seguir probando
# rbac_admin.establecer_permisos_rol()/establecer_roles_usuario(): las DOS
# pasan por aplicar_si_no_bloquea, que exige que YA quede (o quede tras el
# cambio) al menos un administrador — exactamente como en producción, donde
# nadie puede llamar a estos endpoints sin ya ser administrador. El primer
# administrador real lo crea el operador con crear_usuario.py (fuera de la
# API), que es este mismo camino: crear el usuario y asignarle el rol.
u_admin1 = _usuario_con_rol(db, "PRUEBA-ADMIN-1", "administrador")
verificar("asignarle 'administrador' al primer usuario SÍ funciona (pasa de 0 a 1)", rbac.usuarios_con_control_total(db) == [u_admin1.id])

print("\n[A5] Permisos efectivos: unión de dos roles")
rol_a = models.Rol(codigo="prueba_a", nombre="Prueba A", es_sistema=False, activo=True)
rol_b = models.Rol(codigo="prueba_b", nombre="Prueba B", es_sistema=False, activo=True)
db.add_all([rol_a, rol_b])
db.commit()
rbac_admin.establecer_permisos_rol(db, rol_a, ["estudiantes.ver", "docentes.ver"])
rbac_admin.establecer_permisos_rol(db, rol_b, ["docentes.ver", "horario.ver"])
u_union = _usuario_con_rol(db, "PRUEBA-UNION")
rbac_admin.establecer_roles_usuario(db, u_union, ["prueba_a", "prueba_b"], asignado_por_id=None)
efectivos = rbac.permisos_efectivos(db, u_union)
verificar(
    f"unión = {sorted(efectivos)}",
    efectivos == {"estudiantes.ver", "docentes.ver", "horario.ver"},
)

print("\n[A6] Permisos/roles inactivos no se otorgan")
u_solo_b = _usuario_con_rol(db, "PRUEBA-SOLO-B", "prueba_b")
verificar("con el rol activo, tiene sus permisos", rbac.permisos_efectivos(db, u_solo_b) == {"docentes.ver", "horario.ver"})
rol_b.activo = False
db.commit()
verificar("rol desactivado → sin permisos de ese rol", rbac.permisos_efectivos(db, u_solo_b) == set())
rol_b.activo = True
db.commit()
permiso_horario = db.scalar(select(models.Permiso).where(models.Permiso.codigo == "horario.ver"))
permiso_horario.activo = False
db.commit()
verificar(
    "un permiso con activo=False no se otorga aunque el rol lo tenga asignado",
    rbac.permisos_efectivos(db, u_solo_b) == {"docentes.ver"},
)
permiso_horario.activo = True
db.commit()

print("\n[A7] Usuario sin roles")
u_sin_roles = _usuario_con_rol(db, "PRUEBA-SIN-ROLES")
verificar("sin roles → sin permisos", rbac.permisos_efectivos(db, u_sin_roles) == set())

print("\n[A8] sedes_permitidas()")
verificar("sin filas en usuario_sedes → None (sin restricción)", rbac.sedes_permitidas(db, u_sin_roles) is None)
sede_1 = db.scalar(select(models.Sede.id))
sede_2 = db.scalars(select(models.Sede.id).where(models.Sede.id != sede_1)).first()
rbac_admin.establecer_sedes_usuario(db, u_sin_roles, [sede_1, sede_2])
verificar(f"con filas → el conjunto exacto {{{sede_1}, {sede_2}}}", rbac.sedes_permitidas(db, u_sin_roles) == {sede_1, sede_2})
rbac_admin.establecer_sedes_usuario(db, u_sin_roles, [])
verificar("vaciar la lista vuelve a 'sin restricción'", rbac.sedes_permitidas(db, u_sin_roles) is None)

print("\n[A9] Reglas anti-bloqueo (a nivel de base)")
verificar("u_admin1 (creado en [A4]) sigue siendo el único con control total", rbac.usuarios_con_control_total(db) == [u_admin1.id])

lanzo = False
try:
    rbac_admin.establecer_roles_usuario(db, u_admin1, [], asignado_por_id=None)
except rbac.ErrorBloqueoAdministrativo:
    lanzo = True
verificar("quitarle el rol al ÚNICO administrador se rechaza (ErrorBloqueoAdministrativo)", lanzo)
db.expire_all()
verificar("...y el cambio se deshizo: sigue siendo administrador", {r.codigo for r in rbac.roles_del_usuario(db, u_admin1.id)} == {"administrador"})

u_admin2 = _usuario_con_rol(db, "PRUEBA-ADMIN-2", "administrador")
verificar(
    "con DOS administradores, sí se le puede quitar el rol a uno",
    rbac_admin.establecer_roles_usuario(db, u_admin1, [], asignado_por_id=None) == [],
)
db.expire_all()
verificar("...ahora u_admin1 no tiene roles", rbac.roles_del_usuario(db, u_admin1.id) == [])
verificar("...y u_admin2 sigue siendo el administrador que sostiene el sistema", rbac.usuarios_con_control_total(db) == [u_admin2.id])

print("\n[A10] Quitar un permiso de un rol y reiniciar NO lo repone")
rol_docente = roles_bd["docente"]
antes = {
    codigo for (codigo,) in db.execute(
        select(models.Permiso.codigo).join(models.RolPermiso, models.RolPermiso.permiso_id == models.Permiso.id)
        .where(models.RolPermiso.rol_id == rol_docente.id)
    ).all()
}
verificar("el rol docente trae 'asistencia.registrar' de fábrica", "asistencia.registrar" in antes)
rbac_admin.establecer_permisos_rol(db, rol_docente, sorted(antes - {"asistencia.registrar"}))
migraciones.sembrar_roles_sistema()  # simula un reinicio del servidor
despues = {
    codigo for (codigo,) in db.execute(
        select(models.Permiso.codigo).join(models.RolPermiso, models.RolPermiso.permiso_id == models.Permiso.id)
        .where(models.RolPermiso.rol_id == rol_docente.id)
    ).all()
}
verificar("tras 'reiniciar' (sembrar_roles_sistema), el permiso quitado NO reaparece", "asistencia.registrar" not in despues)
rbac_admin.establecer_permisos_rol(db, rol_docente, sorted(antes))  # se repone para no afectar la Sección B

print("\n[A11] Roles del sistema: no se pueden eliminar ni desactivar")
try:
    rbac_admin.eliminar_rol(db, roles_bd["administrador"])
    fallo_1 = False
except rbac_admin.ErrorRBAC:
    fallo_1 = True
verificar("eliminar un rol de sistema se rechaza", fallo_1)
import app.schemas as schemas  # noqa: E402
try:
    rbac_admin.actualizar_rol(db, roles_bd["administrador"], schemas.RolActualizar(activo=False))
    fallo_2 = False
except rbac_admin.ErrorRBAC:
    fallo_2 = True
verificar("desactivar un rol de sistema se rechaza", fallo_2)
db.close()

# =============================================================================
# SECCIÓN B: los 17 endpoints por HTTP, con el servidor real
# =============================================================================
print("\n[B0] Servidor de prueba")
registro = open(TMP / "servidor.log", "w", encoding="utf-8")
servidor = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PUERTO), "--log-level", "warning"],
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


class Cliente:
    def __init__(self):
        self.jar = CookieJar()
        self.abridor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

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

    def login(self, documento):
        estado, _ = self.pedir("/api/auth/login", "POST", {"usuario": documento, "clave": CLAVE})
        assert estado == 200, f"login de {documento} falló: {estado}"


def _json(datos: bytes):
    try:
        return json.loads(datos)
    except ValueError:
        return None


try:
    # Los 17 endpoints, uno por permiso distinto que exigen (con un id que no
    # existe donde hace falta uno: la dependencia de permiso se evalúa ANTES
    # de que el endpoint llegue a buscar ese id, así que un 401/403 debe
    # salir igual sin que el 404 se interponga).
    ENDPOINTS = [
        ("GET", "/api/admin/permisos", None),                                   # roles.ver
        ("GET", "/api/admin/roles", None),                                      # roles.ver
        ("GET", "/api/admin/roles/999999", None),                               # roles.ver
        ("POST", "/api/admin/roles", {"codigo": "x", "nombre": "x"}),           # roles.gestionar
        ("PATCH", "/api/admin/roles/999999", {"nombre": "x"}),                  # roles.gestionar
        ("PUT", "/api/admin/roles/999999/permisos", {"permisos": []}),          # roles.gestionar
        ("DELETE", "/api/admin/roles/999999", None),                            # roles.gestionar
        ("GET", "/api/admin/usuarios", None),                                   # usuarios.ver
        ("GET", "/api/admin/usuarios/999999", None),                            # usuarios.ver
        ("POST", "/api/admin/usuarios", {"documento": "X", "nombre": "X"}),     # usuarios.crear
        ("PATCH", "/api/admin/usuarios/999999", {"nombre": "x"}),               # usuarios.editar
        ("POST", "/api/admin/usuarios/999999/estado", {"estado": "inactivo"}),  # usuarios.estado
        ("POST", "/api/admin/usuarios/999999/restablecer-clave", None),         # usuarios.restablecer_clave
        ("PUT", "/api/admin/usuarios/999999/roles", {"roles": []}),             # usuarios.roles
        ("PUT", "/api/admin/usuarios/999999/sedes", {"sedes": []}),             # usuarios.sedes
        ("GET", "/api/admin/usuarios/999999/sesiones", None),                   # sesiones.ver
        ("POST", "/api/admin/usuarios/999999/revocar-sesiones", None),         # sesiones.revocar
    ]
    verificar(f"la muestra cubre los 17 endpoints de administración", len(ENDPOINTS) == 17)

    print("\n[B1] Sin sesión: los 17 endpoints de administración exigen 401")
    anonimo = Cliente()
    for metodo, ruta, cuerpo in ENDPOINTS:
        estado, _ = anonimo.pedir(ruta, metodo, cuerpo)
        verificar(f"{metodo} {ruta} sin sesión → {estado}", estado == 401)

    print("\n[B2] Con sesión pero SIN el permiso: 403")
    db = SessionLocal()
    _usuario_con_rol(db, "PRUEBA-SIN-PERMISOS")  # sin roles
    db.close()
    sin_permisos = Cliente()
    sin_permisos.login("PRUEBA-SIN-PERMISOS")
    for metodo, ruta, cuerpo in ENDPOINTS:
        estado, _ = sin_permisos.pedir(ruta, metodo, cuerpo)
        verificar(f"{metodo} {ruta} sin el permiso → {estado}", estado == 403)

    print("\n[B3] Bootstrap: el primer administrador (por HTTP no hay nadie que lo cree)")
    db = SessionLocal()
    _usuario_con_rol(db, "PRUEBA-SUPERADMIN", "administrador")
    db.close()
    admin = Cliente()
    admin.login("PRUEBA-SUPERADMIN")
    estado, cuerpo_yo = admin.pedir("/api/auth/yo")
    superadmin_id = cuerpo_yo["usuario"]["id"]  # de la respuesta HTTP: sin riesgo de objeto ORM "detached"
    verificar(
        f"/api/auth/yo trae roles y permisos ({len(cuerpo_yo['usuario']['permisos'])} permisos)",
        estado == 200 and cuerpo_yo["usuario"]["roles"] == ["administrador"]
        and "roles.gestionar" in cuerpo_yo["usuario"]["permisos"],
    )
    verificar("nunca se expone el hash de la contraseña", "clave_hash" not in json.dumps(cuerpo_yo) and "scrypt" not in json.dumps(cuerpo_yo))

    print("\n[B4] Con el permiso, el administrador SÍ puede usar los 17 endpoints")
    estado, permisos_api = admin.pedir("/api/admin/permisos")
    verificar(f"GET /api/admin/permisos: {len(permisos_api) if estado == 200 else estado} permisos", estado == 200 and len(permisos_api) == len(catalogo.CATALOGO))

    estado, roles_api = admin.pedir("/api/admin/roles")
    verificar(f"GET /api/admin/roles: {len(roles_api) if estado == 200 else estado}", estado == 200 and len(roles_api) >= 5)
    rol_admin_id = next(r["id"] for r in roles_api if r["codigo"] == "administrador")

    estado, detalle = admin.pedir(f"/api/admin/roles/{rol_admin_id}")
    verificar(f"GET /api/admin/roles/{{id}}: {len(detalle.get('permisos', [])) if estado == 200 else estado} permisos", estado == 200 and "roles.gestionar" in detalle["permisos"])

    estado, rol_prueba = admin.pedir("/api/admin/roles", "POST", {"codigo": "revisor_prueba", "nombre": "Revisor de prueba"})
    verificar(f"POST /api/admin/roles: {estado}", estado == 201 and rol_prueba["total_permisos"] == 0)
    rol_prueba_id = rol_prueba["id"]

    estado, actualizado = admin.pedir(f"/api/admin/roles/{rol_prueba_id}", "PATCH", {"descripcion": "para las pruebas"})
    verificar(f"PATCH /api/admin/roles/{{id}}: {estado}", estado == 200 and actualizado["descripcion"] == "para las pruebas")

    estado, con_permiso = admin.pedir(f"/api/admin/roles/{rol_prueba_id}/permisos", "PUT", {"permisos": ["roles.ver"]})
    verificar(f"PUT .../permisos: {estado}", estado == 200 and con_permiso["permisos"] == ["roles.ver"])

    estado, usuarios_api = admin.pedir("/api/admin/usuarios")
    verificar(f"GET /api/admin/usuarios: {len(usuarios_api) if estado == 200 else estado}", estado == 200 and len(usuarios_api) >= 3)

    estado, creado = admin.pedir("/api/admin/usuarios", "POST", {
        "documento": "PRUEBA-CREADO-API", "nombre": "Creado por API", "roles": ["revisor_prueba"],
    })
    verificar(
        f"POST /api/admin/usuarios: {estado}, clave temporal entregada",
        estado == 201 and len(creado.get("clave_temporal", "")) >= 8,
    )
    usuario_creado_id = creado["usuario"]["id"]

    estado, editado = admin.pedir(f"/api/admin/usuarios/{usuario_creado_id}", "PATCH", {"nombre": "Nombre editado"})
    verificar(f"PATCH /api/admin/usuarios/{{id}}: {estado}", estado == 200 and editado["nombre"] == "Nombre editado")

    estado, con_clave = admin.pedir(f"/api/admin/usuarios/{usuario_creado_id}/restablecer-clave", "POST")
    verificar(f"POST .../restablecer-clave: {estado}", estado == 200 and len(con_clave.get("clave_temporal", "")) >= 8)

    estado, con_rol = admin.pedir(f"/api/admin/usuarios/{usuario_creado_id}/roles", "PUT", {"roles": ["revisor_prueba", "docente"]})
    verificar(f"PUT .../roles: {estado}", estado == 200 and sorted(con_rol["roles"]) == ["docente", "revisor_prueba"])

    estado, con_sede = admin.pedir(f"/api/admin/usuarios/{usuario_creado_id}/sedes", "PUT", {"sedes": [sede_1]})
    verificar(f"PUT .../sedes: {estado}", estado == 200 and con_sede["sedes"] == [sede_1])

    estado, ses = admin.pedir(f"/api/admin/usuarios/{usuario_creado_id}/sesiones")
    verificar(f"GET .../sesiones: {estado}", estado == 200 and isinstance(ses, list))

    estado, desactivado = admin.pedir(f"/api/admin/usuarios/{usuario_creado_id}/estado", "POST", {"estado": "inactivo"})
    verificar(f"POST .../estado: {estado}", estado == 200 and desactivado["estado"] == "inactivo")

    estado, revocadas = admin.pedir(f"/api/admin/usuarios/{usuario_creado_id}/revocar-sesiones", "POST")
    verificar(f"POST .../revocar-sesiones: {estado}", estado == 200 and "sesiones_cerradas" in revocadas)

    print("\n[B5] Un cambio de permisos surte efecto EN LA SIGUIENTE petición, sin reiniciar el servidor")
    revisor = Cliente()
    db = SessionLocal()
    u_revisor = _usuario_con_rol(db, "PRUEBA-REVISOR", "revisor_prueba")
    db.close()
    revisor.login("PRUEBA-REVISOR")
    estado, _ = revisor.pedir("/api/admin/roles")
    verificar(f"con 'roles.ver' concedido al rol, puede listar roles: {estado}", estado == 200)
    estado, _ = admin.pedir(f"/api/admin/roles/{rol_prueba_id}/permisos", "PUT", {"permisos": []})
    verificar(f"el administrador le quita el permiso al rol: {estado}", estado == 200)
    estado, _ = revisor.pedir("/api/admin/roles")
    verificar(f"LA MISMA sesión, sin volver a iniciar sesión, ya no puede: {estado}", estado == 403)

    print("\n[B6] Unión de permisos de DOS roles (por HTTP)")
    admin.pedir(f"/api/admin/roles/{rol_prueba_id}/permisos", "PUT", {"permisos": ["roles.ver"]})
    estado, rol_b_api = admin.pedir("/api/admin/roles", "POST", {"codigo": "revisor_prueba_2", "nombre": "Revisor 2"})
    admin.pedir(f"/api/admin/roles/{rol_b_api['id']}/permisos", "PUT", {"permisos": ["usuarios.ver"]})
    dos_roles = Cliente()
    db = SessionLocal()
    u_dos = _usuario_con_rol(db, "PRUEBA-DOS-ROLES", "revisor_prueba", "revisor_prueba_2")
    db.close()
    dos_roles.login("PRUEBA-DOS-ROLES")
    estado, y = dos_roles.pedir("/api/auth/yo")
    verificar(
        f"tiene la unión de los dos roles: {sorted(y['usuario']['permisos'])}",
        set(y["usuario"]["permisos"]) == {"roles.ver", "usuarios.ver"},
    )
    verificar("puede /api/admin/roles (por revisor_prueba)", dos_roles.pedir("/api/admin/roles")[0] == 200)
    verificar("puede /api/admin/usuarios (por revisor_prueba_2)", dos_roles.pedir("/api/admin/usuarios")[0] == 200)
    verificar("NO puede crear roles (ninguno de los dos le da roles.gestionar)", dos_roles.pedir("/api/admin/roles", "POST", {"codigo": "x2", "nombre": "x2"})[0] == 403)

    print("\n[B7] usuarios.sedes es un permiso independiente de usuarios.roles")
    admin.pedir("/api/admin/roles", "POST", {"codigo": "solo_sedes", "nombre": "Solo sedes"})
    estado, r_sedes = admin.pedir("/api/admin/roles")
    rol_solo_sedes = next(r for r in r_sedes if r["codigo"] == "solo_sedes")
    admin.pedir(f"/api/admin/roles/{rol_solo_sedes['id']}/permisos", "PUT", {"permisos": ["usuarios.sedes"]})
    db = SessionLocal()
    u_solo_sedes = _usuario_con_rol(db, "PRUEBA-SOLO-SEDES", "solo_sedes")
    objetivo_id = u_solo_sedes.id
    db.close()
    solo_sedes = Cliente()
    solo_sedes.login("PRUEBA-SOLO-SEDES")
    estado, _ = solo_sedes.pedir(f"/api/admin/usuarios/{objetivo_id}/sedes", "PUT", {"sedes": [sede_1]})
    verificar(f"con SOLO usuarios.sedes, puede asignar sedes: {estado}", estado == 200)
    estado, _ = solo_sedes.pedir(f"/api/admin/usuarios/{objetivo_id}/roles", "PUT", {"roles": []})
    verificar(f"...pero NO puede asignar roles: {estado}", estado == 403)

    print("\n[B8] Reglas anti-bloqueo por HTTP")
    estado, cuerpo = admin.pedir(f"/api/admin/usuarios/{superadmin_id}/estado", "POST", {"estado": "inactivo"})
    verificar(f"el administrador no puede desactivarse a sí mismo: {estado} — {cuerpo.get('detail','')}", estado == 400)

    # Deja a superadmin como el ÚNICO usuario con el rol administrador (los
    # de la Sección A —u_admin1/u_admin2— quedan fuera de esta base HTTP).
    db = SessionLocal()
    otros_admins = db.scalars(
        select(models.Usuario)
        .join(models.UsuarioRol, models.UsuarioRol.usuario_id == models.Usuario.id)
        .join(models.Rol, models.Rol.id == models.UsuarioRol.rol_id)
        .where(
            models.Rol.codigo == "administrador", models.Usuario.id != superadmin_id, models.Usuario.estado == "activo",
        )
    ).all()
    for u in otros_admins:
        db.execute(delete(models.UsuarioRol).where(models.UsuarioRol.usuario_id == u.id))
    db.commit()
    db.close()
    estado, cuerpo = admin.pedir(f"/api/admin/usuarios/{superadmin_id}/roles", "PUT", {"roles": []})
    verificar(f"quitarle el rol al ÚNICO administrador se rechaza: {estado}", estado == 409)

    estado, roles_de_nuevo = admin.pedir(f"/api/admin/usuarios/{superadmin_id}")
    verificar("...y el administrador conserva su rol (se deshizo el cambio)", "administrador" in roles_de_nuevo["roles"])

    estado, _ = admin.pedir(f"/api/admin/roles/{rol_admin_id}", "PATCH", {"activo": False})
    verificar(f"desactivar el rol 'administrador' por HTTP se rechaza: {estado}", estado == 400)
    estado, _ = admin.pedir(f"/api/admin/roles/{rol_admin_id}", "DELETE")
    verificar(f"eliminar el rol 'administrador' por HTTP se rechaza: {estado}", estado == 400)

    print("\n[B9] Las rutas EXISTENTES siguen sin protección")
    anonimo2 = Cliente()
    for ruta in (
        "/api/sedes", "/api/docentes", "/api/estudiantes/pagina?sede_id=1&grado=10",
        "/api/boletines/pendientes?anio_lectivo=2026&periodo=2", "/api/horario/hoy",
        "/api/certificados", "/api/boletines/auditoria-sapred", "/api/reportes/conciliacion",
    ):
        estado, _ = anonimo2.pedir(ruta)
        verificar(f"{ruta} sigue respondiendo 200 SIN sesión", estado == 200)
finally:
    servidor.terminate()
    servidor.wait(timeout=20)
    registro.close()

print("\n[C] Estado final de la copia")
c = sqlite3.connect(COPIA)
print(f"  integrity_check = {c.execute('PRAGMA integrity_check').fetchone()[0]}")
print(f"  journal_mode = {c.execute('PRAGMA journal_mode').fetchone()[0]}")
print(f"  filas huérfanas = {len(c.execute('PRAGMA foreign_key_check').fetchall())}")
c.close()

from app.database import engine  # noqa: E402

engine.dispose()
shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'TODO OK' if not fallos else f'{fallos} FALLOS'}")
sys.exit(1 if fallos else 0)
