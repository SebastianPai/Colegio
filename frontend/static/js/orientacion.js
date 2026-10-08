// --- Vista: Orientación/Psicología ------------------------------------------
// Tres secciones (botones del sidebar, prefijo or-vista): Bandeja de
// observaciones confidenciales, Orientación por grado y por estudiante. Las
// dos últimas trabajan sobre tres capas separadas (ver backend/app/models.py):
// DiagnosticoGrado/DiagnosticoMencion son la fotografía importada del Excel
// (solo lectura, nunca se edita); Caso es el trabajo ACTIVO de orientación
// sobre un estudiante puntual (nace de una mención o se crea a mano);
// CasoSeguimiento es el historial de un caso.
//
// "Por grado" parte de la MATRÍCULA real (GET /api/diagnosticos/grupos), no
// solo de las hojas del Excel: un grupo sin hoja (ej. 6-6) igual se trabaja.
// Formularios (caso, seguimiento, agregar/registrar estudiante) van en un
// modal propio (#modal-orientacion). Prefijos CSS: dx- (diagnóstico, ya
// existente), ox- (layout de esta pantalla).

let orVista = "bandeja"; // bandeja | diagnostico-grados | diagnostico-estudiante

let orEstado = "abierta";
let orTipo = "";
let orAbierta = null; // id de la observación con el detalle desplegado

// --- Por grado ---
let orSedes = null; // sedes del colegio (pertenece_ietaba)
let orSedeId = null;
let orFiltroGrupos = ""; // texto de búsqueda en la lista de grupos
let orChipGrupos = "todos"; // todos | casos | revisar | sin_diag
let orVistaLanding = "grupos"; // grupos | generales
let orCampoGeneral = "tematicas_trabajar"; // campo de OR_GENERALES que se compara entre grupos, o "todo"
let orFiltroGenerales = "";
let orGradoSel = null; // {sede_id, grado, curso} del grupo abierto (core.js lo pone en null al navegar)
let orGrupoDetalle = null; // caché de /api/diagnosticos/grupos/{sede}/{grado}
let orGrupoTab = "estudiantes"; // estudiantes | diagnostico | casos | revision
let orDiagVersionId = null; // versión del diagnóstico elegida (null = la vigente)
let orDiagDetalle = null; // caché de /api/diagnosticos/grados/{id}
let orFiltroEstGrupo = ""; // búsqueda en la pestaña Estudiantes
let orChipEstGrupo = "todos"; // todos | situaciones | casos | sin_novedad
let orChipCasos = "activos"; // activos | cerrados | todos
let orGradoVinculando = null; // id de la mención con el buscador de estudiante abierto
let orFiltroSituaciones = ""; // texto de búsqueda en "Situaciones de estudiantes"
let orSituacionesExpandidas = new Set(); // claves de tarjetas de estudiante expandidas

// --- Casos (compartido entre grado y estudiante) ---
let orCasosExpandidos = new Set(); // ids de casos con el detalle desplegado
let orCasosDetalle = new Map(); // caché id -> CasoDetalle (se carga al expandir)

// --- Por estudiante ---
let orEstudianteTexto = "";
let orEstudianteSel = null; // id del estudiante con el perfil abierto (core.js lo pone en null al navegar)
let orEstudianteResumen = null; // caché de /api/diagnosticos/estudiantes/{id}
let orPerfilDesdeGrupo = null; // nombre del grupo si se llegó al perfil desde "Por grado" (migas de pan)

// El listado de estudiantes no siempre trae nombre_completo armado (ver
// schemas.Estudiante): se arma igual que en el resto del frontend
// (estudiantes.js, reportes.js...). Si ya viene armado (ej. desde una
// mención), se usa tal cual.
function orNombreEstudiante(e) {
  if (e.nombre_completo) return e.nombre_completo;
  return `${e.primer_nombre} ${e.segundo_nombre || ""} ${e.primer_apellido} ${e.segundo_apellido || ""}`
    .replace(/\s+/g, " ")
    .trim();
}

async function renderOrientacion() {
  if (typeof modulosSistema !== "undefined" && modulosSistema.orientacion === false) {
    app.innerHTML = `<div class="ox-vacio"><p><b>El módulo de Orientación está desactivado.</b></p>
      <p>No se borró nada: el administrador puede volver a activarlo en Usuarios → Módulos del sistema.</p></div>`;
    return;
  }
  if (orVista === "diagnostico-grados") return renderOrPorGrado();
  if (orVista === "diagnostico-estudiante") return renderOrPorEstudiante();
  return renderOrBandeja();
}

// --- Descarga/impresión de PDF: mismo criterio que reportes.js (fetch para
// poder mostrar un error legible si algo falla, en vez de una pestaña en
// blanco), pero como respuesta "inline" se abre para imprimir, no se baja. ---
// `boton` (opcional) muestra "Generando..." mientras tanto: el informe
// general tarda unos segundos. Si el navegador bloquea la pestaña nueva (pasa
// cuando se abre después de esperar el fetch), el PDF se descarga igual.
async function orAbrirPdf(url, boton) {
  const textoOriginal = boton ? boton.textContent : "";
  if (boton) {
    boton.disabled = true;
    boton.textContent = "Generando…";
  }
  try {
    await asegurarSesionFresca();
    let res = await fetch(url);
    if (res.status === 401 && (await _intentarRefresh())) res = await fetch(url);
    if (!res.ok) {
      const detalle = await res.json().catch(() => ({}));
      throw new Error(detalle.detail || `Error ${res.status} generando el PDF`);
    }
    const objectUrl = URL.createObjectURL(await res.blob());
    const ventana = window.open(objectUrl, "_blank");
    if (!ventana) {
      const nombre = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") || "");
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = nombre ? nombre[1] : "informe_orientacion.pdf";
      document.body.appendChild(a);
      a.click();
      a.remove();
      orAviso("El navegador bloqueó la pestaña nueva: el informe se descargó.");
    }
    setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
  } catch (e) {
    orAviso(e.message || "No se pudo generar el PDF.", "error");
  } finally {
    if (boton) {
      boton.disabled = false;
      boton.textContent = textoOriginal;
    }
  }
}

// =============================================================================
// Bandeja de observaciones confidenciales
// =============================================================================

async function renderOrBandeja() {
  app.innerHTML = "<p>Cargando bandeja...</p>";
  let items;
  try {
    const q = new URLSearchParams();
    if (orEstado) q.set("estado", orEstado);
    if (orTipo) q.set("tipo", orTipo);
    items = await api(`/api/orientacion/observaciones?${q.toString()}`);
  } catch (e) {
    app.innerHTML = `<p class="alerta-caja">${esc(
      e.status === 403 ? "No tienes permiso para ver la bandeja de orientación." : "No se pudo cargar: " + e.message
    )}</p>`;
    return;
  }
  orPintarBandeja(items);
}

function orPintarBandeja(items) {
  const TIPOS = { academica: "Académica", convivencia: "Convivencia", general: "General", psicologia: "Remisión a psicología" };

  const tarjetas = items
    .map((o) => {
      const claseTipo = o.tipo === "psicologia" ? "alerta" : o.tipo === "convivencia" ? "proceso" : o.tipo === "academica" ? "" : "naranja";
      const abierta = orAbierta === o.id;
      const seguimientos = (o.seguimientos || [])
        .map(
          (s) => `
          <div class="dk-seg-item">
            <span class="dk-obs-fecha">${esc(s.autor_nombre)} · ${esc(instanteUtcDesdeApi(s.creado_en)?.toLocaleString("es-CO") || "")}</span>
            <p>${esc(s.nota)}</p>
          </div>`
        )
        .join("");
      return `
        <div class="dk-obs-item dk-obs-confidencial">
          <div class="dk-obs-cabecera">
            <span class="badge-estado ${claseTipo}">${esc(TIPOS[o.tipo] || o.tipo)}</span>
            <span class="badge-estado ${o.estado === "abierta" ? "alerta" : o.estado === "atendida" ? "proceso" : "ok"}">${esc(o.estado)}</span>
            <span class="dk-obs-fecha">${esc(o.fecha)} · ${esc(o.autor_nombre)}</span>
          </div>
          <strong>${esc(o.estudiante_nombre)}</strong> <span class="dk-obs-fecha">${esc(o.estudiante_documento)} · ${esc(o.nombre_grupo)}</span>
          <p>${esc(o.detalle)}</p>
          <button type="button" class="boton-texto-chico" data-or-toggle="${o.id}">${abierta ? "Ocultar seguimiento" : `Seguimiento (${(o.seguimientos || []).length})`}</button>
          ${
            abierta
              ? `
              <div class="dk-seg-lista">${seguimientos || '<p class="subtitulo-pagina">Todavía no hay seguimiento.</p>'}</div>
              <form class="dk-obs-form" data-or-seguimiento="${o.id}">
                <textarea name="nota" rows="2" placeholder="Agregar nota de seguimiento..." required></textarea>
                <div class="dk-obs-acciones">
                  <button type="submit" class="boton dk-boton-secundario">Agregar nota</button>
                  ${o.estado !== "atendida" ? `<button type="button" class="boton-texto-chico" data-or-estado="${o.id}|atendida">Marcar atendida</button>` : ""}
                  ${o.estado !== "cerrada" ? `<button type="button" class="boton-texto-chico" data-or-estado="${o.id}|cerrada">Cerrar caso</button>` : ""}
                </div>
              </form>`
              : ""
          }
        </div>`;
    })
    .join("");

  app.innerHTML = `
    <h2>Orientación / Psicología</h2>
    <p class="subtitulo-pagina">Remisiones y observaciones confidenciales.</p>
    <div class="toolbar">
      <select id="or-estado">
        <option value="abierta" ${orEstado === "abierta" ? "selected" : ""}>Abiertas</option>
        <option value="atendida" ${orEstado === "atendida" ? "selected" : ""}>Atendidas</option>
        <option value="cerrada" ${orEstado === "cerrada" ? "selected" : ""}>Cerradas</option>
        <option value="" ${orEstado === "" ? "selected" : ""}>Todas</option>
      </select>
      <select id="or-tipo">
        <option value="">Todos los tipos</option>
        <option value="psicologia" ${orTipo === "psicologia" ? "selected" : ""}>Remisión a psicología</option>
        <option value="academica" ${orTipo === "academica" ? "selected" : ""}>Académica</option>
        <option value="convivencia" ${orTipo === "convivencia" ? "selected" : ""}>Convivencia</option>
        <option value="general" ${orTipo === "general" ? "selected" : ""}>General</option>
      </select>
    </div>
    ${items.length ? `<div class="dk-obs-lista">${tarjetas}</div>` : '<p class="exito-caja">No hay nada en este filtro.</p>'}`;

  document.getElementById("or-estado").addEventListener("change", (ev) => {
    orEstado = ev.target.value;
    renderOrBandeja();
  });
  document.getElementById("or-tipo").addEventListener("change", (ev) => {
    orTipo = ev.target.value;
    renderOrBandeja();
  });
  document.querySelectorAll("[data-or-toggle]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const id = Number(btn.dataset.orToggle);
      orAbierta = orAbierta === id ? null : id;
      orPintarBandeja(items);
    })
  );
  document.querySelectorAll("[data-or-seguimiento]").forEach((form) =>
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const id = form.dataset.orSeguimiento;
      const nota = String(new FormData(form).get("nota") || "").trim();
      if (!nota) return;
      try {
        await api(`/api/orientacion/observaciones/${id}/seguimiento`, { method: "POST", body: JSON.stringify({ nota }) });
        renderOrBandeja();
      } catch (e) {
        alert(e.message || "No se pudo agregar el seguimiento.");
      }
    })
  );
  document.querySelectorAll("[data-or-estado]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const [id, estado] = btn.dataset.orEstado.split("|");
      try {
        await api(`/api/orientacion/observaciones/${id}/estado`, { method: "PATCH", body: JSON.stringify({ estado }) });
        renderOrBandeja();
      } catch (e) {
        alert(e.message || "No se pudo cambiar el estado.");
      }
    })
  );
}

// =============================================================================
// Vocabulario compartido (menciones del Excel + casos de orientación)
// =============================================================================

// Categorías de las MENCIONES que el sistema detecta solo del Excel
// (DiagnosticoMencion) — de solo lectura, nunca se crean desde la app.
const OR_CATEGORIAS = {
  no_asiste: "No asiste",
  intermitencia: "Intermitencia",
  desplazado: "Desplazado",
  embarazada: "Embarazada",
  victima_conflicto: "Víctima de conflicto armado",
  dificultad_academica: "Dificultad académica",
  dificultad_comportamiento: "Dificultad de comportamiento",
  llamado_atencion: "Llamado de atención",
  salud: "Salud",
};

// Tono del chip de cada categoría: asistencia (ámbar), riesgo (rojo),
// salud/embarazo (rosa), académico (azul), comportamiento (violeta).
const OR_CATEGORIA_TONO = {
  no_asiste: "ambar", intermitencia: "ambar",
  desplazado: "rojo", victima_conflicto: "rojo",
  embarazada: "rosa", salud: "rosa",
  dificultad_academica: "azul",
  dificultad_comportamiento: "violeta", llamado_atencion: "violeta",
};

// Tipos de CASO (trabajo activo de orientación) — deben calzar con
// crud.CASO_TIPOS en el backend.
const OR_CASO_TIPOS = {
  academica: "Académico",
  comportamiento: "Comportamiento",
  inasistencia: "Inasistencia",
  intermitencia: "Intermitencia",
  familiar: "Familiar",
  salud: "Salud",
  convivencia: "Convivencia",
  orientacion: "Orientación",
  riesgo: "Riesgo",
  otra: "Otra",
};

const OR_CASO_ESTADOS = { abierto: "Abierto", en_seguimiento: "En seguimiento", cerrado: "Cerrado" };
const OR_CASO_ESTADO_CLASE = { abierto: "alerta", en_seguimiento: "proceso", cerrado: "ok" };

// Categoría detectada en el Excel -> tipo de caso sugerido al "Abrir caso"
// (ella la ve y puede cambiarla en el formulario antes de guardar).
const OR_CATEGORIA_A_TIPO_CASO = {
  no_asiste: "inasistencia", intermitencia: "intermitencia", desplazado: "riesgo",
  embarazada: "salud", victima_conflicto: "riesgo", dificultad_academica: "academica",
  dificultad_comportamiento: "comportamiento", llamado_atencion: "comportamiento", salud: "salud",
};

