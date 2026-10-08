// --- Vista: Horarios --------------------------------------------------------
// Central de coordinación académica de la Sede #01: qué pasa hoy, quién está
// libre, consulta por docente / grupo / día, planificación, análisis y reportes.
//
// Este archivo tiene el ARMAZÓN (encabezado, buscador, navegación, caché y
// componentes compartidos) y la sección OPERACIÓN (Hoy, Disponibilidad,
// Reemplazos, Conflictos). Las demás secciones (Docente, Grupo, Día, Abrir
// hueco, Resumen, Horas libres, Reporte Word) viven en horario_consulta.js.
// Ninguna cambia la lógica académica: todo sale de los mismos endpoints de
// /api/horario/*.

// Cada grupo es una pestaña primaria; sus secciones van en una segunda fila
// (solo si el grupo tiene más de una). El orden es el de uso: lo operativo del
// día primero, lo que se consulta después, y al final planificar y reportar.
const GRUPOS_HORARIO = [
  { id: "operacion", label: "Operación", detalle: "Lo que pasa hoy" },
  { id: "consultar", label: "Consultar", detalle: "Docente, grupo o día" },
  { id: "planificar", label: "Planificar", detalle: "Dónde colocar una clase" },
  { id: "analisis", label: "Análisis", detalle: "Cargas y disponibilidad" },
  { id: "reportes", label: "Reportes", detalle: "Documentos oficiales" },
];

const SECCIONES_HORARIO = [
  { grupo: "operacion", id: "hoy", label: "Hoy" },
  { grupo: "operacion", id: "libres", label: "Disponibilidad" },
  { grupo: "operacion", id: "reemplazos", label: "Reemplazos" },
  { grupo: "operacion", id: "conflictos", label: "Conflictos" },
  { grupo: "consultar", id: "docente", label: "Docente" },
  { grupo: "consultar", id: "grupo", label: "Grupo" },
  { grupo: "consultar", id: "dia", label: "Día" },
  { grupo: "planificar", id: "asignar", label: "Abrir hueco" },
  { grupo: "analisis", id: "general", label: "Resumen" },
  { grupo: "analisis", id: "horaslibres", label: "Horas libres" },
  { grupo: "reportes", id: "reporte", label: "Reporte Word" },
];

const DIAS_HORARIO = [
  [1, "Lunes"], [2, "Martes"], [3, "Miércoles"], [4, "Jueves"], [5, "Viernes"],
];

const FRANJAS_HORARIO = [
  { hora: 1, inicio: "7:30", fin: "8:25" },
  { hora: 2, inicio: "8:25", fin: "9:20" },
  { hora: 3, inicio: "9:20", fin: "10:15" },
  { hora: 4, inicio: "11:00", fin: "11:50" },
  { hora: 5, inicio: "11:50", fin: "12:40" },
  { hora: 6, inicio: "12:40", fin: "13:30" },
];

const ESTADO_HORARIO = {
  libre: { emoji: "<span class=punto-verde></span>", texto: "Libre", clase: "est-libre" },
  en_clase: { emoji: "<span class=punto-azul></span>", texto: "En clase", clase: "est-clase" },
  descanso: { emoji: "<span class=punto-amarillo></span>", texto: "Descanso", clase: "est-descanso" },
  fuera_jornada: { emoji: "<span class=punto-gris></span>", texto: "Fuera de jornada", clase: "est-fuera" },
  ausente: { emoji: "<span class=punto-rojo></span>", texto: "Ausente", clase: "est-ausente" },
  cubriendo: { emoji: "<span class=punto-naranja></span>", texto: "Cubriendo reemplazo", clase: "est-cubriendo" },
};

// --- Estado del módulo (los nombres se conservan: main.js los usa para los
// --- enlaces directos ?vista=horario&sub=...&fecha=...&docente=...) ---------
let horarioSub = "hoy";
let horarioAnio = new Date().getFullYear();
let horarioDocenteId = null;
let horarioGrupoSel = null; // {grado, curso}
let horarioDiaSel = new Date().getDay() >= 1 && new Date().getDay() <= 5 ? new Date().getDay() : 1;
let horarioRelojTimer = null;
let horarioAsignarSel = null; // {docenteId, docenteTexto, grado, curso, areaId, horas}
let horarioConflictosN = 0;
let horarioLibresNivel = ""; // "" | "primaria" | "secundaria"
let horarioFecha = fechaColombiaISO();
let busquedaHorarioSeq = 0;

// --- Utilidades ---------------------------------------------------------------

function fechaHoyISO() {
  return fechaColombiaISO();
}

function sumarDiasISO(iso, n) {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d + n);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
}

function diaSemanaISO(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).getDay(); // 0 = domingo … 6 = sábado
}

// Día de clases más cercano en una dirección (para saltar fines de semana).
function diaHabilCercano(iso, dir) {
  let f = sumarDiasISO(iso, dir);
  for (let i = 0; i < 7 && (diaSemanaISO(f) === 0 || diaSemanaISO(f) === 6); i++) f = sumarDiasISO(f, dir);
  return f;
}

function fechaLargaHorario(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const t = new Date(y, m - 1, d).toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return t.charAt(0).toUpperCase() + t.slice(1);
}

function fechaCortaHorario(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("es-CO", { weekday: "short", day: "numeric", month: "short" }).replace(".", "");
}

function nombreDiaHorario(dia) {
  return (DIAS_HORARIO.find(([n]) => n === dia) || [0, "—"])[1];
}

// [1,2] -> "1ª–2ª" · [3] -> "3ª"
function rangoHoras(horas) {
  if (!horas || !horas.length) return "";
  return horas.length === 1 ? `${horas[0]}ª` : `${horas[0]}ª–${horas[horas.length - 1]}ª`;
}

function etiquetaGrupoHorario(grado, curso) {
  return curso ? `${grado}-${curso}` : String(grado);
}

// Primaria = Preescolar + 1° a 5° (grado 0-5). Secundaria/media = 6° a 11°.
function nivelDeGrado(grado) {
  return grado <= 5 ? "primaria" : "secundaria";
}

// "SUSANA BEATRIZ BISBICUS CANTICUS" -> "Susana Bisbicus": nombre + primer apellido.
function nombreCortoHorario(nombre) {
  const p = String(nombre || "").trim().split(/\s+/).filter(Boolean);
  const bonito = (s) => s.charAt(0) + s.slice(1).toLowerCase();
  if (p.length >= 4) return `${bonito(p[0])} ${bonito(p[2])}`;
  if (p.length === 3) return `${bonito(p[0])} ${bonito(p[1])}`;
  return p.map(bonito).join(" ");
}

const puedeGestionarHorario = () => tienePermiso("horario.gestionar");
const puedeExportarHorario = () => tienePermiso("horario.exportar");

// --- Caché del módulo -----------------------------------------------------------
// Docentes, áreas, la rejilla completa del año y los conflictos se pedían una
// y otra vez al cambiar de sección. Ahora se piden una vez y se invalidan solo
// cuando algo cambia (resolver un conflicto, asignar una clase, cambiar el año).
const hzCache = { docentes: null, areas: null, bloques: {}, conflictos: {} };

const hzDocentes = async () => (hzCache.docentes ||= await api("/api/docentes"));
const hzAreas = async () => (hzCache.areas ||= await api("/api/areas"));
const hzBloques = async () =>
  (hzCache.bloques[horarioAnio] ||= await api(`/api/horario/bloques?anio_lectivo=${horarioAnio}`));
async function hzConflictos(fresco = false) {
  if (fresco || !hzCache.conflictos[horarioAnio]) {
    hzCache.conflictos[horarioAnio] = await api(`/api/horario/conflictos?anio_lectivo=${horarioAnio}`);
  }
  horarioConflictosN = hzCache.conflictos[horarioAnio].length;
  return hzCache.conflictos[horarioAnio];
}
function hzInvalidar(...que) {
  que.forEach((k) => {
    if (k === "bloques") hzCache.bloques = {};
    else if (k === "conflictos") hzCache.conflictos = {};
    else hzCache[k] = null;
  });
}

// --- Componentes compartidos ------------------------------------------------------

const hzIcono = { ok: "<i data-lucide=check class=ico></i> ", warn: "<i data-lucide=triangle-alert class=ico></i> ", error: "<i data-lucide=x class=ico></i> ", info: "<i data-lucide=info class=ico></i> " };

// Aviso discreto, no bloqueante. Sustituye a alert(); los errores duran más.
function horarioNotificar(mensaje, tipo = "ok") {
  let zona = document.getElementById("horario-avisos");
  if (!zona) {
    zona = document.createElement("div");
    zona.id = "horario-avisos";
    zona.className = "horario-avisos no-imprimir";
    zona.setAttribute("aria-live", "polite");
    document.body.appendChild(zona);
  }
  const aviso = document.createElement("div");
  aviso.className = `horario-aviso ${tipo}`;
  aviso.innerHTML = `<span class="horario-aviso-icono" aria-hidden="true">${hzIcono[tipo] || hzIcono.info}</span><span>${esc(mensaje)}</span>`;
  zona.appendChild(aviso);
  setTimeout(() => aviso.remove(), tipo === "ok" ? 4200 : 7000);
}

// Diálogo de confirmación dentro de la página (sustituye a confirm()).
function hzConfirmar({ titulo, texto = "", confirmar = "Confirmar", cancelar = "Cancelar", peligro = false }) {
  return new Promise((resolver) => {
    const fondo = document.createElement("div");
    fondo.className = "modal-fondo hz-confirmar no-imprimir";
    fondo.innerHTML = `
      <div class="modal-caja hz-confirmar-caja" role="alertdialog" aria-modal="true" aria-label="${esc(titulo)}">
        <h3>${esc(titulo)}</h3>
        ${texto ? `<p>${texto}</p>` : ""}
        <div class="modal-acciones">
          <button type="button" class="boton secundario" data-no>${esc(cancelar)}</button>
          <button type="button" class="boton ${peligro ? "boton-peligro" : ""}" data-si>${esc(confirmar)}</button>
        </div>
      </div>`;
    const cerrar = (valor) => {
      document.removeEventListener("keydown", teclas, true);
      fondo.remove();
      resolver(valor);
    };
    const teclas = (ev) => {
      if (ev.key === "Escape") { ev.stopPropagation(); cerrar(false); }
    };
    document.addEventListener("keydown", teclas, true);
    fondo.addEventListener("click", (ev) => { if (ev.target === fondo) cerrar(false); });
    fondo.querySelector("[data-no]").addEventListener("click", () => cerrar(false));
    fondo.querySelector("[data-si]").addEventListener("click", () => cerrar(true));
    document.body.appendChild(fondo);
    fondo.querySelector("[data-si]").focus();
  });
}

