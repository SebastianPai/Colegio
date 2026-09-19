// --- Vista: Horarios --------------------------------------------------------
// Central administrativa del horario de la Sede #01: consulta rápida,
// "¿quién está libre ahora?", panel del día, ausencias y reemplazos.

const SECCIONES_HORARIO = [
  { id: "hoy", label: "Hoy" },
  { id: "libres", label: "Libres ahora" },
  { id: "docente", label: "Docente" },
  { id: "grupo", label: "Grupo" },
  { id: "asignar", label: "Abrir hueco" },
  { id: "dia", label: "Día" },
  { id: "reemplazos", label: "Reemplazos de hoy" },
  { id: "conflictos", label: "Conflictos" },
  { id: "general", label: "General" },
  { id: "horaslibres", label: "Horas libres" },
  { id: "reporte", label: "Reporte Word" },
];

let horarioAsignarSel = null; // {docenteId, docenteTexto, grado, curso, areaId, horas}

let horarioConflictosN = 0; // se actualiza en cada renderHorario

const DIAS_HORARIO = [
  [1, "Lunes"], [2, "Martes"], [3, "Miércoles"], [4, "Jueves"], [5, "Viernes"],
];

const FRANJAS_HORARIO = [
  { hora: 1, inicio: "7:30", fin: "8:25" },
  { hora: 2, inicio: "8:25", fin: "9:20" },
  { hora: 3, inicio: "9:20", fin: "10:15" },
  { hora: 4, inicio: "11:00", fin: "11:50" },
  { hora: 5, inicio: "11:50", fin: "12:40" },
  { hora: 6, inicio: "12:40", fin: "13:30" },
];

const ESTADO_HORARIO = {
  libre: { emoji: "🟢", texto: "Libre", clase: "est-libre" },
  en_clase: { emoji: "🔵", texto: "En clase", clase: "est-clase" },
  descanso: { emoji: "🟡", texto: "Descanso", clase: "est-descanso" },
  fuera_jornada: { emoji: "⚪", texto: "Fuera de jornada", clase: "est-fuera" },
  ausente: { emoji: "🔴", texto: "Ausente", clase: "est-ausente" },
  cubriendo: { emoji: "🟠", texto: "Cubriendo reemplazo", clase: "est-cubriendo" },
};

let horarioSub = "hoy";
let horarioAnio = new Date().getFullYear();
let horarioDocenteId = null;
let horarioGrupoSel = null; // {grado, curso}
let horarioDiaSel = new Date().getDay() >= 1 && new Date().getDay() <= 5 ? new Date().getDay() : 1;
let horarioRelojTimer = null;

function fechaHoyISO() {
  return fechaColombiaISO();
}

// Fecha del panel "Hoy" / "Reemplazos" — arranca en hoy pero se puede cambiar
// (p. ej. para preparar los reemplazos de mañana).
let horarioFecha = fechaHoyISO();

function sumarDiasISO(iso, n) {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d + n);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
}

function nombreDiaHorario(dia) {
  return (DIAS_HORARIO.find(([n]) => n === dia) || [0, "—"])[1];
}

// [1,2] -> "1ª–2ª" · [3] -> "3ª"
function rangoHoras(horas) {
  if (!horas || !horas.length) return "";
  return horas.length === 1
    ? `${horas[0]}ª`
    : `${horas[0]}ª–${horas[horas.length - 1]}ª`;
}

function etiquetaGrupoHorario(grado, curso) {
  return curso ? `${grado}-${curso}` : String(grado);
}

// --- Combo buscable (input + menú filtrado) para listas largas ------------
// items: [{ id, texto }]. Escribe un <input> visible + un <input type=hidden>
// con name=hiddenName que lleva el id elegido.

function comboBuscableHtml(inputId, { hiddenName = "", placeholder = "Escribe para buscar…", valorTexto = "", valorId = "" } = {}) {
  return `
    <div class="combo-buscable" data-combo="${inputId}">
      <input type="text" id="${inputId}" class="combo-input" placeholder="${placeholder}" autocomplete="off" value="${valorTexto}" />
      <input type="hidden" name="${hiddenName}" id="${inputId}-val" value="${valorId}" />
      <div id="${inputId}-menu" class="combo-menu" hidden></div>
    </div>`;
}

function vincularComboBuscable(inputId, items, onPick) {
  const input = document.getElementById(inputId);
  const hidden = document.getElementById(`${inputId}-val`);
  const menu = document.getElementById(`${inputId}-menu`);
  const norm = (s) => (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const pintar = () => {
    const nq = norm(input.value);
    const res = items.filter((it) => norm(it.texto).includes(nq)).slice(0, 50);
    menu.innerHTML = res.length
      ? res.map((it) => `<button type="button" class="combo-item" data-id="${it.id}">${it.texto}</button>`).join("")
      : `<div class="combo-vacio">Sin coincidencias</div>`;
    menu.hidden = false;
  };
  input.addEventListener("focus", pintar);
  input.addEventListener("input", () => {
    hidden.value = "";
    pintar();
  });
  menu.addEventListener("click", (e) => {
    const b = e.target.closest(".combo-item");
    if (!b) return;
    const it = items.find((x) => String(x.id) === b.dataset.id);
    hidden.value = it.id;
    input.value = it.texto;
    menu.hidden = true;
    onPick && onPick(it);
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(`[data-combo="${inputId}"]`)) menu.hidden = true;
  });
}

function limpiarRelojHorario() {
  if (horarioRelojTimer) {
    clearInterval(horarioRelojTimer);
    horarioRelojTimer = null;
  }
}

// --- Cabecera + navegación -------------------------------------------------

function encabezadoHorarioHtml() {
  return `
    <div class="pagina-header no-imprimir">
      <div>
        <h1>Horarios</h1>
        <p class="subtitulo-pagina">Consulta rápida, disponibilidad y reemplazos — Sede #01.</p>
      </div>
      <div class="modulo-periodo">
        <label class="filtro-campo">Año lectivo
          <input type="number" id="horario-anio" value="${horarioAnio}" />
        </label>
      </div>
    </div>
    <div class="buscador-horario no-imprimir">
      <input type="text" id="horario-buscar" placeholder="Buscar docente, grupo (8-1) o área…" autocomplete="off" />
      <div id="horario-buscar-resultados" class="buscador-horario-menu" hidden></div>
    </div>
    <nav class="subnav-modulo no-imprimir" aria-label="Secciones de Horarios">
      ${SECCIONES_HORARIO.map((s) => {
        const badge =
          s.id === "conflictos" && horarioConflictosN
            ? ` <span class="subnav-badge">${horarioConflictosN}</span>`
            : "";
        return `<button type="button" class="subnav-item ${horarioSub === s.id ? "activo" : ""}" data-seccion-horario="${s.id}">${s.label}${badge}</button>`;
      }).join("")}
    </nav>
  `;
}

function vincularEncabezadoHorario() {
  document.getElementById("horario-anio").addEventListener("change", (e) => {
    horarioAnio = Number(e.target.value) || horarioAnio;
    render();
  });
  document.querySelectorAll("[data-seccion-horario]").forEach((btn) => {
    btn.addEventListener("click", () => {
      horarioSub = btn.dataset.seccionHorario;
      render();
    });
  });
  vincularBuscadorHorario();
}

function vincularBuscadorHorario() {
  const input = document.getElementById("horario-buscar");
  const menu = document.getElementById("horario-buscar-resultados");
  if (!input) return;
  let t = null;
  input.addEventListener("input", () => {
    clearTimeout(t);
    const q = input.value.trim();
    if (q.length < 2) {
      menu.hidden = true;
      return;
    }
    t = setTimeout(async () => {
      const r = await api(`/api/horario/buscar?q=${encodeURIComponent(q)}&anio_lectivo=${horarioAnio}`);
      const filas = [];
      r.docentes.slice(0, 8).forEach((d) =>
        filas.push(
          `<button type="button" class="buscador-horario-item" data-tipo="docente" data-id="${d.id}">
             <span class="bh-tag">Docente</span> ${d.texto}${d.con_horario ? "" : ' <span class="bh-nota">(sin horario)</span>'}
           </button>`
        )
      );
      r.grupos.slice(0, 8).forEach((g) =>
        filas.push(
          `<button type="button" class="buscador-horario-item" data-tipo="grupo" data-grado="${g.grado}" data-curso="${g.curso ?? ""}">
             <span class="bh-tag">Grupo</span> ${g.texto} (${etiquetaGrupoHorario(g.grado, g.curso)})
           </button>`
        )
      );
      r.areas.slice(0, 8).forEach((a) =>
        filas.push(
          `<button type="button" class="buscador-horario-item" data-tipo="area" data-label="${(a.area_label || a.texto).replace(/"/g, "&quot;")}">
             <span class="bh-tag">Área</span> ${a.texto}
           </button>`
        )
      );
      menu.innerHTML = filas.join("") || `<div class="buscador-horario-vacio">Sin coincidencias</div>`;
      menu.hidden = false;
    }, 180);
  });

  menu.addEventListener("click", (e) => {
    const item = e.target.closest(".buscador-horario-item");
    if (!item) return;
    menu.hidden = true;
    input.value = "";
    if (item.dataset.tipo === "docente") {
      horarioDocenteId = Number(item.dataset.id);
      horarioSub = "docente";
    } else if (item.dataset.tipo === "grupo") {
      horarioGrupoSel = {
        grado: Number(item.dataset.grado),
        curso: item.dataset.curso === "" ? null : Number(item.dataset.curso),
      };
      horarioSub = "grupo";
    } else {
      horarioSub = "general";
      horarioGeneralFiltroArea = item.dataset.label;
    }
    render();
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".buscador-horario")) menu.hidden = true;
  });
}