// Sugerencias para "Tipo de atención" de un seguimiento (texto libre igual).
const OR_TIPOS_ATENCION = [
  "Entrevista con el estudiante", "Entrevista con el acudiente", "Llamada telefónica",
  "Visita domiciliaria", "Reunión con el director de grupo", "Remisión externa", "Taller grupal",
];

// Cada sección del diagnóstico es un bloque visualmente independiente. La
// info general, las situaciones de estudiantes y el seguimiento se arman
// aparte porque no son un solo campo de texto; el resto sigue este mapeo
// directo campo -> título de sección.
// Lo GENERAL que reporta el director de cada grupo (no de un estudiante):
// se muestra SIEMPRE, con "sin respuesta" si quedó en blanco en el Excel —
// antes, un campo vacío simplemente no aparecía y parecía que faltaba info.
const OR_GENERALES = [
  ["Temáticas para trabajar con los estudiantes", "tematicas_trabajar", "list-checks"],
  ["Estrategias para solucionar conflictos", "estrategias_conflicto", "handshake"],
  ["Estrategias para fortalecer el aprendizaje", "estrategias_aprendizaje", "lightbulb"],
  ["Resguardos que se atienden", "resguardos_atendidos", "map-pin"],
  ["Recomendaciones de los docentes", "recomendaciones_docentes", "message-square"],
  ["Orientación que se ha brindado", "orientacion_brindada", "compass"],
  ["Acompañamiento de los padres de familia", "acompanamiento_padres", "users"],
];

function orGeneralesHtml(d) {
  const respondidos = OR_GENERALES.filter(([, c]) => (d[c] || "").trim()).length;
  return `
    <section class="ox-seccion">
      <header class="ox-seccion-cab"><h3 class="ox-h3">${icono("clipboard-list")}Lo que se trabaja con el grupo</h3>
        <span class="ox-tenue">${respondidos} de ${OR_GENERALES.length} respondidos por el director de grupo</span></header>
      <div class="ox-generales">
        ${OR_GENERALES.map(([titulo, campo, ic]) => {
          const v = (d[campo] || "").trim();
          return `<article class="ox-general${v ? "" : " ox-general-vacio"}">
            <h4>${icono(ic)}${esc(titulo)}</h4>
            ${v ? `<p>${esc(v)}</p>` : '<p class="ox-tenue">Sin respuesta del director de grupo en el diagnóstico.</p>'}
          </article>`;
        }).join("")}
      </div>
    </section>`;
}

const OR_SECCIONES = [
  ["Asistencia e inasistencia", "no_asisten_texto"],
  ["Dificultades académicas", "dificultades_academicas"],
  ["Dificultades de comportamiento", "dificultades_comportamiento"],
  ["Acompañamiento familiar", "acompanamiento_padres"],
  ["Situaciones de salud", "problemas_salud"],
  ["Temáticas para trabajar", "tematicas_trabajar"],
  ["Estrategias para fortalecer el aprendizaje", "estrategias_aprendizaje"],
  ["Estrategias para solucionar conflictos", "estrategias_conflicto"],
  ["Resguardos atendidos", "resguardos_atendidos"],
  ["Recomendaciones docentes", "recomendaciones_docentes"],
  ["Estudiantes con llamados de atención", "llamados_atencion"],
  ["Estudiantes que han recibido orientación", "orientacion_brindada"],
  ["Transporte escolar", "transporte_escolar"],
  ["Observaciones generales", "observaciones_generales"],
];

const OR_NIVELES = [
  ["Preescolar", (g) => g === 0],
  ["Básica primaria", (g) => g >= 1 && g <= 5],
  ["Básica secundaria", (g) => g >= 6 && g <= 9],
  ["Media", (g) => g >= 10],
];

// =============================================================================
// Utilidades de presentación
// =============================================================================

function orCategoriaTexto(categoria) {
  return OR_CATEGORIAS[categoria] || OR_CASO_TIPOS[categoria] || categoria;
}

function orChipCategoria(categoria) {
  return `<span class="ox-chip ox-tono-${OR_CATEGORIA_TONO[categoria] || "gris"}">${esc(orCategoriaTexto(categoria))}</span>`;
}

function orFechaLarga(iso) {
  if (!iso) return null;
  const f = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(f.getTime())) return iso;
  return f.toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });
}

function orFechaCorta(iso) {
  if (!iso) return "";
  const f = new Date(`${iso}T00:00:00`);
  return Number.isNaN(f.getTime()) ? iso : f.toLocaleDateString("es-CO", { day: "numeric", month: "short", year: "numeric" });
}

function orDiasHasta(iso) {
  const hoy = new Date(`${fechaColombiaISO()}T00:00:00`);
  return Math.round((new Date(`${iso}T00:00:00`) - hoy) / 86400000);
}

function orSumarDias(dias) {
  const f = new Date(`${fechaColombiaISO()}T00:00:00`);
  f.setDate(f.getDate() + dias);
  return `${f.getFullYear()}-${String(f.getMonth() + 1).padStart(2, "0")}-${String(f.getDate()).padStart(2, "0")}`;
}

// "Vencido hace 3 días" / "Hoy" / "En 5 días", con la clase de tono.
function orProximoHtml(iso) {
  if (!iso) return '<span class="ox-tenue">—</span>';
  const d = orDiasHasta(iso);
  const texto = d < 0 ? `Vencido hace ${-d} día${d === -1 ? "" : "s"}` : d === 0 ? "Hoy" : d === 1 ? "Mañana" : `En ${d} días`;
  const clase = d < 0 ? "ox-vencido" : d <= 2 ? "ox-pronto" : "ox-tenue";
  return `<span class="${clase}" title="${esc(orFechaLarga(iso))}">${texto}</span>`;
}

function orIniciales(nombre) {
  const p = String(nombre || "").trim().split(/\s+/).filter(Boolean);
  if (!p.length) return "?";
  const apellido = p.length > 2 ? p[p.length - 2] : p[1] || "";
  return (p[0][0] + (apellido[0] || "")).toUpperCase();
}

function orAvatar(nombre, genero, grande) {
  const tono = genero === "F" ? "f" : genero === "M" ? "m" : "n";
  return `<span class="ox-avatar ox-avatar-${tono}${grande ? " ox-avatar-grande" : ""}" aria-hidden="true">${esc(orIniciales(nombre))}</span>`;
}

function orEdad(isoNacimiento) {
  if (!isoNacimiento) return null;
  const n = new Date(`${isoNacimiento}T00:00:00`);
  const hoy = new Date(`${fechaColombiaISO()}T00:00:00`);
  let edad = hoy.getFullYear() - n.getFullYear();
  if (hoy.getMonth() < n.getMonth() || (hoy.getMonth() === n.getMonth() && hoy.getDate() < n.getDate())) edad--;
  return edad >= 0 && edad < 100 ? edad : null;
}

function orCodigoGrupo(g) {
  const base = g.grado === 0 ? "Pre" : String(g.grado);
  return g.curso ? `${base}-${g.curso}` : base;
}

function orKpi(valor, etiqueta, tono) {
  return `<div class="ox-kpi${tono ? ` ox-kpi-${tono}` : ""}"><b>${valor}</b><span>${esc(etiqueta)}</span></div>`;
}

function orChips(nombre, opciones, actual) {
  return `<div class="ox-chips" role="group">${opciones
    .map(
      ([valor, texto, n]) =>
        `<button type="button" class="ox-chip-filtro${actual === valor ? " activo" : ""}" data-${nombre}="${valor}" aria-pressed="${actual === valor}">${esc(texto)}${n !== undefined ? ` <span>${n}</span>` : ""}</button>`
    )
    .join("")}</div>`;
}

function orCargandoHtml(texto) {
  return `<div class="ox-cargando"><span class="ox-spinner"></span>${esc(texto)}</div>`;
}

function orErrorHtml(e, sinPermiso) {
  return `<p class="alerta-caja">${esc(e.status === 403 ? sinPermiso : "No se pudo cargar: " + e.message)}</p>`;
}

// Marca en el sidebar el botón de la sub-vista actual cuando se cambia de
// vista desde dentro de la pantalla (ej. "Ver perfil" desde un grupo).
function orMarcarTab() {
  document.querySelectorAll('[data-vista="orientacion"]').forEach((t) => t.classList.toggle("activo", t.dataset.orVista === orVista));
}

// Aviso breve abajo a la derecha (confirmación de guardado o error).
function orAviso(texto, tipo) {
  document.getElementById("ox-aviso")?.remove();
  const el = document.createElement("div");
  el.id = "ox-aviso";
  el.className = `ox-aviso${tipo === "error" ? " ox-aviso-error" : ""}`;
  el.setAttribute("role", "status");
  el.textContent = texto;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// =============================================================================
// Modal propio de orientación
// =============================================================================

function orMontarModal(titulo, cuerpoHtml, opciones) {
  orCerrarModal();
  const cont = document.createElement("div");
  cont.id = "modal-orientacion";
  cont.innerHTML = `
    <div class="modal-fondo">
      <div class="modal-caja ox-modal${opciones && opciones.ancho ? " ox-modal-ancho" : ""}" role="dialog" aria-modal="true">
        <header class="est-modal-head">
          <h3 data-or-modal-titulo></h3>
          <button type="button" class="est-visor-cerrar" data-or-cerrar-modal aria-label="Cerrar"></button>
        </header>
        <div data-or-modal-cuerpo></div>
      </div>
    </div>`;
  cont.querySelector("[data-or-modal-titulo]").textContent = titulo;
  cont.querySelector("[data-or-modal-cuerpo]").innerHTML = cuerpoHtml;
  document.body.appendChild(cont);
  cont.querySelector("[data-or-cerrar-modal]").addEventListener("click", orCerrarModal);
  cont.querySelector(".modal-fondo").addEventListener("mousedown", (ev) => {
    if (ev.target.classList.contains("modal-fondo")) orCerrarModal();
  });
  return cont;
}

function orModalCuerpo(titulo, html) {
  const cont = document.getElementById("modal-orientacion");
  if (!cont) return null;
  cont.querySelector("[data-or-modal-titulo]").textContent = titulo;
  cont.querySelector("[data-or-modal-cuerpo]").innerHTML = html;
  return cont;
}

function orCerrarModal() {
  document.getElementById("modal-orientacion")?.remove();
}

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") orCerrarModal();
});

function orErrorModal(cont, mensaje) {
  const caja = cont.querySelector("[data-or-modal-error]");
  if (caja) caja.innerHTML = `<div class="alerta-caja">${esc(mensaje)}</div>`;
  else orAviso(mensaje, "error");
}

// Botones "+1 semana / +15 días / +1 mes" junto a un campo de fecha.
function orAtajosFechaHtml(nombreCampo) {
  return `<span class="ox-atajos">${[
    [7, "+1 semana"], [15, "+15 días"], [30, "+1 mes"],
  ]
    .map(([d, t]) => `<button type="button" class="ox-atajo" data-or-atajo="${nombreCampo}|${d}">${t}</button>`)
    .join("")}</span>`;
}

function orWireAtajosFecha(raiz) {
  raiz.querySelectorAll("[data-or-atajo]").forEach((b) =>
    b.addEventListener("click", () => {
      const [campo, dias] = b.dataset.orAtajo.split("|");
      raiz.querySelector(`[name="${campo}"]`).value = orSumarDias(Number(dias));
    })
  );
}

// =============================================================================
// Flujo "Agregar estudiante al seguimiento" / "Nuevo caso"
// =============================================================================
// Un solo flujo para todo lo que abre un caso:
//   elegir estudiante (del grupo o de todo el colegio)
//     └─ ¿no aparece? registrar estudiante nuevo (solo con estudiantes.crear)
//   → datos del caso → guardar.
// ctx = { estudiante?, prefill?, grupo?: GrupoOrientacionDetalle, alGuardar(caso) }

function orAbrirFlujoCaso(ctx) {
  orMontarModal("", "", { ancho: true });
  if (ctx.estudiante) orPasoCaso(ctx);
  else orPasoElegir(ctx);
}

