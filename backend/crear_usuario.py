"""Crea y administra los usuarios del sistema desde el PC servidor.

No hay ninguna pantalla ni endpoint para crear usuarios (eso llega con la
consola de administración, cuando existan los roles): por ahora se hace aquí,
a mano, en el equipo donde vive la base. La contraseña se escribe por teclado
(no queda en el historial de comandos) o se genera una temporal que se muestra
una sola vez y debe cambiarse en el primer ingreso.

Ejemplos:
    # Usuario para una persona administrativa (pide la clave por teclado)
    ./venv/Scripts/python.exe crear_usuario.py crear --documento 1087654321 --nombre "Ana Pai"

    # Usuario para un docente que YA existe en la tabla docentes, con clave temporal
    ./venv/Scripts/python.exe crear_usuario.py crear --documento 1000000000 \
        --nombre "Ejemplo Docente" --docente-documento 1000000000 --clave-temporal

    ./venv/Scripts/python.exe crear_usuario.py listar
    ./venv/Scripts/python.exe crear_usuario.py clave --documento 1087654321 --clave-temporal
    ./venv/Scripts/python.exe crear_usuario.py estado --documento 1087654321 --valor inactivo

    # Roles (Fase 3): crear con un rol de una vez, o asignar/quitar después
    ./venv/Scripts/python.exe crear_usuario.py crear --documento 1087654321 --nombre "Ana Pai" --rol administrador
    ./venv/Scripts/python.exe crear_usuario.py roles --documento 1087654321
    ./venv/Scripts/python.exe crear_usuario.py roles --documento 1087654321 --asignar coordinador
    ./venv/Scripts/python.exe crear_usuario.py roles --documento 1087654321 --quitar coordinador
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select  # noqa: E402

from app import auth, models, permisos, rbac, rbac_admin  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.seguridad import clave_temporal  # noqa: E402


def _pedir_clave(documento: str) -> str:
    while True:
        clave = getpass.getpass("Contraseña nueva: ")
        if clave != getpass.getpass("Repite la contraseña: "):
            print("No coinciden, intenta de nuevo.")
            continue
        from app.seguridad import problema_con_la_clave

        problema = problema_con_la_clave(clave, documento)
        if problema:
            print(problema)
            continue
        return clave


def _resolver_docente(db, args) -> int | None:
    if args.docente_id:
        return args.docente_id
    if args.docente_documento:
        docente = db.scalar(
            select(models.Docente).where(models.Docente.documento == args.docente_documento.strip())
        )
        if docente is None:
            sys.exit(f"No existe un docente con documento {args.docente_documento}.")
        print(f"Se enlazara con el docente #{docente.id} {docente.nombre_completo}")
        return docente.id
    return None


def comando_crear(db, args) -> None:
    docente_id = _resolver_docente(db, args)
    if args.clave_temporal:
        clave = clave_temporal()
    else:
        clave = _pedir_clave(args.documento)
    usuario = auth.registrar_usuario(
        db,
        documento=args.documento,
        nombre=args.nombre,
        clave=clave,
        email=args.email,
        docente_id=docente_id,
        debe_cambiar_clave=True if args.clave_temporal else not args.sin_cambio_obligatorio,
    )
    print(f"\nUsuario creado: #{usuario.id} {usuario.documento} — {usuario.nombre}")
    if usuario.docente_id:
        print(f"Enlazado al docente #{usuario.docente_id}")
    if args.clave_temporal:
        print(f"\n  CONTRASENA TEMPORAL: {clave}")
        print("  Entregala en persona. Se le pedira cambiarla al ingresar.")
        print("  No queda guardada en ninguna parte: si se pierde, se genera otra.\n")
    if usuario.debe_cambiar_clave:
        print("Debera cambiar la contrasena en el primer ingreso.")
    if args.rol:
        try:
            asignados = rbac_admin.establecer_roles_usuario(db, usuario, args.rol, asignado_por_id=None)
            print(f"Rol(es) asignado(s): {', '.join(asignados)}")
        except rbac_admin.ErrorRBAC as e:
            print(f"\nEl usuario se creo, pero NO se pudo asignar el rol: {e.mensaje}")
        except rbac.ErrorBloqueoAdministrativo as e:
            print(f"\nEl usuario se creo, pero NO se pudo asignar el rol: {e}")
            print("(el sistema quedaria sin ningun administrador activo; revisa con 'crear_usuario.py roles')")


def comando_listar(db, _args) -> None:
    usuarios = db.scalars(select(models.Usuario).order_by(models.Usuario.id)).all()
    if not usuarios:
        print("Todavia no hay usuarios.")
        return
    print(f"{'id':>4}  {'documento':<15} {'estado':<10} {'docente':<8} {'ultimo acceso':<20} {'roles':<28} nombre")
    for u in usuarios:
        sesiones = len(auth.listar_sesiones(db, u.id))
        ultimo = u.ultimo_acceso.strftime("%Y-%m-%d %H:%M") if u.ultimo_acceso else "nunca"
        roles = ",".join(r.codigo for r in rbac.roles_del_usuario(db, u.id)) or "-"
        print(
            f"{u.id:>4}  {u.documento:<15} {u.estado:<10} "
            f"{(str(u.docente_id) if u.docente_id else '-'):<8} {ultimo:<20} {roles:<28} {u.nombre}"
            + (f"   ({sesiones} sesion/es abiertas)" if sesiones else "")
        )


def _usuario_o_salir(db, documento: str) -> models.Usuario:
    usuario = auth.buscar_usuario(db, documento)
    if usuario is None:
        sys.exit(f"No existe un usuario con documento o correo {documento}.")
    return usuario


def comando_clave(db, args) -> None:
    usuario = _usuario_o_salir(db, args.documento)
    clave = clave_temporal() if args.clave_temporal else _pedir_clave(usuario.documento)
    auth.establecer_clave(db, usuario, clave, exigir_cambio=True)
    print(f"Contrasena restablecida para {usuario.documento}. Se cerraron sus sesiones abiertas.")
    if args.clave_temporal:
        print(f"\n  CONTRASENA TEMPORAL: {clave}\n")


def comando_estado(db, args) -> None:
    usuario = _usuario_o_salir(db, args.documento)
    auth.cambiar_estado(db, usuario, args.valor)
    print(f"{usuario.documento} quedo en estado '{args.valor}'.")


def comando_roles(db, args) -> None:
    """Sin --asignar ni --quitar, solo muestra los roles actuales. Cada uno
    se aplica sobre la lista ACTUAL (no reemplaza toda la lista de una)."""
    usuario = _usuario_o_salir(db, args.documento)
    actuales = {r.codigo for r in rbac.roles_del_usuario(db, usuario.id)}
    nuevos = (actuales | set(args.asignar or [])) - set(args.quitar or [])
    if nuevos != actuales:
        rbac_admin.establecer_roles_usuario(db, usuario, sorted(nuevos), asignado_por_id=None)
    print(f"Roles de {usuario.documento}: {', '.join(sorted(nuevos)) or '(ninguno)'}")


ROLES_DISPONIBLES = [r.codigo for r in permisos.ROLES_SISTEMA]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)

    crear = sub.add_parser("crear", help="crea un usuario")
    crear.add_argument("--documento", required=True)
    crear.add_argument("--nombre", required=True)
    crear.add_argument("--email")
    crear.add_argument("--docente-id", type=int, help="id de un Docente existente")
    crear.add_argument("--docente-documento", help="documento de un Docente existente")
    crear.add_argument("--clave-temporal", action="store_true", help="genera una clave temporal y la muestra")
    crear.add_argument("--sin-cambio-obligatorio", action="store_true", help="no exigir cambio en el primer ingreso")
    crear.add_argument(
        "--rol", action="append", default=[],
        help=f"código de rol a asignar (repetible). Roles del sistema: {', '.join(ROLES_DISPONIBLES)}",
    )

    sub.add_parser("listar", help="lista los usuarios (con sus roles)")

    clave = sub.add_parser("clave", help="restablece la contrasena de un usuario")
    clave.add_argument("--documento", required=True)
    clave.add_argument("--clave-temporal", action="store_true")

    estado = sub.add_parser("estado", help="activa o desactiva un usuario")
    estado.add_argument("--documento", required=True)
    estado.add_argument("--valor", required=True, choices=["activo", "inactivo", "bloqueado"])

    roles = sub.add_parser("roles", help="ver o cambiar los roles de un usuario existente")
    roles.add_argument("--documento", required=True)
    roles.add_argument("--asignar", action="append", default=[], help="código de rol a agregar (repetible)")
    roles.add_argument("--quitar", action="append", default=[], help="código de rol a quitar (repetible)")

    args = parser.parse_args()
    db = SessionLocal()
    try:
        {
            "crear": comando_crear, "listar": comando_listar, "clave": comando_clave,
            "estado": comando_estado, "roles": comando_roles,
        }[args.comando](db, args)
    except (auth.ErrorAutenticacion, rbac_admin.ErrorRBAC) as e:
        sys.exit(f"Error: {e.mensaje}")
    except rbac.ErrorBloqueoAdministrativo as e:
        sys.exit(f"Error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
