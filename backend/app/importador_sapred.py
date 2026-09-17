"""Parser del reporte de SAPRED "Consolidado de Asignaturas por periodo"
(Reportes > Resultados Académicos), exportado como PDF.

No depende de la base de datos: solo lee el PDF y devuelve, por cada bloque
de curso (una sección/grupo), qué áreas tiene el reporte y qué estudiante
tiene o no tiene nota en cada una. La aplicación (crud.py) es la que decide
qué hacer con eso (crear pendientes, cruzar con la matrícula, etc.).

El formato se dedujo de un reporte real. Cada curso trae, en este orden:
  "Curso  {grado}-{curso} {SEDE_CORTA}, ..."
  "Fecha Impresion: ... {año}"
  "Periodo: N"
  una fila con los CÓDIGOS de área (ej. COE DESM JTD LM MATE NAP TPEC TAL)
  una fila "No. Código Estudiante P{N} P{N} ... " (tantos "P{N}" como áreas)
  una fila "Cn Cn Cn ..."
  una fila por estudiante: No., documento, nombre y, en cada columna de
  área, la nota si existe (nada si no)
  "CONVENCIONES:" con el nombre completo de cada código.
"""

import re
import unicodedata

import fitz


def normalizar(texto: str) -> str:
    """Sin acentos, sin nada que no sea letra/número, en mayúsculas — para
    comparar nombres de sede que pueden venir con problemas de codificación
    del PDF (ej. "Biling�e" en vez de "Bilingüe")."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]", "", texto).upper()


def _agrupar_por_fila(palabras: list, tolerancia: float = 3.0) -> list:
    """Agrupa palabras (x0,y0,x1,y1,texto,...) en filas según su y0, cada
    fila ordenada de izquierda a derecha y las filas ordenadas de arriba
    a abajo."""
    filas: list[list] = []
    for palabra in sorted(palabras, key=lambda w: (w[1], w[0])):
        y = palabra[1]
        fila = next((f for f in filas if abs(f[0][1] - y) <= tolerancia), None)
        if fila is None:
            filas.append([palabra])
        else:
            fila.append(palabra)
    for fila in filas:
        fila.sort(key=lambda w: w[0])
    filas.sort(key=lambda f: f[0][1])
    return filas


def _nombres_completos_desde_convenciones(filas: list, idx_conv: int) -> dict[str, str]:
    """CONVENCIONES: "COE: Comunicación... DESM: Desempeño..." — da el
    nombre completo de cada código. Es solo un complemento (para dar de
    alta un área nueva en el catálogo); si viene con acentos rotos no es
    grave, el código es el dato confiable."""
    palabras: list = []
    for fila in filas[idx_conv:]:
        texto_fila = fila[0][4]
        if texto_fila.startswith("Cn:") or texto_fila.startswith("Elaborado"):
            break
        palabras.extend(fila)

    nombres: dict[str, str] = {}
    codigo_actual = None
    nombre_actual: list[str] = []
    for p in palabras[1:]:  # se salta "CONVENCIONES:"
        texto = p[4]
        if re.match(r"^[A-Za-z]{2,6}:$", texto) and texto.isupper():
            if codigo_actual:
                nombres[codigo_actual] = " ".join(nombre_actual).strip()
            codigo_actual = texto.rstrip(":")
            nombre_actual = []
        else:
            nombre_actual.append(texto)
    if codigo_actual:
        nombres[codigo_actual] = " ".join(nombre_actual).strip()
    return nombres


def parsear_pdf_notas(datos_pdf: bytes) -> list[dict]:
    """Devuelve una lista de bloques, uno por cada curso encontrado en el
    PDF (puede haber varias páginas / varios cursos). Cada bloque:

    {
      "grado": int, "curso": int, "sede_corta": str, "periodo": int,
      "anio_lectivo": int | None, "director_grupo": str | None,
      "areas": [{"codigo": str, "nombre": str}, ...],   # en orden de columna
      "estudiantes": [
        {"documento": str, "nombre": str,
         "notas": {"COE": "3.1", "LM": None, ...}},
        ...
      ],
    }
    """
    doc = fitz.open(stream=datos_pdf, filetype="pdf")
    bloques = []

    for pagina in doc:
        palabras = pagina.get_text("words")
        if not palabras:
            continue
        filas = _agrupar_por_fila(palabras)

        idx_curso = next((i for i, f in enumerate(filas) if f[0][4] == "Curso"), None)
        idx_periodo = next((i for i, f in enumerate(filas) if f[0][4] == "Periodo:"), None)
        idx_conv = next((i for i, f in enumerate(filas) if f[0][4].startswith("CONVENCIONES")), None)
        if idx_curso is None or idx_periodo is None:
            continue

        # Normalmente el token es solo "{grado}-{curso}" y la sede viene en
        # la palabra siguiente (ej. "6-1" "IETABA,"). Pero algunos cursos
        # (visto en 8° y 11°) traen la sede pegada al mismo token, sin
        # espacio (ej. "8-1-IETABA,") — se admite también ese formato.
        fila_curso = filas[idx_curso]
        m = re.match(r"^(\d+)-(\d+)(?:-(.+))?$", fila_curso[1][4]) if len(fila_curso) > 1 else None
        if not m or len(fila_curso) < 3:
            continue
        grado, curso = int(m.group(1)), int(m.group(2))
        sede_corta = m.group(3).rstrip(",") if m.group(3) else fila_curso[2][4].rstrip(",")

        fila_periodo = filas[idx_periodo]
        periodo = int(fila_periodo[1][4]) if len(fila_periodo) > 1 else 1

        fila_fecha = next((f for f in filas if f[0][4] == "Fecha"), None)
        anio_lectivo = None
        if fila_fecha:
            m_anio = re.search(r"(20\d{2})", " ".join(p[4] for p in fila_fecha))
            if m_anio:
                anio_lectivo = int(m_anio.group(1))

        # Fila justo después de "Periodo: N" = códigos de área, en orden.
        if idx_periodo + 2 >= len(filas):
            continue
        fila_codigos_area = filas[idx_periodo + 1]
        fila_pn = filas[idx_periodo + 2]
        columnas_x = [p[0] for p in fila_pn if p[4] == f"P{periodo}"]
        codigos = [p[4] for p in fila_codigos_area]
        if len(columnas_x) != len(codigos) or not columnas_x:
            continue  # no se pudo alinear columnas con áreas — se descarta esta página

        nombres_completos = (
            _nombres_completos_desde_convenciones(filas, idx_conv) if idx_conv is not None else {}
        )
        columnas = list(zip(columnas_x, codigos))  # [(x, codigo), ...] izquierda a derecha

        # Filas de estudiantes: entre el encabezado "Cn" y "CONVENCIONES".
        idx_cn = next((i for i, f in enumerate(filas) if f[0][4] == "Cn"), idx_periodo + 3)
        y_inicio = filas[idx_cn][0][1]
        y_fin = filas[idx_conv][0][1] if idx_conv is not None else 10_000

        estudiantes = []
        for fila in filas:
            y = fila[0][1]
            if y <= y_inicio or y >= y_fin:
                continue
            if len(fila) < 2 or not re.match(r"^\d+$", fila[0][4]) or not re.match(r"^\d+$", fila[1][4]):
                continue  # no es una fila "No. documento nombre..."
            documento = fila[1][4]
            nombre_partes = []
            notas: dict[str, str | None] = {codigo: None for _, codigo in columnas}
            for palabra in fila[2:]:
                x = palabra[0]
                col_x, col_codigo = min(columnas, key=lambda c: abs(c[0] - x))
                if abs(col_x - x) <= 25:
                    notas[col_codigo] = palabra[4]
                else:
                    nombre_partes.append(palabra[4])
            estudiantes.append(
                {"documento": documento, "nombre": " ".join(nombre_partes).strip(), "notas": notas}
            )

        director_grupo = None
        for i, fila in enumerate(filas):
            if fila[0][4] == "Director" and len(fila) > 1 and fila[1][4] == "de" and i > 0:
                director_grupo = " ".join(p[4] for p in filas[i - 1])
                break

        bloques.append(
            {
                "grado": grado,
                "curso": curso,
                "sede_corta": sede_corta,
                "periodo": periodo,
                "anio_lectivo": anio_lectivo,
                "director_grupo": director_grupo,
                "areas": [{"codigo": c, "nombre": nombres_completos.get(c, c)} for c in codigos],
                "estudiantes": estudiantes,
            }
        )

    return bloques