function orPasoElegir(ctx) {
  const grupo = ctx.grupo;
  let ambito = grupo ? "grupo" : "colegio";
  const puedeRegistrar = tienePermiso("estudiantes.crear");
  const cont = orModalCuerpo(
    "Agregar estudiante al seguimiento",
    `
    <p class="ox-ayuda">Elige a quién le vas a abrir un caso. Puede ser cualquier estudiante, aunque el diagnóstico del director de grupo no lo mencione.</p>
    ${grupo ? orChips("or-ambito", [["grupo", `En ${grupo.grado_nombre}`], ["colegio", "Todo el colegio"]], ambito) : ""}
    <div class="ox-buscador ox-buscador-modal">
      <input type="search" data-or-elegir-buscar placeholder="Nombre o número de documento..." autocomplete="off" aria-label="Buscar estudiante" />
    </div>
    <div class="ox-picker" data-or-elegir-lista></div>
    <div class="ox-picker-pie">
      ${
        puedeRegistrar
          ? `¿Es un estudiante nuevo que todavía no está en el sistema? <button type="button" class="boton-texto-chico" data-or-ir-registrar>Registrar estudiante nuevo</button>`
          : "¿Es un estudiante nuevo que todavía no aparece en ningún grupo? Pide a secretaría que lo matricule y luego vuelve a buscarlo aquí."
      }
    </div>`
  );
  const input = cont.querySelector("[data-or-elegir-buscar]");
  const lista = cont.querySelector("[data-or-elegir-lista]");
  let timer = null;
  let resultados = [];

  const itemHtml = (e) => {
    const situaciones = e.total_situaciones ? `<span class="ox-chip ox-tono-gris">${e.total_situaciones} en el diagnóstico</span>` : "";
    const casos = e.casos_activos ? `<span class="ox-chip ox-tono-ambar">${e.casos_activos} caso${e.casos_activos === 1 ? "" : "s"} activo${e.casos_activos === 1 ? "" : "s"}</span>` : "";
    return `
      <button type="button" class="ox-picker-item" data-or-elegido="${e.id}">
        ${orAvatar(orNombreEstudiante(e), e.genero)}
        <span class="ox-picker-texto"><strong>${esc(orNombreEstudiante(e))}</strong><span>${esc(e.documento)} · ${esc(e.grupo || "")}</span></span>
        <span class="ox-picker-badges">${situaciones}${casos}</span>
      </button>`;
  };

  const pintar = () => {
    if (ambito === "grupo") {
      const f = normalizarTexto(input.value.trim());
      resultados = grupo.estudiantes.filter((e) => e.en_matricula_del_grupo && (!f || normalizarTexto(`${e.nombre_completo} ${e.documento}`).includes(f)));
      lista.innerHTML = resultados.length
        ? resultados.map(itemHtml).join("")
        : `<p class="ox-vacio-chico">Nadie en ${esc(grupo.grado_nombre)} coincide. Prueba en "Todo el colegio".</p>`;
    } else {
      lista.innerHTML = resultados.length
        ? resultados.map(itemHtml).join("")
        : `<p class="ox-vacio-chico">${input.value.trim().length < 3 ? "Escribe al menos 3 letras del nombre o del documento." : "Sin resultados."}</p>`;
    }
    lista.querySelectorAll("[data-or-elegido]").forEach((b) =>
      b.addEventListener("click", () => {
        const e = resultados.find((x) => x.id === Number(b.dataset.orElegido));
        orPasoCaso({ ...ctx, estudiante: e, desdeElegir: true });
      })
    );
  };

  const buscarColegio = () => {
    clearTimeout(timer);
    const texto = input.value.trim();
    if (texto.length < 3) {
      resultados = [];
      pintar();
      return;
    }
    lista.innerHTML = orCargandoHtml("Buscando...");
    timer = setTimeout(async () => {
      try {
        const r = await api(`/api/estudiantes/pagina?q=${encodeURIComponent(texto)}&por_pagina=12`);
        if (ambito !== "colegio" || input.value.trim() !== texto) return;
        resultados = r.items;
      } catch {
        resultados = [];
      }
      pintar();
    }, 300);
  };

  input.addEventListener("input", () => (ambito === "grupo" ? pintar() : buscarColegio()));
  cont.querySelectorAll("[data-or-ambito]").forEach((b) =>
    b.addEventListener("click", () => {
      ambito = b.dataset.orAmbito;
      cont.querySelectorAll("[data-or-ambito]").forEach((x) => {
        x.classList.toggle("activo", x === b);
        x.setAttribute("aria-pressed", x === b);
      });
      resultados = [];
      ambito === "grupo" ? pintar() : buscarColegio();
      input.focus();
    })
  );
  cont.querySelector("[data-or-ir-registrar]")?.addEventListener("click", () => orPasoRegistrar(ctx));
  pintar();
  input.focus();
}

function orPasoCaso(ctx) {
  const e = ctx.estudiante;
  const p = ctx.prefill || {};
  const opcionesTipo = Object.entries(OR_CASO_TIPOS)
    .map(([k, v]) => `<option value="${k}" ${p.tipo === k ? "selected" : ""}>${esc(v)}</option>`)
    .join("");
  const cont = orModalCuerpo(
    p.mencionOrigenId ? "Abrir caso desde el diagnóstico" : "Nuevo caso de orientación",
    `
    ${ctx.aviso ? `<div class="exito-caja ox-mb">${esc(ctx.aviso)}</div>` : ""}
    <div class="ox-estudiante-elegido">
      ${orAvatar(orNombreEstudiante(e), e.genero)}
      <span class="ox-picker-texto"><strong>${esc(orNombreEstudiante(e))}</strong><span>${esc(e.documento || "")}${e.grupo ? ` · ${esc(e.grupo)}` : ""}</span></span>
      ${ctx.desdeElegir ? '<button type="button" class="boton-texto-chico" data-or-cambiar-est>Cambiar</button>' : ""}
    </div>
    ${p.mencionOrigenId ? `<blockquote class="ox-cita"><span>Del diagnóstico del director de grupo</span>${esc(p.descripcion || "")}</blockquote>` : ""}
    <form class="ox-form" data-or-form-caso novalidate>
      <div class="ox-form-grid">
        <label>Tipo de caso <select name="tipo">${opcionesTipo}</select></label>
        <label>Fecha de apertura <input type="date" name="fecha_apertura" value="${fechaColombiaISO()}" max="${fechaColombiaISO()}" /></label>
        <label class="ox-ancho">Motivo <span class="ox-opcional">opcional</span>
          <input type="text" name="titulo" maxlength="150" value="${esc(p.titulo || "")}" placeholder="Ej. Inasistencia reiterada desde marzo" /></label>
        <label class="ox-ancho">Descripción de la situación <span class="ox-req">*</span>
          <textarea name="descripcion" rows="4" placeholder="¿Qué está pasando? ¿Desde cuándo? ¿Quién lo reporta?">${esc(p.descripcion || "")}</textarea></label>
        <label class="ox-ancho">Acciones ya realizadas <span class="ox-opcional">opcional</span>
          <textarea name="acciones" rows="2"></textarea></label>
        <label class="ox-ancho">Observaciones <span class="ox-opcional">opcional</span>
          <textarea name="observaciones" rows="2"></textarea></label>
        <label class="ox-ancho">Próximo seguimiento <span class="ox-opcional">opcional</span>
          <span class="ox-fecha-con-atajos"><input type="date" name="proximo_seguimiento" min="${fechaColombiaISO()}" />${orAtajosFechaHtml("proximo_seguimiento")}</span></label>
      </div>
      <div data-or-modal-error></div>
      <div class="modal-acciones">
        <button type="button" class="boton secundario" data-or-cancelar>Cancelar</button>
        <button type="submit" class="boton">Abrir caso</button>
      </div>
    </form>`
  );
  const form = cont.querySelector("[data-or-form-caso]");
  orWireAtajosFecha(form);
  cont.querySelector("[data-or-cambiar-est]")?.addEventListener("click", () => orPasoElegir(ctx));
  cont.querySelector("[data-or-cancelar]").addEventListener("click", orCerrarModal);
  form.querySelector('[name="descripcion"]').focus();
  form.querySelector('[name="descripcion"]').addEventListener("input", () => {
    cont.querySelector("[data-or-modal-error]").innerHTML = "";
  });
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const datos = new FormData(form);
    const descripcion = String(datos.get("descripcion") || "").trim();
    if (!descripcion) {
      orErrorModal(cont, "Describe la situación: es lo único obligatorio para abrir el caso.");
      form.querySelector('[name="descripcion"]').focus();
      return;
    }
    const boton = form.querySelector('[type="submit"]');
    boton.disabled = true;
    try {
      const caso = await api("/api/diagnosticos/casos", {
        method: "POST",
        body: JSON.stringify({
          estudiante_id: e.id,
          tipo: datos.get("tipo"),
          titulo: String(datos.get("titulo") || "").trim() || null,
          descripcion,
          acciones: String(datos.get("acciones") || "").trim() || null,
          observaciones: String(datos.get("observaciones") || "").trim() || null,
          fecha_apertura: datos.get("fecha_apertura") || null,
          proximo_seguimiento: datos.get("proximo_seguimiento") || null,
          mencion_origen_id: p.mencionOrigenId || null,
        }),
      });
      orCerrarModal();
      orAviso(`Caso abierto para ${orNombreEstudiante(e)}.`);
      orCasosDetalle.set(caso.id, caso);
      orCasosExpandidos.add(caso.id);
      if (ctx.alGuardar) ctx.alGuardar(caso);
    } catch (err) {
      boton.disabled = false;
      orErrorModal(cont, err.message || "No se pudo guardar el caso.");
    }
  });
}

// --- Registrar estudiante nuevo (solo con estudiantes.crear) --------------
// Mismo criterio que la pantalla de Matrícula (agregar.js): primero se
// verifica el documento contra la base; si ya existe, se usa ese registro.

async function orCargarSedes() {
  if (!orSedes) orSedes = (await api("/api/sedes")).filter((s) => s.pertenece_ietaba);
  return orSedes;
}

function orPasoRegistrar(ctx) {
  const cont = orModalCuerpo(
    "Registrar estudiante nuevo",
    `
    <p class="ox-ayuda">Primero se verifica el documento, para no duplicar a alguien que ya está matriculado.</p>
    <form class="ox-form" data-or-verificar>
      <div class="ox-fila-verificar">
        <label>Número de documento <input type="text" name="documento" inputmode="numeric" autocomplete="off" required /></label>
        <button type="submit" class="boton">Verificar</button>
      </div>
    </form>
    <div data-or-verificacion></div>
    <div class="modal-acciones ox-acciones-izq">
      <button type="button" class="boton-texto-chico" data-or-volver-elegir>&larr; Volver a buscar</button>
    </div>`
  );
  cont.querySelector("[data-or-volver-elegir]").addEventListener("click", () => orPasoElegir(ctx));
  const formVerificar = cont.querySelector("[data-or-verificar]");
  formVerificar.querySelector("input").focus();
  formVerificar.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const documento = formVerificar.documento.value.trim();
    if (!documento) return;
    const zona = cont.querySelector("[data-or-verificacion]");
    zona.innerHTML = orCargandoHtml("Verificando...");
    let r;
    try {
      r = await api(`/api/estudiantes/verificar?documento=${encodeURIComponent(documento)}`);
    } catch (err) {
      zona.innerHTML = `<div class="alerta-caja">${esc(err.message)}</div>`;
      return;
    }
    if (r.existe) {
      const e = r.estudiante;
      zona.innerHTML = `
        <div class="exito-caja">Este documento ya está registrado — no hace falta crearlo de nuevo.</div>
        <div class="ox-estudiante-elegido">
          ${orAvatar(orNombreEstudiante(e), e.genero)}
          <span class="ox-picker-texto"><strong>${esc(orNombreEstudiante(e))}</strong><span>${esc(e.documento)} · ${esc(e.grupo || "")} · ${esc(e.sede ? e.sede.nombre : "sin sede")} (${esc(e.estado)})</span></span>
          <button type="button" class="boton" data-or-usar-existente>Usar este estudiante</button>
        </div>`;
      zona.querySelector("[data-or-usar-existente]").addEventListener("click", () =>
        orPasoCaso({ ...ctx, estudiante: { ...e, nombre_completo: orNombreEstudiante(e) }, desdeElegir: true })
      );
      return;
    }
    formVerificar.documento.readOnly = true;
    await orPintarFormRegistro(zona, documento, ctx);
  });
}

async function orPintarFormRegistro(zona, documento, ctx) {
  let sedes;
  try {
    sedes = await orCargarSedes();
  } catch {
    sedes = [];
  }
  const g = ctx.grupo;
  const sedeInicial = g ? g.sede_id : orSedeId;
  const gradoInicial = g ? g.grado : 0;
  zona.innerHTML = `
    <div class="alerta-caja">Este documento <b>no aparece</b> en la base de matrícula. Confírmalo con coordinación antes de registrarlo
      (puede ser un estudiante nuevo que aún no está en el Excel oficial, o un error de digitación).</div>
    <form class="ox-form" data-or-form-registro novalidate>
      <div class="ox-form-grid">
        ${tipoDocumentoSelectHtml("or_tipo_documento", "T.I.")}
        <label>Primer nombre <span class="ox-req">*</span><input type="text" name="primer_nombre" autocomplete="off" /></label>
        <label>Segundo nombre <span class="ox-opcional">opcional</span><input type="text" name="segundo_nombre" autocomplete="off" /></label>
        <label>Primer apellido <span class="ox-req">*</span><input type="text" name="primer_apellido" autocomplete="off" /></label>
        <label>Segundo apellido <span class="ox-opcional">opcional</span><input type="text" name="segundo_apellido" autocomplete="off" /></label>
        <label>Fecha de nacimiento <input type="date" name="fecha_nacimiento" max="${fechaColombiaISO()}" /></label>
        <label>Género <select name="genero"><option value="F">Femenino</option><option value="M">Masculino</option></select></label>
        <label>Sede <select name="sede_id">${sedes
          .map((s) => `<option value="${s.id}" ${s.id === sedeInicial ? "selected" : ""}>${esc(s.nombre)}</option>`)
          .join("")}</select></label>
        <label>Grado <select name="grado">${NOMBRES_GRADOS.map(
          ([n, nombre]) => `<option value="${n}" ${n === gradoInicial ? "selected" : ""}>${esc(nombre)}</option>`
        ).join("")}</select></label>
        <label>Curso <select name="curso"><option value="">Sin curso</option></select></label>
      </div>
      <div data-or-modal-error></div>
      <div class="modal-acciones">
        <button type="submit" class="boton">Registrar y continuar</button>
      </div>
    </form>`;
  vincularTipoDocumentoOtro("or_tipo_documento");
  const form = zona.querySelector("[data-or-form-registro]");
  form.primer_nombre.focus();

  // Los cursos salen de la matrícula real de esa sede y grado.
  const cargarCursos = async () => {
    const sel = form.curso;
    sel.innerHTML = '<option value="">Sin curso</option>';
    try {
      const grados = await api(`/api/sedes/${form.sede_id.value}/grados`);
      const fila = grados.find((x) => x.grado === Number(form.grado.value));
      (fila ? fila.divisiones : []).forEach((d) => {
        const opt = document.createElement("option");
        opt.value = d.numero;
        opt.textContent = d.nombre;
        if (g && g.curso === d.numero && g.grado === Number(form.grado.value)) opt.selected = true;
        sel.appendChild(opt);
      });
    } catch {
      /* se queda "Sin curso": se puede asignar luego en Estudiantes */
    }
  };
  form.sede_id.addEventListener("change", cargarCursos);
  form.grado.addEventListener("change", cargarCursos);
  await cargarCursos();

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const cont = document.getElementById("modal-orientacion");
    const datos = Object.fromEntries(new FormData(form).entries());
    const tipoDoc = valorTipoDocumento(datos, "or_tipo_documento");
    const cuerpo = {
      documento,
      tipo_documento: tipoDoc || null,
      primer_nombre: datos.primer_nombre.trim().toUpperCase(),
      segundo_nombre: datos.segundo_nombre.trim().toUpperCase() || null,
      primer_apellido: datos.primer_apellido.trim().toUpperCase(),
      segundo_apellido: datos.segundo_apellido.trim().toUpperCase() || null,
      fecha_nacimiento: datos.fecha_nacimiento || null,
      genero: datos.genero,
      sede_id: Number(datos.sede_id) || null,
      grado: Number(datos.grado),
      curso: datos.curso ? Number(datos.curso) : null,
      estado: "ACTIVO",
      observaciones: "Registrado desde Orientación",
    };
    if (!cuerpo.primer_nombre || !cuerpo.primer_apellido) {
      orErrorModal(cont, "Faltan el primer nombre y el primer apellido.");
      return;
    }
    const boton = form.querySelector('[type="submit"]');
    boton.disabled = true;
    try {
      const nuevo = await api("/api/estudiantes", { method: "POST", body: JSON.stringify(cuerpo) });
      orGrupoDetalle = null;
      orPasoCaso({
        ...ctx,
        estudiante: { ...nuevo, nombre_completo: orNombreEstudiante(nuevo) },
        desdeElegir: true,
        aviso: "Estudiante registrado. Recuerda avisar a secretaría para que también quede en el Excel oficial de matrícula.",
      });
    } catch (err) {
      boton.disabled = false;
      orErrorModal(cont, err.message || "No se pudo registrar.");
    }
  });
}

