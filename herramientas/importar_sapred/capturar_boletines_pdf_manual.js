// CAPTURA MANUAL DEL BOLETÍN A PDF
// =================================
// Tú entras a SAPRED y generas cada boletín EXACTAMENTE como lo haces a mano
// (sede, grado, sección, período, Opciones de impresión -> Mostrar Sede /
// Incluir Puesto en Sí -> Guardar -> Generar). Este script solo vigila en
// segundo plano: en cuanto aparece un boletín en pantalla, lo lee y lo
// guarda como PDF (usando un Chrome headless para "imprimir a PDF"). NO toca
// ningún <select> ni botón.
//
// Uso:
//   node capturar_boletines_pdf_manual.js [carpeta-de-salida]
//
//   - Si no pasas carpeta, usa  ..\..\backend\boletines_sedes\manual\
//   - Cada boletín queda como  <lo que diga el encabezado>.pdf  (+ un .html
//     al lado, por si el PDF sale raro y hay que revisar qué se capturó).
//   - Repite "Generar" para cada grupo. Cierra Chrome al terminar para ver el
//     resumen.

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const { abrirNavegadorSapred, esperarLogin, apiPostJSON } = require("./sapred_core.js");

const API_BASE = process.env.SAPRED_API_BASE || "http://127.0.0.1:8000";
const carpetaSalida =
  process.argv[2] ||
  path.join(__dirname, "..", "..", "backend", "boletines_sedes", "manual");
fs.mkdirSync(carpetaSalida, { recursive: true });

const NOMBRES_GRADO = {
  0: "0 Transicion", 1: "1 Primero", 2: "2 Segundo", 3: "3 Tercero", 4: "4 Cuarto",
  5: "5 Quinto", 6: "6 Sexto", 7: "7 Septimo", 8: "8 Octavo", 9: "9 Noveno",
  10: "10 Decimo", 11: "11 Once",
};

