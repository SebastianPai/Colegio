"""Lógica del módulo Horarios: consulta de la rejilla semanal, cálculo de
disponibilidad real ("¿quién está libre ahora?"), panel del día, ausencias y
reemplazos con candidatos puntuados de forma transparente.

No inventa datos: todo se apoya en BloqueHorario (importado del Word oficial)
y en los registros ya existentes (Docente, Sede, Area, y la convención de
grupo grado+curso de Estudiante/AsignacionDocente).
"""

import datetime as dt
import difflib
import json
import re
import unicodedata

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from . import fechas, models, schemas

# --- Franjas y días (la fuente es jornada única de mañana, 6 horas iguales) --

FRANJAS = [
    {"hora": 1, "inicio": "07:30", "fin": "08:25"},
    {"hora": 2, "inicio": "08:25", "fin": "09:20"},
    {"hora": 3, "inicio": "09:20", "fin": "10:15"},
    {"hora": 4, "inicio": "11:00", "fin": "11:50"},
    {"hora": 5, "inicio": "11:50", "fin": "12:40"},
    {"hora": 6, "inicio": "12:40", "fin": "13:30"},
]
DESCANSO = {"inicio": "10:15", "fin": "11:00"}
JORNADA = "mañana"
SEDE_HORARIO_ID = 1  # SEDE # 01 I.E.T.A.B.A. — el Word es solo de esta sede

DIAS_NOMBRES = {1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves", 5: "Viernes"}
DIAS_ABREV = {1: "Lu", 2: "Ma", 3: "Mi", 4: "Ju", 5: "Vi"}

# rótulo del Word (normalizado) -> código de un Area ya existente en el catálogo
# Casos fonéticos que el emparejador difuso no alcanza (nombre del Word
# normalizado -> nombre_completo exacto del Docente ya existente). Se revisó
# uno por uno: mismo apellido + nombre escrito "a la colombiana".
ALIAS_DOCENTES = {
    "GUANGA YINA": "GINA AMPARO GUANGA ORTIZ",
    "MICHAEL PINTA": "MAICOL REINEL CUELAN PINTA",
}

MAPA_AREAS = {
    "AWAPIT": "LM",
    "COMUNICACION": "COE",
    "ETICA": "ETIC",
    "FISICA": "FIS",
    "JUEGOS TRADICIONALES": "JTD",
    "LENGUA EXTRANJERA": "LEI",
    "MATEMATICAS": "MATE",
    "NATURALEZA": "NAP",
    "QUIMICA": "QUIM",
    "TALENTO": "TPEC",
    "TECNOLOGIA": "TPI",
    "TERRITORIO": "TAL",
    "PRODUCCION": "PSA",
    "LEGISLACION": "LI",
    "LEGISLACION INDIGENA": "LI",
    "LENGUA MATERNA": "LM",
    "FILOSOFIA": "FILO",
    "INVESTIGACION": "INV",
}


def _hhmm(texto: str) -> dt.time:
    h, m = texto.split(":")
    return dt.time(int(h), int(m))


def nombre_grupo(grado: int, curso: int | None) -> str:
    # En el Word a veces viene solo el grado ("7", "0") sin división: es todo
    # el grado, sin una división concreta asignada.
    nombre_grado = models.GRADOS_NOMBRES.get(grado, str(grado))
    if not curso:
        return f"{nombre_grado} (sin división)"
    return f"{nombre_grado} - {models.DIVISIONES_NOMBRES.get(curso, curso)}"


def etiqueta_grupo(grado: int, curso: int | None) -> str:
    """Forma corta tipo '8-1' / '0' (como en el Word)."""
    return f"{grado}-{curso}" if curso else str(grado)


# --- Normalización y emparejamiento de nombres (compartido con el importador) -


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^A-Za-z0-9 ]", " ", texto).upper()
    return re.sub(r"\s+", " ", texto).strip()


def _tokens(texto: str) -> set[str]:
    return {t for t in normalizar(texto).split() if len(t) >= 2}


def matchear_docente(nombre_archivo: str, docentes: list[models.Docente]) -> models.Docente | None:
    """Empareja un nombre corto del Word ('APELLIDO NOMBRE' o al revés) con un
    Docente ya existente. Exige que TODOS los tokens del archivo aparezcan en
    el nombre completo (exacto o muy parecido, para casos tipo BAYRON/BAIRON).
    Si hay varias coincidencias igual de buenas, devuelve None para que se
    revise a mano — nunca crea un docente nuevo."""
    objetivo = _tokens(nombre_archivo)
    if not objetivo:
        return None

    alias = ALIAS_DOCENTES.get(normalizar(nombre_archivo))
    if alias:
        for d in docentes:
            if normalizar(d.nombre_completo) == normalizar(alias):
                return d

    candidatos: list[tuple[int, models.Docente]] = []
    for d in docentes:
        dtoks = _tokens(d.nombre_completo)
        if not dtoks:
            continue
        cubre_todo = all(
            any(t == u or difflib.SequenceMatcher(None, t, u).ratio() >= 0.80 for u in dtoks)
            for t in objetivo
        )
        if cubre_todo:
            candidatos.append((len(objetivo & dtoks), d))

    if not candidatos:
        return None
    candidatos.sort(key=lambda x: x[0], reverse=True)
    if len(candidatos) > 1 and candidatos[0][0] == candidatos[1][0]:
        return None  # ambiguo
    return candidatos[0][1]


def matchear_area(label: str, areas: list[models.Area]) -> models.Area | None:
    norm = normalizar(label)
    if not norm:
        return None
    codigo = MAPA_AREAS.get(norm)
    if codigo:
        for a in areas:
            if a.codigo == codigo:
                return a
    for a in areas:
        na = normalizar(a.nombre)
        if norm == na:
            return a
        if len(norm) >= 5 and len(na) >= 5 and (norm in na or na in norm):
            return a
    return None


# --- Franja actual --------------------------------------------------------


def franja_actual(ahora: dt.datetime | None = None) -> dict:
    ahora = ahora or fechas.ahora_colombia().replace(tzinfo=None)
    wd = ahora.weekday()  # 0 = lunes
    if wd >= 5:
        return {
            "fecha": ahora.date().isoformat(),
            "dia": None,
            "dia_nombre": "Fin de semana",
            "hora": None,
            "jornada": JORNADA,
            "franja": None,
            "estado": "fin_de_semana",
        }

    dia = wd + 1
    t = ahora.time()
    base = {
        "fecha": ahora.date().isoformat(),
        "dia": dia,
        "dia_nombre": DIAS_NOMBRES[dia],
        "jornada": JORNADA,
    }
    if t < _hhmm(FRANJAS[0]["inicio"]) or t >= _hhmm(FRANJAS[-1]["fin"]):
        return {**base, "hora": None, "franja": None, "estado": "fuera_jornada"}
    if _hhmm(DESCANSO["inicio"]) <= t < _hhmm(DESCANSO["fin"]):
        return {**base, "hora": None, "franja": DESCANSO, "estado": "descanso"}
    for f in FRANJAS:
        if _hhmm(f["inicio"]) <= t < _hhmm(f["fin"]):
            return {**base, "hora": f["hora"], "franja": f, "estado": "en_franja"}
    # hueco entre franjas (no debería con estos horarios): lo tratamos como libre
    return {**base, "hora": None, "franja": None, "estado": "fuera_jornada"}


# --- Consultas de horario ----------------------------------------------------


def _dia_de_fecha(fecha: dt.date) -> int | None:
    wd = fecha.weekday()
    return wd + 1 if wd < 5 else None


def _bloque_a_schema(b: models.BloqueHorario, en_conflicto: bool = False) -> schemas.BloqueHorario:
    return schemas.BloqueHorario(
        id=b.id,
        anio_lectivo=b.anio_lectivo,
        docente_id=b.docente_id,
        docente_nombre=b.docente.nombre_completo if b.docente else "",
        sede_id=b.sede_id,
        grado=b.grado,
        curso=b.curso,
        grupo=etiqueta_grupo(b.grado, b.curso),
        nombre_grupo=nombre_grupo(b.grado, b.curso),
        area_id=b.area_id,
        area_label=b.area_label,
        area_nombre=b.area.nombre if b.area else b.area_label,
        dia=b.dia,
        dia_nombre=DIAS_NOMBRES.get(b.dia, str(b.dia)),
        hora=b.hora,
        aula=b.aula,
        origen=b.origen,
        estado=b.estado,
        en_conflicto=en_conflicto,
    )


def _slots_en_conflicto(db: Session, anio_lectivo: int) -> set[tuple]:
    """(grado, curso, dia, hora) con más de un bloque 'activo' y que todavía
    nadie ha revisado (ni siquiera para decir "dejar los dos")."""
    filas = db.scalars(
        select(models.BloqueHorario).where(
            models.BloqueHorario.anio_lectivo == anio_lectivo,
            models.BloqueHorario.estado == "activo",
        )
    ).all()
    por_slot: dict[tuple, list[models.BloqueHorario]] = {}
    for b in filas:
        por_slot.setdefault((b.grado, b.curso, b.dia, b.hora), []).append(b)
    return {
        slot
        for slot, bs in por_slot.items()
        if len(bs) > 1 and not all(b.conflicto_revisado for b in bs)
    }


