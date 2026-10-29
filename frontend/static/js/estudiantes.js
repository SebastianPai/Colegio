// --- Vista: Estudiantes (lista + impresión contextual + hoja oficial) --

let mesSeleccionado = new Date().getMonth();
let paginaActual = 1;
let porPagina = 50;
let soloNoVerificados = false;
let sinCurso = false; // estudiantes con grado pero sin sección/curso asignado (típico de sedes rurales)
let soloPendientesSimat = false; // matriculados aquí, aún sin registrar en SIMAT
let mostrarImprimir = false;
let busquedaActual = "";
let estadoSeleccionado = "";
let temporizadorBusqueda;

// Las sedes casi no cambian en una sesión y se piden en cada render de la
// lista: se cachean para que buscar/paginar no vuelva a traerlas.
let sedesCache = null;
async function obtenerSedes() {
  if (!sedesCache) sedesCache = await api("/api/sedes");
  return sedesCache;
}

// Parámetros de /api/estudiantes/pagina con los filtros actuales.
function construirParamsEstudiantes() {
  const params = new URLSearchParams();
  if (sedeSeleccionada) params.set("sede_id", sedeSeleccionada);
  if (gradoSeleccionado !== null) params.set("grado", gradoSeleccionado);
  if (divisionSeleccionada !== null) params.set("curso", divisionSeleccionada);
  if (soloNoVerificados) params.set("solo_no_verificados", "true");
  if (sinCurso) params.set("sin_curso", "true");
  if (soloPendientesSimat) params.set("pendiente_simat", "true");
  if (busquedaActual) params.set("q", busquedaActual);
  if (estadoSeleccionado) params.set("estado", estadoSeleccionado);
  params.set("pagina", paginaActual);
  params.set("por_pagina", porPagina);
  return params;
}

const MESES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

const TAMANOS_PAGINA = [25, 50, 100, 200];

// Cuenta estudiantes con los filtros estructurales actuales (sede/grado/
// división/búsqueda) más los que se le agreguen, sin traer los registros:
// por_pagina=1 hace que el backend solo calcule el total. Así el resumen
// siempre refleja los mismos filtros que ve el usuario, sin inventar cifras.
async function contarEstudiantes(paramsExtra) {
  const params = new URLSearchParams();
  if (sedeSeleccionada) params.set("sede_id", sedeSeleccionada);
  if (gradoSeleccionado !== null) params.set("grado", gradoSeleccionado);
  if (divisionSeleccionada !== null) params.set("curso", divisionSeleccionada);
  if (busquedaActual) params.set("q", busquedaActual);
  params.set("pagina", 1);
  params.set("por_pagina", 1);
  Object.entries(paramsExtra || {}).forEach(([k, v]) => params.set(k, v));
  const resultado = await api(`/api/estudiantes/pagina?${params}`);
  return resultado.total;
}

// --- Estado de la pantalla (solo de esta vista) -----------------------------
// Los filtros en sí (sedeSeleccionada, gradoSeleccionado, busquedaActual…)
// siguen siendo las variables globales de siempre: main.js, sedes.js, la
// impresión y "Volver" desde el detalle dependen de ellas.

let estGradosSedeId; // sede cuyos grados/divisiones están en estGradosData
let estGradosData = [];
let estMasFiltrosAbierto = false;
let estRefrescoToken = 0; // descarta respuestas viejas si llega una más nueva
let estScrollGuardado = null; // para volver al mismo punto tras abrir un estudiante

const nombreDeGrado = (g) => (NOMBRES_GRADOS.find(([n]) => n === g) || [g, String(g)])[1];

// Sede en su forma corta: "SEDE # 17  ALTO GUELMAMBI" -> "#17 ALTO GUELMAMBI".
// partesNombreSede() vive en sedes.js (se carga antes que este archivo).
function sedeCorta(sede) {
  if (!sede) return "—";
  const { numero, nombre } = partesNombreSede(sede.nombre);
  return numero ? `#${numero} ${nombre}` : nombre;
}

const hayFiltrosEstudiantes = () =>
  Boolean(
    sedeSeleccionada ||
      gradoSeleccionado !== null ||
      divisionSeleccionada !== null ||
      estadoSeleccionado ||
      soloNoVerificados ||
      sinCurso ||
      soloPendientesSimat ||
      busquedaActual
  );

