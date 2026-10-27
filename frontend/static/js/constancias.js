// --- Vista: Registro de constancias generadas -------------------------------

let filtroConstanciasBusqueda = "";
let filtroConstanciasDesde = "";
let filtroConstanciasHasta = "";
let filtroConstanciasProposito = "";

async function renderConstancias() {
  app.innerHTML = "<p>Cargando registro...</p>";
  const opciones = await api("/api/certificados/opciones");

  const params = new URLSearchParams();
  if (filtroConstanciasBusqueda) params.set("q", filtroConstanciasBusqueda);
  if (filtroConstanciasDesde) params.set("desde", filtroConstanciasDesde);
  if (filtroConstanciasHasta) params.set("hasta", filtroConstanciasHasta);
  if (filtroConstanciasProposito) params.set("proposito", filtroConstanciasProposito);
  const registros = await api(`/api/certificados?${params}`);

  app.innerHTML = `
    <div class="toolbar">
      <input type="text" id="buscar-constancia" placeholder="Buscar por nombre o documento..." value="${filtroConstanciasBusqueda}" />
      <label class="check-linea">Desde <input type="date" id="constancia-desde" value="${filtroConstanciasDesde}" /></label>
      <label class="check-linea">Hasta <input type="date" id="constancia-hasta" value="${filtroConstanciasHasta}" /></label>
      <select id="constancia-proposito">
        <option value="">Todos los propósitos</option>
        ${(opciones.propositos_registro || opciones.propositos)
          .map((p) => `<option value="${p}" ${p === filtroConstanciasProposito ? "selected" : ""}>${p}</option>`)
          .join("")}
      </select>
    </div>
    ${tienePermiso("constancias.generar")
      ? `<p><button type="button" class="boton" id="btn-paz-y-salvo"><i data-lucide=graduation-cap class=ico></i> Paz y salvo grado 11 (servicio social)</button></p>`
      : ""}
    <p>${registros.length} constancia(s) generada(s)</p>
    <table>
      <thead>
        <tr>
          <th>Fecha generación</th><th>Estudiante</th><th>Documento</th><th>Grupo</th>
          <th>Propósito</th><th>Fecha expedición</th><th>Archivos</th>
        </tr>
      </thead>
      <tbody>
        ${registros
          .map((r) => {
            const nombre = `${r.estudiante.primer_nombre} ${r.estudiante.segundo_nombre || ""} ${r.estudiante.primer_apellido} ${r.estudiante.segundo_apellido || ""}`
              .replace(/\s+/g, " ")
              .trim();
            return `
          <tr>
            <td>${r.generado_en.slice(0, 16).replace("T", " ")}</td>
            <td>${nombre}</td>
            <td>${r.estudiante.documento}</td>
            <td>${r.estudiante.grupo}</td>
            <td>${r.proposito}</td>
            <td>${r.fecha_expedicion}</td>
            <td>
              <a class="boton secundario" href="/api/certificados/${r.id}/archivo?formato=docx">Word</a>
              ${r.archivo_pdf ? `<a class="boton secundario" href="/api/certificados/${r.id}/archivo?formato=pdf">PDF</a>` : ""}
            </td>
          </tr>`;
          })
          .join("")}
      </tbody>
    </table>
  `;

  document.getElementById("btn-paz-y-salvo")?.addEventListener("click", abrirPazYSalvo);

  let temporizador;
  document.getElementById("buscar-constancia").addEventListener("input", (e) => {
    clearTimeout(temporizador);
    const valor = e.target.value;
    temporizador = setTimeout(() => {
      filtroConstanciasBusqueda = valor;
      render();
    }, 400);
  });

  document.getElementById("constancia-desde").addEventListener("change", (e) => {
    filtroConstanciasDesde = e.target.value;
    render();
  });
  document.getElementById("constancia-hasta").addEventListener("change", (e) => {
    filtroConstanciasHasta = e.target.value;
    render();
  });
  document.getElementById("constancia-proposito").addEventListener("change", (e) => {
    filtroConstanciasProposito = e.target.value;
    render();
  });
}

