// --- Vista: detalle del estudiante -------------------------------------------
//
// Estructura (rediseño UX): una cabecera de identidad fija + 5 subvistas
//
//   Resumen · Datos · Documentos · Matrícula oficial · Constancias
//
// en vez de los 6 <details> apilados que había antes. Cada subvista pinta
// sólo su panel; el estado de cuál está activa vive en fichaSub y sobrevive
// a los renderFicha() que disparan los guardados y las subidas.
//
// IMPORTANTE — LA FICHA OFICIAL NO SE TOCA. El documento vive en
// static/ficha_matricula.html (generado de la plantilla Word por
// herramientas/generar_html_ficha.py) y se inyecta tal cual en
// #ficha-contenedor. Aquí sólo cambia DÓNDE se muestra: ahora dentro de un
// visor a pantalla completa (#ficha-visor) en vez de en medio del scroll.
// La hoja se sigue cargando SIEMPRE en el DOM aunque el visor esté cerrado,
// porque descargarFicha()/imprimirFicha()/guardarDatosFicha() leen los
// valores de "#ficha-hoja input": si sólo se cargara al abrir el visor,
// descargar el Word desde otra pestaña generaría una ficha vacía.

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

// Valores iniciales de la ficha de matrícula: lo que ya sabemos del estudiante.
function valoresInicialesFicha(e) {
  const fn = e.fecha_nacimiento ? new Date(`${e.fecha_nacimiento}T00:00:00`) : null;
  const hoy = new Date();
  return {
    nombres: [e.primer_nombre, e.segundo_nombre].filter(Boolean).join(" "),
    primer_apellido: e.primer_apellido || "",
    segundo_apellido: e.segundo_apellido || "",
    dia_nac: fn ? String(fn.getDate()) : "",
    mes_nac: fn ? (MESES_TEXTO[fn.getMonth() + 1] || "").toUpperCase() : "",
    anio_nac: fn ? String(fn.getFullYear()) : "",
    numero_documento: e.documento || "",
    municipio_expedicion: e.lugar_expedicion_documento || "",
    sexo_m: e.genero === "M" ? "X" : "",
    sexo_f: e.genero === "F" ? "X" : "",
    grado_2025: String(e.grado), // "GRADO AÑO 2026": el grado de hoy, en número (Preescolar = 0)
    est_antiguo: "X",
    docente: (typeof sesionActual !== "undefined" && sesionActual?.usuario?.nombre) || "",
    dilig_dia: String(hoy.getDate()),
    dilig_mes: (MESES_TEXTO[hoy.getMonth() + 1] || "").toUpperCase(),
    dilig_anio: String(hoy.getFullYear()),
  };
}

// --- Promoción: rendimiento del año + permiso de coordinación ----------------
// Regla (backend/app/promocion.py): aprobó → sube UN grado (0 → 1, no 0 → 2);
// repite → mismo grado. Subir con materias perdidas, saltar o bajar de grado
// necesita permiso APROBADO de coordinación: mientras no lo haya, esta
// pantalla no deja generar ni imprimir la ficha con ese grado (y el backend
// lo vuelve a verificar al generar — la pantalla no es la que manda).
let riesgoFicha = null; // RiesgoPromocion: notas del año por materia, con su docente
let evaluacionFicha = null; // EvaluacionPromocion del grado escrito en la ficha
let estudiantePromocion = null;
let _evaluarFichaTimer = null;

const MOTIVOS_PROMOCION = {
  perdidas: "sube de grado con materias perdidas",
  salto: "salta grados (lo normal es subir uno)",
  retroceso: "baja de grado",
};

function nombreGradoFicha(g) {
  return (NOMBRES_GRADOS.find(([n]) => n === g) || [g, `Grado ${g}`])[1];
}

function gradoDestinoFicha() {
  const v = document.querySelector('#ficha-hoja input[name="grado_2026"]')?.value || "";
  const m = v.match(/\d+/);
  return m ? Number(m[0]) : null;
}

