// --- Vista: Resultados ICFES (Saber 11) entre años -------------------------
//
// Tres subvistas:
//  - Resumen: cómo le ha ido al colegio año tras año (puntaje global, cada
//    prueba, niveles de desempeño) y en palabras dónde mejoró y dónde empeoró.
//  - Estudiantes: la lista de un año, con puesto y prueba más débil.
//  - Ficha: un estudiante frente al promedio del colegio en su año.
//
// Datos: /api/icfes/panorama, /api/icfes/anios/{a}/estudiantes y
// /api/icfes/resultados/{id} (ver backend app/icfes.py). Los carga
// backend/importar_icfes.py desde PRISMA. Los años con muy pocos estudiantes
// (validantes, pruebas tardías) se muestran pero no se comparan.

let icVista = "resumen"; // resumen | estudiantes | ficha
let icAnio = null;
let icResultadoId = null;
let icMedida = "promedio"; // promedio | percentil (gráfica por prueba)
let icPruebaNiveles = "mat";
let icBuscar = "";
let icOrden = "puesto";
let icPanorama = null;
let icCharts = [];

// Series en orden fijo (validado con el verificador de paletas, modo claro):
// una prueba siempre tiene el mismo color en todas las gráficas.
const IC_COLOR_PRUEBA = { lc: "#2a78d6", mat: "#eb6834", syc: "#1baf7a", cn: "#eda100", ing: "#e87ba4" };
// Niveles: naranja por debajo, azul por encima (misma escala que Análisis académico).
const IC_COLOR_NIVEL_4 = ["#c2410c", "#eda067", "#93b7ec", "#1d4ed8"];
const IC_COLOR_NIVEL_5 = ["#c2410c", "#eda067", "#c9d8f0", "#93b7ec", "#1d4ed8"];
const IC_TINTA_NIVEL_4 = ["#ffffff", "#172033", "#172033", "#ffffff"];
const IC_TINTA_NIVEL_5 = ["#ffffff", "#172033", "#172033", "#172033", "#ffffff"];

function icDestruirCharts() {
  icCharts.forEach((c) => c.destroy());
  icCharts = [];
}