// Estado vacío compacto: qué pasa y, si tiene sentido, qué puede hacer.
function hzVacio({ icono = "<i data-lucide=info class=ico></i> ", titulo, texto = "", acciones = [], tono = "" }) {
  return `
    <div class="hz-vacio ${tono}">
      <span class="hz-vacio-icono" aria-hidden="true">${icono}</span>
      <div class="hz-vacio-cuerpo">
        <strong>${titulo}</strong>
        ${texto ? `<span>${texto}</span>` : ""}
        ${acciones.length ? `<div class="hz-vacio-acciones">${acciones
          .map((a) => `<button type="button" class="boton ${a.primaria ? "" : "secundario"} boton-chico" data-hz-accion="${a.id}">${a.texto}</button>`)
          .join("")}</div>` : ""}
      </div>
    </div>`;
}

function hzVincularAcciones(scope, mapa) {
  scope.querySelectorAll("[data-hz-accion]").forEach((b) => {
    const fn = mapa[b.dataset.hzAccion];
    if (fn) b.addEventListener("click", fn);
  });
}

const hzCargando = (texto = "Cargando…") =>
  `<div class="hz-cargando" role="status"><span class="hz-spinner" aria-hidden="true"></span>${texto}</div>`;

function hzError(e) {
  return `<div class="hz-vacio error">
    <span class="hz-vacio-icono" aria-hidden="true"><i data-lucide=triangle-alert class=ico></i> </span>
    <div class="hz-vacio-cuerpo"><strong>No se pudo cargar esta sección</strong><span>${esc(e.message || e)}</span>
      <div class="hz-vacio-acciones"><button type="button" class="boton secundario boton-chico" data-hz-accion="reintentar">Reintentar</button></div>
    </div></div>`;
}

// Título de sección con su descripción y, a la derecha, sus acciones.
function hzTitulo(titulo, descripcion = "", acciones = "") {
  return `
    <div class="hz-titulo-seccion no-imprimir">
      <div><h2>${titulo}</h2>${descripcion ? `<p>${descripcion}</p>` : ""}</div>
      ${acciones ? `<div class="hz-titulo-acciones">${acciones}</div>` : ""}
    </div>`;
}

// Indicadores: tono ok (verde) · alerta (rojo) · aviso (amarillo) · vacío (gris).
function hzKpi({ n, txt, sub = "", tono = "", accion = "", titulo = "" }) {
  const cuerpo = `<span class="hz-kpi-num">${n}</span><span class="hz-kpi-txt">${txt}</span>${sub ? `<span class="hz-kpi-sub">${sub}</span>` : ""}`;
  return accion
    ? `<button type="button" class="hz-kpi hz-kpi-boton ${tono}" data-hz-ir="${accion}" title="${esc(titulo)}">${cuerpo}</button>`
    : `<div class="hz-kpi ${tono}">${cuerpo}</div>`;
}

// Control segmentado (mismo lenguaje que Usuarios/Sedes).
function hzSegmentado(id, opciones, valor) {
  return `<div class="segmentado" role="group" data-hz-seg="${id}">${opciones
    .map((o) => `<button type="button" class="segmentado-btn ${String(o.v) === String(valor) ? "activo" : ""}" data-v="${o.v}">${o.t}${o.n != null ? ` <span class="segmentado-num">${o.n}</span>` : ""}</button>`)
    .join("")}</div>`;
}
function hzVincularSeg(scope, id, alCambiar) {
  const caja = scope.querySelector(`[data-hz-seg="${id}"]`);
  caja?.addEventListener("click", (e) => {
    const b = e.target.closest(".segmentado-btn");
    if (!b) return;
    caja.querySelectorAll(".segmentado-btn").forEach((x) => x.classList.toggle("activo", x === b));
    alCambiar(b.dataset.v);
  });
}

// Navegación por fecha (Hoy, Reemplazos): ‹ fecha › + "Ir a hoy".
function hzFechaNavHtml(id, fecha) {
  const esHoy = fecha === fechaHoyISO();
  return `
    <div class="fecha-nav hz-fecha-nav">
      <button type="button" class="boton-icono" data-fecha-paso="-1" title="Día anterior" aria-label="Día anterior">‹</button>
      <input type="date" id="${id}" value="${fecha}" aria-label="Fecha" />
      <button type="button" class="boton-icono" data-fecha-paso="1" title="Día siguiente" aria-label="Día siguiente">›</button>
      ${esHoy ? `<span class="badge-estado ok">hoy</span>` : `<button type="button" class="boton-texto-chico" data-fecha-hoy>Ir a hoy</button>`}
    </div>`;
}
function hzVincularFechaNav(scope, id, fecha, irA) {
  scope.querySelector(`#${id}`)?.addEventListener("change", (e) => irA(e.target.value || fechaHoyISO()));
  scope.querySelectorAll("[data-fecha-paso]").forEach((b) =>
    b.addEventListener("click", () => irA(sumarDiasISO(fecha, Number(b.dataset.fechaPaso))))
  );
  scope.querySelector("[data-fecha-hoy]")?.addEventListener("click", () => irA(fechaHoyISO()));
}

// Barra de acciones de reporte, la misma en todas las vistas que exportan.
// Solo pinta los botones que ESA vista realmente ofrece.
function hzAccionesReporte({ pdf = false, imprimir = false, word = false, imprimirTexto = "Imprimir", pdfTexto = "Descargar PDF", ayuda = "" } = {}) {
  return `
    <div class="hz-acciones-reporte no-imprimir" role="group" aria-label="Acciones del reporte">
      <span class="hz-acciones-titulo">Acciones</span>
      ${pdf ? `<button type="button" class="boton" data-hz-rep="pdf"><i data-lucide=file-text class=ico></i> ${pdfTexto}</button>` : ""}
      ${imprimir ? `<button type="button" class="boton secundario" data-hz-rep="imprimir"><i data-lucide=printer class=ico></i> ${imprimirTexto}</button>` : ""}
      ${word ? `<button type="button" class="boton" data-hz-rep="word" ${puedeExportarHorario() ? "" : 'disabled title="Tu rol no puede exportar reportes de horario."'}>Generar Word</button>` : ""}
      ${ayuda ? `<span class="hz-acciones-ayuda">${ayuda}</span>` : ""}
    </div>`;
}
function hzVincularAcciones2(scope, { pdf, imprimir, word } = {}) {
  scope.querySelector('[data-hz-rep="pdf"]')?.addEventListener("click", pdf);
  scope.querySelector('[data-hz-rep="imprimir"]')?.addEventListener("click", imprimir || (() => window.print()));
  scope.querySelector('[data-hz-rep="word"]')?.addEventListener("click", word);
}

// Descarga un archivo del backend (Word, PDF) con la sesión al día y mensajes
// claros. Antes se abría una pestaña con la URL: si el servidor respondía un
// error (p. ej. «hoy» en fin de semana) la persona veía un JSON crudo en una
// pestaña en blanco. Ahora el error llega como aviso en la propia pantalla.
//  · verEnPestana: el PDF se muestra en una pestaña nueva (que se abre YA, dentro
//    del clic, para que el bloqueador de ventanas no la corte).
//  · si no, se baja como archivo.
async function hzDescargarArchivo(url, { verEnPestana = false, nombre = "archivo" } = {}) {
  const ventana = verEnPestana ? window.open("", "_blank") : null;
  try {
    await asegurarSesionFresca();
    const res = await fetch(url);
    if (!res.ok) {
      const cuerpo = await res.json().catch(() => ({}));
      throw new Error(cuerpo.detail || `Error ${res.status}`);
    }
    const blob = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    if (ventana) {
      ventana.location = objUrl;
    } else {
      const cd = res.headers.get("content-disposition") || "";
      const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
      const a = document.createElement("a");
      a.href = objUrl;
      a.download = m ? decodeURIComponent(m[1]) : nombre;
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
    setTimeout(() => URL.revokeObjectURL(objUrl), 60000);
  } catch (e) {
    if (ventana) ventana.close();
    throw e;
  }
}

// --- Combo buscable (input + menú filtrado) para listas largas ----------------
// items: [{ id, texto }]. Escribe un <input> visible + un <input type=hidden>
// con name=hiddenName que lleva el id elegido. Teclado: ↑ ↓ Enter Esc.

function comboBuscableHtml(inputId, { hiddenName = "", placeholder = "Escribe para buscar…", valorTexto = "", valorId = "" } = {}) {
  return `
    <div class="combo-buscable" data-combo="${inputId}">
      <input type="text" id="${inputId}" class="combo-input" placeholder="${placeholder}" autocomplete="off" value="${esc(valorTexto)}" role="combobox" aria-expanded="false" aria-controls="${inputId}-menu" />
      <input type="hidden" name="${hiddenName}" id="${inputId}-val" value="${valorId}" />
      <div id="${inputId}-menu" class="combo-menu" role="listbox" hidden></div>
    </div>`;
}

function vincularComboBuscable(inputId, items, onPick) {
  const input = document.getElementById(inputId);
  const hidden = document.getElementById(`${inputId}-val`);
  const menu = document.getElementById(`${inputId}-menu`);
  const norm = (s) => normalizarTexto(s);
  let activo = -1;
  const marcar = () => {
    menu.querySelectorAll(".combo-item").forEach((b, i) => b.classList.toggle("activo", i === activo));
    menu.querySelector(".combo-item.activo")?.scrollIntoView({ block: "nearest" });
  };
  const pintar = () => {
    const nq = norm(input.value);
    const res = items.filter((it) => norm(it.texto).includes(nq)).slice(0, 50);
    menu.innerHTML = res.length
      ? res.map((it) => `<button type="button" class="combo-item" role="option" data-id="${it.id}">${esc(it.texto)}${it.nota ? ` <span class="combo-nota">${esc(it.nota)}</span>` : ""}</button>`).join("")
      : `<div class="combo-vacio">Sin coincidencias</div>`;
    menu.hidden = false;
    input.setAttribute("aria-expanded", "true");
    activo = -1;
  };
  const elegir = (it) => {
    hidden.value = it.id;
    input.value = it.texto;
    menu.hidden = true;
    input.setAttribute("aria-expanded", "false");
    onPick && onPick(it);
  };
  input.addEventListener("focus", () => { input.select(); pintar(); });
  input.addEventListener("input", () => { hidden.value = ""; pintar(); });
  input.addEventListener("keydown", (e) => {
    const botones = [...menu.querySelectorAll(".combo-item")];
    if (e.key === "ArrowDown") { e.preventDefault(); if (menu.hidden) pintar(); activo = Math.min(botones.length - 1, activo + 1); marcar(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); activo = Math.max(0, activo - 1); marcar(); }
    else if (e.key === "Enter" && !menu.hidden && botones.length) {
      e.preventDefault();
      elegir(items.find((x) => String(x.id) === botones[Math.max(0, activo)].dataset.id));
    } else if (e.key === "Escape") { menu.hidden = true; input.setAttribute("aria-expanded", "false"); }
  });
  menu.addEventListener("click", (e) => {
    const b = e.target.closest(".combo-item");
    if (!b) return;
    elegir(items.find((x) => String(x.id) === b.dataset.id));
  });
}
// Un solo oyente global (antes se sumaba uno por cada combo pintado).
document.addEventListener("click", (e) => {
  document.querySelectorAll(".combo-buscable").forEach((c) => {
    if (!c.contains(e.target)) c.querySelector(".combo-menu").hidden = true;
  });
});

function limpiarRelojHorario() {
  if (horarioRelojTimer) {
    clearInterval(horarioRelojTimer);
    horarioRelojTimer = null;
  }
}

// --- Modales -------------------------------------------------------------------------

function hzAbrirModal(titulo, cuerpoHtml, { ancha = false } = {}) {
  const cont = document.getElementById("horario-modal");
  cont.innerHTML = `
    <div class="modal-fondo hz-modal no-imprimir">
      <div class="modal-caja ${ancha ? "modal-caja-ancha" : ""}" role="dialog" aria-modal="true" aria-label="${esc(titulo)}">
        <header class="est-modal-head"><h3>${titulo}</h3>
          <button type="button" class="est-visor-cerrar" data-hz-cerrar aria-label="Cerrar"></button></header>
        ${cuerpoHtml}
      </div>
    </div>`;
  cont.querySelector("[data-hz-cerrar]").addEventListener("click", hzCerrarModal);
  cont.querySelector(".modal-fondo").addEventListener("click", (e) => {
    if (e.target.classList.contains("modal-fondo")) hzCerrarModal();
  });
  return cont;
}
function hzCerrarModal() {
  const cont = document.getElementById("horario-modal");
  if (cont) cont.innerHTML = "";
}
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && document.querySelector("#horario-modal .modal-fondo")) hzCerrarModal();
});

