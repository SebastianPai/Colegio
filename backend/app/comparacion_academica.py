"""Motor de comparación académica entre dos períodos cualesquiera (hoy
Período 1 -> Período 2; mañana P2->P3, P1->P4, o entre años, sin cambiar
código: todo recibe (anio_lectivo, periodo) para cada extremo).

Arma UNA lista de filas estudiante+área ("comparar") a partir de lo ya
importado de SAPRED (NotaSapred). Todo lo demás — resumen global, por área,
por grupo, por docente, por sede, matriz de transición, alertas — se agrega
desde esa MISMA lista en memoria, nunca con consultas repetidas: así cada
indicador es auditable hasta la fila real que lo compone (nunca un
porcentaje inventado).

Reglas que no se negocian (pedido explícito del colegio):
- El cruce entre períodos es SIEMPRE por estudiante_id (PK estable), nunca
  por nombre.
- Si falta un extremo (solo hay nota en un período), la fila queda
  comparable=False — nunca se cuenta como empeoramiento.
- El resumen a nivel estudiante/grupo/sede promedia las áreas del
  estudiante dentro del filtro (para que uno con 8 materias no pese 8 veces
  más que uno con 2). El detalle por área y por docente sí es por fila,
  porque ya es la unidad natural ahí (un docente dicta un área).
- Nada de este módulo le atribuye causalidad a un docente: los textos son
  descriptivos ("el promedio del grupo varió X"), no evaluativos.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import models, schemas

PeriodoRef = tuple[int, int]  # (anio_lectivo, periodo)

# Desempeño Actitudinal (actitud/convivencia): NO es una materia académica y
# su promedio es mucho más alto que el resto. Por decisión del colegio va
# APARTE: comparar() lo excluye de todo lo académico salvo que se pida esa
# área explícitamente (area_id) o incluir_actitudinal=True — ver
# evaluacion_docente.estado_actitudinal().
AREA_ACTITUDINAL = "DESM"

# Posible retiro (pedido 05/10/2026). En SAPRED la nota mínima de la escala
# (1.0) es la que queda cuando el estudiante no presentó nada: un 1.0 en
# varias materias a la vez es la huella típica de quien dejó de venir (caso
# real: 1.0 en sus 7 materias tras 3.5-5.0 en el P1). Solo es una SEÑAL para
# confirmar con el director de grupo: nunca cambia el estado del estudiante.
RETIRO_MIN_AREAS_EN_MINIMA = 2  # desde 2 materias con la nota mínima: "posible"
RETIRO_FRACCION_MUY_PROBABLE = 0.6  # y si son el 60% o más de sus materias: "muy probable"
# Si gran parte de un grupo tiene la nota mínima en la MISMA materia, no son
# retiros: es la nota que el docente aún no carga (caso real: Ética en
# Octavo-Tres, 18 de 30 en 1.0). Esa materia no cuenta para el retiro y se
# avisa aparte (_avisos_datos).
MINIMA_MASIVA_FRACCION = 0.4
MINIMA_MASIVA_MIN_ESTUDIANTES = 5


def _minima_masiva(filas, config) -> dict[tuple, tuple[int, int, str, str]]:
    """(sede_id, grado, curso, area_id) -> (en mínima, con nota, grupo, área)
    de las materias de un grupo donde la nota mínima es masiva."""
    conteo: dict[tuple, list] = {}
    for f in filas:
        if f.valor_comparado is None:
            continue
        c = conteo.setdefault((f.sede_id, f.grado, f.curso, f.area_id), [0, 0, f.nombre_grupo, f.area_nombre])
        c[1] += 1
        if f.valor_comparado <= config.escala_min:
            c[0] += 1
    return {
        k: tuple(c) for k, c in conteo.items()
        if c[0] >= MINIMA_MASIVA_MIN_ESTUDIANTES and c[0] / c[1] >= MINIMA_MASIVA_FRACCION
    }


class NoEncontrado(Exception):
    """El estudiante/período pedido no existe: el router la traduce a 404."""


# --- Clasificación (escala y umbrales configurables) ------------------------


def nivel_desempeno(valor: float, config: schemas.ConfigComparacion) -> str:
    """Los umbrales vienen en la escala de una décima del boletín ("Bajo
    hasta 2.9" = todo lo que no llega a 3.0). Por eso se compara con el
    inicio del nivel siguiente y no con "<= 2.9": un PROMEDIO de 2.95 no
    llega a 3.0 y es Bajo (antes quedaba en Básico, contradiciendo el
    "menor a 3.0" que dicen los textos de pantalla y evaluacion_docente)."""
    if valor < round(config.nivel_bajo_hasta + 0.1, 2):
        return "BAJO"
    if valor < round(config.nivel_basico_hasta + 0.1, 2):
        return "BASICO"
    if valor < round(config.nivel_alto_hasta + 0.1, 2):
        return "ALTO"
    return "SUPERIOR"


def clasificar_variacion(delta: float, config: schemas.ConfigComparacion) -> str:
    if delta >= config.umbral_mejora_significativa:
        return "MEJORA_SIGNIFICATIVA"
    if delta <= -config.umbral_descenso_significativo:
        return "DESCENSO_SIGNIFICATIVO"
    if delta >= config.umbral_mejora:
        return "MEJORA"
    if delta <= -config.umbral_descenso:
        return "DESCENSO"
    return "ESTABLE"


# --- Lectura de un período (una consulta, reutilizada para ambos extremos) --


@dataclass
class _NotaContexto:
    valor: float
    sede_id: int
    sede_nombre: str
    grado: int
    curso: int | None
    docente_id: int | None
    docente_nombre: str | None


def _notas_periodo(
    db: Session, anio_lectivo: int, periodo: int, *,
    sede_id: int | None = None, grado: int | None = None, curso: int | None = None,
    area_id: int | None = None, memo: dict | None = None,
) -> dict[tuple[int, int], _NotaContexto]:
    """(estudiante_id, area_id) -> contexto. memo: dict compartido dentro
    de UNA petición (panorama lee P1/P2 para comparar y otra vez para la
    evolución; así se leen una sola vez). Mismo patrón de join que
    reporte_notas.reporte_tendencia; el docente se resuelve con el patrón
    CORRECTO de grilla_sapred.py (asignación por área específica, no solo
    director de grupo — reporte_notas.py usa esa simplificación para otra
    cosa, aquí no aplica)."""
    clave_memo = (anio_lectivo, periodo, sede_id, grado, curso, area_id)
    if memo is not None and clave_memo in memo:
        return memo[clave_memo]
    # Solo las columnas que se usan (no objetos ORM completos): con ~10.000
    # notas por período, cargar entidades era la mayor parte del tiempo.
    consulta = (
        select(
            models.NotaSapred.estudiante_id, models.NotaSapred.area_id, models.NotaSapred.valor,
            models.RevisionBoletin.sede_id, models.RevisionBoletin.grado, models.RevisionBoletin.curso,
        )
        .join(models.RevisionBoletin, models.NotaSapred.revision_id == models.RevisionBoletin.id)
        .where(
            models.RevisionBoletin.anio_lectivo == anio_lectivo,
            models.RevisionBoletin.periodo == periodo,
        )
    )
    if sede_id is not None:
        consulta = consulta.where(models.RevisionBoletin.sede_id == sede_id)
    if grado is not None:
        consulta = consulta.where(models.RevisionBoletin.grado == grado)
    if curso is not None:
        consulta = consulta.where(models.RevisionBoletin.curso == curso)
    if area_id is not None:
        consulta = consulta.where(models.NotaSapred.area_id == area_id)

    filas = db.execute(consulta).all()
    if not filas:
        return {}

    sedes = {s.id: s.nombre for s in db.scalars(select(models.Sede)).all()}
    docentes_por_area = {
        (a.sede_id, a.grado, a.curso, a.area_id): a.docente
        for a in db.scalars(
            select(models.AsignacionDocente)
            .options(selectinload(models.AsignacionDocente.docente))
            .where(
                models.AsignacionDocente.anio_lectivo == anio_lectivo,
                models.AsignacionDocente.area_id.is_not(None),
            )
        ).all()
    }

    resultado: dict[tuple[int, int], _NotaContexto] = {}
    for estudiante_id, nota_area_id, valor_txt, r_sede_id, r_grado, r_curso in filas:
        try:
            valor = float(valor_txt)
        except (TypeError, ValueError):
            continue  # conceptos u otros valores no numéricos no entran a este análisis
        docente = docentes_por_area.get((r_sede_id, r_grado, r_curso, nota_area_id))
        resultado[(estudiante_id, nota_area_id)] = _NotaContexto(
            valor=valor, sede_id=r_sede_id, sede_nombre=sedes.get(r_sede_id, ""),
            grado=r_grado, curso=r_curso,
            docente_id=docente.id if docente else None,
            docente_nombre=docente.nombre_completo if docente else None,
        )
    if memo is not None:
        memo[clave_memo] = resultado
    return resultado


def _construir_fila(
    estudiante: models.Estudiante, area: models.Area,
    ctx_base: _NotaContexto | None, ctx_comparado: _NotaContexto | None,
    config: schemas.ConfigComparacion,
) -> schemas.FilaComparacionAcademica:
    # El período comparado manda el contexto (sede/grado/grupo/docente): es
    # "dónde está el estudiante ahora". Si no hay comparado (perdió el
    # período más reciente, ej. se retiró), se usa el del base.
    ctx_ref = ctx_comparado or ctx_base
    assert ctx_ref is not None  # siempre hay al menos un extremo (así se construyó la clave)

    valor_base = ctx_base.valor if ctx_base else None
    valor_comparado = ctx_comparado.valor if ctx_comparado else None
    comparable = valor_base is not None and valor_comparado is not None
    delta = round(valor_comparado - valor_base, 2) if comparable else None

    nombre_grado = models.GRADOS_NOMBRES.get(ctx_ref.grado, str(ctx_ref.grado))
    nombre_grupo = (
        f"{nombre_grado} - {models.DIVISIONES_NOMBRES.get(ctx_ref.curso, ctx_ref.curso)}"
        if ctx_ref.curso
        else nombre_grado
    )

    # model_construct: los valores ya salen tipados de la base y de este
    # mismo módulo; validar 12.000 filas por petición era ~la mitad del tiempo.
    return schemas.FilaComparacionAcademica.model_construct(
        estudiante_id=estudiante.id, documento=estudiante.documento, nombre_completo=estudiante.nombre_completo,
        area_id=area.id, area_codigo=area.codigo, area_nombre=area.nombre,
        sede_id=ctx_ref.sede_id, sede_nombre=ctx_ref.sede_nombre,
        grado=ctx_ref.grado, nombre_grado=nombre_grado, curso=ctx_ref.curso, nombre_grupo=nombre_grupo,
        docente_id=ctx_ref.docente_id, docente_nombre=ctx_ref.docente_nombre,
        valor_base=valor_base, valor_comparado=valor_comparado, delta=delta,
        categoria_variacion=clasificar_variacion(delta, config) if comparable else None,
        nivel_base=nivel_desempeno(valor_base, config) if valor_base is not None else None,
        nivel_comparado=nivel_desempeno(valor_comparado, config) if valor_comparado is not None else None,
        comparable=comparable,
    )


def comparar(
    db: Session, *, base: PeriodoRef, comparado: PeriodoRef,
    sede_id: int | None = None, grado: int | None = None, curso: int | None = None,
    area_id: int | None = None, docente_id: int | None = None,
    estado: str | None = "ACTIVO", config: schemas.ConfigComparacion | None = None,
    incluir_actitudinal: bool = False, memo: dict | None = None,
) -> list[schemas.FilaComparacionAcademica]:
    """La función central: TODA vista de este módulo parte de esta lista.
    Sin area_id, deja por fuera el Desempeño Actitudinal (AREA_ACTITUDINAL)
    salvo incluir_actitudinal=True."""
    config = config or schemas.ConfigComparacion()
    notas_base = _notas_periodo(db, *base, sede_id=sede_id, grado=grado, curso=curso, area_id=area_id, memo=memo)
    notas_comparado = _notas_periodo(db, *comparado, sede_id=sede_id, grado=grado, curso=curso, area_id=area_id, memo=memo)

    claves = set(notas_base) | set(notas_comparado)
    if not claves:
        return []

    estudiante_ids = {c[0] for c in claves}
    area_ids = {c[1] for c in claves}
    estudiantes = {
        e.id: e for e in db.scalars(select(models.Estudiante).where(models.Estudiante.id.in_(estudiante_ids))).all()
    }
    areas = {a.id: a for a in db.scalars(select(models.Area).where(models.Area.id.in_(area_ids))).all()}

    filas: list[schemas.FilaComparacionAcademica] = []
    for est_id, ar_id in claves:
        estudiante = estudiantes.get(est_id)
        area = areas.get(ar_id)
        if estudiante is None or area is None:
            continue
        if area_id is None and not incluir_actitudinal and area.codigo == AREA_ACTITUDINAL:
            continue
        if estado is not None and estudiante.estado != estado:
            continue
        fila = _construir_fila(estudiante, area, notas_base.get((est_id, ar_id)), notas_comparado.get((est_id, ar_id)), config)
        if docente_id is not None and fila.docente_id != docente_id:
            continue
        filas.append(fila)

    filas.sort(key=lambda f: (f.nombre_completo, f.area_nombre))
    return filas


# --- Agregación a nivel estudiante (promedio de sus áreas en el filtro) -----
#
# Dos poblaciones, siempre explícitas (pedido: "nunca un porcentaje sin
# decir sobre quién"):
# - COMPARABLES: estudiantes con al menos un área con nota en ambos
#   períodos. El promedio de cada uno usa SOLO esas áreas, así base y
#   comparado miden lo mismo. De aquí sale todo lo que habla de CAMBIO.
# - ACTUAL: todo estudiante con alguna nota en el período comparado,
#   promediando todas sus áreas de ese período. De aquí sale el "¿cómo
#   estamos hoy?", aunque su grupo no tenga el período base importado.

MEJORAS = ("MEJORA", "MEJORA_SIGNIFICATIVA")
DESCENSOS = ("DESCENSO", "DESCENSO_SIGNIFICATIVO")


@dataclass
class _EstudianteAgregado:
    estudiante_id: int
    documento: str
    nombre_completo: str
    sede_id: int
    sede_nombre: str
    grado: int
    nombre_grado: str
    curso: int | None
    nombre_grupo: str
    promedio_base: float | None
    promedio_comparado: float | None
    delta: float | None
    categoria_variacion: str | None
    nivel_base: str | None
    nivel_comparado: str | None
    comparable: bool
    areas_comparables: int
    tiene_base: bool
    actual_promedio: float | None  # todas sus áreas del período comparado
    actual_nivel: str | None
    areas_en_bajo: list[str]
    areas_bajaron: list[str]
    areas_en_minima: list[str]  # nota del período comparado = mínima de la escala (1.0)
    areas_actuales: int  # materias con nota en el período comparado
    riesgo_retiro: str | None  # MUY_PROBABLE | POSIBLE | None
    motivo_retiro: str | None


def _riesgo_retiro(tiene_base: bool, en_minima: int, actuales: int) -> tuple[str | None, str | None]:
    if actuales == 0:
        if tiene_base:
            return "MUY_PROBABLE", "Tenía notas en el período anterior y en este no tiene ninguna."
        return None, None
    if en_minima < RETIRO_MIN_AREAS_EN_MINIMA:
        return None, None
    texto = f"Tiene la nota mínima (no presentó nada) en {en_minima} de sus {actuales} materias."
    if en_minima / actuales >= RETIRO_FRACCION_MUY_PROBABLE:
        return "MUY_PROBABLE", texto
    return "POSIBLE", texto


def _media(valores: list[float]) -> float | None:
    return round(sum(valores) / len(valores), 2) if valores else None


def _agregar_por_estudiante(
    filas: list[schemas.FilaComparacionAcademica], config: schemas.ConfigComparacion,
) -> list[_EstudianteAgregado]:
    por_estudiante: dict[int, list[schemas.FilaComparacionAcademica]] = {}
    for f in filas:
        por_estudiante.setdefault(f.estudiante_id, []).append(f)

    masiva = _minima_masiva(filas, config)
    resultado = []
    for est_id, sus_filas in por_estudiante.items():
        comparables = [f for f in sus_filas if f.comparable]
        con_actual = [f for f in sus_filas if f.valor_comparado is not None]
        ultima = sus_filas[-1]  # contexto de grupo (todas comparten estudiante, y normalmente grupo)
        promedio_base = _media([f.valor_base for f in comparables])
        promedio_comparado = _media([f.valor_comparado for f in comparables])
        delta = round(promedio_comparado - promedio_base, 2) if comparables else None
        actual_promedio = _media([f.valor_comparado for f in con_actual])
        tiene_base = any(f.valor_base is not None for f in sus_filas)
        en_minima = sorted(
            f.area_nombre for f in con_actual
            if f.valor_comparado <= config.escala_min and (f.sede_id, f.grado, f.curso, f.area_id) not in masiva
        )
        riesgo, motivo = _riesgo_retiro(tiene_base, len(en_minima), len(con_actual))
        resultado.append(_EstudianteAgregado(
            estudiante_id=est_id, documento=ultima.documento, nombre_completo=ultima.nombre_completo,
            sede_id=ultima.sede_id, sede_nombre=ultima.sede_nombre,
            grado=ultima.grado, nombre_grado=ultima.nombre_grado, curso=ultima.curso, nombre_grupo=ultima.nombre_grupo,
            promedio_base=promedio_base, promedio_comparado=promedio_comparado, delta=delta,
            categoria_variacion=clasificar_variacion(delta, config) if comparables else None,
            nivel_base=nivel_desempeno(promedio_base, config) if comparables else None,
            nivel_comparado=nivel_desempeno(promedio_comparado, config) if comparables else None,
            comparable=bool(comparables), areas_comparables=len(comparables),
            tiene_base=tiene_base,
            actual_promedio=actual_promedio,
            actual_nivel=nivel_desempeno(actual_promedio, config) if actual_promedio is not None else None,
            areas_en_bajo=sorted(f.area_nombre for f in con_actual if f.nivel_comparado == "BAJO"),
            areas_bajaron=sorted(f.area_nombre for f in comparables if f.categoria_variacion in DESCENSOS),
            areas_en_minima=en_minima, areas_actuales=len(con_actual),
            riesgo_retiro=riesgo, motivo_retiro=motivo,
        ))
    return resultado


def _distribucion(niveles) -> dict[str, int]:
    conteo = {n: 0 for n in schemas.NIVELES_DESEMPENO}
    for n in niveles:
        if n is not None:
            conteo[n] += 1
    return conteo


def _estadisticas(estudiantes: list[_EstudianteAgregado]) -> dict:
    """Los mismos números para el colegio, un grado, un grupo o una sede:
    así nunca hay dos fórmulas distintas para "% que mejoró"."""
    comparables = [e for e in estudiantes if e.comparable]
    actuales = [e for e in estudiantes if e.actual_promedio is not None]
    n_comp = len(comparables)
    mejoraron = sum(1 for e in comparables if e.categoria_variacion in MEJORAS)
    empeoraron = sum(1 for e in comparables if e.categoria_variacion in DESCENSOS)
    estables = sum(1 for e in comparables if e.categoria_variacion == "ESTABLE")
    promedio_base = _media([e.promedio_base for e in comparables])
    promedio_comparado = _media([e.promedio_comparado for e in comparables])

    def pct(n: int) -> float:
        return round(n / n_comp * 100, 1) if n_comp else 0.0

    return dict(
        total_estudiantes=len(estudiantes), estudiantes_comparables=n_comp,
        promedio_base=promedio_base, promedio_comparado=promedio_comparado,
        # variación desde los promedios SIN redondear (evita que dos
        # redondeos sumen un error de 0.01)
        variacion=(
            round(sum(e.promedio_comparado for e in comparables) / n_comp - sum(e.promedio_base for e in comparables) / n_comp, 2)
            if n_comp else None
        ),
        mejoraron=mejoraron, empeoraron=empeoraron, estables=estables,
        pct_mejoraron=pct(mejoraron), pct_empeoraron=pct(empeoraron), pct_estables=pct(estables),
        salieron_de_bajo=sum(1 for e in comparables if e.nivel_base == "BAJO" and e.nivel_comparado != "BAJO"),
        entraron_a_bajo=sum(1 for e in comparables if e.nivel_base != "BAJO" and e.nivel_comparado == "BAJO"),
        permanecen_en_bajo=sum(1 for e in comparables if e.nivel_base == "BAJO" and e.nivel_comparado == "BAJO"),
        distribucion_base=_distribucion(e.nivel_base for e in comparables),
        distribucion_comparado=_distribucion(e.nivel_comparado for e in comparables),
        actual_evaluados=len(actuales),
        actual_promedio=_media([e.actual_promedio for e in actuales]),
        actual_n_bajo=sum(1 for e in actuales if e.actual_nivel == "BAJO"),
        actual_distribucion=_distribucion(e.actual_nivel for e in actuales),
    )


def resumen_global(
    filas: list[schemas.FilaComparacionAcademica], *,
    periodo_base: schemas.PeriodoDisponible, periodo_comparado: schemas.PeriodoDisponible,
    config: schemas.ConfigComparacion,
) -> schemas.ResumenComparacion:
    estudiantes = _agregar_por_estudiante(filas, config)
    s = _estadisticas(estudiantes)

    # Cobertura: qué sedes/grupos tienen estudiantes hoy pero NINGUNO
    # comparable (típico: el período base no se importó para ese grupo).
    grupos: dict[tuple, list[_EstudianteAgregado]] = {}
    for e in estudiantes:
        grupos.setdefault((e.sede_id, e.sede_nombre, e.grado, e.curso, e.nombre_grupo), []).append(e)
    sedes: dict[str, bool] = {}
    grupos_sin = []
    for (_sid, sede_nombre, grado, curso, nombre_grupo), sus in sorted(grupos.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][3] or 0)):
        alguno = any(e.comparable for e in sus)
        sedes[sede_nombre] = sedes.get(sede_nombre, False) or alguno
        if not alguno and any(e.actual_promedio is not None for e in sus):
            grupos_sin.append(f"{nombre_grupo} ({sede_nombre.strip()})")

    resumen = schemas.ResumenComparacion(
        periodo_base=periodo_base, periodo_comparado=periodo_comparado, config=config,
        total_estudiantes=s["total_estudiantes"], estudiantes_comparables=s["estudiantes_comparables"],
        estudiantes_sin_comparar=s["total_estudiantes"] - s["estudiantes_comparables"],
        promedio_base=s["promedio_base"], promedio_comparado=s["promedio_comparado"], variacion_promedio=s["variacion"],
        **{k: s[k] for k in (
            "mejoraron", "empeoraron", "estables", "pct_mejoraron", "pct_empeoraron", "pct_estables",
            "salieron_de_bajo", "entraron_a_bajo", "permanecen_en_bajo",
            "distribucion_base", "distribucion_comparado",
            "actual_evaluados", "actual_promedio", "actual_n_bajo", "actual_distribucion",
        )},
        informe_texto="",
        solo_en_base=sum(1 for e in estudiantes if not e.comparable and e.actual_promedio is None),
        solo_en_comparado=sum(1 for e in estudiantes if not e.comparable and e.actual_promedio is not None),
        sedes_sin_comparacion=sorted(n.strip() for n, alguno in sedes.items() if not alguno),
        grupos_sin_comparacion=grupos_sin,
    )
    resumen.informe_texto = _informe_texto(resumen, periodo_base, periodo_comparado)
    resumen.avisos_datos = _avisos_datos(filas, config)
    return resumen


def _avisos_datos(filas: list[schemas.FilaComparacionAcademica], config: schemas.ConfigComparacion) -> list[str]:
    """Hoy detecta grupos importados con un grado fuera de la escala
    (p. ej. grado 2026: el año leído como grado). Esas notas SÍ cuentan en
    los totales (son notas reales); se avisa para corregir la importación."""
    raros: dict[int, list[schemas.FilaComparacionAcademica]] = {}
    for f in filas:
        if f.grado not in models.GRADOS_NOMBRES:
            raros.setdefault(f.grado, []).append(f)
    avisos = []
    for grado, sus in sorted(raros.items()):
        sedes = sorted({f.sede_nombre.strip() for f in sus})
        avisos.append(
            f"Hay notas importadas con grado «{grado}», que no existe: {len(sus)} notas de "
            f"{len({f.estudiante_id for f in sus})} estudiantes ({', '.join(sedes)}). "
            f"Aparecen como un grado aparte; conviene revisar esa importación de SAPRED."
        )
    for en_minima, con_nota, grupo, area in sorted(_minima_masiva(filas, config).values(), key=lambda c: (c[2], c[3])):
        avisos.append(
            f"{area} en {grupo}: {en_minima} de {con_nota} estudiantes tienen {config.escala_min:.1f}. "
            f"Parece una nota que el docente aún no ha cargado en SAPRED; esos {config.escala_min:.1f} "
            f"cuentan como pérdida en el análisis, pero no como señal de retiro."
        )
    return avisos


def _informe_texto(
    r: schemas.ResumenComparacion, pb: schemas.PeriodoDisponible, pc: schemas.PeriodoDisponible,
) -> str:
    nombre_pb, nombre_pc = f"Período {pb.periodo} ({pb.anio_lectivo})", f"Período {pc.periodo} ({pc.anio_lectivo})"
    if r.estudiantes_comparables == 0:
        return f"No hay estudiantes con información comparable entre {nombre_pb} y {nombre_pc} para este filtro."

    partes = [
        f"Durante la comparación entre {nombre_pb} y {nombre_pc} se analizaron {r.estudiantes_comparables} "
        f"estudiantes con información comparable"
        + (
            f" (de {r.total_estudiantes} en total; {r.estudiantes_sin_comparar} no tuvieron nota en ambos "
            f"períodos y no se cuentan como mejora ni descenso)."
            if r.estudiantes_sin_comparar
            else "."
        ),
        f"El promedio general pasó de {r.promedio_base:.2f} a {r.promedio_comparado:.2f}, "
        f"una variación de {r.variacion_promedio:+.2f}.",
        f"El {r.pct_mejoraron:.1f}% de los estudiantes mejoró, el {r.pct_empeoraron:.1f}% descendió "
        f"y el {r.pct_estables:.1f}% se mantuvo estable.",
    ]
    if r.salieron_de_bajo or r.entraron_a_bajo:
        partes.append(
            f"{r.salieron_de_bajo} estudiante(s) salieron de desempeño bajo y {r.entraron_a_bajo} "
            f"entraron a desempeño bajo; {r.permanecen_en_bajo} siguen en ese nivel."
        )
    return " ".join(partes)


def estudiantes_comparacion(
    filas: list[schemas.FilaComparacionAcademica], config: schemas.ConfigComparacion, cambio: str | None = None,
) -> list[schemas.EstudianteComparacion]:
    """La lista EXACTA detrás de cada número del resumen (mismo
    _agregar_por_estudiante): "Mejoraron 33" abre estos 33, no filas
    estudiante+área con otra cuenta."""
    filtros = {
        None: lambda e: True,
        "mejoraron": lambda e: e.categoria_variacion in MEJORAS,
        "empeoraron": lambda e: e.categoria_variacion in DESCENSOS,
        "estables": lambda e: e.categoria_variacion == "ESTABLE",
        "descenso_significativo": lambda e: e.categoria_variacion == "DESCENSO_SIGNIFICATIVO",
        "entraron_bajo": lambda e: e.comparable and e.nivel_base != "BAJO" and e.nivel_comparado == "BAJO",
        "salieron_bajo": lambda e: e.comparable and e.nivel_base == "BAJO" and e.nivel_comparado != "BAJO",
        "permanecen_bajo": lambda e: e.nivel_base == "BAJO" and e.nivel_comparado == "BAJO",
        # atención = cualquiera de las tres situaciones que piden seguimiento
        "atencion": lambda e: e.comparable and (
            e.categoria_variacion == "DESCENSO_SIGNIFICATIVO" or e.nivel_comparado == "BAJO"
        ),
        "bajo_actual": lambda e: e.actual_nivel == "BAJO",
        "sin_comparar": lambda e: not e.comparable,
        "posible_retiro": lambda e: e.riesgo_retiro is not None,
    }
    if cambio not in filtros:
        raise ValueError(f"Tipo de cambio desconocido: {cambio}")
    elegidos = [e for e in _agregar_por_estudiante(filas, config) if filtros[cambio](e)]
    # Primero lo que más bajó; los sin comparación al final, por nombre.
    elegidos.sort(key=lambda e: (e.delta is None, e.delta if e.delta is not None else 0, e.nombre_completo))
    return [
        schemas.EstudianteComparacion(
            estudiante_id=e.estudiante_id, documento=e.documento, nombre_completo=e.nombre_completo,
            sede_id=e.sede_id, sede_nombre=e.sede_nombre, grado=e.grado, nombre_grado=e.nombre_grado,
            curso=e.curso, nombre_grupo=e.nombre_grupo,
            promedio_base=e.promedio_base,
            # sin comparación: se muestra su promedio actual (todas sus áreas)
            promedio_comparado=e.promedio_comparado if e.comparable else e.actual_promedio,
            delta=e.delta, categoria_variacion=e.categoria_variacion,
            nivel_base=e.nivel_base, nivel_comparado=e.nivel_comparado if e.comparable else e.actual_nivel,
            comparable=e.comparable, areas_comparables=e.areas_comparables,
            areas_en_bajo=e.areas_en_bajo, areas_bajaron=e.areas_bajaron,
            areas_en_minima=e.areas_en_minima, areas_actuales=e.areas_actuales,
            riesgo_retiro=e.riesgo_retiro, motivo_retiro=e.motivo_retiro,
        )
        for e in elegidos
    ]


# --- Agregación por área / grupo / docente / sede (desde las mismas filas) --


def por_area(
    filas: list[schemas.FilaComparacionAcademica], config: schemas.ConfigComparacion | None = None,
) -> list[schemas.ComparacionPorArea]:
    """Por fila estudiante+área (la unidad natural de un área). Incluye
    áreas sin filas comparables (solo "hoy"), con promedios de cambio en
    None — nunca un 0 inventado."""
    config = config or schemas.ConfigComparacion()
    por_area_dict: dict[int, list[schemas.FilaComparacionAcademica]] = {}
    for f in filas:
        por_area_dict.setdefault(f.area_id, []).append(f)

    resultado = []
    for area_id, todas in por_area_dict.items():
        sus_filas = [f for f in todas if f.comparable]
        actuales = [f for f in todas if f.valor_comparado is not None]
        if not sus_filas and not actuales:
            continue
        n = len(sus_filas)
        promedio_base = _media([f.valor_base for f in sus_filas])
        promedio_comparado = _media([f.valor_comparado for f in sus_filas])
        mejoraron = sum(1 for f in sus_filas if f.categoria_variacion in MEJORAS)
        empeoraron = sum(1 for f in sus_filas if f.categoria_variacion in DESCENSOS)
        estables = sum(1 for f in sus_filas if f.categoria_variacion == "ESTABLE")
        primero = todas[0]

        def pct(k: int) -> float:
            return round(k / n * 100, 1) if n else 0.0

        resultado.append(schemas.ComparacionPorArea(
            area_id=area_id, area_codigo=primero.area_codigo, area_nombre=primero.area_nombre,
            total_evaluados=n, promedio_base=promedio_base, promedio_comparado=promedio_comparado,
            variacion=(
                round(sum(f.valor_comparado for f in sus_filas) / n - sum(f.valor_base for f in sus_filas) / n, 2)
                if n else None
            ),
            mejoraron=mejoraron, empeoraron=empeoraron, estables=estables,
            pct_mejoraron=pct(mejoraron), pct_empeoraron=pct(empeoraron), pct_estables=pct(estables),
            n_bajo_base=sum(1 for f in sus_filas if f.nivel_base == "BAJO"),
            n_bajo_comparado=sum(1 for f in sus_filas if f.nivel_comparado == "BAJO"),
            actual_evaluados=len(actuales),
            actual_promedio=_media([f.valor_comparado for f in actuales]),
            actual_n_bajo=sum(1 for f in actuales if f.nivel_comparado == "BAJO"),
        ))
    resultado.sort(key=lambda a: a.area_nombre)
    return resultado


def _grupo_desde_estadisticas(
    s: dict, *, sede_id, sede_nombre, grado, nombre_grado, curso, nombre_grupo,
) -> schemas.ComparacionPorGrupo:
    return schemas.ComparacionPorGrupo(
        sede_id=sede_id, sede_nombre=sede_nombre, grado=grado, nombre_grado=nombre_grado,
        curso=curso, nombre_grupo=nombre_grupo,
        **{k: s[k] for k in (
            "total_estudiantes", "promedio_base", "promedio_comparado", "variacion",
            "mejoraron", "empeoraron", "estables", "pct_mejoraron", "pct_empeoraron", "pct_estables",
            "salieron_de_bajo", "entraron_a_bajo", "permanecen_en_bajo",
            "estudiantes_comparables", "actual_evaluados", "actual_promedio", "actual_n_bajo",
        )},
    )


def por_grupo(filas: list[schemas.FilaComparacionAcademica], config: schemas.ConfigComparacion) -> list[schemas.ComparacionPorGrupo]:
    por_grupo_dict: dict[tuple[int, int, int | None], list[schemas.FilaComparacionAcademica]] = {}
    for f in filas:
        por_grupo_dict.setdefault((f.sede_id, f.grado, f.curso), []).append(f)

    resultado = []
    for (sede_id, grado, curso), sus_filas in por_grupo_dict.items():
        primero = sus_filas[0]
        resultado.append(_grupo_desde_estadisticas(
            _estadisticas(_agregar_por_estudiante(sus_filas, config)),
            sede_id=sede_id, sede_nombre=primero.sede_nombre, grado=grado, nombre_grado=primero.nombre_grado,
            curso=curso, nombre_grupo=primero.nombre_grupo,
        ))
    resultado.sort(key=lambda g: (g.sede_nombre, g.grado, g.curso or 0))
    return resultado


def por_grado(filas: list[schemas.FilaComparacionAcademica], config: schemas.ConfigComparacion) -> list[schemas.ComparacionPorGrupo]:
    """Un grado junta todos sus grupos (y sedes, si el filtro no fija una)."""
    por_grado_dict: dict[int, list[schemas.FilaComparacionAcademica]] = {}
    for f in filas:
        por_grado_dict.setdefault(f.grado, []).append(f)

    resultado = []
    for grado, sus_filas in por_grado_dict.items():
        sedes = {f.sede_id for f in sus_filas}
        una_sede = len(sedes) == 1
        primero = sus_filas[0]
        resultado.append(_grupo_desde_estadisticas(
            _estadisticas(_agregar_por_estudiante(sus_filas, config)),
            sede_id=primero.sede_id if una_sede else None,
            sede_nombre=primero.sede_nombre if una_sede else f"{len(sedes)} sedes",
            grado=grado, nombre_grado=primero.nombre_grado, curso=None, nombre_grupo=primero.nombre_grado,
        ))
    resultado.sort(key=lambda g: g.grado)
    return resultado


def por_docente(filas: list[schemas.FilaComparacionAcademica]) -> list[schemas.ComparacionPorDocente]:
    """Descriptivo, no evaluativo: variación del promedio del grupo/área
    asociado al docente, nunca 'el docente mejoró/empeoró'."""
    por_docente_dict: dict[tuple[int, int, int, int | None], list[schemas.FilaComparacionAcademica]] = {}
    for f in filas:
        if f.comparable and f.docente_id is not None:
            por_docente_dict.setdefault((f.docente_id, f.area_id, f.grado, f.curso), []).append(f)

    resultado = []
    for (docente_id, area_id, grado, curso), sus_filas in por_docente_dict.items():
        n = len(sus_filas)
        promedio_base = round(sum(f.valor_base for f in sus_filas) / n, 2)
        promedio_comparado = round(sum(f.valor_comparado for f in sus_filas) / n, 2)
        mejoraron = sum(1 for f in sus_filas if f.categoria_variacion in MEJORAS)
        empeoraron = sum(1 for f in sus_filas if f.categoria_variacion in DESCENSOS)
        estables = sum(1 for f in sus_filas if f.categoria_variacion == "ESTABLE")
        primero = sus_filas[0]
        resultado.append(schemas.ComparacionPorDocente(
            docente_id=docente_id, docente_nombre=primero.docente_nombre or "",
            area_id=area_id, area_nombre=primero.area_nombre, grado=grado, nombre_grado=primero.nombre_grado, curso=curso,
            total_evaluados=n, promedio_base=promedio_base, promedio_comparado=promedio_comparado,
            variacion=round(sum(f.valor_comparado for f in sus_filas) / n - sum(f.valor_base for f in sus_filas) / n, 2),
            mejoraron=mejoraron, empeoraron=empeoraron, estables=estables,
            pct_mejoraron=round(mejoraron / n * 100, 1), pct_empeoraron=round(empeoraron / n * 100, 1),
            pct_estables=round(estables / n * 100, 1),
            salieron_de_bajo=sum(1 for f in sus_filas if f.nivel_base == "BAJO" and f.nivel_comparado != "BAJO"),
            entraron_a_bajo=sum(1 for f in sus_filas if f.nivel_base != "BAJO" and f.nivel_comparado == "BAJO"),
            permanecen_en_bajo=sum(1 for f in sus_filas if f.nivel_base == "BAJO" and f.nivel_comparado == "BAJO"),
        ))
    # Orden alfabético por docente — a propósito NO por variación, para que
    # esto no se lea como un ranking de "mejor/peor docente".
    resultado.sort(key=lambda d: (d.docente_nombre, d.area_nombre))
    return resultado


def por_sede(filas: list[schemas.FilaComparacionAcademica], config: schemas.ConfigComparacion) -> list[schemas.ComparacionPorSede]:
    por_sede_dict: dict[int, list[schemas.FilaComparacionAcademica]] = {}
    for f in filas:
        por_sede_dict.setdefault(f.sede_id, []).append(f)

    resultado = []
    for sede_id, sus_filas in por_sede_dict.items():
        s = _estadisticas(_agregar_por_estudiante(sus_filas, config))
        resultado.append(schemas.ComparacionPorSede(
            sede_id=sede_id, sede_nombre=sus_filas[0].sede_nombre,
            **{k: s[k] for k in (
                "total_estudiantes", "promedio_base", "promedio_comparado", "variacion",
                "pct_mejoraron", "pct_empeoraron", "pct_estables",
                "estudiantes_comparables", "actual_evaluados", "actual_promedio", "actual_n_bajo",
            )},
        ))
    resultado.sort(key=lambda s: s.sede_nombre)
    return resultado


# --- Evolución en todos los períodos del año --------------------------------

# Umbrales de LECTURA de promedios de grupo (no de un estudiante: un
# promedio institucional que se mueve 0.3 es un cambio enorme, uno de un
# estudiante no). Visibles en pantalla junto a cada frase.
TENDENCIA_ESTABLE = 0.05  # |variación| menor a esto = "se mantuvo estable"
TENDENCIA_LEVE = 0.15  # menor a esto = "levemente"
TENDENCIA_MARCADA = 0.3  # desde esto = "de forma marcada" / cambio brusco


def evolucion(
    db: Session, *, anio_lectivo: int,
    sede_id: int | None = None, grado: int | None = None, curso: int | None = None,
    area_id: int | None = None, docente_id: int | None = None,
    estado: str | None = "ACTIVO", config: schemas.ConfigComparacion | None = None,
    incluir_actitudinal: bool = False, memo: dict | None = None,
) -> schemas.EvolucionAcademica:
    """Serie P1 → P2 → P3 → P4 del año con los mismos filtros que comparar().
    La línea de tendencia usa la COHORTE (los mismos estudiantes en todos
    los períodos, solo sus áreas presentes en todos): si un período está
    incompleto, el promedio "de todos" mezcla poblaciones distintas y
    aparentaría cambios que son solo de cobertura."""
    config = config or schemas.ConfigComparacion()
    periodos = [p.periodo for p in periodos_disponibles(db) if p.anio_lectivo == anio_lectivo]
    codigos = {a.id: a.codigo for a in db.scalars(select(models.Area)).all()}

    por_periodo: dict[int, dict[int, dict[int, float]]] = {}
    contexto: dict[int, _NotaContexto] = {}
    for p in periodos:
        est: dict[int, dict[int, float]] = {}
        for (e, a), ctx in _notas_periodo(db, anio_lectivo, p, sede_id=sede_id, grado=grado, curso=curso, area_id=area_id, memo=memo).items():
            if area_id is None and not incluir_actitudinal and codigos.get(a) == AREA_ACTITUDINAL:
                continue
            if docente_id is not None and ctx.docente_id != docente_id:
                continue
            est.setdefault(e, {})[a] = ctx.valor
            contexto[e] = ctx  # el período más reciente manda (se recorre en orden)
        por_periodo[p] = est

    ids = set().union(*por_periodo.values()) if por_periodo else set()
    nombres: dict[int, str] = {}
    if ids:
        validos = set()
        for est in db.scalars(select(models.Estudiante).where(models.Estudiante.id.in_(ids))).all():
            nombres[est.id] = est.nombre_completo
            if estado is None or est.estado == estado:
                validos.add(est.id)
        por_periodo = {p: {e: v for e, v in est.items() if e in validos} for p, est in por_periodo.items()}

    def media_de(notas: dict[int, float], areas) -> float:
        return round(sum(notas[a] for a in areas) / len(areas), 2)

    # Cohorte: presentes en TODOS los períodos, con al menos un área común.
    cohorte_ids = set.intersection(*(set(v) for v in por_periodo.values())) if por_periodo else set()
    cohorte: dict[int, dict[int, float]] = {p: {} for p in periodos}
    for e in cohorte_ids:
        comunes = set.intersection(*(set(por_periodo[p][e]) for p in periodos))
        if comunes:
            for p in periodos:
                cohorte[p][e] = media_de(por_periodo[p][e], comunes)

    puntos = []
    for p in periodos:
        todos = [media_de(notas, notas) for notas in por_periodo[p].values()]
        coh = list(cohorte[p].values())
        puntos.append(schemas.PuntoEvolucion(
            anio_lectivo=anio_lectivo, periodo=p,
            evaluados_todos=len(todos), promedio_todos=_media(todos),
            distribucion_todos=_distribucion(nivel_desempeno(v, config) for v in todos),
            evaluados_cohorte=len(coh), promedio_cohorte=_media(coh),
            distribucion_cohorte=_distribucion(nivel_desempeno(v, config) for v in coh),
        ))

    # Descenso consecutivo: bajó (umbral de descenso) en CADA una de las dos
    # últimas transiciones. Con menos de 3 períodos no existe: None, y la
    # pantalla lo dice en vez de mostrar un "0" engañoso.
    descenso = None
    if len(periodos) >= 3:
        ultimos = periodos[-3:]
        descenso = []
        for e in set.intersection(*(set(por_periodo[p]) for p in ultimos)):
            comunes = set.intersection(*(set(por_periodo[p][e]) for p in ultimos))
            if not comunes:
                continue
            v = [media_de(por_periodo[p][e], comunes) for p in ultimos]
            if v[1] - v[0] <= -config.umbral_descenso and v[2] - v[1] <= -config.umbral_descenso:
                ctx = contexto[e]
                nombre_grado = models.GRADOS_NOMBRES.get(ctx.grado, str(ctx.grado))
                descenso.append(schemas.EstudianteDescensoConsecutivo(
                    estudiante_id=e, nombre_completo=nombres.get(e, ""), sede_nombre=ctx.sede_nombre,
                    nombre_grupo=f"{nombre_grado} - {models.DIVISIONES_NOMBRES.get(ctx.curso, ctx.curso)}" if ctx.curso else nombre_grado,
                    valores=v,
                ))
        descenso.sort(key=lambda d: d.valores[-1] - d.valores[0])

    return schemas.EvolucionAcademica(
        anio_lectivo=anio_lectivo, puntos=puntos, cohorte=len(cohorte[periodos[0]]) if periodos else 0,
        descenso_consecutivo=descenso,
    )


# --- Lectura e hallazgos: frases CALCULADAS, nunca redactadas a mano ---------

# Mínimos para que un área/grado pueda generar un hallazgo: con 4 notas un
# cambio de 0.5 es ruido, no un hallazgo.
HALLAZGO_MIN_AREA = 20
HALLAZGO_MIN_GRADO = 10
HALLAZGO_VARIACION = 0.1  # puntos de promedio
HALLAZGO_PUNTOS_PCT = 5  # puntos porcentuales de "% en bajo"
HALLAZGO_PCT_BAJO_ACTUAL = 15  # % de notas en bajo "hoy" que ya es un foco


def _nombre_periodo(p: schemas.PeriodoDisponible) -> str:
    return f"Período {p.periodo}"


def lectura_general(
    r: schemas.ResumenComparacion, pb: schemas.PeriodoDisponible, pc: schemas.PeriodoDisponible,
) -> schemas.LecturaGeneral:
    npb, npc = _nombre_periodo(pb), _nombre_periodo(pc)
    if not r.estudiantes_comparables:
        hoy = (
            f" Hoy hay {r.actual_evaluados} estudiantes con notas del {npc}, con promedio {r.actual_promedio:.2f}."
            if r.actual_evaluados else ""
        )
        return schemas.LecturaGeneral(
            tendencia="sin_datos", titulo="No hay con qué comparar",
            frase=f"Ningún estudiante de este filtro tiene notas en el {npb} y en el {npc}, así que no se puede decir si mejoró o empeoró.{hoy}",
        )
    d = r.variacion_promedio
    if abs(d) < TENDENCIA_ESTABLE:
        tendencia, titulo = "estable", "El rendimiento se mantuvo estable"
    else:
        tendencia = "sube" if d > 0 else "baja"
        verbo = "mejoró" if d > 0 else "bajó"
        matiz = " levemente" if abs(d) < TENDENCIA_LEVE else " de forma marcada" if abs(d) >= TENDENCIA_MARCADA else ""
        titulo = f"El rendimiento {verbo}{matiz}"
    frase = (
        f"El promedio de los {r.estudiantes_comparables} estudiantes con notas en ambos períodos pasó de "
        f"{r.promedio_base:.2f} a {r.promedio_comparado:.2f} ({d:+.2f}) entre el {npb} y el {npc}."
    )
    return schemas.LecturaGeneral(tendencia=tendencia, titulo=titulo, frase=frase)


def _pct(n: int, total: int) -> float:
    return n / total * 100 if total else 0.0


def hallazgos(
    r: schemas.ResumenComparacion, estudiantes: list[_EstudianteAgregado],
    areas: list[schemas.ComparacionPorArea], grados: list[schemas.ComparacionPorGrupo],
    evol: schemas.EvolucionAcademica, pb: schemas.PeriodoDisponible, pc: schemas.PeriodoDisponible,
) -> list[schemas.Hallazgo]:
    """Cada hallazgo es una regla con umbral (constantes HALLAZGO_*) sobre
    los mismos agregados que se ven en pantalla, y lleva su evidencia y el
    drill-down que la sustenta."""
    npb, npc = _nombre_periodo(pb), _nombre_periodo(pc)
    lista: list[schemas.Hallazgo] = []
    n = r.estudiantes_comparables
    cfg = r.config
    corte = f"{cfg.nivel_bajo_hasta + 0.1:.1f}"  # inicio de Básico (3.0)

    if n:
        bajo_b = r.distribucion_base.get("BAJO", 0)
        bajo_c = r.distribucion_comparado.get("BAJO", 0)
        if r.entraron_a_bajo:
            lista.append(schemas.Hallazgo(
                tipo="alerta", titulo=f"{r.entraron_a_bajo} estudiantes pasaron a desempeño bajo",
                detalle=f"Su promedio era {corte} o más en el {npb} y quedó por debajo de {corte} en el {npc}.",
                accion={"cambio": "entraron_bajo"},
                evidencia=[["Pasaron a bajo", str(r.entraron_a_bajo)], ["Siguen en bajo", str(r.permanecen_en_bajo)],
                           ["Salieron de bajo", str(r.salieron_de_bajo)], ["Estudiantes comparados", str(n)]],
            ))
        significativos = sum(1 for e in estudiantes if e.categoria_variacion == "DESCENSO_SIGNIFICATIVO")
        if significativos:
            lista.append(schemas.Hallazgo(
                tipo="alerta", titulo=f"{significativos} estudiantes bajaron {cfg.umbral_descenso_significativo:.1f} puntos o más en su promedio",
                detalle=f"Es el descenso más fuerte posible entre el {npb} y el {npc}; conviene revisar caso por caso.",
                accion={"cambio": "descenso_significativo"},
                evidencia=[[f"Descenso significativo (≥ {cfg.umbral_descenso_significativo:.1f})", str(significativos)], ["Estudiantes comparados", str(n)]],
            ))
        pp = _pct(bajo_c, n) - _pct(bajo_b, n)
        if abs(pp) >= HALLAZGO_PUNTOS_PCT:
            lista.append(schemas.Hallazgo(
                tipo="baja" if pp > 0 else "sube",
                titulo=f"El porcentaje de estudiantes en desempeño bajo {'subió' if pp > 0 else 'bajó'} {abs(pp):.0f} puntos",
                detalle=f"Pasó de {_pct(bajo_b, n):.0f}% ({bajo_b}) a {_pct(bajo_c, n):.0f}% ({bajo_c}) entre los mismos {n} estudiantes.",
                accion={"cambio": "bajo_actual"},
                evidencia=[[npb, f"{_pct(bajo_b, n):.1f}% ({bajo_b})"], [npc, f"{_pct(bajo_c, n):.1f}% ({bajo_c})"]],
            ))

    if evol.descenso_consecutivo:
        k = len(evol.descenso_consecutivo)
        periodos = [p.periodo for p in evol.puntos][-3:]
        lista.append(schemas.Hallazgo(
            tipo="alerta", titulo=f"{k} estudiantes bajaron en dos períodos seguidos",
            detalle=f"Su promedio bajó {cfg.umbral_descenso:.1f} o más del Período {periodos[0]} al {periodos[1]} y otra vez del {periodos[1]} al {periodos[2]}.",
            accion={"lista": "descenso_consecutivo"},
            evidencia=[[d.nombre_completo, " → ".join(f"{v:.2f}" for v in d.valores)] for d in evol.descenso_consecutivo[:15]],
        ))

    def evidencia_area(a: schemas.ComparacionPorArea) -> list[list[str]]:
        return [
            ["Notas comparadas (mismos estudiantes)", str(a.total_evaluados)],
            [f"Promedio {npb} → {npc}", f"{a.promedio_base:.2f} → {a.promedio_comparado:.2f}"],
            ["Notas en bajo", f"{a.n_bajo_base} → {a.n_bajo_comparado}"],
            ["Bajaron / subieron", f"{a.empeoraron} / {a.mejoraron}"],
        ]

    con_cambio = [a for a in areas if a.variacion is not None and a.total_evaluados >= HALLAZGO_MIN_AREA]
    for a in sorted(con_cambio, key=lambda a: a.variacion)[:2]:
        if a.variacion <= -HALLAZGO_VARIACION:
            lista.append(schemas.Hallazgo(
                tipo="baja", titulo=f"{a.area_nombre} bajó {abs(a.variacion):.2f} puntos",
                detalle=f"Promedio {a.promedio_base:.2f} → {a.promedio_comparado:.2f} en {a.total_evaluados} notas comparables; "
                        f"{a.empeoraron} estudiantes bajaron en esta área.",
                accion={"filtro": "area_id", "valor": a.area_id, "nombre": a.area_nombre}, evidencia=evidencia_area(a),
            ))
    if con_cambio:
        mejor = max(con_cambio, key=lambda a: a.variacion)
        if mejor.variacion >= HALLAZGO_VARIACION:
            lista.append(schemas.Hallazgo(
                tipo="sube", titulo=f"{mejor.area_nombre} subió {mejor.variacion:.2f} puntos",
                detalle=f"Promedio {mejor.promedio_base:.2f} → {mejor.promedio_comparado:.2f} en {mejor.total_evaluados} notas comparables.",
                accion={"filtro": "area_id", "valor": mejor.area_id, "nombre": mejor.area_nombre}, evidencia=evidencia_area(mejor),
            ))

    con_hoy = [a for a in areas if a.actual_evaluados >= HALLAZGO_MIN_AREA]
    if con_hoy:
        foco = max(con_hoy, key=lambda a: _pct(a.actual_n_bajo, a.actual_evaluados))
        pct_foco = _pct(foco.actual_n_bajo, foco.actual_evaluados)
        if pct_foco >= HALLAZGO_PCT_BAJO_ACTUAL:
            lista.append(schemas.Hallazgo(
                tipo="alerta", titulo=f"{foco.area_nombre} concentra la mayor dificultad hoy",
                detalle=f"{pct_foco:.0f}% de sus notas del {npc} están en desempeño bajo ({foco.actual_n_bajo} de {foco.actual_evaluados}).",
                accion={"filtro": "area_id", "valor": foco.area_id, "nombre": foco.area_nombre},
                evidencia=[[x.area_nombre, f"{_pct(x.actual_n_bajo, x.actual_evaluados):.0f}% en bajo ({x.actual_n_bajo} de {x.actual_evaluados})"]
                           for x in sorted(con_hoy, key=lambda x: -_pct(x.actual_n_bajo, x.actual_evaluados))[:5]],
            ))

    comparables_grado = [g for g in grados if g.estudiantes_comparables >= HALLAZGO_MIN_GRADO]
    if comparables_grado:
        def pp_bajo(g):
            m = g.estudiantes_comparables
            return _pct(g.entraron_a_bajo + g.permanecen_en_bajo, m) - _pct(g.salieron_de_bajo + g.permanecen_en_bajo, m)
        peor = max(comparables_grado, key=pp_bajo)
        if pp_bajo(peor) >= HALLAZGO_PUNTOS_PCT:
            m = peor.estudiantes_comparables
            antes, ahora = peor.salieron_de_bajo + peor.permanecen_en_bajo, peor.entraron_a_bajo + peor.permanecen_en_bajo
            lista.append(schemas.Hallazgo(
                tipo="baja", titulo=f"En {peor.nombre_grado} el desempeño bajo subió {pp_bajo(peor):.0f} puntos porcentuales",
                detalle=f"De {_pct(antes, m):.0f}% ({antes}) a {_pct(ahora, m):.0f}% ({ahora}) entre sus {m} estudiantes comparables.",
                accion={"filtro": "grado", "valor": peor.grado, "nombre": peor.nombre_grado},
                evidencia=[[g.nombre_grado, f"{pp_bajo(g):+.0f} pp · promedio {g.variacion:+.2f}"]
                           for g in sorted(comparables_grado, key=lambda g: -pp_bajo(g))[:5]],
            ))
        caida = min(comparables_grado, key=lambda g: g.variacion)
        if caida.variacion <= -HALLAZGO_VARIACION and not (pp_bajo(peor) >= HALLAZGO_PUNTOS_PCT and caida.grado == peor.grado):
            lista.append(schemas.Hallazgo(
                tipo="baja", titulo=f"{caida.nombre_grado} tuvo la mayor caída de promedio",
                detalle=f"{caida.promedio_base:.2f} → {caida.promedio_comparado:.2f} ({caida.variacion:+.2f}) en {caida.estudiantes_comparables} estudiantes comparables.",
                accion={"filtro": "grado", "valor": caida.grado, "nombre": caida.nombre_grado},
                evidencia=[[g.nombre_grado, f"{g.promedio_base:.2f} → {g.promedio_comparado:.2f} ({g.variacion:+.2f})"]
                           for g in sorted(comparables_grado, key=lambda g: g.variacion)[:5]],
            ))

    if n and r.salieron_de_bajo:
        lista.append(schemas.Hallazgo(
            tipo="ok", titulo=f"{r.salieron_de_bajo} estudiantes salieron de desempeño bajo",
            detalle=f"Estaban por debajo de {corte} en el {npb} y ya no.", accion={"cambio": "salieron_bajo"},
        ))
    if n and r.mejoraron:
        lista.append(schemas.Hallazgo(
            tipo="ok", titulo=f"{r.mejoraron} estudiantes mejoraron su promedio",
            detalle=f"Subieron {cfg.umbral_mejora:.1f} o más entre el {npb} y el {npc} ({r.pct_mejoraron:.0f}% de los {n} comparados).",
            accion={"cambio": "mejoraron"},
        ))

    orden = {"alerta": 0, "baja": 1, "sube": 2, "ok": 3}
    lista.sort(key=lambda h: orden[h.tipo])  # estable: respeta el orden de las reglas dentro de cada tipo
    return lista


# Caché corta del panorama: la pantalla va y vuelve entre Resumen, Áreas y
# Grados (y al filtro anterior) con los mismos parámetros. Misma idea que
# evaluacion_docente._preparar: la clave lleva una "huella" de los datos, así
# un import nuevo de SAPRED, un cambio de asignación o un retiro la invalida.
_CACHE_PANORAMA: dict = {}
_CACHE_PANORAMA_SEGUNDOS = 300
_CACHE_PANORAMA_ENTRADAS = 12


def _huella_datos(db: Session) -> tuple:
    from sqlalchemy import func

    return (
        db.scalar(select(func.count(models.NotaSapred.id))), db.scalar(select(func.max(models.NotaSapred.id))),
        db.scalar(select(func.max(models.NotaSapred.actualizado_en))),
        db.scalar(select(func.max(models.AsignacionDocente.id))), db.scalar(select(func.count(models.AsignacionDocente.id))),
        db.scalar(select(func.count(models.Estudiante.id)).where(models.Estudiante.estado == "ACTIVO")),
    )


def panorama_cacheado(db: Session, p: dict) -> schemas.PanoramaAcademico:
    import time

    clave = (repr(sorted((k, repr(v)) for k, v in p.items())), _huella_datos(db))
    ahora = time.monotonic()
    guardado = _CACHE_PANORAMA.get(clave)
    if guardado and ahora - guardado[0] < _CACHE_PANORAMA_SEGUNDOS:
        return guardado[1]
    resultado = panorama(db, p)
    if len(_CACHE_PANORAMA) >= _CACHE_PANORAMA_ENTRADAS:
        _CACHE_PANORAMA.pop(min(_CACHE_PANORAMA, key=lambda k: _CACHE_PANORAMA[k][0]))
    _CACHE_PANORAMA[clave] = (ahora, resultado)
    return resultado


def panorama(db: Session, p: dict) -> schemas.PanoramaAcademico:
    """Resumen + evolución + áreas + grados + grupos + sedes + hallazgos en
    una sola pasada de comparar() (p = router._parametros_comparacion)."""
    config = p["config"]
    memo: dict = {}
    filas = comparar(db, **p, memo=memo)
    disponibles = periodos_disponibles(db)
    pb = periodo_disponible(disponibles, *p["base"])
    pc = periodo_disponible(disponibles, *p["comparado"])
    r = resumen_global(filas, periodo_base=pb, periodo_comparado=pc, config=config)
    evol = evolucion(
        db, anio_lectivo=p["comparado"][0], sede_id=p["sede_id"], grado=p["grado"], curso=p["curso"],
        area_id=p["area_id"], docente_id=p["docente_id"], estado=p["estado"], config=config, memo=memo,
    )
    areas = por_area(filas, config)
    grados = por_grado(filas, config)
    return schemas.PanoramaAcademico(
        resumen=r, lectura=lectura_general(r, pb, pc), evolucion=evol, areas=areas, grados=grados,
        grupos=por_grupo(filas, config), sedes=por_sede(filas, config),
        hallazgos=hallazgos(r, _agregar_por_estudiante(filas, config), areas, grados, evol, pb, pc),
    )


def matriz_transicion(filas: list[schemas.FilaComparacionAcademica]) -> schemas.MatrizTransicion:
    comparables = [f for f in filas if f.comparable]
    conteo: dict[tuple[str, str], int] = {}
    for f in comparables:
        clave = (f.nivel_base, f.nivel_comparado)
        conteo[clave] = conteo.get(clave, 0) + 1

    celdas = [
        schemas.CeldaMatrizTransicion(nivel_base=nb, nivel_comparado=nc, cantidad=conteo.get((nb, nc), 0))
        for nb in schemas.NIVELES_DESEMPENO
        for nc in schemas.NIVELES_DESEMPENO
    ]
    return schemas.MatrizTransicion(total_comparables=len(comparables), celdas=celdas)


def alertas(filas: list[schemas.FilaComparacionAcademica]) -> list[schemas.AlertaAcademica]:
    """Solo seguimiento (sección 13 del pedido): nunca un diagnóstico sobre
    el estudiante, solo el hecho y la evidencia detrás."""
    resultado = []
    for f in filas:
        if not f.comparable:
            continue
        tipo = None
        if f.categoria_variacion == "DESCENSO_SIGNIFICATIVO":
            tipo = "descenso_significativo"
        elif f.nivel_base != "BAJO" and f.nivel_comparado == "BAJO":
            tipo = "entro_a_bajo"
        elif f.nivel_base == "BAJO" and f.nivel_comparado == "BAJO":
            tipo = "permanece_en_bajo"
        elif f.categoria_variacion == "MEJORA_SIGNIFICATIVA":
            tipo = "mejora_significativa"
        if tipo is None:
            continue
        resultado.append(schemas.AlertaAcademica(
            tipo=tipo, estudiante_id=f.estudiante_id, nombre_completo=f.nombre_completo, documento=f.documento,
            sede_nombre=f.sede_nombre, nombre_grupo=f.nombre_grupo, area_nombre=f.area_nombre,
            valor_base=f.valor_base, valor_comparado=f.valor_comparado, delta=f.delta,
        ))
    orden = {"descenso_significativo": 0, "entro_a_bajo": 1, "permanece_en_bajo": 2, "mejora_significativa": 3}
    resultado.sort(key=lambda a: (orden[a.tipo], a.delta if a.delta is not None else 0))
    return resultado


# --- ¿Quién puede perder el año? (pedido 05/10/2026) -----------------------
#
# Regla del colegio (reporte_notas.riesgo_promocion): la nota final de cada
# materia es el PROMEDIO SIMPLE de los períodos y una sola materia perdida
# (final < 3.0) es año perdido. El año tiene 4 períodos con el mismo peso
# (confirmado con el usuario). Por materia: qué promedio necesita en los
# períodos que faltan para cerrar en 3.0.
#   necesita > 5.0          -> NO_RECUPERA (ni con 5.0 en todo lo que falta)
#   necesita >= 4.0         -> POSIBLE_PERDIDA
#   necesita > 3.0          -> CUIDADO (hoy va perdiendo, pero se puede)
# Con el año completo: final < 3.0 -> NO_RECUPERA.

PERIODOS_POR_ANIO = 4
ANIO_UMBRAL_POSIBLE_PERDIDA = 4.0
CATEGORIAS_ANIO = ("NO_RECUPERA", "POSIBLE_PERDIDA", "CUIDADO")


def _categoria_anio(necesita: float | None, final: float | None, config: schemas.ConfigComparacion) -> str | None:
    minima = round(config.nivel_bajo_hasta + 0.1, 2)
    if necesita is None:
        return "NO_RECUPERA" if final is not None and final < minima else None
    if necesita > config.escala_max:
        return "NO_RECUPERA"
    if necesita >= ANIO_UMBRAL_POSIBLE_PERDIDA:
        return "POSIBLE_PERDIDA"
    if necesita > minima:
        return "CUIDADO"
    return None


def riesgo_perder_anio(
    db: Session, *, anio_lectivo: int, hasta_periodo: int,
    sede_id: int | None = None, grado: int | None = None, curso: int | None = None,
    area_id: int | None = None, estado: str | None = "ACTIVO",
    config: schemas.ConfigComparacion | None = None,
) -> schemas.RiesgoAnio:
    config = config or schemas.ConfigComparacion()
    minima = round(config.nivel_bajo_hasta + 0.1, 2)
    memo: dict = {}
    por_periodo = {
        p: _notas_periodo(db, anio_lectivo, p, sede_id=sede_id, grado=grado, curso=curso, area_id=area_id, memo=memo)
        for p in range(1, hasta_periodo + 1)
    }
    claves = set().union(*por_periodo.values()) if por_periodo else set()
    estudiantes, areas = {}, {}
    if claves:
        estudiantes = {
            e.id: e for e in db.scalars(select(models.Estudiante).where(models.Estudiante.id.in_({c[0] for c in claves}))).all()
        }
        areas = {a.id: a for a in db.scalars(select(models.Area).where(models.Area.id.in_({c[1] for c in claves}))).all()}

    # Nota mínima masiva en el último período de cada grupo+materia: nota no
    # cargada (mismo criterio que la señal de retiro), no cuenta para perder.
    conteo: dict[tuple, list[int]] = {}
    for (_e, ar), ctx in por_periodo.get(hasta_periodo, {}).items():
        c = conteo.setdefault((ctx.sede_id, ctx.grado, ctx.curso, ar), [0, 0])
        c[1] += 1
        if ctx.valor <= config.escala_min:
            c[0] += 1
    masiva = {k for k, (m, n) in conteo.items() if m >= MINIMA_MASIVA_MIN_ESTUDIANTES and m / n >= MINIMA_MASIVA_FRACCION}

    agrupado: dict[int, dict] = {}
    for est_id, ar_id in claves:
        est, area = estudiantes.get(est_id), areas.get(ar_id)
        if est is None or area is None:
            continue
        if area_id is None and area.codigo == AREA_ACTITUDINAL:
            continue
        if estado is not None and est.estado != estado:
            continue
        notas = {p: por_periodo[p][(est_id, ar_id)] for p in por_periodo if (est_id, ar_id) in por_periodo[p]}
        p_ultimo = max(notas)
        ultimo = notas[p_ultimo]
        d = agrupado.setdefault(est_id, {"est": est, "ctx": ultimo, "p_ctx": p_ultimo, "periodos": set(), "materias": []})
        if p_ultimo > d["p_ctx"]:
            d["ctx"], d["p_ctx"] = ultimo, p_ultimo
        d["periodos"].update(notas)
        valores = [c.valor for c in notas.values()]
        suma, k = sum(valores), len(valores)
        faltan = PERIODOS_POR_ANIO - k
        necesita = round((minima * PERIODOS_POR_ANIO - suma) / faltan, 2) if faltan > 0 else None
        final = round(suma / k, 2) if faltan <= 0 else None
        sin_cargar = (ultimo.sede_id, ultimo.grado, ultimo.curso, ar_id) in masiva and ultimo.valor <= config.escala_min
        categoria = None if sin_cargar else _categoria_anio(necesita, final, config)
        d["materias"].append(schemas.MateriaRiesgoAnio(
            area_id=ar_id, area_nombre=area.nombre,
            notas=[schemas.NotaPorPeriodo(periodo=p, valor=c.valor) for p, c in sorted(notas.items())],
            promedio=round(suma / k, 2), necesita=necesita, final=final, categoria=categoria, sin_cargar=sin_cargar,
        ))

    orden = {c: i for i, c in enumerate(CATEGORIAS_ANIO)}
    resultado = []
    for d in agrupado.values():
        en_riesgo = sorted(
            (m for m in d["materias"] if m.categoria),
            key=lambda m: (orden[m.categoria], -(m.necesita if m.necesita is not None else 99)),
        )
        if not en_riesgo:
            continue
        est, ctx = d["est"], d["ctx"]
        nombre_grado = models.GRADOS_NOMBRES.get(ctx.grado, str(ctx.grado))
        resultado.append(schemas.EstudianteRiesgoAnio(
            estudiante_id=est.id, documento=est.documento, nombre_completo=est.nombre_completo,
            sede_id=ctx.sede_id, sede_nombre=ctx.sede_nombre, grado=ctx.grado, nombre_grado=nombre_grado,
            curso=ctx.curso,
            nombre_grupo=f"{nombre_grado} - {models.DIVISIONES_NOMBRES.get(ctx.curso, ctx.curso)}" if ctx.curso else nombre_grado,
            categoria=en_riesgo[0].categoria, periodos_con_nota=len(d["periodos"]), materias=en_riesgo,
        ))
    resultado.sort(key=lambda e: (
        orden[e.categoria], -sum(1 for m in e.materias if m.categoria == e.categoria), e.nombre_completo,
    ))
    return schemas.RiesgoAnio(
        anio_lectivo=anio_lectivo, hasta_periodo=hasta_periodo, periodos_anio=PERIODOS_POR_ANIO,
        nota_minima=minima, nota_maxima=config.escala_max, umbral_posible_perdida=ANIO_UMBRAL_POSIBLE_PERDIDA,
        total_estudiantes=len(agrupado), estudiantes=resultado,
    )


# --- Períodos disponibles (para que el selector nunca invente un P3) --------


def periodos_disponibles(db: Session) -> list[schemas.PeriodoDisponible]:
    filas = db.execute(
        select(models.RevisionBoletin.anio_lectivo, models.RevisionBoletin.periodo, models.RevisionBoletin.id)
    ).all()
    conteo: dict[tuple[int, int], int] = {}
    for anio, periodo, _id in filas:
        conteo[(anio, periodo)] = conteo.get((anio, periodo), 0) + 1
    resultado = [
        schemas.PeriodoDisponible(anio_lectivo=anio, periodo=periodo, revisiones=n)
        for (anio, periodo), n in conteo.items()
    ]
    resultado.sort(key=lambda p: (p.anio_lectivo, p.periodo))
    return resultado


def periodo_disponible(disponibles: list[schemas.PeriodoDisponible], anio: int, periodo: int) -> schemas.PeriodoDisponible:
    """Busca (anio, periodo) en la lista de periodos_disponibles(); si no
    hay revisiones todavía para ese par, igual devuelve un PeriodoDisponible
    con revisiones=0 (el selector del frontend nunca debe crashear porque
    alguien pidió un período que aún no existe)."""
    for p in disponibles:
        if p.anio_lectivo == anio and p.periodo == periodo:
            return p
    return schemas.PeriodoDisponible(anio_lectivo=anio, periodo=periodo, revisiones=0)


# --- Perfil académico del estudiante (serie completa, N períodos) ----------


def perfil_estudiante(
    db: Session, estudiante_id: int, anio_lectivo: int, config: schemas.ConfigComparacion | None = None,
) -> schemas.PerfilAcademicoEstudiante:
    config = config or schemas.ConfigComparacion()
    estudiante = db.get(models.Estudiante, estudiante_id)
    if estudiante is None:
        raise NoEncontrado(f"Estudiante {estudiante_id} no encontrado.")

    filas = db.execute(
        select(models.NotaSapred, models.RevisionBoletin, models.Area)
        .join(models.RevisionBoletin, models.NotaSapred.revision_id == models.RevisionBoletin.id)
        .join(models.Area, models.NotaSapred.area_id == models.Area.id)
        .where(models.NotaSapred.estudiante_id == estudiante_id, models.RevisionBoletin.anio_lectivo == anio_lectivo)
    ).all()

    por_area_dict: dict[int, dict[int, tuple[float, models.Area]]] = {}
    for nota, revision, area in filas:
        try:
            valor = float(nota.valor)
        except (TypeError, ValueError):
            continue
        # última importación de cada período (por si hubo reimportaciones),
        # mismo criterio que reporte_notas.reporte_tendencia.
        por_area_dict.setdefault(area.id, {})[revision.periodo] = (valor, area)

    areas_resultado = []
    for area_id, por_periodo in por_area_dict.items():
        periodos_ordenados = sorted(por_periodo)
        notas = [schemas.NotaPorPeriodo(periodo=p, valor=por_periodo[p][0]) for p in periodos_ordenados]
        variacion_reciente = None
        categoria_reciente = None
        if len(periodos_ordenados) >= 2:
            v0 = por_periodo[periodos_ordenados[-2]][0]
            v1 = por_periodo[periodos_ordenados[-1]][0]
            variacion_reciente = round(v1 - v0, 2)
            categoria_reciente = clasificar_variacion(variacion_reciente, config)
        area = next(iter(por_periodo.values()))[1]
        areas_resultado.append(schemas.SerieAreaEstudiante(
            area_id=area_id, area_codigo=area.codigo, area_nombre=area.nombre,
            notas=notas, variacion_reciente=variacion_reciente, categoria_variacion_reciente=categoria_reciente,
        ))
    areas_resultado.sort(key=lambda a: a.area_nombre)

    return schemas.PerfilAcademicoEstudiante(
        estudiante_id=estudiante.id, documento=estudiante.documento, nombre_completo=estudiante.nombre_completo,
        grado=estudiante.grado, nombre_grado=models.GRADOS_NOMBRES.get(estudiante.grado, str(estudiante.grado)),
        curso=estudiante.curso, nombre_grupo=estudiante.grupo, anio_lectivo=anio_lectivo, areas=areas_resultado,
    )


# --- Exportación a Excel -----------------------------------------------------


def exportar_comparacion_excel(
    resumen: schemas.ResumenComparacion, filas: list[schemas.FilaComparacionAcademica], titulo: str,
) -> bytes:
    import io

    import openpyxl
    from openpyxl.styles import Font

    libro = openpyxl.Workbook()

    hoja_resumen = libro.active
    hoja_resumen.title = "Resumen"
    hoja_resumen.append([titulo])
    hoja_resumen.append([])
    hoja_resumen.append(["Indicador", "Valor"])
    for celda in hoja_resumen[3]:
        celda.font = Font(bold=True)
    filas_resumen = [
        ("Estudiantes comparables", f"{resumen.estudiantes_comparables} de {resumen.total_estudiantes}"),
        ("Promedio período base", resumen.promedio_base),
        ("Promedio período comparado", resumen.promedio_comparado),
        ("Variación promedio", resumen.variacion_promedio),
        ("Mejoraron", f"{resumen.mejoraron} ({resumen.pct_mejoraron}%)"),
        ("Empeoraron", f"{resumen.empeoraron} ({resumen.pct_empeoraron}%)"),
        ("Estables", f"{resumen.estables} ({resumen.pct_estables}%)"),
        ("Salieron de bajo rendimiento", resumen.salieron_de_bajo),
        ("Entraron a bajo rendimiento", resumen.entraron_a_bajo),
        ("Permanecen en bajo rendimiento", resumen.permanecen_en_bajo),
    ]
    for etiqueta, valor in filas_resumen:
        hoja_resumen.append([etiqueta, valor])
    hoja_resumen.append([])
    hoja_resumen.append([resumen.informe_texto])
    hoja_resumen.column_dimensions["A"].width = 30
    hoja_resumen.column_dimensions["B"].width = 50

    hoja_detalle = libro.create_sheet("Detalle")
    hoja_detalle.append([
        "Sede", "Grupo", "Estudiante", "Documento", "Área", "Docente",
        "Valor base", "Valor comparado", "Variación", "Categoría", "Nivel base", "Nivel comparado", "Comparable",
    ])
    for celda in hoja_detalle[1]:
        celda.font = Font(bold=True)
    for f in filas:
        hoja_detalle.append([
            f.sede_nombre, f.nombre_grupo, f.nombre_completo, f.documento, f.area_nombre, f.docente_nombre or "Sin asignar",
            f.valor_base, f.valor_comparado, f.delta, f.categoria_variacion or "", f.nivel_base or "", f.nivel_comparado or "",
            "Sí" if f.comparable else "No",
        ])
    for columna, ancho in zip(hoja_detalle.columns, [22, 16, 30, 14, 24, 26, 10, 12, 10, 20, 12, 14, 10]):
        hoja_detalle.column_dimensions[columna[0].column_letter].width = ancho

    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()