async function renderEstudiantes() {
  estGradosSedeId = undefined; // al entrar a la pantalla se vuelven a pedir
  app.innerHTML = `
    <div class="pagina-header no-imprimir">
      <div>
        <h1>Estudiantes</h1>
        <p class="subtitulo-pagina">Gestión y consulta de estudiantes matriculados.</p>
      </div>
      ${
        tienePermiso("estudiantes.crear")
          ? '<button type="button" class="boton" id="btn-nuevo-estudiante">+ Nuevo estudiante</button>'
          : ""
      }
    </div>

    <div class="buscador-principal con-limpiar no-imprimir">
      <span class="buscador-principal-icono" aria-hidden="true"><i data-lucide=search class=ico></i> </span>
      <input type="text" id="buscar" placeholder="Nombre, documento o grupo (ej. 5-1, o 5-1 garcia)" value="${esc(busquedaActual)}" aria-label="Buscar estudiante por nombre, documento o grupo" autocomplete="off" />
      <button type="button" class="buscador-limpiar" id="buscar-limpiar" aria-label="Borrar búsqueda" ${busquedaActual ? "" : "hidden"}></button>
    </div>

    <div id="est-filtros" class="no-imprimir"></div>
    <div id="est-resumen" class="no-imprimir"></div>
    <div id="est-resultados" class="panel-tabla-header no-imprimir"></div>
    <div id="zona-impresion"></div>
    <div id="lista-estudiantes" aria-live="polite"><div class="estado-carga">Cargando estudiantes...</div></div>
  `;

  document.getElementById("btn-nuevo-estudiante")?.addEventListener("click", () => {
    document.querySelector('[data-vista="agregar"]')?.click();
  });

  const buscador = document.getElementById("buscar");
  const limpiar = document.getElementById("buscar-limpiar");
  buscador.addEventListener("input", (e) => {
    clearTimeout(temporizadorBusqueda);
    const valor = e.target.value;
    limpiar.hidden = !valor;
    temporizadorBusqueda = setTimeout(() => {
      busquedaActual = valor;
      paginaActual = 1;
      refrescarEstudiantes(); // solo repinta las zonas de datos, no toda la pantalla
    }, 250);
  });
  buscador.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && buscador.value) limpiar.click();
  });
  limpiar.addEventListener("click", () => {
    clearTimeout(temporizadorBusqueda);
    buscador.value = "";
    limpiar.hidden = true;
    busquedaActual = "";
    paginaActual = 1;
    buscador.focus();
    refrescarEstudiantes();
  });

  await refrescarEstudiantes();

  // Al volver desde el detalle de un estudiante se regresa al mismo punto de
  // la lista. core.js sube al inicio después de renderizar, así que se
  // restaura en el siguiente cuadro.
  if (estScrollGuardado !== null) {
    const y = estScrollGuardado;
    estScrollGuardado = null;
    requestAnimationFrame(() => window.scrollTo(0, y));
  }
}

// Trae la lista y las cifras con los filtros actuales y repinta las zonas de
// datos (filtros, resumen, resultados y lista). No toca el encabezado ni el
// buscador, así que no hay parpadeo ni se pierde el foco al filtrar.
async function refrescarEstudiantes({ desplazar = false } = {}) {
  const zonaLista = document.getElementById("lista-estudiantes");
  if (!zonaLista) return;
  const miToken = ++estRefrescoToken;
  zonaLista.classList.add("cargando");
  zonaLista.setAttribute("aria-busy", "true");

  try {
    const sedes = await obtenerSedes();
    if (!sedeSeleccionada) {
      estGradosData = [];
      estGradosSedeId = null;
    } else if (estGradosSedeId !== sedeSeleccionada) {
      estGradosData = await api(`/api/sedes/${sedeSeleccionada}/grados`);
      estGradosSedeId = sedeSeleccionada;
    }
    if (miToken !== estRefrescoToken) return;

    // "Estudiantes" cuenta lo mismo que la lista salvo por Estado / no
    // verificados / sin sección: si esos no están activos son el mismo número
    // y se ahorra una petición.
    const hayExtras = Boolean(estadoSeleccionado || soloNoVerificados || sinCurso || soloPendientesSimat);
    const [resultado, totalContextoExtra, totalActivos, totalPendientes, totalSinCurso] = await Promise.all([
      api(`/api/estudiantes/pagina?${construirParamsEstudiantes()}`),
      hayExtras ? contarEstudiantes({}) : Promise.resolve(null),
      contarEstudiantes({ estado: "ACTIVO" }),
      contarEstudiantes({ solo_no_verificados: "true" }),
      contarEstudiantes({ sin_curso: "true" }),
    ]);
    if (miToken !== estRefrescoToken) return; // llegó una respuesta más nueva
    const totalContexto = totalContextoExtra ?? resultado.total;

    pintarFiltrosEstudiantes(sedes);
    document.getElementById("est-resumen").innerHTML = resumenEstudiantesHtml({
      total: totalContexto, activos: totalActivos, pendientes: totalPendientes, sinCurso: totalSinCurso,
    });
    const puedeImprimir = Boolean(sedeSeleccionada && gradoSeleccionado !== null);
    document.getElementById("est-resultados").innerHTML = resultadosHeaderHtml(resultado.total, puedeImprimir);
    zonaLista.innerHTML = listaEstudiantesHtml(resultado);

    vincularResumenEstudiantes();
    vincularExportarEstudiantes(sedes);
    vincularListaEstudiantes();

    // Hoja de impresión: solo cuando hay sede y grado (igual que antes).
    if (mostrarImprimir && puedeImprimir) await renderZonaImpresion(sedes, estGradosData);
    else document.getElementById("zona-impresion").innerHTML = "";

    if (desplazar) document.getElementById("est-resultados")?.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    if (miToken !== estRefrescoToken) return;
    zonaLista.innerHTML = `<div class="alerta-caja">${
      e.status === 401 || e.status === 403
        ? "No tienes permiso para ver los estudiantes."
        : "No se pudo cargar la lista de estudiantes: " + esc(e.message)
    } <button type="button" class="boton-texto" id="btn-reintentar-lista">Reintentar</button></div>`;
    document.getElementById("btn-reintentar-lista")?.addEventListener("click", () => refrescarEstudiantes());
  } finally {
    if (miToken === estRefrescoToken) {
      zonaLista.classList.remove("cargando");
      zonaLista.removeAttribute("aria-busy");
    }
  }
}

// --- Filtros ------------------------------------------------------------------

