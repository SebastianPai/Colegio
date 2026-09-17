"""Parser del reporte "Boletín informativo" de SAPRED (Reportes > Reportes y
Resultados Académicos > Boletín informativo), exportado como PDF.

A diferencia del "Consolidado de Asignaturas por periodo" (importador_sapred.py),
que solo trae la nota numérica y el Director de Grupo, el "Boletín informativo"
trae, por estudiante:
  - el PROFESOR de cada área (materia),
  - el CONCEPTO descriptivo de cada área (puede venir vacío),
  - la OBSERVACIÓN del director de grupo al pie (puede venir vacía).

Cada estudiante ocupa una página ("INFORME ESCOLAR DE VALORACIÓN"). El texto
del PDF (page.get_text("text")) sale en orden de lectura, línea por línea:

    ESTUDIANTE CODIGO CURSO PERIODO F. PERIODO
    APELLIDOS NOMBRES 1000000000      <- nombre + documento
    1-1                               <- grado-curso
    IETABA                            <- sede
    SEGUNDO                           <- palabra del período
    PERIODO
    2026-05-15
    2026-08-29
    COMUNICACIÓN ORALIDAD Y ESCRITURA (COE)   <- título de área (código al final)
    PROFESOR: EJEMPLO DOCENTE
    PER 1 ACTUAL PER 2 FNJ PRO
    3.8-W 3.9 Wari 0 3.85     <- [P1] nota_P2 nivel FNJ PRO  (P1 y nivel pueden faltar)
    CONCEPTOS:- <texto...>    <- puede ocupar varias líneas, o no aparecer
    ... (una área tras otra) ...
    CONVENCIONES: ...
    MW=Makas Wai(1.00-2.90), PW=... W=... KW=...
    OBSERVACIONES: <texto>   <- del director de grupo; puede venir vacío
    __________________________________
    EJEMPLO DOCENTE
    DIRECTOR DE GRADO        <- o "DIRECTORA DE GRADO"

Si el reporte real difiere, ajustar aquí y volver a correr
backend/probar_boletin.py contra el PDF de muestra.
"""

import re

import fitz

from .importador_sapred import normalizar

PERIODOS_TEXTO = {
    "PRIMER": 1,
    "SEGUNDO": 2,
    "TERCER": 3,
    "TERCERO": 3,
    "CUARTO": 4,
    "QUINTO": 5,
}

NIVELES_POR_DEFECTO = ["Kuisha Wari", "Pichin Wai", "Makas Wai", "Wari"]

_RE_TITULO_AREA = re.compile(r"^(.+?)\s*\(([A-ZÑ]{2,6})\)\s*$")
_RE_NOMBRE_DOC = re.compile(r"^(.+?)\s+(\d{5,})$")
_RE_GRADO_CURSO = re.compile(r"^(\d+)\s*[-.]\s*(\d+)")
_RE_P1 = re.compile(r"^\d+(?:[.,]\d+)?-(?:MW|PW|W|KW)$")  # token "3.8-W" de PER 1
_RE_FECHA = re.compile(r"\b(20\d{2})-\d{2}-\d{2}\b")
_CORTE_OBS = ("ELABORADO", "CONVENCIONES", "MW=", "PW=", "W=", "KW=", "FIRMA")


def _limpiar(texto: str | None) -> str:
    if not texto:
        return ""
    return re.sub(r"^[-–:\s]+", "", texto.strip()).strip()


def _niveles(lineas: list[str]) -> list[str]:
    for t in lineas:
        if "=" not in t or ("Wai" not in t and "Wari" not in t):
            continue
        encontrados: list[str] = []
        for m in re.finditer(r"[A-Z]{1,3}=([A-Za-zÁÉÍÓÚñ ]+?)\s*\(", t):
            nombre = m.group(1).strip()
            if nombre and nombre not in encontrados:
                encontrados.append(nombre)
        if encontrados:
            return sorted(encontrados, key=len, reverse=True)
    return NIVELES_POR_DEFECTO


def _parsear_valores(area: dict, linea: str, niveles: list[str]) -> None:
    """Fila de valores 'PER1 nota_P2 nivel FNJ PRO'. Toma la nota del período
    ACTUAL (P2), que es la que va justo antes de la palabra de nivel. Ignora
    el token de PER 1 (viene con sufijo '-W', '-PW', ...). Si no hay palabra
    de nivel, es que no hay nota del período actual (queda como faltante)."""
    tokens = [t for t in linea.split() if not _RE_P1.match(t)]
    resto = " ".join(tokens)
    for niv in niveles:
        m = re.search(rf"(\d+(?:[.,]\d+)?)\s+{re.escape(niv)}\b", resto)
        if m:
            area["nota"] = m.group(1).replace(",", ".")
            area["nivel"] = niv
            return


