// --- Fase 4.0: autenticación del frontend -----------------------------------
// Se carga justo después de comun.js (que trae api()) y antes de core.js y
// de las vistas. No protege NADA todavía del lado del backend (eso es Fase
// 4B) — esto solo evita que la interfaz se muestre sin sesión, mantiene la
// cookie de acceso renovada y adapta la sidebar por UX.
//
// Estado de sesión SOLO en memoria: nunca localStorage/sessionStorage. Las
// cookies de sesión son httpOnly (el backend las pone y las lee; este
// archivo jamás las toca) — sesionActual es una copia en memoria de lo que
// devuelve /api/auth/yo, para pintar la interfaz (nombre, rol, permisos).

let sesionActual = null; // { usuario: {..., roles, permisos, debe_cambiar_clave}, sesion, expira_acceso_en } | null

let _refrescoEnCurso = null; // promesa compartida: evita varios POST /refresh a la vez

const _PANTALLAS_AUTH = ["pantalla-carga", "pantalla-sin-conexion", "pantalla-login", "pantalla-cambiar-clave"];
const CLAVE_DISPOSITIVO = "ietaba_dispositivo_id"; // no es un token: solo un UUID opaco del equipo

// --- Identificación del equipo (para "confiar en este equipo") -------------
// No es sensible y no son "roles/permisos" ni un token de sesión: es el
// mismo dispositivo_id opaco que ya espera schemas.LoginSolicitud.

function _generarUuid() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  // crypto.randomUUID exige contexto seguro (https o localhost); si el
  // colegio sirve la app por http en la red local, no está disponible.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function idDispositivo() {
  try {
    let id = localStorage.getItem(CLAVE_DISPOSITIVO);
    if (!id) {
      id = _generarUuid();
      localStorage.setItem(CLAVE_DISPOSITIVO, id);
    }
    return id;
  } catch {
    return null; // almacenamiento no disponible (modo privado, etc.): no es crítico
  }
}

function nombreDispositivo() {
  const ua = navigator.userAgent || "";
  const navegador = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "Navegador";
  return `${navegador} · ${navigator.platform || ""}`.trim();
}

// --- fetch crudo (sin pasar por api()): lo usan login/refresh/logout/yo/
// cambiar-clave, precisamente para que NUNCA entren al interceptor de 401
// de comun.js (si no, un refresh fallido podría disparar otro refresh). ----

async function _fetchCrudo(path, opciones = {}) {
  return fetch(path, { headers: { "Content-Type": "application/json" }, ...opciones });
}

// Intenta renovar la sesión con la cookie de renovación. true si quedó con
// sesión válida. Comparte una única promesa entre llamadas concurrentes.
async function _intentarRefresh() {
  if (_refrescoEnCurso) return _refrescoEnCurso;
  _refrescoEnCurso = (async () => {
    try {
      const res = await _fetchCrudo("/api/auth/refresh", { method: "POST" });
      if (!res.ok) return false;
      // Fase 4A': antes el cuerpo se descartaba. Trae el expira_acceso_en
      // nuevo, y sin él asegurarSesionFresca() seguiría creyendo que la
      // cookie está por vencer y refrescaría en cada llamada.
      const sesion = await res.json().catch(() => null);
      if (sesion) {
        if (sesionActual) {
          sesionActual.expira_acceso_en = sesion.expira_acceso_en;
          sesionActual.sesion = sesion.sesion;
        } else {
          // Refresh durante el arranque (iniciarApp aún no tiene sesión):
          // _obtenerYo la reemplaza enseguida por la versión definitiva.
          sesionActual = sesion;
        }
      }
      return true;
    } catch {
      return false; // sin red: se trata igual que un refresh fallido
    } finally {
      _refrescoEnCurso = null;
    }
  })();
  return _refrescoEnCurso;
}

