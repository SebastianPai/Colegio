// --- Módulo Docente: centro de trabajo del profesor -------------------------
// Un solo archivo, un solo lenguaje visual (prefijo dk-). Usa api()/esc()/
// fechaColombiaISO()/instanteUtcDesdeApi() de comun.js, igual que el resto
// de la app, y abrirFicha() de core.js para reusar (sin duplicar) el visor
// oficial de la ficha de matrícula cuando el docente es director de grupo.
// Estado propio (no toca sedeSeleccionada/gradoSeleccionado de core.js: esos
// son de la vista administrativa "Estudiantes").
//
// Navegación de nivel superior (sidebar, ver index.html): Inicio / Mis cursos
// / Asistencia / Historial. Todo lo demás (estudiantes de un curso, perfil,
// asistencia de un curso concreto) es una vista de detalle a la que solo se
// llega EN CONTEXTO (desde una tarjeta o desde "clase actual"), nunca desde
// el sidebar — así cada botón del menú tiene una única razón de ser.

let dkVista = "inicio"; // inicio | cursos | asistencia-elegir | estudiantes | perfil | asistencia | historial
let dkCursoSel = null; // { sede_id, sede_nombre, grado, nombre_grado, curso, nombre_grupo, area_id, area_nombre }
let dkEstudianteSel = null;
let dkVistaAnterior = "cursos"; // a dónde vuelve el perfil
let dkAsistenciaFecha = null;
let dkBloqueDatos = null;
let dkEstados = {}; // estudiante_id -> estado elegido (antes de guardar)
let dkTocados = new Set(); // estudiante_id que el docente ya revisó (para el indicador de progreso)
let dkSucio = false; // hay marcas de asistencia sin guardar
let dkGuardando = false;
let dkGuardadoEn = null;
let dkErrorAsistencia = null;
let dkHistorialDias = 30;
let dkHistorialFiltroCurso = ""; // "" = todos

const DK_ESTADOS = [
  { valor: "presente", etiqueta: "Presente", clase: "ok" },
  { valor: "tardanza", etiqueta: "Tardanza", clase: "proceso" },
  { valor: "excusa", etiqueta: "Excusa", clase: "naranja" },
  { valor: "ausente", etiqueta: "Ausente", clase: "alerta" },
];

function dkConfirmarSalirSinGuardar() {
  if (dkVista !== "asistencia" || !dkSucio) return true;
  return confirm("Tienes cambios de asistencia sin guardar. ¿Seguro que quieres salir sin guardarlos?");
}

function dkAbrirCurso(curso, vista) {
  if (!dkConfirmarSalirSinGuardar()) return;
  dkSucio = false;
  dkCursoSel = curso;
  dkFiltroEst = "";
  dkChipEst = "todos";
  dkVista = vista || "estudiantes";
  render();
}

function dkVolver(a) {
  if (!dkConfirmarSalirSinGuardar()) return;
  dkSucio = false;
  dkVista = a;
  render();
}

// Mantiene resaltado en el sidebar el ítem de nivel superior correspondiente
// (Inicio/Mis cursos/Asistencia/Historial), incluso cuando se llega a esas
// vistas por navegación interna (dkVolver) y no por un clic directo en el
// menú. Las vistas de detalle (estudiantes/perfil/asistencia de un curso) no
// tienen ítem propio: se dejan el último resaltado, como una miga de pan.
function dkSincronizarTabActiva() {
  const conNav = { inicio: "inicio", cursos: "cursos", "asistencia-elegir": "asistencia-elegir", historial: "historial" };
  const destino = conNav[dkVista];
  if (!destino) return;
  document.querySelectorAll('.tab[data-vista="docente"]').forEach((t) => {
    t.classList.toggle("activo", t.dataset.dkVista === destino);
  });
}

async function renderDocente() {
  dkSincronizarTabActiva();
  if (dkVista === "cursos") return renderDkCursos();
  if (dkVista === "asistencia-elegir") return renderDkAsistenciaElegir();
  if (dkVista === "estudiantes") return renderDkEstudiantes();
  if (dkVista === "perfil") return renderDkPerfil();
  if (dkVista === "asistencia") return renderDkAsistencia();
  if (dkVista === "historial") return renderDkHistorial();
  return renderDkInicio();
}

// --- Inicio: centro de trabajo del día ---------------------------------------