async function renderHorario() {
  limpiarRelojHorario();
  app.innerHTML = `${encabezadoHorarioHtml()}<div id="horario-contenido" class="estado-carga">Cargando…</div><div id="horario-modal"></div>`;
  vincularEncabezadoHorario();

  // Contador de conflictos para el badge del subnav (no bloquea el render).
  api(`/api/horario/conflictos?anio_lectivo=${horarioAnio}`)
    .then((c) => {
      if (c.length !== horarioConflictosN) {
        horarioConflictosN = c.length;
        const nav = document.querySelector(".subnav-modulo [data-seccion-horario='conflictos']");
        if (nav && !nav.querySelector(".subnav-badge") && horarioConflictosN) {
          nav.insertAdjacentHTML("beforeend", ` <span class="subnav-badge">${horarioConflictosN}</span>`);
        }
      }
    })
    .catch(() => {});

  const cont = document.getElementById("horario-contenido");
  try {
    if (horarioSub === "hoy") return renderHorarioHoy(cont);
    if (horarioSub === "libres") return renderHorarioLibres(cont);
    if (horarioSub === "docente") return renderHorarioDocente(cont);
    if (horarioSub === "grupo") return renderHorarioGrupo(cont);
    if (horarioSub === "asignar") return renderHorarioAsignar(cont);
    if (horarioSub === "dia") return renderHorarioDia(cont);
    if (horarioSub === "reemplazos") return renderHorarioReemplazos(cont);
    if (horarioSub === "conflictos") return renderHorarioConflictos(cont);
    if (horarioSub === "general") return renderHorarioGeneral(cont);
    if (horarioSub === "horaslibres") return renderHorarioHorasLibres(cont);
    if (horarioSub === "reporte") return renderHorarioReporte(cont);
  } catch (e) {
    cont.innerHTML = `<div class="callout-boletines warn">${e.message}</div>`;
  }
}

// --- HORAS LIBRES (cuadro general de toda la planta) ---------------------
// Una tabla por día con TODOS los docentes: qué dicta cada hora y dónde
// está libre. Mismo contenido que el PDF horizontal con membrete.

let horasLibresDias = new Set([1, 2, 3, 4, 5]);
let horasLibresSoloConLibres = false;
let horasLibresFormato = "cuadro"; // cuadro = tabla por día | por_hora = una fila por franja

// P = primaria, S = secundaria, P·S = dicta en los dos niveles.
function nivelLibresHtml(niveles = []) {
  const t = niveles.length > 1 ? "P·S" : niveles[0] === "primaria" ? "P" : niveles[0] === "secundaria" ? "S" : "";
  return t ? ` <span class="hl-nivel" title="${niveles.join(" y ")}">${t}</span>` : "";
}

