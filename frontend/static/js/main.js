// --- Arranque: parámetros de URL + primer render. Debe cargarse ÚLTIMO, ---
// --- después de que todas las vistas y el estado global existan. ---------
//
// Fase 4.0: esta lógica ya NO se ejecuta directo al cargar el script — queda
// envuelta en iniciarNavegacion() y la dispara auth.js (iniciarApp(), al
// final de este archivo) recién después de confirmar que hay sesión. El
// contenido de la función es exactamente el mismo de antes, sin cambios.

function iniciarNavegacion() {
  // Permite abrir/enlazar directo a Estudiantes con filtros e impresión lista, ej:
  // /?vista=estudiantes&sede=29&grado=6&division=1&imprimir=1
  (function aplicarParametrosDeUrl() {
    const p = new URLSearchParams(window.location.search);
    if (!p.has("vista")) return;
    vistaActual = p.get("vista");
    if (p.has("sede")) sedeSeleccionada = Number(p.get("sede"));
    if (p.has("grado")) gradoSeleccionado = Number(p.get("grado"));
    if (p.has("division")) divisionSeleccionada = Number(p.get("division"));
    if (p.has("mes")) mesSeleccionado = Number(p.get("mes"));
    if (vistaActual === "boletines" && p.has("sec")) seccionBoletines = p.get("sec");
    if (vistaActual === "horario" && p.has("sub")) horarioSub = p.get("sub");
    if (vistaActual === "horario" && p.has("fecha")) horarioFecha = p.get("fecha");
    if (vistaActual === "horario" && p.has("docente")) {
      horarioDocenteId = Number(p.get("docente"));
      if (!p.has("sub")) horarioSub = "docente";
    }
    if (p.get("imprimir") === "1") mostrarImprimir = true;
    if (p.has("id")) fichaEstudianteId = Number(p.get("id"));
    tabs.forEach((t) => t.classList.remove("activo"));
    document.querySelector(`[data-vista="${vistaActual === "ficha" ? "estudiantes" : vistaActual}"]`)?.classList.add("activo");
  })();

  render();
}

iniciarApp();