// --- Paz y salvo de servicio social (grado 11) ---------------------------------
// Certificado de las 80 horas de servicio social obligatorio, con el formato
// oficial (backend/plantillas/paz_y_salvo_servicio_social.docx). Se escogen
// los estudiantes de 11 y sale un solo Word/PDF con una página por cada uno.

let pysEstudiantes = [];
let pysSeleccionados = new Set();
let pysLugares = {}; // id -> lugar escrito en pantalla
let pysSede = "";

async function abrirPazYSalvo() {
  document.getElementById("pys-modal")?.remove();
  const modal = document.createElement("div");
  modal.id = "pys-modal";
  modal.className = "modal-fondo";
  modal.innerHTML = '<div class="modal-caja modal-caja-ancha"><p class="estado-carga">Cargando estudiantes de grado 11...</p></div>';
  document.body.appendChild(modal);
  modal.addEventListener("click", (ev) => { if (ev.target === modal) modal.remove(); });
  try {
    pysEstudiantes = await api("/api/certificados/paz-y-salvo/estudiantes");
  } catch (err) {
    modal.querySelector(".modal-caja").innerHTML = `<div class="alerta-caja">${esc(err.message)}</div>`;
    return;
  }
  pysSeleccionados = new Set(pysEstudiantes.map((e) => e.id));
  pysLugares = Object.fromEntries(pysEstudiantes.map((e) => [e.id, e.lugar_expedicion || ""]));
  pintarPazYSalvo(modal);
}

