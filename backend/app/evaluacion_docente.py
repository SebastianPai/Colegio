"""Evaluación del rendimiento por docente: indicadores con semáforo, puntos
de atención y fortalezas, cada uno con su evidencia (qué grupo, qué materia,
qué estudiantes). Decisión del colegio (24/09/2026): indicadores + semáforo,
SIN nota única ni ranking; solo coordinación/administración lo ven
(permiso docentes.evaluar). El Desempeño Actitudinal (DESM) va aparte.

Todo sale de comparacion_academica.comparar() — las mismas filas
estudiante+área que el resto del Análisis académico — así cada número se
puede rastrear hasta la nota real. Límite que la pantalla debe decir: las
notas las pone el MISMO docente evaluado, así que un promedio bajo puede
reflejar exigencia al calificar; por eso el indicador más justo es la
"brecha con el grupo" (su materia frente a las otras materias de los mismos
estudiantes), no el promedio a secas."""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from . import comparacion_academica as motor
from . import crud, models, schemas

# --- Umbrales del semáforo (a la vista del usuario en EstadoDocentes.umbrales) ---
MIN_EVALUADOS = 5  # por debajo, el indicador sale en gris: muy pocos datos para concluir
PROMEDIO_VERDE, PROMEDIO_ROJO = 3.5, 3.0  # >= 3.5 verde · < 3.0 rojo
BAJO_AMARILLO, BAJO_ROJO = 15.0, 30.0  # % de estudiantes en desempeño bajo
VARIACION_AMARILLO, VARIACION_ROJO = -0.1, -0.3  # caída del promedio entre períodos
BRECHA_AMARILLO, BRECHA_ROJO = -0.3, -0.6  # su materia vs. las otras del mismo grupo
PENDIENTES_ROJO = 5  # notas/conceptos sin cargar en SAPRED
# Puntos de atención por materia-grupo: caída del promedio de 0.3 (amarillo) / 0.5 (rojo).
CAIDA_PUNTO_AMARILLO, CAIDA_PUNTO_ROJO = -0.3, -0.5

UMBRALES_TEXTO = [
    f"Promedio: verde desde {PROMEDIO_VERDE:.1f}; amarillo entre {PROMEDIO_ROJO:.1f} y {PROMEDIO_VERDE:.1f}; rojo por debajo de {PROMEDIO_ROJO:.1f}.",
    f"Desempeño bajo: verde menos del {BAJO_AMARILLO:.0f}% de sus estudiantes; amarillo hasta el {BAJO_ROJO:.0f}%; rojo más del {BAJO_ROJO:.0f}%.",
    f"Variación entre períodos: rojo si el promedio cae más de {abs(VARIACION_ROJO):.1f}; amarillo si cae más de {abs(VARIACION_AMARILLO):.1f}.",
    f"Brecha con el grupo (su materia frente a las otras materias de los MISMOS estudiantes): rojo si está {abs(BRECHA_ROJO):.1f} o más por debajo; amarillo desde {abs(BRECHA_AMARILLO):.1f}. Es el indicador más justo: controla qué tan fuerte es el grupo.",
    f"Notas pendientes en SAPRED: verde sin pendientes; amarillo de 1 a {PENDIENTES_ROJO}; rojo más de {PENDIENTES_ROJO}.",
    f"Con menos de {MIN_EVALUADOS} estudiantes evaluados el indicador sale en gris (muy pocos datos para concluir).",
]


def _media(valores: list[float]) -> float | None:
    return round(sum(valores) / len(valores), 2) if valores else None


def _evidencia(f: schemas.FilaComparacionAcademica) -> schemas.EstudianteEvidencia:
    return schemas.EstudianteEvidencia(
        estudiante_id=f.estudiante_id, nombre_completo=f.nombre_completo, documento=f.documento,
        nombre_grupo=f.nombre_grupo, valor_base=f.valor_base, valor_comparado=f.valor_comparado,
        delta=f.delta, nivel_comparado=f.nivel_comparado,
    )


# --- Una materia en un grupo --------------------------------------------------


@dataclass
class _Asignacion:
    docente_id: int | None
    docente_nombre: str | None
    area_id: int
    area_nombre: str
    sede_nombre: str
    grado: int
    curso: int | None
    nombre_grupo: str
    filas: list[schemas.FilaComparacionAcademica] = field(default_factory=list)


