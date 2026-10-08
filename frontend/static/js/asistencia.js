// --- Vista: Asistencia (panel de coordinación) -------------------------------
//
// Dos tablas separadas, cada una detrás de su propio permiso:
// - "Registro del día" (asistencia.cumplimiento): por grupo, si el director
//   de grupo ya marcó la asistencia general de hoy, con qué conteos.
// - "Estudiantes con inasistencia repetida" (asistencia.estadisticas): racha
//   de días seguidos "faltó todo el día" y excusas recientes.
//
// Las dos miran solo la toma GENERAL (area_id=None): la asistencia por
// área/materia es aparte y opcional, no sirve como fuente de "faltó todo el
// día" (ver comentario en asistencia.py backend).

let asistPanelFecha = null; // null = hoy
let asistPanelSedeId = null;
let asistAlertasSedeId = null;
let asistAlertasGrado = null;
let asistUmbralRacha = 3;

async function renderAsistenciaGeneral() {
  app.innerHTML = '<p class="estado-carga">Cargando asistencia...</p>';
  const puedeCumplimiento = tienePermiso("asistencia.cumplimiento");
  const puedeEstadisticas = tienePermiso("asistencia.estadisticas");

  let sedes = [];
  try {
    sedes = await obtenerSedes();
  } catch {
    sedes = [];
  }

  let panel = [];
  let alertas = [];
  try {
    if (puedeCumplimiento) {
      const params = new URLSearchParams();
      if (asistPanelSedeId) params.set("sede_id", asistPanelSedeId);
      if (asistPanelFecha) params.set("fecha", asistPanelFecha);
      panel = await api(`/api/asistencia/panel-dia?${params}`);
    }
    if (puedeEstadisticas) {
      const params = new URLSearchParams();
      if (asistAlertasSedeId) params.set("sede_id", asistAlertasSedeId);
      if (asistAlertasGrado !== null) params.set("grado", asistAlertasGrado);
      params.set("umbral_racha", asistUmbralRacha);
      alertas = await api(`/api/asistencia/alertas-estudiantes?${params}`);
    }
  } catch (e) {
    app.innerHTML = `<div class="alerta-caja">${
      e.status === 401 || e.status === 403
        ? "No tienes permiso para ver esta sección."
        : "No se pudo cargar la asistencia: " + esc(e.message)
    }</div>`;
    return;
  }

  app.innerHTML = `
    <div class="pagina-header">
      <div>
        <h1>Asistencia</h1>
        <p class="subtitulo-pagina">Quién marcó asistencia hoy y qué estudiantes llevan faltas seguidas.</p>
      </div>
    </div>
    ${puedeCumplimiento ? seccionPanelDiaHtml(panel, sedes) : ""}
    ${puedeEstadisticas ? seccionAlertasAsistenciaHtml(alertas, sedes) : ""}
    ${!puedeCumplimiento && !puedeEstadisticas ? '<div class="alerta-caja">No tienes permiso para ver esta sección.</div>' : ""}
  `;

  vincularAsistenciaGeneral();
}

// --- Sección 1: registro del día --------------------------------------------

function seccionPanelDiaHtml(panel, sedes) {
  const fechaValor = asistPanelFecha || fechaColombiaISO();
  const pendientes = panel.filter((p) => p.estado === "pendiente").length;
  const parciales = panel.filter((p) => p.estado === "parcial").length;
  const completos = panel.filter((p) => p.estado === "completo").length;

  return `
    <section class="asist-seccion">
      <div class="panel-tabla-header">
        <h2>Registro del día</h2>
        <span class="conteo-resultados">${panel.length} grupo(s)</span>
      </div>
      <div class="resumen-reportes resumen-compacta">
        <div class="metric-card ${pendientes ? "alerta" : "ok"}"><span>Sin marcar</span><strong>${pendientes}</strong></div>
        <div class="metric-card ${parciales ? "alerta" : "ok"}"><span>Incompletos</span><strong>${parciales}</strong></div>
        <div class="metric-card ok"><span>Completos</span><strong>${completos}</strong></div>
      </div>
      <div class="barra-filtros">
        <label class="filtro-campo">Fecha
          <input type="date" id="asist-panel-fecha" value="${esc(fechaValor)}" />
        </label>
        <label class="filtro-campo">Sede
          <select id="asist-panel-sede">
            <option value="">Todas las sedes</option>
            ${sedes.map((s) => `<option value="${s.id}" ${Number(asistPanelSedeId) === s.id ? "selected" : ""}>${esc(s.nombre)}</option>`).join("")}
          </select>
        </label>
      </div>
      ${
        panel.length
          ? `<div class="tabla-scroll"><table>
              <thead><tr>
                <th>Grupo</th><th>Docente</th><th>Estado</th>
                <th>Presentes</th><th>Ausentes</th><th>Tardanzas</th><th>Excusas</th><th>Registrados</th>
              </tr></thead>
              <tbody>${panel.map(filaPanelDia).join("")}</tbody></table></div>`
          : '<p class="exito-caja">No hay grupos con director de grupo asignado para este filtro.</p>'
      }
    </section>`;
}

