// Prueba EN VIVO de la automatización real del Boletín informativo: llama
// directamente a generarYExtraerBoletin() (la misma función que usa la app
// en producción) para una sede+grado+periodo de prueba, y muestra:
//   1. Cualquier error interno de la página SAPRED (pageerror/console.error)
//      que ocurra al ir seleccionando los campos — SIN dejar que tumbe el
//      script, igual que le pasa a la automatización real.
//   2. El código fuente de la función mostrar() de SAPRED (para ver qué
//      línea revienta y por qué).
//   3. Los bloques de datos que finalmente devuelve la función — la prueba
//      real de si el reporte se generó con contenido o llegó vacío.
//
// Uso: node probar_boletin_en_vivo.js
// (pide login a mano en Chrome, igual que los demás scripts de esta carpeta)

const {
  abrirNavegadorSapred,
  esperarLogin,
  ocultarPopups,
  abrirPestanaReporteBoletin,
  generarYExtraerBoletin,
} = require("./sapred_core.js");

// Ajusta estos tres valores si quieres probar otra sede/grado/periodo.
const SEDE_PRUEBA = "IE Indígena Técnica Agroambiental Bilingüe Awa";
const GRADO_PRUEBA = "SEPTIMO";
const PERIODO_PRUEBA = "PRIMER PERIODO";

(async () => {
  console.log("Abriendo SAPRED. Inicia sesión en la ventana de Chrome (hasta 15 min)...\n");
  const { browser, page } = await abrirNavegadorSapred();

  page.on("pageerror", (err) => console.log("\n[PAGEERROR de SAPRED, no debería tumbar la prueba]", err.message));
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log("\n[CONSOLE.ERROR de SAPRED]", msg.text());
  });

  const ok = await esperarLogin(page, 15 * 60 * 1000);
  if (!ok) {
    console.log("No se detectó el inicio de sesión a tiempo.");
    await browser.close();
    process.exit(1);
  }
  console.log("Sesión iniciada. Abriendo la pestaña del Boletín informativo...\n");
  await page.waitForTimeout(1500);
  await ocultarPopups(page);

  const frame = await abrirPestanaReporteBoletin(page);
  if (!frame) {
    console.log("No se pudo abrir la pestaña del Boletín informativo (revisa BOLETIN_RUTA/BOLETIN_ID en sapred_core.js).");
    await browser.close();
    process.exit(1);
  }
  frame.on("pageerror", (err) => console.log("\n[PAGEERROR dentro del frame del Boletín]", err.message));

  // Antes de tocar nada: leemos el código de mostrar() para ver exactamente
  // qué intenta hacer y qué elemento espera que exista.
  const fuenteMostrar = await frame
    .evaluate(() => (typeof mostrar === "function" ? mostrar.toString() : "(no existe una función global 'mostrar' en este frame)"))
    .catch((e) => `(no se pudo leer: ${e.message})`);
  console.log("=== Código fuente de mostrar() en la página del Boletín ===\n");
  console.log(fuenteMostrar);
  console.log("\n=== Fin del código de mostrar() ===\n");

  // mostrar(id) hace get(id).style.display='' — y truena cuando get(id) da
  // null. Le ponemos un envoltorio que ANOTA con qué id se llamó y si
  // existía el elemento, sin dejar que el error se propague y corte el
  // resto del onchange de SAPRED (así vemos TODAS las llamadas, no solo la
  // primera que revienta).
  await frame
    .evaluate(() => {
      window.__mostrarOriginal = window.mostrar;
      window.__llamadasMostrar = [];
      window.mostrar = function (id) {
        let existe = false;
        try {
          existe = !!(typeof get === "function" ? get(id) : document.getElementById(id));
        } catch (e) {
          existe = "error al comprobar: " + e.message;
        }
        window.__llamadasMostrar.push({ id, existe });
        try {
          return window.__mostrarOriginal(id);
        } catch (e) {
          // se traga el error para que el resto del onchange de SAPRED
          // siga corriendo — igual que le pasa a Playwright en producción.
          return undefined;
        }
      };
    })
    .catch((e) => console.log("(no se pudo poner el envoltorio de mostrar():", e.message, ")"));

  console.log(`Llamando a generarYExtraerBoletin(sede="${SEDE_PRUEBA}", grado="${GRADO_PRUEBA}", periodo="${PERIODO_PRUEBA}")...\n`);
  try {
    const bloques = await generarYExtraerBoletin(
      page,
      frame,
      browser.contexts()[0] || page.context(),
      SEDE_PRUEBA,
      GRADO_PRUEBA,
      PERIODO_PRUEBA
    );
    console.log(`\n=== RESULTADO: generarYExtraerBoletin devolvió ${bloques ? bloques.length : 0} bloque(s) ===\n`);
    if (bloques && bloques.length) {
      console.log("Primer bloque (para revisar que trae datos reales):");
      console.log(JSON.stringify(bloques[0], null, 2));
    } else {
      console.log("¡Vacío! Esto confirma que el reporte no se está generando con contenido.");
    }
  } catch (e) {
    console.log("\n=== generarYExtraerBoletin lanzó un error ===");
    console.log(e.stack || e.message);
  }

  const llamadas = await frame.evaluate(() => window.__llamadasMostrar || []).catch(() => []);
  console.log(`\n=== Todas las llamadas a mostrar(id) durante la prueba (${llamadas.length}) ===`);
  llamadas.forEach((l, i) => console.log(`  ${i + 1}. mostrar("${l.id}")  ->  ¿existe el elemento?: ${l.existe}`));

  console.log("\nDejo el navegador abierto 30 segundos para que revises la pantalla a mano antes de cerrarlo...");
  await page.waitForTimeout(30000);
  await browser.close();
})();