function pintarPazYSalvo(modal, resultado = null) {
  const sedes = [...new Map(pysEstudiantes.map((e) => [e.sede_id, e.sede_nombre])).entries()];
  const visibles = pysEstudiantes.filter((e) => !pysSede || String(e.sede_id) === String(pysSede));
  const marcados = visibles.filter((e) => pysSeleccionados.has(e.id));
  const sinLugar = marcados.filter((e) => !(pysLugares[e.id] || "").trim()).length;
  const tipoCorto = (t) => (t || "—").replace(/\.$/, "");
  modal.querySelector(".modal-caja").innerHTML = `
    <header class="est-modal-head">
      <h3><i data-lucide=graduation-cap class=ico></i> Paz y salvo de servicio social — grado 11</h3>
      <button type="button" class="est-visor-cerrar" data-pys-cerrar aria-label="Cerrar"></button>
    </header>
    <p class="pendiente">Certifica las 80 horas de servicio social obligatorio (requisito para el título de bachiller), con el formato oficial
      y la firma del rector. Sale un solo documento con una página por estudiante, listo para imprimir, y queda en el registro de constancias.</p>
    ${resultado ? `
      <div class="exito-caja"><i data-lucide=circle-check class=ico></i> Listo: ${resultado.estudiantes} paz y salvo.
        <a class="boton" href="/api/certificados/paz-y-salvo/descargar/${resultado.archivo}?formato=docx"><i data-lucide=download class=ico></i> Word</a>
        ${resultado.pdf
          ? `<a class="boton" href="/api/certificados/paz-y-salvo/descargar/${resultado.archivo}?formato=pdf" target="_blank" rel="noopener"><i data-lucide=download class=ico></i> PDF</a>`
          : '<span class="pendiente">(no se pudo hacer el PDF: Word no está disponible en el servidor)</span>'}
      </div>` : ""}
    <div class="toolbar">
      <label class="check-linea">Fecha de expedición <input type="date" id="pys-fecha" value="${fechaColombiaISO()}" /></label>
      <select id="pys-sede">
        <option value="">Todas las sedes (${pysEstudiantes.length})</option>
        ${sedes.map(([id, nombre]) => `<option value="${id}" ${String(id) === String(pysSede) ? "selected" : ""}>${esc(nombre)} (${pysEstudiantes.filter((e) => e.sede_id === id).length})</option>`).join("")}
      </select>
      <label class="check-linea"><input type="checkbox" id="pys-todos" ${marcados.length === visibles.length && visibles.length ? "checked" : ""} /> Todos</label>
    </div>
    <div class="toolbar">
      <input type="text" id="pys-lugar-comun" placeholder="Lugar de expedición (ej. Barbacoas)" />
      <button type="button" class="boton secundario" id="pys-poner-lugar">Ponerlo a los que no tienen lugar</button>
    </div>
    ${sinLugar ? `<p class="alerta-caja">${sinLugar} estudiante(s) marcado(s) sin lugar de expedición: en su paz y salvo no saldrá «expedida en …».
      El lugar que escriba aquí se guarda también en su ficha.</p>` : ""}
    <div class="tabla-scroll tabla-scroll-alto">
      <table>
        <thead><tr><th></th><th>Estudiante</th><th>Documento</th><th>Grupo</th><th>Sede</th><th>Expedida en</th></tr></thead>
        <tbody>
          ${visibles.map((e) => `
            <tr>
              <td><input type="checkbox" data-pys-est="${e.id}" ${pysSeleccionados.has(e.id) ? "checked" : ""} aria-label="Incluir a ${esc(e.nombre_completo)}" /></td>
              <td>${esc(e.nombre_completo)}</td>
              <td>${esc(tipoCorto(e.tipo_documento))} ${esc(e.documento)}</td>
              <td>${esc(e.grupo)}</td>
              <td>${esc(e.sede_nombre)}</td>
              <td><input type="text" data-pys-lugar="${e.id}" value="${esc(pysLugares[e.id] || "")}" placeholder="Lugar" style="min-width:120px" /></td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>
    <p style="margin-top:12px">
      <button type="button" class="boton" id="pys-generar" ${marcados.length ? "" : "disabled"}>
        <i data-lucide=printer class=ico></i> Generar ${marcados.length} paz y salvo
      </button>
    </p>`;

  const caja = modal.querySelector(".modal-caja");
  caja.querySelector("[data-pys-cerrar]").addEventListener("click", () => {
    modal.remove();
    if (resultado) render(); // el registro de abajo ya trae los nuevos
  });
  caja.querySelector("#pys-sede").addEventListener("change", (e) => { pysSede = e.target.value; pintarPazYSalvo(modal); });
  caja.querySelector("#pys-todos").addEventListener("change", (e) => {
    visibles.forEach((x) => (e.target.checked ? pysSeleccionados.add(x.id) : pysSeleccionados.delete(x.id)));
    pintarPazYSalvo(modal);
  });
  caja.querySelectorAll("[data-pys-est]").forEach((c) =>
    c.addEventListener("change", () => {
      const id = Number(c.dataset.pysEst);
      if (c.checked) pysSeleccionados.add(id);
      else pysSeleccionados.delete(id);
      pintarPazYSalvo(modal);
    })
  );
  caja.querySelectorAll("[data-pys-lugar]").forEach((i) =>
    i.addEventListener("input", () => { pysLugares[Number(i.dataset.pysLugar)] = i.value; })
  );
  caja.querySelector("#pys-poner-lugar").addEventListener("click", () => {
    const lugar = caja.querySelector("#pys-lugar-comun").value.trim();
    if (!lugar) return;
    visibles.forEach((e) => { if (!(pysLugares[e.id] || "").trim()) pysLugares[e.id] = lugar; });
    pintarPazYSalvo(modal);
  });
  caja.querySelector("#pys-generar").addEventListener("click", async (ev) => {
    const boton = ev.currentTarget;
    boton.disabled = true;
    boton.textContent = "Generando… (puede tardar un minuto)";
    const ids = marcados.map((e) => e.id);
    try {
      const r = await api("/api/certificados/paz-y-salvo", {
        method: "POST",
        body: JSON.stringify({
          estudiante_ids: ids,
          fecha_expedicion: caja.querySelector("#pys-fecha").value || fechaColombiaISO(),
          lugares: Object.fromEntries(ids.map((id) => [id, (pysLugares[id] || "").trim()])),
        }),
      });
      pysEstudiantes.forEach((e) => { if (ids.includes(e.id) && pysLugares[e.id]) e.lugar_expedicion = pysLugares[e.id]; });
      pintarPazYSalvo(modal, r);
    } catch (err) {
      alert(err.message || "No se pudo generar el paz y salvo.");
      boton.disabled = false;
      boton.textContent = `Generar ${ids.length} paz y salvo`;
    }
  });
}