function slug(s) {
  return (s || "")
    .normalize("NFKC")
    .replace(/[<>:"/\\|?*\x00-\x1f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 90);
}

// Saca sede / grado / sección / período del propio boletín (está todo en la
// celda "CURSO" = "5-1 ..." y en el encabezado "SEDE EDUCATIVA ...").
function datosDelBoletin(html, texto) {
  const t = (texto || "").replace(/\s+/g, " ");
  let sede = (html.match(/SEDE\s+EDUCATIVA\s+([^<\n]+?)\s*<br/i) || [])[1] || "";
  if (!sede) sede = (t.match(/SEDE\s+EDUCATIVA\s+([A-ZÁÉÍÓÚÑ0-9 .]+?)\s+(?:A[ñn]o|SEDE|PRIMER|SEGUNDO|TERCER|CUARTO)/i) || [])[1] || "";
  sede = slug(sede.replace(/\s+/g, " ").trim()) || "SEDE";

  const curso = t.match(/\b(\d{1,2})-(\d{1,2})\b/);
  const grado = curso ? Number(curso[1]) : null;
  const seccion = curso ? curso[2] : null;

  const per = (t.match(/\b(PRIMER|SEGUNDO|TERCER|CUARTO)\s+PERIODO\b/i) || [])[1] || "";
  const periodo = { PRIMER: 1, SEGUNDO: 2, TERCER: 3, CUARTO: 4 }[per.toUpperCase()] || null;

  return { sede, grado, seccion, periodo };
}

// El reporte del boletín es la página `reportes/boletin/html_ccp.php` (o
// imp_/pdf_/rep_ccp). SOLO eso — NO el menú, ni el sel.php del formulario,
// ni el modal config/index.php.
function pareceBoletin(texto, url) {
  return /reportes\/boletin\/(html|imp|pdf|rep)_ccp\.php/i.test(url || "");
}

function esErrorSapred(texto) {
  return /error al ejecutar la consulta|syntax to use near|MySQLConex|No es un resultado/i.test(
    texto || ""
  );
}

(async () => {
  console.log("Abriendo SAPRED. Inicia sesión en la ventana de Chrome (hasta 15 min)...\n");
  const { browser, page } = await abrirNavegadorSapred();

  const ok = await esperarLogin(page, 15 * 60 * 1000);
  if (!ok) {
    console.log("No se detectó el inicio de sesión a tiempo.");
    await browser.close();
    process.exit(1);
  }

  // Chrome headless aparte, solo para "imprimir a PDF".
  const pdfBrowser = await chromium.launch({ headless: true });
  const pdfContext = await pdfBrowser.newContext();

  console.log("Sesión iniciada.\n");
  console.log("Ahora, en la ventana de Chrome, entra a Reportes -> Boletín, elige");
  console.log("sede / grado / sección / período, abre 'Opciones de impresión' y deja");
  console.log("Mostrar Sede e Incluir Puesto en Sí (Guardar), y dale 'Generar'.");
  console.log("Repite para cada grupo. Este script guarda cada boletín solo.\n");
  console.log(`Los PDF quedan en:\n  ${carpetaSalida}\n`);
  console.log("Cuando termines, CIERRA la ventana de Chrome para ver el resumen.\n");

  const ventanas = [page];
  const context = page.context();
  context.on("page", (p) => {
    ventanas.push(p);
    p.on("close", () => {
      const i = ventanas.indexOf(p);
      if (i !== -1) ventanas.splice(i, 1);
    });
  });

  const capturadas = new Set(); // firmas ya guardadas (evita duplicar)
  let n = 0;
  let guardados = 0;
  let errores = 0;
  const porSede = new Map(); // sede -> [{grado, seccion, ruta}]

  async function convertirYGuardar(htmlReporte, urlReporte, textoPlano) {
    n++;
    const d = datosDelBoletin(htmlReporte, textoPlano);
    const dirSede = path.join(carpetaSalida, d.sede);
    fs.mkdirSync(dirSede, { recursive: true });
    const stem =
      d.grado != null
        ? `${NOMBRES_GRADO[d.grado] || d.grado}${d.seccion ? "-" + d.seccion : ""}${d.periodo ? " P" + d.periodo : ""}`
        : `boletin-${String(n).padStart(3, "0")}`;
    const destinoPdf = path.join(dirSede, stem + ".pdf");
    const destinoHtml = path.join(dirSede, stem + ".html");
    const nombre = path.join(d.sede, stem);
    try {
      fs.writeFileSync(destinoHtml, htmlReporte, "utf8");
    } catch (e) {
      /* no es grave */
    }

    const conv = await pdfContext.newPage();
    try {
      try {
        await pdfContext.addCookies(await context.cookies());
      } catch (e) {}

      // html_ccp.php recibe sus datos por POST: si se recarga la URL "pelada"
      // sale vacía. Por eso se usa SIEMPRE el HTML tal cual se capturó
      // (con <base> para que los logos/CSS relativos carguen).
      const tieneParams = /\?[^#]/.test(urlReporte || "");
      const puedeRecargar = tieneParams && !/html_ccp\.php/i.test(urlReporte || "");
      let cargo = false;
      if (puedeRecargar) {
        const resp = await conv
          .goto(urlReporte, { waitUntil: "networkidle", timeout: 30000 })
          .catch(() => null);
        if (resp) {
          const t = await conv.evaluate(() => document.body && document.body.innerText).catch(() => "");
          if (t && t.length > 200 && !/iniciar sesi|usuario y contrase/i.test(t)) cargo = true;
        }
      }
      if (!cargo) {
        const base = urlReporte ? `<base href="${urlReporte}">` : "";
        const doc = /<head[^>]*>/i.test(htmlReporte)
          ? htmlReporte.replace(/<head[^>]*>/i, (m) => m + base)
          : `<!doctype html><html><head><meta charset="utf-8">${base}</head><body>${htmlReporte}</body></html>`;
        await conv.setContent(doc, { waitUntil: "networkidle", timeout: 30000 }).catch(() => {});
        await conv.waitForTimeout(2500);
      }
      await conv.emulateMedia({ media: "print" }).catch(() => {});
      await conv.pdf({
        path: destinoPdf,
        format: "Letter",
        printBackground: true,
        margin: { top: "10mm", bottom: "12mm", left: "8mm", right: "8mm" },
      });
    } finally {
      await conv.close().catch(() => {});
    }

    const buf = fs.readFileSync(destinoPdf);
    if (buf.slice(0, 5).toString("latin1") !== "%PDF-" || buf.length < 1500) {
      errores++;
      console.log(`  ✗ "${nombre}": el PDF salió vacío/corrupto. Revisa el .html guardado al lado.`);
      return;
    }
    guardados++;
    if (!porSede.has(d.sede)) porSede.set(d.sede, []);
    porSede.get(d.sede).push({ grado: d.grado ?? 99, seccion: Number(d.seccion) || 0, ruta: destinoPdf });
    console.log(`  ✓ ${nombre}.pdf  (${Math.round(buf.length / 1024)} KB)`);
  }

  // Al terminar: por cada sede, une sus PDF (orden grado, sección) en
  // <carpeta>/<sede>.pdf  — usa el backend de la app (tiene que estar prendido).
  async function unirPorSede() {
    for (const [sede, items] of porSede) {
      if (items.length < 1) continue;
      items.sort((a, b) => a.grado - b.grado || a.seccion - b.seccion);
      const salida = path.join(carpetaSalida, sede + ".pdf");
      try {
        const r = await apiPostJSON(API_BASE, "/api/boletines/unir-pdfs", {
          archivos: items.map((i) => i.ruta),
          salida,
        });
        console.log(`  📎 ${sede}.pdf  (${items.length} grupo(s), ${r.n_paginas} pág.)`);
      } catch (e) {
        console.log(`  ⚠ no pude unir "${sede}" (¿el servidor de la app está prendido?): ${e.message}`);
        console.log(`     Los PDF sueltos quedaron en:  ${path.join(carpetaSalida, sede)}`);
      }
    }
  }

  let corriendo = true;
  browser.on("disconnected", () => (corriendo = false));

  (async () => {
    while (corriendo) {
      await page.waitForTimeout(1500).catch(() => {});
      if (!browser.isConnected()) corriendo = false;
      if (!corriendo) break;

      for (const v of [...ventanas]) {
        let frames = [];
        try {
          frames = v.frames ? v.frames() : [v];
        } catch (e) {
          continue;
        }
        for (const fr of frames) {
          let url = "";
          try {
            url = fr.url();
          } catch (e) {
            continue;
          }
          if (!url || url === "about:blank") continue;

          if (!pareceBoletin("", url)) continue;

          // Esperar a que termine de armarse la tabla del boletín (puede
          // construirse con JS después del load).
          await fr.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
          await page.waitForTimeout(2500);

          let texto = "";
          try {
            texto = await fr.evaluate(() => (document.body ? document.body.innerText : "")).catch(() => "");
          } catch (e) {
            continue;
          }
          const filas = await fr.evaluate(() => document.querySelectorAll("table tr").length).catch(() => 0);
          if (!texto || (texto.length < 400 && filas < 3)) continue; // aún no está listo

          // firma = hash del texto completo (distingue cada grupo aunque el
          // encabezado sea igual).
          let h = 0;
          for (let k = 0; k < texto.length; k++) h = (h * 31 + texto.charCodeAt(k)) | 0;
          const firma = url + "#" + h + "#" + texto.length;
          if (capturadas.has(firma)) continue;
          capturadas.add(firma);

          if (esErrorSapred(texto)) {
            errores++;
            console.log(`  ⚠ SAPRED devolvió un error de consulta — revisa sección/período/modo estudiante`);
            continue;
          }

          let html = "";
          try {
            html = await fr.content();
          } catch (e) {
            continue;
          }
          if (!html || html.length < 400) continue;

          console.log(`\n[Detectado boletín] ${url}`);
          try {
            await convertirYGuardar(html, url, texto);
          } catch (e) {
            errores++;
            console.log(`  ✗ error al convertir: ${e.message}`);
          }
        }
      }
    }
  })();

  await new Promise((resolve) => {
    if (!corriendo) return resolve();
    browser.on("disconnected", resolve);
    const iv = setInterval(() => {
      if (!corriendo) {
        clearInterval(iv);
        resolve();
      }
    }, 1000);
  });
  await pdfBrowser.close().catch(() => {});

  if (porSede.size) {
    console.log("\nUniendo los PDF de cada sede...");
    await unirPorSede();
  }

  console.log("\n=== Resumen ===");
  console.log(`Boletines (grupos) guardados: ${guardados}`);
  console.log(`Sedes con PDF unido:          ${porSede.size}`);
  console.log(`Con problema:                 ${errores}`);
  console.log(`Carpeta:                      ${carpetaSalida}`);
})();
