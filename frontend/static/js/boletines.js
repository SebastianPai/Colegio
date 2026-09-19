// --- Vista: Boletines (revisión académica) -----------------------------------
// Módulo con navegación interna propia (no son rutas globales, solo estado
// en memoria): Resumen | Grupos | Pendientes | Notas | Continuidad | SAPRED.
// Todas comparten año lectivo/período (cabecera del módulo) y los mismos
// endpoints/lógica que antes — esto es una reorganización de UI, no un
// cambio de arquitectura de datos.

let seccionBoletines = "resumen"; // resumen | grupos | pendientes | continuidad | sapred
let sapredSubvista = "hub"; // hub | importar | sincoincidencia | generarpdf

let filtroBoletinesAnio = new Date().getFullYear();
let filtroBoletinesPeriodo = 2;

// --- Grupos -------------------------------------------------------------
let filtroBoletinesSede = "";
let filtroBoletinesDocente = "";
let filtroBoletinesGrado = "";
let filtroBoletinesSoloPendientes = false;
let mostrarInformeBoletines = false;
let sedesAbiertasBoletines = null; // se inicializa la primera vez que se pinta la vista
let informeGrupoUnico = null; // clave de un solo grupo, para el informe "de un grupo" desde el modal

// --- Pendientes -----------------------------------------------------------
let pendientesFiltroSede = "";
let pendientesFiltroGrado = "";
let pendientesFiltroArea = "";
let pendientesFiltroSoloNoResueltos = true;
let busquedaFaltantes = "";
let mantenerFocoBuscarFaltantes = false;
let temporizadorBuscarFaltantes;
let pendientesSeleccionados = new Set(); // ids de PendienteBoletin marcados para exportar
let pendientesPagina = 1;
const PENDIENTES_POR_PAGINA = 50;

// --- Notas (vista propia en el menú principal: Resumen + Grilla) ------------
let seccionNotas = "resumen"; // resumen | grilla
let notasAnio = new Date().getFullYear();
let notasPeriodo = 2;

// Notas > Resumen (notas bajas/altas, estudiantes en riesgo)
let reporteNotasSedeSeleccionada = "";
let reporteNotasGradoSeleccionado = "";
let reporteNotasUmbralBajo = 3.0;
let reporteNotasUmbralAlto = 4.5;
let reporteNotasRiesgoMinimo = 2;

// Notas > Grilla (estudiante x área, formato tipo SAPRED)
let grillaSedeSeleccionada = null;
let grillaGradoSeleccionado = 0;
let grillaCursoSeleccionado = ""; // "" = todas las secciones

const SECCIONES_NOTAS = [
  { id: "resumen", label: "Resumen" },
  { id: "grilla", label: "Grilla" },
];

// --- SAPRED: sin coincidencia -----------------------------------------------
let sinCoincidenciaSedeSeleccionada = "";
let sinCoincidenciaSoloNoResueltos = true;

// --- SAPRED: importación manual de PDF --------------------------------------
let resultadoImportacionSapred = null; // se guarda para que sobreviva al refresco de la vista
let resultadoImportacionBoletin = null; // idem para el "Boletín informativo"

// --- Auditoría SAPRED (Boletines -> SAPRED -> Importar/Auditoría) ----------
let auditoriaSapredIdSeguida = null; // id de la auditoría que se está mostrando/siguiendo
let auditoriaSapredIntervalo = null;
let auditoriaSapredSedesSeleccionadas = null; // Set<number> de sede_id, null = todas
let mostrarInformeAuditoriaModal = false; // toggle "ver informe para imprimir" dentro del detalle de una auditoría pasada
const ESTADOS_AUDITORIA = {
  pendiente: { icono: "⏳", texto: "Pendiente" },
  esperando_login: { icono: "🔑", texto: "Esperando que inicies sesión en SAPRED" },
  en_proceso: { icono: "⚙️", texto: "En proceso" },
  completada: { icono: "✅", texto: "Completada" },
  error: { icono: "❌", texto: "Error" },
};
const ESTADOS_SEDE_AUDITORIA = {
  completada: { icono: "✓", clase: "ok" },
  advertencia: { icono: "⚠", clase: "proceso" },
  error: { icono: "✗", clase: "alerta" },
};

// --- Generar boletines por sede (Boletines -> SAPRED -> Generar boletines) --
let generarBoletinesSedesSeleccionadas = null; // Set<number>, null = todas
let generarBoletinesIntervalo = null;

const ESTADOS_BOLETIN = {
  completo: { icono: "🟢", texto: "Completo", clase: "ok" },
  en_proceso: { icono: "🟡", texto: "En proceso", clase: "proceso" },
  pendiente: { icono: "🔴", texto: "Pendiente", clase: "alerta" },
  sin_informacion: { icono: "⚪", texto: "Sin información", clase: "" },
};

const ETIQUETAS_ESTADO_CONTINUIDAD = {
  activo: { texto: "Activo", clase: "ok" },
  sin_evidencia_p1: { texto: "Sin evidencia académica P1", clase: "alerta" },
  posible_retiro: { texto: "Posible retiro / requiere validación", clase: "proceso" },
  posible_retiro_prioritario: { texto: "Posible retiro (prioritario)", clase: "alerta" },
  p2_sin_auditar: { texto: "Activo P1 — P2 sin auditar", clase: "" },
  p1_sin_auditar: { texto: "Activo P2 — P1 sin auditar", clase: "" },
  sin_auditar: { texto: "Sin auditar (P1 y P2)", clase: "" },
};

let continuidadSedeSeleccionada = null;

const SECCIONES_BOLETINES = [
  { id: "resumen", label: "Resumen" },
  { id: "grupos", label: "Grupos" },
  { id: "pendientes", label: "Pendientes" },
  { id: "docentes", label: "Por docente" },
  { id: "continuidad", label: "Continuidad" },
  { id: "sapred", label: "SAPRED" },
];

let porDocenteBusqueda = "";
let porDocenteSede = ""; // "" = todas las sedes
let porDocenteExpandido = null; // docente_id abierto (drill-down)
let porDocenteReporte = false; // true = mostrando el reporte imprimible
let reporteDocenteFiltro = ""; // filtro por nombre dentro del reporte imprimible
let reporteDocenteUnaHoja = false; // imprimir cada profesor en su propia hoja

function estadoBoletinHtml(g) {
  const { icono, texto, clase } = ESTADOS_BOLETIN[g.estado] || ESTADOS_BOLETIN.sin_informacion;
  const contador = g.pendientes_abiertos > 0 ? ` (${g.pendientes_abiertos})` : "";
  return `<span class="badge-estado ${clase}">${icono} ${texto}${contador}</span>`;
}

function claveGrupo(g) {
  return `${g.sede_id}|${g.grado}|${g.curso ?? ""}`;
}

function tarjetaGrupoHtml(g, docentes) {
  const clave = claveGrupo(g);
  const notasOk = !!(g.revision && g.revision.completo);
  const obsOk = !!(g.revision && g.revision.observaciones_completas);
  return `
    <div class="tarjeta-grupo" data-fila-grupo="${clave}">
      <div class="tarjeta-grupo-cabecera">
        <span class="tarjeta-grupo-nombre">${g.nombre_grupo}</span>
        <span class="tarjeta-grupo-estudiantes">${g.total_estudiantes} estudiante(s)</span>
      </div>
      <label class="tarjeta-grupo-docente">Docente
        <select class="select-docente" data-sede="${g.sede_id}" data-grado="${g.grado}" data-curso="${g.curso ?? ""}">
          <option value="">Sin asignar</option>
          ${docentes.map((d) => `<option value="${d.id}" ${g.docente && g.docente.id === d.id ? "selected" : ""}>${d.nombre_completo}</option>`).join("")}
        </select>
      </label>
      <div class="tarjeta-grupo-pie">
        <div class="tarjeta-grupo-checks">
          <label class="check-linea" title="Todas las notas están completas">
            <input type="checkbox" class="check-notas-ok" data-grupo="${clave}" ${notasOk ? "checked" : ""} /> Notas
          </label>
          <label class="check-linea" title="Las observaciones están completas">
            <input type="checkbox" class="check-obs-ok" data-grupo="${clave}" ${obsOk ? "checked" : ""} /> Observ.
          </label>
        </div>
        ${estadoBoletinHtml(g)}
      </div>
      <button type="button" class="boton tarjeta-grupo-boton" data-revisar="${clave}">Ver detalle →</button>
    </div>`;
}

function agruparGruposPorSede(grupos) {
  const mapa = {};
  grupos.forEach((g) => {
    (mapa[g.sede_nombre] = mapa[g.sede_nombre] || []).push(g);
  });
  return Object.entries(mapa).sort((a, b) => a[0].localeCompare(b[0]));
}

function agruparPorGrado(gruposSede) {
  const mapa = {};
  gruposSede.forEach((g) => {
    (mapa[g.grado] = mapa[g.grado] || []).push(g);
  });
  return Object.entries(mapa)
    .map(([grado, lista]) => [Number(grado), lista])
    .sort((a, b) => a[0] - b[0]);
}

function estaOk(g) {
  return g.estado === "completo";
}

function detalleFaltante(g) {
  const detalle = [];
  if (!g.docente) detalle.push("Sin docente asignado");
  if (g.pendientes_abiertos > 0) detalle.push(`${g.pendientes_abiertos} punto(s) pendiente(s)`);
  if (!g.revision) detalle.push("Sin revisar todavía");
  else {
    if (g.revision.materias_faltantes) detalle.push(`Faltan notas (grupo): ${g.revision.materias_faltantes}`);
    if (g.revision.estudiantes_pendientes) detalle.push(`Faltan notas (puntual): ${g.revision.estudiantes_pendientes}`);
    if (!g.revision.observaciones_completas) detalle.push("Faltan observaciones");
  }
  return detalle.join(" · ") || "—";
}

function informeBoletinesHtml(filtrados, gruposPorSede, resumen) {
  const hoy = new Date().toLocaleDateString("es-CO");
  const pendientes = filtrados.filter((g) => !estaOk(g));
  const completos = filtrados.filter(estaOk);
  const esGrupoUnico = !!informeGrupoUnico && filtrados.length === 1;

  const filaPendiente = (g) => `
    <tr>
      <td>${g.sede_nombre}</td>
      <td>${g.nombre_grupo}</td>
      <td>${g.docente ? g.docente.nombre_completo : "Sin asignar"}</td>
      <td>${detalleFaltante(g)}</td>
    </tr>`;

  const partesTitulo = [`PERÍODO ${filtroBoletinesPeriodo}`, filtroBoletinesAnio];
  if (esGrupoUnico) {
    partesTitulo.push(`GRUPO: ${filtrados[0].sede_nombre} — ${filtrados[0].nombre_grupo}`);
  } else {
    if (filtroBoletinesSede) {
      const s = filtrados[0];
      if (s) partesTitulo.push(s.sede_nombre);
    }
    if (filtroBoletinesGrado) {
      const nombreGrado = (NOMBRES_GRADOS.find(([n]) => String(n) === filtroBoletinesGrado) || [])[1];
      if (nombreGrado) partesTitulo.push(`GRADO: ${nombreGrado}`);
    }
    if (filtroBoletinesDocente) {
      const conDocente = filtrados.find((g) => g.docente);
      if (conDocente) partesTitulo.push(`DOCENTE: ${conDocente.docente.nombre_completo}`);
    }
  }

  return `
    <div class="hoja-imprimir">
      ${membreteHtml(`INFORME DE REVISIÓN DE BOLETINES — ${partesTitulo.join(" — ")}`)}
      <div class="hoja-campos">
        <div class="campo"><span class="etiqueta">FECHA DEL INFORME:</span><span class="valor">${hoy}</span></div>
        <div class="campo"><span class="etiqueta">GRUPOS COMPLETOS:</span><span class="valor">${completos.length} de ${filtrados.length}</span></div>
        ${
          !esGrupoUnico && resumen
            ? `<div class="campo"><span class="etiqueta">RESUMEN INSTITUCIONAL (todas las sedes):</span><span class="valor">🟢 ${resumen.completos} completos · 🟡 ${resumen.en_proceso} en proceso · 🔴 ${resumen.pendientes} pendientes · ⚪ ${resumen.sin_informacion} sin información (${resumen.porcentaje_completo}% completo)</span></div>`
            : ""
        }
      </div>

      <h3 class="informe-sede-titulo informe-titulo-pendientes">⚠ FALTAN POR COMPLETAR (${pendientes.length})</h3>
      ${
        pendientes.length
          ? `<table class="tabla-informe">
               <thead><tr><th>Sede</th><th>Grado</th><th>Docente</th><th>Qué falta</th></tr></thead>
               <tbody>${pendientes.map(filaPendiente).join("")}</tbody>
             </table>`
          : '<p class="pendiente">Ninguno — todos los grupos filtrados están completos.</p>'
      }

      <h3 class="informe-sede-titulo">✓ Completos (${completos.length})</h3>
      <p class="informe-completos-lista">
        ${completos.length ? completos.map((g) => `${g.sede_nombre} ${g.nombre_grupo}`).join(" · ") : "Ninguno todavía."}
      </p>
    </div>
    <div class="toolbar no-imprimir">
      <button type="button" class="boton" onclick="window.print()">Imprimir</button>
    </div>
  `;
}

function resultadoImportarSapredHtml(resultado) {
  const filaBloque = (b) => {
    if (!b.reconocido) {
      return `<li>⚠ Curso ${b.grado}-${b.curso} "${b.sede_corta}" — ${b.motivo_no_reconocido}</li>`;
    }
    const partes = [`${b.pendientes_creados} pendiente(s) nuevo(s)`, `${b.pendientes_ya_existian} ya estaban`];
    if (b.pendientes_resueltos_auto) partes.push(`✅ ${b.pendientes_resueltos_auto} viejo(s) cerrado(s) (ya en SAPRED)`);
    if (b.areas_nuevas.length) partes.push(`áreas nuevas en el catálogo: ${b.areas_nuevas.join(", ")}`);
    return `<li>${b.sede_nombre} — Grado ${b.grado}, curso ${b.curso} (P${b.periodo} ${b.anio_lectivo}): ${partes.join(" · ")}${
      b.estudiantes_no_encontrados.length
        ? `<br><span class="pendiente">⚠ No están en la base de datos: ${b.estudiantes_no_encontrados.join(" · ")}</span>`
        : ""
    }</li>`;
  };

  const fallidos = resultado.archivos_fallidos || [];
  return `
    <div class="exito-caja" style="margin-top:10px">
      <strong>Importación de SAPRED:</strong> ${resultado.bloques.length} curso(s) leído(s) de ${
        fallidos.length ? `${resultado.bloques.length + fallidos.length} archivo(s)` : "los PDF subidos"
      } · ${resultado.total_pendientes_creados} pendiente(s) nuevo(s) en total
      ${resultado.total_pendientes_resueltos_auto ? ` · ✅ ${resultado.total_pendientes_resueltos_auto} pendiente(s) viejo(s) cerrado(s) automáticamente (ya estaban cargados)` : ""}
      ${resultado.total_estudiantes_no_encontrados ? ` · ${resultado.total_estudiantes_no_encontrados} estudiante(s) de SAPRED no están en la base de datos` : ""}
      <ul style="margin:8px 0 4px">${resultado.bloques.map(filaBloque).join("")}</ul>
      ${
        fallidos.length
          ? `<p class="pendiente">⚠ No se pudieron leer: ${fallidos.join(" · ")}</p>`
          : ""
      }
      <p class="pendiente" style="margin-top:10px">
        Estas notas ya quedaron en la base de datos. Para ver si generaron alguna diferencia contra SIMAC:
      </p>
      <button type="button" class="boton" id="btn-ver-conciliacion-sapred">📊 Ver conciliación SIMAC ↔ SAPRED</button>
      <button type="button" class="boton secundario" id="btn-cerrar-resultado-sapred">Cerrar</button>
    </div>
  `;
}

function resultadoImportarBoletinHtml(resultado) {
  const filaBloque = (b) => {
    if (!b.reconocido) {
      return `<li>⚠ Curso ${b.grado}-${b.curso} "${b.sede_corta}" — ${b.motivo_no_reconocido}</li>`;
    }
    const partes = [
      `${b.conceptos_pendientes_creados} concepto(s) faltante(s) nuevo(s)`,
      `${b.notas_pendientes_creados || 0} nota(s) faltante(s) nueva(s)`,
      `${b.observaciones_pendientes_creadas} observación(es) faltante(s) nueva(s)`,
    ];
    if (b.conceptos_pendientes_ya_existian || b.observaciones_pendientes_ya_existian || b.notas_pendientes_ya_existian) {
      partes.push(`ya estaban: ${b.conceptos_pendientes_ya_existian} concepto(s), ${b.notas_pendientes_ya_existian || 0} nota(s), ${b.observaciones_pendientes_ya_existian} observación(es)`);
    }
    if (b.pendientes_resueltos_auto) partes.push(`✅ ${b.pendientes_resueltos_auto} pendiente(s) viejo(s) cerrado(s) (ya en SAPRED)`);
    if (b.docentes_area_asignados.length) partes.push(`profesor por materia asignado: ${b.docentes_area_asignados.join(", ")}`);
    if (b.docente_grupo_asignado) partes.push(`director de grupo: ${b.docente_grupo_asignado}`);
    if (b.areas_nuevas.length) partes.push(`áreas nuevas: ${b.areas_nuevas.join(", ")}`);
    return `<li>${b.sede_nombre} — Grado ${b.grado}, curso ${b.curso} (P${b.periodo} ${b.anio_lectivo}): ${partes.join(" · ")}${
      b.estudiantes_no_encontrados.length
        ? `<br><span class="pendiente">⚠ No están en la base de datos: ${b.estudiantes_no_encontrados.join(" · ")}</span>`
        : ""
    }</li>`;
  };

  const fallidos = resultado.archivos_fallidos || [];
  return `
    <div class="exito-caja" style="margin-top:10px">
      <strong>Importación del Boletín informativo:</strong> ${resultado.bloques.length} curso(s) leído(s)
      · ${resultado.total_conceptos_pendientes} concepto(s) · ${resultado.total_notas_pendientes || 0} nota(s) · ${resultado.total_observaciones_pendientes} observación(es) faltante(s)
      ${resultado.total_pendientes_resueltos_auto ? ` · ✅ ${resultado.total_pendientes_resueltos_auto} pendiente(s) viejo(s) cerrado(s) automáticamente (ya estaban cargados)` : ""}
      ${resultado.total_estudiantes_no_encontrados ? ` · ${resultado.total_estudiantes_no_encontrados} estudiante(s) del boletín no están en la base de datos` : ""}
      <ul style="margin:8px 0 4px">${resultado.bloques.map(filaBloque).join("")}</ul>
      ${fallidos.length ? `<p class="pendiente">⚠ No se pudieron leer: ${fallidos.join(" · ")}</p>` : ""}
      <p class="pendiente" style="margin-top:10px">Lo que falta quedó como pendiente (tipo concepto / observación). Se ve ordenado en Boletines → Pendientes y en Notas → Grilla.</p>
      <button type="button" class="boton secundario" id="btn-cerrar-resultado-boletin">Cerrar</button>
    </div>
  `;
}

// --- Cabecera del módulo + navegación interna --------------------------

function encabezadoBoletinesHtml() {
  return `
    <div class="pagina-header no-imprimir">
      <div>
        <h1>Boletines</h1>
        <p class="subtitulo-pagina">Revisión y seguimiento académico.</p>
      </div>
      <div class="modulo-periodo">
        <label class="filtro-campo">Año lectivo
          <input type="number" id="filtro-boletin-anio" value="${filtroBoletinesAnio}" />
        </label>
        <label class="filtro-campo">Período
          <select id="filtro-boletin-periodo">
            ${[1, 2, 3, 4].map((p) => `<option value="${p}" ${p === filtroBoletinesPeriodo ? "selected" : ""}>${p}</option>`).join("")}
          </select>
        </label>
      </div>
    </div>
    <nav class="subnav-modulo no-imprimir" aria-label="Secciones de Boletines">
      ${SECCIONES_BOLETINES.map(
        (s) => `<button type="button" class="subnav-item ${seccionBoletines === s.id ? "activo" : ""}" data-seccion-boletines="${s.id}">${s.label}</button>`
      ).join("")}
    </nav>
  `;
}

function vincularEncabezadoBoletines() {
  document.getElementById("filtro-boletin-anio").addEventListener("change", (e) => {
    filtroBoletinesAnio = Number(e.target.value) || filtroBoletinesAnio;
    render();
  });
  document.getElementById("filtro-boletin-periodo").addEventListener("change", (e) => {
    filtroBoletinesPeriodo = Number(e.target.value);
    render();
  });
  document.querySelectorAll("[data-seccion-boletines]").forEach((btn) => {
    btn.addEventListener("click", () => {
      seccionBoletines = btn.dataset.seccionBoletines;
      if (seccionBoletines === "sapred") sapredSubvista = "hub";
      porDocenteReporte = false;
      reporteDocenteFiltro = "";
      render();
    });
  });
}

async function renderBoletines() {
  app.innerHTML = `${encabezadoBoletinesHtml()}<div id="contenido-boletines" class="estado-carga">Cargando...</div><div id="modal-revision"></div>`;
  vincularEncabezadoBoletines();

  if (seccionBoletines === "resumen") return renderSeccionResumen();
  if (seccionBoletines === "grupos") return renderSeccionGrupos();
  if (seccionBoletines === "pendientes") return renderSeccionPendientes();
  if (seccionBoletines === "docentes") return renderSeccionPorDocente();
  if (seccionBoletines === "continuidad") return renderSeccionContinuidad();
  if (seccionBoletines === "sapred") return renderSeccionSapred();
}

// --- Sección: Resumen ----------------------------------------------------