def listar_bloques(
    db: Session,
    anio_lectivo: int,
    docente_id: int | None = None,
    grado: int | None = None,
    curso: int | None = None,
    dia: int | None = None,
    area_id: int | None = None,
) -> list[schemas.BloqueHorario]:
    stmt = select(models.BloqueHorario).where(models.BloqueHorario.anio_lectivo == anio_lectivo)
    if docente_id is not None:
        stmt = stmt.where(models.BloqueHorario.docente_id == docente_id)
    if grado is not None:
        stmt = stmt.where(models.BloqueHorario.grado == grado)
    if curso is not None:
        stmt = stmt.where(models.BloqueHorario.curso == curso)
    if dia is not None:
        stmt = stmt.where(models.BloqueHorario.dia == dia)
    if area_id is not None:
        stmt = stmt.where(models.BloqueHorario.area_id == area_id)
    bloques = db.scalars(stmt.order_by(models.BloqueHorario.dia, models.BloqueHorario.hora)).all()
    conflictos = _slots_en_conflicto(db, anio_lectivo)
    return [
        _bloque_a_schema(b, (b.grado, b.curso, b.dia, b.hora) in conflictos) for b in bloques
    ]


def horario_docente(db: Session, docente_id: int, anio_lectivo: int) -> schemas.HorarioDocenteSemana:
    docente = db.get(models.Docente, docente_id)
    if docente is None:
        raise ValueError("Docente no encontrado")
    bloques = db.scalars(
        select(models.BloqueHorario).where(
            models.BloqueHorario.anio_lectivo == anio_lectivo,
            models.BloqueHorario.docente_id == docente_id,
        )
    ).all()
    conflictos = _slots_en_conflicto(db, anio_lectivo)
    # Si en una celda hay un bloque descartado y otro activo, se muestra el activo.
    por_celda: dict[tuple, models.BloqueHorario] = {}
    for b in bloques:
        clave = (b.dia, b.hora)
        if clave not in por_celda or (b.estado == "activo" and por_celda[clave].estado != "activo"):
            por_celda[clave] = b
    filas = []
    for f in FRANJAS:
        celdas = []
        for dia in range(1, 6):
            b = por_celda.get((dia, f["hora"]))
            celdas.append(
                _bloque_a_schema(b, (b.grado, b.curso, b.dia, b.hora) in conflictos) if b else None
            )
        filas.append(schemas.FilaHorario(hora=f["hora"], inicio=f["inicio"], fin=f["fin"], celdas=celdas))
    return schemas.HorarioDocenteSemana(
        docente_id=docente_id,
        docente_nombre=docente.nombre_completo,
        anio_lectivo=anio_lectivo,
        total_bloques=sum(1 for b in bloques if b.estado == "activo"),
        filas=filas,
    )


def horario_grupo(
    db: Session, grado: int, curso: int | None, anio_lectivo: int, dia: int | None = None
) -> schemas.HorarioGrupo:
    stmt = select(models.BloqueHorario).where(
        models.BloqueHorario.anio_lectivo == anio_lectivo,
        models.BloqueHorario.grado == grado,
    )
    if curso is None:
        stmt = stmt.where(models.BloqueHorario.curso.is_(None))
    else:
        stmt = stmt.where(models.BloqueHorario.curso == curso)
    if dia is not None:
        stmt = stmt.where(models.BloqueHorario.dia == dia)
    bloques = db.scalars(stmt.order_by(models.BloqueHorario.dia, models.BloqueHorario.hora)).all()

    # Si el bloque no trae división (curso None), aplica a todo el grado: se
    # cuentan los estudiantes de ese grado en la sede sin importar la división.
    filtros = [
        models.Estudiante.sede_id == SEDE_HORARIO_ID,
        models.Estudiante.grado == grado,
        models.Estudiante.estado == "ACTIVO",
    ]
    if curso is not None:
        filtros.append(models.Estudiante.curso == curso)
    total = db.scalar(select(func.count()).select_from(models.Estudiante).where(*filtros)) or 0
    conflictos = _slots_en_conflicto(db, anio_lectivo)
    return schemas.HorarioGrupo(
        grado=grado,
        curso=curso,
        grupo=etiqueta_grupo(grado, curso),
        nombre_grupo=nombre_grupo(grado, curso),
        anio_lectivo=anio_lectivo,
        total_estudiantes=total,
        bloques=[
            _bloque_a_schema(b, (b.grado, b.curso, b.dia, b.hora) in conflictos) for b in bloques
        ],
    )


# --- Disponibilidad --------------------------------------------------------


def _ids_con_horario(db: Session, anio_lectivo: int) -> set[int]:
    return set(
        db.scalars(
            select(models.BloqueHorario.docente_id)
            .where(
                models.BloqueHorario.anio_lectivo == anio_lectivo,
                models.BloqueHorario.estado == "activo",
            )
            .distinct()
        ).all()
    )


def _ausentes_en(db: Session, fecha: dt.date) -> set[int]:
    return set(
        db.scalars(
            select(models.AusenciaDocente.docente_id).where(models.AusenciaDocente.fecha == fecha)
        ).all()
    )


def _cubriendo_en(db: Session, fecha: dt.date, hora: int | None = None) -> set[int]:
    stmt = select(models.Reemplazo.docente_reemplazo_id).where(
        models.Reemplazo.fecha == fecha,
        models.Reemplazo.estado == "asignado",
        models.Reemplazo.docente_reemplazo_id.is_not(None),
    )
    if hora is not None:
        stmt = stmt.where(models.Reemplazo.hora == hora)
    return set(db.scalars(stmt).all())


def docentes_libres(
    db: Session,
    dia: int,
    hora: int,
    fecha: dt.date,
    anio_lectivo: int,
    hora_fin: int | None = None,
) -> list[schemas.DocenteLibre]:
    """Docentes libres en la franja. Con `hora_fin` se pide un rango: libres
    en TODAS las horas de [hora .. hora_fin] (p. ej. 5ª y 6ª)."""
    con_horario = _ids_con_horario(db, anio_lectivo)
    if not con_horario:
        return []
    horas = list(range(hora, (hora_fin or hora) + 1))
    ocupados = set(
        db.scalars(
            select(models.BloqueHorario.docente_id).where(
                models.BloqueHorario.anio_lectivo == anio_lectivo,
                models.BloqueHorario.dia == dia,
                models.BloqueHorario.hora.in_(horas),
                models.BloqueHorario.estado == "activo",
            )
        ).all()
    )
    ausentes = _ausentes_en(db, fecha)
    cubriendo = set().union(*(_cubriendo_en(db, fecha, h) for h in horas)) if horas else set()
    libres_ids = con_horario - ocupados - ausentes - cubriendo

    docentes = {d.id: d for d in db.scalars(select(models.Docente)).all()}
    carga_dia = _carga_por_dia(db, anio_lectivo, dia)
    niveles = _niveles_por_docente(db, anio_lectivo)
    resultado = []
    for did in libres_ids:
        d = docentes.get(did)
        if d is None:
            continue
        resultado.append(
            schemas.DocenteLibre(
                docente_id=did,
                nombre_completo=d.nombre_completo,
                bloques_ese_dia=carga_dia.get(did, 0),
                cubriendo_reemplazo=did in _cubriendo_en(db, fecha),
                niveles=sorted(niveles.get(did, [])),
            )
        )
    resultado.sort(key=lambda x: (x.bloques_ese_dia, x.nombre_completo))
    return resultado


def nivel_de_grado(grado: int) -> str:
    """Primaria = Preescolar + 1° a 5°. Secundaria/media = 6° a 11°."""
    return "primaria" if grado <= 5 else "secundaria"


def _niveles_por_docente(db: Session, anio_lectivo: int) -> dict[int, set[str]]:
    """docente_id -> {'primaria'} / {'secundaria'} / ambos, según sus clases."""
    filas = db.execute(
        select(models.BloqueHorario.docente_id, models.BloqueHorario.grado)
        .where(
            models.BloqueHorario.anio_lectivo == anio_lectivo,
            models.BloqueHorario.estado == "activo",
        )
        .distinct()
    ).all()
    out: dict[int, set[str]] = {}
    for did, grado in filas:
        out.setdefault(did, set()).add(nivel_de_grado(grado))
    return out


def _carga_por_dia(db: Session, anio_lectivo: int, dia: int) -> dict[int, int]:
    filas = db.execute(
        select(models.BloqueHorario.docente_id, func.count())
        .where(
            models.BloqueHorario.anio_lectivo == anio_lectivo,
            models.BloqueHorario.dia == dia,
            models.BloqueHorario.estado == "activo",
        )
        .group_by(models.BloqueHorario.docente_id)
    ).all()
    return {did: n for did, n in filas}


