// Ayuda de una sola vez para la GENERACIÓN del boletín general (el PDF de
// calificaciones que se entrega al docente). Abre SAPRED, espera el login a
// mano y luego:
//   1. imprime TODAS las llamadas addTab(...) del menú, resaltando las de
//      "boletín" — de ahí se copian BOLETIN_GEN_RUTA / BOLETIN_GEN_ID a
//      sapred_core.js (o a las variables de entorno SAPRED_BOLETIN_GEN_RUTA /
//      SAPRED_BOLETIN_GEN_ID).
//   2. abre ese reporte y lista sus campos (sede/grado/curso/período/formato/
//      botón generar), recorriendo la cascada.
//   3. abre el modal "Opciones de impresión" y lista sus radios, para afinar
//      configurarOpcionesImpresionBoletin() ("Mostrar Sede", "Incluir
//      Puesto").
//
// Uso: node descubrir_boletin_general.js

const { abrirNavegadorSapred, esperarLogin, ocultarPopups } = require("./sapred_core.js");

function normaliza(s) {
  return (s || "")
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

async function leerCampos(frame) {
  return frame.evaluate(() => {
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
        extra = " onclick=" + el.getAttribute("onclick").slice(0, 90);
      }
      r.push(`<${el.tagName.toLowerCase()}${el.type ? " type=" + el.type : ""}> id/name="${id}"${extra}`);
    });
    return r;
  });
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
        document.querySelectorAll("*").forEach((el) => {
          const attrs = [el.getAttribute("onclick"), el.getAttribute("href")].filter(Boolean).join(" ");
          const m = attrs.match(/addTab\s*\([^)]*\)/g);
          if (m) m.forEach((x) => out.push({ call: x, texto: (el.textContent || "").trim().slice(0, 60) }));
        });
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
  console.log("=== Llamadas addTab(...) del menú (se resaltan las de 'boletín') ===\n");
  for (const e of lista) {
    const esBoletin = normaliza(e.call + " " + e.texto).includes("bolet");
    console.log(`${e.call}${e.texto ? "   [" + e.texto + "]" : ""}${esBoletin ? "  <<< BOLETÍN" : ""}`);
  }
  console.log("\nBusca la del boletín de CALIFICACIONES (no 'Boletín informativo').");
  console.log('Sus argumentos son:  addTab("Boletín", "<RUTA>", "", "<ID>")');
  console.log("Copia <RUTA> a BOLETIN_GEN_RUTA y <ID> a BOLETIN_GEN_ID en sapred_core.js\n");

  // Deja que elijas tú mismo el reporte del menú y espera a que aparezca.
  console.log("Ahora abre TÚ el reporte del boletín de calificaciones desde el menú.");
  console.log("Esperando 40 s a que aparezca su formulario...\n");
  await page.waitForTimeout(40000);
  await ocultarPopups(page);

  // El frame más probable del reporte: el último que no sea el del menú.
  const frames = page.frames().filter((f) => f.url() && f.url() !== "about:blank");
  const frame = frames[frames.length - 1] || page.mainFrame();
  console.log(`Frame elegido: ${frame.url()}\n`);

  console.log("=== Campos del formulario del boletín ===");
  try {
    (await leerCampos(frame)).forEach((c) => console.log("  " + c));
  } catch (e) {
    console.log("  no se pudieron leer:", e.message);
  }

  console.log("\n=== Buscando el modal 'Opciones de impresión' ===");
  try {
    const abridor = frame
      .locator(
        'a:has-text("Opciones de impresi"), button:has-text("Opciones de impresi"), [onclick*="impresion" i]'
      )
      .first();
    if (await abridor.count()) {
      await abridor.click().catch(() => {});
      await page.waitForTimeout(2000);
      console.log("(modal abierto)\n");
    } else {
      console.log("(no vi el botón — ábrelo tú, esperando 15 s)\n");
      await page.waitForTimeout(15000);
    }
    for (const f of page.frames()) {
      let tiene = false;
      try {
        tiene = await f.evaluate(() =>
          /opciones de impresi/i.test(document.body ? document.body.innerText : "")
        );
      } catch (e) {
        /* */
      }
      if (!tiene) continue;
      console.log(`--- campos del modal (frame ${f.url()}) ---`);
      (await leerCampos(f)).forEach((c) => console.log("  " + c));
      const filas = await f.evaluate(() =>
        [...document.querySelectorAll("tr")]
          .map((tr) => tr.innerText.replace(/\s+/g, " ").trim())
          .filter((t) => /sede|puesto/i.test(t))
      );
      console.log("  filas con 'sede'/'puesto':", JSON.stringify(filas, null, 2));
    }
  } catch (e) {
    console.log("  no se pudo:", e.message);
  }

  console.log("\nCierra la ventana de Chrome cuando termines.");
  await page.waitForTimeout(2000);
  await browser.close();
})();
