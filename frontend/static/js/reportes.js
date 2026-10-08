// --- Vista: Reportes (resumen institucional + Conciliación SIMAC ↔ SAPRED) --
// Módulo con navegación interna propia, mismo patrón que Boletines/Notas:
// Resumen (lo que ya existía) | Conciliación (nuevo).

let seccionReportes = "resumen"; // resumen | lista | conciliacion

const SECCIONES_REPORTES = [
  { id: "resumen", label: "Resumen" },
  { id: "lista", label: "Lista de estudiantes" },
  { id: "docentes", label: "Lista de docentes" },
  { id: "conciliacion", label: "Conciliación SIMAC <i data-lucide=arrow-left-right class=ico></i> SAPRED" },
];

async function renderReportes() {
  app.innerHTML = `
    <div class="pagina-header">
      <div>
        <h1>Reportes</h1>
        <p class="subtitulo-pagina">Indicadores institucionales y conciliación entre sistemas.</p>
      </div>
    </div>
    <nav class="subnav-modulo" aria-label="Secciones de Reportes">
      ${SECCIONES_REPORTES.map(
        (s) => `<button type="button" class="subnav-item ${seccionReportes === s.id ? "activo" : ""}" data-seccion-reportes="${s.id}">${s.label}</button>`
      ).join("")}
    </nav>
    <div id="contenido-reportes" class="estado-carga">Cargando...</div>
  `;
  document.querySelectorAll("[data-seccion-reportes]").forEach((btn) => {
    btn.addEventListener("click", () => {
      seccionReportes = btn.dataset.seccionReportes;
      render();
    });
  });

  if (seccionReportes === "conciliacion") return renderSeccionConciliacion();
  if (seccionReportes === "lista") return renderSeccionListaCupo();
  if (seccionReportes === "docentes") return renderSeccionListaDocentes();
  return renderSeccionResumenInstitucional();
}

// --- Sección: Lista de estudiantes (desde Preescolar hasta N niños) --------
// Recorre la matrícula en orden grado → grupo → apellido empezando en el
// grado elegido (Preescolar por defecto) y toma estudiantes hasta completar
// la cantidad pedida. Los marcados "posible retiro" o "retirado" NO entran en
// la lista; cada marca tiene su propia vista para poder quitarla. "Retirado"
// es solo una marca: el estudiante sigue ACTIVO en el sistema y en la grilla.

let listaCupoSede = ""; // "" = todas las sedes IETABA
let listaCupoCantidad = 200;
let listaCupoSinLimite = false; // true = todos los que cumplan, sin cupo
let listaCupoDesdeGrado = 0;
let listaCupoHastaGrado = 11;
let listaCupoGrupos = new Set(); // "grado:curso" escogidos a mano; vacío = todo el rango
let listaCupoIncluir = { posibles: false, retirados: false, sinGrupo: false };
let listaCupoVista = "activos"; // activos | posibles | retirados
let listaCupoSeleccion = new Set();
let listaCupoSedeInicializada = false;

const claveGrupoLista = (e) => `${e.grado}:${e.curso ?? ""}`;

// "4:2" -> "4-2" (y al revés), para poder escribir los grupos a mano.
const claveATextoGrupo = (clave) => clave.replace(":", "-").replace(/-$/, "-sg");

// Lee "4-2, 3-2, 5" y devuelve las claves que existan en la sede; "5" solo
// (sin guion) significa todos los grupos de ese grado.
function clavesDesdeTexto(texto, clavesExistentes) {
  const claves = new Set();
  const desconocidos = [];
  texto
    .split(/[,;]+|\s+/)
    .map((t) => t.trim().toLowerCase())
    .filter(Boolean)
    .forEach((token) => {
      const [g, c] = token.split("-");
      const grado = Number(g);
      if (!Number.isInteger(grado)) return desconocidos.push(token);
      if (c === undefined) {
        const delGrado = [...clavesExistentes].filter((k) => Number(k.split(":")[0]) === grado);
        if (!delGrado.length) return desconocidos.push(token);
        return delGrado.forEach((k) => claves.add(k));
      }
      const clave = `${grado}:${c === "sg" ? "" : Number(c)}`;
      if (!clavesExistentes.has(clave)) return desconocidos.push(token);
      claves.add(clave);
    });
  return { claves, desconocidos };
}

const VISTAS_LISTA_CUPO = [
  { id: "activos", label: "Activos" },
  { id: "posibles", label: "<i data-lucide=door-open class=ico></i> Posibles retiros" },
  { id: "retirados", label: "<i data-lucide=x class=ico></i> Retirados" },
];

function nombreGradoLista(n) {
  return (NOMBRES_GRADOS.find(([g]) => g === n) || [null, `Grado ${n}`])[1];
}

function edadLista(fechaISO) {
  if (!fechaISO) return "";
  const [ay, am, ad] = fechaColombiaISO().split("-").map(Number);
  const [ny, nm, nd] = fechaISO.split("-").map(Number);
  return String(ay - ny - (am < nm || (am === nm && ad < nd) ? 1 : 0));
}

// Mismas claves que COLUMNAS en backend/app/lista_estudiantes_pdf.py.
const COLUMNAS_LISTA_CUPO = [
  { id: "nombre", label: "Apellidos y nombres", valor: (e) => [e.primer_apellido, e.segundo_apellido, e.primer_nombre, e.segundo_nombre].filter(Boolean).join(" ") },
  { id: "tipo_documento", label: "Tipo doc.", valor: (e) => e.tipo_documento || "" },
  { id: "documento", label: "Documento", valor: (e) => e.documento },
  { id: "lugar_expedicion", label: "Lugar de expedición", valor: (e) => e.lugar_expedicion_documento || "" },
  { id: "fecha_nacimiento", label: "Fecha de nacimiento", valor: (e) => (e.fecha_nacimiento ? e.fecha_nacimiento.split("-").reverse().join("/") : "") },
  { id: "edad", label: "Edad", valor: (e) => edadLista(e.fecha_nacimiento) },
  { id: "genero", label: "Género", valor: (e) => e.genero || "" },
  { id: "grupo", label: "Grado / Grupo", valor: (e) => e.grupo },
  { id: "sede", label: "Sede", valor: (e) => (e.sede ? e.sede.nombre : "") },
  { id: "estado", label: "Estado", valor: (e) => e.estado || "" },
  { id: "marca", label: "Marca", valor: (e) => (e.retirado ? "Retirado" : e.posible_retirado ? "Posible retiro" : "") },
  { id: "resguardo", label: "Resguardo", valor: (e) => (e.resguardo === false ? "No" : "Sí") },
  { id: "observaciones", label: "Observaciones", valor: (e) => e.observaciones || "" },
  { id: "firma", label: "Firma (en blanco)", valor: () => "" },
];

// Columnas elegidas: se recuerdan en este navegador.
let listaCupoColumnas = (() => {
  try {
    const guardadas = JSON.parse(localStorage.getItem("listaCupoColumnas"));
    if (Array.isArray(guardadas) && guardadas.length) return guardadas;
  } catch (_) {}
  return ["nombre", "documento", "fecha_nacimiento", "grupo"];
})();

function guardarColumnasListaCupo() {
  try {
    localStorage.setItem("listaCupoColumnas", JSON.stringify(listaCupoColumnas));
  } catch (_) {}
}

async function renderSeccionListaCupo() {
  const contenedor = document.getElementById("contenido-reportes");
  const sedes = (await api("/api/sedes")).filter((s) => s.pertenece_ietaba);
  if (!listaCupoSedeInicializada) {
    listaCupoSedeInicializada = true;
    const ietaba = sedes.find((s) => s.nombre.toUpperCase().includes("I.E.T.A.B.A"));
    listaCupoSede = ietaba ? String(ietaba.id) : "";
  }
  await cargarYPintarListaCupo(contenedor, sedes);
}

async function cargarYPintarListaCupo(contenedor, sedes) {
  contenedor.innerHTML = '<div class="estado-carga">Cargando estudiantes...</div>';
  const params = new URLSearchParams({ estado: "ACTIVO" });
  if (listaCupoSede) params.set("sede_id", listaCupoSede);
  let estudiantes;
  try {
    estudiantes = await api(`/api/estudiantes?${params}`);
  } catch (err) {
    contenedor.innerHTML = `<div class="alerta-caja">${err.message}</div>`;
    return;
  }
  const idsSedes = new Set(sedes.map((s) => s.id));
  estudiantes = estudiantes.filter((e) => idsSedes.has(e.sede_id));
  // El backend ordena grado → curso → apellido; con varias sedes se agrupa
  // además por sede dentro de cada grado (sort estable: conserva lo demás).
  const nombreSede = new Map(sedes.map((s) => [s.id, s.nombre]));
  estudiantes.sort(
    (a, b) =>
      a.grado - b.grado ||
      (nombreSede.get(a.sede_id) || "").localeCompare(nombreSede.get(b.sede_id) || "") ||
      (a.curso ?? 0) - (b.curso ?? 0)
  );
  // (retirado siempre viene con posible_retirado=true, ver models.Estudiante)
  const esPosible = (e) => e.posible_retirado && !e.retirado;
  const conteos = { posibles: estudiantes.filter(esPosible).length, retirados: estudiantes.filter((e) => e.retirado).length };
  // Sin grupo asignado no cuentan, pero solo en sedes que SÍ trabajan por
  // grupos (Sede #01): en las rurales nadie tiene grupo y van por grado.
  const sedesConGrupos = new Set(estudiantes.filter((e) => e.curso != null).map((e) => e.sede_id));
  const sinGrupo = (e) => e.curso == null && sedesConGrupos.has(e.sede_id);
  conteos.sinGrupoIds = new Set(estudiantes.filter(sinGrupo).map((e) => e.id));
  // En la vista de activos NO se filtra aquí: los filtros (rango de grados,
  // grupos escogidos, incluir marcados) se aplican al pintar, para poder
  // cambiarlos sin volver a pedir los datos al servidor.
  if (listaCupoVista === "posibles") estudiantes = estudiantes.filter(esPosible);
  if (listaCupoVista === "retirados") estudiantes = estudiantes.filter((e) => e.retirado);
  pintarListaCupo(contenedor, sedes, estudiantes, conteos);
}