async function renderDkInicio() {
  app.innerHTML = "<p>Cargando...</p>";
  let datos, cursos;
  try {
    datos = await api("/api/docente/inicio");
    cursos = await api("/api/docente/mis-cursos").catch(() => []);
  } catch (e) {
    app.innerHTML = `<p class="alerta-caja">${esc(
      e.status === 409 ? e.message : "No se pudo cargar tu inicio: " + e.message
    )}</p>`;
    return;
  }

  const nombre = (typeof sesionActual !== "undefined" && sesionActual?.usuario?.nombre) || "";
  const claseAhora = datos.clases.find((c) => c.es_ahora) || null;
  const direcciones = cursos.filter((c) => c.area_id == null);

  // Próxima clase: solo se calcula dentro de la jornada (en clase o en
  // descanso), donde hora_actual es un dato confiable — fuera de la jornada
  // no se sabe si "todavía no empieza" o "ya terminó", así que no se adivina.
  let proxima = null;
  if (datos.estado_jornada === "en_franja" || datos.estado_jornada === "descanso") {
    const desde = claseAhora ? claseAhora.hora : datos.hora_actual ?? -1;
    proxima = datos.clases.find((c) => c.hora > desde) || null;
  }

  const gruposUnicos = new Map();
  cursos.forEach((c) => {
    const clave = `${c.sede_id}-${c.grado}-${c.curso}`;
    if (!gruposUnicos.has(clave)) gruposUnicos.set(clave, c.total_estudiantes);
  });
  const totalEstudiantes = [...gruposUnicos.values()].reduce((a, b) => a + b, 0);
  const pendientesHoy = datos.clases.filter((c) => !c.asistencia_tomada).length;

  const mensajeJornada = {
    fin_de_semana: "Hoy es fin de semana.",
    fuera_jornada: "Ahora mismo estás fuera del horario de clases.",
    descanso: "Ahora mismo es el descanso.",
    en_franja: null,
  }[datos.estado_jornada];

  const irAClase = (c) => ({
    sede_id: c.sede_id, grado: c.grado, curso: c.curso, area_id: c.area_id,
    area_nombre: c.area_nombre, nombre_grupo: c.nombre_grupo, sede_nombre: "",
  });

  const tarjetaAhora = claseAhora
    ? `
      <div class="dk-ahora-caja">
        <span class="dk-ahora-etiqueta"><i data-lucide=bell class=ico></i> Ahora mismo</span>
        <h2>${esc(claseAhora.area_nombre)} — ${esc(claseAhora.nombre_grupo)}</h2>
        ${
          claseAhora.asistencia_tomada
            ? '<p class="dk-ahora-ok"><span class=punto-verde></span>Ya registraste la asistencia de esta clase.</p>'
            : ""
        }
        <button type="button" class="boton" id="dk-marcar-ahora">
          ${claseAhora.asistencia_tomada ? "Ver / corregir asistencia" : "Registrar asistencia"}
        </button>
      </div>`
    : mensajeJornada
    ? `<p class="exito-caja">${esc(mensajeJornada)}</p>`
    : '<p class="exito-caja">No tienes clase en tu horario en este momento.</p>';

  const tarjetaProxima = proxima
    ? `
      <div class="dk-proxima-caja">
        <span class="dk-ahora-etiqueta">Próxima clase</span>
        <strong>${proxima.hora}ª hora — ${esc(proxima.area_nombre)}</strong>
        <span>${esc(proxima.nombre_grupo)}</span>
      </div>`
    : "";

  const bannerDirector = direcciones.length
    ? `
      <div class="dk-director-banner">
        <strong><i data-lucide=user class=ico></i> Eres director de grupo</strong>
        <div class="dk-director-banner-lista">
          ${direcciones
            .map(
              (d, i) => `<button type="button" class="boton-texto-chico" data-dk-dir-inicio="${i}">${esc(
                d.nombre_grupo
              )} · ${esc(d.sede_nombre)}</button>`
            )
            .join("")}
        </div>
      </div>`
    : "";

  const filasClases = datos.clases
    .map(
      (c, i) => `
      <div class="dk-clase-fila ${c.es_ahora ? "dk-clase-ahora" : ""}" data-dk-clase="${i}">
        <div>
          <strong>${c.hora}ª hora — ${esc(c.area_nombre)}</strong>
          <span>${esc(c.nombre_grupo)}</span>
        </div>
        ${
          c.asistencia_tomada
            ? '<span class="badge-estado ok">Tomada</span>'
            : '<span class="badge-estado">Pendiente</span>'
        }
      </div>`
    )
    .join("");

  app.innerHTML = `
    <h2>Hola${nombre ? ", " + esc(nombre.split(" ")[0]) : ""}</h2>
    <p class="subtitulo-pagina" style="text-transform:capitalize">${esc(datos.dia_nombre)}, ${esc(datos.fecha)}</p>
    ${bannerDirector}
    <div class="dk-resumen-fila">
      <div class="dk-resumen-stat"><strong>${datos.clases.length}</strong><span>Cursos hoy</span></div>
      <div class="dk-resumen-stat"><strong>${pendientesHoy}</strong><span>Asistencias pendientes</span></div>
      <div class="dk-resumen-stat"><strong>${totalEstudiantes}</strong><span>Estudiantes a cargo</span></div>
    </div>
    ${tarjetaAhora}
    ${tarjetaProxima}
    ${
      datos.clases.length
        ? `<h3 class="dk-subtitulo">Tus clases de hoy</h3><div class="dk-lista-clases">${filasClases}</div>`
        : ""
    }`;

  document.getElementById("dk-marcar-ahora")?.addEventListener("click", () => {
    dkCursoSel = irAClase(claseAhora);
    dkAsistenciaFecha = null;
    dkVolver("asistencia");
  });
  document.querySelectorAll("[data-dk-clase]").forEach((el) =>
    el.addEventListener("click", () => {
      const c = datos.clases[Number(el.dataset.dkClase)];
      dkCursoSel = irAClase(c);
      dkAsistenciaFecha = null;
      dkVolver("asistencia");
    })
  );
  document.querySelectorAll("[data-dk-dir-inicio]").forEach((btn) =>
    btn.addEventListener("click", () => dkAbrirCurso(direcciones[Number(btn.dataset.dkDirInicio)], "estudiantes"))
  );
}

// --- Mis cursos ---------------------------------------------------------------

async function renderDkCursos() {
  app.innerHTML = "<p>Cargando tus cursos...</p>";
  let cursos;
  try {
    cursos = await api("/api/docente/mis-cursos");
  } catch (e) {
    app.innerHTML = `<p class="alerta-caja">${esc(
      e.status === 409
        ? e.message
        : e.status === 403
        ? "No tienes permiso para usar el módulo docente."
        : "No se pudieron cargar tus cursos: " + e.message
    )}</p>`;
    return;
  }

  if (!cursos.length) {
    app.innerHTML = `
      <h2>Mis cursos</h2>
      <p class="exito-caja">Todavía no tienes ningún grupo asignado este año lectivo. Si crees que es un error, avísale a coordinación.</p>`;
    return;
  }

  const direcciones = cursos.filter((c) => c.area_id == null);
  const materias = cursos.filter((c) => c.area_id != null);

  const tarjetaDireccion = (c, i) => `
    <div class="card-salon dk-tarjeta-director">
      <span class="badge-estado ok">Director de grupo</span>
      <h3>${esc(c.nombre_grupo)}</h3>
      <div class="grado">${esc(c.sede_nombre)}</div>
      <div class="stats"><span>${c.total_estudiantes} estudiante(s)</span></div>
      <div class="dk-card-acciones">
        <button type="button" class="boton" data-dk-ver-dir="${i}">Ver mi grupo</button>
        <button type="button" class="boton dk-boton-secundario" data-dk-asist-dir="${i}">Asistencia</button>
      </div>
    </div>`;

  const tarjetaMateria = (c, i) => `
    <div class="card-salon">
      <h3>${esc(c.area_nombre)}</h3>
      <div class="grado">${esc(c.nombre_grupo)} · ${esc(c.sede_nombre)}</div>
      <div class="stats"><span>${c.total_estudiantes} estudiante(s)</span></div>
      <div class="dk-card-acciones">
        <button type="button" class="boton" data-dk-ver="${i}">Ver estudiantes</button>
        <button type="button" class="boton dk-boton-secundario" data-dk-asist="${i}">Asistencia</button>
      </div>
    </div>`;

  app.innerHTML = `
    <h2>Mis cursos</h2>
    <p class="subtitulo-pagina">Tus cursos de este año lectivo.</p>
    ${
      direcciones.length
        ? `<h3 class="dk-subtitulo">Director de grupo</h3><div class="grid-salones">${direcciones
            .map(tarjetaDireccion)
            .join("")}</div>`
        : ""
    }
    ${
      materias.length
        ? `<h3 class="dk-subtitulo">Mis asignaturas</h3><div class="grid-salones">${materias
            .map(tarjetaMateria)
            .join("")}</div>`
        : ""
    }`;

  document.querySelectorAll("[data-dk-ver-dir]").forEach((btn) =>
    btn.addEventListener("click", () => dkAbrirCurso(direcciones[Number(btn.dataset.dkVerDir)], "estudiantes"))
  );
  document.querySelectorAll("[data-dk-asist-dir]").forEach((btn) =>
    btn.addEventListener("click", () => {
      dkAsistenciaFecha = null;
      dkAbrirCurso(direcciones[Number(btn.dataset.dkAsistDir)], "asistencia");
    })
  );
  document.querySelectorAll("[data-dk-ver]").forEach((btn) =>
    btn.addEventListener("click", () => dkAbrirCurso(materias[Number(btn.dataset.dkVer)], "estudiantes"))
  );
  document.querySelectorAll("[data-dk-asist]").forEach((btn) =>
    btn.addEventListener("click", () => {
      dkAsistenciaFecha = null;
      dkAbrirCurso(materias[Number(btn.dataset.dkAsist)], "asistencia");
    })
  );
}