// El select de sede agrupa con datos reales de la tabla (no con nombres
// quemados): las que pertenecen a IETABA (Sede.pertenece_ietaba) primero, y
// las demás por su institución. Agrupar además desambigua los números de sede,
// que se repiten entre instituciones (hay dos "SEDE # 11").
function opcionesSedeHtml(sedes) {
  const grupos = new Map();
  for (const s of sedes) {
    const clave = s.pertenece_ietaba ? "IETABA y asociadas" : s.institucion_centro_educativo || "Otras instituciones";
    if (!grupos.has(clave)) grupos.set(clave, { ietaba: s.pertenece_ietaba, sedes: [] });
    grupos.get(clave).sedes.push(s);
  }
  const ordenados = [...grupos.entries()].sort(
    ([an, a], [bn, b]) => Number(b.ietaba) - Number(a.ietaba) || an.localeCompare(bn, "es")
  );
  return ordenados
    .map(
      ([nombre, g]) => `<optgroup label="${esc(nombre)}">
        ${g.sedes
          .map((s) => `<option value="${s.id}" ${s.id === sedeSeleccionada ? "selected" : ""}>${esc(sedeCorta(s))}</option>`)
          .join("")}
      </optgroup>`
    )
    .join("");
}

function chipsFiltrosEstudiantes(sedes) {
  const chips = [];
  if (busquedaActual) chips.push({ id: "busqueda", texto: `Búsqueda: “${busquedaActual}”` });
  if (sedeSeleccionada) chips.push({ id: "sede", texto: `Sede: ${sedeCorta(sedes.find((s) => s.id === sedeSeleccionada))}` });
  if (gradoSeleccionado !== null) chips.push({ id: "grado", texto: `Grado: ${nombreDeGrado(gradoSeleccionado)}` });
  if (divisionSeleccionada !== null) {
    const d = (estGradosData.find((g) => g.grado === gradoSeleccionado)?.divisiones || []).find((x) => x.numero === divisionSeleccionada);
    chips.push({ id: "division", texto: `División: ${d ? d.nombre : divisionSeleccionada}` });
  }
  if (estadoSeleccionado) chips.push({ id: "estado", texto: "Estado: Activos" });
  if (soloNoVerificados) chips.push({ id: "no-verificados", texto: "Solo no verificados" });
  if (sinCurso) chips.push({ id: "sin-curso", texto: "Sin sección asignada" });
  if (soloPendientesSimat) chips.push({ id: "pendiente-simat", texto: "Nuevos · pendiente SIMAT" });
  return chips;
}

function pintarFiltrosEstudiantes(sedes) {
  const zona = document.getElementById("est-filtros");
  const idFoco = document.activeElement?.id; // se restaura tras repintar
  const divisionesDisponibles =
    gradoSeleccionado !== null ? estGradosData.find((g) => g.grado === gradoSeleccionado)?.divisiones || [] : [];
  const chips = chipsFiltrosEstudiantes(sedes);
  const nSecundarios = Number(soloNoVerificados) + Number(sinCurso) + Number(soloPendientesSimat);

  zona.innerHTML = `
    <div class="barra-filtros">
      <label class="filtro-campo">Sede
        <select id="filtro-sede">
          <option value="">Todas las sedes</option>
          ${opcionesSedeHtml(sedes)}
        </select>
      </label>
      <label class="filtro-campo">Grado
        <select id="filtro-grado">
          <option value="">Todos</option>
          ${NOMBRES_GRADOS.map(
            ([g, nombre]) => `<option value="${g}" ${g === gradoSeleccionado ? "selected" : ""}>${nombre}</option>`
          ).join("")}
        </select>
      </label>
      ${
        divisionesDisponibles.length
          ? `<label class="filtro-campo">División
               <select id="filtro-division">
                 <option value="">Todas las divisiones</option>
                 ${divisionesDisponibles
                   .map(
                     (d) => `<option value="${d.numero}" ${d.numero === divisionSeleccionada ? "selected" : ""}>División ${esc(d.nombre)}</option>`
                   )
                   .join("")}
               </select>
             </label>`
          : ""
      }
      <label class="filtro-campo">Estado
        <select id="filtro-estado">
          <option value="" ${estadoSeleccionado === "" ? "selected" : ""}>Todos</option>
          <option value="ACTIVO" ${estadoSeleccionado === "ACTIVO" ? "selected" : ""}>Activos</option>
        </select>
      </label>
      <details class="menu-herramientas menu-mas-filtros" id="menu-mas-filtros" ${estMasFiltrosAbierto ? "open" : ""}>
        <summary class="boton secundario">Más filtros${nSecundarios ? ` <span class="segmentado-num">${nSecundarios}</span>` : ""}</summary>
        <div class="menu-herramientas-lista">
          <label class="check-linea filtro-check">
            <input type="checkbox" id="filtro-no-verificados" ${soloNoVerificados ? "checked" : ""} /> Solo no verificados
          </label>
          <label class="check-linea filtro-check">
            <input type="checkbox" id="filtro-sin-curso" ${sinCurso ? "checked" : ""} /> Sin sección asignada
          </label>
          <label class="check-linea filtro-check">
            <input type="checkbox" id="filtro-pendiente-simat" ${soloPendientesSimat ? "checked" : ""} /> Nuevos · pendiente SIMAT
          </label>
        </div>
      </details>
      ${hayFiltrosEstudiantes() ? '<button type="button" class="boton-texto" id="btn-limpiar-filtros">Limpiar filtros</button>' : ""}
    </div>
    ${
      chips.length
        ? `<div class="chips-filtros" aria-label="Filtros activos">
             <span class="chips-filtros-titulo">Filtros activos (${chips.length})</span>
             ${chips
               .map(
                 (c) => `<button type="button" class="chip-filtro" data-quitar-filtro="${c.id}" aria-label="Quitar filtro: ${esc(c.texto)}">
                           ${esc(c.texto)} <span aria-hidden="true"><i data-lucide=x class=ico></i> </span>
                         </button>`
               )
               .join("")}
           </div>`
        : ""
    }`;

  if (idFoco && zona.querySelector(`#${idFoco}`)) document.getElementById(idFoco).focus();
  vincularFiltrosEstudiantes();
}

