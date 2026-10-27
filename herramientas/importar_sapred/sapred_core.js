// Núcleo de la automatización de SAPRED (login, navegación, generación del
// reporte y extracción de datos). Lo usan tanto la herramienta interactiva
// (importar_sapred.js, para correr a mano) como el modo sin preguntas que
// lanza el backend de la app (importar_sapred_headless.js) — la lógica de
// Playwright vive en un solo lugar.
const { chromium } = require("playwright");
const http = require("http");
const fs = require("fs");
const path = require("path");
const { extraerBloquesDeReporteSapred } = require("./extraer_bloques.js");
const { extraerBloquesDeBoletinSapred } = require("./extraer_bloques_boletin.js");

// --- Identidad de servicio (Fase 4.1) ---------------------------------------
// La usan TODOS los endpoints internos que este archivo llama (progreso,
// ensamblar-sede, unir-pdfs, separar-por-seccion, importar-*-bloques, y el
// conteo reducido de estudiantes). Un solo lugar, para no repetir esto en
// los 13 scripts que importan apiGet/apiPostJSON de aquí.
//
// Dos formas de conseguir el token, sin duplicar el secreto en ningún lado:
//   1. Grupo A (el backend los lanza: los *_headless.js): ya viene en
//      SAPRED_API_TOKEN, inyectado por sapred_auditoria.py al arrancar el
//      subproceso — igual que SAPRED_USUARIO/SAPRED_CLAVE.
//   2. Grupo B (una persona los corre a mano — Importar_SAPRED.bat,
//      capturar_boletin_manual.js, capturar_boletines_pdf_manual.js): no hay
//      backend de por medio que inyecte nada, así que se lee EL MISMO
//      archivo que ya genera/usa el backend (backend/certs/token_servicio_
//      sapred.key) — un solo secreto, nunca dos copias que sincronizar.
//
// Si no se encuentra ninguno de los dos, se sigue igual pero sin el header:
// los endpoints internos responderán 403 y el script fallará con un error
// claro al llamarlos (no falla aquí, para no romper los scripts que NO
// llaman ningún endpoint interno, como los de solo-lectura de descubrimiento).
const RUTA_TOKEN_SERVICIO = path.join(__dirname, "..", "..", "backend", "certs", "token_servicio_sapred.key");
const CABECERA_TOKEN_SERVICIO = "X-Ietaba-Sapred-Token";

function tokenServicio() {
  if (process.env.SAPRED_API_TOKEN) return process.env.SAPRED_API_TOKEN;
  try {
    return fs.readFileSync(RUTA_TOKEN_SERVICIO, "utf8").trim();
  } catch {
    return null;
  }
}

// Reporte "Boletín informativo" — confirmado con descubrir_boletin.js:
//   addTab('Boletin Informativo','reportes/boletin/sel.php','','186')
// OJO: es una página "sel.php" (un formulario de selección), NO el mismo
// index.php del Consolidado. Los ids de los combos (sede/grado/jornada/
// curso/periodo) y el botón de generar en esa página pueden diferir de los
// del Consolidado (#id_sed, #cod_gra, #id_jor, #cod_cur, #id_peri,
// #gen_reporte) — hay que verificarlos ahí y ajustar generarYExtraer si es
// necesario. La importación por PDF ya funciona sin nada de esto.
const BOLETIN_RUTA = process.env.SAPRED_BOLETIN_RUTA || "reportes/boletin/sel.php";
const BOLETIN_ID = process.env.SAPRED_BOLETIN_ID || "186";
const BOLETIN_MATCH = "reportes/boletin/";

// Boletín de CALIFICACIONES que se entrega al docente/acudiente (portada
// "INFORME ESCOLAR DE VALORACIÓN"). CONFIRMADO con descubrir_boletin_general.js
// (sep-2026): NO es un menú aparte — es el MISMO reporte
// `reportes/boletin/sel.php` (id 186) que ya usamos para los conceptos, pero
// pidiendo la salida en PDF (#des2) en vez de HTML (#des1).
const BOLETIN_GEN_RUTA = process.env.SAPRED_BOLETIN_GEN_RUTA || BOLETIN_RUTA;
const BOLETIN_GEN_ID = process.env.SAPRED_BOLETIN_GEN_ID || BOLETIN_ID;
const BOLETIN_GEN_MATCH = process.env.SAPRED_BOLETIN_GEN_MATCH || BOLETIN_MATCH;

// "Opciones de impresión" del boletín: es un botón EN el formulario del
// boletín que abre (showPopWin) un iframe con `config/index.php?tipo=b`.
// CONFIRMADO con descubrir_boletin_general.js: radios `sede_cur` (Mostrar
// Sede) e `inc_puesto` (Incluir Puesto), value "s"/"n"; guardar = id/name
// "btn". Ver configurarOpcionesImpresionBoletin().

const GRADOS = [
  { numero: 0, sapred: "TRANSICION" },
  { numero: 1, sapred: "PRIMERO" },
  { numero: 2, sapred: "SEGUNDO" },
  { numero: 3, sapred: "TERCERO" },
  { numero: 4, sapred: "CUARTO" },
  { numero: 5, sapred: "QUINTO" },
  { numero: 6, sapred: "SEXTO" },
  { numero: 7, sapred: "SEPTIMO" },
  { numero: 8, sapred: "OCTAVO" },
  { numero: 9, sapred: "NOVENO" },
  { numero: 10, sapred: "DECIMO" },
  { numero: 11, sapred: "ONCE" },
];

function apiGet(apiBase, path_) {
  return new Promise((resolve, reject) => {
    const token = tokenServicio();
    const opciones = token ? { headers: { [CABECERA_TOKEN_SERVICIO]: token } } : {};
    http
      .get(`${apiBase}${path_}`, opciones, (res) => {
        let data = "";
        res.on("data", (c) => (data += c));
        res.on("end", () => {
          if (res.statusCode >= 400) return reject(new Error(`HTTP ${res.statusCode} en ${path_}`));
          resolve(JSON.parse(data));
        });
      })
      .on("error", reject);
  });
}

