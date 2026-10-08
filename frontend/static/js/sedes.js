// --- Vista: Sedes -----------------------------------------------------------
//
// Contexto por defecto: IETABA y sus sedes asociadas. La pertenencia NO se
// deduce del nombre ni de ninguna lista quemada: se usa el campo
// `pertenece_ietaba` de la tabla `sedes` (backend/app/models.py), que se
// detecta al importar desde la columna "INSTITUCIÓN Y/O CENTRO EDUCATIVO" y
// queda editable con PATCH /api/sedes/{id}. Es el mismo criterio que ya usa
// el backend en generar_reporte(solo_ietaba=True), conciliación y los
// pendientes de boletín, y viaja en SedeResumen.
//
// El conmutador de contexto es UX, no seguridad: /api/sedes ya devuelve lo
// que el backend autoriza a ver (hoy, con `sedes.ver`, todas — la
// restricción por sede de rbac.sedes_permitidas() está preparada pero
// deliberadamente sin activar). Cambiar el filtro no da acceso a nada nuevo.

const CONTEXTOS_SEDE = [
  { id: "ietaba", nombre: "IETABA y asociadas", prueba: (s) => s.pertenece_ietaba },
  { id: "todas", nombre: "Todas las instituciones", prueba: () => true },
];

let sedesVistaCache = null;
let sedesContexto = "ietaba"; // por defecto, lo pedido: solo IETABA y asociadas
let sedesBusqueda = "";

function contextoSedeActual() {
  return CONTEXTOS_SEDE.find((c) => c.id === sedesContexto) || CONTEXTOS_SEDE[0];
}