async function renderHorarioHorasLibres(cont) {
  const r = await api(`/api/horario/horas-libres?anio_lectivo=${horarioAnio}`);
  if (!r.docentes.length) {
    cont.innerHTML = `<div class="callout-boletines warn">No hay horario cargado para ${horarioAnio}.</div>`;
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
                    ? `<ul class="hl-lista">${libres
                        .map((d) => `<li>${esc(d.nombre)}${nivelLibresHtml(d.niveles)}</li>`)
                        .join("")}</ul>`
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
    const docentes = horasLibresSoloConLibres
      ? r.docentes.filter((d) => (d.libres_por_dia[dia] ?? 0) > 0)
      : r.docentes;
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
                ${r.franjas
                  .map((f) => {
                    const t = d.celdas[`${dia}-${f.hora}`];
                    return t ? `<td>${esc(t)}</td>` : '<td class="hl-libre">LIBRE</td>';
                  })
                  .join("")}
                <td class="tot">${d.libres_por_dia[dia] ?? 0}</td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table></div>`;
  };

  cont.innerHTML = `
    <div class="barra-filtros no-imprimir">
      <strong>Días:</strong>
      ${DIAS_HORARIO.map(
        ([n, nombre]) => `<label class="check-linea filtro-check"><input type="checkbox" data-dia-libres="${n}" ${
          horasLibresDias.has(n) ? "checked" : ""
        } /> ${nombre}</label>`
      ).join("")}

      <label class="filtro-campo">Formato
        <select id="select-formato-libres">
          <option value="cuadro" ${horasLibresFormato === "cuadro" ? "selected" : ""}>Cuadro por día (todas las horas)</option>
          <option value="por_hora" ${horasLibresFormato === "por_hora" ? "selected" : ""}>Una fila por hora (solo los libres)</option>
        </select>
      </label>
      ${
        horasLibresFormato === "cuadro"
          ? `<label class="check-linea filtro-check"><input type="checkbox" id="check-solo-con-libres" ${
              horasLibresSoloConLibres ? "checked" : ""
            } /> Solo docentes con horas libres ese día</label>`
          : ""
      }
      <button type="button" class="boton" id="btn-horas-libres-pdf">📄 Descargar PDF (horizontal)</button>
      <button type="button" class="boton secundario" onclick="window.print()">🖨 Imprimir</button>
    </div>

    <div class="hoja-imprimir">
      <h2 style="margin:6px 0">Horas libres de los docentes — Sede #01 · ${horarioAnio}</h2>
      <p class="pendiente">${r.docentes.length} docentes con horario · ${totalLibres} horas libres a la semana ·
        LIBRE = esa franja no tiene clase asignada (no cuenta permisos ni ausencias del día) ·
        <span class="hl-nivel">P</span> primaria · <span class="hl-nivel">S</span> secundaria ·
        <span class="hl-nivel">P·S</span> los dos niveles.</p>

      ${dias.map(horasLibresFormato === "por_hora" ? tablaPorHora : tablaDia).join("")}
    </div>
  `;

  cont.querySelectorAll("[data-dia-libres]").forEach((chk) =>
    chk.addEventListener("change", () => {
      const dia = Number(chk.dataset.diaLibres);
      if (chk.checked) horasLibresDias.add(dia);
      else horasLibresDias.delete(dia);
      renderHorarioHorasLibres(cont);
    })
  );
  document.getElementById("check-solo-con-libres")?.addEventListener("change", (e) => {
    horasLibresSoloConLibres = e.target.checked;
    renderHorarioHorasLibres(cont);
  });
  document.getElementById("select-formato-libres").addEventListener("change", (e) => {
    horasLibresFormato = e.target.value;
    renderHorarioHorasLibres(cont);
  });
  document.getElementById("btn-horas-libres-pdf").addEventListener("click", async () => {
    if (!horasLibresDias.size) return alert("Escoge al menos un día.");
    // La pestaña se abre dentro del clic (ver nota en el reporte Word).
    const ventana = window.open("", "_blank");
    await asegurarSesionFresca();
    const params = new URLSearchParams({
      anio_lectivo: horarioAnio,
      dias: [...horasLibresDias].sort().join(","),
      solo_libres: horasLibresSoloConLibres,
      formato: horasLibresFormato,
    });
    const url = `/api/horario/horas-libres.pdf?${params}`;
    if (ventana) ventana.location = url;
    else window.location.href = url;
  });
}

// --- CONFLICTOS (dos docentes para el mismo grupo+hora) ------------------

async function renderHorarioConflictos(cont) {
  const conflictos = await api(`/api/horario/conflictos?anio_lectivo=${horarioAnio}`);
  horarioConflictosN = conflictos.length;

  if (!conflictos.length) {
    cont.innerHTML = `<p class="conteo-resultados">✅ No hay conflictos por revisar. Todos los grupos tienen un solo docente confirmado por franja (o ya se aceptó dejar dos).</p>`;
    return;
  }

  cont.innerHTML = `
    <p class="callout-boletines warn">
      ${conflictos.length} grupo(s) tienen <strong>dos docentes a la misma hora</strong> según los
      archivos importados. Confirma cuál es el oficial (o deja los dos si de verdad la comparten).
      Hasta resolverlo, esas clases no cuentan para "libres" ni para reemplazos.
    </p>
    <div class="conflictos-lista">
      ${conflictos.map(tarjetaConflictoHtml).join("")}
    </div>
  `;
  cont.querySelectorAll(".conflicto-card").forEach(vincularTarjetaConflicto);
}

function tarjetaConflictoHtml(c, i) {
  const clave = `${c.grado}|${c.curso ?? ""}|${c.dia}|${c.hora}`;
  return `
    <div class="conflicto-card" data-clave="${clave}" data-idx="${i}">
      <div class="conflicto-cabecera">
        <strong>${c.grupo} · ${c.nombre_grupo}</strong>
        <span class="conteo-resultados">${c.dia_nombre} · ${c.hora}ª hora</span>
      </div>
      <div class="conflicto-opciones">
        ${c.opciones
          .map(
            (o) => `
          <label class="conflicto-opcion">
            <input type="radio" name="conf-${i}" value="${o.bloque_id}" />
            <span>
              <strong>${o.docente_nombre}</strong>
              <span class="conteo-resultados"> — ${o.area_label} · ${o.origen}</span>
            </span>
          </label>`
          )
          .join("")}
      </div>
      <div class="conflicto-acciones">
        <button type="button" class="boton" data-conf-oficial>Confirmar como oficial</button>
        <button type="button" class="boton secundario" data-conf-ambos>Dejar los dos</button>
        <span class="conflicto-resultado"></span>
      </div>
    </div>`;
}

function vincularTarjetaConflicto(card) {
  const [grado, curso, dia, hora] = card.dataset.clave.split("|");
  const cuerpo = {
    anio_lectivo: horarioAnio,
    grado: Number(grado),
    curso: curso === "" ? null : Number(curso),
    dia: Number(dia),
    hora: Number(hora),
  };
  const resultado = card.querySelector(".conflicto-resultado");

  const enviar = async (payload) => {
    try {
      await api("/api/horario/conflictos/resolver", {
        method: "POST",
        body: JSON.stringify({ ...cuerpo, ...payload }),
      });
      render();
    } catch (e) {
      resultado.textContent = e.message;
      resultado.className = "conflicto-resultado error";
    }
  };

  card.querySelector("[data-conf-oficial]").addEventListener("click", () => {
    const sel = card.querySelector("input[type=radio]:checked");
    if (!sel) {
      resultado.textContent = "Marca cuál docente es el oficial.";
      resultado.className = "conflicto-resultado error";
      return;
    }
    enviar({ accion: "oficial", bloque_id: Number(sel.value) });
  });
  card.querySelector("[data-conf-ambos]").addEventListener("click", () =>
    enviar({ accion: "ambos" })
  );
}

// --- HOY -----------------------------------------------------------------

async function renderHorarioHoy(cont) {
  const fecha = horarioFecha;
  const esHoy = fecha === fechaHoyISO();
  const panel = await api(`/api/horario/hoy?fecha=${fecha}`);

  const tarjeta = (emoji, n, txt, clase = "") =>
    `<div class="hoy-stat ${clase}"><span class="hoy-stat-num">${emoji} ${n}</span><span class="hoy-stat-txt">${txt}</span></div>`;

  const ausenciasHtml = panel.ausencias.length
    ? panel.ausencias
        .map((a) => {
          const clases = a.clases_afectadas
            .map((c) => {
              const cubierto = c.reemplazo_estado === "asignado";
              let accion;
              if (cubierto) {
                accion = `<span class="badge-estado ok">Cubre: ${c.reemplazo_docente}</span>`;
              } else if (c.conflicto) {
                const quienes = c.conflicto_opciones.map((o) => o.docente_nombre).join(" o ");
                accion = `<button type="button" class="boton secundario boton-chico" data-ir-conflictos title="${quienes}">⚠ Resolver conflicto primero</button>`;
              } else {
                accion = `<button type="button" class="boton secundario boton-chico" data-buscar-reemplazo="${c.bloque_horario_id}" data-fecha="${fecha}">Buscar reemplazo${c.horas.length > 1 ? " (bloque " + c.horas.length + "h)" : ""}</button>`;
              }
              return `<li class="clase-afectada ${cubierto ? "cubierta" : ""} ${c.conflicto ? "en-conflicto" : ""}">
                  <span>${rangoHoras(c.horas)} hora${c.horas.length > 1 ? "s" : ""} — ${etiquetaGrupoHorario(c.grado, c.curso)} — ${c.area_label}${c.reemplazo_estado === "parcial" ? ' <span class="badge-estado proceso">solo 1 hora cubierta</span>' : ""}</span>
                  ${accion}
                </li>`;
            })
            .join("");
          return `<div class="ausencia-card">
              <div class="ausencia-card-head">
                <strong>${ESTADO_HORARIO.ausente.emoji} ${a.docente_nombre}</strong>
                <span class="ausencia-motivo">${a.motivo || "Ausente"}</span>
                <button type="button" class="boton-texto-chico" data-borrar-ausencia="${a.id}">Quitar</button>
              </div>
              <ul class="clases-afectadas-lista">${clases || "<li>Sin clases ese día</li>"}</ul>
            </div>`;
        })
        .join("")
    : `<p class="conteo-resultados">Sin ausencias registradas para esta fecha.</p>`;

  cont.innerHTML = `
    <div class="panel-boletines">
      <div class="panel-tabla-header">
        <div class="fecha-nav">
          <button type="button" class="boton-icono" data-fecha-paso="-1" title="Día anterior">‹</button>
          <input type="date" id="hoy-fecha" value="${fecha}" />
          <button type="button" class="boton-icono" data-fecha-paso="1" title="Día siguiente">›</button>
          <strong>📅 ${panel.dia_nombre}${panel.dia ? "" : " (no hay clases)"}</strong>
          ${esHoy ? `<span class="badge-estado ok">hoy</span>` : `<button type="button" class="boton-texto-chico" id="btn-fecha-hoy">Ir a hoy</button>`}
        </div>
        <button type="button" class="boton" id="btn-registrar-ausencia">＋ Registrar ausencia</button>
      </div>
      <div class="hoy-stats">
        <div class="hoy-grupo">
          <span class="hoy-grupo-titulo">Docentes</span>
          ${tarjeta(ESTADO_HORARIO.libre.emoji, panel.docentes_libres, "libres")}
          ${tarjeta(ESTADO_HORARIO.en_clase.emoji, panel.docentes_en_clase, "en clase")}
          ${tarjeta(ESTADO_HORARIO.ausente.emoji, panel.docentes_ausentes, "ausentes", panel.docentes_ausentes ? "alerta" : "")}
          ${tarjeta(ESTADO_HORARIO.cubriendo.emoji, panel.docentes_cubriendo, "cubriendo")}
        </div>
        <div class="hoy-grupo">
          <span class="hoy-grupo-titulo">Clases</span>
          ${tarjeta("📚", panel.clases_programadas, "programadas")}
          ${tarjeta("⚠️", panel.clases_necesitan_reemplazo, "necesitan reemplazo", panel.clases_necesitan_reemplazo ? "alerta" : "")}
          ${
            panel.conflictos_pendientes
              ? `<button type="button" class="hoy-stat alerta hoy-stat-boton" data-ir-conflictos>
                   <span class="hoy-stat-num">⚠ ${panel.conflictos_pendientes}</span>
                   <span class="hoy-stat-txt">conflictos por revisar</span>
                 </button>`
              : ""
          }
        </div>
      </div>
    </div>

    <h3 class="subtitulo-seccion">Ausencias ${esHoy ? "de hoy" : "· " + fecha}</h3>
    ${ausenciasHtml}

    <h3 class="subtitulo-seccion">Reemplazos ${esHoy ? "de hoy" : "· " + fecha}</h3>
    ${tablaReemplazosHtml(panel.reemplazos)}
  `;

  const irAFecha = (f) => {
    horarioFecha = f;
    render();
  };
  document.getElementById("hoy-fecha").addEventListener("change", (e) => irAFecha(e.target.value || fechaHoyISO()));
  cont.querySelectorAll("[data-fecha-paso]").forEach((b) =>
    b.addEventListener("click", () => irAFecha(sumarDiasISO(fecha, Number(b.dataset.fechaPaso))))
  );
  document.getElementById("btn-fecha-hoy")?.addEventListener("click", () => irAFecha(fechaHoyISO()));
  document.getElementById("btn-registrar-ausencia").addEventListener("click", () => abrirModalAusencia(fecha));
  cont.querySelectorAll("[data-ir-conflictos]").forEach((b) =>
    b.addEventListener("click", () => {
      horarioSub = "conflictos";
      render();
    })
  );
  cont.querySelectorAll("[data-buscar-reemplazo]").forEach((b) =>
    b.addEventListener("click", () => abrirModalReemplazo(Number(b.dataset.buscarReemplazo), b.dataset.fecha))
  );
  cont.querySelectorAll("[data-borrar-ausencia]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("¿Quitar esta ausencia? Se cancelan sus reemplazos pendientes.")) return;
      await api(`/api/horario/ausencias/${b.dataset.borrarAusencia}`, { method: "DELETE" });
      render();
    })
  );
  vincularAccionesReemplazo(cont);
}

// --- LIBRES AHORA -------------------------------------------------------

let horarioLibresNivel = ""; // "" | "primaria" | "secundaria"

async function renderHorarioLibres(cont) {
  const fecha = fechaHoyISO();
  const ahora = await api("/api/horario/ahora");

  const dentro = ahora.estado === "en_franja";
  const selNivel = `
      <label>Nivel
        <select id="libres-nivel">
          <option value="" ${horarioLibresNivel === "" ? "selected" : ""}>Todos</option>
          <option value="primaria" ${horarioLibresNivel === "primaria" ? "selected" : ""}>Primaria</option>
          <option value="secundaria" ${horarioLibresNivel === "secundaria" ? "selected" : ""}>Secundaria</option>
        </select>
      </label>`;
  cont.innerHTML = `
    <div class="panel-boletines">
      <div class="reloj-ahora">
        <span class="reloj-hora" id="reloj-vivo">--:--</span>
        <span class="reloj-detalle">
          ${ahora.dia_nombre}
          ${dentro ? `· ${ahora.hora}ª hora (${ahora.franja.inicio}–${ahora.franja.fin})`
            : ahora.estado === "descanso" ? "· Descanso"
            : ahora.estado === "fin_de_semana" ? "" : "· Fuera de jornada"}
        </span>
      </div>
      <div class="toolbar" style="margin:8px 0 0">${selNivel}</div>
      <div id="libres-ahora-lista">
        ${dentro ? "<p class='estado-carga'>Cargando…</p>" : `<p class="conteo-resultados">No hay clase en este momento. Consulta una franja concreta abajo.</p>`}
      </div>
    </div>

    <h3 class="subtitulo-seccion">¿Quién está libre? — consulta por franja</h3>
    <div class="toolbar">
      <label>Día
        <select id="libres-dia">${DIAS_HORARIO.map(([n, t]) => `<option value="${n}" ${n === horarioDiaSel ? "selected" : ""}>${t}</option>`).join("")}</select>
      </label>
      <label>Desde la hora
        <select id="libres-hora">${FRANJAS_HORARIO.map((f) => `<option value="${f.hora}">${f.hora}ª (${f.inicio}–${f.fin})</option>`).join("")}</select>
      </label>
      <label>Hasta la hora
        <select id="libres-hora-fin">${FRANJAS_HORARIO.map((f) => `<option value="${f.hora}">${f.hora}ª (${f.inicio}–${f.fin})</option>`).join("")}</select>
      </label>
      <button type="button" class="boton secundario" id="btn-libres-consultar">Consultar</button>
    </div>
    <p class="conteo-resultados">Para un bloque de 2 horas (p. ej. 5ª y 6ª): "Desde 5ª · Hasta 6ª" → solo salen los que están libres las dos.</p>
    <div id="libres-consulta-lista"></div>
  `;

  let ultimaConsulta = null; // {dia, hora} para repintar al cambiar el nivel

  const pintarReloj = () => {
    const d = new Date();
    const el = document.getElementById("reloj-vivo");
    if (el) el.textContent = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  };
  pintarReloj();

  const cargarAhora = async () => {
    const cajaAhora = document.getElementById("libres-ahora-lista");
    if (!cajaAhora) return;
    const fr = await api("/api/horario/ahora");
    if (fr.estado !== "en_franja") {
      render();
      return;
    }
    const libres = await api(`/api/horario/libres?dia=${fr.dia}&hora=${fr.hora}&fecha=${fecha}&anio_lectivo=${horarioAnio}`);
    cajaAhora.innerHTML = listaLibresHtml(libres, `libres ahora (${fr.hora}ª hora)`, horarioLibresNivel);
  };
  if (dentro) cargarAhora();

  limpiarRelojHorario();
  horarioRelojTimer = setInterval(() => {
    pintarReloj();
    if (dentro) cargarAhora();
  }, 30000);

  const consultarFranja = async () => {
    const dia = Number(document.getElementById("libres-dia").value);
    let hora = Number(document.getElementById("libres-hora").value);
    let horaFin = Number(document.getElementById("libres-hora-fin").value);
    if (horaFin < hora) [hora, horaFin] = [horaFin, hora]; // por si los invierten
    horarioDiaSel = dia;
    ultimaConsulta = { dia, hora, horaFin };
    const libres = await api(
      `/api/horario/libres?dia=${dia}&hora=${hora}&hora_fin=${horaFin}&fecha=${fecha}&anio_lectivo=${horarioAnio}`
    );
    const franja = hora === horaFin ? `a la ${hora}ª hora` : `de la ${hora}ª a la ${horaFin}ª hora`;
    document.getElementById("libres-consulta-lista").innerHTML = listaLibresHtml(
      libres,
      `libres el ${nombreDiaHorario(dia)} ${franja}`,
      horarioLibresNivel
    );
  };
  document.getElementById("btn-libres-consultar").addEventListener("click", consultarFranja);
  // "Hasta" sigue a "Desde" si queda por debajo
  document.getElementById("libres-hora").addEventListener("change", (e) => {
    const fin = document.getElementById("libres-hora-fin");
    if (Number(fin.value) < Number(e.target.value)) fin.value = e.target.value;
  });
  document.getElementById("libres-nivel").addEventListener("change", (e) => {
    horarioLibresNivel = e.target.value;
    if (dentro) cargarAhora();
    if (ultimaConsulta) consultarFranja();
  });
}

// Lista de docentes libres. Sin filtro de nivel: se separa en Primaria y
// Secundaria (un docente que da en los dos aparece en ambos). Con filtro:
// solo ese nivel, en una lista.
function listaLibresHtml(libres, titulo, nivel) {
  const chip = (d) => `
    <button type="button" class="chip-docente" data-ver-docente="${d.docente_id}">
      ${ESTADO_HORARIO.libre.emoji} ${d.nombre_completo}
      ${d.niveles && d.niveles.length === 2 ? `<span class="chip-nivel">P·S</span>` : ""}
      <span class="chip-carga">${d.bloques_ese_dia} clases ese día</span>
    </button>`;

  if (nivel) {
    const f = libres.filter((d) => (d.niveles || []).includes(nivel));
    if (!f.length) return `<p class="conteo-resultados">Ningún docente de ${nivel} ${titulo}.</p>`;
    return `<p class="conteo-resultados">${f.length} docentes de ${nivel} ${titulo}</p>
      <div class="chips-docentes">${f.map(chip).join("")}</div>`;
  }

  if (!libres.length) return `<p class="conteo-resultados">Ningún docente ${titulo}.</p>`;
  const grupo = (n, etq) => {
    const f = libres.filter((d) => (d.niveles || []).includes(n));
    return `<h4 class="libres-nivel-titulo">${etq} — ${f.length}</h4>
      <div class="chips-docentes">${f.map(chip).join("") || "<span class='conteo-resultados'>ninguno</span>"}</div>`;
  };
  return `<p class="conteo-resultados">${libres.length} docentes ${titulo}</p>
    ${grupo("primaria", "Primaria")}
    ${grupo("secundaria", "Secundaria")}`;
}

// --- DOCENTE -----------------------------------------------------------

async function renderHorarioDocente(cont) {
  const docentes = await api("/api/docentes");

  const sel = docentes.find((d) => d.id === horarioDocenteId);
  cont.innerHTML = `
    <div class="toolbar">
      <label>Docente
        ${comboBuscableHtml("sel-docente-horario", {
          placeholder: "Escribe para buscar docente…",
          valorTexto: sel ? sel.nombre_completo : "",
          valorId: sel ? sel.id : "",
        })}
      </label>
      <label class="check-linea"><input type="checkbox" id="chk-solo-hoy-docente" /> Solo hoy</label>
    </div>
    <div id="horario-docente-cont"></div>
  `;

  const pintar = async () => {
    const caja = document.getElementById("horario-docente-cont");
    if (!horarioDocenteId) {
      caja.innerHTML = `<p class="conteo-resultados">Elige un docente para ver su horario semanal.</p>`;
      return;
    }
    caja.innerHTML = "<p class='estado-carga'>Cargando…</p>";
    const h = await api(`/api/horario/docente/${horarioDocenteId}?anio_lectivo=${horarioAnio}`);
    const soloHoy = document.getElementById("chk-solo-hoy-docente").checked;
    const hoyDia = new Date().getDay();
    caja.innerHTML = `
      <h3 class="subtitulo-seccion">${h.docente_nombre} · ${h.total_bloques} clases/semana</h3>
      ${
        soloHoy
          ? tablaHorarioDiaUnico(h, hoyDia >= 1 && hoyDia <= 5 ? hoyDia : 1)
          : tablaHorarioSemana(h)
      }`;
  };

  vincularComboBuscable(
    "sel-docente-horario",
    docentes.map((d) => ({ id: d.id, texto: d.nombre_completo })),
    (it) => {
      horarioDocenteId = it.id;
      pintar();
    }
  );
  document.getElementById("chk-solo-hoy-docente").addEventListener("change", pintar);
  pintar();
}

function celdaBloqueHtml(b) {
  if (!b) return `<td class="celda-libre">LIBRE</td>`;
  const descartado = b.estado === "descartado";
  const marca = b.en_conflicto
    ? ` <span class="marca-conflicto" title="Dos docentes para este grupo a esta hora — revisar en Conflictos">⚠</span>`
    : descartado
    ? ` <span class="marca-descartado" title="Descartado al resolver un conflicto">✕</span>`
    : "";
  return `<td class="celda-clase ${descartado ? "celda-descartada" : ""} ${b.en_conflicto ? "celda-conflicto" : ""}">
      <span class="celda-area">${b.area_label}${marca}</span>
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
      <table class="tabla-horario">
        <thead><tr><th>Hora</th>${DIAS_HORARIO.map(([, t]) => `<th>${t}</th>`).join("")}</tr></thead>
        <tbody>
          ${h.filas
            .map(
              (f) => `${f.hora === 4 ? filaRecesoHtml(5) : ""}<tr>
                <th class="col-hora">${f.hora}ª<span>${f.inicio}–${f.fin}</span></th>
                ${f.celdas.map(celdaBloqueHtml).join("")}
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
    .map((f) => {
      const b = f.celdas[idx];
      return `${f.hora === 4 ? filaRecesoHtml(1) : ""}<tr>
        <th class="col-hora">${f.hora}ª<span>${f.inicio}–${f.fin}</span></th>
        ${b ? `<td class="celda-clase"><span class="celda-area">${b.area_label}</span> <span class="celda-grupo">${etiquetaGrupoHorario(b.grado, b.curso)}</span></td>` : `<td class="celda-libre">LIBRE</td>`}
      </tr>`;
    })
    .join("");
  return `<p class="conteo-resultados">${nombreDiaHorario(dia)}</p>
    <div class="tabla-scroll"><table class="tabla-horario"><tbody>${filas}</tbody></table></div>`;
}

// --- GRUPO -----------------------------------------------------------

// Celda de la rejilla por grupo: área + docente (el grupo ya es fijo). Si hay
// dos bloques en la franja (conflicto sin resolver) se apilan los dos.
function celdaGrupoHtml(items) {
  if (!items || !items.length) return `<td class="celda-libre">LIBRE</td>`;
  const enConflicto = items.some((b) => b.en_conflicto);
  const cuerpo = items
    .map((b) => {
      const descartado = b.estado === "descartado";
      const marca = b.en_conflicto
        ? ` <span class="marca-conflicto" title="Dos docentes para este grupo a esta hora — revisar en Conflictos">⚠</span>`
        : descartado
        ? ` <span class="marca-descartado" title="Descartado al resolver un conflicto">✕</span>`
        : "";
      return `<span class="celda-area">${b.area_label}${marca}</span>
        <span class="celda-grupo">${b.docente_nombre}</span>`;
    })
    .join("");
  return `<td class="celda-clase ${items.every((b) => b.estado === "descartado") ? "celda-descartada" : ""} ${enConflicto ? "celda-conflicto" : ""}">${cuerpo}</td>`;
}

function tablaHorarioSemanaGrupo(bloques, dias, grado) {
  const slot = {};
  bloques.forEach((b) => ((slot[`${b.dia}-${b.hora}`] = slot[`${b.dia}-${b.hora}`] || []).push(b)));
  const esPrimaria = grado != null && grado <= 5;
  const tieneHora = (h) => bloques.some((b) => b.hora === h);
  // Preescolar (y cualquier grupo que no tenga 3ª hora ningún día) descansa
  // desde que termina la 2ª: el receso va 9:20–11:00 y no se pinta fila de 3ª.
  const recesoTemprano = !tieneHora(3);
  // Jornada que termina en la 5ª (12:40): 6ª = "Fin de clases".
  const finTrasQuinta = esPrimaria || !tieneHora(6);

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
        : dias.map((d) => celdaGrupoHtml(slot[`${d}-${f.hora}`])).join("");
    filas.push(`<tr>
      <th class="col-hora">${f.hora}ª<span>${f.inicio}–${f.fin}</span></th>
      ${celdas}
    </tr>`);
  }
  return `
    <div class="tabla-scroll">
      <table class="tabla-horario">
        <thead><tr><th>Hora</th>${dias.map((d) => `<th>${nombreDiaHorario(d)}</th>`).join("")}</tr></thead>
        <tbody>${filas.join("")}</tbody>
      </table>
    </div>`;
}

async function renderHorarioGrupo(cont) {
  const bloques = await api(`/api/horario/bloques?anio_lectivo=${horarioAnio}`);
  const grupos = [];
  bloques.forEach((b) => {
    const clave = `${b.grado}-${b.curso ?? ""}`;
    if (!grupos.some((g) => g.clave === clave))
      grupos.push({ clave, grado: b.grado, curso: b.curso, nombre: b.nombre_grupo });
  });
  grupos.sort((a, b) => a.grado - b.grado || (a.curso || 0) - (b.curso || 0));
  if (!horarioGrupoSel && grupos.length) horarioGrupoSel = { grado: grupos[0].grado, curso: grupos[0].curso };

  cont.innerHTML = `
    <div class="toolbar no-imprimir">
      <label>Grupo
        <select id="sel-grupo-horario">
          ${grupos
            .map(
              (g) =>
                `<option value="${g.grado}|${g.curso ?? ""}" ${
                  horarioGrupoSel && g.grado === horarioGrupoSel.grado && g.curso === horarioGrupoSel.curso ? "selected" : ""
                }>${etiquetaGrupoHorario(g.grado, g.curso)} · ${g.nombre}</option>`
            )
            .join("")}
        </select>
      </label>
      <label class="check-linea"><input type="checkbox" id="chk-solo-hoy-grupo" /> Solo hoy</label>
      <button type="button" class="boton secundario" onclick="window.print()">🖨 Imprimir / PDF</button>
    </div>
    <div id="horario-grupo-cont"></div>
  `;

  const pintar = async () => {
    const caja = document.getElementById("horario-grupo-cont");
    caja.innerHTML = "<p class='estado-carga'>Cargando…</p>";
    const soloHoy = document.getElementById("chk-solo-hoy-grupo").checked;
    const hoyDia = new Date().getDay();
    const finde = !(hoyDia >= 1 && hoyDia <= 5);
    const params = new URLSearchParams({ grado: horarioGrupoSel.grado, anio_lectivo: horarioAnio });
    if (horarioGrupoSel.curso != null) params.set("curso", horarioGrupoSel.curso);
    if (soloHoy && !finde) params.set("dia", hoyDia);
    const g = await api(`/api/horario/grupo?${params}`);

    const dias = soloHoy && !finde ? [hoyDia] : [1, 2, 3, 4, 5];
    const tituloDia = soloHoy && !finde ? ` — ${nombreDiaHorario(hoyDia)}` : "";

    caja.innerHTML = `
      <div class="hoja-imprimir">
        ${membreteHtml(`HORARIO — ${etiquetaGrupoHorario(g.grado, g.curso)} · ${g.nombre_grupo}${tituloDia} — Sede #01 · ${horarioAnio}`)}
        <p class="conteo-resultados">${g.total_estudiantes} estudiantes</p>
        ${tablaHorarioSemanaGrupo(g.bloques, dias, g.grado)}
      </div>
    `;
  };

  document.getElementById("sel-grupo-horario").addEventListener("change", (e) => {
    const [grado, curso] = e.target.value.split("|");
    horarioGrupoSel = { grado: Number(grado), curso: curso === "" ? null : Number(curso) };
    pintar();
  });
  document.getElementById("chk-solo-hoy-grupo").addEventListener("change", pintar);
  pintar();
}

// --- ABRIR HUECO / ASIGNAR CLASE NUEVA ---------------------------------

async function renderHorarioAsignar(cont) {
  const [docentes, areas, bloques] = await Promise.all([
    api("/api/docentes"),
    api("/api/areas"),
    api(`/api/horario/bloques?anio_lectivo=${horarioAnio}`),
  ]);
  const grupos = [];
  bloques.forEach((b) => {
    const clave = `${b.grado}|${b.curso ?? ""}`;
    if (!grupos.some((g) => g.clave === clave))
      grupos.push({ clave, grado: b.grado, curso: b.curso, nombre: b.nombre_grupo });
  });
  grupos.sort((a, b) => a.grado - b.grado || (a.curso || 0) - (b.curso || 0));
  const s = horarioAsignarSel || {};

  cont.innerHTML = `
    <p class="conteo-resultados">Elige el profesor, el grupo y la materia. Se recomienda dónde meter la clase <strong>sin dejar al profesor con doble clase</strong>. Si el grupo está lleno, se sugieren las franjas menos costosas de reacomodar (y se dice qué clase se movería).</p>
    <form id="form-asignar" class="form-grid" style="max-width:none">
      <label>Profesor
        ${comboBuscableHtml("asignar-docente", { hiddenName: "docente_id", placeholder: "Escribe para buscar…", valorTexto: s.docenteTexto || "", valorId: s.docenteId || "" })}
      </label>
      <label>Grupo
        <select name="grupo" id="asignar-grupo">
          ${grupos.map((g) => `<option value="${g.grado}|${g.curso ?? ""}" ${s.grado === g.grado && (s.curso ?? "") === (g.curso ?? "") ? "selected" : ""}>${etiquetaGrupoHorario(g.grado, g.curso)} · ${g.nombre}</option>`).join("")}
        </select>
      </label>
      <label>Materia (área)
        <select name="area_id" id="asignar-area">
          ${areas.map((a) => `<option value="${a.id}" ${String(s.areaId) === String(a.id) ? "selected" : ""}>${a.codigo} — ${a.nombre}</option>`).join("")}
        </select>
      </label>
      <label>Duración
        <select name="horas" id="asignar-horas">
          <option value="1" ${s.horas !== 2 ? "selected" : ""}>1 hora</option>
          <option value="2" ${s.horas === 2 ? "selected" : ""}>2 horas seguidas (bloque)</option>
        </select>
      </label>
      <label class="check-linea ancho-completo"><input type="checkbox" name="crear_asignacion" id="asignar-crear-asig" checked /> Registrar también la asignación (aparece en Boletines → Por docente)</label>
      <div class="ancho-completo"><button type="submit" class="boton">Ver dónde meterla</button></div>
    </form>
    <div id="asignar-resultado"></div>
  `;

  vincularComboBuscable(
    "asignar-docente",
    docentes.map((d) => ({ id: d.id, texto: d.nombre_completo }))
  );

  document.getElementById("form-asignar").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const docenteId = Number(fd.get("docente_id"));
    if (!docenteId) return alert("Elige un profesor de la lista.");
    const [grado, curso] = String(fd.get("grupo")).split("|");
    const areaId = Number(fd.get("area_id"));
    const horas = Number(fd.get("horas"));
    horarioAsignarSel = {
      docenteId,
      docenteTexto: document.getElementById("asignar-docente").value,
      grado: Number(grado),
      curso: curso === "" ? null : Number(curso),
      areaId,
      horas,
      crearAsig: document.getElementById("asignar-crear-asig").checked,
    };
    const box = document.getElementById("asignar-resultado");
    box.innerHTML = "<p class='estado-carga'>Analizando el horario…</p>";
    const p = new URLSearchParams({ docente_id: docenteId, grado, area_id: areaId, horas, anio_lectivo: horarioAnio });
    if (curso !== "") p.set("curso", curso);
    let r;
    try {
      r = await api(`/api/horario/huecos?${p}`);
    } catch (err) {
      box.innerHTML = `<div class="callout-boletines warn">${err.message}</div>`;
      return;
    }
    pintarHuecos(box, r);
  });
}

function rejillaGrupoHtml(ocupados) {
  const set = new Set(ocupados.map(([d, h]) => `${d}-${h}`));
  return `
    <div class="tabla-scroll">
      <table class="tabla-horario">
        <thead><tr><th>Hora</th>${DIAS_HORARIO.map(([, t]) => `<th>${t}</th>`).join("")}</tr></thead>
        <tbody>
          ${FRANJAS_HORARIO.map(
            (f) => `<tr><th class="col-hora">${f.hora}ª<span>${f.inicio}–${f.fin}</span></th>${DIAS_HORARIO.map(
              ([d]) => (set.has(`${d}-${f.hora}`) ? `<td class="celda-clase" style="text-align:center">ocupado</td>` : `<td class="celda-libre">LIBRE</td>`)
            ).join("")}</tr>`
          ).join("")}
        </tbody>
      </table>
    </div>`;
}

function pintarHuecos(box, r) {
  const medallas = ["🥇", "🥈", "🥉"];
  const tarjeta = (h, i) => {
    const razones = h.razones.map((z) => `<li class="razon ${z.tipo}">${z.tipo === "ok" ? "✓" : "⚠"} ${z.texto}</li>`).join("");
    const ids = h.ocupa.map((o) => o.bloque_id).join(",");
    const badge = h.libre
      ? `<span class="badge-estado ok">Franja libre</span>`
      : `<span class="badge-estado proceso">Hay que reacomodar ${h.ocupa.length} clase(s)</span>`;
    const rango = h.horas > 1 ? `${h.hora}ª–${h.hora_fin}ª` : `${h.hora}ª`;
    return `<div class="candidato-card">
        <div class="candidato-head">
          <span class="candidato-nombre">${medallas[i] || ""} ${h.nombre_dia} · ${rango} hora <span class="conteo-resultados">${h.franja}</span></span>
          <span class="candidato-pct">${h.puntaje}%</span>
        </div>
        <div class="barra-progreso"><div class="barra-progreso-relleno" style="width:${h.puntaje}%"></div></div>
        ${badge}
        <ul class="razones-lista">${razones}</ul>
        <button type="button" class="boton candidato-asignar" data-asignar-hueco="${h.dia}|${h.hora}|${h.horas}" data-desplazar="${ids}" data-libre="${h.libre ? 1 : 0}">
          ${h.libre ? "Asignar aquí" : "Asignar aquí (y quitar esas clases)"}
        </button>
      </div>`;
  };
  const s = horarioAsignarSel;
  box.innerHTML = `
    <h3 class="subtitulo-seccion">${r.docente_nombre} → ${r.area_label} · ${etiquetaGrupoHorario(r.grado, r.curso)}</h3>
    <p class="conteo-resultados">${r.total_libres} franja(s) libre(s) del grupo · ${r.huecos.length} ubicación(es) posible(s). ${r.horas > 1 ? "Bloque de 2 horas seguidas." : ""}</p>
    <details class="seccion-colapsable" style="margin-bottom:12px"><summary>Ver el horario actual de ${etiquetaGrupoHorario(r.grado, r.curso)}</summary>${rejillaGrupoHtml(r.ocupados)}</details>
    <div class="candidatos-grid">${r.huecos.length ? r.huecos.map(tarjeta).join("") : `<p class="callout-boletines warn">${r.docente_nombre} está ocupado en todas las franjas — no hay dónde meter la clase sin dejarle doble clase.</p>`}</div>
  `;
  box.querySelectorAll("[data-asignar-hueco]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const [dia, hora, horas] = btn.dataset.asignarHueco.split("|").map(Number);
      const desplazar = btn.dataset.desplazar ? btn.dataset.desplazar.split(",").map(Number) : [];
      const libre = btn.dataset.libre === "1";
      const conf = libre
        ? `¿Asignar ${s.docenteTexto} · ${r.area_label} a ${etiquetaGrupoHorario(r.grado, r.curso)} el ${nombreDiaHorario(dia)} ${hora}ª${horas > 1 ? "–" + (hora + horas - 1) + "ª" : ""} hora?`
        : `Se van a QUITAR ${desplazar.length} clase(s) de esa franja y poner en su lugar ${s.docenteTexto} · ${r.area_label}. ¿Continuar?`;
      if (!confirm(conf)) return;
      btn.disabled = true;
      try {
        await api("/api/horario/bloques", {
          method: "POST",
          body: JSON.stringify({
            anio_lectivo: horarioAnio,
            docente_id: s.docenteId,
            grado: r.grado,
            curso: r.curso,
            area_id: s.areaId,
            dia,
            hora,
            horas,
            crear_asignacion: s.crearAsig,
            desplazar_bloque_ids: desplazar,
          }),
        });
        alert("Listo. La clase quedó en el horario.");
        render();
      } catch (err) {
        alert(err.message);
        btn.disabled = false;
      }
    })
  );
}

// --- DÍA -----------------------------------------------------------

async function renderHorarioDia(cont) {
  cont.innerHTML = `
    <div class="toolbar">
      <label>Día
        <select id="sel-dia-horario">${DIAS_HORARIO.map(([n, t]) => `<option value="${n}" ${n === horarioDiaSel ? "selected" : ""}>${t}</option>`).join("")}</select>
      </label>
    </div>
    <div id="horario-dia-cont"></div>
  `;
  const pintar = async () => {
    const caja = document.getElementById("horario-dia-cont");
    caja.innerHTML = "<p class='estado-carga'>Cargando…</p>";
    const bloques = await api(`/api/horario/dia/${horarioDiaSel}?anio_lectivo=${horarioAnio}`);
    const porHora = {};
    bloques.forEach((b) => (porHora[b.hora] = porHora[b.hora] || []).push(b));
    caja.innerHTML = `
      <h3 class="subtitulo-seccion">${nombreDiaHorario(horarioDiaSel)} — ${bloques.length} clases</h3>
      ${FRANJAS_HORARIO.map((f) => {
        const items = (porHora[f.hora] || [])
          .sort((a, b) => a.grado - b.grado || (a.curso || 0) - (b.curso || 0))
          .map((b) => {
            const marca = b.en_conflicto
              ? ` <span class="marca-conflicto" title="Dos docentes — revisar en Conflictos">⚠</span>`
              : b.estado === "descartado"
              ? ` <span class="marca-descartado">✕</span>`
              : "";
            return `<li class="${b.estado === "descartado" ? "linea-descartada" : ""}">${etiquetaGrupoHorario(b.grado, b.curso)} · ${b.area_label} — ${b.docente_nombre}${marca}</li>`;
          })
          .join("");
        return `<div class="grupo-dia">
            <h4>${f.hora}ª hora <span class="conteo-resultados">${f.inicio}–${f.fin}</span></h4>
            <ul class="grupo-dia-lista cols">${items || "<li class='conteo-resultados'>Sin clases</li>"}</ul>
          </div>`;
      }).join("")}
    `;
  };
  document.getElementById("sel-dia-horario").addEventListener("change", (e) => {
    horarioDiaSel = Number(e.target.value);
    pintar();
  });
  pintar();
}

// --- REEMPLAZOS DE HOY -----------------------------------------------------

async function renderHorarioReemplazos(cont) {
  const fecha = horarioFecha;
  const reemplazos = await api(`/api/horario/reemplazos?fecha=${fecha}`);
  cont.innerHTML = `
    <div class="fecha-nav" style="margin:8px 0 16px">
      <button type="button" class="boton-icono" data-fecha-paso="-1" title="Día anterior">‹</button>
      <input type="date" id="reemp-fecha" value="${fecha}" />
      <button type="button" class="boton-icono" data-fecha-paso="1" title="Día siguiente">›</button>
      ${fecha === fechaHoyISO() ? `<span class="badge-estado ok">hoy</span>` : `<button type="button" class="boton-texto-chico" id="btn-reemp-hoy">Ir a hoy</button>`}
    </div>
    <h3 class="subtitulo-seccion">Reemplazos · ${nombreDiaHorario(new Date(fecha + "T00:00").getDay())} ${fecha}</h3>
    ${tablaReemplazosHtml(reemplazos)}
  `;
  const irAFecha = (f) => {
    horarioFecha = f;
    render();
  };
  document.getElementById("reemp-fecha").addEventListener("change", (e) => irAFecha(e.target.value || fechaHoyISO()));
  cont.querySelectorAll("[data-fecha-paso]").forEach((b) =>
    b.addEventListener("click", () => irAFecha(sumarDiasISO(fecha, Number(b.dataset.fechaPaso))))
  );
  document.getElementById("btn-reemp-hoy")?.addEventListener("click", () => irAFecha(fechaHoyISO()));
  vincularAccionesReemplazo(cont);
}

function tablaReemplazosHtml(reemplazos) {
  if (!reemplazos.length) return `<p class="conteo-resultados">Sin reemplazos para esta fecha.</p>`;
  const badge = { pendiente: "proceso", asignado: "ok", cancelado: "" };
  return `
    <div class="tabla-scroll">
      <table class="tabla-informe">
        <thead><tr>
          <th>Hora</th><th>Grupo</th><th>Área</th><th>Docente ausente</th><th>Reemplazante</th><th>%</th><th>Estado</th><th></th>
        </tr></thead>
        <tbody>
          ${reemplazos
            .map((r) => {
              const horas = r.horas && r.horas.length ? r.horas : [r.hora];
              const ids = (r.ids && r.ids.length ? r.ids : [r.id]).join(",");
              return `<tr class="${r.estado === "cancelado" ? "fila-cancelada" : ""}">
                <td>${rangoHoras(horas)}${horas.length > 1 ? " <span class='conteo-resultados'>(bloque)</span>" : ""}</td>
                <td>${etiquetaGrupoHorario(r.grado, r.curso)}</td>
                <td>${r.area_label}</td>
                <td>${r.docente_ausente}</td>
                <td>${r.docente_reemplazo || "—"}</td>
                <td>${r.compatibilidad != null ? r.compatibilidad + "%" : "—"}</td>
                <td><span class="badge-estado ${badge[r.estado] || ""}">${r.estado}</span></td>
                <td class="col-acciones">
                  ${
                    r.estado !== "cancelado" && r.bloque_horario_id
                      ? `<button type="button" class="boton-texto-chico" data-cambiar-reemplazo="${ids}" data-bloque="${r.bloque_horario_id}" data-fecha="${r.fecha}">Cambiar</button>`
                      : ""
                  }
                  ${
                    r.estado === "asignado"
                      ? `<button type="button" class="boton-texto-chico" data-cancelar-reemplazo="${ids}">Cancelar</button>`
                      : ""
                  }
                  ${
                    r.estado === "pendiente" && r.bloque_horario_id
                      ? `<button type="button" class="boton secundario boton-chico" data-buscar-reemplazo="${r.bloque_horario_id}" data-fecha="${r.fecha}">Buscar</button>`
                      : ""
                  }
                </td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function vincularAccionesReemplazo(scope) {
  scope.querySelectorAll("[data-buscar-reemplazo]").forEach((b) =>
    b.addEventListener("click", () => abrirModalReemplazo(Number(b.dataset.buscarReemplazo), b.dataset.fecha))
  );
  scope.querySelectorAll("[data-cambiar-reemplazo]").forEach((b) =>
    b.addEventListener("click", () =>
      abrirModalReemplazo(Number(b.dataset.bloque), b.dataset.fecha, b.dataset.cambiarReemplazo)
    )
  );
  scope.querySelectorAll("[data-cancelar-reemplazo]").forEach((b) =>
    b.addEventListener("click", async () => {
      const ids = b.dataset.cancelarReemplazo.split(",");
      if (!confirm(`¿Cancelar ${ids.length > 1 ? "este bloque (" + ids.length + " horas)" : "este reemplazo"}?`)) return;
      for (const id of ids) {
        await api(`/api/horario/reemplazos/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ estado: "cancelado" }),
        });
      }
      render();
    })
  );
}

