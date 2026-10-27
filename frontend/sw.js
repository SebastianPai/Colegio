// Service worker de IETABA: la app sigue abriendo y mostrando lo último que
// se vio (o se descargó con «Guardar para usar sin wifi») cuando el celular
// no está conectado a la red del colegio.
//
// - La app (index.html, JS, CSS, librerías del escáner) se guarda al
//   instalar y se sirve desde el celular, revisando en segundo plano si hay
//   una versión nueva.
// - Los datos (GET /api/...) van primero a la red; si no hay red (o el
//   servidor no responde en unos segundos) se usa la última copia guardada.
// - Las fotos de documentos (/api/fotos/{id}/...) no cambian nunca para un
//   mismo id: se sirven desde el celular si ya están.
// - Las subidas NO pasan por aquí: sin conexión las guarda la app en su
//   propia cola (static/js/sin_conexion.js) y las manda al volver la red.
//
// Solo funciona por HTTPS (iniciar_https.ps1) o en localhost.

const VERSION_APP = "app-v10";
const CACHE_APP = `ietaba-${VERSION_APP}`;
const CACHE_DATOS = "ietaba-datos";
const CACHE_DOCUMENTOS = "ietaba-documentos";
const ESPERA_RED_MS = 6000;
// «Descargar todo» (sin_conexion.js) marca sus peticiones con esta cabecera:
// con wifi vale más esperar a que llegue (la lista completa de estudiantes
// tarda varios segundos) que quedarse sin el dato.
const CABECERA_DESCARGA = "X-Ietaba-Descarga";
const ESPERA_DESCARGA_MS = 120000;

// Lo que index.html no trae en sus <script>/<link> pero hace falta sin red.
const EXTRAS = [
  "/",
  "/manifest.webmanifest",
  "/static/ficha_matricula.html",
  "/static/logos/logo1.jpg",
  "/static/logos/logo2.jpeg",
  "/static/icons/apple-touch-icon.png",
  "/static/icons/icon-192.png",
  "/static/vendor/opencv.js",
  "/static/vendor/jspdf.umd.min.js",
  "/static/vendor/pdf.min.mjs",
  "/static/vendor/pdf.worker.min.mjs",
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE_APP);
      // Todo lo que index.html carga (con su ?v= exacto): así la primera vez
      // que se abra sin red ya está todo, aunque esa carga nunca haya pasado
      // por el service worker.
      const html = await (await fetch("/", { cache: "no-store" })).text();
      const enlaces = [...html.matchAll(/(?:src|href)="(\/static\/[^"]+)"/g)].map((m) => m[1]);
      const urls = [...new Set([...EXTRAS, ...enlaces])];
      await Promise.all(
        urls.map((url) =>
          fetch(url, { cache: "no-store" })
            .then((res) => (res.ok ? cache.put(url, res) : null))
            .catch(() => null)
        )
      );
      self.skipWaiting();
    })()
  );
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    (async () => {
      const nombres = await caches.keys();
      await Promise.all(
        nombres.filter((n) => n.startsWith("ietaba-app-") && n !== CACHE_APP).map((n) => caches.delete(n))
      );
      await self.clients.claim();
    })()
  );
});

// Al cerrar sesión o al entrar otra persona en el mismo celular se borran
// los datos y documentos guardados (ver sin_conexion.js).
self.addEventListener("message", (evento) => {
  if (evento.data?.tipo === "limpiar-datos") {
    evento.waitUntil(Promise.all([caches.delete(CACHE_DATOS), caches.delete(CACHE_DOCUMENTOS)]));
  }
});

// Tocar la notificación de "descarga completa" (sin_conexion.js) abre la app.
self.addEventListener("notificationclick", (evento) => {
  evento.notification.close();
  evento.waitUntil(
    (async () => {
      const clientes = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      if (clientes.length) return clientes[0].focus();
      return self.clients.openWindow("/");
    })()
  );
});

function conTiempoLimite(promesa, ms) {
  return new Promise((resolver, rechazar) => {
    const t = setTimeout(() => rechazar(new Error("tiempo agotado")), ms);
    promesa.then(
      (v) => { clearTimeout(t); resolver(v); },
      (e) => { clearTimeout(t); rechazar(e); }
    );
  });
}