// --- Registrar un seguimiento de un caso (modal) --------------------------

function orAbrirFormSeguimiento(casoId, alGuardar) {
  const caso = orCasosDetalle.get(casoId);
  const cont = orMontarModal(
    "Registrar seguimiento",
    `
    ${caso ? `<p class="ox-ayuda">${esc(caso.estudiante_nombre)} · ${esc(caso.titulo || OR_CASO_TIPOS[caso.tipo] || caso.tipo)}</p>` : ""}
    <form class="ox-form" data-or-form-seguimiento novalidate>
      <div class="ox-form-grid">
        <label>Fecha de la atención <input type="date" name="fecha" value="${fechaColombiaISO()}" max="${fechaColombiaISO()}" /></label>
        <label>Tipo de atención <span class="ox-opcional">opcional</span>
          <input type="text" name="tipo_atencion" list="or-tipos-atencion" placeholder="Elige o escribe..." />
          <datalist id="or-tipos-atencion">${OR_TIPOS_ATENCION.map((t) => `<option value="${esc(t)}"></option>`).join("")}</datalist></label>
        <label class="ox-ancho">Situación encontrada <span class="ox-req">*</span><textarea name="situacion" rows="3"></textarea></label>
        <label class="ox-ancho">Acción realizada <span class="ox-opcional">opcional</span><textarea name="accion_realizada" rows="2"></textarea></label>
        <label class="ox-ancho">Compromisos <span class="ox-opcional">opcional</span><textarea name="compromisos" rows="2" placeholder="Del estudiante, la familia o el colegio"></textarea></label>
        <label class="ox-ancho">Observaciones <span class="ox-opcional">opcional</span><textarea name="observaciones" rows="2"></textarea></label>
        <label class="ox-ancho">Próximo seguimiento <span class="ox-opcional">opcional</span>
          <span class="ox-fecha-con-atajos"><input type="date" name="proxima_fecha" min="${fechaColombiaISO()}" />${orAtajosFechaHtml("proxima_fecha")}</span></label>
      </div>
      <p class="ox-nota-form">Al guardar, un caso "Abierto" pasa a "En seguimiento".</p>
      <div data-or-modal-error></div>
      <div class="modal-acciones">
        <button type="button" class="boton secundario" data-or-cancelar>Cancelar</button>
        <button type="submit" class="boton">Guardar seguimiento</button>
      </div>
    </form>`,
    { ancho: true }
  );
  const form = cont.querySelector("[data-or-form-seguimiento]");
  orWireAtajosFecha(form);
  cont.querySelector("[data-or-cancelar]").addEventListener("click", orCerrarModal);
  form.situacion.focus();
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const datos = new FormData(form);
    const situacion = String(datos.get("situacion") || "").trim();
    if (!situacion) {
      orErrorModal(cont, "Escribe la situación encontrada.");
      form.situacion.focus();
      return;
    }
    const boton = form.querySelector('[type="submit"]');
    boton.disabled = true;
    try {
      const detalle = await api(`/api/diagnosticos/casos/${casoId}/seguimientos`, {
        method: "POST",
        body: JSON.stringify({
          fecha: datos.get("fecha") || null,
          tipo_atencion: String(datos.get("tipo_atencion") || "").trim() || null,
          situacion,
          accion_realizada: String(datos.get("accion_realizada") || "").trim() || null,
          compromisos: String(datos.get("compromisos") || "").trim() || null,
          observaciones: String(datos.get("observaciones") || "").trim() || null,
          proxima_fecha: datos.get("proxima_fecha") || null,
        }),
      });
      orCasosDetalle.set(casoId, detalle);
      orCerrarModal();
      orAviso("Seguimiento guardado.");
      alGuardar();
    } catch (err) {
      boton.disabled = false;
      orErrorModal(cont, err.message || "No se pudo guardar el seguimiento.");
    }
  });
}

// =============================================================================
// Tarjeta de CASO (compartida entre grupo y perfil de estudiante)
// =============================================================================

function orCasoCuerpoHtml(c) {
  const puedeEditar = tienePermiso("diagnosticos.observar");
  const seguimientos = c.seguimientos
    .map(
      (s) => `
      <li class="ox-linea-item">
        <span class="ox-linea-punto"></span>
        <div>
          <p class="ox-linea-meta"><b>${esc(orFechaCorta(s.fecha))}</b>${s.tipo_atencion ? ` · ${esc(s.tipo_atencion)}` : ""} · ${esc(s.autor_nombre)}</p>
          <p>${esc(s.situacion)}</p>
          ${s.accion_realizada ? `<p><span class="ox-etiqueta">Acción</span> ${esc(s.accion_realizada)}</p>` : ""}
          ${s.compromisos ? `<p><span class="ox-etiqueta">Compromisos</span> ${esc(s.compromisos)}</p>` : ""}
          ${s.observaciones ? `<p><span class="ox-etiqueta">Observaciones</span> ${esc(s.observaciones)}</p>` : ""}
          ${s.proxima_fecha ? `<p class="ox-linea-meta">Próximo seguimiento: ${esc(orFechaCorta(s.proxima_fecha))}</p>` : ""}
        </div>
      </li>`
    )
    .join("");
  const estados = Object.entries(OR_CASO_ESTADOS)
    .map(
      ([k, v]) =>
        `<button type="button" class="ox-seg-btn${c.estado === k ? ` activo ox-seg-${k}` : ""}" data-or-caso-estado="${c.id}|${k}" ${puedeEditar ? "" : "disabled"} aria-pressed="${c.estado === k}">${v}</button>`
    )
    .join("");
  return `
    <div class="ox-caso-acciones">
      <div class="ox-segmentado" role="group" aria-label="Estado del caso">${estados}</div>
      <span class="ox-espaciador"></span>
      ${puedeEditar ? `<button type="button" class="boton" data-or-caso-nuevo-seguimiento="${c.id}">+ Registrar seguimiento</button>` : ""}
      ${tienePermiso("diagnosticos.exportar") ? `<button type="button" class="boton secundario" data-or-caso-pdf="${c.id}">Imprimir informe</button>` : ""}
    </div>
    <dl class="ox-caso-datos">
      <dt>Situación</dt><dd>${esc(c.descripcion)}</dd>
      ${c.acciones ? `<dt>Acciones realizadas</dt><dd>${esc(c.acciones)}</dd>` : ""}
      ${c.observaciones ? `<dt>Observaciones</dt><dd>${esc(c.observaciones)}</dd>` : ""}
      <dt>Origen</dt><dd>${c.origen === "importado" ? "Abierto desde el diagnóstico del director de grupo" : "Registrado directamente por orientación"} · ${esc(c.autor_nombre)} · ${esc(orFechaCorta(c.fecha_apertura))}</dd>
      ${c.cerrado_en ? `<dt>Cierre</dt><dd>${esc(instanteUtcDesdeApi(c.cerrado_en)?.toLocaleDateString("es-CO") || "")}${c.cerrado_por_nombre ? ` · ${esc(c.cerrado_por_nombre)}` : ""}</dd>` : ""}
    </dl>
    <h4 class="ox-h4">Seguimientos (${c.seguimientos.length})</h4>
    ${seguimientos ? `<ol class="ox-linea">${seguimientos}</ol>` : '<p class="ox-vacio-chico">Todavía no hay seguimientos registrados.</p>'}`;
}

function orCasoCardHtml(c, opciones) {
  const expandido = orCasosExpandidos.has(c.id);
  const detalle = orCasosDetalle.get(c.id);
  const mostrarEstudiante = opciones && opciones.mostrarEstudiante;
  const titulo = c.titulo || OR_CASO_TIPOS[c.tipo] || c.tipo;
  return `
    <article class="ox-caso ox-caso-${c.estado}" id="or-caso-${c.id}">
      <button type="button" class="ox-caso-cab" data-or-caso-toggle="${c.id}" aria-expanded="${expandido}">
        <span class="ox-caso-titulo">
          <strong>${mostrarEstudiante ? `${esc(c.estudiante_nombre)} <span class="ox-sep">—</span> ` : ""}${esc(titulo)}</strong>
          <span class="ox-caso-sub">${esc(OR_CASO_TIPOS[c.tipo] || c.tipo)} · abierto el ${esc(orFechaCorta(c.fecha_apertura))} · ${c.total_seguimientos} seguimiento${c.total_seguimientos === 1 ? "" : "s"}</span>
        </span>
        <span class="ox-caso-lado">
          ${c.estado !== "cerrado" && c.proximo_seguimiento ? `<span class="ox-caso-proximo">${orProximoHtml(c.proximo_seguimiento)}</span>` : ""}
          <span class="badge-estado ${OR_CASO_ESTADO_CLASE[c.estado] || ""}">${esc(OR_CASO_ESTADOS[c.estado] || c.estado)}</span>
          <span class="ox-chevron${expandido ? " abierto" : ""}" aria-hidden="true"></span>
        </span>
      </button>
      ${expandido ? `<div class="ox-caso-cuerpo">${detalle ? orCasoCuerpoHtml(detalle) : orCargandoHtml("Cargando caso...")}</div>` : ""}
    </article>`;
}

// recargar(refrescarDatos): vuelve a pintar la vista; con true, además
// descarta las cachés de conteos (cambió un estado o se agregó algo).
function orWireCasoCards(raiz, recargar) {
  raiz.querySelectorAll("[data-or-caso-toggle]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const id = Number(btn.dataset.orCasoToggle);
      if (orCasosExpandidos.has(id)) {
        orCasosExpandidos.delete(id);
        recargar();
        return;
      }
      orCasosExpandidos.add(id);
      recargar();
      if (!orCasosDetalle.has(id)) {
        try {
          orCasosDetalle.set(id, await api(`/api/diagnosticos/casos/${id}`));
        } catch {
          orCasosExpandidos.delete(id);
          orAviso("No se pudo cargar el caso.", "error");
        }
        recargar();
      }
    })
  );
  raiz.querySelectorAll("[data-or-caso-estado]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const [id, estado] = btn.dataset.orCasoEstado.split("|");
      const actual = orCasosDetalle.get(Number(id));
      if (actual && actual.estado === estado) return;
      if (estado === "cerrado" && !confirm("¿Cerrar este caso? Podrás reabrirlo después si hace falta.")) return;
      try {
        orCasosDetalle.set(Number(id), await api(`/api/diagnosticos/casos/${id}/estado`, { method: "PATCH", body: JSON.stringify({ estado }) }));
        orAviso(`Caso marcado como "${OR_CASO_ESTADOS[estado]}".`);
        recargar(true);
      } catch (e) {
        orAviso(e.message || "No se pudo cambiar el estado.", "error");
      }
    })
  );
  raiz.querySelectorAll("[data-or-caso-nuevo-seguimiento]").forEach((btn) =>
    btn.addEventListener("click", () => orAbrirFormSeguimiento(Number(btn.dataset.orCasoNuevoSeguimiento), () => recargar(true)))
  );
  raiz.querySelectorAll("[data-or-caso-pdf]").forEach((btn) =>
    btn.addEventListener("click", () => orAbrirPdf(`/api/diagnosticos/casos/${btn.dataset.orCasoPdf}/pdf`, btn))
  );
}

// =============================================================================
// ORIENTACIÓN POR GRADO — lista de grupos
// =============================================================================

async function orAsegurarSede() {
  await orCargarSedes();
  if (orSedeId && orSedes.some((s) => s.id === orSedeId)) return;
  try {
    const guardada = Number(localStorage.getItem("or-sede"));
    if (guardada && orSedes.some((s) => s.id === guardada)) {
      orSedeId = guardada;
      return;
    }
  } catch {
    /* sin almacenamiento local: se elige abajo */
  }
  // Por defecto, la sede que ya tiene diagnósticos importados.
  try {
    const diags = await api("/api/diagnosticos/grados");
    if (diags.length) orSedeId = diags[0].sede_id;
  } catch {
    /* se usa la primera sede */
  }
  if (!orSedeId && orSedes.length) orSedeId = orSedes[0].id;
}

async function renderOrPorGrado() {
  if (orGradoSel) return renderOrGrupo();
  if (orVistaLanding === "generales") return renderOrGenerales();
  app.innerHTML = orCargandoHtml("Cargando grupos...");
  let grupos, resumen, casos;
  try {
    await orAsegurarSede();
    [grupos, resumen, casos] = await Promise.all([
      api(`/api/diagnosticos/grupos?sede_id=${orSedeId}`),
      api(`/api/diagnosticos/resumen?sede_id=${orSedeId}`),
      api(`/api/diagnosticos/casos?sede_id=${orSedeId}`),
    ]);
  } catch (e) {
    app.innerHTML = orErrorHtml(e, "No tienes permiso para ver orientación por grado.");
    return;
  }
  orPintarPorGrado(grupos, resumen, casos);
}

function orAgendaHtml(casos, conGrupo) {
  const limite = orSumarDias(7);
  const items = casos
    .filter((c) => c.estado !== "cerrado" && c.proximo_seguimiento && c.proximo_seguimiento <= limite)
    .sort((a, b) => a.proximo_seguimiento.localeCompare(b.proximo_seguimiento));
  if (!items.length) return "";
  const vencidos = items.filter((c) => orDiasHasta(c.proximo_seguimiento) < 0).length;
  return `
    <section class="ox-agenda">
      <header><h3 class="ox-h3">Agenda de seguimientos</h3>
        <span class="ox-tenue">${vencidos ? `<b class="ox-vencido">${vencidos} vencido${vencidos === 1 ? "" : "s"}</b> · ` : ""}próximos 7 días</span></header>
      <ul>${items
        .slice(0, 8)
        .map(
          (c) => `
          <li><button type="button" class="ox-agenda-item" data-or-ir-caso="${c.estudiante_id}|${c.id}">
            <span class="ox-agenda-cuando">${orProximoHtml(c.proximo_seguimiento)}</span>
            <span class="ox-agenda-quien"><strong>${esc(c.estudiante_nombre)}</strong>${conGrupo ? ` <span class="ox-tenue">· ${esc(c.grado_nombre)}</span>` : ""}</span>
            <span class="ox-agenda-que">${esc(c.titulo || OR_CASO_TIPOS[c.tipo] || c.tipo)}</span>
          </button></li>`
        )
        .join("")}</ul>
      ${items.length > 8 ? `<p class="ox-tenue">y ${items.length - 8} más.</p>` : ""}
    </section>`;
}