// --- Asistencia: elegir clase (destino del sidebar "Asistencia") ------------

async function renderDkAsistenciaElegir() {
  app.innerHTML = "<p>Cargando...</p>";
  let datos, cursos;
  try {
    [datos, cursos] = await Promise.all([api("/api/docente/inicio"), api("/api/docente/mis-cursos")]);
  } catch (e) {
    app.innerHTML = `<p class="alerta-caja">${esc(
      e.status === 409 ? e.message : "No se pudo cargar tus clases: " + e.message
    )}</p>`;
    return;
  }

  const filasHoy = datos.clases
    .map(
      (c, i) => `
      <div class="dk-clase-fila ${c.es_ahora ? "dk-clase-ahora" : ""}" data-dk-asist-hoy="${i}">
        <div>
          <strong>${c.hora}ª hora — ${esc(c.area_nombre)}</strong>
          <span>${esc(c.nombre_grupo)}</span>
        </div>
        ${
          c.asistencia_tomada
            ? '<span class="badge-estado ok">Tomada</span>'
            : '<span class="badge-estado">Pendiente</span>'
        }
      </div>`
    )
    .join("");

  const clavesHoy = new Set(
    datos.clases.map((c) => `${c.sede_id}-${c.grado}-${c.curso}-${c.area_id ?? "gen"}`)
  );
  const otros = cursos.filter(
    (c) => !clavesHoy.has(`${c.sede_id}-${c.grado}-${c.curso}-${c.area_id ?? "gen"}`)
  );
  const tarjetaOtro = (c, i) => `
    <div class="card-salon">
      <h3>${esc(c.area_nombre)}</h3>
      <div class="grado">${esc(c.nombre_grupo)} · ${esc(c.sede_nombre)}</div>
      <div class="dk-card-acciones">
        <button type="button" class="boton dk-boton-secundario" data-dk-asist-otro="${i}">Registrar asistencia</button>
      </div>
    </div>`;

  app.innerHTML = `
    <h2>Asistencia</h2>
    <p class="subtitulo-pagina">Elige la clase a la que vas a registrar o revisar asistencia.</p>
    ${
      datos.clases.length
        ? `<h3 class="dk-subtitulo">Clases de hoy</h3><div class="dk-lista-clases">${filasHoy}</div>`
        : '<p class="exito-caja">No tienes clases programadas hoy según el horario.</p>'
    }
    ${
      otros.length
        ? `<h3 class="dk-subtitulo">Otros cursos</h3><div class="grid-salones">${otros
            .map(tarjetaOtro)
            .join("")}</div>`
        : ""
    }`;

  document.querySelectorAll("[data-dk-asist-hoy]").forEach((el) =>
    el.addEventListener("click", () => {
      const c = datos.clases[Number(el.dataset.dkAsistHoy)];
      dkCursoSel = {
        sede_id: c.sede_id, grado: c.grado, curso: c.curso, area_id: c.area_id,
        area_nombre: c.area_nombre, nombre_grupo: c.nombre_grupo, sede_nombre: "",
      };
      dkAsistenciaFecha = null;
      dkVolver("asistencia");
    })
  );
  document.querySelectorAll("[data-dk-asist-otro]").forEach((btn) =>
    btn.addEventListener("click", () => {
      dkAsistenciaFecha = null;
      dkAbrirCurso(otros[Number(btn.dataset.dkAsistOtro)], "asistencia");
    })
  );
}

function dkBotonVolverHtml(a, texto) {
  return `<button type="button" class="boton-texto-chico dk-volver" data-dk-volver="${a}">← ${esc(texto || "Volver")}</button>`;
}

function dkEncabezado(curso) {
  return `
    <div class="dk-encabezado">
      ${dkBotonVolverHtml("cursos", "Mis cursos")}
      <h2>${esc(curso.area_nombre)} — ${esc(curso.nombre_grupo)}</h2>
      <p class="subtitulo-pagina">${esc(curso.sede_nombre)}</p>
    </div>`;
}

function dkVincularVolver() {
  document.querySelectorAll("[data-dk-volver]").forEach((btn) =>
    btn.addEventListener("click", () => dkVolver(btn.dataset.dkVolver))
  );
}

// --- Mis estudiantes: lista del grupo con cómo va cada uno -------------------
// GET /api/docente/grupo/seguimiento: el profesor de área ve sus notas en SU
// materia y las faltas en sus clases; el director de grupo ve además qué
// materias va perdiendo cada estudiante y con quién (y puede abrir su perfil).

let dkFiltroEst = "";
let dkChipEst = "todos"; // todos | perdiendo | riesgo | faltas
let dkSeguimiento = null;

