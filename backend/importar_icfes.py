"""Trae los resultados Saber 11 del colegio desde PRISMA (ICFES) y los carga en la base.

Ruta en PRISMA: iniciar sesión → Publicación de Resultados → Consultas →
Consulta Plantel → SABER 11 / año / período → Buscar (tabla de 15 en 15).

Uso (desde backend/):

    python importar_icfes.py                 # extrae TODOS los años y los carga
    python importar_icfes.py 2026            # solo 2026 (o varios: 2025 2026)
    python importar_icfes.py --solo-extraer  # descarga a icfes_crudo/, no toca la base
    python importar_icfes.py --solo-cargar   # carga lo que ya está en icfes_crudo/
    python importar_icfes.py --ver           # muestra el navegador mientras trabaja

Usuario y clave de PRISMA: variables ICFES_USUARIO / ICFES_CLAVE, o se piden
al arrancar (la clave no se muestra ni se guarda en ningún archivo).

Extraer necesita internet y Playwright (`pip install playwright` y
`python -m playwright install chromium`); cargar solo necesita el venv de la
app. Se puede correr cuantas veces se quiera: cada resultado se actualiza por
su número de registro, nunca se duplica.

Lo que hay que saber del sitio del ICFES (se descubrió a golpes, oct-2026):
- El servidor a veces responde con la consulta ANTERIOR (año/período o página
  de la tabla viejos). Por eso cada búsqueda se verifica contra el formulario
  que devuelve el servidor, y cada página de la tabla por el índice de su
  primera fila (data-ri); si no coincide, se repite.
- Tras varias consultas la sesión se "traba" en una búsqueda: se abre una
  sesión limpia por año y otra si un período falla.
- Después de cada Buscar quedan copias viejas de los desplegables en la
  página: solo se hace clic en el panel visible.
"""

import argparse
import getpass
import json
import os
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

CRUDO = Path(__file__).parent / "icfes_crudo"
LOGIN = "http://prisma.icfes.edu.co/prisma-web/pages/administracion/autenticacion/autenticacionIcfes.jsf"
# La tabla de resultados cambia de nombre según el año: hasta 2020 es
# "tab_resul_nuevos"; desde 2021, "tab_resul_nuevos_modulo". Mismas columnas.
TABLAS = ("tab_resul_nuevos_modulo", "tab_resul_nuevos")


def _filas(tabla: str) -> str:
    return f"#{tabla}_data tr[data-ri]"


# --- 1. Extraer (Playwright) --------------------------------------------------


