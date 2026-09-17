// Ayuda de una sola vez: abre SAPRED, espera a que inicies sesión (a mano,
// como siempre) y luego imprime TODAS las llamadas addTab(...) que hay en el
// menú, resaltando las que mencionan "boletín". De ahí se copian los dos
// valores que faltan para la automatización del "Boletín informativo":
// la ruta del index.php y el id numérico.
//
// Uso: node descubrir_boletin.js
// Cuando termine, pega la línea del "Boletín informativo" en:
//   - sapred_core.js  (BOLETIN_RUTA / BOLETIN_ID), o
//   - variables de entorno SAPRED_BOLETIN_RUTA / SAPRED_BOLETIN_ID

const { abrirNavegadorSapred, esperarLogin, estaLogueado, ocultarPopups } = require("./sapred_core.js");

function normaliza(s) {
  return (s || "")
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
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
  console.log("Sesión iniciada. Leyendo el menú...\n");
  await page.waitForTimeout(2500);
  await ocultarPopups(page);

  const llamadas = new Set();
  for (const frame of page.frames()) {
    let encontradas = [];
    try {
      encontradas = await frame.evaluate(() => {
        const out = [];
        // 1) cualquier elemento cuyo onclick/href invoque addTab(...)
        document.querySelectorAll("*").forEach((el) => {
          const attrs = [el.getAttribute("onclick"), el.getAttribute("href")].filter(Boolean).join(" ");
          const m = attrs.match(/addTab\s*\([^)]*\)/g);
          if (m) m.forEach((x) => out.push({ call: x, texto: (el.textContent || "").trim().slice(0, 60) }));
        });
        // 2) el HTML entero por si addTab aparece en scripts inline del menú
        const html = document.documentElement.outerHTML;
        const m2 = html.match(/addTab\s*\([^)]*\)/g);
        if (m2) m2.forEach((x) => out.push({ call: x, texto: "" }));
        return out;
      });
    } catch (e) {
      /* frame en transición */
    }
    encontradas.forEach((e) => llamadas.add(JSON.stringify(e)));
  }

  const lista = [...llamadas].map((s) => JSON.parse(s));
  let rutaBoletin = null;
  if (!lista.length) {
    console.log("No se encontró ninguna llamada addTab(...). Abre a mano el menú");
    console.log("Reportes > Reportes y Resultados Académicos y vuelve a correr esto.");
  } else {
    console.log("=== Llamadas addTab(...) encontradas en el menú ===\n");
    for (const e of lista) {
      const esBoletin = normaliza(e.call + " " + e.texto).includes("bolet");
      console.log(`${e.call}${e.texto ? "   [" + e.texto + "]" : ""}${esBoletin ? "  <<< BOLETÍN" : ""}`);
      if (esBoletin) {
        const m = e.call.match(/addTab\([^,]*,\s*['"]([^'"]+)['"]/);
        if (m) rutaBoletin = m[1];
      }
    }
    console.log("\nBusca la del 'Boletín informativo'. Sus argumentos son:");
    console.log('  addTab("Boletín informativo", "<RUTA>", "", "<ID>")');
    console.log("Copia <RUTA> a BOLETIN_RUTA y <ID> a BOLETIN_ID en sapred_core.js");
  }

  // --- Paso 2: abrir el reporte del Boletín y listar sus campos de formulario
  // OJO: este formulario va revelando campos a medida que se completan los
  // anteriores (Sede -> aparece Grado -> aparece Curso/Periodo -> aparece el
  // resto) — no todo está en el DOM desde el principio. Por eso no basta con
  // leerlo una vez: hay que ir seleccionando cada select nuevo que aparezca
  // (con su primera opción real) y volver a leer el formulario después de
  // cada paso, hasta que ya no aparezca nada nuevo.
  if (rutaBoletin) {
    console.log(`\nAbriendo "${rutaBoletin}" para leer los campos del formulario...`);
    try {
      await page.evaluate((ruta) => addTab("Boletín informativo", ruta, "", "186"), rutaBoletin);
      await page.waitForTimeout(3500);
      await ocultarPopups(page);
      const marca = rutaBoletin.split("/").slice(0, 2).join("/");
      const frame = page.frames().find((f) => f.url().includes(marca)) || page;

      const leerCampos = () =>
        frame.evaluate(() => {
          const r = [];
          document.querySelectorAll("select, input, button, a[onclick]").forEach((el) => {
            const id = el.id || el.name || "";
            if (!id && el.tagName !== "BUTTON" && !el.getAttribute("onclick")) return;
            let extra = "";
            if (el.tagName === "SELECT") {
              extra = " opciones=[" + [...el.options].map((o) => o.textContent.trim()).join(" | ") + "]";
            } else if (el.tagName === "INPUT" && (el.type === "radio" || el.type === "checkbox")) {
              extra = ` value="${el.value}" checked=${el.checked}`;
            } else if (el.getAttribute("onclick")) {
              extra = " onclick=" + el.getAttribute("onclick").slice(0, 80);
            }
            r.push(`<${el.tagName.toLowerCase()}${el.type ? " type=" + el.type : ""}> id/name="${id}"${extra}`);
          });
          return r;
        });

      // Selecciona la SEGUNDA opción (índice 1) de un <select> — en este
      // formulario la opción [0] es siempre el placeholder ("Seleccione una
      // sede", "[ESCOJA UN PERIODO]", etc.), y ese placeholder casi nunca
      // tiene value="" explícito (a veces el navegador le pone como value su
      // propio texto) — por eso NO sirve filtrar por "value no vacío", hay
      // que ir por posición.
      const elegirPrimeraOpcionReal = (idONombre) =>
        frame.evaluate((sel) => {
          const el = document.getElementById(sel) || document.getElementsByName(sel)[0];
          if (!el || el.tagName !== "SELECT" || el.options.length < 2) return null;
          const opcion = el.options[1];
          el.value = opcion.value;
          el.dispatchEvent(new Event("change", { bubbles: true }));
          // algunos onchange de SAPRED están puestos como atributo, no
          // como listener — se dispara también por si acaso.
          if (typeof el.onchange === "function") el.onchange();
          return opcion.textContent.trim();
        }, idONombre);

      let anterior = await leerCampos();
      console.log(`\n--- Paso 0 (recién abierto): ${anterior.length} campo(s) ---`);
      anterior.forEach((c) => console.log("  " + c));

      const procesados = [];
      for (let paso = 1; paso <= 6; paso++) {
        // el primer <select> sin procesar todavía que ya tenga más de una
        // opción (es decir, que no esté vacío esperando el AJAX de un select
        // anterior) es el "siguiente" campo a completar en esta cascada.
        const idSiguienteSelect = await frame
          .evaluate((yaHechos) => {
            const selects = [...document.querySelectorAll("select")];
            const s = selects.find((el) => {
              const clave = el.id || el.name;
              return clave && !yaHechos.includes(clave) && el.options.length > 1;
            });
            return s ? s.id || s.name : null;
          }, procesados)
          .catch(() => null);

        if (!idSiguienteSelect) {
          console.log(`\n(paso ${paso}: no quedan más <select> con opciones por completar — se detiene la cascada)`);
          break;
        }

        procesados.push(idSiguienteSelect);
        const textoElegido = await elegirPrimeraOpcionReal(idSiguienteSelect);
        console.log(`\n>>> Paso ${paso}: seleccioné "${textoElegido}" en id/name="${idSiguienteSelect}", esperando que se actualice el formulario...`);
        await page.waitForTimeout(2000);
        await ocultarPopups(page);

        const actual = await leerCampos();
        const idsAntes = new Set(anterior.map((c) => c));
        const nuevos = actual.filter((c) => !idsAntes.has(c));
        console.log(`--- Paso ${paso}: ${actual.length} campo(s) en total, ${nuevos.length} nuevo(s) ---`);
        (nuevos.length ? nuevos : actual).forEach((c) => console.log("  " + c));
        anterior = actual;
      }

      console.log("\n=== Listado FINAL completo del formulario del Boletín informativo ===");
      console.log("(compara con los del Consolidado: #id_sed #cod_gra #id_jor #cod_cur #id_peri #gen_reporte)\n");
      anterior.forEach((c) => console.log("  " + c));
    } catch (e) {
      console.log("No se pudo abrir/recorrer el reporte automáticamente:", e.message);
    }
  }

  console.log("\nCierra la ventana de Chrome cuando termines.");
  await page.waitForTimeout(2000);
  await browser.close();
})();
