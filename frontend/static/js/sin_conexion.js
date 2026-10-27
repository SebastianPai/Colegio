// --- Uso sin conexión (celular o PC sin red con el servidor del colegio) ------
// Tres piezas, todas en este archivo:
//
// 1. Colas: lo que se guarda sin conexión queda en el dispositivo
//    (IndexedDB) y se envía solo cuando vuelve la red y la app está abierta
//    (iOS no deja enviar con la app cerrada):
//    · subidas: documentos/fotos. Cada una lleva un uuid_cliente: si se
//      reintenta una que sí había llegado, el servidor no la duplica
//      (routers/fotos.py: guardar_documento).
//    · operaciones: cualquier otra escritura hecha con api() (asistencia,
//      observaciones, cambios en la ficha, notas...). Llevan X-Id-Operacion
//      y el servidor tampoco las ejecuta dos veces (operaciones_cliente.py).
//      Se envían en el mismo orden en que se hicieron.
// 2. «Descargar todo para usar sin wifi»: deja en la caché del service worker
//    (/sw.js) todo lo que el rol de la persona puede ver, en cuatro pasos:
//    · pantallas: abre sola cada módulo del menú y cada sección/pestaña de
//      adentro, así queda guardado exactamente lo que esa pantalla pide;
//    · datos: lo que depende de qué se escoja (horario de cada docente y de
//      cada grupo, diagnósticos de cada grupo, grupos del docente, usuarios…);
//    · fichas y documentos de los estudiantes (todos, una sede, o los grupos
//      del director de grupo).
//    El listado de estudiantes (buscar, filtrar, paginar) lo arma sw.js sin
//    red a partir de la lista completa.
// 3. Aviso en pantalla: sin conexión / documentos esperando para subir.
//
// Requiere HTTPS (iniciar_https.ps1) para el service worker; la cola de
// subidas funciona igual sin él.

const SC_BD = "ietaba-sin-conexion";
const SC_TIENDA = "subidas";
const SC_OPERACIONES = "operaciones";
const SC_CLAVE_USUARIO = "ietaba_ultimo_usuario";
const SC_CLAVE_GUARDADOS = "ietaba_guardados_sin_wifi";
const SC_INTERVALO_MS = 30 * 1000;
// Para calcular el peso ANTES de descargar (medido: ficha + datos de la
// ficha + rendimiento ≈ 2,5 KB por estudiante).
const KB_FICHA = 2.5;
const KB_MINIATURA_PDF = 60;

let scSinConexion = false;
let scSincronizando = false;
let scPendientes = 0;
let scDescarga = null; // { fases, fase, hechos, total, ... } mientras se descarga

// Peticiones en curso (todas las de la app pasan por fetch): el recorrido de
// pantallas espera a que una pantalla termine de cargar antes de seguir.
let scEnVuelo = 0;
let scUltimoMovimiento = 0;
const scFetchOriginal = window.fetch.bind(window);
window.fetch = (...args) => {
  scEnVuelo++;
  scUltimoMovimiento = Date.now();
  return scFetchOriginal(...args).finally(() => {
    scEnVuelo--;
    scUltimoMovimiento = Date.now();
  });
};

// --- IndexedDB (cola de subidas) ---------------------------------------------

function scAbrirBd() {
  return new Promise((resolver, rechazar) => {
    const req = indexedDB.open(SC_BD, 2);
    req.onupgradeneeded = (ev) => {
      if (ev.oldVersion < 1) {
        const tienda = req.result.createObjectStore(SC_TIENDA, { keyPath: "uuid" });
        tienda.createIndex("estudiante", "estudianteId");
      }
      if (ev.oldVersion < 2) req.result.createObjectStore(SC_OPERACIONES, { keyPath: "uuid" });
    };
    req.onsuccess = () => resolver(req.result);
    req.onerror = () => rechazar(req.error);
  });
}

async function scTx(modo, fn, nombreTienda = SC_TIENDA) {
  const bd = await scAbrirBd();
  return new Promise((resolver, rechazar) => {
    const tx = bd.transaction(nombreTienda, modo);
    const resultado = fn(tx.objectStore(nombreTienda));
    tx.oncomplete = () => { bd.close(); resolver(resultado?.result ?? resultado); };
    tx.onerror = () => { bd.close(); rechazar(tx.error); };
  });
}

function scUsuarioId() {
  return typeof sesionActual !== "undefined" && sesionActual?.usuario ? sesionActual.usuario.id : null;
}

async function subidasPendientes(estudianteId) {
  try {
    const todas = await scTx("readonly", (t) => t.getAll());
    const uid = scUsuarioId();
    return todas
      .filter((s) => s.usuarioId === uid && (estudianteId == null || s.estudianteId === estudianteId))
      .sort((a, b) => a.creado - b.creado);
  } catch {
    return []; // IndexedDB no disponible (modo privado, etc.): no hay cola
  }
}

async function encolarSubida(item) {
  await scTx("readwrite", (t) => t.put({ ...item, usuarioId: scUsuarioId(), creado: Date.now(), error: null }));
  await scActualizarConteo();
}

async function quitarSubidaPendiente(uuid) {
  await scTx("readwrite", (t) => t.delete(uuid));
  await scActualizarConteo();
}

async function scMarcarError(uuid, error) {
  const item = await scTx("readonly", (t) => t.get(uuid));
  if (item) await scTx("readwrite", (t) => t.put({ ...item, error }));
}

// --- Cola de operaciones (escrituras de api()) ---------------------------------

// Nombre corto para la lista de pendientes cuando quien llama no dio uno.
const SC_NOMBRES_RUTA = [
  [/^\/api\/docente\/asistencia/, "Asistencia"],
  [/^\/api\/asistencia/, "Asistencia"],
  [/observaciones/, "Observación"],
  [/^\/api\/diagnosticos/, "Diagnóstico"],
  [/^\/api\/orientacion/, "Orientación"],
  [/^\/api\/promocion/, "Promoción"],
  [/^\/api\/fotos/, "Documento"],
  [/^\/api\/estudiantes/, "Datos del estudiante"],
  [/^\/api\/horario/, "Horario"],
  [/^\/api\/(boletines|academico|notas)/, "Notas / boletines"],
  [/^\/api\/sedes/, "Sedes"],
  [/^\/api\/admin/, "Administración"],
];

function scDescribirRuta(path, metodo) {
  const nombre = SC_NOMBRES_RUTA.find(([re]) => re.test(path))?.[1] || "Cambio";
  return metodo === "DELETE" ? `${nombre} (borrar)` : nombre;
}

async function operacionesPendientes() {
  try {
    const todas = await scTx("readonly", (t) => t.getAll(), SC_OPERACIONES);
    const uid = scUsuarioId();
    return todas.filter((o) => o.usuarioId === uid).sort((a, b) => a.creado - b.creado);
  } catch {
    return [];
  }
}

// La llama api() (comun.js) cuando una escritura no pudo salir por falta de red.
async function encolarOperacion({ uuid, path, metodo, body, descripcion }) {
  await scTx(
    "readwrite",
    (t) => t.put({
      uuid, path, metodo, body,
      descripcion: descripcion || scDescribirRuta(path, metodo),
      usuarioId: scUsuarioId(), creado: Date.now(), error: null,
    }),
    SC_OPERACIONES
  );
  scMarcarConexion(false);
  await scActualizarConteo();
}

async function quitarOperacionPendiente(uuid) {
  await scTx("readwrite", (t) => t.delete(uuid), SC_OPERACIONES);
  await scActualizarConteo();
}