def estado_docente(
    db: Session,
    docente_id: int,
    fecha: dt.date,
    ahora: dt.datetime | None = None,
    _franja: dict | None = None,
) -> dict:
    """Estado visual de un docente en un momento dado.
    🟢 libre · 🔵 en clase · 🟡 descanso · ⚪ fuera de jornada · 🔴 ausente ·
    🟠 cubriendo reemplazo."""
    if docente_id in _ausentes_en(db, fecha):
        return {"estado": "ausente", "detalle": None}

    fr = _franja if _franja is not None else franja_actual(ahora)
    if fr["estado"] in ("fin_de_semana", "fuera_jornada"):
        return {"estado": "fuera_jornada", "detalle": None}
    if fr["estado"] == "descanso":
        return {"estado": "descanso", "detalle": None}

    dia, hora = fr["dia"], fr["hora"]
    reemplazo = db.scalar(
        select(models.Reemplazo).where(
            models.Reemplazo.fecha == fecha,
            models.Reemplazo.hora == hora,
            models.Reemplazo.estado == "asignado",
            models.Reemplazo.docente_reemplazo_id == docente_id,
        )
    )
    if reemplazo is not None:
        return {
            "estado": "cubriendo",
            "detalle": f"{reemplazo.area_label} {etiqueta_grupo(reemplazo.grado, reemplazo.curso)}",
        }

    bloque = db.scalar(
        select(models.BloqueHorario).where(
            models.BloqueHorario.anio_lectivo == fecha.year,
            models.BloqueHorario.docente_id == docente_id,
            models.BloqueHorario.dia == dia,
            models.BloqueHorario.hora == hora,
            models.BloqueHorario.estado == "activo",
        )
    )
    if bloque is not None:
        return {
            "estado": "en_clase",
            "detalle": f"{bloque.area_label} {etiqueta_grupo(bloque.grado, bloque.curso)}",
        }
    return {"estado": "libre", "detalle": None}


def estado_docentes(db: Session, fecha: dt.date, ahora: dt.datetime | None = None) -> list[schemas.EstadoDocente]:
    fr = franja_actual(ahora)
    con_horario = _ids_con_horario(db, fecha.year)
    docentes = [d for d in db.scalars(select(models.Docente).order_by(models.Docente.nombre_completo)).all() if d.id in con_horario]
    salida = []
    for d in docentes:
        est = estado_docente(db, d.id, fecha, ahora, _franja=fr)
        salida.append(
            schemas.EstadoDocente(
                docente_id=d.id,
                nombre_completo=d.nombre_completo,
                estado=est["estado"],
                detalle=est["detalle"],
            )
        )
    orden = {"ausente": 0, "cubriendo": 1, "en_clase": 2, "libre": 3, "descanso": 4, "fuera_jornada": 5}
    salida.sort(key=lambda x: (orden.get(x.estado, 9), x.nombre_completo))
    return salida


# --- Ausencias y clases afectadas -----------------------------------------


def clases_afectadas(db: Session, docente_id: int, fecha: dt.date) -> list[schemas.ClaseAfectada]:
    dia = _dia_de_fecha(fecha)
    if dia is None:
        return []
    bloques = db.scalars(
        select(models.BloqueHorario)
        .where(
            models.BloqueHorario.anio_lectivo == fecha.year,
            models.BloqueHorario.docente_id == docente_id,
            models.BloqueHorario.dia == dia,
            models.BloqueHorario.estado == "activo",
        )
        .order_by(models.BloqueHorario.hora)
    ).all()
    conflictos = _slots_en_conflicto(db, fecha.year)

    # Agrupa horas SEGUIDAS del mismo grupo+área en una sola "clase" (bloque doble).
    grupos: list[list[models.BloqueHorario]] = []
    for b in bloques:
        g = grupos[-1] if grupos else None
        if (
            g
            and (g[-1].grado, g[-1].curso, g[-1].area_label) == (b.grado, b.curso, b.area_label)
            and b.hora == g[-1].hora + 1
        ):
            g.append(b)
        else:
            grupos.append([b])

    salida = []
    for g in grupos:
        b0 = g[0]
        en_conflicto = any((x.grado, x.curso, x.dia, x.hora) in conflictos for x in g)
        opciones = []
        if en_conflicto:
            for otro in db.scalars(
                select(models.BloqueHorario).where(
                    models.BloqueHorario.anio_lectivo == fecha.year,
                    models.BloqueHorario.grado == b0.grado,
                    models.BloqueHorario.curso == b0.curso if b0.curso is not None else models.BloqueHorario.curso.is_(None),
                    models.BloqueHorario.dia == b0.dia,
                    models.BloqueHorario.hora == b0.hora,
                    models.BloqueHorario.estado == "activo",
                )
            ):
                opciones.append(
                    schemas.OpcionConflicto(
                        bloque_id=otro.id,
                        docente_id=otro.docente_id,
                        docente_nombre=otro.docente.nombre_completo if otro.docente else "",
                        area_label=otro.area_label,
                        origen=otro.origen,
                    )
                )
        reemplazos = [
            db.scalar(
                select(models.Reemplazo).where(
                    models.Reemplazo.fecha == fecha,
                    models.Reemplazo.bloque_horario_id == x.id,
                    models.Reemplazo.estado != "cancelado",
                )
            )
            for x in g
        ]
        con_r = [r for r in reemplazos if r is not None]
        asignados = [r for r in con_r if r.estado == "asignado"]
        if asignados and len(asignados) == len(g):
            estado_r = "asignado"
        elif asignados:
            estado_r = "parcial"
        elif con_r:
            estado_r = "pendiente"
        else:
            estado_r = None
        docente_r = next(
            (r.docente_reemplazo.nombre_completo for r in asignados if r.docente_reemplazo), None
        )
        salida.append(
            schemas.ClaseAfectada(
                bloque_horario_id=b0.id,
                bloque_ids=[x.id for x in g],
                hora=b0.hora,
                horas=[x.hora for x in g],
                dia=b0.dia,
                grado=b0.grado,
                curso=b0.curso,
                grupo=etiqueta_grupo(b0.grado, b0.curso),
                nombre_grupo=nombre_grupo(b0.grado, b0.curso),
                area_id=b0.area_id,
                area_label=b0.area_label,
                conflicto=en_conflicto,
                conflicto_opciones=opciones,
                reemplazo_id=con_r[0].id if con_r else None,
                reemplazo_estado=estado_r,
                reemplazo_docente=docente_r,
            )
        )
    return salida


def registrar_ausencia(db: Session, datos: schemas.AusenciaCrear) -> schemas.Ausencia:
    fecha = datos.fecha
    ausencia = db.scalar(
        select(models.AusenciaDocente).where(
            models.AusenciaDocente.docente_id == datos.docente_id,
            models.AusenciaDocente.fecha == fecha,
        )
    )
    if ausencia is None:
        ausencia = models.AusenciaDocente(
            docente_id=datos.docente_id,
            fecha=fecha,
            motivo=datos.motivo,
            registrado_por=datos.registrado_por,
        )
        db.add(ausencia)
        db.flush()
    else:
        ausencia.motivo = datos.motivo
        if datos.registrado_por:
            ausencia.registrado_por = datos.registrado_por

    # Crea un Reemplazo "pendiente" por cada clase afectada que aún no tenga uno.
    # OJO: si el bloque está en conflicto (dos docentes para ese grupo+hora),
    # NO se crea el pendiente todavía — primero hay que confirmar de quién es la
    # clase (ver clases_afectadas[].conflicto y resolver_conflicto).
    dia = _dia_de_fecha(fecha)
    if dia is not None:
        conflictos = _slots_en_conflicto(db, fecha.year)
        bloques = db.scalars(
            select(models.BloqueHorario).where(
                models.BloqueHorario.anio_lectivo == fecha.year,
                models.BloqueHorario.docente_id == datos.docente_id,
                models.BloqueHorario.dia == dia,
                models.BloqueHorario.estado == "activo",
            )
        ).all()
        for b in bloques:
            if (b.grado, b.curso, b.dia, b.hora) in conflictos:
                continue
            ya = db.scalar(
                select(models.Reemplazo).where(
                    models.Reemplazo.fecha == fecha,
                    models.Reemplazo.bloque_horario_id == b.id,
                    models.Reemplazo.estado != "cancelado",
                )
            )
            if ya is None:
                db.add(
                    models.Reemplazo(
                        fecha=fecha,
                        dia=b.dia,
                        hora=b.hora,
                        grado=b.grado,
                        curso=b.curso,
                        area_id=b.area_id,
                        area_label=b.area_label,
                        docente_ausente_id=datos.docente_id,
                        bloque_horario_id=b.id,
                        ausencia_id=ausencia.id,
                        estado="pendiente",
                    )
                )
            elif ya.ausencia_id is None:
                ya.ausencia_id = ausencia.id
    db.commit()
    db.refresh(ausencia)
    return _ausencia_a_schema(db, ausencia)