def _parsear_pagina(texto: str) -> dict | None:
    lineas = [l.strip() for l in texto.splitlines()]
    if not any("INFORME ESCOLAR DE VALORAC" in l.upper() for l in lineas):
        return None

    idx_lbl = next(
        (i for i, l in enumerate(lineas) if "ESTUDIANTE" in l.upper() and "CODIGO" in l.upper()),
        None,
    )
    if idx_lbl is None:
        return None

    # Cabecera: las celdas (nombre+doc, "1-1", "IETABA", "SEGUNDO"/"PERIODO",
    # fechas) pueden venir en distinto orden según cómo el PDF exponga la
    # tabla — se identifican por su forma, no por su posición.
    cab: list[str] = []
    for l in lineas[idx_lbl + 1:]:
        if not l:
            continue
        if _RE_TITULO_AREA.match(l) or l.upper().startswith(("CONVENCIONES", "OBSERVACIONES")):
            break
        cab.append(l)
        if len(cab) >= 12:
            break
    if len(cab) < 4:
        return None

    m_nd = next((_RE_NOMBRE_DOC.match(x) for x in cab if _RE_NOMBRE_DOC.match(x)), None)
    m_gc = next((_RE_GRADO_CURSO.match(x) for x in cab if _RE_GRADO_CURSO.match(x)), None)
    if not m_nd or not m_gc:
        return None
    nombre = m_nd.group(1).strip()
    documento = m_nd.group(2)
    grado = int(m_gc.group(1))
    curso = int(m_gc.group(2))
    periodo_palabra = next((x.upper() for x in cab if x.strip().upper() in PERIODOS_TEXTO), "")
    periodo = PERIODOS_TEXTO.get(periodo_palabra, 2)
    sede_corta = next(
        (
            x.strip().rstrip(",")
            for x in cab
            if not _RE_NOMBRE_DOC.match(x)
            and not _RE_GRADO_CURSO.match(x)
            and not _RE_FECHA.match(x)
            and x.strip().upper() not in PERIODOS_TEXTO
            and x.strip().upper() != "PERIODO"
        ),
        "",
    )

    m_anio = _RE_FECHA.search(texto)
    if m_anio:
        anio_lectivo = int(m_anio.group(1))
    else:
        m_ae = next((i for i, l in enumerate(lineas) if l.upper().startswith("AÑO ESCOLAR")), None)
        anio_lectivo = (
            int(lineas[m_ae + 1]) if m_ae is not None and lineas[m_ae + 1].isdigit() else None
        )

    niveles = _niveles(lineas)

    # --- Bloques de área -------------------------------------------------
    areas: list[dict] = []
    actual: dict | None = None
    capturando_concepto = False

    def cerrar() -> None:
        nonlocal actual, capturando_concepto
        if actual is not None:
            actual["concepto"] = _limpiar(actual["concepto"]) or None
            areas.append(actual)
        actual = None
        capturando_concepto = False

    # Se recorre desde después de la etiqueta de cabecera; las líneas del
    # encabezado (nombre, "1-1", "IETABA", fechas...) no matchean un título
    # de área, así que se ignoran solas mientras actual sea None.
    for l in lineas[idx_lbl + 1:]:
        if not l:
            continue
        u = l.upper()
        if u.startswith(("CONVENCIONES", "OBSERVACIONES", "MW=")):
            cerrar()
            break

        m_tit = _RE_TITULO_AREA.match(l)
        if m_tit and l == u and not u.startswith(("PROFESOR", "CONCEPTOS")):
            cerrar()
            actual = {
                "codigo": m_tit.group(2),
                "nombre": m_tit.group(1).strip(),
                "docente": None,
                "nota": None,
                "nivel": None,
                "concepto": "",
            }
            continue

        if actual is None:
            continue

        if u.startswith("PROFESOR"):
            actual["docente"] = _limpiar(l.split(":", 1)[-1]) or None
            capturando_concepto = False
        elif u.startswith("CONCEPTOS"):
            actual["concepto"] = l.split(":", 1)[-1]
            capturando_concepto = True
        elif u.startswith("PER 1") and "PRO" in u:
            capturando_concepto = False
        elif capturando_concepto:
            actual["concepto"] += " " + l
        else:
            _parsear_valores(actual, l, niveles)

    cerrar()

    # --- Observación del director + su nombre ---------------------------
    observacion = None
    for i, l in enumerate(lineas):
        # Tiene que ser el encabezado de la sección ("OBSERVACIONES:" al
        # inicio de línea) — buscar la palabra en cualquier parte de la
        # línea es demasiado suelto: el concepto de una materia puede
        # mencionar "observaciones" en medio de una frase normal (ej.
        # "...atención a las observaciones del docente...").
        if not l.upper().startswith("OBSERVACIONES"):
            continue
        partes = [l.split(":", 1)[1].strip() if ":" in l else ""]
        for cont in lineas[i + 1:]:
            cs = cont.strip()
            if not cs or cs.startswith("_"):
                break
            up = cs.upper()
            if up.startswith(_CORTE_OBS) or "DE GRADO" in up or "COORDINADOR" in up or up == "RECTOR":
                break
            if cs == up and len(cs.split()) <= 6:
                break
            partes.append(cs)
        observacion = _limpiar(" ".join(p for p in partes if p)) or None
        break

    director_grupo = None
    for i, l in enumerate(lineas):
        if "DE GRADO" not in l.upper() or not re.search(r"DIRECTORA?\s+DE\s+GRADO", l, re.I):
            continue
        cand = re.sub(r"DIRECTORA?\s+DE\s+GRADO", "", l, flags=re.I).strip()
        if not cand and i > 0:
            cand = lineas[i - 1].strip()
        cand = re.sub(r"[^A-Za-zÁÉÍÓÚÑÜ.\s]", "", cand).strip()
        if cand:
            director_grupo = re.sub(r"\s+", " ", cand)
        break

    return {
        "grado": grado,
        "curso": curso,
        "sede_corta": sede_corta,
        "periodo": periodo,
        "anio_lectivo": anio_lectivo,
        "director_grupo": director_grupo,
        "documento": documento,
        "nombre": nombre,
        "observacion": observacion,
        "areas": areas,
    }