def _agrupar(filas: list[schemas.FilaComparacionAcademica]) -> list[_Asignacion]:
    grupos: dict[tuple, _Asignacion] = {}
    for f in filas:
        clave = (f.docente_id, f.area_id, f.sede_id, f.grado, f.curso)
        if clave not in grupos:
            grupos[clave] = _Asignacion(
                docente_id=f.docente_id, docente_nombre=f.docente_nombre, area_id=f.area_id, area_nombre=f.area_nombre,
                sede_nombre=f.sede_nombre, grado=f.grado, curso=f.curso, nombre_grupo=f.nombre_grupo,
            )
        grupos[clave].filas.append(f)
    return list(grupos.values())


def _otras_por_estudiante(filas: list[schemas.FilaComparacionAcademica]) -> dict[int, dict[int, float]]:
    """estudiante_id -> {area_id: valor del período comparado} (académicas)."""
    resultado: dict[int, dict[int, float]] = {}
    for f in filas:
        if f.valor_comparado is not None:
            resultado.setdefault(f.estudiante_id, {})[f.area_id] = f.valor_comparado
    return resultado


def _evaluar_asignacion(a: _Asignacion, otras: dict[int, dict[int, float]] | None) -> schemas.AsignacionEvaluada:
    con_actual = [f for f in a.filas if f.valor_comparado is not None]
    comparables = [f for f in a.filas if f.comparable]
    n = len(con_actual)
    n_bajo = sum(1 for f in con_actual if f.nivel_comparado == "BAJO")
    promedio_comparado = _media([f.valor_comparado for f in con_actual])
    promedio_otras = brecha = None
    if otras is not None:
        # Solo estudiantes que tienen esta materia Y al menos otra: mismos estudiantes en ambos lados.
        propias, ajenas = [], []
        for f in con_actual:
            resto = [v for area_id, v in otras.get(f.estudiante_id, {}).items() if area_id != a.area_id]
            if resto:
                propias.append(f.valor_comparado)
                ajenas.append(sum(resto) / len(resto))
        if propias:
            promedio_otras = _media(ajenas)
            brecha = round(sum(propias) / len(propias) - sum(ajenas) / len(ajenas), 2)
    return schemas.AsignacionEvaluada(
        docente_id=a.docente_id, docente_nombre=a.docente_nombre, area_id=a.area_id, area_nombre=a.area_nombre,
        sede_nombre=a.sede_nombre, grado=a.grado, curso=a.curso, nombre_grupo=a.nombre_grupo,
        evaluados=n,
        promedio_base=_media([f.valor_base for f in comparables]),
        promedio_comparado=promedio_comparado,
        variacion=round(sum(f.delta for f in comparables) / len(comparables), 2) if comparables else None,
        n_bajo=n_bajo, pct_bajo=round(n_bajo / n * 100, 1) if n else 0.0,
        entraron_a_bajo=sum(1 for f in comparables if f.nivel_base != "BAJO" and f.nivel_comparado == "BAJO"),
        salieron_de_bajo=sum(1 for f in comparables if f.nivel_base == "BAJO" and f.nivel_comparado != "BAJO"),
        promedio_otras_materias=promedio_otras, brecha_grupo=brecha,
    )


# --- Semáforo -----------------------------------------------------------------


def _semaforo_mayor(valor, verde_desde, rojo_bajo):
    if valor is None:
        return "gris"
    return "verde" if valor >= verde_desde else "rojo" if valor < rojo_bajo else "amarillo"