def _ausencia_a_schema(db: Session, a: models.AusenciaDocente) -> schemas.Ausencia:
    return schemas.Ausencia(
        id=a.id,
        docente_id=a.docente_id,
        docente_nombre=a.docente.nombre_completo if a.docente else "",
        fecha=a.fecha,
        motivo=a.motivo,
        registrado_por=a.registrado_por,
        registrado_en=a.registrado_en,
        clases_afectadas=clases_afectadas(db, a.docente_id, a.fecha),
    )


def listar_ausencias(db: Session, fecha: dt.date) -> list[schemas.Ausencia]:
    ausencias = db.scalars(
        select(models.AusenciaDocente)
        .where(models.AusenciaDocente.fecha == fecha)
        .order_by(models.AusenciaDocente.registrado_en)
    ).all()
    return [_ausencia_a_schema(db, a) for a in ausencias]


def eliminar_ausencia(db: Session, ausencia_id: int) -> bool:
    ausencia = db.get(models.AusenciaDocente, ausencia_id)
    if ausencia is None:
        return False
    # El reemplazo no tiene sentido sin la ausencia que lo originó: se borran
    # todos (pendientes y asignados). El horario original (BloqueHorario) no
    # se toca nunca.
    for r in db.scalars(
        select(models.Reemplazo).where(models.Reemplazo.ausencia_id == ausencia_id)
    ).all():
        db.delete(r)
    # Reemplazo no tiene relación ORM con AusenciaDocente, así que SQLAlchemy
    # no sabe que los reemplazos van primero: con las claves foráneas
    # activas, borrar la ausencia antes fallaría. El flush fija el orden.
    db.flush()
    db.delete(ausencia)
    db.commit()
    return True


# --- Reemplazos: candidatos, validación, asignación ----------------------

PESOS = {
    "base": 40,        # libre + sin conflictos (requisitos duros, siempre presentes)
    "bloque": 15,      # libre TODAS las horas de la clase (bloque doble) — cubre completo
    "area": 22,        # dicta la misma área
    "nivel": 8,        # trabaja en el mismo nivel (primaria / secundaria)
    "grado": 13,       # ya trabaja con ese grado
    "grupo": 9,        # ya trabaja con ese grupo exacto
    "continuidad": 6,  # tiene clase contigua (misma sede/grado)
    "sede": 4,         # pertenece a la misma sede
}


def _bloques_de_la_clase(db: Session, bloque: models.BloqueHorario) -> list[models.BloqueHorario]:
    """La 'clase' completa a la que pertenece un bloque: horas SEGUIDAS del
    mismo docente, día, grupo y área (un bloque doble de 2 horas = 2 filas).
    Devuelve la corrida ordenada por hora."""
    hermanos = db.scalars(
        select(models.BloqueHorario).where(
            models.BloqueHorario.anio_lectivo == bloque.anio_lectivo,
            models.BloqueHorario.docente_id == bloque.docente_id,
            models.BloqueHorario.dia == bloque.dia,
            models.BloqueHorario.grado == bloque.grado,
            models.BloqueHorario.curso == bloque.curso
            if bloque.curso is not None
            else models.BloqueHorario.curso.is_(None),
            models.BloqueHorario.area_label == bloque.area_label,
            models.BloqueHorario.estado == "activo",
        )
    ).all()
    por_hora = {b.hora: b for b in hermanos}
    horas = [bloque.hora]
    h = bloque.hora - 1
    while h in por_hora:
        horas.insert(0, h)
        h -= 1
    h = bloque.hora + 1
    while h in por_hora:
        horas.append(h)
        h += 1
    return [por_hora[h] for h in horas]


def _bloques_de(db: Session, docente_id: int, anio_lectivo: int) -> list[models.BloqueHorario]:
    return list(
        db.scalars(
            select(models.BloqueHorario).where(
                models.BloqueHorario.anio_lectivo == anio_lectivo,
                models.BloqueHorario.docente_id == docente_id,
                models.BloqueHorario.estado == "activo",
            )
        ).all()
    )


def _evaluar_candidato(
    db: Session,
    docente: models.Docente,
    bloque: models.BloqueHorario,
    fecha: dt.date,
    carga_dia: int,
    horas_clase: list[int] | None = None,
    horas_libres: set[int] | None = None,
) -> schemas.CandidatoReemplazo:
    anio = fecha.year
    mis_bloques = _bloques_de(db, docente.id, anio)
    horas_clase = horas_clase or [bloque.hora]
    horas_libres = horas_libres if horas_libres is not None else {bloque.hora}
    razones: list[schemas.RazonReemplazo] = []
    puntos = PESOS["base"]
    razones.append(schemas.RazonReemplazo(tipo="ok", texto="Libre en la 1ª hora de la clase"))
    razones.append(schemas.RazonReemplazo(tipo="ok", texto="No está cubriendo otro reemplazo"))

    # Bloque doble: ¿libre TODAS las horas seguidas?
    cubre_completo = len(horas_clase) <= 1 or set(horas_clase) <= horas_libres
    if len(horas_clase) > 1:
        etq_horas = "ª–".join(str(h) for h in [horas_clase[0], horas_clase[-1]]) + "ª"
        if cubre_completo:
            puntos += PESOS["bloque"]
            razones.append(
                schemas.RazonReemplazo(tipo="ok", texto=f"Libre las {len(horas_clase)} horas seguidas ({etq_horas}) — cubre el bloque completo")
            )
        else:
            faltan = [h for h in horas_clase if h not in horas_libres]
            razones.append(
                schemas.RazonReemplazo(
                    tipo="warn",
                    texto=f"Solo libre {len(horas_libres & set(horas_clase))} de {len(horas_clase)} horas del bloque (ocupado en la {faltan[0]}ª)",
                )
            )

    # Mismo nivel (primaria / secundaria)
    nivel_clase = nivel_de_grado(bloque.grado)
    trabaja_nivel = any(nivel_de_grado(b.grado) == nivel_clase for b in mis_bloques)
    if trabaja_nivel:
        puntos += PESOS["nivel"]
        razones.append(schemas.RazonReemplazo(tipo="ok", texto=f"Trabaja en {nivel_clase}"))
    else:
        razones.append(schemas.RazonReemplazo(tipo="warn", texto=f"No trabaja normalmente en {nivel_clase}"))

    # Misma área
    if bloque.area_id is not None:
        misma_area = any(b.area_id == bloque.area_id for b in mis_bloques)
    else:
        objetivo = normalizar(bloque.area_label)
        misma_area = any(normalizar(b.area_label) == objetivo for b in mis_bloques)
    if misma_area:
        puntos += PESOS["area"]
        razones.append(schemas.RazonReemplazo(tipo="ok", texto=f"Dicta la misma área: {bloque.area_label}"))
    else:
        razones.append(schemas.RazonReemplazo(tipo="warn", texto="No dicta normalmente esta área"))

    # Grado / grupo
    nombre_grado = models.GRADOS_NOMBRES.get(bloque.grado, str(bloque.grado))
    if any(b.grado == bloque.grado for b in mis_bloques):
        puntos += PESOS["grado"]
        razones.append(schemas.RazonReemplazo(tipo="ok", texto=f"Ya trabaja con {nombre_grado}"))
    else:
        razones.append(schemas.RazonReemplazo(tipo="warn", texto=f"No trabaja normalmente con {nombre_grado}"))
    if any(b.grado == bloque.grado and b.curso == bloque.curso for b in mis_bloques):
        puntos += PESOS["grupo"]
        razones.append(
            schemas.RazonReemplazo(
                tipo="ok", texto=f"Ya trabaja con el grupo {etiqueta_grupo(bloque.grado, bloque.curso)}"
            )
        )

    # Misma sede
    if any(b.sede_id == bloque.sede_id for b in mis_bloques):
        puntos += PESOS["sede"]
        razones.append(schemas.RazonReemplazo(tipo="ok", texto="Misma sede"))

    # Continuidad: clase contigua (hora ±1) el mismo día, mismo grado o misma sede
    contiguas = [
        b for b in mis_bloques if b.dia == bloque.dia and abs(b.hora - bloque.hora) == 1
    ]
    if any(b.grado == bloque.grado or b.sede_id == bloque.sede_id for b in contiguas):
        puntos += PESOS["continuidad"]
        razones.append(schemas.RazonReemplazo(tipo="ok", texto="Tiene clase contigua ese día"))

    # El peso "bloque" solo cuenta (y solo suma al máximo) si la clase es doble.
    total = sum(v for k, v in PESOS.items() if k != "bloque" or len(horas_clase) > 1)
    porcentaje = round(puntos / total * 100)
    return schemas.CandidatoReemplazo(
        docente_id=docente.id,
        nombre_completo=docente.nombre_completo,
        porcentaje=porcentaje,
        bloques_ese_dia=carga_dia,
        razones=razones,
        nivel=nivel_clase,
        trabaja_ese_nivel=trabaja_nivel,
        horas_libres=len(horas_libres & set(horas_clase)),
        horas_total=len(horas_clase),
        cubre_bloque_completo=cubre_completo,
    )