function dkEstadoNotaHtml(estado) {
  if (estado === "perdida") return '<span class="badge-estado alerta">Perdiendo</span>';
  if (estado === "en_riesgo") return '<span class="badge-estado proceso">En riesgo</span>';
  if (estado === "aprobada") return '<span class="badge-estado ok">Va bien</span>';
  return '<span class="prom-tenue">Sin notas</span>';
}

function dkFaltasHtml(a) {
  if (!a.ausencias && !a.tardanzas && !a.excusas) return '<span class="prom-tenue">—</span>';
  return [
    a.ausencias ? `<span class="dk-falta dk-falta-ausente" title="Ausencias en los últimos ${a.dias} días">${a.ausencias} ${a.ausencias === 1 ? "falta" : "faltas"}</span>` : "",
    a.tardanzas ? `<span class="dk-falta" title="Tardanzas">${a.tardanzas} tard.</span>` : "",
    a.excusas ? `<span class="dk-falta" title="Excusas">${a.excusas} exc.</span>` : "",
  ].join("");
}

// ¿Cómo va? Unifica profesor de área (su materia) y director (todas).
function dkComoVa(e, s) {
  if (s.es_director && !s.area_id) {
    if (e.materias_perdidas && e.materias_perdidas.length) return "perdiendo";
    if (e.materias_en_riesgo) return "riesgo";
    return "bien";
  }
  return e.estado_area === "perdida" ? "perdiendo" : e.estado_area === "en_riesgo" ? "riesgo" : e.estado_area ? "bien" : "sin";
}

function dkFiltrarEstudiantes(s) {
  const f = normalizarTexto(dkFiltroEst.trim());
  return s.estudiantes.filter((e) => {
    if (f && !normalizarTexto(`${e.nombre_completo} ${e.documento}`).includes(f)) return false;
    const va = dkComoVa(e, s);
    if (dkChipEst === "perdiendo") return va === "perdiendo";
    if (dkChipEst === "riesgo") return va === "riesgo";
    if (dkChipEst === "faltas") return e.asistencia.ausencias > 0;
    return true;
  });
}

function dkFilasEstudiantesHtml(s) {
  const lista = dkFiltrarEstudiantes(s);
  const modoDirector = s.es_director && !s.area_id;
  if (!lista.length) return `<tr><td colspan="9"><p class="ox-vacio-chico">Nadie coincide con el filtro.</p></td></tr>`;
  return lista
    .map((e, i) => {
      const idx = s.estudiantes.indexOf(e);
      const nombre = `
        <span class="ox-est-celda">${orAvatar(e.nombre_completo, e.genero)}
          <span class="ox-picker-texto"><strong>${esc(e.nombre_completo)}</strong><span>${esc(e.documento)}</span></span></span>`;
      if (modoDirector) {
        const perdidas = (e.materias_perdidas || [])
          .map(
            (m) => `<span class="dk-materia" title="${esc(m.docente_nombre ? "Docente: " + m.docente_nombre : "Sin docente asignado")}">
              <b>${esc(m.area_nombre)}</b> ${m.promedio.toFixed(1)}${m.docente_nombre ? `<small>${icono("user")}${esc(m.docente_nombre)}</small>` : ""}</span>`
          )
          .join("");
        return `
          <tr data-dk-estudiante="${idx}" class="dk-fila-clicable" tabindex="0">
            <td class="dk-num">${i + 1}</td>
            <td>${nombre}</td>
            <td class="dk-col-materias">${perdidas || (e.materias_en_riesgo ? "" : '<span class="dk-bien">' + icono("circle-check") + "Ninguna perdida</span>")}${
              e.materias_en_riesgo ? `<span class="dk-riesgo-mas">${icono("triangle-alert")}${e.materias_en_riesgo} en riesgo</span>` : ""
            }</td>
            <td>${dkFaltasHtml(e.asistencia)}</td>
            <td class="dk-col-flecha">${icono("chevron-right", "ico-tenue")}</td>
          </tr>`;
      }
      return `
        <tr${s.es_director ? ` data-dk-estudiante="${idx}" class="dk-fila-clicable" tabindex="0"` : ""}>
          <td class="dk-num">${i + 1}</td>
          <td>${nombre}</td>
          ${s.periodos
            .map((p) => {
              const n = e.notas_area.find((x) => x.periodo === p);
              return `<td class="prom-num${n && n.valor < s.nota_minima ? " prom-nota-baja" : ""}">${n ? n.valor.toFixed(1) : "—"}</td>`;
            })
            .join("")}
          <td class="prom-num"><strong>${e.promedio_area != null ? e.promedio_area.toFixed(2) : "—"}</strong></td>
          <td>${dkEstadoNotaHtml(e.estado_area)}</td>
          <td>${dkFaltasHtml(e.asistencia)}</td>
          ${s.es_director ? `<td class="dk-col-flecha">${icono("chevron-right", "ico-tenue")}</td>` : ""}
        </tr>`;
    })
    .join("");
}

async function renderDkEstudiantes() {
  if (!dkCursoSel) return dkVolver("cursos");
  app.innerHTML = dkEncabezado(dkCursoSel) + orCargandoHtml("Cargando estudiantes...");

  const q =
    `sede_id=${dkCursoSel.sede_id}&grado=${dkCursoSel.grado}` +
    (dkCursoSel.curso != null ? `&curso=${dkCursoSel.curso}` : "") +
    (dkCursoSel.area_id != null ? `&area_id=${dkCursoSel.area_id}` : "");
  try {
    dkSeguimiento = await api(`/api/docente/grupo/seguimiento?${q}`);
  } catch (e) {
    app.innerHTML = dkEncabezado(dkCursoSel) + `<p class="alerta-caja">${esc(e.message)}</p>`;
    dkVincularVolver();
    return;
  }
  dkPintarEstudiantes();
}