def _indicadores(
    filas: list[schemas.FilaComparacionAcademica], asignaciones: list[schemas.AsignacionEvaluada], pendientes: int,
) -> list[schemas.IndicadorDocente]:
    con_actual = [f for f in filas if f.valor_comparado is not None]
    comparables = [f for f in filas if f.comparable]
    n = len(con_actual)
    pocos = n < MIN_EVALUADOS
    promedio = _media([f.valor_comparado for f in con_actual])
    pct_bajo = round(sum(1 for f in con_actual if f.nivel_comparado == "BAJO") / n * 100, 1) if n else None
    variacion = round(sum(f.delta for f in comparables) / len(comparables), 2) if comparables else None
    con_brecha = [a for a in asignaciones if a.brecha_grupo is not None and a.evaluados >= MIN_EVALUADOS]
    peor = min(con_brecha, key=lambda a: a.brecha_grupo) if con_brecha else None

    def sem_bajo(v):
        if v is None:
            return "gris"
        return "rojo" if v > BAJO_ROJO else "amarillo" if v > BAJO_AMARILLO else "verde"

    def sem_caida(v, amarillo, rojo):
        if v is None:
            return "gris"
        return "rojo" if v < rojo else "amarillo" if v < amarillo else "verde"

    return [
        schemas.IndicadorDocente(
            clave="promedio", nombre="Promedio de sus estudiantes", valor=promedio,
            texto=f"{promedio:.2f}" if promedio is not None else "—",
            semaforo="gris" if pocos else _semaforo_mayor(promedio, PROMEDIO_VERDE, PROMEDIO_ROJO),
            explicacion=f"Promedio de las notas que puso en el período comparado ({n} notas).",
        ),
        schemas.IndicadorDocente(
            clave="bajo", nombre="Estudiantes en desempeño bajo", valor=pct_bajo,
            texto=f"{pct_bajo:.0f}%" if pct_bajo is not None else "—",
            semaforo="gris" if pocos else sem_bajo(pct_bajo),
            explicacion="Porcentaje de sus notas por debajo de 3.0 (desempeño bajo) en el período comparado.",
        ),
        schemas.IndicadorDocente(
            clave="variacion", nombre="Variación entre períodos", valor=variacion,
            texto=f"{variacion:+.2f}" if variacion is not None else "—",
            semaforo="gris" if len(comparables) < MIN_EVALUADOS else sem_caida(variacion, VARIACION_AMARILLO, VARIACION_ROJO),
            explicacion=f"Cambio promedio de los mismos estudiantes entre los dos períodos ({len(comparables)} comparables).",
        ),
        schemas.IndicadorDocente(
            clave="brecha", nombre="Brecha con el mismo grupo", valor=peor.brecha_grupo if peor else None,
            texto=f"{peor.brecha_grupo:+.2f}" if peor else "—",
            semaforo=sem_caida(peor.brecha_grupo, BRECHA_AMARILLO, BRECHA_ROJO) if peor else "gris",
            explicacion=(
                f"Su peor grupo: {peor.area_nombre} en {peor.nombre_grupo} ({peor.promedio_comparado:.2f}) frente a las otras "
                f"materias de esos mismos estudiantes ({peor.promedio_otras_materias:.2f})." if peor
                else "Sin grupos con datos suficientes para comparar."
            ),
        ),
        schemas.IndicadorDocente(
            clave="pendientes", nombre="Notas pendientes en SAPRED", valor=float(pendientes), texto=str(pendientes),
            semaforo="verde" if pendientes == 0 else "rojo" if pendientes > PENDIENTES_ROJO else "amarillo",
            explicacion="Notas, conceptos u observaciones que la auditoría con SAPRED encontró sin cargar.",
        ),
    ]


# --- Puntos de atención y fortalezas ------------------------------------------


