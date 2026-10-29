// --- Libro de registro de matrícula -----------------------------------------
// Segunda hoja que se firma al matricular (sobre todo a un estudiante nuevo):
// copia del Word oficial "LIBRO DE MATRICULA IETABA 2026" — membrete, los
// renglones con los datos y tres firmas (estudiante, acudiente y responsable
// de la matrícula). Se escribe directamente sobre la hoja; lo que solo pide
// este libro (padres, teléfono, huérfano, albergue) se guarda en los datos de
// la ficha del estudiante (backend/app/datos_ficha.py, TEXTOS_LIBRO).

const LIBRO_LUGAR = "PREDIO EL VERDE, RESGUARDO INDIGENA AWA EL GRAN SABALO, MUNICIPIO DE BARBACOAS NARIÑO";
// Pares Si/No: al hacer clic en una casilla se marca con X y se limpia la otra.
const LIBRO_PARES = [["desplaz_si", "desplaz_no"], ["huerfano_si", "huerfano_no"], ["albergue_si", "albergue_no"],
  ["est_antiguo", "est_nuevo"]];
const LIBRO_MARCAS = new Set(["desplaz_si", "desplaz_no", "huerfano_si", "huerfano_no", "albergue_si", "albergue_no",
  "est_antiguo", "est_nuevo", "disc_cognitiva", "disc_sordera", "disc_fisica", "disc_ceguera"]);
// Casillas que vienen de la ficha (no se guardan desde aquí: el libro las
// muestra ya armadas, ej. "lugar y fecha de nacimiento" o la dirección =
// resguardo + comunidad; esas se corrigen en la ficha).
const LIBRO_SOLO_HOJA = new Set(["nombre", "nacimiento", "documento", "direccion", "municipio_expedicion", "grado", "anio", "est_antiguo", "est_nuevo",
  "dilig_dia", "dilig_mes", "dilig_anio", "lugar", "firma_nombre_est", "responsable"]);

// La hoja en pantalla copia el Word oficial (plantillas/libro_matricula.docx):
// mismo membrete, renglones con el dato subrayado, firmas y pie de página.
// Lo que se descarga en Word/PDF sale de esa plantilla (app/libro_matricula.py).
const LIBRO_ESTILO = `<style>
.lb{--z:1.3;zoom:var(--z);width:640px;max-width:none;margin:0 auto;background:#fff;color:#000;font-family:Arial,Helvetica,sans-serif;font-size:10.5px;padding:34px 46px 22px;box-sizing:border-box;box-shadow:0 2px 12px rgba(0,0,0,.12)}
.lb-enc{display:flex;align-items:center;gap:10px}
.lb-enc img{width:72px;height:72px;object-fit:contain}
.lb-enc div{flex:1;text-align:center;line-height:1.25;font-size:8px;color:#555}
.lb-enc b{display:block;font-size:8.5px;color:#555}.lb-enc em{display:block;font-family:"Brush Script MT",cursive;font-size:12px;text-decoration:underline}
.lb h2{text-align:center;font-size:14px;font-weight:400;margin:28px 0 0}.lb h3{text-align:center;font-size:14px;font-style:italic;font-weight:400;margin:0 0 26px}
.lb p{margin:0 0 5px;line-height:1.55;white-space:nowrap}
.lb input{border:0;border-bottom:1px solid #000;background:transparent;font:700 10.5px Arial,Helvetica,sans-serif;color:#0b2a7a;padding:0 2px;outline:0;box-sizing:border-box}
.lb input.lb-x{width:22px;text-align:center;cursor:pointer}
.lb input:hover{background:rgba(255,255,170,.5)}.lb input:focus{background:rgba(255,255,140,.9)}
.lb input.lb-falta{background:rgba(255,120,120,.3)}
.lb input[name=lugar]{width:100%!important;font-weight:400;font-style:italic;font-size:10px;color:#000;border:0;padding:0}
.lb-firma{display:grid;grid-template-columns:1fr 1fr;gap:56px;margin-top:40px;font-size:9.5px}
.lb-firma div{display:flex;flex-direction:column;justify-content:flex-end}
.lb-firma input{width:100%;text-align:left}
.lb-firma span{padding-top:3px}.lb-firma .lb-linea{border-top:1px solid #000}
.lb-pie{margin-top:48px;border-top:1px solid #000;padding-top:3px;text-align:center;font-size:7.5px;color:#444;line-height:1.35}
.lb-pie em{display:block;font-family:"Brush Script MT",cursive;font-size:11px;color:#000}
@media print{@page{size:letter;margin:12mm}.lb{zoom:1;width:100%;padding:0;box-shadow:none}.lb input{color:#000}.lb input.lb-falta{background:transparent}}
</style>`;