def extraer(usuario: str, clave: str, anios_pedidos: list[str], ver: bool) -> dict:
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    def esperar(page):
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except PWTimeout:
            pass
        page.wait_for_timeout(600)

    def ajax(page, accion, timeout=120000):
        """Ejecuta la acción y espera la respuesta AJAX de JSF (mirar el DOM no basta: queda texto viejo)."""
        with page.expect_response(lambda r: "resultadosPlantel.jsf" in r.url and r.request.method == "POST",
                                  timeout=timeout):
            accion()
        page.wait_for_timeout(500)

    def valor_enviado(page, combo):
        return page.evaluate("c => { const s = document.getElementById(c + '_input');"
                             " return s.options[s.selectedIndex].textContent.trim(); }", combo)

    def elegir(page, combo, etiqueta):
        """Selecciona en un selectOneMenu de PrimeFaces y verifica el <select> oculto (lo que se envía)."""
        if valor_enviado(page, combo) == etiqueta:
            return
        page.locator(f"#{combo} .ui-selectonemenu-trigger").click()
        panel = page.locator(f"div[id='{combo}_panel']").locator("visible=true").last
        item = panel.locator("li").get_by_text(etiqueta, exact=True).first
        if combo == "campoPeriodo":  # el período no dispara AJAX
            item.click()
            page.wait_for_timeout(300)
        else:
            ajax(page, item.click, timeout=90000)
        if valor_enviado(page, combo) != etiqueta:
            raise RuntimeError(f"{combo}: quedó {valor_enviado(page, combo)!r}, se pidió {etiqueta!r}")

    def opciones(page, combo):
        try:
            page.wait_for_function("c => document.querySelectorAll('#' + c + '_input option').length > 1",
                                   arg=combo, timeout=30000)
        except PWTimeout:
            return []
        textos = page.locator(f"#{combo}_input option").evaluate_all("els => els.map(e => e.textContent.trim())")
        return [t for t in textos if t and not t.startswith("Seleccione")]

    def entrar(page):
        page.goto(LOGIN, wait_until="domcontentloaded")
        page.locator("[id='usuario:cb:usuario']").fill(usuario)
        page.locator("[id='constrasena:cb:constrasena']").fill(clave)  # sic: así se llama el campo
        page.get_by_text("Entrar", exact=True).click(no_wait_after=True)
        modulo = page.locator("#linkModulo a", has_text="Publicación de Resultados").first
        try:
            modulo.wait_for(state="attached", timeout=120000)
        except PWTimeout:
            raise RuntimeError("No se pudo iniciar sesión en PRISMA (¿usuario o clave incorrectos?)")
        for _ in range(4):
            modulo.click(no_wait_after=True)
            try:
                page.get_by_text("Consulta Plantel", exact=True).first.wait_for(state="attached", timeout=90000)
            except PWTimeout:
                continue
            page.locator("[id='header_Menu:header_menu'] a", has_text="Consulta Plantel").first.evaluate("a => a.click()")
            try:
                page.locator("#campoAplicacion").wait_for(state="attached", timeout=120000)
                esperar(page)
                elegir(page, "campoAplicacion", "SABER 11")
                return
            except PWTimeout:
                continue
        raise RuntimeError("No se pudo llegar a Consulta Plantel")

    def primera_fila(page, tabla):
        filas = page.locator(_filas(tabla))
        ri = filas.first.get_attribute("data-ri") if filas.count() else None
        return int(ri) if ri is not None else None

    def ir_a_pagina(page, tabla, n, esperado):
        """Deja la tabla en la página n (su primera fila debe ser `esperado`). False si no existe."""
        pag = f"#{tabla} .ui-paginator"
        for _ in range(6):
            if primera_fila(page, tabla) == esperado:
                return True
            enlace = page.locator(f"{pag}-page").get_by_text(str(n), exact=True)
            if enlace.count() and "ui-state-active" in (enlace.first.get_attribute("class") or ""):
                # el paginador cree que ya está en n pero la tabla es vieja: clic en el enlace
                # activo no envía nada, así que primero se va a otra página
                otro = page.locator(f"{pag}-page:not(.ui-state-active)").first
                if otro.count():
                    ajax(page, otro.click, timeout=90000)
                continue
            if not enlace.count():
                if n == 1:
                    enlace = page.locator(f"{pag}-first")
                else:
                    sig = page.locator(f"{pag}-next").first
                    if not sig.count() or "ui-state-disabled" in (sig.get_attribute("class") or ""):
                        return False
                    enlace = sig
            try:
                ajax(page, enlace.first.click, timeout=30000)
            except PWTimeout:
                pass
        raise RuntimeError(f"página {n}: la tabla no llegó a la fila {esperado} (está en {primera_fila(page, tabla)})")

    def consultar(page, anio, periodo):
        elegir(page, "campoAplicacion", "SABER 11")
        elegir(page, "campoAnho", anio)
        elegir(page, "campoPeriodo", periodo)
        for _ in range(4):
            ajax(page, lambda: page.get_by_text("Buscar", exact=True).click())
            usado = page.evaluate("""() => ['campoAnho', 'campoPeriodo'].map(c => {
                const o = document.querySelector('#' + c + '_input option[selected]');
                return o ? o.textContent.trim() : null; })""")
            if usado == [anio, periodo]:
                break
        else:
            raise RuntimeError(f"el servidor respondió con {usado} en vez de {[anio, periodo]}")
        tabla = next((t for t in TABLAS if page.locator(_filas(t)).count()), None)
        if tabla is None:
            return 0
        destino = CRUDO / f"{anio}_{periodo}"
        destino.mkdir(parents=True, exist_ok=True)
        for viejo in destino.glob("pagina_*.html"):
            viejo.unlink()
        n = filas = 0
        while True:
            n += 1
            if not ir_a_pagina(page, tabla, n, filas):
                break
            (destino / f"pagina_{n:02d}.html").write_text(page.locator(f"#{tabla}").inner_html(), encoding="utf-8")
            filas += page.locator(_filas(tabla)).count()
        return filas

    CRUDO.mkdir(exist_ok=True)
    estado = {}
    with sync_playwright() as p:
        nav = p.chromium.launch(headless=not ver)
        ctx = None

        def sesion_nueva():
            nonlocal ctx
            if ctx:
                ctx.close()
            # PRISMA a veces no responde al iniciar sesión tras muchas consultas seguidas:
            # se reintenta con una pausa antes de rendirse
            for intento in (1, 2, 3):
                ctx = nav.new_context()
                page = ctx.new_page()
                page.set_default_timeout(60000)
                try:
                    entrar(page)
                    return page
                except Exception as e:
                    ctx.close()
                    ctx = None
                    if intento == 3:
                        raise
                    print(f"  no se pudo entrar a PRISMA (intento {intento}): {str(e).splitlines()[0][:80]} — reintentando...")
                    time.sleep(30 * intento)

        page = sesion_nueva()
        anios = sorted(opciones(page, "campoAnho"), reverse=True)
        if anios_pedidos:
            anios = [a for a in anios if a in anios_pedidos]
        print("Años a consultar:", ", ".join(anios))
        for anio in anios:
            page = sesion_nueva()  # sesión limpia por año: el servidor arrastra estado entre consultas
            elegir(page, "campoAnho", anio)
            for periodo in opciones(page, "campoPeriodo"):
                for intento in (1, 2, 3):
                    try:
                        n = consultar(page, anio, periodo)
                        estado[f"{anio}-{periodo}"] = n
                        if n:
                            print(f"  {anio} período {periodo}: {n} estudiantes")
                        break
                    except Exception as e:
                        estado[f"{anio}-{periodo}"] = "ERROR"
                        print(f"  {anio} período {periodo}: intento {intento} falló ({str(e).splitlines()[0][:100]})")
                        try:
                            page = sesion_nueva()
                        except Exception as e2:
                            print("  no se pudo abrir una sesión nueva:", str(e2).splitlines()[0][:100])
        nav.close()
    fallidos = [k for k, v in estado.items() if v == "ERROR"]
    if fallidos:
        print("ATENCIÓN, no se pudieron leer:", ", ".join(fallidos), "→ vuelva a correr esos años.")
    return estado


