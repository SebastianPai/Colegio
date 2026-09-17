// --- Escáner documental (cámara -> detección -> corrección -> mejora -> --
// --- multipágina -> PDF) --------------------------------------------------
//
// Módulo aislado: expone abrirEscanerDocumento({ titulo, onGuardar }).
// No conoce nada de "estudiantes" ni "fotos" — quien lo abre le pasa un
// callback onGuardar(archivo, nombreSugerido) que hace la subida real
// reutilizando el endpoint que ya existe (POST /api/estudiantes/{id}/fotos).
//
// OpenCV.js (detección de contorno, perspectiva, mejora) y jsPDF (armar el
// PDF final) se cargan bajo demanda, alojados localmente en /static/vendor
// — esta app corre sin internet en la red del colegio, así que no pueden
// venir de un CDN.

// --- Carga bajo demanda de las librerías -----------------------------------

function cargarScript(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) return resolve();
    const s = document.createElement("script");
    s.src = src;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error(`No se pudo cargar ${src}`));
    document.head.appendChild(s);
  });
}

let _opencvListo = null;
function asegurarOpenCv() {
  if (_opencvListo) return _opencvListo;
  _opencvListo = cargarScript("/static/vendor/opencv.js").then(
    () =>
      new Promise((resolve, reject) => {
        if (window.cv && window.cv.Mat) return resolve();
        if (!window.cv) return reject(new Error("OpenCV.js no se inicializó"));
        const anterior = window.cv["onRuntimeInitialized"];
        window.cv["onRuntimeInitialized"] = () => {
          if (typeof anterior === "function") anterior();
          resolve();
        };
      })
  );
  return _opencvListo;
}

let _jspdfListo = null;
function asegurarJsPdf() {
  if (_jspdfListo) return _jspdfListo;
  _jspdfListo = cargarScript("/static/vendor/jspdf.umd.min.js");
  return _jspdfListo;
}

// --- Punto de entrada público -----------------------------------------------

async function abrirEscanerDocumento({ titulo, onGuardar }) {
  const estado = {
    titulo: titulo || "Documento",
    onGuardar,
    paginas: [], // { dataUrl }
    stream: null,
    facingMode: "environment",
    deteccionTimer: null,
    ultimosCorners: null,
    paginaEnRevision: null, // { canvasCaptura, corners, modo, dataUrl }
  };

  const overlay = document.createElement("div");
  overlay.className = "escaner-overlay";
  document.body.appendChild(overlay);
  const overflowPrevio = document.body.style.overflow;
  document.body.style.overflow = "hidden";

  function cerrar() {
    detenerDeteccion(estado);
    detenerCamara(estado);
    document.body.style.overflow = overflowPrevio;
    overlay.remove();
  }

  pintarCargando(overlay, "Abriendo escáner...");

  if (!window.isSecureContext) {
    pintarFallback(
      overlay,
      estado,
      cerrar,
      "El navegador exige una conexión segura (HTTPS) para usar la cámara desde la web. Puedes tomar la foto o subir el archivo directamente."
    );
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    pintarFallback(overlay, estado, cerrar, "Este navegador no permite acceder a la cámara desde la web.");
    return;
  }

  try {
    await Promise.all([asegurarOpenCv(), asegurarJsPdf()]);
  } catch (err) {
    pintarFallback(overlay, estado, cerrar, "No se pudo cargar el escáner (revisa la conexión) — puedes subir el archivo directamente.");
    return;
  }

  await iniciarVistaCamara(overlay, estado, cerrar);
}

// --- Cámara ------------------------------------------------------------

async function iniciarCamara(estado, video, facingMode) {
  const constraints = {
    audio: false,
    video: {
      facingMode: { ideal: facingMode },
      width: { ideal: 1920 },
      height: { ideal: 1080 },
    },
  };
  const stream = await navigator.mediaDevices.getUserMedia(constraints);
  estado.stream = stream;
  estado.facingMode = facingMode;
  video.srcObject = stream;
  await video.play();
}

function detenerCamara(estado) {
  if (estado.stream) {
    estado.stream.getTracks().forEach((t) => t.stop());
    estado.stream = null;
  }
}

function detenerDeteccion(estado) {
  if (estado.deteccionTimer) {
    clearTimeout(estado.deteccionTimer);
    estado.deteccionTimer = null;
  }
}

function mensajeErrorCamara(err) {
  if (err && err.name === "NotAllowedError") return "No se concedió permiso para usar la cámara.";
  if (err && err.name === "NotFoundError") return "No se encontró ninguna cámara en este dispositivo.";
  if (err && err.name === "NotReadableError") return "La cámara está siendo usada por otra aplicación.";
  return "Puedes tomar la foto o subir el archivo directamente.";
}

