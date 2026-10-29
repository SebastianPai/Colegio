// --- Núcleo de la app: estado global, navegación entre pestañas y helpers ---
// --- que usa más de una vista. Se carga justo después de comun.js (ver   ---
// --- index.html), que trae api(), fechaColombiaISO() y esc(). Cada       ---
// --- vista vive en su propio archivo bajo static/js/.                    ---

const app = document.getElementById("app");
const tabs = document.querySelectorAll(".tab");

let vistaActual = "estudiantes"; // la pantalla principal es buscar estudiantes
let sedeSeleccionada = null;
let gradoSeleccionado = null;
let divisionSeleccionada = null; // null = general (todo el grado, todas las divisiones)
let fichaEstudianteId = null;
let vistaAnterior = "estudiantes";

// Fase 4.0: la llama auth.js al cerrar sesión o cuando expira sin poder
// renovarse, para que la próxima persona que inicie sesión en este mismo
// equipo/pestaña no herede la vista, los filtros ni el contenido ya
// renderizado de la sesión anterior.
function resetearEstadoNavegacion() {
  vistaActual = "estudiantes";
  sedeSeleccionada = null;
  gradoSeleccionado = null;
  divisionSeleccionada = null;
  fichaEstudianteId = null;
  vistaAnterior = "estudiantes";
  if (typeof dkVista !== "undefined") {
    dkVista = "inicio";
    dkCursoSel = null;
    dkEstudianteSel = null;
    dkBloqueDatos = null;
  }
  if (typeof orVista !== "undefined") {
    orVista = "bandeja";
    orGradoSel = null;
    orEstudianteSel = null;
  }
  if (typeof fichaModoDocente !== "undefined") fichaModoDocente = false;
  tabs.forEach((t) => t.classList.remove("activo"));
  document.querySelector('[data-vista="estudiantes"]')?.classList.add("activo");
  app.innerHTML = "";
}

const TIPOS_DOCUMENTO = ["C.C.", "T.I.", "R.C."];

const NOMBRES_GRADOS = [
  [0, "Preescolar"], [1, "Primero"], [2, "Segundo"], [3, "Tercero"], [4, "Cuarto"],
  [5, "Quinto"], [6, "Sexto"], [7, "Séptimo"], [8, "Octavo"], [9, "Noveno"],
  [10, "Décimo"], [11, "Once"],
];

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    if (typeof dkConfirmarSalirSinGuardar !== "undefined" && vistaActual === "docente" && !dkConfirmarSalirSinGuardar()) {
      return;
    }
    tabs.forEach((t) => t.classList.remove("activo"));
    tab.classList.add("activo");
    vistaActual = tab.dataset.vista;
    // Al salir de la pantalla, se olvida el estudiante resaltado en la grilla.
    if (typeof grillaResaltarDoc !== "undefined") grillaResaltarDoc = null;
    if (typeof grillaVolverA !== "undefined") grillaVolverA = null;
    if (vistaActual === "sedes") {
      sedeSeleccionada = null;
      gradoSeleccionado = null;
      divisionSeleccionada = null;
    }
    if (vistaActual === "docente" && typeof dkVista !== "undefined") {
      dkVista = tab.dataset.dkVista || "inicio";
      dkCursoSel = null;
      dkEstudianteSel = null;
    }
    if (vistaActual === "orientacion" && typeof orVista !== "undefined") {
      orVista = tab.dataset.orVista || "bandeja";
      orGradoSel = null;
      orEstudianteSel = null;
    }
    paginaActual = 1;
    mostrarImprimir = false;
    cerrarSidebarMovil();
    render();
  });
});

// --- Sidebar: colapsar en escritorio / drawer en móvil ---------------------
// Puramente visual (no toca vistaActual ni la lógica de negocio de arriba).

const sidebar = document.getElementById("sidebar");
const sidebarOverlay = document.getElementById("sidebar-overlay");
const btnAbrirSidebar = document.getElementById("btn-abrir-sidebar");
const btnColapsarSidebar = document.getElementById("btn-colapsar-sidebar");