function libroCampo(nombre, ancho, extra = "") {
  const clase = LIBRO_MARCAS.has(nombre) ? "lb-x" : "";
  return `<input name="${nombre}" class="${clase}" style="${ancho ? `width:${ancho}` : ""}" autocomplete="off" ${extra} />`;
}

function libroHojaHtml(anio) {
  const c = libroCampo;
  return `${LIBRO_ESTILO}
  <div class="lb" id="libro-hoja">
    <div class="lb-enc">
      <img src="/static/logos/logo2.jpeg" alt="" />
      <div>
        <b>UNIDAD INDIGENA DEL PUEBLO AWA “UNIPA”</b>
        <b>INSTITUCION EDUCATIVA INDIGENATECNICA AGROAMBIENTAL BILINGÜE AWA “IETABA”</b>
        <b>Licencia de Funcionamiento No. 398 del 28 de abril del 2004</b>
        <b>Emanada de la Secretaría Departamental de Educación y Cultura de Nariño</b>
        <b>Código DANE 25207900204501 - NIT. 900000095-4</b>
        <em>Ambiente – Cultura – Ciencia</em>
      </div>
    </div>
    <h2>LIBRO DE REGISTRO DE MATRICULAS</h2>
    <h3>(AÑO ESCOLAR ${anio})</h3>
    <p>NOMBRES Y APELLIDOS DEL ESTUDIANTE: &nbsp;${c("nombre", "300px")}</p>
    <p>LUGAR Y FECHA DE NACIMIENTO: &nbsp;${c("nacimiento", "320px")}</p>
    <p>No IDENTIFICACION: ${c("documento", "130px")} &nbsp;&nbsp; EXPEDIDO: &nbsp;${c("municipio_expedicion", "160px")}</p>
    <p>DIRECCION: ${c("direccion", "440px")}</p>
    <p>HIJO DE: ${c("padres", "450px")}</p>
    <p>MATRICULADO (A) PARA EL GRADO: ${c("grado", "150px")} AÑO ESCOLAR: ${c("anio", "60px", "readonly")}</p>
    <p>SITUACION ACTUAL DEL ESTUDIANTE: DESPLAZADO &nbsp; SI${c("desplaz_si")} NO ${c("desplaz_no")} &nbsp;&nbsp;&nbsp;&nbsp;
      HUERFANO &nbsp; SI${c("huerfano_si")} NO ${c("huerfano_no")}</p>
    <p>NECESITA HOSPEDAJE EN EL ALBERGUE SI ${c("albergue_si")} NO ${c("albergue_no")} &nbsp;DISCAPACIDAD: &nbsp;COGNITIVA: ${c("disc_cognitiva")}</p>
    <p>SORDOMUDO ${c("disc_sordera")} &nbsp;&nbsp;&nbsp; DIFICULTAD PARA MOVERSE ${c("disc_fisica")} &nbsp;&nbsp;&nbsp; CEGUERA ${c("disc_ceguera")}</p>
    <p>No DE TELEFONO: ${c("telefono", "160px")}</p>
    <p>ESTUDIANTE ANTIGUO ${c("est_antiguo")} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ESTUDIANTE NUEVO ${c("est_nuevo")}</p>
    <p>PROVIENE DEL C. EDUCATIVO: ${c("procedencia", "360px")}</p>
    <p>FECHA DE DILIGENCIAMIENTO: DIA ${c("dilig_dia", "40px")} MES ${c("dilig_mes", "100px")} AÑO ${c("dilig_anio", "50px")}</p>
    <p style="display:flex;gap:4px;font-style:italic">LUGAR: ${c("lugar")}</p>
    <div class="lb-firma">
      <div>${c("firma_nombre_est")}<span>NOMBRES Y APELLIDOS</span></div>
      <div><span class="lb-linea">FIRMA DEL ESTUDIANTE</span></div>
    </div>
    <div class="lb-firma">
      <div>${c("acudiente")}<span>NOMBRES Y APELLIDOS ACUDIENTE</span></div>
      <div><span class="lb-linea">FIRMA O HUELLA DEL PADRE, MADRE. O ACUDIENTE</span></div>
    </div>
    <div class="lb-firma">
      <div>${c("responsable")}<span style="font-size:8px">NOMBRES Y APELLIDOS DEL RESPONSABLE DE LA MATRICULA</span></div>
      <div><span class="lb-linea">FIRMA DEL RESPONSABLE</span></div>
    </div>
    <div class="lb-pie">
      <em>Por la pervivencia e identidad del Pueblo Awa</em>
      Unidad administrativa – Predio el Verde, resguardo el Gran Sábalo – El Diviso- Barbacoas Nariño<br />
      E- Mail: ietaba.awa@hotmail.com
    </div>
  </div>`;
}