def _ocupados_en(db: Session, anio: int, dia: int, hora: int) -> set[int]:
    return set(
        db.scalars(
            select(models.BloqueHorario.docente_id).where(
                models.BloqueHorario.anio_lectivo == anio,
                models.BloqueHorario.dia == dia,
                models.BloqueHorario.hora == hora,
                models.BloqueHorario.estado == "activo",
            )
        ).all()
    )


def candidatos_reemplazo(db: Session, bloque_id: int, fecha: dt.date) -> schemas.RespuestaCandidatos:
    bloque = db.get(models.BloqueHorario, bloque_id)
    if bloque is None:
        raise ValueError("Bloque de horario no encontrado")
    anio = fecha.year
    dia = bloque.dia

    clase = _bloques_de_la_clase(db, bloque)
    horas_clase = [b.hora for b in clase]

    con_horario = _ids_con_horario(db, anio)
    ausentes = _ausentes_en(db, fecha)
    # ocupación y "cubriendo otro reemplazo" por cada hora de la clase
    ocup_por_hora = {h: _ocupados_en(db, anio, dia, h) for h in horas_clase}
    cubr_por_hora = {h: _cubriendo_en(db, fecha, h) for h in horas_clase}
    # el candidato tiene que estar libre AL MENOS en la 1ª hora de la clase
    primera = horas_clase[0]
    disponibles = (
        con_horario - ocup_por_hora[primera] - cubr_por_hora[primera] - ausentes - {bloque.docente_id}
    )

    docentes = {d.id: d for d in db.scalars(select(models.Docente)).all()}
    carga_dia = _carga_por_dia(db, anio, dia)
    candidatos = []
    for did in disponibles:
        if did not in docentes:
            continue
        horas_libres = {
            h for h in horas_clase if did not in ocup_por_hora[h] and did not in cubr_por_hora[h]
        }
        candidatos.append(
            _evaluar_candidato(
                db, docentes[did], bloque, fecha, carga_dia.get(did, 0), horas_clase, horas_libres
            )
        )
    # primero los que cubren el bloque completo, luego por %
    candidatos.sort(
        key=lambda c: (not c.cubre_bloque_completo, -c.porcentaje, c.bloques_ese_dia, c.nombre_completo)
    )
    return schemas.RespuestaCandidatos(
        bloque=_bloque_a_schema(bloque),
        fecha=fecha,
        horas=horas_clase,
        bloque_ids=[b.id for b in clase],
        nivel=nivel_de_grado(bloque.grado),
        candidatos=candidatos,
    )


def validar_reemplazo(
    db: Session, bloque: models.BloqueHorario, fecha: dt.date, docente_reemplazo_id: int
) -> list[str]:
    conflictos: list[str] = []
    if docente_reemplazo_id == bloque.docente_id:
        conflictos.append("El reemplazante es el mismo docente ausente")

    if docente_reemplazo_id in _ausentes_en(db, fecha):
        conflictos.append("El docente está registrado como ausente ese día")

    choque = db.scalar(
        select(models.BloqueHorario).where(
            models.BloqueHorario.anio_lectivo == fecha.year,
            models.BloqueHorario.docente_id == docente_reemplazo_id,
            models.BloqueHorario.dia == bloque.dia,
            models.BloqueHorario.hora == bloque.hora,
            models.BloqueHorario.estado == "activo",
        )
    )
    if choque is not None:
        conflictos.append(
            f"El docente tiene clase a esa hora ({choque.area_label} "
            f"{etiqueta_grupo(choque.grado, choque.curso)})"
        )

    otro = db.scalar(
        select(models.Reemplazo).where(
            models.Reemplazo.fecha == fecha,
            models.Reemplazo.hora == bloque.hora,
            models.Reemplazo.estado == "asignado",
            models.Reemplazo.docente_reemplazo_id == docente_reemplazo_id,
        )
    )
    if otro is not None:
        conflictos.append("El docente ya está cubriendo otro reemplazo a esa hora")

    ya_cubierta = db.scalar(
        select(models.Reemplazo).where(
            models.Reemplazo.fecha == fecha,
            models.Reemplazo.bloque_horario_id == bloque.id,
            models.Reemplazo.estado == "asignado",
        )
    )
    if ya_cubierta is not None:
        conflictos.append("Esta clase ya tiene un reemplazo asignado")

    return conflictos


def _reemplazo_a_schema(db: Session, r: models.Reemplazo) -> schemas.Reemplazo:
    return schemas.Reemplazo(
        id=r.id,
        fecha=r.fecha,
        dia=r.dia,
        dia_nombre=DIAS_NOMBRES.get(r.dia, str(r.dia)),
        hora=r.hora,
        grado=r.grado,
        curso=r.curso,
        grupo=etiqueta_grupo(r.grado, r.curso),
        nombre_grupo=nombre_grupo(r.grado, r.curso),
        area_id=r.area_id,
        area_label=r.area_label,
        docente_ausente_id=r.docente_ausente_id,
        docente_ausente=r.docente_ausente.nombre_completo if r.docente_ausente else "",
        docente_reemplazo_id=r.docente_reemplazo_id,
        docente_reemplazo=r.docente_reemplazo.nombre_completo if r.docente_reemplazo else None,
        bloque_horario_id=r.bloque_horario_id,
        estado=r.estado,
        compatibilidad=r.compatibilidad,
        razones=json.loads(r.razones) if r.razones else [],
        asignado_por=r.asignado_por,
        actualizado_en=r.actualizado_en,
        horas=[r.hora],
        ids=[r.id],
    )


def _snapshot_candidato(
    db: Session,
    bloque: models.BloqueHorario,
    fecha: dt.date,
    docente_id: int,
    horas_clase: list[int] | None = None,
    horas_libres: set[int] | None = None,
):
    """% y razones para el candidato elegido, para dejarlo registrado."""
    carga = _carga_por_dia(db, fecha.year, bloque.dia).get(docente_id, 0)
    docente = db.get(models.Docente, docente_id)
    if docente is None:
        return None, None
    cand = _evaluar_candidato(db, docente, bloque, fecha, carga, horas_clase, horas_libres)
    return cand.porcentaje, json.dumps([r.model_dump() for r in cand.razones], ensure_ascii=False)


def asignar_reemplazo(db: Session, datos: schemas.ReemplazoAsignar) -> schemas.Reemplazo:
    bloque = db.get(models.BloqueHorario, datos.bloque_horario_id)
    if bloque is None:
        raise ValueError("Bloque de horario no encontrado")
    fecha = datos.fecha
    did = datos.docente_reemplazo_id

    # La clase puede ser de varias horas seguidas (bloque doble): se asigna al
    # reemplazante en TODAS y se valida en TODAS.
    clase = _bloques_de_la_clase(db, bloque)
    horas_clase = [b.hora for b in clase]
    conflictos = []
    for b in clase:
        for c in validar_reemplazo(db, b, fecha, did):
            etq = f" (en la {b.hora}ª hora)" if len(clase) > 1 else ""
            conflictos.append(c + etq)
    if conflictos:
        raise ValueError("; ".join(dict.fromkeys(conflictos)))

    ausencia = db.scalar(
        select(models.AusenciaDocente).where(
            models.AusenciaDocente.docente_id == bloque.docente_id,
            models.AusenciaDocente.fecha == fecha,
        )
    )
    horas_libres = set(horas_clase)  # ya validado que está libre en todas
    pct, razones = _snapshot_candidato(db, bloque, fecha, did, horas_clase, horas_libres)

    primero = None
    for b in clase:
        reemplazo = db.scalar(
            select(models.Reemplazo).where(
                models.Reemplazo.fecha == fecha,
                models.Reemplazo.bloque_horario_id == b.id,
                models.Reemplazo.estado != "cancelado",
            )
        )
        if reemplazo is None:
            reemplazo = models.Reemplazo(
                fecha=fecha,
                dia=b.dia,
                hora=b.hora,
                grado=b.grado,
                curso=b.curso,
                area_id=b.area_id,
                area_label=b.area_label,
                docente_ausente_id=b.docente_id,
                bloque_horario_id=b.id,
            )
            db.add(reemplazo)
        if ausencia is not None:
            reemplazo.ausencia_id = ausencia.id
        reemplazo.docente_reemplazo_id = did
        reemplazo.estado = "asignado"
        reemplazo.compatibilidad = pct
        reemplazo.razones = razones
        reemplazo.asignado_por = datos.asignado_por
        if primero is None:
            primero = reemplazo

    db.commit()
    db.refresh(primero)
    return _reemplazo_a_schema(db, primero)