async function renderSeccionResumen() {
  const contenedor = document.getElementById("contenido-boletines");
  const resumen = await api(`/api/boletines/resumen?anio_lectivo=${filtroBoletinesAnio}&periodo=${filtroBoletinesPeriodo}`);

  contenedor.innerHTML = `
    <div class="resumen-reportes">
      <div class="metric-card"><span>Grupos</span><strong>${resumen.total_grupos}</strong></div>
      <div class="metric-card ok"><span>🟢 Completos</span><strong>${resumen.completos}</strong></div>
      <div class="metric-card proceso"><span>🟡 En proceso</span><strong>${resumen.en_proceso}</strong></div>
      <div class="metric-card alerta"><span>🔴 Pendientes</span><strong>${resumen.pendientes}</strong></div>
      <div class="metric-card"><span>⚪ Sin información</span><strong>${resumen.sin_informacion}</strong></div>
      <div class="metric-card"><span>% completo</span><strong>${resumen.porcentaje_completo}%</strong></div>
      <div class="metric-card ${resumen.total_pendientes_individuales ? "alerta" : "ok"}"><span>Pendientes puntuales</span><strong>${resumen.total_pendientes_individuales}</strong></div>
    </div>

    <div class="accesos-rapidos-boletines">
      <button type="button" class="boton secundario" id="btn-ir-grupos-pendientes">Ver grupos pendientes →</button>
      <button type="button" class="boton secundario" id="btn-ir-pendientes">Ver pendientes puntuales →</button>
    </div>

    ${
      resumen.por_sede.length
        ? `<h3 class="subtitulo-seccion">Por sede</h3>
           <div class="tabla-scroll"><table>
             <thead><tr><th>Sede</th><th>Grupos</th><th>Completos</th><th>Pendientes</th></tr></thead>
             <tbody>
               ${resumen.por_sede
                 .map(
                   (s) => `<tr>
                 <td>${s.nombre}</td>
                 <td>${s.total_grupos}</td>
                 <td>${s.completos}</td>
                 <td>${s.pendientes ? `<span class="badge inactivo">${s.pendientes}</span>` : "0"}</td>
               </tr>`
                 )
                 .join("")}
             </tbody>
           </table></div>`
        : ""
    }
  `;

  document.getElementById("btn-ir-grupos-pendientes").addEventListener("click", () => {
    filtroBoletinesSoloPendientes = true;
    seccionBoletines = "grupos";
    render();
  });
  document.getElementById("btn-ir-pendientes").addEventListener("click", () => {
    seccionBoletines = "pendientes";
    render();
  });
}

// --- Sección: Grupos -------------------------------------------------------

async function renderSeccionGrupos() {
  const contenedor = document.getElementById("contenido-boletines");
  const [todasLasSedes, docentes, todosLosGrupos, resumen] = await Promise.all([
    api("/api/sedes"),
    api("/api/docentes"),
    api(`/api/grupos?anio_lectivo=${filtroBoletinesAnio}&periodo=${filtroBoletinesPeriodo}`),
    api(`/api/boletines/resumen?anio_lectivo=${filtroBoletinesAnio}&periodo=${filtroBoletinesPeriodo}`),
  ]);

  // Solo interesan las sedes propias de IETABA: el mismo archivo departamental
  // trae también sedes de otras instituciones que no hay que revisar aquí.
  const sedes = todasLasSedes.filter((s) => s.pertenece_ietaba);
  const idsSedesIetaba = new Set(sedes.map((s) => s.id));
  const grupos = todosLosGrupos.filter((g) => idsSedesIetaba.has(g.sede_id));

  let filtrados = filtroBoletinesSede ? grupos.filter((g) => String(g.sede_id) === filtroBoletinesSede) : grupos;
  if (filtroBoletinesDocente) {
    filtrados = filtrados.filter((g) => g.docente && String(g.docente.id) === filtroBoletinesDocente);
  }
  if (filtroBoletinesGrado) {
    filtrados = filtrados.filter((g) => String(g.grado) === filtroBoletinesGrado);
  }
  if (filtroBoletinesSoloPendientes) {
    filtrados = filtrados.filter((g) => g.estado !== "completo");
  }
  // El informe "de un grupo" (abierto desde el modal) ignora los demás
  // filtros: siempre debe mostrar exactamente ese grupo.
  if (informeGrupoUnico) {
    filtrados = grupos.filter((g) => claveGrupo(g) === informeGrupoUnico);
  }

  const gruposPorSede = agruparGruposPorSede(filtrados);
  const abrirTodas = gruposPorSede.length <= 3;
  if (sedesAbiertasBoletines === null) {
    sedesAbiertasBoletines = new Set(abrirTodas ? gruposPorSede.map(([nombre]) => nombre) : []);
  }

  contenedor.innerHTML = `
    <div class="barra-filtros no-imprimir">
      <label class="filtro-campo">Sede
        <select id="filtro-boletin-sede">
          <option value="">Todas las sedes</option>
          ${sedes.map((s) => `<option value="${s.id}" ${String(s.id) === filtroBoletinesSede ? "selected" : ""}>${s.nombre}</option>`).join("")}
        </select>
      </label>
      <label class="filtro-campo">Docente
        <select id="filtro-boletin-docente">
          <option value="">Todos los docentes</option>
          ${docentes.map((d) => `<option value="${d.id}" ${String(d.id) === filtroBoletinesDocente ? "selected" : ""}>${d.nombre_completo}</option>`).join("")}
        </select>
      </label>
      <label class="filtro-campo">Grado
        <select id="filtro-boletin-grado">
          <option value="">Todos</option>
          ${NOMBRES_GRADOS.map(([n, nombre]) => `<option value="${n}" ${String(n) === filtroBoletinesGrado ? "selected" : ""}>${nombre}</option>`).join("")}
        </select>
      </label>
      <label class="check-linea filtro-check">
        <input type="checkbox" id="filtro-boletin-pendientes" ${filtroBoletinesSoloPendientes ? "checked" : ""} />
        Solo pendientes
      </label>
      <button type="button" class="boton secundario" id="btn-toggle-informe">
        ${mostrarInformeBoletines ? "Ocultar informe" : "🖨 Ver informe para imprimir"}
      </button>
    </div>

    ${
      informeGrupoUnico
        ? `<p class="no-imprimir"><button type="button" class="boton secundario" id="btn-quitar-informe-grupo">◀ Volver al informe general</button></p>`
        : ""
    }
    <p class="no-imprimir conteo-resultados">${filtrados.length} grupo(s) en ${gruposPorSede.length} sede(s)</p>
    <div id="zona-informe-boletines">${mostrarInformeBoletines ? informeBoletinesHtml(filtrados, gruposPorSede, resumen) : ""}</div>
    <div class="no-imprimir">
      ${gruposPorSede
        .map(([sedeNombre, gruposSede]) => {
          const okSede = gruposSede.filter((g) => g.estado === "completo").length;
          const porGrado = agruparPorGrado(gruposSede);
          return `
        <details class="seccion-colapsable" data-sede-nombre="${sedeNombre}" ${sedesAbiertasBoletines.has(sedeNombre) || gruposPorSede.length === 1 ? "open" : ""}>
          <summary>${sedeNombre} — ${okSede}/${gruposSede.length} OK</summary>
          ${porGrado
            .map(([grado, lista]) => {
              const nombreGrado = (NOMBRES_GRADOS.find(([n]) => n === grado) || [null, `Grado ${grado}`])[1];
              return `
              <h4 class="subtitulo-grado">${nombreGrado}</h4>
              <div class="grid-tarjetas-grupo">${lista.map((g) => tarjetaGrupoHtml(g, docentes)).join("")}</div>`;
            })
            .join("")}
        </details>`;
        })
        .join("")}
    </div>
  `;

  document.querySelectorAll("details.seccion-colapsable[data-sede-nombre]").forEach((det) => {
    det.addEventListener("toggle", () => {
      if (det.open) sedesAbiertasBoletines.add(det.dataset.sedeNombre);
      else sedesAbiertasBoletines.delete(det.dataset.sedeNombre);
    });
  });

  document.getElementById("filtro-boletin-sede").addEventListener("change", (e) => {
    filtroBoletinesSede = e.target.value;
    render();
  });
  document.getElementById("filtro-boletin-docente").addEventListener("change", (e) => {
    filtroBoletinesDocente = e.target.value;
    render();
  });
  document.getElementById("filtro-boletin-grado").addEventListener("change", (e) => {
    filtroBoletinesGrado = e.target.value;
    render();
  });
  document.getElementById("filtro-boletin-pendientes").addEventListener("change", (e) => {
    filtroBoletinesSoloPendientes = e.target.checked;
    render();
  });
  document.getElementById("btn-toggle-informe").addEventListener("click", () => {
    mostrarInformeBoletines = !mostrarInformeBoletines;
    render();
  });
  document.getElementById("btn-quitar-informe-grupo")?.addEventListener("click", () => {
    informeGrupoUnico = null;
    render();
  });

  document.querySelectorAll(".select-docente").forEach((select) => {
    select.addEventListener("change", async () => {
      await api("/api/asignaciones", {
        method: "POST",
        body: JSON.stringify({
          docente_id: select.value ? Number(select.value) : null,
          sede_id: Number(select.dataset.sede),
          grado: Number(select.dataset.grado),
          curso: select.dataset.curso ? Number(select.dataset.curso) : null,
          anio_lectivo: filtroBoletinesAnio,
        }),
      });
    });
  });

  const guardarRevisionRapida = async (g, cambios) => {
    const r = g.revision;
    await api("/api/revisiones-boletin", {
      method: "POST",
      body: JSON.stringify({
        sede_id: g.sede_id,
        grado: g.grado,
        curso: g.curso,
        anio_lectivo: filtroBoletinesAnio,
        periodo: filtroBoletinesPeriodo,
        completo: r ? r.completo : false,
        materias_faltantes: r ? r.materias_faltantes : null,
        observaciones_completas: r ? r.observaciones_completas : false,
        notas: r ? r.notas : null,
        estudiantes_pendientes: r ? r.estudiantes_pendientes : null,
        ...cambios,
      }),
    });
    await renderSeccionGrupos();
  };

  document.querySelectorAll(".check-notas-ok").forEach((chk) => {
    chk.addEventListener("change", () => {
      const g = grupos.find((x) => claveGrupo(x) === chk.dataset.grupo);
      guardarRevisionRapida(g, {
        completo: chk.checked,
        materias_faltantes: chk.checked ? null : g.revision?.materias_faltantes || null,
      });
    });
  });

  document.querySelectorAll(".check-obs-ok").forEach((chk) => {
    chk.addEventListener("change", () => {
      const g = grupos.find((x) => claveGrupo(x) === chk.dataset.grupo);
      guardarRevisionRapida(g, { observaciones_completas: chk.checked });
    });
  });

  document.querySelectorAll("[data-revisar]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const [sedeId, grado, curso] = btn.dataset.revisar.split("|");
      const grupo = grupos.find(
        (g) => String(g.sede_id) === sedeId && String(g.grado) === grado && String(g.curso ?? "") === curso
      );
      abrirModalRevision(grupo);
    });
  });
}

// --- Sección: Pendientes ----------------------------------------------------

function tablaFaltantesHtml(pendientes) {
  const q = busquedaFaltantes.trim().toLowerCase();
  let filtrados = q
    ? pendientes.filter((p) => {
        const campos = [
          p.sede_nombre,
          p.nombre_grupo,
          p.area?.nombre,
          p.area?.codigo,
          p.estudiante?.nombre_completo,
          p.estudiante?.documento,
          p.docente?.nombre_completo,
          p.detalle,
          p.tipo,
        ];
        return campos.some((c) => c && c.toLowerCase().includes(q));
      })
    : pendientes;

  if (!filtrados.length) {
    return `<div class="estado-vacio"><div class="estado-vacio-icono">🎉</div><h3>${
      pendientes.length ? "Ningún resultado para esa búsqueda" : "Sin pendientes para este filtro"
    }</h3><p>Prueba cambiando los filtros o la búsqueda.</p></div>`;
  }

  // Los seleccionados que ya no están en la lista filtrada no cuentan.
  const idsVisibles = new Set(filtrados.map((p) => p.id));
  [...pendientesSeleccionados].forEach((id) => {
    if (!idsVisibles.has(id)) pendientesSeleccionados.delete(id);
  });
  const nSeleccionados = pendientesSeleccionados.size;

  const totalPaginas = Math.max(1, Math.ceil(filtrados.length / PENDIENTES_POR_PAGINA));
  if (pendientesPagina > totalPaginas) pendientesPagina = totalPaginas;
  const inicio = (pendientesPagina - 1) * PENDIENTES_POR_PAGINA;
  const pagina = filtrados.slice(inicio, inicio + PENDIENTES_POR_PAGINA);

  return `
    <div class="panel-tabla-header no-imprimir">
      <span class="conteo-resultados">${filtrados.length} pendiente(s)${nSeleccionados ? ` · ${nSeleccionados} seleccionado(s)` : ""}</span>
      <span>
        <button type="button" class="boton secundario" id="btn-exportar-seleccionados" ${nSeleccionados ? "" : "disabled"}>⬇ Exportar seleccionados</button>
        <button type="button" class="boton secundario" id="btn-exportar-todos">⬇ Exportar todos (Excel)</button>
      </span>
    </div>
    <div class="tabla-scroll">
    <table class="no-imprimir">
      <thead>
        <tr>
          <th><input type="checkbox" id="check-todos-pendientes" title="Seleccionar todos los de esta página" ${pagina.length && pagina.every((p) => pendientesSeleccionados.has(p.id)) ? "checked" : ""} /></th>
          <th>Estudiante</th><th>Área</th><th>Tipo</th><th>Grupo</th><th>Estado</th><th></th>
        </tr>
      </thead>
      <tbody>${pagina.map(filaFaltanteHtml).join("")}</tbody>
    </table>
    </div>
    <div class="paginacion no-imprimir">
      <span>Mostrando ${pagina.length ? inicio + 1 : 0}-${inicio + pagina.length} de ${filtrados.length}</span>
      <button class="boton secundario" ${pendientesPagina <= 1 ? "disabled" : ""} data-pendientes-pagina="${pendientesPagina - 1}">‹ Anterior</button>
      <span>Página ${pendientesPagina} de ${totalPaginas}</span>
      <button class="boton secundario" ${pendientesPagina >= totalPaginas ? "disabled" : ""} data-pendientes-pagina="${pendientesPagina + 1}">Siguiente ›</button>
    </div>
  `;
}

function filaFaltanteHtml(p) {
  const tipoTexto = { nota: "Nota", concepto: "Concepto", observacion: "Observación" }[p.tipo] || p.tipo;
  const navGrilla = p.estudiante
    ? `data-ver-estudiante-faltante="${p.estudiante.id}" data-g-doc="${p.estudiante.documento}" data-g-sede="${p.sede_id}" data-g-grado="${p.grado}" data-g-curso="${p.curso ?? ""}" data-g-periodo="${p.periodo}"`
    : "";
  const estudianteHtml = p.estudiante
    ? `<span class="fila-clicable" ${navGrilla} title="Abrir la grilla de notas de este grupo, resaltando al estudiante" style="text-decoration:underline; cursor:pointer">${p.estudiante.nombre_completo}${
        p.estudiante.retirado
          ? ' <span class="chip-retiro chip-retirado">✖ RETIRADO</span>'
          : p.estudiante.posible_retirado ? ' <span class="chip-retiro">🚪 posible retiro</span>' : ""
      }</span>`
    : '<span class="pendiente">Todo el grupo</span>';
  return `
    <tr${p.estudiante && p.estudiante.posible_retirado ? ' class="fila-posible-retiro"' : ""}>
      <td><input type="checkbox" class="check-pendiente-seleccionado" value="${p.id}" ${pendientesSeleccionados.has(p.id) ? "checked" : ""} /></td>
      <td>${estudianteHtml}</td>
      <td>${p.area ? p.area.nombre : "General (todo el grupo)"}</td>
      <td>${tipoTexto}${p.detalle ? `: ${p.detalle}` : ""}</td>
      <td>${p.sede_nombre} · ${p.nombre_grupo}${p.docente ? ` · ${p.docente.nombre_completo}` : ""}</td>
      <td><span class="badge-verif ${p.resuelto ? "ok" : "alerta"}">${p.resuelto ? "✓ Resuelto" : "⚠ Pendiente"}</span></td>
      <td>
        ${p.resuelto ? "" : `<button type="button" class="boton secundario" data-resolver="${p.id}">Marcar resuelto</button>`}
        ${
          p.estudiante
            ? `<button type="button" class="boton secundario" data-posible-retiro="${p.estudiante.id}" data-pr-estado="${p.estudiante.posible_retirado ? "1" : "0"}" title="Marcar/quitar 'posible retirado': deja de contar en los pendientes">${p.estudiante.posible_retirado ? "↩ Cuenta de nuevo" : "🚪 Posible retiro"}</button>`
            : ""
        }
        <button type="button" class="boton secundario" data-eliminar-pendiente="${p.id}" title="Eliminar (ej. si se agregó por error)">🗑</button>
      </td>
    </tr>`;
}

function urlExportarPendientes(idsSeleccionados) {
  const params = new URLSearchParams({
    anio_lectivo: filtroBoletinesAnio,
    periodo: filtroBoletinesPeriodo,
    solo_no_resueltos: String(pendientesFiltroSoloNoResueltos),
  });
  if (pendientesFiltroSede) params.set("sede_id", pendientesFiltroSede);
  if (pendientesFiltroGrado) params.set("grado", pendientesFiltroGrado);
  if (pendientesFiltroArea) params.set("area_id", pendientesFiltroArea);
  if (idsSeleccionados) params.set("ids", idsSeleccionados.join(","));
  return `/api/boletines/pendientes/exportar?${params}`;
}

async function renderSeccionPendientes() {
  const contenedor = document.getElementById("contenido-boletines");
  const params = new URLSearchParams({
    anio_lectivo: filtroBoletinesAnio,
    periodo: filtroBoletinesPeriodo,
    solo_no_resueltos: String(pendientesFiltroSoloNoResueltos),
  });
  if (pendientesFiltroSede) params.set("sede_id", pendientesFiltroSede);
  if (pendientesFiltroGrado) params.set("grado", pendientesFiltroGrado);
  if (pendientesFiltroArea) params.set("area_id", pendientesFiltroArea);

  const [todasLasSedes, areas, pendientesPlanos] = await Promise.all([
    api("/api/sedes"),
    api("/api/areas"),
    api(`/api/boletines/pendientes?${params}`),
  ]);
  const sedes = todasLasSedes.filter((s) => s.pertenece_ietaba);

  contenedor.innerHTML = `
    <div class="pagina-header no-imprimir">
      <div>
        <h2 style="margin:0; font-size:20px">Pendientes</h2>
        <p class="subtitulo-pagina">Elementos que requieren revisión.</p>
      </div>
    </div>
    <div class="buscador-principal no-imprimir">
      <span class="buscador-principal-icono" aria-hidden="true">🔎</span>
      <input type="text" id="buscar-faltantes" placeholder="Buscar por estudiante, grupo, docente o área..." value="${busquedaFaltantes}" />
    </div>
    <div class="barra-filtros no-imprimir">
      <label class="filtro-campo">Sede
        <select id="filtro-pendientes-sede">
          <option value="">Todas las sedes</option>
          ${sedes.map((s) => `<option value="${s.id}" ${String(s.id) === pendientesFiltroSede ? "selected" : ""}>${s.nombre}</option>`).join("")}
        </select>
      </label>
      <label class="filtro-campo">Grado
        <select id="filtro-pendientes-grado">
          <option value="">Todos</option>
          ${NOMBRES_GRADOS.map(([n, nombre]) => `<option value="${n}" ${String(n) === pendientesFiltroGrado ? "selected" : ""}>${nombre}</option>`).join("")}
        </select>
      </label>
      <label class="filtro-campo">Área
        <select id="filtro-pendientes-area">
          <option value="">Todas</option>
          ${areas.map((a) => `<option value="${a.id}" ${String(a.id) === pendientesFiltroArea ? "selected" : ""}>${a.nombre}</option>`).join("")}
        </select>
      </label>
      <label class="filtro-campo">Estado
        <select id="filtro-pendientes-estado">
          <option value="true" ${pendientesFiltroSoloNoResueltos ? "selected" : ""}>Sin resolver</option>
          <option value="false" ${!pendientesFiltroSoloNoResueltos ? "selected" : ""}>Todos</option>
        </select>
      </label>
    </div>
    <div id="tabla-pendientes">${tablaFaltantesHtml(pendientesPlanos)}</div>
  `;

  document.getElementById("filtro-pendientes-sede").addEventListener("change", (e) => {
    pendientesFiltroSede = e.target.value;
    pendientesPagina = 1;
    render();
  });
  document.getElementById("filtro-pendientes-grado").addEventListener("change", (e) => {
    pendientesFiltroGrado = e.target.value;
    pendientesPagina = 1;
    render();
  });
  document.getElementById("filtro-pendientes-area").addEventListener("change", (e) => {
    pendientesFiltroArea = e.target.value;
    pendientesPagina = 1;
    render();
  });
  document.getElementById("filtro-pendientes-estado").addEventListener("change", (e) => {
    pendientesFiltroSoloNoResueltos = e.target.value === "true";
    pendientesPagina = 1;
    render();
  });

  document.getElementById("buscar-faltantes").addEventListener("input", (e) => {
    clearTimeout(temporizadorBuscarFaltantes);
    const valor = e.target.value;
    temporizadorBuscarFaltantes = setTimeout(() => {
      busquedaFaltantes = valor;
      mantenerFocoBuscarFaltantes = true;
      pendientesPagina = 1;
      render();
    }, 300);
  });

  document.querySelectorAll("[data-pendientes-pagina]").forEach((btn) => {
    btn.addEventListener("click", () => {
      pendientesPagina = Number(btn.dataset.pendientesPagina);
      renderSeccionPendientes();
    });
  });

  if (mantenerFocoBuscarFaltantes) {
    mantenerFocoBuscarFaltantes = false;
    const buscarInput = document.getElementById("buscar-faltantes");
    buscarInput?.focus();
    buscarInput?.setSelectionRange(buscarInput.value.length, buscarInput.value.length);
  }

  vincularAccionesPendientes();
}