def _puntos(
    asig: list[schemas.AsignacionEvaluada], filas_por_asig: dict[tuple, list[schemas.FilaComparacionAcademica]],
    pendientes: int, periodo: int,
) -> tuple[list[schemas.PuntoAtencion], list[schemas.PuntoAtencion]]:
    puntos: list[schemas.PuntoAtencion] = []
    fortalezas: list[schemas.PuntoAtencion] = []
    for a in asig:
        filas = filas_por_asig[(a.area_id, a.grado, a.curso, a.sede_nombre)]
        if a.evaluados < MIN_EVALUADOS:
            continue
        donde = dict(area_nombre=a.area_nombre, nombre_grupo=a.nombre_grupo)
        if a.pct_bajo > BAJO_AMARILLO and a.n_bajo >= 2:
            puntos.append(schemas.PuntoAtencion(
                nivel="rojo" if a.pct_bajo > BAJO_ROJO else "amarillo",
                titulo=f"{a.n_bajo} de {a.evaluados} estudiantes en desempeño bajo en {a.area_nombre} ({a.nombre_grupo})",
                detalle=f"El {a.pct_bajo:.0f}% del grupo tiene nota menor a 3.0 en esta materia en el período comparado.",
                estudiantes=[_evidencia(f) for f in sorted(filas, key=lambda f: f.valor_comparado or 0) if f.nivel_comparado == "BAJO"],
                **donde,
            ))
        if a.variacion is not None and a.variacion <= CAIDA_PUNTO_AMARILLO:
            puntos.append(schemas.PuntoAtencion(
                nivel="rojo" if a.variacion <= CAIDA_PUNTO_ROJO else "amarillo",
                titulo=f"El promedio de {a.area_nombre} en {a.nombre_grupo} bajó {abs(a.variacion):.2f}",
                detalle=f"Pasó de {a.promedio_base:.2f} a {a.promedio_comparado:.2f} con los mismos estudiantes."
                + (f" {a.entraron_a_bajo} pasaron a desempeño bajo." if a.entraron_a_bajo else ""),
                estudiantes=[_evidencia(f) for f in sorted(filas, key=lambda f: f.delta or 0) if f.comparable and f.delta is not None and f.delta <= -0.3],
                **donde,
            ))
        if a.brecha_grupo is not None and a.brecha_grupo <= BRECHA_AMARILLO:
            puntos.append(schemas.PuntoAtencion(
                nivel="rojo" if a.brecha_grupo <= BRECHA_ROJO else "amarillo",
                titulo=f"{a.nombre_grupo} rinde {abs(a.brecha_grupo):.2f} menos en {a.area_nombre} que en sus otras materias",
                detalle=f"Promedio en esta materia {a.promedio_comparado:.2f}; los mismos estudiantes promedian {a.promedio_otras_materias:.2f} en las demás. "
                "Puede indicar dificultades en la materia o una forma de calificar más exigente: vale la pena revisarlo con el docente.",
                **donde,
            ))
        # Fortalezas: lo que va bien también se muestra.
        if a.variacion is not None and a.variacion >= 0.3:
            fortalezas.append(schemas.PuntoAtencion(
                nivel="fortaleza", titulo=f"El promedio de {a.area_nombre} en {a.nombre_grupo} subió {a.variacion:.2f}",
                detalle=f"Pasó de {a.promedio_base:.2f} a {a.promedio_comparado:.2f}."
                + (f" {a.salieron_de_bajo} salieron de desempeño bajo." if a.salieron_de_bajo else ""),
                **donde,
            ))
        elif a.salieron_de_bajo >= 2:
            fortalezas.append(schemas.PuntoAtencion(
                nivel="fortaleza", titulo=f"{a.salieron_de_bajo} estudiantes salieron de desempeño bajo en {a.area_nombre} ({a.nombre_grupo})",
                detalle="Tenían nota menor a 3.0 en el período base y ya no.", **donde,
            ))
    if pendientes:
        puntos.append(schemas.PuntoAtencion(
            nivel="rojo" if pendientes > PENDIENTES_ROJO else "amarillo",
            titulo=f"{pendientes} nota(s) o concepto(s) pendientes de cargar en SAPRED (período {periodo})",
            detalle="Según la última auditoría con SAPRED. El detalle está en Boletines, «Por docente».",
        ))
    orden = {"rojo": 0, "amarillo": 1}
    puntos.sort(key=lambda p: orden.get(p.nivel, 2))
    return puntos, fortalezas


# --- Entradas públicas ---------------------------------------------------------


# Caché corta del cálculo pesado (notas de dos períodos + pendientes): la
# lista de docentes y luego la ficha de uno piden lo mismo. La clave incluye
# una "huella" de los datos (cuántas notas/pendientes hay y el último id), así
# un import nuevo de SAPRED o una auditoría invalida la caché sola.
_CACHE: dict = {}
_CACHE_SEGUNDOS = 300


def _huella(db: Session) -> tuple:
    from sqlalchemy import func, select

    return (
        db.scalar(select(func.count(models.NotaSapred.id))), db.scalar(select(func.max(models.NotaSapred.id))),
        db.scalar(select(func.max(models.NotaSapred.actualizado_en))),
        db.scalar(select(func.count(models.PendienteBoletin.id)).where(models.PendienteBoletin.resuelto.is_(False))),
        db.scalar(select(func.max(models.AsignacionDocente.id))),
    )


