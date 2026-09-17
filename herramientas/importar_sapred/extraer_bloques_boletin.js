// Extrae, desde la página HTML del reporte "Boletín informativo" de SAPRED,
// un bloque por curso — misma forma que produce el parser de PDF en Python
// (backend/app/importador_boletin.py: parsear_pdf_boletin), para reusar la
// misma lógica de importación en el backend
// (/api/boletines/importar-boletin-bloques).
//
// Trabaja sobre document.body.innerText (no sobre el DOM concreto): cada
// estudiante es una sección "INFORME ESCOLAR DE VALORACIÓN ... OBSERVACIONES".
// La lógica es un espejo de _parsear_pagina() en Python — si se ajusta una,
// ajustar la otra.

function extraerBloquesDeBoletinSapred() {
  const NIVEL_DEFECTO = ["Kuisha Wari", "Pichin Wai", "Makas Wai", "Wari"];
  const PERIODOS = { PRIMER: 1, SEGUNDO: 2, TERCER: 3, TERCERO: 3, CUARTO: 4, QUINTO: 5 };
  const CORTE_OBS = /^(ELABORADO|CONVENCIONES|MW=|PW=|W=|KW=|FIRMA)/;

  const reTitulo = /^(.+?)\s*\(([A-ZÑ]{2,6})\)\s*$/;
  const reNombreDoc = /^(.+?)\s+(\d{5,})$/;
  const reGradoCurso = /^(\d+)\s*[-.]\s*(\d+)/;
  const reP1 = /^\d+(?:[.,]\d+)?-(?:MW|PW|W|KW)$/;
  const reFecha = /\b(20\d{2})-\d{2}-\d{2}\b/;

  const texto = document.body.innerText.replace(/\r/g, "");

  function niveles(lineas) {
    for (const t of lineas) {
      if (t.indexOf("=") === -1 || (t.indexOf("Wai") === -1 && t.indexOf("Wari") === -1)) continue;
      const out = [];
      const re = /[A-Z]{1,3}=([A-Za-zÁÉÍÓÚñ ]+?)\s*\(/g;
      let m;
      while ((m = re.exec(t))) {
        const n = m[1].trim();
        if (n && out.indexOf(n) === -1) out.push(n);
      }
      if (out.length) return out.sort((a, b) => b.length - a.length);
    }
    return NIVEL_DEFECTO.slice();
  }

  function limpiar(s) {
    return (s || "").trim().replace(/^[-–:\s]+/, "").trim();
  }

  function parseValores(area, linea, NIV) {
    const tokens = linea.split(/\s+/).filter((t) => !reP1.test(t));
    const resto = tokens.join(" ");
    for (const nv of NIV) {
      const m = resto.match(new RegExp("(\\d+(?:[.,]\\d+)?)\\s+" + nv.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b"));
      if (m) {
        area.nota = m[1].replace(",", ".");
        area.nivel = nv;
        return;
      }
    }
  }

  function parsePagina(seg) {
    const lineas = seg.split("\n").map((l) => l.trim());
    if (!lineas.some((l) => l.toUpperCase().indexOf("INFORME ESCOLAR DE VALORAC") !== -1)) return null;

    const iLbl = lineas.findIndex((l) => l.toUpperCase().indexOf("ESTUDIANTE") !== -1 && l.toUpperCase().indexOf("CODIGO") !== -1);
    if (iLbl === -1) return null;

    // Celdas de cabecera. En el reporte HTML en vivo (a diferencia del PDF)
    // la fila de datos del estudiante sale como una sola línea con celdas
    // separadas por TAB (columnas de una <table>: ESTUDIANTE, CODIGO, CURSO,
    // PERIODO, F. PERIODO) — hay que partir también por tabulador, si no
    // toda la fila cae como una sola celda y nunca llega a las 4 mínimas.
    const cab = [];
    for (const l of lineas.slice(iLbl + 1)) {
      if (!l) continue;
      if (reTitulo.test(l) || /^(CONVENCIONES|OBSERVACIONES)/.test(l.toUpperCase())) break;
      for (const celda of l.split("\t").map((c) => c.trim()).filter(Boolean)) {
        cab.push(celda);
        if (cab.length >= 12) break;
      }
      if (cab.length >= 12) break;
    }
    if (cab.length < 4) return null;

    const PERIODOS_K = Object.keys(PERIODOS);

    // Nombre + documento: en el PDF suelen venir juntos en una sola celda
    // ("NOMBRE 12345678"); en el HTML en vivo vienen en dos celdas
    // consecutivas (nombre sin dígitos, seguida de una celda solo con el
    // documento) — se prueban ambas formas.
    let nombreEst = null;
    let documentoEst = null;
    const combinado = cab.map((x) => x.match(reNombreDoc)).find(Boolean);
    if (combinado) {
      nombreEst = combinado[1].trim();
      documentoEst = combinado[2];
    } else {
      for (let i = 0; i < cab.length - 1; i++) {
        if (/^\d{5,}$/.test(cab[i + 1]) && /[A-Za-zÁÉÍÓÚÑ]/.test(cab[i]) && !reGradoCurso.test(cab[i])) {
          nombreEst = cab[i];
          documentoEst = cab[i + 1];
          break;
        }
      }
    }
    if (!nombreEst || !documentoEst) return null;

    // Grado-curso: acepta un sufijo de sede pegado en la misma celda ("6-2
    // IETABA", como sale en el HTML en vivo) además del "6-2" solo (PDF).
    const reGradoCursoSede = /^(\d+)\s*[-.]\s*(\d+)\b\s*(.*)$/;
    const mGc = cab.map((x) => x.match(reGradoCursoSede)).find(Boolean);
    if (!mGc) return null;
    const sedeEnCelda = (mGc[3] || "").trim().replace(/,$/, "");

    let periodoPal = "";
    for (const x of cab) {
      const xu = x.trim().toUpperCase();
      const hallado = PERIODOS_K.find((k) => xu === k || xu.startsWith(k + " "));
      if (hallado) {
        periodoPal = hallado;
        break;
      }
    }

    // Si el grado-curso no traía sede pegada (formato PDF), se busca como
    // antes: la celda que no es nombre, documento, grado-curso, fecha ni
    // período.
    const sedeCorta =
      sedeEnCelda ||
      (
        cab.find(
          (x) =>
            x !== nombreEst &&
            x !== documentoEst &&
            !reGradoCurso.test(x) &&
            !reFecha.test(x) &&
            !PERIODOS_K.some((k) => x.trim().toUpperCase().startsWith(k)) &&
            x.trim().toUpperCase() !== "PERIODO"
        ) || ""
      )
        .trim()
        .replace(/,$/, "");
    const mNd = { 1: nombreEst, 2: documentoEst };

    const NIV = niveles(lineas);
    const areas = [];
    let actual = null;
    let capturando = false;
    const cerrar = () => {
      if (actual) {
        actual.concepto = limpiar(actual.concepto) || null;
        areas.push(actual);
      }
      actual = null;
      capturando = false;
    };

    for (const l of lineas.slice(iLbl + 1)) {
      if (!l) continue;
      const u = l.toUpperCase();
      if (u.startsWith("CONVENCIONES") || u.startsWith("OBSERVACIONES") || u.startsWith("MW=")) {
        cerrar();
        break;
      }
      const mt = l.match(reTitulo);
      if (mt && l === u && !u.startsWith("PROFESOR") && !u.startsWith("CONCEPTOS")) {
        cerrar();
        actual = { codigo: mt[2], nombre: mt[1].trim(), docente: null, nota: null, nivel: null, concepto: "" };
        continue;
      }
      if (!actual) continue;
      if (u.startsWith("PROFESOR")) {
        // En el HTML en vivo esta línea trae pegados, tras un TAB, los
        // títulos de columna que le siguen en la tabla ("PER 1  ACTUAL
        // PER 2  FNJ  PRO") — se descartan quedándose solo con lo de
        // antes del primer TAB.
        const soloDocente = l.split("\t")[0];
        actual.docente = limpiar(soloDocente.split(":").slice(1).join(":")) || null;
        capturando = false;
      } else if (u.startsWith("CONCEPTOS")) {
        actual.concepto = l.split(":").slice(1).join(":");
        capturando = true;
      } else if (u.startsWith("PER 1") && u.indexOf("PRO") !== -1) {
        capturando = false;
      } else if (capturando) {
        actual.concepto += " " + l;
      } else {
        parseValores(actual, l, NIV);
      }
    }
    cerrar();

    let observacion = null;
    for (let i = 0; i < lineas.length; i++) {
      // Tiene que ser el encabezado de la sección ("OBSERVACIONES:" al
      // inicio de línea) — buscar la palabra en cualquier parte de la
      // línea es demasiado suelto: el concepto de una materia puede
      // mencionar "observaciones" en medio de una frase normal.
      if (!lineas[i].toUpperCase().startsWith("OBSERVACIONES")) continue;
      const partes = [lineas[i].indexOf(":") !== -1 ? lineas[i].split(":").slice(1).join(":").trim() : ""];
      for (const cont of lineas.slice(i + 1)) {
        const cs = cont.trim();
        if (!cs || cs.startsWith("_")) break;
        const up = cs.toUpperCase();
        if (CORTE_OBS.test(up) || up.indexOf("DE GRADO") !== -1 || up.indexOf("COORDINADOR") !== -1 || up === "RECTOR") break;
        if (cs === up && cs.split(/\s+/).length <= 6) break;
        partes.push(cs);
      }
      observacion = limpiar(partes.filter(Boolean).join(" ")) || null;
      break;
    }

    let director = null;
    for (let i = 0; i < lineas.length; i++) {
      if (!/DIRECTORA?\s+DE\s+GRADO/i.test(lineas[i])) continue;
      let cand = lineas[i].replace(/DIRECTORA?\s+DE\s+GRADO/i, "").trim();
      if (!cand && i > 0) cand = lineas[i - 1].trim();
      cand = cand.replace(/[^A-Za-zÁÉÍÓÚÑÜ.\s]/g, "").trim();
      if (cand) director = cand.replace(/\s+/g, " ");
      break;
    }

    const mAnio = seg.match(reFecha);
    const areasEst = {};
    areas.forEach((a) => {
      areasEst[a.codigo] = { nota: a.nota, nivel: a.nivel, concepto: a.concepto };
    });
    return {
      grado: Number(mGc[1]),
      curso: Number(mGc[2]),
      sedeCorta: sedeCorta,
      periodo: PERIODOS[periodoPal] || 2,
      anio: mAnio ? Number(mAnio[1]) : null,
      director,
      documento: mNd[2],
      nombre: mNd[1].trim(),
      observacion,
      areas,
      areasEst,
    };
  }

  const trozos = texto.split(/(?=INSTITUCION EDUCATIVA IND[ÍI]GENA)/);
  const paginas = [];
  for (const t of trozos) {
    if (!t.trim()) continue;
    const p = parsePagina(t);
    if (p) paginas.push(p);
  }

  const bloques = {};
  for (const p of paginas) {
    const clave = p.sedeCorta.toUpperCase().replace(/[^A-Z0-9]/g, "") + "|" + p.grado + "|" + p.curso + "|" + p.periodo;
    let b = bloques[clave];
    if (!b) {
      b = {
        grado: p.grado,
        curso: p.curso,
        sede_corta: p.sedeCorta,
        periodo: p.periodo,
        anio_lectivo: p.anio,
        director_grupo: p.director,
        areas: [],
        _idx: {},
        estudiantes: [],
      };
      bloques[clave] = b;
    }
    if (!b.anio_lectivo) b.anio_lectivo = p.anio;
    if (!b.director_grupo) b.director_grupo = p.director;
    p.areas.forEach((a) => {
      let reg = b._idx[a.codigo];
      if (!reg) {
        reg = { codigo: a.codigo, nombre: a.nombre, docente: a.docente };
        b._idx[a.codigo] = reg;
        b.areas.push(reg);
      } else if (!reg.docente && a.docente) {
        reg.docente = a.docente;
      }
    });
    b.estudiantes.push({ documento: p.documento, nombre: p.nombre, observacion: p.observacion, areas: p.areasEst });
  }
  return Object.values(bloques).map((b) => {
    delete b._idx;
    return b;
  });
}

module.exports = { extraerBloquesDeBoletinSapred };