function vincularAccionesPendientes() {
  document.querySelectorAll("[data-resolver]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api(`/api/boletines/pendientes/${btn.dataset.resolver}`, {
        method: "PATCH",
        body: JSON.stringify({ resuelto: true }),
      });
      await renderSeccionPendientes();
    });
  });

  document.querySelectorAll("[data-eliminar-pendiente]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("¿Eliminar este pendiente? (por ejemplo, si se agregó por error)")) return;
      await api(`/api/boletines/pendientes/${btn.dataset.eliminarPendiente}`, { method: "DELETE" });
      await renderSeccionPendientes();
    });
  });

  document.querySelectorAll("[data-ver-estudiante-faltante]").forEach((el) => {
    el.addEventListener("click", () =>
      irAGrillaNotas({
        sedeId: el.dataset.gSede,
        grado: el.dataset.gGrado,
        curso: el.dataset.gCurso,
        periodo: el.dataset.gPeriodo,
        doc: el.dataset.gDoc,
        volver: { vista: "boletines", secBoletines: "pendientes", scrollY: window.scrollY },
      })
    );
  });

  document.querySelectorAll("[data-posible-retiro]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      await alternarPosibleRetiro(Number(btn.dataset.posibleRetiro), btn.dataset.prEstado);
      await renderSeccionPendientes();
    });
  });

  document.querySelectorAll(".check-pendiente-seleccionado").forEach((chk) => {
    chk.addEventListener("change", () => {
      const id = Number(chk.value);
      if (chk.checked) pendientesSeleccionados.add(id);
      else pendientesSeleccionados.delete(id);
      renderSeccionPendientes();
    });
  });

  document.getElementById("check-todos-pendientes")?.addEventListener("change", (e) => {
    document.querySelectorAll(".check-pendiente-seleccionado").forEach((chk) => {
      chk.checked = e.target.checked;
      const id = Number(chk.value);
      if (e.target.checked) pendientesSeleccionados.add(id);
      else pendientesSeleccionados.delete(id);
    });
    renderSeccionPendientes();
  });

  document.getElementById("btn-exportar-seleccionados")?.addEventListener("click", () => {
    if (!pendientesSeleccionados.size) return;
    window.location.href = urlExportarPendientes([...pendientesSeleccionados]);
  });

  document.getElementById("btn-exportar-todos")?.addEventListener("click", () => {
    window.location.href = urlExportarPendientes(null);
  });
}

// --- Sección: Notas (reporte de notas) --------------------------------------

function urlReporteNotasParams() {
  const params = new URLSearchParams({
    periodo: notasPeriodo,
    anio_lectivo: notasAnio,
    umbral_bajo: reporteNotasUmbralBajo,
    umbral_alto: reporteNotasUmbralAlto,
    riesgo_minimo: reporteNotasRiesgoMinimo,
  });
  if (reporteNotasSedeSeleccionada) params.set("sede_id", reporteNotasSedeSeleccionada);
  if (reporteNotasGradoSeleccionado) params.set("grado", reporteNotasGradoSeleccionado);
  return params;
}

function filaNotaHtml(n) {
  return `<tr>
    <td>${n.sede_nombre}</td>
    <td>${n.nombre_grupo}</td>
    <td>${n.nombre_completo}</td>
    <td>${n.area_nombre}</td>
    <td><strong>${n.valor}</strong></td>
    <td>${n.docente || "Sin asignar"}</td>
  </tr>`;
}

function filaRiesgoHtml(e) {
  return `<tr>
    <td>${e.sede_nombre}</td>
    <td>${e.nombre_grupo}</td>
    <td>${e.nombre_completo}</td>
    <td>${e.cantidad_notas_bajas}</td>
    <td style="font-size:12px">${e.areas_bajas.join(", ")}</td>
    <td><strong>${e.promedio}</strong></td>
  </tr>`;
}

let notasRenderToken = 0;

async function renderNotas() {
  const miToken = ++notasRenderToken;
  app.innerHTML = `
    <div class="pagina-header">
      <div>
        <h1>Notas</h1>
        <p class="subtitulo-pagina">Notas reales importadas de SAPRED: alertas de notas bajas/altas y la grilla completa por estudiante y área.</p>
      </div>
      <div class="modulo-periodo">
        <label class="filtro-campo">Año lectivo
          <input type="number" id="notas-anio" value="${notasAnio}" />
        </label>
        <label class="filtro-campo">Período
          <select id="notas-periodo-cabecera">
            ${[1, 2, 3, 4].map((p) => `<option value="${p}" ${p === notasPeriodo ? "selected" : ""}>${p}</option>`).join("")}
          </select>
        </label>
      </div>
    </div>
    <nav class="subnav-modulo" aria-label="Secciones de Notas">
      ${SECCIONES_NOTAS.map(
        (s) => `<button type="button" class="subnav-item ${seccionNotas === s.id ? "activo" : ""}" data-seccion-notas="${s.id}">${s.label}</button>`
      ).join("")}
    </nav>
    <div id="contenido-notas" class="estado-carga">Cargando...</div>
  `;
  document.getElementById("notas-anio").addEventListener("change", (e) => {
    notasAnio = Number(e.target.value) || notasAnio;
    render();
  });
  document.getElementById("notas-periodo-cabecera").addEventListener("change", (e) => {
    notasPeriodo = Number(e.target.value);
    render();
  });
  document.querySelectorAll("[data-seccion-notas]").forEach((btn) => {
    btn.addEventListener("click", () => {
      seccionNotas = btn.dataset.seccionNotas;
      grillaResaltarDoc = null;
      grillaVolverA = null;
      render();
    });
  });

  const contenedor = document.getElementById("contenido-notas");
  const todasLasSedes = await api("/api/sedes");
  if (miToken !== notasRenderToken) return; // se navegó a otra sección mientras esto cargaba

  const sedes = todasLasSedes.filter((s) => s.pertenece_ietaba);
  if (reporteNotasSedeSeleccionada === "") {
    const ietaba = sedes.find((s) => s.nombre.toUpperCase().includes("I.E.T.A.B.A"));
    reporteNotasSedeSeleccionada = ietaba ? String(ietaba.id) : "";
  }

  if (seccionNotas === "grilla") return renderSeccionNotasGrilla(contenedor, sedes);
  await cargarYPintarReporteNotas(contenedor, sedes);
}

async function cargarYPintarReporteNotas(contenedor, sedes) {
  contenedor.innerHTML = '<div class="estado-carga">Calculando reporte de notas...</div>';
  let reporte;
  try {
    reporte = await api(`/api/boletines/reporte-notas?${urlReporteNotasParams()}`);
  } catch (err) {
    contenedor.innerHTML = `<div class="alerta-caja">${err.message}</div>`;
    return;
  }
  pintarReporteNotas(contenedor, reporte, sedes);
}

function pintarReporteNotas(contenedor, r, sedes) {
  contenedor.innerHTML = `
    <div class="barra-filtros no-imprimir">
      <label class="filtro-campo">Sede
        <select id="select-sede-reporte-notas">
          <option value="" ${reporteNotasSedeSeleccionada === "" ? "selected" : ""}>Todas las sedes</option>
          ${sedes.map((s) => `<option value="${s.id}" ${String(s.id) === reporteNotasSedeSeleccionada ? "selected" : ""}>${s.nombre}</option>`).join("")}
        </select>
      </label>
      <label class="filtro-campo">Grado
        <select id="select-grado-reporte-notas">
          <option value="" ${reporteNotasGradoSeleccionado === "" ? "selected" : ""}>Todos</option>
          ${NOMBRES_GRADOS.map(([n, nombre]) => `<option value="${n}" ${String(n) === reporteNotasGradoSeleccionado ? "selected" : ""}>${nombre}</option>`).join("")}
        </select>
      </label>
      <label class="filtro-campo">Período
        <select id="select-periodo-reporte-notas">
          ${[1, 2, 3, 4].map((p) => `<option value="${p}" ${p === notasPeriodo ? "selected" : ""}>${p}</option>`).join("")}
        </select>
      </label>
      <label class="filtro-campo">Nota baja &le;
        <input type="number" id="input-umbral-bajo" value="${reporteNotasUmbralBajo}" step="0.1" min="1" max="5" />
      </label>
      <label class="filtro-campo">Nota alta &ge;
        <input type="number" id="input-umbral-alto" value="${reporteNotasUmbralAlto}" step="0.1" min="1" max="5" />
      </label>
      <label class="filtro-campo">Riesgo desde (notas bajas)
        <input type="number" id="input-riesgo-minimo" value="${reporteNotasRiesgoMinimo}" step="1" min="1" max="20" />
      </label>
    </div>

    <div class="resumen-reportes">
      <div class="metric-card"><span>Notas evaluadas</span><strong>${r.total_notas_evaluadas}</strong></div>
      <div class="metric-card ${r.notas_bajas.length ? "alerta" : "ok"}"><span>Notas bajas (&le;${r.umbral_bajo})</span><strong>${r.notas_bajas.length}</strong></div>
      <div class="metric-card ok"><span>Notas altas (&ge;${r.umbral_alto})</span><strong>${r.notas_altas.length}</strong></div>
      <div class="metric-card ${r.estudiantes_en_riesgo.length ? "alerta" : "ok"}"><span>Estudiantes en riesgo</span><strong>${r.estudiantes_en_riesgo.length}</strong></div>
    </div>

    <details class="seccion-colapsable" ${r.estudiantes_en_riesgo.length ? "open" : ""}>
      <summary>⚠ Estudiantes en riesgo — ${r.estudiantes_en_riesgo.length} estudiante(s) con ${r.riesgo_minimo}+ notas bajas</summary>
      ${
        r.estudiantes_en_riesgo.length
          ? `<div class="tabla-scroll tabla-scroll-alto"><table><thead><tr><th>Sede</th><th>Grupo</th><th>Estudiante</th><th>Notas bajas</th><th>Áreas</th><th>Promedio</th></tr></thead>
             <tbody>${r.estudiantes_en_riesgo.map(filaRiesgoHtml).join("")}</tbody></table></div>`
          : '<p class="pendiente">Nadie cumple ese criterio con los filtros actuales.</p>'
      }
    </details>

    <details class="seccion-colapsable">
      <summary>🔴 Notas bajas — ${r.notas_bajas.length} nota(s)</summary>
      ${
        r.notas_bajas.length
          ? `<div class="tabla-scroll tabla-scroll-alto"><table><thead><tr><th>Sede</th><th>Grupo</th><th>Estudiante</th><th>Área</th><th>Nota</th><th>Docente</th></tr></thead>
             <tbody>${r.notas_bajas.map(filaNotaHtml).join("")}</tbody></table></div>`
          : '<p class="pendiente">Sin notas bajas con los filtros actuales.</p>'
      }
    </details>

    <details class="seccion-colapsable">
      <summary>🟢 Notas altas — ${r.notas_altas.length} nota(s)</summary>
      ${
        r.notas_altas.length
          ? `<div class="tabla-scroll tabla-scroll-alto"><table><thead><tr><th>Sede</th><th>Grupo</th><th>Estudiante</th><th>Área</th><th>Nota</th><th>Docente</th></tr></thead>
             <tbody>${r.notas_altas.map(filaNotaHtml).join("")}</tbody></table></div>`
          : '<p class="pendiente">Sin notas altas con los filtros actuales.</p>'
      }
    </details>

    <div class="no-imprimir" style="text-align:right; margin-top:14px">
      <button type="button" class="boton secundario" id="btn-exportar-reporte-notas">⬇ Exportar a Excel</button>
    </div>
  `;

  document.getElementById("select-sede-reporte-notas").addEventListener("change", (e) => {
    reporteNotasSedeSeleccionada = e.target.value;
    cargarYPintarReporteNotas(contenedor, sedes);
  });
  document.getElementById("select-grado-reporte-notas").addEventListener("change", (e) => {
    reporteNotasGradoSeleccionado = e.target.value;
    cargarYPintarReporteNotas(contenedor, sedes);
  });
  document.getElementById("select-periodo-reporte-notas").addEventListener("change", (e) => {
    notasPeriodo = Number(e.target.value);
    const cabecera = document.getElementById("notas-periodo-cabecera");
    if (cabecera) cabecera.value = String(notasPeriodo);
    cargarYPintarReporteNotas(contenedor, sedes);
  });
  const recalcular = () => {
    reporteNotasUmbralBajo = Number(document.getElementById("input-umbral-bajo").value) || 3.0;
    reporteNotasUmbralAlto = Number(document.getElementById("input-umbral-alto").value) || 4.5;
    reporteNotasRiesgoMinimo = Number(document.getElementById("input-riesgo-minimo").value) || 1;
    cargarYPintarReporteNotas(contenedor, sedes);
  };
  document.getElementById("input-umbral-bajo").addEventListener("change", recalcular);
  document.getElementById("input-umbral-alto").addEventListener("change", recalcular);
  document.getElementById("input-riesgo-minimo").addEventListener("change", recalcular);

  document.getElementById("btn-exportar-reporte-notas").addEventListener("click", async () => {
    // Fase 4A': la descarga la hace el navegador, no api(): si el token de
    // acceso venciera, aquí no habría forma de renovarlo ni de reintentar.
    await asegurarSesionFresca();
    window.location.href = `/api/boletines/reporte-notas/exportar?${urlReporteNotasParams()}`;
  });
}

// --- Sección: Notas > Grilla (estudiante x área, formato tipo SAPRED) -------

let grillaSoloFaltantes = false;
let grillaModoInforme = false;
let grillaResaltarDoc = null; // documento del estudiante a resaltar al abrir la grilla desde "¿qué falta?"
let grillaVolverA = null; // {vista, secBoletines, docenteExpandido, reporte, scrollY} para el botón "← Volver"
let grillaSeleccion = new Set(); // estudiante_id seleccionados en la grilla de notas

// ¿A esta celda le falta algo (nota o concepto)?
function celdaFalta(celda) {
  if (!celda) return false;
  return celda.estado === "falta" || celda.concepto_estado === "falta";
}