// --- Fase 4A': mantener viva la cookie de acceso ----------------------------
// El token de acceso dura 15 minutos. Hasta ahora solo se renovaba al recibir
// un 401, pero en modo observación NINGUNA ruta devuelve 401: pasados esos 15
// minutos, cada petición llegaba al servidor sin identidad y quedaba
// registrada como "sin sesión" aunque la persona sí estuviera dentro (42 % de
// las observaciones). Y hay peticiones que nunca podrían aprovechar ese 401:
// las descargas por navegación, las imágenes de documentos escaneados y los
// <a href> — ahí no hay JavaScript que pueda interceptar nada.
//
// La solución es no llegar nunca a que venza: se renueva ANTES, tanto por
// temporizador como justo antes de cada petición.

const MARGEN_REFRESCO_MS = 6 * 60 * 1000;  // renovar cuando queden 6 min o menos
const INTERVALO_KEEPALIVE_MS = 5 * 60 * 1000;  // revisar cada 5 min
// El intervalo DEBE ser menor que el margen: si no, una revisión podría
// saltarse la ventana y encontrar la cookie ya vencida. 5 < 6 < 15.

let _temporizadorKeepAlive = null;

function _accesoPorVencer() {
  const vence = instanteUtcDesdeApi(sesionActual?.expira_acceso_en);
  if (vence === null) return false; // sin dato fiable, no forzar un refresh
  return vence.getTime() - Date.now() <= MARGEN_REFRESCO_MS;
}

// Renueva el token de acceso si está por vencer. Devuelve true si al salir
// hay sesión utilizable. La usan api() (comun.js), las subidas con FormData y
// las descargas por navegación, que no pasan por api().
async function asegurarSesionFresca() {
  if (!sesionActual) return false; // sin sesión no hay nada que refrescar
  if (!_accesoPorVencer()) return true;
  return _intentarRefresh();
}

function _arrancarKeepAlive() {
  _detenerKeepAlive();
  _temporizadorKeepAlive = setInterval(() => {
    // Con la pestaña oculta el navegador frena los temporizadores y no vale
    // la pena gastar peticiones: al volver a mostrarse se revisa enseguida
    // (ver el listener de visibilitychange).
    if (document.visibilityState === "visible") asegurarSesionFresca();
  }, INTERVALO_KEEPALIVE_MS);
}

function _detenerKeepAlive() {
  if (_temporizadorKeepAlive !== null) {
    clearInterval(_temporizadorKeepAlive);
    _temporizadorKeepAlive = null;
  }
}

// GET /api/auth/yo con UN refresh-si-hace-falta (mismo mecanismo que usará
// api() más adelante para cualquier otra ruta). Devuelve la sesión, o null
// si de verdad no hay sesión (incluso después de intentar refrescar).
// Deja pasar sin atrapar cualquier error de red/servidor (lo maneja quien
// llama, para distinguir "no hay sesión" de "no hay servidor").
async function _obtenerYo() {
  let res = await _fetchCrudo("/api/auth/yo");
  if (res.status === 401) {
    const refrescado = await _intentarRefresh();
    if (!refrescado) return null;
    res = await _fetchCrudo("/api/auth/yo");
    if (res.status === 401) return null;
  }
  if (!res.ok) throw new Error(`Error ${res.status} consultando la sesión`);
  return res.json();
}

// --- Pantallas ---------------------------------------------------------------

function _mostrarPantalla(id) {
  _PANTALLAS_AUTH.forEach((otro) => {
    document.getElementById(otro).hidden = otro !== id;
  });
  document.querySelector(".app-shell").hidden = true;
}

function _mostrarApp() {
  _PANTALLAS_AUTH.forEach((id) => {
    document.getElementById(id).hidden = true;
  });
  document.querySelector(".app-shell").hidden = false;
}

// --- UX por permisos (NUNCA seguridad: el backend es quien decide de verdad,
// a partir de Fase 4B) -------------------------------------------------------

// Módulos que el administrador puede apagar (GET /api/sistema/modulos; ver
// backend/app/configuracion.py). Si no se pudo consultar, se asume encendido.
let modulosSistema = { orientacion: true };