// Cualquier cambio de filtro vuelve a la primera página y repinta solo las
// zonas de datos (antes: render() completo, con la pantalla en blanco).
function cambiarFiltroEstudiantes(cambio) {
  cambio();
  paginaActual = 1;
  refrescarEstudiantes();
}

function vincularFiltrosEstudiantes() {
  document.getElementById("filtro-sede").addEventListener("change", (e) =>
    cambiarFiltroEstudiantes(() => {
      sedeSeleccionada = e.target.value ? Number(e.target.value) : null;
      gradoSeleccionado = null;
      divisionSeleccionada = null;
    })
  );
  document.getElementById("filtro-grado").addEventListener("change", (e) =>
    cambiarFiltroEstudiantes(() => {
      gradoSeleccionado = e.target.value === "" ? null : Number(e.target.value);
      divisionSeleccionada = null;
    })
  );
  document.getElementById("filtro-division")?.addEventListener("change", (e) =>
    cambiarFiltroEstudiantes(() => {
      divisionSeleccionada = e.target.value === "" ? null : Number(e.target.value);
    })
  );
  document.getElementById("filtro-estado").addEventListener("change", (e) =>
    cambiarFiltroEstudiantes(() => {
      estadoSeleccionado = e.target.value;
    })
  );
  document.getElementById("filtro-no-verificados").addEventListener("change", (e) =>
    cambiarFiltroEstudiantes(() => {
      soloNoVerificados = e.target.checked;
    })
  );
  document.getElementById("filtro-sin-curso").addEventListener("change", (e) =>
    cambiarFiltroEstudiantes(() => {
      sinCurso = e.target.checked;
    })
  );
  document.getElementById("filtro-pendiente-simat").addEventListener("change", (e) =>
    cambiarFiltroEstudiantes(() => {
      soloPendientesSimat = e.target.checked;
    })
  );
  // "Más filtros" se mantiene abierto mientras se marcan las casillas, aunque
  // la barra se repinte; se cierra al hacer clic fuera (core.js) o con Escape.
  document.getElementById("menu-mas-filtros").addEventListener("toggle", (e) => {
    estMasFiltrosAbierto = e.target.open;
  });

  document.getElementById("btn-limpiar-filtros")?.addEventListener("click", () => {
    clearTimeout(temporizadorBusqueda);
    cambiarFiltroEstudiantes(() => {
      sedeSeleccionada = null;
      gradoSeleccionado = null;
      divisionSeleccionada = null;
      estadoSeleccionado = "";
      soloNoVerificados = false;
      sinCurso = false;
      soloPendientesSimat = false;
      busquedaActual = "";
      const buscador = document.getElementById("buscar");
      if (buscador) buscador.value = "";
      const limpiar = document.getElementById("buscar-limpiar");
      if (limpiar) limpiar.hidden = true;
    });
  });

  document.querySelectorAll("[data-quitar-filtro]").forEach((chip) => {
    chip.addEventListener("click", () =>
      cambiarFiltroEstudiantes(() => {
        switch (chip.dataset.quitarFiltro) {
          case "busqueda": {
            clearTimeout(temporizadorBusqueda);
            busquedaActual = "";
            const buscador = document.getElementById("buscar");
            if (buscador) buscador.value = "";
            const limpiar = document.getElementById("buscar-limpiar");
            if (limpiar) limpiar.hidden = true;
            break;
          }
          case "sede": // igual que el select: al quitar la sede se van sus grados
            sedeSeleccionada = null;
            gradoSeleccionado = null;
            divisionSeleccionada = null;
            break;
          case "grado":
            gradoSeleccionado = null;
            divisionSeleccionada = null;
            break;
          case "division": divisionSeleccionada = null; break;
          case "estado": estadoSeleccionado = ""; break;
          case "no-verificados": soloNoVerificados = false; break;
          case "sin-curso": sinCurso = false; break;
          case "pendiente-simat": soloPendientesSimat = false; break;
        }
      })
    );
  });
}

// --- Resumen ------------------------------------------------------------------

function resumenEstudiantesHtml({ total, activos, pendientes, sinCurso: nSinCurso }) {
  const hayContexto = Boolean(sedeSeleccionada || gradoSeleccionado !== null || divisionSeleccionada !== null || busquedaActual);
  return `
    <div class="resumen-reportes resumen-compacta">
      <div class="metric-card"><span>Estudiantes</span><strong>${numeroConMiles(total)}</strong></div>
      <div class="metric-card ok"><span>Activos</span><strong>${numeroConMiles(activos)}</strong></div>
      <button type="button" class="metric-card metric-boton ${pendientes > 0 ? "alerta" : ""} ${soloNoVerificados ? "seleccionada" : ""}"
              data-metrica="no-verificados" aria-pressed="${soloNoVerificados}"
              title="Estudiantes que no aparecen en la matrícula oficial importada. Clic para filtrar.">
        <span>Por verificar</span><strong>${numeroConMiles(pendientes)}</strong>
      </button>
      <button type="button" class="metric-card metric-boton ${nSinCurso > 0 ? "alarma-suave" : ""} ${sinCurso ? "seleccionada" : ""}"
              data-metrica="sin-curso" aria-pressed="${sinCurso}"
              title="Estudiantes con grado pero sin sección asignada. Clic para filtrar.">
        <span>Sin sección</span><strong>${numeroConMiles(nSinCurso)}</strong>
      </button>
    </div>
    <p class="resumen-contexto">${hayContexto ? "Cifras de la selección actual (sede, grado y búsqueda)." : "Cifras de todos los estudiantes."}</p>`;
}