function cerrarSidebarMovil() {
  sidebar.classList.remove("abierta");
  sidebarOverlay.hidden = true;
  btnAbrirSidebar?.setAttribute("aria-expanded", "false");
}

btnAbrirSidebar?.addEventListener("click", () => {
  sidebar.classList.add("abierta");
  sidebarOverlay.hidden = false;
  btnAbrirSidebar.setAttribute("aria-expanded", "true");
});

sidebarOverlay?.addEventListener("click", cerrarSidebarMovil);

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") cerrarSidebarMovil();
});

btnColapsarSidebar?.addEventListener("click", () => {
  const colapsada = sidebar.classList.toggle("colapsada");
  document.body.classList.toggle("sidebar-colapsada", colapsada);
  btnColapsarSidebar.setAttribute("aria-expanded", String(!colapsada));
  try {
    localStorage.setItem("ietaba_sidebar_colapsada", colapsada ? "1" : "0");
  } catch {
    /* almacenamiento no disponible (modo privado, etc.): no es crítico */
  }
});

try {
  if (localStorage.getItem("ietaba_sidebar_colapsada") === "1") {
    sidebar.classList.add("colapsada");
    document.body.classList.add("sidebar-colapsada");
    btnColapsarSidebar?.setAttribute("aria-expanded", "false");
  }
} catch {
  /* almacenamiento no disponible: se abre expandida por defecto */
}

// api(), fechaColombiaISO() y esc() viven en comun.js (compartidas con la
// futura app docente).

let _vistaRenderizada = null;

// Un solo render() para toda la app. Si se vuelve a pintar la MISMA vista
// (guardar un cambio, un filtro, paginación…) se conserva la posición de
// scroll; si se cambia de vista, se sube al inicio. Así ninguna pantalla
// "salta arriba" al guardar algo.
async function render() {
  const scrollPrevio = window.scrollY;
  const mismaVista = vistaActual === _vistaRenderizada;
  _vistaRenderizada = vistaActual;
  await renderVistaActual();
  window.scrollTo(0, mismaVista ? scrollPrevio : 0);
}

async function renderVistaActual() {
  if (vistaActual === "sedes") return renderSedes();
  if (vistaActual === "estudiantes") return renderEstudiantes();
  if (vistaActual === "reportes") return renderReportes();
  if (vistaActual === "constancias") return renderConstancias();
  if (vistaActual === "boletines") return renderBoletines();
  if (vistaActual === "horario") return renderHorario();
  if (vistaActual === "notas") return renderNotas();
  if (vistaActual === "agregar") return renderAgregar();
  if (vistaActual === "ficha") return renderFicha();
  if (vistaActual === "admin") return renderAdmin();
  if (vistaActual === "alertas") return renderAlertas();
  if (vistaActual === "docente") return renderDocente();
  if (vistaActual === "orientacion") return renderOrientacion();
  if (vistaActual === "asistencia") return renderAsistenciaGeneral();
  if (vistaActual === "analisis") return renderAnalisis();
  if (vistaActual === "icfes") return renderIcfes();
}

function abrirFicha(estudianteId, origen) {
  fichaEstudianteId = estudianteId;
  vistaAnterior = origen || vistaActual;
  vistaActual = "ficha";
  // Solo el llamado desde docente.js (director de grupo) pone
  // fichaModoDocente = true justo antes de invocar esta función; cualquier
  // otro origen (Listado, Alertas, Reportes...) es siempre modo administrador.
  if (typeof fichaModoDocente !== "undefined" && origen !== "docente") fichaModoDocente = false;
  // No se apaga la pestaña del menú: el detalle cuelga de donde se vino
  // (Listado, Alertas, Reportes) y "Volver" regresa allí. Antes quedaba el
  // menú sin ninguna sección marcada, también al volver.
  render();
}