def _preparar(db: Session, p: dict):
    import time

    clave = (repr(sorted((k, repr(v)) for k, v in p.items() if k != "docente_id")), _huella(db))
    guardado = _CACHE.get(clave)
    if guardado and time.monotonic() - guardado[0] < _CACHE_SEGUNDOS:
        return guardado[1]
    resultado = _preparar_sin_cache(db, p)
    _CACHE.clear()  # una sola entrada: basta para lista -> ficha, y no crece
    _CACHE[clave] = (time.monotonic(), resultado)
    return resultado


def _preparar_sin_cache(db: Session, p: dict):
    filas_todas = motor.comparar(db, **{k: v for k, v in p.items() if k != "docente_id"}, incluir_actitudinal=True)
    academicas = [f for f in filas_todas if f.area_codigo != motor.AREA_ACTITUDINAL]
    actitudinales = [f for f in filas_todas if f.area_codigo == motor.AREA_ACTITUDINAL]
    anio, periodo = p["comparado"]
    pendientes = {
        d.docente.id: (d.abiertos, d.por_tipo)
        for d in crud.pendientes_por_docente(db, anio, periodo).docentes
    }
    return academicas, actitudinales, pendientes, periodo


def _ficha(
    docente_id: int, nombre: str, academicas: list, actitudinales: list, otras: dict, pendientes: dict, periodo: int,
) -> tuple[schemas.FichaDocenteResumen, list, list, list, list, dict]:
    mis = [f for f in academicas if f.docente_id == docente_id]
    grupos_asig = _agrupar(mis)
    asig = [_evaluar_asignacion(a, otras) for a in grupos_asig]
    asig.sort(key=lambda a: (a.grado, a.curso or 0, a.area_nombre))
    filas_por_asig = {(a.area_id, a.grado, a.curso, a.sede_nombre): a.filas for a in grupos_asig}
    abiertos, por_tipo = pendientes.get(docente_id, (0, {}))
    indicadores = _indicadores(mis, asig, abiertos)
    puntos, fortalezas = _puntos(asig, filas_por_asig, abiertos, periodo)
    mis_act = [f for f in actitudinales if f.docente_id == docente_id]
    act = [_evaluar_asignacion(a, None) for a in _agrupar(mis_act)]
    resumen = schemas.FichaDocenteResumen(
        docente_id=docente_id, docente_nombre=nombre,
        areas=sorted({a.area_nombre for a in asig}), grupos=sorted({a.nombre_grupo for a in asig}),
        evaluados=sum(a.evaluados for a in asig), indicadores=indicadores,
        rojos=sum(1 for i in indicadores if i.semaforo == "rojo"),
        amarillos=sum(1 for i in indicadores if i.semaforo == "amarillo"),
        puntos_atencion=len(puntos), fortalezas=len(fortalezas),
        dicta_actitudinal=bool(mis_act),
        promedio_actitudinal=_media([f.valor_comparado for f in mis_act if f.valor_comparado is not None]),
    )
    return resumen, asig, act, puntos, fortalezas, por_tipo


def _periodos(db: Session, p: dict):
    disponibles = motor.periodos_disponibles(db)
    return motor.periodo_disponible(disponibles, *p["base"]), motor.periodo_disponible(disponibles, *p["comparado"])


