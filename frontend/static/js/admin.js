// --- Vista: Usuarios (cuentas, roles y acceso) ------------------------------
//
// Consume los endpoints de /api/admin que ya existían desde la Fase 3 (ver
// backend/app/routers/admin.py). Ninguno es nuevo: antes esta pantalla solo
// usaba GET /usuarios y PUT /usuarios/{id}/roles, y todo lo demás había que
// hacerlo a mano con backend/crear_usuario.py.
//
// Permisos: /api/admin/* usa rbac.requiere(), o sea que BLOQUEA de verdad
// (403), a diferencia de las rutas de negocio que solo observan. Aquí se
// ocultan las acciones que el usuario no puede hacer — eso es UX, no
// seguridad: quien decide sigue siendo el backend.

let adminUsuariosCache = null;
let adminRolesCache = [];
let adminBusqueda = "";
let adminFiltroEstado = "todos"; // todos | activo | inactivo
let adminFiltroRol = ""; // "" = todos
let adminFiltroSenal = ""; // "" | nunca_entro | clave_pendiente
let adminAviso = null; // { tipo: "exito"|"error", texto } a mostrar tras re-renderizar

// Señales operativas reales que el backend ya envía en UsuarioAdminResumen y
// que la tabla anterior descartaba.
const SENALES_USUARIO = [
  { id: "nunca_entro", nombre: "Nunca han entrado", prueba: (u) => !u.ultimo_acceso },
  { id: "clave_pendiente", nombre: "Clave sin cambiar", prueba: (u) => u.debe_cambiar_clave },
];

function nombreRol(codigo) {
  return (adminRolesCache.find((r) => r.codigo === codigo) || {}).nombre || codigo;
}

function rolesDeUsuarioHtml(u) {
  if (!u.roles.length) return '<span class="pendiente">Sin rol</span>';
  return u.roles.map((c) => `<span class="badge-rol">${esc(nombreRol(c))}</span>`).join(" ");
}

// "hace 3 días" / "hace 2 h" a partir del instante UTC que manda la API.
function haceCuanto(texto) {
  const fecha = instanteUtcDesdeApi(texto);
  if (!fecha) return null;
  const segundos = Math.round((Date.now() - fecha.getTime()) / 1000);
  if (segundos < 60) return "hace un momento";
  const minutos = Math.round(segundos / 60);
  if (minutos < 60) return `hace ${minutos} min`;
  const horas = Math.round(minutos / 60);
  if (horas < 24) return `hace ${horas} h`;
  const dias = Math.round(horas / 24);
  if (dias < 30) return `hace ${dias} día${dias === 1 ? "" : "s"}`;
  const meses = Math.round(dias / 30);
  if (meses < 12) return `hace ${meses} mes${meses === 1 ? "" : "es"}`;
  return `hace ${Math.round(meses / 12)} año(s)`;
}

function usuariosFiltrados() {
  const q = normalizarTexto(adminBusqueda.trim());
  return (adminUsuariosCache || []).filter((u) => {
    if (adminFiltroEstado !== "todos" && u.estado !== adminFiltroEstado) return false;
    if (adminFiltroRol && !u.roles.includes(adminFiltroRol)) return false;
    const senal = SENALES_USUARIO.find((s) => s.id === adminFiltroSenal);
    if (senal && !senal.prueba(u)) return false;
    if (!q) return true;
    return (
      normalizarTexto(u.nombre).includes(q) ||
      normalizarTexto(u.documento).includes(q) ||
      normalizarTexto(u.email).includes(q)
    );
  });
}