def actualizar_reemplazo(
    db: Session, reemplazo_id: int, datos: schemas.ReemplazoActualizar
) -> schemas.Reemplazo:
    reemplazo = db.get(models.Reemplazo, reemplazo_id)
    if reemplazo is None:
        raise ValueError("Reemplazo no encontrado")

    if datos.estado == "cancelado":
        reemplazo.estado = "cancelado"
        reemplazo.docente_reemplazo_id = None
        reemplazo.compatibilidad = None
        reemplazo.razones = None
        db.commit()
        db.refresh(reemplazo)
        return _reemplazo_a_schema(db, reemplazo)

    if datos.docente_reemplazo_id is not None:
        bloque = reemplazo.bloque_horario
        if bloque is None:
            raise ValueError("El reemplazo no está ligado a un bloque de horario")
        # revalida contra todos menos contra este mismo reemplazo
        reemplazo.estado = "cancelado"
        db.flush()
        conflictos = validar_reemplazo(db, bloque, reemplazo.fecha, datos.docente_reemplazo_id)
        if conflictos:
            db.rollback()
            raise ValueError("; ".join(conflictos))
        pct, razones = _snapshot_candidato(db, bloque, reemplazo.fecha, datos.docente_reemplazo_id)
        reemplazo.docente_reemplazo_id = datos.docente_reemplazo_id
        reemplazo.estado = "asignado"
        reemplazo.compatibilidad = pct
        reemplazo.razones = razones
        if datos.asignado_por:
            reemplazo.asignado_por = datos.asignado_por
        db.commit()
        db.refresh(reemplazo)
        return _reemplazo_a_schema(db, reemplazo)

    raise ValueError("Nada que actualizar")


def listar_reemplazos(db: Session, fecha: dt.date) -> list[schemas.Reemplazo]:
    reemplazos = list(
        db.scalars(
            select(models.Reemplazo)
            .where(models.Reemplazo.fecha == fecha)
            .order_by(
                models.Reemplazo.grado, models.Reemplazo.curso, models.Reemplazo.area_label,
                models.Reemplazo.docente_ausente_id, models.Reemplazo.hora,
            )
        ).all()
    )
    # Colapsa un bloque doble (misma ausencia, mismo grupo/área, mismo
    # reemplazante y estado, horas seguidas) en una sola fila con horas=[1,2].
    filas: list[schemas.Reemplazo] = []
    for r in reemplazos:
        prev = filas[-1] if filas else None
        if (
            prev
            and (prev.grado, prev.curso, prev.area_label, prev.docente_ausente_id,
                 prev.docente_reemplazo_id, prev.estado)
            == (r.grado, r.curso, r.area_label, r.docente_ausente_id,
                r.docente_reemplazo_id, r.estado)
            and r.hora == prev.horas[-1] + 1
        ):
            prev.horas.append(r.hora)
            prev.ids.append(r.id)
        else:
            filas.append(_reemplazo_a_schema(db, r))
    filas.sort(key=lambda x: (x.hora, x.grado, x.curso or 0))
    return filas


def eliminar_reemplazo(db: Session, reemplazo_id: int) -> bool:
    reemplazo = db.get(models.Reemplazo, reemplazo_id)
    if reemplazo is None:
        return False
    db.delete(reemplazo)
    db.commit()
    return True


# --- Conflictos de horario (dos docentes para el mismo grupo+hora) ---------


def conflictos_horario(db: Session, anio_lectivo: int) -> list[schemas.ConflictoHorario]:
    """Un conflicto por cada grupo+día+hora con más de un bloque 'activo' que
    todavía nadie ha confirmado. Trae las opciones (los docentes en pugna) para
    que el administrativo elija el oficial o decida dejarlos a los dos."""
    filas = db.scalars(
        select(models.BloqueHorario).where(
            models.BloqueHorario.anio_lectivo == anio_lectivo,
            models.BloqueHorario.estado == "activo",
        )
    ).all()
    por_slot: dict[tuple, list[models.BloqueHorario]] = {}
    for b in filas:
        por_slot.setdefault((b.grado, b.curso, b.dia, b.hora), []).append(b)

    salida = []
    for (grado, curso, dia, hora), bs in sorted(por_slot.items()):
        if len(bs) < 2 or all(b.conflicto_revisado for b in bs):
            continue
        salida.append(
            schemas.ConflictoHorario(
                grado=grado,
                curso=curso,
                grupo=etiqueta_grupo(grado, curso),
                nombre_grupo=nombre_grupo(grado, curso),
                dia=dia,
                dia_nombre=DIAS_NOMBRES.get(dia, str(dia)),
                hora=hora,
                opciones=[
                    schemas.OpcionConflicto(
                        bloque_id=b.id,
                        docente_id=b.docente_id,
                        docente_nombre=b.docente.nombre_completo if b.docente else "",
                        area_label=b.area_label,
                        origen=b.origen,
                    )
                    for b in bs
                ],
            )
        )
    return salida


def resolver_conflicto(db: Session, datos: schemas.ResolverConflicto) -> dict:
    """`accion="oficial"` + `bloque_id`: ese bloque queda como el oficial, los
    demás del mismo grupo+día+hora se marcan 'descartado'.
    `accion="ambos"`: se dejan los dos, solo se marca el conflicto como revisado."""
    slot_bloques = list(
        db.scalars(
            select(models.BloqueHorario).where(
                models.BloqueHorario.anio_lectivo == datos.anio_lectivo,
                models.BloqueHorario.grado == datos.grado,
                models.BloqueHorario.curso == datos.curso
                if datos.curso is not None
                else models.BloqueHorario.curso.is_(None),
                models.BloqueHorario.dia == datos.dia,
                models.BloqueHorario.hora == datos.hora,
                models.BloqueHorario.estado == "activo",
            )
        ).all()
    )
    if len(slot_bloques) < 2:
        raise ValueError("Ese grupo/día/hora ya no tiene un conflicto que resolver")

    ahora = dt.datetime.utcnow()
    descartados = []
    if datos.accion == "oficial":
        if datos.bloque_id not in {b.id for b in slot_bloques}:
            raise ValueError("El bloque elegido no pertenece a este conflicto")
        for b in slot_bloques:
            b.conflicto_revisado = True
            b.resuelto_por = datos.resuelto_por
            b.resuelto_en = ahora
            if b.id != datos.bloque_id:
                b.estado = "descartado"
                descartados.append(b.id)
    elif datos.accion == "ambos":
        for b in slot_bloques:
            b.conflicto_revisado = True
            b.resuelto_por = datos.resuelto_por
            b.resuelto_en = ahora
    else:
        raise ValueError("Acción no reconocida (usa 'oficial' o 'ambos')")

    # Un reemplazo pendiente atado a un bloque que quedó descartado ya no tiene
    # sentido (esa clase no era de ese docente): se elimina.
    if descartados:
        for r in db.scalars(
            select(models.Reemplazo).where(
                models.Reemplazo.bloque_horario_id.in_(descartados),
                models.Reemplazo.estado == "pendiente",
            )
        ):
            db.delete(r)

    # Si tras confirmar el oficial ese docente está ausente ese mismo día en
    # alguna fecha ya registrada, se le crea el pendiente que antes se saltó.
    if datos.accion == "oficial":
        oficial = next(b for b in slot_bloques if b.id == datos.bloque_id)
        for aus in db.scalars(
            select(models.AusenciaDocente).where(
                models.AusenciaDocente.docente_id == oficial.docente_id
            )
        ):
            if _dia_de_fecha(aus.fecha) != datos.dia or aus.fecha.year != datos.anio_lectivo:
                continue
            ya = db.scalar(
                select(models.Reemplazo).where(
                    models.Reemplazo.fecha == aus.fecha,
                    models.Reemplazo.bloque_horario_id == oficial.id,
                    models.Reemplazo.estado != "cancelado",
                )
            )
            if ya is None:
                db.add(
                    models.Reemplazo(
                        fecha=aus.fecha,
                        dia=oficial.dia,
                        hora=oficial.hora,
                        grado=oficial.grado,
                        curso=oficial.curso,
                        area_id=oficial.area_id,
                        area_label=oficial.area_label,
                        docente_ausente_id=oficial.docente_id,
                        bloque_horario_id=oficial.id,
                        ausencia_id=aus.id,
                        estado="pendiente",
                    )
                )

    db.commit()
    return {"resuelto": True, "descartados": descartados}


# --- Panel HOY -----------------------------------------------------------