function dkPintarEstudiantes() {
  const s = dkSeguimiento;
  const modoDirector = s.es_director && !s.area_id;
  const cuenta = (va) => s.estudiantes.filter((e) => dkComoVa(e, s) === va).length;
  const conFaltas = s.estudiantes.filter((e) => e.asistencia.ausencias > 0).length;
  const materia = s.area_nombre || "alguna materia";
  const sinNotas = !s.periodos.length;

  const cabecera = modoDirector
    ? "<tr><th>#</th><th>Estudiante</th><th>Materias que va perdiendo (y con quién)</th><th>Faltas 30 días</th><th></th></tr>"
    : `<tr><th>#</th><th>Estudiante</th>${s.periodos.map((p) => `<th class="prom-num">P${p}</th>`).join("")}<th class="prom-num">Promedio</th><th>Cómo va</th><th>Faltas 30 días</th>${s.es_director ? "<th></th>" : ""}</tr>`;

  app.innerHTML = `
    ${dkEncabezado(dkCursoSel)}
    <div class="ox-kpis">
      ${orKpi(s.estudiantes.length, "Estudiantes")}
      ${orKpi(cuenta("perdiendo"), modoDirector ? "Pierden alguna materia" : `Perdiendo ${materia}`, cuenta("perdiendo") ? "rojo" : "")}
      ${orKpi(cuenta("riesgo"), "En riesgo", cuenta("riesgo") ? "ambar" : "")}
      ${orKpi(conFaltas, "Con faltas (30 días)")}
    </div>
    <div class="ox-filtros">
      <div class="ox-buscador"><input type="search" data-dk-buscar placeholder="Buscar por nombre o documento..." value="${esc(dkFiltroEst)}" aria-label="Buscar estudiante" /></div>
      ${orChips("dk-chip", [
        ["todos", "Todos", s.estudiantes.length],
        ["perdiendo", "Perdiendo", cuenta("perdiendo")],
        ["riesgo", "En riesgo", cuenta("riesgo")],
        ["faltas", "Con faltas", conFaltas],
      ], dkChipEst)}
      <span class="ox-espaciador"></span>
      <button type="button" class="boton" data-dk-asist-desde-lista>${icono("list-checks")}Registrar asistencia</button>
    </div>
    ${sinNotas ? `<p class="dk-info-caja">${icono("info")} Todavía no hay notas de ${s.anio_lectivo} importadas de SAPRED para este grupo: por ahora solo se ven las faltas.</p>` : ""}
    ${
      !s.es_director
        ? `<p class="dk-info-caja">${icono("info")} Ves las notas y faltas de tu materia. El detalle completo de cada estudiante lo ve el director de grupo.</p>`
        : modoDirector
          ? `<p class="dk-info-caja">${icono("info")} Como director(a) de grupo ves todas las materias. Perdiendo = promedio menor a ${s.nota_minima.toFixed(1)}; en riesgo = menor a ${(s.nota_minima + 0.5).toFixed(1)}. Toca un estudiante para ver su detalle.</p>`
          : ""
    }
    <div class="ox-tabla-envoltura">
      <table class="ox-tabla dk-tabla-est">
        <thead>${cabecera}</thead>
        <tbody data-dk-filas>${dkFilasEstudiantesHtml(s)}</tbody>
      </table>
    </div>`;

  dkVincularVolver();
  const tbody = app.querySelector("[data-dk-filas]");
  const wireFilas = () =>
    tbody.querySelectorAll("[data-dk-estudiante]").forEach((el) => {
      const abrir = () => {
        dkEstudianteSel = s.estudiantes[Number(el.dataset.dkEstudiante)].id;
        dkVistaAnterior = "estudiantes";
        dkVolver("perfil");
      };
      el.addEventListener("click", abrir);
      el.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") abrir();
      });
    });
  wireFilas();
  app.querySelector("[data-dk-buscar]").addEventListener("input", (ev) => {
    dkFiltroEst = ev.target.value;
    tbody.innerHTML = dkFilasEstudiantesHtml(s);
    wireFilas();
  });
  app.querySelectorAll("[data-dk-chip]").forEach((b) =>
    b.addEventListener("click", () => {
      dkChipEst = b.dataset.dkChip;
      dkPintarEstudiantes();
    })
  );
  document.querySelector("[data-dk-asist-desde-lista]")?.addEventListener("click", () => {
    dkAsistenciaFecha = null;
    dkVolver("asistencia");
  });
}

// --- Perfil del estudiante -----------------------------------------------------

const DK_TIPOS_OBS = {
  academica: "Académica",
  convivencia: "Convivencia",
  general: "General",
  psicologia: "Remisión a psicología",
};

let dkPerfilActual = null;
let dkRendimientoActual = null; // GET /api/docente/estudiante/{id}/rendimiento (materias + faltas)
let dkMostrarFormObs = false;
let dkGuardandoObs = false;
let dkErrorObs = null;

async function renderDkPerfil() {
  if (!dkEstudianteSel) return dkVolver("cursos");
  app.innerHTML = dkBotonVolverHtml(dkVistaAnterior, dkVistaAnterior === "estudiantes" ? "Grupo" : "Mis cursos") + "<p>Cargando...</p>";

  let e;
  try {
    e = await api(`/api/docente/estudiante/${dkEstudianteSel}`);
  } catch (err) {
    app.innerHTML =
      dkBotonVolverHtml(dkVistaAnterior) + `<p class="alerta-caja">${esc(err.message || "No se pudo cargar el estudiante.")}</p>`;
    dkVincularVolver();
    return;
  }

  let observaciones = [];
  let observacionesError = null;
  try {
    observaciones = await api(`/api/docente/observaciones?estudiante_id=${dkEstudianteSel}`);
  } catch (err) {
    observacionesError = err;
  }
  try {
    dkRendimientoActual = await api(`/api/docente/estudiante/${dkEstudianteSel}/rendimiento`);
  } catch {
    dkRendimientoActual = null; // el perfil se ve igual, solo sin el rendimiento
  }

  dkPerfilActual = e;
  dkMostrarFormObs = false;
  dkErrorObs = null;
  dkPintarPerfil(e, observaciones, observacionesError);
}