// --- Cabecera: contexto global + buscador + navegación -----------------------------------

function seccionActual() {
  return SECCIONES_HORARIO.find((s) => s.id === horarioSub) || SECCIONES_HORARIO[0];
}

function navegacionHorarioHtml() {
  const actual = seccionActual();
  const secciones = SECCIONES_HORARIO.filter((s) => s.grupo === actual.grupo);
  const badge = (n) => (n ? `<span class="hz-badge" data-hz-badge-conflictos>${n}</span>` : `<span class="hz-badge" data-hz-badge-conflictos hidden></span>`);
  return `
    <nav class="hz-nav no-imprimir" aria-label="Secciones de Horarios">
      <div class="hz-tabs" role="tablist">
        ${GRUPOS_HORARIO.map((g) => {
          const items = SECCIONES_HORARIO.filter((s) => s.grupo === g.id);
          const unica = items.length === 1;
          const activo = actual.grupo === g.id;
          return `<button type="button" role="tab" class="hz-tab ${activo ? "activo" : ""}" aria-selected="${activo}"
                    ${unica ? `data-seccion-horario="${items[0].id}"` : `data-grupo-horario="${g.id}"`} title="${esc(g.detalle)}">
                    ${g.label}${g.id === "operacion" ? badge(horarioConflictosN) : ""}
                  </button>`;
        }).join("")}
      </div>
      ${secciones.length > 1 ? `<div class="hz-subtabs" role="tablist">${secciones
        .map((s) => `<button type="button" role="tab" class="hz-subtab ${horarioSub === s.id ? "activo" : ""}" data-seccion-horario="${s.id}" aria-selected="${horarioSub === s.id}">${s.label}${s.id === "conflictos" ? badge(horarioConflictosN) : ""}</button>`)
        .join("")}</div>` : ""}
    </nav>`;
}

function encabezadoHorarioHtml() {
  return `
    <header class="hz-encabezado no-imprimir">
      <div class="hz-titulo">
        <h1>Horarios</h1>
        <p class="subtitulo-pagina">Coordinación académica · jornada de la mañana</p>
      </div>
      <div class="hz-contexto" aria-label="Contexto del módulo">
        <span class="hz-ctx" title="El módulo trabaja con la sede principal de la institución"><span class="hz-ctx-etq">Sede</span><strong id="hz-sede-nombre">#01</strong></span>
        <label class="hz-ctx hz-ctx-anio"><span class="hz-ctx-etq">Año lectivo</span>
          <button type="button" class="hz-anio-paso" data-anio-paso="-1" aria-label="Año anterior">‹</button>
          <input type="number" id="horario-anio" value="${horarioAnio}" min="2000" max="2100" aria-label="Año lectivo" />
          <button type="button" class="hz-anio-paso" data-anio-paso="1" aria-label="Año siguiente">›</button>
        </label>
      </div>
    </header>
    <div class="hz-buscador no-imprimir">
      <span class="hz-buscador-icono" aria-hidden="true"><i data-lucide=search class=ico></i> </span>
      <input type="text" id="horario-buscar" placeholder="Buscar docente, grupo (8-1) o área…" autocomplete="off" aria-label="Buscar docente, grupo o área" role="combobox" aria-expanded="false" aria-controls="horario-buscar-resultados" />
      <button type="button" class="buscador-limpiar" id="horario-buscar-limpiar" aria-label="Borrar búsqueda" hidden></button>
      <div id="horario-buscar-resultados" class="hz-buscador-menu" role="listbox" hidden></div>
    </div>
    <div id="hz-navegacion">${navegacionHorarioHtml()}</div>`;
}

// El badge de conflictos aparece en la pestaña "Operación" y en la sub-sección.
function hzActualizarBadgeConflictos() {
  document.querySelectorAll("[data-hz-badge-conflictos]").forEach((b) => {
    b.textContent = horarioConflictosN;
    b.hidden = !horarioConflictosN;
  });
}

function hzPintarNavegacion() {
  const cont = document.getElementById("hz-navegacion");
  if (cont) {
    cont.innerHTML = navegacionHorarioHtml();
    vincularNavegacionHorario();
  }
}

// Ir a otra sección sin volver a cargar el módulo: solo cambia el contenido.
function irASeccionHorario(id) {
  if (!SECCIONES_HORARIO.some((s) => s.id === id)) return;
  horarioSub = id;
  hzPintarNavegacion();
  hzPintarSeccion();
  document.getElementById("hz-navegacion")?.scrollIntoView({ block: "nearest" });
}

// Recuerda la última sección visitada de cada grupo: pulsar "Consultar" vuelve
// a donde se estaba, no siempre a la primera.
const hzUltimaPorGrupo = {};

function vincularNavegacionHorario() {
  document.querySelectorAll("[data-seccion-horario]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const id = btn.dataset.seccionHorario;
      hzUltimaPorGrupo[SECCIONES_HORARIO.find((s) => s.id === id).grupo] = id;
      irASeccionHorario(id);
    })
  );
  document.querySelectorAll("[data-grupo-horario]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const g = btn.dataset.grupoHorario;
      irASeccionHorario(hzUltimaPorGrupo[g] || SECCIONES_HORARIO.find((s) => s.grupo === g).id);
    })
  );
}

function vincularEncabezadoHorario() {
  const inputAnio = document.getElementById("horario-anio");
  const cambiarAnio = (nuevo) => {
    if (!nuevo || nuevo === horarioAnio) return;
    horarioAnio = nuevo;
    // El panel operativo se consulta por fecha: mantenerla en el mismo año
    // evita mezclar la rejilla del contexto elegido con otro año lectivo.
    horarioFecha = horarioFecha.replace(/^\d{4}/, String(nuevo));
    inputAnio.value = nuevo;
    hzInvalidar("bloques", "conflictos");
    hzConflictosResueltos = 0;
    hzRefrescarConflictos().then(() => hzPintarNavegacion());
    hzPintarSeccion();
    horarioNotificar(`Año lectivo ${nuevo}`, "info");
  };
  inputAnio.addEventListener("change", (e) => cambiarAnio(Number(e.target.value)));
  document.querySelectorAll("[data-anio-paso]").forEach((b) =>
    b.addEventListener("click", () => cambiarAnio(horarioAnio + Number(b.dataset.anioPaso)))
  );
  vincularNavegacionHorario();
  vincularBuscadorHorario();

  // Nombre real de la sede (sin bloquear el pintado de la pantalla).
  obtenerSedes()
    .then((sedes) => {
      const s = sedes.find((x) => x.id === 1);
      const el = document.getElementById("hz-sede-nombre");
      if (s && el) el.textContent = sedeCorta(s);
    })
    .catch(() => {});
}