async function renderAdmin() {
  app.innerHTML = '<p class="estado-carga">Cargando usuarios...</p>';
  try {
    adminUsuariosCache = await api("/api/admin/usuarios");
  } catch (e) {
    app.innerHTML = `<div class="alerta-caja">${
      e.status === 401 || e.status === 403
        ? "No tienes permiso para ver esta sección."
        : "No se pudo cargar la lista de usuarios: " + esc(e.message)
    }</div>`;
    return;
  }
  // Los roles necesitan su propio permiso (roles.ver). Si falta, la pantalla
  // sigue siendo útil: se muestran los códigos de rol tal cual, en vez de
  // tumbar la vista entera como hacía el Promise.all anterior.
  try {
    adminRolesCache = await api("/api/admin/roles");
  } catch {
    adminRolesCache = [];
  }

  app.innerHTML = adminHtml();
  vincularAdmin();
}

function adminResumenHtml() {
  const todos = adminUsuariosCache || [];
  const activos = todos.filter((u) => u.estado === "activo").length;
  const nunca = todos.filter((u) => !u.ultimo_acceso).length;
  const clave = todos.filter((u) => u.debe_cambiar_clave).length;
  return `
    <div class="resumen-reportes resumen-compacta">
      <div class="metric-card"><span>Usuarios</span><strong>${todos.length}</strong></div>
      <div class="metric-card ok"><span>Activos</span><strong>${activos}</strong></div>
      <div class="metric-card ${nunca ? "alerta" : "ok"}"><span>Nunca han entrado</span><strong>${nunca}</strong></div>
      <div class="metric-card ${clave ? "alerta" : "ok"}"><span>Clave sin cambiar</span><strong>${clave}</strong></div>
    </div>`;
}

// --- Módulos del sistema: apagar/prender Orientación (ej. entre años) ------
function adminModulosHtml() {
  const on = modulosSistema.orientacion !== false;
  const cambio = modulosSistema.orientacion_cambiado_por
    ? `Último cambio: ${esc(modulosSistema.orientacion_cambiado_por)}, ${esc(instanteUtcDesdeApi(modulosSistema.orientacion_cambiado_en)?.toLocaleString("es-CO") || "")}.`
    : "";
  return `
    <section class="adm-modulos">
      <h3>${icono("settings")}Módulos del sistema</h3>
      <div class="adm-modulo">
        <div>
          <strong>Orientación y seguimiento</strong>
          <p>Bandeja, diagnóstico por grado, perfil por estudiante y casos. ${
            on
              ? "Está <b>activo</b>."
              : "Está <b>desactivado</b>: no aparece en el menú de nadie y los docentes no pueden enviar remisiones a psicología."
          } Desactivarlo no borra nada; al activarlo todo vuelve igual. ${cambio}</p>
        </div>
        <button type="button" class="adm-interruptor${on ? " on" : ""}" role="switch" aria-checked="${on}" id="adm-toggle-orientacion">
          <span class="adm-interruptor-bola"></span><span class="adm-interruptor-texto">${on ? "Activo" : "Desactivado"}</span>
        </button>
      </div>
    </section>`;
}

