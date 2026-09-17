"""Solo pone nombre legible a las áreas de SAPRED que quedaron con
nombre == código. NO fusiona nada, NO mueve notas: cambia el texto que se
muestra en la grilla / boletines. Reversible.

DIDA: código de preescolar sin nombre conocido; se asume "Dimensión
Corporal" por ser la 4ª dimensión que falta frente a COG/COM/CORP/SOAF.
Si el colegio dice otra cosa, es solo cambiar este texto.
"""
from sqlalchemy import select

from app.database import SessionLocal
from app import models

NOMBRES = {
    "FILO": "Filosofía",
    "INV": "Investigación",
    "LI": "Legislación Indígena",
    "TECIN": "Tecnología e Informática",
    "CINA": "Ciencias Naturales",
    "COG": "Dimensión Cognitiva",
    "COM": "Dimensión Comunicativa",
    "CORP": "Dimensión Corporal",
    "SOAF": "Dimensión Socioafectiva",
    "DICOG": "Dimensión Cognitiva",
    "DICO": "Dimensión Comunicativa",
    "DISO": "Dimensión Socioafectiva",
    "DIDA": "Dimensión Corporal",
}

db = SessionLocal()
for a in db.scalars(select(models.Area)).all():
    nuevo = NOMBRES.get(a.codigo)
    if nuevo and a.nombre != nuevo:
        print(f"  {a.codigo:6} {a.nombre!r} -> {nuevo!r}")
        a.nombre = nuevo
db.commit()
print("OK")
db.close()