// Buscador global: docentes, grupos y áreas reales, con resultados
// diferenciados por tipo. Cada resultado lleva a su consulta.
function vincularBuscadorHorario() {
  const input = document.getElementById("horario-buscar");
  const menu = document.getElementById("horario-buscar-resultados");
  const limpiar = document.getElementById("horario-buscar-limpiar");
  let t = null;
  let activo = -1;

  const cerrar = () => { menu.hidden = true; input.setAttribute("aria-expanded", "false"); activo = -1; };
  const marcar = () => {
    const items = [...menu.querySelectorAll(".hz-res-item")];
    items.forEach((b, i) => b.classList.toggle("activo", i === activo));
    items[activo]?.scrollIntoView({ block: "nearest" });
  };
  const resaltar = (texto, q) => {
    const i = normalizarTexto(texto).indexOf(normalizarTexto(q));
    if (i < 0 || !q) return esc(texto);
    return `${esc(texto.slice(0, i))}<mark>${esc(texto.slice(i, i + q.length))}</mark>${esc(texto.slice(i + q.length))}`;
  };
  const grupo = (titulo, filas) => (filas.length ? `<div class="hz-res-grupo"><div class="hz-res-titulo">${titulo}</div>${filas.join("")}</div>` : "");

  input.addEventListener("input", () => {
    clearTimeout(t);
    const q = input.value.trim();
    limpiar.hidden = !input.value;
    if (q.length < 2) { cerrar(); return; }
    t = setTimeout(async () => {
      const solicitud = ++busquedaHorarioSeq;
      menu.innerHTML = `<div class="hz-res-vacio">${hzCargando("Buscando…")}</div>`;
      menu.hidden = false;
      input.setAttribute("aria-expanded", "true");
      let r;
      try {
        r = await api(`/api/horario/buscar?q=${encodeURIComponent(q)}&anio_lectivo=${horarioAnio}`);
      } catch (error) {
        if (solicitud === busquedaHorarioSeq) menu.innerHTML = `<div class="hz-res-vacio">No se pudo completar la búsqueda.</div>`;
        return;
      }
      // Una respuesta lenta no puede reemplazar resultados de una búsqueda más reciente.
      if (solicitud !== busquedaHorarioSeq || input.value.trim() !== q) return;
      const docentes = r.docentes.slice(0, 8).map((d) => `
        <button type="button" class="hz-res-item" role="option" data-tipo="docente" data-id="${d.id}">
          <span>${resaltar(d.texto, q)}</span>${d.con_horario ? "" : '<span class="bh-nota">sin horario</span>'}
        </button>`);
      const grupos = r.grupos.slice(0, 8).map((g) => `
        <button type="button" class="hz-res-item" role="option" data-tipo="grupo" data-grado="${g.grado}" data-curso="${g.curso ?? ""}">
          <span>${resaltar(g.texto, q)}</span><span class="bh-nota">${etiquetaGrupoHorario(g.grado, g.curso)}</span>
        </button>`);
      const areas = r.areas.slice(0, 8).map((a) => `
        <button type="button" class="hz-res-item" role="option" data-tipo="area" data-label="${esc(a.area_label || a.texto)}">
          <span>${resaltar(a.texto, q)}</span><span class="bh-nota">ver quién la dicta</span>
        </button>`);
      const html = grupo("Docentes", docentes) + grupo("Grupos", grupos) + grupo("Áreas", areas);
      menu.innerHTML = html || `<div class="hz-res-vacio">Sin coincidencias para «${esc(q)}».<br><small>Prueba con un apellido, un grupo como 8-1 o el nombre de un área.</small></div>`;
      activo = -1;
    }, 180);
  });

  input.addEventListener("keydown", (e) => {
    const items = [...menu.querySelectorAll(".hz-res-item")];
    if (e.key === "ArrowDown" && items.length) { e.preventDefault(); activo = Math.min(items.length - 1, activo + 1); marcar(); }
    else if (e.key === "ArrowUp" && items.length) { e.preventDefault(); activo = Math.max(0, activo - 1); marcar(); }
    else if (e.key === "Enter" && items.length) { e.preventDefault(); (items[activo] || items[0]).click(); }
    else if (e.key === "Escape") { cerrar(); if (!input.value) input.blur(); }
  });
  limpiar.addEventListener("click", () => { input.value = ""; limpiar.hidden = true; cerrar(); input.focus(); });

  menu.addEventListener("click", (e) => {
    const item = e.target.closest(".hz-res-item");
    if (!item) return;
    cerrar();
    input.value = "";
    limpiar.hidden = true;
    if (item.dataset.tipo === "docente") {
      horarioDocenteId = Number(item.dataset.id);
      hzUltimaPorGrupo.consultar = "docente";
      irASeccionHorario("docente");
    } else if (item.dataset.tipo === "grupo") {
      horarioGrupoSel = { grado: Number(item.dataset.grado), curso: item.dataset.curso === "" ? null : Number(item.dataset.curso) };
      hzUltimaPorGrupo.consultar = "grupo";
      irASeccionHorario("grupo");
    } else {
      horarioGeneralFiltroArea = item.dataset.label;
      hzUltimaPorGrupo.analisis = "general";
      irASeccionHorario("general");
    }
  });
}
document.addEventListener("click", (e) => {
  if (e.target.closest(".hz-buscador")) return;
  const menu = document.getElementById("horario-buscar-resultados");
  if (menu) menu.hidden = true;
});

// --- Punto de entrada -----------------------------------------------------------------------

let hzTokenActual = 0; // descarta lo que llegue tarde de una sección ya abandonada
const hzVigente = (tok) => tok === hzTokenActual;

// Vista completa (la llama core.js). Al cambiar de sección o de año NO se vuelve
// aquí: se repinta solo el contenido (hzPintarSeccion).
async function renderHorario() {
  limpiarRelojHorario();
  hzConflictosResueltos = 0;
  if (!SECCIONES_HORARIO.some((s) => s.id === horarioSub)) horarioSub = "hoy";
  app.innerHTML = `<div class="hz-modulo">${encabezadoHorarioHtml()}<div id="horario-contenido" class="hz-contenido"></div><div id="horario-modal"></div></div>`;
  vincularEncabezadoHorario();
  hzRefrescarConflictos().then(() => hzActualizarBadgeConflictos());
  await hzPintarSeccion();
}

// Cuenta de conflictos para el badge. Se pide una vez por entrada al módulo y
// se reutiliza en la sección Conflictos (antes se pedía en cada cambio).
async function hzRefrescarConflictos() {
  try {
    await hzConflictos();
  } catch {
    /* sin permiso o sin conexión: el badge simplemente no aparece */
  }
}

async function hzPintarSeccion() {
  limpiarRelojHorario();
  const cont = document.getElementById("horario-contenido");
  if (!cont) return;
  const tok = ++hzTokenActual;
  cont.innerHTML = hzCargando();
  const pintores = {
    hoy: renderHorarioHoy, libres: renderHorarioLibres, reemplazos: renderHorarioReemplazos,
    conflictos: renderHorarioConflictos, docente: renderHorarioDocente, grupo: renderHorarioGrupo,
    dia: renderHorarioDia, asignar: renderHorarioAsignar, general: renderHorarioGeneral,
    horaslibres: renderHorarioHorasLibres, reporte: renderHorarioReporte,
  };
  try {
    await pintores[horarioSub](cont, tok);
  } catch (e) {
    if (!hzVigente(tok)) return;
    cont.innerHTML = hzError(e);
    hzVincularAcciones(cont, { reintentar: () => hzPintarSeccion() });
  }
}

// Repintar la sección actual conservando el punto de scroll (tras registrar
// una ausencia, cambiar un reemplazo…): sin saltos ni pantalla en blanco.
async function hzRepintarSeccionSuave() {
  const y = window.scrollY;
  await hzPintarSeccion();
  window.scrollTo(0, y);
}

// ==========================================================================
//  OPERACIÓN · HOY
// ==========================================================================

function hzJornada(panel, esHoy) {
  if (!esHoy) {
    return panel.dia
      ? { texto: "Día de clases", detalle: "Programación de esa fecha", tono: "neutro" }
      : { texto: "Sin clases", detalle: "Fin de semana", tono: "neutro" };
  }
  const f = panel.franja || {};
  if (f.estado === "en_franja" && f.franja)
    return { texto: `${f.hora}ª hora`, detalle: `${f.franja.inicio}–${f.franja.fin} · en clase`, tono: "ok" };
  if (f.estado === "descanso") return { texto: "Receso", detalle: "Descanso de la jornada", tono: "aviso" };
  if (f.estado === "fin_de_semana") return { texto: "Sin clases", detalle: "Fin de semana", tono: "neutro" };
  if (f.estado === "fuera_jornada") return { texto: "Fuera de jornada", detalle: "La jornada va de 7:30 a 13:30", tono: "neutro" };
  return { texto: "Sin información de jornada", detalle: "", tono: "neutro" };
}

function coberturaClaseHtml(c, fecha) {
  const cubierto = c.reemplazo_estado === "asignado";
  if (cubierto) return `<span class="badge-estado ok">Cubre: ${esc(nombreCortoHorario(c.reemplazo_docente))}</span>`;
  if (c.conflicto) {
    const quienes = c.conflicto_opciones.map((o) => o.docente_nombre).join(" o ");
    return `<button type="button" class="boton secundario boton-chico" data-hz-ir="conflictos" title="${esc(quienes)}">Resolver conflicto primero</button>`;
  }
  if (!puedeGestionarHorario()) return `<span class="badge-estado proceso">Sin cubrir</span>`;
  return `<button type="button" class="boton boton-chico" data-buscar-reemplazo="${c.bloque_horario_id}" data-fecha="${fecha}">Buscar reemplazo${c.horas.length > 1 ? ` (${c.horas.length}h)` : ""}</button>`;
}

function ausenciaCardHtml(a, fecha) {
  const filas = a.clases_afectadas
    .map((c) => `
      <tr class="${c.reemplazo_estado === "asignado" ? "cubierta" : ""} ${c.conflicto ? "en-conflicto" : ""}">
        <td class="hz-td-hora">${rangoHoras(c.horas)}</td>
        <td><strong>${etiquetaGrupoHorario(c.grado, c.curso)}</strong></td>
        <td>${esc(c.area_label)}${c.reemplazo_estado === "parcial" ? ' <span class="badge-estado proceso">solo 1 hora cubierta</span>' : ""}</td>
        <td class="hz-td-accion">${coberturaClaseHtml(c, fecha)}</td>
      </tr>`)
    .join("");
  return `
    <article class="hz-ausencia">
      <header>
        <div><strong>${ESTADO_HORARIO.ausente.emoji} ${esc(a.docente_nombre)}</strong>
          <span class="hz-motivo">${esc(a.motivo || "Sin motivo registrado")}</span></div>
        ${puedeGestionarHorario() ? `<button type="button" class="boton-texto-chico" data-borrar-ausencia="${a.id}">Quitar ausencia</button>` : ""}
      </header>
      ${filas
        ? `<div class="tabla-scroll"><table class="hz-tabla-mini"><thead><tr><th>Hora</th><th>Grupo</th><th>Materia</th><th>Cobertura</th></tr></thead><tbody>${filas}</tbody></table></div>`
        : `<p class="hz-nota">No tiene clases ese día: no hay reemplazos por gestionar.</p>`}
    </article>`;
}