function apiPostJSON(apiBase, path_, datos) {
  return new Promise((resolve, reject) => {
    const cuerpo = JSON.stringify(datos);
    const url = new URL(apiBase + path_);
    const token = tokenServicio();
    const cabeceras = { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(cuerpo) };
    if (token) cabeceras[CABECERA_TOKEN_SERVICIO] = token;
    const req = http.request(
      {
        hostname: url.hostname,
        port: url.port,
        path: url.pathname + url.search,
        method: "POST",
        headers: cabeceras,
      },
      (res) => {
        let data = "";
        res.on("data", (c) => (data += c));
        res.on("end", () => {
          if (res.statusCode >= 400) return reject(new Error(`HTTP ${res.statusCode}: ${data}`));
          resolve(data ? JSON.parse(data) : null);
        });
      }
    );
    req.on("error", reject);
    req.write(cuerpo);
    req.end();
  });
}

async function ocultarPopups(page) {
  await page
    .evaluate(() => {
      const mask = document.getElementById("popupMask");
      if (mask) { mask.style.display = "none"; mask.style.pointerEvents = "none"; }
      const cont = document.getElementById("popupContainer");
      if (cont) cont.style.display = "none";
    })
    .catch(() => {});
}

async function estaLogueado(page) {
  for (const f of page.frames()) {
    try {
      if ((await f.locator("text=Salir").count()) > 0) return true;
    } catch (e) { /* frame en transición, se ignora */ }
  }
  return false;
}

async function esperarLogin(page, maxMs, alCambiarEstado) {
  const inicio = Date.now();
  while (Date.now() - inicio < maxMs) {
    if (await estaLogueado(page)) return true;
    await page.waitForTimeout(2000);
  }
  return false;
}

const _ES_DETACH = (e) =>
  /detach|Frame was detached|Execution context was destroyed|frame got detached|Target closed|Cannot find context/i.test(
    String((e && e.message) || e)
  );

// Reintenta una acción sobre un frame que puede recargarse debajo (elegir el
// colegio en SAPRED recarga el formulario de login y "desengancha" el frame).
async function _conReintentoDetach(fn, intentos = 4, esperaMs = 900) {
  let ultimo;
  for (let i = 0; i < intentos; i++) {
    try {
      return await fn();
    } catch (e) {
      ultimo = e;
      if (!_ES_DETACH(e)) throw e;
      await new Promise((r) => setTimeout(r, esperaMs));
    }
  }
  throw ultimo;
}

// Devuelve SIEMPRE un frame vivo (no desenganchado) que contiene el formulario
// de login. Reescanea page.frames() hasta encontrarlo, porque el frame cambia
// de identidad tras cada recarga. `conClave` exige que ya esté el campo de
// contraseña (post-selección de colegio).
async function _frameLogin(page, { conClave = false, timeout = 15000 } = {}) {
  const sel = conClave
    ? 'input[type="password"], input#clave, input[name="clave"], input[name="password"]'
    : '#sistema, .ui-autocomplete-input, input[name="sistema"], input[type="password"]';
  const hasta = Date.now() + timeout;
  let candidato = page.mainFrame();
  while (Date.now() < hasta) {
    for (const f of page.frames()) {
      if (f.isDetached && f.isDetached()) continue;
      try {
        if ((await f.locator(sel).count()) > 0) return f;
        if (/cachiri|login|acceso|ingreso/i.test(f.url())) candidato = f;
      } catch (e) {
        /* frame en transición: se ignora y se reintenta en la próxima vuelta */
      }
    }
    await page.waitForTimeout(500);
  }
  return candidato && candidato.isDetached && candidato.isDetached() ? page.mainFrame() : candidato;
}