function orPintarPorGrado(grupos, resumen, casos) {
  const f = normalizarTexto(orFiltroGrupos.trim());
  const activos = (g) => g.casos_abiertos + g.casos_en_seguimiento;
  const pasaChip = {
    todos: () => true,
    casos: (g) => activos(g) > 0,
    revisar: (g) => g.menciones_pendientes > 0,
    sin_diag: (g) => !g.diagnostico_id,
  };
  const visibles = grupos.filter((g) => pasaChip[orChipGrupos](g) && (!f || normalizarTexto(`${g.grado_nombre} ${orCodigoGrupo(g)}`).includes(f)));
  const conDiag = grupos.filter((g) => g.diagnostico_id).length;

  const tarjeta = (g) => {
    const badges = [
      activos(g) ? `<span class="ox-chip ox-tono-azul">${activos(g)} caso${activos(g) === 1 ? "" : "s"} activo${activos(g) === 1 ? "" : "s"}</span>` : "",
      g.seguimientos_vencidos ? `<span class="ox-chip ox-tono-rojo">${g.seguimientos_vencidos} vencido${g.seguimientos_vencidos === 1 ? "" : "s"}</span>` : "",
      g.estudiantes_mencionados ? `<span class="ox-chip ox-tono-gris">${g.estudiantes_mencionados} en el diagnóstico</span>` : "",
      g.menciones_pendientes ? `<span class="ox-chip ox-tono-ambar" title="Nombres del Excel que falta confirmar a qué estudiante corresponden">${g.menciones_pendientes} por revisar</span>` : "",
    ].join("");
    return `
      <button type="button" class="ox-grupo-card" data-or-grupo="${g.grado}|${g.curso ?? ""}">
        <span class="ox-grupo-codigo">${esc(orCodigoGrupo(g))}</span>
        <span class="ox-grupo-cuerpo">
          <strong>${esc(g.grado_nombre)}</strong>
          <span class="ox-grupo-meta">${g.n_estudiantes} estudiante${g.n_estudiantes === 1 ? "" : "s"} · ${
            g.diagnostico_id ? `Diagnóstico ${esc(g.periodo || "sin fecha")}` : '<span class="ox-tenue">Sin diagnóstico</span>'
          }</span>
          <span class="ox-grupo-badges">${badges || '<span class="ox-tenue ox-sin-novedad">Sin novedades</span>'}</span>
        </span>
      </button>`;
  };

  const niveles = OR_NIVELES.map(([nombre, cumple]) => {
    const suyos = visibles.filter((g) => cumple(g.grado));
    if (!suyos.length) return "";
    return `<section class="ox-nivel"><h3 class="ox-h3">${esc(nombre)} <span class="ox-tenue">${suyos.length}</span></h3>
      <div class="ox-grupos-grid">${suyos.map(tarjeta).join("")}</div></section>`;
  }).join("");

  app.innerHTML = `
    <header class="ox-cabecera">
      <div>
        <p class="dx-eyebrow">Orientación escolar</p>
        <h2>Seguimiento por grado</h2>
        <p class="subtitulo-pagina">Grupos según la matrícula, con el diagnóstico del director de grupo y los casos que lleva orientación.</p>
      </div>
      <div class="ox-cabecera-acciones">
        ${
          orSedes.length > 1
            ? `<label class="ox-sede-sel"><span>Sede</span><select data-or-sede>${orSedes
                .map((s) => `<option value="${s.id}" ${s.id === orSedeId ? "selected" : ""}>${esc(s.nombre)}</option>`)
                .join("")}</select></label>`
            : ""
        }
        ${tienePermiso("diagnosticos.exportar") ? '<button type="button" class="boton secundario" data-or-pdf-general title="Resumen de toda la sede: situaciones, grupos y casos activos">Imprimir informe general</button>' : ""}
        ${tienePermiso("diagnosticos.observar") ? '<button type="button" class="boton" data-or-agregar>+ Agregar estudiante al seguimiento</button>' : ""}
      </div>
    </header>
    <div class="ox-kpis">
      ${orKpi(`${conDiag}<small> / ${grupos.length}</small>`, "Grupos con diagnóstico")}
      ${orKpi(resumen.casos_abiertos, "Casos abiertos")}
      ${orKpi(resumen.casos_en_seguimiento, "En seguimiento")}
      ${orKpi(resumen.seguimientos_pendientes, "Seguimientos vencidos", resumen.seguimientos_pendientes ? "rojo" : "")}
    </div>
    ${orAgendaHtml(casos, true)}
    ${orConmutadorLandingHtml()}
    <div class="ox-filtros">
      <div class="ox-buscador"><input type="search" data-or-filtro-grupos placeholder="Buscar grupo (ej. 6-2, Octavo)..." value="${esc(orFiltroGrupos)}" aria-label="Buscar grupo" /></div>
      ${orChips("or-chip-grupos", [
        ["todos", "Todos", grupos.length],
        ["casos", "Con casos activos", grupos.filter(pasaChip.casos).length],
        ["revisar", "Por revisar", grupos.filter(pasaChip.revisar).length],
        ["sin_diag", "Sin diagnóstico", grupos.filter(pasaChip.sin_diag).length],
      ], orChipGrupos)}
    </div>
    ${niveles || '<div class="ox-vacio"><p>Ningún grupo coincide con el filtro.</p></div>'}`;

  const repintar = () => orPintarPorGrado(grupos, resumen, casos);
  app.querySelectorAll("[data-or-grupo]").forEach((b) =>
    b.addEventListener("click", () => {
      const [grado, curso] = b.dataset.orGrupo.split("|");
      orAbrirGrupo(orSedeId, Number(grado), curso === "" ? null : Number(curso));
    })
  );
  const buscador = app.querySelector("[data-or-filtro-grupos]");
  buscador.addEventListener("input", () => {
    orFiltroGrupos = buscador.value;
    const pos = buscador.selectionStart;
    repintar();
    const nuevo = app.querySelector("[data-or-filtro-grupos]");
    nuevo.focus();
    nuevo.setSelectionRange(pos, pos);
  });
  app.querySelectorAll("[data-or-chip-grupos]").forEach((b) =>
    b.addEventListener("click", () => {
      orChipGrupos = b.dataset.orChipGrupos;
      repintar();
    })
  );
  app.querySelector("[data-or-sede]")?.addEventListener("change", (ev) => {
    orSedeId = Number(ev.target.value);
    try {
      localStorage.setItem("or-sede", String(orSedeId));
    } catch {
      /* preferencia opcional */
    }
    renderOrPorGrado();
  });
  orWireConmutadorLanding();
  app.querySelector("[data-or-agregar]")?.addEventListener("click", () =>
    orAbrirFlujoCaso({ alGuardar: (caso) => orIrAPerfil(caso.estudiante_id, null) })
  );
  app.querySelector("[data-or-pdf-general]")?.addEventListener("click", (ev) =>
    orAbrirPdf(`/api/diagnosticos/institucional/pdf?sede_id=${orSedeId}`, ev.currentTarget)
  );
  orWireIrCaso(app);
}

function orConmutadorLandingHtml() {
  return `<div class="ox-conmutador">${orChips("or-vista-landing", [
    ["grupos", "Grupos y casos"],
    ["generales", "Temáticas y estrategias de todos los grupos"],
  ], orVistaLanding)}</div>`;
}

function orWireConmutadorLanding() {
  app.querySelectorAll("[data-or-vista-landing]").forEach((b) =>
    b.addEventListener("click", () => {
      orVistaLanding = b.dataset.orVistaLanding;
      renderOrPorGrado();
    })
  );
}

// Todos los grupos lado a lado: qué temáticas pide trabajar cada director,
// qué estrategias usa, qué resguardos atiende... (lo general del diagnóstico).
async function renderOrGenerales() {
  app.innerHTML = orCargandoHtml("Cargando temáticas y estrategias...");
  let lista;
  try {
    await orAsegurarSede();
    lista = await api(`/api/diagnosticos/generales?sede_id=${orSedeId}`);
  } catch (e) {
    app.innerHTML = orErrorHtml(e, "No tienes permiso para ver esto.");
    return;
  }
  const pintar = () => {
    const f = normalizarTexto(orFiltroGenerales.trim());
    const campos = orCampoGeneral === "todo" ? OR_GENERALES : OR_GENERALES.filter(([, c]) => c === orCampoGeneral);
    const visibles = lista.filter((g) => !f || normalizarTexto(`${g.grado_nombre} ${campos.map(([, c]) => g[c] || "").join(" ")}`).includes(f));
    const conRespuesta = (c) => lista.filter((g) => (g[c] || "").trim()).length;
    const filas = visibles
      .map(
        (g) => `
        <tr class="ox-fila-est" data-or-grupo-gen="${g.grado}|${g.curso ?? ""}" tabindex="0">
          <td><strong>${esc(g.grado_nombre)}</strong><br><span class="ox-tenue">${esc(g.director_grado_nombre || "")}${g.periodo ? ` · ${esc(g.periodo)}` : ""}</span></td>
          ${campos
            .map(([, c]) => `<td class="ox-gen-celda">${(g[c] || "").trim() ? esc(g[c]) : '<span class="ox-tenue">Sin respuesta</span>'}</td>`)
            .join("")}
        </tr>`
      )
      .join("");
    const cont = document.getElementById("or-generales-tabla");
    cont.innerHTML = visibles.length
      ? `<div class="ox-tabla-envoltura"><table class="ox-tabla ox-tabla-generales">
          <thead><tr><th>Grupo</th>${campos.map(([t]) => `<th>${esc(t)}</th>`).join("")}</tr></thead>
          <tbody>${filas}</tbody></table></div>`
      : '<div class="ox-vacio"><p>Ningún grupo coincide con la búsqueda.</p></div>';
    document.getElementById("or-generales-resumen").textContent =
      orCampoGeneral === "todo"
        ? `${lista.length} grupos con diagnóstico.`
        : `${conRespuesta(orCampoGeneral)} de ${lista.length} grupos respondieron este punto.`;
    cont.querySelectorAll("[data-or-grupo-gen]").forEach((tr) =>
      tr.addEventListener("click", () => {
        const [grado, curso] = tr.dataset.orGrupoGen.split("|");
        orVistaLanding = "grupos";
        orAbrirGrupo(orSedeId, Number(grado), curso === "" ? null : Number(curso), "diagnostico");
      })
    );
  };

  app.innerHTML = `
    <header class="ox-cabecera">
      <div>
        <p class="dx-eyebrow">Orientación escolar</p>
        <h2>Temáticas y estrategias</h2>
        <p class="subtitulo-pagina">Lo general que reporta el director de cada grupo en el diagnóstico: qué temáticas hay que trabajar, qué estrategias se aplican, qué resguardos se atienden.</p>
      </div>
    </header>
    ${orConmutadorLandingHtml()}
    <div class="ox-filtros">
      <div class="ox-buscador"><input type="search" data-or-gen-buscar placeholder="Buscar (ej. proyecto de vida, diálogo, Saunde)..." value="${esc(orFiltroGenerales)}" aria-label="Buscar" /></div>
      ${orChips("or-campo-gen", [...OR_GENERALES.map(([t, c]) => [c, t.replace(/ con los estudiantes| de los docentes| de los padres de familia/, "")]), ["todo", "Todo"]], orCampoGeneral)}
    </div>
    <p class="ox-tenue" id="or-generales-resumen"></p>
    <div id="or-generales-tabla"></div>`;

  orWireConmutadorLanding();
  app.querySelector("[data-or-gen-buscar]").addEventListener("input", (ev) => {
    orFiltroGenerales = ev.target.value;
    pintar();
  });
  app.querySelectorAll("[data-or-campo-gen]").forEach((b) =>
    b.addEventListener("click", () => {
      orCampoGeneral = b.dataset.orCampoGen;
      app.querySelectorAll("[data-or-campo-gen]").forEach((x) => x.classList.toggle("activo", x === b));
      pintar();
    })
  );
  pintar();
}

function orWireIrCaso(raiz) {
  raiz.querySelectorAll("[data-or-ir-caso]").forEach((b) =>
    b.addEventListener("click", () => {
      const [estudianteId, casoId] = b.dataset.orIrCaso.split("|").map(Number);
      orIrAPerfil(estudianteId, null, casoId);
    })
  );
}

function orAbrirGrupo(sedeId, grado, curso, tab) {
  orSedeId = sedeId;
  orGradoSel = { sede_id: sedeId, grado, curso };
  orGrupoDetalle = null;
  orDiagDetalle = null;
  orDiagVersionId = null;
  orGrupoTab = tab || "estudiantes";
  orFiltroEstGrupo = "";
  orChipEstGrupo = "todos";
  orGradoVinculando = null;
  orFiltroSituaciones = "";
  orSituacionesExpandidas = new Set();
  orVista = "diagnostico-grados";
  orMarcarTab();
  render();
}

// Abre el perfil de un estudiante; si viene de un grupo, las migas de pan
// ofrecen volver a él. casoId (opcional) queda desplegado al llegar.
function orIrAPerfil(estudianteId, desdeGrupo, casoId) {
  orEstudianteSel = estudianteId;
  orEstudianteResumen = null;
  orPerfilDesdeGrupo = desdeGrupo;
  if (casoId) {
    orCasosExpandidos.add(casoId);
    orCasosDetalle.delete(casoId);
  }
  orVista = "diagnostico-estudiante";
  orMarcarTab();
  render();
}

// =============================================================================
// ORIENTACIÓN POR GRADO — detalle de un grupo (pestañas)
// =============================================================================