function adminHtml() {
  const todos = adminUsuariosCache || [];
  const cuenta = (estado) => (estado === "todos" ? todos.length : todos.filter((u) => u.estado === estado).length);
  const filtrados = usuariosFiltrados();

  return `
    <div class="pagina-header">
      <div>
        <h1>Usuarios</h1>
        <p class="subtitulo-pagina">Cuentas, roles y acceso al sistema.</p>
      </div>
      ${
        tienePermiso("usuarios.crear")
          ? '<button type="button" class="boton" id="btn-nuevo-usuario">+ Nuevo usuario</button>'
          : ""
      }
    </div>

    ${adminResumenHtml()}

    ${tienePermiso("configuracion.gestionar") ? adminModulosHtml() : ""}

    <div class="buscador-principal">
      <span class="buscador-principal-icono" aria-hidden="true"><i data-lucide=search class=ico></i> </span>
      <input type="text" id="buscar-usuario" placeholder="Buscar por nombre, documento o correo..." value="${esc(adminBusqueda)}" />
    </div>

    <div class="barra-filtros">
      <div class="segmentado" role="group" aria-label="Estado de la cuenta">
        ${["todos", "activo", "inactivo"]
          .map(
            (e) => `<button type="button" class="segmentado-btn ${adminFiltroEstado === e ? "activo" : ""}" data-filtro-estado="${e}">
                      ${e === "todos" ? "Todos" : e === "activo" ? "Activos" : "Inactivos"}
                      <span class="segmentado-num">${cuenta(e)}</span>
                    </button>`
          )
          .join("")}
      </div>
      <label class="filtro-campo">Rol
        <select id="filtro-rol">
          <option value="">Todos los roles</option>
          ${adminRolesCache
            .map(
              (r) => `<option value="${esc(r.codigo)}" ${r.codigo === adminFiltroRol ? "selected" : ""}>
                        ${esc(r.nombre)} (${r.total_usuarios})
                      </option>`
            )
            .join("")}
        </select>
      </label>
      <label class="filtro-campo">Señal
        <select id="filtro-senal">
          <option value="">Sin filtro</option>
          ${SENALES_USUARIO.map(
            (s) => `<option value="${s.id}" ${s.id === adminFiltroSenal ? "selected" : ""}>
                      ${s.nombre} (${(adminUsuariosCache || []).filter(s.prueba).length})
                    </option>`
          ).join("")}
        </select>
      </label>
      ${
        adminBusqueda || adminFiltroEstado !== "todos" || adminFiltroRol || adminFiltroSenal
          ? '<button type="button" class="boton-texto-chico" id="limpiar-filtros-usuarios">Limpiar filtros</button>'
          : ""
      }
    </div>

    <div id="admin-aviso">${
      adminAviso ? `<div class="${adminAviso.tipo === "error" ? "alerta-caja" : "exito-caja"}">${esc(adminAviso.texto)}</div>` : ""
    }</div>

    <div class="panel-tabla-header">
      <span class="conteo-resultados" id="conteo-usuarios">${filtrados.length} de ${todos.length} usuario(s)</span>
    </div>
    <div id="lista-usuarios">${tablaUsuariosHtml(filtrados)}</div>
  `;
}

// El menú ⋮ de un usuario llega a 6 acciones (~240px): con 6 filas o menos no hay
// sitio para abrirlo hacia arriba ni hacia abajo dentro del contenedor, así que
// se reserva espacio debajo (ver .tabla-corta-alta en style.css).
function tablaUsuariosHtml(usuarios) {
  if (!usuarios.length) {
    return `
      <div class="estado-vacio">
        <div class="estado-vacio-icono" aria-hidden="true"><i data-lucide=search class=ico></i> </div>
        <h3>No encontramos usuarios</h3>
        <p>Prueba cambiando los filtros o realizando otra búsqueda.</p>
      </div>`;
  }
  return `
    <div class="tabla-scroll ${usuarios.length <= 6 ? "tabla-corta tabla-corta-alta" : ""}">
      <table class="tabla-usuarios">
        <thead>
          <tr>
            <th>Usuario</th>
            <th>Documento</th>
            <th>Rol</th>
            <th>Estado</th>
            <th>Último acceso</th>
            <th class="col-acciones"><span class="sr-only">Acciones</span></th>
          </tr>
        </thead>
        <tbody>${usuarios.map(filaUsuario).join("")}</tbody>
      </table>
    </div>`;
}

