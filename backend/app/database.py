import os
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .texto import sin_tildes

# IETABA_DB_PATH permite apuntar a otra base (p. ej. una copia para pruebas)
# sin tocar colegio.db. Si no está definida, se usa la de siempre.
DB_PATH = Path(os.environ.get("IETABA_DB_PATH") or Path(__file__).resolve().parent.parent / "colegio.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)


@event.listens_for(engine, "connect")
def _configurar_conexion_sqlite(conexion_dbapi, _registro):
    """Se aplica a cada conexión nueva (SQLite no guarda estos ajustes en el
    archivo, salvo journal_mode):
      · busy_timeout: si otra conexión está escribiendo, espera hasta 5 s en
        vez de fallar con "database is locked" (varios usuarios a la vez).
      · journal_mode=WAL: las lecturas no se bloquean mientras alguien
        escribe. Queda guardado en el archivo; repetirlo no cuesta. Si en
        ese instante otra conexión lo impide, se reintenta en la próxima.
      · sin_tildes(): función SQL para búsquedas sin tildes.
      · foreign_keys=ON: SQLite solo valida las claves foráneas si se le
        pide, conexión por conexión."""
    # sin_tildes(): búsquedas que ignoran tildes/ñ/ü (ver texto.py). No se
    # guarda en el archivo: hay que registrarla en cada conexión.
    conexion_dbapi.create_function("sin_tildes", 1, sin_tildes, deterministic=True)
    cursor = conexion_dbapi.cursor()
    cursor.execute("PRAGMA busy_timeout=5000")
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