function vincularResumenEstudiantes() {
  document.querySelectorAll("[data-metrica]").forEach((tarjeta) => {
    tarjeta.addEventListener("click", () =>
      cambiarFiltroEstudiantes(() => {
        if (tarjeta.dataset.metrica === "no-verificados") soloNoVerificados = !soloNoVerificados;
        else sinCurso = !sinCurso;
      })
    );
  });
}

function resultadosHeaderHtml(total, puedeImprimir) {
  return `
    <span class="conteo-resultados" id="conteo-estudiantes">
      <strong>${numeroConMiles(total)}</strong> ${total === 1 ? "estudiante encontrado" : "estudiantes encontrados"}
      <span class="conteo-orden">· ordenados por grado, sección y apellido</span>
    </span>
    ${puedeImprimir ? exportarDropdownHtml() : ""}`;
}

function vincularExportarEstudiantes(sedes) {
  document.getElementById("btn-toggle-imprimir")?.addEventListener("click", async () => {
    mostrarImprimir = !mostrarImprimir;
    await renderZonaImpresion(sedes, estGradosData);
    const btn = document.getElementById("btn-toggle-imprimir");
    if (btn) btn.textContent = mostrarImprimir ? "Ocultar hoja de impresión" : "Imprimir lista (formato oficial)";
    const menuExportar = document.getElementById("menu-exportar");
    if (menuExportar) menuExportar.open = false;
  });
}

// --- Lista --------------------------------------------------------------------

// La lista (tabla + paginación) se pinta con una sola página del servidor:
// nunca hay más filas en el DOM que el tamaño de página elegido.
function listaEstudiantesHtml(resultado) {
  if (!resultado.items.length) return estadoVacioHtml();
  const mostrarSede = !sedeSeleccionada; // dentro de una sede todas las filas son de la misma
  // Con pocas filas no hay sitio bajo la última para desplegar su menú ⋮
  // (el contenedor recorta): se reserva espacio. Con muchas, las últimas
  // filas abren el menú hacia arriba (ver style.css).
  return `
    <div class="tabla-scroll ${resultado.items.length <= 4 ? "tabla-corta" : ""}">
      <table class="tabla-estudiantes">
        <thead>
          <tr>
            <th>Estudiante</th>
            <th class="col-grupo">Grupo</th>
            ${mostrarSede ? '<th class="col-sede">Sede</th>' : ""}
            <th class="col-estado">Estado</th>
            <th class="col-verif">Verificación</th>
            <th class="col-acciones no-imprimir"><span class="sr-only">Acciones</span></th>
          </tr>
        </thead>
        <tbody>${resultado.items.map((e) => filaEstudiante(e, mostrarSede)).join("")}</tbody>
      </table>
    </div>
    ${controlesPaginacion(resultado)}`;
}

function vincularListaEstudiantes() {
  const abrir = (id) => {
    estScrollGuardado = window.scrollY;
    abrirFicha(id, "estudiantes");
  };

  document.querySelectorAll("[data-pagina]").forEach((btn) => {
    btn.addEventListener("click", () => {
      paginaActual = Number(btn.dataset.pagina);
      refrescarEstudiantes({ desplazar: true });
    });
  });

  document.querySelectorAll("[data-abrir-estudiante]").forEach((btn) => {
    btn.addEventListener("click", () => abrir(Number(btn.dataset.abrirEstudiante)));
  });

  // El menú "⋮" vive dentro de la fila clicable: hay que frenar la propagación
  // para que abrir el menú no abra también al estudiante.
  document.querySelectorAll(".menu-fila").forEach((menu) => {
    menu.addEventListener("click", (ev) => ev.stopPropagation());
  });

  document.querySelectorAll("[data-accion-ver]").forEach((btn) => {
    btn.addEventListener("click", () => abrir(Number(btn.dataset.accionVer)));
  });

  // Borrar no tiene vuelta atrás. Si ya tiene notas, constancias o boletines,
  // el servidor no lo deja (409) y se explica que se pase a RETIRADO.
  document.querySelectorAll("[data-accion-eliminar]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.closest("details").open = false;
      const { nombre, documento } = btn.dataset;
      if (!confirm(`¿Eliminar a ${nombre} (doc. ${documento})?\n\nSe borra del sistema con su ficha, fotos y documentos. No se puede deshacer.`)) return;
      try {
        await api(`/api/estudiantes/${btn.dataset.accionEliminar}`, { method: "DELETE", sinCola: true });
        refrescarEstudiantes();
      } catch (err) {
        alert(err.message);
      }
    });
  });

  document.querySelectorAll("[data-accion-imprimir-grupo]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const [sede, grado, curso] = btn.dataset.accionImprimirGrupo.split("|");
      sedeSeleccionada = Number(sede);
      gradoSeleccionado = Number(grado);
      divisionSeleccionada = curso === "" ? null : Number(curso);
      mostrarImprimir = true;
      paginaActual = 1;
      render();
    });
  });

  // Clic en cualquier parte de la fila (comodidad con el mouse). El nombre es
  // el botón accesible; lo demás interactivo de la fila (menú) se excluye.
  document.querySelectorAll("tbody tr[data-id]").forEach((fila) => {
    fila.addEventListener("click", (ev) => {
      if (ev.target.closest("button, a, details")) return;
      abrir(Number(fila.dataset.id));
    });
  });

  document.getElementById("vacio-limpiar")?.addEventListener("click", () => {
    document.getElementById("btn-limpiar-filtros")?.click();
  });

  document.getElementById("tamano-pagina")?.addEventListener("change", (e) => {
    porPagina = Number(e.target.value);
    paginaActual = 1;
    refrescarEstudiantes();
  });
}

