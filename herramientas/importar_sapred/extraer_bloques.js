// Extrae, desde la página HTML del reporte "Consolidado de Asignaturas por
// periodo" de SAPRED, un bloque por cada curso — misma forma que produce el
// parser de PDF en Python (importador_sapred.py), para reusar la misma
// lógica de importación en el backend.
function extraerBloquesDeReporteSapred() {
  const bloques = [];
  const tablas = Array.from(document.querySelectorAll("table"));

  // Texto completo de la página, para sacar "Curso X-Y NOMBRE" y "Periodo: N"
  // que anteceden a cada tabla de datos (mismo layout que el PDF).
  const textoCompleto = document.body.innerText;
  const bloquesTexto = textoCompleto.split(/(?=Curso\s)/).filter((b) => b.trim().startsWith("Curso"));

  const tablasDatos = tablas.filter((t) => t.rows.length > 0 && t.rows[0].className === "fila_tit_n1");

  tablasDatos.forEach((tabla, idx) => {
    const textoBloque = bloquesTexto[idx] || "";
    // Normalmente "1-1", pero al menos una sede real lo tiene con punto ("1.1").
    // Y al menos un grado (Octavo, Once) trae la sede pegada sin espacio,
    // separada solo por otro guion: "8-1-IETABA," en vez de "8-1 IETABA,"
    // (mismo caso que en el parser de PDF, importador_sapred.py).
    const mCurso = textoBloque.match(/Curso\s*\t?\s*(\d+)[-.](\d+)[-\s]+([^\n,]+),/);
    const mPeriodo = textoBloque.match(/Periodo:\s*(\d+)/);
    const mFecha = textoBloque.match(/(20\d{2})/);
    // El nombre del profesor sale justo antes de la línea "Director de Grupo".
    const mDirector = textoBloque.match(/\n\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s.]{4,60})\s*\n\s*Director de Grupo/);
    if (!mCurso) return;

    const filaCodigos = tabla.rows[0];
    const codigos = Array.from(filaCodigos.cells)
      .slice(3) // salta No./Código/Estudiante
      .map((c) => c.textContent.trim());

    const estudiantes = [];
    for (let i = 3; i < tabla.rows.length; i++) {
      const celdas = Array.from(tabla.rows[i].cells).map((c) => c.textContent.trim());
      if (celdas.length < 2 || !/^\d+$/.test(celdas[1])) continue; // celdas[1] = documento
      const documento = celdas[1];
      const nombre = celdas[2] || "";
      const notas = {};
      codigos.forEach((codigo, j) => {
        const valor = celdas[3 + j];
        notas[codigo] = valor ? valor : null;
      });
      estudiantes.push({ documento, nombre, notas });
    }

    bloques.push({
      grado: Number(mCurso[1]),
      curso: Number(mCurso[2]),
      sede_corta: mCurso[3].trim(),
      periodo: mPeriodo ? Number(mPeriodo[1]) : 1,
      anio_lectivo: mFecha ? Number(mFecha[1]) : null,
      director_grupo: mDirector ? mDirector[1].trim().replace(/\s+/g, " ") : null,
      areas: codigos.map((c) => ({ codigo: c, nombre: c })),
      estudiantes,
    });
  });

  return bloques;
}

module.exports = { extraerBloquesDeReporteSapred };