function libroValoresIniciales(e, nombreCompleto, guardado) {
  const fn = e.fecha_nacimiento ? new Date(`${e.fecha_nacimiento}T00:00:00`) : null;
  const hoy = new Date();
  const g = guardado || {};
  const nombreGrado = (NOMBRES_GRADOS.find(([n]) => n === e.grado)?.[1] || String(e.grado ?? "")).toUpperCase();
  const fechaNac = fn ? `${(MESES_TEXTO[fn.getMonth() + 1] || "").toUpperCase()} ${fn.getDate()} DEL ${fn.getFullYear()}` : "";
  const direccion = [g.resguardo, g.direccion].filter(Boolean).join(" – ");
  const nuevo = !!e.matricula_nueva_este_anio;
  return {
    ...g,
    nombre: nombreCompleto.toUpperCase(),
    nacimiento: [g.municipio_nacimiento, fechaNac].filter(Boolean).join(" – ").toUpperCase(),
    documento: e.documento || "",
    municipio_expedicion: (e.lugar_expedicion_documento || g.municipio_expedicion || "").toUpperCase(),
    direccion: direccion.toUpperCase(),
    // Renovación: a qué grado pasa todavía no está decidido (igual que en la
    // ficha); el nuevo entra al grado en que se matriculó.
    grado: nuevo ? nombreGrado : "",
    anio: String(e.anio_ficha_matricula || new Date().getFullYear() + 1),
    est_nuevo: nuevo ? "X" : "",
    est_antiguo: nuevo ? "" : "X",
    dilig_dia: String(hoy.getDate()),
    dilig_mes: (MESES_TEXTO[hoy.getMonth() + 1] || "").toUpperCase(),
    dilig_anio: String(hoy.getFullYear()),
    lugar: LIBRO_LUGAR,
    firma_nombre_est: nombreCompleto.toUpperCase(),
    acudiente: g.acudiente || "",
    responsable: ((typeof sesionActual !== "undefined" && sesionActual?.usuario?.nombre) || "").toUpperCase(),
  };
}

// Rojo = dato que falta (solo en pantalla; al imprimir no se ve).
function libroMarcarFaltantes(hoja) {
  hoja.querySelectorAll("input").forEach((i) => {
    i.classList.toggle("lb-falta", !LIBRO_MARCAS.has(i.name) && !i.value.trim());
  });
}

