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
        ${opciones.propositos
          .map((p) => `<option value="${p}" ${p === filtroConstanciasProposito ? "selected" : ""}>${p}</option>`)
          .join("")}
      </select>
    </div>
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
