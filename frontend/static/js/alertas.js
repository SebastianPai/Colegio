// --- Vista: Autorizaciones de promoción (coordinación / administración) --------
// Solicitudes de permiso para matricular a un estudiante en un grado fuera de
// la regla normal (subir con materias perdidas, saltar o bajar de grado — ver
// backend/app/promocion.py). Las crea quien genera la ficha de matrícula; aquí
// coordinación las aprueba o rechaza (permiso promocion.autorizar) y queda el
// registro de quién pidió, quién decidió, cuándo y por qué.
// Abajo, plegado, el historial de los avisos del sistema anterior
// (AlertaPromocion: solo informaban, no bloqueaban).

let autEstado = "pendiente";
let autFiltro = "";

const AUT_ESTADOS = {
  pendiente: ["Pendiente", "proceso", "clock-3"],
  aprobada: ["Aprobada", "ok", "shield-check"],
  rechazada: ["Rechazada", "alerta", "shield-x"],
  anulada: ["Retirada", "", "circle-x"],
};
const AUT_MOTIVOS = {
  perdidas: "Sube con materias perdidas",
  salto: "Salta grados",
  retroceso: "Baja de grado",
};

function autNombreGrado(g) {
  return (NOMBRES_GRADOS.find(([n]) => n === g) || [g, `Grado ${g}`])[1];
}