// --- Vista: cámara en vivo + detección --------------------------------

async function iniciarVistaCamara(overlay, estado, cerrar) {
  overlay.innerHTML = `
    <div class="escaner-camara">
      <div class="escaner-topbar">
        <button type="button" class="escaner-icono-btn" id="escaner-cerrar" aria-label="Cerrar escáner">✕</button>
        <span class="escaner-titulo-modulo">${estado.titulo}</span>
        <button type="button" class="escaner-icono-btn" id="escaner-cambiar-camara" aria-label="Cambiar cámara" title="Cambiar cámara">🔄</button>
      </div>
      <div class="escaner-video-wrap">
        <video id="escaner-video" playsinline muted autoplay></video>
        <canvas id="escaner-overlay-canvas"></canvas>
        <p class="escaner-estado-deteccion" id="escaner-estado-deteccion">Buscando documento...</p>
      </div>
      <div class="escaner-controles">
        ${estado.paginas.length ? `<button type="button" class="escaner-chip-paginas" id="escaner-ver-paginas">${estado.paginas.length} pág.</button>` : "<span></span>"}
        <button type="button" class="escaner-disparador" id="escaner-capturar" aria-label="Capturar página"></button>
        <span></span>
      </div>
    </div>
  `;

  document.getElementById("escaner-cerrar").addEventListener("click", () => {
    if (estado.paginas.length && !confirm("¿Salir del escáner? Se perderán las páginas ya capturadas.")) return;
    cerrar();
  });
  document.getElementById("escaner-ver-paginas")?.addEventListener("click", () => mostrarPaginas(overlay, estado, cerrar));

  const video = document.getElementById("escaner-video");
  try {
    await iniciarCamara(estado, video, estado.facingMode);
  } catch (err) {
    pintarFallback(overlay, estado, cerrar, mensajeErrorCamara(err));
    return;
  }

  document.getElementById("escaner-cambiar-camara").addEventListener("click", async () => {
    const anterior = estado.facingMode;
    detenerDeteccion(estado);
    detenerCamara(estado);
    try {
      await iniciarCamara(estado, video, anterior === "environment" ? "user" : "environment");
    } catch {
      await iniciarCamara(estado, video, anterior); // si falla, se vuelve a la que sí funcionaba
    }
    iniciarBucleDeteccion(estado, video, document.getElementById("escaner-overlay-canvas"), document.getElementById("escaner-estado-deteccion"));
  });

  document.getElementById("escaner-capturar").addEventListener("click", () => capturarPagina(overlay, estado, cerrar));

  iniciarBucleDeteccion(estado, video, document.getElementById("escaner-overlay-canvas"), document.getElementById("escaner-estado-deteccion"));
}

// --- Detección de documento (OpenCV.js) ---------------------------------
// Corre sobre un cuadro reducido (máx. 400px de lado) cada ~220ms — no en
// cada frame — para no calentar el teléfono ni gastar batería. Es solo
// realimentación visual: la captura SIEMPRE es manual (botón disparador),
// nunca automática.

const LADO_MAX_DETECCION = 400;

function iniciarBucleDeteccion(estado, video, canvasOverlay, etiquetaEstado) {
  const paso = () => {
    if (!estado.stream) return; // cámara detenida (modal cerrado / cambiando de cámara)
    if (video.videoWidth) {
      const corners = detectarEsquinas(video);
      estado.ultimosCorners = corners;
      pintarOverlayEsquinas(canvasOverlay, video, corners);
      etiquetaEstado.textContent = corners ? "Documento detectado ✓" : "Buscando documento...";
      etiquetaEstado.classList.toggle("detectado", !!corners);
    }
    estado.deteccionTimer = setTimeout(paso, 220);
  };
  paso();
}

// Reduce un contorno a 4 esquinas. Primero intenta approxPolyDP con varios
// niveles de tolerancia (bordes reales rara vez simplifican a un polígono
// perfecto de 4 lados a la primera). Si ninguno da un cuadrilátero convexo,
// usa el rectángulo rotado que mejor lo envuelve (minAreaRect) — mucho más
// tolerante con sombras/ruido que exigir un polígono exacto.
function aproximarCuadrilatero(cnt, area) {
  const peri = cv.arcLength(cnt, true);
  for (const factor of [0.02, 0.035, 0.05]) {
    const approx = new cv.Mat();
    cv.approxPolyDP(cnt, approx, factor * peri, true);
    if (approx.rows === 4 && cv.isContourConvex(approx)) {
      const pts = [];
      for (let i = 0; i < 4; i++) pts.push({ x: approx.intPtr(i, 0)[0], y: approx.intPtr(i, 0)[1] });
      approx.delete();
      return pts;
    }
    approx.delete();
  }
  const rect = cv.minAreaRect(cnt);
  if (rect.size.width * rect.size.height < area * 0.6) return null; // el rectángulo no representa bien la forma real
  return esquinasDeRectanguloRotado(rect);
}

