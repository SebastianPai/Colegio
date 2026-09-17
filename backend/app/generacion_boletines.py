"""Generación del *boletín general* (el PDF de calificaciones que se entrega
al docente / acudiente), sede por sede.

A diferencia de `sapred_auditoria` —que LEE reportes de SAPRED para importar
notas/conceptos— esto solo PRODUCE archivos: por cada sede rural genera en
SAPRED el boletín de todos sus grados, y los une en un único PDF ordenado por
grado ('SEDE ## NOMBRE.pdf') listo para imprimir o enviar.

La navegación/generación en SAPRED vive en el script Node
`herramientas/importar_sapred/generar_boletines_headless.js` (igual que la
auditoría). Este módulo solo:
  - decide la carpeta de salida de la corrida,
  - une los PDF por grado de cada sede (con PyMuPDF), y
  - sirve/lista los archivos ya generados.

Reutiliza la tabla `AuditoriaSapred` (con `tipo='boletin_pdf'`) para el
progreso en vivo, el historial y el botón "reintentar solo lo que falló" —
son idénticos a los de la auditoría, no hay por qué duplicarlos.
"""

import re
import time
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF

from . import models, schemas

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent.parent
CARPETA_BOLETINES = RAIZ_PROYECTO / "backend" / "boletines_sedes"
# `carpeta_salida` se guarda relativa a RAIZ_PROYECTO para que Node y el
# backend (mismo equipo, mismo disco) resuelvan la misma ruta sin ambigüedad.
BASE_RELATIVA = "backend/boletines_sedes"


def carpeta_relativa_para(anio: int, periodo: int) -> str:
    return f"{BASE_RELATIVA}/{anio}-P{periodo}"


def carpeta_abs(carpeta_relativa: str) -> Path:
    """Resuelve la ruta guardada en AuditoriaSapred.carpeta_salida, con reja
    anti path-traversal (nunca puede salir de CARPETA_BOLETINES)."""
    p = (RAIZ_PROYECTO / carpeta_relativa).resolve()
    if not str(p).startswith(str(CARPETA_BOLETINES.resolve())):
        raise ValueError(f"Ruta de salida fuera de lo permitido: {carpeta_relativa}")
    return p


def _slug_archivo(nombre: str) -> str:
    """Nombre de archivo seguro en Windows a partir del nombre de la sede.
    Mantiene el '#' y los números ('SEDE # 01  I.E.T.A.B.A.' -> 'SEDE # 01
    I.E.T.A.B.A.pdf'); solo quita lo ilegal y colapsa espacios."""
    limpio = unicodedata.normalize("NFKC", nombre or "").strip()
    limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", limpio)
    limpio = re.sub(r"\s+", " ", limpio).strip(" .")
    return (limpio or "sede")[:120]


def nombre_pdf_sede(sede_nombre: str) -> str:
    return f"{_slug_archivo(sede_nombre)}.pdf"


def ruta_pdf_sede(carpeta_relativa: str, nombre_archivo: str) -> Path:
    """Resuelve un PDF concreto dentro de la carpeta de la corrida, validando
    que `nombre_archivo` sea un nombre plano (sin separadores ni '..')."""
    if not nombre_archivo or "/" in nombre_archivo or "\\" in nombre_archivo or ".." in nombre_archivo:
        raise ValueError("Nombre de archivo inválido")
    ruta = (carpeta_abs(carpeta_relativa) / nombre_archivo).resolve()
    if ruta.parent != carpeta_abs(carpeta_relativa):
        raise ValueError("Nombre de archivo inválido")
    return ruta


def unir_pdfs(archivos: list[str], ruta_salida: str) -> int:
    """Une los PDF de `archivos` (en ese orden) en `ruta_salida`. Devuelve el
    nº de páginas. Todo tiene que quedar dentro de backend/boletines_sedes/."""
    dst = Path(ruta_salida).resolve()
    if not str(dst).startswith(str(CARPETA_BOLETINES.resolve())):
        raise ValueError(f"Ruta de salida fuera de lo permitido: {ruta_salida}")
    salida = fitz.open()
    try:
        usados = 0
        for a in archivos:
            p = Path(a)
            if not p.exists() or p.suffix.lower() != ".pdf":
                continue
            with fitz.open(p) as src:
                salida.insert_pdf(src)
            usados += 1
        if not usados:
            raise ValueError("Ninguno de los PDF a unir existe en el disco.")
        dst.parent.mkdir(parents=True, exist_ok=True)
        salida.save(dst, deflate=True)
        return salida.page_count
    finally:
        salida.close()


def _existe_con_reintento(ruta: Path, intentos: int = 4, espera_seg: float = 1.5) -> bool:
    """El PDF de cada grado lo escribe un proceso Node aparte (Playwright);
    alguna vez se vio un caso en producción donde, ya escrito y verificado
    del lado de Node, este proceso todavía no lo veía en el disco (sospecha:
    algo del sistema operativo -antivirus/indexador- reteniéndolo un
    momento). Un archivo que de verdad nunca se generó sigue fallando igual
    — solo tarda unos segundos más en reportarse en vez de fallar al toque."""
    for intento in range(intentos):
        if ruta.exists():
            return True
        if intento < intentos - 1:
            time.sleep(espera_seg)
    return False


