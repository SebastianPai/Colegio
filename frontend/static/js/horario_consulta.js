// --- Horarios: consultar, planificar, analizar y reportar ----------------------
// Complemento de horario.js (armazón, caché y componentes compartidos). Aquí
// viven Docente, Grupo, Día, Abrir hueco, Resumen, Horas libres y Reporte Word.
// La lógica académica (huecos, receso por nivel, cálculos del resumen, los
// PDF y el Word) es la de siempre; cambia cómo se presenta.

// Día de la semana de HOY (1-5) o 0 si es fin de semana: resalta su columna.
const hzHoyDiaSemana = () => {
  const d = diaSemanaISO(fechaHoyISO());
  return d >= 1 && d <= 5 ? d : 0;
};
const hzColHoy = (dia) => (dia === hzHoyDiaSemana() ? " col-hoy" : "");

// Lista de grupos únicos (grado + curso) de la rejilla, ordenados.
function hzGruposDe(bloques) {
  const grupos = [];
  bloques.forEach((b) => {
    const clave = `${b.grado}|${b.curso ?? ""}`;
    if (!grupos.some((g) => g.clave === clave)) grupos.push({ clave, grado: b.grado, curso: b.curso, nombre: b.nombre_grupo });
  });
  return grupos.sort((a, b) => a.grado - b.grado || (a.curso || 0) - (b.curso || 0));
}

const hzMarcaConflicto = `<span class="marca-conflicto" title="Dos docentes para este grupo a esta hora — revisar en Conflictos"></span>`;
const hzMarcaDescartado = `<span class="marca-descartado" title="Descartado al resolver un conflicto"></span>`;

// ==========================================================================
//  CONSULTAR · DOCENTE
// ==========================================================================

let horarioSoloHoyDocente = false;

function celdaBloqueHtml(b, dia) {
  if (!b) return `<td class="celda-libre${hzColHoy(dia)}"><span>LIBRE</span></td>`;
  const descartado = b.estado === "descartado";
  const marca = b.en_conflicto ? ` ${hzMarcaConflicto}` : descartado ? ` ${hzMarcaDescartado}` : "";
  return `<td class="celda-clase ${descartado ? "celda-descartada" : ""} ${b.en_conflicto ? "celda-conflicto" : ""}${hzColHoy(dia)}">
      <span class="celda-area">${esc(b.area_label)}${marca}</span>
      <span class="celda-grupo">${etiquetaGrupoHorario(b.grado, b.curso)}</span>
    </td>`;
}

// Fila divisoria del receso (10:15–11:00), va entre la 3ª y la 4ª hora.
function filaRecesoHtml(colspan) {
  return `<tr class="fila-receso">
    <th class="col-hora">Receso<span>10:15–11:00</span></th>
    <td class="celda-receso" colspan="${colspan}">RECESO</td>
  </tr>`;
}