function esquinasDeRectanguloRotado(rect) {
  const { center, size, angle } = rect;
  const anguloRad = (angle * Math.PI) / 180;
  const cosA = Math.cos(anguloRad),
    sinA = Math.sin(anguloRad);
  const w2 = size.width / 2,
    h2 = size.height / 2;
  return [
    [-w2, -h2],
    [w2, -h2],
    [w2, h2],
    [-w2, h2],
  ].map(([dx, dy]) => ({ x: center.x + dx * cosA - dy * sinA, y: center.y + dx * sinA + dy * cosA }));
}

function detectarEsquinas(video) {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  const escala = LADO_MAX_DETECCION / Math.max(vw, vh);
  const w = Math.max(1, Math.round(vw * escala));
  const h = Math.max(1, Math.round(vh * escala));

  if (!detectarEsquinas._canvas) detectarEsquinas._canvas = document.createElement("canvas");
  const c = detectarEsquinas._canvas;
  c.width = w;
  c.height = h;
  c.getContext("2d").drawImage(video, 0, 0, w, h);

  let src, gray, blur, edges, dilated, kernel, contours, hierarchy;
  try {
    src = cv.imread(c);
    gray = new cv.Mat();
    cv.cvtColor(src, gray, cv.COLOR_RGBA2GRAY);
    blur = new cv.Mat();
    cv.GaussianBlur(gray, blur, new cv.Size(5, 5), 0);

    // Umbral de Canny adaptado al brillo real del cuadro (en vez de una
    // constante fija que solo servía con la luz de las pruebas de mesa).
    const media = cv.mean(blur)[0];
    const umbralBajo = Math.max(10, media * 0.5);
    const umbralAlto = Math.min(255, media * 1.2);

    edges = new cv.Mat();
    cv.Canny(blur, edges, umbralBajo, umbralAlto);
    dilated = new cv.Mat();
    kernel = cv.Mat.ones(3, 3, cv.CV_8U);
    cv.dilate(edges, dilated, kernel, new cv.Point(-1, -1), 2);

    contours = new cv.MatVector();
    hierarchy = new cv.Mat();
    cv.findContours(dilated, contours, hierarchy, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE);

    let mejorArea = w * h * 0.12; // el documento debe ocupar al menos ~12% del cuadro
    let mejor = null;
    for (let i = 0; i < contours.size(); i++) {
      const cnt = contours.get(i);
      const area = cv.contourArea(cnt);
      if (area > mejorArea) {
        const candidato = aproximarCuadrilatero(cnt, area);
        if (candidato) {
          mejorArea = area;
          mejor = candidato;
        }
      }
      cnt.delete();
    }

    if (!mejor) return null;
    return ordenarEsquinas(mejor.map((p) => ({ x: p.x / escala, y: p.y / escala })));
  } catch (err) {
    return null;
  } finally {
    src?.delete();
    gray?.delete();
    blur?.delete();
    edges?.delete();
    dilated?.delete();
    kernel?.delete();
    contours?.delete();
    hierarchy?.delete();
  }
}

// Ordena 4 puntos como top-left, top-right, bottom-right, bottom-left,
// para poder mapearlos siempre al mismo rectángulo de destino.
function ordenarEsquinas(pts) {
  const suma = pts.map((p) => p.x + p.y);
  const resta = pts.map((p) => p.x - p.y);
  const tl = pts[suma.indexOf(Math.min(...suma))];
  const br = pts[suma.indexOf(Math.max(...suma))];
  const tr = pts[resta.indexOf(Math.max(...resta))];
  const bl = pts[resta.indexOf(Math.min(...resta))];
  return [tl, tr, br, bl];
}

