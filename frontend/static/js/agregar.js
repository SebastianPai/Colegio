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
      <i data-lucide=triangle-alert class=ico></i> Este documento <strong>no aparece</strong> en la base de datos oficial de matrícula
      importada del colegio. Antes de matricularlo aquí, confírmalo con el coordinador
      (puede ser un estudiante nuevo que aún no está en el Excel oficial, o un error de
      digitación en el documento).
    </div>
    <p>Si el coordinador confirma que se puede registrar, completa todos sus datos:</p>
    ${formularioNuevoEstudiante(documento, await api("/api/sedes"))}
  `;

  const form = document.getElementById("form-nuevo-estudiante");
  form.addEventListener("submit", guardarNuevoEstudiante);
  vincularTipoDocumentoOtro("tipo_documento");
  document.getElementById("matr-sede").addEventListener("change", actualizarCursosMatricula);
  document.getElementById("matr-grado").addEventListener("change", actualizarCursosMatricula);
  form.querySelectorAll('input[name="sino_discap"]').forEach((r) =>
    r.addEventListener("change", () => {
      document.getElementById("matr-discapacidades").hidden = form.sino_discap.value !== "si";
    })
  );
}

// Estudiante nuevo: todos los datos del estudiante y de su ficha de
// matrícula en un solo formulario. Lo de la ficha usa los MISMOS nombres de
// casilla que la ficha oficial (backend/app/datos_ficha.py), así lo que se
// escribe aquí sale tal cual en su ficha de matrícula. Queda marcado
// "pendiente SIMAT" y con quién lo matriculó (POST /api/estudiantes/matricula-nueva).

const MESES_FICHA = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO",
  "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"];
const SI_NO_FICHA = [
  ["awapit", "¿Habla awapit?"], ["madre", "¿Madre cabeza de hogar?"], ["desplaz", "¿Víctima de desplazamiento?"],
  ["educ_esp", "¿Requiere educación especial?"], ["rios", "¿Cruza ríos para llegar?"], ["quebradas", "¿Cruza quebradas?"],
];
const DISCAPACIDADES_FICHA = [
  ["disc_ceguera", "Ceguera (visual)"], ["disc_sordera", "Sordera (auditiva)"], ["disc_fisica", "Física (dificultad para moverse)"],
  ["disc_down", "Síndrome Down"], ["disc_cognitiva", "Cognitiva"], ["disc_multiple", "Múltiple"],
];

function siNoFichaHtml(clave, texto) {
  return `
    <fieldset class="matr-si-no">
      <legend>${texto}</legend>
      <label class="check-linea"><input type="radio" name="sino_${clave}" value="si" required /> Sí</label>
      <label class="check-linea"><input type="radio" name="sino_${clave}" value="no" /> No</label>
    </fieldset>`;
}

function formularioNuevoEstudiante(documento, sedes) {
  const hoy = fechaColombiaISO();
  return `
    <form id="form-nuevo-estudiante" class="matr-form">
      <section class="matr-seccion">
        <h3>1. Identificación del estudiante</h3>
        <div class="form-grid">
          ${tipoDocumentoSelectHtml("tipo_documento", "")}
          <label>Número de documento
            <input type="text" name="documento" value="${esc(documento)}" readonly />
          </label>
          <label>Lugar de expedición del documento
            <input type="text" name="lugar_expedicion_documento" required placeholder="Ej: Barbacoas" />
          </label>
          <label>Primer nombre <input type="text" name="primer_nombre" required /></label>
          <label>Segundo nombre <input type="text" name="segundo_nombre" /></label>
          <label>Primer apellido <input type="text" name="primer_apellido" required /></label>
          <label>Segundo apellido <input type="text" name="segundo_apellido" /></label>
          <label>Fecha de nacimiento <input type="date" name="fecha_nacimiento" required /></label>
          <label>Municipio de nacimiento <input type="text" name="ficha_municipio_nacimiento" required /></label>
          <label>Género
            <select name="genero" required>
              <option value="">Escoja...</option>
              <option value="F">Femenino</option>
              <option value="M">Masculino</option>
            </select>
          </label>
        </div>
      </section>

      <section class="matr-seccion">
        <h3>2. Matrícula</h3>
        <div class="form-grid">
          <label>Sede
            <select name="sede_id" id="matr-sede" required>
              <option value="">Escoja la sede...</option>
              ${sedes.map((s) => `<option value="${s.id}">${esc(s.nombre)}</option>`).join("")}
            </select>
          </label>
          <label>Grado
            <select name="grado" id="matr-grado" required>
              ${NOMBRES_GRADOS.map(([g, nombre]) => `<option value="${g}">${nombre}</option>`).join("")}
            </select>
          </label>
          <label>Curso / sección
            <select name="curso" id="matr-curso"><option value="">Sin curso (único grupo)</option></select>
          </label>
          <label>Fecha de ingreso <input type="date" name="fecha_ingreso" value="${hoy}" required /></label>
          <label>Institución o centro de donde viene <input type="text" name="ficha_procedencia" placeholder="Si viene de otra institución" /></label>
          <label>ID SIMAT (si ya lo tiene) <input type="text" name="id_estud" /></label>
          <label class="check-linea ancho-completo"><input type="checkbox" name="ficha_sgp" /> Estudiante SGP</label>
        </div>
      </section>

      <section class="matr-seccion">
        <h3>3. Datos de la ficha de matrícula</h3>
        <div class="form-grid">
          <label>Resguardo <input type="text" name="ficha_resguardo" required /></label>
          <label>Comunidad / dirección <input type="text" name="ficha_direccion" required /></label>
          <label>Tiempo de traslado a la sede: horas <input type="number" min="0" name="ficha_horas" /></label>
          <label>minutos <input type="number" min="0" max="59" name="ficha_minutos" /></label>
          <fieldset class="matr-si-no ancho-completo">
            <legend>Etnia</legend>
            <label class="check-linea"><input type="radio" name="etnia" value="etnia_indigena" required /> Indígena</label>
            <label class="check-linea"><input type="radio" name="etnia" value="etnia_afro" /> Afro</label>
            <label class="check-linea"><input type="radio" name="etnia" value="etnia_mestizo" /> Mestizo</label>
          </fieldset>
          ${SI_NO_FICHA.map(([clave, texto]) => siNoFichaHtml(clave, texto)).join("")}
          <fieldset class="matr-si-no ancho-completo">
            <legend>¿Tiene alguna discapacidad?</legend>
            <label class="check-linea"><input type="radio" name="sino_discap" value="no" required /> No</label>
            <label class="check-linea"><input type="radio" name="sino_discap" value="si" /> Sí</label>
            <div id="matr-discapacidades" class="matr-discapacidades" hidden>
              ${DISCAPACIDADES_FICHA.map(([k, t]) => `<label class="check-linea"><input type="checkbox" name="${k}" /> ${t}</label>`).join("")}
              <label>Otra (¿cuál?) <input type="text" name="disc_otras" /></label>
            </div>
          </fieldset>
        </div>
      </section>

      <section class="matr-seccion">
        <h3>4. Acudiente</h3>
        <div class="form-grid">
          <label>Nombre completo del acudiente <input type="text" name="ficha_acudiente" required /></label>
          <label>Parentesco <input type="text" name="ficha_parentesco" required placeholder="Madre, padre, abuela..." /></label>
          <label>Documento del acudiente <input type="text" name="ficha_documento_acudiente" required /></label>
        </div>
      </section>

      <section class="matr-seccion">
        <div class="form-grid">
          <label class="ancho-completo">Observaciones
            <input type="text" name="observaciones" placeholder="Ej: viene trasladado de otra institución" />
          </label>
        </div>
        <p class="alerta-caja">Quedará marcado <strong>«Nuevo · pendiente SIMAT»</strong> hasta que se confirme que ya está en SIMAT,
          y quedará registrado que <strong>${esc(sesionActual?.usuario?.nombre || "usted")}</strong> lo matriculó.</p>
        <button type="submit" class="boton">Matricular y abrir su ficha de matrícula</button>
      </section>
    </form>
  `;
}

// Cursos (secciones) que ya tiene ese grado en esa sede.
async function actualizarCursosMatricula() {
  const sede = document.getElementById("matr-sede").value;
  const grado = Number(document.getElementById("matr-grado").value);
  const select = document.getElementById("matr-curso");
  let divisiones = [];
  if (sede) {
    const grados = await api(`/api/sedes/${sede}/grados`).catch(() => []);
    divisiones = grados.find((g) => g.grado === grado)?.divisiones || [];
  }
  select.innerHTML = `<option value="">Sin curso (único grupo)</option>` +
    divisiones.map((d) => `<option value="${d.numero}">${grado}-${d.numero} (${esc(d.nombre)})</option>`).join("");
  if (divisiones.length) select.value = String(divisiones[0].numero);
}

// Lo del formulario → { estudiante, campos_ficha } con los nombres de casilla de la ficha oficial.
function datosMatriculaNueva(form) {
  const d = Object.fromEntries(new FormData(form).entries());
  const estudiante = {
    documento: d.documento,
    tipo_documento: valorTipoDocumento(d, "tipo_documento") || null,
    lugar_expedicion_documento: d.lugar_expedicion_documento.trim(),
    primer_nombre: d.primer_nombre.trim(),
    segundo_nombre: d.segundo_nombre.trim() || null,
    primer_apellido: d.primer_apellido.trim(),
    segundo_apellido: d.segundo_apellido.trim() || null,
    fecha_nacimiento: d.fecha_nacimiento || null,
    genero: d.genero,
    sede_id: Number(d.sede_id),
    grado: Number(d.grado),
    curso: d.curso === "" ? null : Number(d.curso),
    id_estud: d.id_estud.trim() || null,
    observaciones: d.observaciones.trim() || null,
    estado: "ACTIVO",
  };
  const campos = {};
  Object.entries(d).forEach(([k, v]) => {
    if (k.startsWith("ficha_") && String(v).trim()) campos[k.slice(6)] = String(v).trim();
  });
  if (d.ficha_sgp) campos.sgp = "X";
  if (d.etnia) campos[d.etnia] = "X";
  SI_NO_FICHA.forEach(([clave]) => {
    if (d[`sino_${clave}`]) campos[`${clave}_${d[`sino_${clave}`]}`] = "X";
  });
  if (d.sino_discap) campos[`discap_${d.sino_discap}`] = "X";
  if (d.sino_discap === "si") {
    DISCAPACIDADES_FICHA.forEach(([k]) => { if (d[k]) campos[k] = "X"; });
    if (d.disc_otras.trim()) campos.disc_otras = d.disc_otras.trim();
  }
  if (d.fecha_ingreso) {
    const [anio, mes, dia] = d.fecha_ingreso.split("-");
    Object.assign(campos, { ingreso_dia: String(Number(dia)), ingreso_mes: MESES_FICHA[Number(mes) - 1], ingreso_anio: anio });
  }
  return { estudiante, campos_ficha: campos };
}

async function guardarNuevoEstudiante(ev) {
  ev.preventDefault();
  const form = ev.target;
  const boton = form.querySelector('button[type="submit"]');
  const contenedor = document.getElementById("resultado-verificacion");
  boton.disabled = true;
  boton.textContent = "Guardando...";
  try {
    const nuevo = await api("/api/estudiantes/matricula-nueva", {
      method: "POST",
      body: JSON.stringify(datosMatriculaNueva(form)),
      sinCola: true, // el documento podría ya existir: hay que saberlo ahora, no después
    });
    // Directo a su ficha, en la pestaña Matrícula: la ficha oficial ya sale llena.
    fichaSubSiguiente = "matricula";
    fichaAviso = { tipo: "exito", texto: `${nuevo.primer_nombre} ${nuevo.primer_apellido} quedó matriculado(a). Ya puede descargar o imprimir su ficha de matrícula.` };
    abrirFicha(nuevo.id, "agregar");
  } catch (err) {
    contenedor.querySelector("#matr-error")?.remove();
    form.insertAdjacentHTML("beforeend", `<div class="alerta-caja" id="matr-error">No se pudo guardar: ${esc(err.message)}</div>`);
    boton.disabled = false;
    boton.textContent = "Matricular y abrir su ficha de matrícula";
  }
}