def estado_docentes(db: Session, p: dict) -> schemas.EstadoDocentes:
    academicas, actitudinales, pendientes, periodo = _preparar(db, p)
    otras = _otras_por_estudiante(academicas)
    nombres = {f.docente_id: f.docente_nombre for f in academicas + actitudinales if f.docente_id is not None}
    fichas = []
    for docente_id, nombre in nombres.items():
        if not any(f.docente_id == docente_id for f in academicas):
            continue  # solo pone Desempeño Actitudinal: no hay evaluación académica que mostrar
        fichas.append(_ficha(docente_id, nombre or "", academicas, actitudinales, otras, pendientes, periodo)[0])
    fichas.sort(key=lambda d: d.docente_nombre)

    con_actual = [f for f in academicas if f.valor_comparado is not None]
    comparables = [f for f in academicas if f.comparable]
    act_actual = [f for f in actitudinales if f.valor_comparado is not None]
    pb, pc = _periodos(db, p)
    con_rojo = sum(1 for d in fichas if d.rojos)
    con_amarillo = sum(1 for d in fichas if not d.rojos and d.amarillos)
    promedio = _media([f.valor_comparado for f in con_actual])
    pct_bajo = round(sum(1 for f in con_actual if f.nivel_comparado == "BAJO") / len(con_actual) * 100, 1) if con_actual else 0.0
    variacion = round(sum(f.delta for f in comparables) / len(comparables), 2) if comparables else None
    pendientes_total = sum(v[0] for k, v in pendientes.items() if k in {d.docente_id for d in fichas})
    texto = (
        f"En el período {pc.periodo} ({pc.anio_lectivo}) se analizaron {len(fichas)} docentes con {len(con_actual)} notas académicas. "
        + (f"El promedio académico es {promedio:.2f} " if promedio is not None else "")
        + (f"({variacion:+.2f} frente al período {pb.periodo}); " if variacion is not None else "")
        + f"el {pct_bajo:.0f}% de las notas está en desempeño bajo. "
        + f"{con_rojo} docente(s) tienen al menos un indicador en rojo, {con_amarillo} solo en amarillo y {len(fichas) - con_rojo - con_amarillo} sin alertas. "
        + (f"Quedan {pendientes_total} notas o conceptos pendientes en SAPRED." if pendientes_total else "No hay notas pendientes en SAPRED.")
    )
    return schemas.EstadoDocentes(
        periodo_base=pb, periodo_comparado=pc, docentes_analizados=len(fichas),
        con_rojo=con_rojo, con_amarillo=con_amarillo, sin_alertas=len(fichas) - con_rojo - con_amarillo,
        promedio_academico=promedio, pct_bajo=pct_bajo, variacion=variacion, pendientes_total=pendientes_total,
        promedio_actitudinal=_media([f.valor_comparado for f in act_actual]),
        pct_bajo_actitudinal=round(sum(1 for f in act_actual if f.nivel_comparado == "BAJO") / len(act_actual) * 100, 1) if act_actual else 0.0,
        umbrales=UMBRALES_TEXTO, informe_texto=texto, docentes=fichas,
    )


def ficha_docente(db: Session, p: dict, docente_id: int) -> schemas.FichaDocente | None:
    docente = db.get(models.Docente, docente_id)
    if docente is None:
        return None
    academicas, actitudinales, pendientes, periodo = _preparar(db, p)
    otras = _otras_por_estudiante(academicas)
    resumen, asig, act, puntos, fortalezas, por_tipo = _ficha(
        docente_id, docente.nombre_completo, academicas, actitudinales, otras, pendientes, periodo
    )
    pb, pc = _periodos(db, p)
    return schemas.FichaDocente(
        **resumen.model_dump(), periodo_base=pb, periodo_comparado=pc,
        asignaciones=asig, actitudinal=act, puntos=puntos, fortalezas_detalle=fortalezas,
        pendientes_por_tipo={k: v for k, v in por_tipo.items() if v},
    )


def estado_actitudinal(db: Session, p: dict) -> schemas.EstadoActitudinal:
    _, actitudinales, _, _ = _preparar(db, p)
    con_actual = [f for f in actitudinales if f.valor_comparado is not None]
    comparables = [f for f in actitudinales if f.comparable]
    grupos = [_evaluar_asignacion(a, None) for a in _agrupar(actitudinales)]
    grupos.sort(key=lambda a: (a.sede_nombre, a.grado, a.curso or 0))
    pb, pc = _periodos(db, p)
    n_bajo = sum(1 for f in con_actual if f.nivel_comparado == "BAJO")
    return schemas.EstadoActitudinal(
        periodo_base=pb, periodo_comparado=pc, evaluados=len(con_actual),
        promedio_base=_media([f.valor_base for f in comparables]),
        promedio_comparado=_media([f.valor_comparado for f in con_actual]),
        variacion=round(sum(f.delta for f in comparables) / len(comparables), 2) if comparables else None,
        n_bajo=n_bajo, pct_bajo=round(n_bajo / len(con_actual) * 100, 1) if con_actual else 0.0,
        grupos=grupos,
        estudiantes_bajo=[_evidencia(f) for f in sorted(con_actual, key=lambda f: f.valor_comparado) if f.nivel_comparado == "BAJO"],
        estudiantes_descenso=[_evidencia(f) for f in sorted(comparables, key=lambda f: f.delta) if f.delta is not None and f.delta <= -0.5],
    )
