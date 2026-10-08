// --- Vista: Análisis académico (comparación entre períodos) -----------------
//
// Rediseño (24/09/2026): la pantalla EXPLICA primero, MUESTRA después y
// deja PROFUNDIZAR al final. Cada bloque responde una pregunta ("¿estamos
// mejorando?", "¿dónde está el problema?", "¿a quién afecta?") con una frase
// calculada de los datos, y debajo la gráfica o tabla que la demuestra. Todo
// número abre la lista exacta que lo compone.
//
// Datos: /api/boletines/comparacion/panorama (resumen, lectura, evolución,
// áreas, grados, grupos, sedes y hallazgos en una sola llamada — ver
// comparacion_academica.panorama) y /estudiantes (la lista exacta detrás de
// cada número). Dos poblaciones, SIEMPRE dichas en pantalla:
//  - "mismos estudiantes": nota en ambos períodos → todo lo que es CAMBIO.
//  - "hoy": todos con nota en el período actual → el estado actual.
// Genérico en períodos (P1→P2 hoy, P3/P4 cuando existan) sin tocar código.
// No hay ranking de docentes ni diagnóstico de estudiantes.

let anzVista = "mejorar"; // mejorar | anio | fortalezas | resumen | areas | grados | docentes | estudiantes | actitudinal
let anzPeriodosDisponibles = null;
let anzAnioBase = null, anzPeriodoBase = null, anzAnioComparado = null, anzPeriodoComparado = null;
// Por ahora el análisis es solo de la Sede #01 I.E.T.A.B.A. (id 1): las
// sedes rurales aún no tienen el Período 1 importado, así que no se pueden
// comparar. Para habilitar otra sede, agregar su id aquí.
const ANZ_SEDES_HABILITADAS = [1];
const ANZ_SEDE_PRINCIPAL = 1;
let anzSedeId = ANZ_SEDE_PRINCIPAL, anzGrado = null, anzCurso = null, anzAreaId = null, anzDocenteId = null;
let anzEstado = "ACTIVO"; // ACTIVO | TODOS
let anzConfig = null; // overrides de umbrales; null = defaults del backend
let anzCatalogo = { sedes: [], areas: [], docentes: [] };
let anzMasFiltros = false;
let anzGruposConocidos = {}; // "sede|grado" -> [{curso, nombre}] (para el filtro Grupo)
const anzCache = new Map(); // url -> Promise: ir y volver entre pestañas no vuelve a pedir
let anzPeticion = 0; // descarta respuestas viejas si el filtro cambió mientras cargaba
let anzTrasPintar = null; // gráficas que se dibujan cuando el HTML ya está en el DOM
let anzChartEvolucion = null;
let anzOrdenAreas = "dificultad", anzOrdenGrados = "dificultad", anzAgrupar = "grado";
let anzEstCambio = "atencion", anzEstModo = "estudiante", anzEstBuscar = "", anzEstLimite = 100, anzEstDatos = null;
let anzDocModo = "asignaturas", anzAsigFiltro = { docente: "", area: "", grado: "" }, anzAsigAbierta = null;

// Mismos defaults que schemas.ConfigComparacion y mismas constantes de
// lectura que comparacion_academica (TENDENCIA_*, HALLAZGO_MIN_*).
const ANZ_DEFAULTS = {
  nivel_bajo_hasta: 2.9, nivel_basico_hasta: 3.9, nivel_alto_hasta: 4.5,
  umbral_mejora: 0.3, umbral_mejora_significativa: 1.0, umbral_descenso: 0.3, umbral_descenso_significativo: 1.0,
};
const ANZ_TENDENCIA_ESTABLE = 0.05, ANZ_CAMBIO_BRUSCO = 0.3;
const ANZ_MIN_AREA = 20, ANZ_MIN_GRUPO = 10;

const NOMBRES_CATEGORIA_VARIACION = {
  MEJORA_SIGNIFICATIVA: "Mejora significativa",
  MEJORA: "Mejora",
  ESTABLE: "Estable",
  DESCENSO: "Descenso",
  DESCENSO_SIGNIFICATIVO: "Descenso significativo",
};
const NOMBRES_NIVEL = { BAJO: "Bajo", BASICO: "Básico", ALTO: "Alto", SUPERIOR: "Superior" };
const ANZ_NIVELES = ["BAJO", "BASICO", "ALTO", "SUPERIOR"];
// Escala de niveles (validada con el verificador de paletas): dos brazos de
// una sola tinta — naranja por debajo de lo esperado, azul por encima — con
// luminosidad ordenada. Siempre con leyenda/etiqueta: nunca solo color.
const ANZ_COLOR_NIVEL = { BAJO: "#c2410c", BASICO: "#eda067", ALTO: "#93b7ec", SUPERIOR: "#1d4ed8" };
const ANZ_TINTA_NIVEL = { BAJO: "#ffffff", BASICO: "#172033", ALTO: "#172033", SUPERIOR: "#ffffff" };
// Cambio: colores de estado de la app (bien / neutro / mal), con texto al lado.
const ANZ_COLOR_CAMBIO = { mejoraron: "#16a34a", estables: "#cbd2dc", empeoraron: "#dc2626" };
const ANZ_DIVISIONES = { 1: "Uno", 2: "Dos", 3: "Tres", 4: "Cuatro", 5: "Cinco", 6: "Seis", 7: "Siete", 8: "Ocho" };

const ANZ_VISTAS = [
  ["mejorar", "¿Quién debe mejorar?"], ["anio", "¿Pierden el año?"], ["fortalezas", "Fortalezas y debilidades"], ["resumen", "Resumen"], ["areas", "Áreas"], ["grados", "Grados y grupos"],
  ["docentes", "Docentes y materias"], ["estudiantes", "Estudiantes"], ["actitudinal", "Actitudinal (DESM)"],
];

// --- Utilidades de formato y lectura ----------------------------------------

function anzCfg() {
  return { ...ANZ_DEFAULTS, ...(anzConfig || {}) };
}
function anzCorte() {
  return (anzCfg().nivel_bajo_hasta + 0.1).toFixed(1); // inicio de Básico (3.0)
}
function anzRangos() {
  const c = anzCfg();
  const d = (v) => v.toFixed(1);
  return {
    BAJO: `menos de ${d(c.nivel_bajo_hasta + 0.1)}`,
    BASICO: `${d(c.nivel_bajo_hasta + 0.1)} a ${d(c.nivel_basico_hasta)}`,
    ALTO: `${d(c.nivel_basico_hasta + 0.1)} a ${d(c.nivel_alto_hasta)}`,
    SUPERIOR: `${d(c.nivel_alto_hasta + 0.1)} a 5.0`,
  };
}
function anzPB() {
  return `Período ${anzPeriodoBase}${anzAnioBase !== anzAnioComparado ? ` de ${anzAnioBase}` : ""}`;
}
function anzPC() {
  return `Período ${anzPeriodoComparado}${anzAnioBase !== anzAnioComparado ? ` de ${anzAnioComparado}` : ""}`;
}
function anzF(v, d = 2) {
  return v === null || v === undefined ? "—" : Number(v).toFixed(d);
}
// Con signo y menos tipográfico ("−0.21"); 0 sin signo.
function anzS(v, d = 2) {
  if (v === null || v === undefined) return "—";
  const t = Math.abs(v).toFixed(d);
  if (Number(t) === 0) return t;
  return v > 0 ? `+${t}` : `−${t}`;
}
function anzPct(n, total) {
  return total ? (n / total) * 100 : null;
}
function anzP(v) {
  return v === null || v === undefined ? "—" : `${Math.round(v)}%`;
}
function anzPl(n, singular, plural) {
  return `${n} ${n === 1 ? singular : plural}`;
}
function anzNombreGrado(g) {
  const x = NOMBRES_GRADOS.find(([n]) => n === g);
  return x ? x[1] : `Grado «${g}» (dato inválido)`;
}
function anzNombreGrupo(grado, curso) {
  const g = anzNombreGrado(grado);
  return curso ? `${g} - ${ANZ_DIVISIONES[curso] || curso}` : g;
}
function anzSede(nombre) {
  return String(nombre || "").replace(/\s+/g, " ").trim();
}
function anzNombreArea(id) {
  return anzCatalogo.areas.find((a) => a.id === Number(id))?.nombre || "Área";
}
function anzClaseCambio(d) {
  return d === null || d === undefined ? "" : d < 0 ? "anz-baja" : d > 0 ? "anz-sube" : "";
}

function paramsComparacion(extra) {
  const p = new URLSearchParams({
    anio_base: anzAnioBase, periodo_base: anzPeriodoBase,
    anio_comparado: anzAnioComparado, periodo_comparado: anzPeriodoComparado,
  });
  if (anzSedeId) p.set("sede_id", anzSedeId);
  if (anzGrado !== null) p.set("grado", anzGrado);
  if (anzCurso !== null) p.set("curso", anzCurso);
  if (anzAreaId) p.set("area_id", anzAreaId);
  if (anzDocenteId) p.set("docente_id", anzDocenteId);
  if (anzEstado) p.set("estado", anzEstado);
  if (anzConfig) for (const [k, v] of Object.entries(anzConfig)) p.set(k, v);
  if (extra) for (const [k, v] of Object.entries(extra)) p.set(k, v);
  return p;
}

function anzGet(url) {
  if (!anzCache.has(url)) {
    const promesa = api(url).catch((e) => {
      anzCache.delete(url); // un error no se queda guardado
      throw e;
    });
    anzCache.set(url, promesa);
    if (anzCache.size > 40) anzCache.delete(anzCache.keys().next().value);
  }
  return anzCache.get(url);
}
function anzPanorama() {
  return anzGet(`/api/boletines/comparacion/panorama?${paramsComparacion()}`);
}

function anzOrdenPeriodosValido() {
  return anzAnioBase < anzAnioComparado || (anzAnioBase === anzAnioComparado && anzPeriodoBase < anzPeriodoComparado);
}

// --- Entrada: períodos, catálogos y esqueleto de la pantalla ---------------

async function renderAnalisis() {
  anzCache.clear(); // al entrar a la vista, datos frescos (pudo haber un import nuevo)
  app.innerHTML = '<p class="estado-carga">Cargando análisis académico...</p>';
  try {
    anzPeriodosDisponibles = await api("/api/boletines/comparacion/periodos-disponibles");
  } catch (e) {
    app.innerHTML = `<div class="alerta-caja">${
      e.status === 401 || e.status === 403
        ? "No tienes permiso para ver esta sección."
        : "No se pudo cargar el análisis académico: " + esc(e.message)
    }</div>`;
    return;
  }

  if (anzPeriodosDisponibles.length < 2) {
    const hay = anzPeriodosDisponibles.map((p) => `Período ${p.periodo} de ${p.anio_lectivo}`).join(", ");
    app.innerHTML = `
      <div class="pagina-header"><div><h1>Análisis académico</h1></div></div>
      <div class="ox-vacio">
        <p><b>Todavía no hay dos períodos para comparar.</b></p>
        <p>${anzPeriodosDisponibles.length ? `Hoy solo hay notas importadas del ${esc(hay)}.` : "Aún no se ha importado ninguna nota de SAPRED."}
        Cuando se importe el siguiente período desde Boletines, esta pantalla se llena sola.</p>
      </div>`;
    return;
  }

  const existe = (a, p) => anzPeriodosDisponibles.some((x) => x.anio_lectivo === a && x.periodo === p);
  if (!existe(anzAnioBase, anzPeriodoBase) || !existe(anzAnioComparado, anzPeriodoComparado)) {
    const [pb, pc] = anzPeriodosDisponibles.slice(-2);
    anzAnioBase = pb.anio_lectivo; anzPeriodoBase = pb.periodo;
    anzAnioComparado = pc.anio_lectivo; anzPeriodoComparado = pc.periodo;
  }

  const [sedes, areas, docentes] = await Promise.all([
    obtenerSedes().catch(() => []),
    api("/api/areas").catch(() => []),
    api("/api/docentes").catch(() => []),
  ]);
  anzCatalogo = { sedes, areas: areas.filter((a) => a.codigo !== "DESM"), docentes };

  app.innerHTML = `
    <div class="pagina-header">
      <div>
        <h1>Análisis académico</h1>
        <p class="subtitulo-pagina">Cómo va el rendimiento, qué cambió entre períodos y dónde conviene mirar. Calculado con las notas importadas de SAPRED.</p>
      </div>
      <div class="anz-cab-acciones">
      <button type="button" class="boton" data-anz-exponer>${icono("presentation")} Exponer</button>
      ${tienePermiso("boletines.exportar") ? `<button type="button" class="boton secundario" id="anz-exportar">${icono("download")} Exportar a Excel</button>` : ""}
      </div>
    </div>
    <div id="anz-filtros-host"></div>
    <div id="anz-subnav-host"></div>
    <div id="anz-contenido" aria-live="polite"></div>`;
  anzPintarFiltros();
  anzPintarSubnav();
  await cargarSubvistaAnalisis();
}

// --- Filtros: una sola barra, compacta; lo avanzado se abre aparte ----------

function anzOpcionesAreas() {
  // Si dos áreas se llaman igual (preescolar: COG/DICOG), se muestra el código.
  const cuenta = {};
  anzCatalogo.areas.forEach((a) => (cuenta[a.nombre] = (cuenta[a.nombre] || 0) + 1));
  return anzCatalogo.areas
    .map((a) => `<option value="${a.id}" ${Number(anzAreaId) === a.id ? "selected" : ""}>${esc(a.nombre)}${cuenta[a.nombre] > 1 ? ` (${esc(a.codigo)})` : ""}</option>`)
    .join("");
}

function anzOpcionesGrupo() {
  if (anzGrado === null) return '<option value="">Elige un grado primero</option>';
  const conocidos = anzGruposConocidos[`${anzSedeId || ""}|${anzGrado}`];
  const cursos = conocidos?.length ? conocidos : [1, 2, 3, 4, 5, 6].map((c) => ({ curso: c, nombre: anzNombreGrupo(anzGrado, c) }));
  return `<option value="">Todos los grupos</option>${cursos
    .map((c) => `<option value="${c.curso}" ${anzCurso === c.curso ? "selected" : ""}>${esc(c.nombre)}</option>`)
    .join("")}`;
}

function anzChipsActivosHtml() {
  const chips = [];
  const sede = anzCatalogo.sedes.find((s) => s.id === Number(anzSedeId));
  // La sede es fija por ahora: no se ofrece quitarla.
  if (anzSedeId && anzSedeId !== ANZ_SEDE_PRINCIPAL) chips.push(["sede", `Sede: ${anzSede(sede?.nombre || anzSedeId)}`]);
  if (anzGrado !== null) chips.push(["grado", `Grado: ${anzNombreGrado(anzGrado)}`]);
  if (anzCurso !== null) chips.push(["curso", `Grupo: ${anzNombreGrupo(anzGrado, anzCurso)}`]);
  if (anzAreaId) chips.push(["area", `Área: ${anzNombreArea(anzAreaId)}`]);
  if (anzDocenteId) {
    const d = anzCatalogo.docentes.find((x) => x.id === Number(anzDocenteId));
    chips.push(["docente", `Docente: ${d?.nombre_completo || anzDocenteId}`]);
  }
  if (anzEstado === "TODOS") chips.push(["estado", "Incluye retirados"]);
  if (anzConfig) chips.push(["umbrales", "Umbrales personalizados"]);
  if (!chips.length) return "";
  return `<div class="anz-chips-activos" aria-label="Filtros aplicados">
    <span class="anz-chips-titulo">Viendo:</span>
    ${chips
      .map(([k, t]) => `<span class="anz-chip-activo">${esc(t)}<button type="button" data-anz-quitar="${k}" aria-label="Quitar ${esc(t)}">${icono("x")}</button></span>`)
      .join("")}
    ${chips.length > 1 ? '<button type="button" class="boton-texto-chico" data-anz-quitar="todos">Quitar todos</button>' : ""}
  </div>`;
}

function anzPintarFiltros() {
  const host = document.getElementById("anz-filtros-host");
  if (!host) return;
  const opcionesPeriodo = (anio, per) =>
    anzPeriodosDisponibles
      .map((p) => `<option value="${p.anio_lectivo}|${p.periodo}" ${p.anio_lectivo === anio && p.periodo === per ? "selected" : ""}>Período ${p.periodo} · ${p.anio_lectivo}</option>`)
      .join("");
  const avanzados = [anzCurso !== null, !!anzDocenteId, anzEstado === "TODOS", !!anzConfig].filter(Boolean).length;
  host.innerHTML = `
    <section class="anz-filtros" aria-label="Filtros del análisis">
      <div class="anz-filtros-fila">
        <label class="anz-filtro anz-filtro-periodos">
          <span>Comparar ${iconoAyuda("El período anterior contra el actual. Solo aparecen los períodos que ya tienen notas importadas de SAPRED; el año va en cada período.")}</span>
          <span class="anz-periodos">
            <select id="anz-periodo-base" aria-label="Período anterior">${opcionesPeriodo(anzAnioBase, anzPeriodoBase)}</select>
            <span class="anz-flecha" aria-hidden="true">→</span>
            <select id="anz-periodo-comparado" aria-label="Período actual">${opcionesPeriodo(anzAnioComparado, anzPeriodoComparado)}</select>
          </span>
        </label>
        <label class="anz-filtro"><span>Sede</span>
          <select id="anz-sede">
            ${anzCatalogo.sedes
              .map((s) => {
                const activa = ANZ_SEDES_HABILITADAS.includes(s.id);
                return `<option value="${s.id}" ${Number(anzSedeId) === s.id ? "selected" : ""} ${activa ? "" : "disabled"}>${esc(anzSede(s.nombre))}${activa ? "" : " (próximamente)"}</option>`;
              })
              .join("")}
          </select></label>
        <label class="anz-filtro"><span>Grado</span>
          <select id="anz-grado"><option value="">Todos los grados</option>
            ${NOMBRES_GRADOS.map(([g, n]) => `<option value="${g}" ${anzGrado === g ? "selected" : ""}>${n}</option>`).join("")}
          </select></label>
        <label class="anz-filtro"><span>Área</span>
          <select id="anz-area"><option value="">Todas las áreas</option>${anzOpcionesAreas()}</select></label>
        <button type="button" class="anz-mas-filtros${anzMasFiltros ? " abierto" : ""}" data-anz-mas-filtros aria-expanded="${anzMasFiltros}" aria-controls="anz-filtros-avanzados">
          ${icono("sliders-horizontal")} Más filtros${avanzados ? ` <span class="segmentado-num">${avanzados}</span>` : ""}
        </button>
      </div>
      <div class="anz-filtros-avanzados" id="anz-filtros-avanzados" ${anzMasFiltros ? "" : "hidden"}>
        <label class="anz-filtro"><span>Grupo</span>
          <select id="anz-curso" ${anzGrado === null ? "disabled" : ""}>${anzOpcionesGrupo()}</select></label>
        <label class="anz-filtro"><span>Docente</span>
          <select id="anz-docente"><option value="">Todos los docentes</option>
            ${anzCatalogo.docentes.map((d) => `<option value="${d.id}" ${Number(anzDocenteId) === d.id ? "selected" : ""}>${esc(d.nombre_completo)}</option>`).join("")}
          </select></label>
        <label class="anz-filtro"><span>Estudiantes</span>
          <select id="anz-estado">
            <option value="ACTIVO" ${anzEstado === "ACTIVO" ? "selected" : ""}>Solo activos</option>
            <option value="TODOS" ${anzEstado === "TODOS" ? "selected" : ""}>Incluir retirados</option>
          </select></label>
        <details class="anz-umbrales">
          <summary>Umbrales de niveles y de cambio</summary>
          ${configAvanzadaHtml()}
        </details>
      </div>
      ${anzChipsActivosHtml()}
    </section>`;
}

function configAvanzadaHtml() {
  const c = anzCfg();
  const campo = (id, etiqueta) =>
    `<label class="anz-filtro"><span>${etiqueta}</span><input type="number" step="0.1" min="0" max="5" id="anz-cfg-${id}" value="${c[id]}" /></label>`;
  return `
    <p class="anz-sub">Niveles según el promedio (escala 1.0 a 5.0) y cuánto debe subir o bajar un estudiante para contar como cambio. Cambiarlos recalcula toda la pantalla.</p>
    <div class="anz-umbrales-campos">
      ${campo("nivel_bajo_hasta", "Bajo hasta")}
      ${campo("nivel_basico_hasta", "Básico hasta")}
      ${campo("nivel_alto_hasta", "Alto hasta (resto = Superior)")}
      ${campo("umbral_mejora", "Mejora desde")}
      ${campo("umbral_mejora_significativa", "Mejora significativa desde")}
      ${campo("umbral_descenso", "Descenso desde")}
      ${campo("umbral_descenso_significativo", "Descenso significativo desde")}
    </div>
    <div class="anz-umbrales-acciones">
      <button type="button" class="boton secundario boton-chico" id="anz-cfg-aplicar">Aplicar</button>
      <button type="button" class="boton-texto-chico" id="anz-cfg-restablecer">Restablecer</button>
    </div>`;
}

function anzPintarSubnav() {
  const host = document.getElementById("anz-subnav-host");
  if (!host) return;
  host.innerHTML = `<div class="segmentado anz-subnav" role="group" aria-label="Sección del análisis">${ANZ_VISTAS.map(
    ([id, nombre]) => `<button type="button" class="segmentado-btn ${anzVista === id ? "activo" : ""}" data-anz-vista="${id}" aria-pressed="${anzVista === id}">${nombre}</button>`
  ).join("")}</div>`;
}

// Cambia filtros/vista y recarga. Un clic en un área, un grado o un período
// es solo esto: agregar un filtro y volver a contar la historia.
function anzAplicar(c, vista) {
  const num = (v) => (v === "" || v === null || v === undefined ? null : Number(v));
  if (c.base) { anzAnioBase = c.base.anio_lectivo; anzPeriodoBase = c.base.periodo; }
  if (c.comparado) { anzAnioComparado = c.comparado.anio_lectivo; anzPeriodoComparado = c.comparado.periodo; }
  if ("sede_id" in c) {
    const s = num(c.sede_id);
    anzSedeId = s !== null && ANZ_SEDES_HABILITADAS.includes(s) ? s : ANZ_SEDE_PRINCIPAL;
    if (!("curso" in c)) anzCurso = null;
  }
  if ("grado" in c) { anzGrado = num(c.grado); if (!("curso" in c)) anzCurso = null; }
  if ("curso" in c) anzCurso = num(c.curso);
  if ("area_id" in c) anzAreaId = num(c.area_id);
  if ("docente_id" in c) anzDocenteId = num(c.docente_id);
  if ("estado" in c) anzEstado = c.estado;
  anzAsigAbierta = null;
  anzDocFicha = null;
  anzEstLimite = 100;
  if (vista) anzVista = vista;
  anzPintarFiltros();
  anzPintarSubnav();
  cargarSubvistaAnalisis();
  if (vista) document.getElementById("anz-filtros-host")?.scrollIntoView({ block: "start", behavior: "smooth" });
}

function anzIrVista(vista) {
  anzVista = vista;
  anzAsigAbierta = null;
  anzDocFicha = null;
  anzPintarSubnav();
  cargarSubvistaAnalisis();
}