function marcaConceptoHtml(celda) {
  const t = (celda.concepto_texto || "").replace(/"/g, "&quot;");
  if (celda.concepto_estado === "tiene") return `<span class="cn-marca ok" title="Concepto: ${t}">C</span>`;
  if (celda.concepto_estado === "falta") return `<span class="cn-marca falta" title="Falta el concepto de esta materia (se ve y se resuelve en Pendientes)">C</span>`;
  if (celda.concepto_estado === "revisado") return `<span class="cn-marca revisado" title="Concepto faltaba, ya revisado">C</span>`;
  return "";
}

function celdaGrillaHtml(areaId, celda) {
  if (!celda) return `<td class="celda-sin-dato">·</td>`;
  const cn = marcaConceptoHtml(celda);
  const cnFalta = celda.concepto_estado === "falta" ? " concepto-falta" : "";
  if (celda.estado === "nota") {
    const num = Number(celda.valor);
    const baja = !Number.isNaN(num) && num <= 2.0 ? " baja" : "";
    return `<td class="celda-nota${baja}${cnFalta}">${celda.valor}${cn}</td>`;
  }
  if (celda.estado === "falta") {
    return `<td class="celda-falta" data-celda-pendiente="${celda.pendiente_id}" title="Falta la nota en SAPRED — clic para marcar como revisado">FALTA${cn}</td>`;
  }
  if (celda.estado === "revisado") {
    return `<td class="celda-revisado" data-celda-pendiente="${celda.pendiente_id}" data-celda-reabrir="1" title="Ya se validó administrativamente — clic para volver a marcar como falta">✓ revisado${cn}</td>`;
  }
  if (celda.estado === "sin_auditar") {
    return `<td class="celda-sin-auditar${cnFalta}" title="Este grupo todavía no se ha auditado contra SAPRED en este período">—${cn}</td>`;
  }
  return `<td class="celda-sin-dato${cnFalta}" title="El grupo sí se auditó, pero esta materia puntual no quedó registrada">·${cn}</td>`;
}

function celdaObservacionHtml(fila) {
  const e = fila.observacion_estado;
  const t = (fila.observacion_texto || "").replace(/"/g, "&quot;");
  if (e === "tiene") return `<td class="celda-nota" title="${t}">✓</td>`;
  if (e === "falta") return `<td class="celda-falta" title="Falta la observación del director de grupo">FALTA</td>`;
  if (e === "revisado") return `<td class="celda-revisado" title="Faltaba, ya revisado">✓ rev.</td>`;
  if (e === "sin_auditar") return `<td class="celda-sin-auditar" title="No se ha importado el Boletín informativo de este grupo">—</td>`;
  return `<td class="celda-sin-dato">·</td>`;
}

function filaTieneFaltante(g, f) {
  if (Object.values(f.celdas).some(celdaFalta)) return true;
  return f.observacion_estado === "falta";
}

function fechaImpresionSapred() {
  const hoy = new Date();
  return `${MESES[hoy.getMonth()]} ${hoy.getDate()} de ${hoy.getFullYear()}`;
}

function grupoGrillaHtml(g) {
  const filas = grillaSoloFaltantes ? g.filas.filter((f) => filaTieneFaltante(g, f)) : g.filas;
  if (grillaSoloFaltantes && !filas.length) return "";

  const faltanNota = g.filas.reduce((acc, f) => acc + Object.values(f.celdas).filter((c) => c.estado === "falta").length, 0);
  const faltanConcepto = g.filas.reduce(
    (acc, f) => acc + Object.values(f.celdas).filter((c) => c.concepto_estado === "falta").length,
    0
  );
  const faltanObs = g.filas.filter((f) => f.observacion_estado === "falta").length;
  const hayFaltas = faltanNota || faltanConcepto || faltanObs;
  const totalCeldas = g.filas.length * g.areas.length;

  return `
    <details class="seccion-colapsable" open>
      <summary>
        ${g.nombre_grupo} — ${filas.length} estudiante(s)
        ${!g.auditado ? '<span class="badge-estado">sin auditar todavía</span>' : ""}
        ${g.auditado && faltanNota ? `<span class="badge-estado alerta">${faltanNota} nota(s)</span>` : ""}
        ${g.auditado && faltanConcepto ? `<span class="badge-estado alerta">${faltanConcepto} concepto(s)</span>` : ""}
        ${g.auditado && faltanObs ? `<span class="badge-estado alerta">${faltanObs} observación(es)</span>` : ""}
        ${g.auditado && !hayFaltas && totalCeldas ? `<span class="badge-estado ok">completo</span>` : ""}
        ${g.docente ? ` · Dir. grupo: ${g.docente.nombre_completo}` : ""}
      </summary>
      <div class="hoja-sapred">
        <div class="sapred-encabezado">
          <div class="sapred-campo"><span class="etiqueta">Curso</span><span class="valor">${g.nombre_grupo}, ${g.sede_nombre}</span></div>
          <div class="sapred-campo"><span class="etiqueta">Fecha Impresión</span><span class="valor">${fechaImpresionSapred()}</span></div>
          <div class="sapred-campo"><span class="etiqueta">Periodo</span><span class="valor">${g.periodo}</span></div>
        </div>
        <div class="tabla-scroll">
          <table class="tabla-grilla-notas tabla-sapred">
            <thead>
              <tr>
                <th class="col-sel no-imprimir" rowspan="3" title="Seleccionar"><input type="checkbox" data-grilla-sel-todos="${g.sede_id}-${g.grado}-${g.curso ?? ""}" /></th>
                <th class="col-no" rowspan="3">No.</th>
                <th class="col-codigo" rowspan="3">Código</th>
                <th class="col-estudiante" rowspan="3">Estudiante</th>
                ${g.areas.map((a) => `<th title="${a.nombre}${a.docente ? " — Prof. " + a.docente.nombre_completo : ""}">${a.codigo}${a.docente ? `<br><span class="th-prof">${a.docente.nombre_completo}</span>` : ""}</th>`).join("")}
                <th rowspan="3" title="Observación del director de grupo">Obs.</th>
              </tr>
              <tr>${g.areas.map(() => `<th class="sub">P${g.periodo} / Cn</th>`).join("")}</tr>
              <tr>${g.areas.map(() => `<th class="sub">nota · concepto</th>`).join("")}</tr>
            </thead>
            <tbody>
              ${filas
                .map(
                  (f, i) => `
                <tr data-grilla-fila="${f.estudiante_id}" class="${grillaSeleccion.has(f.estudiante_id) ? "grilla-fila-sel " : ""}${f.retirado ? "grilla-fila-retirado " : f.posible_retirado ? "grilla-fila-retiro " : ""}${grillaResaltarDoc && String(f.documento) === String(grillaResaltarDoc) ? "grilla-fila-resaltada" : ""}"${grillaResaltarDoc && String(f.documento) === String(grillaResaltarDoc) ? ' data-grilla-resaltada="1"' : ""}>
                  <td class="col-sel no-imprimir"><input type="checkbox" data-grilla-sel="${f.estudiante_id}" ${grillaSeleccion.has(f.estudiante_id) ? "checked" : ""} /></td>
                  <td class="col-no">${i + 1}</td>
                  <td class="col-codigo">${f.documento}</td>
                  <td class="col-estudiante">${
                    f.retirado
                      ? `<span class="nombre-retirado">${f.nombre_completo}</span> <span class="chip-retiro chip-retirado">✖ RETIRADO</span>`
                      : f.nombre_completo + (f.posible_retirado ? ' <span class="chip-retiro">🚪 posible retiro</span>' : "")
                  }</td>
                  ${g.areas.map((a) => celdaGrillaHtml(a.id, f.celdas[a.id])).join("")}
                  ${celdaObservacionHtml(f)}
                </tr>`
                )
                .join("")}
            </tbody>
          </table>
        </div>
        <div class="sapred-pie">
          <p class="sapred-convenciones"><strong>CONVENCIONES:</strong> ${g.areas
            .map((a) => `<strong>${a.codigo}:</strong> ${a.nombre.toUpperCase()}${a.docente ? ` (${a.docente.nombre_completo})` : ""}`)
            .join("&nbsp;&nbsp;&nbsp;")}</p>
          <p class="sapred-convenciones"><strong>Cn:</strong> Concepto de la materia · <strong>Obs.:</strong> Observación del director de grupo</p>
          ${
            g.docente
              ? `<div class="sapred-firma"><span class="firma-linea"></span><span class="firma-nombre">${g.docente.nombre_completo}</span><span class="firma-cargo">Director de Grupo</span></div>`
              : ""
          }
        </div>
      </div>
    </details>`;
}

// Informe imprimible "solo lo que falta", ordenado sede → grupo → área
// (profesor) → estudiante.
function informeFaltantesGrillaHtml(grupos, sedes) {
  const sede = sedes.find((s) => s.id === grillaSedeSeleccionada);
  const nombreGrado = (NOMBRES_GRADOS.find(([n]) => n === grillaGradoSeleccionado) || [null, ""])[1];
  const bloques = [];
  let totalItems = 0;
  const completos = [];

  grupos.forEach((g) => {
    const items = [];
    g.areas.forEach((a) => {
      const prof = a.docente ? a.docente.nombre_completo : "Sin profesor asignado";
      g.filas.forEach((f) => {
        const c = f.celdas[a.id] || {};
        const faltas = [];
        if (c.estado === "falta") faltas.push("falta NOTA");
        if (c.concepto_estado === "falta") faltas.push("falta CONCEPTO");
        if (faltas.length) items.push({ area: `${a.codigo} — ${a.nombre}`, prof, est: f.nombre_completo, doc: f.documento, que: faltas.join(" y ") });
      });
    });
    g.filas.forEach((f) => {
      if (f.observacion_estado === "falta") {
        items.push({ area: "OBSERVACIÓN (director de grupo)", prof: g.docente ? g.docente.nombre_completo : "Sin director asignado", est: f.nombre_completo, doc: f.documento, que: "falta OBSERVACIÓN" });
      }
    });
    items.sort((x, y) => x.area.localeCompare(y.area) || x.est.localeCompare(y.est));
    totalItems += items.length;
    if (items.length) bloques.push({ g, items });
    else if (g.auditado) completos.push(g.nombre_grupo);
  });

  const filaHtml = (it) => `<tr><td>${it.area}</td><td>${it.prof}</td><td>${it.est}</td><td>${it.doc}</td><td class="pendiente">${it.que}</td></tr>`;

  return `
    <div class="hoja-imprimir">
      ${membreteHtml(`FALTANTES DE BOLETÍN — PERÍODO ${notasPeriodo} ${notasAnio}${sede ? " — " + sede.nombre : ""}${nombreGrado ? " — " + nombreGrado : ""}`)}
      <div class="hoja-campos">
        <div class="campo"><span class="etiqueta">FECHA DEL INFORME:</span><span class="valor">${new Date().toLocaleDateString("es-CO")}</span></div>
        <div class="campo"><span class="etiqueta">TOTAL FALTANTES:</span><span class="valor">${totalItems}</span></div>
      </div>
      ${
        bloques.length
          ? bloques
              .map(
                (b) => `
        <h3 class="informe-sede-titulo">${b.g.nombre_grupo} (${b.items.length})</h3>
        <table class="tabla-informe">
          <thead><tr><th>Área</th><th>Profesor</th><th>Estudiante</th><th>Documento</th><th>Qué falta</th></tr></thead>
          <tbody>${b.items.map(filaHtml).join("")}</tbody>
        </table>`
              )
              .join("")
          : '<p class="pendiente">No falta nada con los filtros actuales. 🎉</p>'
      }
      ${completos.length ? `<h3 class="informe-sede-titulo">✓ Grupos completos</h3><p class="informe-completos-lista">${completos.join(" · ")}</p>` : ""}
    </div>
    <div class="toolbar no-imprimir"><button type="button" class="boton" onclick="window.print()">Imprimir</button></div>
  `;
}

function renderSeccionNotasGrilla(contenedor, sedes) {
  if (grillaSedeSeleccionada === null) {
    const ietaba = sedes.find((s) => s.nombre.toUpperCase().includes("I.E.T.A.B.A"));
    grillaSedeSeleccionada = ietaba ? ietaba.id : sedes[0]?.id;
  }
  if (!grillaSedeSeleccionada) {
    contenedor.innerHTML = '<p class="pendiente">No hay sedes IETABA registradas.</p>';
    return;
  }
  return cargarYPintarGrilla(contenedor, sedes);
}

async function cargarYPintarGrilla(contenedor, sedes) {
  contenedor.innerHTML = '<div class="estado-carga">Cargando notas...</div>';
  const params = new URLSearchParams({
    sede_id: grillaSedeSeleccionada,
    grado: grillaGradoSeleccionado,
    periodo: notasPeriodo,
    anio_lectivo: notasAnio,
  });
  if (grillaCursoSeleccionado !== "") params.set("curso", grillaCursoSeleccionado);
  let grupos;
  try {
    grupos = await api(`/api/boletines/grilla?${params}`);
  } catch (err) {
    contenedor.innerHTML = `<div class="alerta-caja">${err.message}</div>`;
    return;
  }
  pintarGrilla(contenedor, grupos, sedes);
}

function pintarGrilla(contenedor, grupos, sedes) {
  const cursosDisponibles = [...new Set(grupos.map((g) => g.curso).filter((c) => c !== null))].sort((a, b) => a - b);
  const totalEstudiantes = grupos.reduce((acc, g) => acc + g.filas.length, 0);

  contenedor.innerHTML = `
    ${
      grillaVolverA
        ? `<div class="toolbar no-imprimir" style="margin-bottom:8px"><button type="button" class="boton secundario" id="btn-volver-grilla">← Volver a donde estaba</button></div>`
        : ""
    }
    <p class="pendiente">Cada celda muestra la nota real de SAPRED, o marca claramente qué falta. Clic en "FALTA" para marcarla como revisada administrativamente.</p>

    <div class="barra-filtros no-imprimir">
      <label class="filtro-campo">Sede
        <select id="select-sede-grilla">
          ${sedes.map((s) => `<option value="${s.id}" ${s.id === grillaSedeSeleccionada ? "selected" : ""}>${s.nombre}</option>`).join("")}
        </select>
      </label>
      <label class="filtro-campo">Grado
        <select id="select-grado-grilla">
          ${NOMBRES_GRADOS.map(([n, nombre]) => `<option value="${n}" ${n === grillaGradoSeleccionado ? "selected" : ""}>${nombre}</option>`).join("")}
        </select>
      </label>
      <label class="filtro-campo">Sección
        <select id="select-curso-grilla">
          <option value="" ${grillaCursoSeleccionado === "" ? "selected" : ""}>Todas las secciones</option>
          ${cursosDisponibles.map((c) => `<option value="${c}" ${String(c) === String(grillaCursoSeleccionado) ? "selected" : ""}>Sección ${c}</option>`).join("")}
        </select>
      </label>
      <label class="filtro-campo">Período
        <select id="select-periodo-grilla">
          ${[1, 2, 3, 4].map((p) => `<option value="${p}" ${p === notasPeriodo ? "selected" : ""}>Período ${p}</option>`).join("")}
        </select>
      </label>
    </div>

    <div class="barra-filtros no-imprimir">
      <label class="check-linea filtro-check">
        <input type="checkbox" id="check-grilla-solo-faltantes" ${grillaSoloFaltantes ? "checked" : ""} />
        Solo lo que falta (nota, concepto u observación)
      </label>
      <button type="button" class="boton secundario" id="btn-grilla-informe">
        ${grillaModoInforme ? "Ocultar informe" : "🖨 Informe de faltantes para imprimir"}
      </button>
    </div>

    <div class="leyenda-grilla">
      <span><i style="background:#fee2e2"></i> Falta (nota o concepto)</span>
      <span><i style="background:#fef3c7"></i> Faltaba, ya revisado</span>
      <span><i style="background:#f1f2f5"></i> Sin dato puntual</span>
      <span><i style="background:#f8f8f8"></i> Sin auditar todavía</span>
      <span><i style="background:#dcfce7"></i> Completo · <b>C</b> = concepto de la materia</span>
    </div>

    <div id="zona-informe-grilla">${grillaModoInforme ? informeFaltantesGrillaHtml(grupos, sedes) : ""}</div>

    <div id="barra-seleccion-grilla" class="barra-seleccion-grilla no-imprimir" ${grillaSeleccion.size ? "" : "hidden"}>
      <strong id="barra-seleccion-conteo">${grillaSeleccion.size} seleccionado(s)</strong>
      <button type="button" class="boton secundario" id="btn-sel-posible-retiro">🚪 Marcar posible retiro</button>
      <button type="button" class="boton secundario" id="btn-sel-retirado">✖ Marcar retirado</button>
      <button type="button" class="boton secundario" id="btn-sel-quitar-retiro">↩ Quitar marca (retiro)</button>
      <button type="button" class="boton secundario" id="btn-sel-revisado">✓ Marcar revisado lo que les falta</button>
      <button type="button" class="boton-texto-chico" id="btn-sel-limpiar">✕ Quitar selección</button>
    </div>

    ${
      grupos.length
        ? `<p class="pendiente no-imprimir">${totalEstudiantes} estudiante(s) en ${grupos.length} grupo(s)</p>
           <div class="${grillaModoInforme ? "no-imprimir" : ""}">${grupos.map(grupoGrillaHtml).join("") || '<p class="pendiente">Ningún grupo con faltantes.</p>'}</div>`
        : '<p class="pendiente">No hay estudiantes activos para ese grado en esta sede.</p>'
    }
  `;

  document.getElementById("select-sede-grilla").addEventListener("change", (e) => {
    grillaSedeSeleccionada = Number(e.target.value);
    grillaCursoSeleccionado = "";
    grillaSeleccion.clear();
    cargarYPintarGrilla(contenedor, sedes);
  });
  document.getElementById("select-grado-grilla").addEventListener("change", (e) => {
    grillaGradoSeleccionado = Number(e.target.value);
    grillaCursoSeleccionado = "";
    grillaSeleccion.clear();
    cargarYPintarGrilla(contenedor, sedes);
  });
  document.getElementById("select-curso-grilla").addEventListener("change", (e) => {
    grillaCursoSeleccionado = e.target.value;
    grillaSeleccion.clear();
    cargarYPintarGrilla(contenedor, sedes);
  });
  document.getElementById("select-periodo-grilla").addEventListener("change", (e) => {
    notasPeriodo = Number(e.target.value);
    const cabecera = document.getElementById("notas-periodo-cabecera");
    if (cabecera) cabecera.value = String(notasPeriodo);
    grillaSeleccion.clear();
    cargarYPintarGrilla(contenedor, sedes);
  });

  document.getElementById("check-grilla-solo-faltantes").addEventListener("change", (e) => {
    grillaSoloFaltantes = e.target.checked;
    pintarGrilla(contenedor, grupos, sedes);
  });
  document.getElementById("btn-grilla-informe").addEventListener("click", () => {
    grillaModoInforme = !grillaModoInforme;
    pintarGrilla(contenedor, grupos, sedes);
  });

  document.querySelectorAll("[data-celda-pendiente]").forEach((celda) => {
    celda.addEventListener("click", async () => {
      const resueltoActual = celda.dataset.celdaReabrir === "1";
      await api(`/api/boletines/pendientes/${celda.dataset.celdaPendiente}`, {
        method: "PATCH",
        body: JSON.stringify({ resuelto: !resueltoActual }),
      });
      await cargarYPintarGrilla(contenedor, sedes);
    });
  });

  // --- Selección de estudiantes en la grilla + acciones en lote ----------
  const refrescarBarraSeleccion = () => {
    const barra = document.getElementById("barra-seleccion-grilla");
    if (!barra) return;
    barra.hidden = grillaSeleccion.size === 0;
    const conteo = document.getElementById("barra-seleccion-conteo");
    if (conteo) conteo.textContent = `${grillaSeleccion.size} seleccionado(s)`;
    contenedor.querySelectorAll("[data-grilla-fila]").forEach((tr) => {
      tr.classList.toggle("grilla-fila-sel", grillaSeleccion.has(Number(tr.dataset.grillaFila)));
    });
  };

  contenedor.querySelectorAll("[data-grilla-sel]").forEach((chk) => {
    chk.addEventListener("change", () => {
      const id = Number(chk.dataset.grillaSel);
      if (chk.checked) grillaSeleccion.add(id);
      else grillaSeleccion.delete(id);
      refrescarBarraSeleccion();
    });
  });
  contenedor.querySelectorAll("[data-grilla-sel-todos]").forEach((chk) => {
    chk.addEventListener("change", () => {
      const tabla = chk.closest("table");
      tabla.querySelectorAll("[data-grilla-sel]").forEach((c) => {
        c.checked = chk.checked;
        const id = Number(c.dataset.grillaSel);
        if (chk.checked) grillaSeleccion.add(id);
        else grillaSeleccion.delete(id);
      });
      refrescarBarraSeleccion();
    });
  });

  document.getElementById("btn-sel-limpiar")?.addEventListener("click", () => {
    grillaSeleccion.clear();
    contenedor.querySelectorAll("[data-grilla-sel], [data-grilla-sel-todos]").forEach((c) => (c.checked = false));
    refrescarBarraSeleccion();
  });

  document.getElementById("btn-sel-posible-retiro")?.addEventListener("click", async () => {
    const ids = [...grillaSeleccion];
    if (!ids.length) return;
    if (!confirm(`Marcar ${ids.length} estudiante(s) como "posible retiro"?\nSeguirán en el sistema pero dejarán de contar en los pendientes de boletín.`)) return;
    const barra = document.getElementById("barra-seleccion-grilla");
    if (barra) barra.querySelectorAll("button").forEach((b) => (b.disabled = true));
    await Promise.all(
      ids.map((id) =>
        api(`/api/estudiantes/${id}`, { method: "PATCH", body: JSON.stringify({ posible_retirado: true, retirado: false }) })
      )
    );
    grillaSeleccion.clear();
    await cargarYPintarGrilla(contenedor, sedes);
  });

  // Quitar la marca (no puede hacerse desde "¿qué falta?" porque ahí los
  // posibles retirados ya no aparecen) y marcar "retirado" (solo una marca:
  // el estudiante sigue en el sistema y en esta grilla).
  const cambiarEstadoSeleccion = async (cuerpo, pregunta) => {
    const ids = [...grillaSeleccion];
    if (!ids.length || !confirm(pregunta(ids.length))) return;
    const barra = document.getElementById("barra-seleccion-grilla");
    if (barra) barra.querySelectorAll("button").forEach((b) => (b.disabled = true));
    await Promise.all(
      ids.map((id) => api(`/api/estudiantes/${id}`, { method: "PATCH", body: JSON.stringify(cuerpo) }))
    );
    grillaSeleccion.clear();
    await cargarYPintarGrilla(contenedor, sedes);
  };
  document.getElementById("btn-sel-quitar-retiro")?.addEventListener("click", () =>
    cambiarEstadoSeleccion(
      { posible_retirado: false, retirado: false },
      (n) => `Quitar la marca de "posible retiro" / "retirado" a ${n} estudiante(s)?\nVolverán a contar en los pendientes de boletín.`
    )
  );
  document.getElementById("btn-sel-retirado")?.addEventListener("click", () =>
    cambiarEstadoSeleccion(
      { retirado: true },
      (n) => `Marcar ${n} estudiante(s) como "retirado"?\nSiguen en el sistema y en la grilla (con la etiqueta), pero no cuentan en pendientes ni en la lista de Reportes. La marca se puede quitar.`
    )
  );

  document.getElementById("btn-sel-revisado")?.addEventListener("click", async () => {
    const ids = new Set(grillaSeleccion);
    if (!ids.size) return;
    const pendienteIds = [];
    grupos.forEach((g) =>
      g.filas.forEach((f) => {
        if (!ids.has(f.estudiante_id)) return;
        Object.values(f.celdas).forEach((c) => {
          if (c.estado === "falta" && c.pendiente_id) pendienteIds.push(c.pendiente_id);
          if (c.concepto_estado === "falta" && c.concepto_pendiente_id) pendienteIds.push(c.concepto_pendiente_id);
        });
        if (f.observacion_estado === "falta" && f.observacion_pendiente_id) pendienteIds.push(f.observacion_pendiente_id);
      })
    );
    if (!pendienteIds.length) {
      alert("Los estudiantes seleccionados no tienen nada pendiente en este período.");
      return;
    }
    if (!confirm(`Marcar como revisado ${pendienteIds.length} pendiente(s) de ${ids.size} estudiante(s)?`)) return;
    const barra = document.getElementById("barra-seleccion-grilla");
    if (barra) barra.querySelectorAll("button").forEach((b) => (b.disabled = true));
    await api("/api/boletines/pendientes/resolver-lote", {
      method: "POST",
      body: JSON.stringify({ ids: pendienteIds, resuelto: true }),
    });
    grillaSeleccion.clear();
    await cargarYPintarGrilla(contenedor, sedes);
  });

  document.getElementById("btn-volver-grilla")?.addEventListener("click", volverDeGrilla);

  // Llegamos aquí desde "¿qué falta?" con un estudiante para resaltar. El
  // resaltado NO se quita solo: se mantiene (aunque se toque la fila o se
  // pase el mouse) hasta que se salga de la pantalla o se use "← Volver".
  if (grillaResaltarDoc) {
    const fila = contenedor.querySelector('[data-grilla-resaltada="1"]');
    if (fila) {
      const det = fila.closest("details");
      if (det) det.open = true;
      fila.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }
}

// Abre Notas -> Grilla en el grupo indicado y resalta al estudiante (doc).
function irAGrillaNotas({ sedeId, grado, curso, periodo, doc, volver }) {
  seccionNotas = "grilla";
  vistaActual = "notas";
  if (sedeId != null) grillaSedeSeleccionada = Number(sedeId);
  if (grado != null && grado !== "") grillaGradoSeleccionado = Number(grado);
  grillaCursoSeleccionado = curso == null || curso === "" ? "" : String(curso);
  if (periodo) notasPeriodo = Number(periodo);
  grillaSoloFaltantes = false;
  grillaResaltarDoc = doc != null ? String(doc) : null;
  grillaVolverA = volver || null;
  tabs.forEach((t) => t.classList.remove("activo"));
  document.querySelector('[data-vista="notas"]')?.classList.add("activo");
  cerrarSidebarMovil();
  render();
}

// Vuelve a EXACTAMENTE donde se estaba antes de entrar a la grilla.
async function volverDeGrilla() {
  const v = grillaVolverA;
  grillaVolverA = null;
  grillaResaltarDoc = null;
  if (!v) {
    seccionNotas = "resumen";
    render();
    return;
  }
  vistaActual = v.vista;
  if (v.secBoletines) seccionBoletines = v.secBoletines;
  if ("docenteExpandido" in v) porDocenteExpandido = v.docenteExpandido;
  if ("reporte" in v) porDocenteReporte = v.reporte;
  tabs.forEach((t) => t.classList.remove("activo"));
  document.querySelector(`[data-vista="${v.vista}"]`)?.classList.add("activo");
  await render();
  // reabrir el drill-down del docente y restaurar el scroll
  if (v.vista === "boletines" && v.secBoletines === "docentes" && porDocenteExpandido) {
    await cargarDetalleDocente(porDocenteExpandido);
  }
  requestAnimationFrame(() => window.scrollTo(0, v.scrollY || 0));
  setTimeout(() => window.scrollTo(0, v.scrollY || 0), 120);
}

// Marca / desmarca a un estudiante como "posible retirado" (no cuenta en
// pendientes). `estado` = "1" si ACTUALMENTE está marcado.
async function alternarPosibleRetiro(estudianteId, estadoActual) {
  const nuevo = estadoActual !== "1";
  await api(`/api/estudiantes/${estudianteId}`, {
    method: "PATCH",
    body: JSON.stringify({ posible_retirado: nuevo }),
  });
  return nuevo;
}

// --- Sección: Por docente (¿a este profesor le falta algo?) --------------

async function renderSeccionPorDocente() {
  if (porDocenteReporte) return renderReporteFaltantesDocente();
  const contenedor = document.getElementById("contenido-boletines");
  const params = new URLSearchParams({ anio_lectivo: filtroBoletinesAnio, periodo: filtroBoletinesPeriodo });
  const resp = await api(`/api/boletines/por-docente?${params}`);
  const lista = resp.docentes;

  const sedesLista = [...new Set(lista.flatMap((d) => d.sedes || []))].sort();
  if (porDocenteSede && !sedesLista.includes(porDocenteSede)) porDocenteSede = "";

  const q = porDocenteBusqueda.trim().toLowerCase();
  const filtrados = lista.filter((d) => {
    if (porDocenteSede && !(d.sedes || []).includes(porDocenteSede)) return false;
    if (!q) return true;
    return (
      d.docente.nombre_completo.toLowerCase().includes(q) ||
      d.grupos.some((g) => g.toLowerCase().includes(q)) ||
      d.areas.some((a) => a.toLowerCase().includes(q)) ||
      (d.sedes || []).some((s) => s.toLowerCase().includes(q))
    );
  });

  const conPendientes = filtrados.filter((d) => !d.al_dia);
  const alDia = filtrados.filter((d) => d.al_dia);

  const desglose = (t) => {
    const p = [];
    if (t.nota) p.push(`${t.nota} nota${t.nota > 1 ? "s" : ""}`);
    if (t.concepto) p.push(`${t.concepto} concepto${t.concepto > 1 ? "s" : ""}`);
    if (t.observacion) p.push(`${t.observacion} observación${t.observacion > 1 ? "es" : ""}`);
    return p.join(" · ");
  };

  const tarjeta = (d) => `
    <div class="doc-pend-card ${d.al_dia ? "al-dia" : ""}" data-doc="${d.docente.id}">
      <div class="doc-pend-head">
        <strong>${d.docente.nombre_completo}</strong>
        ${
          d.al_dia
            ? `<span class="badge-estado ok">✅ Al día</span>`
            : `<span class="badge-estado alerta">⚠ ${d.abiertos} pendiente${d.abiertos > 1 ? "s" : ""}</span>`
        }
      </div>
      ${
        d.dirige && d.dirige.length
          ? `<div class="doc-pend-dirige" title="Como director de grupo responde por las observaciones y la nota de comportamiento (Desempeño Actitudinal) de este grupo">🎓 Director de grupo: ${d.dirige.join(" · ")}</div>`
          : ""
      }
      ${!d.al_dia ? `<div class="doc-pend-desglose">${desglose(d.por_tipo)}</div>` : ""}
      ${d.sedes && d.sedes.length ? `<div class="doc-pend-sede">🏫 ${d.sedes.join(" · ")}</div>` : ""}
      <div class="doc-pend-grupos">${d.grupos.join(" · ")}</div>
      ${!d.al_dia ? `<button type="button" class="boton-texto-chico" data-abrir-doc="${d.docente.id}">${porDocenteExpandido === d.docente.id ? "Ocultar" : "Ver qué falta →"}</button>` : ""}
      ${porDocenteExpandido === d.docente.id ? `<div class="doc-pend-detalle" id="doc-detalle-${d.docente.id}"><p class="estado-carga">Cargando…</p></div>` : ""}
    </div>`;

  contenedor.innerHTML = `
    <div class="pagina-header no-imprimir">
      <div>
        <h2 style="margin:0; font-size:20px">Por docente — Período ${filtroBoletinesPeriodo}</h2>
        <p class="subtitulo-pagina">Qué le falta a cada profesor (notas, conceptos y observaciones) EN ESTE PERÍODO, según sus grupos y su horario.</p>
      </div>
      <div class="filtro-campo" style="flex-direction:row; gap:8px; align-items:flex-end; flex-wrap:wrap">
        <label class="filtro-campo">Período
          <select id="por-docente-periodo">
            ${[1, 2, 3, 4].map((p) => `<option value="${p}" ${p === filtroBoletinesPeriodo ? "selected" : ""}>Período ${p}</option>`).join("")}
          </select>
        </label>
        <label class="filtro-campo">Sede
          <select id="por-docente-sede">
            <option value="">Todas las sedes</option>
            ${sedesLista.map((s) => `<option value="${s}" ${s === porDocenteSede ? "selected" : ""}>${s}</option>`).join("")}
          </select>
        </label>
        <button type="button" class="boton secundario" id="btn-reporte-por-docente">🖨 Reporte para imprimir</button>
        <button type="button" class="boton secundario" id="btn-depurar-obsoletos" title="Cierra los pendientes que ya están cargados en SAPRED pero quedaron abiertos de una auditoría vieja">🧹 Limpiar ya resueltos</button>
      </div>
    </div>
    <div class="buscador-principal no-imprimir">
      <span class="buscador-principal-icono" aria-hidden="true">🔎</span>
      <input type="text" id="buscar-por-docente" placeholder="Buscar profesor, grupo o área…" value="${porDocenteBusqueda}" />
    </div>
    ${
      !resp.hay_auditoria
        ? `<div class="callout-boletines warn">⚠ Todavía no se ha hecho la auditoría (ni importado nada) del <strong>Período ${filtroBoletinesPeriodo}</strong>. Ve a <strong>SAPRED → Auditoría</strong> y elige ese período. Hasta entonces esta lista no refleja lo que falta de verdad.</div>`
        : ""
    }
    <p class="conteo-resultados">Período ${filtroBoletinesPeriodo} · ${conPendientes.length} con pendientes · ${alDia.length} al día · ${lista.length} docentes en total</p>
    ${
      conPendientes.length
        ? `<div class="doc-pend-lista">${conPendientes.map(tarjeta).join("")}</div>`
        : `<div class="estado-vacio"><div class="estado-vacio-icono">${resp.hay_auditoria ? "🎉" : "📭"}</div><h3>${resp.hay_auditoria ? "Nadie tiene pendientes con este filtro" : "Sin datos de este período"}</h3></div>`
    }
    ${
      alDia.length
        ? `<details class="seccion-colapsable" style="margin-top:16px"><summary>Al día (${alDia.length})</summary>
             <div class="doc-pend-lista">${alDia.map(tarjeta).join("")}</div></details>`
        : ""
    }
  `;

  document.getElementById("por-docente-periodo").addEventListener("change", (e) => {
    filtroBoletinesPeriodo = Number(e.target.value);
    porDocenteExpandido = null;
    render(); // re-renderiza también la cabecera del módulo con el nuevo período
  });

  document.getElementById("por-docente-sede").addEventListener("change", (e) => {
    porDocenteSede = e.target.value;
    porDocenteExpandido = null;
    renderSeccionPorDocente();
  });

  document.getElementById("btn-reporte-por-docente").addEventListener("click", () => {
    porDocenteReporte = true;
    renderSeccionPorDocente();
  });

  document.getElementById("btn-depurar-obsoletos").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Limpiando…";
    try {
      const r = await api(
        `/api/boletines/pendientes/depurar-obsoletos?anio_lectivo=${filtroBoletinesAnio}&periodo=${filtroBoletinesPeriodo}`,
        { method: "POST" }
      );
      alert(
        r.cerrados
          ? `${r.cerrados} pendiente(s) cerrado(s): ya estaban cargados en SAPRED.`
          : "No había pendientes viejos que cerrar. Todo al día."
      );
      await renderSeccionPorDocente();
    } catch (err) {
      alert(err.message);
      btn.disabled = false;
      btn.textContent = "🧹 Limpiar ya resueltos";
    }
  });

  document.getElementById("buscar-por-docente").addEventListener("input", (e) => {
    clearTimeout(temporizadorBuscarFaltantes);
    const v = e.target.value;
    temporizadorBuscarFaltantes = setTimeout(() => {
      porDocenteBusqueda = v;
      renderSeccionPorDocente();
    }, 300);
  });

  contenedor.querySelectorAll("[data-abrir-doc]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const id = Number(btn.dataset.abrirDoc);
      porDocenteExpandido = porDocenteExpandido === id ? null : id;
      await renderSeccionPorDocente();
      if (porDocenteExpandido) await cargarDetalleDocente(porDocenteExpandido);
    })
  );
  if (porDocenteExpandido) await cargarDetalleDocente(porDocenteExpandido);
}

