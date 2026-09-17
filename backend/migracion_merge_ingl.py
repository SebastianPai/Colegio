"""Fusiona el área 19 (codigo INGL, 'INGL') en el área 6 (codigo LEI,
'Lengua Extranjera Inglés'). SAPRED manda 'INGL' como código solo para
noveno; eso creó un área duplicada y una columna vacía en la grilla.
No hay solapamientos (verificado): la fusión es 1:1.

Backup previo: colegio.db.bak_antes_merge_INGL_*
"""
import sys

from sqlalchemy import func, select, text

from app.database import SessionLocal
from app import models

VIEJA, NUEVA = 19, 6

db = SessionLocal()

area_vieja = db.get(models.Area, VIEJA)
area_nueva = db.get(models.Area, NUEVA)
assert area_vieja and area_vieja.codigo == "INGL", area_vieja
assert area_nueva and area_nueva.codigo == "LEI", area_nueva
print(f"Fusionando #{VIEJA} {area_vieja.codigo!r} -> #{NUEVA} {area_nueva.codigo!r}")

# 1) NotaSapred, TextoBoletin, PendienteBoletin: repuntar area_id (sin choques).
for cls in (models.NotaSapred, models.TextoBoletin, models.PendienteBoletin):
    filas = db.scalars(select(cls).where(cls.area_id == VIEJA)).all()
    for f in filas:
        f.area_id = NUEVA
    print(f"  {cls.__name__}: {len(filas)} fila(s) repuntadas")

# 2) AsignacionDocente: si el mismo grupo/docente ya tiene una del área nueva
#    -> borrar; si no -> repuntar.
for a in db.scalars(select(models.AsignacionDocente).where(models.AsignacionDocente.area_id == VIEJA)).all():
    gemela = db.scalar(
        select(models.AsignacionDocente).where(
            models.AsignacionDocente.docente_id == a.docente_id,
            models.AsignacionDocente.sede_id == a.sede_id,
            models.AsignacionDocente.grado == a.grado,
            models.AsignacionDocente.curso == a.curso,
            models.AsignacionDocente.area_id == NUEVA,
            models.AsignacionDocente.anio_lectivo == a.anio_lectivo,
        )
    )
    if gemela:
        db.delete(a)
        print(f"  AsignacionDocente #{a.id}: borrada (ya existe #{gemela.id} con área {NUEVA})")
    else:
        a.area_id = NUEVA
        print(f"  AsignacionDocente #{a.id}: repuntada a área {NUEVA}")

# 3) AreaGrado: (NUEVA, grado) ya existe -> borrar las del área vieja.
for ag in db.scalars(select(models.AreaGrado).where(models.AreaGrado.area_id == VIEJA)).all():
    ya = db.scalar(select(models.AreaGrado).where(models.AreaGrado.area_id == NUEVA, models.AreaGrado.grado == ag.grado))
    if ya:
        db.delete(ag)
        print(f"  AreaGrado (area {VIEJA}, grado {ag.grado}): borrada (ya existe con área {NUEVA})")
    else:
        ag.area_id = NUEVA
        print(f"  AreaGrado grado {ag.grado}: repuntada a área {NUEVA}")

# 4) BloqueHorario, Reemplazo: por si acaso.
for cls in (models.BloqueHorario, models.Reemplazo):
    filas = db.scalars(select(cls).where(cls.area_id == VIEJA)).all()
    for f in filas:
        f.area_id = NUEVA
    if filas:
        print(f"  {cls.__name__}: {len(filas)} fila(s) repuntadas")

db.flush()

# 5) Escaneo: NINGUNA tabla puede quedar apuntando al área 19.
restos = []
for tabla in db.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).scalars():
    cols = [r[1] for r in db.execute(text(f"PRAGMA table_info('{tabla}')"))]
    if "area_id" in cols:
        n = db.execute(text(f"SELECT COUNT(*) FROM '{tabla}' WHERE area_id = :v"), {"v": VIEJA}).scalar()
        if n:
            restos.append((tabla, n))
if restos:
    db.rollback()
    print("ABORTADO — quedan referencias al área 19:", restos)
    sys.exit(1)

db.delete(area_vieja)
db.commit()
print("OK — área 19 fusionada y eliminada.")

db2 = SessionLocal()
print("¿área 19 existe?", db2.get(models.Area, VIEJA) is not None)
print("NotaSapred área 6:", db2.scalar(select(func.count()).select_from(models.NotaSapred).where(models.NotaSapred.area_id == 6)))
print("TextoBoletin área 6:", db2.scalar(select(func.count()).select_from(models.TextoBoletin).where(models.TextoBoletin.area_id == 6)))
db2.close()