function exportarDropdownHtml() {
  return `
    <details class="menu-herramientas" id="menu-exportar">
      <summary class="boton secundario" style="display:inline-block; cursor:pointer">Exportar ▾</summary>
      <div class="menu-herramientas-lista">
        <button type="button" class="item-menu" id="btn-toggle-imprimir">
          ${mostrarImprimir ? "Ocultar hoja de impresión" : "<i data-lucide=printer class=ico></i> Imprimir lista (formato oficial)"}
        </button>
      </div>
    </details>`;
}

// El mensaje depende de QUÉ se pidió: no es lo mismo una búsqueda sin
// coincidencias que "0 pendientes de verificación", que es una buena noticia.
function estadoVacioHtml() {
  let icono = "<i data-lucide=search class=ico></i> ";
  let titulo = "No encontramos estudiantes";
  let texto = "Prueba cambiando los filtros o realizando otra búsqueda.";
  if (busquedaActual) {
    titulo = `Ningún estudiante coincide con «${esc(busquedaActual)}»`;
    texto = "Se busca por nombre o documento, sin distinguir mayúsculas ni tildes.";
  } else if (soloNoVerificados && !sinCurso) {
    icono = "<i data-lucide=circle-check class=ico></i> ";
    titulo = "No hay estudiantes por verificar";
    texto = "Todos los de esta selección que se pudieron comparar aparecen en la matrícula oficial.";
  } else if (sinCurso && !soloNoVerificados) {
    icono = "<i data-lucide=circle-check class=ico></i> ";
    titulo = "Todos tienen sección asignada";
    texto = "Ningún estudiante de esta selección está sin sección.";
  } else if (sedeSeleccionada && gradoSeleccionado === null && divisionSeleccionada === null && !estadoSeleccionado) {
    icono = "<i data-lucide=school class=ico></i> ";
    titulo = "Esta sede no tiene estudiantes";
    texto = "No hay estudiantes registrados en la sede seleccionada.";
  }
  return `
    <div class="estado-vacio">
      <div class="estado-vacio-icono" aria-hidden="true">${icono}</div>
      <h3>${titulo}</h3>
      <p>${texto}</p>
      ${hayFiltrosEstudiantes() ? '<button type="button" class="boton secundario est-vacio-accion" id="vacio-limpiar">Limpiar filtros</button>' : ""}
    </div>`;
}

function inicialesDe(nombreCompleto) {
  const partes = nombreCompleto.split(" ").filter(Boolean);
  return [partes[0], partes[partes.length - 1]]
    .filter(Boolean)
    .map((p) => p[0].toUpperCase())
    .join("");
}

// Ventana de páginas: 1 … 4 5 [6] 7 8 … 44
function ventanaPaginas(actual, total) {
  const set = new Set([1, total, actual - 2, actual - 1, actual, actual + 1, actual + 2]);
  const orden = [...set].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b);
  const salida = [];
  orden.forEach((p, i) => {
    if (i && p - orden[i - 1] > 1) salida.push("…");
    salida.push(p);
  });
  return salida;
}

function controlesPaginacion(resultado) {
  if (resultado.por_pagina <= 0) return "";
  const totalPaginas = Math.max(1, Math.ceil(resultado.total / resultado.por_pagina));
  const actual = resultado.pagina;
  const desde = resultado.total === 0 ? 0 : (actual - 1) * resultado.por_pagina + 1;
  const hasta = Math.min(resultado.total, actual * resultado.por_pagina);

  const numeros = ventanaPaginas(actual, totalPaginas)
    .map((p) =>
      p === "…"
        ? '<span class="paginacion-puntos" aria-hidden="true">…</span>'
        : `<button type="button" class="pag-num ${p === actual ? "activa" : ""}" data-pagina="${p}" ${p === actual ? 'aria-current="page"' : ""} aria-label="Página ${p}">${p}</button>`
    )
    .join("");

  return `
    <div class="paginacion paginacion-estudiantes no-imprimir">
      <span class="paginacion-info">Mostrando ${numeroConMiles(desde)}–${numeroConMiles(hasta)} de ${numeroConMiles(resultado.total)}</span>
      ${
        totalPaginas > 1
          ? `<nav class="paginacion-nav" aria-label="Paginación">
               <button type="button" class="boton secundario boton-chico" ${actual <= 1 ? "disabled" : ""} data-pagina="${actual - 1}">‹ Anterior</button>
               <span class="paginacion-numeros">${numeros}</span>
               <span class="paginacion-estado">Página ${actual} de ${totalPaginas}</span>
               <button type="button" class="boton secundario boton-chico" ${actual >= totalPaginas ? "disabled" : ""} data-pagina="${actual + 1}">Siguiente ›</button>
             </nav>`
          : ""
      }
      <select id="tamano-pagina" aria-label="Estudiantes por página">
        ${TAMANOS_PAGINA.map((n) => `<option value="${n}" ${n === porPagina ? "selected" : ""}>${n} por página</option>`).join("")}
      </select>
    </div>`;
}

