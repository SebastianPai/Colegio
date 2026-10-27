"""Operaciones idempotentes para el uso sin conexión.

Cuando un dispositivo guarda algo sin red (asistencia, una observación, un
cambio en la ficha...), la app lo deja en una cola del dispositivo y lo
reenvía al volver la conexión (frontend/static/js/sin_conexion.js). Cada
escritura lleva un encabezado `X-Id-Operacion` (un uuid generado una sola vez
en el dispositivo), y aquí se recuerda la respuesta que dio el servidor:

  · Si la misma operación llega dos veces (p. ej. la primera sí llegó pero la
    respuesta se perdió al caerse el wifi), la segunda NO se vuelve a
    ejecutar: se devuelve la respuesta guardada, con `X-Operacion-Repetida: 1`.
  · Si llega mientras la primera todavía se está procesando: 409 con
    `X-Operacion-En-Curso: 1` (el dispositivo reintenta más tarde).
  · Los errores 5xx y los de sesión/permiso (401, 403, 408, 429) no se
    guardan: la operación se puede reintentar tal cual cuando se arregle.

Es un middleware ASGI puro (no lee el cuerpo de la petición, solo intercepta
la respuesta), así que no cambia nada de los endpoints. Las peticiones sin el
encabezado pasan como siempre.
"""

import datetime as dt
import re

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from . import fechas
from .database import SessionLocal
from .models import OperacionCliente

ENCABEZADO = b"x-id-operacion"
METODOS = {"POST", "PUT", "PATCH", "DELETE"}
CLAVE_VALIDA = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
# Estados que dependen del momento (sesión vencida, permisos, saturación):
# no se recuerdan, para que el reintento se ejecute de verdad.
NO_GUARDAR = {401, 403, 408, 429}
MAX_CUERPO = 1024 * 1024  # respuestas más grandes se recuerdan sin cuerpo
DIAS_A_RECORDAR = 120


def _clave(scope) -> str | None:
    if scope["type"] != "http" or scope["method"] not in METODOS:
        return None
    ruta = scope["path"]
    if not ruta.startswith("/api/") or ruta.startswith("/api/auth/"):
        return None
    for nombre, valor in scope.get("headers", []):
        if nombre == ENCABEZADO:
            clave = valor.decode("latin-1").strip()
            return clave if CLAVE_VALIDA.match(clave) else None
    return None


async def _responder(send, estado: int, cuerpo: bytes, tipo: str | None, extra: list[tuple[bytes, bytes]]):
    encabezados = [(b"content-length", str(len(cuerpo)).encode())] + extra
    if tipo:
        encabezados.append((b"content-type", tipo.encode("latin-1")))
    await send({"type": "http.response.start", "status": estado, "headers": encabezados})
    await send({"type": "http.response.body", "body": cuerpo})


def _reservar(clave: str, metodo: str, ruta: str) -> OperacionCliente | None:
    """Registra la operación como "en curso". Devuelve la fila ya existente
    si esta clave ya se había visto (terminada o en curso)."""
    with SessionLocal() as db:
        previa = db.get(OperacionCliente, clave)
        if previa is not None:
            db.expunge(previa)
            return previa
        db.add(OperacionCliente(clave=clave, metodo=metodo, ruta=ruta[:300]))
        try:
            db.commit()
        except IntegrityError:  # llegó otra copia en el mismo instante
            db.rollback()
            previa = db.get(OperacionCliente, clave)
            if previa is not None:
                db.expunge(previa)
            return previa
    return None


def _terminar(clave: str, estado: int, tipo: str | None, cuerpo: bytes) -> None:
    with SessionLocal() as db:
        fila = db.get(OperacionCliente, clave)
        if fila is None:
            return
        if estado >= 500 or estado in NO_GUARDAR:
            db.delete(fila)  # se podrá reintentar
        else:
            fila.estado_http = estado
            fila.tipo_contenido = (tipo or "")[:100] or None
            fila.cuerpo = cuerpo if len(cuerpo) <= MAX_CUERPO else b""
        db.commit()


def limpiar_antiguas() -> int:
    """Olvida las operaciones de hace más de DIAS_A_RECORDAR días (un
    dispositivo no pasa tanto tiempo sin volver a la red del colegio)."""
    limite = fechas.ahora_utc() - dt.timedelta(days=DIAS_A_RECORDAR)
    with SessionLocal() as db:
        borradas = db.execute(delete(OperacionCliente).where(OperacionCliente.creado < limite)).rowcount
        db.commit()
    return borradas or 0


class OperacionesIdempotentes:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        clave = _clave(scope)
        if clave is None:
            await self.app(scope, receive, send)
            return

        previa = _reservar(clave, scope["method"], scope["path"])
        if previa is not None:
            if previa.estado_http is None:
                await _responder(
                    send, 409,
                    b'{"detail":"Esta operacion todavia se esta procesando. Se reintentara en un momento."}',
                    "application/json", [(b"x-operacion-en-curso", b"1")],
                )
            else:
                await _responder(
                    send, previa.estado_http, previa.cuerpo or b"", previa.tipo_contenido,
                    [(b"x-operacion-repetida", b"1")],
                )
            return

        estado = {"codigo": 500, "tipo": None}
        partes: list[bytes] = []
        tamano = 0

        async def enviar(mensaje):
            nonlocal tamano
            if mensaje["type"] == "http.response.start":
                estado["codigo"] = mensaje["status"]
                for nombre, valor in mensaje.get("headers", []):
                    if nombre.lower() == b"content-type":
                        estado["tipo"] = valor.decode("latin-1")
            elif mensaje["type"] == "http.response.body":
                cuerpo = mensaje.get("body", b"")
                tamano += len(cuerpo)
                if tamano <= MAX_CUERPO:
                    partes.append(cuerpo)
            await send(mensaje)

        try:
            await self.app(scope, receive, enviar)
        except Exception:
            _terminar(clave, 500, None, b"")
            raise
        _terminar(clave, estado["codigo"], estado["tipo"], b"".join(partes) if tamano <= MAX_CUERPO else b"")