def _agrupar_paginas(paginas: list[dict]) -> list[dict]:
    bloques: dict[tuple, dict] = {}
    for p in paginas:
        clave = (normalizar(p["sede_corta"]), p["grado"], p["curso"], p["periodo"])
        bloque = bloques.get(clave)
        if bloque is None:
            bloque = {
                "grado": p["grado"],
                "curso": p["curso"],
                "sede_corta": p["sede_corta"],
                "periodo": p["periodo"],
                "anio_lectivo": p["anio_lectivo"],
                "director_grupo": p["director_grupo"],
                "areas": [],
                "_areas_idx": {},
                "estudiantes": [],
            }
            bloques[clave] = bloque
        if not bloque["anio_lectivo"]:
            bloque["anio_lectivo"] = p["anio_lectivo"]
        if not bloque["director_grupo"]:
            bloque["director_grupo"] = p["director_grupo"]

        areas_estudiante: dict[str, dict] = {}
        for a in p["areas"]:
            codigo = a["codigo"]
            reg = bloque["_areas_idx"].get(codigo)
            if reg is None:
                reg = {"codigo": codigo, "nombre": a["nombre"], "docente": a["docente"]}
                bloque["_areas_idx"][codigo] = reg
                bloque["areas"].append(reg)
            elif not reg["docente"] and a["docente"]:
                reg["docente"] = a["docente"]
            areas_estudiante[codigo] = {
                "nota": a["nota"],
                "nivel": a["nivel"],
                "concepto": a["concepto"],
            }
        bloque["estudiantes"].append(
            {
                "documento": p["documento"],
                "nombre": p["nombre"],
                "observacion": p["observacion"],
                "areas": areas_estudiante,
            }
        )

    for bloque in bloques.values():
        bloque.pop("_areas_idx", None)
    return list(bloques.values())


def parsear_texto_boletin(texto_completo: str) -> list[dict]:
    """Igual que parsear_pdf_boletin pero desde texto ya extraído (para
    pruebas y para la ruta de automatización que ya tiene el texto). Separa
    páginas por la cabecera 'INSTITUCION EDUCATIVA ...'."""
    trozos = re.split(r"(?=INSTITUCION EDUCATIVA IND[ÍI]GENA)", texto_completo)
    paginas = [p for t in trozos if t.strip() for p in [_parsear_pagina(t)] if p]
    return _agrupar_paginas(paginas)


def parsear_pdf_boletin(datos_pdf: bytes) -> list[dict]:
    """Devuelve una lista de bloques, uno por grupo (sede+grado+curso+periodo).
    Cada bloque:

    {
      "grado": int, "curso": int, "sede_corta": str, "periodo": int,
      "anio_lectivo": int | None, "director_grupo": str | None,
      "areas": [{"codigo": str, "nombre": str, "docente": str | None}, ...],
      "estudiantes": [
        {"documento": str, "nombre": str, "observacion": str | None,
         "areas": {"COE": {"nota": "3.9", "nivel": "Wari",
                           "concepto": "texto" | None}, ...}},
        ...
      ],
    }
    """
    doc = fitz.open(stream=datos_pdf, filetype="pdf")
    paginas: list[dict] = []
    for pagina in doc:
        texto = pagina.get_text("text")
        if not texto.strip():
            continue
        parsed = _parsear_pagina(texto)
        if parsed:
            paginas.append(parsed)
    return _agrupar_paginas(paginas)
