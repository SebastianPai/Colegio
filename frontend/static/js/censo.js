// --- Censo del resguardo (Ministerio del Interior) --------------------------
// Reportes → «Censo Gran Sábalo» y el bloque «Censo del resguardo» del perfil
// del estudiante. El censo lo carga backend/importar_censo.py; el vínculo con
// los estudiantes es por documento y, si no, por nombre único (esos se marcan
// «verificar»). Ver backend/app/censo.py.

let censoSoloIetaba = false;
let censoBusqueda = "";
let censoDatos = null;
let censoPdfDesde = 0;
let censoPdfHasta = 11;

const GRADOS_CENSO = ["Preescolar", "Primero", "Segundo", "Tercero", "Cuarto", "Quinto", "Sexto", "Séptimo",
  "Octavo", "Noveno", "Décimo", "Once"];

function opcionesGradoCenso(elegido) {
  return GRADOS_CENSO.map((n, g) => `<option value="${g}" ${g === elegido ? "selected" : ""}>${n}</option>`).join("");
}

// PDF con membrete (solo la sede principal I.E.T.A.B.A.): se pide con la sesión y se abre en
// otra pestaña; si el navegador bloquea la ventana, se descarga.
async function abrirPdfCenso(boton) {
  if (censoPdfDesde > censoPdfHasta) [censoPdfDesde, censoPdfHasta] = [censoPdfHasta, censoPdfDesde];
  const url = `/api/censo/reporte.pdf?desde=${censoPdfDesde}&hasta=${censoPdfHasta}`;
  const original = boton.innerHTML;
  boton.disabled = true;
  boton.textContent = "Generando PDF…";
  const ventana = window.open("", "_blank");
  try {
    await asegurarSesionFresca();
    let res = await fetch(url);
    if (res.status === 401 && (await _intentarRefresh())) res = await fetch(url);
    if (!res.ok) {
      const detalle = await res.json().catch(() => ({}));
      throw new Error(detalle.detail || `Error ${res.status} generando el PDF`);
    }
    const objUrl = URL.createObjectURL(await res.blob());
    if (ventana) {
      ventana.location = objUrl;
    } else {
      const a = document.createElement("a");
      a.href = objUrl;
      a.download = `censo_gran_sabalo_${censoPdfDesde}-${censoPdfHasta}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
    setTimeout(() => URL.revokeObjectURL(objUrl), 60000);
  } catch (err) {
    if (ventana) ventana.close();
    const aviso = document.getElementById("censo-aviso");
    if (aviso) aviso.innerHTML = `<div class="alerta-caja">${esc(err.message || "No se pudo generar el PDF.")}</div>`;
  } finally {
    boton.disabled = false;
    boton.innerHTML = original;
    if (window.lucide?.createIcons) lucide.createIcons();
  }
}

function sinTildesCenso(s) {
  return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase();
}

function tablaConteoCensoHtml(titulo, filas) {
  if (!filas.length) return '<p class="rep-detalle">Sin datos.</p>';
  const t = filas.reduce((a, f) => ({ total: a.total + f.total, hombres: a.hombres + f.hombres, mujeres: a.mujeres + f.mujeres }),
    { total: 0, hombres: 0, mujeres: 0 });
  return `
    <div class="tabla-scroll"><table class="rep-tabla">
      <thead><tr><th>${esc(titulo)}</th><th>Total</th><th>%</th><th>Hombres</th><th>Mujeres</th></tr></thead>
      <tbody>${filas.map((f) => `
        <tr><td>${esc(String(f.nombre))}</td><td><strong>${f.total}</strong></td>
          <td>${t.total ? ((f.total * 100) / t.total).toFixed(1) : "0.0"}%</td><td>${f.hombres}</td><td>${f.mujeres}</td></tr>`).join("")}
      </tbody>
      <tfoot><tr><th>Total</th><th>${t.total}</th><th>100%</th><th>${t.hombres}</th><th>${t.mujeres}</th></tr></tfoot>
    </table></div>`;
}

function filasCensoFiltradas() {
  const q = sinTildesCenso(censoBusqueda.trim());
  if (!q) return censoDatos.estudiantes;
  return censoDatos.estudiantes.filter((e) =>
    sinTildesCenso(`${e.nombre} ${e.documento} ${e.comunidad || ""} ${e.sede || ""} ${e.grupo}`).includes(q));
}

function listaCensoHtml() {
  const filas = filasCensoFiltradas();
  return `
    <p class="rep-hoja-sub">${filas.length} de ${censoDatos.estudiantes.length} estudiantes · clic en un nombre para abrir su perfil.</p>
    <div class="tabla-scroll"><table class="rep-tabla">
      <thead><tr><th>#</th><th>Estudiante</th><th>Documento</th><th>Grado</th><th>Sede</th><th>Edad</th><th>Sexo</th><th>Comunidad</th><th>Familia</th><th>Nota</th></tr></thead>
      <tbody>${filas.map((e, i) => `
        <tr>
          <td>${i + 1}</td>
          <td><button type="button" class="rep-accion" data-censo-abrir="${e.id}">${esc(e.nombre)}</button></td>
          <td>${esc(e.documento)}</td>
          <td>${esc(e.grupo)}</td>
          <td>${esc(e.sede || "—")}</td>
          <td>${e.edad ?? "—"}</td>
          <td>${esc(e.genero || "—")}</td>
          <td>${esc(e.comunidad || "—")}</td>
          <td>${esc(e.familia || "—")}${e.parentesco ? ` <span class="rep-detalle">(${esc(e.parentesco)})</span>` : ""}</td>
          <td>${[
            e.vinculo === "nombre" ? '<span class="badge-estado proceso" title="El documento no coincide con el del censo, solo el nombre completo">Verificar: solo nombre</span>' : "",
            e.fecha_distinta ? '<span class="badge-estado proceso" title="La fecha de nacimiento del sistema no es la del censo">Fecha nac. distinta</span>' : "",
            e.posible_retirado ? '<span class="badge-estado alerta">Posible retiro</span>' : "",
          ].join(" ")}</td>
        </tr>`).join("")}
      </tbody>
    </table></div>`;
}

function descargarCsvCenso() {
  const cab = ["Estudiante", "Documento", "Grado", "Sede", "Edad", "Sexo", "Comunidad", "Familia", "Parentesco", "Vínculo con el censo", "Fecha nac. distinta"];
  const filas = filasCensoFiltradas().map((e) => [e.nombre, e.documento, e.grupo, e.sede || "", e.edad ?? "", e.genero || "",
    e.comunidad || "", e.familia || "", e.parentesco || "", e.vinculo === "nombre" ? "Solo nombre (verificar)" : "Documento",
    e.fecha_distinta ? "Sí" : ""]);
  const csv = [cab, ...filas].map((f) => f.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(";")).join("\r\n");
  const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `censo_gran_sabalo_estudiantes_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function renderSeccionCenso() {
  const contenedor = document.getElementById("contenido-reportes");
  try {
    censoDatos = await api(`/api/censo/reporte?solo_ietaba=${censoSoloIetaba}`);
  } catch (err) {
    contenedor.innerHTML = `<div class="alerta-caja">${esc(err.message || "No se pudo cargar el censo.")}</div>`;
    return;
  }
  const d = censoDatos;
  if (!d.cargado) {
    contenedor.innerHTML = `
      <section class="rep-hoja">
        <h2 class="rep-hoja-titulo">Censo del resguardo</h2>
        <p class="rep-hoja-nota">Todavía no se ha cargado el censo. En el PC servidor, desde la carpeta <code>backend</code>:</p>
        <pre>./venv/Scripts/python.exe importar_censo.py "ruta/al/CENSO MININTERIOR GRAN SABALO.xlsx"</pre>
      </section>`;
    return;
  }
  const r = d.estudiantes_resumen;
  const c = d.censo;
  const fuera = d.fuera_del_colegio;
  const fechaCarga = instanteUtcDesdeApi(d.importado_en);
  contenedor.innerHTML = `
    <div class="rep-barra">
      <label class="rep-chip"><input type="checkbox" id="censo-solo-ietaba" ${censoSoloIetaba ? "checked" : ""} /> Solo sede principal I.E.T.A.B.A.</label>
      <span class="rep-detalle">Censo ${esc(d.resguardo)} · vigencia ${d.vigencia || "—"}${fechaCarga ? ` · cargado el ${fechaCarga.toLocaleDateString("es-CO")}` : ""}</span>
      <div class="rep-acciones">
        <label class="filtro-campo">De
          <select id="censo-pdf-desde">${opcionesGradoCenso(censoPdfDesde)}</select></label>
        <label class="filtro-campo">a
          <select id="censo-pdf-hasta">${opcionesGradoCenso(censoPdfHasta)}</select></label>
        <button type="button" class="boton" id="censo-pdf" title="Solo la sede principal I.E.T.A.B.A., por grado y grupo, con el membrete oficial"><i data-lucide=file-text class=ico></i> PDF con membrete</button>
        <button type="button" class="boton secundario" id="censo-csv"><i data-lucide=download class=ico></i> Descargar lista (Excel)</button>
        <button type="button" class="boton secundario" id="censo-imprimir"><i data-lucide=printer class=ico></i> Imprimir</button>
      </div>
    </div>

    <div id="censo-aviso"></div>
    <div class="resumen-reportes">
      <div class="metric-card"><span>Estudiantes del resguardo</span><strong>${r.total}</strong></div>
      <div class="metric-card"><span>Hombres</span><strong>${r.hombres}</strong></div>
      <div class="metric-card"><span>Mujeres</span><strong>${r.mujeres}</strong></div>
      <div class="metric-card"><span>% de los activos${censoSoloIetaba ? " de la sede principal" : ""}</span><strong>${r.pct_del_colegio ?? "—"}%</strong></div>
      <div class="metric-card"><span>Edad promedio</span><strong>${r.edad_promedio ?? "—"}</strong></div>
    </div>
    <p class="rep-hoja-nota">${r.total} de ${r.total_activos_colegio} estudiantes activos${censoSoloIetaba ? " de la sede principal I.E.T.A.B.A." : ""} están en el censo
      (edades de ${r.edad_min ?? "—"} a ${r.edad_max ?? "—"} años).
      ${r.por_nombre ? `<strong>${r.por_nombre}</strong> se reconocieron solo por el nombre porque su documento no coincide: conviene verificarlos.` : ""}
      ${r.fecha_distinta ? `<strong>${r.fecha_distinta}</strong> tienen una fecha de nacimiento distinta a la del censo.` : ""}</p>

    <section class="rep-hoja">
      <h2 class="rep-hoja-titulo">Solo IETABA (sede principal): estudiantes del resguardo</h2>
      <p class="rep-hoja-sub">Solo «SEDE # 01 I.E.T.A.B.A.», sin los «Nuevo · pendiente SIMAT».</p>
      <div class="resumen-reportes resumen-compacta">
        <div class="metric-card"><span>Cantidad</span><strong>${d.ietaba.total}</strong></div>
        <div class="metric-card"><span>Hombres</span><strong>${d.ietaba.hombres}</strong></div>
        <div class="metric-card"><span>Mujeres</span><strong>${d.ietaba.mujeres}</strong></div>
        <div class="metric-card"><span>Comunidades</span><strong>${d.ietaba.por_comunidad.length}</strong></div>
      </div>
      ${tablaConteoCensoHtml("Comunidad", d.ietaba.por_comunidad)}
    </section>

    <section class="rep-hoja">
      <h2 class="rep-hoja-titulo">El censo del resguardo</h2>
      <p class="rep-hoja-sub">Toda la población censada, no solo estudiantes.</p>
      <div class="resumen-reportes resumen-compacta">
        <div class="metric-card"><span>Personas</span><strong>${c.personas}</strong></div>
        <div class="metric-card"><span>Hombres / Mujeres</span><strong>${c.hombres} / ${c.mujeres}</strong></div>
        <div class="metric-card"><span>Familias</span><strong>${c.familias}</strong></div>
        <div class="metric-card"><span>Comunidades</span><strong>${c.comunidades}</strong></div>
        <div class="metric-card"><span>En edad escolar (5–17)</span><strong>${c.en_edad_escolar}</strong></div>
        <div class="metric-card alerta"><span>De 5–17 que no están en el colegio</span><strong>${fuera.total}</strong></div>
      </div>
    </section>

    <section class="rep-hoja">
      <h2 class="rep-hoja-titulo">Estudiantes por edad</h2>
      <p class="rep-hoja-sub">Edad cumplida a hoy (fecha de nacimiento del sistema; si no la tiene, la del censo).</p>
      ${tablaConteoCensoHtml("Rango de edad", d.por_rango_edad)}
      <details class="seccion-colapsable"><summary>Ver por edad exacta</summary>
        ${tablaConteoCensoHtml("Edad", d.por_edad.map((f) => ({ ...f, nombre: typeof f.nombre === "number" ? `${f.nombre} años` : f.nombre })))}
      </details>
    </section>

    <section class="rep-hoja">
      <h2 class="rep-hoja-titulo">Estudiantes por grado</h2>
      ${tablaConteoCensoHtml("Grado", d.por_grado)}
    </section>

    <section class="rep-hoja">
      <h2 class="rep-hoja-titulo">Estudiantes por comunidad</h2>
      <p class="rep-hoja-sub">Comunidad del resguardo según el censo.</p>
      ${tablaConteoCensoHtml("Comunidad", d.por_comunidad)}
    </section>

    <section class="rep-hoja">
      <h2 class="rep-hoja-titulo">Estudiantes por sede</h2>
      ${tablaConteoCensoHtml("Sede", d.por_sede)}
    </section>

    <section class="rep-hoja">
      <h2 class="rep-hoja-titulo">Niños y jóvenes de 5 a 17 años del censo que no están en el colegio</h2>
      <p class="rep-hoja-sub">No aparecen en el sistema (ni como retirados): pueden estar sin estudiar, en otro colegio o con el documento cambiado.</p>
      ${tablaConteoCensoHtml("Comunidad", fuera.por_comunidad)}
      <details class="seccion-colapsable"><summary>Ver por edad</summary>
        ${tablaConteoCensoHtml("Edad", fuera.por_edad.map((f) => ({ ...f, nombre: `${f.nombre} años` })))}
      </details>
    </section>

    <section class="rep-hoja">
      <h2 class="rep-hoja-titulo">Lista de estudiantes del resguardo</h2>
      <div class="rep-barra">
        <label class="rep-buscar"><i data-lucide=search class=ico></i>
          <input type="search" id="censo-buscar" placeholder="Buscar por nombre, documento, comunidad, sede o grado" value="${esc(censoBusqueda)}" /></label>
      </div>
      <div id="censo-lista">${listaCensoHtml()}</div>
    </section>
  `;

  document.getElementById("censo-solo-ietaba").addEventListener("change", (ev) => {
    censoSoloIetaba = ev.target.checked;
    renderSeccionCenso();
  });
  document.getElementById("censo-csv").addEventListener("click", descargarCsvCenso);
  document.getElementById("censo-pdf-desde").addEventListener("change", (ev) => { censoPdfDesde = Number(ev.target.value); });
  document.getElementById("censo-pdf-hasta").addEventListener("change", (ev) => { censoPdfHasta = Number(ev.target.value); });
  document.getElementById("censo-pdf").addEventListener("click", (ev) => abrirPdfCenso(ev.currentTarget));
  document.getElementById("censo-imprimir").addEventListener("click", () => window.print());
  const lista = document.getElementById("censo-lista");
  document.getElementById("censo-buscar").addEventListener("input", (ev) => {
    censoBusqueda = ev.target.value;
    lista.innerHTML = listaCensoHtml();
  });
  lista.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-censo-abrir]");
    if (b) abrirFicha(Number(b.dataset.censoAbrir), "reportes");
  });
}