function pintarOverlayEsquinas(canvas, video, corners) {
  const rect = video.getBoundingClientRect();
  if (canvas.width !== rect.width || canvas.height !== rect.height) {
    canvas.width = rect.width;
    canvas.height = rect.height;
  }
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!corners) return;

  // El <video> se muestra con object-fit:cover — hay que mapear las
  // coordenadas (en píxeles nativos del video) al recorte real en pantalla.
  const vw = video.videoWidth,
    vh = video.videoHeight;
  const escalaCover = Math.max(canvas.width / vw, canvas.height / vh);
  const offX = (canvas.width - vw * escalaCover) / 2;
  const offY = (canvas.height - vh * escalaCover) / 2;
  const mapear = (p) => ({ x: p.x * escalaCover + offX, y: p.y * escalaCover + offY });
  const [tl, tr, br, bl] = corners.map(mapear);

  ctx.strokeStyle = "#22c55e";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(tl.x, tl.y);
  ctx.lineTo(tr.x, tr.y);
  ctx.lineTo(br.x, br.y);
  ctx.lineTo(bl.x, bl.y);
  ctx.closePath();
  ctx.stroke();
  ctx.fillStyle = "#22c55e";
  [tl, tr, br, bl].forEach((p) => {
    ctx.beginPath();
    ctx.arc(p.x, p.y, 6, 0, Math.PI * 2);
    ctx.fill();
  });
}

// --- Captura + procesamiento de una página --------------------------------

const LADO_MAX_CAPTURA = 2000; // limita la resolución antes de procesar (cámaras de 12-48MP son innecesarias aquí)

function capturarPagina(overlay, estado, cerrar) {
  const video = document.getElementById("escaner-video");
  const corners = estado.ultimosCorners;
  detenerDeteccion(estado);

  const vw = video.videoWidth,
    vh = video.videoHeight;
  const escala = Math.min(1, LADO_MAX_CAPTURA / Math.max(vw, vh));
  const canvasCaptura = document.createElement("canvas");
  canvasCaptura.width = Math.round(vw * escala);
  canvasCaptura.height = Math.round(vh * escala);
  canvasCaptura.getContext("2d").drawImage(video, 0, 0, canvasCaptura.width, canvasCaptura.height);

  const cornersEscalados = corners ? corners.map((p) => ({ x: p.x * escala, y: p.y * escala })) : null;

  detenerCamara(estado); // se libera mientras se revisa esta página (se reabre al capturar la siguiente)
  mostrarAjusteBordes(overlay, estado, cerrar, canvasCaptura, cornersEscalados);
}

// --- Vista: ajustar bordes a mano (respaldo cuando la detección automática --
// --- no encontró el documento, o para corregirla) --------------------------
// Si la cámara sí detectó 4 esquinas, empiezan ahí; si no, se ofrece un
// recuadro con margen del 6% como punto de partida. Siempre se puede
// arrastrar — nunca depende de que la detección automática haya acertado.

function mostrarAjusteBordes(overlay, estado, cerrar, canvasCaptura, cornersIniciales) {
  const w = canvasCaptura.width,
    h = canvasCaptura.height;
  const margen = 0.06;
  const corners = cornersIniciales || [
    { x: w * margen, y: h * margen },
    { x: w * (1 - margen), y: h * margen },
    { x: w * (1 - margen), y: h * (1 - margen) },
    { x: w * margen, y: h * (1 - margen) },
  ];

  overlay.innerHTML = `
    <div class="escaner-ajuste">
      <div class="escaner-topbar">
        <button type="button" class="escaner-icono-btn" id="escaner-ajuste-repetir" aria-label="Repetir foto">✕</button>
        <span class="escaner-titulo-modulo">Ajustar bordes</span>
        <span style="width:38px"></span>
      </div>
      <p class="escaner-ajuste-ayuda">Arrastra las esquinas para que coincidan con el documento.</p>
      <div class="escaner-ajuste-lienzo-wrap" id="escaner-ajuste-wrap">
        <img src="${canvasCaptura.toDataURL("image/jpeg", 0.85)}" alt="" id="escaner-ajuste-imagen" />
        <svg class="escaner-ajuste-svg" id="escaner-ajuste-svg"></svg>
        ${[0, 1, 2, 3].map((i) => `<div class="escaner-ajuste-manija" data-manija="${i}"></div>`).join("")}
      </div>
      <div class="escaner-revision-acciones">
        <button type="button" class="boton secundario" id="escaner-ajuste-completo">Usar toda la imagen</button>
        <button type="button" class="boton" id="escaner-ajuste-listo">✓ Recortar</button>
      </div>
    </div>
  `;

  document.getElementById("escaner-ajuste-repetir").addEventListener("click", () => {
    iniciarVistaCamara(overlay, estado, cerrar);
  });
  document.getElementById("escaner-ajuste-completo").addEventListener("click", () => {
    mostrarRevisionPagina(overlay, estado, cerrar, canvasCaptura, null, "automatico");
  });
  document.getElementById("escaner-ajuste-listo").addEventListener("click", () => {
    mostrarRevisionPagina(overlay, estado, cerrar, canvasCaptura, corners, "automatico");
  });

  const imgEl = document.getElementById("escaner-ajuste-imagen");
  const svgEl = document.getElementById("escaner-ajuste-svg");
  const wrapEl = document.getElementById("escaner-ajuste-wrap");

  const redibujar = () => {
    const { escala, offX, offY, rect } = mapaContenido(imgEl, w, h);
    svgEl.setAttribute("width", String(rect.width));
    svgEl.setAttribute("height", String(rect.height));
    const puntos = corners.map((p) => `${p.x * escala + offX},${p.y * escala + offY}`).join(" ");
    svgEl.innerHTML = `<polygon points="${puntos}" fill="rgba(34,197,94,0.18)" stroke="#22c55e" stroke-width="2.5" />`;
    wrapEl.querySelectorAll(".escaner-ajuste-manija").forEach((manija) => {
      const p = corners[Number(manija.dataset.manija)];
      manija.style.left = `${p.x * escala + offX}px`;
      manija.style.top = `${p.y * escala + offY}px`;
    });
  };

  vincularArrastreManijas(wrapEl, imgEl, corners, w, h, redibujar);
  if (imgEl.complete) redibujar();
  else imgEl.addEventListener("load", redibujar);
  window.addEventListener("resize", redibujar);
}