def panel_hoy(db: Session, fecha: dt.date, ahora: dt.datetime | None = None) -> schemas.PanelHoy:
    anio = fecha.year
    # Si el panel es de otro día (p. ej. preparando los reemplazos de mañana),
    # se usa esa fecha con la hora actual para que día/franja sean coherentes.
    if ahora is None:
        ahora_col = fechas.ahora_colombia().replace(tzinfo=None)
        ahora = (
            ahora_col
            if fecha == ahora_col.date()
            else dt.datetime.combine(fecha, ahora_col.time())
        )
    fr = franja_actual(ahora)
    dia = _dia_de_fecha(fecha)

    estados = estado_docentes(db, fecha, ahora)
    conteo: dict[str, int] = {}
    for e in estados:
        conteo[e.estado] = conteo.get(e.estado, 0) + 1

    clases_programadas = 0
    if dia is not None:
        clases_programadas = (
            db.scalar(
                select(func.count())
                .select_from(models.BloqueHorario)
                .where(
                    models.BloqueHorario.anio_lectivo == anio,
                    models.BloqueHorario.dia == dia,
                    models.BloqueHorario.estado == "activo",
                )
            )
            or 0
        )

    ausencias = listar_ausencias(db, fecha)
    clases_por_reemplazar = sum(
        1
        for a in ausencias
        for c in a.clases_afectadas
        if c.reemplazo_estado in (None, "pendiente", "parcial")
    )

    return schemas.PanelHoy(
        fecha=fecha,
        dia=dia,
        dia_nombre=fr["dia_nombre"],
        franja=fr,
        docentes_libres=conteo.get("libre", 0),
        docentes_en_clase=conteo.get("en_clase", 0),
        docentes_ausentes=conteo.get("ausente", 0),
        docentes_cubriendo=conteo.get("cubriendo", 0),
        docentes_descanso=conteo.get("descanso", 0),
        docentes_fuera_jornada=conteo.get("fuera_jornada", 0),
        clases_programadas=clases_programadas,
        clases_necesitan_reemplazo=clases_por_reemplazar,
        conflictos_pendientes=len(_slots_en_conflicto(db, anio)),
        ausencias=ausencias,
        reemplazos=listar_reemplazos(db, fecha),
    )


# --- Abrir hueco / asignar una clase nueva ---------------------------------

PESOS_HUECO = {
    "continuidad_grupo": 34,  # pegada a otra clase del profe con ESE grupo el mismo día
    "continuidad": 12,        # pegada a cualquier clase del profe el mismo día
    "dia_que_trabaja": 16,    # el profe ya viene ese día (no un día extra por 1 hora)
    "dia_liviano": 8,         # ese día el profe tiene poca carga
    "nivel": 8,               # el profe trabaja en ese nivel
    "hueco_intermedio": 6,    # el grupo tiene clase antes y después (tapa un hueco)
    "hora_central": 4,        # 2ª a 5ª hora
}
_MAX_HUECO = sum(PESOS_HUECO.values())


def _slots_ocupados_docente(db: Session, docente_id: int, anio: int) -> set[tuple[int, int]]:
    return {
        (b.dia, b.hora)
        for b in db.scalars(
            select(models.BloqueHorario).where(
                models.BloqueHorario.anio_lectivo == anio,
                models.BloqueHorario.docente_id == docente_id,
                models.BloqueHorario.estado == "activo",
            )
        ).all()
    }


def _slots_ocupados_grupo(db: Session, grado: int, curso: int | None, anio: int) -> set[tuple[int, int]]:
    """(dia, hora) que el grupo ya tiene ocupadas. Una clase de grado sin
    división (curso NULL) ocupa a TODAS las divisiones; y si el objetivo es
    'todo el grado' (curso None), cualquier división cuenta."""
    out: set[tuple[int, int]] = set()
    for b in db.scalars(
        select(models.BloqueHorario).where(
            models.BloqueHorario.anio_lectivo == anio,
            models.BloqueHorario.grado == grado,
            models.BloqueHorario.estado == "activo",
        )
    ).all():
        if curso is None or b.curso is None or b.curso == curso:
            out.add((b.dia, b.hora))
    return out


def huecos_para_asignar(
    db: Session,
    docente_id: int,
    grado: int,
    curso: int | None,
    area_id: int | None,
    anio_lectivo: int,
    horas: int = 1,
) -> schemas.HuecosRespuesta:
    """Sugiere en qué día+hora meter una clase nueva de `area` para `docente`
    en el grupo `grado-curso`. Requisito duro: el PROFE tiene que estar libre
    (no se le hace doble clase). El GRUPO puede estar lleno — en ese caso se
    proponen las franjas menos costosas para 'abrir el hueco' desplazando una
    clase (y se dice cuál). Ordena: franjas libres primero, luego por qué tan
    buena / poco disruptiva es la ubicación."""
    docente = db.get(models.Docente, docente_id)
    if docente is None:
        raise ValueError("Docente no encontrado")
    area = db.get(models.Area, area_id) if area_id else None
    horas = 2 if horas == 2 else 1

    ocup_doc = _slots_ocupados_docente(db, docente_id, anio_lectivo)
    ocup_grp = _slots_ocupados_grupo(db, grado, curso, anio_lectivo)
    # bloques del grupo por (dia,hora) + horas/semana por área del grupo
    bloques_grp = [
        b
        for b in db.scalars(
            select(models.BloqueHorario).where(
                models.BloqueHorario.anio_lectivo == anio_lectivo,
                models.BloqueHorario.grado == grado,
                models.BloqueHorario.estado == "activo",
            )
        ).all()
        if curso is None or b.curso is None or b.curso == curso
    ]
    grp_por_slot: dict[tuple[int, int], list] = {}
    horas_area: dict[str, int] = {}
    for b in bloques_grp:
        grp_por_slot.setdefault((b.dia, b.hora), []).append(b)
        horas_area[b.area_label] = horas_area.get(b.area_label, 0) + 1

    mis = _bloques_de(db, docente_id, anio_lectivo)
    por_dia_doc: dict[int, list] = {}
    for b in mis:
        por_dia_doc.setdefault(b.dia, []).append(b)
    nivel_obj = nivel_de_grado(grado)
    trabaja_nivel = any(nivel_de_grado(b.grado) == nivel_obj for b in mis)
    prim_nombre = docente.nombre_completo.split()[0].title()

    huecos: list[schemas.HuecoHorario] = []
    for dia in (1, 2, 3, 4, 5):
        for hora in (1, 2, 3, 4, 5, 6):
            rango = [hora] if horas == 1 else [hora, hora + 1]
            if rango[-1] > 6:
                continue
            if any((dia, h) in ocup_doc for h in rango):
                continue  # duro: no se le hace doble clase al profe

            razones: list[tuple[str, str]] = []
            puntos = 0
            clases_dia = por_dia_doc.get(dia, [])

            # ¿el grupo tiene libre TODO el rango?
            ocupa_bloques = [b for h in rango for b in grp_por_slot.get((dia, h), [])]
            libre = not ocupa_bloques

            cont_grupo = any(
                b.grado == grado and b.curso == curso and min(abs(b.hora - h) for h in rango) == 1
                for b in clases_dia
            )
            cont_gen = any(min(abs(b.hora - h) for h in rango) == 1 for b in clases_dia)
            if cont_grupo:
                puntos += PESOS_HUECO["continuidad_grupo"]
                razones.append(("ok", f"Queda pegada a otra clase que {prim_nombre} ya tiene con ese grupo ese día"))
            elif cont_gen:
                puntos += PESOS_HUECO["continuidad"]
                razones.append(("ok", "Queda pegada a otra clase del profesor ese día"))

            if clases_dia:
                puntos += PESOS_HUECO["dia_que_trabaja"]
                razones.append(("ok", f"El profesor ya trabaja el {DIAS_NOMBRES[dia].lower()} ({len(clases_dia)} clase(s))"))
            else:
                razones.append(("warn", f"El profesor NO tiene clases el {DIAS_NOMBRES[dia].lower()} — sería un día nuevo para él"))

            puntos += PESOS_HUECO["dia_liviano"] * max(0, 6 - len(clases_dia)) // 6

            if trabaja_nivel:
                puntos += PESOS_HUECO["nivel"]
                razones.append(("ok", f"El profesor trabaja en {nivel_obj}"))
            else:
                razones.append(("warn", f"El profesor no trabaja normalmente en {nivel_obj}"))

            if libre and (dia, rango[0] - 1) in ocup_grp and (dia, rango[-1] + 1) in ocup_grp:
                puntos += PESOS_HUECO["hueco_intermedio"]
                razones.append(("ok", "Tapa un hueco del grupo (ya tiene clase la hora anterior y la siguiente)"))

            if hora >= 2 and rango[-1] <= 5:
                puntos += PESOS_HUECO["hora_central"]

            ocupa: list[schemas.OcupaSlot] = []
            if not libre:
                razones.append(("warn", "El grupo tiene esa franja OCUPADA — se abriría el hueco quitando:"))
                costo = 0
                for b in ocupa_bloques:
                    hsem = horas_area.get(b.area_label, 1)
                    ocupa.append(
                        schemas.OcupaSlot(
                            bloque_id=b.id,
                            docente_id=b.docente_id,
                            docente_nombre=b.docente.nombre_completo if b.docente else "",
                            area_label=b.area_label,
                            horas_area_semana=hsem,
                        )
                    )
                    if b.origen == "manual":
                        costo += 1
                    elif hsem >= 4:
                        costo += 2
                    elif hsem == 3:
                        costo += 4
                    elif hsem == 2:
                        costo += 7
                    else:
                        costo += 12  # es la ÚNICA hora de esa área ese grupo
                    if (b.area_label or "").upper().startswith(("DESEMP", "COMPORT")):
                        costo += 6
                    razones.append(
                        ("warn", f"· {b.area_label} de {b.docente.nombre_completo if b.docente else '—'} ({hsem} h/sem del grupo)")
                    )
                puntos -= costo * 5  # cuanto más duele quitar la clase, peor la sugerencia

            base = round(puntos / _MAX_HUECO * 100)
            huecos.append(
                schemas.HuecoHorario(
                    dia=dia,
                    nombre_dia=DIAS_NOMBRES[dia],
                    hora=hora,
                    hora_fin=rango[-1],
                    franja=f"{FRANJAS[hora - 1]['inicio']}–{FRANJAS[rango[-1] - 1]['fin']}",
                    horas=len(rango),
                    puntaje=max(0, min(100, base + (10 if libre else 0))),
                    continuidad=cont_grupo,
                    libre=libre,
                    ocupa=ocupa,
                    razones=[schemas.RazonReemplazo(tipo=t, texto=x) for t, x in razones],
                )
            )

    huecos.sort(key=lambda h: (not h.libre, -h.puntaje, h.dia, h.hora))
    return schemas.HuecosRespuesta(
        docente_id=docente_id,
        docente_nombre=docente.nombre_completo,
        grado=grado,
        curso=curso,
        grupo=etiqueta_grupo(grado, curso),
        nombre_grupo=nombre_grupo(grado, curso),
        area_id=area_id,
        area_label=(area.nombre if area else ""),
        horas=horas,
        total_libres=sum(1 for h in huecos if h.libre),
        huecos=huecos,
        ocupados=sorted([list(x) for x in ocup_grp]),
    )