function filaUsuario(u) {
  const relativo = haceCuanto(u.ultimo_acceso);
  const exacto = instanteUtcDesdeApi(u.ultimo_acceso);
  const acceso = relativo
    ? `<span title="${esc(exacto.toLocaleString("es-CO"))}">${esc(relativo)}</span>`
    : '<span class="pendiente">Nunca</span>';
  const yoMismo = typeof sesionActual !== "undefined" && sesionActual?.usuario?.id === u.id;

  return `
    <tr data-id="${u.id}">
      <td>
        <div class="celda-estudiante">
          <span class="avatar-iniciales" aria-hidden="true">${esc(inicialesDe(u.nombre))}</span>
          <div>
            <div class="nombre-estudiante">${esc(u.nombre)}${yoMismo ? ' <span class="badge-rol tenue">tú</span>' : ""}</div>
            <div class="doc-estudiante">${esc(u.email || "sin correo")}${
              u.docente_id ? " · docente" : ""
            }</div>
          </div>
        </div>
      </td>
      <td>${esc(u.documento)}</td>
      <td>${rolesDeUsuarioHtml(u)}</td>
      <td>
        <span class="badge ${u.estado === "activo" ? "activo" : "inactivo"}">${esc(u.estado)}</span>
        ${u.debe_cambiar_clave ? '<div class="marca-fila">clave sin cambiar</div>' : ""}
      </td>
      <td>
        ${acceso}
        ${u.sesiones_activas ? `<div class="marca-fila">${u.sesiones_activas} sesión(es) activa(s)</div>` : ""}
      </td>
      <td class="col-acciones">${menuUsuarioHtml(u, yoMismo)}</td>
    </tr>`;
}

// Cada acción se oculta si al usuario le falta el permiso. El backend vuelve
// a comprobarlo igual (403): esto solo evita ofrecer lo que no se puede.
function menuUsuarioHtml(u, yoMismo) {
  const items = [`<button type="button" class="item-menu" data-usuario-ver="${u.id}">Ver detalles</button>`];
  if (tienePermiso("usuarios.roles") && adminRolesCache.length)
    items.push(`<button type="button" class="item-menu" data-usuario-rol="${u.id}">Cambiar rol</button>`);
  if (tienePermiso("usuarios.editar"))
    items.push(`<button type="button" class="item-menu" data-usuario-editar="${u.id}">Editar datos</button>`);
  if (tienePermiso("usuarios.estado") && !yoMismo)
    items.push(
      `<button type="button" class="item-menu" data-usuario-estado="${u.id}" data-nuevo-estado="${
        u.estado === "activo" ? "inactivo" : "activo"
      }">${u.estado === "activo" ? "Desactivar cuenta" : "Activar cuenta"}</button>`
    );
  if (tienePermiso("usuarios.restablecer_clave"))
    items.push(`<button type="button" class="item-menu" data-usuario-clave="${u.id}">Restablecer contraseña</button>`);
  if (tienePermiso("sesiones.revocar") && u.sesiones_activas)
    items.push(`<button type="button" class="item-menu" data-usuario-revocar="${u.id}">Cerrar sus sesiones</button>`);

  return `
    <details class="menu-fila">
      <summary class="boton-icono" aria-label="Acciones de ${esc(u.nombre)}" title="Acciones">⋮</summary>
      <div class="menu-herramientas-lista">${items.join("")}</div>
    </details>`;
}

// --- Modales ----------------------------------------------------------------
// Mismo patrón que ya usan Boletines y Horarios: se monta el .modal-fondo en
// un contenedor y se quita al cerrar.

function montarModal(titulo, cuerpoHtml, pieHtml) {
  cerrarModalAdmin();
  const cont = document.createElement("div");
  cont.id = "modal-admin";
  cont.innerHTML = `
    <div class="modal-fondo">
      <div class="modal-caja modal-caja-ancha">
        <header class="est-modal-head">
          <h3>${titulo}</h3>
          <button type="button" class="est-visor-cerrar" data-cerrar-modal-admin aria-label="Cerrar"></button>
        </header>
        <div class="modal-cuerpo">${cuerpoHtml}</div>
        ${pieHtml ? `<div class="modal-acciones">${pieHtml}</div>` : ""}
      </div>
    </div>`;
  document.body.appendChild(cont);
  cont.querySelectorAll("[data-cerrar-modal-admin]").forEach((b) => b.addEventListener("click", cerrarModalAdmin));
  cont.querySelector(".modal-fondo").addEventListener("click", (ev) => {
    if (ev.target.classList.contains("modal-fondo")) cerrarModalAdmin();
  });
  return cont;
}

function cerrarModalAdmin() {
  document.getElementById("modal-admin")?.remove();
}

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") cerrarModalAdmin();
});

