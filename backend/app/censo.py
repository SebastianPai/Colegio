"""Censo indígena del Ministerio del Interior (hoy: resguardo El Gran Sábalo).

Sirve para saber qué estudiantes del colegio pertenecen al resguardo según el
censo oficial: el reporte (Reportes → Censo Gran Sábalo) y el bloque «Censo
del resguardo» en el perfil del estudiante. Lo carga backend/importar_censo.py.

Cómo se une con los estudiantes:
1. por número de documento (lo normal);
2. si no aparece, por nombre completo sin tildes, y SOLO cuando hay una única
   coincidencia en cada lado (vinculo = "nombre"): un nombre repetido queda
   sin vincular antes que vincularse mal, y la pantalla pide verificarlo.
"""

import datetime as dt
import re
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from . import fechas, models
from .texto import sin_tildes

RESGUARDO_GRAN_SABALO = "EL GRAN SÁBALO"

# Códigos del "DICCIONARIO DE VARIABLES" del mismo Excel (formato AN-AI-P7-F1).
TIPOS_DOCUMENTO = {1: "Registro civil", 2: "Tarjeta de identidad", 3: "Cédula de ciudadanía", 4: "No tiene documento"}
SEXOS = {1: "M", 2: "F"}
PARENTESCOS = {
    1: "Padre", 2: "Madre", 3: "Cónyuge", 4: "Hermano(a)", 5: "Cabeza de familia", 6: "Esposa", 7: "Hijo(a)",
    8: "Yerno", 9: "Nuera", 10: "Suegro(a)", 11: "Sobrino(a)", 12: "Cuñado(a)", 13: "Tío(a)", 14: "Abuelo(a)",
    15: "Otro no pariente",
}
ESCOLARIDADES = {
    1: "Básica primaria", 2: "Básica secundaria", 3: "Media", 4: "Técnico", 5: "Tecnológico", 6: "Universitario",
    7: "Especialización", 8: "Maestría", 9: "Doctorado", 10: "Ninguno", 11: "No aplica",
}
ESTADOS_CIVILES = {
    1: "Unión libre", 2: "Casado(a)", 3: "Divorciado(a)", 4: "Viudo(a)", 5: "Soltero(a)", 6: "Separado(a)",
    7: "No informa", 8: "No aplica",
}

# Rangos de edad del reporte (edad cumplida a hoy).
RANGOS_EDAD = [
    ("0 a 4 años", 0, 4), ("5 a 6 años", 5, 6), ("7 a 10 años", 7, 10), ("11 a 14 años", 11, 14),
    ("15 a 17 años", 15, 17), ("18 a 20 años", 18, 20), ("21 años o más", 21, 200),
]
EDAD_ESCOLAR = (5, 17)  # Transición a Once, edades típicas


# --- Lectura del Excel ---------------------------------------------------------


def _clave(texto) -> str:
    return " ".join(sin_tildes(str(texto or "")).upper().split())