async function cargarSubvistaAnalisis() {
  const cont = document.getElementById("anz-contenido");
  if (!cont) return;
  const turno = ++anzPeticion;
  anzTrasPintar = null;

  if (!anzOrdenPeriodosValido()) {
    cont.innerHTML = `<div class="ox-vacio"><p><b>El período anterior tiene que ser antes del actual.</b></p>
      <p>Elegiste ${esc(anzPB())} → ${esc(anzPC())}.</p>
      <button type="button" class="boton secundario boton-chico" data-anz-invertir>Invertir los períodos</button></div>`;
    return;
  }

  // Mientras carga se mantiene lo anterior atenuado (sin saltos de página).
  if (cont.innerHTML.trim()) cont.classList.add("anz-recargando");
  else cont.innerHTML = '<p class="estado-carga">Cargando...</p>';
  try {
    const html = await anzSubvistaHtml();
    if (turno !== anzPeticion) return;
    cont.innerHTML = html;
    if (anzTrasPintar) anzTrasPintar();
  } catch (e) {
    if (turno !== anzPeticion) return;
    cont.innerHTML = `<div class="alerta-caja">No se pudo cargar esta sección: ${esc(e.message)}</div>`;
  } finally {
    if (turno === anzPeticion) cont.classList.remove("anz-recargando");
  }
}

function anzSubvistaHtml() {
  if (anzVista === "areas") return anzAreasHtml();
  if (anzVista === "grados") return anzGradosHtml();
  if (anzVista === "docentes") return anzDocentesHtml();
  if (anzVista === "estudiantes") return anzEstudiantesHtml();
  if (anzVista === "actitudinal") return subvistaActitudinalHtml();
  if (anzVista === "mejorar") return anzMejorarHtml();
  if (anzVista === "fortalezas") return anzFortalezasHtml();
  if (anzVista === "anio") return anzPerderAnioHtml();
  return anzResumenHtml();
}

function anzRecordarGrupos(P) {
  // Para el filtro "Grupo": qué grupos existen de verdad en cada grado.
  if (anzGrado === null || anzCurso !== null) return;
  const clave = `${anzSedeId || ""}|${anzGrado}`;
  const vistos = new Map();
  P.grupos.forEach((g) => { if (g.curso) vistos.set(g.curso, g.nombre_grupo); });
  anzGruposConocidos[clave] = [...vistos.entries()].sort((a, b) => a[0] - b[0]).map(([curso, nombre]) => ({ curso, nombre }));
}

function anzVacioFiltroHtml() {
  return `<div class="ox-vacio">
    <p><b>No hay notas para este filtro.</b></p>
    <p>Ningún estudiante tiene notas del ${esc(anzPB())} ni del ${esc(anzPC())} con la combinación elegida (sede, grado, área, docente).</p>
    <button type="button" class="boton secundario boton-chico" data-anz-quitar="todos">Quitar filtros</button>
  </div>`;
}

// --- Piezas visuales reutilizables (HTML, no canvas: se pueden clicar,
//     leer con lector de pantalla y siempre llevan el número escrito) -------

// Barra 100% apilada. segs: [{valor, color, tinta, titulo, attr}]
function anzApilada(segs, { alta = false, etiquetas = false, aria = "" } = {}) {
  const total = segs.reduce((s, x) => s + (x.valor || 0), 0);
  if (!total) return "";
  return `<div class="anz-apilada${alta ? " anz-apilada-alta" : ""}" role="group" aria-label="${esc(aria)}">${segs
    .filter((s) => s.valor > 0)
    .map((s) => {
      const pct = (s.valor / total) * 100;
      // La etiqueta solo va adentro si cabe; si no, queda en la leyenda.
      const texto = etiquetas && pct >= 9 ? `${Math.round(pct)}%` : "";
      const estilo = `flex:${s.valor} 1 0;background:${s.color};color:${s.tinta || "#fff"}`;
      return s.attr
        ? `<button type="button" class="anz-seg anz-seg-clic" ${s.attr} style="${estilo}" title="${esc(s.titulo)}" aria-label="${esc(s.titulo)}">${texto}</button>`
        : `<span class="anz-seg" style="${estilo}" title="${esc(s.titulo)}">${texto}</span>`;
    })
    .join("")}</div>`;
}

function anzLeyenda(items) {
  return `<div class="anz-leyenda">${items
    .map((i) =>
      i.attr
        ? `<button type="button" class="anz-leyenda-item anz-clic" ${i.attr}><span class="anz-muestra" style="background:${i.color}"></span>${i.texto}</button>`
        : `<span class="anz-leyenda-item"><span class="anz-muestra" style="background:${i.color}"></span>${i.texto}</span>`
    )
    .join("")}</div>`;
}