// --- Búsquedas que ignoran tildes y diéresis --------------------------------
// Muchos nombres del territorio llevan ñ o ü (PEÑA BLANCA, CARAÑO, ÑAMBI,
// GUIGÜAY) y nadie los escribe así al buscar a las carreras. Se comparan las
// dos partes sin marcas diacríticas para que "pena blanca" encuentre "PEÑA
// BLANCA". La ñ se conserva como n, que es justo lo que se quiere aquí.

function normalizarTexto(valor) {
  return String(valor ?? "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

// --- Permisos en la interfaz -----------------------------------------------
// NUNCA es seguridad: el backend vuelve a comprobar cada permiso (las rutas
// de /api/admin/* responden 403). Esto solo evita ofrecer acciones que la
// persona no va a poder completar. sesionActual lo llena auth.js desde
// /api/auth/yo. A diferencia de _aplicarVisibilidadPorPermisos(), que corre
// una sola vez al entrar sobre el HTML estático, esto sirve para el HTML que
// cada vista pinta después.

function tienePermiso(codigo) {
  return !!(typeof sesionActual !== "undefined" && sesionActual?.usuario?.permisos?.includes(codigo));
}

// --- Helpers: tipo de documento con opción "Otro" (Agregar + Ficha) --------

function tipoDocumentoSelectHtml(name, valorActual) {
  const esConocido = TIPOS_DOCUMENTO.includes(valorActual);
  return `
    <label>Tipo de documento
      <select name="${name}" id="${name}_select">
        <option value="">Sin definir</option>
        ${TIPOS_DOCUMENTO.map(
          (t) => `<option value="${t}" ${valorActual === t ? "selected" : ""}>${t}</option>`
        ).join("")}
        <option value="__otro__" ${!esConocido && valorActual ? "selected" : ""}>Otro</option>
      </select>
    </label>
    <label id="${name}_otro_campo" style="${!esConocido && valorActual ? "" : "display:none"}">
      Especifica cuál
      <input type="text" name="${name}_otro" value="${!esConocido && valorActual ? valorActual : ""}" />
    </label>
  `;
}

function vincularTipoDocumentoOtro(name) {
  const select = document.getElementById(`${name}_select`);
  const campoOtro = document.getElementById(`${name}_otro_campo`);
  select?.addEventListener("change", () => {
    campoOtro.style.display = select.value === "__otro__" ? "" : "none";
  });
}

function valorTipoDocumento(datos, name) {
  return datos[`${name}`] === "__otro__" ? datos[`${name}_otro`] : datos[`${name}`];
}

// --- Membrete oficial reutilizable (Estudiantes y Boletines lo comparten) --

// Membrete oficial reutilizable (mismo texto y logos que trae la plantilla
// de constancias), para que cualquier informe impreso se vea consistente.
function membreteHtml(titulo) {
  return `
    <div class="hoja-encabezado membrete">
      <img src="/static/logos/logo1.jpg" alt="UNIPA" />
      <div class="titulo">
        <p>UNIDAD INDIGENA DEL PUEBLO AWA "UNIPA"</p>
        <p>INSTITUCION EDUCATIVA INDIGENA TECNICA AGROAMBIENTAL BILINGÜE AWA "IETABA"</p>
        <p class="membrete-chico">Licencia de Funcionamiento No. 398 del 28 de abril del 2004</p>
        <p class="membrete-chico">Emanada de la Secretaría Departamental de Educación y Cultura de Nariño</p>
        <p class="membrete-chico">Código DANE 25207900204501 - NIT. 900000095-4</p>
        <p class="membrete-lema">Ambiente – Cultura – Ciencia</p>
        ${titulo ? `<div class="lista-asistencia">${titulo}</div>` : ""}
      </div>
      <img src="/static/logos/logo2.jpeg" alt="IETABA" />
    </div>
  `;
}

// --- Menús desplegables que se cierran solos ---------------------------------
// El "⋮" de cada fila y el "Más filtros" son <details>: el navegador no los
// cierra al hacer clic fuera, así que se quedaban abiertos, y podían quedar
// varios a la vez. Fase de captura (true) porque el menú de fila frena la
// propagación de sus clics y un listener normal en document nunca los vería.
const SELECTOR_MENUS_AUTOCIERRE = "details.menu-fila[open], details.menu-mas-filtros[open]";

document.addEventListener(
  "click",
  (ev) => {
    document.querySelectorAll(SELECTOR_MENUS_AUTOCIERRE).forEach((d) => {
      if (!d.contains(ev.target)) d.open = false;
    });
  },
  true
);
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") document.querySelectorAll(SELECTOR_MENUS_AUTOCIERRE).forEach((d) => (d.open = false));
});