// Rendimiento (misma tabla que la ficha de matrícula: rendimientoFichaHtml en
// ficha.js, con el docente de cada materia) + faltas de los últimos 30 días.
function dkRendimientoHtml(r) {
  if (!r) return "";
  const a = r.asistencia;
  const ESTADO = { ausente: "Ausente", tardanza: "Tardanza", excusa: "Excusa" };
  const faltas = r.ultimas_faltas
    .map(
      (f) => `<li><span class="dk-falta${f.estado === "ausente" ? " dk-falta-ausente" : ""}">${ESTADO[f.estado] || esc(f.estado)}</span>
        ${esc(new Date(`${f.fecha}T00:00:00`).toLocaleDateString("es-CO", { weekday: "short", day: "numeric", month: "short" }))}${f.area ? ` · ${esc(f.area)}` : ""}</li>`
    )
    .join("");
  return `
    ${rendimientoFichaHtml(r.riesgo)}
    <div class="dk-perfil-caja">
      <h3>${icono("calendar")}Asistencia — últimos ${a.dias} días</h3>
      <div class="ox-kpis dk-kpis-chicos">
        ${orKpi(a.ausencias, "Ausencias", a.ausencias >= 3 ? "rojo" : "")}
        ${orKpi(a.tardanzas, "Tardanzas")}
        ${orKpi(a.excusas, "Excusas")}
      </div>
      ${faltas ? `<ul class="dk-faltas-lista">${faltas}</ul>` : '<p class="prom-tenue">Sin faltas registradas en este tiempo.</p>'}
    </div>`;
}

function dkPintarPerfil(e, observaciones, observacionesError) {
  app.innerHTML = `
    ${dkBotonVolverHtml(dkVistaAnterior, dkVistaAnterior === "estudiantes" ? "Grupo" : "Mis cursos")}
    <h2>${esc(e.nombre_completo)}</h2>
    <p class="subtitulo-pagina">${esc(e.documento)}</p>
    <div class="dk-perfil-caja">
      <h3>Información académica</h3>
      <dl class="dk-perfil-datos">
        <dt>Grado oficial</dt><dd>${esc(e.nombre_grado)}</dd>
        <dt>Grupo oficial</dt><dd>${esc(e.nombre_grupo)}</dd>
        <dt>Sede</dt><dd>${esc(e.sede_nombre)}</dd>
        <dt>Estado</dt><dd>${e.estado === "ACTIVO" ? '<span class="badge-estado ok">Activo</span>' : esc(e.estado)}</dd>
        ${e.genero ? `<dt>Género</dt><dd>${esc(e.genero)}</dd>` : ""}
        ${e.fecha_nacimiento ? `<dt>Fecha de nacimiento</dt><dd>${esc(e.fecha_nacimiento)}</dd>` : ""}
      </dl>
    </div>
    ${dkRendimientoHtml(dkRendimientoActual)}
    <div class="dk-perfil-caja">
      <div class="dk-obs-titulo">
        <h3>Ficha de matrícula completa</h3>
        <button type="button" class="boton dk-boton-secundario" id="dk-editar-ficha">Editar ficha completa</button>
      </div>
      <p class="subtitulo-pagina">Acudiente, dirección, etnia, discapacidad y documentos — el mismo formato oficial que usa secretaría. Los documentos se ven, pero no se suben desde aquí.</p>
    </div>
    ${dkObservacionesHtml(observaciones, observacionesError)}`;
  dkVincularVolver();
  dkVincularObservaciones();
  document.getElementById("dk-editar-ficha")?.addEventListener("click", () => {
    fichaModoDocente = true;
    fichaSub = "datos";
    abrirFicha(dkEstudianteSel, "docente");
  });
}

function dkObservacionesHtml(observaciones, observacionesError) {
  if (observacionesError) {
    return observacionesError.status === 403 ? "" : `<p class="alerta-caja">No se pudieron cargar las observaciones: ${esc(observacionesError.message)}</p>`;
  }
  const filas = observaciones
    .map((o) => {
      const esPsicologia = o.tipo === "psicologia";
      const claseTipo = esPsicologia ? "alerta" : o.tipo === "convivencia" ? "proceso" : o.tipo === "academica" ? "" : "naranja";
      const cuando = instanteUtcDesdeApi(o.creado_en);
      return `
        <div class="dk-obs-item ${esPsicologia ? "dk-obs-confidencial" : ""}">
          <div class="dk-obs-cabecera">
            <span class="badge-estado ${claseTipo}">${esc(DK_TIPOS_OBS[o.tipo] || o.tipo)}</span>
            <span class="dk-obs-fecha">${esc(o.fecha)}${cuando ? " · " + esc(cuando.toLocaleDateString("es-CO")) : ""} · ${esc(o.autor_nombre)}</span>
          </div>
          ${o.titulo ? `<strong>${esc(o.titulo)}</strong>` : ""}
          <p>${esc(o.detalle)}</p>
          ${esPsicologia ? `<p class="dk-obs-aviso"><i data-lucide=lock class=ico></i> Confidencial: solo la ve orientación/psicología. Estado: ${esc(o.estado)}</p>` : ""}
        </div>`;
    })
    .join("");

  return `
    <div class="dk-perfil-caja">
      <div class="dk-obs-titulo">
        <h3>Observaciones</h3>
        ${tienePermiso("observaciones.crear") ? '<button type="button" class="boton dk-boton-secundario" id="dk-nueva-obs">+ Nueva observación</button>' : ""}
      </div>
      ${dkErrorObs ? `<p class="alerta-caja">${esc(dkErrorObs)}</p>` : ""}
      <form id="form-dk-obs" class="form-grid dk-obs-form" ${dkMostrarFormObs ? "" : "hidden"}>
        <label>Tipo
          <select name="tipo" id="dk-obs-tipo">
            <option value="academica">Académica</option>
            <option value="convivencia">Convivencia</option>
            <option value="general">General</option>
            ${typeof modulosSistema !== "undefined" && modulosSistema.orientacion === false ? "" : '<option value="psicologia">Remitir a psicología</option>'}
          </select>
        </label>
        <label class="ancho-completo">Detalle
          <textarea name="detalle" rows="3" required placeholder="Describe brevemente la situación..."></textarea>
        </label>
        <p class="dk-obs-aviso ancho-completo" id="dk-obs-aviso-confidencial" hidden>
          <i data-lucide=lock class=ico></i> Esto queda marcado como confidencial: solo orientación/psicología podrá verlo (tú seguirás viendo lo que escribiste, pero no el seguimiento que ellos hagan).
        </p>
        <div class="ancho-completo dk-obs-acciones">
          <button type="submit" class="boton" ${dkGuardandoObs ? "disabled" : ""}>${dkGuardandoObs ? "Guardando..." : "Guardar observación"}</button>
          <button type="button" class="boton-texto-chico" id="dk-cancelar-obs">Cancelar</button>
        </div>
      </form>
      ${
        observaciones.length
          ? `<div class="dk-obs-lista">${filas}</div>`
          : '<p class="subtitulo-pagina">Todavía no hay observaciones registradas.</p>'
      }
    </div>`;
}

