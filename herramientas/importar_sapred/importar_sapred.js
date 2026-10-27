// Herramienta MANUAL de respaldo: hace la misma auditoría que
// "Boletines -> Auditoría SAPRED" en la app, pero desde la consola, por si
// alguna vez no se puede usar la app (ej. mientras se prueba un cambio).
// El camino recomendado para el día a día es la app — ver LEEME.txt.
//
// Uso: doble clic en Importar_SAPRED.bat, o "node importar_sapred.js"

const readline = require("readline");
const { GRADOS, apiGet, apiPostJSON, estaLogueado, esperarLogin, abrirNavegadorSapred, abrirPestanaReporte, generarYExtraerTodasJornadas, textoPeriodo } = require("./sapred_core.js");
const SEDES_SAPRED = require("./config_sedes.json");

const API_BASE = "http://127.0.0.1:8000";

function preguntar(texto) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => rl.question(texto, (resp) => { rl.close(); resolve(resp.trim()); }));
}

(async () => {
  console.log("=== Importador de notas SAPRED -> IETABA (modo manual) ===\n");

  try {
    await apiGet(API_BASE, "/api/sedes");
  } catch (e) {
    console.log("No pude conectarme a la app IETABA en " + API_BASE + ".");
    console.log("Abre primero el servidor de la app y vuelve a correr esto.");
    await preguntar("\nPresiona Enter para cerrar...");
    process.exit(1);
  }

  let periodoNum = process.argv[2] || (await preguntar("¿Qué período vas a revisar? (1, 2, 3 o 4, Enter = 2): "));
  let periodoTexto = textoPeriodo(periodoNum.trim() || "2");
  while (!periodoTexto) {
    periodoNum = await preguntar("Ese período no existe. Escribe 1, 2, 3 o 4: ");
    periodoTexto = textoPeriodo(periodoNum);
  }

  let gradoFiltro = process.argv[3] || (await preguntar("¿Solo un grado? Número (0=Transición...11=Once) o Enter para TODOS: "));
  const gradosAProcesar = gradoFiltro ? GRADOS.filter((g) => String(g.numero) === gradoFiltro.trim()) : GRADOS;

  console.log(`\nPeríodo: ${periodoTexto}`);
  console.log(`Grados a revisar: ${gradosAProcesar.map((g) => g.sapred).join(", ")}\n`);

  const todasLasSedesDB = await apiGet(API_BASE, "/api/sedes");
  const sedeIdPorNombre = {};
  todasLasSedesDB.forEach((s) => { sedeIdPorNombre[s.nombre] = s.id; });

  console.log("Abriendo ventana de SAPRED — entra con tu usuario y contraseña ahí (eso lo haces tú).");
  const { browser, page } = await abrirNavegadorSapred();

  console.log("\nEsperando a que inicies sesión (hasta 15 minutos)...");
  const logueado = await esperarLogin(page, 15 * 60 * 1000);
  if (!logueado) {
    console.log("No se detectó el login a tiempo. Vuelve a correr el programa cuando vayas a entrar.");
    await browser.close();
    await preguntar("\nPresiona Enter para cerrar...");
    process.exit(1);
  }
  console.log("Sesión iniciada. De aquí en adelante corre solo.\n");

  const context = browser.contexts()[0];
  let frame = await abrirPestanaReporte(page);

  const resumenGeneral = { totalPendientesCreados: 0, sedesOk: 0, sedesFallidas: [], gradosConDatos: 0 };

  for (const grado of gradosAProcesar) {
    let conteoDelGrado;
    try {
      // Fase 4.1: ruta reducida (solo sede_id + cantidad, sin datos
      // personales) — es endpoint interno, exige identidad de servicio.
      conteoDelGrado = await apiGet(API_BASE, `/api/estudiantes/conteo-por-sede?grado=${grado.numero}&estado=ACTIVO`);
    } catch (e) {
      console.log(`No pude consultar estudiantes de grado ${grado.sapred}: ${e.message}`);
      continue;
    }
    const sedeIdsConEstudiantes = new Set(conteoDelGrado.map((c) => c.sede_id));
    const sedesDelGrado = Object.entries(SEDES_SAPRED).filter(
      ([nombreDB]) => sedeIdsConEstudiantes.has(sedeIdPorNombre[nombreDB])
    );

    if (!sedesDelGrado.length) {
      console.log(`--- Grado ${grado.sapred}: ninguna sede tiene estudiantes activos, se salta. ---`);
      continue;
    }

    console.log(`\n=== Grado ${grado.sapred} (${sedesDelGrado.length} sede(s)) ===`);
    resumenGeneral.gradosConDatos++;
    const bloquesDelGrado = [];

    for (const [nombreDB, sedeSapred] of sedesDelGrado) {
      process.stdout.write(`  ${nombreDB} ... `);
      let intentos = 0;
      let ok = false;
      while (intentos < 2 && !ok) {
        intentos++;
        try {
          if (!(await estaLogueado(page))) throw new Error("la sesión se cerró");
          const bloques = await generarYExtraerTodasJornadas(page, frame, context, sedeSapred, grado.sapred, periodoTexto);
          bloques.forEach((b) => { b.sede_id = sedeIdPorNombre[nombreDB]; });
          bloquesDelGrado.push(...bloques);
          const totalEst = bloques.reduce((a, b) => a + b.estudiantes.length, 0);
          console.log(`${bloques.length} curso(s), ${totalEst} estudiante(s)`);
          ok = true;
          resumenGeneral.sedesOk++;
        } catch (err) {
          if (intentos >= 2) {
            console.log(`FALLÓ: ${err.message}`);
            resumenGeneral.sedesFallidas.push(`${nombreDB} (grado ${grado.sapred}): ${err.message}`);
          } else {
            frame = (await abrirPestanaReporte(page)) || frame;
          }
        }
      }
    }

    if (bloquesDelGrado.length) {
      try {
        const resultado = await apiPostJSON(API_BASE, "/api/boletines/importar-sapred-bloques", bloquesDelGrado);
        resumenGeneral.totalPendientesCreados += resultado.total_pendientes_creados;
        console.log(`  -> ${resultado.total_pendientes_creados} pendiente(s) nuevo(s) para grado ${grado.sapred}.`);
      } catch (err) {
        console.log(`  No se pudo enviar a la app: ${err.message}`);
      }
    }
  }

  await browser.close();

  console.log("\n\n================ RESUMEN ================");
  console.log(`Grados con datos: ${resumenGeneral.gradosConDatos}`);
  console.log(`Sedes procesadas correctamente: ${resumenGeneral.sedesOk}`);
  console.log(`Total de pendientes nuevos creados: ${resumenGeneral.totalPendientesCreados}`);
  if (resumenGeneral.sedesFallidas.length) {
    console.log(`\nNo se pudieron procesar (${resumenGeneral.sedesFallidas.length}):`);
    resumenGeneral.sedesFallidas.forEach((f) => console.log(`  - ${f}`));
  }
  console.log("\nYa puedes ir a la pestaña Boletines de la app a revisar.");
  await preguntar("\nPresiona Enter para cerrar esta ventana...");
})();