async function avisarSinConexion() {
  const clientes = await self.clients.matchAll({ type: "window" });
  clientes.forEach((c) => c.postMessage({ tipo: "sin-conexion" }));
}

// Clave con la que se guarda un dato: la ruta y los parámetros ORDENADOS.
// Cada pantalla arma sus parámetros en su propio orden; así lo que bajó
// «Descargar todo» (sin_conexion.js) sirve aunque lo haya pedido en otro.
function claveDatos(url) {
  const u = new URL(url);
  const pares = [...u.searchParams.entries()].sort(([a, x], [b, y]) => (a < b ? -1 : a > b ? 1 : x < y ? -1 : x > y ? 1 : 0));
  const q = new URLSearchParams(pares).toString();
  return u.pathname + (q ? `?${q}` : "");
}

function respuestaJson(datos) {
  return new Response(JSON.stringify(datos), {
    headers: { "Content-Type": "application/json", "X-Sin-Conexion": "1" },
  });
}

// --- Listado de estudiantes sin red -------------------------------------------
// Buscar, filtrar y paginar dan una URL distinta por cada combinación: no se
// pueden bajar todas. Sin red se responden aquí a partir de la lista completa
// (/api/estudiantes, que «Descargar todo» guarda), con los mismos filtros que
// crud._filtrar_estudiantes. Esa lista ya viene en el orden del servidor
// (grado, curso, apellido, nombre), así que filtrar no lo cambia.