async function cargarModulosSistema() {
  try {
    modulosSistema = await api("/api/sistema/modulos");
  } catch {
    modulosSistema = { orientacion: true };
  }
}

function _aplicarVisibilidadPorPermisos(permisos) {
  const lista = permisos || [];
  document.querySelectorAll("[data-permiso]").forEach((el) => {
    const moduloApagado = el.dataset.vista === "orientacion" && modulosSistema.orientacion === false;
    // Docencia trabaja sobre las asignaciones del docente enlazado: sin
    // enlace (p. ej. el Administrador, que tiene todos los permisos) solo
    // daría "Tu usuario no está vinculado a un docente".
    const sinDocente = "requiereDocente" in el.dataset && !sesionActual?.usuario?.docente_id;
    el.hidden = !lista.includes(el.dataset.permiso) || moduloApagado || sinDocente;
  });
  // Un grupo del menú (ej. "Gestión") sin NINGÚN botón visible (ni siquiera
  // un "Próximamente") se oculta completo, para no dejar un título suelto
  // sin nada debajo.
  document.querySelectorAll(".nav-grupo").forEach((grupo) => {
    const algunoVisible = Array.from(grupo.querySelectorAll(".tab, .tab-proximamente")).some((el) => !el.hidden);
    grupo.hidden = !algunoVisible;
  });
}

function _actualizarCuentaUsuario(usuario) {
  document.getElementById("cuenta-usuario-nombre").textContent = usuario.nombre;
  document.getElementById("cuenta-usuario-rol").textContent = (usuario.roles || []).join(", ") || "Sin rol asignado";
}

// --- Arranque y transiciones de sesión ---------------------------------------

async function _continuarConSesion(sesion) {
  sesionActual = sesion;
  if (sesion.usuario.debe_cambiar_clave) {
    _mostrarPantalla("pantalla-cambiar-clave");
    return;
  }
  _actualizarCuentaUsuario(sesion.usuario);
  await cargarModulosSistema();
  _aplicarVisibilidadPorPermisos(sesion.usuario.permisos);
  _mostrarApp();
  _arrancarKeepAlive(); // Fase 4A': que la cookie de acceso no venza en uso
  // Uso sin conexión (sin_conexion.js): borra lo guardado si entró otra
  // persona en este celular y sube lo que haya quedado en cola.
  if (typeof sinConexionAlIniciarSesion === "function") sinConexionAlIniciarSesion(sesion.usuario);
  // main.js define iniciarNavegacion(): aplica los parámetros de la URL y
  // llama a render() — exactamente la misma lógica que ya existía, solo que
  // ahora se ejecuta después de confirmar la sesión en vez de al cargar el
  // script.
  if (typeof iniciarNavegacion === "function") iniciarNavegacion();
}

function _sesionExpirada() {
  _detenerKeepAlive();
  sesionActual = null;
  resetearEstadoNavegacion();
  document.getElementById("login-error").hidden = true;
  document.getElementById("login-aviso-sesion").hidden = false;
  _mostrarPantalla("pantalla-login");
}

async function iniciarApp() {
  _mostrarPantalla("pantalla-carga");
  let yo;
  try {
    yo = await _obtenerYo();
  } catch {
    _mostrarPantalla("pantalla-sin-conexion");
    return;
  }
  if (yo === null) {
    document.getElementById("login-aviso-sesion").hidden = true;
    _mostrarPantalla("pantalla-login");
    return;
  }
  await _continuarConSesion(yo);
}

// --- Formularios ---------------------------------------------------------------

