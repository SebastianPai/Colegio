// Captura del "Boletín informativo" SIN automatizar el formulario: tú
// entras a SAPRED y navegas/generas el reporte exactamente como siempre lo
// haces a mano (sede, grado, curso, período, "Generar"), y este script se
// queda vigilando en segundo plano — en cuanto detecta que apareció un
// reporte de Boletín en pantalla (en una ventana emergente o en el mismo
// marco), lo lee y lo manda a la app automáticamente. No toca ningún
// <select> ni botón por ti.
//
// Por qué existe: la automatización que sí llena el formulario
// (generarYExtraerBoletin, en sapred_core.js) choca con un bug propio de la
// página de SAPRED (su función interna mostrar() revienta al cambiar de
// curso) y el reporte sale vacío. Haciendo la selección tú mismo se esquiva
// ese bug por completo — tu manera de entrar siempre ha funcionado.
//
// Uso: node capturar_boletin_manual.js
//   1. Inicia sesión en la ventana de Chrome (como siempre).
//   2. Entra a Reportes -> Boletín informativo, elige sede/grado/curso/
//      periodo y dale "Generar" — repite para todos los cursos que quieras
//      importar en esta sesión, uno tras otro.
//   3. Cada vez que se genere un reporte con contenido, este script lo
//      captura solo y lo importa a la app (verás un aviso en la consola).
//   4. Cuando termines, simplemente cierra la ventana de Chrome — el script
//      se cierra solo y muestra el resumen total.

const fs = require("fs");
const path = require("path");
const { abrirNavegadorSapred, esperarLogin, apiPostJSON } = require("./sapred_core.js");
const { extraerBloquesDeBoletinSapred } = require("./extraer_bloques_boletin.js");

const API_BASE = process.env.SAPRED_API_BASE || "http://127.0.0.1:8000";
let volcadoGuardado = false; // solo se guarda un volcado de diagnóstico por corrida

function tieneBoletin(texto) {
  return (texto || "").toUpperCase().includes("INFORME ESCOLAR DE VALORAC");
}

async function extraerDeDestino(destino) {
  try {
    const texto = await destino.evaluate(() => document.body && document.body.innerText).catch(() => "");
    if (!tieneBoletin(texto)) return null;
    const bloques = await destino.evaluate(extraerBloquesDeBoletinSapred);
    if ((!bloques || !bloques.length) && !volcadoGuardado) {
      volcadoGuardado = true;
      const destinoArchivo = path.join(__dirname, "diagnostico_boletin_html.txt");
      fs.writeFileSync(destinoArchivo, texto, "utf8");
      console.log(`\n[DIAGNÓSTICO] La página trae el boletín pero el lector no sacó ningún bloque.`);
      console.log(`  Se guardó el texto completo en: ${destinoArchivo}`);
      console.log(`  Pégamelo (o el contenido de ese archivo) para ajustar el lector.`);
    }
    return bloques;
  } catch (e) {
    return null;
  }
}

