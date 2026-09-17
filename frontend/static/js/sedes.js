// --- Vista: Sedes -----------------------------------------------------

async function renderSedes() {
  app.innerHTML = "<p>Cargando sedes...</p>";
  const sedes = await api("/api/sedes");

  const totalEstudiantes = sedes.reduce((acc, s) => acc + s.total_estudiantes, 0);
  const totalActivos = sedes.reduce((acc, s) => acc + s.total_activos, 0);

  app.innerHTML = `
    <div class="toolbar">
      <strong>${sedes.length} sedes</strong>
      <span>${totalEstudiantes} estudiantes (${totalActivos} activos)</span>
      <input type="text" id="buscar-sede" placeholder="Buscar sede..." />
    </div>
    <div class="grid-salones" id="grid-sedes">
      ${sedes.map(tarjetaSede).join("")}
    </div>
  `;

  vincularClicksSede();

  document.getElementById("buscar-sede").addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    document.getElementById("grid-sedes").innerHTML = sedes
      .filter((s) => s.nombre.toLowerCase().includes(q))
      .map(tarjetaSede)
      .join("");
    vincularClicksSede();
  });
}

function tarjetaSede(s) {
  const inactivos = s.total_estudiantes - s.total_activos;
  return `
    <div class="card-salon" data-id="${s.id}">
      <h3>${s.nombre.replace(/^SEDE\s*#?\s*\d+\s*/i, "")}</h3>
      <div class="grado">${s.resguardo || ""}</div>
      <div class="stats">
        <span>${s.total_activos} activos</span>
        ${inactivos > 0 ? `<span class="alerta">${inactivos} inactivos</span>` : `<span>0 inactivos</span>`}
      </div>
    </div>`;
}

function vincularClicksSede() {
  document.querySelectorAll(".card-salon").forEach((card) => {
    card.addEventListener("click", () => {
      sedeSeleccionada = Number(card.dataset.id);
      gradoSeleccionado = null;
      divisionSeleccionada = null;
      paginaActual = 1;
      vistaActual = "estudiantes";
      tabs.forEach((t) => t.classList.remove("activo"));
      document.querySelector('[data-vista="estudiantes"]').classList.add("activo");
      render();
    });
  });
}