// Tras una acción correcta: recarga la lista y deja el aviso arriba.
async function trasAccionAdmin(texto) {
  adminAviso = { tipo: "exito", texto };
  cerrarModalAdmin();
  await renderAdmin();
}

function errorEnModal(cont, mensaje) {
  const caja = cont.querySelector(".modal-error");
  if (caja) caja.innerHTML = `<div class="alerta-caja">${esc(mensaje)}</div>`;
  else alert(mensaje);
}

// --- Acciones ---------------------------------------------------------------

async function abrirDetalleUsuario(id) {
  const cont = montarModal("Detalle del usuario", '<p class="estado-carga">Cargando...</p>');
  let u;
  try {
    u = await api(`/api/admin/usuarios/${id}`);
  } catch (e) {
    cont.querySelector(".modal-cuerpo").innerHTML = `<div class="alerta-caja">${esc(e.message)}</div>`;
    return;
  }
  let sesiones = null;
  if (tienePermiso("sesiones.ver")) {
    try {
      sesiones = await api(`/api/admin/usuarios/${id}/sesiones`);
    } catch {
      sesiones = null;
    }
  }
  const acceso = haceCuanto(u.ultimo_acceso);
  const creado = instanteUtcDesdeApi(u.creado_en);
  const filas = [
    ["Nombre", esc(u.nombre)],
    ["Documento", esc(u.documento)],
    ["Correo", esc(u.email || "—")],
    ["Rol", rolesDeUsuarioHtml(u)],
    ["Estado", `<span class="badge ${u.estado === "activo" ? "activo" : "inactivo"}">${esc(u.estado)}</span>`],
    ["Debe cambiar la clave", u.debe_cambiar_clave ? "Sí" : "No"],
    ["Último acceso", acceso ? esc(acceso) : "Nunca"],
    ["Creado", creado ? esc(creado.toLocaleDateString("es-CO")) : "—"],
    ["Sesiones activas", String(u.sesiones_activas)],
    ["Enlazado a docente", u.docente_id ? `Sí (#${u.docente_id})` : "No"],
    // usuario_sedes: [] significa "sin restricción" (ver schemas.py:696).
    ["Alcance por sede", u.sedes.length ? `${u.sedes.length} sede(s) asignada(s)` : "Todas las sedes"],
  ];

  let sesionesHtml = "";
  if (sesiones && sesiones.length) {
    sesionesHtml = `
      <p class="est-subtitulo-mini">Sesiones abiertas</p>
      <div class="tabla-scroll">
        <table>
          <thead><tr><th>Dispositivo</th><th>Último uso</th><th>IP</th></tr></thead>
          <tbody>
            ${sesiones
              .map(
                (s) => `<tr>
                  <td>${esc(s.dispositivo_nombre || "—")}${s.confiable ? ' <span class="badge-rol tenue">de confianza</span>' : ""}</td>
                  <td>${esc(haceCuanto(s.ultimo_uso) || "—")}</td>
                  <td>${esc(s.ip || "—")}</td>
                </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>`;
  } else if (sesiones) {
    sesionesHtml = '<p class="est-subtitulo-mini">Sesiones abiertas</p><p class="pendiente est-vacio-linea">No tiene sesiones abiertas.</p>';
  }

  cont.querySelector(".modal-cuerpo").innerHTML = `
    <dl class="est-dl">${filas.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join("")}</dl>
    ${sesionesHtml}`;
}

function abrirCambiarRol(id) {
  const u = adminUsuariosCache.find((x) => x.id === id);
  const actual = u.roles[0] || "";
  const cont = montarModal(
    "Cambiar rol",
    `<p class="est-bloque-desc">Usuario: <strong>${esc(u.nombre)}</strong> · ${esc(u.documento)}</p>
     <div class="modal-error"></div>
     <div class="lista-opciones-rol">
       ${adminRolesCache
         .map(
           (r) => `<label class="opcion-rol">
             <input type="radio" name="rol-nuevo" value="${esc(r.codigo)}" ${r.codigo === actual ? "checked" : ""} />
             <span>
               <strong>${esc(r.nombre)}</strong>
               <small>${esc(r.descripcion || "")} · ${r.total_permisos} permiso(s) · ${r.total_usuarios} usuario(s)</small>
             </span>
           </label>`
         )
         .join("")}
     </div>`,
    `<button type="button" class="boton secundario" data-cerrar-modal-admin>Cancelar</button>
     <button type="button" class="boton" id="btn-confirmar-rol">Guardar rol</button>`
  );
  cont.querySelectorAll("[data-cerrar-modal-admin]").forEach((b) => b.addEventListener("click", cerrarModalAdmin));
  cont.querySelector("#btn-confirmar-rol").addEventListener("click", async (ev) => {
    const elegido = cont.querySelector('input[name="rol-nuevo"]:checked')?.value;
    if (!elegido) return errorEnModal(cont, "Elige un rol.");
    ev.target.disabled = true;
    try {
      await api(`/api/admin/usuarios/${id}/roles`, { method: "PUT", body: JSON.stringify({ roles: [elegido] }) });
      await trasAccionAdmin(`Rol de ${u.nombre} cambiado a "${nombreRol(elegido)}".`);
    } catch (e) {
      ev.target.disabled = false;
      errorEnModal(cont, e.message);
    }
  });
}

function abrirEditarUsuario(id) {
  const u = adminUsuariosCache.find((x) => x.id === id);
  const cont = montarModal(
    "Editar datos",
    `<div class="modal-error"></div>
     <form class="form-grid form-grid-bloque" id="form-editar-usuario">
       <label class="ancho-completo">Nombre
         <input type="text" name="nombre" value="${esc(u.nombre)}" required />
       </label>
       <label>Documento
         <input type="text" name="documento" value="${esc(u.documento)}" required />
       </label>
       <label>Correo
         <input type="email" name="email" value="${esc(u.email || "")}" placeholder="opcional" />
       </label>
     </form>`,
    `<button type="button" class="boton secundario" data-cerrar-modal-admin>Cancelar</button>
     <button type="button" class="boton" id="btn-guardar-usuario">Guardar</button>`
  );
  cont.querySelectorAll("[data-cerrar-modal-admin]").forEach((b) => b.addEventListener("click", cerrarModalAdmin));
  cont.querySelector("#btn-guardar-usuario").addEventListener("click", async (ev) => {
    const d = Object.fromEntries(new FormData(cont.querySelector("#form-editar-usuario")).entries());
    if (!d.nombre.trim() || !d.documento.trim()) return errorEnModal(cont, "El nombre y el documento son obligatorios.");
    ev.target.disabled = true;
    try {
      await api(`/api/admin/usuarios/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ nombre: d.nombre, documento: d.documento, email: d.email || null }),
      });
      await trasAccionAdmin("Datos actualizados.");
    } catch (e) {
      ev.target.disabled = false;
      errorEnModal(cont, e.message);
    }
  });
}

