"""Importa el Excel "DIAGNOSTICO IETABA" (una hoja por grado, diligenciada a
mano por cada director de grupo para orientación/psicología) hacia
DiagnosticoGrado + DiagnosticoMencion.

El archivo NO es una tabla limpia: cada hoja es un formulario narrativo con
etiquetas sueltas (ej. "Dificultades academicas presentadas") cuyo valor
sigue en las celdas de al lado o de abajo, y la posición exacta varía de
hoja en hoja porque cada docente lo llenó a su manera. La estrategia:

  1. Se recorre toda la hoja buscando celdas que EMPIECEN con una de las
     frases conocidas de `ETIQUETAS` (comparando sin tildes/mayúsculas) —
     esas son "anclas".
  2. El valor de cada ancla es el texto que sigue: primero lo que queda en
     la misma celda después de la etiqueta (ej. "Estudiantes que no
     asisten: 3" -> "3"), más lo que haya en las columnas siguientes de esa
     misma fila (hasta la próxima ancla de esa fila) y en esas mismas
     columnas en las filas de abajo (hasta la próxima fila que traiga
     cualquier ancla, en cualquier columna — ese es el límite del bloque).
  3. Nunca se pierde nada: `texto_crudo` guarda cada celda no vacía de la
     hoja tal cual, como red de seguridad para lo que la extracción por
     campo no haya podido ubicar bien.

Los NOMBRES de estudiantes mencionados dentro de esos textos (quién no
asiste, quién es intermitente, quién tiene una dificultad...) se detectan
con una heurística de mayúsculas (ver `_candidatos_nombre`) y se intentan
enlazar con el Estudiante real del mismo grado (ver `vincular_estudiante`);
si no hay una coincidencia clara quedan sin enlazar para que orientación lo
haga a mano — nunca se adivina con baja confianza un dato sensible."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, field

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .certificados import MESES_TEXTO
from .texto import sin_tildes

_MES_NUMERO = {sin_tildes(nombre): numero for numero, nombre in MESES_TEXTO.items()}
_RE_FECHA_TEXTO = re.compile(
    r"(" + "|".join(_MES_NUMERO) + r")\s+(\d{1,2})\s*(?:de)?\s*(?:del?)?\s*(\d{4})"
)

# --- Catálogo de etiquetas conocidas ----------------------------------------
# (campo del modelo, patrón que debe estar al INICIO de la celda ya
# normalizada). Los tres primeros son el bloque numérico de cabecera: su
# valor vive en la(s) columna(s) inmediatamente a la derecha, en la MISMA
# fila. El resto es texto narrativo: su valor puede seguir varias filas
# abajo en las mismas columnas.
CAMPO_EN_LISTA = "n_en_lista"
CAMPO_ASISTEN = "n_asisten"

ETIQUETAS: list[tuple[str, re.Pattern]] = [
    (CAMPO_EN_LISTA, re.compile(r"^no\.?\s*estudiantes?\s*(en|n)\s*lista")),
    (CAMPO_ASISTEN, re.compile(r"^estudiantes?\s*que\s*est[ae]n\s*asistiendo")),
    ("no_asisten_texto", re.compile(r"^estudiantes?\s*que\s*no\s*asisten")),
    ("desplazados_texto", re.compile(r"^estudiantes?\s*desplazados")),
    ("embarazadas_texto", re.compile(r"^estudiantes?\s*embarazadas")),
    ("victimas_conflicto_texto", re.compile(r"^estudiantes?\s*victimas?\s*de\s*conflicto\s*armado")),
    ("dificultades_academicas", re.compile(r"^dificultades\s*academicas(\s*presentadas)?")),
    ("dificultades_comportamiento", re.compile(r"^dificultades\s*de\s*comportamiento(\s*presentadas)?")),
    ("acompanamiento_padres", re.compile(r"^acompa.amiento\s*de\s*los\s*padres\s*de\s*familia")),
    ("problemas_salud", re.compile(r"^problemas\s*de\s*salud\s*en\s*general")),
    ("tematicas_trabajar", re.compile(r"^tematicas\s*para\s*trabajar\s*con\s*los\s*estudiantes")),
    ("estrategias_conflicto", re.compile(r"^estrategias\s*que\s*utiliza\s*el\s*docente\s*y\s*director\s*para\s*solucionar\s*los\s*conflictos\s*\??")),
    ("estrategias_aprendizaje", re.compile(r"^estrategias\s*que\s*utiliza\s*para\s*fortalecer\s*el\s*aprendizaje")),
    ("resguardos_atendidos", re.compile(r"^cuales\s*son\s*los\s*resguardos\s*que\s*se\s*atienden\s*\??")),
    ("recomendaciones_docentes", re.compile(r"^recomendaciones\s*de\s*los\s*docentes")),
    ("llamados_atencion", re.compile(r"^estudiantes?\s*con\s*llamados\s*de\s*atencion")),
    ("orientacion_brindada", re.compile(r"^estudiantes?\s*que\s*se\s*ha\s*brindado\s*la\s*orientacion")),
    ("transporte_escolar", re.compile(r"^no\.?\s*estudiantes?\s*que\s*utli?zan\s*el\s*transporte\s*escolar")),
    ("observaciones_generales", re.compile(r"^observaciones\s*:?")),
    ("director_grado_nombre", re.compile(r"^firma\s*del\s*director\s*de\s*grado")),
    ("orientador_escolar_nombre", re.compile(r"^firma\s*del\s*orientador\s*escolar")),
    ("seguimiento_nota", re.compile(r"^seguimiento\s*:?$")),
]

CAMPOS_HEADER = {CAMPO_EN_LISTA, CAMPO_ASISTEN}

# Categorías de mención por campo narrativo (para DiagnosticoMencion). Los
# campos que no aparecen aquí no generan menciones (son texto de contexto
# general del grado, no de un estudiante puntual).
CAMPO_A_CATEGORIA = {
    "no_asisten_texto": "no_asiste",
    "desplazados_texto": "desplazado",
    "embarazadas_texto": "embarazada",
    "victimas_conflicto_texto": "victima_conflicto",
    "dificultades_academicas": "dificultad_academica",
    "dificultades_comportamiento": "dificultad_comportamiento",
    "problemas_salud": "salud",
    "llamados_atencion": "llamado_atencion",
}

_RE_NOMBRE = re.compile(
    r"(?:[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]+|[A-ZÁÉÍÓÚÑÜ]{2,})"
    r"(?:\s+(?:[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]+|[A-ZÁÉÍÓÚÑÜ]{2,})){1,4}"
)
_RE_INTERMITENCIA = re.compile(r"^intermitenc", re.IGNORECASE)


@dataclass
class HojaDiagnostico:
    hoja_excel: str
    grado: int
    curso: int | None
    fecha: dt.date | None = None
    campos: dict[str, str] = field(default_factory=dict)
    texto_crudo: str = ""


def _etiqueta_de(texto_normalizado: str) -> tuple[str, re.Match] | None:
    for campo, patron in ETIQUETAS:
        m = patron.match(texto_normalizado)
        if m:
            return campo, m
    return None


def _grado_curso_de_hoja(nombre_hoja: str) -> tuple[int, int | None] | None:
    t = sin_tildes(nombre_hoja).strip()
    if "preescolar" in t:
        return 0, None
    m = re.search(r"(\d{1,2})\s*[.\-]\s*(\d{1,2})", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{1,2})", t)
    if m:
        return int(m.group(1)), None
    return None


# Marcas sueltas de la plantilla que no son respuesta (en 2026, "DX" quedó
# en la celda de "estrategias para fortalecer el aprendizaje" de 8 hojas).
MARCAS_NO_RESPUESTA = {"dx"}


def _celda_texto(valor) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _es_marca(texto: str) -> bool:
    return sin_tildes(texto).strip().lower() in MARCAS_NO_RESPUESTA


def _extraer_fecha(ws) -> dt.date | None:
    """La fecha del diagnóstico ("LUGAR Y FECHA" / "MARZO 19 DE 2026") no
    tiene una posición fija — se busca entre las primeras filas, primero
    como valor de fecha real de Excel, luego como texto en español."""
    for fila in ws.iter_rows(max_row=min(8, ws.max_row)):
        for celda in fila:
            v = celda.value
            if isinstance(v, dt.datetime):
                return v.date()
            if isinstance(v, dt.date):
                return v
    for fila in ws.iter_rows(max_row=min(8, ws.max_row)):
        for celda in fila:
            texto = _celda_texto(celda.value)
            if not texto:
                continue
            m = _RE_FECHA_TEXTO.search(sin_tildes(texto))
            if m:
                mes = _MES_NUMERO[m.group(1)]
                try:
                    return dt.date(int(m.group(3)), mes, int(m.group(2)))
                except ValueError:
                    continue
    return None


def leer_hoja(ws, ignorar: set[tuple[int, int]] | None = None) -> HojaDiagnostico | None:
    """`ignorar`: celdas (fila, col) que son sobrante de plantilla en ESTA
    hoja (ver detectar_sobrantes_plantilla) — no entran a ningún campo."""
    ignorar = ignorar or set()
    info = _grado_curso_de_hoja(ws.title)
    if info is None:
        return None
    grado, curso = info
    fecha = _extraer_fecha(ws)

    filas = list(ws.iter_rows())
    if not filas:
        return None
    max_col = ws.max_column

    # --- Anclas: (fila, col, campo, remanente_en_la_misma_celda) -----------
    anclas: list[tuple[int, int, str, str]] = []
    crudo: list[str] = []
    for fila in filas:
        for celda in fila:
            texto = _celda_texto(celda.value)
            if not texto or (celda.row, celda.column) in ignorar:
                continue
            crudo.append(texto)
            encontrada = _etiqueta_de(sin_tildes(texto))
            if encontrada:
                campo, m = encontrada
                remanente = texto[m.end():].lstrip(" :·-\t")
                anclas.append((celda.row, celda.column, campo, remanente))

    if not anclas:
        return HojaDiagnostico(hoja_excel=ws.title, grado=grado, curso=curso, fecha=fecha, texto_crudo="\n".join(crudo))

    filas_ancla = sorted({a[0] for a in anclas})
    anclas_por_fila: dict[int, list[int]] = {}
    for fr, fc, _, _ in anclas:
        anclas_por_fila.setdefault(fr, []).append(fc)

    valores: dict[str, list[str]] = {}
    ignorar_todo = ignorar
    for fila_ancla, col_ancla, campo, remanente in anclas:
        ignorar = set() if campo in CAMPOS_SIN_SOBRANTE else ignorar_todo
        siguiente_fila_ancla = next((f for f in filas_ancla if f > fila_ancla), ws.max_row + 1)
        cols_misma_fila = sorted(c for c in anclas_por_fila.get(fila_ancla, []) if c > col_ancla)
        limite_col = cols_misma_fila[0] if cols_misma_fila else min(col_ancla + 3, max_col + 1)

        partes: list[str] = [remanente] if remanente else []
        # Misma fila, columnas entre la etiqueta y la próxima ancla (o +2).
        for c in range(col_ancla + 1, limite_col):
            v = _celda_texto(ws.cell(fila_ancla, c).value) if (fila_ancla, c) not in ignorar else ""
            if v and not _es_marca(v):
                partes.append(v)
        # Filas de abajo, mismas columnas (incluida la de la propia
        # etiqueta: varias hojas siguen el relato justo debajo del rótulo).
        for r in range(fila_ancla + 1, siguiente_fila_ancla):
            for c in range(col_ancla, limite_col):
                v = _celda_texto(ws.cell(r, c).value) if (r, c) not in ignorar else ""
                if v and not _es_marca(v) and not _etiqueta_de(sin_tildes(v)):
                    partes.append(v)
        if partes:
            valores.setdefault(campo, []).extend(partes)

    campos: dict[str, str] = {k: "; ".join(dict.fromkeys(v)) for k, v in valores.items() if v}
    return HojaDiagnostico(hoja_excel=ws.title, grado=grado, curso=curso, fecha=fecha, campos=campos, texto_crudo="\n".join(crudo))


# Sobrante de plantilla: en el Excel real (2026) las hojas se armaron
# copiando una ya llenada, y un texto de Preescolar («Se siente muy bien en
# el desempeño de sus tejidos…», «Tortugaña Telembi, Guelmambi Caraño») quedó
# en las mismas celdas de 26 hojas más — el sistema se lo atribuía a cada
# grado. Regla: texto LARGO (respuestas cortas como "0"/"Ninguno" se repiten
# legítimamente) idéntico en la MISMA celda en muchas hojas = copiado; solo
# cuenta en la primera hoja donde aparece (la original). Decisión del
# usuario 24/09/2026.
# 12: alcanza a nombres de estudiantes copiados ("Erick Andrey Nastacuas") y
# deja fuera respuestas cortas legítimas ("0", "ninguno", "Inasisten").
SOBRANTE_MIN_CARACTERES = 12
# Nunca se tratan como sobrante: las firmas (el mismo orientador/director
# firma muchas hojas de verdad) — ver leer_hoja.
CAMPOS_SIN_SOBRANTE = {"director_grado_nombre", "orientador_escolar_nombre"}
SOBRANTE_MIN_HOJAS = 5
SOBRANTE_FRACCION = 0.4


def detectar_sobrantes_plantilla(hojas_ws: list) -> dict[str, set[tuple[int, int]]]:
    """nombre de hoja -> celdas a ignorar en ella (todas menos la original).
    Se compara el TEXTO, no la posición: en una hoja el mismo sobrante quedó
    una fila más abajo (L23 en vez de L22)."""
    apariciones: dict[str, dict[str, list[tuple[int, int]]]] = {}  # texto -> hoja -> celdas
    for ws in hojas_ws:
        for fila in ws.iter_rows():
            for celda in fila:
                texto = _celda_texto(celda.value)
                if len(texto) < SOBRANTE_MIN_CARACTERES or _etiqueta_de(sin_tildes(texto)):
                    continue
                # Subtítulos ("Intermitencia:") organizan la respuesta real: se conservan.
                if texto.rstrip().endswith(":") or _RE_INTERMITENCIA.match(texto.strip()) and len(texto) < 20:
                    continue
                clave = " ".join(texto.split())
                apariciones.setdefault(clave, {}).setdefault(ws.title, []).append((celda.row, celda.column))
    minimo = max(SOBRANTE_MIN_HOJAS, int(len(hojas_ws) * SOBRANTE_FRACCION))
    ignorar: dict[str, set[tuple[int, int]]] = {}
    for por_hoja in apariciones.values():
        if len(por_hoja) >= minimo:
            for nombre in list(por_hoja)[1:]:  # la primera (orden del libro) es la original
                ignorar.setdefault(nombre, set()).update(por_hoja[nombre])
    return ignorar


def leer_libro(ruta) -> list[HojaDiagnostico]:
    wb = openpyxl.load_workbook(ruta, data_only=True)
    hojas: list[HojaDiagnostico] = []
    hojas_dx = [wb[n] for n in wb.sheetnames if sin_tildes(n).strip().startswith("dx")]
    sobrantes = detectar_sobrantes_plantilla(hojas_dx)
    for ws in hojas_dx:
        h = leer_hoja(ws, sobrantes.get(ws.title))
        if h is not None and (h.campos or h.texto_crudo):
            hojas.append(h)
    return hojas


def _a_entero(texto: str | None) -> int | None:
    if not texto:
        return None
    m = re.search(r"\d+", texto)
    return int(m.group()) if m else None


def contenido_hash(hoja: HojaDiagnostico) -> str:
    base = "\x1f".join(f"{k}={v}" for k, v in sorted(hoja.campos.items()))
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _limpiar_borde(texto: str) -> str:
    """Quita separadores sueltos (coma, punto y coma, guiones, espacios) de
    los bordes de un fragmento de texto, sin tocar lo de adentro."""
    return re.sub(r"^[\s,;:.\-–]+|[\s,;:.\-–]+$", "", texto)


# Cuánto texto "real" (ya sin comas/conectores de borde) tiene que separar a
# dos nombres para considerar que ESE texto es el detalle propio del primero
# y no solo un conector ("y", ", "). Deliberadamente bajo: frases reales en
# español suelen ser cortas ("No memoriza" = 11 caracteres) y si el umbral
# es muy alto esas frases cortas también se tratan como conector y se
# pierden agrupadas — solo lo puramente conector (1-5 caracteres) debe
# agruparse.
UMBRAL_TEXTO_PROPIO = 6


def _segmentos_por_nombre(fragmento: str) -> list[tuple[list[str], str, bool]]:
    """Divide un fragmento del Excel en (nombres, detalle, compartido) según
    la POSICIÓN donde aparece cada nombre detectado — nunca según "buscar
    todos los nombres y copiarles el párrafo completo", que es justo el bug
    que esto reemplaza (ver el encargo del 23/09/2026: "AYLEN → todo el
    párrafo, JHON → todo el párrafo..." con 5 nombres en un mismo texto).

    El detalle de un nombre es el texto entre el FINAL de su nombre (o del
    último nombre del grupo al que quedó pegado) y el INICIO del siguiente
    nombre detectado (o el final del fragmento, para el último) — nunca el
    texto entre el INICIO del grupo y el siguiente nombre, porque eso
    arrastraría el nombre de los compañeros de grupo adentro del "detalle"
    (bug encontrado el 23/09/2026 al probar con "ANYELA..., KEVIN..., DIEGO
    CADENA": el detalle de ANYELA terminaba siendo literalmente el nombre
    de KEVIN y DIEGO). Cuando dos nombres quedan pegados sin texto real de
    por medio (ej. "Jhon y Pedro tienen dificultades..."), no se le inventa
    a cada uno su propia mitad: se agrupan y comparten el mismo detalle,
    marcados con `compartido=True` para que la aplicación lo deje claro."""
    spans = list(_RE_NOMBRE.finditer(fragmento))
    if not spans:
        return []

    resultado: list[tuple[list[str], str, bool]] = []
    grupo = [spans[0].group().strip()]
    fin_ultimo = spans[0].end()
    for i in range(1, len(spans)):
        entre = _limpiar_borde(fragmento[fin_ultimo : spans[i].start()])
        if len(entre) >= UMBRAL_TEXTO_PROPIO:
            resultado.append((grupo, entre, len(grupo) > 1))
            grupo = [spans[i].group().strip()]
        else:
            grupo.append(spans[i].group().strip())
        fin_ultimo = spans[i].end()
    detalle_final = _limpiar_borde(fragmento[fin_ultimo:]) or fragmento.strip()
    resultado.append((grupo, detalle_final, len(grupo) > 1))
    return resultado


def _dividir_nombre_ancho(nombre: str) -> list[str] | None:
    """Un nombre detectado con un salto de 2+ espacios adentro (ej. "KEVIN
    ANDREY SEVILLANO       SAMUEL LOMBANA") puede ser en realidad DOS
    nombres que quedaron pegados por cómo se alineó la celda del Excel, no
    uno solo de 5 palabras. Devuelve las partes candidatas (cada una con
    2+ palabras) o None si no aplica — quien llama solo debe usarlas si
    CADA parte por separado logra un vínculo de confianza alta; si no,
    mejor dejar el nombre pegado tal cual que inventar un corte que no
    corresponda (ver YADEILIS YALEILA  CANTICUS BISBICUS: un solo nombre
    real con doble espacio adentro por error de tipeo, no dos personas)."""
    partes = [p.strip() for p in re.split(r"\s{2,}", nombre) if p.strip()]
    if len(partes) < 2 or any(len(p.split()) < 2 for p in partes):
        return None
    return partes


def vincular_estudiante(
    db: Session, sede_id: int, grado: int, curso: int | None, nombre_crudo: str
) -> tuple[models.Estudiante | None, str, list[int]]:
    """Intenta enlazar `nombre_crudo` con un Estudiante real del mismo grado
    y devuelve (estudiante_o_None, confianza, ids_candidatos_empatados).

    Exige al menos 2 palabras (nombre+apellido) en común — en esta comunidad
    "Pai" y "Pascal" son apellidos tan comunes que una sola palabra en común
    no basta para tener confianza. Si hay cualquier duda, no enlaza: mejor
    una mención suelta pendiente de revisión que un dato sensible mal
    atribuido. `confianza`:
      alta  = un único candidato con el mejor puntaje, sin ambigüedad.
      media = 2+ candidatos empatados con el mismo puntaje (podría ser
              cualquiera de ellos — no se elige a ciegas).
      baja  = ningún estudiante del grupo llega al puntaje mínimo: puede ser
              un familiar, un docente, un lugar u otra persona mencionada,
              o un estudiante que no está en la lista."""
    tokens_mencion = {t for t in sin_tildes(nombre_crudo).split() if len(t) >= 2}
    if len(tokens_mencion) < 2:
        return None, "baja", []

    stmt = select(models.Estudiante).where(
        models.Estudiante.sede_id == sede_id, models.Estudiante.grado == grado
    )
    candidatos = list(db.scalars(stmt))
    si_curso = [e for e in candidatos if curso is not None and e.curso == curso]
    universo = si_curso or candidatos

    puntajes: list[tuple[int, models.Estudiante]] = []
    for e in universo:
        tokens_candidato = set(sin_tildes(e.nombre_completo).split())
        score = len(tokens_mencion & tokens_candidato)
        if score >= 2:
            puntajes.append((score, e))
    if not puntajes:
        return None, "baja", []
    puntajes.sort(key=lambda p: p[0], reverse=True)
    mejor = puntajes[0][0]
    empatados = [e for s, e in puntajes if s == mejor]
    if len(empatados) == 1:
        return empatados[0], "alta", []
    return None, "media", [e.id for e in empatados]


def construir_menciones(db: Session, hoja: HojaDiagnostico, sede_id: int) -> list[models.DiagnosticoMencion]:
    menciones: list[models.DiagnosticoMencion] = []
    for campo_valor, categoria_base in CAMPO_A_CATEGORIA.items():
        texto = hoja.campos.get(campo_valor)
        if not texto:
            continue
        # Dentro de "Estudiantes que no asisten" el Excel suele traer dos
        # bloques bajo el mismo campo: inasistencia y, más abajo, un rótulo
        # "Intermitencia:" seguido de otra lista de nombres — son situaciones
        # distintas aunque compartan campo, así que la categoría cambia ahí.
        categoria_actual = categoria_base
        for fragmento in texto.split(";"):
            fragmento = fragmento.strip()
            if not fragmento:
                continue
            if _RE_INTERMITENCIA.match(fragmento):
                categoria_actual = "intermitencia"
                continue
            for nombres, detalle, compartido in _segmentos_por_nombre(fragmento):
                for nombre in nombres:
                    # Un nombre pegado por doble espacio ("KEVIN ANDREY
                    # SEVILLANO       SAMUEL LOMBANA") puede ser en
                    # realidad DOS personas, no una de 5 palabras — se
                    # revisa ANTES de vincular el nombre completo, porque
                    # ese a veces sí vincula "bien" a UNA de las dos
                    # personas y esconde que falta la otra. Solo se separa
                    # si AMBAS partes, por su cuenta, vinculan con
                    # confianza alta; si no, se deja pegado tal cual (mejor
                    # eso que inventar un corte incorrecto).
                    partes_anchas = _dividir_nombre_ancho(nombre)
                    if partes_anchas:
                        vinculos_partes = [
                            vincular_estudiante(db, sede_id, hoja.grado, hoja.curso, p) for p in partes_anchas
                        ]
                        if all(c == "alta" for _, c, _ in vinculos_partes):
                            for nombre_parte, (est_parte, conf_parte, _) in zip(partes_anchas, vinculos_partes):
                                menciones.append(
                                    models.DiagnosticoMencion(
                                        categoria=categoria_actual, texto=detalle,
                                        nombre_detectado=nombre_parte,
                                        estudiante_id=est_parte.id, vinculo_automatico=True,
                                        confianza=conf_parte, texto_compartido=True,
                                    )
                                )
                            continue
                    estudiante, confianza, candidatos = vincular_estudiante(
                        db, sede_id, hoja.grado, hoja.curso, nombre
                    )
                    menciones.append(
                        models.DiagnosticoMencion(
                            categoria=categoria_actual,
                            texto=detalle,
                            nombre_detectado=nombre,
                            estudiante_id=estudiante.id if estudiante else None,
                            vinculo_automatico=estudiante is not None,
                            confianza=confianza,
                            texto_compartido=compartido,
                            candidatos_json=json.dumps(candidatos) if candidatos else None,
                        )
                    )
    return menciones


def hoja_a_diagnostico(
    db: Session, hoja: HojaDiagnostico, sede_id: int, archivo_origen: str,
    importado_por_usuario_id: int | None, fecha_respaldo: dt.date | None = None,
) -> models.DiagnosticoGrado:
    c = hoja.campos
    diagnostico = models.DiagnosticoGrado(
        sede_id=sede_id,
        grado=hoja.grado,
        curso=hoja.curso,
        hoja_excel=hoja.hoja_excel,
        contenido_hash=contenido_hash(hoja),
        archivo_origen=archivo_origen,
        importado_por_usuario_id=importado_por_usuario_id,
        # La hoja casi siempre trae su propia fecha ("MARZO 19 DE 2026"); si
        # esa hoja puntual no la tiene, se usa `fecha_respaldo` (--periodo del
        # script) en vez de dejarla en blanco — nunca se inventa un día, como
        # mucho el mes/año que la persona que importa indicó a propósito.
        fecha_diligenciado=hoja.fecha or fecha_respaldo,
        n_en_lista=_a_entero(c.get(CAMPO_EN_LISTA)),
        n_asisten=_a_entero(c.get(CAMPO_ASISTEN)),
        no_asisten_texto=c.get("no_asisten_texto"),
        desplazados_texto=c.get("desplazados_texto"),
        embarazadas_texto=c.get("embarazadas_texto"),
        victimas_conflicto_texto=c.get("victimas_conflicto_texto"),
        dificultades_academicas=c.get("dificultades_academicas"),
        dificultades_comportamiento=c.get("dificultades_comportamiento"),
        acompanamiento_padres=c.get("acompanamiento_padres"),
        problemas_salud=c.get("problemas_salud"),
        tematicas_trabajar=c.get("tematicas_trabajar"),
        estrategias_conflicto=c.get("estrategias_conflicto"),
        estrategias_aprendizaje=c.get("estrategias_aprendizaje"),
        resguardos_atendidos=c.get("resguardos_atendidos"),
        recomendaciones_docentes=c.get("recomendaciones_docentes"),
        llamados_atencion=c.get("llamados_atencion"),
        orientacion_brindada=c.get("orientacion_brindada"),
        transporte_escolar=c.get("transporte_escolar"),
        observaciones_generales=c.get("observaciones_generales"),
        director_grado_nombre=c.get("director_grado_nombre"),
        orientador_escolar_nombre=c.get("orientador_escolar_nombre"),
        seguimiento_nota=c.get("seguimiento_nota"),
        texto_crudo=hoja.texto_crudo,
    )
    diagnostico.menciones = construir_menciones(db, hoja, sede_id)
    return diagnostico


def importar(
    db: Session, ruta, sede_id: int, importado_por_usuario_id: int | None = None,
    fecha_respaldo: dt.date | None = None,
) -> dict:
    """Importa el libro completo. Cada hoja se guarda como una VERSIÓN nueva
    de DiagnosticoGrado (nunca se sobreescribe una anterior); si el
    contenido extraído es idéntico a la última versión ya guardada para ese
    grado, se omite (evita duplicar cuando el mismo archivo se reimporta sin
    cambios). `fecha_respaldo` solo se usa para las hojas que no traen su
    propia fecha adentro. Devuelve un resumen para mostrarle a quien lo corrió."""
    hojas = leer_libro(ruta)
    creados: list[models.DiagnosticoGrado] = []
    omitidos_sin_cambios: list[str] = []
    for hoja in hojas:
        h = contenido_hash(hoja)
        ultimo = db.scalar(
            select(models.DiagnosticoGrado)
            .where(
                models.DiagnosticoGrado.sede_id == sede_id,
                models.DiagnosticoGrado.grado == hoja.grado,
                models.DiagnosticoGrado.curso == hoja.curso,
            )
            .order_by(models.DiagnosticoGrado.importado_en.desc())
        )
        if ultimo is not None and ultimo.contenido_hash == h:
            omitidos_sin_cambios.append(hoja.hoja_excel)
            continue
        diagnostico = hoja_a_diagnostico(db, hoja, sede_id, str(ruta), importado_por_usuario_id, fecha_respaldo)
        db.add(diagnostico)
        creados.append(diagnostico)
    db.flush()
    return {
        "hojas_leidas": len(hojas),
        "creados": creados,
        "omitidos_sin_cambios": omitidos_sin_cambios,
    }