async function renderOrGrupo() {
  if (!orGrupoDetalle) app.innerHTML = orCargandoHtml("Cargando grupo...");
  try {
    if (!orGrupoDetalle) {
      const s = orGradoSel;
      orGrupoDetalle = await api(`/api/diagnosticos/grupos/${s.sede_id}/${s.grado}${s.curso != null ? `?curso=${s.curso}` : ""}`);
    }
    const idDiag = orDiagVersionId || orGrupoDetalle.diagnostico_id;
    if ((orGrupoTab === "diagnostico" || orGrupoTab === "revision") && idDiag && (!orDiagDetalle || orDiagDetalle.id !== idDiag)) {
      orDiagDetalle = await api(`/api/diagnosticos/grados/${idDiag}`);
    }
  } catch (e) {
    app.innerHTML = orErrorHtml(e, "No tienes permiso para ver este grupo.");
    return;
  }
  orPintarGrupo();
}

function orRecargarGrupo(refrescar) {
  if (refrescar) {
    orGrupoDetalle = null;
    orDiagDetalle = null;
  }
  renderOrGrupo();
}

function orPintarGrupo() {
  const g = orGrupoDetalle;
  const activos = g.casos_abiertos + g.casos_en_seguimiento;
  const mencionados = g.estudiantes.filter((e) => e.total_situaciones).length;
  const puedeVincular = tienePermiso("diagnosticos.vincular");
  const tabs = [
    ["estudiantes", "Estudiantes", g.estudiantes.filter((e) => e.en_matricula_del_grupo).length],
    ["diagnostico", "Diagnóstico del grado", null],
    ["casos", "Casos", g.casos.length],
  ];
  if (g.diagnostico_id && puedeVincular) tabs.push(["revision", "Revisión de nombres", g.menciones_pendientes]);
  if (!tabs.some(([k]) => k === orGrupoTab)) orGrupoTab = "estudiantes";

  let panel = "";
  if (orGrupoTab === "estudiantes") panel = orPanelEstudiantesHtml(g);
  else if (orGrupoTab === "diagnostico") panel = orPanelDiagnosticoHtml(g);
  else if (orGrupoTab === "casos") panel = orPanelCasosHtml(g);
  else panel = orPanelRevisionHtml();

  app.innerHTML = `
    <nav class="ox-migas" aria-label="Ruta">
      <button type="button" data-or-volver>Orientación por grado</button><span aria-hidden="true">/</span><span>${esc(g.grado_nombre)}</span>
    </nav>
    <header class="ox-cabecera ox-cabecera-grupo">
      <div class="ox-cabecera-titulo">
        <span class="ox-grupo-codigo ox-grupo-codigo-grande">${esc(orCodigoGrupo(g))}</span>
        <div>
          <p class="dx-eyebrow">${esc(g.sede_nombre)}</p>
          <h2>${esc(g.grado_nombre)}</h2>
          <p class="subtitulo-pagina">${g.director_grado_nombre ? `Director(a) de grupo: ${esc(g.director_grado_nombre)} · ` : ""}${
            g.diagnostico_id ? `Diagnóstico de ${esc(g.periodo || orFechaLarga(g.fecha_diligenciado) || "fecha sin determinar")}` : "Sin diagnóstico importado"
          }</p>
        </div>
      </div>
      <div class="ox-cabecera-acciones">
        ${tienePermiso("diagnosticos.exportar") ? '<button type="button" class="boton secundario" data-or-pdf-grupo title="Resumen del grupo: situaciones, estudiantes con novedades y casos">Imprimir informe del grupo</button>' : ""}
        ${tienePermiso("diagnosticos.observar") ? '<button type="button" class="boton" data-or-agregar>+ Agregar estudiante al seguimiento</button>' : ""}
      </div>
    </header>
    <div class="ox-kpis">
      ${orKpi(g.n_estudiantes, "Estudiantes activos")}
      ${orKpi(mencionados, "Mencionados en el diagnóstico")}
      ${orKpi(activos, "Casos activos")}
      ${orKpi(g.seguimientos_vencidos, "Seguimientos vencidos", g.seguimientos_vencidos ? "rojo" : "")}
    </div>
    <div class="ox-tabs" role="tablist">
      ${tabs
        .map(
          ([k, t, n]) =>
            `<button type="button" role="tab" class="ox-tab${orGrupoTab === k ? " activo" : ""}" aria-selected="${orGrupoTab === k}" data-or-tab="${k}">${esc(t)}${
              n !== null && n !== undefined ? ` <span class="ox-tab-n${k === "revision" && n ? " ox-tab-n-ambar" : ""}">${n}</span>` : ""
            }</button>`
        )
        .join("")}
    </div>
    <div class="ox-panel" role="tabpanel">${panel}</div>`;

  app.querySelector("[data-or-volver]").addEventListener("click", () => {
    orGradoSel = null;
    render();
  });
  app.querySelectorAll("[data-or-tab]").forEach((b) =>
    b.addEventListener("click", () => {
      orGrupoTab = b.dataset.orTab;
      renderOrGrupo();
    })
  );
  app.querySelector("[data-or-pdf-grupo]")?.addEventListener("click", (ev) =>
    orAbrirPdf(`/api/diagnosticos/grupos/${g.sede_id}/${g.grado}/pdf${g.curso != null ? `?curso=${g.curso}` : ""}`, ev.currentTarget)
  );
  app.querySelector("[data-or-agregar]")?.addEventListener("click", () =>
    orAbrirFlujoCaso({ grupo: g, alGuardar: () => { orGrupoTab = "casos"; orRecargarGrupo(true); } })
  );

  if (orGrupoTab === "estudiantes") orWirePanelEstudiantes(g);
  else if (orGrupoTab === "diagnostico") orWirePanelDiagnostico(g);
  else if (orGrupoTab === "casos") orWirePanelCasos();
  else orWirePanelRevision();
}

// --- Pestaña: Estudiantes ---------------------------------------------------

function orFiltrarEstudiantesGrupo(g) {
  const f = normalizarTexto(orFiltroEstGrupo.trim());
  const pasa = {
    todos: () => true,
    situaciones: (e) => e.total_situaciones > 0,
    casos: (e) => e.casos_activos > 0,
    sin_novedad: (e) => !e.total_situaciones && !e.casos_total,
  };
  return g.estudiantes.filter((e) => pasa[orChipEstGrupo](e) && (!f || normalizarTexto(`${e.nombre_completo} ${e.documento}`).includes(f)));
}

function orFilasEstudiantesHtml(g) {
  const lista = orFiltrarEstudiantesGrupo(g);
  if (!lista.length) return '<tr><td colspan="5"><p class="ox-vacio-chico">Nadie coincide con el filtro.</p></td></tr>';
  const puedeCaso = tienePermiso("diagnosticos.observar");
  return lista
    .map((e) => {
      const chips = e.situaciones.slice(0, 3).map(orChipCategoria).join("") + (e.situaciones.length > 3 ? `<span class="ox-chip ox-tono-gris">+${e.situaciones.length - 3}</span>` : "");
      const orientacion = e.casos_activos
        ? `<span class="badge-estado proceso">${e.casos_activos} caso${e.casos_activos === 1 ? "" : "s"} activo${e.casos_activos === 1 ? "" : "s"}</span>`
        : e.casos_total
          ? '<span class="badge-estado ok">Casos cerrados</span>'
          : '<span class="ox-tenue">—</span>';
      return `
        <tr class="ox-fila-est${e.en_matricula_del_grupo ? "" : " ox-fila-fuera"}" data-or-perfil="${e.id}" tabindex="0">
          <td>
            <span class="ox-est-celda">
              ${orAvatar(e.nombre_completo, e.genero)}
              <span class="ox-picker-texto"><strong>${esc(e.nombre_completo)}</strong><span>${esc(e.documento)}${
                e.casos_activos ? ` <span class="ox-solo-movil ox-pronto">· ${e.casos_activos} caso${e.casos_activos === 1 ? "" : "s"} activo${e.casos_activos === 1 ? "" : "s"}</span>` : ""
              }${
                e.en_matricula_del_grupo ? "" : ` · <span class="ox-pronto">Ya no está activo en este grupo (${esc(e.grupo)}, ${esc(e.estado)})</span>`
              }</span></span>
            </span>
          </td>
          <td class="ox-col-sit">${chips || '<span class="ox-tenue">—</span>'}</td>
          <td class="ox-col-ori">${orientacion}</td>
          <td class="ox-col-prox">${orProximoHtml(e.proximo_seguimiento)}</td>
          <td class="ox-col-acc">${puedeCaso ? `<button type="button" class="boton-texto-chico" data-or-caso-est="${e.id}">Abrir caso</button>` : ""}<span class="ox-chevron-der" aria-hidden="true"></span></td>
        </tr>`;
    })
    .join("");
}

function orPanelEstudiantesHtml(g) {
  const conteo = (fn) => g.estudiantes.filter(fn).length;
  return `
    <div class="ox-filtros">
      <div class="ox-buscador"><input type="search" data-or-filtro-est placeholder="Buscar por nombre o documento..." value="${esc(orFiltroEstGrupo)}" aria-label="Buscar estudiante del grupo" /></div>
      ${orChips("or-chip-est", [
        ["todos", "Todos", g.estudiantes.length],
        ["situaciones", "En el diagnóstico", conteo((e) => e.total_situaciones > 0)],
        ["casos", "Con caso activo", conteo((e) => e.casos_activos > 0)],
        ["sin_novedad", "Sin novedades", conteo((e) => !e.total_situaciones && !e.casos_total)],
      ], orChipEstGrupo)}
    </div>
    <div class="ox-tabla-envoltura">
      <table class="ox-tabla">
        <thead><tr><th>Estudiante</th><th class="ox-col-sit">Situaciones en el diagnóstico</th><th class="ox-col-ori">Orientación</th><th class="ox-col-prox">Próximo seguimiento</th><th class="ox-col-acc"></th></tr></thead>
        <tbody data-or-filas-est>${orFilasEstudiantesHtml(g)}</tbody>
      </table>
    </div>
    <p class="ox-pie-nota">¿Falta alguien en esta lista? ${
      tienePermiso("estudiantes.crear")
        ? 'Usa <b>+ Agregar estudiante al seguimiento</b> → "Registrar estudiante nuevo".'
        : "Si es un estudiante nuevo, pide a secretaría que lo matricule en este grupo."
    }</p>`;
}

function orWirePanelEstudiantes(g) {
  const tbody = app.querySelector("[data-or-filas-est]");
  const wireFilas = () => {
    tbody.querySelectorAll("[data-or-perfil]").forEach((tr) => {
      const abrir = () => orIrAPerfil(Number(tr.dataset.orPerfil), g.grado_nombre);
      tr.addEventListener("click", abrir);
      tr.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") abrir();
      });
    });
    tbody.querySelectorAll("[data-or-caso-est]").forEach((b) =>
      b.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const e = g.estudiantes.find((x) => x.id === Number(b.dataset.orCasoEst));
        orAbrirFlujoCaso({ grupo: g, estudiante: e, alGuardar: () => orRecargarGrupo(true) });
      })
    );
  };
  app.querySelector("[data-or-filtro-est]").addEventListener("input", (ev) => {
    orFiltroEstGrupo = ev.target.value;
    tbody.innerHTML = orFilasEstudiantesHtml(g);
    wireFilas();
  });
  app.querySelectorAll("[data-or-chip-est]").forEach((b) =>
    b.addEventListener("click", () => {
      orChipEstGrupo = b.dataset.orChipEst;
      orPintarGrupo();
    })
  );
  wireFilas();
}

// --- Pestaña: Diagnóstico del grado (contenido del Excel, solo lectura) ----

function orPanelDiagnosticoHtml(g) {
  if (!g.diagnostico_id) {
    return `<div class="ox-vacio">
      <p><b>Este grupo no tiene diagnóstico importado.</b></p>
      <p>El Excel "DIAGNOSTICO IETABA" no trae una hoja para ${esc(g.grado_nombre)}. Igual puedes abrir casos desde la pestaña Estudiantes.</p>
    </div>`;
  }
  const d = orDiagDetalle;
  if (!d) return orCargandoHtml("Cargando diagnóstico...");

  const versiones =
    d.historial.length > 1
      ? `<div class="ox-versiones"><span class="ox-tenue">Versión:</span>${d.historial
          .map(
            (v) =>
              `<button type="button" class="ox-chip-filtro${v.id === d.id ? " activo" : ""}" data-or-version="${v.id}">${esc(v.periodo || orFechaLarga(v.fecha_diligenciado) || "—")}${v.es_version_actual ? " · vigente" : ""}</button>`
          )
          .join("")}</div>`
      : "";

  const general = [
    ["Estudiantes desplazados", d.desplazados_texto],
    ["Estudiantes embarazadas", d.embarazadas_texto],
    ["Estudiantes víctimas de conflicto armado", d.victimas_conflicto_texto],
  ].filter(([, v]) => (v || "").trim());

  const generales = new Set(OR_GENERALES.map(([, c]) => c));
  const secciones = OR_SECCIONES.filter(([, campo]) => !generales.has(campo) && (d[campo] || "").trim())
    .map(
      ([titulo, campo]) => `
      <details class="ox-bloque" open>
        <summary>${esc(titulo)}</summary>
        <p>${esc(d[campo])}</p>
      </details>`
    )
    .join("");

  return `
    <div class="ox-diag-barra">
      ${versiones || "<span></span>"}
      ${tienePermiso("diagnosticos.exportar") ? '<button type="button" class="boton secundario" data-or-pdf-diag title="El formulario que diligenció el director de grupo, completo">Imprimir diagnóstico del director</button>' : ""}
    </div>
    <section class="ox-ficha">
      <dl>
        <div><dt>Periodo</dt><dd>${esc(d.periodo || "—")}</dd></div>
        <div><dt>Fecha del diagnóstico</dt><dd>${esc(orFechaLarga(d.fecha_diligenciado) || "—")}</dd></div>
        <div><dt>Director(a) de grupo</dt><dd>${esc(d.director_grado_nombre || "—")}</dd></div>
        <div><dt>Orientador(a) escolar</dt><dd>${esc(d.orientador_escolar_nombre || "—")}</dd></div>
        <div><dt>En lista / asisten</dt><dd>${d.n_en_lista ?? "—"} / ${d.n_asisten ?? "—"}</dd></div>
        <div><dt>Situaciones detectadas</dt><dd>${d.total_menciones} de ${d.estudiantes_mencionados} estudiante${d.estudiantes_mencionados === 1 ? "" : "s"}</dd></div>
      </dl>
    </section>
    ${orGeneralesHtml(d)}
    ${
      d.menciones.length
        ? `<section class="ox-seccion">
            <header class="ox-seccion-cab"><h3 class="ox-h3">Situaciones de estudiantes</h3>
              <div class="ox-buscador ox-buscador-chico"><input type="search" data-or-filtro-situaciones placeholder="Buscar estudiante..." value="${esc(orFiltroSituaciones)}" aria-label="Buscar en situaciones" /></div></header>
            <div class="dx-lista-situaciones">${orPintarGruposSituaciones(d.menciones)}</div>
          </section>`
        : ""
    }
    ${
      general.length
        ? `<section class="ox-seccion"><h3 class="ox-h3">Información general del grupo</h3>${general
            .map(([t, v]) => `<details class="ox-bloque" open><summary>${esc(t)}</summary><p>${esc(v)}</p></details>`)
            .join("")}</section>`
        : ""
    }
    ${secciones ? `<section class="ox-seccion"><h3 class="ox-h3">Lo que reporta el director de grupo</h3>${secciones}</section>` : ""}
    ${d.seguimiento_nota ? `<section class="ox-seccion"><h3 class="ox-h3">Seguimiento (del formulario)</h3><div class="ox-bloque-plano"><p>${esc(d.seguimiento_nota)}</p></div></section>` : ""}`;
}