function abrirNuevoUsuario() {
  const cont = montarModal(
    "Nuevo usuario",
    `<div class="modal-error"></div>
     <p class="est-bloque-desc">Se genera una contraseña temporal que deberá cambiar al entrar por primera vez.</p>
     <form class="form-grid form-grid-bloque" id="form-nuevo-usuario">
       <label class="ancho-completo">Nombre completo
         <input type="text" name="nombre" required />
       </label>
       <label>Documento
         <input type="text" name="documento" required />
       </label>
       <label>Correo
         <input type="email" name="email" placeholder="opcional" />
       </label>
       <label class="ancho-completo">Rol
         <select name="rol">
           <option value="">Sin rol</option>
           ${adminRolesCache.map((r) => `<option value="${esc(r.codigo)}">${esc(r.nombre)}</option>`).join("")}
         </select>
       </label>
     </form>`,
    `<button type="button" class="boton secundario" data-cerrar-modal-admin>Cancelar</button>
     <button type="button" class="boton" id="btn-crear-usuario">Crear usuario</button>`
  );
  cont.querySelectorAll("[data-cerrar-modal-admin]").forEach((b) => b.addEventListener("click", cerrarModalAdmin));
  cont.querySelector("#btn-crear-usuario").addEventListener("click", async (ev) => {
    const d = Object.fromEntries(new FormData(cont.querySelector("#form-nuevo-usuario")).entries());
    if (!d.nombre.trim() || !d.documento.trim()) return errorEnModal(cont, "El nombre y el documento son obligatorios.");
    ev.target.disabled = true;
    try {
      const creado = await api("/api/admin/usuarios", {
        method: "POST",
        body: JSON.stringify({
          documento: d.documento,
          nombre: d.nombre,
          email: d.email || null,
          roles: d.rol ? [d.rol] : [],
        }),
      });
      adminUsuariosCache = await api("/api/admin/usuarios");
      mostrarClaveTemporal(creado.usuario.nombre, creado.clave_temporal, "Usuario creado");
    } catch (e) {
      ev.target.disabled = false;
      errorEnModal(cont, e.message);
    }
  });
}

