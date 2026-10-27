// Genera el BOLETÍN GENERAL (PDF de calificaciones) de cada sede y lo deja en
// disco, un archivo por sede ordenado por grado, listo para entregar al
// docente. Lo lanza el backend (app/sapred_auditoria.py, tipo 'boletin_pdf')
// como subproceso; reporta progreso llamando de vuelta a la API de la app.
//
// A diferencia de importar_boletin_headless.js, esto NO importa nada: solo
// produce archivos. Por cada sede:
//   1. genera en SAPRED el boletín de cada grado (todas las secciones), en PDF
//   2. guarda cada PDF de grado en <carpeta>/_partes/<sede_id>/<grado>.pdf
//   3. pide al backend que los una en 'SEDE ## NOMBRE.pdf' (orden de grado)
//
// "Opciones de impresión" (Mostrar Sede = Sí, Incluir Puesto = Sí) se fija
// UNA vez al principio — es configuración global del reporte en SAPRED.
//
// La única parte manual sigue siendo escribir usuario/contraseña en la
// ventana de Chrome (o pasarlas por SAPRED_USUARIO / SAPRED_CLAVE).
//
// Argumentos: --audit-id=N --periodo=1..4 --carpeta=<dir absoluto>
//             [--grado=N] [--sedes=id1,id2,...] [--api-base=http://127.0.0.1:8000]

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const {
  GRADOS,
  BOLETIN_GEN_MATCH,
  apiGet,
  apiPostJSON,
  estaLogueado,
  esperarLogin,
  abrirNavegadorSapred,
  abrirPestanaBoletinGeneral,
  configurarOpcionesImpresionBoletin,
  generarBoletinPdfSede,
  leerPeriodosYGrados,
} = require("./sapred_core.js");
const SEDES_SAPRED = require("./config_sedes.json");