function pintarListaCupo(contenedor, sedes, estudiantes, conteos) {
  // El backend ya los entrega en orden grado → curso → apellido → nombre.
  const esActivos = listaCupoVista === "activos";
  const sinGrupoIds = conteos.sinGrupoIds || new Set();
  // Grupos que existen en la sede (para escoger 4-2, 6-4, etc.).
  const gruposDisponibles = [];
  const porClave = new Map();
  estudiantes.forEach((e) => {
    const clave = claveGrupoLista(e);
    if (!porClave.has(clave)) {
      porClave.set(clave, { clave, grado: e.grado, etiqueta: e.grupo, total: 0 });
      gruposDisponibles.push(porClave.get(clave));
    }
    porClave.get(clave).total += 1;
  });
  // Si cambió la sede, se descartan los grupos escogidos que ya no existen.
  if (listaCupoGrupos.size) {
    listaCupoGrupos = new Set([...listaCupoGrupos].filter((c) => porClave.has(c)));
  }
  const enRango = (e) =>
    listaCupoGrupos.size
      ? listaCupoGrupos.has(claveGrupoLista(e))
      : e.grado >= listaCupoDesdeGrado && e.grado <= listaCupoHastaGrado;
  const candidatos = esActivos
    ? estudiantes.filter((e) => {
        if (!listaCupoIncluir.posibles && e.posible_retirado && !e.retirado) return false;
        if (!listaCupoIncluir.retirados && e.retirado) return false;
        if (!listaCupoIncluir.sinGrupo && sinGrupoIds.has(e.id)) return false;
        return enRango(e);
      })
    : estudiantes;
  const lista =
    esActivos && !listaCupoSinLimite ? candidatos.slice(0, Math.max(listaCupoCantidad, 0)) : candidatos;
  // Sin grupo que quedaron fuera DENTRO del rango de grados de la lista.
  const gradoFinal = lista.length ? lista[lista.length - 1].grado : -1;
  const sinGrupoEnRango =
    esActivos && !listaCupoIncluir.sinGrupo
      ? estudiantes.filter((e) => sinGrupoIds.has(e.id) && enRango(e) && e.grado <= gradoFinal).length
      : 0;
  const gruposEscogidosTxt = [...listaCupoGrupos]
    .map((c) => porClave.get(c) && porClave.get(c).etiqueta)
    .filter(Boolean)
    .join(", ");
  const idsVisibles = new Set(lista.map((e) => e.id));
  listaCupoSeleccion = new Set([...listaCupoSeleccion].filter((id) => idsVisibles.has(id)));

  // Dónde se cortó la lista y cuántos de ese mismo grupo quedaron por fuera.
  let notaCorte = "";
  if (esActivos) {
    const alcance = listaCupoGrupos.size
      ? `los grupos escogidos (${gruposEscogidosTxt})`
      : `${nombreGradoLista(listaCupoDesdeGrado)} a ${nombreGradoLista(listaCupoHastaGrado)}`;
    if (!lista.length) {
      notaCorte = "No hay estudiantes para estos filtros.";
    } else if (candidatos.length <= lista.length) {
      notaCorte = `${lista.length} estudiante(s) en ${alcance}${listaCupoSinLimite ? "" : " (alcanzan todos, el cupo no cortó la lista)"}.`;
    } else {
      const ultimo = lista[lista.length - 1];
      const mismoGrupo = (e) => e.grado === ultimo.grado && e.curso === ultimo.curso && e.sede_id === ultimo.sede_id;
      const fueraGrupo = candidatos.slice(lista.length).filter(mismoGrupo).length;
      notaCorte = `Los ${lista.length} cupos llegan hasta <strong>${ultimo.grupo}</strong>${
        fueraGrupo ? ` — de ese grupo quedan <strong>${fueraGrupo}</strong> estudiante(s) por fuera` : " (ese grupo entra completo)"
      }. Faltan ${candidatos.length - lista.length} estudiante(s) más adelante.`;
    }
  }

  // Resumen por grado de lo que quedó en la lista.
  const porGrado = new Map();
  lista.forEach((e) => porGrado.set(e.grado, (porGrado.get(e.grado) || 0) + 1));
  const sedeNombre = listaCupoSede ? (sedes.find((s) => String(s.id) === listaCupoSede) || {}).nombre : "Todas las sedes IETABA";
  const columnas = COLUMNAS_LISTA_CUPO.filter((c) => listaCupoColumnas.includes(c.id));
  const titulo = esActivos
    ? `Lista de estudiantes — ${lista.length} ${
        listaCupoGrupos.size
          ? `de ${gruposEscogidosTxt}`
          : `de ${nombreGradoLista(listaCupoDesdeGrado)} a ${nombreGradoLista(listaCupoHastaGrado)}`
      }`
    : listaCupoVista === "posibles" ? "Estudiantes marcados como posible retiro" : "Estudiantes marcados como retirados";

  const accionesFila = (e) => {
    const b = [];
    if (listaCupoVista === "activos") {
      b.push(`<button type="button" class="boton secundario" data-lista-accion="posible" data-lista-id="${e.id}" title="Sigue en el sistema pero no cuenta en pendientes de boletín">Posible retiro</button>`);
    }
    if (listaCupoVista !== "retirados") {
      b.push(`<button type="button" class="boton secundario" data-lista-accion="retirado" data-lista-id="${e.id}" title="Queda marcado como retirado (no se borra ni se retira del sistema)">Retirado</button>`);
    }
    if (listaCupoVista !== "activos") {
      b.push(`<button type="button" class="boton secundario" data-lista-accion="quitar" data-lista-id="${e.id}" title="Vuelve a ser un estudiante activo normal">Quitar</button>`);
    }
    return b.join(" ");
  };

  contenedor.innerHTML = `
    <nav class="subnav-modulo no-imprimir">
      ${VISTAS_LISTA_CUPO.map(
        (v) => `<button type="button" class="subnav-item ${listaCupoVista === v.id ? "activo" : ""}" data-vista-lista="${v.id}">${v.label}${
          conteos[v.id] ? ` (${conteos[v.id]})` : ""
        }</button>`
      ).join("")}
    </nav>

    <div class="barra-filtros no-imprimir">
      <label class="filtro-campo">Sede
        <select id="select-lista-sede">
          <option value="" ${listaCupoSede === "" ? "selected" : ""}>Todas las sedes IETABA</option>
          ${sedes.map((s) => `<option value="${s.id}" ${String(s.id) === listaCupoSede ? "selected" : ""}>${s.nombre}</option>`).join("")}
        </select>
      </label>
      ${
        esActivos
          ? `<label class="filtro-campo">Desde el grado
               <select id="select-lista-desde" ${listaCupoGrupos.size ? "disabled" : ""}>
                 ${NOMBRES_GRADOS.map(([n, nombre]) => `<option value="${n}" ${n === listaCupoDesdeGrado ? "selected" : ""}>${nombre}</option>`).join("")}
               </select>
             </label>
             <label class="filtro-campo">Hasta el grado
               <select id="select-lista-hasta" ${listaCupoGrupos.size ? "disabled" : ""}>
                 ${NOMBRES_GRADOS.map(([n, nombre]) => `<option value="${n}" ${n === listaCupoHastaGrado ? "selected" : ""}>${nombre}</option>`).join("")}
               </select>
             </label>
             <label class="filtro-campo">Cantidad de estudiantes
               <input type="number" id="input-lista-cantidad" value="${listaCupoCantidad}" min="1" step="1" ${listaCupoSinLimite ? "disabled" : ""} />
             </label>
             <label class="check-linea filtro-check">
               <input type="checkbox" id="check-lista-sin-limite" ${listaCupoSinLimite ? "checked" : ""} /> Sin límite (todos los que cumplan)
             </label>`
          : ""
      }
      <button type="button" class="boton" id="btn-lista-pdf" ${lista.length ? "" : "disabled"}><i data-lucide=file-text class=ico></i> Descargar PDF</button>
      <button type="button" class="boton secundario" onclick="window.print()"><i data-lucide=printer class=ico></i> Imprimir</button>
    </div>

    ${
      esActivos
        ? `<div class="barra-filtros no-imprimir">
             <strong>Incluir también:</strong>
             <label class="check-linea filtro-check"><input type="checkbox" data-lista-incluir="posibles" ${listaCupoIncluir.posibles ? "checked" : ""} /> <i data-lucide=door-open class=ico></i> Posibles retiros</label>
             <label class="check-linea filtro-check"><input type="checkbox" data-lista-incluir="retirados" ${listaCupoIncluir.retirados ? "checked" : ""} /> <i data-lucide=x class=ico></i> Retirados</label>
             <label class="check-linea filtro-check"><input type="checkbox" data-lista-incluir="sinGrupo" ${listaCupoIncluir.sinGrupo ? "checked" : ""} /> Sin grupo asignado</label>
           </div>

           <details class="seccion-colapsable no-imprimir" ${listaCupoGrupos.size ? "open" : ""}>
             <summary>Grados y grupos a imprimir — ${
               listaCupoGrupos.size ? `${listaCupoGrupos.size} escogido(s): ${gruposEscogidosTxt}` : "todos los del rango de grados"
             }</summary>
             <div class="toolbar">
               <label class="filtro-campo">Escribe los grupos
                 <input type="text" id="input-grupos-texto" placeholder="Ej: 4-2, 3-2 (o 4 = todo Cuarto)" value="${[...listaCupoGrupos].map(claveATextoGrupo).join(", ")}" />
               </label>
               <button type="button" class="boton secundario" id="btn-grupos-aplicar">Aplicar</button>
               <button type="button" class="boton secundario" id="btn-grupos-limpiar">Todos (usar el rango de grados)</button>
             </div>
             ${[...new Set(gruposDisponibles.map((g) => g.grado))]
               .sort((a, b) => a - b)
               .map((grado) => {
                 const delGrado = gruposDisponibles.filter((g) => g.grado === grado);
                 const todos = delGrado.every((g) => listaCupoGrupos.has(g.clave));
                 return `<div class="fila-grupos-lista">
                   <button type="button" class="boton-texto-chico" data-grado-todos="${grado}">${todos ? "<i data-lucide=check class=ico></i> " : ""}${nombreGradoLista(grado)} (todo el grado)</button>
                   ${delGrado
                     .map(
                       (g) => `<label class="check-linea filtro-check"><input type="checkbox" data-grupo-lista="${g.clave}" ${
                         listaCupoGrupos.has(g.clave) ? "checked" : ""
                       } /> ${esc(g.etiqueta)} <span class="pendiente">(${g.total})</span></label>`
                     )
                     .join("")}
                 </div>`;
               })
               .join("")}
           </details>`
        : ""
    }

    <div class="barra-filtros no-imprimir">
      <strong>Columnas:</strong>
      ${COLUMNAS_LISTA_CUPO.map(
        (c) => `<label class="check-linea filtro-check"><input type="checkbox" data-lista-columna="${c.id}" ${listaCupoColumnas.includes(c.id) ? "checked" : ""} /> ${c.label}</label>`
      ).join("")}
    </div>

    <div class="hoja-imprimir">
      <h2 style="margin:6px 0">${titulo}</h2>
      <p class="pendiente">${sedeNombre}${
        esActivos
          ? ` · ${
              [
                listaCupoIncluir.posibles ? "" : "posibles retiros",
                listaCupoIncluir.retirados ? "" : "retirados",
                listaCupoIncluir.sinGrupo || !sinGrupoEnRango ? "" : `${sinGrupoEnRango} sin grupo asignado`,
              ].filter(Boolean).length
                ? "sin incluir: " +
                  [
                    listaCupoIncluir.posibles ? "" : "posibles retiros",
                    listaCupoIncluir.retirados ? "" : "retirados",
                    listaCupoIncluir.sinGrupo || !sinGrupoEnRango ? "" : `${sinGrupoEnRango} sin grupo asignado`,
                  ]
                    .filter(Boolean)
                    .join(", ")
                : "incluye posibles retiros, retirados y sin grupo"
            }`
          : ""
      }</p>
      ${esActivos ? `<p>${notaCorte}</p>` : `<p class="conteo-resultados">${lista.length} estudiante(s)</p>`}
      ${
        esActivos && porGrado.size
          ? `<div class="resumen-reportes">${[...porGrado.entries()]
              .map(([g, n]) => `<div class="metric-card"><span>${nombreGradoLista(g)}</span><strong>${n}</strong></div>`)
              .join("")}</div>`
          : ""
      }

      <div id="barra-seleccion-lista" class="barra-seleccion-grilla no-imprimir" ${listaCupoSeleccion.size ? "" : "hidden"}>
        <strong id="barra-seleccion-lista-conteo">${listaCupoSeleccion.size} seleccionado(s)</strong>
        ${listaCupoVista === "activos" ? '<button type="button" class="boton secundario" data-lista-lote="posible"><i data-lucide=door-open class=ico></i> Marcar posible retiro</button>' : ""}
        ${listaCupoVista !== "retirados" ? '<button type="button" class="boton secundario" data-lista-lote="retirado"><i data-lucide=x class=ico></i> Marcar retirado</button>' : ""}
        ${listaCupoVista !== "activos" ? '<button type="button" class="boton secundario" data-lista-lote="quitar"><i data-lucide=undo-2 class=ico></i> Quitar marca</button>' : ""}
        <button type="button" class="boton-texto-chico" id="btn-lista-limpiar"><i data-lucide=x class=ico></i> Quitar selección</button>
      </div>

      ${
        lista.length
          ? `<div class="tabla-scroll"><table>
               <thead><tr>
                 <th class="no-imprimir"><input type="checkbox" id="check-lista-todos" ${lista.length && listaCupoSeleccion.size === lista.length ? "checked" : ""} title="Seleccionar todos" /></th>
                 <th>#</th>${columnas.map((c) => `<th>${esc(c.label)}</th>`).join("")}<th class="no-imprimir"></th>
               </tr></thead>
               <tbody>
                 ${lista
                   .map(
                     (e, i) => `<tr>
                   <td class="no-imprimir"><input type="checkbox" data-lista-sel="${e.id}" ${listaCupoSeleccion.has(e.id) ? "checked" : ""} /></td>
                   <td>${i + 1}</td>
                   ${columnas
                     .map(
                       (c, ci) =>
                         `<td>${esc(c.valor(e))}${
                           ci === 0 && e.retirado
                             ? ' <span class="chip-retiro chip-retirado"><i data-lucide=x class=ico></i> RETIRADO</span>'
                             : ci === 0 && e.posible_retirado
                             ? ' <span class="chip-retiro"><i data-lucide=door-open class=ico></i> posible retiro</span>'
                             : ""
                         }</td>`
                     )
                     .join("")}
                   <td class="no-imprimir" style="white-space:nowrap">${accionesFila(e)}</td>
                 </tr>`
                   )
                   .join("")}
               </tbody>
             </table></div>`
          : !esActivos
          ? `<div class="estado-vacio"><div class="estado-vacio-icono"><i data-lucide=check class=ico></i> </div><h3>No hay estudiantes en esta lista</h3></div>`
          : ""
      }
    </div>
  `;

  vincularListaCupo(contenedor, sedes, lista);

  // Filtros que no necesitan volver a pedir datos al servidor: se repinta.
  const repintar = () => pintarListaCupo(contenedor, sedes, estudiantes, conteos);
  document.getElementById("select-lista-desde")?.addEventListener("change", (ev) => {
    listaCupoDesdeGrado = Number(ev.target.value);
    if (listaCupoHastaGrado < listaCupoDesdeGrado) listaCupoHastaGrado = listaCupoDesdeGrado;
    repintar();
  });
  document.getElementById("input-lista-cantidad")?.addEventListener("change", (ev) => {
    const n = parseInt(ev.target.value, 10);
    listaCupoCantidad = n > 0 ? n : listaCupoCantidad;
    repintar();
  });
  document.getElementById("select-lista-hasta")?.addEventListener("change", (ev) => {
    listaCupoHastaGrado = Number(ev.target.value);
    if (listaCupoHastaGrado < listaCupoDesdeGrado) listaCupoDesdeGrado = listaCupoHastaGrado;
    repintar();
  });
  document.getElementById("check-lista-sin-limite")?.addEventListener("change", (ev) => {
    listaCupoSinLimite = ev.target.checked;
    repintar();
  });
  contenedor.querySelectorAll("[data-lista-incluir]").forEach((chk) =>
    chk.addEventListener("change", () => {
      listaCupoIncluir[chk.dataset.listaIncluir] = chk.checked;
      repintar();
    })
  );
  contenedor.querySelectorAll("[data-grupo-lista]").forEach((chk) =>
    chk.addEventListener("change", () => {
      if (chk.checked) listaCupoGrupos.add(chk.dataset.grupoLista);
      else listaCupoGrupos.delete(chk.dataset.grupoLista);
      repintar();
    })
  );
  contenedor.querySelectorAll("[data-grado-todos]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const grado = Number(btn.dataset.gradoTodos);
      const claves = gruposDisponibles.filter((g) => g.grado === grado).map((g) => g.clave);
      const todos = claves.every((c) => listaCupoGrupos.has(c));
      claves.forEach((c) => (todos ? listaCupoGrupos.delete(c) : listaCupoGrupos.add(c)));
      repintar();
    })
  );
  const aplicarGruposEscritos = () => {
    const campo = document.getElementById("input-grupos-texto");
    if (!campo) return;
    const { claves, desconocidos } = clavesDesdeTexto(campo.value, new Set(gruposDisponibles.map((g) => g.clave)));
    if (desconocidos.length) alert(`No existen en esta sede: ${desconocidos.join(", ")}`);
    listaCupoGrupos = claves;
    repintar();
  };
  document.getElementById("btn-grupos-aplicar")?.addEventListener("click", aplicarGruposEscritos);
  document.getElementById("input-grupos-texto")?.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") aplicarGruposEscritos();
  });
  document.getElementById("btn-grupos-limpiar")?.addEventListener("click", () => {
    listaCupoGrupos.clear();
    repintar();
  });

  contenedor.querySelectorAll("[data-lista-columna]").forEach((chk) =>
    chk.addEventListener("change", () => {
      const id = chk.dataset.listaColumna;
      listaCupoColumnas = chk.checked
        ? COLUMNAS_LISTA_CUPO.map((c) => c.id).filter((c) => c === id || listaCupoColumnas.includes(c))
        : listaCupoColumnas.filter((c) => c !== id);
      guardarColumnasListaCupo();
      pintarListaCupo(contenedor, sedes, estudiantes, conteos); // sin volver a pedir datos
    })
  );

  document.getElementById("btn-lista-pdf").addEventListener("click", async (ev) => {
    if (!columnas.length) return alert("Escoge al menos una columna para el PDF.");
    const btn = ev.currentTarget;
    btn.disabled = true;
    btn.textContent = "Generando PDF...";
    try {
      await descargarPdfListaCupo({
        ids: lista.map((e) => e.id),
        columnas: columnas.map((c) => c.id),
        vista: listaCupoVista,
        sede_nombre: sedeNombre,
        desde_grado: listaCupoDesdeGrado,
        hasta_grado: listaCupoHastaGrado,
        grupos_txt: esActivos ? gruposEscogidosTxt : "",
        cantidad: esActivos && !listaCupoSinLimite ? listaCupoCantidad : null,
        completo: !esActivos || listaCupoSinLimite || candidatos.length <= lista.length,
        sin_grupo_excluidos: sinGrupoEnRango,
        incluye_posibles: esActivos && listaCupoIncluir.posibles,
        incluye_retirados: esActivos && listaCupoIncluir.retirados,
      });
    } catch (err) {
      alert(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Descargar PDF";
    }
  });
}