async function abrirNavegadorSapred() {
  const browser = await chromium.launch({ headless: false, args: ["--start-maximized"] });
  const page = await browser.newPage({ viewport: null });
  await page.goto("https://sapred.com/", { waitUntil: "load", timeout: 45000 });
  // SAPRED arma el formulario de login por JS/frames tras el load: se espera a
  // que exista antes de tocarlo (evita el "Frame was detached" por correr
  // demasiado pronto sobre un frame que todavía se está montando).
  await _frameLogin(page, { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(1200);
  await seleccionarColegioSapred(page); // AWA — siempre, con o sin credenciales
  await intentarLoginAutomatico(page); // solo si vienen SAPRED_USUARIO / SAPRED_CLAVE
  await page.bringToFront();
  return { browser, page };
}

// Deja el colegio (AWA) elegido en el combo de SAPRED. El combo puede ser un
// <select> normal o un autocomplete (input + menú), así que se intentan las
// dos formas. Se ejecuta siempre — también cuando el login es manual.
async function seleccionarColegioSapred(page) {
  const log = (m) => console.log(`[login-auto] ${m}`);
  const ETIQUETA = "INSTITUCION EDUCATIVA INDIGENA TECNICA AGROAMBIENTAL BILINGUE AWA";
  try {
    // 1) <select id="sistema">. En el PC, SAPRED lo esconde detrás de un
    //    combobox de jQuery UI (un <input> con el nombre visible): hay que
    //    poner el colegio en LOS DOS. Si solo se cambia el <select>, el input
    //    sigue diciendo «DEMO», el combobox lo "corrige" y deja el <select>
    //    vacío, y validar() de SAPRED rechaza el ingreso por falta de colegio.
    //    Nunca se escoge otra institución "por si acaso": si no aparece AWA
    //    se pasa al paso 2 y, si tampoco, la persona lo elige a mano.
    const puestoPorSelect = await _conReintentoDetach(async () => {
      const fr = await _frameLogin(page, { timeout: 15000 });
      if (!(await fr.locator("select#sistema").count())) return false;
      return fr.evaluate((etiqueta) => {
        const s = document.querySelector("select#sistema");
        const norm = (t) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim().toUpperCase();
        const opcion = [...s.options].find((o) => norm(o.text) === etiqueta);
        if (!opcion) return false;
        s.value = opcion.value;
        opcion.selected = true;
        const visible = s.parentElement && s.parentElement.querySelector(".ui-autocomplete-input");
        if (visible) visible.value = opcion.text;
        if (typeof s.onchange === "function") s.onchange.call(s);
        if (window.jQuery) window.jQuery(s).trigger("change");
        return s.value === opcion.value;
      }, ETIQUETA);
    }).catch(() => false);
    if (puestoPorSelect) {
      await page.waitForTimeout(2500);
      // SAPRED puede recargar el formulario al cambiar de colegio: se
      // confirma que siga elegido antes de seguir.
      const sigue = await _frameLogin(page, { timeout: 10000 })
        .then((fr) => fr.evaluate(() => (document.querySelector("select#sistema") || {}).value || ""))
        .catch(() => "");
      if (sigue) {
        log(`colegio elegido (AWA, código ${sigue})`);
        return;
      }
      log("el colegio no quedó fijado en el <select>: se intenta por el menú");
    }

    // 2) Autocomplete (input + menú). Cada paso re-resuelve el frame.
    await _conReintentoDetach(async () => {
      const fr = await _frameLogin(page, { timeout: 15000 });
      const combo = fr
        .locator('#sistema, input#sistema, input[name="sistema"], .ui-autocomplete-input, input[role="combobox"], #sistema ~ input')
        .first();
      if (!(await combo.count())) throw new Error("sin combo de colegio todavía");
      await combo.click({ timeout: 5000 }).catch(() => {});
      await combo.fill("").catch(() => {});
      await combo.type("AWA", { delay: 110 });
      await fr.waitForTimeout(1800);
      const opcion = fr
        .locator('.ui-menu-item:has-text("AWA"), li:has-text("AWA"), .ui-menu-item a:has-text("AWA"), option:has-text("AWA")')
        .first();
      if (await opcion.count()) {
        await opcion.click().catch(() => {});
        log("colegio elegido en el menú (AWA)");
      } else {
        await combo.press("ArrowDown").catch(() => {});
        await combo.press("Enter").catch(() => {});
        log("colegio: ArrowDown+Enter");
      }
    });
    // SAPRED recarga el formulario de login al fijar el colegio: hay que
    // dejarlo asentar antes de tocar los campos de usuario/clave.
    await page.waitForTimeout(2500);
  } catch (e) {
    console.log(`[login-auto] no pude fijar el colegio: ${e.message}`);
  }
}

// Login automático BEST-EFFORT: si vienen SAPRED_USUARIO / SAPRED_CLAVE por
// entorno, llena usuario/contraseña y pulsa INGRESAR. Si algo no calza (SAPRED
// cambió el formulario) NO rompe nada: se cae al login manual de siempre
// (esperarLogin sigue vigilando). Nunca imprime las credenciales; solo el
// paso alcanzado, para diagnóstico.
async function intentarLoginAutomatico(page) {
  const usuario = process.env.SAPRED_USUARIO;
  const clave = process.env.SAPRED_CLAVE;
  if (!usuario || !clave) return;
  const log = (m) => console.log(`[login-auto] ${m}`);

  try {
    const escrito = await _conReintentoDetach(async () => {
    const fr = await _frameLogin(page, { conClave: true, timeout: 20000 });
    await fr.waitForSelector('input[type="password"]', { timeout: 15000 });

    // Los campos pueden habilitarse recién cuando el colegio queda fijado.
    await fr.waitForTimeout(1200);

    // Se ubican los campos en el DOM: la contraseña es inequívoca; el usuario
    // es el input de texto que va JUSTO ANTES de la contraseña (nunca el
    // combo del colegio #sistema, que también es un input de texto).
    return await fr.evaluate(
      ({ usuario, clave }) => {
        const pass = document.querySelector(
          'input[type="password"], input#clave, input[name="clave"], input[name="contrasena"], input[name="password"]'
        );
        if (!pass) return "sin-campo-clave";

        let user =
          document.querySelector(
            'input#usuario, input[name="usuario"], input[name="nombreusuario"], input[name="user"], input[name="login"], input[name="nombre_usuario"]'
          ) || null;
        if (!user) {
          const textos = [...document.querySelectorAll('input')].filter((el) => {
            const t = (el.type || "text").toLowerCase();
            if (!["text", "", "email", "tel"].includes(t)) return false;
            if (el === pass) return false;
            if (el.id === "sistema" || el.name === "sistema") return false;
            if (el.className && /autocomplete|combobox|select2/i.test(el.className)) return false;
            return true;
          });
          // el último input de texto que aparece ANTES de la contraseña
          const before = textos.filter(
            (el) => el.compareDocumentPosition(pass) & Node.DOCUMENT_POSITION_FOLLOWING
          );
          user = before[before.length - 1] || textos[0] || null;
        }
        if (!user) return "sin-campo-usuario";

        const set = (el, val) => {
          el.focus();
          el.value = val;
          el.dispatchEvent(new Event("input", { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));
          el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true }));
        };
        set(user, usuario);
        set(pass, clave);
        return "ok";
      },
      { usuario, clave }
    );
    });
    log(`campos: ${escrito}`);
    if (escrito !== "ok") return;

    // INGRESAR (re-resolviendo el frame por si se recargó al escribir).
    await _conReintentoDetach(async () => {
      const fr = await _frameLogin(page, { conClave: true, timeout: 10000 });
      const btn = fr
        .locator(
          'input[type="submit"], button[type="submit"], input[type="button"][value*="ingres" i], ' +
            'button:has-text("INGRESAR"), a:has-text("INGRESAR"), [onclick*="ingres" i], ' +
            'button:has-text("Ingresar"), a:has-text("Ingresar"), :text-is("INGRESAR")'
        )
        .first();
      if (await btn.count()) {
        await btn.click({ timeout: 5000 }).catch(() => {});
        log("click en INGRESAR");
      } else {
        await fr.locator('input[type="password"]').first().press("Enter").catch(() => {});
        log("Enter en contraseña (no vi el botón)");
      }
    });
  } catch (e) {
    console.log(`[login-auto] no completado, sigue el login manual: ${e.message}`);
  }
}

async function abrirPestanaReporte(page) {
  await ocultarPopups(page);
  await page.evaluate(() => {
    addTab("Consolidado de Asignaturas por periodo", "reportes/notas_seccion/index.php", "", "132");
  });
  await page.waitForTimeout(2500);
  await ocultarPopups(page);
  return page.frames().find((f) => f.url().includes("reportes/notas_seccion/index.php"));
}