async function scMarcarErrorOperacion(uuid, error) {
  const item = await scTx("readonly", (t) => t.get(uuid), SC_OPERACIONES);
  if (item) await scTx("readwrite", (t) => t.put({ ...item, error }), SC_OPERACIONES);
}

// Reenvía UNA operación con su mismo X-Id-Operacion. Devuelve "ok", "sin-red",
// "sesion" (hay que volver a entrar), "despues" (servidor ocupado: reintentar
// más tarde) o el texto del error que dio el servidor.
async function scEnviarOperacion(op) {
  let res;
  try {
    await asegurarSesionFresca();
    res = await fetch(op.path, {
      method: op.metodo,
      headers: { "Content-Type": "application/json", "X-Id-Operacion": op.uuid },
      body: op.body ?? undefined,
    });
  } catch {
    return "sin-red";
  }
  if (res.ok) return "ok";
  if (res.status === 401) return "sesion";
  if (res.status === 409 && res.headers.get("X-Operacion-En-Curso")) return "despues";
  if (res.status >= 500 || res.status === 408 || res.status === 429) return "despues";
  const cuerpo = await res.json().catch(() => ({}));
  const detalle = Array.isArray(cuerpo.detail) ? cuerpo.detail.map((d) => d.msg).join("; ") : cuerpo.detail;
  return detalle || `Error ${res.status}`;
}