# --- 2. Leer el HTML guardado ------------------------------------------------


class _Tabla(HTMLParser):
    """Lee la tabla de PrimeFaces: 2º renglón del encabezado (pruebas) y filas con data-ri."""

    def __init__(self):
        super().__init__()
        self.encabezado2, self.filas = [], []
        self._thead = self._celda = False
        self._renglon_head = 0
        self._fila = None
        self._txt = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "thead":
            self._thead = True
        elif tag == "tr":
            if self._thead:
                self._renglon_head += 1
            elif "data-ri" in a:
                self._fila = []
        elif tag in ("th", "td"):
            self._celda, self._txt = True, ""

    def handle_endtag(self, tag):
        if tag == "thead":
            self._thead = False
        elif tag == "th" and self._thead and self._renglon_head == 2:
            self.encabezado2.append(self._txt.strip())
        elif tag == "td" and self._fila is not None:
            self._fila.append(self._txt.strip())
        elif tag == "tr" and self._fila is not None:
            self.filas.append(self._fila)
            self._fila = None
        if tag in ("th", "td"):
            self._celda = False

    def handle_data(self, d):
        if self._celda:
            self._txt += d


def _num(v):
    return int(v) if re.fullmatch(r"\d+", v or "") else None


def leer_crudo(anios_pedidos: list[str]) -> list[dict]:
    salida = []
    for carpeta in sorted(CRUDO.glob("*_*")):
        if not carpeta.is_dir():
            continue
        anio, periodo = carpeta.name.split("_")
        if anios_pedidos and anio not in anios_pedidos:
            continue
        vistos, indices = set(), []
        for pag in sorted(carpeta.glob("pagina_*.html")):
            html = pag.read_text(encoding="utf-8")
            indices += [int(x) for x in re.findall(r'data-ri="(\d+)"', html)]
            t = _Tabla()
            t.feed(html)
            # el encabezado repite las pruebas en 3 bloques: puntaje, percentil nacional, percentil especial
            nb = len(t.encabezado2) // 3
            pruebas = t.encabezado2[:nb]
            for f in t.filas:
                if f[0] in vistos:
                    continue
                vistos.add(f[0])
                fila = {"anio": int(anio), "periodo": int(periodo), "registro": f[0], "nombre": " ".join(f[1].split()),
                        "puntajes": {}, "percentil_nacional": {}, "percentil_especial": {}}
                for i, prueba in enumerate(pruebas):
                    if prueba:
                        fila["puntajes"][prueba] = _num(f[2 + i])
                        fila["percentil_nacional"][prueba] = _num(f[2 + nb + i])
                        fila["percentil_especial"][prueba] = _num(f[2 + 2 * nb + i])
                fila["percentil_global"] = _num(f[2 + 3 * nb])
                fila["puntaje_global"] = _num(f[3 + 3 * nb])
                salida.append(fila)
        if sorted(indices) != list(range(len(indices))):
            raise RuntimeError(f"{anio} período {periodo}: filas incompletas o repetidas en icfes_crudo/ — "
                               "vuelva a extraer ese año")
    return salida


# --- 3. Cargar a la base -------------------------------------------------------


def cargar(filas: list[dict]) -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    from app import icfes, migraciones
    from app.database import SessionLocal

    migraciones.ejecutar()  # crea la tabla resultados_icfes si aún no existe
    with SessionLocal() as db:
        return icfes.importar(db, filas)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("anios", nargs="*", help="años a traer (por defecto todos)")
    ap.add_argument("--solo-extraer", action="store_true")
    ap.add_argument("--solo-cargar", action="store_true")
    ap.add_argument("--ver", action="store_true", help="mostrar el navegador")
    a = ap.parse_args()

    if not a.solo_cargar:
        usuario = os.environ.get("ICFES_USUARIO") or input("Usuario PRISMA (código del colegio): ").strip()
        clave = os.environ.get("ICFES_CLAVE") or getpass.getpass("Clave PRISMA: ")
        extraer(usuario, clave, a.anios, a.ver)
    if not a.solo_extraer:
        filas = leer_crudo(a.anios)
        por_anio = {}
        for f in filas:
            por_anio[f["anio"]] = por_anio.get(f["anio"], 0) + 1
        print("Leídos:", ", ".join(f"{k}: {v}" for k, v in sorted(por_anio.items())))
        r = cargar(filas)
        print(f"Base: {r['nuevos']} nuevos, {r['actualizados']} actualizados, "
              f"{r['vinculados']} vinculados a un estudiante de la base.")


if __name__ == "__main__":
    main()