async function abrirPestanaReporteBoletin(page) {
  await ocultarPopups(page);
  await page.evaluate(
    ([ruta, id]) => {
      addTab("Boletín informativo", ruta, "", id);
    },
    [BOLETIN_RUTA, BOLETIN_ID]
  );
  await page.waitForTimeout(2500);
  await ocultarPopups(page);
  return page.frames().find((f) => f.url().includes(BOLETIN_MATCH));
}

// La jornada de un grupo depende del sede+grado (SAPRED repuebla #id_jor al
// elegirlos), así que hay que leer las opciones reales ahí en vez de asumir
// que la jornada correcta siempre cae en el mismo índice del combo: una sede
// con MAÑANA y TARDE puede tener, para un grado, sus estudiantes reales en
// la segunda opción y no en la primera (el caso "Octavo" que hizo evidente
// este bug: el índice fijo agarraba una jornada vacía).
async function listarJornadas(page, frame, sedeSapred, gradoSapred) {
  await ocultarPopups(page);
  await frame.selectOption("#id_sed", { label: sedeSapred });
  await page.waitForTimeout(1800);
  await frame.selectOption("#cod_gra", { label: gradoSapred });
  await page.waitForTimeout(1800);
  const opciones = await frame.$$eval("#id_jor option", (opts) =>
    opts.map((o) => ({ value: o.value, texto: (o.textContent || "").trim() }))
  );
  return opciones.filter((o) => o.value !== "");
}

// Periodos tal como los rotula SAPRED en el combo #id_peri. Un solo catálogo
// para todos los scripts: antes cada uno hacía `periodo === "1" ? "1" : "2"`,
// y el 3.er y 4.º periodo terminaban convertidos en el segundo.
const PERIODOS_TEXTO = {
  "1": "PRIMER PERIODO",
  "2": "SEGUNDO PERIODO",
  "3": "TERCER PERIODO",
  "4": "CUARTO PERIODO",
};

// "3" -> "TERCER PERIODO". null si el número no es un periodo (el script debe
// avisar y parar, nunca escoger otro periodo en silencio).
function textoPeriodo(numero) {
  return PERIODOS_TEXTO[String(numero ?? "").trim()] || null;
}

// Periodos y grados de una corrida, a partir de los argumentos del backend:
// --periodos=1,2,3 (o el viejo --periodo=N) y --grados=5,7,9 (o el viejo
// --grado=N; sin ninguno = todos los grados). Lanza un error claro si algo
// no es válido, en vez de cambiarlo por otro valor.
function leerPeriodosYGrados(args) {
  const lista = (v) => String(v || "").split(",").map((x) => x.trim()).filter(Boolean);
  const nums = lista(args.periodos).length ? lista(args.periodos) : lista(args.periodo);
  if (!nums.length) throw new Error("Falta el periodo (--periodos=1,2 o --periodo=N).");
  const periodos = [...new Set(nums)].sort().map((n) => {
    const texto = textoPeriodo(n);
    if (!texto) throw new Error(`Periodo no válido: ${n} (debe ser 1, 2, 3 o 4).`);
    return { numero: Number(n), texto };
  });
  const pedidos = lista(args.grados).length ? lista(args.grados) : lista(args.grado);
  const grados = pedidos.length ? GRADOS.filter((g) => pedidos.includes(String(g.numero))) : GRADOS;
  if (pedidos.length && grados.length !== new Set(pedidos).size) throw new Error(`Grado no válido en: ${pedidos.join(", ")}.`);
  return { periodos, grados };
}