// Lista de barras horizontales (muchas categorías). items: [{etiqueta,
// valor, texto, attr, poco, titulo}]. o: {min, max, color, divergente, marca}
function anzBarrasHtml(items, o) {
  const min = o.min || 0;
  return `<div class="anz-barras">${items
    .map((i) => {
      let barra;
      if (i.valor === null || i.valor === undefined) {
        barra = '<span class="anz-barra-nula">sin datos para comparar</span>';
      } else if (o.divergente) {
        const w = Math.min(50, (Math.abs(i.valor) / o.max) * 50); // tope: el borde de la pista
        const neg = i.valor < 0;
        const color = i.poco ? "#cbd2dc" : neg ? "#dc2626" : "#16a34a";
        barra = `<span class="anz-barra-cero"></span><span class="anz-barra ${neg ? "anz-barra-neg" : "anz-barra-pos"}" style="${neg ? "right" : "left"}:50%;width:${w}%;background:${color}"></span>`;
      } else {
        const w = Math.max(0, Math.min(100, ((i.valor - min) / (o.max - min)) * 100));
        const marca = o.marca !== undefined ? `<span class="anz-barra-marca" style="left:${((o.marca - min) / (o.max - min)) * 100}%"></span>` : "";
        barra = `<span class="anz-barra anz-barra-pos" style="left:0;width:${w}%;background:${i.poco ? "#cbd2dc" : o.color}"></span>${marca}`;
      }
      const cuerpo = `<span class="anz-barra-etq">${esc(i.etiqueta)}${i.poco ? ' <span class="anz-poco">pocos datos</span>' : ""}</span>
        <span class="anz-barra-pista">${barra}</span>
        <span class="anz-barra-valor">${i.texto}</span>`;
      return i.attr
        ? `<button type="button" class="anz-barra-fila anz-clic" ${i.attr} title="${esc(i.titulo || "")}">${cuerpo}</button>`
        : `<div class="anz-barra-fila">${cuerpo}</div>`;
    })
    .join("")}</div>`;
}

function anzSegmentado(nombre, opciones, actual, etiqueta) {
  return `<div class="anz-control"><span class="anz-control-etq">${etiqueta}</span><div class="segmentado" role="group" aria-label="${esc(etiqueta)}">${opciones
    .map(([v, t]) => `<button type="button" class="segmentado-btn ${actual === v ? "activo" : ""}" data-${nombre}="${v}" aria-pressed="${actual === v}">${t}</button>`)
    .join("")}</div></div>`;
}

// --- Resumen: ¿cómo estamos?, ¿mejoramos?, ¿dónde?, ¿a quién? -------------

async function anzResumenHtml() {
  const P = await anzPanorama();
  const r = P.resumen;
  anzRecordarGrupos(P);
  if (!r.total_estudiantes) return anzVacioFiltroHtml();
  anzTrasPintar = () => anzDibujarEvolucion(P.evolucion);
  return [
    anzLecturaHtml(P.lectura),
    anzGlosarioHtml(),
    anzAvisosDatosHtml(r),
    anzPoblacionHtml(r),
    anzKpisHtml(r),
    anzEvolucionHtml(P.evolucion),
    anzCambioHtml(r),
    anzDistribucionHtml(r),
    anzFocoHtml(P),
    anzHallazgosHtml(P.hallazgos),
  ].join("");
}

function anzContextoFiltro() {
  const partes = [];
  if (anzSedeId) partes.push(anzSede(anzCatalogo.sedes.find((s) => s.id === Number(anzSedeId))?.nombre));
  if (anzGrado !== null) partes.push(anzCurso !== null ? anzNombreGrupo(anzGrado, anzCurso) : anzNombreGrado(anzGrado));
  if (anzAreaId) partes.push(anzNombreArea(anzAreaId));
  if (anzDocenteId) partes.push(anzCatalogo.docentes.find((d) => d.id === Number(anzDocenteId))?.nombre_completo || "");
  return partes.length ? ` · ${partes.map(esc).join(" · ")}` : " · Todo el colegio";
}

function anzLecturaHtml(L) {
  const ico = { sube: "trending-up", baja: "trending-down", estable: "move-right", sin_datos: "circle-help" }[L.tendencia] || "info";
  return `
    <section class="anz-lectura anz-lectura-${L.tendencia}">
      ${icono(ico)}
      <div>
        <p class="dx-eyebrow">${esc(anzPB())} → ${esc(anzPC())}${anzContextoFiltro()}</p>
        <h2>${esc(L.titulo)}</h2>
        <p>${esc(L.frase)}</p>
      </div>
    </section>`;
}

function anzAvisosDatosHtml(r) {
  return (r.avisos_datos || [])
    .map((a) => `<div class="anz-aviso anz-aviso-ambar">${icono("triangle-alert")}<div><b>Revisar los datos.</b> ${esc(a)}</div></div>`)
    .join("");
}

function anzPoblacionHtml(r) {
  const n = r.estudiantes_comparables;
  const pb = anzPB(), pc = anzPC();
  const partes = [];
  partes.push(
    n
      ? `El <b>cambio</b> se mide con <b>${n}</b> ${n === 1 ? "estudiante que tiene" : "estudiantes que tienen"} notas en el ${pb} y en el ${pc}.`
      : `Ningún estudiante de este filtro tiene notas en el ${pb} y en el ${pc}, así que no se puede medir el cambio.`
  );
  if (r.solo_en_comparado) {
    partes.push(`Otros <b>${r.solo_en_comparado}</b> solo tienen notas del ${pc}: cuentan en «cómo estamos hoy» (${r.actual_evaluados} en total), no en el cambio.`);
  }
  if (r.solo_en_base) partes.push(`${anzPl(r.solo_en_base, "estudiante solo tiene", "estudiantes solo tienen")} notas del ${pb}.`);

  const sedesSin = r.sedes_sin_comparacion || [];
  const gruposSin = (r.grupos_sin_comparacion || []).filter((g) => !sedesSin.some((s) => g.includes(s)));
  const porQue =
    sedesSin.length || gruposSin.length
      ? `<details><summary>¿Quiénes no tienen notas del ${pb}?</summary>
          ${sedesSin.length ? `<p><b>${anzPl(sedesSin.length, "sede", "sedes")} sin notas del ${pb}:</b> ${esc(sedesSin.map(anzSede).join(" · "))}</p>` : ""}
          ${gruposSin.length ? `<p><b>${anzPl(gruposSin.length, "grupo", "grupos")} sin notas del ${pb}:</b> ${esc(gruposSin.map(anzSede).join(" · "))}</p>` : ""}
          <p>Si esas notas existen en SAPRED, se pueden importar desde Boletines. Mientras tanto, esos estudiantes no cuentan como mejora ni como descenso.</p>
        </details>`
      : "";
  const pocos = n && r.actual_evaluados && n / r.actual_evaluados < 0.6;
  return `<div class="anz-aviso${pocos ? " anz-aviso-ambar" : ""}">${icono("users")}<div><b>Con qué datos.</b> ${partes.join(" ")}${porQue}</div></div>`;
}

function anzDelta(valor, texto, subirEsBueno, umbral) {
  const dir = Math.abs(valor) < umbral ? "neutro" : (valor > 0) === subirEsBueno ? "bueno" : "malo";
  const flecha = Math.abs(valor) < umbral ? "minus" : valor > 0 ? "arrow-up" : "arrow-down";
  return `<span class="anz-delta anz-delta-${dir}">${icono(flecha)}${texto}</span>`;
}

function anzKpisHtml(r) {
  const n = r.estudiantes_comparables;
  const pb = anzPB(), pc = anzPC();

  // 1. Promedio
  let delta1 = "", explica1 = `Sin notas del ${pb} para comparar.`;
  if (n) {
    const d = r.variacion_promedio;
    delta1 = anzDelta(d, `${anzS(d)} vs. ${pb}`, true, ANZ_TENDENCIA_ESTABLE);
    const verbo = Math.abs(d) < ANZ_TENDENCIA_ESTABLE ? "Se mantuvo" : d > 0 ? "Subió" : "Bajó";
    explica1 = `${verbo}: los mismos ${n} estudiantes pasaron de ${anzF(r.promedio_base)} a ${anzF(r.promedio_comparado)}.`;
  }
  const k1 = `
    <div class="anz-kpi">
      <span class="anz-kpi-etq">Promedio general hoy ${iconoAyuda(`Primero se promedia cada estudiante (sus áreas del ${pc}) y luego se promedian los estudiantes: así nadie pesa más por tener más materias.`)}</span>
      <b class="anz-kpi-valor">${anzF(r.actual_promedio)}</b>
      <span class="anz-kpi-sub">${r.actual_evaluados} estudiantes con notas del ${pc}</span>
      ${delta1}
      <span class="anz-kpi-explica">${explica1}</span>
    </div>`;

  // 2. Desempeño bajo
  const pctHoy = anzPct(r.actual_n_bajo, r.actual_evaluados);
  let delta2 = "", explica2 = `Promedio menor a ${anzCorte()}.`;
  if (n) {
    const b0 = anzPct(r.distribucion_base.BAJO || 0, n), b1 = anzPct(r.distribucion_comparado.BAJO || 0, n);
    const pp = b1 - b0;
    delta2 = anzDelta(pp, `${pp > 0 ? "+" : pp < 0 ? "−" : ""}${Math.abs(pp).toFixed(0)} puntos vs. ${pb}`, false, 1);
    explica2 = `Entre los mismos ${n}: de ${anzP(b0)} a ${anzP(b1)} (${r.distribucion_base.BAJO || 0} → ${r.distribucion_comparado.BAJO || 0} estudiantes).`;
  }
  const k2 = `
    <button type="button" class="anz-kpi anz-kpi-clic" data-anz-cambio="bajo_actual">
      <span class="anz-kpi-etq">En desempeño bajo hoy</span>
      <b class="anz-kpi-valor">${anzP(pctHoy)}</b>
      <span class="anz-kpi-sub">${r.actual_n_bajo} de ${r.actual_evaluados} con promedio menor a ${anzCorte()}</span>
      ${delta2}
      <span class="anz-kpi-explica">${explica2}</span>
      <span class="anz-kpi-ir">Ver quiénes son ${icono("arrow-right")}</span>
    </button>`;

  // 3. Cambio individual
  let k3;
  if (n) {
    const frase =
      r.empeoraron > r.mejoraron * 1.5
        ? "Empeoraron más estudiantes de los que mejoraron."
        : r.mejoraron > r.empeoraron * 1.5
          ? "Mejoraron más estudiantes de los que empeoraron."
          : "Mejoras y descensos en cantidades parecidas.";
    const item = (clave, pct, cant, texto) =>
      `<button type="button" class="anz-trio-item" data-anz-cambio="${clave}"><b>${anzP(pct)}</b><span><span class="anz-muestra" style="background:${ANZ_COLOR_CAMBIO[clave]}"></span>${texto} <span class="prom-tenue">(${cant})</span></span></button>`;
    k3 = `
      <div class="anz-kpi">
        <span class="anz-kpi-etq">Cambio de cada estudiante</span>
        <div class="anz-trio">
          ${item("mejoraron", r.pct_mejoraron, r.mejoraron, "mejoraron")}
          ${item("estables", r.pct_estables, r.estables, "estables")}
          ${item("empeoraron", r.pct_empeoraron, r.empeoraron, "empeoraron")}
        </div>
        ${anzApilada(
          [
            { valor: r.mejoraron, color: ANZ_COLOR_CAMBIO.mejoraron, titulo: `${r.mejoraron} mejoraron` },
            { valor: r.estables, color: ANZ_COLOR_CAMBIO.estables, titulo: `${r.estables} estables` },
            { valor: r.empeoraron, color: ANZ_COLOR_CAMBIO.empeoraron, titulo: `${r.empeoraron} empeoraron` },
          ],
          { aria: "Proporción de estudiantes que mejoraron, se mantuvieron o empeoraron" }
        )}
        <span class="anz-kpi-sub">de ${n} estudiantes con ambos períodos</span>
        <span class="anz-kpi-explica">${frase}</span>
      </div>`;
  } else {
    k3 = `<div class="anz-kpi"><span class="anz-kpi-etq">Cambio de cada estudiante</span><b class="anz-kpi-valor">—</b>
      <span class="anz-kpi-explica">No se puede medir: nadie en este filtro tiene notas en los dos períodos.</span></div>`;
  }
  return `<div class="anz-kpis">${k1}${k2}${k3}</div>`;
}

// --- Evolución ---------------------------------------------------------------

function anzSerieEvolucion(ev) {
  const cohorte = ev.cohorte > 0;
  return { cohorte, valores: ev.puntos.map((p) => (cohorte ? p.promedio_cohorte : p.promedio_todos)) };
}

// Frase calculada: tendencia por tramos, sin inventar causas.
function anzInterpretarSerie(periodos, valores) {
  const tramos = [];
  for (let i = 1; i < valores.length; i++) {
    if (valores[i] === null || valores[i - 1] === null) continue;
    const d = Math.round((valores[i] - valores[i - 1]) * 100) / 100;
    tramos.push({ de: periodos[i - 1], a: periodos[i], d, tipo: Math.abs(d) < ANZ_TENDENCIA_ESTABLE ? "estable" : d > 0 ? "sube" : "baja" });
  }
  if (!tramos.length) return "<b>Aún no hay tendencia.</b> Falta un segundo período con notas.";
  const tipos = new Set(tramos.map((t) => t.tipo));
  const titulo = tipos.size === 1
    ? { sube: "Tendencia positiva", baja: "Tendencia descendente", estable: "Tendencia estable" }[tramos[0].tipo]
    : "Tendencia irregular";
  const verbo = (t) => (t.tipo === "estable" ? "se mantuvo" : t.tipo === "sube" ? "subió" : "bajó");
  let detalle;
  if (tramos.length === 1) {
    const t = tramos[0];
    detalle = t.tipo === "estable"
      ? `El promedio se mantuvo del Período ${t.de} al ${t.a} (${anzF(valores[0])} → ${anzF(valores[1])}).`
      : `El promedio ${verbo(t)} ${Math.abs(t.d).toFixed(2)} puntos del Período ${t.de} al ${t.a} (${anzF(valores[0])} → ${anzF(valores[1])}).`;
  } else {
    const primero = valores.find((v) => v !== null), ultimo = [...valores].reverse().find((v) => v !== null);
    detalle = `${tramos.map((t) => `${verbo(t)} del Período ${t.de} al ${t.a} (${anzS(t.d)})`).join(", ")}. En total pasó de ${anzF(primero)} a ${anzF(ultimo)}.`;
    detalle = detalle.charAt(0).toUpperCase() + detalle.slice(1);
  }
  const bruscos = tramos.filter((t) => Math.abs(t.d) >= ANZ_CAMBIO_BRUSCO);
  const brusco = bruscos.length
    ? ` <b>Cambio brusco</b> ${bruscos.map((t) => `entre el Período ${t.de} y el ${t.a} (${anzS(t.d)})`).join(" y ")}: conviene revisar qué pasó en ese período.`
    : "";
  return `<b>${titulo}.</b> ${detalle}${brusco}`;
}

function anzEvolucionHtml(ev) {
  const pts = ev.puntos;
  const { cohorte, valores } = anzSerieEvolucion(ev);
  const faltan = [1, 2, 3, 4].filter((p) => !pts.some((x) => x.periodo === p));
  const interp =
    pts.length < 2
      ? `<b>Aún no hay tendencia.</b> En ${ev.anio_lectivo} solo el Período ${pts[0]?.periodo ?? "—"} tiene notas con este filtro.`
      : anzInterpretarSerie(pts.map((p) => p.periodo), valores);
  const sub = cohorte
    ? `Promedio de los mismos <b>${ev.cohorte}</b> estudiantes en cada período de ${ev.anio_lectivo} (los que tienen notas en todos). Así la línea no cambia solo porque cambió quién está.`
    : `Ningún estudiante de este filtro tiene notas en todos los períodos: la línea usa a todos los evaluados de cada período, así que parte del cambio puede deberse a que no son los mismos estudiantes.`;
  const filas = pts
    .map(
      (p, i) => `<tr>
        <td><b>Período ${p.periodo}</b></td>
        <td class="anz-num">${anzF(cohorte ? p.promedio_cohorte : p.promedio_todos)}</td>
        <td class="anz-num ${anzClaseCambio(i && valores[i] !== null && valores[i - 1] !== null ? valores[i] - valores[i - 1] : null)}">${i && valores[i] !== null && valores[i - 1] !== null ? anzS(valores[i] - valores[i - 1]) : "—"}</td>
        <td class="anz-num">${anzP(anzPct((cohorte ? p.distribucion_cohorte : p.distribucion_todos).BAJO, cohorte ? p.evaluados_cohorte : p.evaluados_todos))}</td>
        <td class="anz-num">${anzF(p.promedio_todos)} <span class="prom-tenue">(${p.evaluados_todos})</span></td>
        <td>${i ? `<button type="button" class="boton-texto-chico" data-anz-comparar-idx="${i}">Comparar con el ${pts[i - 1].periodo}</button>` : ""}</td>
      </tr>`
    )
    .join("");
  return `
    <section class="anz-bloque">
      <h2>Evolución del promedio por período</h2>
      <p class="anz-sub">${sub}</p>
      <p class="anz-interpretacion">${interp}</p>
      <div class="anz-lienzo" role="img" aria-label="Promedio por período: ${pts.map((p, i) => `Período ${p.periodo} ${anzF(valores[i])}`).join(", ")}">
        <canvas id="anz-chart-evolucion"></canvas>
      </div>
      <p class="anz-nota">${pts.length >= 2 ? "Clic en un período para compararlo con el anterior. " : ""}La línea gris horizontal marca ${anzCorte()}, el mínimo de desempeño básico.${
        faltan.length ? ` Aún sin notas importadas en ${ev.anio_lectivo}: ${faltan.map((p) => `Período ${p}`).join(", ")}.` : ""
      }</p>
      <details class="anz-datos"><summary>Ver los datos en tabla</summary>
        <div class="ox-tabla-envoltura"><table class="ox-tabla anz-tabla">
          <thead><tr><th>Período</th><th class="anz-num">${cohorte ? "Mismos estudiantes" : "Promedio"}</th><th class="anz-num">Cambio</th><th class="anz-num">En bajo</th><th class="anz-num">Todos los evaluados</th><th></th></tr></thead>
          <tbody>${filas}</tbody>
        </table></div>
      </details>
    </section>`;
}

function anzDibujarEvolucion(ev) {
  anzChartEvolucion?.destroy();
  anzChartEvolucion = null;
  const c = document.getElementById("anz-chart-evolucion");
  if (!c) return;
  if (typeof Chart === "undefined") {
    c.parentElement.innerHTML = '<p class="ox-vacio-chico">No se pudo cargar la librería de gráficas; los datos están en la tabla de abajo.</p>';
    return;
  }
  const pts = ev.puntos;
  const { cohorte, valores } = anzSerieEvolucion(ev);
  const corte = Number(anzCorte());
  const validos = valores.filter((v) => v !== null);
  if (!validos.length) {
    c.parentElement.innerHTML = '<p class="ox-vacio-chico">No hay promedios que graficar con este filtro.</p>';
    return;
  }
  // Escala acotada a los datos (en pasos de 0.5) pero siempre incluyendo el
  // 3.0: con 1–5 fijo un cambio de 0.2 se vería plano.
  const min = Math.max(1, Math.floor((Math.min(...validos, corte) - 0.3) * 2) / 2);
  const max = Math.min(5, Math.ceil((Math.max(...validos, corte) + 0.3) * 2) / 2);
  const esComparado = (i) =>
    (pts[i].anio_lectivo === anzAnioComparado && pts[i].periodo === anzPeriodoComparado) ||
    (pts[i].anio_lectivo === anzAnioBase && pts[i].periodo === anzPeriodoBase);

  const lineaCorte = {
    id: "anzCorte",
    beforeDatasetsDraw(chart) {
      const { ctx, chartArea: a, scales } = chart;
      const y = scales.y.getPixelForValue(corte);
      if (y < a.top || y > a.bottom) return;
      ctx.save();
      ctx.strokeStyle = "#98a2b3";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(a.left, y);
      ctx.lineTo(a.right, y);
      ctx.stroke();
      ctx.fillStyle = "#667085";
      ctx.font = "11px Inter, system-ui, sans-serif";
      ctx.textAlign = "right";
      ctx.fillText(`${corte.toFixed(1)} · mínimo básico`, a.right - 4, y - 5);
      ctx.restore();
    },
  };
  // Pocos puntos (≤ 4 períodos): el valor va escrito sobre cada punto.
  const etiquetas = {
    id: "anzEtiquetas",
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      ctx.save();
      ctx.font = "600 12px Inter, system-ui, sans-serif";
      ctx.fillStyle = "#172033";
      ctx.textAlign = "center";
      chart.getDatasetMeta(0).data.forEach((pt, i) => {
        if (valores[i] !== null) ctx.fillText(valores[i].toFixed(2), pt.x, pt.y - 12);
      });
      ctx.restore();
    },
  };

  anzChartEvolucion = new Chart(c, {
    type: "line",
    data: {
      labels: pts.map((p) => `Período ${p.periodo}`),
      datasets: [{
        data: valores,
        borderColor: "#1d4ed8",
        backgroundColor: "#1d4ed8",
        borderWidth: 2,
        pointRadius: pts.map((_, i) => (esComparado(i) ? 6 : 4)),
        pointHoverRadius: 7,
        pointBorderColor: "#ffffff",
        pointBorderWidth: 2,
        tension: 0,
        spanGaps: true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 24, right: 16, left: 4 } },
      interaction: { mode: "nearest", axis: "x", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false,
          callbacks: {
            title: (items) => `Período ${pts[items[0].dataIndex].periodo} de ${ev.anio_lectivo}`,
            label: (item) => {
              const i = item.dataIndex, p = pts[i];
              const lineas = [`${cohorte ? "Mismos estudiantes" : "Todos los evaluados"}: ${anzF(valores[i])} (${cohorte ? p.evaluados_cohorte : p.evaluados_todos} estudiantes)`];
              if (cohorte) lineas.push(`Todos los evaluados: ${anzF(p.promedio_todos)} (${p.evaluados_todos})`);
              const dist = cohorte ? p.distribucion_cohorte : p.distribucion_todos;
              lineas.push(`En desempeño bajo: ${anzP(anzPct(dist.BAJO, cohorte ? p.evaluados_cohorte : p.evaluados_todos))}`);
              if (i > 0 && valores[i] !== null && valores[i - 1] !== null) lineas.push(`Cambio vs. Período ${pts[i - 1].periodo}: ${anzS(valores[i] - valores[i - 1])}`);
              return lineas;
            },
            footer: (items) => (items[0].dataIndex > 0 ? "Clic: comparar con el período anterior" : ""),
          },
        },
      },
      scales: {
        y: {
          min, max,
          ticks: { stepSize: 0.5, callback: (v) => Number(v).toFixed(1), color: "#667085" },
          grid: { color: "#eef0f3" },
          border: { display: false },
        },
        x: { offset: true, grid: { display: false }, ticks: { color: "#344054", font: { weight: 600 } } },
      },
      onClick: (evt, _els, chart) => {
        const cerca = chart.getElementsAtEventForMode(evt, "nearest", { intersect: false, axis: "x" }, false);
        if (!cerca.length || cerca[0].index === 0) return;
        const i = cerca[0].index;
        anzAplicar({ base: pts[i - 1], comparado: pts[i] }, "resumen");
      },
      onHover: (evt, els) => {
        evt.native.target.style.cursor = els.length && els[0].index > 0 ? "pointer" : "default";
      },
    },
    plugins: [lineaCorte, etiquetas],
  });
}

// --- Mejoraron / empeoraron / estables -------------------------------------

function anzCambioHtml(r) {
  const n = r.estudiantes_comparables;
  const c = anzCfg();
  const cab = `
    <h2>Mejoraron, empeoraron o se mantuvieron</h2>
    <p class="anz-sub">Se compara el promedio de cada estudiante en sus áreas con nota en ambos períodos.
      Mejoró = subió ${c.umbral_mejora.toFixed(1)} o más; empeoró = bajó ${c.umbral_descenso.toFixed(1)} o más; lo demás cuenta como estable.</p>`;
  if (!n) {
    return `<section class="anz-bloque">${cab}<div class="ox-vacio"><p>No se puede medir: ningún estudiante de este filtro tiene notas en el ${esc(anzPB())} y en el ${esc(anzPC())}.</p></div></section>`;
  }
  const segs = [
    ["mejoraron", r.mejoraron, r.pct_mejoraron, "mejoraron"],
    ["estables", r.estables, r.pct_estables, "se mantuvieron estables"],
    ["empeoraron", r.empeoraron, r.pct_empeoraron, "empeoraron"],
  ];
  return `
    <section class="anz-bloque">
      ${cab}
      <p class="anz-frase">De <b>${n}</b> estudiantes analizados, <b>${r.mejoraron}</b> mejoraron, <b>${r.empeoraron}</b> empeoraron y <b>${r.estables}</b> se mantuvieron estables.</p>
      ${anzApilada(
        segs.map(([k, v, pct, t]) => ({
          valor: v, color: ANZ_COLOR_CAMBIO[k], tinta: k === "estables" ? "#172033" : "#ffffff",
          titulo: `${v} ${t} (${anzP(pct)}). Clic para ver quiénes.`, attr: `data-anz-cambio="${k}"`,
        })),
        { alta: true, etiquetas: true, aria: "Estudiantes que mejoraron, se mantuvieron o empeoraron" }
      )}
      ${anzLeyenda(segs.map(([k, v, pct, t]) => ({ color: ANZ_COLOR_CAMBIO[k], texto: `<b>${v}</b>&nbsp;${t} <span class="prom-tenue">(${anzP(pct)})</span>`, attr: `data-anz-cambio="${k}"` })))}
      <div class="anz-mov-bajo">
        <span class="anz-mov-titulo">Desempeño bajo (promedio menor a ${anzCorte()}):</span>
        <button type="button" class="anz-enlace" data-anz-cambio="entraron_bajo"><b>${r.entraron_a_bajo}</b> pasaron a bajo</button>
        <button type="button" class="anz-enlace" data-anz-cambio="permanecen_bajo"><b>${r.permanecen_en_bajo}</b> siguen en bajo</button>
        <button type="button" class="anz-enlace" data-anz-cambio="salieron_bajo"><b>${r.salieron_de_bajo}</b> salieron de bajo</button>
      </div>
    </section>`;
}

// --- Distribución por nivel --------------------------------------------------

function anzFilaDistribucion(etiqueta, sub, dist, total, clave) {
  const rangos = anzRangos();
  return `<div class="anz-dist-fila">
    <div class="anz-dist-etq"><b>${etiqueta}</b><span>${sub}</span></div>
    ${anzApilada(
      ANZ_NIVELES.map((nv) => ({
        valor: dist[nv] || 0, color: ANZ_COLOR_NIVEL[nv], tinta: ANZ_TINTA_NIVEL[nv],
        titulo: `${NOMBRES_NIVEL[nv]} (${rangos[nv]}): ${dist[nv] || 0} de ${total} (${anzP(anzPct(dist[nv] || 0, total))})`,
        attr: nv === "BAJO" && clave ? `data-anz-cambio="${clave}"` : "",
      })),
      { alta: true, etiquetas: true, aria: `Distribución por nivel, ${etiqueta}` }
    )}
  </div>`;
}

function anzDistribucionHtml(r) {
  const n = r.estudiantes_comparables, hoy = r.actual_evaluados;
  const pb = anzPB(), pc = anzPC();
  const rangos = anzRangos();
  let interp = "";
  if (n) {
    const b0 = anzPct(r.distribucion_base.BAJO, n), b1 = anzPct(r.distribucion_comparado.BAJO, n);
    const a0 = anzPct(r.distribucion_base.ALTO + r.distribucion_base.SUPERIOR, n);
    const a1 = anzPct(r.distribucion_comparado.ALTO + r.distribucion_comparado.SUPERIOR, n);
    interp = `<p class="anz-interpretacion">Entre los mismos ${n} estudiantes, el nivel <b>Bajo</b> pasó de ${anzP(b0)} a ${anzP(b1)} y <b>Alto + Superior</b> de ${anzP(a0)} a ${anzP(a1)}.</p>`;
  }
  return `
    <section class="anz-bloque">
      <h2>Cómo se reparten los estudiantes por nivel</h2>
      <p class="anz-sub">Nivel según el promedio de cada estudiante. ${ANZ_NIVELES.map((nv) => `${NOMBRES_NIVEL[nv]}: ${rangos[nv]}`).join(" · ")}.</p>
      ${interp}
      ${n ? anzFilaDistribucion(pb, `mismos ${n} estudiantes`, r.distribucion_base, n) : ""}
      ${n ? anzFilaDistribucion(pc, `mismos ${n} estudiantes`, r.distribucion_comparado, n) : ""}
      ${hoy ? `${n ? '<hr class="anz-separador">' : ""}${anzFilaDistribucion(pc, `todos los evaluados (${hoy})`, r.actual_distribucion, hoy, "bajo_actual")}` : ""}
      ${anzLeyenda(ANZ_NIVELES.map((nv) => ({ color: ANZ_COLOR_NIVEL[nv], texto: `${NOMBRES_NIVEL[nv]} <span class="prom-tenue">(${rangos[nv]})</span>` })))}
      ${n ? `<details class="anz-datos" data-anz-matriz><summary>¿A qué nivel pasó cada estudiante? (tabla de transición)</summary><div data-anz-matriz-cuerpo><p class="estado-carga">Cargando...</p></div></details>` : ""}
    </section>`;
}

// Tabla de transición a nivel ESTUDIANTE (la misma unidad que la
// distribución de arriba; se arma con /estudiantes, al abrirla).
async function anzCargarMatriz(det) {
  const cuerpo = det.querySelector("[data-anz-matriz-cuerpo]");
  if (!cuerpo || cuerpo.dataset.cargado) return;
  cuerpo.dataset.cargado = "1";
  try {
    const lista = (await anzGet(`/api/boletines/comparacion/estudiantes?${paramsComparacion()}`)).filter((e) => e.comparable);
    const conteo = {};
    lista.forEach((e) => { const k = `${e.nivel_base}|${e.nivel_comparado}`; conteo[k] = (conteo[k] || 0) + 1; });
    const max = Math.max(1, ...Object.values(conteo));
    const celda = (nb, nc) => {
      const c = conteo[`${nb}|${nc}`] || 0;
      const fondo = c ? `rgba(29, 78, 216, ${0.08 + (c / max) * 0.55})` : "transparent";
      const tinta = c / max > 0.6 ? "#ffffff" : "#172033";
      const diag = nb === nc ? " anz-matriz-diag" : "";
      return `<td class="${diag}">${c ? `<button type="button" class="anz-matriz-celda" style="background:${fondo};color:${tinta}" data-anz-matriz-celda="${nb}|${nc}" title="${c} estudiantes: ${NOMBRES_NIVEL[nb]} en el ${esc(anzPB())} → ${NOMBRES_NIVEL[nc]} en el ${esc(anzPC())}">${c}</button>` : '<span class="prom-tenue">·</span>'}</td>`;
    };
    cuerpo.innerHTML = `
      <p class="anz-sub">Filas: nivel en el ${esc(anzPB())}. Columnas: nivel en el ${esc(anzPC())}. La diagonal son quienes se quedaron en el mismo nivel; clic en un número para ver esos estudiantes.</p>
      <div class="tabla-scroll"><table class="anz-tabla-matriz">
        <thead><tr><th></th>${ANZ_NIVELES.map((n) => `<th>${NOMBRES_NIVEL[n]}</th>`).join("")}</tr></thead>
        <tbody>${ANZ_NIVELES.map((nb) => `<tr><th>${NOMBRES_NIVEL[nb]}</th>${ANZ_NIVELES.map((nc) => celda(nb, nc)).join("")}</tr>`).join("")}</tbody>
      </table></div>
      <div data-anz-matriz-lista></div>`;
    cuerpo._lista = lista;
  } catch (e) {
    cuerpo.innerHTML = `<div class="alerta-caja">No se pudo cargar: ${esc(e.message)}</div>`;
    delete cuerpo.dataset.cargado;
  }
}

// --- Dónde concentrar la atención -------------------------------------------

function anzFocoHtml(P) {
  const pc = anzPC();
  const areas = P.areas
    .filter((a) => a.actual_evaluados >= ANZ_MIN_AREA)
    .map((a) => ({ a, pct: anzPct(a.actual_n_bajo, a.actual_evaluados) }))
    .sort((x, y) => y.pct - x.pct)
    .slice(0, 5)
    .map(({ a, pct }) => ({
      etiqueta: a.area_nombre, valor: pct,
      texto: `${anzP(pct)} <span class="prom-tenue">(${a.actual_n_bajo} de ${a.actual_evaluados})</span>`,
      attr: `data-anz-filtro="area_id" data-anz-valor="${a.area_id}"`, titulo: `Analizar ${a.area_nombre}`,
    }));
  const porGrupo = anzGrado !== null;
  const unidades = (porGrupo ? P.grupos : P.grados)
    .filter((g) => g.actual_evaluados >= ANZ_MIN_GRUPO)
    .map((g) => ({ g, pct: anzPct(g.actual_n_bajo, g.actual_evaluados) }))
    .sort((x, y) => y.pct - x.pct)
    .slice(0, 5)
    .map(({ g, pct }) => ({
      etiqueta: porGrupo ? `${g.nombre_grupo}${anzSedeId ? "" : ` · ${anzSede(g.sede_nombre)}`}` : anzNombreGrado(g.grado),
      valor: pct,
      texto: `${anzP(pct)} <span class="prom-tenue">(${g.actual_n_bajo} de ${g.actual_evaluados})</span>`,
      attr: porGrupo ? `data-anz-grupo="${g.sede_id ?? ""}|${g.grado}|${g.curso ?? ""}"` : `data-anz-filtro="grado" data-anz-valor="${g.grado}"`,
      titulo: `Analizar ${porGrupo ? g.nombre_grupo : anzNombreGrado(g.grado)}`,
    }));
  const maxPct = Math.max(10, ...areas.map((x) => x.valor), ...unidades.map((x) => x.valor));
  const escala = Math.ceil(maxPct / 10) * 10;
  const col = (titulo, sub, items, ir) => `
    <div class="anz-foco-col">
      <h3 class="ox-h3">${titulo}</h3>
      <p class="anz-sub">${sub}</p>
      ${items.length ? anzBarrasHtml(items, { max: escala, color: ANZ_COLOR_NIVEL.BAJO }) : '<p class="ox-vacio-chico">No hay suficientes datos con este filtro.</p>'}
      <button type="button" class="boton-texto-chico" data-anz-vista-ir="${ir}">Ver todos ${icono("arrow-right")}</button>
    </div>`;
  const cols = [];
  if (!anzAreaId) cols.push(col("Áreas", `% de <b>notas</b> en desempeño bajo (${esc(pc)}); solo áreas con ${ANZ_MIN_AREA} notas o más.`, areas, "areas"));
  if (anzCurso === null) {
    cols.push(col(porGrupo ? "Grupos" : "Grados", `% de <b>estudiantes</b> con promedio en bajo (${esc(pc)}); solo ${porGrupo ? "grupos" : "grados"} con ${ANZ_MIN_GRUPO} estudiantes o más.`, unidades, "grados"));
  }
  if (!cols.length) return "";
  return `
    <section class="anz-bloque">
      <h2>Dónde concentrar la atención</h2>
      <p class="anz-sub">Dónde hay hoy más desempeño bajo. Clic en una fila para ver su análisis completo.</p>
      <div class="anz-dos-col">${cols.join("")}</div>
    </section>`;
}

// --- Hallazgos (calculados en el backend: comparacion_academica.hallazgos) --

function anzHallazgosHtml(lista) {
  const ICO = { alerta: "circle-alert", baja: "trending-down", sube: "trending-up", ok: "circle-check" };
  const ETQ = { alerta: "Atención", baja: "Bajó", sube: "Subió", ok: "Positivo" };
  const c = anzCfg();
  const accion = (h) => {
    const a = h.accion || {};
    if (a.cambio) return `<button type="button" class="boton secundario boton-chico" data-anz-cambio="${esc(a.cambio)}">Ver los estudiantes</button>`;
    if (a.filtro) return `<button type="button" class="boton secundario boton-chico" data-anz-filtro="${esc(a.filtro)}" data-anz-valor="${esc(a.valor)}">Analizar ${esc(a.nombre || "")}</button>`;
    return "";
  };
  const tarjeta = (h) => `
      <details class="anz-hallazgo anz-hallazgo-${h.tipo}">
        <summary>
          ${icono(ICO[h.tipo] || "info")}
          <span class="anz-hallazgo-texto"><span class="anz-hallazgo-tipo">${ETQ[h.tipo] || ""}</span><strong>${esc(h.titulo)}</strong><span>${esc(h.detalle)}</span></span>
          ${icono("chevron-down", "anz-hallazgo-flecha")}
        </summary>
        <div class="anz-hallazgo-cuerpo">
          ${h.evidencia.length
            ? `<p class="anz-sub">Datos que lo sustentan:</p><table class="anz-evidencia"><tbody>${h.evidencia
                .map((f) => `<tr>${f.map((x, j) => `<td class="${j ? "anz-num" : ""}">${esc(x)}</td>`).join("")}</tr>`)
                .join("")}</tbody></table>`
            : ""}
          ${accion(h)}
        </div>
      </details>`;
  const VISIBLES = 6;
  const items =
    lista.slice(0, VISIBLES).map(tarjeta).join("") +
    (lista.length > VISIBLES
      ? `<details class="anz-datos anz-mas-hallazgos"><summary>Ver ${lista.length - VISIBLES} hallazgos más</summary>${lista.slice(VISIBLES).map(tarjeta).join("")}</details>`
      : "");
  return `
    <section class="anz-bloque">
      <h2>Hallazgos</h2>
      <p class="anz-sub">Cambios importantes detectados con reglas fijas sobre estos mismos datos, nunca escritos a mano. Abre cada uno para ver los números que lo sustentan.</p>
      ${items || '<div class="ox-vacio"><p>Ningún cambio supera los umbrales con este filtro.</p></div>'}
      <details class="anz-datos"><summary>¿Con qué reglas se detectan?</summary>
        <ul class="anz-reglas">
          <li>Estudiantes que pasaron a bajo o bajaron ${c.umbral_descenso_significativo.toFixed(1)} o más: se cuentan todos los que cumplen la condición.</li>
          <li>% en desempeño bajo: se reporta si cambia 5 puntos porcentuales o más entre los mismos estudiantes.</li>
          <li>Áreas: solo con ${ANZ_MIN_AREA} notas comparables o más; se reportan las dos mayores caídas y la mayor subida si son de 0.10 o más.</li>
          <li>Mayor dificultad hoy: el área con más % de notas en bajo, si es 15% o más.</li>
          <li>Grados: solo con ${ANZ_MIN_GRUPO} estudiantes comparables o más; aumento de 5+ puntos en desempeño bajo o caída de promedio de 0.10 o más.</li>
          <li>Descenso en dos períodos seguidos: solo cuando hay 3 períodos o más; bajó ${c.umbral_descenso.toFixed(1)} o más en cada uno.</li>
        </ul>
      </details>
    </section>`;
}

// --- Áreas ------------------------------------------------------------------

const ANZ_ORDENES = [["dificultad", "Más dificultad hoy"], ["deterioro", "Más bajaron"], ["mejora", "Más subieron"], ["promedio", "Promedio más bajo"]];

// Ordena y arma barras + frase para Áreas y Grados con la misma lógica.
// u: [{nombre, hoyN, hoyBajo, hoyProm, compN, variacion, attr}]
function anzRankingVisual(u, orden, minN, unidad, queCuenta) {
  const pct = (x) => anzPct(x.hoyBajo, x.hoyN);
  // Los de pocos datos van al final y no fijan la escala: 1 de 1 en bajo
  // (100%) no puede aplastar las barras de las áreas con cientos de notas.
  const alFinal = (lista, esPoco) => [...lista.filter((x) => !esPoco(x)), ...lista.filter(esPoco)];
  let lista, items, opts, interp;
  if (orden === "dificultad") {
    lista = alFinal(u.filter((x) => x.hoyN > 0).sort((a, b) => pct(b) - pct(a)), (x) => x.hoyN < minN);
    const escala = Math.ceil(Math.max(10, ...lista.filter((x) => x.hoyN >= minN).map(pct)) / 10) * 10;
    items = lista.map((x) => ({ etiqueta: x.nombre, valor: pct(x), poco: x.hoyN < minN, attr: x.attr, titulo: `Analizar ${x.nombre}`, texto: `${anzP(pct(x))} <span class="prom-tenue">(${x.hoyBajo} de ${x.hoyN})</span>` }));
    opts = { max: escala, color: ANZ_COLOR_NIVEL.BAJO };
    const fiables = lista.filter((x) => x.hoyN >= minN);
    interp = fiables.length
      ? `<b>${esc(fiables[0].nombre)}</b> tiene la mayor proporción de ${queCuenta} en desempeño bajo hoy: ${anzP(pct(fiables[0]))} (${fiables[0].hoyBajo} de ${fiables[0].hoyN}).${
          fiables[1] ? ` Le ${fiables[2] ? "siguen" : "sigue"} ${fiables.slice(1, 3).map((x) => `${esc(x.nombre)} (${anzP(pct(x))})`).join(" y ")}.` : ""
        } En ${fiables.filter((x) => pct(x) >= 15).length} de ${fiables.length} ${unidad} el 15% o más está en bajo.`
      : `Ningún(a) ${unidad.replace(/s$/, "")} tiene suficientes datos (${minN}+) para sacar conclusiones.`;
  } else if (orden === "promedio") {
    lista = alFinal(u.filter((x) => x.hoyProm !== null).sort((a, b) => a.hoyProm - b.hoyProm), (x) => x.hoyN < minN);
    items = lista.map((x) => ({ etiqueta: x.nombre, valor: x.hoyProm, poco: x.hoyN < minN, attr: x.attr, titulo: `Analizar ${x.nombre}`, texto: `${anzF(x.hoyProm)} <span class="prom-tenue">(${x.hoyN})</span>` }));
    opts = { min: 1, max: 5, color: "#1d4ed8", marca: Number(anzCorte()) };
    const fiables = lista.filter((x) => x.hoyN >= minN);
    interp = fiables.length > 1
      ? `El promedio más bajo hoy es el de <b>${esc(fiables[0].nombre)}</b> (${anzF(fiables[0].hoyProm)}); el más alto, <b>${esc(fiables[fiables.length - 1].nombre)}</b> (${anzF(fiables[fiables.length - 1].hoyProm)}). La marca vertical es ${anzCorte()}.`
      : "No hay suficientes datos para comparar promedios.";
  } else {
    const baja = orden === "deterioro";
    const con = u.filter((x) => x.variacion !== null).sort((a, b) => (baja ? a.variacion - b.variacion : b.variacion - a.variacion));
    const sin = u.filter((x) => x.variacion === null);
    lista = [...alFinal(con, (x) => x.compN < minN), ...sin];
    const escala = Math.max(0.1, ...con.filter((x) => x.compN >= minN).map((x) => Math.abs(x.variacion)));
    items = lista.map((x) => ({ etiqueta: x.nombre, valor: x.variacion, poco: x.variacion !== null && x.compN < minN, attr: x.attr, titulo: `Analizar ${x.nombre}`, texto: x.variacion === null ? '<span class="prom-tenue">—</span>' : `${anzS(x.variacion)} <span class="prom-tenue">(${x.compN})</span>` }));
    opts = { divergente: true, max: escala };
    const fiables = con.filter((x) => x.compN >= minN);
    const bajaron = fiables.filter((x) => x.variacion <= -0.1).length, subieron = fiables.filter((x) => x.variacion >= 0.1).length;
    const extremo = fiables[0];
    interp = fiables.length
      ? `${anzPl(bajaron, unidad.replace(/s$/, "") + " bajó", unidad + " bajaron")} su promedio 0.10 o más, ${subieron} ${subieron === 1 ? "subió" : "subieron"} y ${fiables.length - bajaron - subieron} se ${fiables.length - bajaron - subieron === 1 ? "mantuvo" : "mantuvieron"} (de ${fiables.length} con ${minN}+ datos comparables). ${
          extremo ? `${baja ? "La mayor caída" : "La mayor subida"}: <b>${esc(extremo.nombre)}</b> (${anzS(extremo.variacion)}).` : ""
        }${sin.length ? ` ${anzPl(sin.length, unidad.replace(/s$/, "") + " no tiene", unidad + " no tienen")} datos del ${esc(anzPB())} para comparar.` : ""}`
      : `No hay ${unidad} con suficientes datos comparables (${minN}+) entre el ${esc(anzPB())} y el ${esc(anzPC())}.`;
  }
  return { items, opts, interp };
}

async function anzAreasHtml() {
  const P = await anzPanorama();
  if (!P.resumen.total_estudiantes || !P.areas.length) return anzVacioFiltroHtml();
  const pb = anzPB(), pc = anzPC();
  const u = P.areas.map((a) => ({
    nombre: a.area_nombre, hoyN: a.actual_evaluados, hoyBajo: a.actual_n_bajo, hoyProm: a.actual_promedio,
    compN: a.total_evaluados, variacion: a.variacion, attr: `data-anz-filtro="area_id" data-anz-valor="${a.area_id}"`,
  }));
  const { items, opts, interp } = anzRankingVisual(u, anzOrdenAreas, ANZ_MIN_AREA, "áreas", "notas");
  // Mismo criterio que las barras: las de pocos datos al final.
  const poco = (a) => (a.actual_evaluados < ANZ_MIN_AREA ? 1 : 0);
  const orden = [...P.areas].sort(
    (a, b) => poco(a) - poco(b) || (anzPct(b.actual_n_bajo, b.actual_evaluados) ?? -1) - (anzPct(a.actual_n_bajo, a.actual_evaluados) ?? -1)
  );
  const filas = orden
    .map(
      (a) => `<tr class="anz-fila-clic" data-anz-filtro="area_id" data-anz-valor="${a.area_id}" tabindex="0">
        <td><strong>${esc(a.area_nombre)}</strong> <span class="prom-tenue">${esc(a.area_codigo)}</span></td>
        <td class="anz-num">${anzF(a.actual_promedio)}</td>
        <td class="anz-num">${anzP(anzPct(a.actual_n_bajo, a.actual_evaluados))} <span class="prom-tenue">(${a.actual_n_bajo}/${a.actual_evaluados})</span></td>
        <td class="anz-num">${a.variacion === null ? "—" : `${anzF(a.promedio_base)} → ${anzF(a.promedio_comparado)}`}</td>
        <td class="anz-num ${anzClaseCambio(a.variacion)}"><b>${anzS(a.variacion)}</b></td>
        <td class="anz-num">${a.variacion === null ? "—" : `${a.n_bajo_base} → ${a.n_bajo_comparado}`}</td>
        <td class="anz-num">${a.variacion === null ? "—" : `${a.empeoraron} / ${a.mejoraron}`}</td>
        <td class="anz-num">${a.total_evaluados || "—"}</td>
      </tr>`
    )
    .join("");
  return `
    ${anzAreaId ? `<div class="anz-aviso">${icono("filter")}<div>Estás viendo solo <b>${esc(anzNombreArea(anzAreaId))}</b>. <button type="button" class="anz-enlace" data-anz-quitar="area">Quitar el filtro de área</button> para comparar todas.</div></div>` : ""}
    <section class="anz-bloque">
      <h2>Qué áreas tienen más dificultad y cómo cambiaron</h2>
      <p class="anz-sub">Cada área cuenta <b>notas</b> (un estudiante en esa área). «Hoy» usa todas las notas del ${esc(pc)}; el cambio usa solo las notas de estudiantes que tienen esa área en los dos períodos. Las áreas con menos de ${ANZ_MIN_AREA} notas salen en gris: con tan pocos datos un cambio puede ser casualidad.</p>
      ${anzSegmentado("anz-orden-areas", ANZ_ORDENES, anzOrdenAreas, "Ordenar por")}
      <p class="anz-interpretacion">${interp}</p>
      ${anzBarrasHtml(items, opts)}
      <p class="anz-nota">Clic en un área para ver su análisis completo: evolución, grados y estudiantes solo de esa área.</p>
    </section>
    <section class="anz-bloque">
      <h2>Tabla de áreas</h2>
      <p class="anz-sub">Ordenada por % de notas en bajo hoy; las de menos de ${ANZ_MIN_AREA} notas van al final.</p>
      <div class="ox-tabla-envoltura"><table class="ox-tabla anz-tabla">
        <thead>
          <tr><th rowspan="2">Área</th><th colspan="2" class="anz-th-grupo">Hoy (${esc(pc)})</th><th colspan="5" class="anz-th-grupo">Cambio · mismos estudiantes</th></tr>
          <tr><th class="anz-num">Promedio</th><th class="anz-num">En bajo</th><th class="anz-num">${esc(pb)} → ${esc(pc)}</th><th class="anz-num">Cambio</th><th class="anz-num">Notas en bajo</th><th class="anz-num">Bajaron / subieron</th><th class="anz-num">Notas comparadas</th></tr>
        </thead>
        <tbody>${filas}</tbody>
      </table></div>
    </section>`;
}

// --- Grados, grupos y sedes ---------------------------------------------------

async function anzGradosHtml() {
  const P = await anzPanorama();
  anzRecordarGrupos(P);
  if (!P.resumen.total_estudiantes) return anzVacioFiltroHtml();
  if (anzAgrupar === "sede" && anzSedeId) anzAgrupar = "grado";
  const pb = anzPB(), pc = anzPC();
  const fuente = anzAgrupar === "grupo" ? P.grupos : anzAgrupar === "sede" ? P.sedes : P.grados;
  const nombre = (g) =>
    anzAgrupar === "sede" ? anzSede(g.sede_nombre)
      : anzAgrupar === "grupo" ? `${g.nombre_grupo}${anzSedeId ? "" : ` · ${anzSede(g.sede_nombre)}`}`
        : anzNombreGrado(g.grado);
  const attr = (g) =>
    anzAgrupar === "sede" ? `data-anz-filtro="sede_id" data-anz-valor="${g.sede_id}"`
      : anzAgrupar === "grupo" ? `data-anz-grupo="${g.sede_id ?? ""}|${g.grado}|${g.curso ?? ""}"`
        : `data-anz-filtro="grado" data-anz-valor="${g.grado}"`;
  const u = fuente.map((g) => ({
    nombre: nombre(g), hoyN: g.actual_evaluados, hoyBajo: g.actual_n_bajo, hoyProm: g.actual_promedio,
    compN: g.estudiantes_comparables, variacion: g.estudiantes_comparables ? g.variacion : null, attr: attr(g),
  }));
  const unidad = { grado: "grados", grupo: "grupos", sede: "sedes" }[anzAgrupar];
  const { items, opts, interp } = anzRankingVisual(u, anzOrdenGrados, ANZ_MIN_GRUPO, unidad, "estudiantes");
  const visibles = items.slice(0, 20);

  const tieneBajoBase = anzAgrupar !== "sede";
  const filas = [...fuente]
    .sort((a, b) => (anzAgrupar === "grado" ? a.grado - b.grado : 0))
    .map((g) => {
      const m = g.estudiantes_comparables;
      const bajoAntes = tieneBajoBase ? g.salieron_de_bajo + g.permanecen_en_bajo : null;
      const bajoAhora = tieneBajoBase ? g.entraron_a_bajo + g.permanecen_en_bajo : null;
      return `<tr class="anz-fila-clic" ${attr(g)} tabindex="0">
        <td><strong>${esc(nombre(g))}</strong></td>
        <td class="anz-num">${g.actual_evaluados}</td>
        <td class="anz-num">${anzF(g.actual_promedio)}</td>
        <td class="anz-num">${anzP(anzPct(g.actual_n_bajo, g.actual_evaluados))} <span class="prom-tenue">(${g.actual_n_bajo})</span></td>
        <td class="anz-num">${m ? `${anzF(g.promedio_base)} → ${anzF(g.promedio_comparado)}` : '<span class="prom-tenue">sin ' + esc(pb) + "</span>"}</td>
        <td class="anz-num ${anzClaseCambio(m ? g.variacion : null)}"><b>${m ? anzS(g.variacion) : "—"}</b></td>
        ${tieneBajoBase ? `<td class="anz-num">${m ? `${anzP(anzPct(bajoAntes, m))} → ${anzP(anzPct(bajoAhora, m))}` : "—"}</td>` : ""}
        <td class="anz-num">${m ? `${anzP(g.pct_mejoraron)} / ${anzP(g.pct_empeoraron)}` : "—"}</td>
        <td class="anz-num">${m || "—"}</td>
      </tr>`;
    })
    .join("");

  const agrupar = [["grado", "Grado"], ["grupo", "Grupo"], ...(anzSedeId ? [] : [["sede", "Sede"]])];
  return `
    ${anzGrado !== null && anzAgrupar === "grado" ? `<div class="anz-aviso">${icono("filter")}<div>Estás viendo solo <b>${esc(anzNombreGrado(anzGrado))}</b>. Agrupa por «Grupo» para ver cada grupo, o <button type="button" class="anz-enlace" data-anz-quitar="grado">quita el filtro de grado</button>.</div></div>` : ""}
    <section class="anz-bloque">
      <h2>Qué ${unidad} tienen más bajo rendimiento y cómo cambiaron</h2>
      <p class="anz-sub">Cada ${unidad.replace(/s$/, "")} cuenta <b>estudiantes</b> (el promedio de sus áreas). «Hoy» usa a todos los evaluados del ${esc(pc)}; el cambio, solo a los que tienen notas en ambos períodos. Con menos de ${ANZ_MIN_GRUPO} estudiantes sale en gris.</p>
      <div class="anz-controles">
        ${anzSegmentado("anz-agrupar", agrupar, anzAgrupar, "Ver por")}
        ${anzSegmentado("anz-orden-grados", ANZ_ORDENES, anzOrdenGrados, "Ordenar por")}
      </div>
      <p class="anz-interpretacion">${interp}</p>
      ${anzBarrasHtml(visibles, opts)}
      ${items.length > visibles.length ? `<p class="anz-nota">Se muestran los primeros ${visibles.length} de ${items.length}; la tabla de abajo los tiene todos.</p>` : ""}
      <p class="anz-nota">Clic en una fila para ver su análisis completo.</p>
    </section>
    <section class="anz-bloque">
      <h2>Tabla por ${unidad.replace(/s$/, "")}</h2>
      <div class="ox-tabla-envoltura"><table class="ox-tabla anz-tabla">
        <thead>
          <tr><th rowspan="2">${{ grado: "Grado", grupo: "Grupo", sede: "Sede" }[anzAgrupar]}</th><th colspan="3" class="anz-th-grupo">Hoy (${esc(pc)})</th><th colspan="${tieneBajoBase ? 5 : 4}" class="anz-th-grupo">Cambio · mismos estudiantes</th></tr>
          <tr><th class="anz-num">Estudiantes</th><th class="anz-num">Promedio</th><th class="anz-num">En bajo</th>
            <th class="anz-num">${esc(pb)} → ${esc(pc)}</th><th class="anz-num">Cambio</th>${tieneBajoBase ? '<th class="anz-num">En bajo antes → ahora</th>' : ""}
            <th class="anz-num">Mejoraron / empeoraron</th><th class="anz-num">Comparados</th></tr>
        </thead>
        <tbody>${filas}</tbody>
      </table></div>
    </section>`;
}

// --- Docentes y materias ------------------------------------------------------

async function anzDocentesHtml() {
  const puedeEvaluar = tienePermiso("docentes.evaluar");
  if (!puedeEvaluar) anzDocModo = "asignaturas";
  const seg = puedeEvaluar
    ? anzSegmentado("anz-doc-modo", [["asignaturas", "Materias y grupos"], ["evaluacion", "Evaluación por docente"]], anzDocModo, "Ver")
    : "";
  if (anzDocModo === "evaluacion") {
    const cuerpo = anzDocFicha ? await fichaDocenteHtml(anzDocFicha) : await anzEvaluacionListaHtml();
    return `${seg}<div data-anz-doc-cuerpo>${cuerpo}</div>`;
  }
  const lista = await anzGet(`/api/boletines/comparacion/por-docente?${paramsComparacion()}`);
  if (anzAsigAbierta) return seg + (await anzAsignaturaDetalleHtml(lista));
  return seg + anzAsignaturasHtml(lista);
}

function anzClaveAsig(a) {
  return `${a.docente_id}|${a.area_id}|${a.grado}|${a.curso ?? ""}`;
}

function anzAsignaturasHtml(lista) {
  const f = anzAsigFiltro;
  const docentes = [...new Map(lista.map((a) => [a.docente_id, a.docente_nombre])).entries()].sort((a, b) => a[1].localeCompare(b[1]));
  const paraArea = lista.filter((a) => !f.docente || a.docente_id === Number(f.docente));
  const areas = [...new Map(paraArea.map((a) => [a.area_id, a.area_nombre])).entries()].sort((a, b) => a[1].localeCompare(b[1]));
  const paraGrado = paraArea.filter((a) => !f.area || a.area_id === Number(f.area));
  const grados = [...new Set(paraGrado.map((a) => a.grado))].sort((a, b) => a - b);
  const filtradas = paraGrado.filter((a) => f.grado === "" || a.grado === Number(f.grado));
  const sel = (nombre, etiqueta, todos, opciones, actual) =>
    `<label class="anz-filtro"><span>${etiqueta}</span><select data-anz-asig-sel="${nombre}"><option value="">${todos}</option>${opciones
      .map(([v, t]) => `<option value="${v}" ${String(actual) === String(v) ? "selected" : ""}>${esc(t)}</option>`)
      .join("")}</select></label>`;

  const filas = filtradas
    .map((a) => {
      const bajoAntes = a.salieron_de_bajo + a.permanecen_en_bajo, bajoAhora = a.entraron_a_bajo + a.permanecen_en_bajo;
      return `<tr class="anz-fila-clic" data-anz-asig="${anzClaveAsig(a)}" tabindex="0">
        <td>${esc(a.docente_nombre)}</td>
        <td><strong>${esc(a.area_nombre)}</strong></td>
        <td>${esc(anzNombreGrupo(a.grado, a.curso))}</td>
        <td class="anz-num">${a.total_evaluados}</td>
        <td class="anz-num">${anzF(a.promedio_base)} → ${anzF(a.promedio_comparado)}</td>
        <td class="anz-num ${anzClaseCambio(a.variacion)}"><b>${anzS(a.variacion)}</b></td>
        <td class="anz-num">${bajoAntes} → ${bajoAhora}</td>
        <td class="anz-num">${a.mejoraron}</td>
        <td class="anz-num">${a.empeoraron}</td>
        <td class="dk-col-flecha">${icono("chevron-right", "ico-tenue")}</td>
      </tr>`;
    })
    .join("");
  return `
    <div class="anz-aviso">${icono("info")}<div><b>Esto describe resultados, no califica docentes.</b> Cada fila es una materia en un grupo: cómo cambiaron las notas de esos estudiantes entre el ${esc(anzPB())} y el ${esc(anzPC())}.
      Las notas las pone el mismo docente y dependen de muchas cosas (el grupo, el tema del período, la forma de evaluar), así que no sirve para comparar personas. El orden es alfabético a propósito.</div></div>
    <section class="anz-bloque">
      <h2>Materias y grupos</h2>
      <p class="anz-sub">Elige docente → área → grado para acotar. Clic en una fila para ver la distribución y los estudiantes de esa materia. Solo aparecen materias con docente asignado y notas en ambos períodos.</p>
      <div class="anz-filtros-fila anz-asig-filtros">
        ${sel("docente", "Docente", "Todos los docentes", docentes, f.docente)}
        ${sel("area", "Área", "Todas las áreas", areas, f.area)}
        ${sel("grado", "Grado", "Todos los grados", grados.map((g) => [g, anzNombreGrado(g)]), f.grado)}
      </div>
      <p class="anz-nota">${anzPl(filtradas.length, "materia-grupo", "materias-grupo")} de ${anzPl(new Set(filtradas.map((a) => a.docente_id)).size, "docente", "docentes")}.</p>
      ${
        filtradas.length
          ? `<div class="ox-tabla-envoltura"><table class="ox-tabla anz-tabla">
              <thead><tr><th>Docente</th><th>Materia</th><th>Grupo</th><th class="anz-num">Evaluados</th><th class="anz-num">Promedio ${esc(anzPB())} → ${esc(anzPC())}</th><th class="anz-num">Cambio</th><th class="anz-num">En bajo antes → ahora</th><th class="anz-num">Mejoraron</th><th class="anz-num">Empeoraron</th><th></th></tr></thead>
              <tbody>${filas}</tbody></table></div>`
          : '<div class="ox-vacio"><p>No hay materias con notas en ambos períodos para esta combinación.</p></div>'
      }
    </section>`;
}

async function anzAsignaturaDetalleHtml(lista) {
  const [docId, areaId, grado, curso] = anzAsigAbierta.split("|");
  const a = lista.find((x) => anzClaveAsig(x) === anzAsigAbierta);
  const migas = `<nav class="ox-migas" aria-label="Ruta"><button type="button" data-anz-asig-volver>Materias y grupos</button><span aria-hidden="true">/</span><span>${esc(a ? `${a.area_nombre} · ${anzNombreGrupo(a.grado, a.curso)}` : "Materia")}</span></nav>`;
  if (!a) return `${migas}<div class="ox-vacio"><p>Esta materia ya no aparece con los filtros actuales.</p></div>`;
  const extra = { docente_id: docId, area_id: areaId, grado, limite: 2000 };
  if (curso !== "") extra.curso = curso;
  const filas = await anzGet(`/api/boletines/comparacion/detalle?${paramsComparacion(extra)}`);
  const n = filas.length;
  const dist = (campo) => { const d = {}; ANZ_NIVELES.forEach((nv) => (d[nv] = filas.filter((f) => f[campo] === nv).length)); return d; };
  const c = anzCfg();
  const estudiantes = [...filas].sort((x, y) => x.delta - y.delta);
  return `
    ${migas}
    <section class="anz-lectura anz-lectura-${Math.abs(a.variacion) < ANZ_TENDENCIA_ESTABLE ? "estable" : a.variacion > 0 ? "sube" : "baja"}">
      ${icono("book-open")}
      <div>
        <p class="dx-eyebrow">${esc(anzPB())} → ${esc(anzPC())} · Docente: ${esc(a.docente_nombre)}</p>
        <h2>${esc(a.area_nombre)} · ${esc(anzNombreGrupo(a.grado, a.curso))}</h2>
        <p>El promedio de los ${a.total_evaluados} estudiantes con nota en ambos períodos pasó de ${anzF(a.promedio_base)} a ${anzF(a.promedio_comparado)} (${anzS(a.variacion)}).
          ${a.mejoraron} subieron ${c.umbral_mejora.toFixed(1)} o más, ${a.empeoraron} bajaron ${c.umbral_descenso.toFixed(1)} o más y ${a.estables} se mantuvieron.</p>
      </div>
    </section>
    <section class="anz-bloque">
      <h2>Distribución de desempeño en esta materia</h2>
      <p class="anz-sub">Nivel de la nota de cada estudiante en esta materia, mismos ${n} estudiantes en los dos períodos.</p>
      ${anzFilaDistribucion(anzPB(), `${n} estudiantes`, dist("nivel_base"), n)}
      ${anzFilaDistribucion(anzPC(), `${n} estudiantes`, dist("nivel_comparado"), n)}
      ${anzLeyenda(ANZ_NIVELES.map((nv) => ({ color: ANZ_COLOR_NIVEL[nv], texto: `${NOMBRES_NIVEL[nv]} <span class="prom-tenue">(${anzRangos()[nv]})</span>` })))}
    </section>
    <section class="anz-bloque">
      <h2>Estudiantes</h2>
      <p class="anz-sub">Del que más bajó al que más subió. Clic en un nombre para ver su evolución en todas las áreas.</p>
      <div class="ox-tabla-envoltura"><table class="ox-tabla anz-tabla">
        <thead><tr><th>Estudiante</th><th class="anz-num">${esc(anzPB())}</th><th class="anz-num">${esc(anzPC())}</th><th class="anz-num">Cambio</th><th>Nivel ahora</th></tr></thead>
        <tbody>${estudiantes
          .map(
            (f) => `<tr class="anz-fila-clic" data-anz-ver-estudiante="${f.estudiante_id}" tabindex="0">
              <td><strong>${esc(f.nombre_completo)}</strong></td>
              <td class="anz-num">${anzF(f.valor_base, 1)}</td>
              <td class="anz-num ${f.nivel_comparado === "BAJO" ? "anz-nota-baja" : ""}"><b>${anzF(f.valor_comparado, 1)}</b></td>
              <td class="anz-num ${anzClaseCambio(f.delta)}">${anzS(f.delta)}</td>
              <td>${anzNivelChip(f.nivel_comparado)}</td>
            </tr>`
          )
          .join("")}</tbody>
      </table></div>
    </section>`;
}

function anzNivelChip(nivel) {
  if (!nivel) return '<span class="prom-tenue">—</span>';
  return `<span class="anz-nivel"><span class="anz-muestra" style="background:${ANZ_COLOR_NIVEL[nivel]}"></span>${NOMBRES_NIVEL[nivel]}</span>`;
}

// --- ¿Quién debe mejorar? (vista sencilla, sin estadística) -----------------
// Pedido del colegio (05/10/2026): "hay muchas estadísticas y no las
// entiendo todas". Esta pestaña responde UNA pregunta con nombres propios:
// qué estudiantes tienen que mejorar y en qué materias. Mismos datos que
// /estudiantes (sin filtro de cambio); la prioridad se decide aquí con
// reglas fijas que la pantalla dice en palabras.

let anzMejChip = "todos"; // todos | retiro | urgente | atencion | vigilar
let anzMejBuscar = "", anzMejLimite = 50, anzMejDatos = [];
const ANZ_MEJ_URGENTE_AREAS = 3; // pierde 3 o más materias = urgente

const ANZ_MEJ_PRIORIDADES = [
  ["retiro", "Posible retiro", "#6d28d9"],
  ["urgente", "Urgente", "#dc2626"],
  ["atencion", "Necesita apoyo", "#c2410c"],
  ["vigilar", "Hay que vigilar", "#a16207"],
];

function anzMejReglas() {
  const corte = anzCorte(), c = anzCfg();
  return {
    retiro: `Tiene 1.0 (no presentó nada) en varias materias, o ya no aparece en las notas del ${anzPC()}. Confirmar con el director de grupo.`,
    urgente: `Pierde ${ANZ_MEJ_URGENTE_AREAS} materias o más, o su promedio está por debajo de ${corte}.`,
    atencion: `Pierde 1 o 2 materias.`,
    vigilar: `No pierde ninguna, pero su promedio bajó ${c.umbral_descenso.toFixed(1)} o más desde el ${anzPB()}.`,
  };
}

function anzPrioridadMejora(e) {
  if (e.riesgo_retiro) return "retiro";
  const pierde = e.areas_en_bajo.length;
  if (pierde >= ANZ_MEJ_URGENTE_AREAS || e.nivel_comparado === "BAJO") return "urgente";
  if (pierde > 0) return "atencion";
  if (e.comparable && e.delta !== null && e.delta <= -anzCfg().umbral_descenso) return "vigilar";
  return null;
}

// "Bajó 0.40", "Subió 0.20", "Igual": el cambio dicho en palabras.
function anzCambioEnPalabras(e) {
  if (!e.comparable || e.delta === null) return `<span class="prom-tenue">sin notas del ${esc(anzPB())}</span>`;
  const c = anzCfg();
  if (e.delta <= -c.umbral_descenso) return `<span class="anz-baja">${icono("arrow-down")} bajó ${anzF(Math.abs(e.delta))}</span>`;
  if (e.delta >= c.umbral_mejora) return `<span class="anz-sube">${icono("arrow-up")} subió ${anzF(e.delta)}</span>`;
  return '<span class="prom-tenue">casi igual</span>';
}

// Lista de quienes deben mejorar, ordenada del más urgente al menos urgente
// (también la usan Fortalezas y la exposición). evaluados = con alguna nota
// del período actual o señalados como posible retiro.
function anzClasificarMejora(todos) {
  const evaluados = todos.filter((e) => e.promedio_comparado !== null || e.riesgo_retiro);
  const orden = { retiro: 0, urgente: 1, atencion: 2, vigilar: 3 };
  const lista = evaluados
    .map((e) => ({ ...e, prioridad: anzPrioridadMejora(e) }))
    .filter((e) => e.prioridad)
    .sort((a, b) =>
      orden[a.prioridad] - orden[b.prioridad] ||
      (a.riesgo_retiro === "MUY_PROBABLE" ? 0 : 1) - (b.riesgo_retiro === "MUY_PROBABLE" ? 0 : 1) ||
      b.areas_en_bajo.length - a.areas_en_bajo.length ||
      (a.promedio_comparado ?? 0) - (b.promedio_comparado ?? 0) ||
      a.nombre_completo.localeCompare(b.nombre_completo)
    );
  const cuenta = { retiro: 0, urgente: 0, atencion: 0, vigilar: 0 };
  lista.forEach((e) => cuenta[e.prioridad]++);
  return { evaluados, lista, cuenta };
}

function anzEstudiantesTodos() {
  return anzGet(`/api/boletines/comparacion/estudiantes?${paramsComparacion()}`);
}

async function anzMejorarHtml() {
  const [P, todos] = await Promise.all([
    anzPanorama(),
    anzEstudiantesTodos(),
  ]);
  anzRecordarGrupos(P);
  const { evaluados, lista, cuenta } = anzClasificarMejora(todos);
  if (!evaluados.length) return anzVacioFiltroHtml();
  anzMejDatos = lista;
  const total = anzMejDatos.length, pc = anzPC(), corte = anzCorte();
  const reglas = anzMejReglas();

  const tarjetas = ANZ_MEJ_PRIORIDADES.map(([id, nombre, color]) => `
    <button type="button" class="anz-mej-tarjeta${anzMejChip === id ? " activo" : ""}" data-anz-mej-chip="${id}" aria-pressed="${anzMejChip === id}" style="--mej-color:${color}">
      <span class="anz-mej-tarjeta-etq"><span class="anz-muestra" style="background:${color}"></span>${nombre}</span>
      <b>${cuenta[id]}</b>
      <span>${cuenta[id] === 1 ? "estudiante" : "estudiantes"}</span>
      <span class="anz-mej-regla">${esc(reglas[id])}</span>
    </button>`).join("");

  return `
    <section class="anz-lectura anz-lectura-${cuenta.urgente ? "baja" : "estable"}">
      ${icono("users")}
      <div>
        <p class="dx-eyebrow">${esc(pc)}${anzContextoFiltro()}</p>
        <h2>${total} de ${evaluados.length} estudiantes tienen algo por mejorar</h2>
        <p>Una materia <b>se pierde</b> cuando la nota del ${esc(pc)} es menor a <b>${corte}</b>.
          Aquí están ordenados del más urgente al menos urgente. Toca un nombre para ver todas sus notas.</p>
      </div>
    </section>
    <div class="anz-mej-tarjetas">${tarjetas}</div>
    ${anzMejDondeHtml(P)}
    <section class="anz-bloque">
      <h2>${anzMejChip === "todos" ? "Todos los que deben mejorar" : esc(ANZ_MEJ_PRIORIDADES.find((p) => p[0] === anzMejChip)[1])}</h2>
      <div class="anz-controles">
        ${anzMejChip !== "todos" ? '<button type="button" class="boton-texto-chico" data-anz-mej-chip="todos">Ver todos</button>' : ""}
        <div class="ox-buscador anz-buscador"><input type="search" data-anz-mej-buscar placeholder="Buscar estudiante, documento o grupo..." value="${esc(anzMejBuscar)}" aria-label="Buscar estudiante" /></div>
      </div>
      <div data-anz-mej-cuerpo>${anzMejCuerpoHtml()}</div>
    </section>
    ${anzGlosarioHtml()}`;
}

// Materias que más se pierden y grupos con más estudiantes por mejorar:
// conteos simples de personas, sin porcentajes de notas.
function anzMejDondeHtml(P) {
  const porArea = new Map();
  // Sin los posibles retiros: sus 1.0 son de no venir, no de la materia.
  anzMejDatos.filter((e) => e.prioridad !== "retiro").forEach((e) => e.areas_en_bajo.forEach((a) => porArea.set(a, (porArea.get(a) || 0) + 1)));
  const idArea = new Map();
  P.areas.forEach((a) => idArea.set(a.area_nombre, idArea.has(a.area_nombre) ? null : a.area_id)); // nombre repetido: sin clic
  const areas = [...porArea.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([nombre, n]) => ({
    etiqueta: nombre, valor: n, texto: `<b>${n}</b> ${n === 1 ? "estudiante" : "estudiantes"}`,
    attr: idArea.get(nombre) ? `data-anz-mej-area="${idArea.get(nombre)}"` : "",
    titulo: `Ver quiénes pierden ${nombre}`,
  }));

  const porGrupo = new Map();
  anzMejDatos.forEach((e) => {
    const k = `${e.sede_id}|${e.grado}|${e.curso ?? ""}`;
    const g = porGrupo.get(k) || { nombre: e.nombre_grupo, sede: e.sede_nombre, n: 0, urgentes: 0 };
    g.n++;
    if (e.prioridad === "urgente") g.urgentes++;
    porGrupo.set(k, g);
  });
  const grupos = [...porGrupo.entries()].sort((a, b) => b[1].urgentes - a[1].urgentes || b[1].n - a[1].n).slice(0, 8).map(([k, g]) => ({
    etiqueta: `${g.nombre}${anzSedeId ? "" : ` · ${anzSede(g.sede)}`}`, valor: g.urgentes,
    texto: `<b>${g.urgentes}</b> urgentes <span class="prom-tenue">· ${g.n} en total</span>`,
    attr: `data-anz-mej-grupo="${k}"`, titulo: `Ver solo ${g.nombre}`,
  }));

  const cols = [];
  if (!anzAreaId && areas.length) {
    const max = Math.max(...areas.map((x) => x.valor));
    cols.push(`<div class="anz-foco-col"><h3 class="ox-h3">Materias que más se pierden</h3>
      <p class="anz-sub">Cuántos estudiantes pierden cada materia (sin contar los posibles retiros). Toca una para ver solo esa.</p>
      ${anzBarrasHtml(areas, { max, color: ANZ_COLOR_NIVEL.BAJO })}</div>`);
  }
  if (anzCurso === null && grupos.length > 1) {
    const max = Math.max(1, ...grupos.map((x) => x.valor));
    cols.push(`<div class="anz-foco-col"><h3 class="ox-h3">Grupos con más casos urgentes</h3>
      <p class="anz-sub">Cuántos estudiantes urgentes hay en cada grupo. Toca uno para ver solo ese grupo.</p>
      ${anzBarrasHtml(grupos, { max, color: "#dc2626" })}</div>`);
  }
  if (!cols.length) return "";
  return `<section class="anz-bloque"><h2>¿Dónde está el problema?</h2><div class="anz-dos-col">${cols.join("")}</div></section>`;
}

function anzMejCuerpoHtml() {
  const q = normalizarTexto(anzMejBuscar.trim());
  const lista = anzMejDatos.filter(
    (e) => (anzMejChip === "todos" || e.prioridad === anzMejChip) &&
      (!q || normalizarTexto(`${e.nombre_completo} ${e.documento} ${e.nombre_grupo} ${e.sede_nombre}`).includes(q))
  );
  if (!lista.length) {
    return `<div class="ox-vacio"><p>${q ? "Ningún estudiante coincide con la búsqueda." : "Ningún estudiante en este grupo. ¡Buena noticia!"}</p></div>`;
  }
  const nombres = Object.fromEntries(ANZ_MEJ_PRIORIDADES.map(([id, n, color]) => [id, [n, color]]));
  const visibles = lista.slice(0, anzMejLimite);
  const conSede = !anzSedeId;
  const filas = visibles.map((e) => {
    const [nombre, color] = nombres[e.prioridad];
    let pierde = e.areas_en_bajo.length
      ? `<b>${e.areas_en_bajo.length}</b>: ${e.areas_en_bajo.map((a) => `<span class="anz-chip-area">${esc(a)}</span>`).join("")}`
      : '<span class="prom-tenue">ninguna</span>';
    if (e.riesgo_retiro) {
      pierde = `<span class="anz-mej-motivo">${e.riesgo_retiro === "MUY_PROBABLE" ? "<b>Muy probable.</b> " : ""}${esc(e.motivo_retiro)}</span>${e.areas_en_bajo.length ? `<br>${pierde}` : ""}`;
    }
    return `<tr class="anz-fila-clic" data-anz-ver-estudiante="${e.estudiante_id}" tabindex="0">
      <td><span class="anz-mej-prioridad" style="--mej-color:${color}">${nombre}</span><strong>${esc(e.nombre_completo)}</strong><br><span class="prom-tenue">${esc(e.documento)}</span></td>
      <td>${esc(e.nombre_grupo)}${conSede ? `<br><span class="prom-tenue">${esc(anzSede(e.sede_nombre))}</span>` : ""}</td>
      <td class="anz-mej-pierde">${pierde}</td>
      <td class="anz-num ${e.nivel_comparado === "BAJO" ? "anz-nota-baja" : ""}"><b>${anzF(e.promedio_comparado)}</b></td>
      <td>${anzCambioEnPalabras(e)}</td></tr>`;
  }).join("");
  return `
    <p class="anz-nota">${anzPl(lista.length, "estudiante", "estudiantes")}${q ? " (con la búsqueda)" : ""}.</p>
    <div class="ox-tabla-envoltura"><table class="ox-tabla anz-tabla">
      <thead><tr><th>Estudiante</th><th>Grupo</th><th>Materias que pierde</th><th class="anz-num">Promedio</th><th>Frente al ${esc(anzPB())}</th></tr></thead>
      <tbody>${filas}</tbody></table></div>
    ${lista.length > visibles.length ? `<button type="button" class="boton secundario boton-chico anz-mas" data-anz-mej-mas>Mostrar ${Math.min(50, lista.length - visibles.length)} más (quedan ${lista.length - visibles.length})</button>` : ""}`;
}

// --- ¿Pierden el año? (comparacion_academica.riesgo_perder_anio) -----------
// Regla del colegio: nota final de cada materia = promedio de los 4
// períodos; una materia por debajo de 3.0 = año perdido. Por materia se
// calcula qué promedio necesita en los períodos que faltan.

let anzAnioChip = "todos"; // todos | NO_RECUPERA | POSIBLE_PERDIDA | CUIDADO
let anzAnioBuscar = "", anzAnioLimite = 50, anzAnioDatos = null, anzAnioRetiros = new Map();

const ANZ_ANIO_CATEGORIAS = [
  ["NO_RECUPERA", "Ya no se recupera", "#7f1d1d"],
  ["POSIBLE_PERDIDA", "Posible pérdida", "#dc2626"],
  ["CUIDADO", "Tener cuidado", "#d97706"],
];

function anzPerderAnio() {
  return anzGet(`/api/boletines/comparacion/perder-anio?${paramsComparacion()}`);
}

function anzAnioReglas(R) {
  const min = anzF(R.nota_minima, 1), max = anzF(R.nota_maxima, 1);
  return {
    NO_RECUPERA: `Aunque saque ${max} en todo lo que falta, alguna materia no llega a ${min}.`,
    POSIBLE_PERDIDA: `Necesita ${anzF(R.umbral_posible_perdida, 1)} o más en lo que falta para ganar alguna materia.`,
    CUIDADO: `Hoy va perdiendo alguna materia, pero la recupera si sube a una nota alcanzable (menos de ${anzF(R.umbral_posible_perdida, 1)}).`,
  };
}

function anzAnioCuenta(R) {
  const cuenta = { NO_RECUPERA: 0, POSIBLE_PERDIDA: 0, CUIDADO: 0 };
  R.estudiantes.forEach((e) => cuenta[e.categoria]++);
  return cuenta;
}

async function anzPerderAnioHtml() {
  const [P, R, todos] = await Promise.all([anzPanorama(), anzPerderAnio(), anzEstudiantesTodos()]);
  anzRecordarGrupos(P);
  if (!R.total_estudiantes) return anzVacioFiltroHtml();
  anzAnioDatos = R;
  anzAnioRetiros = new Map(todos.filter((e) => e.riesgo_retiro).map((e) => [e.estudiante_id, e.riesgo_retiro]));
  const cuenta = anzAnioCuenta(R), reglas = anzAnioReglas(R);
  const faltan = R.periodos_anio - R.hasta_periodo;
  const nota = !cuenta.NO_RECUPERA && faltan >= 2
    ? `<p class="anz-nota">Con ${faltan} períodos por delante, todavía nadie está perdido del todo: hasta quien tiene ${anzF(R.nota_minima - 2, 1)} de promedio puede llegar a ${anzF(R.nota_minima, 1)} con ${anzF(R.nota_maxima, 1)} en lo que falta. Desde el Período ${R.periodos_anio - 1} empiezan a aparecer los que ya no se recuperan.</p>`
    : "";
  const tarjetas = ANZ_ANIO_CATEGORIAS.map(([id, nombre, color]) => `
    <button type="button" class="anz-mej-tarjeta${anzAnioChip === id ? " activo" : ""}" data-anz-anio-chip="${id}" aria-pressed="${anzAnioChip === id}" style="--mej-color:${color}">
      <span class="anz-mej-tarjeta-etq"><span class="anz-muestra" style="background:${color}"></span>${nombre}</span>
      <b>${cuenta[id]}</b>
      <span>${cuenta[id] === 1 ? "estudiante" : "estudiantes"}</span>
      <span class="anz-mej-regla">${esc(reglas[id])}</span>
    </button>`).join("");
  const enRiesgo = R.estudiantes.length;
  return `
    <section class="anz-lectura anz-lectura-${cuenta.NO_RECUPERA || cuenta.POSIBLE_PERDIDA ? "baja" : "estable"}">
      ${icono("calendar-x")}
      <div>
        <p class="dx-eyebrow">Año ${R.anio_lectivo} · van ${R.hasta_periodo} de ${R.periodos_anio} períodos${anzContextoFiltro()}</p>
        <h2>${enRiesgo} de ${R.total_estudiantes} estudiantes pueden perder el año</h2>
        <p>La nota final de cada materia es el <b>promedio de los ${R.periodos_anio} períodos</b>. Si una sola materia queda por debajo de
          <b>${anzF(R.nota_minima, 1)}</b>, se pierde el año. Aquí se calcula, materia por materia, qué nota necesita en ${faltan === 1 ? "el período que falta" : `los ${faltan} períodos que faltan`}.</p>
      </div>
    </section>
    <div class="anz-mej-tarjetas">${tarjetas}</div>
    ${nota}
    <section class="anz-bloque">
      <h2>${anzAnioChip === "todos" ? "Todos los que pueden perder el año" : esc(ANZ_ANIO_CATEGORIAS.find((c) => c[0] === anzAnioChip)[1])}</h2>
      <div class="anz-controles">
        ${anzAnioChip !== "todos" ? '<button type="button" class="boton-texto-chico" data-anz-anio-chip="todos">Ver todos</button>' : ""}
        <div class="ox-buscador anz-buscador"><input type="search" data-anz-anio-buscar placeholder="Buscar estudiante, documento o grupo..." value="${esc(anzAnioBuscar)}" aria-label="Buscar estudiante" /></div>
      </div>
      <div data-anz-anio-cuerpo>${anzAnioCuerpoHtml()}</div>
    </section>
    <details class="anz-datos anz-glosario"><summary>${icono("calculator")} ¿Cómo se calcula «qué nota necesita»?</summary>
      <p>Ejemplo: en Matemáticas sacó 1.5 en el P1 y 2.0 en el P2. Para terminar el año en ${anzF(R.nota_minima, 1)} necesita sumar
        ${anzF(R.nota_minima, 1)} × ${R.periodos_anio} = ${anzF(R.nota_minima * R.periodos_anio, 1)} puntos; ya lleva 3.5, le faltan ${anzF(R.nota_minima * R.periodos_anio - 3.5, 1)}
        repartidos en 2 períodos: necesita <b>${anzF((R.nota_minima * R.periodos_anio - 3.5) / 2)}</b> de promedio en el P3 y el P4.</p>
      <p>Las materias donde casi todo el grupo tiene 1.0 (nota que el docente parece no haber cargado) no se cuentan. Si a un estudiante le falta la nota de algún período en el sistema, se cuenta solo lo que hay.</p>
    </details>`;
}

function anzAnioCuerpoHtml() {
  const R = anzAnioDatos;
  if (!R) return "";
  const q = normalizarTexto(anzAnioBuscar.trim());
  const lista = R.estudiantes.filter(
    (e) => (anzAnioChip === "todos" || e.categoria === anzAnioChip) &&
      (!q || normalizarTexto(`${e.nombre_completo} ${e.documento} ${e.nombre_grupo} ${e.sede_nombre}`).includes(q))
  );
  if (!lista.length) {
    return `<div class="ox-vacio"><p>${q ? "Ningún estudiante coincide con la búsqueda." : "Ningún estudiante en este grupo."}</p></div>`;
  }
  const cat = Object.fromEntries(ANZ_ANIO_CATEGORIAS.map(([id, n, c]) => [id, [n, c]]));
  const conSede = !anzSedeId;
  const filas = lista.slice(0, anzAnioLimite).map((e) => {
    const [nombre, color] = cat[e.categoria];
    const retiro = anzAnioRetiros.get(e.estudiante_id);
    const materias = e.materias.map((m) => {
      const [, c] = cat[m.categoria];
      const notas = m.notas.map((n) => `P${n.periodo} ${anzF(n.valor, 1)}`).join(" · ");
      const necesita = m.necesita === null ? `final ${anzF(m.final)}` : m.necesita > R.nota_maxima ? `necesitaría ${anzF(m.necesita)}` : `necesita ${anzF(m.necesita)}`;
      return `<div class="anz-anio-materia" style="--mej-color:${c}"><b>${esc(m.area_nombre)}</b> <span class="prom-tenue">${notas}</span> → <b class="anz-anio-necesita">${necesita}</b></div>`;
    }).join("");
    return `<tr class="anz-fila-clic" data-anz-ver-estudiante="${e.estudiante_id}" tabindex="0">
      <td><span class="anz-mej-prioridad" style="--mej-color:${color}">${nombre}</span>${retiro ? `<span class="anz-mej-prioridad" style="--mej-color:#6d28d9">¿retirado?</span>` : ""}<br><strong>${esc(e.nombre_completo)}</strong><br><span class="prom-tenue">${esc(e.documento)}</span></td>
      <td>${esc(e.nombre_grupo)}${conSede ? `<br><span class="prom-tenue">${esc(anzSede(e.sede_nombre))}</span>` : ""}</td>
      <td class="anz-mej-pierde">${materias}</td></tr>`;
  }).join("");
  return `
    <p class="anz-nota">${anzPl(lista.length, "estudiante", "estudiantes")}${q ? " (con la búsqueda)" : ""}, del más grave al menos grave. Toca un nombre para ver todas sus notas.</p>
    <div class="ox-tabla-envoltura"><table class="ox-tabla anz-tabla">
      <thead><tr><th>Estudiante</th><th>Grupo</th><th>Materias en riesgo y nota que necesita en lo que falta</th></tr></thead>
      <tbody>${filas}</tbody></table></div>
    ${lista.length > anzAnioLimite ? `<button type="button" class="boton secundario boton-chico anz-mas" data-anz-anio-mas>Mostrar ${Math.min(50, lista.length - anzAnioLimite)} más (quedan ${lista.length - anzAnioLimite})</button>` : ""}`;
}

// --- Fortalezas y debilidades ---------------------------------------------
// Pedido 05/10/2026: frases cortas, calculadas con reglas fijas sobre los
// mismos datos del panorama (nada escrito a mano), para leer y exponer en
// la comisión de evaluación. Cada una trae los números que la sustentan.

const ANZ_FYD_PROM_FUERTE = 3.5; // materia "fuerte": promedio de 3.5 o más hoy
const ANZ_FYD_VARIACION = 0.1; // mismo umbral que los hallazgos por área
const ANZ_FYD_PCT_BAJO = 15; // materia/grupo "débil": 15% o más en bajo

function anzFortalezasDebilidades(P, todos, R) {
  const r = P.resumen, pb = anzPB(), corte = anzCorte();
  const F = [], D = [];
  const pctBajo = (x) => anzPct(x.actual_n_bajo, x.actual_evaluados);
  const areas = P.areas.filter((a) => a.actual_evaluados >= ANZ_MIN_AREA);
  const areaAttr = (a) => `data-anz-filtro="area_id" data-anz-valor="${a.area_id}"`;

  if (!anzAreaId) {
    const fuertes = areas.filter((a) => a.actual_promedio >= ANZ_FYD_PROM_FUERTE).sort((a, b) => b.actual_promedio - a.actual_promedio).slice(0, 3);
    if (fuertes.length) F.push({
      titulo: fuertes.length === 1 ? `La materia más fuerte es ${fuertes[0].area_nombre}` : `Las materias más fuertes son ${fuertes.map((a) => a.area_nombre).join(", ")}`,
      lineas: fuertes.map((a) => [a.area_nombre, `promedio ${anzF(a.actual_promedio)}`, `la pierde el ${anzP(pctBajo(a))}`, areaAttr(a)]),
    });
    const suben = areas.filter((a) => a.variacion !== null && a.variacion >= ANZ_FYD_VARIACION).sort((a, b) => b.variacion - a.variacion).slice(0, 3);
    if (suben.length) F.push({
      titulo: `${suben.length === 1 ? "Mejoró" : "Mejoraron"} ${suben.map((a) => a.area_nombre).join(", ")} frente al ${pb}`,
      lineas: suben.map((a) => [a.area_nombre, `${anzF(a.promedio_base)} → ${anzF(a.promedio_comparado)}`, `subió ${anzF(a.variacion)}`, areaAttr(a)]),
    });
    const debiles = areas.filter((a) => pctBajo(a) >= ANZ_FYD_PCT_BAJO).sort((a, b) => pctBajo(b) - pctBajo(a)).slice(0, 3);
    if (debiles.length) D.push({
      titulo: `${debiles.length === 1 ? "La materia que más se pierde es" : "Las materias que más se pierden son"} ${debiles.map((a) => a.area_nombre).join(", ")}`,
      lineas: debiles.map((a) => [a.area_nombre, `la pierde el ${anzP(pctBajo(a))}`, `${a.actual_n_bajo} de ${a.actual_evaluados} notas menores a ${corte}`, areaAttr(a)]),
    });
    const bajan = areas.filter((a) => a.variacion !== null && a.variacion <= -ANZ_FYD_VARIACION).sort((a, b) => a.variacion - b.variacion).slice(0, 3);
    if (bajan.length) D.push({
      titulo: `${bajan.length === 1 ? "Bajó" : "Bajaron"} ${bajan.map((a) => a.area_nombre).join(", ")} frente al ${pb}`,
      lineas: bajan.map((a) => [a.area_nombre, `${anzF(a.promedio_base)} → ${anzF(a.promedio_comparado)}`, `bajó ${anzF(Math.abs(a.variacion))}`, areaAttr(a)]),
    });
  }

  const n = r.estudiantes_comparables;
  if (n && r.variacion_promedio >= ANZ_TENDENCIA_ESTABLE) {
    F.push({ titulo: `El promedio general subió ${anzF(r.variacion_promedio)}`, lineas: [[`Mismos ${n} estudiantes`, `${anzF(r.promedio_base)} → ${anzF(r.promedio_comparado)}`]] });
  } else if (n && r.variacion_promedio <= -ANZ_TENDENCIA_ESTABLE) {
    D.push({ titulo: `El promedio general bajó ${anzF(Math.abs(r.variacion_promedio))}`, lineas: [[`Mismos ${n} estudiantes`, `${anzF(r.promedio_base)} → ${anzF(r.promedio_comparado)}`]] });
  }
  if (n && r.mejoraron) {
    F.push({
      titulo: `${r.mejoraron} ${r.mejoraron === 1 ? "estudiante mejoró" : "estudiantes mejoraron"} su promedio`,
      lineas: [[`De ${n} con notas en los dos períodos`, `${anzP(r.pct_mejoraron)}`, "", 'data-anz-cambio="mejoraron"'],
        ...(r.salieron_de_bajo ? [[`Salieron de desempeño bajo`, `${r.salieron_de_bajo}`, "", 'data-anz-cambio="salieron_bajo"']] : [])],
    });
  }
  const hoy = r.actual_evaluados;
  const altos = (r.actual_distribucion.ALTO || 0) + (r.actual_distribucion.SUPERIOR || 0);
  if (hoy && altos) {
    F.push({ titulo: `${altos} ${altos === 1 ? "estudiante tiene" : "estudiantes tienen"} promedio Alto o Superior`, lineas: [[`De ${hoy} evaluados hoy`, anzP(anzPct(altos, hoy))]] });
  }
  if (n && r.entraron_a_bajo) {
    D.push({
      titulo: `${r.entraron_a_bajo} ${r.entraron_a_bajo === 1 ? "estudiante pasó" : "estudiantes pasaron"} a desempeño bajo`,
      lineas: [[`Tenían ${corte} o más en el ${pb} y ahora menos`, `${r.entraron_a_bajo}`, "", 'data-anz-cambio="entraron_bajo"'],
        ...(r.permanecen_en_bajo ? [[`Siguen en bajo desde el ${pb}`, `${r.permanecen_en_bajo}`, "", 'data-anz-cambio="permanecen_bajo"']] : [])],
    });
  }
  const { cuenta } = anzClasificarMejora(todos);
  if (cuenta.urgente) {
    D.push({ titulo: `${cuenta.urgente} ${cuenta.urgente === 1 ? "estudiante está" : "estudiantes están"} en situación urgente`, lineas: [[`Pierden ${ANZ_MEJ_URGENTE_AREAS} materias o más, o su promedio es menor a ${corte}`, `${cuenta.urgente}`, "", 'data-anz-mej-chip="urgente"']] });
  }
  if (R) {
    const ca = anzAnioCuenta(R);
    const graves = ca.NO_RECUPERA + ca.POSIBLE_PERDIDA;
    if (graves) {
      D.push({
        titulo: `${graves} ${graves === 1 ? "estudiante puede" : "estudiantes pueden"} perder el año`,
        lineas: [
          ...(ca.NO_RECUPERA ? [["Ya no se recuperan", `${ca.NO_RECUPERA}`, "", 'data-anz-anio-chip="NO_RECUPERA"']] : []),
          ...(ca.POSIBLE_PERDIDA ? [[`Necesitan ${anzF(R.umbral_posible_perdida, 1)} o más en lo que falta`, `${ca.POSIBLE_PERDIDA}`, "", 'data-anz-anio-chip="POSIBLE_PERDIDA"']] : []),
          ...(ca.CUIDADO ? [["Además, a tener cuidado", `${ca.CUIDADO}`, "", 'data-anz-anio-chip="CUIDADO"']] : []),
        ],
      });
    }
  }
  if (cuenta.retiro) {
    D.push({ titulo: `${cuenta.retiro} ${cuenta.retiro === 1 ? "posible retiro" : "posibles retiros"}`, lineas: [["Tienen 1.0 en varias materias o ya no aparecen en las notas", `${cuenta.retiro}`, "", 'data-anz-mej-chip="retiro"']] });
  }

  if (anzCurso === null) {
    const porGrupo = anzGrado !== null;
    const unidades = (porGrupo ? P.grupos : P.grados).filter((g) => g.actual_evaluados >= ANZ_MIN_GRUPO);
    if (unidades.length > 1) {
      const nombre = (g) => (porGrupo ? g.nombre_grupo : anzNombreGrado(g.grado));
      const attr = (g) => (porGrupo ? `data-anz-grupo="${g.sede_id ?? ""}|${g.grado}|${g.curso ?? ""}"` : `data-anz-filtro="grado" data-anz-valor="${g.grado}"`);
      const mejores = [...unidades].sort((a, b) => b.actual_promedio - a.actual_promedio).slice(0, 2);
      F.push({
        titulo: `${porGrupo ? "Grupos" : "Grados"} con mejor promedio: ${mejores.map(nombre).join(" y ")}`,
        lineas: mejores.map((g) => [nombre(g), `promedio ${anzF(g.actual_promedio)}`, `${anzP(pctBajo(g))} en bajo`, attr(g)]),
      });
      const peores = unidades.filter((g) => pctBajo(g) >= ANZ_FYD_PCT_BAJO).sort((a, b) => pctBajo(b) - pctBajo(a)).slice(0, 3);
      if (peores.length) D.push({
        titulo: `${porGrupo ? "Grupos" : "Grados"} con más estudiantes en bajo: ${peores.map(nombre).join(", ")}`,
        lineas: peores.map((g) => [nombre(g), `${anzP(pctBajo(g))} en bajo`, `${g.actual_n_bajo} de ${g.actual_evaluados} estudiantes`, attr(g)]),
      });
    }
  }
  return { fortalezas: F, debilidades: D };
}

function anzFydListaHtml(items, tipo) {
  if (!items.length) {
    return `<p class="ox-vacio-chico">${tipo === "f" ? "No se encontraron fortalezas con estas reglas." : "No se encontraron debilidades con estas reglas."}</p>`;
  }
  return `<ul class="anz-fyd-lista">${items.map((it) => `
    <li><strong>${esc(it.titulo)}</strong>
      <ul>${it.lineas.map(([etq, a, b, attr]) => {
        const txt = `${esc(etq)}: <b>${esc(a)}</b>${b ? ` <span class="prom-tenue">· ${esc(b)}</span>` : ""}`;
        return `<li>${attr ? `<button type="button" class="anz-enlace" ${attr}>${txt}</button>` : txt}</li>`;
      }).join("")}</ul></li>`).join("")}</ul>`;
}

async function anzFortalezasHtml() {
  const [P, todos, R] = await Promise.all([anzPanorama(), anzEstudiantesTodos(), anzPerderAnio()]);
  anzRecordarGrupos(P);
  if (!P.resumen.total_estudiantes) return anzVacioFiltroHtml();
  const { fortalezas, debilidades } = anzFortalezasDebilidades(P, todos, R);
  return `
    <section class="anz-lectura anz-lectura-estable">
      ${icono("scale")}
      <div>
        <p class="dx-eyebrow">${esc(anzPB())} → ${esc(anzPC())}${anzContextoFiltro()}</p>
        <h2>Fortalezas y debilidades</h2>
        <p>Lo que va bien y lo que hay que trabajar, en frases cortas. Cambia el filtro (grado, grupo o materia) para ver las de ese grupo.
          Toca un dato para ver su detalle.</p>
      </div>
      <button type="button" class="boton" data-anz-exponer>${icono("presentation")} Exponer</button>
    </section>
    <div class="anz-dos-col anz-fyd">
      <section class="anz-bloque anz-fyd-col anz-fyd-f"><h2>${icono("thumbs-up")} Fortalezas</h2>${anzFydListaHtml(fortalezas, "f")}</section>
      <section class="anz-bloque anz-fyd-col anz-fyd-d"><h2>${icono("triangle-alert")} Debilidades</h2>${anzFydListaHtml(debilidades, "d")}</section>
    </div>
    <details class="anz-datos anz-glosario"><summary>${icono("list-checks")} ¿Con qué reglas se escogen?</summary>
      <ul class="anz-reglas">
        <li>Materia fuerte: promedio de ${ANZ_FYD_PROM_FUERTE.toFixed(1)} o más hoy (las 3 mejores). Materia débil: ${ANZ_FYD_PCT_BAJO}% o más de sus notas por debajo de ${anzCorte()} (las 3 peores).</li>
        <li>Materia que mejoró o bajó: su promedio cambió ${ANZ_FYD_VARIACION.toFixed(1)} o más entre los mismos estudiantes.</li>
        <li>Solo se tienen en cuenta materias con ${ANZ_MIN_AREA} notas o más y ${anzGrado !== null ? "grupos" : "grados"} con ${ANZ_MIN_GRUPO} estudiantes o más.</li>
        <li>Urgentes y posibles retiros: las mismas reglas de «¿Quién debe mejorar?». Perder el año: las de «¿Pierden el año?».</li>
      </ul>
    </details>
    ${anzGlosarioHtml()}`;
}

// --- Modo exposición: diapositivas a pantalla completa ----------------------
// Para proyectar en la reunión o comisión de evaluación. Se arma con los
// mismos datos (y el mismo filtro) que está en pantalla; también se imprime
// (una diapositiva por hoja, horizontal).

let anzExpoIdx = 0;
const ANZ_EXPO_POR_DIAPO = 12; // nombres por diapositiva

function anzExpoNombresDiapos(titulo, sub, lista, col3) {
  const out = [];
  for (let i = 0; i < lista.length; i += ANZ_EXPO_POR_DIAPO) {
    const parte = lista.slice(i, i + ANZ_EXPO_POR_DIAPO);
    const pag = lista.length > ANZ_EXPO_POR_DIAPO ? ` <span class="anz-expo-pag">(${i / ANZ_EXPO_POR_DIAPO + 1} de ${Math.ceil(lista.length / ANZ_EXPO_POR_DIAPO)})</span>` : "";
    out.push(`<h2>${titulo}${pag}</h2><p class="anz-expo-sub">${sub}</p>
      <table class="anz-expo-tabla"><tbody>${parte.map((e) => `<tr><td><b>${esc(e.nombre_completo)}</b></td><td>${esc(e.nombre_grupo)}</td><td>${col3(e)}</td></tr>`).join("")}</tbody></table>`);
  }
  return out;
}

async function anzAbrirExposicion() {
  const [P, todos, R] = await Promise.all([anzPanorama(), anzEstudiantesTodos(), anzPerderAnio()]);
  const r = P.resumen, pb = anzPB(), pc = anzPC(), corte = anzCorte();
  const alcance = anzContextoFiltro().replace(/^ · /, "");
  const { fortalezas, debilidades } = anzFortalezasDebilidades(P, todos, R);
  const { evaluados, lista, cuenta } = anzClasificarMejora(todos);
  const fyd = (items, vacio) =>
    items.length
      ? `<ul class="anz-expo-puntos">${items.slice(0, 6).map((it) => `<li><b>${esc(it.titulo)}</b><span>${it.lineas.map(([e, a, b]) => `${esc(e)}: ${esc(a)}${b ? ` (${esc(b)})` : ""}`).join(" · ")}</span></li>`).join("")}</ul>`
      : `<p class="anz-expo-sub">${vacio}</p>`;
  const numero = (valor, etq, sub, color) => `<div class="anz-expo-num" style="--expo-color:${color || "var(--texto)"}"><b>${valor}</b><span>${etq}</span>${sub ? `<small>${sub}</small>` : ""}</div>`;

  const d = [];
  d.push(`<div class="anz-expo-portada"><p class="anz-expo-sub">I.E.T.A.B.A. · Análisis académico</p>
    <h1>${esc(alcance)}</h1><p class="anz-expo-periodos">${esc(pb)} → ${esc(pc)}</p>
    <p class="anz-expo-sub">${new Date().toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" })}</p></div>`);
  const pctBajoHoy = anzPct(r.actual_n_bajo, r.actual_evaluados);
  d.push(`<h2>¿Cómo vamos?</h2><p class="anz-expo-sub">${esc(P.lectura.frase)}</p>
    <div class="anz-expo-nums">
      ${numero(anzF(r.actual_promedio), "promedio general", r.estudiantes_comparables ? `${r.variacion_promedio >= 0 ? "subió" : "bajó"} ${anzF(Math.abs(r.variacion_promedio))} desde el ${esc(pb)}` : "")}
      ${numero(anzP(pctBajoHoy), "en desempeño bajo", `${r.actual_n_bajo} de ${r.actual_evaluados} con promedio menor a ${corte}`, "#c2410c")}
      ${r.estudiantes_comparables ? numero(r.mejoraron, "mejoraron", `y ${r.empeoraron} empeoraron, de ${r.estudiantes_comparables}`, "#16a34a") : ""}
    </div>`);
  d.push(`<h2 class="anz-expo-verde">${icono("thumbs-up")} Fortalezas</h2>${fyd(fortalezas, "No se encontraron fortalezas con las reglas del análisis.")}`);
  d.push(`<h2 class="anz-expo-rojo">${icono("triangle-alert")} Debilidades</h2>${fyd(debilidades, "No se encontraron debilidades con las reglas del análisis.")}`);
  d.push(`<h2>¿Quién debe mejorar?</h2><p class="anz-expo-sub">${lista.length} de ${evaluados.length} estudiantes. Una materia se pierde con nota menor a ${corte}.</p>
    <div class="anz-expo-nums">${ANZ_MEJ_PRIORIDADES.map(([id, nombre, color]) => numero(cuenta[id], nombre, esc(anzMejReglas()[id]), color)).join("")}</div>`);
  const ca = anzAnioCuenta(R);
  d.push(`<h2>¿Pierden el año?</h2><p class="anz-expo-sub">Van ${R.hasta_periodo} de ${R.periodos_anio} períodos. Una materia con promedio final menor a ${anzF(R.nota_minima, 1)} = año perdido.</p>
    <div class="anz-expo-nums">${ANZ_ANIO_CATEGORIAS.map(([id, nombre, color]) => numero(ca[id], nombre, esc(anzAnioReglas(R)[id]), color)).join("")}</div>`);
  const graves = R.estudiantes.filter((e) => e.categoria !== "CUIDADO");
  if (graves.length && (anzCurso !== null || graves.length <= ANZ_EXPO_POR_DIAPO * 4)) {
    const nomCat = Object.fromEntries(ANZ_ANIO_CATEGORIAS.map(([id, n]) => [id, n]));
    d.push(...anzExpoNombresDiapos("Pueden perder el año", `Nota que necesitan en lo que falta del año para ganar cada materia.`, graves,
      (e) => `<b>${nomCat[e.categoria]}.</b> ${e.materias.filter((m) => m.categoria !== "CUIDADO").map((m) => `${esc(m.area_nombre)} (${m.necesita === null ? `final ${anzF(m.final)}` : `necesita ${anzF(m.necesita)}`})`).join(", ")}`));
  }
  const retiros = lista.filter((e) => e.prioridad === "retiro");
  if (retiros.length) {
    d.push(...anzExpoNombresDiapos(`Posibles retiros`, "Confirmar con el director de grupo si siguen asistiendo.", retiros,
      (e) => `${e.riesgo_retiro === "MUY_PROBABLE" ? "<b>Muy probable.</b> " : ""}${esc(e.motivo_retiro)}`));
  }
  const urgentes = lista.filter((e) => e.prioridad === "urgente");
  if (urgentes.length && (anzCurso !== null || urgentes.length <= ANZ_EXPO_POR_DIAPO * 3)) {
    d.push(...anzExpoNombresDiapos("Estudiantes en situación urgente", `Pierden ${ANZ_MEJ_URGENTE_AREAS} materias o más, o su promedio es menor a ${corte}.`, urgentes,
      (e) => `${e.areas_en_bajo.length} materias: ${esc(e.areas_en_bajo.join(", "))}`));
  } else if (urgentes.length) {
    const porGrupo = new Map();
    urgentes.forEach((e) => porGrupo.set(e.nombre_grupo, (porGrupo.get(e.nombre_grupo) || 0) + 1));
    const top = [...porGrupo.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
    d.push(`<h2>Grupos con más estudiantes urgentes</h2><p class="anz-expo-sub">${urgentes.length} estudiantes urgentes en total. Para ver los nombres, filtra un grupo y vuelve a exponer.</p>
      <table class="anz-expo-tabla"><tbody>${top.map(([g, k]) => `<tr><td><b>${esc(g)}</b></td><td>${k} ${k === 1 ? "estudiante" : "estudiantes"}</td></tr>`).join("")}</tbody></table>`);
  }

  document.getElementById("anz-expo")?.remove();
  const capa = document.createElement("div");
  capa.id = "anz-expo";
  capa.className = "anz-expo";
  capa.setAttribute("role", "dialog");
  capa.setAttribute("aria-label", "Exposición del análisis académico");
  capa.innerHTML = `
    <div class="anz-expo-barra">
      <span data-anz-expo-contador></span>
      <button type="button" class="boton secundario boton-chico" data-anz-expo-ir="-1" aria-label="Anterior">${icono("chevron-left")}</button>
      <button type="button" class="boton secundario boton-chico" data-anz-expo-ir="1" aria-label="Siguiente">${icono("chevron-right")}</button>
      <button type="button" class="boton secundario boton-chico" data-anz-expo-completa>${icono("maximize")} Pantalla completa</button>
      <button type="button" class="boton secundario boton-chico" data-anz-expo-imprimir>${icono("printer")} Imprimir</button>
      <button type="button" class="boton secundario boton-chico" data-anz-expo-cerrar>${icono("x")} Cerrar</button>
    </div>
    ${d.map((html, i) => `<section class="anz-expo-diapo" data-i="${i}">${html}<footer>${esc(alcance)} · ${esc(pb)} → ${esc(pc)} · ${i + 1}/${d.length}</footer></section>`).join("")}`;
  document.body.appendChild(capa);
  document.body.classList.add("anz-expo-abierta");
  anzExpoIr(0);
  capa.querySelector("[data-anz-expo-ir='1']").focus();
}

function anzExpoIr(i) {
  const diapos = document.querySelectorAll("#anz-expo .anz-expo-diapo");
  if (!diapos.length) return;
  anzExpoIdx = Math.max(0, Math.min(diapos.length - 1, i));
  diapos.forEach((el, k) => el.classList.toggle("activa", k === anzExpoIdx));
  const cont = document.querySelector("[data-anz-expo-contador]");
  if (cont) cont.textContent = `${anzExpoIdx + 1} de ${diapos.length} · usa las flechas del teclado`;
}

function anzCerrarExposicion() {
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  document.getElementById("anz-expo")?.remove();
  document.body.classList.remove("anz-expo-abierta");
}

document.addEventListener("click", (ev) => {
  const t = ev.target;
  if (t.closest("[data-anz-exponer]")) {
    anzAbrirExposicion().catch((e) => alert("No se pudo preparar la exposición: " + e.message));
    return;
  }
  if (!t.closest("#anz-expo")) return;
  let el;
  if ((el = t.closest("[data-anz-expo-ir]"))) return anzExpoIr(anzExpoIdx + Number(el.dataset.anzExpoIr));
  if (t.closest("[data-anz-expo-cerrar]")) return anzCerrarExposicion();
  if (t.closest("[data-anz-expo-imprimir]")) return window.print();
  if (t.closest("[data-anz-expo-completa]")) {
    const capa = document.getElementById("anz-expo");
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else capa?.requestFullscreen?.().catch(() => {});
    return;
  }
  // Clic en la diapositiva = siguiente (como un control remoto).
  if (t.closest(".anz-expo-diapo")) anzExpoIr(anzExpoIdx + 1);
});

document.addEventListener("keydown", (ev) => {
  if (!document.getElementById("anz-expo")) return;
  if (["ArrowRight", "PageDown", " "].includes(ev.key)) { ev.preventDefault(); anzExpoIr(anzExpoIdx + 1); }
  else if (["ArrowLeft", "PageUp"].includes(ev.key)) { ev.preventDefault(); anzExpoIr(anzExpoIdx - 1); }
  else if (ev.key === "Home") anzExpoIr(0);
  else if (ev.key === "End") anzExpoIr(1e9);
  else if (ev.key === "Escape" && !document.fullscreenElement) anzCerrarExposicion();
});

// Diccionario en palabras simples de lo que aparece en las demás pestañas.
function anzGlosarioHtml(abierto = false) {
  const c = anzCfg(), r = anzRangos(), pb = anzPB(), pc = anzPC();
  const t = (palabra, dice) => `<dt>${palabra}</dt><dd>${dice}</dd>`;
  return `
    <details class="anz-datos anz-glosario"${abierto ? " open" : ""}>
      <summary>${icono("book-open")} ¿Qué significa cada palabra del análisis?</summary>
      <dl>
        ${t("Promedio", `Se suman las notas de las materias del estudiante y se divide por cuántas son. Va de 1.0 a 5.0.`)}
        ${t("Período anterior y actual", `Se compara el <b>${esc(pb)}</b> (antes) con el <b>${esc(pc)}</b> (ahora).`)}
        ${t("Perder una materia / Bajo", `Nota menor a ${anzCorte()}. Es lo mismo que «desempeño bajo».`)}
        ${t("Básico, Alto, Superior", `Básico: ${r.BASICO} · Alto: ${r.ALTO} · Superior: ${r.SUPERIOR}.`)}
        ${t("Mejoró / Empeoró", `Su promedio subió (o bajó) ${c.umbral_mejora.toFixed(1)} o más de un período al otro. Si cambió menos, cuenta como <b>estable</b>.`)}
        ${t("«Los mismos estudiantes»", `Para decir si algo mejoró solo se cuentan los estudiantes que tienen notas en los dos períodos; así no se compara a unos con otros distintos.`)}
        ${t("Puntos porcentuales", `La diferencia entre dos porcentajes: pasar de 10% a 15% es subir 5 puntos.`)}
        ${t("«Pocos datos»", `Hay muy pocos estudiantes o notas para sacar conclusiones; ese número puede engañar.`)}
        ${t("Actitudinal (DESM)", `La nota de actitud y convivencia. Va aparte y no cuenta en lo académico.`)}
      </dl>
    </details>`;
}

// --- Estudiantes: la lista exacta detrás de cada número ---------------------

function anzTiposCambio() {
  const c = anzCfg(), pb = anzPB(), pc = anzPC(), corte = anzCorte();
  return [
    ["atencion", "Requieren atención", `Promedio menor a ${corte} en el ${pc}, o bajaron ${c.umbral_descenso_significativo.toFixed(1)} o más desde el ${pb}.`],
    ["entraron_bajo", "Pasaron a bajo", `Tenían ${corte} o más en el ${pb} y ahora están por debajo.`],
    ["descenso_significativo", `Bajaron ${c.umbral_descenso_significativo.toFixed(1)}+`, `Su promedio bajó ${c.umbral_descenso_significativo.toFixed(1)} puntos o más.`],
    ["empeoraron", "Empeoraron", `Su promedio bajó ${c.umbral_descenso.toFixed(1)} o más (incluye a los que bajaron mucho).`],
    ["permanecen_bajo", "Siguen en bajo", `Por debajo de ${corte} en los dos períodos.`],
    ["mejoraron", "Mejoraron", `Su promedio subió ${c.umbral_mejora.toFixed(1)} o más.`],
    ["salieron_bajo", "Salieron de bajo", `Estaban por debajo de ${corte} en el ${pb} y ya no.`],
    ["estables", "Estables", `Su promedio cambió menos de ${c.umbral_mejora.toFixed(1)}.`],
    ["bajo_actual", "En bajo hoy", `Todos los que hoy tienen promedio menor a ${corte}, tengan o no notas del ${pb}.`],
    ["sin_comparar", "Sin comparación", `No tienen notas en los dos períodos (normalmente: su grupo no tiene el ${pb} importado).`],
  ];
}

// Vista "notas por área": qué pedir al /detalle para cada tipo (filtro por
// NOTA, no por promedio del estudiante). post: filtro extra en el navegador.
const ANZ_DETALLE_POR_TIPO = {
  mejoraron: [{ tipo_cambio: "mejora" }],
  empeoraron: [{ tipo_cambio: "descenso" }],
  estables: [{ categoria_variacion: "ESTABLE" }],
  descenso_significativo: [{ categoria_variacion: "DESCENSO_SIGNIFICATIVO" }],
  permanecen_bajo: [{ nivel_base: "BAJO", nivel_comparado: "BAJO" }],
  entraron_bajo: [{ nivel_comparado: "BAJO" }, (f) => f.nivel_base !== "BAJO"],
  salieron_bajo: [{ nivel_base: "BAJO" }, (f) => f.nivel_comparado !== "BAJO"],
  bajo_actual: [{ nivel_comparado: "BAJO", solo_comparables: "false" }],
  atencion: [{ nivel_comparado: "BAJO" }, null, { categoria_variacion: "DESCENSO_SIGNIFICATIVO" }],
};
const ANZ_LIMITE_DETALLE = 3000;

async function anzCargarEstudiantes() {
  if (anzEstModo === "estudiante") {
    return anzGet(`/api/boletines/comparacion/estudiantes?${paramsComparacion({ cambio: anzEstCambio })}`);
  }
  const def = ANZ_DETALLE_POR_TIPO[anzEstCambio];
  if (!def) return null; // no aplica por nota
  const [params, post, otro] = def;
  const pedir = (extra) => anzGet(`/api/boletines/comparacion/detalle?${paramsComparacion({ ...extra, limite: ANZ_LIMITE_DETALLE })}`);
  let filas = await pedir(params);
  if (post) filas = filas.filter(post);
  if (otro) {
    const vistos = new Set(filas.map((f) => `${f.estudiante_id}|${f.area_id}`));
    (await pedir(otro)).forEach((f) => { if (!vistos.has(`${f.estudiante_id}|${f.area_id}`)) filas.push(f); });
  }
  return [...filas].sort((a, b) => (a.delta ?? 0) - (b.delta ?? 0));
}

async function anzEstudiantesHtml() {
  const P = await anzPanorama();
  const r = P.resumen;
  const conteos = {
    mejoraron: r.mejoraron, empeoraron: r.empeoraron, estables: r.estables,
    entraron_bajo: r.entraron_a_bajo, salieron_bajo: r.salieron_de_bajo, permanecen_bajo: r.permanecen_en_bajo,
    bajo_actual: r.actual_n_bajo, sin_comparar: r.total_estudiantes - r.estudiantes_comparables,
  };
  const tipos = anzTiposCambio();
  const tipo = tipos.find((t) => t[0] === anzEstCambio) || tipos[0];
  anzEstDatos = await anzCargarEstudiantes();
  const porNota = anzEstModo === "area";
  return `
    <section class="anz-bloque">
      <h2>Estudiantes · ${esc(tipo[1])}</h2>
      <p class="anz-sub">${esc(tipo[2])} ${porNota ? "En esta vista cada fila es una <b>nota</b> (estudiante + área) y la condición se aplica a cada nota." : "Cada fila es un estudiante con el promedio de sus áreas (el mismo cálculo que los números del Resumen)."}</p>
      <div class="ox-chips anz-est-chips" role="group" aria-label="Tipo de cambio">${tipos
        .map(([id, t]) => `<button type="button" class="ox-chip-filtro${anzEstCambio === id ? " activo" : ""}" data-anz-est-chip="${id}" aria-pressed="${anzEstCambio === id}">${esc(t)}${conteos[id] !== undefined ? ` <span>${conteos[id]}</span>` : ""}</button>`)
        .join("")}</div>
      <div class="anz-controles">
        ${anzSegmentado("anz-est-modo", [["estudiante", "Por estudiante"], ["area", "Notas por área"]], anzEstModo, "Ver")}
        <div class="ox-buscador anz-buscador"><input type="search" data-anz-est-buscar placeholder="Buscar estudiante, documento o grupo..." value="${esc(anzEstBuscar)}" aria-label="Buscar estudiante" /></div>
      </div>
      <div data-anz-est-cuerpo>${anzEstCuerpoHtml()}</div>
    </section>`;
}

function anzEstCuerpoHtml() {
  if (anzEstDatos === null) {
    return '<div class="ox-vacio"><p>Esta condición se mide sobre el promedio del estudiante; por nota no aplica. Usa «Por estudiante».</p></div>';
  }
  const q = normalizarTexto(anzEstBuscar.trim());
  const porNota = anzEstModo === "area";
  const lista = anzEstDatos.filter(
    (e) => !q || normalizarTexto(`${e.nombre_completo} ${e.documento} ${e.nombre_grupo} ${e.sede_nombre} ${porNota ? e.area_nombre : ""}`).includes(q)
  );
  if (!lista.length) {
    return `<div class="ox-vacio"><p>${anzEstDatos.length ? "Ningún estudiante coincide con la búsqueda." : "Ningún estudiante cumple esta condición con los filtros actuales."}</p></div>`;
  }
  const visibles = lista.slice(0, anzEstLimite);
  const conSede = !anzSedeId;
  const cabeza = porNota
    ? `<tr><th>Estudiante</th><th>Grupo</th><th>Área</th><th class="anz-num">${esc(anzPB())}</th><th class="anz-num">${esc(anzPC())}</th><th class="anz-num">Cambio</th></tr>`
    : `<tr><th>Estudiante</th><th>Grupo</th><th class="anz-num">${esc(anzPB())}</th><th class="anz-num">${esc(anzPC())}</th><th class="anz-num">Cambio</th><th>Áreas en bajo hoy</th></tr>`;
  const filas = visibles
    .map((e) => {
      const grupo = `${esc(e.nombre_grupo)}${conSede ? `<br><span class="prom-tenue">${esc(anzSede(e.sede_nombre))}</span>` : ""}`;
      if (porNota) {
        return `<tr class="anz-fila-clic" data-anz-ver-estudiante="${e.estudiante_id}" tabindex="0">
          <td><strong>${esc(e.nombre_completo)}</strong><br><span class="prom-tenue">${esc(e.documento)}</span></td><td>${grupo}</td>
          <td>${esc(e.area_nombre)}</td>
          <td class="anz-num">${anzF(e.valor_base, 1)}</td>
          <td class="anz-num ${e.nivel_comparado === "BAJO" ? "anz-nota-baja" : ""}"><b>${anzF(e.valor_comparado, 1)}</b></td>
          <td class="anz-num ${anzClaseCambio(e.delta)}">${anzS(e.delta)}</td></tr>`;
      }
      const areas = e.areas_en_bajo.length
        ? `${e.areas_en_bajo.slice(0, 3).map((a) => `<span class="anz-chip-area">${esc(a)}</span>`).join("")}${e.areas_en_bajo.length > 3 ? `<span class="prom-tenue"> y ${e.areas_en_bajo.length - 3} más</span>` : ""}`
        : '<span class="prom-tenue">ninguna</span>';
      return `<tr class="anz-fila-clic" data-anz-ver-estudiante="${e.estudiante_id}" tabindex="0">
        <td><strong>${esc(e.nombre_completo)}</strong><br><span class="prom-tenue">${esc(e.documento)}</span></td><td>${grupo}</td>
        <td class="anz-num">${anzF(e.promedio_base)}</td>
        <td class="anz-num ${e.nivel_comparado === "BAJO" ? "anz-nota-baja" : ""}"><b>${anzF(e.promedio_comparado)}</b></td>
        <td class="anz-num ${anzClaseCambio(e.delta)}">${e.comparable ? anzS(e.delta) : '<span class="prom-tenue">sin ' + esc(anzPB()) + "</span>"}</td>
        <td>${areas}</td></tr>`;
    })
    .join("");
  const truncado = porNota && anzEstDatos.length >= ANZ_LIMITE_DETALLE;
  return `
    <p class="anz-nota">${lista.length} ${porNota ? (lista.length === 1 ? "nota" : "notas") : lista.length === 1 ? "estudiante" : "estudiantes"}${q ? " (con la búsqueda)" : ""} · ordenados del que más bajó al que más subió. Clic en una fila para ver la evolución del estudiante.${truncado ? ` Se cargaron las primeras ${ANZ_LIMITE_DETALLE}; para verlas todas usa «Exportar a Excel».` : ""}</p>
    <div class="ox-tabla-envoltura"><table class="ox-tabla anz-tabla"><thead>${cabeza}</thead><tbody>${filas}</tbody></table></div>
    ${lista.length > visibles.length ? `<button type="button" class="boton secundario boton-chico anz-mas" data-anz-est-mas>Mostrar ${Math.min(100, lista.length - visibles.length)} más (quedan ${lista.length - visibles.length})</button>` : ""}`;
}

// --- Docentes: indicadores + semáforo + puntos de atención (evaluacion_docente.py) ---
// Decisión del colegio (24/09/2026): se califica a cada docente con
// indicadores en semáforo y puntos de atención con su evidencia; SIN nota
// única ni ranking. Solo quien tiene docentes.evaluar (coordinación y
// administración). El Desempeño Actitudinal (DESM) va en su propia pestaña.

let anzDocFicha = null; // docente_id con la ficha abierta
let anzDocChip = "todos"; // todos | rojo | amarillo | verde
let anzDocOrden = "alfabetico"; // alfabetico | atencion
let anzDocBuscar = "";
let anzDocEstado = null; // caché de la última lista (para filtrar sin volver a pedir)

const ANZ_SEMAFORO_TEXTO = { verde: "Bien", amarillo: "Revisar", rojo: "Atención", gris: "Pocos datos" };

function anzPuntoSemaforo(s) {
  const tono = { verde: "verde", amarillo: "amarillo", rojo: "rojo", gris: "gris" }[s] || "gris";
  return puntoEstado(tono, ANZ_SEMAFORO_TEXTO[s]);
}

function anzNum(v, dec = 2, signo = false) {
  if (v === null || v === undefined) return "—";
  const t = Number(v).toFixed(dec);
  return signo && v > 0 ? `+${t}` : t;
}

// Dentro de "Docentes y materias" → "Evaluación por docente" (anzDocentesHtml).
async function anzEvaluacionListaHtml() {
  if (!tienePermiso("docentes.evaluar")) {
    return `<div class="dk-info-caja">${icono("lock")} La evaluación por docente solo la ven coordinación y administración.</div>`;
  }
  anzDocEstado = await api(`/api/boletines/comparacion/docentes?${paramsComparacion()}`);
  return listaDocentesHtml();
}

function anzFiltrarDocentes(lista) {
  const f = normalizarTexto(anzDocBuscar.trim());
  let r = lista.filter((d) => {
    if (f && !normalizarTexto(`${d.docente_nombre} ${d.areas.join(" ")} ${d.grupos.join(" ")}`).includes(f)) return false;
    if (anzDocChip === "rojo") return d.rojos > 0;
    if (anzDocChip === "amarillo") return !d.rojos && d.amarillos > 0;
    if (anzDocChip === "verde") return !d.rojos && !d.amarillos;
    return true;
  });
  if (anzDocOrden === "atencion") r = [...r].sort((a, b) => b.rojos - a.rojos || b.amarillos - a.amarillos || b.puntos_atencion - a.puntos_atencion);
  return r;
}

function filasDocentesHtml() {
  const lista = anzFiltrarDocentes(anzDocEstado.docentes);
  if (!lista.length) return '<tr><td colspan="8"><p class="ox-vacio-chico">Ningún docente coincide con el filtro.</p></td></tr>';
  return lista
    .map(
      (d) => `
      <tr class="dk-fila-clicable" data-anz-doc="${d.docente_id}" tabindex="0">
        <td><span class="ox-est-celda">${orAvatar(d.docente_nombre, null)}<span class="ox-picker-texto"><strong>${esc(d.docente_nombre)}</strong>
          <span>${esc(d.areas.slice(0, 3).join(", "))}${d.areas.length > 3 ? ` y ${d.areas.length - 3} más` : ""} · ${d.grupos.length} grupo${d.grupos.length === 1 ? "" : "s"}</span></span></span></td>
        ${d.indicadores
          .map((i) => `<td class="anz-ind-celda" title="${esc(i.explicacion)}">${anzPuntoSemaforo(i.semaforo)}<span>${esc(i.texto)}</span></td>`)
          .join("")}
        <td class="prom-num">${d.puntos_atencion ? `<span class="anz-atencion">${d.puntos_atencion}</span>` : '<span class="prom-tenue">0</span>'}</td>
        <td class="dk-col-flecha">${icono("chevron-right", "ico-tenue")}</td>
      </tr>`
    )
    .join("");
}

function listaDocentesHtml() {
  const e = anzDocEstado;
  const pc = e.periodo_comparado, pb = e.periodo_base;
  return `
    <section class="anz-estado">
      <header><h3>${icono("activity")}¿Cómo estamos? <span class="prom-tenue">Período ${pb.periodo} → Período ${pc.periodo} (${pc.anio_lectivo})</span></h3></header>
      <p class="anz-informe">${esc(e.informe_texto)}</p>
      <div class="ox-kpis">
        ${orKpi(e.docentes_analizados, "Docentes analizados")}
        ${orKpi(e.con_rojo, "Con algún indicador en rojo", e.con_rojo ? "rojo" : "")}
        ${orKpi(e.con_amarillo, "Solo en amarillo", e.con_amarillo ? "ambar" : "")}
        ${orKpi(e.sin_alertas, "Sin alertas")}
        ${orKpi(`${anzNum(e.promedio_academico)}<small> ${e.variacion != null ? anzNum(e.variacion, 2, true) : ""}</small>`, "Promedio académico")}
        ${orKpi(`${Math.round(e.pct_bajo)}%`, "Notas en desempeño bajo", e.pct_bajo > 15 ? "ambar" : "")}
        ${orKpi(e.pendientes_total, "Pendientes en SAPRED", e.pendientes_total ? "ambar" : "")}
        ${orKpi(anzNum(e.promedio_actitudinal), "Desempeño actitudinal (aparte)")}
      </div>
    </section>
    <div class="anz-aviso">${icono("info")}<div><b>Cómo leer esto.</b> Las notas las pone el mismo docente que se evalúa: un promedio bajo puede ser dificultad real o una forma de calificar más exigente.
      Por eso el indicador más justo es la <b>brecha con el mismo grupo</b> (su materia frente a las otras materias de esos mismos estudiantes). Úsalo para conversar con el docente, no como sanción.
      <details><summary>Cómo se pinta cada semáforo</summary><ul>${e.umbrales.map((u) => `<li>${esc(u)}</li>`).join("")}</ul></details></div></div>
    <div class="ox-filtros">
      <div class="ox-buscador"><input type="search" data-anz-doc-buscar placeholder="Buscar docente, materia o grupo..." value="${esc(anzDocBuscar)}" aria-label="Buscar docente" /></div>
      ${orChips("anz-doc-chip", [
        ["todos", "Todos", e.docentes.length],
        ["rojo", "Con rojo", e.con_rojo],
        ["amarillo", "Solo amarillo", e.con_amarillo],
        ["verde", "Sin alertas", e.sin_alertas],
      ], anzDocChip)}
      <label class="ox-sede-sel anz-orden"><span>Orden</span><select data-anz-doc-orden>
        <option value="alfabetico" ${anzDocOrden === "alfabetico" ? "selected" : ""}>Alfabético</option>
        <option value="atencion" ${anzDocOrden === "atencion" ? "selected" : ""}>Más puntos de atención primero</option>
      </select></label>
    </div>
    <div class="ox-tabla-envoltura">
      <table class="ox-tabla anz-tabla-docentes">
        <thead><tr><th>Docente</th><th>Promedio</th><th>En bajo</th><th>Variación</th><th>Brecha grupo</th><th>Pendientes</th><th class="prom-num">Atención</th><th></th></tr></thead>
        <tbody data-anz-doc-filas>${filasDocentesHtml()}</tbody>
      </table>
    </div>`;
}

function anzEstudiantesTablaHtml(lista, conGrupo) {
  if (!lista.length) return "";
  return `<div class="tabla-scroll"><table class="prom-tabla">
    <thead><tr><th>Estudiante</th>${conGrupo ? "<th>Grupo</th>" : ""}<th class="prom-num">Antes</th><th class="prom-num">Ahora</th><th class="prom-num">Cambio</th></tr></thead>
    <tbody>${lista
      .map(
        (s) => `<tr><td><a href="#" data-anz-ver-estudiante="${s.estudiante_id}">${esc(s.nombre_completo)}</a></td>${conGrupo ? `<td>${esc(s.nombre_grupo)}</td>` : ""}
          <td class="prom-num">${anzNum(s.valor_base, 1)}</td>
          <td class="prom-num ${s.valor_comparado != null && s.valor_comparado < 3 ? "prom-nota-baja" : ""}"><b>${anzNum(s.valor_comparado, 1)}</b></td>
          <td class="prom-num ${s.delta != null && s.delta < 0 ? "anz-baja" : "anz-sube"}">${anzNum(s.delta, 2, true)}</td></tr>`
      )
      .join("")}</tbody></table></div>`;
}

function anzPuntoHtml(p) {
  const icon = p.nivel === "fortaleza" ? "trending-up" : p.nivel === "rojo" ? "circle-alert" : "triangle-alert";
  return `
    <article class="anz-punto anz-punto-${p.nivel}">
      ${icono(icon)}
      <div class="anz-punto-cuerpo">
        <strong>${esc(p.titulo)}</strong>
        <p>${esc(p.detalle)}</p>
        ${
          p.estudiantes.length
            ? `<details><summary>Ver los ${p.estudiantes.length} estudiante${p.estudiantes.length === 1 ? "" : "s"}</summary>${anzEstudiantesTablaHtml(p.estudiantes, false)}</details>`
            : ""
        }
      </div>
    </article>`;
}

function anzAsignacionesHtml(lista, conBrecha) {
  return `<div class="tabla-scroll"><table class="prom-tabla">
    <thead><tr><th>Materia</th><th>Grupo</th><th class="prom-num">Evaluados</th><th class="prom-num">Antes</th><th class="prom-num">Ahora</th><th class="prom-num">Cambio</th><th class="prom-num">En bajo</th>${
      conBrecha ? '<th class="prom-num">Otras materias</th><th class="prom-num">Brecha</th>' : ""
    }</tr></thead>
    <tbody>${lista
      .map(
        (a) => `<tr>
          <td><strong>${esc(a.area_nombre)}</strong></td><td>${esc(a.nombre_grupo)}</td>
          <td class="prom-num">${a.evaluados}</td><td class="prom-num">${anzNum(a.promedio_base)}</td>
          <td class="prom-num ${a.promedio_comparado != null && a.promedio_comparado < 3 ? "prom-nota-baja" : ""}"><b>${anzNum(a.promedio_comparado)}</b></td>
          <td class="prom-num ${a.variacion != null && a.variacion < 0 ? "anz-baja" : "anz-sube"}">${anzNum(a.variacion, 2, true)}</td>
          <td class="prom-num">${a.n_bajo} <span class="prom-tenue">(${Math.round(a.pct_bajo)}%)</span></td>
          ${
            conBrecha
              ? `<td class="prom-num">${anzNum(a.promedio_otras_materias)}</td><td class="prom-num ${a.brecha_grupo != null && a.brecha_grupo <= -0.3 ? "anz-baja" : ""}"><b>${anzNum(a.brecha_grupo, 2, true)}</b></td>`
              : ""
          }
        </tr>`
      )
      .join("")}</tbody></table></div>`;
}

async function fichaDocenteHtml(id) {
  const f = await api(`/api/boletines/comparacion/docentes/${id}?${paramsComparacion()}`);
  const TIPOS = { nota: "notas", concepto: "conceptos", observacion: "observaciones" };
  return `
    <nav class="ox-migas" aria-label="Ruta"><button type="button" data-anz-doc-volver>Docentes</button><span aria-hidden="true">/</span><span>${esc(f.docente_nombre)}</span></nav>
    <header class="ox-cabecera">
      <div class="ox-cabecera-titulo">${orAvatar(f.docente_nombre, null, true)}<div>
        <p class="dx-eyebrow">Rendimiento del docente · Período ${f.periodo_base.periodo} → ${f.periodo_comparado.periodo} (${f.periodo_comparado.anio_lectivo})</p>
        <h2>${esc(f.docente_nombre)}</h2>
        <p class="subtitulo-pagina">${esc(f.areas.join(" · "))}</p>
        <p class="prom-tenue">${f.grupos.length} grupo(s): ${esc(f.grupos.join(", "))} · ${f.evaluados} notas evaluadas</p>
      </div></div>
    </header>
    <div class="anz-indicadores">
      ${f.indicadores
        .map(
          (i) => `<div class="anz-indicador anz-sem-${i.semaforo}">
            <span class="anz-indicador-cab">${anzPuntoSemaforo(i.semaforo)}${esc(i.nombre)}</span>
            <b>${esc(i.texto)}</b>
            <span class="anz-indicador-estado">${ANZ_SEMAFORO_TEXTO[i.semaforo]}</span>
            <p>${esc(i.explicacion)}</p>
          </div>`
        )
        .join("")}
    </div>
    <section class="ox-seccion">
      <h3 class="ox-h3">${icono("circle-alert", "ico-alerta")}Puntos de atención <span class="ox-tenue">${f.puntos.length}</span></h3>
      ${f.puntos.length ? f.puntos.map(anzPuntoHtml).join("") : '<div class="ox-vacio"><p>Sin puntos de atención en este período.</p></div>'}
    </section>
    ${
      f.fortalezas_detalle.length
        ? `<section class="ox-seccion"><h3 class="ox-h3">${icono("trending-up", "ico-ok")}Fortalezas <span class="ox-tenue">${f.fortalezas_detalle.length}</span></h3>${f.fortalezas_detalle.map(anzPuntoHtml).join("")}</section>`
        : ""
    }
    <section class="ox-seccion">
      <h3 class="ox-h3">${icono("book-open")}Materias y grupos</h3>
      <p class="prom-tenue">"Otras materias" = promedio de esos mismos estudiantes en sus demás materias académicas. Brecha = esta materia menos las otras.</p>
      ${anzAsignacionesHtml(f.asignaciones, true)}
    </section>
    ${
      f.actitudinal.length
        ? `<section class="ox-seccion"><h3 class="ox-h3">${icono("heart-handshake")}Desempeño Actitudinal (DESM) que pone <span class="ox-tenue">aparte de lo académico</span></h3>${anzAsignacionesHtml(f.actitudinal, false)}</section>`
        : ""
    }
    ${
      Object.keys(f.pendientes_por_tipo).length
        ? `<section class="ox-seccion"><h3 class="ox-h3">${icono("file-warning")}Pendientes en SAPRED</h3>
            <p>${Object.entries(f.pendientes_por_tipo).map(([t, n]) => `${n} ${TIPOS[t] || t}`).join(" · ")} sin cargar (período ${f.periodo_comparado.periodo}). El detalle está en Boletines → «Por docente».</p></section>`
        : ""
    }`;
}

// --- Desempeño Actitudinal (DESM): aparte de lo académico -------------------

async function subvistaActitudinalHtml() {
  const a = await api(`/api/boletines/comparacion/actitudinal?${paramsComparacion()}`);
  if (!a.evaluados) return '<div class="ox-vacio"><p>No hay notas de Desempeño Actitudinal para este filtro.</p></div>';
  return `
    <div class="anz-aviso">${icono("info")}<div><b>Desempeño Actitudinal (DESM)</b> evalúa actitud y convivencia, no una materia académica. Por eso va aparte y no entra en los promedios académicos del colegio ni de los docentes.</div></div>
    <div class="ox-kpis">
      ${orKpi(a.evaluados, "Estudiantes evaluados")}
      ${orKpi(`${anzNum(a.promedio_comparado)}<small> ${anzNum(a.variacion, 2, true)}</small>`, `Promedio (antes ${anzNum(a.promedio_base)})`)}
      ${orKpi(a.n_bajo, `En desempeño bajo (${Math.round(a.pct_bajo)}%)`, a.n_bajo ? "rojo" : "")}
      ${orKpi(a.estudiantes_descenso.length, "Bajaron 0.5 o más", a.estudiantes_descenso.length ? "ambar" : "")}
    </div>
    ${a.estudiantes_bajo.length ? `<section class="ox-seccion"><h3 class="ox-h3">${icono("circle-alert", "ico-alerta")}Estudiantes con desempeño actitudinal bajo</h3>${anzEstudiantesTablaHtml(a.estudiantes_bajo, true)}</section>` : ""}
    <section class="ox-seccion"><h3 class="ox-h3">${icono("users")}Por grupo y quién la pone</h3>
      <div class="tabla-scroll"><table class="prom-tabla">
        <thead><tr><th>Grupo</th><th>La pone</th><th class="prom-num">Evaluados</th><th class="prom-num">Antes</th><th class="prom-num">Ahora</th><th class="prom-num">Cambio</th><th class="prom-num">En bajo</th></tr></thead>
        <tbody>${a.grupos
          .map(
            (g) => `<tr><td><strong>${esc(g.nombre_grupo)}</strong><br><span class="prom-tenue">${esc(g.sede_nombre)}</span></td>
              <td>${g.docente_nombre ? esc(g.docente_nombre) : '<span class="prom-tenue">Sin asignar</span>'}</td>
              <td class="prom-num">${g.evaluados}</td><td class="prom-num">${anzNum(g.promedio_base)}</td>
              <td class="prom-num"><b>${anzNum(g.promedio_comparado)}</b></td>
              <td class="prom-num ${g.variacion != null && g.variacion < 0 ? "anz-baja" : "anz-sube"}">${anzNum(g.variacion, 2, true)}</td>
              <td class="prom-num">${g.n_bajo}</td></tr>`
          )
          .join("")}</tbody></table></div>
    </section>
    ${
      a.estudiantes_descenso.length
        ? `<details class="seccion-colapsable"><summary>Estudiantes cuyo desempeño actitudinal bajó 0.5 o más <span class="segmentado-num">${a.estudiantes_descenso.length}</span></summary>${anzEstudiantesTablaHtml(a.estudiantes_descenso, true)}</details>`
        : ""
    }`;
}

// Interacciones de estas dos subvistas (delegadas: el contenido se repinta).
document.addEventListener("click", (ev) => {
  const fila = ev.target.closest("[data-anz-doc]");
  if (fila) {
    anzDocFicha = Number(fila.dataset.anzDoc);
    cargarSubvistaAnalisis().then(() => window.scrollTo(0, 0));
    return;
  }
  if (ev.target.closest("[data-anz-doc-volver]")) {
    anzDocFicha = null;
    cargarSubvistaAnalisis();
    return;
  }
  const chip = ev.target.closest("[data-anz-doc-chip]");
  if (chip && anzDocEstado) {
    anzDocChip = chip.dataset.anzDocChip;
    const cuerpo = document.querySelector("[data-anz-doc-cuerpo]");
    if (cuerpo) cuerpo.innerHTML = listaDocentesHtml();
  }
});
document.addEventListener("input", (ev) => {
  if (ev.target.matches("[data-anz-doc-buscar]") && anzDocEstado) {
    anzDocBuscar = ev.target.value;
    document.querySelector("[data-anz-doc-filas]").innerHTML = filasDocentesHtml();
  }
});
document.addEventListener("change", (ev) => {
  if (ev.target.matches("[data-anz-doc-orden]") && anzDocEstado) {
    anzDocOrden = ev.target.value;
    document.querySelector("[data-anz-doc-filas]").innerHTML = filasDocentesHtml();
  }
});
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && ev.target.matches?.("[data-anz-doc]")) ev.target.click();
});