// Mapea coordenadas reales de la imagen (canvasCaptura, w x h) al recuadro
// donde se muestra en pantalla con object-fit:contain (sin recorte, con
// barras si no coincide la proporción).
function mapaContenido(imgEl, w, h) {
  const rect = imgEl.getBoundingClientRect();
  const escala = Math.min(rect.width / w, rect.height / h);
  const offX = (rect.width - w * escala) / 2;
  const offY = (rect.height - h * escala) / 2;
  return { escala, offX, offY, rect };
}

function vincularArrastreManijas(wrapEl, imgEl, corners, w, h, redibujar) {
  wrapEl.querySelectorAll(".escaner-ajuste-manija").forEach((manija) => {
    const idx = Number(manija.dataset.manija);
    manija.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      manija.setPointerCapture(ev.pointerId);
      const mover = (ev2) => {
        const { escala, offX, offY, rect } = mapaContenido(imgEl, w, h);
        const x = Math.max(0, Math.min(w, (ev2.clientX - rect.left - offX) / escala));
        const y = Math.max(0, Math.min(h, (ev2.clientY - rect.top - offY) / escala));
        corners[idx] = { x, y };
        redibujar();
      };
      const soltar = () => {
        manija.removeEventListener("pointermove", mover);
        manija.removeEventListener("pointerup", soltar);
      };
      manija.addEventListener("pointermove", mover);
      manija.addEventListener("pointerup", soltar);
    });
  });
}