// Nombre de archivo/carpeta seguro (Windows) a partir del nombre de la sede.
function slugSede(nombre) {
  return (nombre || "sede")
    .normalize("NFKC")
    .replace(/[<>:"/\\|?*\x00-\x1f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 120) || "sede";
}

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
  // Un solo periodo (los PDF van a una carpeta por periodo) y uno, varios o
  // todos los grados.
  let periodoTexto, gradosAProcesar;
  try {
    const leido = leerPeriodosYGrados(args);
    if (leido.periodos.length !== 1) throw new Error("Los boletines en PDF se generan de a un periodo.");
    periodoTexto = leido.periodos[0].texto;
    gradosAProcesar = leido.grados;
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
  const sedeIdsFiltro = args.sedes ? args.sedes.split(",").map(Number) : null;
  const carpeta = args.carpeta;

  if (!auditId || !carpeta) {
    console.error("Falta --audit-id o --carpeta");
    process.exit(1);
  }
  fs.mkdirSync(carpeta, { recursive: true });

  let browser = null;
  let pdfBrowser = null;
  try {
    const sedesDB = await apiGet(apiBase, "/api/sedes");
    const sedeIdPorNombre = {};
    sedesDB.forEach((s) => {
      sedeIdPorNombre[s.nombre] = s.id;
    });


    // Plan agrupado POR SEDE: { sedeId, sedeNombreDB, sedeSapred, grados: [{grado, n}] }
    const porSede = new Map();
    for (const grado of gradosAProcesar) {
      // Fase 4.1: ruta reducida (solo sede_id + cantidad, sin datos
      // personales) — es endpoint interno, exige identidad de servicio.
      const conteo = await apiGet(
        apiBase,
        `/api/estudiantes/conteo-por-sede?grado=${grado.numero}&estado=ACTIVO`
      );
      const conteoPorSede = {};
      conteo.forEach((c) => {
        conteoPorSede[c.sede_id] = c.cantidad;
      });
      for (const [nombreDB, sedeSapred] of Object.entries(SEDES_SAPRED)) {
        const sedeId = sedeIdPorNombre[nombreDB];
        if (!conteoPorSede[sedeId]) continue;
        if (sedeIdsFiltro && !sedeIdsFiltro.includes(sedeId)) continue;
        if (!porSede.has(sedeId)) {
          porSede.set(sedeId, { sedeId, sedeNombreDB: nombreDB, sedeSapred, grados: [] });
        }
        porSede.get(sedeId).grados.push({ grado, n: conteoPorSede[sedeId] });
      }
    }
    const plan = [...porSede.values()];
    plan.forEach((s) => s.grados.sort((a, b) => a.grado.numero - b.grado.numero));

    await reportarProgreso(apiBase, auditId, {
      estado: "esperando_login",
      sedes_totales: plan.length,
    });

    if (!plan.length) {
      await reportarProgreso(apiBase, auditId, { estado: "completada" });
      process.exit(0);
    }

    const { browser: b, page } = await abrirNavegadorSapred();
    browser = b;

    const logueado = await esperarLogin(page, 15 * 60 * 1000);
    if (!logueado) {
      await reportarProgreso(apiBase, auditId, {
        estado: "error",
        error: "No se detectó el login a tiempo (15 min).",
      });
      await browser.close();
      process.exit(1);
    }
    await reportarProgreso(apiBase, auditId, { estado: "en_proceso" });

    // Chromium headless aparte: SAPRED entrega el boletín como HTML y
    // page.pdf() solo funciona headless (el navegador de SAPRED es headful).
    pdfBrowser = await chromium.launch({ headless: true });
    const pdfContext = await pdfBrowser.newContext();

    const context = browser.contexts()[0];
    let frame = await abrirPestanaBoletinGeneral(page);
    if (!frame) {
      await reportarProgreso(apiBase, auditId, {
        estado: "error",
        error:
          "No se pudo abrir el reporte 'Boletín' en SAPRED. Confirma la ruta/id del menú con " +
          "`node descubrir_boletin_general.js` y ponla en sapred_core.js (BOLETIN_GEN_RUTA/ID).",
      });
      await browser.close();
      await pdfBrowser.close().catch(() => {});
      process.exit(1);
    }

    // "Opciones de impresión" (Mostrar Sede / Incluir Puesto = Sí): UNA vez.
    await configurarOpcionesImpresionBoletin(page, frame);
    frame = (await abrirPestanaBoletinGeneral(page)) || frame;

    for (const sede of plan) {
      await reportarProgreso(apiBase, auditId, { sede_actual: sede.sedeNombreDB, grado_actual: null });

      // Los PDF por grado quedan en una subcarpeta CON NOMBRE (no se borran):
      //   <carpeta>/SEDE ## NOMBRE/1 Primero.pdf , 2 Segundo.pdf , ...
      // y el consolidado en <carpeta>/SEDE ## NOMBRE.pdf
      const dirSede = path.join(carpeta, slugSede(sede.sedeNombreDB));
      fs.mkdirSync(dirSede, { recursive: true });

      const partes = [];
      const fallos = [];
      for (const { grado, n } of sede.grados) {
        await reportarProgreso(apiBase, auditId, {
          sede_actual: sede.sedeNombreDB,
          grado_actual: grado.sapred,
        });
        const nombreGrado = `${grado.numero} ${grado.sapred.charAt(0)}${grado.sapred.slice(1).toLowerCase()}.pdf`;
        const rutaGrado = path.join(dirSede, nombreGrado);
        let ok = false;
        let ultimoError = null;
        for (let intento = 1; intento <= 2 && !ok; intento++) {
          try {
            if (!(await estaLogueado(page))) throw new Error("la sesión de SAPRED se cerró");
            const { rutas } = await generarBoletinPdfSede(
              page, frame, context, sede.sedeSapred, grado.sapred, periodoTexto, rutaGrado, { pdfContext }
            );
            rutas.forEach((r) => partes.push({ grado: grado.numero, ruta: r, n_estudiantes: n }));
            ok = true;

            // Además del PDF del grado completo, lo divide por sección en
            // <dirSede>/<grado>/<grado>-<seccion>.pdf (carpeta "4" con
            // "4-1.pdf", "4-2.pdf"...). Dinámico: sirve para 1 sección o 6.
            // Best-effort: si falla, el PDF combinado del grado sigue intacto.
            for (const r of rutas) {
              try {
                const sep = await apiPostJSON(apiBase, "/api/boletines/separar-por-seccion", {
                  html: r.replace(/\.pdf$/i, ".html"),
                  pdf: r,
                  carpeta_salida: path.join(dirSede, String(grado.numero)),
                });
                if (sep.separado) {
                  console.log(`[separar-seccion] grado ${grado.numero}: ${Object.keys(sep.secciones).join(", ")}`);
                } else {
                  console.log(`[separar-seccion] grado ${grado.numero}: no se pudo separar (queda solo el PDF combinado)`);
                }
              } catch (e) {
                console.log(`[separar-seccion] grado ${grado.numero}: error — ${e.message}`);
              }
            }
          } catch (err) {
            ultimoError = err;
            const transitorio = /detach|target closed|context was destroyed|navigation|timeout|se cerr/i.test(
              String((err && err.message) || err)
            );
            if (intento < 2 && transitorio) {
              await page.waitForTimeout(1500);
              frame = page.frames().find((f) => f.url().includes(BOLETIN_GEN_MATCH)) || frame;
            } else {
              break; // error determinista: no reintentar (evita generar 2 veces)
            }
          }
        }
        if (!ok) fallos.push(`${grado.sapred}: ${ultimoError ? ultimoError.message : "error"}`);
      }

      if (!partes.length) {
        await reportarProgreso(apiBase, auditId, {
          sedes_completadas: 1,
          detalle_sede: {
            sede: sede.sedeNombreDB,
            estado: "error",
            detalle: `No se generó ningún grado. ${fallos.join(" · ")}`,
          },
        });
        continue;
      }

      try {
        const res = await apiPostJSON(
          apiBase,
          `/api/boletines/generar-pdf/${auditId}/ensamblar-sede`,
          {
            sede_id: sede.sedeId,
            sede_nombre: sede.sedeNombreDB,
            partes,
          }
        );
        await reportarProgreso(apiBase, auditId, {
          sedes_completadas: 1,
          estudiantes_revisados_delta: res.n_estudiantes || 0,
          detalle_sede: {
            sede: sede.sedeNombreDB,
            estado: fallos.length ? "advertencia" : "completada",
            detalle: fallos.length ? `Faltaron grados: ${fallos.join(" · ")}` : null,
            archivo: res.archivo,
            n_estudiantes: res.n_estudiantes,
            n_paginas: res.n_paginas,
          },
        });
      } catch (e) {
        await reportarProgreso(apiBase, auditId, {
          sedes_completadas: 1,
          detalle_sede: {
            sede: sede.sedeNombreDB,
            estado: "error",
            detalle: `Se generaron los PDF por grado pero falló el ensamblado: ${e.message}`,
          },
        });
      }
    }

    // Los PDF por grado se DEJAN en <carpeta>/<SEDE ...>/ (el usuario los
    // quiere poder ver); el backend solo unió el consolidado.

    await browser.close().catch(() => {});
    await pdfBrowser.close().catch(() => {});
    await reportarProgreso(apiBase, auditId, { estado: "completada" });
    process.exit(0);
  } catch (err) {
    console.error(err);
    try {
      await reportarProgreso(apiBase, auditId, { estado: "error", error: String(err.message || err) });
    } catch (e) {
      /* ya se perdió la conexión */
    }
    if (browser) await browser.close().catch(() => {});
    if (pdfBrowser) await pdfBrowser.close().catch(() => {});
    process.exit(1);
  }
})();