function fechaHoraFicha(t) {
  const f = instanteUtcDesdeApi(t);
  return f ? f.toLocaleString("es-CO", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" }) : "";
}

// Tabla de rendimiento: primero lo perdido y en riesgo, lo aprobado plegado.
function rendimientoFichaHtml(r) {
  if (!r.areas_evaluadas) {
    return `<div class="prom-caja prom-neutra">${icono("info")}<div>No hay notas de ${r.anio_lectivo} en el sistema para este estudiante: no se puede verificar si lleva materias perdidas.</div></div>`;
  }
  const periodos = r.periodos_con_notas;
  const materias = r.materias && r.materias.length ? r.materias : r.perdidas;
  const perdidas = materias.filter((m) => m.estado === "perdida");
  const riesgo = materias.filter((m) => m.estado === "en_riesgo");
  const aprobadas = materias.filter((m) => m.estado === "aprobada");
  const ESTADO = {
    perdida: '<span class="badge-estado alerta">Perdida</span>',
    en_riesgo: '<span class="badge-estado proceso">En riesgo</span>',
    aprobada: '<span class="badge-estado ok">Aprobada</span>',
  };
  const fila = (m) => `
    <tr class="prom-fila-${m.estado}">
      <td><strong>${esc(m.area_nombre)}</strong></td>
      <td>${m.docente_nombre ? `${icono("user", "ico-tenue")}${esc(m.docente_nombre)}` : '<span class="prom-tenue">Sin docente asignado</span>'}</td>
      ${periodos
        .map((p) => {
          const n = m.notas.find((x) => x.periodo === p);
          return `<td class="prom-num${n && n.valor < r.nota_minima ? " prom-nota-baja" : ""}">${n ? n.valor.toFixed(1) : "—"}</td>`;
        })
        .join("")}
      <td class="prom-num"><strong>${m.promedio.toFixed(2)}</strong></td>
      <td>${ESTADO[m.estado] || ""}</td>
    </tr>`;
  const cabecera = `<thead><tr><th>Materia</th><th>Docente</th>${periodos.map((p) => `<th class="prom-num">P${p}</th>`).join("")}<th class="prom-num">Promedio</th><th>Estado</th></tr></thead>`;
  const resumen = perdidas.length
    ? `<span class="prom-dato prom-dato-alerta">${icono("circle-x")}${perdidas.length} perdida${perdidas.length === 1 ? "" : "s"}</span>`
    : `<span class="prom-dato prom-dato-ok">${icono("circle-check")}Ninguna perdida</span>`;
  return `
    <section class="prom-rendimiento">
      <header>
        <h4>${icono("book-open")}Rendimiento ${r.anio_lectivo}</h4>
        <div class="prom-datos">
          ${resumen}
          ${riesgo.length ? `<span class="prom-dato prom-dato-aviso">${icono("triangle-alert")}${riesgo.length} en riesgo</span>` : ""}
          <span class="prom-dato">${materias.length} evaluadas · períodos ${periodos.join(", ")}</span>
        </div>
      </header>
      <p class="prom-regla">Perdida = promedio menor a ${r.nota_minima.toFixed(1)} (una sola materia perdida = año perdido). En riesgo = promedio menor a ${(r.nota_minima + 0.5).toFixed(1)}.</p>
      ${
        perdidas.length || riesgo.length
          ? `<div class="tabla-scroll"><table class="prom-tabla">${cabecera}<tbody>${[...perdidas, ...riesgo].map(fila).join("")}</tbody></table></div>`
          : ""
      }
      ${
        aprobadas.length
          ? `<details class="prom-aprobadas"${perdidas.length || riesgo.length ? "" : " open"}><summary>Ver ${perdidas.length || riesgo.length ? "las " : ""}${aprobadas.length} materia${aprobadas.length === 1 ? "" : "s"} aprobada${aprobadas.length === 1 ? "" : "s"}</summary>
              <div class="tabla-scroll"><table class="prom-tabla">${cabecera}<tbody>${aprobadas.map(fila).join("")}</tbody></table></div></details>`
          : ""
      }
    </section>`;
}

// Estado del grado escrito en la ficha: corresponde, o hace falta permiso
// (pedirlo / pendiente / autorizado / rechazado).
function estadoPromocionHtml(ev) {
  if (!ev) return "";
  const destino = `${nombreGradoFicha(ev.grado_destino)} (${ev.grado_destino})`;
  if (!ev.requiere_autorizacion) {
    const texto = ev.grado_destino === ev.grado_actual ? "Repite el grado." : "Sube un grado, como corresponde.";
    return `<div class="prom-caja prom-ok">${icono("circle-check")}<div><strong>Grado ${esc(destino)}: corresponde.</strong> ${texto}</div></div>`;
  }
  const s = ev.solicitud;
  const motivos = ev.motivos.map((m) => MOTIVOS_PROMOCION[m] || m).join("; ");
  const normal =
    `Hoy está en ${esc(nombreGradoFicha(ev.grado_actual))} (${ev.grado_actual}). Lo normal sería ${esc(nombreGradoFicha(ev.grado_esperado))} (${ev.grado_esperado})` +
    (ev.motivos.includes("perdidas") ? `, o repetir ${esc(nombreGradoFicha(ev.grado_actual))} por las materias perdidas.` : ".");
  const puedeDecidir = tienePermiso("promocion.autorizar");
  const soyYo = s && typeof sesionActual !== "undefined" && sesionActual?.usuario?.nombre === s.solicitado_por_nombre;
  const formulario = `
    <form class="prom-form" data-prom-form>
      <label>¿Por qué debe matricularse en ${esc(destino)}? <span class="prom-tenue">(coordinación decide con base en esto)</span>
        <textarea name="justificacion" rows="3" required placeholder="Ej. Recuperó las materias en el plan de mejoramiento; acta de comisión de evaluación del ..."></textarea>
      </label>
      <div class="prom-form-acciones"><button type="submit" class="boton">${icono("send")}Pedir permiso a coordinación</button></div>
    </form>`;
  let estado = "";
  let clase = "prom-requiere";
  if (!s) {
    estado = formulario;
  } else if (s.estado === "pendiente") {
    clase = "prom-pendiente";
    estado = `
      <p class="prom-linea">${icono("clock-3")}<span>Permiso pedido por <b>${esc(s.solicitado_por_nombre)}</b> el ${esc(fechaHoraFicha(s.solicitado_en))}. <b>Esperando la decisión de coordinación.</b></span></p>
      <blockquote class="prom-cita">${esc(s.justificacion)}</blockquote>
      ${
        puedeDecidir
          ? `<div class="prom-decidir">
              <textarea data-prom-nota rows="2" placeholder="Nota de la decisión (obligatoria para rechazar)"></textarea>
              <div class="prom-form-acciones">
                <button type="button" class="boton" data-prom-accion="aprobar" data-id="${s.id}">${icono("shield-check")}Aprobar</button>
                <button type="button" class="boton secundario prom-boton-rechazar" data-prom-accion="rechazar" data-id="${s.id}">${icono("shield-x")}Rechazar</button>
              </div>
            </div>`
          : ""
      }
      ${soyYo || puedeDecidir ? `<button type="button" class="boton-texto-chico prom-retirar" data-prom-accion="anular" data-id="${s.id}">Retirar solicitud</button>` : ""}`;
  } else if (s.estado === "aprobada") {
    clase = "prom-aprobada";
    estado = `<p class="prom-linea">${icono("shield-check")}<span><b>Autorizado por ${esc(s.decidido_por_nombre || "coordinación")}</b> el ${esc(fechaHoraFicha(s.decidido_en))}${s.nota_decision ? `: «${esc(s.nota_decision)}»` : "."} Ya se puede generar la ficha con este grado.</span></p>
      <p class="prom-tenue">Lo pidió ${esc(s.solicitado_por_nombre)} el ${esc(fechaHoraFicha(s.solicitado_en))}.</p>`;
  } else if (s.estado === "rechazada") {
    clase = "prom-rechazada";
    estado = `<p class="prom-linea">${icono("shield-x")}<span><b>Rechazado por ${esc(s.decidido_por_nombre || "coordinación")}</b> el ${esc(fechaHoraFicha(s.decidido_en))}: «${esc(s.nota_decision || "")}»</span></p>
      <p class="prom-tenue">Puedes matricularlo en el grado que corresponde, o volver a pedir el permiso con más información:</p>${formulario}`;
  }
  const titulo = s && s.estado === "aprobada" ? "Grado autorizado por coordinación" : "Este grado necesita permiso de coordinación";
  return `
    <div class="prom-caja ${clase}">
      ${icono(s && s.estado === "aprobada" ? "shield-check" : "shield-alert")}
      <div class="prom-cuerpo">
        <strong>${titulo}: ${esc(destino)}</strong>
        <p class="prom-motivos">Motivo: ${esc(motivos)}. ${normal}</p>
        ${estado}
      </div>
    </div>`;
}

// Se pinta en TODOS los [data-ficha-riesgo] (Resumen, Matrícula y la barra
// del visor); en el visor (data-ficha-riesgo="compacto") va sin la tabla.
function pintarRiesgoFicha() {
  document.querySelectorAll("[data-ficha-riesgo]").forEach((c) => {
    const compacto = c.dataset.fichaRiesgo === "compacto";
    const destino = gradoDestinoFicha();
    const ev = evaluacionFicha && evaluacionFicha.grado_destino === destino ? evaluacionFicha : null;
    c.innerHTML = (compacto || !riesgoFicha ? "" : rendimientoFichaHtml(riesgoFicha)) + estadoPromocionHtml(ev);
  });
}

async function evaluarPromocionFicha(e) {
  estudiantePromocion = e;
  const destino = gradoDestinoFicha();
  try {
    if (destino === null) {
      evaluacionFicha = null;
      if (!riesgoFicha) riesgoFicha = await api(`/api/estudiantes/${e.id}/riesgo-promocion`);
    } else {
      evaluacionFicha = await api(`/api/promocion/evaluar?estudiante_id=${e.id}&grado_destino=${destino}`);
      riesgoFicha = evaluacionFicha.riesgo;
    }
  } catch {
    /* sin permiso o sin notas: la ficha funciona igual, solo sin el panel */
  }
  pintarRiesgoFicha();
}

function cargarRiesgoFicha(e) {
  riesgoFicha = null;
  evaluacionFicha = null;
  return evaluarPromocionFicha(e);
}

// Al escribir en la ficha: se vuelve a evaluar solo si cambió el grado.
function programarEvaluacionFicha(e) {
  const destino = gradoDestinoFicha();
  if (evaluacionFicha && evaluacionFicha.grado_destino === destino) return;
  if (!evaluacionFicha && destino === null) return;
  clearTimeout(_evaluarFichaTimer);
  _evaluarFichaTimer = setTimeout(() => evaluarPromocionFicha(e), 350);
}

// Antes de generar/imprimir: evaluación fresca del grado escrito. Devuelve
// false (y lo explica) si ese grado necesita un permiso que no está aprobado.
async function promocionPermiteGenerar(e) {
  clearTimeout(_evaluarFichaTimer);
  await evaluarPromocionFicha(e);
  if (!evaluacionFicha || evaluacionFicha.puede_generar) return true;
  const s = evaluacionFicha.solicitud;
  const razon = !s
    ? "Primero hay que pedir permiso a coordinación (formulario de arriba)."
    : s.estado === "pendiente"
      ? "El permiso está pedido y todavía no lo aprueba coordinación."
      : "Coordinación rechazó el permiso para este grado.";
  pintarResultadoFicha(
    `<div class="alerta-caja">${icono("lock")} No se puede generar ni imprimir la ficha con el grado ${evaluacionFicha.grado_destino}. ${razon} Mientras tanto puedes usar el grado que corresponde.</div>`
  );
  document.querySelector("[data-ficha-riesgo] .prom-caja")?.scrollIntoView({ behavior: "smooth", block: "center" });
  return false;
}

// Botones dentro del panel (se repite en varios sitios): delegación global.
document.addEventListener("submit", async (ev) => {
  const form = ev.target.closest("[data-prom-form]");
  if (!form || !estudiantePromocion || !evaluacionFicha) return;
  ev.preventDefault();
  const justificacion = String(new FormData(form).get("justificacion") || "").trim();
  const boton = form.querySelector('[type="submit"]');
  boton.disabled = true;
  try {
    await api("/api/promocion/solicitudes", {
      method: "POST",
      body: JSON.stringify({ estudiante_id: estudiantePromocion.id, grado_destino: evaluacionFicha.grado_destino, justificacion }),
    });
    pintarResultadoFicha(`<div class="exito-caja">${icono("send")} Permiso pedido. Coordinación lo verá en «Autorizaciones de promoción»; aquí mismo aparecerá su respuesta.</div>`);
    await evaluarPromocionFicha(estudiantePromocion);
  } catch (err) {
    boton.disabled = false;
    pintarResultadoFicha(`<div class="alerta-caja">${esc(err.message)}</div>`);
  }
});

document.addEventListener("click", async (ev) => {
  const btn = ev.target.closest("[data-prom-accion]");
  if (!btn || !estudiantePromocion) return;
  const accion = btn.dataset.promAccion;
  const id = btn.dataset.id;
  try {
    if (accion === "anular") {
      if (!confirm("¿Retirar esta solicitud de permiso?")) return;
      await api(`/api/promocion/solicitudes/${id}/anular`, { method: "POST" });
    } else {
      const nota = btn.closest(".prom-cuerpo")?.querySelector("[data-prom-nota]")?.value || "";
      await api(`/api/promocion/solicitudes/${id}/decidir`, {
        method: "POST",
        body: JSON.stringify({ aprobar: accion === "aprobar", nota }),
      });
    }
    await evaluarPromocionFicha(estudiantePromocion);
  } catch (err) {
    pintarResultadoFicha(`<div class="alerta-caja">${esc(err.message)}</div>`);
  }
});

// El resultado de generar/guardar la ficha también puede pedirse desde el
// panel de Matrícula o desde el visor abierto: se pinta en los dos.
function pintarResultadoFicha(html) {
  document.querySelectorAll("[data-resultado-ficha]").forEach((c) => { c.innerHTML = html; });
}

// Guarda en el estudiante lo escrito en la ficha para que el programa lo use.
async function guardarDatosFicha(e) {
  const campos = {};
  document.querySelectorAll("#ficha-hoja input").forEach((i) => { campos[i.name] = i.value; });
  await api(fichaUrlDatosFicha(e.id), { method: "PUT", body: JSON.stringify({ campos }) });
}

// Carga la ficha (tablas HTML reales, generadas de la plantilla Word por
// herramientas/generar_html_ficha.py) y le pone los datos verificados.
async function cargarHojaFicha(e) {
  const cont = document.getElementById("ficha-contenedor");
  if (!cont) return;
  const res = await fetch("/static/ficha_matricula.html?v=f60");
  cont.innerHTML = await res.text();
  const inicial = valoresInicialesFicha(e);
  cont.querySelectorAll("input").forEach((i) => { i.value = inicial[i.name] || ""; });
  try {
    // Lo que ya se guardó del estudiante (acudiente, comunidad, etnia, discapacidad...).
    const guardado = await api(fichaUrlDatosFicha(e.id));
    cont.querySelectorAll("input").forEach((i) => {
      if (guardado.campos[i.name] !== undefined) i.value = guardado.campos[i.name];
    });
  } catch {
    /* sin permiso o sin datos guardados: se queda con los valores por defecto */
  }
  aplicarZoomFicha();
}

// El zoom NO modifica el documento: fija la variable CSS --z que la propia
// hoja ya usa para escalarse (ver el <style> de ficha_matricula.html).
function aplicarZoomFicha() {
  const control = document.getElementById("zoom-ficha");
  if (!control) return;
  const z = Number(control.value);
  document.getElementById("zoom-ficha-valor").textContent = `${z}%`;
  document.getElementById("ficha-hoja")?.style.setProperty("--z", z / 100);
  guardarPreferencia("ietaba_zoom_ficha", String(z));
}

// Imprime solo la ficha, con lo escrito en las casillas.
function imprimirFicha() {
  const hoja = document.getElementById("ficha-hoja").cloneNode(true);
  document.querySelectorAll("#ficha-hoja input").forEach((orig, i) => {
    hoja.querySelectorAll("input")[i].setAttribute("value", orig.value);
  });
  const estilos = document.querySelector("#ficha-contenedor style")?.outerHTML || "";
  const w = window.open("", "_blank");
  w.document.write(`<!doctype html><meta charset="utf-8"><title>Ficha de matrícula</title>${estilos}<body style="margin:0">${hoja.outerHTML}</body>`);
  w.document.close();
  w.onload = () => { w.focus(); w.print(); };
  setTimeout(() => { try { w.focus(); w.print(); } catch {} }, 700);
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
      <div class="foto-etiqueta">${esc(f.etiqueta)}</div>
      <button type="button" class="boton secundario boton-chico" data-eliminar-foto="${f.id}">Eliminar</button>
    </div>`;
}

// --- Estado de la vista ----------------------------------------------------

let fichaDocEstudianteIdActual = null; // para saber cuándo cambió de estudiante
let fichaDocCategoriaIndex = 0;
let fichaDocAnioSeleccionado = null; // null = automático (año más reciente con datos, o el actual)
let fichaDocAccionPendiente = null; // { modo: "escanear"|"reemplazar", categoria, permanente, fotoIdAReemplazar? }
let vistaDocumentos = leerPreferencia("ietaba_vista_documentos", "lista"); // "lista" | "carrusel"

const SUBVISTAS_FICHA = [
  { id: "resumen", nombre: "Resumen" },
  { id: "datos", nombre: "Datos" },
  { id: "documentos", nombre: "Documentos" },
  { id: "matricula", nombre: "Matrícula" },
  { id: "constancias", nombre: "Constancias" },
];
let fichaSub = "resumen";        // pestaña activa; se conserva entre renders
let fichaVisorAbierto = false;   // visor a pantalla completa de la ficha oficial
let fichaModalAbierto = null;    // null | "masiva" | "otro"
let fichaAviso = null;           // { tipo: "exito"|"error", texto } a mostrar tras re-renderizar

// Fase docente (22/09/2026): el director de grupo abre esta MISMA ficha desde
// el módulo docente (docente.js) para ver/editar la ficha de matrícula
// completa de un estudiante de su grupo — el documento oficial no se
// reconstruye aparte. `fichaModoDocente` cambia solo 3 cosas: a qué URL se
// piden/guardan los datos (fichaUrlEstudiante/fichaUrlDatosFicha), qué
// subvistas y acciones administrativas se muestran, y a dónde vuelve el
// botón "Volver" — el layout de #ficha-hoja NO cambia nunca.
let fichaModoDocente = false;

const SUBVISTAS_FICHA_DOCENTE = ["datos", "documentos", "matricula"];

function fichaUrlEstudiante(id) {
  return fichaModoDocente ? `/api/docente/estudiante/${id}/completo` : `/api/estudiantes/${id}`;
}

function fichaUrlDatosFicha(id) {
  return fichaModoDocente ? `/api/docente/estudiante/${id}/datos-ficha` : `/api/estudiantes/${id}/datos-ficha`;
}

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
        ${foto ? imagenConEstadoHtml(`/api/fotos/${foto.id}/miniatura`, "") : '<span class="doc-carrusel-peek-icono"><i data-lucide=file-text class=ico></i> </span>'}
      </div>
      <span class="doc-carrusel-peek-etiqueta">${categoria.nombre}</span>
    </div>`;
}

// Acciones de una categoría (escanear/reescanear/reemplazar/eliminar) —
// las mismas para el carrusel y para la rejilla, un solo lugar.
function accionesDocCategoriaHtml(categoria, foto, tamano) {
  const chico = tamano === "chico" ? " boton-chico" : "";
  if (foto) {
    return `<button type="button" class="boton secundario${chico}" data-doc-escanear="1" data-doc-categoria="${categoria.nombre}" data-doc-permanente="${categoria.permanente}" data-doc-foto-id-reemplazar="${foto.id}"><i data-lucide=camera class=ico></i> Reescanear</button>
            <button type="button" class="boton secundario${chico}" data-doc-accion="reemplazar" data-doc-categoria="${categoria.nombre}" data-doc-permanente="${categoria.permanente}" data-doc-foto-id="${foto.id}"><i data-lucide=refresh-cw class=ico></i> Reemplazar archivo</button>
            <button type="button" class="boton secundario${chico}" data-eliminar-foto="${foto.id}"><i data-lucide=trash-2 class=ico></i> Eliminar</button>`;
  }
  return `<button type="button" class="boton doc-carrusel-boton-escanear" data-doc-escanear="1" data-doc-categoria="${categoria.nombre}" data-doc-permanente="${categoria.permanente}"><i data-lucide=camera class=ico></i> Escanear documento</button>
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
              : `<span class="doc-carrusel-vacio-icono"><i data-lucide=file-text class=ico></i> </span><p class="doc-carrusel-vacio-texto">Todavía no se ha subido</p>`
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

// Rejilla (vista por defecto): una unidad visual por categoría, y el estado
// — cargado / pendiente — se ve de un golpe sin leer los nombres.
function tarjetaDocHtml(categoria, foto) {
  const estado = foto
    ? '<span class="est-chip ok"><i data-lucide=check class=ico></i> Cargado</span>'
    : '<span class="est-chip pendiente"><i data-lucide=triangle-alert class=ico></i> Pendiente</span>';
  const alcance = categoria.permanente
    ? '<span class="est-doc-alcance">Todos los años</span>'
    : '<span class="est-doc-alcance">Por año lectivo</span>';
  return `
    <article class="est-doc-card ${foto ? "ok" : "falta"}">
      <div class="est-doc-thumb">
        ${
          foto
            ? `<a href="/api/fotos/${foto.id}/archivo" target="_blank" title="Abrir documento">
                 ${imagenConEstadoHtml(`/api/fotos/${foto.id}/miniatura`, categoria.nombre)}
                 ${foto.es_pdf ? '<span class="foto-badge-pdf">PDF</span>' : ""}
               </a>`
            : '<span class="est-doc-thumb-vacio"><i data-lucide=file-text class=ico></i> </span>'
        }
      </div>
      <div class="est-doc-cuerpo">
        <h4 class="est-doc-nombre">${categoria.nombre}</h4>
        <p class="est-doc-estado">${estado} ${alcance}</p>
        <div class="est-doc-acciones">
          ${foto ? `<a class="boton secundario boton-chico" href="/api/fotos/${foto.id}/archivo" target="_blank"><i data-lucide=eye class=ico></i> Ver</a>` : ""}
          ${accionesDocCategoriaHtml(categoria, foto, "chico")}
        </div>
      </div>
    </article>`;
}

function rejillaDocumentosHtml(fotos, anio) {
  return `<div class="est-doc-grid">
    ${CATEGORIAS_DOCUMENTO.map((cat) => tarjetaDocHtml(cat, fotoParaCategoria(fotos, cat, anio))).join("")}
  </div>`;
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
    <section class="est-bloque est-bloque-suelto">
      <header class="est-bloque-head">
        <h3>Documentos adicionales <span class="est-contador">${otros.length}</span></h3>
      </header>
      <div class="galeria-fotos">${otros.map(fotoHtml).join("")}</div>
    </section>`;
}

// --- Bloques de datos en solo-lectura ---------------------------------------
// Cada bloque tiene su propio [Editar]: desbloquea SOLO esa sección y muestra
// Guardar / Cancelar. Al guardar o cancelar vuelve a bloquearse.

function accionesFichaHtml() {
  return `
    <div class="ancho-completo form-acciones-ficha">
      <button type="button" class="boton secundario boton-chico" data-ficha-editar><i data-lucide=pencil class=ico></i> Editar</button>
      <button type="submit" class="boton boton-chico" data-ficha-guardar hidden>Guardar</button>
      <button type="button" class="boton secundario boton-chico" data-ficha-cancelar hidden>Cancelar</button>
    </div>`;
}

function bloqueDatosHtml(titulo, descripcion, idForm, camposHtml, extraHtml) {
  return `
    <section class="est-bloque">
      <header class="est-bloque-head">
        <h3>${titulo}</h3>
        ${descripcion ? `<p class="est-bloque-desc">${descripcion}</p>` : ""}
      </header>
      <form id="${idForm}" class="form-grid form-grid-bloque" data-bloqueable>
        ${camposHtml}
        ${accionesFichaHtml()}
      </form>
      <div id="resultado-${idForm}"></div>
      ${extraHtml || ""}
    </section>`;
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
  document.querySelectorAll("form[data-bloqueable]").forEach((form) => {
    bloquearFormularioFicha(form);
    form.querySelector("[data-ficha-editar]").addEventListener("click", () => desbloquearFormularioFicha(form));
    form.querySelector("[data-ficha-cancelar]").addEventListener("click", () => renderFicha());
  });
}

// Muestra, dentro de "Datos", lo que se guardó desde la ficha de matrícula
// (acudiente, comunidad, etnia, discapacidad...). Es de solo lectura: se
// cambia abriendo la ficha oficial en la pestaña «Matrícula».
async function pintarDatosMatriculaGuardados(e) {
  const cont = document.getElementById("datos-matricula-guardados");
  if (!cont) return;
  let c;
  try {
    c = (await api(fichaUrlDatosFicha(e.id))).campos;
  } catch {
    return;
  }
  const marca = (k) => (c[k] ? "Sí" : "");
  const siNo = (si, no) => (c[si] ? "Sí" : c[no] ? "No" : "");
  const etnia = c.etnia_indigena ? "Indígena" : c.etnia_afro ? "Afro" : c.etnia_mestizo ? "Mestizo" : "";
  const disc = c.discap_si
    ? ["disc_ceguera:Ceguera", "disc_sordera:Sordera", "disc_fisica:Dificultad para moverse", "disc_down:Síndrome Down",
       "disc_cognitiva:Cognitiva", "disc_multiple:Múltiple"]
        .filter((x) => c[x.split(":")[0]]).map((x) => x.split(":")[1])
        .concat(c.disc_otras ? [`Otras: ${c.disc_otras}`] : []).join(", ") || "Sí"
    : c.discap_no ? "No" : "";
  const ingreso = c.ingreso_dia ? `${c.ingreso_dia} ${c.ingreso_mes || ""} ${c.ingreso_anio || ""}`.trim() : "";
  const filas = [
    ["Acudiente", [c.acudiente, c.parentesco && `(${c.parentesco})`, c.documento_acudiente && `doc. ${c.documento_acudiente}`].filter(Boolean).join(" ")],
    ["Lugar de expedición del documento", c.municipio_expedicion],
    ["Municipio de nacimiento", c.municipio_nacimiento],
    ["Comunidad / dirección", c.direccion],
    ["Resguardo", c.resguardo],
    ["Viene de (C.E.)", c.procedencia],
    ["Etnia", etnia],
    ["Habla Awapit", siNo("awapit_si", "awapit_no")],
    ["Madre cabeza de familia", siNo("madre_si", "madre_no")],
    ["Discapacidad", disc],
    ["Necesita educación especial", siNo("educ_esp_si", "educ_esp_no")],
    ["En situación de desplazamiento", siNo("desplaz_si", "desplaz_no")],
    ["Fecha de ingreso al colegio", ingreso],
    ["Estudiante SGP", marca("sgp")],
  ].filter(([, v]) => v);
  cont.innerHTML = filas.length
    ? `<dl class="est-dl">
         ${filas.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}
       </dl>`
    : `<p class="pendiente est-vacio-linea">Aún no hay datos de matrícula guardados (acudiente, comunidad, etnia...).
       Se llenan abriendo la ficha oficial en la pestaña «Matrícula».</p>`;
}

// --- Helpers de presentación (sólo formato, no inventan datos) --------------

function inicialesEstudiante(e) {
  return `${(e.primer_nombre || "?")[0]}${(e.primer_apellido || "")[0] || ""}`.toUpperCase();
}

function fechaLegible(iso) {
  if (!iso) return "";
  const [a, m, d] = iso.split("-");
  return `${d}/${m}/${a}`;
}

function edadDesde(iso) {
  if (!iso) return "";
  const n = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(n.getTime())) return "";
  const hoy = new Date();
  let edad = hoy.getFullYear() - n.getFullYear();
  const m = hoy.getMonth() - n.getMonth();
  if (m < 0 || (m === 0 && hoy.getDate() < n.getDate())) edad--;
  return edad >= 0 && edad < 120 ? `${edad} años` : "";
}