// La clave temporal solo llega UNA vez en la respuesta: se muestra en grande
// y la pantalla no se recarga hasta que la persona la cierra a propósito.
function mostrarClaveTemporal(nombre, clave, titulo) {
  const cont = montarModal(
    titulo,
    `<p class="est-bloque-desc">Contraseña temporal de <strong>${esc(nombre)}</strong>.
       Entrégasela en persona: <strong>no se puede volver a consultar</strong>. Deberá cambiarla al entrar.</p>
     <div class="clave-temporal"><code>${esc(clave)}</code>
       <button type="button" class="boton secundario boton-chico" id="btn-copiar-clave">Copiar</button>
     </div>`,
    '<button type="button" class="boton" id="btn-cerrar-clave">Entendido</button>'
  );
  cont.querySelector("#btn-copiar-clave").addEventListener("click", async (ev) => {
    try {
      await navigator.clipboard.writeText(clave);
      ev.target.textContent = "Copiada";
    } catch {
      ev.target.textContent = "Cópiala a mano";
    }
  });
  cont.querySelector("#btn-cerrar-clave").addEventListener("click", () => trasAccionAdmin(`${titulo}: ${nombre}.`));
}

async function cambiarEstadoUsuario(id, nuevoEstado) {
  const u = adminUsuariosCache.find((x) => x.id === id);
  const verbo = nuevoEstado === "activo" ? "activar" : "desactivar";
  if (!confirm(`¿${verbo[0].toUpperCase() + verbo.slice(1)} la cuenta de ${u.nombre}?`)) return;
  try {
    await api(`/api/admin/usuarios/${id}/estado`, { method: "POST", body: JSON.stringify({ estado: nuevoEstado }) });
    await trasAccionAdmin(`Cuenta de ${u.nombre} ${nuevoEstado === "activo" ? "activada" : "desactivada"}.`);
  } catch (e) {
    // El backend impide dejar el sistema sin quien gestione roles/usuarios
    // (409) y desactivarte a ti mismo (400): se muestra su mensaje tal cual.
    adminAviso = { tipo: "error", texto: e.message };
    await renderAdmin();
  }
}

async function restablecerClaveUsuario(id) {
  const u = adminUsuariosCache.find((x) => x.id === id);
  if (!confirm(`¿Restablecer la contraseña de ${u.nombre}? La actual dejará de servir.`)) return;
  try {
    const r = await api(`/api/admin/usuarios/${id}/restablecer-clave`, { method: "POST" });
    mostrarClaveTemporal(u.nombre, r.clave_temporal, "Contraseña restablecida");
  } catch (e) {
    adminAviso = { tipo: "error", texto: e.message };
    await renderAdmin();
  }
}

