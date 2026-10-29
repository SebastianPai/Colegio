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
  document.getElementById("matr-grado").addEventListener("change", actualizarCursosMatricula);
  actualizarCursosMatricula();
  form.querySelectorAll('input[name="anio_matricula"]').forEach((r) =>
    r.addEventListener("change", () => actualizarAnioMatricula(form))
  );
  form.querySelectorAll('input[name="sino_huerfano"]').forEach((r) =>
    r.addEventListener("change", () => actualizarAcudienteMatricula(form))
  );
  ["sino_retiro", "sino_promovido", "sino_repitente"].forEach((n) =>
    form.querySelectorAll(`input[name="${n}"]`).forEach((r) => r.addEventListener("change", () => actualizarSituacionMatricula(form, n)))
  );
  form.parentesco_opcion.addEventListener("change", () => actualizarAcudienteMatricula(form));
  form.querySelectorAll('input[name="sino_discap"]').forEach((r) =>
    r.addEventListener("change", () => {
      const caja = document.getElementById("matr-discapacidades");
      caja.hidden = form.sino_discap.value !== "si";
      if (caja.hidden) caja.querySelectorAll("input").forEach((i) => { i.type === "checkbox" ? (i.checked = false) : (i.value = ""); });
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

// Tabla del pie de la ficha oficial: en la casilla va solo el número.
const MOTIVOS_RETIRO_FICHA = [
  [1, "Costo muy alto o falta dinero"], [2, "Necesita trabajar"], [3, "Responsabilidades familiares"],
  [4, "Considera que no tiene edad para estudiar"], [5, "Descomposición familiar"],
  [6, "No le gusta o no le interesa el estudio / padres no quieren que estudie"],
  [7, "Cambio de lugar de residencia para mejores oportunidades"], [8, "Acompañó (formó hogar)"],
  [9, "Cruce de ríos peligrosos"], [10, "Falta quien lo acompañe (niños pequeños)"],
  [11, "Maternidad o paternidad a temprana edad"], [12, "Problema de drogas"], [13, "Por enfermedad"],
  [14, "Es discapacitado / necesita educación especial"], [15, "Perdió el año o fue expulsado / bajo rendimiento"],
  [16, "No le gustan los profesores"], [17, "El centro educativo está lejos"],
  [20, "Influencia de amigos / problemas con compañeros"], [21, "Desplazamiento forzado / orden público"],
  [22, "Ausencia o mal estado de vías de acceso"], [23, "Creencias étnicas culturales"],
  [24, "Desconocen la importancia de la educación"], [25, "Otras razones"],
  [26, "Se matriculó y no asistió"], [28, "Se desconoce la causa"],
];

// Promovido y repitente se excluyen: marcar uno en "Sí" pone el otro en "No".
function actualizarSituacionMatricula(form, cambio) {
  const motivo = document.getElementById("matr-motivo-retiro");
  motivo.hidden = form.sino_retiro.value !== "si";
  motivo.querySelector("select").required = !motivo.hidden;
  if (motivo.hidden) motivo.querySelector("select").value = "";
  const otro = { sino_promovido: "sino_repitente", sino_repitente: "sino_promovido" }[cambio];
  if (otro && form[cambio].value === "si") form[otro].value = "no";
}

const PARENTESCOS_ACUDIENTE = ["Madre", "Padre", "Abuela", "Abuelo", "Tía", "Tío", "Hermana", "Hermano", "Madrina", "Padrino", "Otro"];

// "Hijo(a) de" sobra si el acudiente es la madre o el padre (se toma su
// nombre) o si es huérfano(a); y un huérfano no puede tener de acudiente a
// la madre o al padre.
function actualizarAcudienteMatricula(form) {
  const huerfano = form.sino_huerfano.value === "si";
  const select = form.parentesco_opcion;
  select.querySelectorAll('option[value="Madre"], option[value="Padre"]').forEach((o) => { o.hidden = o.disabled = huerfano; });
  if (huerfano && ["Madre", "Padre"].includes(select.value)) select.value = "";
  const otro = document.getElementById("matr-parentesco-otro");
  otro.hidden = select.value !== "Otro";
  otro.querySelector("input").required = !otro.hidden;
  const padres = document.getElementById("matr-padres");
  padres.hidden = huerfano || ["Madre", "Padre"].includes(select.value);
  padres.querySelector("input").required = !padres.hidden;
}

function formularioNuevoEstudiante(documento, sedes) {
  // Toda matrícula nueva es de la sede principal de IETABA: no se escoge.
  const sedeIetaba = sedes.find((s) => /I\.?E\.?T\.?A\.?B\.?A/i.test(s.nombre) && s.pertenece_ietaba) || sedes.find((s) => s.pertenece_ietaba);
  const hoy = fechaColombiaISO();
  const anioActual = Number(hoy.slice(0, 4));
  return `
    <form id="form-nuevo-estudiante" class="matr-form">
      <section class="matr-seccion">
        <h3>¿Para qué año escolar es esta matrícula?</h3>
        <fieldset class="matr-si-no ancho-completo">
          <label class="check-linea"><input type="radio" name="anio_matricula" value="${anioActual}" required />
            <strong>${anioActual}</strong> — entra a estudiar ya, este año</label>
          <label class="check-linea"><input type="radio" name="anio_matricula" value="${anioActual + 1}" />
            <strong>${anioActual + 1}</strong> — matrícula para el próximo año escolar</label>
        </fieldset>
        <p class="pendiente" id="matr-anio-aviso">Escoja el año: con él salen la ficha y el libro de registro de matrícula.</p>
      </section>
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
        <h3>2. Matrícula <span class="matr-anio-titulo"></span></h3>
        <div class="form-grid">
          <label>Sede
            <input type="text" value="${esc(sedeIetaba?.nombre || "")}" readonly class="matr-sede-fija" />
            <input type="hidden" name="sede_id" id="matr-sede" value="${sedeIetaba?.id ?? ""}" />
          </label>
          <label>Grado
            <select name="grado" id="matr-grado" required>
              ${NOMBRES_GRADOS.map(([g, nombre]) => `<option value="${g}">${nombre}</option>`).join("")}
            </select>
          </label>
          <label>Curso / sección
            <select name="curso" id="matr-curso"><option value="">Pendiente (se asigna después)</option></select>
          </label>
          <label>Fecha de ingreso <input type="date" name="fecha_ingreso" value="${hoy}" required /></label>
          <label>Institución o centro de donde viene <input type="text" name="ficha_procedencia" placeholder="Si viene de otra institución" /></label>
          <label>ID SIMAT (si ya lo tiene) <input type="text" name="id_estud" /></label>
          <label class="check-linea ancho-completo"><input type="checkbox" name="ficha_sgp" checked /> Estudiante SGP</label>
        </div>
      </section>

      <section class="matr-seccion">
        <h3>Situación académica</h3>
        <div class="form-grid">
          <label class="ancho-completo"><span id="matr-grado-anterior-texto">¿En qué grado estuvo el año anterior?</span>
            <select name="grado_anterior" required>
              <option value="">Escoja...</option>
              ${NOMBRES_GRADOS.map(([g, nombre]) => `<option value="${g}">${nombre}</option>`).join("")}
              <option value="NO ESTUDIÓ">No estaba estudiando</option>
            </select>
          </label>
          <fieldset class="matr-si-no">
            <legend>¿Se retiró de estudiar el año anterior?</legend>
            <label class="check-linea"><input type="radio" name="sino_retiro" value="si" required /> Sí</label>
            <label class="check-linea"><input type="radio" name="sino_retiro" value="no" /> No</label>
          </fieldset>
          <label id="matr-motivo-retiro" hidden>Motivo del retiro
            <select name="ficha_motivo_retiro">
              <option value="">Escoja...</option>
              ${MOTIVOS_RETIRO_FICHA.map(([n, t]) => `<option value="${n}">${n}. ${t}</option>`).join("")}
            </select>
          </label>
          <fieldset class="matr-si-no">
            <legend>¿Fue promovido(a)?</legend>
            <label class="check-linea"><input type="radio" name="sino_promovido" value="si" required /> Sí</label>
            <label class="check-linea"><input type="radio" name="sino_promovido" value="no" /> No</label>
          </fieldset>
          <fieldset class="matr-si-no">
            <legend>¿Es repitente? (terminó y no obtuvo los logros)</legend>
            <label class="check-linea"><input type="radio" name="sino_repitente" value="si" required /> Sí</label>
            <label class="check-linea"><input type="radio" name="sino_repitente" value="no" /> No</label>
          </fieldset>
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
        <h3>4. Acudiente y familia (para la ficha y el libro de registro)</h3>
        <div class="form-grid">
          <fieldset class="matr-si-no">
            <legend>¿Es huérfano(a)?</legend>
            <label class="check-linea"><input type="radio" name="sino_huerfano" value="si" required /> Sí</label>
            <label class="check-linea"><input type="radio" name="sino_huerfano" value="no" /> No</label>
          </fieldset>
          <label>Nombre completo del acudiente <input type="text" name="ficha_acudiente" required /></label>
          <label>Parentesco
            <select name="parentesco_opcion" id="matr-parentesco" required>
              <option value="">Escoja...</option>
              ${PARENTESCOS_ACUDIENTE.map((p) => `<option value="${p}">${p}</option>`).join("")}
            </select>
          </label>
          <label id="matr-parentesco-otro" hidden>¿Cuál parentesco? <input type="text" name="parentesco_otro" /></label>
          <label>Documento del acudiente <input type="text" name="ficha_documento_acudiente" required /></label>
          <label id="matr-padres">Hijo(a) de (nombres de la madre y del padre) <input type="text" name="ficha_padres" required placeholder="Ej: María García y Edgar Beltrán" /></label>
          <label>Teléfono <input type="tel" name="ficha_telefono" /></label>
          <fieldset class="matr-si-no">
            <legend>¿Necesita hospedaje en el albergue?</legend>
            <label class="check-linea"><input type="radio" name="sino_albergue" value="si" required /> Sí</label>
            <label class="check-linea"><input type="radio" name="sino_albergue" value="no" /> No</label>
          </fieldset>
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

// El año escogido se repite en el título de la sección y en el botón, para
// que nunca quede la duda de para qué año se está matriculando.
function actualizarAnioMatricula(form) {
  const anio = form.anio_matricula.value;
  const boton = form.querySelector('button[type="submit"]');
  form.querySelector(".matr-anio-titulo").textContent = anio ? `· año escolar ${anio}` : "";
  // Matrícula para este año: se pregunta el grado del año pasado; para el
  // próximo año: el grado que cursa ahora. Es la casilla "GRADO AÑO <anterior>".
  const actual = Number(fechaColombiaISO().slice(0, 4));
  document.getElementById("matr-grado-anterior-texto").textContent = !anio
    ? "¿En qué grado estuvo el año anterior?"
    : Number(anio) > actual
      ? `¿En qué grado está ahora, en ${actual}?`
      : `¿En qué grado estuvo el año anterior (${Number(anio) - 1})?`;
  document.getElementById("matr-anio-aviso").hidden = !!anio;
  if (!boton.disabled) boton.textContent = anio ? `Matricular para ${anio} y abrir su ficha de matrícula` : "Matricular y abrir su ficha de matrícula";
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
  // La sección es opcional: por defecto queda pendiente.
  select.innerHTML = `<option value="">Pendiente (se asigna después)</option>` +
    divisiones.map((d) => `<option value="${d.numero}">${grado}-${d.numero} (${esc(d.nombre)})</option>`).join("");
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
  campos.parentesco = d.parentesco_opcion === "Otro" ? (d.parentesco_otro || "").trim() : d.parentesco_opcion;
  if (d.sino_huerfano === "si") delete campos.padres;
  else if (["Madre", "Padre"].includes(d.parentesco_opcion)) campos.padres = (d.ficha_acudiente || "").trim();
  if (d.ficha_sgp) campos.sgp = "X";
  if (d.etnia) campos[d.etnia] = "X";
  SI_NO_FICHA.forEach(([clave]) => {
    if (d[`sino_${clave}`]) campos[`${clave}_${d[`sino_${clave}`]}`] = "X";
  });
  if (d.sino_discap) campos[`discap_${d.sino_discap}`] = "X";
  if (d.sino_huerfano) campos[`huerfano_${d.sino_huerfano}`] = "X";
  if (d.sino_retiro) campos[`retiro_${d.sino_retiro}`] = "X";
  if (d.sino_promovido) campos[`promovido_${d.sino_promovido}`] = "X";
  if (d.sino_repitente) campos[`repitente_${d.sino_repitente}`] = "X";
  if (d.grado_anterior !== "") campos.grado_anterior = d.grado_anterior;
  if (d.sino_albergue) campos[`albergue_${d.sino_albergue}`] = "X";
  if (d.sino_discap === "si") {
    DISCAPACIDADES_FICHA.forEach(([k]) => { if (d[k]) campos[k] = "X"; });
    if (d.disc_otras.trim()) campos.disc_otras = d.disc_otras.trim();
  }
  if (d.fecha_ingreso) {
    const [anio, mes, dia] = d.fecha_ingreso.split("-");
    Object.assign(campos, { ingreso_dia: String(Number(dia)), ingreso_mes: MESES_FICHA[Number(mes) - 1], ingreso_anio: anio });
  }
  return { estudiante, campos_ficha: campos, anio_matricula: Number(d.anio_matricula) };
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
    fichaVisorSiguiente = true; // abre la ficha oficial de una vez; «Siguiente» lleva al libro
    fichaAviso = { tipo: "exito", texto: `${nuevo.primer_nombre} ${nuevo.primer_apellido} quedó matriculado(a) para el año escolar ${nuevo.anio_ficha_matricula}. Imprima la ficha de matrícula y el libro de registro, y hágalos firmar.` };
    abrirFicha(nuevo.id, "agregar");
  } catch (err) {
    contenedor.querySelector("#matr-error")?.remove();
    form.insertAdjacentHTML("beforeend", `<div class="alerta-caja" id="matr-error">No se pudo guardar: ${esc(err.message)}</div>`);
    boton.disabled = false;
    boton.textContent = "Matricular y abrir su ficha de matrícula";
    actualizarAnioMatricula(form);
  }
}
