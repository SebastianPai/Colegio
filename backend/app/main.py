import base64
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from . import migraciones, operaciones_cliente
from .routers import (
    academico,
    admin,
    alertas,
    asistencia,
    auth,
    certificados,
    diagnostico,
    docente,
    estudiantes,
    fotos,
    horario,
    icfes,
    orientacion,
    promocion,
    sistema,
    reportes,
    sedes,
)

# Tablas, columnas, claves foráneas, índices y datos semilla. Es idempotente:
# seguro en cada arranque (ver migraciones.py).
migraciones.ejecutar()
operaciones_cliente.limpiar_antiguas()

app = FastAPI(title="Sistema Colegio")
# Escrituras reenviadas desde la cola sin conexión: nunca se ejecutan dos
# veces (ver operaciones_cliente.py).
app.add_middleware(operaciones_cliente.OperacionesIdempotentes)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(alertas.router)
app.include_router(promocion.router)
app.include_router(sistema.router)
app.include_router(sedes.router)
app.include_router(estudiantes.router)
app.include_router(asistencia.router)
app.include_router(docente.router)
app.include_router(orientacion.router)
app.include_router(diagnostico.router)
app.include_router(fotos.router)
app.include_router(certificados.router)
app.include_router(academico.router)
app.include_router(horario.router)
app.include_router(reportes.router)
app.include_router(icfes.router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")

    # El ícono de iPhone va DENTRO de la página (data:): al "Agregar a Inicio",
    # iOS no usa el que descarga de un servidor con certificado propio (el del
    # colegio) aunque la página sí cargue, y pone una "I" en su lugar. Se arma
    # en cada petición desde los archivos, así cambiar el logo no exige nada más.
    ICONO_APPLE_LINK = '<link rel="apple-touch-icon" sizes="180x180" href="/static/icons/apple-touch-icon.png?v=2" />'

    def _index_con_icono() -> str:
        html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
        icono = base64.b64encode((FRONTEND_DIR / "static" / "icons" / "apple-touch-icon.png").read_bytes()).decode()
        return html.replace(
            ICONO_APPLE_LINK,
            f'<link rel="apple-touch-icon" sizes="180x180" href="data:image/png;base64,{icono}" />',
        )

    @app.get("/")
    def servir_index():
        # no-cache: el navegador revalida index.html en cada visita, así nunca
        # combina un index.html viejo con scripts nuevos.
        return HTMLResponse(_index_con_icono(), headers={"Cache-Control": "no-cache"})

    # App instalable en el celular ("Agregar a pantalla de inicio") y uso sin
    # conexión. El service worker tiene que servirse desde la raíz para poder
    # controlar toda la app (no solo /static/). Solo funciona por HTTPS
    # (iniciar_https.ps1) o en localhost.
    @app.get("/sw.js")
    def servir_service_worker():
        return FileResponse(
            FRONTEND_DIR / "sw.js",
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
        )

    @app.get("/manifest.webmanifest")
    def servir_manifiesto():
        return FileResponse(
            FRONTEND_DIR / "manifest.webmanifest",
            media_type="application/manifest+json",
            headers={"Cache-Control": "no-cache"},
        )

    # iPhone/iPad buscan el ícono también en la raíz (y algunos navegadores
    # piden /favicon.ico), aparte del <link rel="apple-touch-icon">: si una de
    # esas búsquedas falla, el acceso directo queda sin logo.
    ICONOS = FRONTEND_DIR / "static" / "icons"

    @app.get("/apple-touch-icon.png", include_in_schema=False)
    @app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
    @app.get("/apple-touch-icon-180x180.png", include_in_schema=False)
    def icono_apple():
        return FileResponse(ICONOS / "apple-touch-icon.png", media_type="image/png")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(ICONOS / "icon-192.png", media_type="image/png")

    # Instalador para los computadores de la red (no el servidor): instala el
    # certificado del colegio en Windows (para el usuario actual, sin
    # Administrador) y crea el acceso directo a la dirección segura, que es la
    # única con la que la app funciona sin conexión. Se arma con la misma
    # dirección por la que se descargó, así no hay que escribir la IP.
    @app.get("/instalar-pc.cmd")
    def instalador_pc(request: Request):
        servidor = request.url.hostname or "localhost"
        lineas = [
            "@echo off",
            "chcp 65001 >nul",
            "title Instalar IETABA en este computador",
            f"set SERVIDOR={servidor}",
            "echo.",
            "echo  Instalando IETABA en este computador (servidor: %SERVIDOR%)",
            "echo.",
            'curl -s -f -o "%TEMP%\\ietaba-ca.crt" http://%SERVIDOR%:8000/static/ca.crt',
            "if errorlevel 1 (",
            "  echo  No se pudo descargar el certificado. Revise que este PC este en la red del colegio",
            "  echo  y que el servidor este encendido, y vuelva a intentarlo.",
            "  pause",
            "  exit /b 1",
            ")",
            'echo  1. Certificado del colegio: Windows va a preguntar si confia en "IETABA Local CA". Responda SI.',
            'certutil -user -addstore Root "%TEMP%\\ietaba-ca.crt" >nul',
            "if errorlevel 1 (",
            "  echo  No se instalo el certificado. Vuelva a ejecutar este archivo y responda SI.",
            "  pause",
            "  exit /b 1",
            ")",
            'del "%TEMP%\\ietaba-ca.crt" >nul 2>&1',
            "echo  2. Acceso directo en el escritorio...",
            'for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[Environment]::GetFolderPath(\'Desktop\')"`) do set ESCRITORIO=%%d',
            '(echo [InternetShortcut]& echo URL=https://%SERVIDOR%:8443/) > "%ESCRITORIO%\\IETABA.url"',
            "echo.",
            "echo  Listo. Use siempre el acceso directo IETABA del escritorio (https://%SERVIDOR%:8443).",
            "echo  Para tenerla como programa: en Chrome o Edge, menu ... ^> Instalar IETABA.",
            'echo  Despues, en "Usar sin wifi", descargue lo que necesite antes de quedarse sin conexion.',
            "echo.",
            'start "" https://%SERVIDOR%:8443/',
            "pause",
        ]
        return Response(
            "\r\n".join(lineas) + "\r\n",
            media_type="application/octet-stream",
            headers={"Content-Disposition": 'attachment; filename="instalar_ietaba.cmd"', "Cache-Control": "no-store"},
        )