function dkVincularObservaciones() {
  document.getElementById("dk-nueva-obs")?.addEventListener("click", () => {
    dkMostrarFormObs = true;
    document.getElementById("form-dk-obs").hidden = false;
  });
  document.getElementById("dk-cancelar-obs")?.addEventListener("click", () => {
    dkMostrarFormObs = false;
    document.getElementById("form-dk-obs").hidden = true;
  });
  document.getElementById("dk-obs-tipo")?.addEventListener("change", (ev) => {
    document.getElementById("dk-obs-aviso-confidencial").hidden = ev.target.value !== "psicologia";
  });
  document.getElementById("form-dk-obs")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (dkGuardandoObs) return;
    const datos = new FormData(ev.target);
    const detalle = String(datos.get("detalle") || "").trim();
    if (!detalle) return;
    dkGuardandoObs = true;
    dkErrorObs = null;
    try {
      await api("/api/docente/observaciones", {
        method: "POST",
        body: JSON.stringify({
          estudiante_id: dkEstudianteSel,
          tipo: datos.get("tipo"),
          detalle,
          uuid_cliente: `dkobs-${dkEstudianteSel}-${Date.now()}`,
        }),
      });
      dkGuardandoObs = false;
      renderDkPerfil();
    } catch (e) {
      dkGuardandoObs = false;
      dkErrorObs = e.message || "No se pudo guardar la observación.";
      dkPintarPerfil(dkPerfilActual, [], null);
    }
  });
}

// --- Asistencia ---------------------------------------------------------------

function dkClaveBloque(curso, fecha) {
  return (
    `sede_id=${curso.sede_id}&grado=${curso.grado}` +
    (curso.curso != null ? `&curso=${curso.curso}` : "") +
    (curso.area_id != null ? `&area_id=${curso.area_id}` : "") +
    `&fecha=${fecha}`
  );
}

async function renderDkAsistencia() {
  if (!dkCursoSel) return dkVolver("cursos");
  if (!dkAsistenciaFecha) dkAsistenciaFecha = fechaColombiaISO();
  app.innerHTML = dkEncabezado(dkCursoSel) + "<p>Cargando asistencia...</p>";

  try {
    dkBloqueDatos = await api(`/api/docente/asistencia/bloque?${dkClaveBloque(dkCursoSel, dkAsistenciaFecha)}`);
  } catch (e) {
    app.innerHTML = dkEncabezado(dkCursoSel) + `<p class="alerta-caja">${esc(e.message || "No se pudo cargar la asistencia.")}</p>`;
    dkVincularVolver();
    return;
  }

  dkEstados = {};
  dkTocados = new Set();
  dkBloqueDatos.estudiantes.forEach((e) => {
    dkEstados[e.estudiante_id] = e.estado || "presente";
    if (e.estado) dkTocados.add(e.estudiante_id);
  });
  dkGuardadoEn = null;
  dkErrorAsistencia = null;
  dkSucio = false;
  dkPintarAsistencia();
}

function dkPintarAsistencia() {
  const v = dkBloqueDatos;
  const soloLectura = !v.puede_registrar;
  const total = v.estudiantes.length;
  const revisados = dkTocados.size;
  const pct = total ? Math.round((revisados / total) * 100) : 0;

  const filas = v.estudiantes
    .map((e) => {
      const estadoActual = dkEstados[e.estudiante_id];
      const tocado = dkTocados.has(e.estudiante_id);
      const botones = DK_ESTADOS.map(
        (op) => `
        <button type="button"
          class="dk-estado-btn ${op.clase} ${estadoActual === op.valor ? "activo" : ""}"
          data-dk-est="${e.estudiante_id}" data-dk-valor="${op.valor}" ${soloLectura ? "disabled" : ""}>
          ${op.etiqueta}
        </button>`
      ).join("");
      return `
        <div class="dk-fila-asistencia ${!soloLectura && !tocado ? "dk-fila-sin-revisar" : ""}">
          <div class="dk-fila-nombre">
            <strong>${esc(e.apellidos)} ${esc(e.nombres)}</strong>
            <span>${esc(e.documento)}</span>
          </div>
          <div class="dk-fila-botones">${botones}</div>
        </div>`;
    })
    .join("");

  const fechaLegible = new Date(v.fecha + "T12:00:00").toLocaleDateString("es-CO", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });

  app.innerHTML = `
    ${dkEncabezado(dkCursoSel)}
    <div class="toolbar">
      <label>Fecha
        <input type="date" id="dk-fecha-asistencia" value="${v.fecha}" />
      </label>
      ${!soloLectura ? '<button type="button" class="boton dk-boton-secundario" id="dk-todos-presentes">Marcar todos presentes</button>' : ""}
    </div>
    <p class="subtitulo-pagina" style="text-transform:capitalize">${esc(fechaLegible)}</p>
    ${soloLectura ? `<p class="alerta-caja">${esc(v.motivo_solo_lectura || "Solo puedes consultar esta asistencia.")}</p>` : ""}
    ${
      !soloLectura
        ? `<div class="dk-progreso">
            <div class="dk-progreso-barra"><span style="width:${pct}%"></span></div>
            <span class="dk-progreso-texto">${revisados} de ${total} revisados</span>
          </div>`
        : ""
    }
    ${dkErrorAsistencia ? `<p class="alerta-caja">${esc(dkErrorAsistencia)}</p>` : ""}
    <div class="dk-lista-asistencia">${filas}</div>
    ${
      !soloLectura
        ? `<div class="dk-barra-guardar">
            <button type="button" class="boton" id="dk-guardar-asistencia" ${dkGuardando ? "disabled" : ""}>
              ${dkGuardando ? "Guardando..." : "Guardar asistencia"}
            </button>
            ${dkGuardadoEn ? `<span class="dk-guardado-ok"><span class=punto-verde></span>Guardado ${esc(dkGuardadoEn)}</span>` : ""}
          </div>`
        : ""
    }`;

  dkVincularVolver();
  document.getElementById("dk-fecha-asistencia")?.addEventListener("change", (ev) => {
    if (dkSucio && !confirm("Tienes cambios sin guardar en esta fecha. ¿Cambiar de fecha de todos modos?")) {
      ev.target.value = dkAsistenciaFecha;
      return;
    }
    dkSucio = false;
    dkAsistenciaFecha = ev.target.value;
    renderDkAsistencia();
  });
  document.getElementById("dk-todos-presentes")?.addEventListener("click", () => {
    v.estudiantes.forEach((e) => {
      dkEstados[e.estudiante_id] = "presente";
      dkTocados.add(e.estudiante_id);
    });
    dkSucio = true;
    dkPintarAsistencia();
  });
  document.querySelectorAll("[data-dk-est]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const id = Number(btn.dataset.dkEst);
      dkEstados[id] = btn.dataset.dkValor;
      dkTocados.add(id);
      dkSucio = true;
      dkPintarAsistencia();
    })
  );
  document.getElementById("dk-guardar-asistencia")?.addEventListener("click", dkGuardarAsistencia);
}

