"""Pruebas de las operaciones idempotentes (cola sin conexión): una escritura
reenviada con el mismo X-Id-Operacion no se ejecuta dos veces.

Trabaja SIEMPRE sobre una copia temporal de la base: nunca modifica
colegio.db.

    ./venv/Scripts/python.exe probar_operaciones_cliente.py
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
ORIGEN = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND / "colegio.db"
TMP = Path(tempfile.mkdtemp(prefix="ietaba_operaciones_"))
COPIA = TMP / "colegio.db"


def _copiar(origen: Path, destino: Path) -> None:
    src = sqlite3.connect(f"file:{origen}?mode=ro", uri=True)
    dst = sqlite3.connect(destino)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()


_copiar(ORIGEN, COPIA)
os.environ["IETABA_DB_PATH"] = str(COPIA)
sys.path.insert(0, str(BACKEND))

import asyncio  # noqa: E402
import json  # noqa: E402

from fastapi import HTTPException  # noqa: E402

print(f"Copia de prueba: {COPIA}\n")
from app import main  # noqa: E402  (ejecuta migraciones.ejecutar())
from app import models  # noqa: E402
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


# Rutas de prueba (solo existen dentro de este script).
contador = {"sumar": 0, "falla": 0, "sesion": 0}


@main.app.post("/api/prueba-operaciones/sumar")
def _sumar():
    contador["sumar"] += 1
    return {"veces": contador["sumar"]}


@main.app.post("/api/prueba-operaciones/falla")
def _falla():
    contador["falla"] += 1
    if contador["falla"] == 1:
        raise HTTPException(503, "servidor ocupado")
    return {"veces": contador["falla"]}


@main.app.post("/api/prueba-operaciones/sesion")
def _sesion():
    contador["sesion"] += 1
    if contador["sesion"] == 1:
        raise HTTPException(401, "sin sesión")
    return {"veces": contador["sesion"]}


@main.app.post("/api/prueba-operaciones/invalido")
def _invalido():
    raise HTTPException(422, "dato inválido")


class Respuesta:
    def __init__(self, estado, encabezados, cuerpo):
        self.status_code = estado
        self.headers = encabezados
        self.text = cuerpo.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.text)


class Cliente:
    """Llama a la app ASGI directamente (sin httpx ni red)."""

    def _pedir(self, metodo, ruta, headers=None):
        encabezados = {"host": "testserver", **{k.lower(): v for k, v in (headers or {}).items()}}
        servidor, _, puerto = encabezados["host"].partition(":")
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": metodo, "scheme": "http", "path": ruta, "raw_path": ruta.encode(),
            "query_string": b"", "root_path": "",
            "headers": [(k.encode(), v.encode()) for k, v in encabezados.items()],
            "client": ("127.0.0.1", 50000), "server": (servidor, int(puerto or 80)),
        }
        salida = {"estado": None, "encabezados": {}, "cuerpo": b""}

        async def recibir():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def enviar(mensaje):
            if mensaje["type"] == "http.response.start":
                salida["estado"] = mensaje["status"]
                salida["encabezados"] = {k.decode().lower(): v.decode() for k, v in mensaje["headers"]}
            elif mensaje["type"] == "http.response.body":
                salida["cuerpo"] += mensaje.get("body", b"")

        asyncio.run(main.app(scope, recibir, enviar))
        return Respuesta(salida["estado"], salida["encabezados"], salida["cuerpo"])

    def post(self, ruta, headers=None):
        return self._pedir("POST", ruta, headers)

    def get(self, ruta, headers=None):
        return self._pedir("GET", ruta, headers)


cliente = Cliente()
CLAVE = "prueba-0000-aaaa-bbbb-000000000001"

print("[1] Reenvío de la misma operación")
r1 = cliente.post("/api/prueba-operaciones/sumar", headers={"X-Id-Operacion": CLAVE})
r2 = cliente.post("/api/prueba-operaciones/sumar", headers={"X-Id-Operacion": CLAVE})
verificar("la primera se ejecuta", r1.status_code == 200 and r1.json() == {"veces": 1}, r1.text)
verificar("la segunda devuelve la misma respuesta", r2.status_code == 200 and r2.json() == {"veces": 1}, r2.text)
verificar("la segunda va marcada como repetida", r2.headers.get("x-operacion-repetida") == "1")
verificar("el endpoint corrió una sola vez", contador["sumar"] == 1, str(contador))

print("[2] Sin encabezado: todo igual que siempre")
cliente.post("/api/prueba-operaciones/sumar")
cliente.post("/api/prueba-operaciones/sumar")
verificar("se ejecuta cada vez", contador["sumar"] == 3, str(contador))
r = cliente.post("/api/prueba-operaciones/sumar", headers={"X-Id-Operacion": "x"})
verificar("clave inválida se ignora (no se recuerda)", r.json() == {"veces": 4}, r.text)

print("[3] Errores pasajeros no se recuerdan")
c = "prueba-0000-aaaa-bbbb-000000000002"
r1 = cliente.post("/api/prueba-operaciones/falla", headers={"X-Id-Operacion": c})
r2 = cliente.post("/api/prueba-operaciones/falla", headers={"X-Id-Operacion": c})
verificar("5xx: el reintento se ejecuta de verdad", r1.status_code == 503 and r2.status_code == 200, f"{r1.status_code} {r2.status_code}")
c = "prueba-0000-aaaa-bbbb-000000000003"
r1 = cliente.post("/api/prueba-operaciones/sesion", headers={"X-Id-Operacion": c})
r2 = cliente.post("/api/prueba-operaciones/sesion", headers={"X-Id-Operacion": c})
verificar("401: el reintento se ejecuta de verdad", r1.status_code == 401 and r2.status_code == 200, f"{r1.status_code} {r2.status_code}")

print("[4] Rechazos definitivos sí se recuerdan")
c = "prueba-0000-aaaa-bbbb-000000000004"
r1 = cliente.post("/api/prueba-operaciones/invalido", headers={"X-Id-Operacion": c})
r2 = cliente.post("/api/prueba-operaciones/invalido", headers={"X-Id-Operacion": c})
verificar("422 repetido devuelve el mismo error", r1.status_code == r2.status_code == 422 and r2.json() == r1.json(), r2.text)

print("[5] Operación en curso")
c = "prueba-0000-aaaa-bbbb-000000000005"
with SessionLocal() as db:
    db.add(models.OperacionCliente(clave=c, metodo="POST", ruta="/api/prueba-operaciones/sumar"))
    db.commit()
antes = contador["sumar"]
r = cliente.post("/api/prueba-operaciones/sumar", headers={"X-Id-Operacion": c})
verificar("responde 409 en curso sin ejecutar", r.status_code == 409 and r.headers.get("x-operacion-en-curso") == "1" and contador["sumar"] == antes, r.text)

print("[6] Rutas excluidas")
r = cliente.post("/api/auth/logout", headers={"X-Id-Operacion": "prueba-0000-aaaa-bbbb-000000000006"})
with SessionLocal() as db:
    verificar("/api/auth no se recuerda", db.get(models.OperacionCliente, "prueba-0000-aaaa-bbbb-000000000006") is None)

print("[7] Instalador para PC")
r = cliente.get("/instalar-pc.cmd", headers={"Host": "192.168.1.50:8000"})
texto = r.text
verificar("se descarga como .cmd", r.status_code == 200 and "instalar_ietaba.cmd" in r.headers.get("content-disposition", ""))
verificar("trae la IP por la que se pidió", "set SERVIDOR=192.168.1.50" in texto, texto[:200])
verificar("usa finales de línea de Windows", "\r\n" in texto)
verificar("instala la CA sin Administrador", 'certutil -user -addstore Root' in texto)

print()
if fallos:
    print(f"\033[91m{fallos} prueba(s) fallaron.\033[0m")
    sys.exit(1)
print("\033[92mTodo bien.\033[0m")