// --- Evolución académica de un estudiante (modal, reusa montarModal de admin.js)

async function abrirPerfilAcademico(estudianteId) {
  const cont = montarModal("Evolución académica", '<p class="estado-carga">Cargando...</p>');
  const cuerpo = cont.querySelector(".modal-cuerpo");
  let perfil;
  try {
    perfil = await api(`/api/boletines/comparacion/estudiante/${estudianteId}?anio_lectivo=${anzAnioComparado}`);
  } catch (e) {
    cuerpo.innerHTML = `<div class="alerta-caja">${esc(e.message)}</div>`;
    return;
  }
  const cab = `<p class="anz-perfil-cab"><strong>${esc(perfil.nombre_completo)}</strong><span>${esc(perfil.documento)} · ${esc(perfil.nombre_grupo || anzNombreGrado(perfil.grado))}</span></p>`;
  if (!perfil.areas.length) {
    cuerpo.innerHTML = `${cab}<div class="ox-vacio"><p>Este estudiante no tiene notas importadas de SAPRED en ${perfil.anio_lectivo}.</p></div>`;
    return;
  }

  const periodos = [...new Set(perfil.areas.flatMap((a) => a.notas.map((n) => n.periodo)))].sort((a, b) => a - b);
  const nota = (a, p) => a.notas.find((n) => n.periodo === p)?.valor ?? null;
  const academicas = perfil.areas.filter((a) => a.area_codigo !== "DESM");
  const actitudinal = perfil.areas.filter((a) => a.area_codigo === "DESM");
  const corte = Number(anzCorte());

  // Frase: solo con las áreas que tiene en AMBOS períodos de la comparación
  // (la misma regla del resto de la pantalla).
  const mismoAnio = anzAnioBase === anzAnioComparado && perfil.anio_lectivo === anzAnioComparado;
  const pb = anzPeriodoBase, pc = anzPeriodoComparado;
  let frase = "";
  if (mismoAnio) {
    const comunes = academicas.filter((a) => nota(a, pb) !== null && nota(a, pc) !== null);
    const enBajo = academicas.filter((a) => nota(a, pc) !== null && nota(a, pc) < corte).map((a) => a.area_nombre);
    const bajaron = comunes.filter((a) => nota(a, pc) - nota(a, pb) <= -anzCfg().umbral_descenso).map((a) => a.area_nombre);
    if (comunes.length) {
      const b = comunes.reduce((s, a) => s + nota(a, pb), 0) / comunes.length;
      const c = comunes.reduce((s, a) => s + nota(a, pc), 0) / comunes.length;
      frase = `En sus ${anzPl(comunes.length, "área", "áreas")} con nota en ambos períodos, su promedio pasó de <b>${anzF(b)}</b> a <b>${anzF(c)}</b> (${anzS(c - b)}) entre el Período ${pb} y el ${pc}.`;
    } else {
      frase = `No tiene notas en el Período ${pb} y en el ${pc} a la vez, así que no se puede medir su cambio.`;
    }
    if (enBajo.length) frase += ` En el Período ${pc} está por debajo de ${anzCorte()} en: ${esc(enBajo.join(", "))}.`;
    if (bajaron.length) frase += ` Bajó ${anzCfg().umbral_descenso.toFixed(1)} o más en: ${esc(bajaron.join(", "))}.`;
  }

  const celda = (v) => `<td class="anz-num ${v !== null && v < corte ? "anz-nota-baja" : ""}">${v === null ? '<span class="prom-tenue">—</span>' : anzF(v, 1)}</td>`;
  const fila = (a, extra) => {
    const valores = periodos.map((p) => nota(a, p));
    return `<tr><td>${esc(a.area_nombre)}${extra || ""}</td>${valores.map(celda).join("")}
      <td class="anz-num ${anzClaseCambio(a.variacion_reciente)}">${a.variacion_reciente === null ? "—" : anzS(a.variacion_reciente)}</td></tr>`;
  };
  const promedioPeriodo = (p) => {
    const v = academicas.map((a) => nota(a, p)).filter((x) => x !== null);
    return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null;
  };

  cuerpo.innerHTML = `
    ${cab}
    ${frase ? `<p class="anz-interpretacion">${frase}</p>` : ""}
    <div class="ox-tabla-envoltura"><table class="ox-tabla anz-tabla">
      <thead><tr><th>Área</th>${periodos.map((p) => `<th class="anz-num">Período ${p}</th>`).join("")}<th class="anz-num">Último cambio</th></tr></thead>
      <tbody>
        ${academicas.map((a) => fila(a)).join("")}
        <tr class="anz-fila-total"><td><b>Promedio de sus áreas</b> <span class="prom-tenue">(todas las que tenga en cada período)</span></td>${periodos.map((p) => celda(promedioPeriodo(p))).join("")}<td></td></tr>
        ${actitudinal.map((a) => fila(a, ' <span class="prom-tenue">· actitudinal, va aparte</span>')).join("")}
      </tbody>
    </table></div>
    <p class="anz-nota">Notas en rojo: por debajo de ${anzCorte()}. «Último cambio» compara los dos últimos períodos con nota en esa área.</p>`;
}