async function _manejarSubmitLogin(evento) {
  evento.preventDefault();
  const form = evento.target;
  const datos = Object.fromEntries(new FormData(form));
  const errorBox = document.getElementById("login-error");
  errorBox.hidden = true;
  document.getElementById("login-aviso-sesion").hidden = true;
  const boton = form.querySelector("button[type=submit]");
  boton.disabled = true;
  try {
    const res = await _fetchCrudo("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        usuario: datos.usuario,
        clave: datos.clave,
        confiar_en_dispositivo: !!datos.confiar_en_dispositivo,
        dispositivo_id: idDispositivo(),
        nombre_dispositivo: nombreDispositivo(),
      }),
    });
    if (!res.ok) {
      const cuerpo = await res.json().catch(() => ({}));
      errorBox.textContent = cuerpo.detail || `Error ${res.status} al iniciar sesión`;
      errorBox.hidden = false;
      return;
    }
    const sesion = await res.json();
    form.reset();
    await _continuarConSesion(sesion);
  } catch {
    errorBox.textContent = "No se pudo conectar con el servidor.";
    errorBox.hidden = false;
  } finally {
    boton.disabled = false;
  }
}

async function _manejarSubmitCambiarClave(evento) {
  evento.preventDefault();
  const form = evento.target;
  const datos = Object.fromEntries(new FormData(form));
  const errorBox = document.getElementById("cambiar-clave-error");
  errorBox.hidden = true;

  if (datos.clave_nueva !== datos.clave_nueva_repetir) {
    errorBox.textContent = "Las contraseñas nuevas no coinciden.";
    errorBox.hidden = false;
    return;
  }

  const boton = form.querySelector("button[type=submit]");
  boton.disabled = true;
  try {
    const res = await _fetchCrudo("/api/auth/cambiar-clave", {
      method: "POST",
      body: JSON.stringify({ clave_actual: datos.clave_actual, clave_nueva: datos.clave_nueva }),
    });
    if (!res.ok) {
      const cuerpo = await res.json().catch(() => ({}));
      errorBox.textContent = cuerpo.detail || `Error ${res.status} al cambiar la contraseña`;
      errorBox.hidden = false;
      return;
    }
    form.reset();
    // cambiar-clave revoca las OTRAS sesiones pero conserva la actual (backend,
    // ver auth.cambiar_clave con sesion_actual_id): /yo debe responder directo,
    // sin pedir login de nuevo.
    const yo = await _obtenerYo();
    if (yo === null) {
      _mostrarPantalla("pantalla-login");
      return;
    }
    await _continuarConSesion(yo);
  } catch {
    errorBox.textContent = "No se pudo conectar con el servidor.";
    errorBox.hidden = false;
  } finally {
    boton.disabled = false;
  }
}

async function _manejarLogout() {
  // Avisa si hay documentos sin subir y borra del celular lo guardado para
  // usar sin wifi (fichas y fotos de estudiantes): no debe quedar para la
  // próxima persona que use este equipo.
  if (typeof sinConexionAntesDeCerrarSesion === "function" && !(await sinConexionAntesDeCerrarSesion())) return;
  try {
    await _fetchCrudo("/api/auth/logout", { method: "POST" });
  } catch {
    // Si no hay red, igual se cierra del lado del cliente: no tiene sentido
    // dejar a alguien "atrapado" en la app porque el logout no pudo avisar
    // al servidor.
  }
  _detenerKeepAlive();
  sesionActual = null;
  resetearEstadoNavegacion();
  document.getElementById("login-aviso-sesion").hidden = true;
  _mostrarPantalla("pantalla-login");
}

// --- Listeners (los elementos ya existen: los scripts van al final del body) -

document.getElementById("form-login").addEventListener("submit", _manejarSubmitLogin);
document.getElementById("form-cambiar-clave").addEventListener("submit", _manejarSubmitCambiarClave);
document.getElementById("btn-logout").addEventListener("click", _manejarLogout);
document.getElementById("btn-reintentar-conexion").addEventListener("click", iniciarApp);

// Fase 4A': al volver a una pestaña que estuvo oculta (portátil cerrado, otra
// pestaña al frente), el navegador tuvo frenado el temporizador y la cookie
// pudo vencerse mientras tanto. Se revisa de inmediato, antes de que la
// persona alcance a hacer clic en nada.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") asegurarSesionFresca();
});