// --- GENERAL ---------------------------------------------------------

let horarioGeneralFiltroArea = "";

// Primaria = Preescolar + 1° a 5° (grado 0-5). Secundaria/media = 6° a 11°.
function nivelDeGrado(grado) {
  return grado <= 5 ? "primaria" : "secundaria";
}

async function renderHorarioGeneral(cont) {
  const bloques = (await api(`/api/horario/bloques?anio_lectivo=${horarioAnio}`)).filter(
    (b) => b.estado === "activo"
  );
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
      label,
      nombre: r.nombre,
      pd: r.primaria.docentes.size,
      pc: r.primaria.clases,
      sd: r.secundaria.docentes.size,
      sc: r.secundaria.clases,
      // "General": docentes distintos en total (uno que da en los dos niveles
      // cuenta una vez) y total de clases.
      td: new Set([...r.primaria.docentes, ...r.secundaria.docentes]).size,
      tc: r.primaria.clases + r.secundaria.clases,
    }))
    .sort((a, b) => b.td - a.td || b.tc - a.tc);

  cont.innerHTML = `
    <h3 class="subtitulo-seccion">Resumen por área</h3>
    <p class="conteo-resultados">Primaria = Preescolar y 1°–5° · Secundaria = 6°–11°. "Docentes" = cuántos la dictan; en General, uno que da en los dos niveles cuenta una sola vez.</p>
    <div class="tabla-scroll">
      <table class="tabla-informe tabla-resumen-areas">
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
              (a) => `<tr data-area="${a.label.replace(/"/g, "&quot;")}">
                <td><strong>${a.label}</strong>${a.nombre ? `<span class="conteo-resultados"> · ${a.nombre}</span>` : ""}</td>
                <td>${a.pd || "—"}</td><td>${a.pc || "—"}</td>
                <td>${a.sd || "—"}</td><td>${a.sc || "—"}</td>
                <td class="col-general"><strong>${a.td}</strong></td><td class="col-general">${a.tc}</td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>

    <h3 class="subtitulo-seccion">Detalle</h3>
    <div class="toolbar">
      <input type="text" id="gen-buscar" placeholder="Filtrar por docente o grupo…" />
      <label>Nivel
        <select id="gen-nivel">
          <option value="">Todos</option>
          <option value="primaria">Primaria</option>
          <option value="secundaria">Secundaria</option>
        </select>
      </label>
      <label>Área
        <select id="gen-area">
          <option value="">Todas</option>
          ${areas.map((a) => `<option value="${a}" ${a === horarioGeneralFiltroArea ? "selected" : ""}>${a}</option>`).join("")}
        </select>
      </label>
      <span class="conteo-resultados" id="gen-conteo"></span>
    </div>
    <div class="tabla-scroll tabla-scroll-alto" id="gen-tabla"></div>
  `;

  const pintar = () => {
    const q = document.getElementById("gen-buscar").value.trim().toLowerCase();
    const area = document.getElementById("gen-area").value;
    const nivel = document.getElementById("gen-nivel").value;
    const filas = bloques
      .filter((b) => !area || b.area_label === area)
      .filter((b) => !nivel || nivelDeGrado(b.grado) === nivel)
      .filter(
        (b) =>
          !q ||
          b.docente_nombre.toLowerCase().includes(q) ||
          etiquetaGrupoHorario(b.grado, b.curso).includes(q) ||
          b.nombre_grupo.toLowerCase().includes(q)
      )
      .sort(
        (a, b) =>
          a.docente_nombre.localeCompare(b.docente_nombre) || a.dia - b.dia || a.hora - b.hora
      );
    const docs = new Set(filas.map((b) => b.docente_id)).size;
    document.getElementById("gen-conteo").textContent = `${filas.length} clases · ${docs} docentes`;
    document.getElementById("gen-tabla").innerHTML = `
      <table class="tabla-informe">
        <thead><tr><th>Docente</th><th>Nivel</th><th>Día</th><th>Hora</th><th>Grupo</th><th>Área</th></tr></thead>
        <tbody>
          ${filas
            .map(
              (b) =>
                `<tr><td>${b.docente_nombre}</td><td>${nivelDeGrado(b.grado) === "primaria" ? "Primaria" : "Secundaria"}</td><td>${nombreDiaHorario(
                  b.dia
                )}</td><td>${b.hora}ª</td><td>${etiquetaGrupoHorario(b.grado, b.curso)}</td><td>${b.area_label}</td></tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  };

  cont.querySelectorAll(".tabla-resumen-areas tbody tr").forEach((tr) =>
    tr.addEventListener("click", () => {
      document.getElementById("gen-area").value = tr.dataset.area;
      pintar();
      document.getElementById("gen-tabla").scrollIntoView({ block: "nearest", behavior: "smooth" });
    })
  );
  document.getElementById("gen-buscar").addEventListener("input", pintar);
  document.getElementById("gen-area").addEventListener("change", pintar);
  document.getElementById("gen-nivel").addEventListener("change", pintar);
  pintar();
  horarioGeneralFiltroArea = "";
}

// --- Modales: ausencia y reemplazo --------------------------------------

async function abrirModalAusencia(fecha) {
  const docentes = await api("/api/docentes");
  const cont = document.getElementById("horario-modal");
  cont.innerHTML = `
    <div class="modal-fondo">
      <div class="modal-caja">
        <h3 style="margin-top:0">Registrar ausencia</h3>
        <form id="form-ausencia" class="form-vertical">
          <label>Docente
            ${comboBuscableHtml("ausencia-docente", {
              hiddenName: "docente_id",
              placeholder: "Escribe para buscar docente…",
            })}
          </label>
          <label>Fecha
            <input type="date" name="fecha" value="${fecha}" required />
          </label>
          <label>Motivo (opcional)
            <input type="text" name="motivo" placeholder="Cita médica, permiso…" />
          </label>
          <div class="modal-acciones">
            <button type="button" class="boton secundario" id="btn-cancelar-ausencia">Cancelar</button>
            <button type="submit" class="boton">Registrar y ver clases afectadas</button>
          </div>
        </form>
      </div>
    </div>`;
  const cerrar = () => (cont.innerHTML = "");
  document.getElementById("btn-cancelar-ausencia").addEventListener("click", cerrar);
  cont.querySelector(".modal-fondo").addEventListener("click", (e) => {
    if (e.target.classList.contains("modal-fondo")) cerrar();
  });
  vincularComboBuscable(
    "ausencia-docente",
    docentes.map((d) => ({ id: d.id, texto: d.nombre_completo }))
  );
  document.getElementById("form-ausencia").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const docenteId = Number(fd.get("docente_id"));
    if (!docenteId) {
      alert("Elige un docente de la lista.");
      return;
    }
    const fechaAusencia = fd.get("fecha");
    try {
      const res = await api("/api/horario/ausencias", {
        method: "POST",
        body: JSON.stringify({
          docente_id: docenteId,
          fecha: fechaAusencia,
          motivo: fd.get("motivo") || null,
        }),
      });
      cerrar();
      horarioFecha = fechaAusencia; // el panel salta a la fecha de la ausencia
      horarioSub = "hoy";
      render();
      if (!res.clases_afectadas.length) {
        alert(
          `Ausencia registrada, pero ${res.docente_nombre} no tiene clases en el horario ese día ` +
            `(${fechaAusencia}), así que no hay reemplazos que buscar.`
        );
      }
    } catch (err) {
      alert(err.message);
    }
  });
}

async function abrirModalReemplazo(bloqueId, fecha, reemplazoId = null) {
  const cont = document.getElementById("horario-modal");
  cont.innerHTML = `<div class="modal-fondo"><div class="modal-caja modal-caja-ancha"><p>Analizando candidatos…</p></div></div>`;
  let data;
  try {
    data = await api(`/api/horario/reemplazos/candidatos?bloque_id=${bloqueId}&fecha=${fecha}`);
  } catch (e) {
    cont.innerHTML = `<div class="modal-fondo"><div class="modal-caja"><p class="callout-boletines warn">${e.message}</p><div class="modal-acciones"><button class="boton" id="x">Cerrar</button></div></div></div>`;
    document.getElementById("x").addEventListener("click", () => (cont.innerHTML = ""));
    return;
  }

  const b = data.bloque;
  const horas = data.horas && data.horas.length ? data.horas : [b.hora];
  const esDoble = horas.length > 1;
  const medallas = ["🥇", "🥈", "🥉"];

  const tarjeta = (c, i) => {
    const razones = c.razones
      .map((r) => `<li class="razon ${r.tipo}">${r.tipo === "ok" ? "✓" : "⚠"} ${r.texto}</li>`)
      .join("");
    const cobertura = esDoble
      ? c.cubre_bloque_completo
        ? `<span class="badge-estado ok">✓ Cubre las ${c.horas_total} horas</span>`
        : `<span class="badge-estado proceso">Solo ${c.horas_libres} de ${c.horas_total} horas</span>`
      : "";
    return `<div class="candidato-card ${esDoble && !c.cubre_bloque_completo ? "candidato-parcial" : ""}" data-completo="${c.cubre_bloque_completo ? 1 : 0}">
        <div class="candidato-head">
          <span class="candidato-nombre">${medallas[i] || ""} ${c.nombre_completo}</span>
          <span class="candidato-pct">${c.porcentaje}%</span>
        </div>
        <div class="barra-progreso"><div class="barra-progreso-relleno" style="width:${c.porcentaje}%"></div></div>
        ${cobertura}
        <ul class="razones-lista">${razones}</ul>
        <button type="button" class="boton candidato-asignar" data-asignar="${c.docente_id}">Asignar</button>
      </div>`;
  };
  const tarjetas = data.candidatos.length
    ? data.candidatos.map(tarjeta).join("")
    : `<p class="callout-boletines warn">No hay docentes disponibles sin conflicto para esta franja.</p>`;

  cont.innerHTML = `
    <div class="modal-fondo">
      <div class="modal-caja modal-caja-ancha">
        <div class="panel-tabla-header">
          <h3 style="margin:0">${etiquetaGrupoHorario(b.grado, b.curso)} · ${b.area_label} · ${rangoHoras(horas)} hora${esDoble ? "s" : ""}</h3>
          <button type="button" class="boton-texto-chico" id="btn-cerrar-reemplazo">Cerrar</button>
        </div>
        <p class="conteo-resultados">
          ${nombreDiaHorario(b.dia)} ${fecha} · ${data.nivel || nivelDeGrado(b.grado)} — buscando quién cubre a ${b.docente_nombre}
          ${esDoble ? "<br><strong>Bloque de " + horas.length + " horas seguidas.</strong> Se prioriza a quien esté libre las " + horas.length + "." : ""}
        </p>
        ${esDoble ? `<label class="check-linea" style="margin-bottom:10px"><input type="checkbox" id="chk-solo-completo" /> Mostrar solo los que cubren el bloque completo</label>` : ""}
        <div class="candidatos-grid" id="candidatos-grid">${tarjetas}</div>
      </div>
    </div>`;

  const cerrar = () => (cont.innerHTML = "");
  document.getElementById("btn-cerrar-reemplazo").addEventListener("click", cerrar);
  cont.querySelector(".modal-fondo").addEventListener("click", (e) => {
    if (e.target.classList.contains("modal-fondo")) cerrar();
  });
  document.getElementById("chk-solo-completo")?.addEventListener("change", (e) => {
    cont.querySelectorAll("#candidatos-grid .candidato-card").forEach((card) => {
      card.hidden = e.target.checked && card.dataset.completo !== "1";
    });
  });
  cont.querySelectorAll("[data-asignar]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      const did = Number(btn.dataset.asignar);
      try {
        if (reemplazoId) {
          // "Cambiar": re-asigna cada hora del bloque al nuevo reemplazante.
          for (const id of String(reemplazoId).split(",")) {
            await api(`/api/horario/reemplazos/${id}`, {
              method: "PATCH",
              body: JSON.stringify({ docente_reemplazo_id: did }),
            });
          }
        } else {
          await api("/api/horario/reemplazos", {
            method: "POST",
            body: JSON.stringify({ bloque_horario_id: bloqueId, fecha, docente_reemplazo_id: did }),
          });
        }
        cerrar();
        render();
      } catch (err) {
        alert(err.message);
        btn.disabled = false;
      }
    })
  );
}

// Delegación: chips "ver docente" en Libres ahora.
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-ver-docente]");
  if (!b || vistaActual !== "horario") return;
  horarioDocenteId = Number(b.dataset.verDocente);
  horarioSub = "docente";
  render();
});

// --- REPORTE WORD (varios bloques: día + grado + horas) -----------------
// Cada bloque genera, en el .docx con membrete oficial, una tabla por cada
// división activa del grado en la Sede #01 (11-1, 11-2, …) con una fila por
// hora (Hora · Docente · Materia). "Hoy" usa el día de la semana de la fecha
// elegida abajo. Precargado con el caso típico: mar 9°, mié 10°, jue 11° en
// 2ª–4ª, y hoy 8° en 4ª–6ª.

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
    <tr data-bloque-reporte="${i}">
      <td>
        <select class="rep-dia">
          ${DIAS_REPORTE.map(([v, t]) => `<option value="${v}" ${v === bloque.dia ? "selected" : ""}>${t}</option>`).join("")}
        </select>
      </td>
      <td>
        <select class="rep-grado">
          ${NOMBRES_GRADOS.map(([g, t]) => `<option value="${g}" ${g === bloque.grado ? "selected" : ""}>${t} (${g})</option>`).join("")}
        </select>
      </td>
      <td class="rep-horas">
        ${FRANJAS_HORARIO.map(
          (f) => `<label class="rep-hora"><input type="checkbox" class="rep-hora-chk" value="${f.hora}" ${bloque.horas.includes(f.hora) ? "checked" : ""} /> ${f.hora}ª</label>`
        ).join("")}
      </td>
      <td><button type="button" class="boton secundario boton-chico rep-quitar" title="Quitar bloque">✕</button></td>
    </tr>`;
}

function renderHorarioReporte(cont) {
  cont.innerHTML = `
    <p class="conteo-resultados">
      Cada bloque = un día + un grado + las horas marcadas. En el Word sale una tabla por cada
      división activa del grado en la Sede #01 (11-1, 11-2, …), con una fila por hora
      (Hora · Docente · Materia). Si el grupo no tiene clase a esa hora, la fila dice "Sin clase".
    </p>
    <div class="toolbar">
      <label class="filtro-campo">Fecha para "Hoy"
        <input type="date" id="rep-fecha" value="${horarioFecha}" />
      </label>
    </div>
    <table class="tabla-informe">
      <thead>
        <tr><th>Día</th><th>Grado</th><th>Horas</th><th></th></tr>
      </thead>
      <tbody id="rep-cuerpo">
        ${horarioReporteBloques.map((b, i) => filaBloqueReporteHtml(b, i)).join("")}
      </tbody>
    </table>
    <div class="toolbar">
      <button type="button" class="boton secundario" id="rep-agregar">＋ Agregar bloque</button>
      <button type="button" class="boton" id="rep-generar">⬇ Generar Word</button>
    </div>
    <p id="rep-aviso" class="callout-boletines warn" hidden></p>
  `;

  const sincronizar = () => {
    horarioReporteBloques = [...cont.querySelectorAll("[data-bloque-reporte]")].map((tr) => ({
      dia: tr.querySelector(".rep-dia").value,
      grado: Number(tr.querySelector(".rep-grado").value),
      horas: [...tr.querySelectorAll(".rep-hora-chk:checked")].map((c) => Number(c.value)).sort((a, b) => a - b),
    }));
  };

  cont.querySelector("#rep-cuerpo").addEventListener("change", sincronizar);
  cont.querySelector("#rep-cuerpo").addEventListener("click", (e) => {
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
  });
  cont.querySelector("#rep-generar").addEventListener("click", async () => {
    sincronizar();
    const aviso = cont.querySelector("#rep-aviso");
    if (!horarioReporteBloques.length) {
      aviso.textContent = "Agrega al menos un bloque.";
      aviso.hidden = false;
      return;
    }
    if (horarioReporteBloques.some((b) => !b.horas.length)) {
      aviso.textContent = "Cada bloque necesita al menos una hora marcada.";
      aviso.hidden = false;
      return;
    }
    aviso.hidden = true;
    const fecha = cont.querySelector("#rep-fecha").value || fechaHoyISO();
    const params = new URLSearchParams();
    params.set("anio_lectivo", horarioAnio);
    params.set("fecha", fecha);
    horarioReporteBloques.forEach((b) =>
      params.append("b", `${b.dia}-${b.grado}-${b.horas.join("-")}`)
    );
    // Pestaña aparte: la respuesta es Content-Disposition: attachment, así que
    // el navegador baja el .docx y la pestaña en blanco se cierra sola.
    //
    // Fase 4A': la pestaña se abre YA, dentro del clic y sin esperar nada —
    // si se abriera después del await, el bloqueador de elementos emergentes
    // la cortaría por no venir de un gesto del usuario. La URL se le pone
    // después, con la sesión ya renovada si hacía falta.
    const ventana = window.open("", "_blank");
    await asegurarSesionFresca();
    const url = `/api/horario/reporte.docx?${params.toString()}`;
    if (ventana) ventana.location = url;
    else window.location.href = url; // si aun así la bloquearon, se baja en esta pestaña
  });
}