async function renderHorarioHoy(cont, tok) {
  const fecha = horarioFecha;
  const esHoy = fecha === fechaHoyISO();
  const panel = await api(`/api/horario/hoy?fecha=${fecha}`);
  if (!hzVigente(tok)) return;
  horarioConflictosN = panel.conflictos_pendientes;
  hzActualizarBadgeConflictos();

  const jornada = hzJornada(panel, esHoy);
  const totalDocentes =
    panel.docentes_libres + panel.docentes_en_clase + panel.docentes_ausentes +
    panel.docentes_cubriendo + panel.docentes_descanso + panel.docentes_fuera_jornada;
  const asignados = panel.reemplazos.filter((r) => r.estado === "asignado").length;
  const pendientes = panel.reemplazos.filter((r) => r.estado === "pendiente").length;
  const sinClases = !panel.dia;

  const kpis = [
    hzKpi({ n: totalDocentes, txt: "Docentes", sub: "con horario", tono: "" }),
    hzKpi({ n: panel.clases_programadas, txt: "Clases", sub: sinClases ? "sin clases" : "programadas", tono: sinClases ? "vacio" : "" }),
    hzKpi({ n: panel.docentes_libres, txt: "Libres", sub: esHoy && panel.franja?.estado === "en_franja" ? "en esta hora" : "en la jornada", tono: panel.docentes_libres ? "ok" : "vacio", accion: "libres", titulo: "Ver quién está libre" }),
    hzKpi({ n: panel.docentes_ausentes, txt: "Ausentes", sub: "docentes", tono: panel.docentes_ausentes ? "alerta" : "vacio" }),
    hzKpi({ n: asignados + pendientes, txt: "Reemplazos", sub: pendientes ? `${pendientes} sin asignar` : asignados ? "todos asignados" : "ninguno", tono: pendientes ? "aviso" : asignados ? "ok" : "vacio", accion: "reemplazos", titulo: "Ver reemplazos" }),
    hzKpi({ n: panel.conflictos_pendientes, txt: "Conflictos", sub: panel.conflictos_pendientes ? "por revisar" : "al día", tono: panel.conflictos_pendientes ? "alerta" : "ok", accion: "conflictos", titulo: "Revisar conflictos de horario" }),
  ].join("");

  const alertas = [];
  if (panel.clases_necesitan_reemplazo)
    alertas.push(`<strong>${panel.clases_necesitan_reemplazo}</strong> clase(s) sin cubrir por ausencias`);
  if (panel.conflictos_pendientes)
    alertas.push(`<strong>${panel.conflictos_pendientes}</strong> conflicto(s) de horario sin resolver`);
  const bannerAlertas = alertas.length
    ? `<section class="hz-alerta" role="alert">
         <span class="hz-alerta-icono" aria-hidden="true"><i data-lucide=triangle-alert class=ico></i> </span>
         <div><strong>Requiere atención</strong><span>${alertas.join(" · ")}</span></div>
         <div class="hz-alerta-acciones">
           ${panel.conflictos_pendientes ? `<button type="button" class="boton boton-chico" data-hz-ir="conflictos">Revisar conflictos</button>` : ""}
           ${panel.clases_necesitan_reemplazo ? `<a class="boton secundario boton-chico" href="#hz-ausencias" data-hz-scroll="hz-ausencias">Ver ausencias</a>` : ""}
         </div>
       </section>`
    : "";

  const avisoSinClases = sinClases
    ? `<section class="hz-info">
         <span aria-hidden="true"><i data-lucide=calendar class=ico></i> </span>
         <div><strong>${esHoy ? "Hoy no hay clases" : "Ese día no hay clases"}</strong>
           <span>${esc(panel.dia_nombre)}: los indicadores de disponibilidad no aplican.</span></div>
         <div class="hz-alerta-acciones">
           <button type="button" class="boton secundario boton-chico" data-hz-fecha="${diaHabilCercano(fecha, -1)}">‹ ${fechaCortaHorario(diaHabilCercano(fecha, -1))}</button>
           <button type="button" class="boton secundario boton-chico" data-hz-fecha="${diaHabilCercano(fecha, 1)}">${fechaCortaHorario(diaHabilCercano(fecha, 1))} ›</button>
         </div>
       </section>`
    : "";

  const ausenciasHtml = panel.ausencias.length
    ? panel.ausencias.map((a) => ausenciaCardHtml(a, fecha)).join("")
    : hzVacio({
        icono: "<i data-lucide=circle-check class=ico></i> ",
        titulo: "Sin ausencias registradas",
        texto: sinClases ? "No hay clases que cubrir en esta fecha." : "No hay clases que requieran cobertura para esta fecha.",
        acciones: puedeGestionarHorario() && !sinClases ? [{ id: "ausencia", texto: "＋ Registrar ausencia" }] : [],
      });

  cont.innerHTML = `
    <section class="hz-barra-dia">
      <div class="hz-barra-fecha">
        ${hzFechaNavHtml("hoy-fecha", fecha)}
        <h2 class="hz-fecha-larga">${esc(fechaLargaHorario(fecha))}</h2>
      </div>
      <div class="hz-barra-dia-derecha">
        <span class="hz-jornada ${jornada.tono}" title="${esc(jornada.detalle)}"><strong>${esc(jornada.texto)}</strong>${jornada.detalle ? `<span>${esc(jornada.detalle)}</span>` : ""}</span>
        ${puedeGestionarHorario() ? `<button type="button" class="boton" id="btn-registrar-ausencia">＋ Registrar ausencia</button>` : ""}
      </div>
    </section>

    ${avisoSinClases}
    <section class="hz-kpis ${sinClases ? "hz-kpis-inactivos" : ""}" aria-label="Resumen del día">${kpis}</section>
    ${bannerAlertas}

    <div class="hz-dos-columnas">
      <section id="hz-ausencias" class="hz-panel">
        <h3 class="hz-panel-titulo">Ausencias ${esHoy ? "de hoy" : "del día"} <span class="hz-contador">${panel.ausencias.length}</span></h3>
        ${ausenciasHtml}
      </section>
      <section class="hz-panel">
        <h3 class="hz-panel-titulo">Reemplazos ${esHoy ? "de hoy" : "del día"} <span class="hz-contador">${panel.reemplazos.length}</span></h3>
        ${tablaReemplazosHtml(panel.reemplazos, { compacta: true, fecha, sinClases })}
      </section>
    </div>
  `;

  hzVincularFechaNav(cont, "hoy-fecha", fecha, (f) => { horarioFecha = f; hzPintarSeccion(); });
  document.getElementById("btn-registrar-ausencia")?.addEventListener("click", () => abrirModalAusencia(fecha));
  cont.querySelectorAll("[data-hz-fecha]").forEach((b) => b.addEventListener("click", () => { horarioFecha = b.dataset.hzFecha; hzPintarSeccion(); }));
  hzVincularIrA(cont);
  cont.querySelectorAll("[data-hz-scroll]").forEach((a) =>
    a.addEventListener("click", (e) => { e.preventDefault(); document.getElementById(a.dataset.hzScroll)?.scrollIntoView({ behavior: "smooth", block: "start" }); })
  );
  hzVincularAcciones(cont, { ausencia: () => abrirModalAusencia(fecha) });
  cont.querySelectorAll("[data-buscar-reemplazo]").forEach((b) =>
    b.addEventListener("click", () => abrirModalReemplazo(Number(b.dataset.buscarReemplazo), b.dataset.fecha))
  );
  cont.querySelectorAll("[data-borrar-ausencia]").forEach((b) =>
    b.addEventListener("click", async () => {
      const ok = await hzConfirmar({
        titulo: "¿Quitar esta ausencia?",
        texto: "Se cancelan sus reemplazos pendientes. Las clases vuelven a quedar a cargo del docente.",
        confirmar: "Quitar ausencia",
        peligro: true,
      });
      if (!ok) return;
      try {
        await api(`/api/horario/ausencias/${b.dataset.borrarAusencia}`, { method: "DELETE" });
        horarioNotificar("Ausencia retirada correctamente.");
        hzRepintarSeccionSuave();
      } catch (e) {
        horarioNotificar(`No se pudo quitar la ausencia: ${e.message}`, "error");
      }
    })
  );
  vincularAccionesReemplazo(cont);
}

// Cualquier elemento con data-hz-ir="seccion" lleva a esa sección.
function hzVincularIrA(scope) {
  scope.querySelectorAll("[data-hz-ir]").forEach((b) => b.addEventListener("click", () => irASeccionHorario(b.dataset.hzIr)));
}

// ==========================================================================
//  OPERACIÓN · DISPONIBILIDAD ("¿quién está libre?")
// ==========================================================================

// Por qué no hay clase en este momento, dicho en claro.
function hzExplicarAhora(ahora) {
  const f = ahora.estado;
  if (f === "fin_de_semana") return { titulo: "Hoy no hay clases", texto: "Es fin de semana. La jornada se reanuda el lunes a las 7:30." };
  if (f === "descanso") return { titulo: "Receso", texto: "Las clases continúan a las 11:00 con la 4ª hora." };
  if (f === "fuera_jornada") {
    const hora = new Date().getHours() * 60 + new Date().getMinutes();
    return hora < 450
      ? { titulo: "La jornada aún no empieza", texto: "La 1ª hora comienza a las 7:30." }
      : { titulo: "La jornada ya terminó", texto: "La última hora terminó a las 13:30. Consulta una franja concreta abajo." };
  }
  return { titulo: "Sin clase en este momento", texto: "" };
}

function chipsLibresHtml(libres, nivel, etiqueta) {
  const chip = (d) => `
    <button type="button" class="chip-docente" data-ver-docente="${d.docente_id}" title="Ver el horario de ${esc(d.nombre_completo)}">
      ${ESTADO_HORARIO.libre.emoji} ${esc(d.nombre_completo)}
      ${d.niveles && d.niveles.length === 2 ? `<span class="chip-nivel">P·S</span>` : ""}
      <span class="chip-carga">${d.bloques_ese_dia} clases ese día</span>
    </button>`;
  if (nivel) {
    const f = libres.filter((d) => (d.niveles || []).includes(nivel));
    if (!f.length)
      return hzVacio({ icono: "<i data-lucide=search class=ico></i> ", titulo: `Ningún docente de ${nivel} está libre ${etiqueta}`, texto: "Prueba con otra franja, otro día o quita el filtro de nivel." });
    return `<p class="hz-resultado-titulo"><strong>${f.length}</strong> docente(s) de ${nivel} libre(s) ${etiqueta}</p><div class="chips-docentes">${f.map(chip).join("")}</div>`;
  }
  if (!libres.length)
    return hzVacio({ icono: "<i data-lucide=search class=ico></i> ", titulo: `Ningún docente está libre ${etiqueta}`, texto: "Todos tienen clase, están ausentes o cubren un reemplazo en esa franja." });
  const grupo = (n, etq) => {
    const f = libres.filter((d) => (d.niveles || []).includes(n));
    return `<h4 class="libres-nivel-titulo">${etq} <span class="hz-contador">${f.length}</span></h4>
      <div class="chips-docentes">${f.map(chip).join("") || "<span class='conteo-resultados'>Ninguno</span>"}</div>`;
  };
  return `<p class="hz-resultado-titulo"><strong>${libres.length}</strong> docente(s) libre(s) ${etiqueta}</p>${grupo("primaria", "Primaria")}${grupo("secundaria", "Secundaria")}`;
}