function tablaHorarioSemana(h) {
  return `
    <div class="tabla-scroll">
      <table class="tabla-horario hz-grilla">
        <thead><tr><th class="col-hora">Hora</th>${DIAS_HORARIO.map(([n, t]) => `<th class="${hzColHoy(n).trim()}">${t}${n === hzHoyDiaSemana() ? " <small>hoy</small>" : ""}</th>`).join("")}</tr></thead>
        <tbody>
          ${h.filas
            .map(
              (f) => `${f.hora === 4 ? filaRecesoHtml(5) : ""}<tr>
                <th class="col-hora">${f.hora}ª<span>${f.inicio}–${f.fin}</span></th>
                ${f.celdas.map((b, i) => celdaBloqueHtml(b, i + 1)).join("")}
              </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function tablaHorarioDiaUnico(h, dia) {
  const idx = dia - 1;
  const filas = h.filas
    .map((f) => `${f.hora === 4 ? filaRecesoHtml(1) : ""}<tr>
        <th class="col-hora">${f.hora}ª<span>${f.inicio}–${f.fin}</span></th>
        ${celdaBloqueHtml(f.celdas[idx], dia)}
      </tr>`)
    .join("");
  return `<p class="hz-nota"><strong>${nombreDiaHorario(dia)}</strong></p>
    <div class="tabla-scroll"><table class="tabla-horario hz-grilla"><tbody>${filas}</tbody></table></div>`;
}

async function renderHorarioDocente(cont, tok) {
  const [docentes, todosBloques] = await Promise.all([hzDocentes(), hzBloques()]);
  if (!hzVigente(tok)) return;
  // La lista de docentes trae también a quienes no tienen clases cargadas: el
  // directorio y los botones ‹ › solo recorren a los que tienen horario, y en
  // el buscador los demás se marcan «sin horario».
  const conHorario = new Set(todosBloques.filter((b) => b.estado === "activo").map((b) => b.docente_id));
  const items = docentes.map((d) => ({ id: d.id, texto: d.nombre_completo, nota: conHorario.has(d.id) ? "" : "sin horario" }));
  const sel = docentes.find((d) => d.id === horarioDocenteId);

  cont.innerHTML = `
    ${hzTitulo("Horario de un docente", "Su semana completa: clases, horas libres y conflictos.")}
    <div class="hz-toolbar no-imprimir">
      <div class="hz-selector">
        <button type="button" class="boton-icono" data-doc-paso="-1" title="Docente anterior" aria-label="Docente anterior">‹</button>
        ${comboBuscableHtml("sel-docente-horario", { placeholder: "Escribe para buscar docente…", valorTexto: sel ? sel.nombre_completo : "", valorId: sel ? sel.id : "" })}
        <button type="button" class="boton-icono" data-doc-paso="1" title="Docente siguiente" aria-label="Docente siguiente">›</button>
      </div>
      ${hzSegmentado("doc-vista", [{ v: "semana", t: "Semana" }, { v: "hoy", t: "Solo hoy" }], horarioSoloHoyDocente ? "hoy" : "semana")}
    </div>
    <div id="horario-docente-cont"></div>`;

  let ultimo = null;
  const pintar = async () => {
    const caja = document.getElementById("horario-docente-cont");
    if (!horarioDocenteId) {
      const directorio = docentes.filter((d) => conHorario.has(d.id)).sort((a, b) => a.nombre_completo.localeCompare(b.nombre_completo, "es"));
      caja.innerHTML = `
        ${hzVacio({
          icono: "<i data-lucide=presentation class=ico></i> ", titulo: "Elige un docente para ver su horario",
          texto: "Escribe su nombre arriba, usa ‹ › para recorrerlos, o elígelo de la lista.",
        })}
        <h3 class="hz-panel-titulo" style="margin-top:16px">Docentes <span class="hz-contador">${directorio.length}</span></h3>
        <div class="chips-docentes">${directorio
          .map((d) => `<button type="button" class="chip-docente" data-ver-docente="${d.id}">${esc(d.nombre_completo)}</button>`)
          .join("")}</div>`;
      return;
    }
    caja.innerHTML = hzCargando("Cargando horario…");
    let h;
    try {
      h = await api(`/api/horario/docente/${horarioDocenteId}?anio_lectivo=${horarioAnio}`);
    } catch (e) {
      caja.innerHTML = hzError(e);
      hzVincularAcciones(caja, { reintentar: pintar });
      return;
    }
    if (!hzVigente(tok) || !document.getElementById("horario-docente-cont")) return;
    ultimo = h;
    const hoyDia = hzHoyDiaSemana();
    const celdas = h.filas.flatMap((f) => f.celdas);
    const libres = celdas.filter((b) => !b).length;
    const conflictos = celdas.filter((b) => b && b.en_conflicto).length;
    const soloHoy = horarioSoloHoyDocente;
    const dia = hoyDia || 1;

    caja.innerHTML = `
      <div class="hoja-imprimir hz-hoja">
        <header class="hz-hoja-cab">
          <div><span class="etiqueta-contexto">Horario docente</span><h3>${esc(h.docente_nombre)}</h3>
            <span class="hz-nota">Sede #01 · ${horarioAnio}${soloHoy ? ` · ${nombreDiaHorario(dia)}` : ""}</span></div>
          ${h.total_bloques === 0 ? "" : `<div class="hz-kpis hz-kpis-mini">
            ${hzKpi({ n: h.total_bloques, txt: "Clases por semana" })}
            ${hzKpi({ n: libres, txt: "Horas libres", tono: libres ? "ok" : "vacio" })}
            ${hzKpi({ n: conflictos, txt: "Conflictos", tono: conflictos ? "alerta" : "vacio", accion: conflictos ? "conflictos" : "", titulo: "Revisar conflictos" })}
          </div>`}
        </header>
        ${h.total_bloques === 0
          ? hzVacio({ icono: "<i data-lucide=inbox class=ico></i> ", titulo: "Este docente no tiene clases en el horario", texto: `No hay horario cargado para ${esc(h.docente_nombre)} en ${horarioAnio}.` })
          : soloHoy && !hoyDia
          ? hzVacio({ icono: "<i data-lucide=calendar class=ico></i> ", titulo: "Hoy no hay clases", texto: "Es fin de semana. Cambia a «Semana» para ver el horario completo." })
          : soloHoy ? tablaHorarioDiaUnico(h, dia) : tablaHorarioSemana(h)}
        <p class="hz-leyenda no-imprimir"><span class="hz-l libre"></span> Libre <span class="hz-l conflicto"></span> Conflicto <span class="hz-l receso"></span> Receso</p>
      </div>
      ${hzAccionesReporte({ imprimir: true, imprimirTexto: "Imprimir / Guardar PDF" })}`;
    hzVincularAcciones2(caja, {});
    hzVincularIrA(caja);
  };

  vincularComboBuscable("sel-docente-horario", items, (it) => {
    horarioDocenteId = it.id;
    pintar();
  });
  cont.querySelectorAll("[data-doc-paso]").forEach((b) =>
    b.addEventListener("click", () => {
      const orden = items.filter((x) => conHorario.has(x.id)).sort((a, c) => a.texto.localeCompare(c.texto, "es"));
      const i = orden.findIndex((x) => x.id === horarioDocenteId);
      const nuevo = orden[(i < 0 ? 0 : i + Number(b.dataset.docPaso) + orden.length) % orden.length];
      horarioDocenteId = nuevo.id;
      document.getElementById("sel-docente-horario").value = nuevo.texto;
      document.getElementById("sel-docente-horario-val").value = nuevo.id;
      pintar();
    })
  );
  hzVincularSeg(cont, "doc-vista", (v) => { horarioSoloHoyDocente = v === "hoy"; pintar(); });
  pintar();
}

// ==========================================================================
//  CONSULTAR · GRUPO
// ==========================================================================

let horarioSoloHoyGrupo = false;

// Celda de la rejilla por grupo: área + docente (el grupo ya es fijo). Si hay
// dos bloques en la franja (conflicto sin resolver) se apilan los dos.
function celdaGrupoHtml(items, dia) {
  if (!items || !items.length) return `<td class="celda-libre${hzColHoy(dia)}"><span>LIBRE</span></td>`;
  const enConflicto = items.some((b) => b.en_conflicto);
  const cuerpo = items
    .map((b) => {
      const marca = b.en_conflicto ? ` ${hzMarcaConflicto}` : b.estado === "descartado" ? ` ${hzMarcaDescartado}` : "";
      return `<span class="celda-area">${esc(b.area_label)}${marca}</span>
        <span class="celda-grupo">${esc(b.docente_nombre)}</span>`;
    })
    .join("");
  return `<td class="celda-clase ${items.every((b) => b.estado === "descartado") ? "celda-descartada" : ""} ${enConflicto ? "celda-conflicto" : ""}${hzColHoy(dia)}">${cuerpo}</td>`;
}

function tablaHorarioSemanaGrupo(bloques, dias, grado) {
  const slot = {};
  bloques.forEach((b) => ((slot[`${b.dia}-${b.hora}`] = slot[`${b.dia}-${b.hora}`] || []).push(b)));
  const tieneHora = (h) => bloques.some((b) => b.hora === h);
  // Preescolar (y cualquier grupo que no tenga 3ª hora ningún día) descansa
  // desde que termina la 2ª: el receso va 9:20–11:00 y no se pinta fila de 3ª.
  const recesoTemprano = !tieneHora(3);
  // Jornada que termina en la 5ª (12:40): 6ª = "Fin de clases". Si el grupo SÍ
  // tiene una clase en la 6ª (p. ej. recién asignada con «Abrir hueco») se
  // muestra: antes la fila se tapaba por ser primaria aunque hubiera clase.
  const finTrasQuinta = !tieneHora(6);

  const filas = [];
  for (const f of FRANJAS_HORARIO) {
    if (f.hora === 3 && recesoTemprano) continue; // absorbida por el receso
    if (f.hora === 4) {
      const ini = recesoTemprano ? "9:20" : "10:15";
      filas.push(`<tr class="fila-receso">
        <th class="col-hora">Receso<span>${ini}–11:00</span></th>
        <td class="celda-receso" colspan="${dias.length}">RECESO</td>
      </tr>`);
    }
    const celdas =
      f.hora === 6 && finTrasQuinta
        ? `<td class="celda-fin" colspan="${dias.length}">Fin de clases</td>`
        : dias.map((d) => celdaGrupoHtml(slot[`${d}-${f.hora}`], d)).join("");
    filas.push(`<tr>
      <th class="col-hora">${f.hora}ª<span>${f.inicio}–${f.fin}</span></th>
      ${celdas}
    </tr>`);
  }
  return `
    <div class="tabla-scroll">
      <table class="tabla-horario hz-grilla">
        <thead><tr><th class="col-hora">Hora</th>${dias.map((d) => `<th class="${hzColHoy(d).trim()}">${nombreDiaHorario(d)}${d === hzHoyDiaSemana() ? " <small>hoy</small>" : ""}</th>`).join("")}</tr></thead>
        <tbody>${filas.join("")}</tbody>
      </table>
    </div>`;
}

async function renderHorarioGrupo(cont, tok) {
  const bloques = await hzBloques();
  if (!hzVigente(tok)) return;
  const grupos = hzGruposDe(bloques);
  if (!grupos.length) {
    cont.innerHTML = `${hzTitulo("Horario de un grupo")}${hzVacio({ icono: "<i data-lucide=inbox class=ico></i> ", titulo: `No hay horario cargado para ${horarioAnio}`, texto: "Cambia el año lectivo arriba o importa el horario." })}`;
    return;
  }
  if (!horarioGrupoSel || !grupos.some((g) => g.grado === horarioGrupoSel.grado && (g.curso ?? null) === (horarioGrupoSel.curso ?? null)))
    horarioGrupoSel = { grado: grupos[0].grado, curso: grupos[0].curso };
  const claveSel = () => `${horarioGrupoSel.grado}|${horarioGrupoSel.curso ?? ""}`;

  cont.innerHTML = `
    ${hzTitulo("Horario de un grupo", "Qué materia y qué docente tiene el grupo en cada hora.")}
    <div class="hz-toolbar no-imprimir">
      <div class="hz-selector">
        <button type="button" class="boton-icono" data-grupo-paso="-1" title="Grupo anterior" aria-label="Grupo anterior">‹</button>
        <select id="sel-grupo-horario" aria-label="Grupo">
          ${grupos.map((g) => `<option value="${g.clave}" ${g.clave === claveSel() ? "selected" : ""}>${etiquetaGrupoHorario(g.grado, g.curso)} · ${esc(g.nombre)}</option>`).join("")}
        </select>
        <button type="button" class="boton-icono" data-grupo-paso="1" title="Grupo siguiente" aria-label="Grupo siguiente">›</button>
      </div>
      ${hzSegmentado("grupo-vista", [{ v: "semana", t: "Semana" }, { v: "hoy", t: "Solo hoy" }], horarioSoloHoyGrupo ? "hoy" : "semana")}
    </div>
    <div id="horario-grupo-cont"></div>`;

  const pintar = async () => {
    const caja = document.getElementById("horario-grupo-cont");
    caja.innerHTML = hzCargando("Cargando horario…");
    const hoyDia = hzHoyDiaSemana();
    const soloHoy = horarioSoloHoyGrupo;
    const params = new URLSearchParams({ grado: horarioGrupoSel.grado, anio_lectivo: horarioAnio });
    if (horarioGrupoSel.curso != null) params.set("curso", horarioGrupoSel.curso);
    if (soloHoy && hoyDia) params.set("dia", hoyDia);
    let g;
    try {
      g = await api(`/api/horario/grupo?${params}`);
    } catch (e) {
      caja.innerHTML = hzError(e);
      hzVincularAcciones(caja, { reintentar: pintar });
      return;
    }
    if (!hzVigente(tok) || !document.getElementById("horario-grupo-cont")) return;
    const dias = soloHoy && hoyDia ? [hoyDia] : [1, 2, 3, 4, 5];
    const tituloDia = soloHoy && hoyDia ? ` — ${nombreDiaHorario(hoyDia)}` : "";
    const activos = g.bloques.filter((b) => b.estado === "activo");
    const docentes = new Set(activos.map((b) => b.docente_id)).size;
    const conflictos = new Set(g.bloques.filter((b) => b.en_conflicto).map((b) => `${b.dia}-${b.hora}`)).size;

    caja.innerHTML = `
      <div class="hz-kpis hz-kpis-mini no-imprimir">
        ${hzKpi({ n: g.total_estudiantes, txt: "Estudiantes" })}
        ${hzKpi({ n: activos.length, txt: "Clases por semana" })}
        ${hzKpi({ n: docentes, txt: "Docentes" })}
        ${hzKpi({ n: conflictos, txt: "Conflictos", tono: conflictos ? "alerta" : "vacio", accion: conflictos ? "conflictos" : "", titulo: "Revisar conflictos" })}
      </div>
      ${soloHoy && !hoyDia ? hzVacio({ icono: "<i data-lucide=calendar class=ico></i> ", titulo: "Hoy no hay clases", texto: "Es fin de semana. Cambia a «Semana» para ver el horario completo.", tono: "neutro" }) : ""}
      <div class="hoja-imprimir hz-hoja">
        <div class="horario-documento-cabecera">${membreteHtml(`HORARIO — ${etiquetaGrupoHorario(g.grado, g.curso)} · ${esc(g.nombre_grupo)}${tituloDia} — Sede #01 · ${horarioAnio}`)}</div>
        ${tablaHorarioSemanaGrupo(g.bloques, dias, g.grado)}
      </div>
      ${hzAccionesReporte({ imprimir: true, imprimirTexto: "Imprimir / Guardar PDF", ayuda: "En el diálogo de impresión elige «Guardar como PDF»." })}`;
    hzVincularAcciones2(caja, {});
    hzVincularIrA(caja);
  };

  const elegir = (clave) => {
    const [grado, curso] = clave.split("|");
    horarioGrupoSel = { grado: Number(grado), curso: curso === "" ? null : Number(curso) };
    document.getElementById("sel-grupo-horario").value = clave;
    pintar();
  };
  document.getElementById("sel-grupo-horario").addEventListener("change", (e) => elegir(e.target.value));
  cont.querySelectorAll("[data-grupo-paso]").forEach((b) =>
    b.addEventListener("click", () => {
      const i = grupos.findIndex((g) => g.clave === claveSel());
      elegir(grupos[(i + Number(b.dataset.grupoPaso) + grupos.length) % grupos.length].clave);
    })
  );
  hzVincularSeg(cont, "grupo-vista", (v) => { horarioSoloHoyGrupo = v === "hoy"; pintar(); });
  pintar();
}

// ==========================================================================
//  CONSULTAR · DÍA (matriz grupo × hora)
// ==========================================================================

let horarioDiaNivel = "";
let horarioDiaFiltro = "";

async function renderHorarioDia(cont, tok) {
  const todos = await hzBloques();
  if (!hzVigente(tok)) return;
  const grupos = hzGruposDe(todos);
  const hoy = hzHoyDiaSemana();

  cont.innerHTML = `
    ${hzTitulo("Horario del día", "Todas las clases de la jornada: una fila por grupo y una columna por hora.")}
    <div class="hz-toolbar no-imprimir">
      ${hzSegmentado("dia-sel", DIAS_HORARIO.map(([n, t]) => ({ v: n, t: n === hoy ? `${t} · hoy` : t })), horarioDiaSel)}
      ${hzSegmentado("dia-nivel", [{ v: "", t: "Todos" }, { v: "primaria", t: "Primaria" }, { v: "secundaria", t: "Secundaria" }], horarioDiaNivel)}
      <div class="hz-filtro-texto">
        <input type="search" id="dia-filtro" placeholder="Resaltar docente, grupo o área…" value="${esc(horarioDiaFiltro)}" aria-label="Resaltar en la matriz" />
      </div>
    </div>
    <div id="horario-dia-cont"></div>`;

  const pintar = () => {
    const caja = document.getElementById("horario-dia-cont");
    const q = normalizarTexto(horarioDiaFiltro.trim());
    const delDia = todos.filter((b) => b.dia === horarioDiaSel);
    const porCelda = {};
    delDia.forEach((b) => ((porCelda[`${b.grado}|${b.curso ?? ""}|${b.hora}`] ||= []).push(b)));
    const coincide = (b) =>
      normalizarTexto(b.docente_nombre).includes(q) || normalizarTexto(b.area_label).includes(q) ||
      normalizarTexto(b.area_nombre).includes(q) || normalizarTexto(etiquetaGrupoHorario(b.grado, b.curso)) === q ||
      normalizarTexto(b.nombre_grupo).includes(q);

    let filas = grupos.filter((g) => !horarioDiaNivel || nivelDeGrado(g.grado) === horarioDiaNivel);
    if (q) filas = filas.filter((g) => FRANJAS_HORARIO.some((f) => (porCelda[`${g.clave}|${f.hora}`] || []).some(coincide)));

    const activas = delDia.filter((b) => b.estado === "activo");
    const docentes = new Set(activas.map((b) => b.docente_id)).size;
    if (!delDia.length) {
      caja.innerHTML = hzVacio({ icono: "<i data-lucide=inbox class=ico></i> ", titulo: `No hay clases cargadas el ${nombreDiaHorario(horarioDiaSel).toLowerCase()}`, texto: `No hay horario para ese día en ${horarioAnio}.` });
      return;
    }
    caja.innerHTML = `
      <p class="hz-resumen-linea"><strong>${activas.length}</strong> clases · <strong>${filas.length}</strong> grupos${q || horarioDiaNivel ? " (filtrados)" : ""} · <strong>${docentes}</strong> docentes
        ${q ? `· resaltando «${esc(horarioDiaFiltro.trim())}»` : ""}</p>
      ${filas.length ? `
      <div class="tabla-scroll hz-matriz-scroll">
        <table class="hz-matriz">
          <thead><tr><th class="hz-m-grupo">Grupo</th>${FRANJAS_HORARIO.map((f) => `<th class="hz-m-hora ${f.hora === 4 ? "tras-receso" : ""}">${f.hora}ª<span>${f.inicio}–${f.fin}</span></th>`).join("")}</tr></thead>
          <tbody>
            ${filas.map((g) => `<tr>
              <th class="hz-m-grupo" scope="row"><strong>${etiquetaGrupoHorario(g.grado, g.curso)}</strong><span>${esc(g.nombre)}</span></th>
              ${FRANJAS_HORARIO.map((f) => {
                const items = porCelda[`${g.clave}|${f.hora}`] || [];
                if (!items.length) return `<td class="hz-m-vacia ${f.hora === 4 ? "tras-receso" : ""}">—</td>`;
                return `<td class="${f.hora === 4 ? "tras-receso" : ""}">${items.map((b) => `
                  <div class="hz-m-clase ${b.estado === "descartado" ? "descartada" : ""} ${b.en_conflicto ? "conflicto" : ""} ${q ? (coincide(b) ? "hit" : "dim") : ""}" title="${esc(`${b.area_nombre || b.area_label} — ${b.docente_nombre}`)}">
                    <strong>${esc(b.area_label)}${b.en_conflicto ? " " + hzMarcaConflicto : ""}</strong>
                    <span>${esc(nombreCortoHorario(b.docente_nombre))}</span>
                  </div>`).join("")}</td>`;
              }).join("")}
            </tr>`).join("")}
          </tbody>
        </table>
      </div>` : hzVacio({ icono: "<i data-lucide=search class=ico></i> ", titulo: "Ninguna clase coincide con lo que buscas", texto: "Prueba con otro nombre, otro grupo o quita el filtro de nivel.", acciones: [{ id: "limpiar", texto: "Quitar filtros" }] })}`;
    hzVincularAcciones(caja, { limpiar: () => { horarioDiaFiltro = ""; horarioDiaNivel = ""; renderHorarioDia(cont, tok); } });
  };

  hzVincularSeg(cont, "dia-sel", (v) => { horarioDiaSel = Number(v); pintar(); });
  hzVincularSeg(cont, "dia-nivel", (v) => { horarioDiaNivel = v; pintar(); });
  let t = null;
  document.getElementById("dia-filtro").addEventListener("input", (e) => {
    clearTimeout(t);
    t = setTimeout(() => { horarioDiaFiltro = e.target.value; pintar(); }, 150);
  });
  pintar();
}

// ==========================================================================
//  PLANIFICAR · ABRIR HUECO
// ==========================================================================

function rejillaGrupoHtml(ocupados) {
  const set = new Set(ocupados.map(([d, h]) => `${d}-${h}`));
  return `
    <div class="tabla-scroll">
      <table class="tabla-horario hz-grilla">
        <thead><tr><th class="col-hora">Hora</th>${DIAS_HORARIO.map(([, t]) => `<th>${t}</th>`).join("")}</tr></thead>
        <tbody>
          ${FRANJAS_HORARIO.map(
            (f) => `<tr><th class="col-hora">${f.hora}ª<span>${f.inicio}–${f.fin}</span></th>${DIAS_HORARIO.map(
              ([d]) => (set.has(`${d}-${f.hora}`) ? `<td class="celda-clase" style="text-align:center">ocupado</td>` : `<td class="celda-libre"><span>LIBRE</span></td>`)
            ).join("")}</tr>`
          ).join("")}
        </tbody>
      </table>
    </div>`;
}

async function renderHorarioAsignar(cont, tok) {
  const [docentes, areas, bloques] = await Promise.all([hzDocentes(), hzAreas(), hzBloques()]);
  if (!hzVigente(tok)) return;
  const grupos = hzGruposDe(bloques);
  const s = horarioAsignarSel || {};

  cont.innerHTML = `
    ${hzTitulo("Abrir hueco", "Encuentra dónde colocar una clase nueva sin dejarle al docente ni al grupo una doble clase.")}
    <form id="form-asignar" class="hz-form-pasos">
      <div class="hz-paso"><span class="hz-paso-num">1</span>
        <label>Profesor
          ${comboBuscableHtml("asignar-docente", { hiddenName: "docente_id", placeholder: "Escribe para buscar…", valorTexto: s.docenteTexto || "", valorId: s.docenteId || "" })}
        </label></div>
      <div class="hz-paso"><span class="hz-paso-num">2</span>
        <label>Grupo
          <select name="grupo" id="asignar-grupo">
            ${grupos.map((g) => `<option value="${g.grado}|${g.curso ?? ""}" ${s.grado === g.grado && (s.curso ?? "") === (g.curso ?? "") ? "selected" : ""}>${etiquetaGrupoHorario(g.grado, g.curso)} · ${esc(g.nombre)}</option>`).join("")}
          </select>
        </label></div>
      <div class="hz-paso"><span class="hz-paso-num">3</span>
        <label>Materia (área)
          <select name="area_id" id="asignar-area">
            ${areas.map((a) => `<option value="${a.id}" ${String(s.areaId) === String(a.id) ? "selected" : ""}>${esc(a.codigo)} — ${esc(a.nombre)}</option>`).join("")}
          </select>
        </label></div>
      <div class="hz-paso"><span class="hz-paso-num">4</span>
        <label>Duración
          <select name="horas" id="asignar-horas">
            <option value="1" ${s.horas !== 2 ? "selected" : ""}>1 hora</option>
            <option value="2" ${s.horas === 2 ? "selected" : ""}>2 horas seguidas (bloque)</option>
          </select>
        </label></div>
      <div class="hz-paso hz-paso-accion"><span class="hz-paso-num">5</span>
        <button type="submit" class="boton" id="btn-asignar-buscar">Buscar espacios</button></div>
      <label class="check-linea hz-form-check"><input type="checkbox" name="crear_asignacion" id="asignar-crear-asig" ${s.crearAsig === false ? "" : "checked"} /> Registrar también la asignación (aparece en Boletines → Por docente)</label>
      <p class="hz-nota hz-form-error" id="asignar-error" role="alert" hidden></p>
    </form>
    <div id="asignar-resultado"></div>`;

  vincularComboBuscable("asignar-docente", docentes.map((d) => ({ id: d.id, texto: d.nombre_completo })));

  const buscar = async () => {
    const fd = new FormData(document.getElementById("form-asignar"));
    const docenteId = Number(fd.get("docente_id"));
    const error = document.getElementById("asignar-error");
    if (!docenteId) {
      error.textContent = "Elige un profesor de la lista.";
      error.hidden = false;
      document.getElementById("asignar-docente").focus();
      return;
    }
    error.hidden = true;
    const [grado, curso] = String(fd.get("grupo")).split("|");
    const areaId = Number(fd.get("area_id"));
    const horas = Number(fd.get("horas"));
    horarioAsignarSel = {
      docenteId, docenteTexto: document.getElementById("asignar-docente").value,
      grado: Number(grado), curso: curso === "" ? null : Number(curso), areaId, horas,
      crearAsig: document.getElementById("asignar-crear-asig").checked,
    };
    const box = document.getElementById("asignar-resultado");
    box.innerHTML = hzCargando("Analizando el horario…");
    const boton = document.getElementById("btn-asignar-buscar");
    boton.disabled = true;
    const p = new URLSearchParams({ docente_id: docenteId, grado, area_id: areaId, horas, anio_lectivo: horarioAnio });
    if (curso !== "") p.set("curso", curso);
    try {
      const r = await api(`/api/horario/huecos?${p}`);
      pintarHuecos(box, r, buscar);
    } catch (err) {
      box.innerHTML = hzError(err);
      hzVincularAcciones(box, { reintentar: buscar });
    } finally {
      boton.disabled = false;
    }
  };
  document.getElementById("form-asignar").addEventListener("submit", (e) => { e.preventDefault(); buscar(); });
}

function pintarHuecos(box, r, volverABuscar) {
  const s = horarioAsignarSel;
  const rango = (h) => (h.horas > 1 ? `${h.hora}ª–${h.hora_fin}ª` : `${h.hora}ª`);
  const fila = (h, i) => {
    const razones = h.razones.map((z) => `<li class="razon ${z.tipo}">${z.tipo === "ok" ? "<i data-lucide=check class=ico></i> " : "<i data-lucide=triangle-alert class=ico></i> "} ${esc(z.texto)}</li>`).join("");
    const ids = h.ocupa.map((o) => o.bloque_id).join(",");
    return `
      <article class="hz-hueco ${h.libre ? "libre" : "desplaza"}">
        <div class="hz-hueco-cuando">
          <strong>${esc(h.nombre_dia)}</strong>
          <span>${rango(h)} hora</span>
          <small>${esc(h.franja)}</small>
        </div>
        <ul class="hz-hueco-razones">${razones}</ul>
        <div class="hz-hueco-puntaje" title="Puntaje de idoneidad calculado por el sistema">
          <strong>${h.puntaje}%</strong>
          <div class="barra-progreso"><div class="barra-progreso-relleno" style="width:${h.puntaje}%"></div></div>
        </div>
        <div class="hz-hueco-accion">
          ${h.libre ? "" : `<span class="badge-estado proceso">Reacomodar ${h.ocupa.length} clase(s)</span>`}
          ${puedeGestionarHorario()
            ? `<button type="button" class="boton ${h.libre ? "" : "secundario"} boton-chico" data-asignar-hueco="${h.dia}|${h.hora}|${h.horas}" data-desplazar="${ids}" data-libre="${h.libre ? 1 : 0}">${h.libre ? "Asignar aquí" : "Asignar y quitar esas clases"}</button>`
            : ""}
        </div>
        ${i === 0 && h.libre ? `<span class="hz-hueco-mejor">Mejor opción</span>` : ""}
      </article>`;
  };
  const libres = r.huecos.filter((h) => h.libre);
  const otros = r.huecos.filter((h) => !h.libre);
  let idx = 0;

  box.innerHTML = `
    <section class="hz-resumen-seleccion">
      <span><strong>${esc(r.docente_nombre)}</strong></span><span class="hz-flecha">→</span>
      <span>${esc(r.area_label)}</span><span class="hz-flecha">·</span>
      <span>Grupo <strong>${etiquetaGrupoHorario(r.grado, r.curso)}</strong></span><span class="hz-flecha">·</span>
      <span>${r.horas > 1 ? "Bloque de 2 horas seguidas" : "1 hora"}</span>
    </section>
    <h3 class="hz-panel-titulo">Espacios disponibles <span class="hz-contador">${r.huecos.length}</span></h3>
    <p class="hz-nota">${r.total_libres} franja(s) libre(s) del grupo · ${libres.length} sin desplazar clases${otros.length ? ` · ${otros.length} que obligan a reacomodar` : ""}.</p>
    <details class="seccion-colapsable" style="margin-bottom:12px"><summary>Ver el horario actual de ${etiquetaGrupoHorario(r.grado, r.curso)}</summary>${rejillaGrupoHtml(r.ocupados)}</details>
    ${r.huecos.length
      ? `${libres.length ? `<h4 class="hz-subgrupo ok">Sin desplazar clases <span class="hz-contador">${libres.length}</span></h4><div class="hz-huecos">${libres.map((h) => fila(h, idx++)).join("")}</div>` : ""}
         ${otros.length ? `<h4 class="hz-subgrupo aviso">Requieren reacomodar otras clases <span class="hz-contador">${otros.length}</span></h4><div class="hz-huecos">${otros.map((h) => fila(h, idx++)).join("")}</div>` : ""}`
      : hzVacio({ icono: "<i data-lucide=ban class=ico></i> ", titulo: `${esc(r.docente_nombre)} está ocupado en todas las franjas`, texto: "No hay dónde meter la clase sin dejarle doble clase. Prueba con otro docente o reduce la duración.", tono: "aviso" })}
  `;

  box.querySelectorAll("[data-asignar-hueco]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const [dia, hora, horas] = btn.dataset.asignarHueco.split("|").map(Number);
      const desplazar = btn.dataset.desplazar ? btn.dataset.desplazar.split(",").map(Number) : [];
      const libre = btn.dataset.libre === "1";
      const cuando = `${nombreDiaHorario(dia)} ${hora}ª${horas > 1 ? "–" + (hora + horas - 1) + "ª" : ""} hora`;
      const ok = await hzConfirmar(
        libre
          ? { titulo: "¿Asignar esta clase?", texto: `<strong>${esc(s.docenteTexto)}</strong> · ${esc(r.area_label)} a <strong>${etiquetaGrupoHorario(r.grado, r.curso)}</strong> el ${cuando}.`, confirmar: "Asignar aquí" }
          : { titulo: `Se quitarán ${desplazar.length} clase(s)`, texto: `Se eliminan las clases que hoy ocupan esa franja (${cuando}) y se pone en su lugar a <strong>${esc(s.docenteTexto)}</strong> · ${esc(r.area_label)}.`, confirmar: "Asignar y quitar", peligro: true }
      );
      if (!ok) return;
      btn.disabled = true;
      try {
        await api("/api/horario/bloques", {
          method: "POST",
          body: JSON.stringify({
            anio_lectivo: horarioAnio, docente_id: s.docenteId, grado: r.grado, curso: r.curso, area_id: s.areaId,
            dia, hora, horas, crear_asignacion: s.crearAsig, desplazar_bloque_ids: desplazar,
          }),
        });
        hzInvalidar("bloques", "conflictos");
        horarioNotificar("Clase incorporada al horario.");
        volverABuscar(); // el mismo análisis, ya con la clase puesta
      } catch (err) {
        horarioNotificar(`No se pudo completar la operación: ${err.message}`, "error");
        btn.disabled = false;
      }
    })
  );
}

// ==========================================================================
//  ANÁLISIS · RESUMEN (por área)
// ==========================================================================

let horarioGeneralFiltroArea = "";

async function renderHorarioGeneral(cont, tok) {
  const bloques = (await hzBloques()).filter((b) => b.estado === "activo");
  if (!hzVigente(tok)) return;
  if (!bloques.length) {
    cont.innerHTML = `${hzTitulo("Resumen por área")}${hzVacio({ icono: "<i data-lucide=inbox class=ico></i> ", titulo: `No hay horario cargado para ${horarioAnio}`, texto: "Cambia el año lectivo arriba." })}`;
    return;
  }
  const areas = [...new Set(bloques.map((b) => b.area_label))].sort();

  // Resumen por área, separado en primaria y secundaria: cuántos docentes la
  // dictan y cuántas clases por semana en cada nivel.
  const porArea = {};
  bloques.forEach((b) => {
    const r = (porArea[b.area_label] = porArea[b.area_label] || {
      nombre: b.area_nombre !== b.area_label ? b.area_nombre : "",
      primaria: { docentes: new Set(), clases: 0 },
      secundaria: { docentes: new Set(), clases: 0 },
    });
    const n = r[nivelDeGrado(b.grado)];
    n.docentes.add(b.docente_id);
    n.clases += 1;
  });
  const resumenAreas = Object.entries(porArea)
    .map(([label, r]) => ({
      label, nombre: r.nombre,
      pd: r.primaria.docentes.size, pc: r.primaria.clases,
      sd: r.secundaria.docentes.size, sc: r.secundaria.clases,
      // "General": docentes distintos en total (uno que da en los dos niveles
      // cuenta una vez) y total de clases.
      td: new Set([...r.primaria.docentes, ...r.secundaria.docentes]).size,
      tc: r.primaria.clases + r.secundaria.clases,
    }))
    .sort((a, b) => b.td - a.td || b.tc - a.tc);
  const totalDocentes = new Set(bloques.map((b) => b.docente_id)).size;
  const totalGrupos = new Set(bloques.map((b) => `${b.grado}|${b.curso ?? ""}`)).size;

  cont.innerHTML = `
    ${hzTitulo("Resumen por área", "Cuántos docentes dictan cada área y cuántas clases por semana, por nivel.")}
    <div class="hz-kpis hz-kpis-mini">
      ${hzKpi({ n: resumenAreas.length, txt: "Áreas" })}
      ${hzKpi({ n: bloques.length, txt: "Clases por semana" })}
      ${hzKpi({ n: totalDocentes, txt: "Docentes" })}
      ${hzKpi({ n: totalGrupos, txt: "Grupos" })}
    </div>
    <p class="hz-nota">Primaria = Preescolar y 1°–5° · Secundaria = 6°–11°. «Docentes» = cuántos la dictan; en General, quien da en los dos niveles cuenta una sola vez. Pulsa un área para ver su detalle.</p>
    <div class="tabla-scroll">
      <table class="tabla-informe tabla-resumen-areas hz-tabla-num">
        <thead>
          <tr>
            <th rowspan="2">Área</th>
            <th colspan="2" class="col-nivel">Primaria</th>
            <th colspan="2" class="col-nivel">Secundaria</th>
            <th colspan="2" class="col-nivel col-general">General</th>
          </tr>
          <tr>
            <th>Docentes</th><th>Clases/sem.</th>
            <th>Docentes</th><th>Clases/sem.</th>
            <th class="col-general">Docentes</th><th class="col-general">Clases/sem.</th>
          </tr>
        </thead>
        <tbody>
          ${resumenAreas
            .map(
              (a) => `<tr data-area="${esc(a.label)}" tabindex="0">
                <td><strong>${esc(a.label)}</strong>${a.nombre ? `<span class="conteo-resultados"> · ${esc(a.nombre)}</span>` : ""}</td>
                <td>${a.pd || "—"}</td><td>${a.pc || "—"}</td>
                <td>${a.sd || "—"}</td><td>${a.sc || "—"}</td>
                <td class="col-general"><strong>${a.td}</strong></td><td class="col-general">${a.tc}</td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>

    <h3 class="hz-panel-titulo" id="gen-detalle-titulo">Detalle de clases</h3>
    <div class="hz-toolbar no-imprimir">
      <input type="search" id="gen-buscar" placeholder="Filtrar por docente o grupo…" />
      ${hzSegmentado("gen-nivel", [{ v: "", t: "Todos" }, { v: "primaria", t: "Primaria" }, { v: "secundaria", t: "Secundaria" }], "")}
      <label class="filtro-campo">Área
        <select id="gen-area">
          <option value="">Todas</option>
          ${areas.map((a) => `<option value="${esc(a)}" ${a === horarioGeneralFiltroArea ? "selected" : ""}>${esc(a)}</option>`).join("")}
        </select>
      </label>
      <span class="conteo-resultados" id="gen-conteo"></span>
    </div>
    <div class="tabla-scroll tabla-scroll-alto" id="gen-tabla"></div>
  `;

  let nivel = "";
  const pintar = () => {
    const q = normalizarTexto(document.getElementById("gen-buscar").value.trim());
    const area = document.getElementById("gen-area").value;
    const filas = bloques
      .filter((b) => !area || b.area_label === area)
      .filter((b) => !nivel || nivelDeGrado(b.grado) === nivel)
      .filter((b) => !q || normalizarTexto(b.docente_nombre).includes(q) || etiquetaGrupoHorario(b.grado, b.curso).includes(q) || normalizarTexto(b.nombre_grupo).includes(q))
      .sort((a, b) => a.docente_nombre.localeCompare(b.docente_nombre) || a.dia - b.dia || a.hora - b.hora);
    const docs = new Set(filas.map((b) => b.docente_id)).size;
    document.getElementById("gen-conteo").textContent = `${filas.length} clases · ${docs} docentes`;
    document.getElementById("gen-tabla").innerHTML = filas.length
      ? `<table class="tabla-informe">
          <thead><tr><th>Docente</th><th>Nivel</th><th>Día</th><th>Hora</th><th>Grupo</th><th>Área</th></tr></thead>
          <tbody>${filas.map((b) => `<tr><td>${esc(b.docente_nombre)}</td><td>${nivelDeGrado(b.grado) === "primaria" ? "Primaria" : "Secundaria"}</td><td>${nombreDiaHorario(b.dia)}</td><td>${b.hora}ª</td><td>${etiquetaGrupoHorario(b.grado, b.curso)}</td><td>${esc(b.area_label)}</td></tr>`).join("")}</tbody>
        </table>`
      : hzVacio({ icono: "<i data-lucide=search class=ico></i> ", titulo: "Ninguna clase coincide con esos filtros", acciones: [{ id: "limpiar", texto: "Quitar filtros" }] });
    hzVincularAcciones(document.getElementById("gen-tabla"), {
      limpiar: () => { document.getElementById("gen-buscar").value = ""; document.getElementById("gen-area").value = ""; nivel = ""; cont.querySelectorAll('[data-hz-seg="gen-nivel"] .segmentado-btn').forEach((x, i) => x.classList.toggle("activo", i === 0)); pintar(); },
    });
  };
  const elegirArea = (tr) => {
    document.getElementById("gen-area").value = tr.dataset.area;
    pintar();
    document.getElementById("gen-detalle-titulo").scrollIntoView({ block: "start", behavior: "smooth" });
  };
  cont.querySelectorAll(".tabla-resumen-areas tbody tr").forEach((tr) => {
    tr.addEventListener("click", () => elegirArea(tr));
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") elegirArea(tr); });
  });
  document.getElementById("gen-buscar").addEventListener("input", pintar);
  document.getElementById("gen-area").addEventListener("change", pintar);
  hzVincularSeg(cont, "gen-nivel", (v) => { nivel = v; pintar(); });
  pintar();
  if (horarioGeneralFiltroArea) {
    document.getElementById("gen-detalle-titulo").scrollIntoView({ block: "start" });
    horarioGeneralFiltroArea = "";
  }
}

// ==========================================================================
//  ANÁLISIS · HORAS LIBRES (reporte de disponibilidad docente)
// ==========================================================================

let horasLibresDias = new Set([1, 2, 3, 4, 5]);
let horasLibresSoloConLibres = false;
let horasLibresFormato = "cuadro"; // cuadro = tabla por día | por_hora = una fila por franja

// P = primaria, S = secundaria, P·S = dicta en los dos niveles.
function nivelLibresHtml(niveles = []) {
  const t = niveles.length > 1 ? "P·S" : niveles[0] === "primaria" ? "P" : niveles[0] === "secundaria" ? "S" : "";
  return t ? ` <span class="hl-nivel" title="${niveles.join(" y ")}">${t}</span>` : "";
}

async function renderHorarioHorasLibres(cont, tok) {
  const r = await api(`/api/horario/horas-libres?anio_lectivo=${horarioAnio}`);
  if (!hzVigente(tok)) return;
  if (!r.docentes.length) {
    cont.innerHTML = `${hzTitulo("Reporte de disponibilidad docente")}${hzVacio({ icono: "<i data-lucide=inbox class=ico></i> ", titulo: `No hay horario cargado para ${horarioAnio}`, texto: "Cambia el año lectivo arriba." })}`;
    return;
  }
  const dias = DIAS_HORARIO.filter(([d]) => horasLibresDias.has(d));
  const totalLibres = r.docentes.reduce((n, d) => n + d.total_libres, 0);

  // Formato "una fila por hora": por día, cada franja con quiénes están libres
  // (en columnas, para que los nombres queden alineados).
  const tablaPorHora = ([dia, nombre]) => {
    const libresDia = r.docentes.reduce((n, d) => n + (d.libres_por_dia[dia] ?? 0), 0);
    return `
      <h3 class="titulo-dia-libres">${nombre} <span class="pendiente">(${libresDia} horas libres en total)</span></h3>
      <div class="tabla-scroll"><table class="tabla-horas-libres">
        <thead><tr><th class="col-doc">Hora</th><th>Libres</th><th class="col-doc">Docentes libres en esa hora</th></tr></thead>
        <tbody>
          ${r.franjas
            .map((f, i) => {
              const libres = r.docentes
                .filter((d) => !d.celdas[`${dia}-${f.hora}`])
                .map((d) => ({ nombre: d.nombre_completo, niveles: d.niveles || [] }))
                .sort((a, b) => a.nombre.localeCompare(b.nombre));
              return `<tr class="${i % 2 ? "par" : ""}">
                <td class="col-doc hl-franja">${f.hora}ª hora <span class="hl-hora">${f.inicio}–${f.fin}</span></td>
                <td class="tot hl-cuenta">${libres.length}</td>
                <td class="col-doc hl-nombres">${
                  libres.length
                    ? `<ul class="hl-lista">${libres.map((d) => `<li>${esc(d.nombre)}${nivelLibresHtml(d.niveles)}</li>`).join("")}</ul>`
                    : '<span class="hl-nadie">Ningún docente libre en esta hora</span>'
                }</td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table></div>`;
  };

  // Formato "cuadro por día": todos los docentes por las 6 franjas.
  const tablaDia = ([dia, nombre]) => {
    const docentes = horasLibresSoloConLibres ? r.docentes.filter((d) => (d.libres_por_dia[dia] ?? 0) > 0) : r.docentes;
    const libresDia = r.docentes.reduce((n, d) => n + (d.libres_por_dia[dia] ?? 0), 0);
    return `
      <h3 class="titulo-dia-libres">${nombre} <span class="pendiente">(${libresDia} horas libres · ${docentes.length} docentes)</span></h3>
      <div class="tabla-scroll"><table class="tabla-horas-libres">
        <thead><tr><th class="col-doc">Docente</th>
          ${r.franjas.map((f) => `<th>${f.hora}ª<br/><span class="hl-hora">${f.inicio}–${f.fin}</span></th>`).join("")}
          <th>Libres</th></tr></thead>
        <tbody>
          ${docentes
            .map(
              (d, i) => `<tr class="${i % 2 ? "par" : ""}">
                <td class="col-doc">${esc(d.nombre_completo)}${nivelLibresHtml(d.niveles)}</td>
                ${r.franjas.map((f) => { const t = d.celdas[`${dia}-${f.hora}`]; return t ? `<td>${esc(t)}</td>` : '<td class="hl-libre">LIBRE</td>'; }).join("")}
                <td class="tot">${d.libres_por_dia[dia] ?? 0}</td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table></div>`;
  };

  cont.innerHTML = `
    ${hzTitulo("Reporte de disponibilidad docente", "Qué dicta cada docente en cada hora y dónde está libre.")}
    <div class="hz-config no-imprimir">
      <div class="hz-config-campo"><span class="hz-config-etq">Días</span>
        <div class="hz-chips-check">${DIAS_HORARIO.map(([n, nombre]) => `<label class="hz-chip-check ${horasLibresDias.has(n) ? "activo" : ""}"><input type="checkbox" data-dia-libres="${n}" ${horasLibresDias.has(n) ? "checked" : ""} /> ${nombre}</label>`).join("")}</div>
      </div>
      <div class="hz-config-campo"><span class="hz-config-etq">Formato</span>
        ${hzSegmentado("libres-formato", [{ v: "cuadro", t: "Cuadro por día" }, { v: "por_hora", t: "Una fila por hora" }], horasLibresFormato)}
      </div>
      ${horasLibresFormato === "cuadro"
        ? `<label class="check-linea filtro-check"><input type="checkbox" id="check-solo-con-libres" ${horasLibresSoloConLibres ? "checked" : ""} /> Solo docentes con horas libres ese día</label>` : ""}
    </div>
    ${hzAccionesReporte({ pdf: true, imprimir: true, pdfTexto: "Descargar PDF (horizontal)" })}

    <div class="hoja-imprimir hz-hoja">
      <h2 style="margin:6px 0">Horas libres de los docentes — Sede #01 · ${horarioAnio}</h2>
      <p class="pendiente">${r.docentes.length} docentes con horario · ${totalLibres} horas libres a la semana ·
        LIBRE = esa franja no tiene clase asignada (no cuenta permisos ni ausencias del día) ·
        <span class="hl-nivel">P</span> primaria · <span class="hl-nivel">S</span> secundaria ·
        <span class="hl-nivel">P·S</span> los dos niveles.</p>
      ${dias.length ? dias.map(horasLibresFormato === "por_hora" ? tablaPorHora : tablaDia).join("") : hzVacio({ icono: "<i data-lucide=calendar class=ico></i> ", titulo: "Elige al menos un día", texto: "Marca los días que quieres ver en el reporte." })}
    </div>`;

  cont.querySelectorAll("[data-dia-libres]").forEach((chk) =>
    chk.addEventListener("change", () => {
      const dia = Number(chk.dataset.diaLibres);
      if (chk.checked) horasLibresDias.add(dia);
      else horasLibresDias.delete(dia);
      renderHorarioHorasLibres(cont, tok);
    })
  );
  document.getElementById("check-solo-con-libres")?.addEventListener("change", (e) => { horasLibresSoloConLibres = e.target.checked; renderHorarioHorasLibres(cont, tok); });
  hzVincularSeg(cont, "libres-formato", (v) => { horasLibresFormato = v; renderHorarioHorasLibres(cont, tok); });
  hzVincularAcciones2(cont, {
    imprimir: () => window.print(),
    pdf: async () => {
      if (!horasLibresDias.size) return horarioNotificar("Escoge al menos un día.", "warn");
      const params = new URLSearchParams({
        anio_lectivo: horarioAnio, dias: [...horasLibresDias].sort().join(","),
        solo_libres: horasLibresSoloConLibres, formato: horasLibresFormato,
      });
      try {
        await hzDescargarArchivo(`/api/horario/horas-libres.pdf?${params}`, { verEnPestana: true });
        horarioNotificar("Reporte generado: se abre el PDF en una pestaña nueva.");
      } catch (e) {
        horarioNotificar(`No se pudo generar el PDF: ${e.message}`, "error");
      }
    },
  });
}

// ==========================================================================
//  REPORTES · WORD (varios bloques: día + grado + horas)
// ==========================================================================
// Cada bloque genera, en el .docx con membrete oficial, una tabla por cada
// división activa del grado en la Sede #01 (11-1, 11-2, …) con una fila por
// hora (Hora · Docente · Materia). "Hoy" usa el día de la semana de la fecha
// elegida abajo. Precargado con el caso típico: mar 9°, mié 10°, jue 11° en
// 2ª–4ª, y hoy 8° en 4ª–6ª. El formato del Word NO cambia.

const DIAS_REPORTE = [
  ["lu", "Lunes"], ["ma", "Martes"], ["mi", "Miércoles"],
  ["ju", "Jueves"], ["vi", "Viernes"], ["hoy", "Hoy"],
];

let horarioReporteBloques = [
  { dia: "ma", grado: 9, horas: [2, 3, 4] },
  { dia: "mi", grado: 10, horas: [2, 3, 4] },
  { dia: "ju", grado: 11, horas: [2, 3, 4] },
  { dia: "hoy", grado: 8, horas: [4, 5, 6] },
];

function filaBloqueReporteHtml(bloque, i) {
  return `
    <article class="hz-bloque-rep" data-bloque-reporte="${i}">
      <header><strong>Bloque ${i + 1}</strong>
        <button type="button" class="boton-texto-chico rep-quitar hz-peligro" title="Quitar este bloque">Quitar</button></header>
      <div class="hz-bloque-campos">
        <label>Día
          <select class="rep-dia">${DIAS_REPORTE.map(([v, t]) => `<option value="${v}" ${v === bloque.dia ? "selected" : ""}>${t}</option>`).join("")}</select>
        </label>
        <label>Grado
          <select class="rep-grado">${NOMBRES_GRADOS.map(([g, t]) => `<option value="${g}" ${g === bloque.grado ? "selected" : ""}>${t} (${g})</option>`).join("")}</select>
        </label>
        <div class="rep-horas"><span class="hz-config-etq">Horas</span>
          <div class="hz-chips-check">${FRANJAS_HORARIO.map((f) => `<label class="hz-chip-check ${bloque.horas.includes(f.hora) ? "activo" : ""}" title="${f.inicio}–${f.fin}"><input type="checkbox" class="rep-hora-chk" value="${f.hora}" ${bloque.horas.includes(f.hora) ? "checked" : ""} /> ${f.hora}ª</label>`).join("")}</div>
        </div>
      </div>
    </article>`;
}

function renderHorarioReporte(cont) {
  const puede = puedeExportarHorario();
  // «Hoy» necesita un día de clases: si hoy es fin de semana se propone el
  // próximo día hábil (con «hoy» un sábado el servidor rechaza el reporte).
  const finde = [0, 6].includes(diaSemanaISO(horarioFecha));
  const fechaPropuesta = finde ? diaHabilCercano(horarioFecha, 1) : horarioFecha;
  cont.innerHTML = `
    ${hzTitulo("Configurar reporte Word", "Cada bloque genera una tabla por cada división activa del grado en la Sede #01, con una fila por hora (Hora · Docente · Materia). Si el grupo no tiene clase a esa hora, la fila dice «Sin clase».")}
    ${puede ? "" : hzVacio({ icono: "<i data-lucide=lock class=ico></i> ", titulo: "Tu rol no puede generar este reporte", texto: "Pídele a coordinación o secretaría que lo genere.", tono: "aviso" })}
    <div class="hz-config no-imprimir">
      <label class="hz-config-campo">Fecha para «Hoy»
        <input type="date" id="rep-fecha" value="${fechaPropuesta}" />
      </label>
      <span class="hz-nota">Los bloques con día «Hoy» usan el día de la semana de esta fecha.${finde ? " <strong>Hoy es fin de semana: se propone el próximo día de clases.</strong>" : ""}</span>
    </div>
    <div id="rep-cuerpo" class="hz-bloques-rep">
      ${horarioReporteBloques.length ? horarioReporteBloques.map((b, i) => filaBloqueReporteHtml(b, i)).join("")
        : hzVacio({ icono: "<i data-lucide=puzzle class=ico></i> ", titulo: "Todavía no hay bloques", texto: "Agrega un bloque (día + grado + horas) para armar el reporte." })}
    </div>
    <div class="hz-acciones-reporte no-imprimir">
      <span class="hz-acciones-titulo">Reporte</span>
      <button type="button" class="boton secundario" id="rep-agregar">＋ Agregar bloque</button>
      <button type="button" class="boton" id="rep-generar" ${puede ? "" : 'disabled title="Tu rol no puede exportar reportes de horario."'}>Generar Word</button>
      <span class="hz-acciones-ayuda">${horarioReporteBloques.length} bloque(s)</span>
    </div>
    <p id="rep-aviso" class="hz-nota hz-form-error" role="alert" hidden></p>
  `;

  const sincronizar = () => {
    horarioReporteBloques = [...cont.querySelectorAll("[data-bloque-reporte]")].map((art) => ({
      dia: art.querySelector(".rep-dia").value,
      grado: Number(art.querySelector(".rep-grado").value),
      horas: [...art.querySelectorAll(".rep-hora-chk:checked")].map((c) => Number(c.value)).sort((a, b) => a - b),
    }));
  };
  const cuerpo = cont.querySelector("#rep-cuerpo");
  cuerpo.addEventListener("change", (e) => {
    if (e.target.classList.contains("rep-hora-chk")) e.target.closest(".hz-chip-check").classList.toggle("activo", e.target.checked);
    sincronizar();
  });
  cuerpo.addEventListener("click", (e) => {
    if (!e.target.closest(".rep-quitar")) return;
    sincronizar();
    const i = Number(e.target.closest("[data-bloque-reporte]").dataset.bloqueReporte);
    horarioReporteBloques.splice(i, 1);
    renderHorarioReporte(cont);
  });
  cont.querySelector("#rep-agregar").addEventListener("click", () => {
    sincronizar();
    horarioReporteBloques.push({ dia: "ma", grado: 6, horas: [2, 3, 4] });
    renderHorarioReporte(cont);
    cont.querySelector("#rep-cuerpo").lastElementChild?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  });
  cont.querySelector("#rep-generar").addEventListener("click", async () => {
    sincronizar();
    const aviso = cont.querySelector("#rep-aviso");
    const rechazar = (texto) => { aviso.textContent = `${texto}`; aviso.hidden = false; };
    if (!horarioReporteBloques.length) return rechazar("Agrega al menos un bloque.");
    const sinHoras = horarioReporteBloques.findIndex((b) => !b.horas.length);
    if (sinHoras >= 0) {
      cont.querySelectorAll("[data-bloque-reporte]")[sinHoras].classList.add("con-error");
      return rechazar(`El bloque ${sinHoras + 1} necesita al menos una hora marcada.`);
    }
    const fecha = cont.querySelector("#rep-fecha").value || fechaHoyISO();
    if (horarioReporteBloques.some((b) => b.dia === "hoy") && [0, 6].includes(diaSemanaISO(fecha)))
      return rechazar("Hay bloques con día «Hoy» y esa fecha cae en fin de semana. Elige un día de clases en «Fecha para Hoy» o cambia el día del bloque.");
    aviso.hidden = true;
    cont.querySelectorAll(".con-error").forEach((x) => x.classList.remove("con-error"));
    const params = new URLSearchParams();
    params.set("anio_lectivo", horarioAnio);
    params.set("fecha", fecha);
    horarioReporteBloques.forEach((b) => params.append("b", `${b.dia}-${b.grado}-${b.horas.join("-")}`));
    // El formato del Word NO cambia: es el mismo endpoint y los mismos parámetros.
    // Solo cambia cómo se descarga (ver hzDescargarArchivo): con feedback en
    // pantalla en vez de una pestaña en blanco.
    const boton = cont.querySelector("#rep-generar");
    boton.disabled = true;
    boton.textContent = "Generando…";
    try {
      await hzDescargarArchivo(`/api/horario/reporte.docx?${params.toString()}`, { nombre: "Horario por grado.docx" });
      horarioNotificar(`Reporte generado: ${horarioReporteBloques.length} bloque(s). Se descarga como Word.`);
    } catch (e) {
      rechazar(e.message);
      horarioNotificar(`No se pudo generar el reporte: ${e.message}`, "error");
    } finally {
      boton.disabled = !puede;
      boton.textContent = "Generar Word";
    }
  });
}