function scNuevoUuid() {
  if (window.crypto?.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

// --- Enviar (o dejar en cola) --------------------------------------------------

function scFormulario(item) {
  const form = new FormData();
  form.set("etiqueta", item.etiqueta);
  form.set("anio_lectivo", String(item.anioLectivo));
  form.set("permanente", item.permanente ? "true" : "false");
  form.set("uuid_cliente", item.uuid);
  if (item.reemplazaId) form.set("reemplaza_id", String(item.reemplazaId));
  form.set("archivo", item.archivo, item.nombre);
  return form;
}

// Error que significa "no hay red" (no "el servidor dijo que no").
class SinConexionError extends Error {}

async function scEnviar(item) {
  let res;
  try {
    await asegurarSesionFresca();
    res = await fetch(item.url, { method: "POST", body: scFormulario(item) });
  } catch {
    throw new SinConexionError("Sin conexión");
  }
  if (!res.ok) {
    if (res.status === 401) throw Object.assign(new Error("Su sesión se cerró. Vuelva a entrar con su usuario."), { status: 401 });
    if (res.status === 403) throw Object.assign(new Error("Su usuario no tiene permiso para subir documentos. Pida ayuda en secretaría."), { status: 403 });
    const cuerpo = await res.json().catch(() => ({}));
    throw Object.assign(new Error(cuerpo.detail || "No se pudo guardar el documento."), { status: res.status });
  }
  return res.json().catch(() => null);
}

// Punto único que usa ficha.js: intenta subir ya; si no hay red, queda en
// la cola del celular. Devuelve { enCola: bool, respuesta }.
async function subirOEncolar(item) {
  const completo = { uuid: scNuevoUuid(), ...item };
  try {
    const respuesta = await scEnviar(completo);
    scMarcarConexion(true);
    return { enCola: false, respuesta };
  } catch (err) {
    if (!(err instanceof SinConexionError)) throw err;
    await encolarSubida(completo);
    scMarcarConexion(false);
    return { enCola: true, respuesta: null };
  }
}

// --- Sincronizar la cola -----------------------------------------------------

// Envía las operaciones en el orden en que se hicieron. Devuelve cuántas
// llegaron y si hay que parar (sin red / sesión cerrada).
// Las que el servidor ya rechazó no se reintentan solas (darían el mismo
// error cada 30 s): solo con «Reintentar» en el panel.
async function scSincronizarOperaciones({ reintentarRechazadas = false } = {}) {
  let enviadas = 0;
  for (const op of await operacionesPendientes()) {
    if (op.error && !reintentarRechazadas) continue;
    const r = await scEnviarOperacion(op);
    if (r === "ok") {
      await quitarOperacionPendiente(op.uuid);
      enviadas++;
      scMarcarConexion(true);
    } else if (r === "sin-red") {
      scMarcarConexion(false);
      return { enviadas, parar: true };
    } else if (r === "sesion" || r === "despues") {
      return { enviadas, parar: true }; // la cola se conserva tal cual
    } else {
      // El servidor la rechazó (p. ej. otra persona ya cambió ese dato): se
      // avisa en el panel y se sigue con las demás.
      await scMarcarErrorOperacion(op.uuid, r);
    }
  }
  return { enviadas, parar: false };
}

async function sincronizarSubidas({ reintentarRechazadas = false } = {}) {
  if (scSincronizando || !scUsuarioId()) return;
  const cola = await subidasPendientes();
  const operaciones = await operacionesPendientes();
  if (!cola.length && !operaciones.length) return;
  scSincronizando = true;
  scPintarAviso();
  const estudiantesTocados = new Set();
  let enviadas = 0;
  try {
    const r = await scSincronizarOperaciones({ reintentarRechazadas });
    enviadas = r.enviadas;
    if (r.parar) return;
    for (const item of cola) {
      try {
        await scEnviar(item);
        await quitarSubidaPendiente(item.uuid);
        estudiantesTocados.add(item.estudianteId);
        scMarcarConexion(true);
      } catch (err) {
        if (err instanceof SinConexionError) {
          scMarcarConexion(false);
          break; // sigue sin red: se reintenta más tarde
        }
        if (err.status === 401) break; // hay que volver a entrar; la cola se conserva
        await scMarcarError(item.uuid, err.message); // este archivo no sirve: se avisa, no se reintenta en bucle
      }
    }
  } finally {
    scSincronizando = false;
    await scActualizarConteo();
    if (enviadas) {
      const quedan = (await operacionesPendientes()).filter((o) => o.error).length;
      scAvisoTemporal(
        `Volvió la conexión: se enviaron ${enviadas} cambio${enviadas === 1 ? "" : "s"} hecho${enviadas === 1 ? "" : "s"} sin conexión.` +
          (quedan ? ` ${quedan} no se pudo${quedan === 1 ? "" : "ieron"} guardar: revíselo${quedan === 1 ? "" : "s"} en «Usar sin wifi».` : "")
      );
    }
  }
  if (
    estudiantesTocados.size &&
    typeof vistaActual !== "undefined" && vistaActual === "ficha" &&
    estudiantesTocados.has(fichaEstudianteId) && typeof renderFicha === "function"
  ) {
    fichaAviso = { tipo: "exito", texto: "Volvió la conexión: los documentos guardados en el celular ya se subieron." };
    renderFicha();
  }
}

// --- Estado de conexión + aviso en pantalla ----------------------------------

function scMarcarConexion(hayRed) {
  const antes = scSinConexion;
  scSinConexion = !hayRed;
  if (antes !== scSinConexion) {
    scPintarAviso();
    if (hayRed) sincronizarSubidas();
  }
}

async function scActualizarConteo() {
  scPendientes = (await subidasPendientes()).length + (await operacionesPendientes()).length;
  scPintarAviso();
}

// ¿Hay red hasta el servidor? (navigator.onLine dice "hay wifi", no "el
// servidor del colegio responde"). El ?ping= nunca está guardado, así que el
// service worker va a la red: 503 = sin conexión.
async function scProbarConexion() {
  try {
    const res = await fetch(`/manifest.webmanifest?ping=${Date.now()}`, { cache: "no-store" });
    scMarcarConexion(res.ok);
  } catch {
    scMarcarConexion(false);
  }
}

function scPintarAviso() {
  let aviso = document.getElementById("sc-aviso");
  const mostrar = scSinConexion || scPendientes > 0 || scDescarga;
  if (!mostrar) {
    aviso?.remove();
    return;
  }
  if (!aviso) {
    aviso = document.createElement("div");
    aviso.id = "sc-aviso";
    aviso.className = "sc-aviso";
    aviso.setAttribute("role", "status");
    document.body.appendChild(aviso);
    aviso.addEventListener("click", (ev) => {
      if (ev.target.closest("[data-sc-subir]")) sincronizarSubidas();
      else if (ev.target.closest("[data-sc-abrir]")) abrirPanelSinWifi();
    });
  }
  const partes = [];
  const a = scAvance();
  if (a) {
    partes.push(
      `<span><i data-lucide=download class=ico></i> Descargando para usar sin wifi: ${esc(a.corto)}</span>` +
        `<span class="sc-aviso-barra"><span style="width:${a.pct}%"></span></span>`
    );
  } else if (scSinConexion) {
    partes.push('<span><i data-lucide=wifi-off class=ico></i> Sin conexión: mostrando lo guardado en este dispositivo</span>');
  }
  if (scPendientes) {
    partes.push(
      `<span><i data-lucide=cloud-upload class=ico></i> ${scPendientes} cambio${scPendientes === 1 ? "" : "s"} ${scSincronizando ? "enviándose..." : "esperando conexión"}</span>` +
        (!scSinConexion && !scSincronizando ? '<button type="button" data-sc-subir>Subir ahora</button>' : "")
    );
  }
  aviso.className = `sc-aviso ${scSinConexion ? "sin-red" : ""}`;
  aviso.innerHTML = `${partes.join("")}<button type="button" data-sc-abrir>Ver</button>`;
}

// Mensaje corto abajo (ej. "Descarga completa") que se va solo.
function scAvisoTemporal(texto) {
  document.getElementById("sc-aviso-temporal")?.remove();
  const aviso = document.createElement("div");
  aviso.id = "sc-aviso-temporal";
  aviso.className = "sc-aviso sc-aviso-listo";
  aviso.setAttribute("role", "status");
  aviso.innerHTML = `<span><i data-lucide=circle-check class=ico></i> ${esc(texto)}</span><button type="button">Cerrar</button>`;
  aviso.querySelector("button").addEventListener("click", () => aviso.remove());
  document.body.appendChild(aviso);
  setTimeout(() => aviso.remove(), 12000);
}

// --- Sesión: otra persona en el mismo celular / cerrar sesión ----------------

async function scBorrarGuardado() {
  try {
    const nombres = await caches.keys();
    await Promise.all(nombres.filter((n) => n === "ietaba-datos" || n === "ietaba-documentos").map((n) => caches.delete(n)));
  } catch { /* sin Cache API */ }
  try { localStorage.removeItem(SC_CLAVE_GUARDADOS); } catch { /* sin almacenamiento */ }
}

// La llama auth.js al confirmar una sesión.
async function sinConexionAlIniciarSesion(usuario) {
  let anterior = null;
  try { anterior = localStorage.getItem(SC_CLAVE_USUARIO); } catch { /* */ }
  if (anterior && anterior !== String(usuario.id)) {
    // Lo guardado era de otra persona: no debe verlo quien entra ahora.
    await scBorrarGuardado();
  }
  try { localStorage.setItem(SC_CLAVE_USUARIO, String(usuario.id)); } catch { /* */ }
  ["btn-sin-wifi", "btn-sin-wifi-movil"].forEach((id) => {
    const btn = document.getElementById(id);
    if (btn) btn.hidden = false;
  });
  await scActualizarConteo();
  scProbarConexion().then(sincronizarSubidas);
}

// La llama auth.js antes de cerrar sesión. false = la persona se arrepintió.
async function sinConexionAntesDeCerrarSesion() {
  const pendientes = await subidasPendientes();
  const operaciones = await operacionesPendientes();
  const total = pendientes.length + operaciones.length;
  if (
    total &&
    !confirm(
      `Hay ${total} cambio${total === 1 ? "" : "s"} guardado${total === 1 ? "" : "s"} en este dispositivo que todavía no se ha${total === 1 ? "" : "n"} enviado al sistema.\n\n` +
        "Si cierra sesión ahora se borrarán. ¿Cerrar sesión igual?"
    )
  ) {
    return false;
  }
  for (const p of pendientes) await quitarSubidaPendiente(p.uuid);
  for (const o of operaciones) await quitarOperacionPendiente(o.uuid);
  await scBorrarGuardado();
  try { localStorage.removeItem(SC_CLAVE_USUARIO); } catch { /* */ }
  return true;
}

// --- «Guardar para usar sin wifi» ----------------------------------------------

function scLeerGuardados() {
  try {
    return JSON.parse(localStorage.getItem(SC_CLAVE_GUARDADOS) || "null") || { estudiantes: [], fecha: null };
  } catch {
    return { estudiantes: [], fecha: null };
  }
}

function scEscribirGuardados(datos) {
  try { localStorage.setItem(SC_CLAVE_GUARDADOS, JSON.stringify(datos)); } catch { /* */ }
}

async function scPedir(url) {
  // Pasa por el service worker, que guarda la respuesta en el celular (la
  // cabecera le dice que espere aunque el servidor tarde: ver sw.js).
  const res = await fetch(url, { headers: { "X-Ietaba-Descarga": "1" } });
  if (!res.ok) throw new Error(`Error ${res.status}`);
  return res;
}

// Bytes de una respuesta (para el "faltan X MB").
async function scBytes(res) {
  const largo = Number(res.headers.get("content-length"));
  if (largo > 0) return largo;
  try { return (await res.clone().blob()).size; } catch { return 0; }
}

function scMb(bytes) {
  const mb = bytes / (1024 * 1024);
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`.replace(".", ",");
  return `${mb < 10 ? mb.toFixed(1) : Math.round(mb)} MB`.replace(".", ",");
}

function scTiempo(segundos) {
  if (!Number.isFinite(segundos) || segundos <= 0) return "";
  if (segundos < 60) return `unos ${Math.max(5, Math.round(segundos / 5) * 5)} s`;
  return `unos ${Math.round(segundos / 60)} min`;
}

async function scEnParalelo(tareas, n, alAvanzar) {
  let i = 0;
  let hechos = 0;
  const trabajador = async () => {
    while (i < tareas.length) {
      const tarea = tareas[i++];
      try { await tarea(); } catch { /* un dato que falla no detiene el resto */ }
      alAvanzar(++hechos);
    }
  };
  await Promise.all(Array.from({ length: Math.min(n, tareas.length) }, trabajador));
}

function scRepintarAvance() {
  scPintarAviso();
  scPintarProgresoPanel();
}

// Pasa la descarga al paso `fase` (ver SC_FASES) con `total` cosas por hacer.
function scFase(fase, total) {
  Object.assign(scDescarga, { fase, hechos: 0, total, bytes: 0, bytesTotal: 0, inicio: Date.now(), nombre: "" });
  scRepintarAvance();
}

async function scJson(url) {
  try {
    return await (await scPedir(url)).json();
  } catch {
    return null; // sin permiso o sin datos: se sigue con lo demás
  }
}

// --- Paso «pantallas»: recorrer cada módulo del menú --------------------------
// Cada pantalla arma sus consultas a su manera (filtros por defecto, año,
// periodo…). En vez de copiar esa lógica aquí, se abre la pantalla de verdad
// y el service worker guarda lo que pidió. Dentro de cada una se tocan también
// sus secciones/pestañas (los botones con estos data-*), que solo cambian lo
// que se muestra: ninguno guarda ni borra nada.
const SC_NAV = [
  "seccionBoletines", "seccionNotas", "seccionReportes", "vistaLista", "vistaDocentes",
  "vistaConciliacion", "grupoHorario", "seccionHorario", "anzVista", "icVista",
];
const SC_NAV_SELECTOR = SC_NAV.map((k) => `[data-${k.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)}]`).join(",");
const SC_MAX_SECCIONES = 40; // por módulo, por si una pantalla generara botones sin fin

// Estado de navegación que el recorrido cambia y luego deja como estaba.
const SC_ESTADO_VISTAS = [
  "vistaActual", "vistaAnterior", "sedeSeleccionada", "gradoSeleccionado", "divisionSeleccionada",
  "fichaEstudianteId", "paginaActual", "horarioSub", "seccionBoletines", "seccionNotas", "seccionReportes",
  "listaCupoVista", "listaDocentesVista", "conciliacionVista", "anzVista", "icVista", "dkVista", "orVista",
];
// Son `let` de otros archivos: no cuelgan de window, pero un eval indirecto
// corre en el ámbito global y sí los ve.
function scLeerGlobal(nombre) {
  try { return (0, eval)(nombre); } catch { return undefined; }
}
function scEscribirGlobal(nombre, valor) {
  try { (0, eval)(`${nombre} = ${JSON.stringify(valor)}`); } catch { /* ese módulo no existe */ }
}

// Espera a que la pantalla deje de pedir datos (nada en curso durante
// `quieto` ms). Tope `maximo` para no quedarse pegado en una que tarde.
async function scEsperarCalma({ quieto = 700, maximo = 60000 } = {}) {
  const inicio = Date.now();
  await new Promise((r) => setTimeout(r, 60));
  while (Date.now() - inicio < maximo) {
    if (scEnVuelo === 0 && Date.now() - scUltimoMovimiento >= quieto) return;
    await new Promise((r) => setTimeout(r, 120));
  }
}

function scClaveNav(boton) {
  const k = SC_NAV.find((n) => n in boton.dataset);
  return `${k}=${boton.dataset[k]}`;
}

async function scRecorrerPantallas() {
  const antes = SC_ESTADO_VISTAS.map((n) => [n, scLeerGlobal(n)]).filter(([, v]) => v !== undefined);
  const tabAntes = document.querySelector(".sidebar-nav .tab.activo");
  const scrollAntes = window.scrollY;
  const tabsVisibles = [...document.querySelectorAll(".sidebar-nav .tab")].filter((t) => !t.hidden && !t.closest("[hidden]"));
  scFase("pantallas", tabsVisibles.length);
  try {
    for (const tab of tabsVisibles) {
      const grupo = tab.closest(".nav-grupo")?.querySelector(".nav-grupo-titulo")?.textContent.trim();
      scDescarga.nombre = grupo ? `${grupo} · ${tab.textContent.trim()}` : tab.textContent.trim();
      scRepintarAvance();
      tab.click();
      await scEsperarCalma();
      const vistas = new Set();
      for (let i = 0; i < SC_MAX_SECCIONES; i++) {
        const botones = [...app.querySelectorAll(SC_NAV_SELECTOR)];
        botones.filter((b) => b.classList.contains("activo")).forEach((b) => vistas.add(scClaveNav(b)));
        const siguiente = botones.find((b) => !b.disabled && !vistas.has(scClaveNav(b)));
        if (!siguiente) break;
        vistas.add(scClaveNav(siguiente));
        siguiente.click();
        await scEsperarCalma();
      }
      scDescarga.hechos++;
      scRepintarAvance();
    }
  } finally {
    // De vuelta a donde estaba la persona, con sus filtros.
    antes.forEach(([n, v]) => scEscribirGlobal(n, v));
    tabs.forEach((t) => t.classList.toggle("activo", t === tabAntes));
    await render();
    window.scrollTo(0, scrollAntes);
  }
}

// --- Paso «datos»: lo que depende de qué se escoja en cada pantalla -----------

function scEsDocenteEnlazado() {
  return !!(sesionActual?.usuario?.docente_id && tienePermiso("asistencia.registrar"));
}

// Los próximos `n` días (fecha de Colombia), empezando hoy: para ir a una
// sede varios días sin red.
function scProximosDias(n) {
  return Array.from({ length: n }, (_, i) => fechaColombiaISO(new Date(Date.now() + i * 86400000)));
}

async function scUrlsPorEntidad() {
  const urls = new Set(["/api/auth/yo", "/api/sistema/modulos", "/api/sedes", "/api/areas", "/api/docentes", "/api/certificados/opciones"]);
  const anio = new Date().getFullYear();
  const dias = scProximosDias(7);
  const enParalelo = (lista, fn) => scEnParalelo(lista.map((x) => () => fn(x)), 6, () => {});
  const sedes = (await scJson("/api/sedes")) || [];

  if (tienePermiso("estudiantes.ver")) {
    // La lista completa: con ella sw.js arma sin red el listado filtrado.
    urls.add("/api/estudiantes");
    sedes.forEach((s) => urls.add(`/api/sedes/${s.id}/grados`));
  }

  if (tienePermiso("horario.ver")) {
    urls.add("/api/horario/bloques");
    const bloques = (await scJson(`/api/horario/bloques?anio_lectivo=${anio}`)) || [];
    new Set(bloques.map((b) => b.docente_id)).forEach((id) => urls.add(`/api/horario/docente/${id}?anio_lectivo=${anio}`));
    hzGruposDe(bloques).forEach((g) => {
      const base = `grado=${g.grado}&anio_lectivo=${anio}${g.curso != null ? `&curso=${g.curso}` : ""}`;
      urls.add(`/api/horario/grupo?${base}`);
      for (let dia = 1; dia <= 5; dia++) urls.add(`/api/horario/grupo?${base}&dia=${dia}`); // «Solo hoy»
    });
    dias.forEach((f) => {
      urls.add(`/api/horario/hoy?fecha=${f}`);
      urls.add(`/api/horario/reemplazos?fecha=${f}`);
    });
  }

  if (tienePermiso("diagnosticos.ver")) {
    urls.add("/api/diagnosticos/grados");
    sedes.filter((s) => s.pertenece_ietaba).forEach((s) =>
      ["grupos", "resumen", "casos", "generales"].forEach((k) => urls.add(`/api/diagnosticos/${k}?sede_id=${s.id}`))
    );
    // Detalle de cada grupo (y de sus estudiantes y casos) solo donde hay
    // diagnósticos: en las demás sedes no hay nada más que ver.
    const diagnosticos = (await scJson("/api/diagnosticos/grados")) || [];
    const grupos = [];
    for (const sedeId of new Set(diagnosticos.map((d) => d.sede_id))) {
      grupos.push(...((await scJson(`/api/diagnosticos/grupos?sede_id=${sedeId}`)) || []));
    }
    await enParalelo(grupos, async (g) => {
      const detalle = await scJson(`/api/diagnosticos/grupos/${g.sede_id}/${g.grado}${g.curso != null ? `?curso=${g.curso}` : ""}`);
      if (g.diagnostico_id) urls.add(`/api/diagnosticos/grados/${g.diagnostico_id}`);
      detalle?.estudiantes?.forEach((e) => urls.add(`/api/diagnosticos/estudiantes/${e.id}`));
      detalle?.casos?.forEach((c) => urls.add(`/api/diagnosticos/casos/${c.id}`));
    });
  }

  if (tienePermiso("usuarios.ver")) {
    ((await scJson("/api/admin/usuarios")) || []).forEach((u) => {
      urls.add(`/api/admin/usuarios/${u.id}`);
      if (tienePermiso("sesiones.ver")) urls.add(`/api/admin/usuarios/${u.id}/sesiones`);
    });
  }
  if (tienePermiso("roles.ver")) {
    urls.add("/api/admin/permisos");
    ((await scJson("/api/admin/roles")) || []).forEach((r) => urls.add(`/api/admin/roles/${r.id}`));
  }

  if (scEsDocenteEnlazado()) {
    urls.add("/api/docente/inicio");
    urls.add("/api/docente/mis-cursos");
    if (tienePermiso("asistencia.ver_propia")) [7, 30].forEach((d) => urls.add(`/api/docente/historial?dias=${d}`));
    const cursos = (await scJson("/api/docente/mis-cursos")) || [];
    const estudiantes = new Set();
    await enParalelo(cursos, async (c) => {
      const q = dkClaveBloque(c, "").replace(/&fecha=$/, "");
      dias.forEach((f) => urls.add(`/api/docente/asistencia/bloque?${dkClaveBloque(c, f)}`));
      const seg = await scJson(`/api/docente/grupo/seguimiento?${q}`);
      seg?.estudiantes?.forEach((e) => estudiantes.add(e.id));
    });
    estudiantes.forEach((id) => {
      urls.add(`/api/docente/estudiante/${id}`);
      urls.add(`/api/docente/observaciones?estudiante_id=${id}`);
    });
  }
  return [...urls];
}

// --- Pasos «fichas» y «documentos» ---------------------------------------------
// fichas (datos de cada estudiante): "812 de 2160"; documentos (fotos/PDF):
// "63 % · 6,1 de 10,5 MB · faltan 4,4 MB". Lo que ya estaba en el celular no
// se vuelve a bajar.
async function scDescargarEstudiantes(lista, modo, conDocumentos) {
  const guardados = [];
  const documentos = new Map(); // url → bytes esperados
  scFase("fichas", lista.length);
  const avanzar = scRepintarAvance;

  const tareasFichas = lista.map((est) => async () => {
    const base = modo === "docente" ? `/api/docente/estudiante/${est.id}` : `/api/estudiantes/${est.id}`;
    const completo = await (await scPedir(modo === "docente" ? `${base}/completo` : base)).json();
    const extras = modo === "docente"
      ? [base, `${base}/rendimiento`, `/api/docente/observaciones?estudiante_id=${est.id}`, `${base}/datos-ficha`]
      : [`${base}/datos-ficha`, `${base}/riesgo-promocion`];
    await Promise.all(extras.map((u) => scPedir(u).catch(() => null)));
    if (conDocumentos) (completo.fotos || []).forEach((f) => {
      documentos.set(`/api/fotos/${f.id}/archivo`, f.tamano_bytes || 0);
      // La miniatura de una foto es el mismo archivo (sin red, sw.js la saca de
      // /archivo): solo se baja aparte la de los PDF, que es una imagen chica.
      if (f.es_pdf) documentos.set(`/api/fotos/${f.id}/miniatura`, KB_MINIATURA_PDF * 1024);
    });
    guardados.push({
      id: est.id,
      modo,
      nombre: [completo.primer_nombre, completo.segundo_nombre, completo.primer_apellido, completo.segundo_apellido].filter(Boolean).join(" "),
      grupo: `${typeof nombreGrado === "function" ? nombreGrado(completo.grado) : completo.grado}${completo.curso != null ? ` · ${completo.curso}` : ""}`,
      sede: completo.sede?.nombre || "",
      documentos: conDocumentos ? (completo.fotos || []).length : 0,
    });
  });
  await scEnParalelo(tareasFichas, 6, (hechos) => { scDescarga.hechos = hechos; avanzar(); });

  // Documentos. Se saltan los que ya están en el celular.
  let cache = null;
  try { cache = await caches.open("ietaba-documentos"); } catch { /* sin Cache API */ }
  const faltan = [];
  let yaEstaban = 0;
  for (const [url, bytes] of documentos) {
    if (cache && (await cache.match(url))) yaEstaban += bytes;
    else faltan.push({ url, bytes });
  }
  scFase("documentos", faltan.length);
  Object.assign(scDescarga, { bytesTotal: faltan.reduce((s, d) => s + d.bytes, 0), yaEstaban });
  avanzar();
  const tareasDocs = faltan.map((d) => async () => {
    const res = await scPedir(d.url);
    const real = await scBytes(res);
    scDescarga.bytes += real || d.bytes;
    scDescarga.bytesTotal = Math.max(scDescarga.bytesTotal, scDescarga.bytes);
  });
  await scEnParalelo(tareasDocs, 4, (hechos) => { scDescarga.hechos = hechos; avanzar(); });

  const resumen = {
    documentos: [...documentos.keys()].filter((u) => u.endsWith("/archivo")).length,
    mb: scMb(scDescarga.bytes + yaEstaban),
  };
  return { guardados, resumen };
}

// Estudiantes de los grupos donde el docente es director de grupo (la ficha
// completa y los documentos son solo suyos). [] si no dirige ninguno: igual
// se baja todo lo demás de sus cursos.
async function scListaMisGrupos() {
  await scPedir("/api/docente/inicio").catch(() => null);
  const cursos = await api("/api/docente/mis-cursos");
  const estudiantes = new Map();
  for (const c of cursos) {
    const q =
      `sede_id=${c.sede_id}&grado=${c.grado}` +
      (c.curso != null ? `&curso=${c.curso}` : "") +
      (c.area_id != null ? `&area_id=${c.area_id}` : "");
    const seg = await (await scPedir(`/api/docente/grupo/seguimiento?${q}`)).json().catch(() => null);
    // La ficha completa (con documentos) es solo del director de grupo.
    if (seg?.es_director) seg.estudiantes.forEach((e) => estudiantes.set(e.id, e));
  }
  return [...estudiantes.values()];
}

// sedeId vacío = todas las sedes.
async function scListaSedes(sedeId) {
  return api(`/api/estudiantes?estado=ACTIVO${sedeId ? `&sede_id=${sedeId}` : ""}`);
}

// Fichas de quién baja este usuario: «admin» (todos los activos, o una
// sede), «docente» (sus grupos de director) o ninguna.
function scModoFichas() {
  if (scPuedeSede()) return "admin";
  if (scEsDocente()) return "docente";
  return null;
}

// «Descargar todo»: los cuatro pasos seguidos. sedeId solo limita las fichas
// y documentos (para celulares con poco espacio); lo demás va completo.
async function scDescargarTodo(sedeId) {
  const modo = scModoFichas();
  scDescarga = { fases: modo ? ["pantallas", "datos", "fichas", "documentos"] : ["pantallas", "datos"], inicio: Date.now() };
  await scRecorrerPantallas();

  const urls = await scUrlsPorEntidad();
  scFase("datos", urls.length);
  await scEnParalelo(urls.map((u) => () => scPedir(u)), 6, (hechos) => { scDescarga.hechos = hechos; scRepintarAvance(); });

  let guardados = [];
  let resumen = { documentos: 0, mb: scMb(0) };
  if (modo) {
    const lista = modo === "docente" ? await scListaMisGrupos() : await scListaSedes(sedeId);
    const conDocumentos = modo === "docente" || tienePermiso("estudiantes.ver_documentos");
    if (lista.length) ({ guardados, resumen } = await scDescargarEstudiantes(lista, modo, conDocumentos));
  }
  scDescarga = null;
  scPintarAviso();
  return { guardados, resumen, datos: urls.length };
}

// r = { estudiantes, documentos, pdfs, bytes_documentos } (del servidor).
function scBytesEstimados(r) {
  return r.estudiantes * KB_FICHA * 1024 + r.bytes_documentos + r.pdfs * KB_MINIATURA_PDF * 1024;
}

function scResumenPeso(r) {
  return `${r.estudiantes.toLocaleString("es-CO")} estudiantes · ${r.documentos} documentos · aprox. ${scMb(scBytesEstimados(r))}`;
}

async function scEspacioLibre() {
  try {
    const { quota, usage } = await navigator.storage.estimate();
    return quota ? { libre: quota - usage, usado: usage } : null;
  } catch {
    return null;
  }
}

// --- Mientras descarga: notificación al terminar + pantalla encendida -----------
// · Notificación: solo si la persona está en otra app/pestaña cuando termina
//   (si está mirando la app ya ve el aviso). Funciona en Android y PC; en
//   iPhone solo dentro del ícono de inicio (iOS 16.4+), y como iOS congela la
//   app al salir de ella, allá lo que de verdad ayuda es lo siguiente:
// · Pantalla encendida (Wake Lock): que el celular no se bloquee solo a mitad
//   de la descarga, que es lo que la pausa en iPhone. Se suelta al terminar.

async function scPedirPermisoNotificaciones() {
  try {
    if ("Notification" in window && Notification.permission === "default") await Notification.requestPermission();
  } catch { /* navegador sin notificaciones */ }
}

async function scNotificar(titulo, cuerpo) {
  if (document.visibilityState === "visible") return;
  try {
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    const opciones = { body: cuerpo, icon: "/static/icons/icon-192.png?v=2", badge: "/static/icons/icon-192.png?v=2", tag: "ietaba-descarga" };
    const registro = "serviceWorker" in navigator ? await navigator.serviceWorker.getRegistration() : null;
    if (registro) await registro.showNotification(titulo, opciones);
    else new Notification(titulo, opciones);
  } catch { /* sin permiso o no soportado: queda el aviso dentro de la app */ }
}

let scBloqueoPantalla = null;

async function scMantenerPantallaEncendida(encender) {
  try {
    if (!encender) {
      await scBloqueoPantalla?.release();
      scBloqueoPantalla = null;
      return;
    }
    if (!scBloqueoPantalla && navigator.wakeLock && document.visibilityState === "visible") {
      scBloqueoPantalla = await navigator.wakeLock.request("screen");
      scBloqueoPantalla.addEventListener("release", () => { scBloqueoPantalla = null; });
    }
  } catch { /* no soportado o sin batería: sigue igual, solo puede bloquearse */ }
}

// --- Panel «Usar sin wifi» ---------------------------------------------------

function scEsDocente() {
  const u = sesionActual?.usuario;
  return !!(u?.docente_id && u.permisos?.includes("estudiantes.documentos_grupo"));
}

function scPuedeSede() {
  return !!sesionActual?.usuario?.permisos?.includes("estudiantes.ver");
}

// Texto y porcentaje del avance (lo usan el panel y el aviso de abajo).
const SC_FASES = {
  pantallas: { titulo: "Abriendo cada pantalla", corto: "Pantallas", unidad: "módulos" },
  datos: { titulo: "Horarios, grupos y demás datos", corto: "Datos", unidad: "datos" },
  fichas: { titulo: "Fichas de estudiantes", corto: "Fichas", unidad: "estudiantes" },
  documentos: { titulo: "Descargando documentos", corto: "Documentos", unidad: "documentos" },
};

function scAvance() {
  const d = scDescarga;
  if (!d?.fase) return null;
  const f = SC_FASES[d.fase];
  const titulo = `Paso ${d.fases.indexOf(d.fase) + 1} de ${d.fases.length} · ${f.titulo}`;
  if (d.fase !== "documentos") {
    const pct = d.total ? Math.round((d.hechos / d.total) * 100) : 0;
    const detalle = `${d.hechos} de ${d.total} ${f.unidad}${d.nombre ? ` · ahora: ${d.nombre}` : ""}`;
    return { pct, titulo, detalle, corto: `${f.corto} ${pct} %` };
  }
  if (!d.total) return { pct: 100, titulo, detalle: "Ya estaban todos en el celular", corto: "100 %" };
  const pct = d.bytesTotal ? Math.min(100, Math.round((d.bytes / d.bytesTotal) * 100)) : Math.round((d.hechos / d.total) * 100);
  const faltan = Math.max(0, d.bytesTotal - d.bytes);
  const seg = (Date.now() - d.inicio) / 1000;
  const velocidad = seg > 1 ? d.bytes / seg : 0;
  const tiempo = velocidad ? scTiempo(faltan / velocidad) : "";
  return {
    pct,
    titulo,
    detalle: `${scMb(d.bytes)} de ${scMb(d.bytesTotal)} · faltan ${scMb(faltan)}${tiempo ? ` · ${tiempo}` : ""}`,
    corto: `${pct} % · faltan ${scMb(faltan)}`,
  };
}

function scPintarProgresoPanel() {
  const cont = document.getElementById("sc-progreso");
  const a = scAvance();
  if (!cont || !a) return;
  cont.innerHTML = `
    <div class="sc-descarga">
      <div class="sc-descarga-fila"><strong>${esc(a.titulo)}</strong><span class="sc-descarga-pct">${a.pct} %</span></div>
      <div class="sc-descarga-barra"><span style="width:${a.pct}%"></span></div>
      <p class="docv-sub">${esc(a.detalle)}</p>
      ${scDescarga.fase === "pantallas"
        ? '<p class="sc-descarga-espere"><i data-lucide=loader class=ico></i> La app está abriendo sola cada pantalla para guardarla. No la toque hasta que pase al paso 2.</p>'
        : '<p class="sc-descarga-espere"><i data-lucide=loader class=ico></i> Descargando en segundo plano…</p>'}
      <p class="docv-sub">${scDescarga.fase === "pantallas" ? "Después" : "Ya"} puede cerrar esta ventana y seguir usando la app; el avance se ve abajo. La pantalla se queda encendida sola hasta que termine.
        ${/iPhone|iPad|iPod/i.test(navigator.userAgent)
          ? "En iPhone <strong>no salga de la app</strong>: si sale, iOS pausa la descarga (sigue al volver)."
          : "Si se va a otra app, le avisamos con una notificación cuando termine."}</p>
    </div>`;
}

async function abrirPanelSinWifi() {
  document.getElementById("sc-panel")?.remove();
  const panel = document.createElement("div");
  panel.id = "sc-panel";
  panel.className = "modal-fondo est-modal";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Usar sin wifi");
  document.body.appendChild(panel);
  panel.addEventListener("click", (ev) => { if (ev.target === panel) panel.remove(); });
  await scPintarPanel();
}

async function scPintarPanel() {
  const panel = document.getElementById("sc-panel");
  if (!panel) return;
  const pendientes = await subidasPendientes();
  const operaciones = await operacionesPendientes();
  const guardados = scLeerGuardados();
  const swActivo = "serviceWorker" in navigator && !!navigator.serviceWorker.controller;
  const esCelular = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
  // En iPhone/iPad, Safari y la app de la pantalla de inicio guardan cada uno
  // lo suyo (sesión, descargas): lo bajado en Safari no se ve en la app.
  const esIos = /iPhone|iPad|iPod/i.test(navigator.userAgent);
  const enAppDeInicio = window.navigator.standalone === true || window.matchMedia?.("(display-mode: standalone)").matches;
  const totalPendientes = pendientes.length + operaciones.length;
  // Peso de cada opción, para mostrarlo antes de descargar.
  let tamanos = null;
  if (!scSinConexion) {
    try {
      tamanos = scModoFichas() === "admin" ? await api("/api/estudiantes/tamano-descarga")
        : scModoFichas() === "docente" ? await api("/api/docente/tamano-descarga") : null;
    } catch { /* sin red: se muestra sin peso */ }
  }
  const sedes = tamanos?.sedes || [];
  const espacio = await scEspacioLibre();
  const modoFichas = scModoFichas();
  const modulos = [...document.querySelectorAll(".sidebar-nav .tab")]
    .filter((t) => !t.hidden && !t.closest("[hidden]"))
    .map((t) => (t.dataset.vista === "docente" ? "Docencia" : t.dataset.vista === "orientacion" ? "Orientación" : t.textContent.trim()))
    .filter((m, i, todos) => todos.indexOf(m) === i);

  panel.innerHTML = `
    <div class="modal-caja modal-caja-ancha sc-caja">
      <header class="est-modal-head">
        <h3><i data-lucide=wifi-off class=ico></i> Usar sin wifi</h3>
        <button type="button" class="est-visor-cerrar" data-sc-cerrar aria-label="Cerrar"></button>
      </header>

      <p class="sc-estado ${scSinConexion ? "sin-red" : "con-red"}">
        ${scSinConexion
          ? '<i data-lucide=wifi-off class=ico></i> Ahora <strong>no hay conexión</strong> con el sistema del colegio. Puede mirar lo guardado y tomar fotos: se subirán solas cuando vuelva la conexión (con la app abierta).'
          : '<i data-lucide=wifi class=ico></i> Hay conexión con el sistema del colegio.'}
      </p>
      ${esIos && !enAppDeInicio
        ? '<p class="alerta-caja"><strong>Está en Safari.</strong> En iPhone, Safari y el ícono IETABA de la pantalla de inicio guardan las cosas por separado: lo que descargue aquí <strong>no</strong> aparece en el ícono. Si va a usar el ícono, ábralo, entre con su usuario y descargue desde allá.</p>'
        : ""}
      ${swActivo ? "" : esCelular || window.isSecureContext
        ? '<p class="alerta-caja">Para usar la app sin wifi hay que abrirla por la dirección segura (<strong>https://…:8443</strong>) y agregarla a la pantalla de inicio. Pida ayuda en secretaría.</p>'
        : `<p class="alerta-caja">Este computador todavía no puede usar la app sin conexión (entró por la dirección normal, sin candado).
             <a class="boton secundario" href="/instalar-pc.cmd" download><i data-lucide=monitor-down class=ico></i> Instalar en este computador</a><br>
             <span class="docv-sub">Descargue y abra el archivo (si Windows avisa, «Más información» → «Ejecutar de todas formas»). Instala el certificado del colegio y deja en el escritorio el acceso directo <strong>IETABA</strong>: use siempre ese.</span></p>`}

      <section class="sc-seccion">
        <h4>Cambios esperando para enviarse (${totalPendientes})</h4>
        ${operaciones.length
          ? `<ul class="sc-lista">${operaciones.map((o) => `
              <li>
                <div><strong>${esc(o.descripcion)}</strong><span class="docv-sub">${new Date(o.creado).toLocaleString("es-CO")}</span>
                ${o.error ? `<span class="sc-error">El sistema no lo aceptó: ${esc(o.error)}</span>` : ""}</div>
                <button type="button" class="docv-icono-btn peligro" data-sc-quitar-op="${o.uuid}" title="Descartar este cambio" aria-label="Descartar este cambio"><i data-lucide=trash-2 class=ico></i></button>
              </li>`).join("")}</ul>`
          : ""}
        ${pendientes.length
          ? `<ul class="sc-lista">${pendientes.map((p) => `
              <li>
                <div><strong>${esc(p.etiqueta)}</strong><span class="docv-sub">${esc(p.estudianteNombre || `Estudiante #${p.estudianteId}`)} · ${new Date(p.creado).toLocaleString("es-CO")}</span>
                ${p.error ? `<span class="sc-error">No se pudo subir: ${esc(p.error)}</span>` : ""}</div>
                <button type="button" class="docv-icono-btn peligro" data-sc-quitar="${p.uuid}" title="Quitar de la cola" aria-label="Quitar de la cola"><i data-lucide=trash-2 class=ico></i></button>
              </li>`).join("")}</ul>`
          : ""}
        ${totalPendientes
          ? scSinConexion ? "" : `<button type="button" class="boton" data-sc-subir-panel><i data-lucide=cloud-upload class=ico></i> ${operaciones.some((o) => o.error) ? "Reintentar todo ahora" : "Enviar ahora"}</button>`
          : '<p class="docv-sub">Ninguno. Todo lo que hizo ya está en el sistema.</p>'}
      </section>

      <section class="sc-seccion">
        <h4>Descargar todo para usar sin wifi</h4>
        <p class="docv-sub">
          Se guarda en este dispositivo todo lo que su usuario puede ver: <strong>${esc(modulos.join(", ") || "su información")}</strong>${
            modoFichas === "admin" ? ", y las fichas" + (tienePermiso("estudiantes.ver_documentos") ? " y documentos" : "") + " de los estudiantes activos"
            : modoFichas === "docente" ? ", y las fichas y documentos de los grupos que dirige" : ""}.
          Así puede usar la app igual que con wifi; lo que cambie sin conexión se envía solo al volver.
          Hágalo con wifi, antes de ir a la sede. Si ya había descargado, los documentos que ya tiene no se vuelven a bajar.
          ${espacio ? `<br>Espacio libre en el celular para la app: <strong>${scMb(espacio.libre)}</strong> · ya usado: ${scMb(espacio.usado)}.` : ""}
        </p>
        <div id="sc-progreso"></div>
        ${scSinConexion ? '<p class="docv-sub">Necesita conexión para descargar.</p>' : `
          <button type="button" class="boton doc-boton-grande sc-boton-descargar" data-sc-guardar="todo" ${scDescarga ? "disabled" : ""}>
            <span><i data-lucide=download class=ico></i> Descargar todo${modoFichas === "admin" ? " (todas las sedes)" : ""}</span>
            ${tamanos ? `<span class="sc-peso">${scResumenPeso(modoFichas === "admin" ? tamanos.total : tamanos)} + horarios y demás módulos</span>` : ""}
          </button>
          ${modoFichas === "admin" ? `
            <div class="sc-fila"><select id="sc-sede"><option value="">o fichas de una sola sede…</option>${sedes
              .map((s) => `<option value="${s.sede_id}" data-peso="${esc(scResumenPeso(s))}">${esc(s.nombre)} · ${s.estudiantes} est. · ${scMb(scBytesEstimados(s))}</option>`)
              .join("")}</select>
            <button type="button" class="boton secundario" data-sc-guardar="sede" id="sc-btn-sede" ${scDescarga ? "disabled" : ""}><i data-lucide=download class=ico></i> Todo, con fichas solo de esa sede</button></div>
            <p class="docv-sub" id="sc-peso-sede"></p>` : ""}`}
      </section>

      <section class="sc-seccion">
        <h4>Guardado en este celular (${guardados.modulos ? "todos los módulos · " : ""}${guardados.estudiantes.length} estudiantes)</h4>
        ${guardados.fecha ? `<p class="docv-sub">Última descarga: ${new Date(guardados.fecha).toLocaleString("es-CO")}</p>` : ""}
        ${guardados.estudiantes.length
          ? `<input type="search" id="sc-buscar" class="sc-buscar" placeholder="Buscar estudiante..." />
             <ul class="sc-lista sc-lista-estudiantes">${guardados.estudiantes.map((g) => `
               <li data-sc-nombre="${esc(g.nombre.toLowerCase())}">
                 <button type="button" class="sc-estudiante" data-sc-abrir-est="${g.id}" data-sc-modo="${g.modo}">
                   <strong>${esc(g.nombre)}</strong><span class="docv-sub">${esc(g.grupo)} · ${esc(g.sede)} · ${g.documentos} doc.</span>
                 </button>
               </li>`).join("")}</ul>
             <button type="button" class="docv-link" data-sc-borrar><i data-lucide=trash-2 class=ico></i> Borrar lo guardado en este celular</button>`
          : guardados.modulos
            ? '<button type="button" class="docv-link" data-sc-borrar><i data-lucide=trash-2 class=ico></i> Borrar lo guardado en este celular</button>'
            : '<p class="docv-sub">Todavía no ha guardado nada.</p>'}
      </section>
    </div>`;

  panel.querySelector("[data-sc-cerrar]").addEventListener("click", () => panel.remove());
  panel.querySelectorAll("[data-sc-quitar]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("¿Quitar este documento de la cola? No se subirá y se borrará del celular.")) return;
      await quitarSubidaPendiente(b.dataset.scQuitar);
      scPintarPanel();
    })
  );
  panel.querySelectorAll("[data-sc-quitar-op]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("¿Descartar este cambio? No se enviará al sistema y se borrará de este dispositivo.")) return;
      await quitarOperacionPendiente(b.dataset.scQuitarOp);
      scPintarPanel();
    })
  );
  panel.querySelector("[data-sc-subir-panel]")?.addEventListener("click", async () => {
    await sincronizarSubidas({ reintentarRechazadas: true });
    scPintarPanel();
  });
  panel.querySelectorAll("[data-sc-guardar]").forEach((boton) => boton.addEventListener("click", async () => {
    const tipo = boton.dataset.scGuardar;
    const sedeId = document.getElementById("sc-sede")?.value;
    if (tipo === "sede" && !sedeId) {
      alert("Escoja primero la sede.");
      return;
    }
    panel.querySelectorAll("[data-sc-guardar]").forEach((b) => { b.disabled = true; });
    // El permiso se pide aquí: el navegador solo lo deja preguntar justo
    // después de un toque de la persona.
    await scPedirPermisoNotificaciones();
    await scMantenerPantallaEncendida(true);
    try {
      const { guardados: nuevos, resumen, datos } = await scDescargarTodo(tipo === "sede" ? sedeId : "");
      const previos = scLeerGuardados().estudiantes.filter((g) => !nuevos.some((n) => n.id === g.id));
      const todos = [...previos, ...nuevos].sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
      scEscribirGuardados({ estudiantes: todos, fecha: Date.now(), modulos: true });
      const cuanto = nuevos.length
        ? `todos los módulos, ${datos} datos, ${nuevos.length} estudiantes y ${resumen.documentos} documentos (${resumen.mb})`
        : `todos los módulos y ${datos} datos`;
      const texto = `Descarga completa (100 %): ${cuanto}. Ya puede usar la app sin wifi.`;
      scMantenerPantallaEncendida(false);
      scNotificar("Descarga completa", `${cuanto}. Ya puede usar la app sin wifi.`);
      // Si la persona cerró el panel mientras descargaba (sigue en segundo
      // plano), el aviso de abajo le cuenta que terminó.
      if (!document.getElementById("sc-panel")) {
        scAvisoTemporal(texto);
        return;
      }
      await scPintarPanel();
      const cont = document.getElementById("sc-progreso");
      if (cont) cont.innerHTML = `<p class="exito-caja"><i data-lucide=circle-check class=ico></i> ${esc(texto)}</p>`;
    } catch (err) {
      scDescarga = null;
      scPintarAviso();
      scMantenerPantallaEncendida(false);
      scNotificar("La descarga no terminó", "Lo que alcanzó a bajar queda guardado. Abra IETABA y toque Descargar de nuevo para seguir.");
      const texto = `No se pudo descargar: ${err.message}. Lo que alcanzó a bajar queda guardado; toque de nuevo para seguir.`;
      const cont = document.getElementById("sc-progreso");
      if (cont) cont.innerHTML = `<p class="alerta-caja">${esc(texto)}</p>`;
      else scAvisoTemporal(texto);
      document.querySelectorAll("#sc-panel [data-sc-guardar]").forEach((b) => { b.disabled = false; });
    }
  }));
  panel.querySelector("#sc-sede")?.addEventListener("change", (ev) => {
    const opcion = ev.target.selectedOptions[0];
    document.getElementById("sc-peso-sede").textContent = opcion?.dataset.peso ? `Esa sede: ${opcion.dataset.peso}` : "";
  });
  panel.querySelector("#sc-buscar")?.addEventListener("input", (ev) => {
    const q = ev.target.value.trim().toLowerCase();
    panel.querySelectorAll("[data-sc-nombre]").forEach((li) => { li.hidden = !!q && !li.dataset.scNombre.includes(q); });
  });
  panel.querySelectorAll("[data-sc-abrir-est]").forEach((b) =>
    b.addEventListener("click", () => {
      panel.remove();
      fichaModoDocente = b.dataset.scModo === "docente";
      fichaSubSiguiente = "documentos";
      abrirFicha(Number(b.dataset.scAbrirEst), fichaModoDocente ? "docente" : "estudiantes");
    })
  );
  panel.querySelector("[data-sc-borrar]")?.addEventListener("click", async () => {
    if (!confirm("¿Borrar del celular las fichas y fotos guardadas? (Lo que está en el sistema no se toca.)")) return;
    await scBorrarGuardado();
    scPintarPanel();
  });
  scPintarProgresoPanel();
}

// --- Arranque ------------------------------------------------------------------

(function iniciarSinConexion() {
  document.getElementById("btn-sin-wifi")?.addEventListener("click", abrirPanelSinWifi);
  document.getElementById("btn-sin-wifi-movil")?.addEventListener("click", abrirPanelSinWifi);

  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/sw.js").catch(() => { /* sin SW la app funciona igual, solo no offline */ });
    navigator.serviceWorker.addEventListener("message", (ev) => {
      if (ev.data?.tipo === "sin-conexion") scMarcarConexion(false);
    });
    // Que iOS no borre lo guardado por falta de espacio sin preguntar.
    navigator.storage?.persist?.().catch(() => {});
  }

  window.addEventListener("online", () => scProbarConexion());
  window.addEventListener("offline", () => scMarcarConexion(false));
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    scProbarConexion().then(sincronizarSubidas);
    // El navegador suelta el "pantalla encendida" al salir de la app.
    if (scDescarga) scMantenerPantallaEncendida(true);
  });
  setInterval(() => {
    if (document.visibilityState === "visible" && (scPendientes || scSinConexion)) {
      scProbarConexion().then(sincronizarSubidas);
    }
  }, SC_INTERVALO_MS);
})();