async function importarBloques(bloques, resumen) {
  if (!bloques || !bloques.length) return;
  let resultado;
  try {
    resultado = await apiPostJSON(API_BASE, "/api/boletines/importar-boletin-bloques", bloques);
  } catch (e) {
    console.log(`  ✗ Error enviando a la app: ${e.message}`);
    return;
  }
  for (const r of resultado.bloques || resultado) {
    resumen.bloquesVistos++;
    const etiqueta = `${r.sede_corta} — grado ${r.grado}, curso ${r.curso ?? "(único)"}, periodo ${r.periodo}`;
    if (!r.reconocido) {
      console.log(`  ⚠ NO reconocida: ${etiqueta} — ${r.motivo_no_reconocido || "sede no encontrada"}`);
      resumen.noReconocidos++;
      continue;
    }
    resumen.reconocidos++;
    const nuevosPend =
      (r.conceptos_pendientes_creados || 0) +
      (r.notas_pendientes_creados || 0) +
      (r.observaciones_pendientes_creadas || 0);
    console.log(`  ✓ ${etiqueta}: importado (${nuevosPend} pendiente(s) nuevo(s) creados)`);
    if (r.estudiantes_no_encontrados && r.estudiantes_no_encontrados.length) {
      console.log(`    Estudiantes no encontrados en la base: ${r.estudiantes_no_encontrados.join(", ")}`);
    }
  }
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

  console.log("Sesión iniciada.\n");
  console.log("Ahora entra tú mismo a Reportes -> Boletín informativo, elige sede,");
  console.log("grado, curso y período como siempre, y dale \"Generar\". Repite para");
  console.log("cada curso que quieras importar. Este script captura cada reporte solo,");
  console.log("apenas aparezca en pantalla — no hace falta avisarle nada.\n");
  console.log("Cuando termines, cierra la ventana de Chrome para ver el resumen.\n");

  const resumen = { bloquesVistos: 0, reconocidos: 0, noReconocidos: 0 };
  const yaCapturados = new Set(); // evita reprocesar el mismo marco dos veces
  const urlsVistas = new Set(); // solo para el registro/diagnóstico en consola

  const registrarDescargas = (ventana, etiqueta) => {
    ventana.on("download", (d) => {
      console.log(`\n[DESCARGA] ${etiqueta}: "${d.suggestedFilename()}" — url=${d.url()}`);
      console.log("  (si esto sale, SAPRED está entregando el boletín como archivo descargado,");
      console.log("   no como página — en ese caso hay que importar ese archivo a mano, ver abajo)");
    });
  };
  registrarDescargas(page, "ventana principal");

  // SAPRED anida casi todo en iframes — el reporte puede aparecer en el
  // documento raíz de una ventana nueva, o (más probable, igual que el resto
  // del sitio) adentro de un iframe metido en esa ventana, o directamente en
  // el mismo marco de la ventana principal. Por eso se revisan TODAS las
  // ventanas conocidas (principal + emergentes) y, dentro de cada una,
  // TODOS sus frames (page.frames() ya incluye los anidados), no solo el
  // documento raíz.
  const ventanas = [page];
  const context = page.context();
  context.on("page", (popup) => {
    console.log(`\n[Ventana nueva abierta] url inicial: ${popup.url() || "(en blanco todavía)"}`);
    registrarDescargas(popup, "ventana nueva");
    ventanas.push(popup);
    popup.on("close", () => {
      const i = ventanas.indexOf(popup);
      if (i !== -1) ventanas.splice(i, 1);
    });
  });

  let corriendo = true;
  browser.on("disconnected", () => {
    corriendo = false;
  });
  (async () => {
    while (corriendo) {
      await page.waitForTimeout(1500).catch(() => {});
      // Además del evento "disconnected" (que a veces no llega si Chrome se
      // cierra de una forma rara), se revisa directamente si el navegador
      // sigue conectado — así nunca se queda esperando para siempre.
      if (!browser.isConnected()) corriendo = false;
      if (!corriendo) break;
      for (const ventana of [...ventanas]) {
        let frames = [];
        try {
          frames = ventana.frames ? ventana.frames() : [ventana];
        } catch (e) {
          continue; // ventana cerrada justo ahora
        }
        for (const frame of frames) {
          let url;
          try {
            url = frame.url();
          } catch (e) {
            continue;
          }
          if (!urlsVistas.has(url) && url && url !== "about:blank") {
            urlsVistas.add(url);
            const muestra = await frame
              .evaluate(() => (document.body ? document.body.innerText.slice(0, 120).replace(/\s+/g, " ") : "(sin <body>)"))
              .catch((e) => `(no se pudo leer: ${e.message})`);
            console.log(`\n[frame nuevo] ${url}\n  primeros caracteres: "${muestra}"`);
          }
          if (yaCapturados.has(url)) continue;
          const bloques = await extraerDeDestino(frame);
          if (bloques && bloques.length) {
            yaCapturados.add(url);
            console.log(`\n[Detectado] Reporte de Boletín — ${bloques.length} bloque(s). Importando...`);
            await importarBloques(bloques, resumen);
          }
        }
      }
    }
  })();

  // Espera a que el navegador se cierre. No basta con el evento
  // "disconnected" solo (a veces no llega) — también se revisa "corriendo",
  // que el bucle de arriba ya pone en false apenas nota que el navegador
  // dejó de responder.
  await new Promise((resolve) => {
    if (!corriendo) return resolve();
    browser.on("disconnected", resolve);
    const chequeo = setInterval(() => {
      if (!corriendo) {
        clearInterval(chequeo);
        resolve();
      }
    }, 1000);
  });
  await browser.close().catch(() => {});

  console.log("\n=== Resumen de esta sesión ===");
  console.log(`Bloques vistos: ${resumen.bloquesVistos}`);
  console.log(`  Reconocidos e importados: ${resumen.reconocidos}`);
  console.log(`  No reconocidos (revisar sede): ${resumen.noReconocidos}`);
})();