function orWirePanelDiagnostico(g) {
  const d = orDiagDetalle;
  if (!d) return;
  app.querySelectorAll("[data-or-version]").forEach((b) =>
    b.addEventListener("click", () => {
      orDiagVersionId = Number(b.dataset.orVersion);
      renderOrGrupo();
    })
  );
  app.querySelector("[data-or-pdf-diag]")?.addEventListener("click", (ev) => orAbrirPdf(`/api/diagnosticos/grados/${d.id}/pdf`, ev.currentTarget));
  app.querySelector("[data-or-filtro-situaciones]")?.addEventListener("input", (ev) => {
    orFiltroSituaciones = ev.target.value;
    orRepintarSituaciones(d.menciones, g);
  });
  orWireGruposSituaciones(d.menciones, g);
}

// --- Situaciones agrupadas por estudiante ---------------------------------

function orGruposSituaciones(menciones) {
  const grupos = new Map();
  for (const m of menciones) {
    const clave = m.estudiante_id ? `e${m.estudiante_id}` : `n${(m.nombre_detectado || m.texto || "").toLowerCase().trim()}`;
    if (!grupos.has(clave)) {
      grupos.set(clave, { clave, nombre: m.estudiante_id ? m.estudiante_nombre : m.nombre_detectado || "Sin nombre detectado", estudianteId: m.estudiante_id, items: [] });
    }
    grupos.get(clave).items.push(m);
  }
  return [...grupos.values()].sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
}

function orPintarGruposSituaciones(menciones) {
  const filtro = normalizarTexto(orFiltroSituaciones.trim());
  const grupos = orGruposSituaciones(menciones).filter((g) => !filtro || normalizarTexto(g.nombre).includes(filtro));
  if (!grupos.length) return '<p class="ox-vacio-chico">No hay coincidencias.</p>';
  const puedeCaso = tienePermiso("diagnosticos.observar");
  return grupos
    .map((g) => {
      const expandido = orSituacionesExpandidas.has(g.clave);
      const categorias = [...new Set(g.items.map((m) => m.categoria))];
      const detalle = g.items
        .map(
          (m) => `
          <div class="dx-situacion-item">
            ${orChipCategoria(m.categoria)}${m.texto_compartido ? ' <span class="ox-tenue">· texto compartido con otro estudiante mencionado en la misma frase</span>' : ""}
            <p>${esc(m.texto)}</p>
            <div class="dx-situacion-acciones">
              ${g.estudianteId ? `<button type="button" class="boton-texto-chico" data-or-ver-estudiante="${g.estudianteId}">Ver perfil</button>` : '<span class="ox-tenue">Sin vincular a un estudiante — ver pestaña "Revisión de nombres"</span>'}
              ${
                m.caso_id
                  ? `<button type="button" class="boton-texto-chico" data-or-ver-caso="${m.caso_id}">Ver caso</button>`
                  : g.estudianteId && puedeCaso
                    ? `<button type="button" class="boton-texto-chico" data-or-abrir-caso="${m.id}">Abrir caso</button>`
                    : ""
              }
            </div>
          </div>`
        )
        .join("");
      return `
        <div class="dx-tarjeta-situacion">
          <button type="button" class="dx-tarjeta-situacion-cab" data-or-toggle-situacion="${esc(g.clave)}" aria-expanded="${expandido}">
            <span class="ox-est-celda">${orAvatar(g.nombre, null)}<span>${esc(g.nombre)}</span></span>
            <span class="dx-tarjeta-situacion-meta">${categorias.map(orChipCategoria).join("")}<span class="ox-chevron${expandido ? " abierto" : ""}" aria-hidden="true"></span></span>
          </button>
          ${expandido ? `<div class="dx-tarjeta-situacion-cuerpo">${detalle}</div>` : ""}
        </div>`;
    })
    .join("");
}

function orRepintarSituaciones(menciones, grupo) {
  const contenedor = app.querySelector(".dx-lista-situaciones");
  if (!contenedor) return;
  contenedor.innerHTML = orPintarGruposSituaciones(menciones);
  orWireGruposSituaciones(menciones, grupo);
}

function orWireGruposSituaciones(menciones, grupo) {
  const contenedor = app.querySelector(".dx-lista-situaciones");
  if (!contenedor) return;
  contenedor.querySelectorAll("[data-or-toggle-situacion]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const clave = btn.dataset.orToggleSituacion;
      if (orSituacionesExpandidas.has(clave)) orSituacionesExpandidas.delete(clave);
      else orSituacionesExpandidas.add(clave);
      orRepintarSituaciones(menciones, grupo);
    })
  );
  contenedor.querySelectorAll("[data-or-ver-estudiante]").forEach((btn) =>
    btn.addEventListener("click", () => orIrAPerfil(Number(btn.dataset.orVerEstudiante), grupo.grado_nombre))
  );
  contenedor.querySelectorAll("[data-or-abrir-caso]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const m = menciones.find((x) => x.id === Number(btn.dataset.orAbrirCaso));
      const est = grupo.estudiantes.find((x) => x.id === m.estudiante_id) || {
        id: m.estudiante_id, nombre_completo: m.estudiante_nombre, documento: m.estudiante_documento || "",
      };
      orAbrirFlujoCaso({
        grupo,
        estudiante: est,
        prefill: {
          mencionOrigenId: m.id, tipo: OR_CATEGORIA_A_TIPO_CASO[m.categoria] || "otra",
          titulo: orCategoriaTexto(m.categoria), descripcion: m.texto,
        },
        alGuardar: () => orRecargarGrupo(true),
      });
    })
  );
  contenedor.querySelectorAll("[data-or-ver-caso]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const id = Number(btn.dataset.orVerCaso);
      orCasosExpandidos.add(id);
      orChipCasos = "todos";
      orGrupoTab = "casos";
      renderOrGrupo().then(() => {
        if (!orCasosDetalle.has(id)) {
          api(`/api/diagnosticos/casos/${id}`)
            .then((det) => {
              orCasosDetalle.set(id, det);
              orPintarGrupo();
              document.getElementById(`or-caso-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
            })
            .catch(() => {});
        } else {
          document.getElementById(`or-caso-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      });
    })
  );
}

// --- Pestaña: Casos del grupo -----------------------------------------------

function orPanelCasosHtml(g) {
  const pasa = { activos: (c) => c.estado !== "cerrado", cerrados: (c) => c.estado === "cerrado", todos: () => true };
  const lista = g.casos.filter(pasa[orChipCasos]);
  return `
    <div class="ox-filtros">
      ${orChips("or-chip-casos", [
        ["activos", "Activos", g.casos.filter(pasa.activos).length],
        ["cerrados", "Cerrados", g.casos.filter(pasa.cerrados).length],
        ["todos", "Todos", g.casos.length],
      ], orChipCasos)}
    </div>
    ${
      lista.length
        ? `<div class="ox-casos">${lista.map((c) => orCasoCardHtml(c, { mostrarEstudiante: true })).join("")}</div>`
        : `<div class="ox-vacio">
            <p><b>${g.casos.length ? "No hay casos en este filtro." : "Todavía no hay casos en este grupo."}</b></p>
            ${
              !g.casos.length && tienePermiso("diagnosticos.observar")
                ? '<p>Abre uno desde la pestaña Estudiantes, desde una situación del diagnóstico, o con "+ Agregar estudiante al seguimiento".</p>'
                : ""
            }
          </div>`
    }`;
}

function orWirePanelCasos() {
  app.querySelectorAll("[data-or-chip-casos]").forEach((b) =>
    b.addEventListener("click", () => {
      orChipCasos = b.dataset.orChipCasos;
      orPintarGrupo();
    })
  );
  orWireCasoCards(app, (refrescar) => (refrescar ? orRecargarGrupo(true) : orPintarGrupo()));
}

// --- Pestaña: Revisión de nombres (uso interno, nunca sale en el PDF) -------

// alta = vinculado con confianza · media = posible coincidencia, hace
// falta elegir · baja = no coincide con nadie del grupo (puede ser un
// familiar, docente u otra persona, o un estudiante que no está en la
// lista). Solo para la app — nunca aparece en el informe impreso.
function orEstadoVinculo(m) {
  if (m.estudiante_id) return ["ok", m.vinculo_automatico ? "Reconocido" : "Confirmado"];
  if (m.confianza === "media") return ["proceso", "Posible coincidencia"];
  return ["", "Sin coincidencia"];
}

function orPanelRevisionHtml() {
  const d = orDiagDetalle;
  if (!d) return orCargandoHtml("Cargando diagnóstico...");
  if (!d.menciones.length) return '<div class="ox-vacio"><p>Este diagnóstico no nombra a ningún estudiante.</p></div>';
  const ordenadas = [...d.menciones].sort((a, b) => (a.estudiante_id ? 1 : 0) - (b.estudiante_id ? 1 : 0));
  const pendientes = d.menciones.filter((m) => !m.estudiante_id).length;
  const filas = ordenadas
    .map((m) => {
      const [clase, texto] = orEstadoVinculo(m);
      return `
      <tr>
        <td><span class="badge-estado ${clase}">${texto}</span></td>
        <td>${orChipCategoria(m.categoria)}</td>
        <td class="ox-texto-original">${esc(m.texto)}</td>
        <td>
          ${m.estudiante_id ? `<strong>${esc(m.estudiante_nombre)}</strong>` : `<span class="ox-tenue">Nombre en el Excel:</span> ${esc(m.nombre_detectado || "—")}`}
          ${
            !m.estudiante_id && m.candidatos && m.candidatos.length
              ? `<div class="ox-candidatos"><span class="ox-tenue">¿Es alguno de estos?</span>${m.candidatos
                  .map((c) => `<button type="button" class="ox-chip-filtro" data-or-vincular-directo="${m.id}|${c.id}">${esc(c.nombre_completo)}</button>`)
                  .join("")}</div>`
              : ""
          }
          ${
            orGradoVinculando === m.id
              ? `<div class="ox-vincular-buscar">
                  <div class="ox-buscador ox-buscador-chico"><input type="search" data-or-vincular-input="${m.id}" placeholder="Buscar estudiante..." autocomplete="off" /></div>
                  <div data-or-vincular-resultados></div>
                  ${m.estudiante_id ? `<button type="button" class="boton-texto-chico ox-peligro" data-or-desvincular="${m.id}">Quitar vínculo</button>` : ""}
                </div>`
              : ""
          }
        </td>
        <td><button type="button" class="boton-texto-chico" data-or-vincular="${m.id}">${orGradoVinculando === m.id ? "Cerrar" : m.estudiante_id ? "Cambiar" : "Buscar..."}</button></td>
      </tr>`;
    })
    .join("");
  return `
    <div class="dx-panel-interno no-imprimir">
      <h3>Uso interno — ¿a qué estudiante corresponde cada nombre del Excel?</h3>
      <p class="subtitulo-pagina">El sistema intenta reconocer a quién se refiere cada nombre que escribió el director de grupo.
        Esto es solo para trabajar dentro de la aplicación: <b>no aparece en el informe impreso</b>, ahí siempre se ve el nombre tal cual.
        ${pendientes ? `<b>${pendientes} pendiente${pendientes === 1 ? "" : "s"} de revisión.</b>` : "Todo vinculado o revisado."}</p>
      <div class="ox-tabla-envoltura">
        <table class="ox-tabla ox-tabla-revision"><thead><tr><th>Estado</th><th>Situación</th><th>Texto original</th><th>Estudiante</th><th></th></tr></thead><tbody>${filas}</tbody></table>
      </div>
    </div>`;
}

async function orVincular(mencionId, estudianteId) {
  try {
    await api(`/api/diagnosticos/menciones/${mencionId}`, { method: "PATCH", body: JSON.stringify({ estudiante_id: estudianteId }) });
    orGradoVinculando = null;
    orAviso(estudianteId ? "Nombre vinculado al estudiante." : "Vínculo quitado.");
    orRecargarGrupo(true);
  } catch (e) {
    orAviso(e.message || "No se pudo guardar el vínculo.", "error");
  }
}

function orWirePanelRevision() {
  app.querySelectorAll("[data-or-vincular]").forEach((b) =>
    b.addEventListener("click", () => {
      const id = Number(b.dataset.orVincular);
      orGradoVinculando = orGradoVinculando === id ? null : id;
      orPintarGrupo();
      app.querySelector("[data-or-vincular-input]")?.focus();
    })
  );
  app.querySelectorAll("[data-or-vincular-directo]").forEach((b) =>
    b.addEventListener("click", () => {
      const [mencionId, estudianteId] = b.dataset.orVincularDirecto.split("|").map(Number);
      orVincular(mencionId, estudianteId);
    })
  );
  app.querySelectorAll("[data-or-desvincular]").forEach((b) => b.addEventListener("click", () => orVincular(Number(b.dataset.orDesvincular), null)));
  const input = app.querySelector("[data-or-vincular-input]");
  if (!input) return;
  const contenedor = app.querySelector("[data-or-vincular-resultados]");
  let timer = null;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const texto = input.value.trim();
    if (texto.length < 3) {
      contenedor.innerHTML = "";
      return;
    }
    timer = setTimeout(async () => {
      try {
        const r = await api(`/api/estudiantes/pagina?q=${encodeURIComponent(texto)}&por_pagina=8`);
        contenedor.innerHTML = r.items.length
          ? `<div class="ox-picker ox-picker-chico">${r.items
              .map(
                (e) => `<button type="button" class="ox-picker-item" data-or-elegir="${e.id}">${orAvatar(orNombreEstudiante(e), e.genero)}
                  <span class="ox-picker-texto"><strong>${esc(orNombreEstudiante(e))}</strong><span>${esc(e.documento)} · ${esc(e.grupo || "")}</span></span></button>`
              )
              .join("")}</div>`
          : '<p class="ox-vacio-chico">Sin resultados.</p>';
        contenedor.querySelectorAll("[data-or-elegir]").forEach((b) =>
          b.addEventListener("click", () => orVincular(Number(input.dataset.orVincularInput), Number(b.dataset.orElegir)))
        );
      } catch {
        contenedor.innerHTML = '<p class="ox-vacio-chico">No se pudo buscar.</p>';
      }
    }, 300);
  });
}