const icF = (v, d = 1) => (v === null || v === undefined ? "—" : Number(v).toFixed(d));
const icS = (v, d = 1) => (v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(d)}`);

function icPrueba(codigo) {
  return icPanorama?.pruebas.find((p) => p.codigo === codigo);
}

function icColorNivel(codigo, nivel) {
  const niveles = icPrueba(codigo)?.niveles || [];
  const i = niveles.indexOf(nivel);
  if (i < 0) return null;
  return niveles.length === 5
    ? { fondo: IC_COLOR_NIVEL_5[i], tinta: IC_TINTA_NIVEL_5[i] }
    : { fondo: IC_COLOR_NIVEL_4[i], tinta: IC_TINTA_NIVEL_4[i] };
}

function icNombreNivel(codigo, nivel) {
  if (!nivel) return "—";
  return codigo === "ing" ? nivel : `Nivel ${nivel}`;
}

function icCambioHtml(delta, tendencia, umbral) {
  if (delta === null || delta === undefined) return '<span class="ic-cambio">—</span>';
  const clase = tendencia === "mejoro" ? "sube" : tendencia === "empeoro" ? "baja" : "igual";
  const ico = tendencia === "mejoro" ? "trending-up" : tendencia === "empeoro" ? "trending-down" : "minus";
  const txt = tendencia === "mejoro" ? "mejoró" : tendencia === "empeoro" ? "empeoró" : "estable";
  return `<span class="ic-cambio ${clase}" title="Cambios menores a ${umbral} puntos se consideran estables">${icono(ico)} ${icS(delta)} <span class="ic-cambio-txt">${txt}</span></span>`;
}

// --- Entrada ----------------------------------------------------------------

async function renderIcfes() {
  icDestruirCharts();
  app.innerHTML = '<p class="estado-carga">Cargando resultados ICFES...</p>';
  try {
    icPanorama = await api("/api/icfes/panorama");
  } catch (e) {
    app.innerHTML = `<div class="alerta-caja">${
      e.status === 401 || e.status === 403 ? "No tienes permiso para ver esta sección." : "No se pudieron cargar los resultados ICFES: " + esc(e.message)
    }</div>`;
    return;
  }

  const cab = `
    <div class="pagina-header">
      <div>
        <h1>Resultados ICFES</h1>
        <p class="subtitulo-pagina">Pruebas Saber 11 del colegio año por año: dónde mejoramos, dónde empeoramos y cómo le fue a cada estudiante. Datos publicados por el ICFES en PRISMA.</p>
      </div>
    </div>`;

  if (!icPanorama.anios.length) {
    app.innerHTML = `${cab}
      <div class="ox-vacio">
        <p><b>Todavía no se han traído resultados del ICFES.</b></p>
        <p>En el computador del servidor, desde la carpeta <code>backend</code>, ejecute
        <code>python importar_icfes.py</code> e ingrese el usuario y la clave de PRISMA.</p>
      </div>`;
    return;
  }
  const anios = icPanorama.anios.map((a) => a.anio);
  if (!anios.includes(icAnio)) {
    const comparables = icPanorama.anios.filter((a) => a.comparable);
    icAnio = (comparables.length ? comparables : icPanorama.anios).at(-1).anio;
  }

  app.innerHTML = `${cab}
    <div class="segmentado anz-subnav" role="group" aria-label="Sección">
      ${[["resumen", "Resumen general"], ["estudiantes", "Estudiantes por año"], ["ficha", "Ficha individual"]]
        .map(([id, n]) => `<button type="button" class="segmentado-btn ${icVista === id ? "activo" : ""}" data-ic-vista="${id}" aria-pressed="${icVista === id}">${n}</button>`)
        .join("")}
    </div>
    <div id="ic-contenido" aria-live="polite"></div>`;

  app.querySelectorAll("[data-ic-vista]").forEach((b) =>
    b.addEventListener("click", () => {
      icVista = b.dataset.icVista;
      renderIcfes();
    })
  );
  if (icVista === "resumen") icPintarResumen();
  else if (icVista === "estudiantes") await icPintarEstudiantes();
  else await icPintarFicha();
}

function icIrA(vista, cambios = {}) {
  if ("anio" in cambios) icAnio = cambios.anio;
  if ("resultado" in cambios) icResultadoId = cambios.resultado;
  icVista = vista;
  renderIcfes().then(() => window.scrollTo(0, 0));
}

// --- Resumen general -------------------------------------------------------

function icPintarResumen() {
  const host = document.getElementById("ic-contenido");
  const P = icPanorama;
  const comparables = P.anios.filter((a) => a.comparable);
  const ult = comparables.at(-1);
  const cambio = P.cambios.at(-1);
  const ICONO_H = { mejoro: "trending-up", empeoro: "trending-down", estable: "minus", atencion: "alert-triangle", info: "info" };

  const hallazgos = P.hallazgos.length
    ? `<ul class="ic-hallazgos">${P.hallazgos.map((h) => `<li class="ic-hallazgo ${h.tipo}">${icono(ICONO_H[h.tipo] || "info")}<span>${esc(h.texto)}</span></li>`).join("")}</ul>`
    : "";

  let kpis = "";
  if (ult) {
    const conPct = P.pruebas.map((p) => [p, ult.pruebas[p.codigo]]).filter(([, v]) => v.percentil !== null);
    const fuerte = conPct.length ? conPct.reduce((a, b) => (b[1].percentil > a[1].percentil ? b : a)) : null;
    const debil = conPct.length ? conPct.reduce((a, b) => (b[1].percentil < a[1].percentil ? b : a)) : null;
    kpis = `<div class="anz-kpis">
      <div class="anz-kpi">
        <span class="anz-kpi-etq">Puntaje global promedio ${ult.anio} ${iconoAyuda("Promedio del puntaje global (0 a 500) de todos los estudiantes del colegio que presentaron la prueba ese año.")}</span>
        <b class="anz-kpi-valor">${icF(ult.global)}</b>
        <span class="anz-kpi-sub">${ult.n} estudiantes · de 0 a 500</span>
        ${cambio ? `<span class="anz-kpi-explica">Frente a ${cambio.desde}: ${icCambioHtml(cambio.global.delta, cambio.global.tendencia, P.umbrales.global)}</span>` : ""}
      </div>
      ${fuerte ? `<div class="anz-kpi">
        <span class="anz-kpi-etq">Prueba más fuerte frente al país ${iconoAyuda("Percentil nacional promedio: en promedio, nuestros estudiantes superan a ese porcentaje de los estudiantes del país en esa prueba.")}</span>
        <b class="anz-kpi-valor">${esc(fuerte[0].nombre)}</b>
        <span class="anz-kpi-explica">El estudiante típico supera al <b>${icF(fuerte[1].percentil, 0)}%</b> del país.</span>
      </div>` : ""}
      ${debil ? `<div class="anz-kpi">
        <span class="anz-kpi-etq">Prueba más débil frente al país</span>
        <b class="anz-kpi-valor">${esc(debil[0].nombre)}</b>
        <span class="anz-kpi-explica">El estudiante típico supera solo al <b>${icF(debil[1].percentil, 0)}%</b> del país; ${debil[1].pct_nivel_bajo}% quedó en el nivel más bajo.</span>
      </div>` : ""}
    </div>`;
  }

  const excluidos = P.excluidos.length
    ? `<p class="ic-nota">${icono("info")} No se comparan (muy pocos estudiantes, normalmente pruebas tardías o validantes):
       ${P.excluidos.map((e) => `${e.anio} (${e.n})`).join(", ")}. Mínimo para comparar: ${P.umbrales.min_estudiantes} estudiantes.</p>`
    : "";

  host.innerHTML = `
    ${hallazgos}
    ${kpis}
    <section class="ic-bloque">
      <h2>¿Cómo ha evolucionado el puntaje global?</h2>
      <p class="ic-bloque-desc">Promedio del colegio cada año (escala 0 a 500). Pase el mouse por un punto para ver el detalle.</p>
      <div class="ic-grafica"><canvas id="ic-chart-global" aria-label="Puntaje global promedio por año" role="img"></canvas></div>
    </section>
    <section class="ic-bloque">
      <div class="ic-bloque-cab">
        <div>
          <h2>¿En qué pruebas mejoramos y en cuáles empeoramos?</h2>
          <p class="ic-bloque-desc">${icMedida === "promedio"
            ? "Puntaje promedio de cada prueba (0 a 100)."
            : "Percentil nacional promedio: a qué porcentaje del país supera el estudiante típico. Sirve para comparar años aunque la prueba cambie de dificultad."}</p>
        </div>
        <div class="segmentado" role="group" aria-label="Medida">
          <button type="button" class="segmentado-btn ${icMedida === "promedio" ? "activo" : ""}" data-ic-medida="promedio">Puntaje</button>
          <button type="button" class="segmentado-btn ${icMedida === "percentil" ? "activo" : ""}" data-ic-medida="percentil">Frente al país</button>
        </div>
      </div>
      <div class="ic-grafica ic-grafica-alta"><canvas id="ic-chart-pruebas" aria-label="Promedio por prueba y año" role="img"></canvas></div>
      ${icTablaAniosHtml(comparables)}
    </section>
    <section class="ic-bloque">
      <div class="ic-bloque-cab">
        <div>
          <h2>¿Cuántos estudiantes quedan en cada nivel de desempeño?</h2>
          <p class="ic-bloque-desc">Porcentaje de estudiantes por nivel del ICFES en cada año. Lo ideal es que la franja naranja (niveles bajos) se achique.</p>
        </div>
        <label class="ic-select">Prueba
          <select id="ic-prueba-niveles">${P.pruebas.map((p) => `<option value="${p.codigo}" ${p.codigo === icPruebaNiveles ? "selected" : ""}>${esc(p.nombre)}</option>`).join("")}</select>
        </label>
      </div>
      <div class="ic-grafica"><canvas id="ic-chart-niveles" aria-label="Distribución por niveles de desempeño" role="img"></canvas></div>
    </section>
    ${excluidos}`;

  host.querySelectorAll("[data-ic-medida]").forEach((b) => b.addEventListener("click", () => { icMedida = b.dataset.icMedida; icDestruirCharts(); icPintarResumen(); }));
  host.querySelector("#ic-prueba-niveles").addEventListener("change", (e) => { icPruebaNiveles = e.target.value; icDestruirCharts(); icPintarResumen(); });
  host.querySelectorAll("[data-ic-anio]").forEach((el) => el.addEventListener("click", () => icIrA("estudiantes", { anio: Number(el.dataset.icAnio) })));

  icChartGlobal(comparables);
  icChartPruebas(comparables);
  icChartNiveles(comparables);
}

function icTablaAniosHtml(comparables) {
  const P = icPanorama;
  const cambioDe = (anio) => P.cambios.find((c) => c.hasta === anio);
  const filas = comparables.slice().reverse().map((a) => {
    const c = cambioDe(a.anio);
    const celdas = P.pruebas.map((p) => {
      const v = a.pruebas[p.codigo];
      const cp = c?.pruebas[p.codigo];
      const valor = icMedida === "promedio" ? icF(v.promedio) : `${icF(v.percentil, 0)}%`;
      const delta = icMedida === "promedio" ? cp?.delta : cp?.delta_percentil;
      return `<td><b>${valor}</b>${cp ? `<br>${icCambioHtml(delta, icMedida === "promedio" ? cp.tendencia : delta >= P.umbrales.prueba ? "mejoro" : delta <= -P.umbrales.prueba ? "empeoro" : "estable", P.umbrales.prueba)}` : ""}</td>`;
    }).join("");
    return `<tr>
      <th scope="row"><button type="button" class="ic-link" data-ic-anio="${a.anio}" title="Ver estudiantes de ${a.anio}">${a.anio}</button></th>
      <td>${a.n}</td>
      <td><b>${icF(a.global)}</b>${c ? `<br>${icCambioHtml(c.global.delta, c.global.tendencia, P.umbrales.global)}` : ""}</td>
      ${celdas}
    </tr>`;
  }).join("");
  return `<div class="tabla-scroll"><table class="ox-tabla anz-tabla ic-tabla-anios">
    <thead><tr><th>Año</th><th>Estudiantes</th><th>Global</th>${P.pruebas.map((p) => `<th><span class="ic-punto" style="background:${IC_COLOR_PRUEBA[p.codigo]}"></span>${esc(p.nombre)}</th>`).join("")}</tr></thead>
    <tbody>${filas}</tbody>
  </table></div>
  <p class="ic-nota">El cambio se compara con el año anterior que tenga datos. Diferencias menores a ${P.umbrales.prueba} punto por prueba (o ${P.umbrales.global} en el global) se consideran estables. Clic en un año para ver sus estudiantes.</p>`;
}

const IC_EJE = { grid: { color: "#eef0f3" }, border: { display: false }, ticks: { color: "#667085" } };

function icChartGlobal(comparables) {
  const c = document.getElementById("ic-chart-global");
  if (!c || !comparables.length) return;
  const valores = comparables.map((a) => a.global);
  const etiquetas = {
    id: "icEtiquetas",
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      ctx.save();
      ctx.font = "600 12px Inter, system-ui, sans-serif";
      ctx.fillStyle = "#172033";
      ctx.textAlign = "center";
      chart.getDatasetMeta(0).data.forEach((pt, i) => valores[i] !== null && ctx.fillText(valores[i].toFixed(1), pt.x, pt.y - 12));
      ctx.restore();
    },
  };
  icCharts.push(new Chart(c, {
    type: "line",
    data: { labels: comparables.map((a) => a.anio), datasets: [{ data: valores, borderColor: "#1d4ed8", backgroundColor: "#1d4ed8", borderWidth: 2, pointRadius: 5, pointHoverRadius: 7, pointBorderColor: "#fff", pointBorderWidth: 2, tension: 0 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      layout: { padding: { top: 24, right: 16 } },
      interaction: { mode: "nearest", axis: "x", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false,
          callbacks: {
            title: (it) => `Saber 11 de ${comparables[it[0].dataIndex].anio}`,
            label: (it) => {
              const a = comparables[it.dataIndex];
              return [`Puntaje global promedio: ${icF(a.global)}`, `Estudiantes: ${a.n}`, `Más alto: ${a.global_max} · más bajo: ${a.global_min}`];
            },
          },
        },
      },
      scales: { y: { ...IC_EJE, grace: "10%" }, x: { offset: true, grid: { display: false }, ticks: { color: "#344054", font: { weight: 600 } } } },
    },
    plugins: [etiquetas],
  }));
}

function icChartPruebas(comparables) {
  const c = document.getElementById("ic-chart-pruebas");
  if (!c || !comparables.length) return;
  const P = icPanorama;
  const campo = icMedida === "promedio" ? "promedio" : "percentil";
  // En pantallas angostas los nombres al final de cada línea aplastan la gráfica: queda solo la leyenda.
  const angosto = c.parentElement.clientWidth < 560;
  // Nombre de la prueba al final de cada línea (identidad sin depender solo del color)
  const finLinea = {
    id: "icFinLinea",
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      ctx.save();
      ctx.font = "600 11.5px Inter, system-ui, sans-serif";
      ctx.fillStyle = "#344054";
      ctx.textAlign = "left";
      const usados = [];
      chart.data.datasets.forEach((ds, i) => {
        const meta = chart.getDatasetMeta(i);
        if (meta.hidden) return;
        const pt = [...meta.data].reverse().find((p, j) => ds.data[ds.data.length - 1 - j] !== null);
        if (!pt) return;
        let y = pt.y;
        while (usados.some((u) => Math.abs(u - y) < 13)) y += 13;
        usados.push(y);
        ctx.fillText(ds.label, pt.x + 10, y + 4);
      });
      ctx.restore();
    },
  };
  icCharts.push(new Chart(c, {
    type: "line",
    data: {
      labels: comparables.map((a) => a.anio),
      datasets: P.pruebas.map((p) => ({
        label: p.nombre,
        data: comparables.map((a) => a.pruebas[p.codigo][campo]),
        borderColor: IC_COLOR_PRUEBA[p.codigo], backgroundColor: IC_COLOR_PRUEBA[p.codigo],
        borderWidth: 2, pointRadius: 4, pointHoverRadius: 6, pointBorderColor: "#fff", pointBorderWidth: 2, tension: 0, spanGaps: true,
      })),
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      layout: { padding: { right: angosto ? 8 : 150, top: 8 } },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8, color: "#344054" } },
        tooltip: {
          callbacks: {
            title: (it) => `Saber 11 de ${it[0].label}`,
            label: (it) => `${it.dataset.label}: ${icMedida === "promedio" ? icF(it.raw) : `supera al ${icF(it.raw, 0)}% del país`}`,
          },
        },
      },
      scales: {
        y: { ...IC_EJE, grace: "8%", ticks: { ...IC_EJE.ticks, callback: (v) => (icMedida === "promedio" ? v : `${v}%`) } },
        x: { offset: true, grid: { display: false }, ticks: { color: "#344054", font: { weight: 600 } } },
      },
    },
    plugins: angosto ? [] : [finLinea],
  }));
}

function icChartNiveles(comparables) {
  const c = document.getElementById("ic-chart-niveles");
  if (!c || !comparables.length) return;
  const p = icPrueba(icPruebaNiveles);
  icCharts.push(new Chart(c, {
    type: "bar",
    data: {
      labels: comparables.map((a) => a.anio),
      datasets: p.niveles.map((n) => {
        const col = icColorNivel(p.codigo, n);
        return {
          label: icNombreNivel(p.codigo, n),
          data: comparables.map((a) => a.pruebas[p.codigo].niveles[n]),
          backgroundColor: col.fondo, borderColor: "#ffffff", borderWidth: { top: 0, bottom: 0, left: 0, right: 2 }, borderSkipped: false,
          tinta: col.tinta,
        };
      }),
    },
    options: {
      indexAxis: "y", responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, color: "#344054" } },
        tooltip: { callbacks: { label: (it) => `${it.dataset.label}: ${it.raw}%` } },
      },
      scales: {
        x: { stacked: true, max: 100, ...IC_EJE, ticks: { ...IC_EJE.ticks, callback: (v) => `${v}%` } },
        y: { stacked: true, grid: { display: false }, ticks: { color: "#344054", font: { weight: 600 } } },
      },
    },
    plugins: [{
      id: "icPctEnBarra",
      afterDatasetsDraw(chart) {
        const { ctx } = chart;
        ctx.save();
        ctx.font = "600 11px Inter, system-ui, sans-serif";
        ctx.textAlign = "center";
        chart.data.datasets.forEach((ds, i) => chart.getDatasetMeta(i).data.forEach((bar, j) => {
          const v = ds.data[j];
          if (!v || bar.width < 26) return;
          ctx.fillStyle = ds.tinta;
          ctx.fillText(`${v}%`, bar.x - bar.width / 2, bar.y + 4);
        }));
        ctx.restore();
      },
    }],
  }));
  c.parentElement.style.height = `${Math.max(180, comparables.length * 34 + 70)}px`;
}

// --- Estudiantes por año -----------------------------------------------------

async function icPintarEstudiantes() {
  const host = document.getElementById("ic-contenido");
  host.innerHTML = '<p class="estado-carga">Cargando estudiantes...</p>';
  let datos;
  try {
    datos = await api(`/api/icfes/anios/${icAnio}/estudiantes`);
  } catch (e) {
    host.innerHTML = `<div class="alerta-caja">No se pudo cargar la lista: ${esc(e.message)}</div>`;
    return;
  }
  const P = icPanorama;
  const r = datos.resumen;

  const selector = `<div class="segmentado ic-anios" role="group" aria-label="Año">${P.anios
    .map((a) => `<button type="button" class="segmentado-btn ${a.anio === icAnio ? "activo" : ""}" data-ic-anio="${a.anio}">${a.anio} <span class="segmentado-num">${a.n}</span></button>`)
    .join("")}</div>`;

  const pintarTabla = () => {
    const q = normalizarTexto(icBuscar);
    let lista = datos.estudiantes.filter((e) => !q || normalizarTexto(e.nombre).includes(q) || e.registro.toLowerCase().includes(q));
    if (icOrden === "nombre") lista = lista.slice().sort((a, b) => a.nombre.localeCompare(b.nombre));
    else if (icOrden.startsWith("p:")) {
      const p = icOrden.slice(2);
      lista = lista.slice().sort((a, b) => (b.pruebas[p].puntaje ?? -1) - (a.pruebas[p].puntaje ?? -1));
    }
    const celdaPrueba = (e, p) => {
      const v = e.pruebas[p.codigo];
      if (v.puntaje === null) return '<td class="ic-celda-nivel">—</td>';
      const col = icColorNivel(p.codigo, v.nivel);
      return `<td class="ic-celda-nivel"><span class="ic-chip-nivel" style="background:${col.fondo};color:${col.tinta}" title="${icNombreNivel(p.codigo, v.nivel)} · percentil nacional ${v.percentil ?? "—"}">${v.puntaje}</span></td>`;
    };
    document.getElementById("ic-tabla-est").innerHTML = lista.length
      ? `<div class="tabla-scroll"><table class="ox-tabla anz-tabla ic-tabla-est">
        <thead><tr>
          <th><button type="button" class="ic-orden ${icOrden === "puesto" ? "activo" : ""}" data-ic-orden="puesto">Puesto</button></th>
          <th><button type="button" class="ic-orden ${icOrden === "nombre" ? "activo" : ""}" data-ic-orden="nombre">Estudiante</button></th>
          <th>Global</th>
          ${P.pruebas.map((p) => `<th><button type="button" class="ic-orden ${icOrden === "p:" + p.codigo ? "activo" : ""}" data-ic-orden="p:${p.codigo}" title="Ordenar por ${esc(p.nombre)}">${p.codigo.toUpperCase()}</button></th>`).join("")}
          <th>Más débil</th>
        </tr></thead>
        <tbody>${lista.map((e) => `<tr class="ic-fila" data-ic-resultado="${e.id}" tabindex="0">
          <td>${e.puesto ?? "—"}</td>
          <td><b>${esc(e.nombre)}</b><br><span class="ic-sub">${esc(e.registro)}${e.periodo ? ` · período ${e.periodo}` : ""}</span></td>
          <td><b>${e.puntaje_global ?? "—"}</b></td>
          ${P.pruebas.map((p) => celdaPrueba(e, p)).join("")}
          <td>${e.mas_debil ? esc(icPrueba(e.mas_debil).nombre) : "—"}</td>
        </tr>`).join("")}</tbody>
      </table></div>`
      : '<p class="ox-vacio-chico">Nadie coincide con la búsqueda.</p>';
    document.querySelectorAll("[data-ic-orden]").forEach((b) => b.addEventListener("click", () => { icOrden = b.dataset.icOrden; pintarTabla(); }));
    document.querySelectorAll("[data-ic-resultado]").forEach((tr) => {
      const abrir = () => icIrA("ficha", { resultado: Number(tr.dataset.icResultado) });
      tr.addEventListener("click", abrir);
      tr.addEventListener("keydown", (ev) => ev.key === "Enter" && abrir());
    });
  };

  const leyenda = P.pruebas.slice(0, 1).concat(P.pruebas.filter((p) => p.codigo === "ing")).map((p) =>
    `<span class="ic-leyenda-grupo">${p.codigo === "ing" ? "Inglés:" : "Demás pruebas:"} ${p.niveles.map((n) => {
      const col = icColorNivel(p.codigo, n);
      return `<span class="ic-chip-nivel" style="background:${col.fondo};color:${col.tinta}">${icNombreNivel(p.codigo, n)}</span>`;
    }).join(" ")}</span>`).join("");

  host.innerHTML = `
    ${selector}
    ${!r.comparable ? `<p class="ic-nota">${icono("info")} En ${r.anio} solo hay ${r.n} estudiante(s): no se usa en las comparaciones entre años.</p>` : ""}
    <div class="anz-kpis">
      <div class="anz-kpi"><span class="anz-kpi-etq">Estudiantes ${r.anio}</span><b class="anz-kpi-valor">${r.n}</b><span class="anz-kpi-sub">períodos de aplicación: ${r.periodos.join(", ")}</span></div>
      <div class="anz-kpi"><span class="anz-kpi-etq">Puntaje global promedio</span><b class="anz-kpi-valor">${icF(r.global)}</b><span class="anz-kpi-sub">más alto ${r.global_max ?? "—"} · más bajo ${r.global_min ?? "—"}</span></div>
      <div class="anz-kpi"><span class="anz-kpi-etq">Promedio por prueba</span>
        <span class="ic-mini-pruebas">${P.pruebas.map((p) => `<span><span class="ic-punto" style="background:${IC_COLOR_PRUEBA[p.codigo]}"></span>${p.codigo.toUpperCase()} <b>${icF(r.pruebas[p.codigo].promedio)}</b></span>`).join("")}</span>
      </div>
    </div>
    <div class="ic-barra-est">
      <input type="search" id="ic-buscar" placeholder="Buscar por nombre o número de registro" value="${esc(icBuscar)}" aria-label="Buscar estudiante">
      <div class="ic-leyenda">${leyenda}</div>
    </div>
    <div id="ic-tabla-est"></div>
    <p class="ic-nota">El color de cada puntaje es su nivel de desempeño del ICFES. "Más débil" es la prueba en la que el estudiante queda más por debajo del promedio del colegio. Clic en un estudiante para ver su ficha.</p>`;

  host.querySelectorAll(".ic-anios [data-ic-anio]").forEach((b) => b.addEventListener("click", () => { icAnio = Number(b.dataset.icAnio); icPintarEstudiantes(); }));
  host.querySelector("#ic-buscar").addEventListener("input", (e) => { icBuscar = e.target.value; pintarTabla(); });
  pintarTabla();
}

// --- Ficha individual --------------------------------------------------------

async function icPintarFicha() {
  const host = document.getElementById("ic-contenido");
  if (!icResultadoId) {
    host.innerHTML = `<div class="ox-vacio"><p><b>Elija un estudiante.</b></p>
      <p>Vaya a <button type="button" class="ic-link" data-ic-ir-est>Estudiantes por año</button> y haga clic en un nombre.</p></div>`;
    host.querySelector("[data-ic-ir-est]").addEventListener("click", () => icIrA("estudiantes"));
    return;
  }
  host.innerHTML = '<p class="estado-carga">Cargando ficha...</p>';
  let f;
  try {
    f = await api(`/api/icfes/resultados/${icResultadoId}`);
  } catch (e) {
    host.innerHTML = `<div class="alerta-caja">No se pudo cargar la ficha: ${esc(e.message)}</div>`;
    return;
  }
  const P = icPanorama;
  const conDif = P.pruebas.filter((p) => f.comparacion[p.codigo].diferencia !== null);
  const fuertes = conDif.filter((p) => f.comparacion[p.codigo].diferencia >= 3).map((p) => p.nombre);
  const debiles = conDif.filter((p) => f.comparacion[p.codigo].diferencia <= -3).map((p) => p.nombre);
  const bajos = P.pruebas.filter((p) => f.pruebas[p.codigo].nivel === p.nivel_bajo).map((p) => p.nombre);
  const difGlobal = f.puntaje_global !== null && f.colegio_global !== null ? f.puntaje_global - f.colegio_global : null;

  const lectura = [
    difGlobal !== null
      ? `Su puntaje global (${f.puntaje_global}) está ${Math.abs(difGlobal).toFixed(1)} puntos ${difGlobal >= 0 ? "por encima" : "por debajo"} del promedio del colegio en ${f.anio} (${icF(f.colegio_global)}); quedó en el puesto ${f.puesto} de ${f.total_anio}.`
      : null,
    fuertes.length ? `Le fue mejor que al promedio del colegio en: ${fuertes.join(", ")}.` : null,
    debiles.length ? `Quedó por debajo del promedio del colegio en: ${debiles.join(", ")}.` : null,
    bajos.length ? `Quedó en el nivel más bajo del ICFES en: ${bajos.join(", ")}.` : null,
  ].filter(Boolean);

  host.innerHTML = `
    <div class="ic-ficha-cab">
      <button type="button" class="boton secundario" data-ic-volver>${icono("arrow-left")} Volver a ${f.anio}</button>
      <div>
        <h2>${esc(f.nombre)}</h2>
        <p class="ic-sub">Saber 11 de ${f.anio} · período ${f.periodo} · registro ${esc(f.registro)}
          ${f.estudiante_id ? ` · <button type="button" class="ic-link" data-ic-ficha-est="${f.estudiante_id}">ver ficha del estudiante</button>` : ""}</p>
      </div>
    </div>
    <div class="anz-kpis">
      <div class="anz-kpi"><span class="anz-kpi-etq">Puntaje global</span><b class="anz-kpi-valor">${f.puntaje_global ?? "—"}</b><span class="anz-kpi-sub">promedio del colegio: ${icF(f.colegio_global)}</span></div>
      <div class="anz-kpi"><span class="anz-kpi-etq">Puesto en el colegio</span><b class="anz-kpi-valor">${f.puesto ?? "—"}<small> de ${f.total_anio}</small></b><span class="anz-kpi-sub">por puntaje global en ${f.anio}</span></div>
      ${f.percentil_global ? `<div class="anz-kpi"><span class="anz-kpi-etq">Percentil nacional global</span><b class="anz-kpi-valor">${f.percentil_global}%</b><span class="anz-kpi-sub">supera a ese % del país</span></div>` : ""}
    </div>
    ${lectura.length ? `<ul class="ic-hallazgos">${lectura.map((t) => `<li class="ic-hallazgo info">${icono("user")}<span>${esc(t)}</span></li>`).join("")}</ul>` : ""}
    <section class="ic-bloque">
      <h2>El estudiante frente al promedio del colegio</h2>
      <p class="ic-bloque-desc">Puntaje de cada prueba (0 a 100) del estudiante y del promedio del colegio en ${f.anio}.</p>
      <div class="ic-grafica"><canvas id="ic-chart-ficha" aria-label="Puntajes del estudiante y del colegio" role="img"></canvas></div>
      <div class="tabla-scroll"><table class="ox-tabla anz-tabla">
        <thead><tr><th>Prueba</th><th>Puntaje</th><th>Nivel</th><th>Percentil nacional</th><th>Promedio colegio</th><th>Diferencia</th></tr></thead>
        <tbody>${P.pruebas.map((p) => {
          const v = f.pruebas[p.codigo], c = f.comparacion[p.codigo];
          const col = v.nivel ? icColorNivel(p.codigo, v.nivel) : null;
          return `<tr><th scope="row">${esc(p.nombre)}</th><td><b>${v.puntaje ?? "—"}</b></td>
            <td>${col ? `<span class="ic-chip-nivel" style="background:${col.fondo};color:${col.tinta}">${icNombreNivel(p.codigo, v.nivel)}</span>` : "—"}</td>
            <td>${v.percentil !== null ? `supera al ${v.percentil}% del país` : "—"}</td>
            <td>${icF(c.colegio)}</td>
            <td>${c.diferencia === null ? "—" : `<span class="ic-cambio ${c.diferencia >= 3 ? "sube" : c.diferencia <= -3 ? "baja" : "igual"}">${icS(c.diferencia)}</span>`}</td></tr>`;
        }).join("")}</tbody>
      </table></div>
    </section>
    ${f.otros.length ? `<section class="ic-bloque"><h2>Otras veces que presentó la prueba</h2>
      <ul class="ic-otros">${f.otros.map((o) => `<li><button type="button" class="ic-link" data-ic-otro="${o.id}">${o.anio} · período ${o.periodo}</button> — puntaje global ${o.puntaje_global ?? "—"}</li>`).join("")}</ul></section>` : ""}`;

  host.querySelector("[data-ic-volver]").addEventListener("click", () => icIrA("estudiantes", { anio: f.anio }));
  host.querySelector("[data-ic-ficha-est]")?.addEventListener("click", (e) => abrirFicha(Number(e.currentTarget.dataset.icFichaEst), "icfes"));
  host.querySelectorAll("[data-ic-otro]").forEach((b) => b.addEventListener("click", () => icIrA("ficha", { resultado: Number(b.dataset.icOtro) })));

  const c = document.getElementById("ic-chart-ficha");
  icCharts.push(new Chart(c, {
    type: "bar",
    data: {
      labels: P.pruebas.map((p) => p.nombre),
      datasets: [
        { label: "Estudiante", data: P.pruebas.map((p) => f.pruebas[p.codigo].puntaje), backgroundColor: "#1d4ed8", borderRadius: 4, borderSkipped: "bottom", maxBarThickness: 34 },
        { label: `Promedio del colegio ${f.anio}`, data: P.pruebas.map((p) => f.comparacion[p.codigo].colegio), backgroundColor: "#cbd2dc", borderRadius: 4, borderSkipped: "bottom", maxBarThickness: 34 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12, color: "#344054" } } },
      scales: { y: { ...IC_EJE, min: 0, max: 100 }, x: { grid: { display: false }, ticks: { color: "#344054" } } },
    },
  }));
}
