// --- Utilidades compartidas por todas las pantallas (el panel administrativo ---
// --- y, más adelante, la app docente). Se carga ANTES que core.js. Sin estado ---
// --- de vistas: solo la llamada a la API y funciones puras.                  ---

const ZONA_COLOMBIA = "America/Bogota";

const _formatoFechaColombia = new Intl.DateTimeFormat("en-CA", {
  timeZone: ZONA_COLOMBIA,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

// Fecha de calendario "YYYY-MM-DD" en Colombia para un instante (por defecto,
// ahora), sin importar la zona configurada en el equipo o el celular.
// No usar new Date().toISOString().slice(0, 10): esa es la fecha en UTC, que
// desde las 7:00 p. m. de Colombia ya es el día siguiente.
function fechaColombiaISO(instante = new Date()) {
  const partes = Object.fromEntries(
    _formatoFechaColombia.formatToParts(instante).map((p) => [p.type, p.value])
  );
  return `${partes.year}-${partes.month}-${partes.day}`;
}

// Convierte un instante que devuelve la API ("2026-09-17T16:56:08.849073") en
// un Date. El backend guarda y envía los instantes en UTC SIN zona (ver
// fechas.ahora_utc), y JavaScript interpreta una fecha-hora sin sufijo como
// hora LOCAL: en Colombia eso la corre 5 horas hacia adelante. Es el mismo
// error que ya costó las fechas de ficha.js en Fase 1, al revés.
// Devuelve null si el texto no sirve, para que quien llame decida qué hacer.
function instanteUtcDesdeApi(texto) {
  if (!texto) return null;
  // Si ya trae zona ("Z" o "+05:00"), se respeta tal cual.
  const conZona = /(?:Z|[+-]\d{2}:?\d{2})$/.test(texto);
  const fecha = new Date(conZona ? texto : `${texto}Z`);
  return Number.isNaN(fecha.getTime()) ? null : fecha;
}

// Escapa texto para interpolarlo en HTML (innerHTML / plantillas). Todo texto
// escrito por usuarios o traído de importaciones debe pasar por aquí.
function esc(valor) {
  return String(valor ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function api(path, opciones = {}) {
  // Fase 4A': si al token de acceso le queda poco, se renueva ANTES de salir
  // (ver asegurarSesionFresca en auth.js). El 401 de más abajo se conserva
  // como red de seguridad — esto solo evita llegar a él.
  await asegurarSesionFresca();

  let res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opciones,
  });

  // Fase 4.0: si el token de acceso venció (15 min), se intenta UN refresh
  // silencioso y se reintenta la petición original UNA sola vez. _intentarRefresh
  // (en auth.js) comparte una única promesa entre refrescos concurrentes, así
  // que varias llamadas a api() casi simultáneas no disparan varios /refresh.
  // Si el refresh falla, se fuerza la vuelta a la pantalla de login (ver
  // _sesionExpirada en auth.js) y no se reintenta una segunda vez: nunca hay
  // más de un ciclo 401 -> refresh -> reintento por petición.
  if (res.status === 401) {
    const refrescado = await _intentarRefresh();
    if (refrescado) {
      res = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...opciones,
      });
    }
    if (!refrescado || res.status === 401) {
      _sesionExpirada();
      const error = new Error("Tu sesión expiró. Vuelve a iniciar sesión.");
      error.status = 401;
      throw error;
    }
  }

  if (!res.ok) {
    const cuerpo = await res.json().catch(() => ({}));
    const error = new Error(cuerpo.detail || `Error ${res.status} en ${path}`);
    error.status = res.status;
    throw error;
  }
  if (res.status === 204) return null;
  return res.json();
}

// --- Íconos (Lucide, vendor/lucide.min.js) --------------------------------------
// La interfaz usa íconos de línea en vez de emojis. Cualquier
// <i data-lucide="nombre"></i> que llegue al DOM (por innerHTML en cualquier
// pantalla) se convierte solo en su <svg>: un MutationObserver lo detecta y
// llama a lucide.createIcons() una vez por cuadro. Así ninguna vista tiene que
// acordarse de "pintar los íconos" después de renderizar.
// Nombres: https://lucide.dev/icons (kebab-case, ej. "triangle-alert").

function icono(nombre, clase) {
  return `<i data-lucide="${nombre}" class="ico${clase ? " " + clase : ""}" aria-hidden="true"></i>`;
}

// Punto de estado (verde/amarillo/rojo/gris/naranja/azul) — reemplaza a los
// círculos de color emoji; se dibuja con CSS (.punto-*).
function puntoEstado(tono, titulo) {
  return `<span class="punto punto-${tono}"${titulo ? ` title="${esc(titulo)}"` : ""} aria-hidden="true"></span>`;
}

let _iconosPendientes = false;
function _pintarIconos() {
  _iconosPendientes = false;
  if (typeof lucide !== "undefined" && document.querySelector("i[data-lucide]")) {
    lucide.createIcons({ attrs: { "stroke-width": 2 } });
  }
}
if (typeof MutationObserver !== "undefined") {
  new MutationObserver(() => {
    if (_iconosPendientes) return;
    _iconosPendientes = true;
    requestAnimationFrame(_pintarIconos);
  }).observe(document.documentElement, { childList: true, subtree: true });
}
document.addEventListener("DOMContentLoaded", _pintarIconos);