function distancia(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

// Recorta y endereza el documento a partir de las 4 esquinas detectadas.
// El llamador es responsable de liberar (.delete()) el Mat devuelto.
function aplicarPerspectiva(canvasOrigen, corners) {
  const src = cv.imread(canvasOrigen);
  try {
    const [tl, tr, br, bl] = corners;
    const anchoDestino = Math.round(Math.max(distancia(tl, tr), distancia(bl, br)));
    const altoDestino = Math.round(Math.max(distancia(tl, bl), distancia(tr, br)));
    if (anchoDestino < 10 || altoDestino < 10) return src.clone();

    const srcTri = cv.matFromArray(4, 1, cv.CV_32FC2, [tl.x, tl.y, tr.x, tr.y, br.x, br.y, bl.x, bl.y]);
    const dstTri = cv.matFromArray(4, 1, cv.CV_32FC2, [0, 0, anchoDestino, 0, anchoDestino, altoDestino, 0, altoDestino]);
    const M = cv.getPerspectiveTransform(srcTri, dstTri);
    const dst = new cv.Mat();
    cv.warpPerspective(src, dst, M, new cv.Size(anchoDestino, altoDestino));
    srcTri.delete();
    dstTri.delete();
    M.delete();
    return dst;
  } finally {
    src.delete();
  }
}

// Heurística simple para el modo "Automático": si el documento tiene poco
// color (formulario/texto impreso) se procesa como "documento" (gris +
// contraste); si tiene color relevante (fotos, sellos de color) se mejora
// el contraste conservando el color.
function decidirModoAutomatico(matRGBA) {
  const rgb = new cv.Mat();
  const hsv = new cv.Mat();
  const canales = new cv.MatVector();
  try {
    cv.cvtColor(matRGBA, rgb, cv.COLOR_RGBA2RGB);
    cv.cvtColor(rgb, hsv, cv.COLOR_RGB2HSV);
    cv.split(hsv, canales);
    const satMedia = cv.mean(canales.get(1))[0];
    return satMedia < 30 ? "documento" : "color";
  } finally {
    rgb.delete();
    hsv.delete();
    for (let i = 0; i < canales.size(); i++) canales.get(i).delete();
    canales.delete();
  }
}

// Mejora de contraste (CLAHE, sobre L de Lab) conservando el color original
// — para "Color" y para lo que decida "Automático" cuando hay color real.
function mejorarColorConservandoTono(matRGBA) {
  const rgb = new cv.Mat();
  const lab = new cv.Mat();
  const canales = new cv.MatVector();
  const combinados = new cv.MatVector();
  let lMejorado, labFinal;
  try {
    cv.cvtColor(matRGBA, rgb, cv.COLOR_RGBA2RGB);
    cv.cvtColor(rgb, lab, cv.COLOR_RGB2Lab);
    cv.split(lab, canales);
    const l = canales.get(0),
      a = canales.get(1),
      b = canales.get(2);
    lMejorado = new cv.Mat();
    const clahe = new cv.CLAHE(2.0, new cv.Size(8, 8));
    clahe.apply(l, lMejorado);
    clahe.delete();
    l.delete();
    combinados.push_back(lMejorado);
    combinados.push_back(a);
    combinados.push_back(b);
    labFinal = new cv.Mat();
    cv.merge(combinados, labFinal);
    a.delete();
    b.delete();
    const rgbFinal = new cv.Mat();
    cv.cvtColor(labFinal, rgbFinal, cv.COLOR_Lab2RGB);
    return rgbFinal;
  } finally {
    rgb.delete();
    lab.delete();
    canales.delete();
    combinados.delete();
    lMejorado?.delete();
    labFinal?.delete();
  }
}

// Escala de grises + CLAHE + nitidez suave — texto legible sin perder
// firmas/sellos débiles (a diferencia de una binarización agresiva).
function mejorarComoDocumento(matRGBA) {
  const gray = new cv.Mat();
  let clahe, mejorado, desenfocado;
  try {
    cv.cvtColor(matRGBA, gray, cv.COLOR_RGBA2GRAY);
    clahe = new cv.CLAHE(2.0, new cv.Size(8, 8));
    mejorado = new cv.Mat();
    clahe.apply(gray, mejorado);
    desenfocado = new cv.Mat();
    cv.GaussianBlur(mejorado, desenfocado, new cv.Size(0, 0), 3);
    const nitido = new cv.Mat();
    cv.addWeighted(mejorado, 1.5, desenfocado, -0.5, 0, nitido);
    return nitido;
  } finally {
    gray.delete();
    clahe?.delete();
    mejorado?.delete();
    desenfocado?.delete();
  }
}

// Blanco y negro tipo escáner — adaptiveThreshold (no un corte global fijo)
// para no borrar firmas/sellos claros en zonas con sombra o luz despareja.
function mejorarBlancoYNegro(matRGBA) {
  const gray = new cv.Mat();
  try {
    cv.cvtColor(matRGBA, gray, cv.COLOR_RGBA2GRAY);
    const bin = new cv.Mat();
    cv.adaptiveThreshold(gray, bin, 255, cv.ADAPTIVE_THRESH_GAUSSIAN_C, cv.THRESH_BINARY, 31, 12);
    return bin;
  } finally {
    gray.delete();
  }
}

// matEntrada: cv.Mat RGBA (perspectiva ya corregida, o el cuadro completo).
// El llamador debe liberar el resultado.
function aplicarMejora(matEntrada, modoSolicitado) {
  let modo = modoSolicitado;
  if (modo === "automatico") modo = decidirModoAutomatico(matEntrada);
  if (modo === "color") return mejorarColorConservandoTono(matEntrada);
  if (modo === "bn") return mejorarBlancoYNegro(matEntrada);
  return mejorarComoDocumento(matEntrada); // "documento" (y "automatico" cuando decide que hay poco color)
}

function procesarPagina(canvasCaptura, corners, modo) {
  let base = null,
    mejorado = null;
  try {
    base = corners ? aplicarPerspectiva(canvasCaptura, corners) : cv.imread(canvasCaptura);
    mejorado = aplicarMejora(base, modo);
    const canvasSalida = document.createElement("canvas");
    canvasSalida.width = mejorado.cols;
    canvasSalida.height = mejorado.rows;
    cv.imshow(canvasSalida, mejorado);
    return canvasSalida.toDataURL("image/jpeg", 0.85);
  } finally {
    base?.delete();
    mejorado?.delete();
  }
}

// --- Vista: revisión de una página (elegir modo, usar o descartar) --------

const MODOS_MEJORA = [
  { id: "automatico", label: "Automático" },
  { id: "color", label: "Color" },
  { id: "documento", label: "Documento" },
  { id: "bn", label: "Blanco y negro" },
];

function mostrarRevisionPagina(overlay, estado, cerrar, canvasCaptura, corners, modoInicial) {
  const dataUrl = procesarPagina(canvasCaptura, corners, modoInicial);
  estado.paginaEnRevision = { canvasCaptura, corners, modo: modoInicial, dataUrl };
  pintarRevisionPagina(overlay, estado, cerrar);
}

function pintarRevisionPagina(overlay, estado, cerrar) {
  const rev = estado.paginaEnRevision;
  overlay.innerHTML = `
    <div class="escaner-revision">
      <div class="escaner-topbar">
        <button type="button" class="escaner-icono-btn" id="escaner-descartar" aria-label="Descartar y repetir">✕</button>
        <span class="escaner-titulo-modulo">Revisar página</span>
        <span style="width:38px"></span>
      </div>
      <div class="escaner-revision-imagen-wrap">
        <img src="${rev.dataUrl}" alt="Página capturada" class="escaner-revision-imagen" />
      </div>
      <div class="escaner-modos">
        ${MODOS_MEJORA.map((m) => `<button type="button" class="escaner-modo-btn ${rev.modo === m.id ? "activo" : ""}" data-modo="${m.id}">${m.label}</button>`).join("")}
      </div>
      <div class="escaner-revision-acciones">
        <button type="button" class="boton secundario" id="escaner-repetir">↺ Repetir</button>
        <button type="button" class="boton" id="escaner-usar-pagina">✓ Usar esta página</button>
      </div>
    </div>
  `;

  document.getElementById("escaner-descartar").addEventListener("click", () => {
    estado.paginaEnRevision = null;
    iniciarVistaCamara(overlay, estado, cerrar);
  });
  document.getElementById("escaner-repetir").addEventListener("click", () => {
    estado.paginaEnRevision = null;
    iniciarVistaCamara(overlay, estado, cerrar);
  });

  document.querySelectorAll(".escaner-modo-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const modo = btn.dataset.modo;
      rev.modo = modo;
      rev.dataUrl = procesarPagina(rev.canvasCaptura, rev.corners, modo);
      pintarRevisionPagina(overlay, estado, cerrar);
    });
  });

  document.getElementById("escaner-usar-pagina").addEventListener("click", () => {
    estado.paginas.push({ dataUrl: rev.dataUrl });
    estado.paginaEnRevision = null;
    iniciarVistaCamara(overlay, estado, cerrar);
  });
}

