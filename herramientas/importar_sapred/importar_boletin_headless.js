// Versión sin preguntas de la importación del "Boletín informativo" de
// SAPRED: la lanza el backend de la app (ver app/sapred_auditoria.py, cuando
// la auditoría es de tipo "boletin") como subproceso. Reporta el progreso
// llamando de vuelta a la propia API de la app.
//
// Es el gemelo de importar_sapred_headless.js (que importa el Consolidado de
// notas). La diferencia es el reporte que abre en SAPRED y el endpoint al
// que envía los bloques.
//
// La única parte manual sigue siendo escribir usuario/contraseña en la
// ventana de Chrome que se abre.
//
// Argumentos: --audit-id=N --periodo=1|2 [--grado=N] [--sedes=id1,id2,...] [--api-base=http://127.0.0.1:8000]

const {
  GRADOS,
  apiGet,
  apiPostJSON,
  estaLogueado,
  esperarLogin,
  abrirNavegadorSapred,
  abrirPestanaReporteBoletin,
  generarYExtraerBoletinTodasJornadas,
} = require("./sapred_core.js");
const SEDES_SAPRED = require("./config_sedes.json");

function leerArgs() {
  const args = {};
  for (const a of process.argv.slice(2)) {
    const m = a.match(/^--([^=]+)=(.*)$/);
    if (m) args[m[1]] = m[2];
  }
  return args;
}

async function reportarProgreso(apiBase, auditId, datos) {
  try {
    await apiPostJSON(apiBase, `/api/boletines/auditoria-sapred/${auditId}/progreso`, datos);
  } catch (e) {
    console.error("No se pudo reportar progreso:", e.message);
  }
}

(async () => {
  const args = leerArgs();
  const auditId = args["audit-id"];
  const apiBase = args["api-base"] || "http://127.0.0.1:8000";
  const periodoNum = args.periodo === "1" ? "1" : "2";
  const periodoTexto = periodoNum === "1" ? "PRIMER PERIODO" : "SEGUNDO PERIODO";
  const gradoFiltro = args.grado ? Number(args.grado) : null;
  const sedeIdsFiltro = args.sedes ? args.sedes.split(",").map(Number) : null;

  if (!auditId) {
    console.error("Falta --audit-id");
    process.exit(1);
  }

  let browser = null;
  try {
    const todasLasSedesDB = await apiGet(apiBase, "/api/sedes");
    const sedeIdPorNombre = {};
    todasLasSedesDB.forEach((s) => {
      sedeIdPorNombre[s.nombre] = s.id;
    });

    const gradosAProcesar = gradoFiltro !== null ? GRADOS.filter((g) => g.numero === gradoFiltro) : GRADOS;

    const plan = [];
    for (const grado of gradosAProcesar) {
      // Fase 4.1: ruta reducida (solo sede_id + cantidad, sin datos
      // personales) — es endpoint interno, exige identidad de servicio.
      const conteo = await apiGet(apiBase, `/api/estudiantes/conteo-por-sede?grado=${grado.numero}&estado=ACTIVO`);
      const conteoPorSede = {};
      conteo.forEach((c) => {
        conteoPorSede[c.sede_id] = c.cantidad;
      });
      for (const [nombreDB, sedeSapred] of Object.entries(SEDES_SAPRED)) {
        const sedeId = sedeIdPorNombre[nombreDB];
        if (!conteoPorSede[sedeId]) continue;
        if (sedeIdsFiltro && !sedeIdsFiltro.includes(sedeId)) continue;
        plan.push({ grado, sedeSapred, sedeId, sedeNombreDB: nombreDB, estudiantesEsperados: conteoPorSede[sedeId] });
      }
    }

    await reportarProgreso(apiBase, auditId, { estado: "esperando_login", sedes_totales: plan.length });

    if (!plan.length) {
      await reportarProgreso(apiBase, auditId, { estado: "completada" });
      process.exit(0);
    }

    const { browser: b, page } = await abrirNavegadorSapred();
    browser = b;

    const logueado = await esperarLogin(page, 15 * 60 * 1000);
    if (!logueado) {
      await reportarProgreso(apiBase, auditId, { estado: "error", error: "No se detectó el login a tiempo (15 min)." });
      await browser.close();
      process.exit(1);
    }
    await reportarProgreso(apiBase, auditId, { estado: "en_proceso" });

    const context = browser.contexts()[0];
    let frame = await abrirPestanaReporteBoletin(page);

    const bloquesPorGrado = new Map();

    for (const item of plan) {
      await reportarProgreso(apiBase, auditId, {
        sede_actual: item.sedeNombreDB,
        grado_actual: item.grado.sapred,
      });

      let intentos = 0;
      let ok = false;
      let ultimoError = null;
      while (intentos < 2 && !ok) {
        intentos++;
        try {
          if (!(await estaLogueado(page))) throw new Error("la sesión se cerró");
          const bloques = await generarYExtraerBoletinTodasJornadas(
            page, frame, context, item.sedeSapred, item.grado.sapred, periodoTexto
          );
          bloques.forEach((bl) => {
            bl.sede_id = item.sedeId;
          });
          const totalEst = bloques.reduce((a, bl) => a + bl.estudiantes.length, 0);

          if (totalEst === 0 && item.estudiantesEsperados > 0) {
            await reportarProgreso(apiBase, auditId, {
              sedes_completadas: 1,
              detalle_sede: {
                sede: `${item.sedeNombreDB} (${item.grado.sapred})`,
                estado: "advertencia",
                detalle: `El boletín no devolvió estudiantes. La base local registra ${item.estudiantesEsperados} en este grado.`,
              },
            });
          } else {
            if (!bloquesPorGrado.has(item.grado.numero)) bloquesPorGrado.set(item.grado.numero, []);
            bloquesPorGrado.get(item.grado.numero).push(...bloques);
            await reportarProgreso(apiBase, auditId, {
              sedes_completadas: 1,
              estudiantes_revisados_delta: totalEst,
              detalle_sede: { sede: `${item.sedeNombreDB} (${item.grado.sapred})`, estado: "completada" },
            });
          }
          ok = true;
        } catch (err) {
          ultimoError = err;
          if (intentos < 2) frame = (await abrirPestanaReporteBoletin(page)) || frame;
        }
      }
      if (!ok) {
        await reportarProgreso(apiBase, auditId, {
          sedes_completadas: 1,
          detalle_sede: {
            sede: `${item.sedeNombreDB} (${item.grado.sapred})`,
            estado: "error",
            detalle: ultimoError ? ultimoError.message : "error desconocido",
          },
        });
      }
    }

    let totalPendientes = 0;
    for (const [, bloques] of bloquesPorGrado) {
      if (!bloques.length) continue;
      try {
        const resultado = await apiPostJSON(apiBase, "/api/boletines/importar-boletin-bloques", bloques);
        totalPendientes += (resultado.total_conceptos_pendientes || 0) + (resultado.total_observaciones_pendientes || 0);
      } catch (e) {
        console.error("Error enviando bloques:", e.message);
      }
    }

    await browser.close();
    await reportarProgreso(apiBase, auditId, { estado: "completada", pendientes_encontrados_delta: totalPendientes });
    process.exit(0);
  } catch (err) {
    console.error(err);
    try {
      await reportarProgreso(apiBase, auditId, { estado: "error", error: String(err.message || err) });
    } catch (e) {
      /* ya se perdió la conexión */
    }
    if (browser) await browser.close().catch(() => {});
    process.exit(1);
  }
})();