def _texto(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = " ".join(str(v).split())
    return s or None


def normalizar_documento(v) -> str | None:
    s = _texto(v)
    if not s:
        return None
    s = re.sub(r"[^0-9A-Za-z]", "", s.removesuffix(".0")).upper()
    return s or None


def _codigo(v) -> int | None:
    m = re.match(r"\s*(\d+)", str(v if v is not None else ""))
    return int(m.group(1)) if m else None


def _fecha(v) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = _texto(v)
    if not s:
        return None
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(s, formato).date()
        except ValueError:
            pass
    return None


# Encabezado del Excel (sin tildes, mayúsculas) → campo.
COLUMNAS = {
    "VIGENCIA": "vigencia",
    "NOMBRE DEL RESGUARDO INDIGENA": "resguardo",
    "COMUNIDAD": "comunidad",
    "NUMERO DE VIVIENDA": "numero_vivienda",
    "FAMILIA": "familia",
    "PRIMER NOMBRE": "primer_nombre",
    "SEGUNDO NOMBRE": "segundo_nombre",
    "PRIMER APELLIDO": "primer_apellido",
    "SEGUNDO APELLIDO": "segundo_apellido",
    "PARENTESCO": "parentesco",
    "TIPO IDENTIFICACION": "tipo_documento",
    "NUMERO DOCUMENTO": "documento",
    "SEXO": "sexo",
    "FECHA NACIMIENTO": "fecha_nacimiento",
    "ESCOLARIDAD": "escolaridad",
    "ESTADOCIVIL": "estado_civil",
    "TELEFONO": "telefono",
}


def leer_excel(ruta: Path) -> list[dict]:
    """Personas de la hoja del listado censal (FORMATO_CENSOS). Las hojas de
    fallecidos y retiro voluntario NO se cargan: ya no son del censo."""
    import openpyxl

    libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    hoja = libro["FORMATO_CENSOS"] if "FORMATO_CENSOS" in libro.sheetnames else libro.worksheets[0]
    filas = hoja.iter_rows(values_only=True)
    indices = None
    for fila in filas:
        claves = [_clave(c) for c in fila]
        if "NUMERO DOCUMENTO" in claves and "PRIMER NOMBRE" in claves:
            indices = {campo: claves.index(enc) for enc, campo in COLUMNAS.items() if enc in claves}
            break
    if indices is None:
        raise ValueError("No se encontró el encabezado del listado censal (NUMERO DOCUMENTO, PRIMER NOMBRE...).")

    personas = []
    for fila in filas:
        val = {campo: (fila[i] if i < len(fila) else None) for campo, i in indices.items()}
        if not (val.get("documento") or val.get("primer_nombre") or val.get("primer_apellido")):
            continue
        personas.append({
            "vigencia": _codigo(val.get("vigencia")),
            "resguardo": _texto(val.get("resguardo")) or RESGUARDO_GRAN_SABALO,
            "comunidad": _texto(val.get("comunidad")),
            "numero_vivienda": _texto(val.get("numero_vivienda")),
            "familia": _texto(val.get("familia")),
            "primer_nombre": _texto(val.get("primer_nombre")),
            "segundo_nombre": _texto(val.get("segundo_nombre")),
            "primer_apellido": _texto(val.get("primer_apellido")),
            "segundo_apellido": _texto(val.get("segundo_apellido")),
            "parentesco": PARENTESCOS.get(_codigo(val.get("parentesco"))),
            "tipo_documento": TIPOS_DOCUMENTO.get(_codigo(val.get("tipo_documento"))),
            "documento": normalizar_documento(val.get("documento")),
            "sexo": SEXOS.get(_codigo(val.get("sexo"))),
            "fecha_nacimiento": _fecha(val.get("fecha_nacimiento")),
            "escolaridad": ESCOLARIDADES.get(_codigo(val.get("escolaridad"))),
            "estado_civil": ESTADOS_CIVILES.get(_codigo(val.get("estado_civil"))),
            "telefono": _texto(val.get("telefono")),
        })
    return personas


# --- Importación y vínculo -----------------------------------------------------


def importar(db: Session, personas: list[dict]) -> dict:
    """Reemplaza el censo de cada resguardo que venga en `personas`."""
    resguardos = {p["resguardo"] for p in personas}
    for r in resguardos:
        db.execute(delete(models.PersonaCenso).where(models.PersonaCenso.resguardo == r))
    db.add_all(models.PersonaCenso(**p) for p in personas)
    db.flush()
    resultado = vincular_estudiantes(db)
    db.commit()
    return {"personas": len(personas), "resguardos": sorted(resguardos), **resultado}


def _nombre_estudiante(e: models.Estudiante) -> str:
    return _clave(e.nombre_completo)


def vincular_estudiantes(db: Session) -> dict:
    estudiantes = list(db.scalars(select(models.Estudiante)))
    por_documento = {normalizar_documento(e.documento): e.id for e in estudiantes if normalizar_documento(e.documento)}
    por_nombre = defaultdict(list)
    for e in estudiantes:
        por_nombre[_nombre_estudiante(e)].append(e.id)

    personas = list(db.scalars(select(models.PersonaCenso)))
    nombres_censo = Counter(_clave(p.nombre_completo) for p in personas)
    nombre_de = {e.id: _nombre_estudiante(e) for e in estudiantes}
    usados = set()
    n_doc = n_nombre = 0
    # El censo trae algunos documentos repetidos (dos personas con el mismo
    # número): a cada estudiante se le une UNA sola fila, la de su mismo nombre
    # si la hay, para no contarlo dos veces.
    candidatos = defaultdict(list)
    for p in personas:
        p.estudiante_id, p.vinculo = None, None
        eid = por_documento.get(p.documento) if p.documento else None
        if eid is not None:
            candidatos[eid].append(p)
    for eid, filas in candidatos.items():
        p = next((f for f in filas if _clave(f.nombre_completo) == nombre_de[eid]), filas[0])
        p.estudiante_id, p.vinculo = eid, "documento"
        usados.add(eid)
        n_doc += 1
    for p in personas:
        if p.estudiante_id is not None:
            continue
        nombre = _clave(p.nombre_completo)
        ids = por_nombre.get(nombre, [])
        if nombre and len(ids) == 1 and nombres_censo[nombre] == 1 and ids[0] not in usados:
            p.estudiante_id, p.vinculo = ids[0], "nombre"
            usados.add(ids[0])
            n_nombre += 1
    return {"vinculados_documento": n_doc, "vinculados_nombre": n_nombre}


# --- Consultas -----------------------------------------------------------------


def edad(fecha: dt.date | None, hoy: dt.date) -> int | None:
    if not fecha:
        return None
    return hoy.year - fecha.year - ((hoy.month, hoy.day) < (fecha.month, fecha.day))


def _rango(e: int | None) -> str:
    if e is None:
        return "Sin fecha de nacimiento"
    return next((n for n, a, b in RANGOS_EDAD if a <= e <= b), "Sin fecha de nacimiento")


def _conteo(filas: list[dict], clave, orden=None) -> list[dict]:
    grupos = defaultdict(lambda: {"total": 0, "hombres": 0, "mujeres": 0})
    for f in filas:
        g = grupos[clave(f)]
        g["total"] += 1
        g["hombres"] += f["genero"] == "M"
        g["mujeres"] += f["genero"] == "F"
    llaves = orden if orden is not None else sorted(grupos, key=lambda k: (-grupos[k]["total"], str(k)))
    return [{"nombre": k, **grupos[k]} for k in llaves if k in grupos]


def resguardos_cargados(db: Session) -> list[str]:
    return list(db.scalars(select(models.PersonaCenso.resguardo).distinct().order_by(models.PersonaCenso.resguardo)))


def es_sede_principal(sede: models.Sede | None) -> bool:
    """«SEDE # 01  I.E.T.A.B.A.»: para el usuario «solo IETABA» en este
    reporte es SOLO la sede principal, no las sedes rurales marcadas IETABA."""
    return bool(sede) and "IETABA" in sede.nombre.upper().replace(".", "").replace(" ", "")


def _cuenta(e: models.Estudiante, solo_ietaba: bool) -> bool:
    # Los «Nuevo · pendiente SIMAT» no salen en el reporte (ni en el total del
    # colegio) hasta que se confirme que ya están en SIMAT.
    return (e.activo and not e.pendiente_simat
            and (not solo_ietaba or es_sede_principal(e.sede)))


def reporte(db: Session, resguardo: str | None = None, solo_ietaba: bool = False) -> dict:
    """Estudiantes ACTIVOS que están en el censo del resguardo. solo_ietaba =
    solo la sede principal I.E.T.A.B.A.; si no, todas las sedes del sistema."""
    hoy = fechas.hoy_colombia()
    cargados = resguardos_cargados(db)
    if resguardo is None:
        resguardo = cargados[0] if cargados else RESGUARDO_GRAN_SABALO
    personas = list(db.scalars(
        select(models.PersonaCenso).where(models.PersonaCenso.resguardo == resguardo)
        .options(selectinload(models.PersonaCenso.estudiante).selectinload(models.Estudiante.sede))
    ))
    if not personas:
        return {"cargado": False, "resguardo": resguardo, "resguardos": cargados}

    total_activos = sum(1 for e in db.scalars(
        select(models.Estudiante).where(models.Estudiante.estado == "ACTIVO")
        .options(selectinload(models.Estudiante.sede))
    ) if _cuenta(e, solo_ietaba))

    estudiantes = []
    for p in personas:
        e = p.estudiante
        if e is None or not _cuenta(e, solo_ietaba):
            continue
        nac = e.fecha_nacimiento or p.fecha_nacimiento
        anios = edad(nac, hoy)
        estudiantes.append({
            "id": e.id,
            "nombre": e.nombre_completo,
            "documento": e.documento,
            "grado": e.grado,
            "curso": e.curso,
            "grupo": e.grupo,
            "sede": e.sede.nombre if e.sede else None,
            "genero": e.genero or p.sexo,
            "edad": anios,
            "comunidad": p.comunidad,
            "familia": p.familia,
            "parentesco": p.parentesco,
            "vinculo": p.vinculo,
            "fecha_distinta": bool(e.fecha_nacimiento and p.fecha_nacimiento and e.fecha_nacimiento != p.fecha_nacimiento),
            "posible_retirado": e.posible_retirado,
            "ietaba": es_sede_principal(e.sede),
        })
    estudiantes.sort(key=lambda x: (x["grado"], x["curso"] or 0, x["nombre"]))
    # Cuadro fijo «solo IETABA» (sale igual con o sin el filtro de sedes).
    de_ietaba = [x for x in estudiantes if x["ietaba"]]

    edades = [x["edad"] for x in estudiantes if x["edad"] is not None]

    # Personas del censo en edad escolar que NO están en el colegio (ni como
    # retirados): posibles niños sin matricular o estudiando en otra parte.
    fuera = []
    for p in personas:
        anios = edad(p.fecha_nacimiento, hoy)
        if p.estudiante_id is None and anios is not None and EDAD_ESCOLAR[0] <= anios <= EDAD_ESCOLAR[1]:
            fuera.append({"genero": p.sexo, "edad": anios, "comunidad": p.comunidad or "Sin comunidad"})

    orden_rangos = [n for n, _, _ in RANGOS_EDAD] + ["Sin fecha de nacimiento"]
    return {
        "cargado": True,
        "solo_ietaba": solo_ietaba,
        "resguardo": resguardo,
        "resguardos": cargados,
        "vigencia": max((p.vigencia for p in personas if p.vigencia), default=None),
        "importado_en": max(p.importado_en for p in personas),
        "censo": {
            "personas": len(personas),
            "familias": len({(p.comunidad, p.familia) for p in personas if p.familia}),
            "comunidades": len({p.comunidad for p in personas if p.comunidad}),
            "hombres": sum(p.sexo == "M" for p in personas),
            "mujeres": sum(p.sexo == "F" for p in personas),
            "en_edad_escolar": sum(1 for p in personas if (a := edad(p.fecha_nacimiento, hoy)) is not None
                                   and EDAD_ESCOLAR[0] <= a <= EDAD_ESCOLAR[1]),
        },
        "estudiantes_resumen": {
            "total": len(estudiantes),
            "hombres": sum(x["genero"] == "M" for x in estudiantes),
            "mujeres": sum(x["genero"] == "F" for x in estudiantes),
            "pct_del_colegio": round(100 * len(estudiantes) / total_activos, 1) if total_activos else None,
            "total_activos_colegio": total_activos,
            "edad_promedio": round(sum(edades) / len(edades), 1) if edades else None,
            "edad_min": min(edades, default=None),
            "edad_max": max(edades, default=None),
            "por_nombre": sum(x["vinculo"] == "nombre" for x in estudiantes),
            "fecha_distinta": sum(x["fecha_distinta"] for x in estudiantes),
        },
        "por_rango_edad": _conteo(estudiantes, lambda x: _rango(x["edad"]), orden_rangos),
        "por_edad": _conteo(estudiantes, lambda x: x["edad"] if x["edad"] is not None else "Sin dato",
                            sorted({x["edad"] for x in estudiantes if x["edad"] is not None}) + ["Sin dato"]),
        "por_grado": [
            {**g, "nombre": models.GRADOS_NOMBRES.get(g["nombre"], str(g["nombre"]))}
            for g in _conteo(estudiantes, lambda x: x["grado"], list(range(0, 12)))
        ],
        "por_sede": _conteo(estudiantes, lambda x: x["sede"] or "Sin sede"),
        "por_comunidad": _conteo(estudiantes, lambda x: x["comunidad"] or "Sin comunidad"),
        "ietaba": {
            "total": len(de_ietaba),
            "hombres": sum(x["genero"] == "M" for x in de_ietaba),
            "mujeres": sum(x["genero"] == "F" for x in de_ietaba),
            "por_comunidad": _conteo(de_ietaba, lambda x: x["comunidad"] or "Sin comunidad"),
        },
        "fuera_del_colegio": {
            "total": len(fuera),
            "hombres": sum(x["genero"] == "M" for x in fuera),
            "mujeres": sum(x["genero"] == "F" for x in fuera),
            "por_comunidad": _conteo(fuera, lambda x: x["comunidad"]),
            "por_edad": _conteo(fuera, lambda x: x["edad"], list(range(EDAD_ESCOLAR[0], EDAD_ESCOLAR[1] + 1))),
        },
        "estudiantes": estudiantes,
    }


def del_estudiante(db: Session, estudiante_id: int) -> dict:
    """Lo que dice el censo de un estudiante, con su núcleo familiar (y quiénes
    de su familia también estudian aquí). `en_censo` False si no aparece."""
    hoy = fechas.hoy_colombia()
    p = db.scalar(select(models.PersonaCenso).where(models.PersonaCenso.estudiante_id == estudiante_id))
    if p is None:
        hay_censo = db.scalar(select(models.PersonaCenso.id).limit(1)) is not None
        return {"en_censo": False, "censo_cargado": hay_censo}
    familia = []
    if p.familia:
        miembros = db.scalars(
            select(models.PersonaCenso)
            .where(models.PersonaCenso.resguardo == p.resguardo, models.PersonaCenso.comunidad == p.comunidad,
                   models.PersonaCenso.familia == p.familia, models.PersonaCenso.id != p.id)
            .options(selectinload(models.PersonaCenso.estudiante))
        )
        for m in miembros:
            familia.append({
                "nombre": m.nombre_completo,
                "parentesco": m.parentesco,
                "edad": edad(m.fecha_nacimiento, hoy),
                "documento": m.documento,
                "estudiante_id": m.estudiante_id,
                "grupo": m.estudiante.grupo if m.estudiante else None,
            })
        familia.sort(key=lambda m: -(m["edad"] or 0))
    return {
        "en_censo": True,
        "resguardo": p.resguardo,
        "vigencia": p.vigencia,
        "comunidad": p.comunidad,
        "familia": p.familia,
        "numero_vivienda": p.numero_vivienda,
        "parentesco": p.parentesco,
        "tipo_documento": p.tipo_documento,
        "documento": p.documento,
        "nombre": p.nombre_completo,
        "fecha_nacimiento": p.fecha_nacimiento,
        "escolaridad": p.escolaridad,
        "telefono": p.telefono,
        "vinculo": p.vinculo,
        "nucleo_familiar": familia,
    }
