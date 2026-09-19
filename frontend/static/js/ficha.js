// --- Vista: Ficha del estudiante (fotos + constancia) -----------------------

const TIPOS_DOCUMENTO_TEXTO = {
  "C.C.": "Cédula de ciudadanía",
  "T.I.": "Tarjeta de identidad",
  "R.C.": "Registro civil de nacimiento",
};
const NIVELES_POR_GRADO = {
  0: "preescolar", 1: "básica primaria", 2: "básica primaria", 3: "básica primaria",
  4: "básica primaria", 5: "básica primaria", 6: "básica secundaria", 7: "básica secundaria",
  8: "básica secundaria", 9: "básica secundaria", 10: "media", 11: "media",
};
const DIAS_TEXTO = {
  1: "uno", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis", 7: "siete", 8: "ocho",
  9: "nueve", 10: "diez", 11: "once", 12: "doce", 13: "trece", 14: "catorce", 15: "quince",
  16: "dieciséis", 17: "diecisiete", 18: "dieciocho", 19: "diecinueve", 20: "veinte",
  21: "veintiuno", 22: "veintidós", 23: "veintitrés", 24: "veinticuatro", 25: "veinticinco",
  26: "veintiséis", 27: "veintisiete", 28: "veintiocho", 29: "veintinueve", 30: "treinta",
  31: "treinta y uno",
};
const MESES_TEXTO = {
  1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio", 7: "julio",
  8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
};

function previsualizarConstancia(e, nombreCompleto, datos) {
  const nombreGrado = (NOMBRES_GRADOS.find(([g]) => g === e.grado) || [0, ""])[1].toLowerCase();
  const nivel = NIVELES_POR_GRADO[e.grado] || "básica";
  const tipoDocTexto = TIPOS_DOCUMENTO_TEXTO[e.tipo_documento] || e.tipo_documento || "Cédula de ciudadanía";
  const fecha = datos.fecha_expedicion ? new Date(`${datos.fecha_expedicion}T00:00:00`) : new Date();
  const diaTexto = DIAS_TEXTO[fecha.getDate()] || fecha.getDate();
  const mesTexto = MESES_TEXTO[fecha.getMonth() + 1] || "";

  return `
    <div class="preview-constancia-hoja">
      <div class="preview-logos">
        <img src="/static/logos/logo1.jpg" alt="UNIPA" />
        <div class="preview-titulo">
          UNIDAD INDIGENA DEL PUEBLO AWA "UNIPA"<br />
          INSTITUCION EDUCATIVA INDIGENA TECNICA AGROAMBIENTAL BILINGÜE AWA "IETABA"
        </div>
        <img src="/static/logos/logo2.jpeg" alt="IETABA" />
      </div>
      <p class="preview-constancia-titulo">Constancia:</p>
      <p>Que el estudiante: <strong>${nombreCompleto}</strong>, identificado(a) con
      ${tipoDocTexto} No. ${e.documento} de ${datos.lugar_expedicion || "____"} se encuentra
      matriculado(a) y registrado (a) en la base de Datos del sistema Integrado de
      Matriculas_ SIMAT, de la Institución Educativa Indígena Técnica Agroambiental
      Bilingüe Awá IETABA" en el Grado ${nombreGrado} (${e.grado}) de la Educación ${nivel},
      jornada ${datos.jornada || ""}, Calendario A, año escolar ${datos.anio_escolar || ""}.</p>
      <p>Para constancia se firma en el Predio el Verde, Resguardo el Gran Sábalo del
      Municipio de Barbacoas Nariño a los ${diaTexto} (${fecha.getDate()}) días del mes de
      ${mesTexto} del año ${fecha.getFullYear()}.</p>
      <p><strong>Válido para ${datos.proposito || "____"}.</strong></p>
      <div class="preview-firma">
        <div class="preview-linea-firma"></div>
        JOSE MIGUEL BISBICUS<br />C.C. N° 87.432.650 de Barbacoas (N)<br />
        RECTOR "IETABA"<br />CEL: 3185226156
      </div>
    </div>
  `;
}

// "permanente" es el valor por defecto del checkbox según la categoría —
// documentos como la cédula de los padres o el documento del estudiante no
// cambian cada año, a diferencia de la ficha de matrícula o el boletín, que
// sí se vuelven a presentar cada año lectivo. Siempre se puede cambiar a mano.
const CATEGORIAS_DOCUMENTO = [
  { nombre: "Ficha de matrícula - Página 1", permanente: false },
  { nombre: "Ficha de matrícula - Página 2", permanente: false },
  { nombre: "Documento de identidad del estudiante", permanente: true },
  { nombre: "Certificado de notas (año anterior)", permanente: false },
  { nombre: "Liberación de cupo", permanente: false },
  { nombre: "Boletín colegio anterior", permanente: false },
  { nombre: "Cédula del padre", permanente: true },
  { nombre: "Cédula de la madre", permanente: true },
];

function opcionesAnioLectivo(anioSeleccionado) {
  const actual = new Date().getFullYear();
  const anios = [];
  for (let a = actual + 1; a >= actual - 3; a--) anios.push(a);
  return anios
    .map((a) => `<option value="${a}" ${a === anioSeleccionado ? "selected" : ""}>${a}</option>`)
    .join("");
}

// --- Preferencias del usuario (persistidas, nunca bloquean si el --------
// --- almacenamiento no está disponible) -------------------------------
function leerPreferencia(clave, porDefecto) {
  try {
    return localStorage.getItem(clave) || porDefecto;
  } catch {
    return porDefecto;
  }
}
function guardarPreferencia(clave, valor) {
  try {
    localStorage.setItem(clave, valor);
  } catch {
    /* almacenamiento no disponible: no es crítico */
  }
}