// --- Interacciones (delegadas: el contenido se repinta) ----------------------

document.addEventListener("click", (ev) => {
  if (vistaActual !== "analisis") return;
  const t = ev.target;
  const x = (sel) => t.closest(sel);
  let el;

  if (t.closest("#anz-exportar")) {
    window.location.href = `/api/boletines/comparacion/exportar?${paramsComparacion()}`;
    return;
  }
  if ((el = x("[data-anz-vista]"))) return anzIrVista(el.dataset.anzVista);
  if ((el = x("[data-anz-mej-chip]"))) {
    anzMejChip = el.dataset.anzMejChip;
    anzMejLimite = 50;
    if (anzVista !== "mejorar") return anzIrVista("mejorar"); // desde Fortalezas
    return cargarSubvistaAnalisis();
  }
  if (x("[data-anz-mej-mas]")) {
    anzMejLimite += 50;
    const cuerpo = document.querySelector("[data-anz-mej-cuerpo]");
    if (cuerpo) cuerpo.innerHTML = anzMejCuerpoHtml();
    return;
  }
  if ((el = x("[data-anz-anio-chip]"))) {
    anzAnioChip = el.dataset.anzAnioChip;
    anzAnioLimite = 50;
    if (anzVista !== "anio") return anzIrVista("anio"); // desde Fortalezas
    return cargarSubvistaAnalisis();
  }
  if (x("[data-anz-anio-mas]")) {
    anzAnioLimite += 50;
    const cuerpo = document.querySelector("[data-anz-anio-cuerpo]");
    if (cuerpo) cuerpo.innerHTML = anzAnioCuerpoHtml();
    return;
  }
  if ((el = x("[data-anz-mej-area]"))) return anzAplicar({ area_id: el.dataset.anzMejArea }, "mejorar");
  if ((el = x("[data-anz-mej-grupo]"))) {
    const [sede, grado, curso] = el.dataset.anzMejGrupo.split("|");
    return anzAplicar({ sede_id: sede || anzSedeId, grado, curso }, "mejorar");
  }
  if ((el = x("[data-anz-vista-ir]"))) return anzIrVista(el.dataset.anzVistaIr);
  if (x("[data-anz-mas-filtros]")) {
    anzMasFiltros = !anzMasFiltros;
    anzPintarFiltros();
    return;
  }
  if ((el = x("[data-anz-quitar]"))) {
    const k = el.dataset.anzQuitar;
    if (k === "todos") {
      anzConfig = null;
      return anzAplicar({ sede_id: ANZ_SEDE_PRINCIPAL, grado: null, curso: null, area_id: null, docente_id: null, estado: "ACTIVO" });
    }
    if (k === "umbrales") { anzConfig = null; return anzAplicar({}); }
    const mapa = { sede: "sede_id", grado: "grado", curso: "curso", area: "area_id", docente: "docente_id" };
    if (k === "estado") return anzAplicar({ estado: "ACTIVO" });
    return anzAplicar({ [mapa[k]]: null });
  }
  if (x("[data-anz-invertir]")) {
    [anzAnioBase, anzAnioComparado] = [anzAnioComparado, anzAnioBase];
    [anzPeriodoBase, anzPeriodoComparado] = [anzPeriodoComparado, anzPeriodoBase];
    return anzAplicar({});
  }
  if ((el = x("[data-anz-cambio]"))) {
    anzEstCambio = el.dataset.anzCambio;
    anzEstModo = "estudiante";
    anzEstBuscar = "";
    anzEstLimite = 100;
    anzIrVista("estudiantes");
    document.getElementById("anz-subnav-host")?.scrollIntoView({ block: "start", behavior: "smooth" });
    return;
  }
  if ((el = x("[data-anz-filtro]"))) {
    ev.preventDefault();
    return anzAplicar({ [el.dataset.anzFiltro]: el.dataset.anzValor }, "resumen");
  }
  if ((el = x("[data-anz-grupo]"))) {
    const [sede, grado, curso] = el.dataset.anzGrupo.split("|");
    return anzAplicar({ sede_id: sede || anzSedeId, grado, curso }, "resumen");
  }
  if ((el = x("[data-anz-comparar-idx]"))) {
    anzPanorama().then((P) => {
      const i = Number(el.dataset.anzCompararIdx), pts = P.evolucion.puntos;
      anzAplicar({ base: pts[i - 1], comparado: pts[i] }, "resumen");
    });
    return;
  }
  if ((el = x("[data-anz-orden-areas]"))) { anzOrdenAreas = el.dataset.anzOrdenAreas; return cargarSubvistaAnalisis(); }
  if ((el = x("[data-anz-orden-grados]"))) { anzOrdenGrados = el.dataset.anzOrdenGrados; return cargarSubvistaAnalisis(); }
  if ((el = x("[data-anz-agrupar]"))) { anzAgrupar = el.dataset.anzAgrupar; return cargarSubvistaAnalisis(); }
  if ((el = x("[data-anz-est-chip]"))) {
    anzEstCambio = el.dataset.anzEstChip;
    anzEstLimite = 100;
    return cargarSubvistaAnalisis();
  }
  if ((el = x("[data-anz-est-modo]"))) { anzEstModo = el.dataset.anzEstModo; anzEstLimite = 100; return cargarSubvistaAnalisis(); }
  if (x("[data-anz-est-mas]")) {
    anzEstLimite += 100;
    const cuerpo = document.querySelector("[data-anz-est-cuerpo]");
    if (cuerpo) cuerpo.innerHTML = anzEstCuerpoHtml();
    return;
  }
  if ((el = x("[data-anz-doc-modo]"))) { anzDocModo = el.dataset.anzDocModo; anzDocFicha = null; anzAsigAbierta = null; return cargarSubvistaAnalisis(); }
  if ((el = x("[data-anz-asig]"))) {
    anzAsigAbierta = el.dataset.anzAsig;
    cargarSubvistaAnalisis().then(() => document.getElementById("anz-subnav-host")?.scrollIntoView({ block: "start" }));
    return;
  }
  if (x("[data-anz-asig-volver]")) { anzAsigAbierta = null; return cargarSubvistaAnalisis(); }
  if ((el = x("[data-anz-matriz-celda]"))) {
    const cuerpo = el.closest("[data-anz-matriz-cuerpo]");
    const [nb, nc] = el.dataset.anzMatrizCelda.split("|");
    const lista = (cuerpo?._lista || []).filter((e) => e.nivel_base === nb && e.nivel_comparado === nc);
    const destino = cuerpo?.querySelector("[data-anz-matriz-lista]");
    if (destino) {
      destino.innerHTML = `<p class="anz-nota"><b>${lista.length}</b> ${lista.length === 1 ? "estudiante" : "estudiantes"}: ${NOMBRES_NIVEL[nb]} → ${NOMBRES_NIVEL[nc]}. Clic en un nombre para ver su evolución.</p>
        <div class="ox-tabla-envoltura"><table class="ox-tabla anz-tabla"><thead><tr><th>Estudiante</th><th>Grupo</th><th class="anz-num">${esc(anzPB())}</th><th class="anz-num">${esc(anzPC())}</th><th class="anz-num">Cambio</th></tr></thead>
        <tbody>${lista
          .slice(0, 200)
          .map((e) => `<tr class="anz-fila-clic" data-anz-ver-estudiante="${e.estudiante_id}" tabindex="0"><td>${esc(e.nombre_completo)}</td><td>${esc(e.nombre_grupo)}</td><td class="anz-num">${anzF(e.promedio_base)}</td><td class="anz-num"><b>${anzF(e.promedio_comparado)}</b></td><td class="anz-num ${anzClaseCambio(e.delta)}">${anzS(e.delta)}</td></tr>`)
          .join("")}</tbody></table></div>${lista.length > 200 ? `<p class="anz-nota">Se muestran 200 de ${lista.length}.</p>` : ""}`;
    }
    return;
  }
  if ((el = x("[data-anz-ver-estudiante]"))) {
    ev.preventDefault();
    abrirPerfilAcademico(Number(el.dataset.anzVerEstudiante));
    return;
  }
  if (t.id === "anz-cfg-aplicar") {
    const campos = Object.keys(ANZ_DEFAULTS);
    const nuevo = {};
    for (const id of campos) {
      const v = Number(document.getElementById(`anz-cfg-${id}`)?.value);
      if (!Number.isNaN(v) && v !== ANZ_DEFAULTS[id]) nuevo[id] = v;
    }
    anzConfig = Object.keys(nuevo).length ? nuevo : null;
    return anzAplicar({});
  }
  if (t.id === "anz-cfg-restablecer") {
    anzConfig = null;
    return anzAplicar({});
  }
});

