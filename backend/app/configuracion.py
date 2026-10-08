"""Parámetros generales del sistema (tabla configuracion_sistema).

Módulo de Orientación activable: el administrador lo apaga, por ejemplo,
mientras empieza otro año y todavía no hay diagnósticos ni casos, y lo
vuelve a prender después. Apagado NO borra nada: solo oculta el menú y
cierra las rutas de /api/orientacion y /api/diagnosticos (exigir_orientacion_activa),
y los docentes dejan de poder enviar "Remisión a psicología" (nadie la vería)."""

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from . import fechas, models
from .database import get_db

ORIENTACION_ACTIVA = "modulo_orientacion_activo"
MENSAJE_ORIENTACION_APAGADA = (
    "El módulo de Orientación está desactivado. El administrador puede activarlo en Configuración."
)


def obtener_bool(db: Session, clave: str, por_defecto: bool) -> bool:
    fila = db.get(models.ConfiguracionSistema, clave)
    return por_defecto if fila is None else fila.valor == "1"


def guardar_bool(db: Session, clave: str, valor: bool, usuario_id: int) -> models.ConfiguracionSistema:
    fila = db.get(models.ConfiguracionSistema, clave)
    if fila is None:
        fila = models.ConfiguracionSistema(clave=clave, valor="1" if valor else "0")
        db.add(fila)
    fila.valor = "1" if valor else "0"
    fila.actualizado_por_id = usuario_id
    fila.actualizado_en = fechas.ahora_utc()
    db.commit()
    db.refresh(fila)
    return fila


def orientacion_activa(db: Session) -> bool:
    return obtener_bool(db, ORIENTACION_ACTIVA, True)


def exigir_orientacion_activa(db: Session = Depends(get_db)) -> None:
    """Dependencia a nivel de router: 423 si el módulo está apagado."""
    if not orientacion_activa(db):
        raise HTTPException(status_code=423, detail=MENSAJE_ORIENTACION_APAGADA)