// --- Indicador de carga de vista previa (verde = cargó, rojo = falló) ---
// Envuelve cualquier <img> de miniatura; se conecta después de pintar el
// HTML con vincularEstadoPreviews().
function imagenConEstadoHtml(src, alt, claseImg) {
  return `<span class="doc-preview-estado-wrap">
    <img src="${src}" alt="${alt || ""}" class="doc-preview-img ${claseImg || ""}" loading="lazy" />
    <span class="doc-preview-punto" title="Cargando vista previa..."></span>
  </span>`;
}
function vincularEstadoPreviews(raiz) {
  (raiz || document).querySelectorAll(".doc-preview-img").forEach((img) => {
    const punto = img.nextElementSibling;
    const marcar = (ok) => {
      if (!punto || !punto.classList.contains("doc-preview-punto")) return;
      punto.classList.toggle("ok", ok);
      punto.classList.toggle("error", !ok);
      punto.title = ok ? "Vista previa cargada" : "No se pudo cargar la vista previa";
    };
    if (img.complete) marcar(img.naturalWidth > 0);
    else {
      img.addEventListener("load", () => marcar(true), { once: true });
      img.addEventListener("error", () => marcar(false), { once: true });
    }
  });
}

// --- PDF.js: leer un PDF existente página por página (subida masiva) ------
// Es lo contrario del escáner (static/js/scanner.js), que genera un PDF
// nuevo con jsPDF — esto LEE uno que el usuario ya tiene, para poder
// elegir qué páginas usar y a qué categoría va cada una (como ILovePDF).
// Se carga bajo demanda, solo cuando de verdad se sube un PDF.

let _pdfjsListo = null;
function asegurarPdfJs() {
  if (_pdfjsListo) return _pdfjsListo;
  _pdfjsListo = import("/static/vendor/pdf.min.mjs").then((mod) => {
    mod.GlobalWorkerOptions.workerSrc = "/static/vendor/pdf.worker.min.mjs";
    return mod;
  });
  return _pdfjsListo;
}

async function paginasDePdfComoMiniaturas(arrayBuffer) {
  const pdfjsLib = await asegurarPdfJs();
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer.slice(0) }).promise;
  const paginas = [];
  try {
    for (let n = 1; n <= pdf.numPages; n++) {
      const pagina = await pdf.getPage(n);
      const viewport = pagina.getViewport({ scale: 0.35 });
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(viewport.width));
      canvas.height = Math.max(1, Math.round(viewport.height));
      await pagina.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
      paginas.push({ numero: n, previewUrl: canvas.toDataURL("image/jpeg", 0.7) });
    }
  } finally {
    await pdf.destroy();
  }
  return paginas;
}

// Vuelve a renderizar UNA página a buena resolución (la miniatura de arriba
// es chica, solo para elegir) y la entrega como blob JPEG listo para subir
// por el mismo camino que cualquier otra foto.
async function renderizarPaginaPdfAImagen(arrayBuffer, numeroPagina) {
  const pdfjsLib = await asegurarPdfJs();
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer.slice(0) }).promise;
  try {
    const pagina = await pdf.getPage(numeroPagina);
    const viewport = pagina.getViewport({ scale: 2.0 });
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(viewport.width);
    canvas.height = Math.round(viewport.height);
    await pagina.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
    return await new Promise((resolve) => canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.88));
  } finally {
    await pdf.destroy();
  }
}

function fotoHtml(f) {
  const contenido = `
    <a href="/api/fotos/${f.id}/archivo" target="_blank" class="foto-miniatura-link">
      ${imagenConEstadoHtml(`/api/fotos/${f.id}/miniatura`, f.etiqueta)}
      ${f.es_pdf ? '<span class="foto-badge-pdf">PDF</span>' : ""}
      ${f.anio_lectivo === null ? '<span class="foto-badge-permanente">Todos los años</span>' : ""}
    </a>`;
  return `
    <div class="foto-card">
      ${contenido}
      <div class="foto-etiqueta">${f.etiqueta}</div>
      <button type="button" class="boton secundario" data-eliminar-foto="${f.id}">Eliminar</button>
    </div>`;
}

// --- Carrusel de documentos por categoría (ficha del estudiante) -----------
// Reemplaza la vieja galería plana: muestra las 8 categorías esperadas una
// por una (con flechas para pasar y "peeks" a los lados, como el diseño de
// referencia), y cuando a una categoría le falta el archivo aparece un botón
// grande de "Escanear / Subir" en su lugar en vez de tener que ir a buscar
// un formulario aparte y elegir el tipo de documento a mano.

let fichaDocEstudianteIdActual = null; // para saber cuándo cambió de estudiante
let fichaDocCategoriaIndex = 0;
let fichaDocAnioSeleccionado = null; // null = automático (año más reciente con datos, o el actual)
let fichaDocAccionPendiente = null; // { modo: "escanear"|"reemplazar", categoria, permanente, fotoIdAReemplazar? }
let vistaDocumentos = leerPreferencia("ietaba_vista_documentos", "carrusel"); // "carrusel" | "lista"

// La categoría que se estaba viendo se recuerda POR ESTUDIANTE (no solo en
// memoria): así, volver a un estudiante — o recargar la página — no manda
// siempre a la categoría 1, sino a donde se había quedado con él.
function leerIndiceCategoriaGuardado(estudianteId) {
  const valor = Number(leerPreferencia(`ietaba_doc_categoria_${estudianteId}`, "0"));
  return Number.isInteger(valor) && valor >= 0 && valor < CATEGORIAS_DOCUMENTO.length ? valor : 0;
}
function guardarIndiceCategoria(estudianteId, indice) {
  guardarPreferencia(`ietaba_doc_categoria_${estudianteId}`, String(indice));
}

function fotoParaCategoria(fotos, categoria, anioSeleccionado) {
  if (categoria.permanente) {
    return fotos.find((f) => f.etiqueta === categoria.nombre && f.anio_lectivo === null) || null;
  }
  return fotos.find((f) => f.etiqueta === categoria.nombre && f.anio_lectivo === anioSeleccionado) || null;
}

