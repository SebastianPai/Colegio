"""Identidad de servicio para los procesos internos de SAPRED (Fase 4.1).

Completamente separada de la identidad humana (auth.py / rbac.py): no hay
Usuario, no hay roles, no hay permisos — ni tabla ni fila en la base. Es una
credencial de un solo nivel ("es la maquinaria interna de SAPRED" o no lo
es) para un puñado CERRADO de endpoints que los scripts Node/Playwright
llaman sin sesión de navegador (no pueden tenerla: no son un navegador).

`exigir_token_servicio` se cuelga EXPLÍCITAMENTE, uno por uno, solo de esos
endpoints (ver routers/academico.py y routers/estudiantes.py) — nunca de
forma genérica ("cualquier ruta con este header pasa"), y nunca junto con
`rbac.requiere(...)` en el mismo endpoint: una ruta es humana o es de
servicio, nunca las dos a la vez. Así ni una sesión humana (por privilegiada
que sea) sirve aquí, ni el token de servicio sirve en ninguna ruta humana.

Dos barreras, en este orden (la del origen es gratis: no toca el secreto):
  1. la petición debe venir de loopback (127.0.0.1 / ::1) — el servidor
     corre en 0.0.0.0, alcanzable desde toda la red del colegio, así que
     esto NO es redundante;
  2. el header debe traer el token correcto, comparado en tiempo constante.

Ambos fallos devuelven el mismo 403 genérico: no hay pistas sobre cuál de
los dos falló, ni el valor recibido se refleja en ninguna parte.
"""

from fastapi import HTTPException, Request

from . import seguridad

ORIGENES_LOOPBACK = {"127.0.0.1", "::1"}


def exigir_token_servicio(request: Request) -> None:
    origen = request.client.host if request.client else ""
    if origen not in ORIGENES_LOOPBACK:
        raise HTTPException(status_code=403, detail="Acceso restringido.")

    recibido = request.headers.get(seguridad.CABECERA_TOKEN_SERVICIO, "")
    if not seguridad.verificar_token_servicio(recibido):
        raise HTTPException(status_code=403, detail="Acceso restringido.")