document.addEventListener("change", (ev) => {
  if (vistaActual !== "analisis") return;
  const t = ev.target;
  const periodo = (v) => {
    const [anio_lectivo, per] = v.split("|").map(Number);
    return { anio_lectivo, periodo: per };
  };
  if (t.id === "anz-periodo-base") return anzAplicar({ base: periodo(t.value) });
  if (t.id === "anz-periodo-comparado") return anzAplicar({ comparado: periodo(t.value) });
  if (t.id === "anz-sede") return anzAplicar({ sede_id: t.value });
  if (t.id === "anz-grado") return anzAplicar({ grado: t.value });
  if (t.id === "anz-area") return anzAplicar({ area_id: t.value });
  if (t.id === "anz-curso") return anzAplicar({ curso: t.value });
  if (t.id === "anz-docente") return anzAplicar({ docente_id: t.value });
  if (t.id === "anz-estado") return anzAplicar({ estado: t.value });
  if (t.matches("[data-anz-asig-sel]")) {
    const k = t.dataset.anzAsigSel;
    anzAsigFiltro[k] = t.value;
    if (k === "docente") { anzAsigFiltro.area = ""; anzAsigFiltro.grado = ""; }
    if (k === "area") anzAsigFiltro.grado = "";
    cargarSubvistaAnalisis();
  }
});

