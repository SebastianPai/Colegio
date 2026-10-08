from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import migraciones
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

app = FastAPI(title="Sistema Colegio")

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

    @app.get("/")
    def servir_index():
        # no-cache: el navegador revalida index.html en cada visita (304 si no
        # cambió), así nunca combina un index.html viejo con scripts nuevos.
        return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-cache"})