// --- Vista: administrar páginas (agregar / eliminar / finalizar) --------

function mostrarPaginas(overlay, estado, cerrar) {
  overlay.innerHTML = `
    <div class="escaner-paginas">
      <div class="escaner-topbar">
        <button type="button" class="escaner-icono-btn" id="escaner-volver-camara" aria-label="Volver a la cámara">←</button>
        <span class="escaner-titulo-modulo">${estado.paginas.length} página(s)</span>
        <span style="width:38px"></span>
      </div>
      <div class="escaner-grid-paginas">
        ${estado.paginas
          .map(
            (p, i) => `
          <div class="escaner-miniatura-pagina">
            <img src="${p.dataUrl}" alt="Página ${i + 1}" />
            <span class="escaner-miniatura-numero">${i + 1}</span>
            <button type="button" class="escaner-miniatura-quitar" data-quitar-pagina="${i}" aria-label="Eliminar página ${i + 1}">✕</button>
          </div>`
          )
          .join("")}
        <button type="button" class="escaner-agregar-pagina" id="escaner-agregar-pagina">+ Agregar página</button>
      </div>
      <div class="escaner-revision-acciones">
        <button type="button" class="boton secundario" id="escaner-cancelar-todo">Cancelar</button>
        <button type="button" class="boton" id="escaner-finalizar" ${estado.paginas.length ? "" : "disabled"}>Finalizar y generar PDF</button>
      </div>
    </div>
  `;

  document.getElementById("escaner-volver-camara").addEventListener("click", () => iniciarVistaCamara(overlay, estado, cerrar));
  document.getElementById("escaner-agregar-pagina").addEventListener("click", () => iniciarVistaCamara(overlay, estado, cerrar));
  document.getElementById("escaner-cancelar-todo").addEventListener("click", () => {
    if (!confirm("¿Cancelar? Se perderán las páginas capturadas.")) return;
    cerrar();
  });
  document.querySelectorAll("[data-quitar-pagina]").forEach((btn) => {
    btn.addEventListener("click", () => {
      estado.paginas.splice(Number(btn.dataset.quitarPagina), 1);
      mostrarPaginas(overlay, estado, cerrar);
    });
  });
  document.getElementById("escaner-finalizar").addEventListener("click", () => finalizarYGuardar(overlay, estado, cerrar));
}