// "SEDE # 17  ALTO GUEMBIAMBI" -> { numero: "17", nombre: "ALTO GUEMBIAMBI" }
// El número es como el personal se refiere a las sedes, así que se conserva
// (antes se borraba con un replace). Si el nombre no lleva el prefijo, se
// devuelve entero y sin número.
function partesNombreSede(nombre) {
  const m = String(nombre).match(/^\s*SEDE\s*#?\s*(\d+)\s*(.*)$/i);
  return m ? { numero: m[1], nombre: m[2].trim() || nombre } : { numero: null, nombre };
}

// Un solo buscador, que siempre opera DENTRO del contexto elegido.
function sedesVisibles() {
  const contexto = contextoSedeActual();
  const q = normalizarTexto(sedesBusqueda.trim());
  return (sedesVistaCache || []).filter((s) => {
    if (!contexto.prueba(s)) return false;
    if (!q) return true;
    return (
      normalizarTexto(s.nombre).includes(q) ||
      normalizarTexto(s.resguardo).includes(q) ||
      normalizarTexto(s.institucion_centro_educativo).includes(q)
    );
  });
}

function totalesDe(sedes) {
  return {
    sedes: sedes.length,
    estudiantes: sedes.reduce((a, s) => a + s.total_estudiantes, 0),
    activos: sedes.reduce((a, s) => a + s.total_activos, 0),
  };
}

const numeroConMiles = (n) => n.toLocaleString("es-CO");

async function renderSedes() {
  app.innerHTML = '<p class="estado-carga">Cargando sedes...</p>';
  try {
    sedesVistaCache = await api("/api/sedes");
  } catch (e) {
    app.innerHTML = `<div class="alerta-caja">${
      e.status === 401 || e.status === 403
        ? "No tienes permiso para ver las sedes."
        : "No se pudieron cargar las sedes: " + esc(e.message)
    }</div>`;
    return;
  }

  app.innerHTML = sedesHtml();
  vincularSedes();
}

function sedesHtml() {
  const contexto = contextoSedeActual();
  const visibles = sedesVisibles();
  const t = totalesDe(visibles);

  return `
    <div class="pagina-header">
      <div>
        <h1>Sedes</h1>
        <p class="subtitulo-pagina">${esc(contexto.nombre)}. Entra a una sede para ver sus estudiantes.</p>
      </div>
    </div>

    <div class="barra-filtros">
      <div class="segmentado" role="group" aria-label="Contexto institucional">
        ${CONTEXTOS_SEDE.map((c) => {
          const n = (sedesVistaCache || []).filter(c.prueba).length;
          return `<button type="button" class="segmentado-btn ${sedesContexto === c.id ? "activo" : ""}" data-contexto-sede="${c.id}">
                    ${esc(c.nombre)} <span class="segmentado-num">${n}</span>
                  </button>`;
        }).join("")}
      </div>
    </div>

    <div class="buscador-principal">
      <span class="buscador-principal-icono" aria-hidden="true"><i data-lucide=search class=ico></i> </span>
      <input type="text" id="buscar-sede" placeholder="Buscar por nombre, resguardo o institución..." value="${esc(sedesBusqueda)}" />
    </div>

    <div class="resumen-reportes resumen-compacta" id="resumen-sedes">${resumenSedesHtml(t)}</div>

    <div id="lista-sedes">${gridSedesHtml(visibles)}</div>
  `;
}

// Los contadores responden al contexto Y a la búsqueda: nunca muestran
// números de un conjunto que no es el que se está viendo.
function resumenSedesHtml(t) {
  const inactivos = t.estudiantes - t.activos;
  return `
    <div class="metric-card"><span>Sedes</span><strong>${numeroConMiles(t.sedes)}</strong></div>
    <div class="metric-card"><span>Estudiantes</span><strong>${numeroConMiles(t.estudiantes)}</strong></div>
    <div class="metric-card ok"><span>Activos</span><strong>${numeroConMiles(t.activos)}</strong></div>
    <div class="metric-card ${inactivos ? "alerta" : ""}"><span>Inactivos</span><strong>${numeroConMiles(inactivos)}</strong></div>`;
}

function gridSedesHtml(sedes) {
  if (!sedes.length) return estadoVacioSedesHtml();
  return `<div class="grid-sedes">${sedes.map(tarjetaSede).join("")}</div>`;
}

function estadoVacioSedesHtml() {
  if (sedesBusqueda.trim()) {
    return `
      <div class="estado-vacio">
        <div class="estado-vacio-icono" aria-hidden="true"><i data-lucide=search class=ico></i> </div>
        <h3>Ninguna sede coincide con «${esc(sedesBusqueda.trim())}»</h3>
        <p>Estás buscando dentro de «${esc(contextoSedeActual().nombre)}».
           ${sedesContexto === "ietaba" ? "Prueba en «Todas las instituciones»." : "Prueba con otro término."}</p>
      </div>`;
  }
  return `
    <div class="estado-vacio">
      <div class="estado-vacio-icono" aria-hidden="true"><i data-lucide=school class=ico></i> </div>
      <h3>No hay sedes en este contexto</h3>
      <p>No se encontró ninguna sede marcada como «${esc(contextoSedeActual().nombre)}».</p>
    </div>`;
}

function tarjetaSede(s) {
  const { numero, nombre } = partesNombreSede(s.nombre);
  const inactivos = s.total_estudiantes - s.total_activos;
  // La institución solo aporta cuando se están viendo varias: además los
  // números de sede se repiten entre instituciones (hay dos "SEDE # 11"),
  // así que ahí es necesaria para distinguirlas.
  const mostrarInstitucion = sedesContexto === "todas" && s.institucion_centro_educativo;

  return `
    <button type="button" class="tarjeta-sede" data-sede-id="${s.id}" aria-label="Abrir ${esc(s.nombre)}">
      <div class="tarjeta-sede-cabecera">
        ${numero ? `<span class="tarjeta-sede-numero">#${esc(numero)}</span>` : ""}
        <h3 class="tarjeta-sede-nombre">${esc(nombre)}</h3>
      </div>
      <p class="tarjeta-sede-territorio">${esc(s.resguardo || "Sin resguardo registrado")}</p>
      ${mostrarInstitucion ? `<p class="tarjeta-sede-institucion">${esc(s.institucion_centro_educativo)}</p>` : ""}
      <div class="tarjeta-sede-pie">
        ${
          s.total_estudiantes
            ? `<span class="tarjeta-sede-total">${numeroConMiles(s.total_estudiantes)}<small>estudiantes</small></span>
               <span class="tarjeta-sede-estados">
                 <span class="est-chip ok">${numeroConMiles(s.total_activos)} activos</span>
                 ${inactivos > 0 ? `<span class="est-chip error">${numeroConMiles(inactivos)} inactivos</span>` : ""}
               </span>`
            : '<span class="tarjeta-sede-vacia">Sin estudiantes registrados</span>'
        }
      </div>
    </button>`;
}

// Solo repinta la rejilla y los contadores: al escribir no se reconstruye la
// pantalla ni se pierde el foco del buscador.
function refrescarListaSedes() {
  const visibles = sedesVisibles();
  document.getElementById("lista-sedes").innerHTML = gridSedesHtml(visibles);
  document.getElementById("resumen-sedes").innerHTML = resumenSedesHtml(totalesDe(visibles));
  vincularClicksSede();
}

function vincularSedes() {
  document.getElementById("buscar-sede").addEventListener("input", (e) => {
    sedesBusqueda = e.target.value;
    refrescarListaSedes();
  });
  document.querySelectorAll("[data-contexto-sede]").forEach((btn) => {
    btn.addEventListener("click", () => {
      sedesContexto = btn.dataset.contextoSede;
      renderSedes();
    });
  });
  vincularClicksSede();
}

function vincularClicksSede() {
  document.querySelectorAll(".tarjeta-sede").forEach((card) => {
    card.addEventListener("click", () => {
      sedeSeleccionada = Number(card.dataset.sedeId);
      gradoSeleccionado = null;
      divisionSeleccionada = null;
      paginaActual = 1;
      vistaActual = "estudiantes";
      tabs.forEach((t) => t.classList.remove("activo"));
      document.querySelector('[data-vista="estudiantes"]').classList.add("activo");
      render();
    });
  });
}