// El menú ⋮ vive dentro de tablas con overflow:hidden (esquinas redondeadas)
// o con scroll horizontal, que lo recortaban (con 1 o 2 resultados casi no se
// veía). Abierto, se posiciona fijo sobre la pantalla: debajo del botón, o
// encima si abajo no cabe. Al hacer scroll se cierra para no quedar flotando.
document.addEventListener(
  "toggle",
  (ev) => {
    const d = ev.target;
    if (!(d instanceof HTMLDetailsElement) || !d.classList.contains("menu-fila")) return;
    const lista = d.querySelector(".menu-herramientas-lista");
    if (!lista) return;
    if (!d.open) {
      lista.removeAttribute("style");
      return;
    }
    const boton = d.querySelector("summary").getBoundingClientRect();
    Object.assign(lista.style, { position: "fixed", top: "0px", left: "0px", right: "auto", bottom: "auto", zIndex: 1000 });
    const menu = lista.getBoundingClientRect();
    const abajo = boton.bottom + 6;
    const top = abajo + menu.height <= window.innerHeight - 8 ? abajo : Math.max(8, boton.top - 6 - menu.height);
    const left = Math.min(Math.max(8, boton.right - menu.width), window.innerWidth - menu.width - 8);
    Object.assign(lista.style, { top: `${top}px`, left: `${left}px` });
  },
  true
);
window.addEventListener(
  "scroll",
  (ev) => {
    if (ev.target instanceof Element && ev.target.closest(".menu-herramientas-lista")) return;
    document.querySelectorAll("details.menu-fila[open]").forEach((d) => (d.open = false));
  },
  true
);

// --- Ícono de ayuda "(?)" reutilizable --------------------------------------
// Para explicar en lenguaje simple qué significa un término técnico (ej.
// "Pendientes encontrados" en la auditoría SAPRED) sin saturar la pantalla:
// un botoncito "?" que al tocarlo muestra una burbuja de texto cortita.

function iconoAyuda(texto) {
  const seguro = String(texto).replace(/"/g, "&quot;");
  return `<button type="button" class="icono-ayuda" data-ayuda="${seguro}" aria-label="Qué significa esto">?</button>`;
}

let botonAyudaAbierto = null;

document.addEventListener("click", (e) => {
  document.querySelector(".ayuda-globo")?.remove();
  const btn = e.target.closest(".icono-ayuda");
  if (!btn || btn === botonAyudaAbierto) {
    botonAyudaAbierto = null;
    return;
  }
  botonAyudaAbierto = btn;
  const globo = document.createElement("div");
  globo.className = "ayuda-globo";
  globo.textContent = btn.dataset.ayuda;
  document.body.appendChild(globo);
  const r = btn.getBoundingClientRect();
  const anchoGlobo = globo.offsetWidth;
  let left = r.left + window.scrollX;
  const maxLeft = window.scrollX + document.documentElement.clientWidth - anchoGlobo - 8;
  globo.style.left = `${Math.max(8, Math.min(left, maxLeft))}px`;
  globo.style.top = `${r.bottom + window.scrollY + 6}px`;
});