function verificacionBadgeHtml(e) {
  if (e.pendiente_simat)
    return `<span class="badge-verif alerta" title="Matriculado aquí${e.creado_por_nombre ? ` por ${esc(e.creado_por_nombre)}` : ""}; falta registrarlo en SIMAT">Nuevo · pendiente SIMAT</span>`;
  if (e.verificado_matricula === true) return '<span class="badge-verif ok"><i data-lucide=check class=ico></i> Verificado</span>';
  if (e.verificado_matricula === false)
    return '<span class="badge-verif alerta" title="No aparece en la base de datos oficial de matrícula importada">Pendiente</span>';
  return '<span class="badge-verif neutro" title="Todavía no hay Excel de matrícula propio para esta sede con el cual comparar">Sin comparar</span>';
}

function filaEstudiante(e, mostrarSede) {
  const nombre = `${e.primer_nombre} ${e.segundo_nombre || ""} ${e.primer_apellido} ${e.segundo_apellido || ""}`
    .replace(/\s+/g, " ")
    .trim();
  const grupoImprimir = `${e.sede_id ?? ""}|${e.grado}|${e.curso ?? ""}`;
  // Sin sección se distingue a simple vista: el modelo devuelve solo el nombre
  // del grado ("Preescolar") cuando curso es NULL, idéntico a un grupo normal.
  const grupoHtml =
    e.curso === null
      ? `${esc(e.grupo)} <span class="chip-sin-seccion" title="Grado asignado, pero todavía sin sección/curso">Sin sección</span>`
      : esc(e.grupo);
  const detalleSede = e.sede
    ? [e.sede.resguardo, e.sede.institucion_centro_educativo].filter(Boolean).join(" · ")
    : "";

  return `
    <tr data-id="${e.id}" class="fila-clicable">
      <td class="col-estudiante">
        <div class="celda-estudiante">
          <span class="avatar-iniciales" aria-hidden="true">${esc(inicialesDe(nombre))}</span>
          <div class="celda-estudiante-texto">
            <button type="button" class="enlace-estudiante" data-abrir-estudiante="${e.id}">${esc(nombre)}</button>
            <div class="doc-estudiante">${esc(e.documento)}</div>
            <div class="est-secundaria-movil">${grupoHtml}${mostrarSede ? ` · ${esc(sedeCorta(e.sede))}` : ""}</div>
          </div>
        </div>
      </td>
      <td class="col-grupo">${grupoHtml}</td>
      ${
        mostrarSede
          ? `<td class="col-sede" title="${esc(detalleSede)}"><span class="sede-etiqueta">${esc(sedeCorta(e.sede))}</span></td>`
          : ""
      }
      <td class="col-estado"><span class="badge ${e.activo ? "activo" : "inactivo"}">${esc((e.estado || "").toLowerCase())}</span></td>
      <td class="col-verif">${verificacionBadgeHtml(e)}</td>
      <td class="col-acciones no-imprimir">
        <details class="menu-fila">
          <summary class="boton-icono" aria-label="Acciones de ${esc(nombre)}" title="Acciones">⋮</summary>
          <div class="menu-herramientas-lista">
            <button type="button" class="item-menu" data-accion-ver="${e.id}">Ver estudiante</button>
            ${
              e.sede_id != null
                ? `<button type="button" class="item-menu" data-accion-imprimir-grupo="${grupoImprimir}">Imprimir lista de su grupo</button>`
                : ""
            }
            ${
              tienePermiso("estudiantes.eliminar")
                ? `<button type="button" class="item-menu item-peligro" data-accion-eliminar="${e.id}" data-nombre="${esc(nombre)}" data-documento="${esc(e.documento)}">Eliminar estudiante</button>`
                : ""
            }
          </div>
        </details>
      </td>
    </tr>`;
}

// --- Zona de impresión contextual (dentro de Estudiantes) -------------------

async function renderZonaImpresion(sedes, gradosDeSede) {
  const zona = document.getElementById("zona-impresion");
  if (!mostrarImprimir) {
    zona.innerHTML = "";
    return;
  }

  const divisionesDisponibles =
    gradoSeleccionado !== null
      ? gradosDeSede.find((g) => g.grado === gradoSeleccionado)?.divisiones || []
      : [];

  const params = new URLSearchParams();
  params.set("sede_id", sedeSeleccionada);
  params.set("grado", gradoSeleccionado);
  if (divisionSeleccionada !== null) params.set("curso", divisionSeleccionada);
  params.set("estado", "ACTIVO");
  const estudiantes = await api(`/api/estudiantes?${params}`);

  const sede = sedes.find((s) => s.id === sedeSeleccionada);
  const nombreGrado = gradosDeSede.find((g) => g.grado === gradoSeleccionado)?.nombre_grado || "";

  zona.innerHTML = `
    <div class="toolbar no-imprimir">
      ${
        divisionesDisponibles.length
          ? `<select id="filtro-division-imprimir">
               <option value="">General (todas las divisiones)</option>
               ${divisionesDisponibles
                 .map(
                   (d) =>
                     `<option value="${d.numero}" ${d.numero === divisionSeleccionada ? "selected" : ""}>División ${d.nombre}</option>`
                 )
                 .join("")}
             </select>`
          : ""
      }
      <select id="filtro-mes-imprimir">
        ${MESES.map((m, i) => `<option value="${i}" ${i === mesSeleccionado ? "selected" : ""}>${m}</option>`).join("")}
      </select>
      <button class="boton" id="btn-imprimir">Imprimir</button>
      ${tienePermiso("reportes.ver") ? '<button type="button" class="boton secundario" id="btn-imprimir-varios">Imprimir varios grupos a la vez</button>' : ""}
    </div>
    ${
      estudiantes.length
        ? hojaImprimible(sede, nombreGrado, estudiantes)
        : '<p class="no-imprimir">Esta sede/grado no tiene estudiantes activos.</p>'
    }
  `;

  document.getElementById("filtro-division-imprimir")?.addEventListener("change", (e) => {
    divisionSeleccionada = e.target.value === "" ? null : Number(e.target.value);
    render();
  });

  document.getElementById("filtro-mes-imprimir")?.addEventListener("change", (e) => {
    mesSeleccionado = Number(e.target.value);
    renderZonaImpresion(sedes, gradosDeSede);
  });

  document.getElementById("btn-imprimir")?.addEventListener("click", () => window.print());
  // Reportes → Listas de asistencia: varios grupos en un solo PDF oficio.
  document.getElementById("btn-imprimir-varios")?.addEventListener("click", () => {
    seccionReportes = "asistencia";
    asistListaSede = String(sedeSeleccionada);
    const grupo = divisionSeleccionada !== null ? `${gradoSeleccionado}-${divisionSeleccionada}` : String(gradoSeleccionado);
    asistListaGrupos = grupo;
    asistListaMes = mesSeleccionado + 1;
    document.querySelector('[data-vista="reportes"]')?.click();
  });
}