async function renderHorarioLibres(cont, tok) {
  const fecha = horarioFecha;
  const esFechaActual = fecha === fechaHoyISO();
  const ahora = await api("/api/horario/ahora");
  if (!hzVigente(tok)) return;
  const dentro = esFechaActual && ahora.estado === "en_franja" && ahora.franja;
  const explica = hzExplicarAhora(ahora);
  const horaDefecto = dentro ? ahora.hora : 1;

  cont.innerHTML = `
    ${hzTitulo("Disponibilidad docente", "¿Quién está libre ahora, o en una franja concreta?", hzSegmentado("libres-nivel", [
      { v: "", t: "Todos" }, { v: "primaria", t: "Primaria" }, { v: "secundaria", t: "Secundaria" },
    ], horarioLibresNivel))}

    <div class="hz-dos-columnas hz-libres-cols">
      <section class="hz-panel hz-ahora ${dentro ? "en-clase" : ""}">
        <h3 class="hz-panel-titulo">Ahora</h3>
        <div class="reloj-ahora">
          <span class="reloj-hora" id="reloj-vivo">--:--</span>
          <span class="reloj-detalle">
            ${esFechaActual ? esc(ahora.dia_nombre) : `Consulta para ${esc(fechaLargaHorario(fecha))}`}
            ${dentro ? `· <strong>${ahora.hora}ª hora</strong> (${ahora.franja.inicio}–${ahora.franja.fin})` : ""}
          </span>
        </div>
        <div id="libres-ahora-lista">
          ${dentro
            ? hzCargando("Buscando docentes libres…")
            : hzVacio({
                icono: ahora.estado === "descanso" ? "<i data-lucide=coffee class=ico></i> " : "<i data-lucide=clock class=ico></i> ",
                titulo: esFechaActual ? explica.titulo : "La disponibilidad en vivo solo corresponde a hoy",
                texto: esFechaActual ? explica.texto : "Usa la consulta por franja para cualquier fecha.",
                tono: "neutro",
              })}
        </div>
      </section>

      <section class="hz-panel">
        <h3 class="hz-panel-titulo">Consultar una franja</h3>
        <div class="hz-form-fila">
          <label>Fecha<input type="date" id="libres-fecha" value="${fecha}" /></label>
          <label>Día<select id="libres-dia">${DIAS_HORARIO.map(([n, t]) => `<option value="${n}" ${n === horarioDiaSel ? "selected" : ""}>${t}</option>`).join("")}</select></label>
          <label>Desde<select id="libres-hora">${FRANJAS_HORARIO.map((f) => `<option value="${f.hora}" ${f.hora === horaDefecto ? "selected" : ""}>${f.hora}ª · ${f.inicio}–${f.fin}</option>`).join("")}</select></label>
          <label>Hasta<select id="libres-hora-fin">${FRANJAS_HORARIO.map((f) => `<option value="${f.hora}" ${f.hora === horaDefecto ? "selected" : ""}>${f.hora}ª · ${f.inicio}–${f.fin}</option>`).join("")}</select></label>
          <button type="button" class="boton" id="btn-libres-consultar">Consultar</button>
        </div>
        <p class="hz-nota">Bloque de 2 horas (p. ej. 5ª y 6ª): «Desde 5ª · Hasta 6ª» muestra solo a quienes están libres las dos.</p>
        <div id="libres-consulta-lista" aria-live="polite">${hzCargando("Consultando…")}</div>
      </section>
    </div>
  `;

  let cargarAhoraCont = 0;
  const pintarReloj = () => {
    const d = new Date();
    const el = document.getElementById("reloj-vivo");
    if (el) el.textContent = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  };
  pintarReloj();

  const cargarAhora = async () => {
    const caja = document.getElementById("libres-ahora-lista");
    if (!caja || !dentro) return;
    const yo = ++cargarAhoraCont;
    const fr = await api("/api/horario/ahora");
    if (fr.estado !== "en_franja") { hzPintarSeccion(); return; } // cambió de franja: se explica el nuevo estado
    const libres = await api(`/api/horario/libres?dia=${fr.dia}&hora=${fr.hora}&fecha=${fecha}&anio_lectivo=${horarioAnio}`);
    if (yo !== cargarAhoraCont || !document.getElementById("libres-ahora-lista")) return;
    caja.innerHTML = chipsLibresHtml(libres, horarioLibresNivel, `ahora (${fr.hora}ª hora)`);
  };
  if (dentro) cargarAhora();

  limpiarRelojHorario();
  horarioRelojTimer = setInterval(() => {
    // Si la persona ya salió de esta pantalla, el reloj se apaga solo.
    if (!document.getElementById("reloj-vivo")) return limpiarRelojHorario();
    pintarReloj();
    if (dentro) cargarAhora().catch(() => {});
  }, 30000);

  let seq = 0;
  const consultarFranja = async () => {
    const caja = document.getElementById("libres-consulta-lista");
    const dia = Number(document.getElementById("libres-dia").value);
    let hora = Number(document.getElementById("libres-hora").value);
    let horaFin = Number(document.getElementById("libres-hora-fin").value);
    if (horaFin < hora) [hora, horaFin] = [horaFin, hora]; // por si los invierten
    horarioDiaSel = dia;
    const yo = ++seq;
    caja.innerHTML = hzCargando("Consultando…");
    try {
      const libres = await api(`/api/horario/libres?dia=${dia}&hora=${hora}&hora_fin=${horaFin}&fecha=${fecha}&anio_lectivo=${horarioAnio}`);
      if (yo !== seq || !document.getElementById("libres-consulta-lista")) return;
      const franja = hora === horaFin ? `a la ${hora}ª hora` : `de la ${hora}ª a la ${horaFin}ª hora`;
      caja.innerHTML = chipsLibresHtml(libres, horarioLibresNivel, `el ${nombreDiaHorario(dia).toLowerCase()} ${franja}`);
    } catch (e) {
      if (yo === seq) caja.innerHTML = hzError(e);
    }
  };
  // La consulta se ejecuta sola al abrir y al cambiar cualquier control.
  document.getElementById("btn-libres-consultar").addEventListener("click", consultarFranja);
  ["libres-dia", "libres-hora-fin"].forEach((id) => document.getElementById(id).addEventListener("change", consultarFranja));
  document.getElementById("libres-hora").addEventListener("change", (e) => {
    const fin = document.getElementById("libres-hora-fin");
    if (Number(fin.value) < Number(e.target.value)) fin.value = e.target.value; // "Hasta" sigue a "Desde"
    consultarFranja();
  });
  document.getElementById("libres-fecha").addEventListener("change", (e) => {
    if (!e.target.value) return;
    horarioFecha = e.target.value;
    const dia = diaSemanaISO(e.target.value);
    if (dia >= 1 && dia <= 5) horarioDiaSel = dia;
    hzPintarSeccion();
  });
  hzVincularSeg(cont, "libres-nivel", (v) => { horarioLibresNivel = v; if (dentro) cargarAhora(); consultarFranja(); });
  hzVincularAcciones(cont, { reintentar: consultarFranja });
  consultarFranja();
}

// ==========================================================================
//  OPERACIÓN · REEMPLAZOS
// ==========================================================================

async function renderHorarioReemplazos(cont, tok) {
  const fecha = horarioFecha;
  const reemplazos = await api(`/api/horario/reemplazos?fecha=${fecha}`);
  if (!hzVigente(tok)) return;
  const cuenta = (e) => reemplazos.filter((r) => r.estado === e).length;

  cont.innerHTML = `
    ${hzTitulo("Reemplazos", "Coberturas de las clases de docentes ausentes.", puedeGestionarHorario() ? `<button type="button" class="boton" id="btn-reemp-ausencia">＋ Registrar ausencia</button>` : "")}
    <div class="hz-barra-dia">
      <div class="hz-barra-fecha">${hzFechaNavHtml("reemp-fecha", fecha)}<h3 class="hz-fecha-larga">${esc(fechaLargaHorario(fecha))}</h3></div>
      ${reemplazos.length ? `<div class="hz-resumen-estados">
        <span class="badge-estado ok">${cuenta("asignado")} asignado(s)</span>
        <span class="badge-estado proceso">${cuenta("pendiente")} pendiente(s)</span>
        ${cuenta("cancelado") ? `<span class="badge-estado">${cuenta("cancelado")} cancelado(s)</span>` : ""}
      </div>` : ""}
    </div>
    ${tablaReemplazosHtml(reemplazos, { fecha })}
  `;
  hzVincularFechaNav(cont, "reemp-fecha", fecha, (f) => { horarioFecha = f; hzPintarSeccion(); });
  document.getElementById("btn-reemp-ausencia")?.addEventListener("click", () => abrirModalAusencia(fecha));
  hzVincularAcciones(cont, {
    ausencia: () => abrirModalAusencia(fecha),
    hoy: () => { horarioFecha = fechaHoyISO(); hzPintarSeccion(); },
    fecha: () => document.getElementById("reemp-fecha")?.showPicker?.() || document.getElementById("reemp-fecha")?.focus(),
  });
  vincularAccionesReemplazo(cont);
}