// --- Generación del PDF + subida ----------------------------------------

function cargarImagen(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("No se pudo leer una de las páginas"));
    img.src = src;
  });
}

async function generarPdf(paginas) {
  const { jsPDF } = window.jspdf;
  const ANCHO_MM = 210; // ancho tipo A4; cada página conserva su propia proporción
  let doc = null;
  for (let i = 0; i < paginas.length; i++) {
    const img = await cargarImagen(paginas[i].dataUrl);
    const altoMm = (img.height / img.width) * ANCHO_MM;
    const orientacion = altoMm >= ANCHO_MM ? "portrait" : "landscape";
    if (i === 0) {
      doc = new jsPDF({ unit: "mm", format: [ANCHO_MM, altoMm], orientation: orientacion });
    } else {
      doc.addPage([ANCHO_MM, altoMm], orientacion);
    }
    doc.addImage(paginas[i].dataUrl, "JPEG", 0, 0, ANCHO_MM, altoMm, undefined, "FAST");
  }
  return doc.output("blob");
}

async function finalizarYGuardar(overlay, estado, cerrar) {
  pintarCargando(overlay, "Generando PDF...");
  let blob;
  try {
    blob = await generarPdf(estado.paginas);
  } catch (err) {
    pintarError(overlay, "No se pudo generar el PDF: " + err.message, () => mostrarPaginas(overlay, estado, cerrar));
    return;
  }

  pintarCargando(overlay, "Guardando...");
  try {
    await estado.onGuardar(blob, "documento_escaneado.pdf");
    pintarExito(overlay, `Documento guardado (${estado.paginas.length} página(s))`);
    setTimeout(cerrar, 900);
  } catch (err) {
    pintarError(overlay, err.message || "No se pudo guardar el documento.", () => mostrarPaginas(overlay, estado, cerrar));
  }
}

// --- Estados auxiliares (cargando / error / fallback) -----------------

function pintarCargando(overlay, texto) {
  overlay.innerHTML = `<div class="escaner-centro"><div class="escaner-spinner"></div><p>${texto}</p></div>`;
}

function pintarExito(overlay, texto) {
  overlay.innerHTML = `<div class="escaner-centro"><div class="escaner-icono-exito">✓</div><p>${texto}</p></div>`;
}

function pintarError(overlay, texto, alReintentar) {
  overlay.innerHTML = `
    <div class="escaner-centro">
      <p class="escaner-texto-error">${texto}</p>
      <button type="button" class="boton" id="escaner-error-volver">Volver</button>
    </div>`;
  document.getElementById("escaner-error-volver").addEventListener("click", alReintentar);
}

// Cuando la cámara no está disponible (sin HTTPS, sin permiso, sin
// hardware, librería no cargó): nunca se bloquea — se ofrece el input de
// archivo tradicional, que ya sabe manejar imagen o PDF.
function pintarFallback(overlay, estado, cerrar, mensaje) {
  overlay.innerHTML = `
    <div class="escaner-centro">
      <p class="escaner-texto-error">No fue posible utilizar el escáner.</p>
      <p class="escaner-texto-fallback">${mensaje}</p>
      <label class="boton" style="cursor:pointer">
        Tomar/seleccionar una imagen
        <input type="file" id="escaner-fallback-input" accept="image/*,application/pdf" capture="environment" style="display:none" />
      </label>
      <button type="button" class="boton secundario" id="escaner-fallback-cerrar" style="margin-top:10px">Cancelar</button>
    </div>`;

  document.getElementById("escaner-fallback-cerrar").addEventListener("click", cerrar);
  document.getElementById("escaner-fallback-input").addEventListener("change", async (e) => {
    const archivo = e.target.files[0];
    if (!archivo) return;
    pintarCargando(overlay, "Guardando...");
    try {
      await estado.onGuardar(archivo, archivo.name);
      pintarExito(overlay, "Documento guardado");
      setTimeout(cerrar, 900);
    } catch (err) {
      pintarError(overlay, err.message || "No se pudo guardar el documento.", cerrar);
    }
  });
}