// A qué categorías todavía les falta el archivo (en el orden de la lista),
// para sugerir automáticamente a cuál asignar cada archivo de una subida
// masiva — así casi nunca hay que tocar el selector, solo corregir alguno.
function categoriasFaltantesOrdenadas(fotos, anioSeleccionado) {
  return CATEGORIAS_DOCUMENTO.filter((c) => !fotoParaCategoria(fotos, c, anioSeleccionado));
}

function tarjetaPeekDocHtml(categoria, foto, indice) {
  return `
    <div class="doc-carrusel-peek" data-doc-ir="${indice}">
      <div class="doc-carrusel-preview">
        ${foto ? imagenConEstadoHtml(`/api/fotos/${foto.id}/miniatura`, "") : '<span class="doc-carrusel-peek-icono">📄</span>'}
      </div>
      <span class="doc-carrusel-peek-etiqueta">${categoria.nombre}</span>
    </div>`;
}

// Acciones de una categoría (escanear/reescanear/reemplazar/eliminar) —
// las mismas para el carrusel y para la lista, un solo lugar.
function accionesDocCategoriaHtml(categoria, foto, tamano) {
  const chico = tamano === "chico" ? " boton-chico" : "";
  if (foto) {
    return `<button type="button" class="boton secundario${chico}" data-doc-escanear="1" data-doc-categoria="${categoria.nombre}" data-doc-permanente="${categoria.permanente}" data-doc-foto-id-reemplazar="${foto.id}">📷 Reescanear</button>
            <button type="button" class="boton secundario${chico}" data-doc-accion="reemplazar" data-doc-categoria="${categoria.nombre}" data-doc-permanente="${categoria.permanente}" data-doc-foto-id="${foto.id}">🔄 Reemplazar archivo</button>
            <button type="button" class="boton secundario${chico}" data-eliminar-foto="${foto.id}">🗑 Eliminar</button>`;
  }
  return `<button type="button" class="boton doc-carrusel-boton-escanear" data-doc-escanear="1" data-doc-categoria="${categoria.nombre}" data-doc-permanente="${categoria.permanente}">📷 Escanear documento</button>
          <button type="button" class="boton-texto-chico" data-doc-accion="escanear" data-doc-categoria="${categoria.nombre}" data-doc-permanente="${categoria.permanente}">o subir un archivo existente</button>`;
}

function carruselCuerpoHtml(fotos, anio) {
  const n = CATEGORIAS_DOCUMENTO.length;
  const i = fichaDocCategoriaIndex;
  const iPrev = (i - 1 + n) % n;
  const iNext = (i + 1) % n;

  const catActual = CATEGORIAS_DOCUMENTO[i];
  const catPrev = CATEGORIAS_DOCUMENTO[iPrev];
  const catNext = CATEGORIAS_DOCUMENTO[iNext];
  const fotoActual = fotoParaCategoria(fotos, catActual, anio);
  const fotoPrev = fotoParaCategoria(fotos, catPrev, anio);
  const fotoNext = fotoParaCategoria(fotos, catNext, anio);

  return `
    <div class="doc-carrusel-fila">
      <button type="button" class="doc-carrusel-flecha" id="doc-carrusel-prev" title="Categoría anterior">‹</button>
      ${tarjetaPeekDocHtml(catPrev, fotoPrev, iPrev)}
      <div class="doc-carrusel-centro ${fotoActual ? "doc-carrusel-lista" : ""}">
        <span class="doc-carrusel-etiqueta">
          ${catActual.nombre}${catActual.permanente ? ' <span class="doc-carrusel-permanente">· todos los años</span>' : ""}
        </span>
        <div class="doc-carrusel-preview">
          ${
            fotoActual
              ? `<a href="/api/fotos/${fotoActual.id}/archivo" target="_blank">
                   ${imagenConEstadoHtml(`/api/fotos/${fotoActual.id}/miniatura`, catActual.nombre)}
                   ${fotoActual.es_pdf ? '<span class="foto-badge-pdf">PDF</span>' : ""}
                 </a>`
              : `<span class="doc-carrusel-vacio-icono">📄</span><p class="doc-carrusel-vacio-texto">Todavía no se ha subido</p>`
          }
        </div>
        <div class="doc-carrusel-acciones">${accionesDocCategoriaHtml(catActual, fotoActual, "chico")}</div>
      </div>
      ${tarjetaPeekDocHtml(catNext, fotoNext, iNext)}
      <button type="button" class="doc-carrusel-flecha" id="doc-carrusel-next" title="Siguiente categoría">›</button>
    </div>
    <p class="doc-carrusel-contador">Categoría ${i + 1} de ${n}</p>
  `;
}

function tarjetaDocListaHtml(categoria, foto) {
  return `
    <div class="tarjeta-doc-lista">
      <div class="tarjeta-doc-lista-preview">
        ${
          foto
            ? `<a href="/api/fotos/${foto.id}/archivo" target="_blank">
                 ${imagenConEstadoHtml(`/api/fotos/${foto.id}/miniatura`, categoria.nombre)}
                 ${foto.es_pdf ? '<span class="foto-badge-pdf">PDF</span>' : ""}
               </a>`
            : `<span class="doc-carrusel-vacio-icono">📄</span>`
        }
      </div>
      <div class="tarjeta-doc-lista-nombre">
        ${categoria.nombre}${categoria.permanente ? ' <span class="doc-carrusel-permanente">· todos los años</span>' : ""}
      </div>
      <div class="tarjeta-doc-lista-acciones">${accionesDocCategoriaHtml(categoria, foto, "chico")}</div>
    </div>`;
}

function listaDocumentosHtml(fotos, anio) {
  return `<div class="grid-tarjetas-doc">
    ${CATEGORIAS_DOCUMENTO.map((cat) => tarjetaDocListaHtml(cat, fotoParaCategoria(fotos, cat, anio))).join("")}
  </div>`;
}

