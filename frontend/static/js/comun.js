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