// Mismo visor que la ficha: pantalla completa, zoom, guardar, Word, PDF e
// imprimir. Desde la ficha se llega con «Siguiente: libro de matrícula».
async function abrirLibroMatricula(e, nombreCompleto) {
  document.getElementById("libro-visor")?.remove();
  const anio = e.anio_ficha_matricula || new Date().getFullYear() + 1;
  const zoom = Number(leerPreferencia("ietaba_zoom_ficha", "130")) || 130;
  const visor = document.createElement("div");
  visor.className = "est-visor";
  visor.id = "libro-visor";
  visor.setAttribute("role", "dialog");
  visor.setAttribute("aria-label", "Libro de registro de matrícula");
  visor.innerHTML = `
    <header class="est-visor-barra">
      <div class="est-visor-titulo">
        <strong>Libro de registro de matrícula · ${anio}</strong>
        <span>${esc(nombreCompleto)} · Doc. ${esc(e.documento)}</span>
      </div>
      <div class="est-visor-controles">
        <div class="est-visor-zoom">
          <button type="button" class="est-visor-zoom-btn" data-zoom-paso="-10" aria-label="Alejar">−</button>
          <input type="range" min="60" max="200" step="5" value="${zoom}" aria-label="Zoom" data-libro-zoom />
          <button type="button" class="est-visor-zoom-btn" data-zoom-paso="10" aria-label="Acercar">+</button>
          <span data-libro-zoom-valor>${zoom}%</span>
        </div>
        <button type="button" class="boton secundario" data-libro-accion="ficha">← Ficha</button>
        <button type="button" class="boton" data-libro-accion="guardar">Guardar en el estudiante</button>
        <button type="button" class="boton secundario" data-libro-accion="docx">Word</button>
        <button type="button" class="boton secundario" data-libro-accion="pdf">PDF</button>
        <button type="button" class="boton secundario" data-libro-accion="imprimir">Imprimir</button>
        <button type="button" class="est-visor-cerrar" data-libro-accion="cerrar" aria-label="Cerrar"></button>
      </div>
    </header>
    <div class="est-visor-avisos"><div data-libro-resultado></div></div>
    <div class="est-visor-lienzo">${libroHojaHtml(anio)}</div>`;
  document.body.appendChild(visor);
  bloquearScrollFondo(true);

  const hoja = visor.querySelector("#libro-hoja");
  const zoomInput = visor.querySelector("[data-libro-zoom]");
  const aplicarZoom = (recordar = true) => {
    hoja.style.setProperty("--z", Number(zoomInput.value) / 100);
    visor.querySelector("[data-libro-zoom-valor]").textContent = `${zoomInput.value}%`;
    if (recordar) guardarPreferencia("ietaba_zoom_ficha", zoomInput.value);
  };
  zoomInput.addEventListener("input", () => aplicarZoom());
  visor.querySelectorAll("[data-zoom-paso]").forEach((b) => b.addEventListener("click", () => {
    zoomInput.value = Number(zoomInput.value) + Number(b.dataset.zoomPaso);
    aplicarZoom();
  }));
  // En el celular la hoja (640px) no cabe: se abre ajustada al ancho, sin
  // cambiar el zoom que la persona dejó guardado para el computador.
  const anchoDisponible = visor.querySelector(".est-visor-lienzo").clientWidth - 36;
  const ajuste = Math.floor((anchoDisponible / 640) * 20) * 5;
  if (ajuste < Number(zoomInput.value)) {
    zoomInput.min = String(Math.min(40, ajuste));
    zoomInput.value = String(ajuste);
    aplicarZoom(false);
  } else {
    aplicarZoom();
  }

  let guardado = {};
  try {
    guardado = (await api(fichaUrlDatosFicha(e.id))).campos || {};
  } catch {
    /* sin permiso o sin datos: la hoja sale con lo que se sabe del estudiante */
  }
  const inicial = libroValoresIniciales(e, nombreCompleto, guardado);
  hoja.querySelectorAll("input").forEach((i) => { i.value = inicial[i.name] || ""; });
  libroMarcarFaltantes(hoja);
  hoja.addEventListener("input", () => libroMarcarFaltantes(hoja));
  hoja.querySelectorAll("input.lb-x").forEach((i) => {
    i.readOnly = true;
    i.addEventListener("click", () => {
      const marcar = !i.value;
      const par = LIBRO_PARES.find((p) => p.includes(i.name));
      if (par && marcar) par.forEach((n) => { hoja.querySelector(`[name="${n}"]`).value = ""; });
      i.value = marcar ? "X" : "";
      libroMarcarFaltantes(hoja);
    });
  });

  const resultado = visor.querySelector("[data-libro-resultado]");
  const cerrar = () => {
    visor.remove();
    if (document.getElementById("ficha-visor")?.hidden !== false) bloquearScrollFondo(false);
  };
  // Se parte de lo ya guardado de la ficha para no borrar lo que el libro no
  // muestra (etnia, traslado, SGP...).
  const guardar = async () => {
    const campos = { ...guardado };
    hoja.querySelectorAll("input").forEach((i) => {
      if (!LIBRO_SOLO_HOJA.has(i.name)) campos[i.name] = i.value.trim();
    });
    const discap = ["disc_cognitiva", "disc_sordera", "disc_fisica", "disc_ceguera", "disc_down", "disc_multiple", "disc_otras"]
      .some((k) => (campos[k] || "").trim());
    if (discap) Object.assign(campos, { discap_si: "X", discap_no: "" });
    const r = await api(fichaUrlDatosFicha(e.id), { method: "PUT", body: JSON.stringify({ campos }) });
    guardado = r.campos || campos;
  };
  const descargar = async (formato) => {
    resultado.innerHTML = "<p>Generando...</p>";
    let aviso = " Los datos quedaron guardados en el estudiante.";
    try {
      await guardar();
    } catch (err) {
      aviso = ` (No se pudieron guardar en el estudiante: ${esc(err.message)}.)`;
    }
    const campos = {};
    hoja.querySelectorAll("input").forEach((i) => { campos[i.name] = i.value.trim(); });
    campos.expedido = campos.municipio_expedicion;
    try {
      // Devuelve un archivo binario (no JSON): no puede pasar por api().
      await asegurarSesionFresca();
      const res = await fetch("/api/certificados/libro-matricula", {
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
      a.download = `Libro matricula - ${nombreCompleto}.${formato}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      resultado.innerHTML = `<p class="exito-caja">Libro generado y descargado.${aviso}</p>`;
    } catch (err) {
      resultado.innerHTML = `<p class="alerta-caja">${esc(err.message)}</p>`;
    }
  };
  visor.querySelectorAll("[data-libro-accion]").forEach((btn) => btn.addEventListener("click", async () => {
    const accion = btn.dataset.libroAccion;
    if (accion === "cerrar") cerrar();
    else if (accion === "ficha") { cerrar(); abrirVisorFicha(); }
    else if (accion === "imprimir") imprimirLibroMatricula(hoja);
    else if (accion === "docx" || accion === "pdf") descargar(accion);
    else if (accion === "guardar") {
      btn.disabled = true;
      try {
        await guardar();
        resultado.innerHTML = '<div class="exito-caja"><i data-lucide=circle-check class=ico></i> Guardado en el estudiante.</div>';
      } catch (err) {
        resultado.innerHTML = `<div class="alerta-caja">No se pudo guardar: ${esc(err.message)}</div>`;
      } finally {
        btn.disabled = false;
        if (window.lucide) lucide.createIcons();
      }
    }
  }));
}

function imprimirLibroMatricula(hoja) {
  const copia = hoja.cloneNode(true);
  hoja.querySelectorAll("input").forEach((orig, i) => {
    const c = copia.querySelectorAll("input")[i];
    c.setAttribute("value", orig.value);
    c.classList.remove("lb-falta");
  });
  const w = window.open("", "_blank");
  w.document.write(`<!doctype html><meta charset="utf-8"><title>Libro de registro de matrícula</title>${LIBRO_ESTILO}<body style="margin:0">${copia.outerHTML}</body>`);
  w.document.close();
  w.onload = () => { w.focus(); w.print(); };
  setTimeout(() => { try { w.focus(); w.print(); } catch {} }, 700);
}