// Encabezado compartido (título + selector Carrusel/Lista + año lectivo) y
// el input de archivo oculto que usan tanto "Escanear"/"Reemplazar" como el
// escáner, sin importar cuál de las dos vistas esté activa.
function documentosSeccionHtml(fotos) {
  const anio = fichaDocAnioSeleccionado ?? new Date().getFullYear();
  return `
    <div class="doc-carrusel-encabezado">
      <h4>Documentos por categoría</h4>
      <div class="doc-vista-toggle" role="group" aria-label="Vista de documentos">
        <button type="button" class="doc-vista-btn ${vistaDocumentos === "carrusel" ? "activo" : ""}" data-doc-vista="carrusel">▤ Carrusel</button>
        <button type="button" class="doc-vista-btn ${vistaDocumentos === "lista" ? "activo" : ""}" data-doc-vista="lista">☰ Lista</button>
      </div>
      <label class="check-linea">Año lectivo
        <select id="select-anio-documentos">${opcionesAnioLectivo(anio)}</select>
      </label>
    </div>
    ${vistaDocumentos === "carrusel" ? carruselCuerpoHtml(fotos, anio) : listaDocumentosHtml(fotos, anio)}
    <input type="file" id="doc-carrusel-input-archivo" accept="image/*,application/pdf" style="display:none" />
  `;
}

// Punto único de subida de un documento por categoría — lo usan tanto el
// input de archivo tradicional como el escáner (static/js/scanner.js), para
// no duplicar la lógica de reemplazo/permanente/año lectivo.
async function subirDocumentoCategoria(categoria, permanente, fotoIdAReemplazar, archivo, nombreArchivo) {
  if (fotoIdAReemplazar) {
    await api(`/api/fotos/${fotoIdAReemplazar}`, { method: "DELETE" });
  }
  const form = new FormData();
  form.set("etiqueta", categoria);
  form.set("anio_lectivo", String(fichaDocAnioSeleccionado ?? new Date().getFullYear()));
  form.set("permanente", permanente ? "true" : "false");
  form.set("archivo", archivo, nombreArchivo || undefined);
  // Fase 4A': fetch crudo (sube un archivo), no pasa por api(): la renovación
  // del token de acceso hay que pedirla explícitamente.
  await asegurarSesionFresca();
  const res = await fetch(`/api/estudiantes/${fichaEstudianteId}/fotos`, { method: "POST", body: form });
  if (!res.ok) {
    const cuerpo = await res.json().catch(() => ({}));
    throw new Error(cuerpo.detail || "No se pudo subir el documento");
  }
}

// Documentos subidos con un nombre libre (categoría "Otro"), fuera de las 8
// categorías fijas — se muestran aparte, en su propia galería chiquita.
function otrosDocumentosHtml(fotos) {
  const nombresFijos = new Set(CATEGORIAS_DOCUMENTO.map((c) => c.nombre));
  const otros = fotos.filter((f) => !nombresFijos.has(f.etiqueta));
  if (!otros.length) return "";
  return `
    <details class="seccion-colapsable" style="margin-top:14px">
      <summary>Otros documentos (${otros.length})</summary>
      <div class="galeria-fotos">${otros.map(fotoHtml).join("")}</div>
    </details>`;
}

// La ficha arranca en solo-lectura por sección: los campos se pueden leer y
// copiar, pero no se modifican por accidente. "Editar" desbloquea esa sección
// y muestra Guardar / Cancelar; al guardar o cancelar se vuelve a bloquear.
function accionesFichaHtml() {
  return `
    <div class="ancho-completo form-acciones-ficha">
      <button type="button" class="boton secundario" data-ficha-editar>✏️ Editar</button>
      <button type="submit" class="boton" data-ficha-guardar hidden>Guardar</button>
      <button type="button" class="boton secundario" data-ficha-cancelar hidden>Cancelar</button>
    </div>`;
}

function bloquearFormularioFicha(form) {
  form.querySelectorAll("input, select, textarea").forEach((el) => {
    if (el.tagName === "SELECT" || el.type === "checkbox" || el.type === "radio") el.disabled = true;
    else el.readOnly = true;
  });
  form.classList.add("form-bloqueado");
  form.querySelector("[data-ficha-editar]").hidden = false;
  form.querySelector("[data-ficha-guardar]").hidden = true;
  form.querySelector("[data-ficha-cancelar]").hidden = true;
}

function desbloquearFormularioFicha(form) {
  form.querySelectorAll("input, select, textarea").forEach((el) => {
    el.disabled = false;
    el.readOnly = false;
  });
  form.classList.remove("form-bloqueado");
  form.querySelector("[data-ficha-editar]").hidden = true;
  form.querySelector("[data-ficha-guardar]").hidden = false;
  form.querySelector("[data-ficha-cancelar]").hidden = false;
  form.querySelector("input:not([type=hidden]), select, textarea")?.focus();
}

function vincularBloqueoFicha() {
  ["form-datos-estudiante", "form-doc-identidad"].forEach((id) => {
    const form = document.getElementById(id);
    if (!form) return;
    bloquearFormularioFicha(form);
    form.querySelector("[data-ficha-editar]").addEventListener("click", () => desbloquearFormularioFicha(form));
    form.querySelector("[data-ficha-cancelar]").addEventListener("click", () => renderFicha());
  });
}