async function renderReporteFaltantesDocente() {
  const contenedor = document.getElementById("contenido-boletines");
  contenedor.innerHTML = '<div class="estado-carga">Generando reporte…</div>';
  const params = new URLSearchParams({ anio_lectivo: filtroBoletinesAnio, periodo: filtroBoletinesPeriodo });
  let rep;
  try {
    rep = await api(`/api/boletines/por-docente/reporte?${params}`);
  } catch (err) {
    contenedor.innerHTML = `<div class="alerta-caja">${err.message}</div>`;
    return;
  }

  const q = reporteDocenteFiltro.trim().toLowerCase();
  let docentes = rep.docentes.filter((d) => d.items.length);
  const totalDocentesConPendientes = docentes.length;
  const sedesReporte = [...new Set(docentes.flatMap((d) => d.sedes || []))].sort();
  if (porDocenteSede && !sedesReporte.includes(porDocenteSede)) porDocenteSede = "";
  if (porDocenteSede) docentes = docentes.filter((d) => (d.sedes || []).includes(porDocenteSede));
  if (q) docentes = docentes.filter((d) => d.docente.nombre_completo.toLowerCase().includes(q));

  // "la nota", "el concepto", "la observación"
  const FALTA = { nota: "la nota", concepto: "el concepto", observacion: "la observación" };
  const listaFalta = (tipos) => {
    const t = [...tipos].sort();
    const txt = t.map((x) => FALTA[x] || x);
    return txt.length <= 1 ? txt.join("") : txt.slice(0, -1).join(", ") + " y " + txt[txt.length - 1];
  };

  // Agrupa los items de un docente por (grupo, área); junta los tipos por estudiante.
  const bloquesDe = (d) => {
    const mapa = new Map();
    d.items.forEach((it) => {
      const key = `${it.nombre_grupo}||${it.area_nombre}`;
      if (!mapa.has(key))
        mapa.set(key, {
          grupo: it.nombre_grupo,
          area: it.area_nombre,
          esDirector: it.area_id === null,
          total: it.total_grupo,
          tiposGrupo: new Set(),
          porEstudiante: new Map(),
        });
      const b = mapa.get(key);
      b.total = it.total_grupo || b.total;
      if (it.alcance === "grupo") b.tiposGrupo.add(it.tipo);
      else
        it.estudiantes.forEach((nom) => {
          if (!b.porEstudiante.has(nom)) b.porEstudiante.set(nom, new Set());
          b.porEstudiante.get(nom).add(it.tipo);
        });
    });
    return [...mapa.values()].sort(
      (a, b) => Number(b.esDirector) - Number(a.esDirector) || a.grupo.localeCompare(b.grupo) || a.area.localeCompare(b.area)
    );
  };

  const bloqueHtml = (b) => {
    const lineas = [];
    if (b.tiposGrupo.size)
      lineas.push(
        `<li><strong>A todo el grupo</strong> le falta ${listaFalta(b.tiposGrupo)}${b.total ? ` — son ${b.total} estudiantes` : ""}.</li>`
      );
    [...b.porEstudiante.entries()]
      .sort((x, y) => x[0].localeCompare(y[0]))
      .forEach(([nom, tipos]) => lineas.push(`<li>${nom} — falta ${listaFalta(tipos)}</li>`));
    return `
      <div class="reporte-bloque">
        <p class="reporte-bloque-titulo">${b.grupo} · ${b.area}${b.esDirector ? " <em>(como director de grupo)</em>" : ""}</p>
        <ul class="reporte-lista">${lineas.join("")}</ul>
      </div>`;
  };

  const bloqueDocente = (d) => `
    <section class="reporte-docente${reporteDocenteUnaHoja ? " una-hoja" : ""}">
      <h3 class="reporte-docente-nombre">${d.docente.nombre_completo}</h3>
      <p class="reporte-docente-sub">
        ${d.sedes && d.sedes.length ? `🏫 ${d.sedes.join(", ")} · ` : ""}
        ${d.dirige.length ? `🎓 Director de grupo de <strong>${d.dirige.join(", ")}</strong> · ` : ""}
        Le falta registrar información en <strong>${new Set(d.items.map((it) => it.nombre_grupo)).size}</strong> grupo(s).
      </p>
      ${bloquesDe(d).map(bloqueHtml).join("")}
      ${
        d.grupos_ok && d.grupos_ok.length
          ? `<p class="reporte-ok">✓ Sin pendientes en: ${d.grupos_ok.join(", ")}</p>`
          : ""
      }
    </section>`;

  contenedor.innerHTML = `
    <div class="toolbar no-imprimir" style="margin-bottom:10px; gap:8px; flex-wrap:wrap">
      <button type="button" class="boton secundario" id="btn-volver-por-docente">← Volver a la lista</button>
      <input type="text" id="filtro-reporte-docente" class="input-inline" placeholder="Filtrar por profesor…" value="${reporteDocenteFiltro}" style="min-width:200px" />
      <select id="filtro-reporte-sede" class="input-inline">
        <option value="">Todas las sedes</option>
        ${sedesReporte.map((s) => `<option value="${s}" ${s === porDocenteSede ? "selected" : ""}>${s}</option>`).join("")}
      </select>
      <label class="check-linea"><input type="checkbox" id="chk-una-hoja" ${reporteDocenteUnaHoja ? "checked" : ""} /> Una hoja por profesor</label>
      <button type="button" class="boton" onclick="window.print()">🖨 Imprimir / Guardar PDF</button>
    </div>
    <div class="hoja-imprimir">
      ${membreteHtml(`LO QUE LE FALTA A CADA DOCENTE — PERÍODO ${filtroBoletinesPeriodo} · ${filtroBoletinesAnio}`)}
      <div class="hoja-campos">
        <div class="campo"><span class="etiqueta">FECHA:</span><span class="valor">${new Date().toLocaleDateString("es-CO")}</span></div>
        <div class="campo"><span class="etiqueta">PROFESORES CON PENDIENTES:</span><span class="valor">${q ? `${docentes.length} de ${totalDocentesConPendientes}` : docentes.length}</span></div>
      </div>
      <p class="reporte-ayuda">Para cada profesor: en qué grupo y materia le falta, y a qué estudiantes. Si le falta a <em>todo</em> el grupo, se indica así en vez de listar cada nombre.${q ? ` <span class="no-imprimir">· Filtro: "${reporteDocenteFiltro}"</span>` : ""}</p>
      ${
        docentes.length
          ? docentes.map(bloqueDocente).join("")
          : `<p class="pendiente">${totalDocentesConPendientes ? "Ningún profesor coincide con el filtro." : "Nadie tiene pendientes en este período. 🎉"}</p>`
      }
    </div>
  `;

  document.getElementById("btn-volver-por-docente").addEventListener("click", () => {
    porDocenteReporte = false;
    renderSeccionPorDocente();
  });
  const inp = document.getElementById("filtro-reporte-docente");
  inp.addEventListener("input", (e) => {
    clearTimeout(temporizadorBuscarFaltantes);
    const v = e.target.value;
    temporizadorBuscarFaltantes = setTimeout(() => {
      reporteDocenteFiltro = v;
      renderReporteFaltantesDocente();
    }, 300);
  });
  document.getElementById("chk-una-hoja").addEventListener("change", (e) => {
    reporteDocenteUnaHoja = e.target.checked;
    renderReporteFaltantesDocente();
  });
  document.getElementById("filtro-reporte-sede").addEventListener("change", (e) => {
    porDocenteSede = e.target.value;
    renderReporteFaltantesDocente();
  });
}

async function cargarDetalleDocente(docenteId) {
  const caja = document.getElementById(`doc-detalle-${docenteId}`);
  if (!caja) return;
  const params = new URLSearchParams({
    anio_lectivo: filtroBoletinesAnio,
    periodo: filtroBoletinesPeriodo,
    docente_id: docenteId,
    solo_no_resueltos: "true",
  });
  const pend = await api(`/api/boletines/pendientes?${params}`);
  if (!pend.length) {
    caja.innerHTML = `<p class="conteo-resultados">Ya no tiene pendientes.</p>`;
    return;
  }
  // Agrupa por grupo
  const porGrupo = {};
  pend.forEach((p) => (porGrupo[`${p.sede_nombre} · ${p.nombre_grupo}`] ||= []).push(p));
  caja.innerHTML = Object.entries(porGrupo)
    .map(
      ([grupo, items]) => `
        <h4 class="doc-pend-grupo-titulo">${grupo} <span class="conteo-resultados">(${items.length})</span></h4>
        <div class="tabla-scroll"><table class="no-imprimir">
          <thead><tr><th>Estudiante</th><th>Área</th><th>Tipo</th><th>Grupo</th><th>Estado</th><th></th></tr></thead>
          <tbody>${items.map(filaFaltanteHtml).join("")}</tbody>
        </table></div>`
    )
    .join("");
  // Acciones dentro del drill-down (sin salir de "Por docente").
  caja.querySelectorAll("[data-resolver]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      await api(`/api/boletines/pendientes/${btn.dataset.resolver}`, {
        method: "PATCH",
        body: JSON.stringify({ resuelto: true }),
      });
      await renderSeccionPorDocente();
      if (porDocenteExpandido) await cargarDetalleDocente(porDocenteExpandido);
    })
  );
  caja.querySelectorAll("[data-ver-estudiante-faltante]").forEach((el) =>
    el.addEventListener("click", () =>
      irAGrillaNotas({
        sedeId: el.dataset.gSede,
        grado: el.dataset.gGrado,
        curso: el.dataset.gCurso,
        periodo: el.dataset.gPeriodo,
        doc: el.dataset.gDoc,
        volver: {
          vista: "boletines",
          secBoletines: "docentes",
          docenteExpandido: docenteId,
          scrollY: window.scrollY,
        },
      })
    )
  );
  caja.querySelectorAll("[data-posible-retiro]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      await alternarPosibleRetiro(Number(btn.dataset.posibleRetiro), btn.dataset.prEstado);
      await renderSeccionPorDocente();
      if (porDocenteExpandido) await cargarDetalleDocente(porDocenteExpandido);
    })
  );
}

// --- Sección: Continuidad académica (P1 vs P2) ------------------------------

async function renderSeccionContinuidad() {
  const contenedor = document.getElementById("contenido-boletines");
  const todasLasSedes = await api("/api/sedes");
  const sedes = todasLasSedes.filter((s) => s.pertenece_ietaba);

  if (continuidadSedeSeleccionada === null) {
    const ietaba = sedes.find((s) => s.nombre.toUpperCase().includes("I.E.T.A.B.A"));
    continuidadSedeSeleccionada = ietaba ? ietaba.id : sedes[0]?.id;
  }
  if (!continuidadSedeSeleccionada) {
    contenedor.innerHTML = '<p class="pendiente">No hay sedes IETABA registradas.</p>';
    return;
  }
  await cargarYPintarContinuidad(contenedor, sedes);
}

async function cargarYPintarContinuidad(contenedor, sedes) {
  contenedor.innerHTML = '<div class="estado-carga">Calculando continuidad académica...</div>';
  let resumen;
  try {
    resumen = await api(`/api/boletines/continuidad?sede_id=${continuidadSedeSeleccionada}&anio_lectivo=${filtroBoletinesAnio}`);
  } catch (err) {
    contenedor.innerHTML = `<div class="alerta-caja">${err.message}</div>`;
    return;
  }
  pintarInformeContinuidad(contenedor, resumen, sedes);
}