document.addEventListener("input", (ev) => {
  if (ev.target.matches?.("[data-anz-anio-buscar]")) {
    anzAnioBuscar = ev.target.value;
    anzAnioLimite = 50;
    const cuerpo = document.querySelector("[data-anz-anio-cuerpo]");
    if (cuerpo) cuerpo.innerHTML = anzAnioCuerpoHtml();
  }
  if (ev.target.matches?.("[data-anz-mej-buscar]")) {
    anzMejBuscar = ev.target.value;
    anzMejLimite = 50;
    const cuerpo = document.querySelector("[data-anz-mej-cuerpo]");
    if (cuerpo) cuerpo.innerHTML = anzMejCuerpoHtml();
  }
  if (ev.target.matches?.("[data-anz-est-buscar]")) {
    anzEstBuscar = ev.target.value;
    anzEstLimite = 100;
    const cuerpo = document.querySelector("[data-anz-est-cuerpo]");
    if (cuerpo) cuerpo.innerHTML = anzEstCuerpoHtml();
  }
});

// La tabla de transición se carga solo si alguien la abre.
document.addEventListener(
  "toggle",
  (ev) => {
    if (ev.target.matches?.("[data-anz-matriz]") && ev.target.open) anzCargarMatriz(ev.target);
  },
  true
);

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && ev.target.matches?.(".anz-fila-clic")) ev.target.click();
});
