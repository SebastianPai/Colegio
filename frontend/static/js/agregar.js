// --- Vista: Agregar estudiante ---------------------------------------------

async function renderAgregar() {
  app.innerHTML = `
    <div class="pagina-header">
      <div>
        <h1>Matrícula</h1>
        <p class="subtitulo-pagina">Verifica el documento contra la base oficial antes de matricular a un estudiante nuevo.</p>
      </div>
    </div>
    <div class="toolbar">
      <input type="text" id="doc-verificar" placeholder="Número de documento del estudiante..." />
      <button class="boton" id="btn-verificar">Verificar</button>
    </div>
    <div id="resultado-verificacion"></div>
  `;

  document.getElementById("btn-verificar").addEventListener("click", verificarDocumento);
  document.getElementById("doc-verificar").addEventListener("keydown", (e) => {
    if (e.key === "Enter") verificarDocumento();
  });
}

async function verificarDocumento() {
  const documento = document.getElementById("doc-verificar").value.trim();
  const contenedor = document.getElementById("resultado-verificacion");
  if (!documento) return;

  contenedor.innerHTML = "<p>Buscando...</p>";
  const resultado = await api(`/api/estudiantes/verificar?documento=${encodeURIComponent(documento)}`);

  if (resultado.existe) {
    const e = resultado.estudiante;
    const nombre = `${e.primer_nombre} ${e.segundo_nombre || ""} ${e.primer_apellido} ${e.segundo_apellido || ""}`
      .replace(/\s+/g, " ")
      .trim();
    contenedor.innerHTML = `
      <div class="exito-caja">
        Este documento ya está registrado: <strong>${nombre}</strong> —
        ${e.grupo}, ${e.sede ? e.sede.nombre : "sin sede"} (${e.estado}).
        No es necesario volver a agregarlo.
      </div>
    `;
    return;
  }

  contenedor.innerHTML = `
    <div class="alerta-caja">
      ⚠️ Este documento <strong>no aparece</strong> en la base de datos oficial de matrícula
      importada del colegio. Antes de matricularlo aquí, confírmalo con el coordinador
      (puede ser un estudiante nuevo que aún no está en el Excel oficial, o un error de
      digitación en el documento).
    </div>
    <p>Si el coordinador confirma que se puede registrar, completa estos datos:</p>
    ${formularioNuevoEstudiante(documento)}
  `;

  document.getElementById("form-nuevo-estudiante").addEventListener("submit", guardarNuevoEstudiante);
  vincularTipoDocumentoOtro("tipo_documento");
}

function formularioNuevoEstudiante(documento) {
  return `
    <form id="form-nuevo-estudiante" class="form-grid">
      ${tipoDocumentoSelectHtml("tipo_documento", "")}
      <label>Número de documento
        <input type="text" name="documento" value="${documento}" readonly />
      </label>
      <label>Primer nombre
        <input type="text" name="primer_nombre" required />
      </label>
      <label>Segundo nombre
        <input type="text" name="segundo_nombre" />
      </label>
      <label>Primer apellido
        <input type="text" name="primer_apellido" required />
      </label>
      <label>Segundo apellido
        <input type="text" name="segundo_apellido" />
      </label>
      <label>Fecha de nacimiento
        <input type="date" name="fecha_nacimiento" />
      </label>
      <label>Género
        <select name="genero">
          <option value="F">F</option>
          <option value="M">M</option>
        </select>
      </label>
      <label>Grado
        <select name="grado">
          ${NOMBRES_GRADOS.map(([g, nombre]) => `<option value="${g}">${nombre}</option>`).join("")}
        </select>
      </label>
      <label class="ancho-completo">Observaciones
        <input type="text" name="observaciones" placeholder="Ej: pendiente confirmación del coordinador" />
      </label>
      <div class="ancho-completo">
        <button type="submit" class="boton">Guardar de todas formas</button>
      </div>
    </form>
  `;
}

async function guardarNuevoEstudiante(ev) {
  ev.preventDefault();
  const datos = Object.fromEntries(new FormData(ev.target).entries());
  datos.tipo_documento = valorTipoDocumento(datos, "tipo_documento");
  delete datos.tipo_documento_otro;
  Object.keys(datos).forEach((k) => {
    if (datos[k] === "") delete datos[k];
  });
  datos.grado = Number(datos.grado);
  datos.estado = "ACTIVO";

  const contenedor = document.getElementById("resultado-verificacion");
  try {
    const nuevo = await api("/api/estudiantes", { method: "POST", body: JSON.stringify(datos) });
    contenedor.innerHTML = `<div class="exito-caja">Estudiante guardado: ${nuevo.primer_nombre} ${nuevo.primer_apellido}. Recuerda avisarle al coordinador para que quede también en el Excel oficial.</div>`;
  } catch (err) {
    contenedor.innerHTML = `<div class="alerta-caja">No se pudo guardar: ${err.message}</div>`;
  }
}