async function renderFicha() {
  app.innerHTML = "<p>Cargando...</p>";
  const [e, opciones] = await Promise.all([
    api(`/api/estudiantes/${fichaEstudianteId}`),
    api("/api/certificados/opciones"),
  ]);

  const nombreCompleto = `${e.primer_nombre} ${e.segundo_nombre || ""} ${e.primer_apellido} ${e.segundo_apellido || ""}`
    .replace(/\s+/g, " ")
    .trim();
  const hoy = fechaColombiaISO();

  if (fichaDocEstudianteIdActual !== fichaEstudianteId) {
    fichaDocEstudianteIdActual = fichaEstudianteId;
    fichaDocCategoriaIndex = leerIndiceCategoriaGuardado(fichaEstudianteId);
    fichaDocAnioSeleccionado = null;
  }

  app.innerHTML = `
    <button class="volver" id="btn-volver-ficha">← Volver</button>
    <div class="ficha-header">
      <h1>${nombreCompleto}</h1>
      <p class="ficha-meta">
        ${e.grupo} · ${e.sede ? e.sede.nombre : "sin sede"} · Documento: ${e.documento}
        · <span class="badge ${e.activo ? "activo" : "inactivo"}">${(e.estado || "").toLowerCase()}</span>
      </p>
    </div>

    <details class="seccion-colapsable" open>
      <summary>Datos del estudiante</summary>
      <form id="form-datos-estudiante" class="form-grid">
        <label>Fecha de nacimiento
          <input type="date" name="fecha_nacimiento" value="${e.fecha_nacimiento || ""}" />
        </label>
        <label>Género
          <select name="genero">
            <option value="" ${!e.genero ? "selected" : ""}>Sin dato</option>
            <option value="M" ${e.genero === "M" ? "selected" : ""}>Masculino</option>
            <option value="F" ${e.genero === "F" ? "selected" : ""}>Femenino</option>
          </select>
        </label>
        <label>Grado
          <select name="grado">
            ${NOMBRES_GRADOS.map(([g, nombre]) => `<option value="${g}" ${g === e.grado ? "selected" : ""}>${nombre}</option>`).join("")}
          </select>
        </label>
        <label>Curso / sección
          <input type="number" name="curso" min="1" step="1" value="${e.curso ?? ""}" placeholder="Ej: 1, 2, 3..." />
        </label>
        <label>ID de estudiante (SIMAT)
          <input type="text" name="id_estud" value="${e.id_estud || ""}" />
        </label>
        <label class="ancho-completo">Observaciones
          <input type="text" name="observaciones" value="${e.observaciones || ""}" placeholder="Notas internas sobre este estudiante" />
        </label>
        <label class="ancho-completo check-linea">
          <input type="checkbox" name="posible_retirado" ${e.posible_retirado ? "checked" : ""} />
          Posible retirado — sigue en el sistema pero <strong>no cuenta</strong> en los pendientes de boletín (¿qué falta?). No es un retiro formal.
        </label>
        ${accionesFichaHtml()}
      </form>
      <div id="resultado-datos-estudiante"></div>
      ${
        e.curso === null
          ? `<p class="pendiente" style="font-size:12.5px; margin-top:10px">
               ⚠ Sin sección/curso asignado — esto es normal para las sedes rurales que todavía no
               tienen su propio Excel de matrícula. Complétalo aquí si ya lo confirmaste.
             </p>`
          : ""
      }
    </details>

    <details class="seccion-colapsable" open>
      <summary>Tipo y número de documento</summary>
      <form id="form-doc-identidad" class="form-grid">
        ${tipoDocumentoSelectHtml("tipo_documento", e.tipo_documento || "")}
        <label>Número de documento
          <input type="text" name="documento" value="${e.documento}" />
        </label>
        <label class="ancho-completo">Lugar de expedición
          <input type="text" name="lugar_expedicion_documento" value="${e.lugar_expedicion_documento || ""}" placeholder="Ej: Barbacoas (N)" />
        </label>
        ${accionesFichaHtml()}
      </form>
      <div id="resultado-doc-identidad"></div>
      ${
        e.historial_documento.length
          ? `<details class="seccion-colapsable" style="margin-top:14px">
               <summary>Historial de documento (${e.historial_documento.length})</summary>
               <table>
                 <thead><tr><th>Tipo</th><th>Número</th><th>Vigente hasta</th></tr></thead>
                 <tbody>
                   ${e.historial_documento
                     .map(
                       (h) =>
                         `<tr><td>${h.tipo_documento || "-"}</td><td>${h.documento || "-"}</td><td>${h.vigente_hasta.slice(0, 16).replace("T", " ")}</td></tr>`
                     )
                     .join("")}
                 </tbody>
               </table>
             </details>`
          : ""
      }
    </details>

    <details class="seccion-colapsable" open>
      <summary>Documentos de matrícula</summary>
      ${documentosSeccionHtml(e.fotos)}
      ${otrosDocumentosHtml(e.fotos)}
      <details class="seccion-colapsable" style="margin-top:14px">
        <summary>📤 Subir varios documentos de este estudiante a la vez</summary>
        <p class="pendiente" style="font-size:12.5px">
          Ideal si ya escaneaste varias páginas con el celular (ej. con Adobe Scan o Microsoft 365):
          elige todos los archivos juntos y aquí les asignas la categoría a cada uno, en vez de entrar
          categoría por categoría arriba.
        </p>
        <label class="boton secundario" style="cursor:pointer; display:inline-block">
          Elegir varios archivos...
          <input type="file" id="input-subida-masiva" accept="image/*,application/pdf" multiple style="display:none" />
        </label>
        <div id="lista-subida-masiva"></div>
      </details>
      <details class="seccion-colapsable" style="margin-top:14px">
        <summary>+ Agregar otro documento (fuera de las categorías de arriba)</summary>
        <form id="form-subir-foto" class="form-grid no-imprimir">
          <label class="ancho-completo">Nombre del documento
            <input type="text" name="etiqueta_otro" placeholder="Ej: Certificado médico" required />
          </label>
          <label id="anio_lectivo_campo">Año lectivo
            <select name="anio_lectivo">${opcionesAnioLectivo(new Date().getFullYear())}</select>
          </label>
          <label>Archivo (foto, escaneo o PDF)
            <input type="file" name="archivo" accept="image/*,application/pdf" required />
          </label>
          <div class="ancho-completo check-permanente-caja">
            <label class="check-linea">
              <input type="checkbox" name="permanente" id="permanente_check" />
              Mostrar en <strong>todos los años</strong> (no repetir cada año)
            </label>
          </div>
          <div class="ancho-completo"><button type="submit" class="boton">Subir documento</button></div>
        </form>
        <div id="resultado-foto"></div>
      </details>
    </details>

    <details class="seccion-colapsable" open>
      <summary>Generar constancia de estudio</summary>
      <div class="constancia-editor">
        <form id="form-constancia" class="form-grid">
          <label>Lugar de expedición (para el texto de la constancia)
            <input type="text" name="lugar_expedicion" value="${e.lugar_expedicion_documento || ""}" required />
          </label>
          <label>Jornada
            <input type="text" name="jornada" value="Diurna" />
          </label>
          <label>Año escolar
            <input type="number" name="anio_escolar" value="${new Date().getFullYear()}" />
          </label>
          <label>Fecha de expedición
            <input type="date" name="fecha_expedicion" value="${hoy}" />
          </label>
          <label class="ancho-completo">Válido para
            <select name="proposito_select" id="proposito_select">
              ${opciones.propositos.map((p) => `<option value="${p}">${p}</option>`).join("")}
              <option value="__otro__">Otro (especificar)</option>
            </select>
          </label>
          <label class="ancho-completo" id="campo-proposito-otro" style="display:none">
            Especifica el propósito
            <input type="text" name="proposito_otro" />
          </label>
          <div class="ancho-completo"><button type="submit" class="boton">Generar constancia</button></div>
        </form>
        <div>
          <p class="pendiente" style="margin-top:0">Vista previa (aproximada, el Word/PDF real lleva el formato oficial completo)</p>
          <div id="preview-constancia"></div>
        </div>
      </div>
      <div id="resultado-constancia"></div>
    </details>
  `;

  document.getElementById("btn-volver-ficha").addEventListener("click", () => {
    vistaActual = vistaAnterior;
    render();
  });

  vincularTipoDocumentoOtro("tipo_documento");
  vincularEstadoPreviews();
  vincularBloqueoFicha();

  document.getElementById("form-datos-estudiante").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const datos = Object.fromEntries(new FormData(ev.target).entries());
    const cont = document.getElementById("resultado-datos-estudiante");
    try {
      await api(`/api/estudiantes/${fichaEstudianteId}`, {
        method: "PATCH",
        body: JSON.stringify({
          fecha_nacimiento: datos.fecha_nacimiento || null,
          genero: datos.genero || null,
          grado: Number(datos.grado),
          curso: datos.curso === "" ? null : Number(datos.curso),
          id_estud: datos.id_estud || null,
          observaciones: datos.observaciones || null,
          posible_retirado: ev.target.querySelector('[name="posible_retirado"]').checked,
        }),
      });
      cont.innerHTML = '<div class="exito-caja">Guardado.</div>';
      await renderFicha();
    } catch (err) {
      cont.innerHTML = `<div class="alerta-caja">${err.message}</div>`;
    }
  });

  document.getElementById("form-doc-identidad").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const datos = Object.fromEntries(new FormData(ev.target).entries());
    const cont = document.getElementById("resultado-doc-identidad");
    try {
      await api(`/api/estudiantes/${fichaEstudianteId}`, {
        method: "PATCH",
        body: JSON.stringify({
          tipo_documento: valorTipoDocumento(datos, "tipo_documento") || null,
          documento: datos.documento,
          lugar_expedicion_documento: datos.lugar_expedicion_documento || null,
        }),
      });
      cont.innerHTML = '<div class="exito-caja">Guardado.</div>';
      await renderFicha();
    } catch (err) {
      cont.innerHTML = `<div class="alerta-caja">${err.message}</div>`;
    }
  });

  const actualizarCampoAnioLectivo = () => {
    const esPermanente = document.getElementById("permanente_check").checked;
    document.getElementById("anio_lectivo_campo").style.display = esPermanente ? "none" : "";
  };
  document.getElementById("permanente_check").addEventListener("change", actualizarCampoAnioLectivo);
  actualizarCampoAnioLectivo();

  document.getElementById("form-subir-foto").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = new FormData(ev.target);
    form.set("etiqueta", form.get("etiqueta_otro") || "Documento");
    form.delete("etiqueta_otro");
    const cont = document.getElementById("resultado-foto");
    cont.innerHTML = "<p>Subiendo...</p>";
    try {
      await asegurarSesionFresca(); // Fase 4A': fetch crudo, no pasa por api()
      const res = await fetch(`/api/estudiantes/${fichaEstudianteId}/fotos`, { method: "POST", body: form });
      if (!res.ok) {
        const cuerpo = await res.json().catch(() => ({}));
        throw new Error(cuerpo.detail || "No se pudo subir el documento");
      }
      cont.innerHTML = "";
      await renderFicha();
    } catch (err) {
      cont.innerHTML = `<div class="alerta-caja">${err.message}</div>`;
    }
  });

  document.querySelectorAll("[data-eliminar-foto]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("¿Eliminar esta foto?")) return;
      await api(`/api/fotos/${btn.dataset.eliminarFoto}`, { method: "DELETE" });
      await renderFicha();
    });
  });

  // --- Carrusel / lista de documentos por categoría ----------------------
  const n = CATEGORIAS_DOCUMENTO.length;
  document.getElementById("doc-carrusel-prev")?.addEventListener("click", () => {
    fichaDocCategoriaIndex = (fichaDocCategoriaIndex - 1 + n) % n;
    guardarIndiceCategoria(fichaEstudianteId, fichaDocCategoriaIndex);
    renderFicha();
  });
  document.getElementById("doc-carrusel-next")?.addEventListener("click", () => {
    fichaDocCategoriaIndex = (fichaDocCategoriaIndex + 1) % n;
    guardarIndiceCategoria(fichaEstudianteId, fichaDocCategoriaIndex);
    renderFicha();
  });
  document.querySelectorAll("[data-doc-ir]").forEach((el) => {
    el.addEventListener("click", () => {
      fichaDocCategoriaIndex = Number(el.dataset.docIr);
      guardarIndiceCategoria(fichaEstudianteId, fichaDocCategoriaIndex);
      renderFicha();
    });
  });
  document.querySelectorAll("[data-doc-vista]").forEach((btn) => {
    btn.addEventListener("click", () => {
      vistaDocumentos = btn.dataset.docVista;
      guardarPreferencia("ietaba_vista_documentos", vistaDocumentos);
      renderFicha();
    });
  });
  document.getElementById("select-anio-documentos")?.addEventListener("change", (ev) => {
    fichaDocAnioSeleccionado = Number(ev.target.value);
    renderFicha();
  });

  const inputArchivoCarrusel = document.getElementById("doc-carrusel-input-archivo");
  document.querySelectorAll("[data-doc-accion]").forEach((btn) => {
    btn.addEventListener("click", () => {
      fichaDocAccionPendiente = {
        modo: btn.dataset.docAccion,
        categoria: btn.dataset.docCategoria,
        permanente: btn.dataset.docPermanente === "true",
        fotoIdAReemplazar: btn.dataset.docFotoId || null,
      };
      inputArchivoCarrusel.click();
    });
  });
  inputArchivoCarrusel.addEventListener("change", async () => {
    const archivo = inputArchivoCarrusel.files[0];
    const accion = fichaDocAccionPendiente;
    if (!archivo || !accion) return;
    try {
      await subirDocumentoCategoria(accion.categoria, accion.permanente, accion.fotoIdAReemplazar, archivo, archivo.name);
      fichaDocAccionPendiente = null;
      await renderFicha();
    } catch (err) {
      alert(err.message);
      fichaDocAccionPendiente = null;
    }
  });

  // Escáner documental (cámara -> detección -> corrección -> mejora ->
  // multipágina -> PDF): reutiliza el mismo endpoint de subida de arriba,
  // solo cambia de dónde sale el archivo.
  document.querySelectorAll("[data-doc-escanear]").forEach((btn) => {
    btn.addEventListener("click", () => {
      abrirEscanerDocumento({
        titulo: btn.dataset.docCategoria,
        onGuardar: async (archivo, nombreArchivo) => {
          await subirDocumentoCategoria(
            btn.dataset.docCategoria,
            btn.dataset.docPermanente === "true",
            btn.dataset.docFotoIdReemplazar || null,
            archivo,
            nombreArchivo
          );
          await renderFicha();
        },
      });
    });
  });

  // --- Subir varios documentos de una vez, con categoría por archivo -----
  // Si uno de los archivos es un PDF de varias páginas, en vez de tratarlo
  // como un solo bloque se ofrece elegir página por página (como en
  // ILovePDF): cada página entra a la lista por separado, sin categoría
  // asignada por defecto — la que no se le asigna categoría, se descarta.
  let archivosSubidaMasiva = [];

  function pintarListaSubidaMasiva() {
    const cont = document.getElementById("lista-subida-masiva");
    if (!archivosSubidaMasiva.length) {
      cont.innerHTML = "";
      return;
    }
    const conteoPorCategoria = {};
    archivosSubidaMasiva.forEach((item) => {
      if (item.categoria) conteoPorCategoria[item.categoria] = (conteoPorCategoria[item.categoria] || 0) + 1;
    });
    const nAsignados = archivosSubidaMasiva.filter((x) => x.categoria).length;
    const nSinAsignar = archivosSubidaMasiva.length - nAsignados;

    cont.innerHTML = `
      <table style="margin-top:10px">
        <thead><tr><th></th><th>Archivo</th><th>Categoría</th><th></th></tr></thead>
        <tbody>
          ${archivosSubidaMasiva
            .map((item, i) => {
              const nombreMostrado =
                item.tipo === "pdf-pagina" ? `${item.nombreOrigen} — pág. ${item.numeroPagina} de ${item.totalPaginas}` : item.file.name;
              return `
            <tr class="${!item.categoria ? "fila-subida-descartada" : ""}">
              <td>${
                item.previewUrl
                  ? imagenConEstadoHtml(item.previewUrl, "", "doc-preview-chico")
                  : '<span style="font-size:22px">📄</span>'
              }</td>
              <td style="font-size:12.5px; max-width:190px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap" title="${nombreMostrado}">${nombreMostrado}</td>
              <td>
                <select data-subida-categoria="${i}">
                  <option value="" ${!item.categoria ? "selected" : ""}>No incluir (descartar)</option>
                  ${CATEGORIAS_DOCUMENTO.map((c) => `<option value="${c.nombre}" ${c.nombre === item.categoria ? "selected" : ""}>${c.nombre}</option>`).join("")}
                </select>
                ${item.categoria && conteoPorCategoria[item.categoria] > 1 ? '<div class="pendiente" style="color:var(--rojo); font-size:11px">⚠ repetida con otro archivo de la lista</div>' : ""}
              </td>
              <td><button type="button" class="boton secundario boton-chico" data-subida-quitar="${i}">✕</button></td>
            </tr>`;
            })
            .join("")}
        </tbody>
      </table>
      <p class="pendiente" style="font-size:12px">
        ${nAsignados} con categoría asignada${nSinAsignar ? ` · ${nSinAsignar} sin asignar (no se van a subir)` : ""}
      </p>
      <div style="margin-top:10px">
        <button type="button" class="boton" id="btn-guardar-subida-masiva" ${nAsignados ? "" : "disabled"}>Guardar ${nAsignados} documento(s)</button>
      </div>
      <div id="resultado-subida-masiva"></div>
    `;
    vincularEstadoPreviews(cont);

    cont.querySelectorAll("[data-subida-categoria]").forEach((sel) => {
      sel.addEventListener("change", (ev) => {
        archivosSubidaMasiva[Number(sel.dataset.subidaCategoria)].categoria = ev.target.value || null;
        pintarListaSubidaMasiva();
      });
    });
    cont.querySelectorAll("[data-subida-quitar]").forEach((btn) => {
      btn.addEventListener("click", () => {
        archivosSubidaMasiva.splice(Number(btn.dataset.subidaQuitar), 1);
        pintarListaSubidaMasiva();
      });
    });

    document.getElementById("btn-guardar-subida-masiva").addEventListener("click", async () => {
      const resultado = document.getElementById("resultado-subida-masiva");
      const boton = document.getElementById("btn-guardar-subida-masiva");
      boton.disabled = true;
      const paraSubir = archivosSubidaMasiva.filter((x) => x.categoria);
      for (let i = 0; i < paraSubir.length; i++) {
        const item = paraSubir[i];
        const nombreMostrado = item.tipo === "pdf-pagina" ? `${item.nombreOrigen} pág. ${item.numeroPagina}` : item.file.name;
        resultado.innerHTML = `<p class="pendiente">Subiendo ${i + 1} de ${paraSubir.length}: ${nombreMostrado}...</p>`;
        const categoriaInfo = CATEGORIAS_DOCUMENTO.find((c) => c.nombre === item.categoria);
        try {
          let archivo, nombreArchivo;
          if (item.tipo === "pdf-pagina") {
            archivo = await renderizarPaginaPdfAImagen(item.pdfArrayBuffer, item.numeroPagina);
            nombreArchivo = `${item.nombreOrigen.replace(/\.pdf$/i, "")}_pag${item.numeroPagina}.jpg`;
          } else {
            archivo = item.file;
            nombreArchivo = item.file.name;
          }
          await subirDocumentoCategoria(item.categoria, categoriaInfo?.permanente || false, null, archivo, nombreArchivo);
        } catch (err) {
          resultado.innerHTML = `<div class="alerta-caja">Error subiendo "${nombreMostrado}": ${err.message}. Se detuvo aquí — los anteriores ya quedaron guardados, intenta de nuevo con los que faltan.</div>`;
          boton.disabled = false;
          return;
        }
      }
      archivosSubidaMasiva = [];
      await renderFicha();
    });
  }

  document.getElementById("input-subida-masiva").addEventListener("change", async () => {
    const input = document.getElementById("input-subida-masiva");
    const anio = fichaDocAnioSeleccionado ?? new Date().getFullYear();
    const archivos = Array.from(input.files || []);
    input.value = ""; // permite volver a elegir los mismos archivos si hace falta corregir algo

    for (const file of archivos) {
      if (file.type === "application/pdf") {
        try {
          const buffer = await file.arrayBuffer();
          const paginas = await paginasDePdfComoMiniaturas(buffer);
          paginas.forEach((p) => {
            archivosSubidaMasiva.push({
              tipo: "pdf-pagina",
              nombreOrigen: file.name,
              numeroPagina: p.numero,
              totalPaginas: paginas.length,
              pdfArrayBuffer: buffer,
              categoria: null, // sin elegir a propósito: si no se asigna, se descarta
              previewUrl: p.previewUrl,
            });
          });
          pintarListaSubidaMasiva();
          continue;
        } catch (err) {
          // El navegador no pudo leer el PDF página por página (formato raro,
          // archivo dañado): se sube completo como antes, sin dividir.
        }
      }
      const yaUsadas = new Set(archivosSubidaMasiva.map((x) => x.categoria).filter(Boolean));
      const faltantes = categoriasFaltantesOrdenadas(e.fotos, anio).filter((c) => !yaUsadas.has(c.nombre));
      const sugerida = faltantes[0] || null;
      archivosSubidaMasiva.push({
        tipo: "imagen",
        file,
        categoria: sugerida ? sugerida.nombre : null,
        previewUrl: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
      });
    }
    pintarListaSubidaMasiva();
  });

  const formConstancia = document.getElementById("form-constancia");

  const actualizarPreview = () => {
    const datos = Object.fromEntries(new FormData(formConstancia).entries());
    datos.proposito = datos.proposito_select === "__otro__" ? datos.proposito_otro : datos.proposito_select;
    document.getElementById("preview-constancia").innerHTML = previsualizarConstancia(e, nombreCompleto, datos);
  };

  document.getElementById("proposito_select").addEventListener("change", (ev) => {
    document.getElementById("campo-proposito-otro").style.display =
      ev.target.value === "__otro__" ? "" : "none";
    actualizarPreview();
  });
  formConstancia.addEventListener("input", actualizarPreview);
  actualizarPreview();

  formConstancia.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const datos = Object.fromEntries(new FormData(ev.target).entries());
    const proposito = datos.proposito_select === "__otro__" ? datos.proposito_otro : datos.proposito_select;
    const cont = document.getElementById("resultado-constancia");
    cont.innerHTML = "<p>Generando (la conversión a PDF puede tardar unos segundos)...</p>";
    try {
      const registro = await api("/api/certificados/constancia", {
        method: "POST",
        body: JSON.stringify({
          estudiante_id: fichaEstudianteId,
          lugar_expedicion: datos.lugar_expedicion,
          jornada: datos.jornada,
          anio_escolar: Number(datos.anio_escolar),
          fecha_expedicion: datos.fecha_expedicion,
          proposito,
        }),
      });
      cont.innerHTML = `
        <div class="exito-caja">
          Constancia generada y guardada en el registro.
          <a class="boton secundario" href="/api/certificados/${registro.id}/archivo?formato=docx">Descargar Word</a>
          ${
            registro.archivo_pdf
              ? `<a class="boton secundario" href="/api/certificados/${registro.id}/archivo?formato=pdf">Descargar PDF</a>`
              : '<span class="pendiente">(no se pudo generar PDF)</span>'
          }
        </div>`;
    } catch (err) {
      cont.innerHTML = `<div class="alerta-caja">${err.message}</div>`;
    }
  });
}