// --- Perfil del estudiante: bloque «Censo del resguardo» --------------------

async function pintarCensoEstudiante(e) {
  const cont = document.getElementById("censo-estudiante");
  const chip = document.getElementById("chip-censo-estudiante");
  if (!cont && !chip) return;
  let c;
  try {
    c = await api(`/api/censo/estudiantes/${e.id}`);
  } catch {
    cont?.closest("section")?.remove();
    return;
  }
  if (chip && c.en_censo) {
    chip.hidden = false;
    chip.innerHTML = `<i data-lucide=badge-check class=ico></i> Censo ${esc(tituloResguardoCenso(c.resguardo))}`;
  }
  if (!cont) return;
  if (!c.en_censo) {
    cont.innerHTML = c.censo_cargado
      ? '<p class="pendiente est-vacio-linea">No aparece en el censo del resguardo cargado (ni por documento ni por nombre).</p>'
      : '<p class="pendiente est-vacio-linea">Todavía no se ha cargado ningún censo.</p>';
    return;
  }
  const fila = (k, v) => (v ? `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>` : "");
  const fn = c.fecha_nacimiento ? new Date(`${c.fecha_nacimiento}T00:00:00`).toLocaleDateString("es-CO") : "";
  const fechaDistinta = c.fecha_nacimiento && e.fecha_nacimiento && c.fecha_nacimiento !== e.fecha_nacimiento;
  cont.innerHTML = `
    ${c.vinculo === "nombre" ? `<div class="alerta-caja">Se reconoció solo por el nombre: en el censo figura con el documento ${esc(c.documento || "(sin documento)")}. Verifique que sea la misma persona.</div>` : ""}
    <dl class="est-dl">
      ${fila("Resguardo", tituloResguardoCenso(c.resguardo))}
      ${fila("Comunidad", c.comunidad)}
      ${fila("Familia N.º", c.familia)}
      ${fila("Vivienda N.º", c.numero_vivienda)}
      ${fila("Parentesco en la familia", c.parentesco)}
      ${fila("Documento en el censo", [c.tipo_documento, c.documento].filter(Boolean).join(" "))}
      ${fila("Fecha de nacimiento en el censo", fn + (fechaDistinta ? " (distinta a la del sistema)" : ""))}
      ${fila("Teléfono de la familia", c.telefono)}
      ${fila("Censo vigencia", c.vigencia ? String(c.vigencia) : "")}
    </dl>
    ${c.nucleo_familiar.length ? `
      <p class="est-subtitulo-mini">Núcleo familiar según el censo (${c.nucleo_familiar.length + 1} personas)</p>
      <div class="tabla-scroll"><table class="rep-tabla">
        <thead><tr><th>Nombre</th><th>Parentesco</th><th>Edad</th><th>En el colegio</th></tr></thead>
        <tbody>${c.nucleo_familiar.map((m) => `
          <tr><td>${m.estudiante_id ? `<button type="button" class="rep-accion" data-censo-hermano="${m.estudiante_id}">${esc(m.nombre)}</button>` : esc(m.nombre)}</td>
            <td>${esc(m.parentesco || "—")}</td><td>${m.edad ?? "—"}</td>
            <td>${m.grupo ? `<span class="badge-estado ok">${esc(m.grupo)}</span>` : ""}</td></tr>`).join("")}
        </tbody>
      </table></div>` : ""}`;
  cont.querySelectorAll("[data-censo-hermano]").forEach((b) =>
    b.addEventListener("click", () => abrirFicha(Number(b.dataset.censoHermano), vistaAnterior)));
}

function tituloResguardoCenso(nombre) {
  return String(nombre || "").toLowerCase().replace(/(^|\s)\S/g, (l) => l.toUpperCase());
}