async function dkGuardarAsistencia() {
  if (dkGuardando) return;
  dkGuardando = true;
  dkErrorAsistencia = null;
  dkPintarAsistencia();

  const registros = dkBloqueDatos.estudiantes.map((e) => ({
    estudiante_id: e.estudiante_id,
    estado: dkEstados[e.estudiante_id] || "presente",
    uuid_cliente: `dk-${e.estudiante_id}-${dkCursoSel.sede_id}-${dkCursoSel.area_id ?? "gen"}-${dkBloqueDatos.fecha}`,
  }));

  try {
    await api("/api/docente/asistencia", {
      method: "POST",
      body: JSON.stringify({
        sede_id: dkCursoSel.sede_id, grado: dkCursoSel.grado, curso: dkCursoSel.curso,
        area_id: dkCursoSel.area_id, bloque_horario_id: dkBloqueDatos.bloque_horario_id,
        fecha: dkBloqueDatos.fecha, registros,
      }),
    });
    dkGuardando = false;
    dkSucio = false;
    dkGuardadoEn = new Date().toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" });
    dkPintarAsistencia();
  } catch (e) {
    dkGuardando = false;
    dkErrorAsistencia = e.message || "No se pudo guardar la asistencia.";
    dkPintarAsistencia();
  }
}

// --- Historial -----------------------------------------------------------------

let dkHistorialItems = [];

async function renderDkHistorial() {
  app.innerHTML = dkBotonVolverHtml("inicio", "Inicio") + "<p>Cargando historial...</p>";
  try {
    dkHistorialItems = await api(`/api/docente/historial?dias=${dkHistorialDias}`);
  } catch (e) {
    app.innerHTML = dkBotonVolverHtml("inicio", "Inicio") + `<p class="alerta-caja">${esc(e.message)}</p>`;
    dkVincularVolver();
    return;
  }
  dkPintarHistorial();
}

function dkPintarHistorial() {
  const items = dkHistorialItems;
  const claveCurso = (h) => `${h.nombre_grupo}|${h.area_nombre}`;
  const cursosUnicos = [...new Map(items.map((h) => [claveCurso(h), h])).values()];
  const filtrados = dkHistorialFiltroCurso ? items.filter((h) => claveCurso(h) === dkHistorialFiltroCurso) : items;

  const filas = filtrados
    .map(
      (h, i) => `
      <div class="dk-historial-fila">
        <div class="dk-historial-fecha">
          <strong>${esc(h.fecha)}</strong>
          <span>${esc(h.area_nombre)} — ${esc(h.nombre_grupo)}</span>
        </div>
        <div class="dk-historial-conteos">
          <span class="badge-estado ok">${h.presentes} presente(s)</span>
          ${h.tardanzas ? `<span class="badge-estado proceso">${h.tardanzas} tardanza(s)</span>` : ""}
          ${h.excusas ? `<span class="badge-estado naranja">${h.excusas} excusa(s)</span>` : ""}
          ${h.ausentes ? `<span class="badge-estado alerta">${h.ausentes} ausente(s)</span>` : ""}
        </div>
        <button type="button" class="boton-texto-chico" data-dk-hist-detalle="${i}">Ver detalle</button>
      </div>`
    )
    .join("");

  app.innerHTML = `
    ${dkBotonVolverHtml("inicio", "Inicio")}
    <h2>Historial de asistencia</h2>
    <p class="subtitulo-pagina">Lo que has registrado, con acceso directo al detalle de cualquier día.</p>
    <div class="toolbar dk-historial-filtros">
      <label>Período
        <select id="dk-historial-dias">
          <option value="7" ${dkHistorialDias === 7 ? "selected" : ""}>Últimos 7 días</option>
          <option value="30" ${dkHistorialDias === 30 ? "selected" : ""}>Últimos 30 días</option>
          <option value="90" ${dkHistorialDias === 90 ? "selected" : ""}>Últimos 90 días</option>
        </select>
      </label>
      ${
        cursosUnicos.length > 1
          ? `<label>Curso
              <select id="dk-historial-curso">
                <option value="">Todos</option>
                ${cursosUnicos
                  .map(
                    (h) =>
                      `<option value="${esc(claveCurso(h))}" ${dkHistorialFiltroCurso === claveCurso(h) ? "selected" : ""}>${esc(
                        h.area_nombre
                      )} — ${esc(h.nombre_grupo)}</option>`
                  )
                  .join("")}
              </select>
            </label>`
          : ""
      }
    </div>
    ${filtrados.length ? `<div class="dk-historial-lista">${filas}</div>` : '<p class="exito-caja">No hay asistencia registrada en este período.</p>'}`;

  dkVincularVolver();
  document.getElementById("dk-historial-dias")?.addEventListener("change", (ev) => {
    dkHistorialDias = Number(ev.target.value);
    renderDkHistorial();
  });
  document.getElementById("dk-historial-curso")?.addEventListener("change", (ev) => {
    dkHistorialFiltroCurso = ev.target.value;
    dkPintarHistorial();
  });
  document.querySelectorAll("[data-dk-hist-detalle]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const h = filtrados[Number(btn.dataset.dkHistDetalle)];
      dkCursoSel = {
        sede_id: h.sede_id, sede_nombre: "", grado: h.grado, curso: h.curso,
        nombre_grupo: h.nombre_grupo, area_id: h.area_id, area_nombre: h.area_nombre,
      };
      dkAsistenciaFecha = h.fecha;
      dkVolver("asistencia");
    })
  );
}