// POST (la lista de ids puede ser larga) → blob → descarga. Mismo manejo de
// sesión que api(): un 401 intenta refrescar el token una vez.
async function descargarPdfListaCupo(cuerpo) {
  const pedir = () =>
    fetch("/api/reportes/lista-estudiantes/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    });
  await asegurarSesionFresca(); // Fase 4A': renovar antes, no solo tras un 401
  let res = await pedir();
  if (res.status === 401 && (await _intentarRefresh())) res = await pedir();
  if (!res.ok) {
    const detalle = await res.json().catch(() => ({}));
    throw new Error(detalle.detail || `Error ${res.status} generando el PDF`);
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `lista_estudiantes_${fechaColombiaISO()}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

// Cambia el estado de uno o varios estudiantes:
//   posible  → sigue ACTIVO pero marcado como posible retiro
//   retirado → marcado como retirado (sigue en el sistema, solo la marca)
//   quitar   → sin ninguna marca (vuelve a contar normal)
const CAMBIOS_LISTA_CUPO = {
  posible: { body: { posible_retirado: true, retirado: false }, texto: 'marcar como "posible retiro"' },
  retirado: { body: { retirado: true }, texto: 'marcar como "retirado"' },
  quitar: { body: { posible_retirado: false, retirado: false }, texto: "quitarle la marca" },
};

async function aplicarCambioListaCupo(ids, accion) {
  const cambio = CAMBIOS_LISTA_CUPO[accion];
  await Promise.all(
    ids.map((id) => api(`/api/estudiantes/${id}`, { method: "PATCH", body: JSON.stringify(cambio.body) }))
  );
}

function vincularListaCupo(contenedor, sedes, lista) {
  const recargar = () => cargarYPintarListaCupo(contenedor, sedes);

  contenedor.querySelectorAll("[data-vista-lista]").forEach((btn) =>
    btn.addEventListener("click", () => {
      listaCupoVista = btn.dataset.vistaLista;
      listaCupoSeleccion.clear();
      recargar();
    })
  );
  document.getElementById("select-lista-sede").addEventListener("change", (e) => {
    listaCupoSede = e.target.value;
    listaCupoSeleccion.clear();
    recargar();
  });

  const refrescarBarra = () => {
    const barra = document.getElementById("barra-seleccion-lista");
    barra.hidden = listaCupoSeleccion.size === 0;
    document.getElementById("barra-seleccion-lista-conteo").textContent = `${listaCupoSeleccion.size} seleccionado(s)`;
  };
  contenedor.querySelectorAll("[data-lista-sel]").forEach((chk) =>
    chk.addEventListener("change", () => {
      const id = Number(chk.dataset.listaSel);
      if (chk.checked) listaCupoSeleccion.add(id);
      else listaCupoSeleccion.delete(id);
      refrescarBarra();
    })
  );
  document.getElementById("check-lista-todos")?.addEventListener("change", (e) => {
    contenedor.querySelectorAll("[data-lista-sel]").forEach((c) => (c.checked = e.target.checked));
    listaCupoSeleccion = e.target.checked ? new Set(lista.map((x) => x.id)) : new Set();
    refrescarBarra();
  });
  document.getElementById("btn-lista-limpiar").addEventListener("click", () => {
    listaCupoSeleccion.clear();
    contenedor.querySelectorAll("[data-lista-sel], #check-lista-todos").forEach((c) => (c.checked = false));
    refrescarBarra();
  });

  contenedor.querySelectorAll("[data-lista-accion]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const accion = btn.dataset.listaAccion;
      const est = lista.find((x) => x.id === Number(btn.dataset.listaId));
      const nombre = est ? `${est.primer_nombre} ${est.primer_apellido}` : "";
      if (accion === "retirado" && !confirm(`¿${CAMBIOS_LISTA_CUPO.retirado.texto}: ${nombre}?`)) return;
      btn.disabled = true;
      try {
        await aplicarCambioListaCupo([Number(btn.dataset.listaId)], accion);
      } catch (err) {
        alert(err.message);
      }
      listaCupoSeleccion.delete(Number(btn.dataset.listaId));
      recargar();
    })
  );
  contenedor.querySelectorAll("[data-lista-lote]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const ids = [...listaCupoSeleccion];
      const accion = btn.dataset.listaLote;
      if (!ids.length) return;
      if (!confirm(`¿${CAMBIOS_LISTA_CUPO[accion].texto} a ${ids.length} estudiante(s)?`)) return;
      document.querySelectorAll("#barra-seleccion-lista button").forEach((b) => (b.disabled = true));
      try {
        await aplicarCambioListaCupo(ids, accion);
      } catch (err) {
        alert(err.message);
      }
      listaCupoSeleccion.clear();
      recargar();
    })
  );
}

// --- Sección: Lista de docentes (dinámico: columnas y responsables de grupo) --
// El backend (GET /api/reportes/docentes, ver crud.listar_docentes_reporte) ya
// calcula por docente sus asignaciones y si es "responsable de grupo" —
// director de grupo (grupo con profesores de área) o maestro único (rural,
// dicta todo el grupo). Aquí solo se filtra "todos / solo responsables" y se
// escogen las columnas a mostrar/exportar, mismo patrón que Lista de estudiantes.

let listaDocentesSede = ""; // "" = todas las sedes IETABA
let listaDocentesVista = "todos"; // todos | responsables
let listaDocentesSedeInicializada = false;

function rolDocenteTexto(d) {
  const tipos = new Set(d.asignaciones.map((a) => a.tipo));
  if (tipos.has("DIRECTOR")) return "Director de grupo";
  if (tipos.has("GRUPO")) return "Maestro único";
  if (tipos.has("AREA")) return "Docente de área";
  return "Sin asignación";
}

// Mismas claves que COLUMNAS en backend/app/docentes_pdf.py.
const COLUMNAS_LISTA_DOCENTES = [
  { id: "nombre", label: "Nombre completo", valor: (d) => d.nombre_completo },
  { id: "documento", label: "Documento", valor: (d) => d.documento },
  { id: "telefono", label: "Teléfono", valor: (d) => d.telefono || "" },
  { id: "email", label: "Correo", valor: (d) => d.email || "" },
  { id: "direccion", label: "Dirección", valor: (d) => d.direccion || "" },
  { id: "fecha_nacimiento", label: "Fecha de nacimiento", valor: (d) => (d.fecha_nacimiento ? d.fecha_nacimiento.split("-").reverse().join("/") : "") },
  { id: "sede", label: "Sede(s)", valor: (d) => [...new Set(d.asignaciones.map((a) => a.sede_nombre).filter(Boolean))].sort().join(", ") },
  { id: "rol", label: "Rol", valor: rolDocenteTexto },
  { id: "director_de", label: "Director/responsable de", valor: (d) => d.grupos_dirige.join(", ") || "—" },
  {
    id: "areas",
    label: "Área(s) que dicta",
    valor: (d) => [...new Set(d.asignaciones.map((a) => a.area_nombre).filter(Boolean))].sort().join(", ") || "—",
  },
  { id: "firma", label: "Firma (en blanco)", valor: () => "" },
];

// Columnas elegidas: se recuerdan en este navegador.
let listaDocentesColumnas = (() => {
  try {
    const guardadas = JSON.parse(localStorage.getItem("listaDocentesColumnas"));
    if (Array.isArray(guardadas) && guardadas.length) return guardadas;
  } catch (_) {}
  return ["nombre", "documento", "rol", "director_de"];
})();

// Columnas cortas tipo etiqueta (sede, rol): no se parten a media frase.
const CELDA_NOWRAP_DOCENTES = new Set(["sede", "rol", "documento", "telefono", "fecha_nacimiento"]);

function guardarColumnasListaDocentes() {
  try {
    localStorage.setItem("listaDocentesColumnas", JSON.stringify(listaDocentesColumnas));
  } catch (_) {}
}

async function renderSeccionListaDocentes() {
  const contenedor = document.getElementById("contenido-reportes");
  const sedes = (await api("/api/sedes")).filter((s) => s.pertenece_ietaba);
  if (!listaDocentesSedeInicializada) {
    listaDocentesSedeInicializada = true;
    const ietaba = sedes.find((s) => s.nombre.toUpperCase().includes("I.E.T.A.B.A"));
    listaDocentesSede = ietaba ? String(ietaba.id) : "";
  }
  await cargarYPintarListaDocentes(contenedor, sedes);
}

async function cargarYPintarListaDocentes(contenedor, sedes) {
  contenedor.innerHTML = '<div class="estado-carga">Cargando docentes...</div>';
  const params = new URLSearchParams();
  if (listaDocentesSede) params.set("sede_id", listaDocentesSede);
  let docentes;
  try {
    docentes = await api(`/api/reportes/docentes?${params}`);
  } catch (err) {
    contenedor.innerHTML = `<div class="alerta-caja">${err.message}</div>`;
    return;
  }
  pintarListaDocentes(contenedor, sedes, docentes);
}

function pintarListaDocentes(contenedor, sedes, docentes) {
  const totalResponsables = docentes.filter((d) => d.es_responsable_grupo).length;
  const lista = listaDocentesVista === "responsables" ? docentes.filter((d) => d.es_responsable_grupo) : docentes;

  const soloUnaSede = listaDocentesSede !== "";
  const sedeNombre = soloUnaSede
    ? (sedes.find((s) => String(s.id) === listaDocentesSede) || {}).nombre
    : "Todas las sedes IETABA";
  // Con una sola sede en pantalla, la columna "Sede(s)" repetiría el mismo
  // valor en cada fila — ese dato ya va una sola vez en el título.
  const columnas = COLUMNAS_LISTA_DOCENTES.filter(
    (c) => listaDocentesColumnas.includes(c.id) && !(soloUnaSede && c.id === "sede")
  );
  const base = listaDocentesVista === "responsables" ? "Docentes responsables de grupo" : "Docentes";
  const titulo = soloUnaSede ? `${base} — ${sedeNombre} (${lista.length})` : `${base} — ${lista.length}`;

  contenedor.innerHTML = `
    <nav class="subnav-modulo no-imprimir">
      <button type="button" class="subnav-item ${listaDocentesVista === "todos" ? "activo" : ""}" data-vista-docentes="todos">Todos (${docentes.length})</button>
      <button type="button" class="subnav-item ${listaDocentesVista === "responsables" ? "activo" : ""}" data-vista-docentes="responsables">Solo directores/responsables de grupo (${totalResponsables})</button>
    </nav>

    <div class="barra-filtros no-imprimir">
      <label class="filtro-campo">Sede
        <select id="select-docentes-sede">
          <option value="" ${listaDocentesSede === "" ? "selected" : ""}>Todas las sedes IETABA</option>
          ${sedes.map((s) => `<option value="${s.id}" ${String(s.id) === listaDocentesSede ? "selected" : ""}>${s.nombre}</option>`).join("")}
        </select>
      </label>
      <button type="button" class="boton" id="btn-docentes-pdf" ${lista.length ? "" : "disabled"}><i data-lucide=file-text class=ico></i> Descargar PDF</button>
      <button type="button" class="boton secundario" onclick="window.print()"><i data-lucide=printer class=ico></i> Imprimir</button>
    </div>

    <div class="barra-filtros no-imprimir">
      <strong>Columnas:</strong>
      ${COLUMNAS_LISTA_DOCENTES.map((c) => {
        const deshabilitada = soloUnaSede && c.id === "sede";
        return `<label class="check-linea filtro-check" ${deshabilitada ? 'title="Ya está en el título, arriba: solo aplica con \'Todas las sedes IETABA\'"' : ""}><input type="checkbox" data-docentes-columna="${c.id}" ${listaDocentesColumnas.includes(c.id) ? "checked" : ""} ${deshabilitada ? "disabled" : ""} /> ${c.label}</label>`;
      }).join("")}
    </div>

    <div class="hoja-imprimir">
      <h2 style="margin:6px 0">${titulo}</h2>
      ${soloUnaSede ? "" : `<p class="pendiente">${sedeNombre}</p>`}
      ${
        lista.length
          ? `<div class="tabla-scroll"><table>
               <thead><tr><th>#</th>${columnas.map((c) => `<th${CELDA_NOWRAP_DOCENTES.has(c.id) ? ' class="celda-nowrap"' : ""}>${esc(c.label)}</th>`).join("")}</tr></thead>
               <tbody>
                 ${lista
                   .map(
                     (d, i) => `<tr>
                   <td>${i + 1}</td>
                   ${columnas.map((c) => `<td${CELDA_NOWRAP_DOCENTES.has(c.id) ? ' class="celda-nowrap"' : ""}>${esc(c.valor(d))}</td>`).join("")}
                 </tr>`
                   )
                   .join("")}
               </tbody>
             </table></div>`
          : `<div class="estado-vacio"><div class="estado-vacio-icono"><i data-lucide=check class=ico></i> </div><h3>No hay docentes para estos filtros</h3></div>`
      }
    </div>
  `;

  document.getElementById("select-docentes-sede").addEventListener("change", (e) => {
    listaDocentesSede = e.target.value;
    cargarYPintarListaDocentes(contenedor, sedes);
  });
  contenedor.querySelectorAll("[data-vista-docentes]").forEach((btn) =>
    btn.addEventListener("click", () => {
      listaDocentesVista = btn.dataset.vistaDocentes;
      pintarListaDocentes(contenedor, sedes, docentes);
    })
  );
  contenedor.querySelectorAll("[data-docentes-columna]").forEach((chk) =>
    chk.addEventListener("change", () => {
      const id = chk.dataset.docentesColumna;
      listaDocentesColumnas = chk.checked
        ? COLUMNAS_LISTA_DOCENTES.map((c) => c.id).filter((c) => c === id || listaDocentesColumnas.includes(c))
        : listaDocentesColumnas.filter((c) => c !== id);
      guardarColumnasListaDocentes();
      pintarListaDocentes(contenedor, sedes, docentes);
    })
  );

  document.getElementById("btn-docentes-pdf").addEventListener("click", async (ev) => {
    if (!columnas.length) return alert("Escoge al menos una columna para el PDF.");
    const btn = ev.currentTarget;
    btn.disabled = true;
    btn.textContent = "Generando PDF...";
    try {
      await descargarPdfListaDocentes({
        ids: lista.map((d) => d.id),
        columnas: columnas.map((c) => c.id),
        sede_nombre: sedeNombre,
        solo_responsables_grupo: listaDocentesVista === "responsables",
      });
    } catch (err) {
      alert(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Descargar PDF";
    }
  });
}

// POST → blob → descarga. Mismo manejo de sesión que descargarPdfListaCupo().
async function descargarPdfListaDocentes(cuerpo) {
  const pedir = () =>
    fetch("/api/reportes/lista-docentes/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    });
  await asegurarSesionFresca();
  let res = await pedir();
  if (res.status === 401 && (await _intentarRefresh())) res = await pedir();
  if (!res.ok) {
    const detalle = await res.json().catch(() => ({}));
    throw new Error(detalle.detail || `Error ${res.status} generando el PDF`);
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `lista_docentes_${fechaColombiaISO()}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

// --- Sección: Resumen institucional (clasificación de sedes) ---------------

async function renderSeccionResumenInstitucional() {
  const contenedor = document.getElementById("contenido-reportes");
  const [sedes, reporte] = await Promise.all([
    api("/api/sedes"),
    api("/api/sedes/reporte?solo_ietaba=true"),
  ]);

  const sedesIetaba = sedes.filter((s) => s.pertenece_ietaba).length;

  contenedor.innerHTML = `
    <div class="resumen-reportes">
      <div class="metric-card"><span>Sedes IETABA</span><strong>${sedesIetaba}</strong></div>
      <div class="metric-card"><span>Estudiantes activos</span><strong>${reporte.total_estudiantes}</strong></div>
      <div class="metric-card"><span>Hombres</span><strong>${reporte.hombres}</strong></div>
      <div class="metric-card"><span>Mujeres</span><strong>${reporte.mujeres}</strong></div>
    </div>
    <details class="seccion-colapsable">
      <summary>Clasificación de sedes (${sedes.length} sedes del archivo, ${sedesIetaba} marcadas como IETABA)</summary>
      <table>
        <thead>
          <tr><th>IETABA</th><th>Sede</th><th>Institucion</th><th>Resguardo</th><th>Activos</th></tr>
        </thead>
        <tbody>
          ${sedes.map((s) => `
            <tr>
              <td><input class="check-ietaba" type="checkbox" data-id="${s.id}" ${s.pertenece_ietaba ? "checked" : ""} /></td>
              <td>${s.nombre}</td>
              <td>${s.institucion_centro_educativo || "-"}</td>
              <td>${s.resguardo || "-"}</td>
              <td>${s.total_activos}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </details>
    <div class="toolbar reporte-subtitulo">
      <strong>Resumen por sede IETABA</strong>
    </div>
    <table>
      <thead>
        <tr><th>Sede</th><th>Total activos</th><th>Hombres</th><th>Mujeres</th></tr>
      </thead>
      <tbody>
        ${reporte.por_sede.map((s) => `
          <tr><td>${s.nombre}</td><td>${s.total_estudiantes}</td><td>${s.hombres}</td><td>${s.mujeres}</td></tr>
        `).join("")}
      </tbody>
      <tfoot>
        <tr>
          <th>Total</th>
          <th>${reporte.total_estudiantes}</th>
          <th>${reporte.hombres}</th>
          <th>${reporte.mujeres}</th>
        </tr>
      </tfoot>
    </table>
  `;

  document.querySelectorAll(".check-ietaba").forEach((check) => {
    check.addEventListener("change", async () => {
      await api(`/api/sedes/${check.dataset.id}`, {
        method: "PATCH",
        body: JSON.stringify({ pertenece_ietaba: check.checked }),
      });
      renderReportes();
    });
  });
}

// --- Sección: Conciliación SIMAC ↔ SAPRED -----------------------------------
// SIMAC = la base de matrícula local (tabla Estudiante, ver nota en
// backend/app/models.py). SAPRED = lo ya importado en NotaSapred/
// RevisionBoletin/EstudianteSapredSinCoincidencia. Esta vista solo lee y
// clasifica lo que ya existe (endpoint /api/reportes/conciliacion) — no
// guarda nada ni inventa una tercera fuente.

let conciliacionAnio = new Date().getFullYear();
let conciliacionPeriodo = 2;
let conciliacionSedeSeleccionada = "";
let conciliacionGradoSeleccionado = "";
let conciliacionVista = "estudiantes"; // estudiantes | grupos | docentes
let conciliacionEstadoFiltro = "problemas"; // "problemas" = todo menos "coincide" (el default: lo que va bien no necesita salir en el reporte)
let conciliacionDocenteFiltro = "";
let conciliacionBusqueda = "";
let mantenerFocoBuscarConciliacion = false;
let temporizadorBuscarConciliacion;
let conciliacionCache = null; // último ConciliacionResultado recibido del backend
let conciliacionUltimaActualizacion = null; // Date del último fetch exitoso
let conciliacionRenderToken = 0;
let hallazgosIncluirResueltos = false; // false = solo pendientes; true = historial completo (incluye ya corregidos)
let presenciaIncluirCoincide = false; // false = solo Solo SIMAT / Solo SAPRED; true = también los que coinciden

const ETIQUETAS_ESTADO_CONCILIACION = {
  coincide: { icono: "<span class=punto-verde></span>", texto: "Coincide", clase: "ok" },
  solo_simac: { icono: "<span class=punto-rojo></span>", texto: "Solo SIMAC", clase: "alerta" },
  solo_sapred: { icono: "<span class=punto-naranja></span>", texto: "Solo SAPRED", clase: "naranja" },
  diferencia: { icono: "<span class=punto-amarillo></span>", texto: "Diferencia", clase: "proceso" },
};

const ETIQUETAS_CAMPO_DIFERENCIA = {
  nombre: "Nombre",
  grupo: "Grado / Grupo",
  documento: "Documento",
};

function badgeEstadoConciliacionHtml(estado) {
  const e = ETIQUETAS_ESTADO_CONCILIACION[estado] || { icono: "", texto: estado, clase: "" };
  return `<span class="badge-estado ${e.clase}">${e.icono} ${e.texto}</span>`;
}

function colorCalidadConciliacion(pct) {
  if (pct >= 90) return "var(--verde)";
  if (pct >= 70) return "var(--amarillo)";
  return "var(--rojo)";
}

function formatoFechaHoraConciliacion(fecha) {
  return `${fecha.toLocaleDateString("es-CO")} - ${fecha.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" })}`;
}

function urlConciliacionParams() {
  const params = new URLSearchParams({ anio_lectivo: conciliacionAnio, periodo: conciliacionPeriodo });
  if (conciliacionSedeSeleccionada) params.set("sede_id", conciliacionSedeSeleccionada);
  if (conciliacionGradoSeleccionado) params.set("grado", conciliacionGradoSeleccionado);
  return params;
}

async function renderSeccionConciliacion() {
  const contenedor = document.getElementById("contenido-reportes");
  const todasLasSedes = await api("/api/sedes");
  const sedes = todasLasSedes.filter((s) => s.pertenece_ietaba);
  if (conciliacionSedeSeleccionada === "") {
    const ietaba = sedes.find((s) => s.nombre.toUpperCase().includes("I.E.T.A.B.A"));
    conciliacionSedeSeleccionada = ietaba ? String(ietaba.id) : "";
  }
  await cargarYPintarConciliacion(contenedor, sedes);
}

async function cargarYPintarConciliacion(contenedor, sedes) {
  const miToken = ++conciliacionRenderToken;
  contenedor.innerHTML = '<div class="estado-carga">Calculando conciliación SIMAC <i data-lucide=arrow-left-right class=ico></i> SAPRED...</div>';
  let resultado;
  try {
    resultado = await api(`/api/reportes/conciliacion?${urlConciliacionParams()}`);
  } catch (err) {
    if (miToken !== conciliacionRenderToken) return;
    contenedor.innerHTML = `<div class="alerta-caja">${err.message}</div>`;
    return;
  }
  if (miToken !== conciliacionRenderToken) return;
  conciliacionCache = resultado;
  conciliacionUltimaActualizacion = new Date();
  pintarConciliacion(contenedor, sedes);
}

function filtrarEstudiantesConciliacion(estudiantes) {
  let filtrados = estudiantes;
  if (conciliacionEstadoFiltro === "problemas") {
    filtrados = filtrados.filter((e) => e.estado_conciliacion !== "coincide");
  } else if (conciliacionEstadoFiltro === "promocion_anticipada") {
    filtrados = filtrados.filter((e) => e.candidato_promocion_anticipada);
  } else if (conciliacionEstadoFiltro) {
    filtrados = filtrados.filter((e) => e.estado_conciliacion === conciliacionEstadoFiltro);
  }
  if (conciliacionDocenteFiltro) {
    filtrados = filtrados.filter((e) => e.docente === conciliacionDocenteFiltro);
  }
  const q = conciliacionBusqueda.trim().toLowerCase();
  if (q) {
    filtrados = filtrados.filter((e) => [e.nombre_completo, e.documento].some((c) => c && c.toLowerCase().includes(q)));
  }
  return filtrados;
}

function pintarConciliacion(contenedor, sedes) {
  const r = conciliacionCache;
  const docentesDisponibles = [...new Set(r.grupos.map((g) => g.docente).filter(Boolean))].sort();

  contenedor.innerHTML = `
    <div class="conciliacion-header-info no-imprimir">
      <span class="conteo-resultados">Última actualización: ${
        conciliacionUltimaActualizacion ? formatoFechaHoraConciliacion(conciliacionUltimaActualizacion) : "-"
      }</span>
      <button type="button" class="boton secundario" id="btn-actualizar-conciliacion"><i data-lucide=refresh-cw class=ico></i> Actualizar conciliación</button>
      <button type="button" class="boton secundario" id="btn-exportar-conciliacion"><i data-lucide=download class=ico></i> Exportar inconsistencias (Excel)</button>
      <label class="check-linea filtro-check" title="Por defecto el PDF de presencia solo trae Solo SIMAT / Solo SAPRED">
        <input type="checkbox" id="check-presencia-incluir-coincide" ${presenciaIncluirCoincide ? "checked" : ""} /> PDF: incluir los que coinciden
      </label>
      <button type="button" class="boton" id="btn-presencia-pdf"><i data-lucide=file-text class=ico></i> PDF de presencia (SIMAT/SAPRED)</button>
    </div>

    <div class="barra-filtros no-imprimir">
      <label class="filtro-campo">Año lectivo
        <input type="number" id="input-conciliacion-anio" value="${conciliacionAnio}" />
      </label>
      <label class="filtro-campo">Período
        <select id="select-conciliacion-periodo">
          ${[1, 2, 3, 4].map((p) => `<option value="${p}" ${p === conciliacionPeriodo ? "selected" : ""}>Período ${p}</option>`).join("")}
        </select>
      </label>
      <label class="filtro-campo">Sede
        <select id="select-conciliacion-sede">
          <option value="" ${conciliacionSedeSeleccionada === "" ? "selected" : ""}>Todas las sedes</option>
          ${sedes.map((s) => `<option value="${s.id}" ${String(s.id) === conciliacionSedeSeleccionada ? "selected" : ""}>${s.nombre}</option>`).join("")}
        </select>
      </label>
      <label class="filtro-campo">Grado
        <select id="select-conciliacion-grado">
          <option value="" ${conciliacionGradoSeleccionado === "" ? "selected" : ""}>Todos</option>
          ${NOMBRES_GRADOS.map(([n, nombre]) => `<option value="${n}" ${String(n) === conciliacionGradoSeleccionado ? "selected" : ""}>${nombre}</option>`).join("")}
        </select>
      </label>
    </div>

    <div class="resumen-reportes">
      <div class="metric-card"><span>SIMAC</span><strong>${r.resumen.total_simac}</strong></div>
      <div class="metric-card"><span>SAPRED</span><strong>${r.resumen.total_sapred}</strong></div>
      <div class="metric-card ok"><span>Coinciden</span><strong>${r.resumen.coinciden}</strong></div>
      <div class="metric-card ${r.resumen.solo_simac ? "alerta" : "ok"}"><span><span class=punto-rojo></span>Solo SIMAC</span><strong>${r.resumen.solo_simac}</strong></div>
      <div class="metric-card ${r.resumen.solo_sapred ? "alerta" : "ok"}"><span><span class=punto-naranja></span>Solo SAPRED</span><strong>${r.resumen.solo_sapred}</strong></div>
      <div class="metric-card ${r.resumen.diferencias ? "proceso" : "ok"}"><span><span class=punto-amarillo></span>Con diferencias</span><strong>${r.resumen.diferencias}</strong></div>
      <div class="metric-card ${r.resumen.candidatos_promocion_anticipada ? "alerta" : "ok"}" title="SAPRED ya lo tiene en un grado más alto que SIMAC: probablemente ya lo promovieron en la práctica y la matrícula no se actualizó"><span>Posible promoción anticipada</span><strong>${r.resumen.candidatos_promocion_anticipada}</strong></div>
      <div class="metric-card ${r.resumen.grupos_con_inconsistencias ? "alerta" : "ok"}"><span>Grupos pendientes</span><strong>${r.resumen.grupos_con_inconsistencias}</strong></div>
      <div class="metric-card ${r.resumen.docentes_pendientes ? "alerta" : "ok"}"><span>Docentes pendientes</span><strong>${r.resumen.docentes_pendientes}</strong></div>
    </div>

    <div class="barra-progreso-wrap">
      <div class="barra-progreso"><div class="barra-progreso-relleno" style="width:${r.resumen.calidad_pct}%; background:${colorCalidadConciliacion(r.resumen.calidad_pct)}"></div></div>
      <span class="barra-progreso-texto">Calidad de conciliación: ${r.resumen.calidad_pct}% de los registros coinciden</span>
    </div>

    <nav class="subnav-modulo no-imprimir" style="margin-top:18px">
      <button type="button" class="subnav-item ${conciliacionVista === "estudiantes" ? "activo" : ""}" data-vista-conciliacion="estudiantes">Estudiantes</button>
      <button type="button" class="subnav-item ${conciliacionVista === "grupos" ? "activo" : ""}" data-vista-conciliacion="grupos">Grado y grupo</button>
      <button type="button" class="subnav-item ${conciliacionVista === "docentes" ? "activo" : ""}" data-vista-conciliacion="docentes">Por docente</button>
      <button type="button" class="subnav-item ${conciliacionVista === "hallazgos" ? "activo" : ""}" data-vista-conciliacion="hallazgos"><i data-lucide=folder-open class=ico></i> Grilla — Promoción anticipada${r.resumen.candidatos_promocion_anticipada ? ` (${r.resumen.candidatos_promocion_anticipada})` : ""}</button>
    </nav>

    <div id="detalle-conciliacion">
      ${conciliacionVista === "estudiantes" ? htmlVistaEstudiantesConciliacion(filtrarEstudiantesConciliacion(r.estudiantes), docentesDisponibles) : ""}
      ${conciliacionVista === "grupos" ? htmlVistaGruposConciliacion(r.grupos) : ""}
      ${conciliacionVista === "docentes" ? htmlVistaDocentesConciliacion(r.docentes) : ""}
      ${conciliacionVista === "hallazgos" ? '<div class="estado-carga">Cargando hallazgos...</div>' : ""}
    </div>
    <div id="modal-diferencia-conciliacion"></div>
  `;

  vincularConciliacion(contenedor, sedes);
  if (conciliacionVista === "hallazgos") cargarYPintarHallazgos(contenedor, sedes);

  if (mantenerFocoBuscarConciliacion) {
    mantenerFocoBuscarConciliacion = false;
    const input = document.getElementById("buscar-conciliacion");
    input?.focus();
    input?.setSelectionRange(input.value.length, input.value.length);
  }
}

function filaEstudianteConciliacionHtml(e) {
  const acciones = [];
  if (e.estudiante_id) {
    acciones.push(`<button type="button" class="boton secundario" data-ver-estudiante-conciliacion="${e.estudiante_id}">Ver estudiante</button>`);
  }
  if (e.diferencias.length) {
    acciones.push(`<button type="button" class="boton secundario" data-ver-diferencia-conciliacion="${e.estudiante_id}">Ver diferencia</button>`);
  }
  return `<tr>
    <td>${e.nombre_completo}</td>
    <td>${e.documento}</td>
    <td>${e.nombre_grado}</td>
    <td>${e.nombre_grupo}</td>
    <td>${e.docente || "Sin asignar"}</td>
    <td>${badgeEstadoConciliacionHtml(e.estado_conciliacion)}${
      e.candidato_promocion_anticipada
        ? ' <span class="badge-estado alerta" title="SAPRED ya lo tiene en un grado más alto: corregir en la matrícula del siguiente año">Promoción anticipada</span>'
        : ""
    }</td>
    <td>${acciones.join(" ")}</td>
  </tr>`;
}

function htmlVistaEstudiantesConciliacion(estudiantes, docentesDisponibles) {
  return `
    <div class="buscador-principal no-imprimir">
      <span class="buscador-principal-icono" aria-hidden="true"><i data-lucide=search class=ico></i> </span>
      <input type="text" id="buscar-conciliacion" placeholder="Buscar por nombre o documento..." value="${conciliacionBusqueda}" />
    </div>
    <div class="barra-filtros no-imprimir">
      <label class="filtro-campo">Estado
        <select id="select-conciliacion-estado">
          <option value="problemas" ${conciliacionEstadoFiltro === "problemas" ? "selected" : ""}>Solo con problemas (oculta los que coinciden)</option>
          <option value="" ${conciliacionEstadoFiltro === "" ? "selected" : ""}>Todos (incluye los que coinciden)</option>
          <option value="coincide" ${conciliacionEstadoFiltro === "coincide" ? "selected" : ""}>Solo coincide</option>
          <option value="solo_simac" ${conciliacionEstadoFiltro === "solo_simac" ? "selected" : ""}>Solo SIMAC</option>
          <option value="solo_sapred" ${conciliacionEstadoFiltro === "solo_sapred" ? "selected" : ""}>Solo SAPRED</option>
          <option value="diferencia" ${conciliacionEstadoFiltro === "diferencia" ? "selected" : ""}>Diferencia</option>
          <option value="promocion_anticipada" ${conciliacionEstadoFiltro === "promocion_anticipada" ? "selected" : ""}>Posible promoción anticipada</option>
        </select>
      </label>
      <label class="filtro-campo">Director / docente
        <select id="select-conciliacion-docente">
          <option value="" ${conciliacionDocenteFiltro === "" ? "selected" : ""}>Todos</option>
          ${docentesDisponibles.map((d) => `<option value="${d}" ${d === conciliacionDocenteFiltro ? "selected" : ""}>${d}</option>`).join("")}
        </select>
      </label>
    </div>
    <p class="conteo-resultados no-imprimir">${estudiantes.length} estudiante(s)</p>
    ${
      estudiantes.length
        ? `<div class="tabla-scroll"><table>
             <thead><tr><th>Estudiante</th><th>Documento</th><th>Grado</th><th>Grupo</th><th>Director</th><th>Estado</th><th></th></tr></thead>
             <tbody>${estudiantes.map(filaEstudianteConciliacionHtml).join("")}</tbody>
           </table></div>`
        : `<div class="estado-vacio"><div class="estado-vacio-icono"><i data-lucide=check class=ico></i> </div><h3>Sin resultados para estos filtros</h3><p>Prueba cambiando el estado, el docente o la búsqueda.</p></div>`
    }
  `;
}

function htmlVistaGruposConciliacion(grupos) {
  if (!grupos.length) {
    return `<div class="estado-vacio"><div class="estado-vacio-icono"><i data-lucide=check class=ico></i> </div><h3>Sin grupos para este filtro</h3><p>Prueba cambiando la sede, el grado o el período.</p></div>`;
  }
  return `
    <p class="conteo-resultados no-imprimir">${grupos.length} grupo(s)</p>
    <div class="tabla-scroll"><table>
      <thead><tr><th>Sede</th><th>Grupo</th><th>Director</th><th>SIMAC</th><th>SAPRED</th><th>Coinciden</th><th>Faltantes</th><th>Estado</th></tr></thead>
      <tbody>
        ${grupos
          .map(
            (g) => `<tr>
          <td>${g.sede_nombre}</td>
          <td>${g.nombre_grupo}</td>
          <td>${g.docente || "Sin asignar"}</td>
          <td>${g.total_simac}</td>
          <td>${g.total_sapred}</td>
          <td>${g.coinciden}</td>
          <td>${g.solo_simac + g.solo_sapred + g.diferencias}</td>
          <td>${g.estado === "correcto" ? '<span class="badge-estado ok"><span class=punto-verde></span>Correcto</span>' : '<span class="badge-estado alerta"><span class=punto-rojo></span>Requiere revisión</span>'}</td>
        </tr>`
          )
          .join("")}
      </tbody>
    </table></div>
  `;
}

function htmlVistaDocentesConciliacion(docentes) {
  if (!docentes.length) {
    return `<div class="estado-vacio"><div class="estado-vacio-icono"><i data-lucide=check class=ico></i> </div><h3>Sin docentes para este filtro</h3><p>Prueba cambiando la sede, el grado o el período.</p></div>`;
  }
  return docentes
    .map(
      (d) => `
    <details class="seccion-colapsable" ${d.total_diferencias ? "open" : ""}>
      <summary>${d.nombre_completo}
        ${
          d.total_diferencias
            ? `<span class="badge-estado alerta">${d.total_diferencias} inconsistencia(s)</span>`
            : '<span class="badge-estado ok"><span class=punto-verde></span>Todo correcto</span>'
        }
      </summary>
      <div class="tabla-scroll"><table>
        <thead><tr><th>Sede</th><th>Grupo</th><th>SIMAC</th><th>SAPRED</th><th>Estado</th></tr></thead>
        <tbody>
          ${d.grupos
            .map(
              (g) => `<tr>
            <td>${g.sede_nombre}</td>
            <td>${g.nombre_grupo}</td>
            <td>${g.total_simac}</td>
            <td>${g.total_sapred}</td>
            <td>${g.estado === "correcto" ? '<span class="badge-estado ok"><span class=punto-verde></span>Correcto</span>' : '<span class="badge-estado alerta"><span class=punto-rojo></span>Requiere revisión</span>'}</td>
          </tr>`
            )
            .join("")}
        </tbody>
      </table></div>
    </details>`
    )
    .join("");
}

function abrirModalDiferenciaConciliacion(estudiante) {
  const contenedor = document.getElementById("modal-diferencia-conciliacion");
  const filas = estudiante.diferencias
    .map(
      (d) => `<tr>
        <td>${ETIQUETAS_CAMPO_DIFERENCIA[d.campo] || d.campo}</td>
        <td>${d.valor_simac}</td>
        <td>${d.valor_sapred}</td>
      </tr>`
    )
    .join("");
  contenedor.innerHTML = `
    <div class="modal-fondo">
      <div class="modal-caja">
        <h3 style="margin-top:0">${estudiante.nombre_completo}</h3>
        <p class="pendiente">Documento: ${estudiante.documento} · ${estudiante.nombre_grupo}</p>
        <table>
          <thead><tr><th>Dato</th><th>SIMAC</th><th>SAPRED</th></tr></thead>
          <tbody>${filas}</tbody>
        </table>
        <div class="toolbar" style="margin-top:14px; justify-content:flex-end">
          <button type="button" class="boton secundario" id="btn-cerrar-modal-diferencia">Cerrar</button>
        </div>
      </div>
    </div>
  `;
  document.getElementById("btn-cerrar-modal-diferencia").addEventListener("click", () => {
    contenedor.innerHTML = "";
  });
}

function vincularConciliacion(contenedor, sedes) {
  document.getElementById("btn-actualizar-conciliacion").addEventListener("click", () => {
    cargarYPintarConciliacion(contenedor, sedes);
  });
  document.getElementById("btn-exportar-conciliacion").addEventListener("click", async () => {
    // Fase 4A': la descarga la hace el navegador, no api(): si el token de
    // acceso venciera, aquí no habría forma de renovarlo ni de reintentar.
    await asegurarSesionFresca();
    window.location.href = `/api/reportes/conciliacion/exportar?${urlConciliacionParams()}`;
  });
  document.getElementById("check-presencia-incluir-coincide")?.addEventListener("change", (e) => {
    presenciaIncluirCoincide = e.target.checked;
  });
  document.getElementById("btn-presencia-pdf")?.addEventListener("click", async (ev) => {
    const btn = ev.currentTarget;
    const sedeNombre = conciliacionSedeSeleccionada
      ? (sedes.find((s) => String(s.id) === conciliacionSedeSeleccionada) || {}).nombre || ""
      : "Todas las sedes IETABA";
    btn.disabled = true;
    btn.textContent = "Generando PDF...";
    try {
      await descargarPdfPresencia({
        anio_lectivo: conciliacionAnio,
        periodo: conciliacionPeriodo,
        sede_id: conciliacionSedeSeleccionada ? Number(conciliacionSedeSeleccionada) : null,
        grado: conciliacionGradoSeleccionado ? Number(conciliacionGradoSeleccionado) : null,
        sede_nombre: sedeNombre,
        incluir_coincide: presenciaIncluirCoincide,
      });
    } catch (err) {
      alert(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "PDF de presencia (SIMAT/SAPRED)";
    }
  });
  document.getElementById("input-conciliacion-anio").addEventListener("change", (e) => {
    conciliacionAnio = Number(e.target.value) || conciliacionAnio;
    cargarYPintarConciliacion(contenedor, sedes);
  });
  document.getElementById("select-conciliacion-periodo").addEventListener("change", (e) => {
    conciliacionPeriodo = Number(e.target.value);
    cargarYPintarConciliacion(contenedor, sedes);
  });
  document.getElementById("select-conciliacion-sede").addEventListener("change", (e) => {
    conciliacionSedeSeleccionada = e.target.value;
    conciliacionDocenteFiltro = "";
    cargarYPintarConciliacion(contenedor, sedes);
  });
  document.getElementById("select-conciliacion-grado").addEventListener("change", (e) => {
    conciliacionGradoSeleccionado = e.target.value;
    cargarYPintarConciliacion(contenedor, sedes);
  });

  document.querySelectorAll("[data-vista-conciliacion]").forEach((btn) => {
    btn.addEventListener("click", () => {
      conciliacionVista = btn.dataset.vistaConciliacion;
      pintarConciliacion(contenedor, sedes);
    });
  });

  document.getElementById("select-conciliacion-estado")?.addEventListener("change", (e) => {
    conciliacionEstadoFiltro = e.target.value;
    pintarConciliacion(contenedor, sedes);
  });
  document.getElementById("select-conciliacion-docente")?.addEventListener("change", (e) => {
    conciliacionDocenteFiltro = e.target.value;
    pintarConciliacion(contenedor, sedes);
  });
  document.getElementById("buscar-conciliacion")?.addEventListener("input", (e) => {
    clearTimeout(temporizadorBuscarConciliacion);
    const valor = e.target.value;
    temporizadorBuscarConciliacion = setTimeout(() => {
      conciliacionBusqueda = valor;
      mantenerFocoBuscarConciliacion = true;
      pintarConciliacion(contenedor, sedes);
    }, 250);
  });

  document.querySelectorAll("[data-ver-estudiante-conciliacion]").forEach((btn) => {
    btn.addEventListener("click", () => abrirFicha(Number(btn.dataset.verEstudianteConciliacion), "reportes"));
  });
  document.querySelectorAll("[data-ver-diferencia-conciliacion]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.dataset.verDiferenciaConciliacion);
      const estudiante = conciliacionCache.estudiantes.find((e) => e.estudiante_id === id);
      if (estudiante) abrirModalDiferenciaConciliacion(estudiante);
    });
  });
}

// POST → blob → descarga. Mismo manejo de sesión que descargarPdfListaCupo().
async function descargarPdfPresencia(cuerpo) {
  const pedir = () =>
    fetch("/api/reportes/conciliacion/presencia/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    });
  await asegurarSesionFresca();
  let res = await pedir();
  if (res.status === 401 && (await _intentarRefresh())) res = await pedir();
  if (!res.ok) {
    const detalle = await res.json().catch(() => ({}));
    throw new Error(detalle.detail || `Error ${res.status} generando el PDF`);
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `presencia_simat_sapred_${fechaColombiaISO()}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

// --- Vista "Grilla" de Conciliación: historial persistente de casos de -----
// grado distinto SIMAC/SAPRED (hallazgos_conciliacion en el backend). A
// diferencia de las otras vistas (que solo leen el cálculo en vivo de
// conciliar()), esta SÍ guarda: un caso no desaparece porque se corrija el
// dato o se cambie de filtro, queda con fecha de detección, última vez
// visto, y quién/cuándo lo resolvió — para no perder de un año a otro a
// quién hay que hacerle una promoción anticipada en la matrícula.

async function cargarYPintarHallazgos(contenedor, sedes) {
  const destino = document.getElementById("detalle-conciliacion");
  const params = new URLSearchParams({
    anio_lectivo: conciliacionAnio,
    periodo: conciliacionPeriodo,
    incluir_resueltos: hallazgosIncluirResueltos ? "true" : "false",
  });
  if (conciliacionSedeSeleccionada) params.set("sede_id", conciliacionSedeSeleccionada);
  if (conciliacionGradoSeleccionado) params.set("grado", conciliacionGradoSeleccionado);
  let hallazgos;
  try {
    hallazgos = await api(`/api/reportes/conciliacion/hallazgos?${params}`);
  } catch (err) {
    destino.innerHTML = `<div class="alerta-caja">${err.message}</div>`;
    return;
  }
  pintarHallazgos(destino, contenedor, sedes, hallazgos);
}

function fechaCortaHallazgo(iso) {
  return new Date(iso).toLocaleDateString("es-CO");
}

function filaHallazgoHtml(h) {
  return `<tr class="${h.resuelto ? "hallazgo-fila-resuelta" : ""}">
    <td>${esc(h.nombre_completo)}</td>
    <td class="celda-nowrap">${esc(h.documento)}</td>
    <td class="celda-nowrap">${esc(h.sede_nombre)}</td>
    <td class="celda-nowrap">${esc(h.nombre_grupo_simac)}</td>
    <td class="celda-nowrap">${esc(h.nombre_grupo_sapred)}${
      h.es_promocion_anticipada ? ' <span class="badge-estado alerta"><i data-lucide=arrow-up class=ico></i> Promoción anticipada</span>' : ""
    }</td>
    <td class="celda-nowrap">${fechaCortaHallazgo(h.detectado_en)}</td>
    <td class="celda-nowrap">${fechaCortaHallazgo(h.visto_en)}</td>
    <td>${
      h.resuelto
        ? `<span class="badge-estado ok"><i data-lucide=check class=ico></i> Resuelto</span><br/><span class="pendiente">${esc(h.resuelto_por || "")} · ${fechaCortaHallazgo(h.resuelto_en)}${h.nota ? " · " + esc(h.nota) : ""}</span>`
        : `<span class="badge-estado alerta">Pendiente</span>`
    }</td>
    <td class="no-imprimir celda-nowrap">
      ${
        h.resuelto
          ? `<button type="button" class="boton secundario" data-reabrir-hallazgo="${h.id}"><i data-lucide=undo-2 class=ico></i> Reabrir</button>`
          : `<button type="button" class="boton secundario" data-resolver-hallazgo="${h.id}"><i data-lucide=check class=ico></i> Marcar resuelto</button>`
      }
    </td>
  </tr>`;
}

function htmlGradoHallazgos(grado, filas) {
  return `
    <p class="grupo" style="margin-top:16px">${nombreGradoLista(grado)} <span>(${filas.length})</span></p>
    <div class="tabla-scroll"><table>
      <thead><tr>
        <th>Nombre</th><th>Documento</th><th>Sede</th>
        <th>SIMAC dice</th><th>SAPRED dice</th>
        <th>Detectado</th><th>Visto por última vez</th>
        <th>Estado</th><th class="no-imprimir">Acciones</th>
      </tr></thead>
      <tbody>${filas.map(filaHallazgoHtml).join("")}</tbody>
    </table></div>
  `;
}

function pintarHallazgos(destino, contenedor, sedes, hallazgos) {
  const porGrado = new Map();
  hallazgos.forEach((h) => porGrado.set(h.grado_simac, [...(porGrado.get(h.grado_simac) || []), h]));
  const grados = [...porGrado.keys()].sort((a, b) => a - b);

  const sedeNombre = conciliacionSedeSeleccionada
    ? (sedes.find((s) => String(s.id) === conciliacionSedeSeleccionada) || {}).nombre || ""
    : "Todas las sedes IETABA";

  destino.innerHTML = `
    <div class="barra-filtros no-imprimir">
      <label class="check-linea filtro-check">
        <input type="checkbox" id="check-hallazgos-resueltos" ${hallazgosIncluirResueltos ? "checked" : ""} /> Incluir ya resueltos (historial completo)
      </label>
      <button type="button" class="boton" id="btn-hallazgos-pdf" ${hallazgos.length ? "" : "disabled"}><i data-lucide=file-text class=ico></i> Descargar PDF</button>
      <button type="button" class="boton secundario" onclick="window.print()"><i data-lucide=printer class=ico></i> Imprimir</button>
    </div>
    <div class="hoja-imprimir">
      <h2 style="margin:6px 0">Casos de grado distinto entre SIMAC y SAPRED</h2>
      <p class="pendiente">Esta grilla se guarda aunque se corrija el dato o se cambie de filtro: queda como historial, con cuándo se detectó cada caso y quién lo resolvió — para no perder de un año a otro a quién hay que promoverle el grado en la próxima matrícula.</p>
      ${
        !hallazgos.length
          ? `<div class="estado-vacio"><div class="estado-vacio-icono"><i data-lucide=check class=ico></i> </div><h3>No hay casos ${hallazgosIncluirResueltos ? "" : "pendientes "}para este filtro</h3></div>`
          : grados.map((g) => htmlGradoHallazgos(g, porGrado.get(g))).join("")
      }
    </div>
  `;
  vincularHallazgos(destino, contenedor, sedes, hallazgos, sedeNombre);
}

// POST → blob → descarga. Mismo manejo de sesión que descargarPdfListaCupo().
async function descargarPdfHallazgos(cuerpo) {
  const pedir = () =>
    fetch("/api/reportes/conciliacion/hallazgos/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    });
  await asegurarSesionFresca();
  let res = await pedir();
  if (res.status === 401 && (await _intentarRefresh())) res = await pedir();
  if (!res.ok) {
    const detalle = await res.json().catch(() => ({}));
    throw new Error(detalle.detail || `Error ${res.status} generando el PDF`);
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `diferencias_grado_simat_sapred_${fechaColombiaISO()}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

function vincularHallazgos(destino, contenedor, sedes, hallazgos, sedeNombre) {
  document.getElementById("check-hallazgos-resueltos")?.addEventListener("change", (e) => {
    hallazgosIncluirResueltos = e.target.checked;
    cargarYPintarHallazgos(contenedor, sedes);
  });
  document.getElementById("btn-hallazgos-pdf")?.addEventListener("click", async (ev) => {
    const btn = ev.currentTarget;
    btn.disabled = true;
    btn.textContent = "Generando PDF...";
    try {
      await descargarPdfHallazgos({
        ids: hallazgos.map((h) => h.id),
        anio_lectivo: conciliacionAnio,
        periodo: conciliacionPeriodo,
        sede_nombre: sedeNombre,
        incluir_resueltos: hallazgosIncluirResueltos,
      });
    } catch (err) {
      alert(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Descargar PDF";
    }
  });
  destino.querySelectorAll("[data-resolver-hallazgo]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const nota = prompt('Nota (opcional) — ej. "corregido en la matrícula 2027":', "") ?? "";
      const resuelto_por = (typeof sesionActual !== "undefined" && sesionActual?.usuario?.nombre) || "";
      btn.disabled = true;
      try {
        await api(`/api/reportes/conciliacion/hallazgos/${btn.dataset.resolverHallazgo}/resolver`, {
          method: "POST",
          body: JSON.stringify({ resuelto_por, nota: nota || null }),
        });
      } catch (err) {
        alert(err.message);
      }
      cargarYPintarHallazgos(contenedor, sedes);
    })
  );
  destino.querySelectorAll("[data-reabrir-hallazgo]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        await api(`/api/reportes/conciliacion/hallazgos/${btn.dataset.reabrirHallazgo}/reabrir`, { method: "POST" });
      } catch (err) {
        alert(err.message);
      }
      cargarYPintarHallazgos(contenedor, sedes);
    })
  );
}