async function revocarSesionesUsuario(id) {
  const u = adminUsuariosCache.find((x) => x.id === id);
  if (!confirm(`¿Cerrar todas las sesiones de ${u.nombre}? Tendrá que volver a entrar.`)) return;
  try {
    const r = await api(`/api/admin/usuarios/${id}/revocar-sesiones`, { method: "POST" });
    await trasAccionAdmin(`Se cerraron ${r.sesiones_cerradas} sesión(es) de ${u.nombre}.`);
  } catch (e) {
    adminAviso = { tipo: "error", texto: e.message };
    await renderAdmin();
  }
}

// --- Enlazado ---------------------------------------------------------------

// Solo repinta la tabla y su contador: al escribir en el buscador no se
// reconstruye la pantalla entera ni se pierde el foco del input.
function refrescarListaUsuarios() {
  const filtrados = usuariosFiltrados();
  document.getElementById("lista-usuarios").innerHTML = tablaUsuariosHtml(filtrados);
  document.getElementById("conteo-usuarios").textContent =
    `${filtrados.length} de ${(adminUsuariosCache || []).length} usuario(s)`;
  vincularFilasUsuarios();
}

function vincularAdmin() {
  adminAviso = null;

  document.getElementById("adm-toggle-orientacion")?.addEventListener("click", async (ev) => {
    const btn = ev.currentTarget;
    const activar = modulosSistema.orientacion === false;
    if (!activar && !confirm("¿Desactivar Orientación? Se oculta del menú para todos y los docentes no podrán enviar remisiones a psicología. No se borra nada.")) return;
    btn.disabled = true;
    try {
      modulosSistema = await api("/api/sistema/modulos/orientacion", { method: "PUT", body: JSON.stringify({ activo: activar }) });
      _aplicarVisibilidadPorPermisos(sesionActual.usuario.permisos);
      orAviso(activar ? "Orientación activada." : "Orientación desactivada.");
      renderAdmin();
    } catch (e) {
      btn.disabled = false;
      orAviso(e.message || "No se pudo cambiar.", "error");
    }
  });

  const buscador = document.getElementById("buscar-usuario");
  buscador.addEventListener("input", (e) => {
    adminBusqueda = e.target.value;
    refrescarListaUsuarios();
  });

  document.querySelectorAll("[data-filtro-estado]").forEach((btn) => {
    btn.addEventListener("click", () => {
      adminFiltroEstado = btn.dataset.filtroEstado;
      renderAdmin();
    });
  });
  document.getElementById("filtro-rol")?.addEventListener("change", (e) => {
    adminFiltroRol = e.target.value;
    renderAdmin();
  });
  document.getElementById("filtro-senal")?.addEventListener("change", (e) => {
    adminFiltroSenal = e.target.value;
    renderAdmin();
  });
  document.getElementById("limpiar-filtros-usuarios")?.addEventListener("click", () => {
    adminBusqueda = "";
    adminFiltroEstado = "todos";
    adminFiltroRol = "";
    adminFiltroSenal = "";
    renderAdmin();
  });
  document.getElementById("btn-nuevo-usuario")?.addEventListener("click", abrirNuevoUsuario);

  vincularFilasUsuarios();
}

function vincularFilasUsuarios() {
  const acciones = [
    ["usuarioVer", (id) => abrirDetalleUsuario(id)],
    ["usuarioRol", (id) => abrirCambiarRol(id)],
    ["usuarioEditar", (id) => abrirEditarUsuario(id)],
    ["usuarioClave", (id) => restablecerClaveUsuario(id)],
    ["usuarioRevocar", (id) => revocarSesionesUsuario(id)],
  ];
  for (const [clave, fn] of acciones) {
    document.querySelectorAll(`[data-${clave.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase())}]`).forEach((btn) => {
      btn.addEventListener("click", () => fn(Number(btn.dataset[clave])));
    });
  }
  document.querySelectorAll("[data-usuario-estado]").forEach((btn) => {
    btn.addEventListener("click", () => cambiarEstadoUsuario(Number(btn.dataset.usuarioEstado), btn.dataset.nuevoEstado));
  });
}