function filaPanelDia(p) {
  const badge =
    p.estado === "completo"
      ? '<span class="badge-estado ok">completo</span>'
      : p.estado === "parcial"
      ? '<span class="badge-estado proceso">incompleto</span>'
      : '<span class="badge-estado alerta">sin marcar</span>';
  const cuando = instanteUtcDesdeApi(p.ultimo_registro);
  const hora = cuando ? cuando.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" }) : null;
  return `
    <tr>
      <td>${esc(p.sede_nombre)} · <strong>${esc(p.nombre_grupo)}</strong></td>
      <td>${esc(p.docente_nombre)}</td>
      <td>${badge}${hora ? `<br><small>${esc(hora)}</small>` : ""}</td>
      <td>${p.presentes}</td>
      <td>${p.ausentes ? `<span class="badge-estado alerta">${p.ausentes}</span>` : "0"}</td>
      <td>${p.tardanzas || 0}</td>
      <td>${p.excusas || 0}</td>
      <td>${p.registrados}/${p.total_estudiantes}</td>
    </tr>`;
}

// --- Sección 2: estudiantes con inasistencia repetida ------------------------

function seccionAlertasAsistenciaHtml(alertas, sedes) {
  return `
    <section class="asist-seccion">
      <div class="panel-tabla-header">
        <h2>Estudiantes con inasistencia repetida</h2>
        <span class="conteo-resultados">${alertas.length} estudiante(s)</span>
      </div>
      <div class="barra-filtros">
        <label class="filtro-campo">Sede
          <select id="asist-alertas-sede">
            <option value="">Todas las sedes</option>
            ${sedes.map((s) => `<option value="${s.id}" ${Number(asistAlertasSedeId) === s.id ? "selected" : ""}>${esc(s.nombre)}</option>`).join("")}
          </select>
        </label>
        <label class="filtro-campo">Grado
          <select id="asist-alertas-grado">
            <option value="">Todos los grados</option>
            ${NOMBRES_GRADOS.map(([g, n]) => `<option value="${g}" ${asistAlertasGrado === g ? "selected" : ""}>${n}</option>`).join("")}
          </select>
        </label>
        <label class="filtro-campo">Faltas seguidas desde
          <select id="asist-alertas-umbral">
            ${[2, 3, 4, 5].map((n) => `<option value="${n}" ${asistUmbralRacha === n ? "selected" : ""}>${n} día(s)</option>`).join("")}
          </select>
        </label>
      </div>
      ${
        alertas.length
          ? `<div class="tabla-scroll"><table>
              <thead><tr><th>Estudiante</th><th>Grupo</th><th>Faltas seguidas</th><th>Excusas recientes</th><th>Último registro</th></tr></thead>
              <tbody>${alertas.map(filaAlertaAsistencia).join("")}</tbody></table></div>`
          : '<p class="exito-caja">Nadie supera el umbral en este filtro.</p>'
      }
    </section>`;
}

function filaAlertaAsistencia(a) {
  return `
    <tr>
      <td><a href="#" data-ver-estudiante-asist="${a.estudiante_id}">${esc(a.nombre_completo)}</a><br><small>${esc(a.documento)}</small></td>
      <td>${esc(a.nombre_grupo)}</td>
      <td>${a.racha_ausente >= asistUmbralRacha ? `<span class="badge-estado alerta">${a.racha_ausente} día(s)</span>` : `${a.racha_ausente} día(s)`}</td>
      <td>${a.excusas_recientes ? `<span class="badge-estado naranja">${a.excusas_recientes}</span>` : "0"}</td>
      <td>${esc(a.ultima_fecha)} · ${esc(a.ultimo_estado)}</td>
    </tr>`;
}

// --- Enlazado -----------------------------------------------------------------

function vincularAsistenciaGeneral() {
  document.getElementById("asist-panel-fecha")?.addEventListener("change", (e) => {
    asistPanelFecha = e.target.value || null;
    renderAsistenciaGeneral();
  });
  document.getElementById("asist-panel-sede")?.addEventListener("change", (e) => {
    asistPanelSedeId = e.target.value || null;
    renderAsistenciaGeneral();
  });
  document.getElementById("asist-alertas-sede")?.addEventListener("change", (e) => {
    asistAlertasSedeId = e.target.value || null;
    renderAsistenciaGeneral();
  });
  document.getElementById("asist-alertas-grado")?.addEventListener("change", (e) => {
    asistAlertasGrado = e.target.value === "" ? null : Number(e.target.value);
    renderAsistenciaGeneral();
  });
  document.getElementById("asist-alertas-umbral")?.addEventListener("change", (e) => {
    asistUmbralRacha = Number(e.target.value);
    renderAsistenciaGeneral();
  });
  document.querySelectorAll("[data-ver-estudiante-asist]").forEach((el) =>
    el.addEventListener("click", (ev) => {
      ev.preventDefault();
      abrirFicha(Number(el.dataset.verEstudianteAsist), "asistencia");
    })
  );
}