function autCuando(t) {
  const f = instanteUtcDesdeApi(t);
  return f ? f.toLocaleString("es-CO", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" }) : "";
}

function autTarjetaHtml(s) {
  const [estadoTxt, estadoClase, estadoIcono] = AUT_ESTADOS[s.estado] || [s.estado, "", "circle"];
  const puedeDecidir = tienePermiso("promocion.autorizar") && s.estado === "pendiente";
  const materias = s.detalle.length
    ? `<div class="tabla-scroll"><table class="prom-tabla">
        <thead><tr><th>Materia</th><th>Docente</th><th>Notas por período</th><th class="prom-num">Promedio</th></tr></thead>
        <tbody>${s.detalle
          .map(
            (d) => `<tr class="prom-fila-perdida"><td><strong>${esc(d.area)}</strong></td>
              <td>${d.docente ? esc(d.docente) : '<span class="prom-tenue">Sin docente asignado</span>'}</td>
              <td>${d.notas.map((n) => `P${n[0]}: <b>${Number(n[1]).toFixed(1)}</b>`).join(" · ")}</td>
              <td class="prom-num"><strong>${Number(d.promedio).toFixed(2)}</strong></td></tr>`
          )
          .join("")}</tbody></table></div>`
    : "";
  return `
    <article class="aut-tarjeta aut-${s.estado}">
      <div class="aut-cab">
        <div>
          <h3><a href="#" data-aut-ver="${s.estudiante_id}">${esc(s.estudiante_nombre)}</a></h3>
          <p class="aut-sub">${esc(s.estudiante_documento)} · ${esc(s.estudiante_grupo)} · año ${s.anio_lectivo}</p>
        </div>
        <span class="badge-estado ${estadoClase}">${icono(estadoIcono)}${estadoTxt}</span>
      </div>
      <div class="aut-grados">
        <span class="aut-grado">${esc(autNombreGrado(s.grado_actual))} (${s.grado_actual})</span>
        ${icono("arrow-right", "ico-tenue")}
        <span class="aut-grado aut-grado-destino">${esc(autNombreGrado(s.grado_destino))} (${s.grado_destino})</span>
        <span class="aut-motivos">${s.motivos.map((m) => `<span class="aut-motivo">${esc(AUT_MOTIVOS[m] || m)}</span>`).join("")}</span>
      </div>
      ${s.materias_perdidas ? `<div class="aut-bloque"><h4>${s.materias_perdidas} materia${s.materias_perdidas === 1 ? "" : "s"} perdida${s.materias_perdidas === 1 ? "" : "s"} al pedir el permiso</h4>${materias}</div>` : ""}
      <div class="aut-bloque"><h4>Justificación</h4><blockquote class="prom-cita">${esc(s.justificacion)}</blockquote></div>
      <div class="aut-registro">
        <div>${icono("send")}<span>Pidió: <b>${esc(s.solicitado_por_nombre)}</b><br><span class="prom-tenue">${esc(autCuando(s.solicitado_en))}</span></span></div>
        ${
          s.decidido_por_nombre
            ? `<div>${icono(estadoIcono)}<span>${s.estado === "aprobada" ? "Aprobó" : "Rechazó"}: <b>${esc(s.decidido_por_nombre)}</b><br><span class="prom-tenue">${esc(autCuando(s.decidido_en))}</span>${s.nota_decision ? `<br>«${esc(s.nota_decision)}»` : ""}</span></div>`
            : ""
        }
        ${s.usada_en ? `<div>${icono("file-check")}<span>Ficha generada con este permiso<br><span class="prom-tenue">${esc(autCuando(s.usada_en))}</span></span></div>` : ""}
      </div>
      ${
        puedeDecidir
          ? `<div class="prom-decidir aut-bloque">
              <textarea data-aut-nota="${s.id}" rows="2" placeholder="Nota de la decisión (obligatoria para rechazar; la ve quien pidió el permiso)"></textarea>
              <div class="prom-form-acciones">
                <button type="button" class="boton" data-aut-decidir="${s.id}|1">${icono("shield-check")}Aprobar</button>
                <button type="button" class="boton secundario prom-boton-rechazar" data-aut-decidir="${s.id}|0">${icono("shield-x")}Rechazar</button>
              </div>
            </div>`
          : ""
      }
    </article>`;
}

async function renderAlertas() {
  app.innerHTML = "<p>Cargando autorizaciones...</p>";
  let solicitudes, pendientes, anteriores;
  try {
    [solicitudes, pendientes, anteriores] = await Promise.all([
      api(`/api/promocion/solicitudes?estado=${encodeURIComponent(autEstado)}`),
      autEstado === "pendiente" ? null : api("/api/promocion/solicitudes?estado=pendiente"),
      api("/api/alertas/promocion?estado=").catch(() => []),
    ]);
  } catch (e) {
    app.innerHTML = `<p class="alerta-caja">${
      e.status === 401 || e.status === 403 ? "No tienes permiso para ver las autorizaciones de promoción." : "No se pudieron cargar: " + esc(e.message)
    }</p>`;
    return;
  }
  const nPendientes = (pendientes || solicitudes).length;
  const f = normalizarTexto(autFiltro.trim());
  const visibles = solicitudes.filter((s) => !f || normalizarTexto(`${s.estudiante_nombre} ${s.estudiante_documento} ${s.solicitado_por_nombre}`).includes(f));

  app.innerHTML = `
    <header class="ox-cabecera">
      <div>
        <p class="dx-eyebrow">Coordinación</p>
        <h2>Autorizaciones de promoción</h2>
        <p class="subtitulo-pagina">Permisos para matricular a un estudiante en un grado fuera de la regla: subir con materias perdidas, saltar grados (lo normal es subir uno) o bajar de grado. Sin aprobación, la ficha de matrícula no se genera con ese grado.</p>
      </div>
    </header>
    ${
      !tienePermiso("promocion.autorizar")
        ? `<p class="dk-info-caja">${icono("info")} Puedes ver las solicitudes, pero aprobar o rechazar le corresponde a coordinación o administración.</p>`
        : ""
    }
    <div class="aut-filtros">
      ${orChips("aut-estado", [
        ["pendiente", `Pendientes`, nPendientes],
        ["aprobada", "Aprobadas"],
        ["rechazada", "Rechazadas"],
        ["anulada", "Retiradas"],
        ["", "Todas"],
      ], autEstado)}
      <div class="ox-buscador"><input type="search" data-aut-buscar placeholder="Buscar estudiante o quién pidió..." value="${esc(autFiltro)}" aria-label="Buscar" /></div>
    </div>
    ${
      visibles.length
        ? `<div class="aut-lista">${visibles.map(autTarjetaHtml).join("")}</div>`
        : `<div class="ox-vacio"><p>${autEstado === "pendiente" ? "No hay permisos esperando decisión." : "No hay solicitudes en este filtro."}</p></div>`
    }
    ${
      anteriores.length
        ? `<details class="seccion-colapsable aut-bloque"><summary>Avisos anteriores (sistema viejo, solo informaban) <span class="segmentado-num">${anteriores.length}</span></summary>
            <div class="tabla-scroll"><table>
              <thead><tr><th>Cuándo</th><th>Estudiante</th><th>Lo matriculó</th><th>Grado</th><th>Materias perdidas</th><th>Estado</th></tr></thead>
              <tbody>${anteriores
                .map(
                  (a) => `<tr><td>${esc(autCuando(a.creado_en))}</td><td>${esc(a.estudiante_nombre)}<br><small>${esc(a.estudiante_documento)}</small></td>
                    <td>${esc(a.usuario_nombre || "—")}</td><td>${esc(autNombreGrado(a.grado_actual))} → <strong>${esc(autNombreGrado(a.grado_destino))}</strong></td>
                    <td>${a.detalle.map((d) => `${esc(d.area)} (${Number(d.promedio).toFixed(2)})`).join("<br>")}</td>
                    <td>${a.estado === "atendida" ? `Atendida${a.atendida_por_nombre ? ` por ${esc(a.atendida_por_nombre)}` : ""}${a.nota_atencion ? `<br><small>${esc(a.nota_atencion)}</small>` : ""}` : "Pendiente"}</td></tr>`
                )
                .join("")}</tbody></table></div></details>`
        : ""
    }`;

  app.querySelectorAll("[data-aut-estado]").forEach((b) =>
    b.addEventListener("click", () => {
      autEstado = b.dataset.autEstado;
      renderAlertas();
    })
  );
  const buscador = app.querySelector("[data-aut-buscar]");
  buscador.addEventListener("change", () => {
    autFiltro = buscador.value;
    renderAlertas();
  });
  app.querySelectorAll("[data-aut-ver]").forEach((el) =>
    el.addEventListener("click", (ev) => {
      ev.preventDefault();
      abrirFicha(Number(el.dataset.autVer), "alertas");
    })
  );
  app.querySelectorAll("[data-aut-decidir]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const [id, aprobar] = btn.dataset.autDecidir.split("|");
      const nota = app.querySelector(`[data-aut-nota="${id}"]`)?.value || "";
      btn.disabled = true;
      try {
        await api(`/api/promocion/solicitudes/${id}/decidir`, { method: "POST", body: JSON.stringify({ aprobar: aprobar === "1", nota }) });
        orAviso(aprobar === "1" ? "Permiso aprobado. Ya se puede generar la ficha con ese grado." : "Permiso rechazado. Quien lo pidió verá el motivo en la ficha.");
        renderAlertas();
      } catch (e) {
        btn.disabled = false;
        orAviso(e.message || "No se pudo guardar la decisión.", "error");
      }
    })
  );
}