// =============================================================================
// ORIENTACIÓN POR ESTUDIANTE
// =============================================================================

async function renderOrPorEstudiante() {
  if (orEstudianteSel) return renderOrPerfil();
  app.innerHTML = orCargandoHtml("Cargando...");
  let casos;
  try {
    casos = await api("/api/diagnosticos/casos");
  } catch (e) {
    app.innerHTML = orErrorHtml(e, "No tienes permiso para ver orientación por estudiante.");
    return;
  }

  // Estudiantes con casos activos, agrupados (uno por persona).
  const porEstudiante = new Map();
  for (const c of casos.filter((x) => x.estado !== "cerrado")) {
    if (!porEstudiante.has(c.estudiante_id)) porEstudiante.set(c.estudiante_id, { ...c, n: 0, proximo: null });
    const e = porEstudiante.get(c.estudiante_id);
    e.n++;
    if (c.proximo_seguimiento && (!e.proximo || c.proximo_seguimiento < e.proximo)) e.proximo = c.proximo_seguimiento;
  }
  const enSeguimiento = [...porEstudiante.values()].sort((a, b) => (a.proximo || "9999").localeCompare(b.proximo || "9999"));

  app.innerHTML = `
    <header class="ox-cabecera">
      <div>
        <p class="dx-eyebrow">Orientación escolar</p>
        <h2>Perfil por estudiante</h2>
        <p class="subtitulo-pagina">Casos, seguimientos y todo lo que el diagnóstico del director de grupo registra de un estudiante.</p>
      </div>
      <div class="ox-cabecera-acciones">
        ${tienePermiso("diagnosticos.observar") ? '<button type="button" class="boton" data-or-agregar>+ Agregar estudiante al seguimiento</button>' : ""}
      </div>
    </header>
    <div class="ox-buscador ox-buscador-grande">
      <input type="search" id="or-est-buscar" placeholder="Buscar por nombre o número de documento..." autocomplete="off" aria-label="Buscar estudiante" value="${esc(orEstudianteTexto)}" />
    </div>
    <div id="or-est-resultados"></div>
    ${orAgendaHtml(casos, true)}
    <section class="ox-seccion">
      <h3 class="ox-h3">Estudiantes con casos activos <span class="ox-tenue">${enSeguimiento.length}</span></h3>
      ${
        enSeguimiento.length
          ? `<div class="ox-picker ox-picker-plano">${enSeguimiento
              .map(
                (e) => `
                <button type="button" class="ox-picker-item" data-or-perfil-id="${e.estudiante_id}">
                  ${orAvatar(e.estudiante_nombre, null)}
                  <span class="ox-picker-texto"><strong>${esc(e.estudiante_nombre)}</strong><span>${esc(e.estudiante_documento)} · ${esc(e.grado_nombre)}</span></span>
                  <span class="ox-picker-badges"><span class="ox-chip ox-tono-ambar">${e.n} caso${e.n === 1 ? "" : "s"}</span>${e.proximo ? orProximoHtml(e.proximo) : ""}</span>
                </button>`
              )
              .join("")}</div>`
          : '<div class="ox-vacio"><p>Nadie tiene casos activos por ahora. Busca un estudiante arriba para ver su perfil o abrirle un caso.</p></div>'
      }
    </section>`;

  const input = document.getElementById("or-est-buscar");
  const zona = document.getElementById("or-est-resultados");
  let timer = null;
  const buscar = () => {
    clearTimeout(timer);
    orEstudianteTexto = input.value;
    const texto = input.value.trim();
    if (texto.length < 3) {
      zona.innerHTML = texto ? '<p class="ox-vacio-chico">Escribe al menos 3 letras.</p>' : "";
      return;
    }
    zona.innerHTML = orCargandoHtml("Buscando...");
    timer = setTimeout(async () => {
      let items = [];
      try {
        items = (await api(`/api/estudiantes/pagina?q=${encodeURIComponent(texto)}&por_pagina=12`)).items;
      } catch {
        zona.innerHTML = '<p class="ox-vacio-chico">No se pudo buscar.</p>';
        return;
      }
      if (input.value.trim() !== texto) return;
      zona.innerHTML = items.length
        ? `<div class="ox-picker ox-picker-resultados">${items
            .map(
              (e) => `
              <button type="button" class="ox-picker-item" data-or-perfil-id="${e.id}">
                ${orAvatar(orNombreEstudiante(e), e.genero)}
                <span class="ox-picker-texto"><strong>${esc(orNombreEstudiante(e))}</strong><span>${esc(e.documento)} · ${esc(e.grupo || "")}${e.estado !== "ACTIVO" ? ` · ${esc(e.estado)}` : ""}</span></span>
                <span class="ox-chevron-der" aria-hidden="true"></span>
              </button>`
            )
            .join("")}</div>`
        : `<div class="ox-vacio"><p>Nadie coincide con "${esc(texto)}".</p>${
            tienePermiso("estudiantes.crear")
              ? '<p>Si es un estudiante nuevo, regístralo con <b>+ Agregar estudiante al seguimiento</b> → "Registrar estudiante nuevo".</p>'
              : "<p>Si es un estudiante nuevo, pide a secretaría que lo matricule.</p>"
          }</div>`;
      zona.querySelectorAll("[data-or-perfil-id]").forEach((b) => b.addEventListener("click", () => orIrAPerfil(Number(b.dataset.orPerfilId), null)));
    }, 300);
  };
  input.addEventListener("input", buscar);
  if (orEstudianteTexto.trim().length >= 3) buscar();
  input.focus();

  app.querySelectorAll(".ox-seccion [data-or-perfil-id]").forEach((b) => b.addEventListener("click", () => orIrAPerfil(Number(b.dataset.orPerfilId), null)));
  app.querySelector("[data-or-agregar]")?.addEventListener("click", () =>
    orAbrirFlujoCaso({ alGuardar: (caso) => orIrAPerfil(caso.estudiante_id, null) })
  );
  orWireIrCaso(app);
}

async function renderOrPerfil() {
  if (!orEstudianteResumen) app.innerHTML = orCargandoHtml("Cargando perfil...");
  try {
    if (!orEstudianteResumen) orEstudianteResumen = await api(`/api/diagnosticos/estudiantes/${orEstudianteSel}`);
    // Casos que llegan desplegados (desde la agenda o "Ver caso"): se trae su detalle.
    const faltan = orEstudianteResumen.casos.filter((c) => orCasosExpandidos.has(c.id) && !orCasosDetalle.has(c.id));
    await Promise.all(faltan.map(async (c) => orCasosDetalle.set(c.id, await api(`/api/diagnosticos/casos/${c.id}`))));
  } catch (e) {
    app.innerHTML = orErrorHtml(e, "No tienes permiso para ver este perfil.");
    return;
  }
  orPintarPerfil();
}

function orPintarPerfil() {
  const r = orEstudianteResumen;
  const e = r.estudiante;
  const activos = r.casos.filter((c) => c.estado !== "cerrado");
  const cerrados = r.casos.length - activos.length;
  const seguimientos = r.casos.reduce((s, c) => s + c.total_seguimientos, 0);
  const proximos = activos.map((c) => c.proximo_seguimiento).filter(Boolean).sort();
  const edad = orEdad(e.fecha_nacimiento);
  const puedeCaso = tienePermiso("diagnosticos.observar");

  // Menciones del Excel agrupadas por versión de diagnóstico (grado + periodo).
  const porDiag = new Map();
  for (const m of r.menciones) {
    if (!porDiag.has(m.diagnostico_id)) porDiag.set(m.diagnostico_id, { titulo: m.grado_nombre, periodo: m.periodo || orFechaLarga(m.fecha_diligenciado) || "sin fecha", items: [] });
    porDiag.get(m.diagnostico_id).items.push(m);
  }
  const diagnosticos = [...porDiag.values()]
    .map(
      (d) => `
      <li class="ox-linea-item">
        <span class="ox-linea-punto"></span>
        <div>
          <p class="ox-linea-meta"><b>${esc(d.periodo)}</b> · Diagnóstico de ${esc(d.titulo)}</p>
          ${d.items
            .map((m) => `<div class="ox-mencion">${orChipCategoria(m.categoria)}<p>${esc(m.texto)}</p>${m.caso_id ? '<span class="ox-tenue">Ya tiene un caso abierto a partir de esto.</span>' : ""}</div>`)
            .join("")}
        </div>
      </li>`
    )
    .join("");

  const migas = orPerfilDesdeGrupo
    ? `<button type="button" data-or-migas-grado>Orientación por grado</button><span aria-hidden="true">/</span><button type="button" data-or-migas-grupo>${esc(orPerfilDesdeGrupo)}</button>`
    : '<button type="button" data-or-migas-est>Perfil por estudiante</button>';

  app.innerHTML = `
    <nav class="ox-migas" aria-label="Ruta">${migas}<span aria-hidden="true">/</span><span>${esc(e.nombre_completo)}</span></nav>
    <header class="ox-cabecera ox-perfil-cab">
      <div class="ox-cabecera-titulo">
        ${orAvatar(e.nombre_completo, e.genero, true)}
        <div>
          <p class="dx-eyebrow">Perfil de orientación</p>
          <h2>${esc(e.nombre_completo)}</h2>
          <p class="subtitulo-pagina">${esc(e.tipo_documento || "Doc.")} ${esc(e.documento)} · ${esc(e.grupo)}${edad !== null ? ` · ${edad} años` : ""}</p>
          <p class="ox-tenue">${esc(e.sede_nombre || "Sin sede")}
            ${e.estado !== "ACTIVO" ? ` <span class="badge-estado alerta">${esc(e.estado)}</span>` : ""}
            ${e.retirado ? ' <span class="badge-estado naranja">Marcado como retirado</span>' : ""}</p>
        </div>
      </div>
      <div class="ox-cabecera-acciones">
        ${e.sede_id ? '<button type="button" class="boton secundario" data-or-ver-grupo>Ver su grupo</button>' : ""}
        ${tienePermiso("diagnosticos.exportar") ? '<button type="button" class="boton secundario" data-or-pdf-est>Imprimir informe</button>' : ""}
        ${puedeCaso ? '<button type="button" class="boton" data-or-nuevo-caso>+ Nuevo caso</button>' : ""}
      </div>
    </header>
    <div class="ox-kpis">
      ${orKpi(activos.length, "Casos activos", activos.length ? "ambar" : "")}
      ${orKpi(cerrados, "Casos cerrados")}
      ${orKpi(seguimientos, "Seguimientos registrados")}
      ${orKpi(r.menciones.length, "Situaciones en diagnósticos")}
      ${orKpi(proximos.length ? orProximoHtml(proximos[0]) : "—", "Próximo seguimiento", proximos.length && orDiasHasta(proximos[0]) < 0 ? "rojo" : "")}
    </div>
    <section class="ox-seccion">
      <h3 class="ox-h3">Casos de orientación</h3>
      ${
        r.casos.length
          ? `<div class="ox-casos">${r.casos.map((c) => orCasoCardHtml(c, { mostrarEstudiante: false })).join("")}</div>`
          : `<div class="ox-vacio"><p><b>Sin casos registrados.</b></p>${
              puedeCaso ? '<p><button type="button" class="boton" data-or-nuevo-caso>+ Abrir el primer caso</button></p>' : ""
            }</div>`
      }
    </section>
    <section class="ox-seccion">
      <h3 class="ox-h3">Lo que registra el diagnóstico del director de grupo</h3>
      ${
        diagnosticos
          ? `<ol class="ox-linea">${diagnosticos}</ol>`
          : '<div class="ox-vacio"><p>El diagnóstico importado no menciona a este estudiante (o su nombre todavía no se ha vinculado en "Revisión de nombres").</p></div>'
      }
    </section>`;

  app.querySelector("[data-or-migas-est]")?.addEventListener("click", () => {
    orEstudianteSel = null;
    render();
  });
  app.querySelector("[data-or-migas-grado]")?.addEventListener("click", () => {
    orEstudianteSel = null;
    orGradoSel = null;
    orVista = "diagnostico-grados";
    orMarcarTab();
    render();
  });
  app.querySelector("[data-or-migas-grupo]")?.addEventListener("click", () => {
    orEstudianteSel = null;
    orVista = "diagnostico-grados";
    orGrupoDetalle = null;
    orMarcarTab();
    render();
  });
  app.querySelector("[data-or-ver-grupo]")?.addEventListener("click", () => orAbrirGrupo(e.sede_id, e.grado, e.curso));
  app.querySelector("[data-or-pdf-est]")?.addEventListener("click", (ev) => orAbrirPdf(`/api/diagnosticos/estudiantes/${e.id}/pdf`, ev.currentTarget));
  app.querySelectorAll("[data-or-nuevo-caso]").forEach((b) =>
    b.addEventListener("click", () =>
      orAbrirFlujoCaso({
        estudiante: e,
        alGuardar: () => {
          orEstudianteResumen = null;
          renderOrPerfil();
        },
      })
    )
  );
  orWireCasoCards(app, (refrescar) => {
    if (refrescar) {
      orEstudianteResumen = null;
      renderOrPerfil();
    } else orPintarPerfil();
  });
}