def crear_bloque_horario(db: Session, datos: schemas.CrearBloqueHorario) -> list[schemas.BloqueHorario]:
    anio = datos.anio_lectivo or dt.date.today().year
    docente = db.get(models.Docente, datos.docente_id)
    if docente is None:
        raise ValueError("Docente no encontrado")
    area = db.get(models.Area, datos.area_id) if datos.area_id else None
    horas = 2 if datos.horas == 2 else 1
    rango = [datos.hora] if horas == 1 else [datos.hora, datos.hora + 1]
    if datos.dia not in (1, 2, 3, 4, 5) or datos.hora < 1 or rango[-1] > 6:
        raise ValueError("Día u hora fuera de la jornada (Lun–Vie, 1ª–6ª).")

    # 1) Si se pidió desplazar clases del grupo para abrir el hueco, se
    #    borran PRIMERO — y solo si de verdad están en esa franja de ese grupo.
    desplazados: list[str] = []
    for bid in datos.desplazar_bloque_ids or []:
        b = db.get(models.BloqueHorario, bid)
        if b is None:
            continue
        mismo_grupo = b.grado == datos.grado and (
            datos.curso is None or b.curso is None or b.curso == datos.curso
        )
        if not (mismo_grupo and b.dia == datos.dia and b.hora in rango):
            raise ValueError(
                "Una de las clases a quitar no corresponde a esa franja de ese grupo — refresca y vuelve a intentar."
            )
        desplazados.append(f"{b.area_label} de {b.docente.nombre_completo if b.docente else '—'} ({DIAS_NOMBRES[b.dia]} {b.hora}ª)")
        soltar_reemplazos_de_bloques(db, [b.id])
        db.delete(b)
    db.flush()

    ocup_doc = _slots_ocupados_docente(db, datos.docente_id, anio)
    ocup_grp = _slots_ocupados_grupo(db, datos.grado, datos.curso, anio)
    for h in rango:
        if (datos.dia, h) in ocup_doc:
            raise ValueError(
                f"{docente.nombre_completo} ya tiene clase el {DIAS_NOMBRES[datos.dia]} en la {h}ª hora."
            )
        if (datos.dia, h) in ocup_grp:
            raise ValueError(
                f"El grupo {etiqueta_grupo(datos.grado, datos.curso)} sigue con clase el {DIAS_NOMBRES[datos.dia]} en la {h}ª hora — quita también esa antes."
            )

    label = ((area.nombre if area else (datos.area_label or "")).strip()) or "SIN ÁREA"
    creados: list[models.BloqueHorario] = []
    for h in rango:
        b = models.BloqueHorario(
            anio_lectivo=anio,
            docente_id=datos.docente_id,
            sede_id=SEDE_HORARIO_ID,
            grado=datos.grado,
            curso=datos.curso,
            area_id=datos.area_id,
            area_label=label,
            dia=datos.dia,
            hora=h,
            aula=datos.aula,
            origen="manual",
            estado="activo",
        )
        db.add(b)
        creados.append(b)

    if datos.crear_asignacion and datos.area_id:
        ya = db.scalar(
            select(models.AsignacionDocente).where(
                models.AsignacionDocente.anio_lectivo == anio,
                models.AsignacionDocente.sede_id == SEDE_HORARIO_ID,
                models.AsignacionDocente.grado == datos.grado,
                models.AsignacionDocente.curso == datos.curso,
                models.AsignacionDocente.area_id == datos.area_id,
            )
        )
        if ya is None:
            db.add(
                models.AsignacionDocente(
                    docente_id=datos.docente_id,
                    sede_id=SEDE_HORARIO_ID,
                    grado=datos.grado,
                    curso=datos.curso,
                    area_id=datos.area_id,
                    anio_lectivo=anio,
                )
            )

    db.commit()
    for b in creados:
        db.refresh(b)
    return [_bloque_a_schema(b) for b in creados]


def soltar_reemplazos_de_bloques(db: Session, bloque_ids) -> None:
    """Antes de borrar bloques del horario: sus reemplazos pierden solo el
    enlace (bloque_horario_id = NULL). Un Reemplazo guarda todo lo que
    describe la clase cubierta, así que sigue siendo válido sin su bloque.
    Con las claves foráneas activas, borrar el bloque sin esto fallaría; y
    antes el id quedaba colgando, y podía terminar apuntando a otro bloque
    si SQLite reutilizaba ese id. `bloque_ids` puede ser una lista o un
    select() de ids."""
    db.execute(
        update(models.Reemplazo)
        .where(models.Reemplazo.bloque_horario_id.in_(bloque_ids))
        .values(bloque_horario_id=None)
        .execution_options(synchronize_session=False)
    )


def eliminar_bloque_horario(db: Session, bloque_id: int) -> bool:
    b = db.get(models.BloqueHorario, bloque_id)
    if b is None:
        return False
    soltar_reemplazos_de_bloques(db, [b.id])
    db.delete(b)
    db.commit()
    return True


# --- Búsqueda rápida ---------------------------------------------------------


def buscar(db: Session, q: str, anio_lectivo: int) -> schemas.ResultadoBusqueda:
    objetivo = normalizar(q)
    docentes_res = []
    grupos_res = []
    areas_res = []
    if not objetivo:
        return schemas.ResultadoBusqueda(docentes=[], grupos=[], areas=[])

    con_horario = _ids_con_horario(db, anio_lectivo)
    for d in db.scalars(select(models.Docente).order_by(models.Docente.nombre_completo)).all():
        if objetivo in normalizar(d.nombre_completo):
            docentes_res.append(
                schemas.BusquedaItem(tipo="docente", id=d.id, texto=d.nombre_completo, con_horario=d.id in con_horario)
            )

    grupos = db.execute(
        select(models.BloqueHorario.grado, models.BloqueHorario.curso)
        .where(models.BloqueHorario.anio_lectivo == anio_lectivo)
        .distinct()
    ).all()
    for grado, curso in sorted(set(grupos)):
        etq = etiqueta_grupo(grado, curso)
        nom = nombre_grupo(grado, curso)
        if objetivo in normalizar(etq) or objetivo in normalizar(nom):
            grupos_res.append(
                schemas.BusquedaItem(tipo="grupo", id=None, texto=nom, grado=grado, curso=curso)
            )

    vistos = set()
    for b in db.scalars(
        select(models.BloqueHorario).where(models.BloqueHorario.anio_lectivo == anio_lectivo)
    ).all():
        clave = (b.area_id, b.area_label)
        if clave in vistos:
            continue
        nom = b.area.nombre if b.area else b.area_label
        if objetivo in normalizar(nom) or objetivo in normalizar(b.area_label):
            vistos.add(clave)
            areas_res.append(
                schemas.BusquedaItem(tipo="area", id=b.area_id, texto=nom, area_label=b.area_label)
            )

    return schemas.ResultadoBusqueda(docentes=docentes_res, grupos=grupos_res, areas=areas_res)