function pintarInformeContinuidad(contenedor, r, sedes) {
  const gradosSinAuditar = r.por_grado.filter((g) => !g.p1_auditado && !g.p2_auditado);
  const gradosConNovedades = r.por_grado.filter((g) => g.novedades.length);

  contenedor.innerHTML = `
    <div class="pagina-header no-imprimir">
      <div>
        <h2 style="margin:0; font-size:20px">Continuidad académica</h2>
        <p class="subtitulo-pagina">Comparación de evidencia académica entre períodos.</p>
      </div>
      <select id="select-sede-continuidad" style="max-width:260px">
        ${sedes.map((s) => `<option value="${s.id}" ${s.id === continuidadSedeSeleccionada ? "selected" : ""}>${s.nombre}</option>`).join("")}
      </select>
    </div>
    <p class="pendiente">Año lectivo ${r.anio_lectivo} · Compara Período 1 contra Período 2 para ${r.sede_nombre}. Un grado sin auditoría en SAPRED queda marcado como "sin auditar", nunca como retirado.</p>

    <div class="resumen-reportes">
      <div class="metric-card"><span>Matriculados</span><strong>${r.total_matriculados}</strong></div>
      <div class="metric-card ok"><span>Con actividad P1</span><strong>${r.total_con_notas_p1}</strong></div>
      <div class="metric-card alerta"><span>Sin evidencia P1</span><strong>${r.total_sin_evidencia_p1}</strong></div>
      <div class="metric-card ok"><span>Activos P2</span><strong>${r.total_activos_p2}</strong></div>
      <div class="metric-card ${r.total_posibles_retiros ? "alerta" : "ok"}"><span>Posibles retiros</span><strong>${r.total_posibles_retiros}</strong></div>
      <div class="metric-card"><span>% continuidad P1→P2</span><strong>${r.porcentaje_continuidad}%</strong></div>
    </div>

    ${
      gradosSinAuditar.length
        ? `<div class="callout-boletines warn">
             ⚠ ${gradosSinAuditar.length} grado(s) sin ninguna auditoría todavía (ni P1 ni P2), no se incluyen en los totales de continuidad:
             ${gradosSinAuditar.map((g) => g.nombre_grado).join(", ")}.
             Ve a SAPRED → Auditoría para completarlos.
           </div>`
        : ""
    }

    <div class="tabla-scroll">
    <table>
      <thead>
        <tr><th>Grado</th><th>Matriculados</th><th>Con notas P1</th><th>Sin notas P1</th><th>Activos P2</th><th>Posibles retiros</th><th>Observaciones</th><th>Cobertura</th></tr>
      </thead>
      <tbody>
        ${r.por_grado
          .map(
            (g) => `
          <tr>
            <td>${g.nombre_grado}</td>
            <td>${g.matriculados}</td>
            <td>${g.con_notas_p1}</td>
            <td>${g.sin_notas_p1}</td>
            <td>${g.activos_p2}</td>
            <td>${g.posibles_retiros}</td>
            <td>${g.observaciones}</td>
            <td>P1 ${g.p1_auditado ? "✓" : "—"} · P2 ${g.p2_auditado ? "✓" : "—"}</td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>
    </div>

    <h3 class="subtitulo-seccion">Novedades por grado</h3>
    ${
      gradosConNovedades.length
        ? gradosConNovedades
            .map(
              (g) => `
          <details class="seccion-colapsable">
            <summary>${g.nombre_grado} — ${g.novedades.length} novedad(es)</summary>
            ${
              g.cursos_sin_notas_p2.length
                ? `<div class="callout-boletines warn">⚠ Curso(s) completos sin ninguna nota en P2 (probable atraso de cargue del docente, no retiro): ${g.cursos_sin_notas_p2.join(", ")}</div>`
                : ""
            }
            <div class="tabla-scroll tabla-scroll-alto">
            <table>
              <thead><tr><th>Estudiante</th><th>Documento</th><th>Curso</th><th>Estado</th><th>Evidencia</th></tr></thead>
              <tbody>
                ${g.novedades
                  .map((n) => {
                    const et = ETIQUETAS_ESTADO_CONTINUIDAD[n.estado] || { texto: n.estado, clase: "" };
                    return `<tr>
                      <td>${n.nombre_completo}</td>
                      <td>${n.documento}</td>
                      <td>${n.curso ?? "—"}</td>
                      <td><span class="badge-estado ${et.clase}">${et.texto}</span></td>
                      <td style="font-size:12px">${n.evidencia}</td>
                    </tr>`;
                  })
                  .join("")}
              </tbody>
            </table>
            </div>
          </details>`
            )
            .join("")
        : '<p class="pendiente">Sin novedades — todos los grados auditados están activos.</p>'
    }

    <div class="no-imprimir" style="text-align:right; margin-top:14px">
      <button type="button" class="boton secundario" id="btn-exportar-continuidad">⬇ Exportar a Excel</button>
    </div>
  `;

  document.getElementById("select-sede-continuidad").addEventListener("change", (e) => {
    continuidadSedeSeleccionada = Number(e.target.value);
    cargarYPintarContinuidad(contenedor, sedes);
  });
  document.getElementById("btn-exportar-continuidad").addEventListener("click", async () => {
    await asegurarSesionFresca(); // Fase 4A': ver la nota en btn-exportar-reporte-notas
    window.location.href = `/api/boletines/continuidad/exportar?sede_id=${continuidadSedeSeleccionada}&anio_lectivo=${filtroBoletinesAnio}`;
  });
}

// --- Sección: SAPRED (hub + subvistas) ---------------------------------

function tarjetaHubHtml(id, icono, titulo, descripcion) {
  return `
    <button type="button" class="tarjeta-hub" data-sapred-ir="${id}">
      <span class="tarjeta-hub-icono" aria-hidden="true">${icono}</span>
      <span class="tarjeta-hub-titulo">${titulo}</span>
      <span class="tarjeta-hub-desc">${descripcion}</span>
      <span class="tarjeta-hub-flecha" aria-hidden="true">→</span>
    </button>`;
}

async function renderSeccionSapred() {
  const contenedor = document.getElementById("contenido-boletines");
  if (sapredSubvista === "hub") return renderSapredHub(contenedor);

  contenedor.innerHTML = `<button type="button" class="volver" id="btn-volver-sapred">← Volver a SAPRED</button><div id="sapred-subvista" class="estado-carga">Cargando...</div>`;
  document.getElementById("btn-volver-sapred").addEventListener("click", () => {
    sapredSubvista = "hub";
    render();
  });
  const subcontenedor = document.getElementById("sapred-subvista");

  const todasLasSedes = await api("/api/sedes");
  const sedes = todasLasSedes.filter((s) => s.pertenece_ietaba);

  if (sapredSubvista === "importar") return renderSapredImportar(subcontenedor, sedes);
  if (sapredSubvista === "sincoincidencia") return renderSapredSinCoincidencia(subcontenedor, sedes);
  if (sapredSubvista === "generarpdf") return renderGenerarBoletinesPdf(subcontenedor, sedes);
}

function irANotasGrilla() {
  seccionNotas = "grilla";
  vistaActual = "notas";
  tabs.forEach((t) => t.classList.remove("activo"));
  document.querySelector('[data-vista="notas"]')?.classList.add("activo");
  cerrarSidebarMovil();
  render();
}

function irAConciliacionSapred() {
  seccionReportes = "conciliacion";
  vistaActual = "reportes";
  tabs.forEach((t) => t.classList.remove("activo"));
  document.querySelector('[data-vista="reportes"]')?.classList.add("activo");
  cerrarSidebarMovil();
  render();
}

function renderSapredHub(contenedor) {
  contenedor.innerHTML = `
    <p class="subtitulo-pagina" style="margin:-8px 0 16px">Integración y comparación con el sistema académico departamental.</p>
    <div id="resultado-importar-sapred">${resultadoImportacionSapred ? resultadoImportarSapredHtml(resultadoImportacionSapred) : ""}</div>
    <div class="hub-sapred">
      ${tarjetaHubHtml("importar", "📥", "Importar notas", "Incorporar información desde SAPRED (automático o subiendo un PDF)")}
      ${tarjetaHubHtml("importar", "🔍", "Auditoría", "Comparar la información local con SAPRED, sede por sede")}
      ${tarjetaHubHtml("generarpdf", "🖨", "Generar boletines por sede", "Un PDF por sede con el boletín de todos sus estudiantes, ordenado por grado, para el docente")}
      ${tarjetaHubHtml("sincoincidencia", "⚠", "Sin coincidencia", "Registros que SAPRED reporta y que requieren revisión")}
    </div>
    <p class="pendiente" style="margin-top:14px">
      ¿Buscas la nota real de cada estudiante por área? Eso se ve en
      <button type="button" class="boton secundario" id="btn-ir-notas-grilla" style="margin-left:6px">📊 Notas → Grilla</button>
    </p>
  `;
  document.getElementById("btn-cerrar-resultado-sapred")?.addEventListener("click", () => {
    resultadoImportacionSapred = null;
    render();
  });
  document.getElementById("btn-ver-conciliacion-sapred")?.addEventListener("click", irAConciliacionSapred);
  document.querySelectorAll("[data-sapred-ir]").forEach((btn) => {
    btn.addEventListener("click", () => {
      sapredSubvista = btn.dataset.sapredIr;
      render();
    });
  });
  document.getElementById("btn-ir-notas-grilla").addEventListener("click", irANotasGrilla);
}

// --- SAPRED > Importar / Auditoría ------------------------------------

function renderSapredImportar(contenedor, sedes) {
  contenedor.innerHTML = `
    <div class="panel-boletines">
      <h3>Importación automática (Iniciar auditoría)</h3>
      <p class="pendiente">
        Se abre una ventana de Chrome con el colegio (AWA) ya seleccionado. Puedes escribir el usuario y la
        contraseña de SAPRED en los campos de abajo (se usan <strong>solo para esta corrida</strong>: no se
        guardan en la base ni en los registros) o dejarlos vacíos e iniciar sesión a mano en la ventana.
        Luego entra sola grado por grado y sede por sede: guarda lo que ya existe y deja como pendiente lo
        que falta. "Boletín informativo" trae notas, conceptos y observaciones a la vez.
      </p>
      <div id="panel-auditoria-sapred"></div>
    </div>
    <div class="panel-boletines">
      <h3>Importación manual — Consolidado por periodo (notas)</h3>
      <p class="pendiente">Sube uno o varios PDF de Reportes &gt; Resultados Académicos &gt; Consolidado de Asignaturas por periodo, de SAPRED.</p>
      <label class="boton secundario" style="cursor:pointer; display:inline-block">
        Elegir PDF...
        <input type="file" id="input-importar-sapred" accept="application/pdf" multiple style="display:none" />
      </label>
      <div id="resultado-importar-sapred-inline"></div>
      <details class="seccion-colapsable" style="margin-top:14px">
        <summary>Historial de importaciones</summary>
        <div id="historial-importaciones-sapred" class="estado-carga">Cargando...</div>
      </details>
    </div>
    <div class="panel-boletines">
      <h3>Importación manual — Boletín informativo (notas + conceptos + observaciones)</h3>
      <p class="pendiente">
        Sube uno o varios PDF de Reportes &gt; Reportes y Resultados Académicos &gt; Boletín informativo, de SAPRED
        (sede, grado, curso, todas las secciones, período). El boletín trae <strong>las tres cosas a la vez</strong>:
        la nota de cada área, el concepto de cada área y la observación del director de grupo. Se guarda lo que
        está, se marca lo que falta, y <strong>lo que ya aparece cargado se cierra solo</strong> (aunque un
        pendiente viejo siguiera abierto).
      </p>
      <label class="boton secundario" style="cursor:pointer; display:inline-block">
        Elegir PDF...
        <input type="file" id="input-importar-boletin" accept="application/pdf" multiple style="display:none" />
      </label>
      <div id="resultado-importar-boletin-inline">${resultadoImportacionBoletin ? resultadoImportarBoletinHtml(resultadoImportacionBoletin) : ""}</div>
      <details class="seccion-colapsable" style="margin-top:14px">
        <summary>Historial de importaciones del boletín</summary>
        <div id="historial-importaciones-boletin" class="estado-carga">Cargando...</div>
      </details>
    </div>
  `;

  document.getElementById("input-importar-sapred").addEventListener("change", async (e) => {
    const archivos = Array.from(e.target.files || []);
    if (!archivos.length) return;
    const resultadoCont = document.getElementById("resultado-importar-sapred-inline");

    const combinado = { bloques: [], total_pendientes_creados: 0, total_pendientes_resueltos_auto: 0, total_estudiantes_no_encontrados: 0, archivos_fallidos: [] };
    const noEncontradosGlobal = new Set();

    for (let i = 0; i < archivos.length; i++) {
      const archivo = archivos[i];
      resultadoCont.innerHTML = `<p class="pendiente">Leyendo PDF ${i + 1} de ${archivos.length} (${archivo.name})...</p>`;
      const form = new FormData();
      form.append("archivo", archivo);
      try {
        // Fase 4A': va por fetch crudo (manda un archivo, no JSON), así que
        // no pasa por api(). Se renueva aquí, dentro del bucle: importar
        // muchos PDF puede tomar más de los 15 minutos que dura el token.
        await asegurarSesionFresca();
        const res = await fetch("/api/boletines/importar-sapred", { method: "POST", body: form });
        if (!res.ok) {
          const cuerpo = await res.json().catch(() => ({}));
          throw new Error(cuerpo.detail || "No se pudo importar el PDF");
        }
        const resultado = await res.json();
        combinado.bloques.push(...resultado.bloques);
        combinado.total_pendientes_creados += resultado.total_pendientes_creados;
        combinado.total_pendientes_resueltos_auto += resultado.total_pendientes_resueltos_auto || 0;
        resultado.bloques.forEach((b) => b.estudiantes_no_encontrados.forEach((n) => noEncontradosGlobal.add(n)));
      } catch (err) {
        combinado.archivos_fallidos.push(`${archivo.name}: ${err.message}`);
      }
    }
    combinado.total_estudiantes_no_encontrados = noEncontradosGlobal.size;
    resultadoImportacionSapred = combinado;
    resultadoCont.innerHTML = resultadoImportarSapredHtml(combinado);
    document.getElementById("btn-cerrar-resultado-sapred").addEventListener("click", () => {
      resultadoImportacionSapred = null;
      resultadoCont.innerHTML = "";
    });
    document.getElementById("btn-ver-conciliacion-sapred")?.addEventListener("click", irAConciliacionSapred);
    cargarYPintarHistorialImportaciones(document.getElementById("historial-importaciones-sapred"));
  });

  document.getElementById("input-importar-boletin").addEventListener("change", async (e) => {
    const archivos = Array.from(e.target.files || []);
    if (!archivos.length) return;
    const resultadoCont = document.getElementById("resultado-importar-boletin-inline");

    const combinado = {
      bloques: [], total_conceptos_pendientes: 0, total_notas_pendientes: 0, total_observaciones_pendientes: 0,
      total_pendientes_resueltos_auto: 0, total_estudiantes_no_encontrados: 0, archivos_fallidos: [],
    };
    const noEncontradosGlobal = new Set();

    for (let i = 0; i < archivos.length; i++) {
      const archivo = archivos[i];
      resultadoCont.innerHTML = `<p class="pendiente">Leyendo PDF ${i + 1} de ${archivos.length} (${archivo.name})...</p>`;
      const form = new FormData();
      form.append("archivo", archivo);
      try {
        await asegurarSesionFresca(); // Fase 4A': ver la nota en importar-sapred
        const res = await fetch("/api/boletines/importar-boletin", { method: "POST", body: form });
        if (!res.ok) {
          const cuerpo = await res.json().catch(() => ({}));
          throw new Error(cuerpo.detail || "No se pudo importar el PDF");
        }
        const resultado = await res.json();
        combinado.bloques.push(...resultado.bloques);
        combinado.total_conceptos_pendientes += resultado.total_conceptos_pendientes;
        combinado.total_notas_pendientes += resultado.total_notas_pendientes || 0;
        combinado.total_observaciones_pendientes += resultado.total_observaciones_pendientes;
        combinado.total_pendientes_resueltos_auto += resultado.total_pendientes_resueltos_auto || 0;
        resultado.bloques.forEach((b) => b.estudiantes_no_encontrados.forEach((n) => noEncontradosGlobal.add(n)));
      } catch (err) {
        combinado.archivos_fallidos.push(`${archivo.name}: ${err.message}`);
      }
    }
    combinado.total_estudiantes_no_encontrados = noEncontradosGlobal.size;
    resultadoImportacionBoletin = combinado;
    resultadoCont.innerHTML = resultadoImportarBoletinHtml(combinado);
    document.getElementById("btn-cerrar-resultado-boletin").addEventListener("click", () => {
      resultadoImportacionBoletin = null;
      resultadoCont.innerHTML = "";
    });
    cargarYPintarHistorialImportacionesBoletin(document.getElementById("historial-importaciones-boletin"));
  });

  abrirPanelAuditoriaSapred(document.getElementById("panel-auditoria-sapred"), sedes);
  cargarYPintarHistorialImportaciones(document.getElementById("historial-importaciones-sapred"));
  cargarYPintarHistorialImportacionesBoletin(document.getElementById("historial-importaciones-boletin"));
}

// --- SAPRED > Generar boletines por sede (PDF) --------------------------

function renderGenerarBoletinesPdf(contenedor, sedes) {
  contenedor.innerHTML = `
    <div class="panel-boletines">
      <h3>Generar boletines por sede</h3>
      <p class="pendiente">
        Se abre una ventana de Chrome con el colegio (AWA) ya seleccionado. Entra sola sede por sede y grado
        por grado, genera el boletín de calificaciones de cada grupo y <strong>une todo en un solo PDF por
        sede</strong>, ordenado por grado (Primero, Segundo, Tercero…), listo para entregar al docente.
        En "Opciones de impresión" activa siempre <strong>Mostrar Sede</strong> e <strong>Incluir Puesto</strong>.
        Los archivos quedan en <code>backend/boletines_sedes/</code> y también se pueden descargar aquí.
      </p>
      <div id="panel-generar-boletines"></div>
    </div>
  `;
  abrirPanelGenerarBoletines(document.getElementById("panel-generar-boletines"), sedes);
}

async function abrirPanelGenerarBoletines(contenedor, sedes) {
  contenedor.innerHTML = '<p class="pendiente">Cargando...</p>';
  const historial = await api("/api/boletines/generar-pdf?limite=10").catch(() => []);
  const enCurso = historial.find((a) =>
    ["pendiente", "esperando_login", "en_proceso"].includes(a.estado)
  );

  if (generarBoletinesSedesSeleccionadas === null) {
    generarBoletinesSedesSeleccionadas = new Set(sedes.map((s) => s.id));
  }

  if (enCurso) {
    pintarProgresoGeneracion(contenedor, enCurso, sedes);
    iniciarPollingGeneracion(enCurso.id, contenedor, sedes);
    return;
  }
  pintarFiltrosGeneracion(contenedor, sedes, historial);
}

function pintarFiltrosGeneracion(contenedor, sedes, historial) {
  const totalSedes = sedes.length;
  const seleccionadas = generarBoletinesSedesSeleccionadas.size;

  contenedor.innerHTML = `
    <form id="form-generar-boletines" class="form-grid">
      <label>Usuario SAPRED (opcional)
        <input type="text" name="usuario" autocomplete="off" placeholder="Vacío = login a mano" />
      </label>
      <label>Contraseña SAPRED (opcional)
        <input type="password" name="clave" autocomplete="off" placeholder="Solo para esta corrida — no se guarda" />
      </label>
      <label>Período
        <select name="periodo">
          ${[1, 2, 3, 4].map((p) => `<option value="${p}" ${filtroBoletinesPeriodo === p ? "selected" : ""}>Período ${p}</option>`).join("")}
        </select>
      </label>
      <label>Grado
        <select name="grado">
          <option value="">Todos los grados de la sede</option>
          ${NOMBRES_GRADOS.map(([n, nombre]) => `<option value="${n}">${nombre}</option>`).join("")}
        </select>
      </label>
      <div class="ancho-completo">
        <details class="seccion-colapsable" id="detalle-sedes-generar">
          <summary>Sedes: ${seleccionadas === totalSedes ? "todas" : `${seleccionadas} de ${totalSedes}`} seleccionadas</summary>
          <label class="check-linea" style="font-weight:600; margin-top:6px">
            <input type="checkbox" id="check-todas-sedes-generar" ${seleccionadas === totalSedes ? "checked" : ""} />
            Seleccionar todas
          </label>
          <div class="lista-estudiantes-modal" style="margin-top:6px">
            ${sedes
              .map(
                (s) => `
              <label class="check-linea fila-estudiante-modal">
                <input type="checkbox" class="check-sede-generar" value="${s.id}" ${generarBoletinesSedesSeleccionadas.has(s.id) ? "checked" : ""} />
                ${s.nombre}
              </label>`
              )
              .join("")}
          </div>
        </details>
      </div>
      <div class="ancho-completo">
        <button type="submit" class="boton" id="btn-generar-boletines">🖨 Generar boletines</button>
      </div>
    </form>

    <details class="seccion-colapsable" style="margin-top:16px">
      <summary>Corridas anteriores</summary>
      <div id="historial-generar-boletines">${historialGeneracionHtml(historial)}</div>
    </details>
  `;

  document.getElementById("check-todas-sedes-generar").addEventListener("change", (e) => {
    if (e.target.checked) sedes.forEach((s) => generarBoletinesSedesSeleccionadas.add(s.id));
    else generarBoletinesSedesSeleccionadas.clear();
    pintarFiltrosGeneracion(contenedor, sedes, historial);
  });

  document.querySelectorAll(".check-sede-generar").forEach((chk) => {
    chk.addEventListener("change", () => {
      const id = Number(chk.value);
      if (chk.checked) generarBoletinesSedesSeleccionadas.add(id);
      else generarBoletinesSedesSeleccionadas.delete(id);
      const resumen = document.querySelector("#detalle-sedes-generar summary");
      const n = generarBoletinesSedesSeleccionadas.size;
      resumen.textContent = `Sedes: ${n === totalSedes ? "todas" : `${n} de ${totalSedes}`} seleccionadas`;
      document.getElementById("check-todas-sedes-generar").checked = n === totalSedes;
    });
  });

  document.getElementById("form-generar-boletines").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!generarBoletinesSedesSeleccionadas.size) {
      alert("Selecciona al menos una sede.");
      return;
    }
    const datos = Object.fromEntries(new FormData(ev.target).entries());
    const todas = generarBoletinesSedesSeleccionadas.size === totalSedes;
    const boton = document.getElementById("btn-generar-boletines");
    boton.disabled = true;
    boton.textContent = "Iniciando...";
    try {
      const corrida = await api("/api/boletines/generar-pdf", {
        method: "POST",
        body: JSON.stringify({
          periodo: Number(datos.periodo),
          grado: datos.grado === "" ? null : Number(datos.grado),
          sede_ids: todas ? null : Array.from(generarBoletinesSedesSeleccionadas),
          usuario: (datos.usuario || "").trim() || null,
          clave: datos.clave || null,
        }),
      });
      pintarProgresoGeneracion(contenedor, corrida, sedes);
      iniciarPollingGeneracion(corrida.id, contenedor, sedes);
    } catch (err) {
      alert(err.message || "No se pudo iniciar la generación.");
      boton.disabled = false;
      boton.textContent = "🖨 Generar boletines";
    }
  });
}

function iniciarPollingGeneracion(id, contenedor, sedes) {
  if (generarBoletinesIntervalo) clearInterval(generarBoletinesIntervalo);
  generarBoletinesIntervalo = setInterval(async () => {
    if (!document.body.contains(contenedor)) {
      clearInterval(generarBoletinesIntervalo);
      generarBoletinesIntervalo = null;
      return;
    }
    try {
      const corrida = await api(`/api/boletines/auditoria-sapred/${id}`);
      pintarProgresoGeneracion(contenedor, corrida, sedes);
      if (["completada", "error"].includes(corrida.estado)) {
        clearInterval(generarBoletinesIntervalo);
        generarBoletinesIntervalo = null;
      }
    } catch (err) {
      /* fallo puntual de red: se reintenta en el siguiente tick */
    }
  }, 2500);
}

function enlaceDescargaBoletinSede(corridaId, d) {
  if (!d.archivo) return "";
  const url = `/api/boletines/generar-pdf/${corridaId}/archivo?nombre=${encodeURIComponent(d.archivo)}`;
  const meta = [
    d.n_estudiantes != null ? `${d.n_estudiantes} estud.` : null,
    d.n_paginas != null ? `${d.n_paginas} pág.` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return `<a class="boton secundario boton-chico" href="${url}" target="_blank" rel="noopener">⬇ PDF</a>${meta ? ` <span class="pendiente" style="font-size:12px">${meta}</span>` : ""}`;
}

function pintarProgresoGeneracion(contenedor, a, sedes) {
  const est = ESTADOS_AUDITORIA[a.estado] || { icono: "", texto: a.estado };
  const porcentaje = a.sedes_totales ? Math.round((a.sedes_completadas / a.sedes_totales) * 100) : 0;
  const terminada = ["completada", "error"].includes(a.estado);
  const hayFallos = a.detalle_sedes.some((d) => d.estado !== "completada");

  contenedor.innerHTML = `
    <p><span class="badge-estado ${a.estado === "error" ? "alerta" : a.estado === "completada" ? "ok" : "proceso"}">${est.icono} ${est.texto}</span></p>

    ${
      a.estado === "esperando_login"
        ? `<div class="alerta-caja">Se abrió una ventana de Chrome — entra ahí con tu usuario y contraseña de SAPRED. En cuanto inicies sesión, esto sigue solo.</div>`
        : ""
    }

    <div class="barra-progreso-wrap">
      <div class="barra-progreso"><div class="barra-progreso-relleno" style="width:${porcentaje}%"></div></div>
      <span class="barra-progreso-texto">${a.sedes_completadas} de ${a.sedes_totales} sede(s) — ${porcentaje}%</span>
    </div>

    ${
      a.sede_actual && !terminada
        ? `<p class="pendiente">Ahora mismo: ${a.sede_actual}${a.grado_actual ? ` — ${a.grado_actual}` : ""}</p>`
        : ""
    }

    ${a.carpeta_salida ? `<p class="pendiente" style="font-size:12px">Carpeta: <code>${a.carpeta_salida}</code></p>` : ""}

    ${
      a.detalle_sedes.length
        ? `<div class="lista-pendientes-modal" style="margin-top:12px; max-height:260px; overflow-y:auto">
             ${a.detalle_sedes
               .map((d) => {
                 const es = ESTADOS_SEDE_AUDITORIA[d.estado] || { icono: "•", clase: "" };
                 return `<div class="fila-pendiente-modal">
                   <div>
                     <span class="badge-estado ${es.clase}">${es.icono} ${d.estado}</span>
                     <strong style="margin-left:6px">${d.sede}</strong>
                     ${d.detalle ? `<div class="pendiente" style="font-size:12px">${d.detalle}</div>` : ""}
                   </div>
                   <div>${enlaceDescargaBoletinSede(a.id, d)}</div>
                 </div>`;
               })
               .join("")}
           </div>`
        : ""
    }

    ${a.estado === "error" && a.error ? `<div class="alerta-caja" style="margin-top:10px">${a.error}</div>` : ""}

    ${
      !terminada
        ? `<p class="pendiente" style="margin:10px 0 0">Puedes cambiar de sección — esto sigue en segundo plano.</p>`
        : ""
    }
    <div style="text-align:right; margin-top:14px; display:flex; gap:8px; justify-content:flex-end; flex-wrap:wrap">
      ${hayFallos ? `<button type="button" class="boton secundario" id="btn-reintentar-generacion">🔁 Reintentar los grados que faltan</button>` : ""}
      <button type="button" class="boton secundario" id="btn-nueva-generacion">↻ Empezar de cero</button>
      ${!terminada ? `<button type="button" class="boton secundario boton-chico" id="btn-cancelar-generacion">✕ Cancelar</button>` : ""}
    </div>
  `;

  const detenerPolling = () => {
    if (generarBoletinesIntervalo) {
      clearInterval(generarBoletinesIntervalo);
      generarBoletinesIntervalo = null;
    }
  };
  // Si sigue "en curso" pero la vamos a reiniciar/reintentar, primero se
  // cancela (el backend no deja dos corridas a la vez).
  const cancelarSiHaceFalta = async () => {
    if (["completada", "error"].includes(a.estado)) return;
    try {
      await api(`/api/boletines/auditoria-sapred/${a.id}/cancelar`, { method: "POST" });
    } catch (err) {
      /* si ya terminó, da igual */
    }
  };

  document.getElementById("btn-nueva-generacion")?.addEventListener("click", async (e) => {
    if (!terminada && !confirm("¿Cancelar esta corrida y volver al formulario? Si dejaste Chrome abierto, ciérralo.")) return;
    detenerPolling();
    await cancelarSiHaceFalta();
    abrirPanelGenerarBoletines(contenedor, sedes);
  });
  document.getElementById("btn-cancelar-generacion")?.addEventListener("click", async (e) => {
    if (!confirm("¿Cancelar esta corrida? Si dejaste la ventana de Chrome abierta, ciérrala tú.")) return;
    e.target.disabled = true;
    e.target.textContent = "Cancelando...";
    detenerPolling();
    await cancelarSiHaceFalta();
    abrirPanelGenerarBoletines(contenedor, sedes);
  });
  document.getElementById("btn-reintentar-generacion")?.addEventListener("click", async (e) => {
    e.target.disabled = true;
    e.target.textContent = "Reintentando...";
    detenerPolling();
    await cancelarSiHaceFalta();
    try {
      const nueva = await api(`/api/boletines/auditoria-sapred/${a.id}/reintentar`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      pintarProgresoGeneracion(contenedor, nueva, sedes);
      iniciarPollingGeneracion(nueva.id, contenedor, sedes);
    } catch (err) {
      alert(err.message || "No se pudo reintentar. Prueba 'Empezar de cero'.");
      abrirPanelGenerarBoletines(contenedor, sedes);
    }
  });
}

function historialGeneracionHtml(historial) {
  if (!historial || !historial.length) return '<p class="pendiente">Todavía no hay corridas.</p>';
  return historial
    .map((a) => {
      const fecha = (a.creado_en || "").slice(0, 16).replace("T", " ");
      const est = ESTADOS_AUDITORIA[a.estado] || { icono: "", texto: a.estado };
      const archivos = a.detalle_sedes
        .filter((d) => d.archivo)
        .map(
          (d) =>
            `<li>${d.sede} — ${enlaceDescargaBoletinSede(a.id, d)}</li>`
        )
        .join("");
      return `<div class="fila-pendiente-modal" style="display:block">
        <div><strong>${fecha}</strong> · P${a.periodo} · <span class="badge-estado ${a.estado === "completada" ? "ok" : a.estado === "error" ? "alerta" : "proceso"}">${est.icono} ${est.texto}</span> · ${a.sedes_completadas}/${a.sedes_totales} sede(s)</div>
        ${archivos ? `<ul style="margin:6px 0 0; padding-left:18px">${archivos}</ul>` : ""}
      </div>`;
    })
    .join("");
}

function filaHistorialImportacionBoletinHtml(h) {
  const fecha = h.importado_en.slice(0, 16).replace("T", " ");
  if (h.error) {
    return `<tr><td>${fecha}</td><td>${h.nombre_archivo}</td><td colspan="2"><span class="badge-estado alerta">⚠ No se pudo leer: ${h.error}</span></td></tr>`;
  }
  const cursos = h.bloques.filter((b) => b.reconocido).length;
  const noReconocidos = h.bloques.length - cursos;
  return `<tr>
    <td>${fecha}</td>
    <td>${h.nombre_archivo}</td>
    <td>${cursos} curso(s)${noReconocidos ? ` · ${noReconocidos} sin reconocer` : ""}</td>
    <td>${h.total_conceptos_pendientes} concepto(s) · ${h.total_observaciones_pendientes} observación(es) faltante(s)${
      h.total_estudiantes_no_encontrados ? ` · ${h.total_estudiantes_no_encontrados} sin coincidencia` : ""
    }</td>
  </tr>`;
}

async function cargarYPintarHistorialImportacionesBoletin(contenedor) {
  if (!contenedor) return;
  contenedor.innerHTML = '<p class="pendiente">Cargando historial...</p>';
  let historial;
  try {
    historial = await api("/api/boletines/importaciones-boletin-pdf?limite=20");
  } catch (err) {
    contenedor.innerHTML = `<div class="alerta-caja">${err.message}</div>`;
    return;
  }
  contenedor.innerHTML = historial.length
    ? `<div class="tabla-scroll"><table>
         <thead><tr><th>Fecha</th><th>Archivo</th><th>Cursos</th><th>Resultado</th></tr></thead>
         <tbody>${historial.map(filaHistorialImportacionBoletinHtml).join("")}</tbody>
       </table></div>`
    : '<p class="pendiente">Todavía no se ha importado ningún boletín.</p>';
}

// --- SAPRED > Importar > Historial de PDF importados ------------------
// Antes el resultado de importar un PDF solo se veía en pantalla y se
// perdía apenas se cerraba el aviso o se recargaba la página. Esto lo deja
// guardado (ver ImportacionSapredPdf en el backend) para poder revisarlo
// después — la Conciliación en Reportes ya no depende de esto (se calcula
// en vivo), pero saber "qué PDF se subió y cuándo" sí hacía falta aparte.

function filaHistorialImportacionHtml(h) {
  const fecha = h.importado_en.slice(0, 16).replace("T", " ");
  if (h.error) {
    return `<tr>
      <td>${fecha}</td>
      <td>${h.nombre_archivo}</td>
      <td colspan="2"><span class="badge-estado alerta">⚠ No se pudo leer: ${h.error}</span></td>
    </tr>`;
  }
  const cursos = h.bloques.filter((b) => b.reconocido).length;
  const noReconocidos = h.bloques.length - cursos;
  return `<tr>
    <td>${fecha}</td>
    <td>${h.nombre_archivo}</td>
    <td>${cursos} curso(s) importado(s)${noReconocidos ? ` · ${noReconocidos} sin reconocer` : ""}</td>
    <td>${h.total_pendientes_creados} pendiente(s) nuevo(s)${
      h.total_estudiantes_no_encontrados ? ` · ${h.total_estudiantes_no_encontrados} estudiante(s) sin coincidencia` : ""
    }</td>
  </tr>`;
}

async function cargarYPintarHistorialImportaciones(contenedor) {
  if (!contenedor) return;
  contenedor.innerHTML = '<p class="pendiente">Cargando historial...</p>';
  let historial;
  try {
    historial = await api("/api/boletines/importaciones-sapred-pdf?limite=20");
  } catch (err) {
    contenedor.innerHTML = `<div class="alerta-caja">${err.message}</div>`;
    return;
  }
  contenedor.innerHTML = historial.length
    ? `<div class="tabla-scroll"><table>
         <thead><tr><th>Fecha</th><th>Archivo</th><th>Cursos</th><th>Resultado</th></tr></thead>
         <tbody>${historial.map(filaHistorialImportacionHtml).join("")}</tbody>
       </table></div>`
    : '<p class="pendiente">Todavía no se ha importado ningún PDF manualmente.</p>';
}

// --- Auditoría SAPRED > Historial (modal, se puede abrir cuando sea) -------
// Antes solo se veía un resumen fijo de cada corrida pasada (fecha, cuántos
// pendientes) y no había forma de volver a ver el detalle por sede una vez
// cerrada la pantalla. Esto guarda nada nuevo (el backend ya guardaba todo
// en AuditoriaSapred.detalle_sedes) — solo lo hace visible de nuevo.

async function abrirModalHistorialAuditorias(sedes) {
  const contenedor = document.getElementById("modal-revision");
  contenedor.innerHTML = `<div class="modal-fondo"><div class="modal-caja"><p>Cargando historial...</p></div></div>`;
  document.getElementById("contenido-boletines")?.classList.add("no-imprimir");

  let historial;
  try {
    historial = await api("/api/boletines/auditoria-sapred?limite=50");
  } catch (err) {
    contenedor.innerHTML = `
      <div class="modal-fondo"><div class="modal-caja">
        <div class="alerta-caja">${err.message}</div>
        <div style="text-align:right; margin-top:12px">
          <button type="button" class="boton secundario" id="btn-cerrar-historial-auditorias">Cerrar</button>
        </div>
      </div></div>`;
    document.getElementById("btn-cerrar-historial-auditorias").addEventListener("click", cerrarModalHistorialAuditorias);
    return;
  }
  pintarListaHistorialAuditorias(contenedor, historial, sedes);
}

function cerrarModalHistorialAuditorias() {
  document.getElementById("contenido-boletines")?.classList.remove("no-imprimir");
  document.getElementById("modal-revision").innerHTML = "";
  mostrarInformeAuditoriaModal = false;
}

function filaHistorialAuditoriaHtml(a, idx) {
  const est = ESTADOS_AUDITORIA[a.estado] || { icono: "", texto: a.estado };
  const nombreGrado = a.grado !== null ? (NOMBRES_GRADOS.find(([n]) => n === a.grado) || [null, "?"])[1] : "Todos";
  return `<tr>
    <td>${a.creado_en.slice(0, 16).replace("T", " ")}</td>
    <td>${a.periodo}</td>
    <td>${nombreGrado}</td>
    <td>${a.sedes_completadas}/${a.sedes_totales}</td>
    <td>${est.icono} ${est.texto}</td>
    <td>${a.pendientes_encontrados}</td>
    <td><button type="button" class="boton secundario boton-chico" data-ver-detalle-auditoria="${idx}">Ver detalle</button></td>
  </tr>`;
}

function pintarListaHistorialAuditorias(contenedor, historial, sedes) {
  contenedor.innerHTML = `
    <div class="modal-fondo">
      <div class="modal-caja modal-caja-ancha">
        <div style="display:flex; justify-content:space-between; align-items:start; gap:10px">
          <div>
            <h3 style="margin:0 0 4px">Historial de auditorías SAPRED</h3>
            <p class="pendiente" style="margin:0">Cada vez que corres "Iniciar auditoría" queda un registro acá — puedes volver a verlo cuando quieras, aunque hayan pasado días.</p>
          </div>
          <button type="button" class="boton secundario boton-chico" id="btn-cerrar-historial-auditorias">✕</button>
        </div>

        ${
          historial.length
            ? `<div class="tabla-scroll" style="margin-top:12px">
                 <table>
                   <thead><tr>
                     <th>Fecha</th><th>Período</th><th>Grado</th><th>Sedes</th><th>Estado</th>
                     <th>Pendientes${iconoAyuda("Notas que en ese momento todavía estaban vacías en SAPRED: le faltaba al profesor ponerlas.")}</th>
                     <th></th>
                   </tr></thead>
                   <tbody>${historial.map((a, i) => filaHistorialAuditoriaHtml(a, i)).join("")}</tbody>
                 </table>
               </div>`
            : `<p class="pendiente" style="margin-top:12px">Todavía no se ha corrido ninguna auditoría automática.</p>`
        }
      </div>
    </div>
  `;

  document.getElementById("btn-cerrar-historial-auditorias").addEventListener("click", cerrarModalHistorialAuditorias);
  document.querySelectorAll("[data-ver-detalle-auditoria]").forEach((btn) => {
    btn.addEventListener("click", () => {
      mostrarInformeAuditoriaModal = false;
      pintarDetalleAuditoriaModal(contenedor, historial[Number(btn.dataset.verDetalleAuditoria)], historial, sedes);
    });
  });
}

function pintarDetalleAuditoriaModal(contenedor, a, historial, sedes) {
  const est = ESTADOS_AUDITORIA[a.estado] || { icono: "", texto: a.estado };
  const nombreGrado = a.grado !== null ? (NOMBRES_GRADOS.find(([n]) => n === a.grado) || [null, "Todos"])[1] : "Todos los grados";
  const fecha = a.creado_en.slice(0, 16).replace("T", " ");
  const fallidas = a.detalle_sedes.filter((d) => d.estado !== "completada");
  const puedeReintentar = ["completada", "error"].includes(a.estado) && fallidas.length > 0;

  contenedor.innerHTML = `
    <div class="modal-fondo">
      <div class="modal-caja modal-caja-ancha">
        <div class="no-imprimir" style="display:flex; justify-content:space-between; align-items:start; gap:10px">
          <div>
            <h3 style="margin:0 0 4px">Auditoría del ${fecha}</h3>
            <p class="pendiente" style="margin:0">
              Período ${a.periodo} · ${nombreGrado} ·
              <span class="badge-estado ${a.estado === "error" ? "alerta" : a.estado === "completada" ? "ok" : "proceso"}">${est.icono} ${est.texto}</span>
            </p>
          </div>
          <button type="button" class="boton secundario boton-chico" id="btn-cerrar-historial-auditorias">✕</button>
        </div>

        <div class="no-imprimir resumen-reportes" style="margin-top:12px">
          <div class="metric-card">
            <span>Estudiantes revisados${iconoAyuda("Cuántos estudiantes miró la app en SAPRED durante esta auditoría.")}</span>
            <strong>${a.estudiantes_revisados}</strong>
          </div>
          <div class="metric-card ${a.pendientes_encontrados ? "alerta" : "ok"}">
            <span>Pendientes encontrados${iconoAyuda("Son notas que todavía estaban vacías en SAPRED en ese momento — le falta al profesor ponerlas. La app no inventa notas, solo avisa cuáles faltan.")}</span>
            <strong>${a.pendientes_encontrados}</strong>
          </div>
        </div>

        ${
          a.detalle_sedes.length
            ? `<div class="no-imprimir lista-pendientes-modal" style="margin-top:12px; max-height:260px; overflow-y:auto">
                 ${a.detalle_sedes
                   .map((d) => {
                     const es = ESTADOS_SEDE_AUDITORIA[d.estado] || { icono: "•", clase: "" };
                     return `<div class="fila-pendiente-modal">
                       <div>
                         <span class="badge-estado ${es.clase}">${es.icono} ${d.estado}</span>
                         <strong style="margin-left:6px">${d.sede}</strong>
                         ${d.detalle ? `<div class="pendiente" style="font-size:12px">${d.detalle}</div>` : ""}
                       </div>
                     </div>`;
                   })
                   .join("")}
               </div>`
            : `<p class="no-imprimir pendiente" style="margin-top:12px">Sin detalle por sede guardado para esta auditoría.</p>`
        }

        ${a.estado === "error" && a.error ? `<div class="no-imprimir alerta-caja" style="margin-top:10px">${a.error}</div>` : ""}

        <div id="zona-informe-auditoria">${mostrarInformeAuditoriaModal ? informeAuditoriaHtml(a) : ""}</div>

        ${
          puedeReintentar
            ? `<div class="no-imprimir callout-boletines" style="margin-top:12px; display:flex; align-items:center; gap:10px; flex-wrap:wrap">
                 <span>${fallidas.length} sede(s)/grado(s) quedaron con advertencia o error.</span>
                 <button type="button" class="boton" id="btn-reintentar-fallidas">🔁 Reintentar solo los que fallaron</button>
               </div>`
            : ""
        }

        <div class="no-imprimir" style="display:flex; justify-content:space-between; margin-top:14px">
          <button type="button" class="boton secundario" id="btn-volver-lista-auditorias">◀ Volver a la lista</button>
          <button type="button" class="boton secundario" id="btn-toggle-informe-auditoria">
            ${mostrarInformeAuditoriaModal ? "Ocultar informe" : "🖨 Ver informe para imprimir / PDF"}
          </button>
        </div>
      </div>
    </div>
  `;

  document.getElementById("btn-cerrar-historial-auditorias").addEventListener("click", cerrarModalHistorialAuditorias);
  document.getElementById("btn-volver-lista-auditorias").addEventListener("click", () => {
    mostrarInformeAuditoriaModal = false;
    pintarListaHistorialAuditorias(contenedor, historial, sedes);
  });
  if (puedeReintentar) {
    document.getElementById("btn-reintentar-fallidas").addEventListener("click", async () => {
      if (
        !confirm(
          `Se lanzará una auditoría NUEVA solo para ${fallidas.length} sede(s)/grado(s) que fallaron.\n` +
            `Período ${a.periodo}. No vuelve a tocar lo que ya quedó completo. ¿Continuar?`
        )
      )
        return;
      const usuario = (prompt("Usuario SAPRED (déjalo vacío para iniciar sesión a mano en la ventana):", "") || "").trim();
      const clave = usuario ? prompt("Contraseña SAPRED:", "") || "" : "";
      const btn = document.getElementById("btn-reintentar-fallidas");
      btn.disabled = true;
      btn.textContent = "Lanzando…";
      try {
        await api(`/api/boletines/auditoria-sapred/${a.id}/reintentar`, {
          method: "POST",
          body: JSON.stringify({ usuario: usuario || null, clave: clave || null }),
        });
        cerrarModalHistorialAuditorias();
        abrirPanelAuditoriaSapred(document.getElementById("panel-auditoria-sapred"), sedes);
      } catch (err) {
        alert(err.message || "No se pudo lanzar el reintento.");
        btn.disabled = false;
        btn.textContent = "🔁 Reintentar solo los que fallaron";
      }
    });
  }
  document.getElementById("btn-toggle-informe-auditoria").addEventListener("click", () => {
    mostrarInformeAuditoriaModal = !mostrarInformeAuditoriaModal;
    pintarDetalleAuditoriaModal(contenedor, a, historial, sedes);
  });
}

// Documento con membrete oficial (igual al de constancias/certificados) para
// que cualquier auditoría, al imprimirse o guardarse en PDF, sirva como
// constancia formal de lo que se revisó — no solo una captura de pantalla.
function informeAuditoriaHtml(a) {
  const hoy = new Date().toLocaleDateString("es-CO");
  const fecha = a.creado_en.slice(0, 16).replace("T", " ");
  const finalizada = a.terminado_en ? a.terminado_en.slice(0, 16).replace("T", " ") : "—";
  const est = ESTADOS_AUDITORIA[a.estado] || { texto: a.estado };
  const nombreGrado = a.grado !== null ? (NOMBRES_GRADOS.find(([n]) => n === a.grado) || [null, "Todos"])[1] : "Todos los grados";
  const textoEstadoSede = { completada: "Completada", advertencia: "Advertencia", error: "Error" };

  const filaSede = (d) => `
    <tr>
      <td>${d.sede}</td>
      <td>${textoEstadoSede[d.estado] || d.estado}</td>
      <td>${d.detalle || "—"}</td>
    </tr>`;

  return `
    <div class="hoja-imprimir">
      ${membreteHtml(`CONSTANCIA DE AUDITORÍA AUTOMÁTICA SAPRED — PERÍODO ${a.periodo} — ${a.anio_lectivo}`)}
      <div class="hoja-campos">
        <div class="campo"><span class="etiqueta">FECHA DE LA AUDITORÍA:</span><span class="valor">${fecha}</span></div>
        <div class="campo"><span class="etiqueta">FINALIZADA:</span><span class="valor">${finalizada}</span></div>
        <div class="campo"><span class="etiqueta">GRADO:</span><span class="valor">${nombreGrado}</span></div>
        <div class="campo"><span class="etiqueta">ESTADO:</span><span class="valor">${est.texto}</span></div>
        <div class="campo"><span class="etiqueta">SEDES REVISADAS:</span><span class="valor">${a.sedes_completadas} de ${a.sedes_totales}</span></div>
        <div class="campo"><span class="etiqueta">ESTUDIANTES REVISADOS:</span><span class="valor">${a.estudiantes_revisados}</span></div>
        <div class="campo"><span class="etiqueta">PENDIENTES ENCONTRADOS:</span><span class="valor">${a.pendientes_encontrados}</span></div>
      </div>

      <h3 class="informe-sede-titulo">Detalle por sede</h3>
      ${
        a.detalle_sedes.length
          ? `<table class="tabla-informe">
               <thead><tr><th>Sede</th><th>Resultado</th><th>Detalle</th></tr></thead>
               <tbody>${a.detalle_sedes.map(filaSede).join("")}</tbody>
             </table>`
          : '<p class="pendiente">Sin detalle por sede guardado para esta auditoría.</p>'
      }
      ${a.error ? `<p class="pendiente" style="margin-top:10px"><strong>Error:</strong> ${a.error}</p>` : ""}

      <p class="pendiente" style="margin-top:16px; font-size:12px">Documento generado el ${hoy} a partir del registro guardado de esta auditoría automática.</p>
    </div>
    <div class="toolbar no-imprimir">
      <button type="button" class="boton" onclick="window.print()">Imprimir / Guardar como PDF</button>
    </div>
  `;
}

async function abrirPanelAuditoriaSapred(contenedor, sedes) {
  contenedor.innerHTML = '<p class="pendiente">Cargando...</p>';

  // Si ya hay una auditoría en curso, la mostramos en vez de ofrecer otra
  // (el backend tampoco deja crear dos a la vez).
  const historial = await api("/api/boletines/auditoria-sapred?limite=10");
  const enCurso = historial.find((a) => ["pendiente", "esperando_login", "en_proceso"].includes(a.estado));

  if (auditoriaSapredSedesSeleccionadas === null) {
    auditoriaSapredSedesSeleccionadas = new Set(sedes.map((s) => s.id));
  }

  if (enCurso) {
    pintarProgresoAuditoria(contenedor, enCurso, sedes);
    iniciarPollingAuditoria(enCurso.id, contenedor, sedes);
    return;
  }

  pintarFiltrosAuditoria(contenedor, sedes, historial);
}

function pintarFiltrosAuditoria(contenedor, sedes, historial) {
  const totalSedes = sedes.length;
  const seleccionadas = auditoriaSapredSedesSeleccionadas.size;

  contenedor.innerHTML = `
    <form id="form-auditoria-sapred" class="form-grid">
      <label>Qué importar
        <select name="tipo">
          <option value="boletin">Notas + conceptos + observaciones (Boletín informativo)</option>
          <option value="notas">Solo notas (Consolidado por periodo)</option>
          <option value="ambos">Consolidado y Boletín (para confirmar las notas)</option>
        </select>
      </label>
      <label>Usuario SAPRED (opcional)
        <input type="text" name="usuario" autocomplete="off" placeholder="Se deja vacío = login a mano" />
      </label>
      <label>Contraseña SAPRED (opcional)
        <input type="password" name="clave" autocomplete="off" placeholder="Solo para esta corrida — no se guarda" />
      </label>
      <label>Período
        <select name="periodo">
          ${[1, 2, 3, 4].map((p) => `<option value="${p}" ${filtroBoletinesPeriodo === p ? "selected" : ""}>Período ${p}</option>`).join("")}
        </select>
      </label>
      <label>Grado
        <select name="grado">
          <option value="">Todos los grados</option>
          ${NOMBRES_GRADOS.map(([n, nombre]) => `<option value="${n}">${nombre}</option>`).join("")}
        </select>
      </label>
      <div class="ancho-completo">
        <details class="seccion-colapsable" id="detalle-sedes-auditoria">
          <summary>Sedes: ${seleccionadas === totalSedes ? "todas" : `${seleccionadas} de ${totalSedes}`} seleccionadas</summary>
          <label class="check-linea" style="font-weight:600; margin-top:6px">
            <input type="checkbox" id="check-todas-sedes-auditoria" ${seleccionadas === totalSedes ? "checked" : ""} />
            Seleccionar todas
          </label>
          <div class="lista-estudiantes-modal" style="margin-top:6px">
            ${sedes
              .map(
                (s) => `
              <label class="check-linea fila-estudiante-modal">
                <input type="checkbox" class="check-sede-auditoria" value="${s.id}" ${auditoriaSapredSedesSeleccionadas.has(s.id) ? "checked" : ""} />
                ${s.nombre}
              </label>`
              )
              .join("")}
          </div>
        </details>
      </div>
      <div class="ancho-completo">
        <button type="submit" class="boton" id="btn-iniciar-auditoria">Iniciar auditoría</button>
      </div>
    </form>

    <div style="margin-top:16px">
      <button type="button" class="boton secundario" id="btn-ver-historial-auditorias">📋 Ver historial de auditorías</button>
    </div>
  `;

  document.getElementById("btn-ver-historial-auditorias").addEventListener("click", () => abrirModalHistorialAuditorias(sedes));

  document.getElementById("check-todas-sedes-auditoria")?.addEventListener("change", (e) => {
    if (e.target.checked) sedes.forEach((s) => auditoriaSapredSedesSeleccionadas.add(s.id));
    else auditoriaSapredSedesSeleccionadas.clear();
    pintarFiltrosAuditoria(contenedor, sedes, historial);
  });

  document.querySelectorAll(".check-sede-auditoria").forEach((chk) => {
    chk.addEventListener("change", () => {
      const id = Number(chk.value);
      if (chk.checked) auditoriaSapredSedesSeleccionadas.add(id);
      else auditoriaSapredSedesSeleccionadas.delete(id);
      const resumen = document.querySelector("#detalle-sedes-auditoria summary");
      const n = auditoriaSapredSedesSeleccionadas.size;
      resumen.textContent = `Sedes: ${n === totalSedes ? "todas" : `${n} de ${totalSedes}`} seleccionadas`;
      document.getElementById("check-todas-sedes-auditoria").checked = n === totalSedes;
    });
  });

  document.getElementById("form-auditoria-sapred").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!auditoriaSapredSedesSeleccionadas.size) {
      alert("Selecciona al menos una sede.");
      return;
    }
    const datos = Object.fromEntries(new FormData(ev.target).entries());
    const todasSeleccionadas = auditoriaSapredSedesSeleccionadas.size === totalSedes;
    const boton = document.getElementById("btn-iniciar-auditoria");
    boton.disabled = true;
    boton.textContent = "Iniciando...";
    try {
      const auditoria = await api("/api/boletines/auditoria-sapred", {
        method: "POST",
        body: JSON.stringify({
          tipo: ["boletin", "ambos"].includes(datos.tipo) ? datos.tipo : "notas",
          periodo: Number(datos.periodo),
          grado: datos.grado === "" ? null : Number(datos.grado),
          sede_ids: todasSeleccionadas ? null : Array.from(auditoriaSapredSedesSeleccionadas),
          usuario: (datos.usuario || "").trim() || null,
          clave: datos.clave || null,
        }),
      });
      pintarProgresoAuditoria(contenedor, auditoria, sedes);
      iniciarPollingAuditoria(auditoria.id, contenedor, sedes);
    } catch (err) {
      alert(err.message || "No se pudo iniciar la auditoría.");
      boton.disabled = false;
      boton.textContent = "Iniciar auditoría";
    }
  });
}

function iniciarPollingAuditoria(id, contenedor, sedes) {
  auditoriaSapredIdSeguida = id;
  if (auditoriaSapredIntervalo) clearInterval(auditoriaSapredIntervalo);
  auditoriaSapredIntervalo = setInterval(async () => {
    if (!document.body.contains(contenedor)) {
      clearInterval(auditoriaSapredIntervalo);
      auditoriaSapredIntervalo = null;
      return;
    }
    try {
      const auditoria = await api(`/api/boletines/auditoria-sapred/${id}`);
      pintarProgresoAuditoria(contenedor, auditoria, sedes);
      if (["completada", "error"].includes(auditoria.estado)) {
        clearInterval(auditoriaSapredIntervalo);
        auditoriaSapredIntervalo = null;
      }
    } catch (err) {
      // fallo puntual de red al hacer polling: se ignora, se reintenta en el siguiente tick
    }
  }, 2000);
}

function pintarProgresoAuditoria(contenedor, a, sedes) {
  const est = ESTADOS_AUDITORIA[a.estado] || { icono: "", texto: a.estado };
  const porcentaje = a.sedes_totales ? Math.round((a.sedes_completadas / a.sedes_totales) * 100) : 0;
  const terminada = ["completada", "error"].includes(a.estado);

  contenedor.innerHTML = `
    <p><span class="badge-estado ${a.estado === "error" ? "alerta" : a.estado === "completada" ? "ok" : "proceso"}">${est.icono} ${est.texto}</span></p>

    ${
      a.estado === "esperando_login"
        ? `<div class="alerta-caja">Se abrió una ventana de Chrome — entra ahí con tu usuario y contraseña de SAPRED. En cuanto inicies sesión, esto sigue solo.</div>`
        : ""
    }

    <div class="barra-progreso-wrap">
      <div class="barra-progreso"><div class="barra-progreso-relleno" style="width:${porcentaje}%"></div></div>
      <span class="barra-progreso-texto">${a.sedes_completadas} de ${a.sedes_totales} sede(s) — ${porcentaje}%</span>
    </div>

    ${
      a.sede_actual && !terminada
        ? `<p class="pendiente">Ahora mismo: ${a.sede_actual}${a.grado_actual ? ` — ${a.grado_actual}` : ""}</p>`
        : ""
    }

    <div class="resumen-reportes" style="margin-top:10px">
      <div class="metric-card">
        <span>Estudiantes revisados${iconoAyuda("Cuántos estudiantes miró la app en SAPRED durante esta auditoría.")}</span>
        <strong>${a.estudiantes_revisados}</strong>
      </div>
      <div class="metric-card ${a.pendientes_encontrados ? "alerta" : "ok"}">
        <span>Pendientes encontrados${iconoAyuda("Son notas que todavía están vacías en SAPRED: le falta al profesor ponerlas. La app no inventa notas, solo avisa cuáles faltan.")}</span>
        <strong>${a.pendientes_encontrados}</strong>
      </div>
    </div>

    ${
      a.detalle_sedes.length
        ? `<div class="lista-pendientes-modal" style="margin-top:12px; max-height:220px; overflow-y:auto">
             ${a.detalle_sedes
               .map((d) => {
                 const es = ESTADOS_SEDE_AUDITORIA[d.estado] || { icono: "•", clase: "" };
                 return `<div class="fila-pendiente-modal">
                   <div>
                     <span class="badge-estado ${es.clase}">${es.icono} ${d.estado}</span>
                     <strong style="margin-left:6px">${d.sede}</strong>
                     ${d.detalle ? `<div class="pendiente" style="font-size:12px">${d.detalle}</div>` : ""}
                   </div>
                 </div>`;
               })
               .join("")}
           </div>`
        : ""
    }

    ${a.estado === "error" && a.error ? `<div class="alerta-caja" style="margin-top:10px">${a.error}</div>` : ""}

    <div style="text-align:right; margin-top:14px">
      ${
        terminada
          ? `<button type="button" class="boton" id="btn-ver-conciliacion-auditoria">📊 Ver conciliación SIMAC ↔ SAPRED</button>
             <button type="button" class="boton secundario" id="btn-ver-pendientes-auditoria">Ver pendientes</button>
             <button type="button" class="boton secundario" id="btn-ver-historial-auditorias">📋 Ver historial</button>
             <button type="button" class="boton secundario" id="btn-nueva-auditoria">Nueva auditoría</button>`
          : `<p class="pendiente" style="text-align:right; margin:0">Puedes cambiar de sección — esto sigue en segundo plano.</p>`
      }
    </div>
  `;

  document.getElementById("btn-ver-conciliacion-auditoria")?.addEventListener("click", irAConciliacionSapred);
  document.getElementById("btn-ver-pendientes-auditoria")?.addEventListener("click", () => {
    seccionBoletines = "pendientes";
    render();
  });
  document.getElementById("btn-ver-historial-auditorias")?.addEventListener("click", () => abrirModalHistorialAuditorias(sedes));
  document.getElementById("btn-nueva-auditoria")?.addEventListener("click", () => {
    pintarFiltrosAuditoria(contenedor, sedes, []);
    api("/api/boletines/auditoria-sapred?limite=10").then((historial) => pintarFiltrosAuditoria(contenedor, sedes, historial));
  });
}

// --- SAPRED > Sin coincidencia -------------------------------------------

function filaSinCoincidenciaHtml(s) {
  return `<tr>
    <td>${s.sede_nombre}</td>
    <td>${s.nombre_grado}${s.curso ? " - " + s.curso : ""}</td>
    <td>${s.nombre_sapred}</td>
    <td>${s.documento}</td>
    <td>${s.tiene_notas ? '<span class="badge-estado alerta">Sí tiene notas</span>' : '<span class="badge-estado">Sin notas todavía</span>'}</td>
    <td>${s.resuelto ? '<span class="badge-verif ok">✓ Revisado</span>' : `<button type="button" class="boton secundario boton-chico" data-resolver-sin-coincidencia="${s.id}">Marcar revisado</button>`}</td>
  </tr>`;
}

async function renderSapredSinCoincidencia(contenedor, sedes) {
  if (sinCoincidenciaSedeSeleccionada === "") {
    const ietaba = sedes.find((s) => s.nombre.toUpperCase().includes("I.E.T.A.B.A"));
    sinCoincidenciaSedeSeleccionada = ietaba ? String(ietaba.id) : "";
  }
  await cargarYPintarSinCoincidencia(contenedor, sedes);
}

async function cargarYPintarSinCoincidencia(contenedor, sedes) {
  contenedor.innerHTML = '<div class="estado-carga">Cargando...</div>';
  const params = new URLSearchParams({
    anio_lectivo: filtroBoletinesAnio,
    periodo: filtroBoletinesPeriodo,
    solo_no_resueltos: String(sinCoincidenciaSoloNoResueltos),
  });
  if (sinCoincidenciaSedeSeleccionada) params.set("sede_id", sinCoincidenciaSedeSeleccionada);
  const registros = await api(`/api/boletines/sapred-sin-coincidencia?${params}`);

  contenedor.innerHTML = `
    <h2 style="margin:0 0 4px; font-size:20px">Sin coincidencia</h2>
    <p class="pendiente">
      SAPRED reporta a estos estudiantes en un curso, pero su documento no existe en nuestra base local — puede ser
      un documento mal digitado, un estudiante nuevo sin matricular aquí, o de otra sede. No se crea a nadie automáticamente.
    </p>
    <div class="barra-filtros no-imprimir">
      <label class="filtro-campo">Sede
        <select id="select-sede-sincoincidencia">
          <option value="" ${sinCoincidenciaSedeSeleccionada === "" ? "selected" : ""}>Todas las sedes</option>
          ${sedes.map((s) => `<option value="${s.id}" ${String(s.id) === sinCoincidenciaSedeSeleccionada ? "selected" : ""}>${s.nombre}</option>`).join("")}
        </select>
      </label>
      <label class="filtro-campo">Estado
        <select id="select-estado-sincoincidencia">
          <option value="true" ${sinCoincidenciaSoloNoResueltos ? "selected" : ""}>Sin revisar</option>
          <option value="false" ${!sinCoincidenciaSoloNoResueltos ? "selected" : ""}>Todos</option>
        </select>
      </label>
    </div>
    ${
      registros.length
        ? `<div class="tabla-scroll"><table><thead><tr><th>Sede</th><th>Grado</th><th>Nombre (SAPRED)</th><th>Documento</th><th>¿Tiene notas?</th><th></th></tr></thead>
           <tbody>${registros.map(filaSinCoincidenciaHtml).join("")}</tbody></table></div>`
        : '<div class="estado-vacio"><div class="estado-vacio-icono">✓</div><h3>Todo coincide</h3><p>Todos los estudiantes que reporta SAPRED coinciden con la base local.</p></div>'
    }
  `;

  document.getElementById("select-sede-sincoincidencia").addEventListener("change", (e) => {
    sinCoincidenciaSedeSeleccionada = e.target.value;
    cargarYPintarSinCoincidencia(contenedor, sedes);
  });
  document.getElementById("select-estado-sincoincidencia").addEventListener("change", (e) => {
    sinCoincidenciaSoloNoResueltos = e.target.value === "true";
    cargarYPintarSinCoincidencia(contenedor, sedes);
  });
  document.querySelectorAll("[data-resolver-sin-coincidencia]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api(`/api/boletines/sapred-sin-coincidencia/${btn.dataset.resolverSinCoincidencia}`, {
        method: "PATCH",
        body: JSON.stringify({ resuelto: true }),
      });
      await cargarYPintarSinCoincidencia(contenedor, sedes);
    });
  });
}

// --- Modal: detalle de un grupo (se mantiene como modal) --------------------

function filaPendienteModal(p) {
  const areaTxt = p.area ? p.area.nombre : "General (todo el grupo)";
  const quienTxt = p.estudiante ? p.estudiante.nombre_completo : "Todo el grupo";
  const tipoTxt = { nota: "Nota", concepto: "Concepto", observacion: "Observación" }[p.tipo] || p.tipo;
  return `
    <div class="fila-pendiente-modal ${p.resuelto ? "resuelto" : ""}">
      <div>
        <strong>${areaTxt}</strong> — ${quienTxt}
        <div class="pendiente" style="font-size:12px">${tipoTxt}${p.detalle ? `: ${p.detalle}` : ""}</div>
      </div>
      <div style="display:flex; gap:6px; flex-shrink:0">
        <button type="button" class="boton secundario boton-chico" data-toggle-pendiente="${p.id}" data-resuelto="${p.resuelto}">
          ${p.resuelto ? "↺ Reabrir" : "✓ Marcar resuelto"}
        </button>
        <button type="button" class="boton secundario boton-chico" data-eliminar-pendiente="${p.id}" title="Eliminar (ej. si se agregó por error)">🗑</button>
      </div>
    </div>`;
}

async function abrirModalRevision(g) {
  const r = g.revision;
  const contenedor = document.getElementById("modal-revision");
  contenedor.innerHTML = `<div class="modal-fondo"><div class="modal-caja"><p>Cargando estudiantes del grupo...</p></div></div>`;

  const paramsEst = new URLSearchParams({ sede_id: g.sede_id, grado: g.grado, estado: "ACTIVO" });
  if (g.curso !== null && g.curso !== undefined) paramsEst.set("curso", g.curso);

  const [estudiantesGrupo, todasAreas] = await Promise.all([
    api(`/api/estudiantes?${paramsEst}`),
    api("/api/areas"),
  ]);
  const areasGrado = todasAreas.filter((a) => a.grados.includes(g.grado));

  const nombreEstudiante = (e) =>
    `${e.primer_nombre} ${e.segundo_nombre || ""} ${e.primer_apellido} ${e.segundo_apellido || ""}`
      .replace(/\s+/g, " ")
      .trim();

  const cargarPendientesGrupo = async () => {
    const paramsPend = new URLSearchParams({
      anio_lectivo: filtroBoletinesAnio,
      periodo: filtroBoletinesPeriodo,
      sede_id: g.sede_id,
      grado: g.grado,
      solo_no_resueltos: "false",
    });
    if (g.curso !== null && g.curso !== undefined) paramsPend.set("curso", g.curso);
    return api(`/api/boletines/pendientes?${paramsPend}`);
  };

  const pintar = (pendientesGrupo) => {
    const resueltos = pendientesGrupo.filter((p) => p.resuelto).length;
    const total = pendientesGrupo.length;
    const porcentaje = total ? Math.round((resueltos / total) * 100) : 0;

    const estadoPorArea = {};
    areasGrado.forEach((a) => {
      const deEstaArea = pendientesGrupo.filter((p) => p.area && p.area.id === a.id);
      const abiertos = deEstaArea.filter((p) => !p.resuelto).length;
      estadoPorArea[a.id] = abiertos > 0 ? "alerta" : deEstaArea.length ? "ok" : "";
    });

    contenedor.innerHTML = `
      <div class="modal-fondo">
        <div class="modal-caja modal-caja-ancha">
          <div style="display:flex; justify-content:space-between; align-items:start; gap:10px">
            <div>
              <h3 style="margin:0 0 4px">${g.sede_nombre} — ${g.nombre_grupo}</h3>
              <p class="pendiente" style="margin:0">
                Período ${filtroBoletinesPeriodo}, año ${filtroBoletinesAnio}${g.docente ? ` · Docente: ${g.docente.nombre_completo}` : ""}
                · ${estadoBoletinHtml(g)}
              </p>
            </div>
            <button type="button" class="boton secundario boton-chico" id="btn-informe-grupo">🖨 Informe de este grupo</button>
          </div>

          ${
            total
              ? `<div class="barra-progreso-wrap">
                   <div class="barra-progreso"><div class="barra-progreso-relleno" style="width:${porcentaje}%"></div></div>
                   <span class="barra-progreso-texto">${resueltos} de ${total} pendientes puntuales resueltos (${porcentaje}%)</span>
                 </div>`
              : ""
          }

          ${
            areasGrado.length
              ? `<h4 style="margin:16px 0 8px">Áreas</h4>
                 <div class="grid-areas-modal">
                   ${areasGrado.map((a) => `<span class="badge-estado ${estadoPorArea[a.id]}" title="${a.nombre}">${a.codigo}</span>`).join("")}
                 </div>`
              : ""
          }

          <div class="lista-pendientes-modal">
            ${
              pendientesGrupo.length
                ? pendientesGrupo.map(filaPendienteModal).join("")
                : '<p class="pendiente">Sin pendientes puntuales registrados todavía para este grupo.</p>'
            }
          </div>

          <form id="form-agregar-pendiente" class="form-grid">
            <label>Área
              <select name="area_id">
                <option value="">General (todo el grupo)</option>
                ${areasGrado.map((a) => `<option value="${a.id}">${a.nombre}</option>`).join("")}
              </select>
            </label>
            <label>Estudiante
              <select name="estudiante_id">
                <option value="">Todo el grupo</option>
                ${estudiantesGrupo.map((e) => `<option value="${e.id}">${nombreEstudiante(e)}</option>`).join("")}
              </select>
            </label>
            <label>Tipo
              <select name="tipo">
                <option value="nota">Nota</option>
                <option value="concepto">Concepto</option>
                <option value="observacion">Observación</option>
              </select>
            </label>
            <label class="ancho-completo">Detalle (opcional)
              <input type="text" name="detalle" placeholder="Ej: falta la nota del tercer corte" />
            </label>
            <div class="ancho-completo"><button type="submit" class="boton secundario">+ Agregar pendiente puntual</button></div>
          </form>

          <hr />

          ${
            r && (r.materias_faltantes || r.estudiantes_pendientes)
              ? `<div class="pendiente" style="font-size:12px; margin:6px 0">
                   <strong>Texto antiguo (de antes de los pendientes por área — ya no se edita aquí):</strong>
                   ${r.materias_faltantes ? `<div>Materias: ${r.materias_faltantes}</div>` : ""}
                   ${r.estudiantes_pendientes ? `<div>Estudiantes: ${r.estudiantes_pendientes}</div>` : ""}
                 </div>`
              : ""
          }
          <form id="form-revision" class="form-grid">
            <label class="check-linea ancho-completo">
              <input type="checkbox" name="completo" ${r && r.completo ? "checked" : ""} />
              Todas las notas están completas
            </label>
            <label class="check-linea ancho-completo">
              <input type="checkbox" name="observaciones_completas" ${r && r.observaciones_completas ? "checked" : ""} />
              Las observaciones están completas
            </label>
            <label class="ancho-completo">Notas / comentarios
              <textarea name="notas" rows="2">${r && r.notas ? r.notas : ""}</textarea>
            </label>
            <div class="ancho-completo">
              <button type="submit" class="boton">Guardar</button>
              <button type="button" class="boton secundario" id="btn-cerrar-modal">Cerrar</button>
            </div>
          </form>
        </div>
      </div>
    `;

    document.getElementById("btn-cerrar-modal").addEventListener("click", () => {
      contenedor.innerHTML = "";
      render();
    });

    document.getElementById("btn-informe-grupo").addEventListener("click", () => {
      informeGrupoUnico = claveGrupo(g);
      mostrarInformeBoletines = true;
      seccionBoletines = "grupos";
      contenedor.innerHTML = "";
      render();
    });

    document.getElementById("form-agregar-pendiente").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const datos = Object.fromEntries(new FormData(ev.target).entries());
      await api("/api/boletines/pendientes", {
        method: "POST",
        body: JSON.stringify({
          sede_id: g.sede_id,
          grado: g.grado,
          curso: g.curso,
          anio_lectivo: filtroBoletinesAnio,
          periodo: filtroBoletinesPeriodo,
          area_id: datos.area_id ? Number(datos.area_id) : null,
          estudiante_id: datos.estudiante_id ? Number(datos.estudiante_id) : null,
          tipo: datos.tipo,
          detalle: datos.detalle || null,
        }),
      });
      pintar(await cargarPendientesGrupo());
    });

    document.querySelectorAll("[data-toggle-pendiente]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const resueltoActual = btn.dataset.resuelto === "true";
        await api(`/api/boletines/pendientes/${btn.dataset.togglePendiente}`, {
          method: "PATCH",
          body: JSON.stringify({ resuelto: !resueltoActual }),
        });
        pintar(await cargarPendientesGrupo());
      });
    });

    document.querySelectorAll("[data-eliminar-pendiente]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("¿Eliminar este pendiente? (por ejemplo, si se agregó por error)")) return;
        await api(`/api/boletines/pendientes/${btn.dataset.eliminarPendiente}`, { method: "DELETE" });
        pintar(await cargarPendientesGrupo());
      });
    });

    document.getElementById("form-revision").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const datosForm = Object.fromEntries(new FormData(ev.target).entries());
      await api("/api/revisiones-boletin", {
        method: "POST",
        body: JSON.stringify({
          sede_id: g.sede_id,
          grado: g.grado,
          curso: g.curso,
          anio_lectivo: filtroBoletinesAnio,
          periodo: filtroBoletinesPeriodo,
          completo: datosForm.completo === "on",
          // El texto libre ya no se edita desde aquí — qué falta se marca
          // con pendientes puntuales (por área/estudiante). Si el grupo
          // tenía texto antiguo, se conserva tal cual hasta que se resuelva.
          materias_faltantes: r ? r.materias_faltantes : null,
          observaciones_completas: datosForm.observaciones_completas === "on",
          notas: datosForm.notas || null,
          estudiantes_pendientes: r ? r.estudiantes_pendientes : null,
        }),
      });
      contenedor.innerHTML = "";
      render();
    });
  };

  pintar(await cargarPendientesGrupo());
}