// --- Hoja imprimible (formato oficial del Excel) -----------------------------

const INSTITUCION_NOMBRE = "INST. EDU. TECNICA AGROAMBIENTAL BILINGÜE AWÁ - IETABA";
const INSTITUCION_CODIGO_DANE = "252079002045";

function formatoFecha(iso) {
  if (!iso) return "";
  const [anio, mes, dia] = iso.split("-");
  return `${dia}/${mes}/${anio}`;
}

// Estas son las UNICAS columnas que realmente se ven al imprimir el Excel
// oficial (columnas A-I y las de FECHA HOY/EDAD existen en la hoja pero
// están ocultas y no salen en el área de impresión).
function columnasEstudiante(e, i) {
  return [
    i + 1,
    e.grado,
    e.tipo_documento || "",
    e.documento,
    e.primer_apellido,
    e.segundo_apellido || "",
    e.primer_nombre,
    e.segundo_nombre || "",
    formatoFecha(e.fecha_nacimiento),
    e.genero || "",
  ];
}

const ENCABEZADOS_DATOS = [
  "No", "GRADO", "TIPO DOC.", "NRO DOCUMENTO", "PRIMER APELLIDO", "SEGUNDO APELLIDO",
  "PRIMER NOMBRE", "SEGUNDO NOMBRE", "FECHA NACIMIENTO", "GENERO",
];

// Ancho de cada columna de datos (%), para que las 31 casillas de días
// alcancen a caber en una sola hoja horizontal, igual que el Excel original.
const ANCHOS_DATOS = [3, 3, 3, 8, 7, 7, 7, 7, 9, 2];

const COLUMNAS_NOMBRE = [4, 5, 6, 7]; // indices de apellidos/nombres: alineados a la izquierda

function hojaImprimible(sede, nombreGrado, estudiantes) {
  const dias = Array.from({ length: 31 }, (_, i) => i + 1);
  const nombreMes = MESES[mesSeleccionado];

  return `
    <div class="hoja-imprimir">
      <div class="hoja-encabezado">
        <img src="/static/logos/logo1.jpg" alt="UNIPA" />
        <div class="titulo">
          <p>UNIDAD INDIGENA DEL PUEBLO AWA</p>
          <p>GOBERNACION DE NARIÑO</p>
          <p>SECRETARIA DE EDUCACION DEPARTAMENTAL</p>
          <p>CONTRATO No. 1987 - 26 DEL 2025</p>
          <div class="lista-asistencia">LISTA DE ASISTENCIA</div>
        </div>
        <img src="/static/logos/logo2.jpeg" alt="IETABA" />
      </div>
      <div class="hoja-campos">
        <div class="campo"><span class="etiqueta">ESTABLECIMIENTO EDUCATIVO:</span><span class="valor">${INSTITUCION_NOMBRE}</span></div>
        <div class="campo"><span class="etiqueta">CODIGO DANE E.E:</span><span class="valor">${INSTITUCION_CODIGO_DANE}</span></div>
        <div class="campo"><span class="etiqueta">MES:</span><span class="valor">${nombreMes.toUpperCase()}</span></div>
        <div class="campo"><span class="etiqueta">NOMBRE DE LA SEDE:</span><span class="valor">${sede?.nombre || ""}</span></div>
        <div class="campo"><span class="etiqueta">CODIGO DANE SEDE:</span><span class="valor">${sede?.codigo_dane_sede || ""}</span></div>
      </div>
      <div class="hoja-tabla-scroll">
        <table class="tabla-imprimir">
          <thead>
            <tr>
              ${ENCABEZADOS_DATOS.map(
                (h, idx) =>
                  `<th class="${COLUMNAS_NOMBRE.includes(idx) ? "col-nombre" : ""}" style="width:${ANCHOS_DATOS[idx]}%">${h}</th>`
              ).join("")}
              ${dias.map((d) => `<th class="col-dia">${d}</th>`).join("")}
            </tr>
          </thead>
          <tbody>
            ${estudiantes
              .map((e, i) => {
                const cols = columnasEstudiante(e, i);
                return `
              <tr>
                ${cols
                  .map((v, idx) => `<td class="${COLUMNAS_NOMBRE.includes(idx) ? "col-nombre" : ""}">${v ?? ""}</td>`)
                  .join("")}
                ${dias.map(() => `<td class="col-dia"></td>`).join("")}
              </tr>`;
              })
              .join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}