// Elige el periodo en #id_peri y CONFIRMA que quedó. Primero por el rótulo
// exacto; si SAPRED lo escribe distinto (TERCERO, "3er periodo", "PERIODO 3"),
// por la primera palabra o el número. Si no lo encuentra, lanza un error con
// las opciones que sí hay, en vez de dejar el que SAPRED traiga por defecto.
async function elegirPeriodo(frame, periodoTexto) {
  const palabra = periodoTexto.split(" ")[0]; // PRIMER | SEGUNDO | TERCER | CUARTO
  const numero = Object.keys(PERIODOS_TEXTO).find((k) => PERIODOS_TEXTO[k] === periodoTexto);
  const r = await frame.$$eval(
    "#id_peri option",
    (opts, { periodoTexto, palabra, numero }) => {
      const norm = (t) => (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim().toUpperCase();
      const con = opts.filter((o) => o.value !== "");
      const elegida =
        con.find((o) => norm(o.textContent) === periodoTexto) ||
        con.find((o) => norm(o.textContent).startsWith(palabra)) ||
        con.find((o) => new RegExp(`(^|[^0-9])${numero}([^0-9]|$)`).test(norm(o.textContent)));
      return { valor: elegida ? elegida.value : null, opciones: con.map((o) => norm(o.textContent)) };
    },
    { periodoTexto, palabra, numero },
  );
  if (r.valor == null) {
    throw new Error(`SAPRED no tiene «${periodoTexto}» en la lista de periodos (hay: ${r.opciones.join(", ") || "ninguno"}).`);
  }
  await frame.selectOption("#id_peri", { value: r.valor });
  const quedo = await frame.$eval("#id_peri", (s) => s.value);
  if (quedo !== r.valor) throw new Error(`No se pudo dejar elegido «${periodoTexto}» en SAPRED.`);
}

async function generarYExtraer(page, frame, context, sedeSapred, gradoSapred, periodoTexto, jornadaValue, extractor) {
  extractor = extractor || extraerBloquesDeReporteSapred;
  await ocultarPopups(page);
  await frame.selectOption("#id_sed", { label: sedeSapred });
  await page.waitForTimeout(1800);
  await frame.selectOption("#cod_gra", { label: gradoSapred });
  await page.waitForTimeout(1800);
  await frame.selectOption("#id_jor", jornadaValue != null ? { value: jornadaValue } : { index: 1 });
  await page.waitForTimeout(1000);
  await frame.selectOption("#cod_cur", { label: "[TODOS LAS SECCIONES]" });
  await page.waitForTimeout(2000);
  await elegirPeriodo(frame, periodoTexto);
  await page.waitForTimeout(800);

  await ocultarPopups(page);
  const popupPromise = context.waitForEvent("page", { timeout: 15000 });
  await frame.click("#gen_reporte");
  const popup = await popupPromise;
  await popup.waitForLoadState("domcontentloaded", { timeout: 15000 });
  await popup.waitForTimeout(1000);
  const bloques = await popup.evaluate(extractor);
  await popup.close();
  return bloques;
}

// Punto de entrada que deberían usar los llamadores en vez de generarYExtraer
// directo: prueba TODAS las jornadas reales de ese sede+grado (normalmente
// una sola) y junta los bloques de todas, para no perderse estudiantes que
// están en una jornada distinta a la que un índice fijo habría adivinado.
async function generarYExtraerTodasJornadas(page, frame, context, sedeSapred, gradoSapred, periodoTexto, extractor) {
  const jornadas = await listarJornadas(page, frame, sedeSapred, gradoSapred);
  if (!jornadas.length) {
    return generarYExtraer(page, frame, context, sedeSapred, gradoSapred, periodoTexto, null, extractor);
  }
  const todosLosBloques = [];
  for (const jornada of jornadas) {
    const bloques = await generarYExtraer(page, frame, context, sedeSapred, gradoSapred, periodoTexto, jornada.value, extractor);
    todosLosBloques.push(...bloques);
  }
  return todosLosBloques;
}

// Elige, en un <select>, la primera opción (SIN CONTAR la opción [0], que
// siempre es el placeholder tipo "[ESCOJA UNA SECCIÓN]") cuyo texto haga
// match con `re`. Si no hay ninguna, deja el select como está y devuelve
// false.
//
// OJO con este bug real que hubo aquí: el placeholder de "Curso"
// ("[ESCOJA UNA SECCIÓN]") contiene la palabra "SECCIÓN", así que una regex
// como /todos|todas|secc/ lo hace matchear A ÉL MISMO (es la opción [0],
// la primera) — el resultado era que "seleccionaba" el propio placeholder
// sin darse cuenta, dejando el combo tal como estaba (sin elegir nada) y
// cortando ahí toda la cascada de campos siguientes (período, botón de
// generar). Por eso se descarta la opción [0] SIEMPRE antes de buscar.
async function _elegirOpcionQueContenga(frame, selector, re) {
  const valor = await frame
    .$$eval(
      `${selector} option`,
      (opts, reStr) => {
        const rx = new RegExp(reStr, "i");
        const o = opts.slice(1).find((op) => rx.test((op.textContent || "").trim()));
        return o ? o.value : null;
      },
      re.source,
    )
    .catch(() => null);
  if (valor == null) return false;
  await frame.selectOption(selector, { value: valor });
  return true;
}

// Genera y extrae el reporte "Boletín informativo" (página reportes/boletin/
// sel.php). Distinto al Consolidado: NO tiene jornada (#id_jor); trae radios
// para el modo de estudiante (est_alu), salida HTML/PDF (des1/des2) y dos
// checkboxes "NO incluir..." (imp_concepto, mos_faltas — hay que dejarlos
// SIN marcar). Se pide: todas las secciones, el período dado, salida HTML
// (para poder leerla) y con concepto y faltas incluidos.
//
// CONFIRMADO contra la página real (node descubrir_boletin.js, agosto 2026):
// #id_sed, #cod_gra (opciones = "PRIMERO".."ONCE"/"TRANSICION", igual que
// GRADOS), #cod_cur (trae "[TODOS LAS SECCIONES]"), #id_peri, #gen_reporte,
// est_alu (radio "h" = todo el grupo, ya viene marcado por defecto) — todos
// coinciden exactamente con lo que este código ya asumía. No hace falta
// tocar los selectores.
async function generarYExtraerBoletin(page, frame, context, sedeSapred, gradoSapred, periodoTexto) {
  await ocultarPopups(page);
  await frame.selectOption("#id_sed", { label: sedeSapred });
  await page.waitForTimeout(1800);
  await frame.selectOption("#cod_gra", { label: gradoSapred });
  await page.waitForTimeout(2000);

  // Modo de estudiante: se marca el primer radio est_alu (normalmente "todo
  // el grupo") y se deja que su onclick recargue la lista.
  await frame.locator('input[name="est_alu"]').first().check().catch(() => {});
  await page.waitForTimeout(1500);

  // Todas las secciones (si el combo trae esa opción); si no, se deja la que
  // haya (una sola sección) y el bloque saldrá igual.
  if (!(await _elegirOpcionQueContenga(frame, "#cod_cur", /todos|todas|secc/))) {
    await frame.selectOption("#cod_cur", { index: 1 }).catch(() => {});
  }
  await page.waitForTimeout(1800);

  await elegirPeriodo(frame, periodoTexto);
  await page.waitForTimeout(600);

  // Salida HTML (para leerla) + mostrar cuanti y cuali. OJO con estos dos:
  // "#imp_concepto" y "#mos_faltas" son checkboxes de "NO incluir..." (así
  // los rotula la propia página SAPRED) — hay que dejarlos SIN marcar para
  // que sí traigan conceptos y faltas, que es justo lo que este reporte
  // existe para importar. Antes se marcaban por error (parecía pedir
  // "incluir concepto" pero en realidad pedía excluirlo, así que el reporte
  // generado nunca traía el dato que se estaba buscando).
  await frame.check("#des1").catch(() => {});
  await frame.uncheck("#imp_concepto").catch(() => {});
  await frame.uncheck("#mos_faltas").catch(() => {});
  await frame.check("#nota_cuan1").catch(() => {});
  await frame.check("#nota_cual1").catch(() => {});
  await page.waitForTimeout(400);

  await ocultarPopups(page);
  const popupPromise = context.waitForEvent("page", { timeout: 8000 }).catch(() => null);
  await frame.click("#gen_reporte");

  const popup = await popupPromise;
  let destino;
  if (popup) {
    await popup.waitForLoadState("domcontentloaded", { timeout: 15000 }).catch(() => {});
    destino = popup;
  } else {
    // Se generó en el mismo frame / iframe: se espera a que aparezca el texto
    // del informe en alguno de los frames de la página.
    await page.waitForTimeout(3000);
    destino =
      page.frames().find((f) => f.url().toLowerCase().includes("html.php")) ||
      (await page.frames().reduce(async (accP, f) => {
        const acc = await accP;
        if (acc) return acc;
        const tiene = await f
          .evaluate(() => document.body && document.body.innerText.includes("INFORME ESCOLAR DE VALORAC"))
          .catch(() => false);
        return tiene ? f : null;
      }, Promise.resolve(null))) ||
      page;
  }

  await destino.waitForTimeout(1000);
  const bloques = await destino.evaluate(extraerBloquesDeBoletinSapred);
  if (popup) await popup.close().catch(() => {});
  return bloques;
}

// Nombre que ya usan importar_boletin_headless.js y descubrir: el "Boletín
// informativo" no tiene jornadas, así que es una sola generación por
// sede+grado.
async function generarYExtraerBoletinTodasJornadas(page, frame, context, sedeSapred, gradoSapred, periodoTexto) {
  return generarYExtraerBoletin(page, frame, context, sedeSapred, gradoSapred, periodoTexto);
}

// ====================================================================
//  BOLETÍN GENERAL (PDF de calificaciones que se entrega al docente)
// ====================================================================

// (fs ya se importa arriba, junto con la identidad de servicio de Fase 4.1)

// Abre la pestaña del boletín y ESPERA a que su <select> de sede exista de
// verdad en el DOM (no basta con que la url del frame calce: el sel.php tarda
// en montar sus combos). Devuelve ese frame, o null si nunca apareció.
// Idempotente: si ya hay un frame del boletín con #id_sed, NO abre otra
// pestaña (evita acumular pestañas y frames en cada llamada).
async function abrirPestanaBoletinGeneral(page) {
  await ocultarPopups(page);

  const yaAbierto = async () => {
    for (const f of page.frames()) {
      let url = "";
      try {
        url = f.url();
      } catch (e) {
        continue;
      }
      if (!url.includes(BOLETIN_GEN_MATCH)) continue;
      const tiene = await f.evaluate(() => !!document.querySelector("#id_sed")).catch(() => false);
      if (tiene) return f;
    }
    return null;
  };

  const existente = await yaAbierto();
  if (existente) return existente;

  await page.evaluate(
    ([ruta, id]) => {
      addTab("Boletín", ruta, "", id);
    },
    [BOLETIN_GEN_RUTA, BOLETIN_GEN_ID]
  );
  await page.waitForTimeout(2500);
  await ocultarPopups(page);

  for (let i = 0; i < 18; i++) {
    for (const f of page.frames()) {
      let url = "";
      try {
        url = f.url();
      } catch (e) {
        continue;
      }
      if (!url.includes(BOLETIN_GEN_MATCH)) continue;
      const tiene = await f
        .evaluate(() => !!document.querySelector("#id_sed"))
        .catch(() => false);
      if (tiene) return f;
    }
    await page.waitForTimeout(1000);
  }
  return page.frames().find((f) => f.url().includes(BOLETIN_GEN_MATCH)) || null;
}

// --- Manejo del formulario del boletín ------------------------------------
// El sel.php vive en un iframe de pestaña que Playwright puede considerar
// "no visible"; por eso los <select>/checkbox se tocan con selectOption/check
// { force:true } (ver _selFz / _chkFz arriba) y el botón Generar por DOM.

async function _clickPorSelector(frame, selector) {
  return frame
    .evaluate((selector) => {
      const el = document.querySelector(selector);
      if (!el) return "sin-elemento";
      try {
        el.click();
      } catch (e) {
        /* el onclick de SAPRED puede reventar por su cuenta; da igual */
      }
      return "ok";
    }, selector)
    .catch(() => "error");
}

// selectOption / check de Playwright con { force:true }: dispara los eventos
// nativos igual que en la auditoría de notas (que SÍ funciona), pero sin
// esperar a que el iframe de pestaña esté "visible". Devuelve true/false.
async function _selFz(frame, selector, opcion) {
  return frame
    .locator(selector)
    .selectOption(opcion, { force: true, timeout: 15000 })
    .then((v) => Array.isArray(v) && v.length > 0)
    .catch(() => false);
}
async function _chkFz(frame, selector, marcar = true) {
  const loc = frame.locator(selector).first();
  return (marcar
    ? loc.check({ force: true, timeout: 8000 })
    : loc.uncheck({ force: true, timeout: 8000 })
  )
    .then(() => true)
    .catch(() => false);
}

// "Opciones de impresión" (Mostrar Sede / Incluir Puesto): en el SAPRED de
// IETABA ya están en "Sí" (confirmado con descubrir_boletin_general.js:
// radios `sede_cur` / `inc_puesto` en `config/index.php?tipo=b`). Abrirlo
// desde la automatización escondía la pestaña del boletín, así que se dejó
// de tocar. Si algún día hay que cambiarlas, se hace a mano una vez en SAPRED.
async function configurarOpcionesImpresionBoletin() {
  /* no-op a propósito — ver comentario arriba */
}

// Descarga a `rutaDestino` los bytes de un PDF servido en `url`, reutilizando
// las cookies de la sesión de SAPRED ya abierta.
async function _descargarPdfDesdeUrl(page, url, rutaDestino) {
  const resp = await page.context().request.get(url, { timeout: 60000 });
  if (!resp.ok()) throw new Error(`HTTP ${resp.status()} al bajar el PDF`);
  const buf = await resp.body();
  const cabecera = buf.slice(0, 5).toString("latin1");
  if (!cabecera.startsWith("%PDF")) throw new Error("la respuesta no es un PDF");
  fs.writeFileSync(rutaDestino, buf);
  return rutaDestino;
}

// SAPRED entrega el boletín como PÁGINA HTML (reportes/boletin/html_ccp.php),
// no como PDF. Se convierte a PDF con un Chromium HEADLESS aparte (page.pdf()
// solo funciona headless; el navegador de SAPRED es headful). `pdfContext` es
// un BrowserContext de ese navegador headless.
async function _htmlAPdf(pdfContext, sapredPage, urlReporte, htmlReporte, rutaDestino) {
  if (!pdfContext) throw new Error("falta el navegador headless para convertir el boletín (HTML) a PDF");
  try {
    await pdfContext.addCookies(await sapredPage.context().cookies());
  } catch (e) {
    /* si falla, se intenta igual con el HTML embebido */
  }
  const conv = await pdfContext.newPage();
  try {
    // 1) Preferido: renderizar EXACTAMENTE el HTML que SAPRED mostró en
    //    pantalla (con <base> para que carguen logos/CSS relativos). Es lo
    //    mismo que haría "click derecho → Imprimir → Guardar como PDF".
    let cargo = false;
    if (htmlReporte && htmlReporte.length > 300) {
      const base = urlReporte ? `<base href="${urlReporte}">` : "";
      const doc = /<head[^>]*>/i.test(htmlReporte)
        ? htmlReporte.replace(/<head[^>]*>/i, (m) => m + base)
        : `<!doctype html><html><head><meta charset="utf-8">${base}</head><body>${htmlReporte}</body></html>`;
      await conv.setContent(doc, { waitUntil: "load", timeout: 30000 }).catch(() => {});
      await conv.waitForTimeout(1800);
      cargo = true;
    }
    // 2) Fallback: recargar la url del reporte con las cookies de sesión.
    if (!cargo && urlReporte && !/^about:/i.test(urlReporte)) {
      await conv.goto(urlReporte, { waitUntil: "networkidle", timeout: 30000 }).catch(() => {});
      await conv.waitForTimeout(1200);
    }
    await conv.emulateMedia({ media: "print" }).catch(() => {});
    await conv.pdf({
      path: rutaDestino,
      format: "Letter",
      printBackground: true,
      margin: { top: "10mm", bottom: "12mm", left: "8mm", right: "8mm" },
    });
  } finally {
    await conv.close().catch(() => {});
  }
  const buf = fs.readFileSync(rutaDestino);
  if (buf.slice(0, 5).toString("latin1") !== "%PDF-") throw new Error("el PDF convertido quedó corrupto");
  if (buf.length < 1500) throw new Error("el PDF convertido salió vacío (¿el reporte no cargó?)");
  return rutaDestino;
}

// "Opciones de impresión" (Mostrar Sede / Incluir Puesto = Sí). Se abre el
// botón del formulario del boletín, que despliega un iframe
// `config/index.php?tipo=b` (CONFIRMADO: radios `sede_cur` / `inc_puesto`
// value "s"/"n", guardar id/name "btn"). Config global: 1 vez por corrida.
async function configurarOpcionesImpresionBoletin(page, frame) {
  const log = (m) => console.log(`[opciones-impresion] ${m}`);
  try {
    const abrio = await frame
      .evaluate(() => {
        const norm = (s) => (s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
        const cand = [...document.querySelectorAll("a,input,button,img,span,div,td")].find((el) => {
          const t = norm(el.textContent) + " " + norm(el.value) + " " + norm(el.title);
          const oc = (el.getAttribute && el.getAttribute("onclick")) || "";
          return t.includes("opciones de impresi") || /tipo=b|config\/index\.php/i.test(oc);
        });
        if (!cand) return false;
        cand.click();
        return true;
      })
      .catch(() => false);
    if (!abrio) return log("no vi el botón 'Opciones de impresión' (se usa lo guardado en SAPRED)");
    await page.waitForTimeout(2800);

    let modal = null;
    for (let i = 0; i < 12 && !modal; i++) {
      modal =
        page.frames().find((f) => /config\/index\.php/i.test(f.url()) && /tipo=b/i.test(f.url())) ||
        page.frames().find((f) => /config\/index\.php/i.test(f.url())) ||
        null;
      if (!modal) await page.waitForTimeout(600);
    }
    if (!modal) return log("no apareció el modal de opciones (se usa lo guardado)");

    const res = await modal.evaluate(() => {
      const marcar = (name) => {
        const si = document.querySelector(`input[type="radio"][name="${name}"][value="s"]`);
        if (!si) return `${name}:sin-radio`;
        if (!si.checked) {
          si.checked = true;
          si.dispatchEvent(new Event("click", { bubbles: true }));
          si.dispatchEvent(new Event("change", { bubbles: true }));
          return `${name}:puesto-en-si`;
        }
        return `${name}:ya-estaba-si`;
      };
      const r = [marcar("sede_cur"), marcar("inc_puesto")].join(" · ");
      const g =
        document.querySelector('#btn, input[name="btn"], input[type="submit"]') ||
        [...document.querySelectorAll("input[type=button],button,a")].find((b) => /guardar/i.test(b.value || b.textContent || ""));
      if (g) g.click();
      return r + (g ? " · guardado" : " · SIN botón guardar");
    });
    log(res);
    await page.waitForTimeout(2000);
    // Cerrar el modal (showPopWin) para que no lo capture el generador.
    await page
      .evaluate(() => {
        try { if (typeof closePopWin === "function") closePopWin(); } catch (e) {}
        for (const id of ["popupMask", "popupContainer"]) {
          const el = document.getElementById(id);
          if (el) { el.style.display = "none"; el.innerHTML = ""; }
        }
      })
      .catch(() => {});
    await ocultarPopups(page);
  } catch (e) {
    log(`no se pudo (se sigue con lo guardado): ${e.message}`);
  }
}

// Elige "[TODOS LAS SECCIONES]" en #cod_cur (opción con valor real que casa
// /todos|todas|secc/, saltando el placeholder [0]); si no la hay, la 1ª
// sección real. Con { force:true } (el iframe puede no estar "visible").
async function _elegirTodasLasSecciones(frame) {
  const valor = await frame
    .$$eval("#cod_cur option", (opts) => {
      const conValor = opts.filter((o) => String(o.value || "").trim() !== "");
      const todas = conValor.find((o) => /todos|todas|secc/i.test((o.textContent || "").trim()) && !/escoja/i.test(o.textContent || ""));
      const el = todas || conValor.find((o) => !/escoja/i.test(o.textContent || "")) || conValor[0];
      return el ? el.value : null;
    })
    .catch(() => null);
  if (valor == null) return false;
  return _selFz(frame, "#cod_cur", { value: valor });
}

// Genera el boletín de un (sede, grado) — TODAS las secciones — y lo deja EN
// PDF en `rutaSalida`. Llenado idéntico a generarYExtraerBoletin (el de la
// auditoría de notas, que funciona), con selectOption { force:true }. SAPRED
// entrega el boletín como HTML (html_ccp.php) → se convierte a PDF con el
// Chromium headless. Devuelve { rutas: [rutaSalida] }.
async function generarBoletinPdfSede(
  page, frame, context, sedeSapred, gradoSapred, periodoTexto, rutaSalida, opts = {}
) {
  const pdfContext = opts.pdfContext;
  await ocultarPopups(page);

  if (!(await _selFz(frame, "#id_sed", { label: sedeSapred }))) {
    throw new Error(`no pude elegir la sede "${sedeSapred}" en #id_sed`);
  }
  await page.waitForTimeout(1800);
  if (!(await _selFz(frame, "#cod_gra", { label: gradoSapred }))) {
    throw new Error(`no pude elegir el grado "${gradoSapred}" en #cod_gra`);
  }
  await page.waitForTimeout(2000);

  // Modo de estudiante: primer radio est_alu (normalmente "todo el grupo").
  await _chkFz(frame, 'input[name="est_alu"]', true);
  await page.waitForTimeout(1500);

  if (!(await _elegirTodasLasSecciones(frame))) {
    await _selFz(frame, "#cod_cur", { index: 1 });
  }
  await page.waitForTimeout(1800);

  await _selFz(frame, "#id_peri", { label: periodoTexto });
  await page.waitForTimeout(600);
  await _chkFz(frame, "#des1", true);
  await _chkFz(frame, "#imp_concepto", false);
  await _chkFz(frame, "#mos_faltas", false);
  await _chkFz(frame, "#nota_cuan1", true);
  await _chkFz(frame, "#nota_cual1", true);
  await page.waitForTimeout(400);

  await ocultarPopups(page);
  const paginasAntes = new Set(context.pages());
  // Click en Generar: primero Playwright (force), y si no, DOM.
  const clickOk = await frame
    .locator("#gen_reporte")
    .first()
    .click({ force: true, timeout: 6000 })
    .then(() => true)
    .catch(() => false);
  if (!clickOk) await _clickPorSelector(frame, "#gen_reporte");

  // Buscar el reporte: SOLO frames cuya url sea reportes/boletin/*_ccp.php
  // (igual que el capturar_boletines_pdf_manual.js, que sí trae contenido).
  // OJO: NO buscar por texto "INFORME ESCOLAR DE VALORAC" — ese texto también
  // sale en el modal de Opciones de impresión y lo capturaba a él.
  let urlReporte = "";
  let htmlReporte = "";
  let popupNuevo = null;
  const inicio = Date.now();
  while (Date.now() - inicio < 40000 && !htmlReporte) {
    await page.waitForTimeout(1500);
    for (const w of context.pages()) {
      let frs = [];
      try {
        frs = w.frames();
      } catch (e) {
        continue;
      }
      for (const fr of frs) {
        let u = "";
        try {
          u = fr.url();
        } catch (e) {
          continue;
        }
        if (!/reportes\/boletin\/(html|imp|pdf|rep)_ccp\.php/i.test(u)) continue;

        await fr.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
        let listo = false;
        for (let k = 0; k < 6 && !listo; k++) {
          listo = await fr
            .evaluate(() => {
              const filas = document.querySelectorAll("table tr").length;
              const t = (document.body ? document.body.innerText : "").length;
              return filas >= 4 && t > 500;
            })
            .catch(() => false);
          if (!listo) await page.waitForTimeout(1200);
        }
        const cont = await fr.content().catch(() => "");
        if (cont && cont.length > 800) {
          urlReporte = u;
          htmlReporte = cont;
          if (!paginasAntes.has(w) && w !== page) popupNuevo = w;
          break;
        }
      }
      if (htmlReporte) break;
    }
  }

  const cerrarPopup = async () => {
    if (popupNuevo && !popupNuevo.isClosed()) await popupNuevo.close().catch(() => {});
  };

  if (!htmlReporte) {
    await cerrarPopup();
    throw new Error("al darle Generar no apareció el reporte con contenido (html_ccp.php)");
  }
  if (/error al ejecutar la consulta|syntax to use near|MySQLConex|No es un resultado/i.test(htmlReporte)) {
    await cerrarPopup();
    throw new Error("SAPRED devolvió un error de consulta (sección/período/modo estudiante)");
  }

  // Guardar el HTML capturado al lado del PDF (diagnóstico si sale raro).
  try {
    fs.writeFileSync(rutaSalida.replace(/\.pdf$/i, ".html"), htmlReporte, "utf8");
  } catch (e) {
    /* no es grave */
  }

  try {
    await _htmlAPdf(pdfContext, page, urlReporte, htmlReporte, rutaSalida);
  } finally {
    await cerrarPopup();
  }
  return { rutas: [rutaSalida] };
}

module.exports = {
  GRADOS,
  PERIODOS_TEXTO,
  textoPeriodo,
  elegirPeriodo,
  leerPeriodosYGrados,
  BOLETIN_GEN_RUTA,
  BOLETIN_GEN_ID,
  BOLETIN_GEN_MATCH,
  apiGet,
  apiPostJSON,
  ocultarPopups,
  estaLogueado,
  esperarLogin,
  abrirNavegadorSapred,
  abrirPestanaReporte,
  abrirPestanaReporteBoletin,
  abrirPestanaBoletinGeneral,
  configurarOpcionesImpresionBoletin,
  generarBoletinPdfSede,
  listarJornadas,
  generarYExtraer,
  generarYExtraerTodasJornadas,
  generarYExtraerBoletin,
  generarYExtraerBoletinTodasJornadas,
};