def ensamblar_sede(
    auditoria: models.AuditoriaSapred, datos: schemas.EnsamblarBoletinSede
) -> schemas.EnsamblarBoletinSedeResultado:
    """Une los PDF por grado de una sede en un solo archivo ordenado por grado
    y borra las partes. Devuelve el nombre del archivo final y sus totales."""
    if not auditoria.carpeta_salida:
        raise ValueError("Esta corrida no tiene carpeta de salida.")
    destino_dir = carpeta_abs(auditoria.carpeta_salida)
    destino_dir.mkdir(parents=True, exist_ok=True)

    partes = sorted(datos.partes, key=lambda p: p.grado)
    if not partes:
        raise ValueError("No llegó ninguna parte que unir.")

    salida = fitz.open()
    n_estudiantes = 0
    try:
        for parte in partes:
            ruta = Path(parte.ruta)
            if not _existe_con_reintento(ruta):
                raise ValueError(f"No está el PDF del grado {parte.grado}: {ruta}")
            with fitz.open(ruta) as src:
                salida.insert_pdf(src)
            n_estudiantes += parte.n_estudiantes or 0

        nombre = nombre_pdf_sede(datos.sede_nombre)
        ruta_final = destino_dir / nombre
        salida.save(ruta_final, deflate=True)
        n_paginas = salida.page_count
    finally:
        salida.close()

    # Los PDF por grado NO se borran: el proceso los deja en una subcarpeta con
    # nombre (<carpeta>/<SEDE ...>/) para que se puedan revisar sueltos.

    return schemas.EnsamblarBoletinSedeResultado(
        archivo=nombre, n_paginas=n_paginas, n_estudiantes=n_estudiantes
    )


# El boletín de un grado se genera en SAPRED con "[TODOS LAS SECCIONES]" (es
# lo único que funciona ahí — ver sapred_core.js), así que sale un PDF con
# TODOS los estudiantes del grado mezclados. Para poder entregarlo separado
# por sección (carpeta "4" -> "4-1.pdf", "4-2.pdf"...) se parte ese PDF
# usando el .html capturado al lado (mismo orden de páginas: un estudiante =
# una página = un bloque separado por <div class="SaltoDePagina">), donde
# cada bloque trae su celda CURSO ("5-1 NOMBRE SEDE", nunca las fechas del
# período que también son "NNNN-NN-NN NNNN-NN-NN"). Es puramente dinámico:
# no importa la sede ni cuántas secciones tenga el grado.
_PATRON_CURSO_HTML = re.compile(r"<strong>\s*(\d{1,2}-\d{1,2})\s+[A-ZÁÉÍÓÚÑ]", re.IGNORECASE)


def separar_por_seccion(datos: schemas.SepararPorSeccion) -> schemas.SepararPorSeccionResultado:
    ruta_html = Path(datos.html)
    ruta_pdf = Path(datos.pdf)
    if not ruta_html.exists() or not ruta_pdf.exists():
        return schemas.SepararPorSeccionResultado(separado=False)

    html = ruta_html.read_text(encoding="utf-8", errors="ignore")
    bloques = re.split(r'<div class="SaltoDePagina">.*?</div>', html, flags=re.S)
    secciones_por_pagina: list[str | None] = []
    for bloque in bloques:
        m = _PATRON_CURSO_HTML.search(bloque)
        if m:
            secciones_por_pagina.append(m.group(1))
    # Si algún bloque no trajo CURSO reconocible, o el total no calza con las
    # páginas reales del PDF, NO se arriesga a partir mal: se deja el PDF
    # combinado tal cual (el usuario igual lo tiene completo).
    doc = fitz.open(ruta_pdf)
    try:
        if len(secciones_por_pagina) != doc.page_count or not secciones_por_pagina:
            return schemas.SepararPorSeccionResultado(separado=False)

        carpeta = Path(datos.carpeta_salida).resolve()
        if not str(carpeta).startswith(str(CARPETA_BOLETINES.resolve())):
            raise ValueError(f"Ruta de salida fuera de lo permitido: {datos.carpeta_salida}")
        carpeta.mkdir(parents=True, exist_ok=True)

        paginas_por_seccion: dict[str, list[int]] = {}
        orden: list[str] = []
        for i, sec in enumerate(secciones_por_pagina):
            if sec not in paginas_por_seccion:
                paginas_por_seccion[sec] = []
                orden.append(sec)
            paginas_por_seccion[sec].append(i)

        resultado: dict[str, int] = {}
        for sec in orden:
            idxs = paginas_por_seccion[sec]
            sub = fitz.open()
            try:
                for i in idxs:
                    sub.insert_pdf(doc, from_page=i, to_page=i)
                nombre = _slug_archivo(sec) + ".pdf"
                sub.save(carpeta / nombre, deflate=True)
            finally:
                sub.close()
            resultado[sec] = len(idxs)
        return schemas.SepararPorSeccionResultado(separado=True, secciones=resultado)
    finally:
        doc.close()