function tablaReemplazosHtml(reemplazos, { compacta = false, fecha = fechaHoyISO(), sinClases = false } = {}) {
  if (!reemplazos.length) {
    const acciones = [];
    if (!compacta) {
      acciones.push({ id: "fecha", texto: "Consultar otra fecha" });
      if (fecha !== fechaHoyISO()) acciones.push({ id: "hoy", texto: "Ir a hoy" });
      if (puedeGestionarHorario() && !sinClases) acciones.push({ id: "ausencia", texto: "＋ Registrar ausencia", primaria: true });
    }
    return hzVacio({
      icono: "<i data-lucide=repeat class=ico></i> ",
      titulo: fecha === fechaHoyISO() ? "No hay reemplazos para hoy" : `No hay reemplazos para el ${esc(fechaCortaHorario(fecha))}`,
      texto: "Los reemplazos aparecen cuando se registra la ausencia de un docente que tiene clases ese día.",
      acciones,
    });
  }
  const badge = { pendiente: "proceso", asignado: "ok", cancelado: "" };
  const columnas = compacta
    ? "<th>Hora</th><th>Grupo</th><th>Materia</th><th>Ausente</th><th>Reemplaza</th><th>Estado</th><th></th>"
    : "<th>Fecha</th><th>Hora</th><th>Grupo</th><th>Materia</th><th>Profesor ausente</th><th>Reemplazante</th><th>Compat.</th><th>Estado</th><th></th>";
  return `
    <div class="tabla-scroll">
      <table class="tabla-informe hz-tabla-reemplazos">
        <thead><tr>${columnas}</tr></thead>
        <tbody>
          ${reemplazos
            .map((r) => {
              const horas = r.horas && r.horas.length ? r.horas : [r.hora];
              const ids = (r.ids && r.ids.length ? r.ids : [r.id]).join(",");
              const acciones = puedeGestionarHorario()
                ? `${r.estado === "pendiente" && r.bloque_horario_id ? `<button type="button" class="boton boton-chico" data-buscar-reemplazo="${r.bloque_horario_id}" data-fecha="${r.fecha}">Buscar</button>` : ""}
                   ${r.estado !== "cancelado" && r.bloque_horario_id ? `<button type="button" class="boton-texto-chico" data-cambiar-reemplazo="${ids}" data-bloque="${r.bloque_horario_id}" data-fecha="${r.fecha}">Cambiar</button>` : ""}
                   ${r.estado === "asignado" ? `<button type="button" class="boton-texto-chico hz-peligro" data-cancelar-reemplazo="${ids}">Cancelar</button>` : ""}`
                : "";
              const compat = r.compatibilidad != null
                ? `<span class="hz-compat" title="Compatibilidad calculada por el sistema">${r.compatibilidad}%</span>` : "—";
              const comunes = `
                <td class="hz-td-hora"><strong>${rangoHoras(horas)}</strong>${horas.length > 1 ? " <small>(bloque)</small>" : ""}</td>
                <td><strong>${etiquetaGrupoHorario(r.grado, r.curso)}</strong></td>
                <td>${esc(r.area_label)}</td>
                <td>${esc(compacta ? nombreCortoHorario(r.docente_ausente) : r.docente_ausente)}</td>
                <td>${r.docente_reemplazo ? esc(compacta ? nombreCortoHorario(r.docente_reemplazo) : r.docente_reemplazo) : '<span class="hz-sin">Sin asignar</span>'}</td>`;
              return `<tr class="${r.estado === "cancelado" ? "fila-cancelada" : ""}">
                ${compacta ? "" : `<td>${esc(fechaCortaHorario(r.fecha))}</td>`}
                ${comunes}
                ${compacta ? "" : `<td>${compat}</td>`}
                <td><span class="badge-estado ${badge[r.estado] || ""}">${esc(r.estado)}</span></td>
                <td class="col-acciones">${acciones}</td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function vincularAccionesReemplazo(scope) {
  scope.querySelectorAll("[data-buscar-reemplazo]").forEach((b) =>
    b.addEventListener("click", () => abrirModalReemplazo(Number(b.dataset.buscarReemplazo), b.dataset.fecha))
  );
  scope.querySelectorAll("[data-cambiar-reemplazo]").forEach((b) =>
    b.addEventListener("click", () => abrirModalReemplazo(Number(b.dataset.bloque), b.dataset.fecha, b.dataset.cambiarReemplazo))
  );
  scope.querySelectorAll("[data-cancelar-reemplazo]").forEach((b) =>
    b.addEventListener("click", async () => {
      const ids = b.dataset.cancelarReemplazo.split(",");
      const ok = await hzConfirmar({
        titulo: ids.length > 1 ? `¿Cancelar este reemplazo de ${ids.length} horas?` : "¿Cancelar este reemplazo?",
        texto: "La clase quedará otra vez sin cubrir.",
        confirmar: "Cancelar reemplazo",
        cancelar: "Volver",
        peligro: true,
      });
      if (!ok) return;
      b.disabled = true;
      try {
        for (const id of ids) {
          await api(`/api/horario/reemplazos/${id}`, { method: "PATCH", body: JSON.stringify({ estado: "cancelado" }) });
        }
        horarioNotificar("Reemplazo cancelado.");
        hzRepintarSeccionSuave();
      } catch (e) {
        horarioNotificar(`No se pudo cancelar el reemplazo: ${e.message}`, "error");
        b.disabled = false;
      }
    })
  );
}

// ==========================================================================
//  OPERACIÓN · CONFLICTOS (dos docentes para el mismo grupo y hora)
// ==========================================================================

let hzConflictosDia = ""; // filtro por día: "" = todos
let hzConflictosResueltos = 0; // resueltos desde que se abrió el módulo (sobrevive a salir y volver)

function fraseFranja(hora) {
  const f = FRANJAS_HORARIO.find((x) => x.hora === hora);
  return f ? `${hora}ª hora · ${f.inicio}–${f.fin}` : `${hora}ª hora`;
}

function tarjetaConflictoHtml(c, i) {
  const clave = `${c.grado}|${c.curso ?? ""}|${c.dia}|${c.hora}`;
  const gestiona = puedeGestionarHorario();
  return `
    <article class="hz-conflicto" data-clave="${clave}" data-idx="${i}">
      <header class="hz-conflicto-cab">
        <div>
          <strong class="hz-conflicto-grupo">${esc(c.grupo)}</strong>
          <span class="hz-conflicto-sub">${esc(c.nombre_grupo)}</span>
        </div>
        <div class="hz-conflicto-cuando"><strong>${esc(c.dia_nombre)}</strong> · ${esc(fraseFranja(c.hora))}</div>
        <button type="button" class="boton-texto-chico" data-ver-grupo="${c.grado}|${c.curso ?? ""}" title="Ver el horario completo de este grupo">Ver horario del grupo →</button>
      </header>
      <p class="hz-conflicto-porque">Dos docentes aparecen dictando a este grupo <strong>a la misma hora</strong>. ${gestiona ? "Elige quién es el oficial, o deja los dos si de verdad la comparten." : "Un coordinador debe resolverlo."}</p>
      <div class="hz-conflicto-opciones" role="radiogroup" aria-label="Docente oficial">
        ${c.opciones
          .map(
            (o) => `
          <label class="hz-opcion ${gestiona ? "" : "solo-lectura"}">
            <input type="radio" name="conf-${i}" value="${o.bloque_id}" ${gestiona ? "" : "disabled"} />
            <span class="hz-opcion-cuerpo">
              <strong>${esc(o.docente_nombre)}</strong>
              <span class="hz-opcion-area">${esc(o.area_label)}</span>
              <span class="hz-opcion-origen" title="Archivo del que se importó esta clase">${esc(o.origen)}</span>
            </span>
          </label>`
          )
          .join("")}
      </div>
      ${gestiona ? `
      <div class="hz-conflicto-acciones">
        <button type="button" class="boton" data-conf-oficial disabled>Confirmar como oficial</button>
        <button type="button" class="boton secundario" data-conf-ambos title="Se mantienen las dos clases (docencia compartida)">Dejar los dos</button>
        <span class="conflicto-resultado" role="status"></span>
      </div>` : ""}
    </article>`;
}

function vincularTarjetaConflicto(card, alResolver) {
  const [grado, curso, dia, hora] = card.dataset.clave.split("|");
  const cuerpo = { anio_lectivo: horarioAnio, grado: Number(grado), curso: curso === "" ? null : Number(curso), dia: Number(dia), hora: Number(hora) };
  const resultado = card.querySelector(".conflicto-resultado");
  const btnOficial = card.querySelector("[data-conf-oficial]");
  const btnAmbos = card.querySelector("[data-conf-ambos]");
  if (!btnOficial) return; // solo lectura

  card.querySelectorAll("input[type=radio]").forEach((r) =>
    r.addEventListener("change", () => {
      card.querySelectorAll(".hz-opcion").forEach((o) => o.classList.toggle("elegida", o.querySelector("input").checked));
      const nombre = r.closest(".hz-opcion").querySelector("strong").textContent;
      btnOficial.disabled = false;
      btnOficial.textContent = `Confirmar a ${nombreCortoHorario(nombre)} como oficial`;
      resultado.textContent = "";
    })
  );

  const enviar = async (payload, mensaje) => {
    btnOficial.disabled = btnAmbos.disabled = true;
    resultado.className = "conflicto-resultado";
    resultado.textContent = "Guardando…";
    try {
      await api("/api/horario/conflictos/resolver", { method: "POST", body: JSON.stringify({ ...cuerpo, ...payload }) });
      alResolver(card, mensaje);
    } catch (e) {
      resultado.textContent = `${e.message}`;
      resultado.className = "conflicto-resultado error";
      btnAmbos.disabled = false;
      btnOficial.disabled = !card.querySelector("input[type=radio]:checked");
      horarioNotificar(`No se pudo completar la operación: ${e.message}`, "error");
    }
  };
  btnOficial.addEventListener("click", () => {
    const sel = card.querySelector("input[type=radio]:checked");
    if (!sel) { resultado.textContent = "Marca cuál docente es el oficial."; resultado.className = "conflicto-resultado error"; return; }
    const nombre = sel.closest(".hz-opcion").querySelector("strong").textContent;
    enviar({ accion: "oficial", bloque_id: Number(sel.value) }, `${nombreCortoHorario(nombre)} quedó como oficial`);
  });
  btnAmbos.addEventListener("click", () => enviar({ accion: "ambos" }, "Se mantienen los dos docentes"));
}

async function renderHorarioConflictos(cont, tok) {
  const todos = [...(await hzConflictos(true))];
  if (!hzVigente(tok)) return;
  hzActualizarBadgeConflictos();
  let lista = todos;
  const resueltos = () => hzConflictosResueltos;
  const inicial = () => lista.length + hzConflictosResueltos;

  const pintar = () => {
    if (!lista.length) {
      cont.innerHTML = `${hzTitulo("Conflictos de horario", "Dos docentes para el mismo grupo y hora.")}
        ${hzVacio({
          icono: "<i data-lucide=circle-check class=ico></i> ",
          titulo: resueltos() ? `Listo: resolviste ${resueltos()} conflicto(s)` : "No hay conflictos pendientes",
          texto: "Todos los grupos tienen un docente confirmado por franja, o se revisó la coexistencia.",
          tono: "exito",
          acciones: [{ id: "hoy", texto: "Volver a Hoy", primaria: true }],
        })}`;
      hzVincularAcciones(cont, { hoy: () => irASeccionHorario("hoy") });
      return;
    }
    const porDia = DIAS_HORARIO.map(([d, n]) => ({ d, n, items: lista.filter((c) => c.dia === d) })).filter((x) => x.items.length);
    // Si ya no queda ninguno en el día filtrado, se vuelve a «Todos».
    if (hzConflictosDia && !porDia.some((x) => String(x.d) === String(hzConflictosDia))) hzConflictosDia = "";
    const visibles = hzConflictosDia ? porDia.filter((x) => String(x.d) === String(hzConflictosDia)) : porDia;
    let idx = 0;
    cont.innerHTML = `
      ${hzTitulo("Conflictos de horario", "Dos docentes para el mismo grupo y hora, según los archivos importados.")}
      <section class="hz-conflictos-resumen ${lista.length ? "alerta" : "ok"}">
        <div class="hz-conflictos-num"><strong>${lista.length}</strong><span data-hz-pend-txt>pendiente${lista.length === 1 ? "" : "s"}</span></div>
        <div class="hz-conflictos-texto">
          Hasta que se resuelvan, esas clases <strong>no cuentan</strong> para «libres» ni para reemplazos.
          <span class="hz-progreso" data-hz-progreso ${resueltos() ? "" : "hidden"}>Llevas ${resueltos()} de ${inicial()} resueltos.</span>
        </div>
        <div class="hz-progreso-barra" aria-hidden="true"><span style="width:${Math.round((resueltos() / inicial()) * 100)}%"></span></div>
      </section>
      <div class="hz-filtro-dia no-imprimir">
        ${hzSegmentado("conf-dia", [{ v: "", t: "Todos", n: lista.length }, ...porDia.map((x) => ({ v: x.d, t: x.n, n: x.items.length }))], hzConflictosDia)}
      </div>
      ${visibles.map((x) => `
        <section class="hz-conflictos-dia">
          <h3 class="hz-panel-titulo">${x.n} <span class="hz-contador">${x.items.length}</span></h3>
          <div class="hz-conflictos-grid">${x.items.map((c) => tarjetaConflictoHtml(c, idx++)).join("")}</div>
        </section>`).join("")}
    `;
    hzVincularSeg(cont, "conf-dia", (v) => { hzConflictosDia = v; pintar(); });
    cont.querySelectorAll(".hz-conflicto").forEach((card) => vincularTarjetaConflicto(card, alResolver));
    cont.querySelectorAll("[data-ver-grupo]").forEach((b) =>
      b.addEventListener("click", () => {
        const [g, c] = b.dataset.verGrupo.split("|");
        horarioGrupoSel = { grado: Number(g), curso: c === "" ? null : Number(c) };
        hzUltimaPorGrupo.consultar = "grupo";
        irASeccionHorario("grupo");
      })
    );
  };

  // Resolver actualiza la lista en el sitio: la tarjeta pasa a "resuelto",
  // los contadores bajan y no se recarga toda la pantalla.
  const alResolver = (card, mensaje) => {
    const clave = card.dataset.clave;
    hzConflictosResueltos += 1;
    lista = lista.filter((c) => `${c.grado}|${c.curso ?? ""}|${c.dia}|${c.hora}` !== clave);
    hzCache.conflictos[horarioAnio] = lista;
    hzInvalidar("bloques"); // la rejilla cambió (uno quedó descartado)
    horarioConflictosN = lista.length;
    hzActualizarBadgeConflictos();
    // El resumen se actualiza al instante; la lista se repinta un momento después.
    const num = cont.querySelector(".hz-conflictos-num strong");
    if (num) num.textContent = lista.length;
    const pend = cont.querySelector("[data-hz-pend-txt]");
    if (pend) pend.textContent = lista.length === 1 ? "pendiente" : "pendientes";
    const prog = cont.querySelector("[data-hz-progreso]");
    if (prog) { prog.hidden = false; prog.textContent = `Llevas ${resueltos()} de ${inicial()} resueltos.`; }
    const barra = cont.querySelector(".hz-progreso-barra span");
    if (barra) barra.style.width = `${Math.round((resueltos() / inicial()) * 100)}%`;
    card.classList.add("resuelto");
    card.innerHTML = `<div class="hz-conflicto-ok"><span aria-hidden="true"><i data-lucide=check class=ico></i> </span> ${esc(mensaje)}</div>`;
    horarioNotificar(`Conflicto actualizado · ${lista.length ? `quedan ${lista.length} pendiente(s)` : "no quedan pendientes"}`);
    setTimeout(pintar, 1100);
  };

  if (!lista.length) { pintar(); return; }
  pintar();
}

// ==========================================================================
//  Modales: ausencia y reemplazo
// ==========================================================================

async function abrirModalAusencia(fecha) {
  const docentes = await hzDocentes();
  const cont = hzAbrirModal("Registrar ausencia", `
    <form id="form-ausencia" class="form-vertical">
      <label>Docente
        ${comboBuscableHtml("ausencia-docente", { hiddenName: "docente_id", placeholder: "Escribe para buscar docente…" })}
      </label>
      <label>Fecha
        <input type="date" name="fecha" value="${fecha}" required />
      </label>
      <label>Motivo (opcional)
        <input type="text" name="motivo" placeholder="Cita médica, permiso…" />
      </label>
      <p class="modal-error hz-nota" role="alert" hidden></p>
      <div class="modal-acciones">
        <button type="button" class="boton secundario" data-hz-cerrar>Cancelar</button>
        <button type="submit" class="boton">Registrar y ver clases afectadas</button>
      </div>
    </form>`);
  cont.querySelectorAll("[data-hz-cerrar]").forEach((b) => b.addEventListener("click", hzCerrarModal));
  vincularComboBuscable("ausencia-docente", docentes.map((d) => ({ id: d.id, texto: d.nombre_completo })));
  document.getElementById("ausencia-docente").focus();
  document.getElementById("form-ausencia").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const docenteId = Number(fd.get("docente_id"));
    const aviso = cont.querySelector(".modal-error");
    if (!docenteId) {
      aviso.textContent = "Elige un docente de la lista.";
      aviso.hidden = false;
      return;
    }
    const fechaAusencia = fd.get("fecha");
    const boton = e.target.querySelector('[type="submit"]');
    boton.disabled = true;
    try {
      const res = await api("/api/horario/ausencias", {
        method: "POST",
        body: JSON.stringify({ docente_id: docenteId, fecha: fechaAusencia, motivo: fd.get("motivo") || null }),
      });
      hzCerrarModal();
      horarioFecha = fechaAusencia; // el panel salta a la fecha de la ausencia
      irASeccionHorario("hoy");
      horarioNotificar(
        res.clases_afectadas.length
          ? "Ausencia registrada; se prepararon las clases afectadas."
          : `Ausencia registrada. ${res.docente_nombre} no tiene clases ese día, así que no hay reemplazos por gestionar.`,
        res.clases_afectadas.length ? "ok" : "warn"
      );
    } catch (err) {
      aviso.textContent = `${err.message}`;
      aviso.hidden = false;
      boton.disabled = false;
    }
  });
}