const sinTildes = (v) => String(v ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function filtrarEstudiantes(lista, p) {
  let r = lista;
  const num = (k) => (p.get(k) != null && p.get(k) !== "" ? Number(p.get(k)) : null);
  const sede = num("sede_id"), grado = num("grado"), curso = num("curso");
  if (sede != null) r = r.filter((e) => e.sede_id === sede);
  if (grado != null) r = r.filter((e) => e.grado === grado);
  if (curso != null) r = r.filter((e) => e.curso === curso);
  if (p.get("sin_curso") === "true") r = r.filter((e) => e.curso == null);
  if (p.get("estado")) r = r.filter((e) => (e.estado || "").toUpperCase() === p.get("estado").toUpperCase());
  if (p.get("solo_no_verificados") === "true") r = r.filter((e) => e.verificado_matricula === false);
  const q = sinTildes(p.get("q") || "");
  if (q) {
    r = r.filter((e) =>
      sinTildes(`${e.primer_nombre || ""} ${e.segundo_nombre || ""} ${e.primer_apellido || ""} ${e.segundo_apellido || ""}`).includes(q) ||
      sinTildes(e.documento).includes(q)
    );
  }
  return r;
}

async function estudiantesSinRed(url, cache) {
  const rutas = ["/api/estudiantes", "/api/estudiantes/pagina", "/api/estudiantes/verificar"];
  if (!rutas.includes(url.pathname)) return null;
  const guardada = await cache.match("/api/estudiantes");
  if (!guardada) return null;
  const todos = await guardada.json();
  const p = url.searchParams;
  if (url.pathname === "/api/estudiantes/verificar") {
    const est = todos.find((e) => e.documento === p.get("documento")) || null;
    return respuestaJson({ existe: !!est, estudiante: est });
  }
  const filtrados = filtrarEstudiantes(todos, p);
  if (url.pathname === "/api/estudiantes") return respuestaJson(filtrados);
  const pagina = Math.max(Number(p.get("pagina")) || 1, 1);
  const porPagina = p.get("por_pagina") != null ? Number(p.get("por_pagina")) : 50;
  const items = porPagina > 0 ? filtrados.slice((pagina - 1) * porPagina, pagina * porPagina) : filtrados;
  return respuestaJson({ total: filtrados.length, pagina, por_pagina: porPagina, items });
}

// Red primero; si falla, la copia guardada. Las respuestas buenas se guardan.
async function redPrimero(request, nombreCache, evento) {
  const cache = await caches.open(nombreCache);
  const clave = claveDatos(request.url);
  // Se guarda cuando llegue, aunque sea después del tiempo límite: la próxima
  // vez sin red ya estará.
  const red = fetch(request).then((res) => {
    if (res.ok) cache.put(clave, res.clone());
    return res;
  });
  evento?.waitUntil(red.catch(() => {}));
  try {
    return await conTiempoLimite(red, request.headers.has(CABECERA_DESCARGA) ? ESPERA_DESCARGA_MS : ESPERA_RED_MS);
  } catch (err) {
    avisarSinConexion();
    const guardada = await cache.match(clave);
    if (guardada) return guardada;
    const armada = await estudiantesSinRed(new URL(request.url), cache).catch(() => null);
    if (armada) return armada;
    return new Response(JSON.stringify({ detail: "Sin conexión y este dato no está guardado en el celular." }), {
      status: 503,
      headers: { "Content-Type": "application/json", "X-Sin-Conexion": "1" },
    });
  }
}

// Copia guardada primero (las fotos no cambian para un mismo id).
async function guardadaPrimero(request, nombreCache) {
  const cache = await caches.open(nombreCache);
  const guardada = await cache.match(request, { ignoreSearch: false });
  if (guardada) return guardada;
  try {
    const res = await fetch(request);
    if (res.ok) cache.put(request, res.clone());
    return res;
  } catch {
    avisarSinConexion();
    // La miniatura de una FOTO es el mismo archivo que /archivo: la descarga
    // «sin wifi» solo guarda /archivo (no baja cada foto dos veces).
    const url = new URL(request.url);
    if (url.pathname.endsWith("/miniatura")) {
      const completa = await cache.match(url.pathname.replace(/\/miniatura$/, "/archivo"));
      if (completa && (completa.headers.get("content-type") || "").startsWith("image/")) return completa;
    }
    return new Response("", { status: 503, headers: { "X-Sin-Conexion": "1" } });
  }
}

// La app: copia guardada al instante y, por detrás, se actualiza.
async function appGuardadaYActualizar(request) {
  const cache = await caches.open(CACHE_APP);
  const guardada = await cache.match(request);
  const deRed = fetch(request)
    .then((res) => {
      if (res.ok) cache.put(request, res.clone());
      return res;
    })
    .catch(() => null);
  return guardada || (await deRed) || new Response("", { status: 503 });
}

self.addEventListener("fetch", (evento) => {
  const { request } = evento;
  if (request.method !== "GET") return; // subidas, login, etc.: directo a la red
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Descargas que se generan al momento (PDF/Word de reportes, listas,
  // constancias): directo a la red, sin tiempo límite. Un PDF de muchas
  // hojas tarda más de ESPERA_RED_MS y quedaba como «Sin conexión». Las fotos
  // de los documentos (/api/fotos/...) sí siguen guardándose, más abajo.
  if (
    url.pathname.startsWith("/api/") && !url.pathname.startsWith("/api/fotos/") &&
    (request.mode === "navigate" || /(\/pdf|\.pdf|\.docx|\/archivo|\/descargar\/[^/]+)$/.test(url.pathname))
  ) {
    return;
  }

  // Abrir la app: red primero (para no quedarse con un index.html viejo),
  // la copia guardada si no hay red.
  if (request.mode === "navigate") {
    evento.respondWith(
      (async () => {
        const cache = await caches.open(CACHE_APP);
        try {
          const res = await conTiempoLimite(fetch(request), ESPERA_RED_MS);
          if (res.ok && url.pathname === "/") cache.put("/", res.clone());
          return res;
        } catch {
          return (await cache.match("/")) || new Response("Sin conexión", { status: 503 });
        }
      })()
    );
    return;
  }

  if (url.pathname.startsWith("/static/") || url.pathname === "/manifest.webmanifest") {
    evento.respondWith(appGuardadaYActualizar(request));
    return;
  }

  if (/^\/api\/fotos\/\d+\/(archivo|miniatura)$/.test(url.pathname)) {
    evento.respondWith(guardadaPrimero(request, CACHE_DOCUMENTOS));
    return;
  }

  if (url.pathname.startsWith("/api/")) {
    // De /api/auth solo /yo (para poder abrir la app sin red con la última
    // sesión conocida); refresh/login/logout nunca se guardan.
    if (url.pathname.startsWith("/api/auth/") && url.pathname !== "/api/auth/yo") return;
    evento.respondWith(redPrimero(request, CACHE_DATOS, evento));
  }
});