function nombreGrado(grado) {
  return (NOMBRES_GRADOS.find(([g]) => g === grado) || [0, String(grado)])[1];
}

// Lista de definición compacta. Los valores llegan YA escapados o son HTML
// controlado (badges); las claves se escapan aquí.
function dlHtml(filas) {
  const visibles = filas.filter(([, v]) => v !== "" && v !== null && v !== undefined);
  if (!visibles.length) return '<p class="pendiente est-vacio-linea">Sin datos.</p>';
  return `<dl class="est-dl">${visibles
    .map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`)
    .join("")}</dl>`;
}

// --- Paneles ----------------------------------------------------------------

function panelResumenHtml(e, docs) {
  const tipoDoc = e.tipo_documento ? `${esc(e.tipo_documento)} ` : "";
  const pendientesHtml = docs.faltantes.length
    ? `<ul class="est-pendientes">${docs.faltantes.map((c) => `<li>${c.nombre}</li>`).join("")}</ul>`
    : '<p class="est-completo"><i data-lucide=check class=ico></i> Toda la documentación está cargada.</p>';

  return `
    <div class="est-columnas">
      <div class="est-columna-principal">
        <div data-ficha-riesgo></div>
        ${
          e.curso === null
            ? `<div class="est-nota-suave"><i data-lucide=triangle-alert class=ico></i> Sin sección/curso asignado — es normal en las sedes rurales que todavía no
                 tienen su propio Excel de matrícula. Se completa en la pestaña «Datos».</div>`
            : ""
        }
        <section class="est-bloque">
          <header class="est-bloque-head">
            <h3>Información del estudiante</h3>
            <button type="button" class="boton secundario boton-chico" data-ir-sub="datos">Editar datos</button>
          </header>
          ${dlHtml([
            ["Documento", `${tipoDoc}${esc(e.documento)}`],
            ["Lugar de expedición", esc(e.lugar_expedicion_documento || "")],
            ["Fecha de nacimiento", [fechaLegible(e.fecha_nacimiento), edadDesde(e.fecha_nacimiento)].filter(Boolean).join(" · ")],
            ["Género", e.genero === "M" ? "Masculino" : e.genero === "F" ? "Femenino" : ""],
            ["Grado", esc(nombreGrado(e.grado))],
            ["Curso / sección", e.curso === null ? "" : esc(String(e.curso))],
            ["Grupo", esc(e.grupo || "")],
            ["Sede", esc(e.sede ? e.sede.nombre : "")],
            ["ID SIMAT", esc(e.id_estud || "")],
            ["Estado", `<span class="badge ${e.activo ? "activo" : "inactivo"}">${esc((e.estado || "").toLowerCase())}</span>`],
            ["Resguardo", e.resguardo === false ? "No pertenece a un resguardo" : "Sí pertenece a un resguardo"],
            ["Posible retirado", e.posible_retirado ? "Sí — no cuenta en los pendientes de boletín" : ""],
            ["Observaciones", esc(e.observaciones || "")],
          ])}
        </section>
      </div>

      <aside class="est-columna-lateral">
        <section class="est-bloque est-bloque-lateral">
          <header class="est-bloque-head"><h3>Estado de documentación</h3></header>
          <div class="est-progreso">
            <div class="est-progreso-barra ${docs.faltantes.length ? "" : "completo"}">
              <span style="width:${docs.pct}%"></span>
            </div>
            <div class="est-progreso-texto">
              <strong>${docs.cargados} de ${docs.total}</strong> documentos · ${docs.pct}%
            </div>
          </div>
          <p class="est-bloque-desc">Año lectivo ${docs.anio}</p>
          ${docs.faltantes.length ? "<p class=\"est-subtitulo-mini\">Pendientes</p>" : ""}
          ${pendientesHtml}
          <button type="button" class="boton secundario est-boton-ancho" data-ir-sub="documentos">Ver documentos</button>
        </section>

        <section class="est-bloque est-bloque-lateral">
          <header class="est-bloque-head"><h3>Acciones rápidas</h3></header>
          <div class="est-acciones-rapidas">
            <button type="button" class="boton est-boton-ancho" data-ficha-accion="abrir"><i data-lucide=clipboard-list class=ico></i> Abrir ficha de matrícula</button>
            <button type="button" class="boton secundario est-boton-ancho" data-ir-sub="constancias"><i data-lucide=file-text class=ico></i> Generar constancia</button>
            <button type="button" class="boton secundario est-boton-ancho" data-ficha-accion="word"><i data-lucide=download class=ico></i> Ficha en Word</button>
            <button type="button" class="boton secundario est-boton-ancho" data-ficha-accion="imprimir"><i data-lucide=printer class=ico></i> Imprimir ficha</button>
          </div>
          <div data-resultado-ficha></div>
        </section>
      </aside>
    </div>`;
}

function panelDatosHtml(e) {
  const historial = e.historial_documento.length
    ? `<details class="seccion-colapsable est-sub-detalle">
         <summary>Historial de documento (${e.historial_documento.length})</summary>
         <table>
           <thead><tr><th>Tipo</th><th>Número</th><th>Vigente hasta</th></tr></thead>
           <tbody>
             ${e.historial_documento
               .map((h) => `<tr><td>${esc(h.tipo_documento || "-")}</td><td>${esc(h.documento || "-")}</td><td>${h.vigente_hasta.slice(0, 16).replace("T", " ")}</td></tr>`)
               .join("")}
           </tbody>
         </table>
       </details>`
    : "";

  return `
    <div class="est-grid-bloques">
      ${bloqueDatosHtml(
        "Identificación",
        "Cambiar el tipo o el número guarda el valor anterior en el historial.",
        "form-doc-identidad",
        `${tipoDocumentoSelectHtml("tipo_documento", e.tipo_documento || "")}
         <label>Número de documento
           <input type="text" name="documento" value="${esc(e.documento)}" />
         </label>
         <label class="ancho-completo">Lugar de expedición
           <input type="text" name="lugar_expedicion_documento" value="${esc(e.lugar_expedicion_documento || "")}" placeholder="Ej: Barbacoas (N)" />
         </label>`,
        historial
      )}

      ${bloqueDatosHtml(
        "Información académica",
        `Sede: ${esc(e.sede ? e.sede.nombre : "sin sede")} · Grupo: ${esc(e.grupo || "-")}`,
        "form-datos-academicos",
        `<label>Grado
           <select name="grado">
             ${NOMBRES_GRADOS.map(([g, nombre]) => `<option value="${g}" ${g === e.grado ? "selected" : ""}>${nombre}</option>`).join("")}
           </select>
         </label>
         <label>Curso / sección
           <input type="number" name="curso" min="1" step="1" value="${e.curso ?? ""}" placeholder="Ej: 1, 2, 3..." />
         </label>
         <label class="ancho-completo">ID de estudiante (SIMAT)
           <input type="text" name="id_estud" value="${esc(e.id_estud || "")}" />
         </label>`
      )}

      ${bloqueDatosHtml(
        "Información personal",
        "",
        "form-datos-personales",
        `<label>Fecha de nacimiento
           <input type="date" name="fecha_nacimiento" value="${e.fecha_nacimiento || ""}" />
         </label>
         <label>Género
           <select name="genero">
             <option value="" ${!e.genero ? "selected" : ""}>Sin dato</option>
             <option value="M" ${e.genero === "M" ? "selected" : ""}>Masculino</option>
             <option value="F" ${e.genero === "F" ? "selected" : ""}>Femenino</option>
           </select>
         </label>`
      )}

      ${bloqueDatosHtml(
        "Estado y observaciones",
        "",
        "form-datos-estado",
        `<label class="ancho-completo">Observaciones
           <input type="text" name="observaciones" value="${esc(e.observaciones || "")}" placeholder="Notas internas sobre este estudiante" />
         </label>
         <label class="ancho-completo check-linea">
           <input type="checkbox" name="resguardo" ${e.resguardo === false ? "" : "checked"} />
           Pertenece a un resguardo
         </label>
         <label class="ancho-completo check-linea">
           <input type="checkbox" name="posible_retirado" ${e.posible_retirado ? "checked" : ""} />
           Posible retirado — sigue en el sistema pero <strong>no cuenta</strong> en los pendientes de boletín. No es un retiro formal.
         </label>`
      )}

      <section class="est-bloque est-bloque-ancho">
        <header class="est-bloque-head">
          <h3>Datos de la ficha de matrícula</h3>
          <button type="button" class="boton secundario boton-chico" data-ficha-accion="abrir">Abrir ficha para editarlos</button>
        </header>
        <p class="est-bloque-desc">Acudiente, comunidad, etnia, discapacidad… Son de solo lectura aquí: se escriben en la ficha oficial.</p>
        <div id="datos-matricula-guardados"></div>
      </section>
    </div>`;
}

function panelDocumentosHtml(e, docs) {
  return `
    <section class="est-bloque est-bloque-ancho">
      <header class="est-doc-barra">
        <div class="est-doc-barra-titulo">
          <h3>Documentos de matrícula</h3>
          <p class="est-bloque-desc">
            ${docs.cargados} de ${docs.total} cargados${docs.faltantes.length ? ` · faltan ${docs.faltantes.length}` : " · completo"}
          </p>
        </div>
        <div class="est-doc-barra-controles">
          <label class="filtro-campo">Año lectivo
            <select id="select-anio-documentos">${opcionesAnioLectivo(docs.anio)}</select>
          </label>
          <div class="doc-vista-toggle" role="group" aria-label="Vista de documentos">
            <button type="button" class="doc-vista-btn ${vistaDocumentos === "lista" ? "activo" : ""}" data-doc-vista="lista"><i data-lucide=menu class=ico></i> Rejilla</button>
            <button type="button" class="doc-vista-btn ${vistaDocumentos === "carrusel" ? "activo" : ""}" data-doc-vista="carrusel">▤ Carrusel</button>
          </div>
          <button type="button" class="boton" data-abrir-modal="masiva"><i data-lucide=upload class=ico></i> Carga masiva</button>
          <button type="button" class="boton-texto-chico" data-abrir-modal="otro">+ Documento adicional</button>
        </div>
      </header>
      ${vistaDocumentos === "carrusel" ? carruselCuerpoHtml(e.fotos, docs.anio) : rejillaDocumentosHtml(e.fotos, docs.anio)}
      <input type="file" id="doc-carrusel-input-archivo" accept="image/*,application/pdf" style="display:none" />
    </section>
    ${otrosDocumentosHtml(e.fotos)}`;
}

// Solo lectura para el director de grupo: mismo catálogo de categorías y
// miniaturas que panelDocumentosHtml, sin ningún control de carga/reemplazo/
// eliminación (esos siguen siendo exclusivos de Administración/Secretaría).
function panelDocumentosSoloLecturaHtml(e, docs) {
  const tarjetas = CATEGORIAS_DOCUMENTO.map((cat) => {
    const foto = fotoParaCategoria(e.fotos, cat, docs.anio);
    return `
      <article class="est-doc-card ${foto ? "ok" : "falta"}">
        <div class="est-doc-thumb">
          ${
            foto
              ? `<a href="/api/fotos/${foto.id}/archivo" target="_blank" title="Abrir documento">
                   ${imagenConEstadoHtml(`/api/fotos/${foto.id}/miniatura`, cat.nombre)}
                   ${foto.es_pdf ? '<span class="foto-badge-pdf">PDF</span>' : ""}
                 </a>`
              : '<span class="est-doc-thumb-vacio"><i data-lucide=file-text class=ico></i> </span>'
          }
        </div>
        <div class="est-doc-cuerpo">
          <h4 class="est-doc-nombre">${cat.nombre}</h4>
          <p class="est-doc-estado">${foto ? '<span class="est-chip ok"><i data-lucide=check class=ico></i> Cargado</span>' : '<span class="est-chip pendiente"><i data-lucide=triangle-alert class=ico></i> Pendiente</span>'}</p>
          ${foto ? `<a class="boton secundario boton-chico" href="/api/fotos/${foto.id}/archivo" target="_blank"><i data-lucide=eye class=ico></i> Ver</a>` : ""}
        </div>
      </article>`;
  }).join("");
  return `
    <section class="est-bloque est-bloque-ancho">
      <header class="est-doc-barra">
        <div class="est-doc-barra-titulo">
          <h3>Documentos de matrícula</h3>
          <p class="est-bloque-desc">${docs.cargados} de ${docs.total} cargados · solo lectura</p>
        </div>
      </header>
      <div class="est-doc-grid">${tarjetas}</div>
    </section>`;
}

function panelMatriculaHtml(e, nombreCompleto) {
  return `
    <div class="est-columnas">
      <div class="est-columna-principal">
        <div data-ficha-riesgo></div>
        <section class="est-documento-oficial">
          <div class="est-documento-icono"><i data-lucide=clipboard-list class=ico></i> </div>
          <div class="est-documento-info">
            <h3>Ficha de matrícula</h3>
            <p class="est-documento-sub">Formato oficial de la institución · ${esc(nombreCompleto)}</p>
            <p class="est-bloque-desc">
              Es el documento oficial y no se puede modificar su formato. Al abrirlo se escribe directamente
              sobre las casillas; revisa especialmente el <strong>Grado año 2026</strong> (número, Preescolar = 0).
              Lo que escribas (acudiente, comunidad, etnia, discapacidad, lugar de expedición…) se guarda en el
              estudiante al descargar el Word o al pulsar «Guardar», y vuelve a aparecer el próximo año.
            </p>
            <div class="est-documento-acciones">
              <button type="button" class="boton" data-ficha-accion="abrir">Abrir ficha</button>
              <button type="button" class="boton secundario" data-ficha-accion="word">Descargar Word (.docx)</button>
              <button type="button" class="boton secundario" data-ficha-accion="pdf">Descargar PDF</button>
              <button type="button" class="boton secundario" data-ficha-accion="imprimir">Imprimir</button>
            </div>
            <div data-resultado-ficha></div>
          </div>
        </section>
      </div>
      <aside class="est-columna-lateral">
        <section class="est-bloque est-bloque-lateral">
          <header class="est-bloque-head"><h3>Páginas escaneadas</h3></header>
          <p class="est-bloque-desc">La ficha firmada se archiva como documento escaneado en estas dos categorías.</p>
          <ul class="est-pendientes est-lista-estado">
            ${CATEGORIAS_DOCUMENTO.slice(0, 2)
              .map((c) => {
                const f = fotoParaCategoria(e.fotos, c, fichaDocAnioSeleccionado ?? new Date().getFullYear());
                return `<li>${f ? '<span class="est-chip ok"><i data-lucide=check class=ico></i> </span>' : '<span class="est-chip pendiente"><i data-lucide=triangle-alert class=ico></i> </span>'} ${c.nombre}</li>`;
              })
              .join("")}
          </ul>
          <button type="button" class="boton secundario est-boton-ancho" data-ir-sub="documentos">Ir a documentos</button>
        </section>
      </aside>
    </div>`;
}

function panelConstanciasHtml(e, opciones, hoy) {
  return `
    <section class="est-bloque est-bloque-ancho">
      <header class="est-bloque-head">
        <h3>Generar constancia de estudio</h3>
        <p class="est-bloque-desc">Queda guardada en el registro de constancias al generarla.</p>
      </header>
      <div class="constancia-editor">
        <form id="form-constancia" class="form-grid form-grid-bloque">
          <label>Lugar de expedición (para el texto de la constancia)
            <input type="text" name="lugar_expedicion" value="${esc(e.lugar_expedicion_documento || "")}" required />
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
              ${opciones.propositos.map((p) => `<option value="${esc(p)}">${esc(p)}</option>`).join("")}
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
          <p class="est-subtitulo-mini">Vista previa (aproximada, el Word/PDF real lleva el formato oficial completo)</p>
          <div id="preview-constancia"></div>
        </div>
      </div>
      <div id="resultado-constancia"></div>
    </section>`;
}

// --- Visor de la ficha oficial ---------------------------------------------
// Contenedor externo rediseñable; el documento de dentro (#ficha-hoja) se
// inyecta tal cual desde static/ficha_matricula.html y NO se modifica.

function visorFichaHtml(e, nombreCompleto) {
  const zoom = Number(leerPreferencia("ietaba_zoom_ficha", "130")) || 130;
  return `
    <div class="est-visor" id="ficha-visor" ${fichaVisorAbierto ? "" : "hidden"} role="dialog" aria-label="Ficha de matrícula">
      <header class="est-visor-barra">
        <div class="est-visor-titulo">
          <strong>Ficha de matrícula</strong>
          <span>${esc(nombreCompleto)} · Doc. ${esc(e.documento)}</span>
        </div>
        <div class="est-visor-controles">
          <div class="est-visor-zoom">
            <button type="button" class="est-visor-zoom-btn" data-zoom-paso="-10" aria-label="Alejar">−</button>
            <input type="range" id="zoom-ficha" min="60" max="200" step="5" value="${zoom}" aria-label="Zoom" />
            <button type="button" class="est-visor-zoom-btn" data-zoom-paso="10" aria-label="Acercar">+</button>
            <span id="zoom-ficha-valor">${zoom}%</span>
          </div>
          <button type="button" class="boton" data-ficha-accion="guardar">Guardar en el estudiante</button>
          <button type="button" class="boton secundario" data-ficha-accion="word">Word</button>
          <button type="button" class="boton secundario" data-ficha-accion="pdf">PDF</button>
          <button type="button" class="boton secundario" data-ficha-accion="imprimir">Imprimir</button>
          <button type="button" class="est-visor-cerrar" id="btn-cerrar-visor" aria-label="Cerrar"></button>
        </div>
      </header>
      <div class="est-visor-avisos">
        <div data-ficha-riesgo="compacto"></div>
        <div data-resultado-ficha></div>
      </div>
      <div class="est-visor-lienzo">
        <div class="ficha-hoja-contenedor" id="ficha-contenedor"><p>Cargando ficha...</p></div>
      </div>
    </div>`;
}

// --- Modales de documentos --------------------------------------------------
// Viven siempre en el DOM (ocultos) para que los bindings de subida masiva y
// de documento adicional no dependan de abrirlos.

function modalesDocumentosHtml() {
  return `
    <div class="modal-fondo est-modal" id="modal-carga-masiva" ${fichaModalAbierto === "masiva" ? "" : "hidden"} role="dialog" aria-label="Carga masiva de documentos">
      <div class="modal-caja modal-caja-ancha">
        <header class="est-modal-head">
          <h3>Carga masiva de documentos</h3>
          <button type="button" class="est-visor-cerrar" data-cerrar-modal aria-label="Cerrar"></button>
        </header>
        <p class="est-bloque-desc">
          Ideal si ya escaneaste varias páginas con el celular (ej. con Adobe Scan o Microsoft 365):
          elige todos los archivos juntos y aquí le asignas la categoría a cada uno. Si un archivo es un
          PDF de varias páginas, cada página entra por separado y eliges cuáles usar.
        </p>
        <label class="boton secundario est-label-archivo">
          Elegir varios archivos...
          <input type="file" id="input-subida-masiva" accept="image/*,application/pdf" multiple style="display:none" />
        </label>
        <div id="lista-subida-masiva"></div>
      </div>
    </div>

    <div class="modal-fondo est-modal" id="modal-doc-adicional" ${fichaModalAbierto === "otro" ? "" : "hidden"} role="dialog" aria-label="Agregar documento adicional">
      <div class="modal-caja">
        <header class="est-modal-head">
          <h3>Agregar documento adicional</h3>
          <button type="button" class="est-visor-cerrar" data-cerrar-modal aria-label="Cerrar"></button>
        </header>
        <p class="est-bloque-desc">Para documentos fuera de las ${CATEGORIAS_DOCUMENTO.length} categorías de matrícula.</p>
        <form id="form-subir-foto" class="form-grid form-grid-bloque no-imprimir">
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
      </div>
    </div>`;
}

// --- Abrir / cerrar superposiciones -----------------------------------------

function bloquearScrollFondo(bloquear) {
  document.body.style.overflow = bloquear ? "hidden" : "";
}

function abrirVisorFicha() {
  const visor = document.getElementById("ficha-visor");
  if (!visor) return;
  fichaVisorAbierto = true;
  visor.hidden = false;
  bloquearScrollFondo(true);
}

function cerrarVisorFicha() {
  const visor = document.getElementById("ficha-visor");
  fichaVisorAbierto = false;
  if (visor) visor.hidden = true;
  if (!fichaModalAbierto) bloquearScrollFondo(false);
}

function abrirModalFicha(cual) {
  const modal = document.getElementById(cual === "masiva" ? "modal-carga-masiva" : "modal-doc-adicional");
  if (!modal) return;
  fichaModalAbierto = cual;
  modal.hidden = false;
  bloquearScrollFondo(true);
}

function cerrarModalesFicha() {
  fichaModalAbierto = null;
  document.querySelectorAll(".est-modal").forEach((m) => { m.hidden = true; });
  if (!fichaVisorAbierto) bloquearScrollFondo(false);
}

function irASubvistaFicha(sub) {
  fichaSub = sub;
  renderFicha();
}

// --- Render -----------------------------------------------------------------

async function renderFicha() {
  app.innerHTML = '<p class="estado-carga">Cargando...</p>';
  const [e, opciones] = await Promise.all([
    api(fichaUrlEstudiante(fichaEstudianteId)),
    fichaModoDocente ? Promise.resolve(null) : api("/api/certificados/opciones"),
  ]);

  const nombreCompleto = `${e.primer_nombre} ${e.segundo_nombre || ""} ${e.primer_apellido} ${e.segundo_apellido || ""}`
    .replace(/\s+/g, " ")
    .trim();
  const hoy = fechaColombiaISO();

  if (fichaDocEstudianteIdActual !== fichaEstudianteId) {
    fichaDocEstudianteIdActual = fichaEstudianteId;
    fichaDocCategoriaIndex = leerIndiceCategoriaGuardado(fichaEstudianteId);
    fichaDocAnioSeleccionado = null;
    fichaSub = "resumen";
    fichaVisorAbierto = false;
    fichaModalAbierto = null;
  }

  // Estado de documentación, con los datos reales del estudiante.
  const anioDocs = fichaDocAnioSeleccionado ?? new Date().getFullYear();
  const faltantes = categoriasFaltantesOrdenadas(e.fotos, anioDocs);
  const docs = {
    anio: anioDocs,
    total: CATEGORIAS_DOCUMENTO.length,
    faltantes,
    cargados: CATEGORIAS_DOCUMENTO.length - faltantes.length,
    pct: Math.round(((CATEGORIAS_DOCUMENTO.length - faltantes.length) / CATEGORIAS_DOCUMENTO.length) * 100),
  };

  const paneles = {
    resumen: () => panelResumenHtml(e, docs),
    datos: () => panelDatosHtml(e),
    documentos: () => (fichaModoDocente ? panelDocumentosSoloLecturaHtml(e, docs) : panelDocumentosHtml(e, docs)),
    matricula: () => panelMatriculaHtml(e, nombreCompleto),
    constancias: () => panelConstanciasHtml(e, opciones, hoy),
  };
  const subvistas = fichaModoDocente
    ? SUBVISTAS_FICHA.filter((s) => SUBVISTAS_FICHA_DOCENTE.includes(s.id))
    : SUBVISTAS_FICHA;
  if (fichaModoDocente && !SUBVISTAS_FICHA_DOCENTE.includes(fichaSub)) fichaSub = "datos";

  app.innerHTML = `
    <div class="est-detalle">
      <button class="volver" id="btn-volver-ficha">← Volver</button>

      <header class="est-cabecera">
        <div class="est-identidad">
          <span class="est-avatar" aria-hidden="true">${esc(inicialesEstudiante(e))}</span>
          <div class="est-identidad-texto">
            <h1 class="est-nombre">${esc(nombreCompleto)}</h1>
            <p class="est-meta">
              <span>${esc(nombreGrado(e.grado))}${e.curso !== null ? ` · Curso ${esc(String(e.curso))}` : ""}</span>
              <span class="est-meta-sep">·</span>
              <span>${esc(e.sede ? e.sede.nombre : "sin sede")}</span>
              <span class="est-meta-sep">·</span>
              <span>Documento: ${esc(e.documento)}</span>
              <span class="badge ${e.activo ? "activo" : "inactivo"}">${esc((e.estado || "").toLowerCase())}</span>
              ${docs.faltantes.length ? `<span class="est-chip pendiente">${docs.faltantes.length} doc. pendiente${docs.faltantes.length > 1 ? "s" : ""}</span>` : '<span class="est-chip ok">Documentación completa</span>'}
            </p>
          </div>
        </div>
        <div class="est-cabecera-acciones">
          <button type="button" class="boton" data-ficha-accion="abrir"><i data-lucide=clipboard-list class=ico></i> Abrir ficha</button>
          ${fichaModoDocente ? "" : '<button type="button" class="boton secundario" data-ir-sub="constancias"><i data-lucide=file-text class=ico></i> Constancia</button>'}
        </div>
      </header>

      <nav class="subnav-modulo est-tabs" aria-label="Secciones del estudiante">
        ${subvistas.map(
          (s) => `<button type="button" class="subnav-item ${fichaSub === s.id ? "activo" : ""}" data-ir-sub="${s.id}">
                    ${s.nombre}${s.id === "documentos" ? ` <span class="est-tab-contador ${docs.faltantes.length ? "" : "ok"}">${docs.cargados}/${docs.total}</span>` : ""}
                  </button>`
        ).join("")}
      </nav>

      <div id="ficha-aviso">${
        fichaAviso ? `<div class="${fichaAviso.tipo === "error" ? "alerta-caja" : "exito-caja"}">${esc(fichaAviso.texto)}</div>` : ""
      }</div>

      <div class="est-panel">${(paneles[fichaSub] || paneles.resumen)()}</div>
    </div>

    ${visorFichaHtml(e, nombreCompleto)}
    ${modalesDocumentosHtml()}
  `;
  fichaAviso = null;

  document.getElementById("btn-volver-ficha").addEventListener("click", () => {
    cerrarVisorFicha();
    cerrarModalesFicha();
    fichaModoDocente = false;
    vistaActual = vistaAnterior;
    render();
  });

  document.querySelectorAll("[data-ir-sub]").forEach((btn) => {
    btn.addEventListener("click", () => irASubvistaFicha(btn.dataset.irSub));
  });

  vincularTipoDocumentoOtro("tipo_documento");
  vincularEstadoPreviews();
  vincularBloqueoFicha();
  pintarDatosMatriculaGuardados(e);
  // El director de grupo ve "Datos" en solo lectura: no edita identidad,
  // grado/curso ni observaciones internas desde el módulo docente — eso
  // sigue siendo de Administración/Secretaría. Lo único editable para él es
  // la ficha de matrícula (pestaña «Matrícula», botón "Abrir ficha").
  if (fichaModoDocente) {
    document.querySelectorAll("[data-ficha-editar]").forEach((b) => { b.hidden = true; });
  }

  // --- Guardar por bloque (mismo endpoint PATCH, payload parcial) ----------
  const guardarBloque = (idForm, construirCambios) => {
    const form = document.getElementById(idForm);
    if (!form) return;
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const datos = Object.fromEntries(new FormData(ev.target).entries());
      try {
        await api(`/api/estudiantes/${fichaEstudianteId}`, {
          method: "PATCH",
          body: JSON.stringify(construirCambios(datos, ev.target)),
        });
        fichaAviso = { tipo: "exito", texto: "Cambios guardados." };
        await renderFicha();
      } catch (err) {
        document.getElementById(`resultado-${idForm}`).innerHTML = `<div class="alerta-caja">${esc(err.message)}</div>`;
      }
    });
  };

  guardarBloque("form-doc-identidad", (d) => ({
    tipo_documento: valorTipoDocumento(d, "tipo_documento") || null,
    documento: d.documento,
    lugar_expedicion_documento: d.lugar_expedicion_documento || null,
  }));
  guardarBloque("form-datos-personales", (d) => ({
    fecha_nacimiento: d.fecha_nacimiento || null,
    genero: d.genero || null,
  }));
  guardarBloque("form-datos-academicos", (d) => ({
    grado: Number(d.grado),
    curso: d.curso === "" ? null : Number(d.curso),
    id_estud: d.id_estud || null,
  }));
  guardarBloque("form-datos-estado", (d, form) => ({
    observaciones: d.observaciones || null,
    resguardo: form.querySelector('[name="resguardo"]').checked,
    posible_retirado: form.querySelector('[name="posible_retirado"]').checked,
  }));

  // --- Modales de documentos ----------------------------------------------
  document.querySelectorAll("[data-abrir-modal]").forEach((btn) => {
    btn.addEventListener("click", () => abrirModalFicha(btn.dataset.abrirModal));
  });
  document.querySelectorAll("[data-cerrar-modal]").forEach((btn) => {
    btn.addEventListener("click", cerrarModalesFicha);
  });
  document.querySelectorAll(".est-modal").forEach((modal) => {
    modal.addEventListener("click", (ev) => {
      if (ev.target === modal) cerrarModalesFicha();
    });
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
      cerrarModalesFicha();
      fichaSub = "documentos";
      fichaAviso = { tipo: "exito", texto: "Documento subido." };
      await renderFicha();
    } catch (err) {
      cont.innerHTML = `<div class="alerta-caja">${esc(err.message)}</div>`;
    }
  });

  document.querySelectorAll("[data-eliminar-foto]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("¿Eliminar esta foto?")) return;
      await api(`/api/fotos/${btn.dataset.eliminarFoto}`, { method: "DELETE" });
      await renderFicha();
    });
  });

  // --- Carrusel / rejilla de documentos por categoría ----------------------
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
  inputArchivoCarrusel?.addEventListener("change", async () => {
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
      <table class="est-tabla-masiva">
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
                  : '<span style="font-size:22px"><i data-lucide=file-text class=ico></i> </span>'
              }</td>
              <td class="est-celda-archivo" title="${esc(nombreMostrado)}">${esc(nombreMostrado)}</td>
              <td>
                <select data-subida-categoria="${i}">
                  <option value="" ${!item.categoria ? "selected" : ""}>No incluir (descartar)</option>
                  ${CATEGORIAS_DOCUMENTO.map((c) => `<option value="${c.nombre}" ${c.nombre === item.categoria ? "selected" : ""}>${c.nombre}</option>`).join("")}
                </select>
                ${item.categoria && conteoPorCategoria[item.categoria] > 1 ? '<div class="pendiente" style="color:var(--rojo); font-size:11px"><i data-lucide=triangle-alert class=ico></i> repetida con otro archivo de la lista</div>' : ""}
              </td>
              <td><button type="button" class="boton secundario boton-chico" data-subida-quitar="${i}"><i data-lucide=x class=ico></i> </button></td>
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
        resultado.innerHTML = `<p class="pendiente">Subiendo ${i + 1} de ${paraSubir.length}: ${esc(nombreMostrado)}...</p>`;
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
          resultado.innerHTML = `<div class="alerta-caja">Error subiendo "${esc(nombreMostrado)}": ${esc(err.message)}. Se detuvo aquí — los anteriores ya quedaron guardados, intenta de nuevo con los que faltan.</div>`;
          boton.disabled = false;
          return;
        }
      }
      const subidos = paraSubir.length;
      archivosSubidaMasiva = [];
      cerrarModalesFicha();
      fichaSub = "documentos";
      fichaAviso = { tipo: "exito", texto: `${subidos} documento(s) subido(s).` };
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
      const faltantesAhora = categoriasFaltantesOrdenadas(e.fotos, anio).filter((c) => !yaUsadas.has(c.nombre));
      const sugerida = faltantesAhora[0] || null;
      archivosSubidaMasiva.push({
        tipo: "imagen",
        file,
        categoria: sugerida ? sugerida.nombre : null,
        previewUrl: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
      });
    }
    pintarListaSubidaMasiva();
  });

  // --- Ficha oficial: visor, zoom y acciones ------------------------------
  document.getElementById("zoom-ficha").addEventListener("input", aplicarZoomFicha);
  document.querySelectorAll("[data-zoom-paso]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const control = document.getElementById("zoom-ficha");
      const nuevo = Number(control.value) + Number(btn.dataset.zoomPaso);
      control.value = String(Math.min(Number(control.max), Math.max(Number(control.min), nuevo)));
      aplicarZoomFicha();
    });
  });
  document.getElementById("btn-cerrar-visor").addEventListener("click", cerrarVisorFicha);

  cargarHojaFicha(e);
  cargarRiesgoFicha(e);
  document.getElementById("ficha-contenedor").addEventListener("input", () => programarEvaluacionFicha(e));
  if (fichaVisorAbierto) bloquearScrollFondo(true);

  const descargarFicha = async (formato) => {
    pintarResultadoFicha("<p>Generando...</p>");
    let avisoGuardado = "";
    try {
      await guardarDatosFicha(e);
      avisoGuardado = " Los datos quedaron guardados en el estudiante.";
    } catch (err) {
      avisoGuardado = ` (No se pudieron guardar en el estudiante: ${esc(err.message)}.)`;
    }
    const campos = {};
    document.querySelectorAll("#ficha-hoja input").forEach((i) => { campos[i.name] = i.value; });
    try {
      // Devuelve un archivo binario (no JSON): no puede pasar por api().
      await asegurarSesionFresca();
      const res = await fetch("/api/certificados/ficha-matricula", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ estudiante_id: e.id, campos, formato }),
      });
      if (!res.ok) {
        const cuerpo = await res.json().catch(() => ({}));
        throw new Error(cuerpo.detail || `Error ${res.status}`);
      }
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `Ficha matricula - ${nombreCompleto}.${formato}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      const autorizada = res.headers.get("X-Promocion") === "autorizada";
      pintarResultadoFicha('<p class="exito-caja">Ficha generada y descargada.' +
        (autorizada ? " Grado autorizado por coordinación." : "") + avisoGuardado + "</p>");
    } catch (err) {
      pintarResultadoFicha(`<p class="alerta-caja">${esc(err.message)}</p>`);
    }
  };

  const guardarFichaEnEstudiante = async () => {
    try {
      await guardarDatosFicha(e);
      pintarResultadoFicha('<p class="exito-caja">Datos guardados en el estudiante.</p>');
      pintarDatosMatriculaGuardados(e);
    } catch (err) {
      pintarResultadoFicha(`<p class="alerta-caja">No se pudo guardar: ${esc(err.message)}</p>`);
    }
  };

  // Un solo lugar para las acciones de la ficha: los mismos botones aparecen
  // en el Resumen, en el panel de Matrícula y en la barra del visor.
  document.querySelectorAll("[data-ficha-accion]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const accion = btn.dataset.fichaAccion;
      // Generar o imprimir con un grado que necesita permiso de coordinación
      // (y no lo tiene aprobado) no se deja — ver promocionPermiteGenerar().
      if (["imprimir", "pdf", "word"].includes(accion) && !(await promocionPermiteGenerar(e))) return;
      if (accion === "abrir") abrirVisorFicha();
      else if (accion === "imprimir") imprimirFicha();
      else if (accion === "pdf") descargarFicha("pdf");
      else if (accion === "word") descargarFicha("docx");
      else if (accion === "guardar") guardarFichaEnEstudiante();
    });
  });

  // --- Constancia ---------------------------------------------------------
  const formConstancia = document.getElementById("form-constancia");
  if (formConstancia) {
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
        cont.innerHTML = `<div class="alerta-caja">${esc(err.message)}</div>`;
      }
    });
  }
}

// Escape cierra primero el visor de la ficha y luego los modales de
// documentos (el escáner y la sidebar manejan su propio Escape).
document.addEventListener("keydown", (ev) => {
  if (ev.key !== "Escape") return;
  if (fichaVisorAbierto) cerrarVisorFicha();
  else if (fichaModalAbierto) cerrarModalesFicha();
});