async function abrirModalReemplazo(bloqueId, fecha, reemplazoId = null) {
  hzAbrirModal("Buscar reemplazo", hzCargando("Analizando candidatos…"), { ancha: true });
  const cont = document.getElementById("horario-modal");
  let data;
  try {
    data = await api(`/api/horario/reemplazos/candidatos?bloque_id=${bloqueId}&fecha=${fecha}`);
  } catch (e) {
    cont.querySelector(".modal-caja").insertAdjacentHTML("beforeend", "");
    cont.querySelector(".hz-cargando").outerHTML = hzVacio({ icono: "<i data-lucide=triangle-alert class=ico></i> ", titulo: "No se pudieron cargar los candidatos", texto: esc(e.message), tono: "error" });
    return;
  }

  const b = data.bloque;
  const horas = data.horas && data.horas.length ? data.horas : [b.hora];
  const esDoble = horas.length > 1;
  const medallas = ["<i data-lucide=medal class=ico></i> ", "<i data-lucide=medal class=ico></i> ", "<i data-lucide=medal class=ico></i> "];

  const tarjeta = (c, i) => {
    const razones = c.razones.map((r) => `<li class="razon ${r.tipo}">${r.tipo === "ok" ? "<i data-lucide=check class=ico></i> " : "<i data-lucide=triangle-alert class=ico></i> "} ${esc(r.texto)}</li>`).join("");
    const cobertura = esDoble
      ? c.cubre_bloque_completo
        ? `<span class="badge-estado ok"><i data-lucide=check class=ico></i> Cubre las ${c.horas_total} horas</span>`
        : `<span class="badge-estado proceso">Solo ${c.horas_libres} de ${c.horas_total} horas</span>`
      : "";
    return `<div class="candidato-card ${esDoble && !c.cubre_bloque_completo ? "candidato-parcial" : ""}" data-completo="${c.cubre_bloque_completo ? 1 : 0}">
        <div class="candidato-head">
          <span class="candidato-nombre">${medallas[i] || ""} ${esc(c.nombre_completo)}</span>
          <span class="candidato-pct">${c.porcentaje}%</span>
        </div>
        <div class="barra-progreso"><div class="barra-progreso-relleno" style="width:${c.porcentaje}%"></div></div>
        ${cobertura}
        <ul class="razones-lista">${razones}</ul>
        <button type="button" class="boton candidato-asignar" data-asignar="${c.docente_id}">Asignar</button>
      </div>`;
  };
  const tarjetas = data.candidatos.length
    ? data.candidatos.map(tarjeta).join("")
    : hzVacio({ icono: "<i data-lucide=search class=ico></i> ", titulo: "No hay docentes disponibles sin conflicto para esta franja", texto: "Prueba con otra fecha o revisa las ausencias del día." });

  cont.querySelector(".modal-caja").innerHTML = `
    <header class="est-modal-head">
      <h3>${etiquetaGrupoHorario(b.grado, b.curso)} · ${esc(b.area_label)} · ${rangoHoras(horas)} hora${esDoble ? "s" : ""}</h3>
      <button type="button" class="est-visor-cerrar" data-hz-cerrar aria-label="Cerrar"></button>
    </header>
    <p class="hz-nota">
      ${nombreDiaHorario(b.dia)} ${fecha} · ${esc(data.nivel || nivelDeGrado(b.grado))} — buscando quién cubre a <strong>${esc(b.docente_nombre)}</strong>
      ${esDoble ? `<br><strong>Bloque de ${horas.length} horas seguidas.</strong> Se prioriza a quien esté libre las ${horas.length}.` : ""}
    </p>
    ${esDoble ? `<label class="check-linea" style="margin-bottom:10px"><input type="checkbox" id="chk-solo-completo" /> Mostrar solo los que cubren el bloque completo</label>` : ""}
    <div class="candidatos-grid" id="candidatos-grid">${tarjetas}</div>`;

  cont.querySelector("[data-hz-cerrar]").addEventListener("click", hzCerrarModal);
  document.getElementById("chk-solo-completo")?.addEventListener("change", (e) => {
    cont.querySelectorAll("#candidatos-grid .candidato-card").forEach((card) => {
      card.hidden = e.target.checked && card.dataset.completo !== "1";
    });
  });
  hzVincularAcciones(cont, {});
  cont.querySelectorAll("[data-asignar]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = "Asignando…";
      const did = Number(btn.dataset.asignar);
      try {
        if (reemplazoId) {
          // "Cambiar": re-asigna cada hora del bloque al nuevo reemplazante.
          for (const id of String(reemplazoId).split(",")) {
            await api(`/api/horario/reemplazos/${id}`, { method: "PATCH", body: JSON.stringify({ docente_reemplazo_id: did }) });
          }
        } else {
          await api("/api/horario/reemplazos", { method: "POST", body: JSON.stringify({ bloque_horario_id: bloqueId, fecha, docente_reemplazo_id: did }) });
        }
        horarioNotificar("Reemplazo registrado.");
        hzCerrarModal();
        hzRepintarSeccionSuave();
      } catch (err) {
        horarioNotificar(`No se pudo completar la operación: ${err.message}`, "error");
        btn.disabled = false;
        btn.textContent = "Asignar";
      }
    })
  );
}

// Delegación única: chips "ver docente" (Disponibilidad).
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-ver-docente]");
  if (!b || vistaActual !== "horario") return;
  horarioDocenteId = Number(b.dataset.verDocente);
  hzUltimaPorGrupo.consultar = "docente";
  irASeccionHorario("docente");
});
