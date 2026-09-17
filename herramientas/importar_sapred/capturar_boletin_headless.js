// Versión sin preguntas de la captura MANUAL del "Boletín informativo": la
// lanza el backend de la app (ver app/sapred_auditoria.py, cuando la
// auditoría es de tipo "boletin") como subproceso, igual que
// importar_sapred_headless.js e importar_boletin_headless.js.
//
// A diferencia de esos dos, este NO llena el formulario de SAPRED por
// código: abre el navegador, espera a que la persona inicie sesión y desde
// ahí navegue y genere el boletín ELLA MISMA (sede, grado, curso, período,
// "Generar" — como siempre lo ha hecho), y se queda vigilando en segundo
// plano para capturar e importar cada reporte apenas aparece en pantalla.
//
// Por qué: la automatización que sí llenaba el formulario
// (generarYExtraerBoletin, en sapred_core.js) choca con un bug propio de
// SAPRED (su función interna mostrar() revienta al cambiar de curso) y el
// reporte siempre salía vacío. Dejando que la persona haga la selección se
// esquiva ese bug por completo.
//
// Reporta progreso llamando de vuelta a la propia API de la app, igual que
// los otros dos scripts headless — así la pantalla de "Auditoría SAPRED"
// de la app funciona igual para los tres tipos.
//
// Argumentos: --audit-id=N [--api-base=http://127.0.0.1:8000]
// (--periodo/--grado/--sedes se aceptan por compatibilidad con la forma en
// que se lanza, pero no se usan: en este modo la persona elige todo eso a
// mano dentro de SAPRED, reporte por reporte.)

const { abrirNavegadorSapred, esperarLogin, apiPostJSON } = require("./sapred_core.js");
const { extraerBloquesDeBoletinSapred } = require("./extraer_bloques_boletin.js");

function leerArgs() {
  const args = {};
  for (const a of process.argv.slice(2)) {
    const m = a.match(/^--([^=]+)=(.*)$/);
    if (m) args[m[1]] = m[2];
  }
  return args;
}

function tieneBoletin(texto) {
  return (texto || "").toUpperCase().includes("INFORME ESCOLAR DE VALORAC");
}

async function extraerDeDestino(destino) {
  try {
    const texto = await destino.evaluate(() => document.body && document.body.innerText).catch(() => "");
    if (!tieneBoletin(texto)) return null;
    return await destino.evaluate(extraerBloquesDeBoletinSapred);
  } catch (e) {
    return null;
  }
}

(async () => {
  const args = leerArgs();
  const auditId = args["audit-id"];
  const apiBase = args["api-base"] || "http://127.0.0.1:8000";

  if (!auditId) {
    console.error("Falta --audit-id");
    process.exit(1);
  }

  const reportarProgreso = async (datos) => {
    try {
      await apiPostJSON(apiBase, `/api/boletines/auditoria-sapred/${auditId}/progreso`, datos);
    } catch (e) {
      console.error("No se pudo reportar progreso:", e.message);
    }
  };

  let browser = null;
  try {
    await reportarProgreso({ estado: "esperando_login" });

    const { browser: b, page } = await abrirNavegadorSapred();
    browser = b;

    const logueado = await esperarLogin(page, 15 * 60 * 1000);
    if (!logueado) {
      await reportarProgreso({ estado: "error", error: "No se detectó el login a tiempo (15 min)." });
      await browser.close();
      process.exit(1);
    }
    await reportarProgreso({
      estado: "en_proceso",
      sede_actual: "Entra a Boletín informativo en SAPRED y genera cada reporte normalmente",
      grado_actual: "se captura solo, apenas aparece en pantalla",
    });

    const yaCapturados = new Set();
    const ventanas = [page];
    const context = page.context();
    context.on("page", (popup) => {
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

    while (corriendo) {
      await page.waitForTimeout(1500).catch(() => {});
      // Además del evento "disconnected" (que a veces no llega si Chrome se
      // cierra de una forma rara), se revisa directamente si el navegador
      // sigue conectado — así la auditoría nunca se queda "en proceso"
      // para siempre en la app.
      if (!browser.isConnected()) corriendo = false;
      if (!corriendo) break;
      for (const ventana of [...ventanas]) {
        let frames = [];
        try {
          frames = ventana.frames ? ventana.frames() : [ventana];
        } catch (e) {
          continue;
        }
        for (const frame of frames) {
          let url;
          try {
            url = frame.url();
          } catch (e) {
            continue;
          }
          if (yaCapturados.has(url)) continue;
          const bloques = await extraerDeDestino(frame);
          if (!bloques || !bloques.length) continue;
          yaCapturados.add(url);

          let resultado;
          try {
            resultado = await apiPostJSON(apiBase, "/api/boletines/importar-boletin-bloques", bloques);
          } catch (e) {
            await reportarProgreso({
              detalle_sede: { sede: "Boletín capturado", estado: "error", detalle: `No se pudo importar: ${e.message}` },
            });
            continue;
          }
          const resultadosBloques = resultado.bloques || resultado;
          for (let i = 0; i < resultadosBloques.length; i++) {
            const r = resultadosBloques[i];
            const etiqueta = `${r.sede_corta} — grado ${r.grado}, curso ${r.curso ?? "(único)"}, periodo ${r.periodo}`;
            if (!r.reconocido) {
              await reportarProgreso({
                sedes_completadas: 1,
                detalle_sede: { sede: etiqueta, estado: "advertencia", detalle: r.motivo_no_reconocido || "sede no encontrada" },
              });
              continue;
            }
            const nuevosPend =
              (r.conceptos_pendientes_creados || 0) +
              (r.notas_pendientes_creados || 0) +
              (r.observaciones_pendientes_creadas || 0);
            const noEncontrados = (r.estudiantes_no_encontrados || []).length;
            const totalEst = (bloques[i] && bloques[i].estudiantes && bloques[i].estudiantes.length) || 0;
            await reportarProgreso({
              sedes_completadas: 1,
              estudiantes_revisados_delta: totalEst,
              pendientes_encontrados_delta: nuevosPend,
              detalle_sede: {
                sede: etiqueta,
                estado: "completada",
                detalle:
                  `${nuevosPend} pendiente(s) nuevo(s)` +
                  (noEncontrados ? ` — ${noEncontrados} estudiante(s) no encontrado(s) en la base` : ""),
              },
            });
          }
        }
      }
    }

    await reportarProgreso({ estado: "completada" });
    process.exit(0);
  } catch (err) {
    console.error(err);
    try {
      await reportarProgreso({ estado: "error", error: String(err.message || err) });
    } catch (e) {
      /* ya se perdió la conexión */
    }
    if (browser) await browser.close().catch(() => {});
    process.exit(1);
  }
})();
