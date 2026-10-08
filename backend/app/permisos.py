"""Catálogo de permisos y matriz inicial de roles del sistema (Fase 3: RBAC).

Los CÓDIGOS de permiso viven AQUÍ, en código: un endpoint que cite un código
que no esté en `CATALOGO` hace fallar el arranque (ver `rbac.requiere`), no
falla en producción frente a un usuario. La ASIGNACIÓN rol → permiso vive en
la base de datos (tabla `rol_permisos`) y la edita el administrador desde la
consola de administración; `MATRIZ_INICIAL` de abajo es solo la semilla que
se siembra la PRIMERA vez que cada rol se crea — después de eso, lo que el
administrador decida manda, y un reinicio del servidor nunca lo revierte
(ver `migraciones.sembrar_roles_sistema`).

Convención de nombres: `<módulo>.<acción>`, en español para que combine con
el resto del código. Cada permiso trae:
  · `sensible`: se muestra marcado en la pantalla de roles y ningún ROL NUEVO
    (creado por el administrador) lo recibe por defecto.
  · `fase`: en qué fase se activa de verdad. Los de fase "asistencia",
    "observaciones", "alertas" y "sistema" se declaran ya para poder armar
    los 5 roles completos desde ahora, aunque esos módulos lleguen después;
    hoy no los exige ningún endpoint.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DefinicionPermiso:
    codigo: str
    modulo: str
    descripcion: str
    sensible: bool = False
    fase: str = "actual"  # actual | asistencia | observaciones | alertas | sistema


CATALOGO: list[DefinicionPermiso] = [
    # --- Usuarios --------------------------------------------------------
    DefinicionPermiso("usuarios.ver", "usuarios", "Ver la lista de usuarios y su detalle"),
    DefinicionPermiso("usuarios.crear", "usuarios", "Crear usuarios nuevos"),
    DefinicionPermiso("usuarios.editar", "usuarios", "Editar nombre, correo y enlace con docente"),
    DefinicionPermiso("usuarios.estado", "usuarios", "Activar o desactivar una cuenta"),
    DefinicionPermiso("usuarios.restablecer_clave", "usuarios", "Restablecer la contraseña de otro usuario", sensible=True),
    DefinicionPermiso("usuarios.roles", "usuarios", "Asignar o quitar roles a un usuario", sensible=True),
    # Permiso separado de usuarios.roles a pedido explícito (aprobación Fase
    # 3, punto 3): administrar A QUÉ ROL puede aspirar alguien es una
    # decisión distinta de administrar SOBRE QUÉ SEDES trabaja un usuario ya
    # asignado. Separarlos permite, por ejemplo, delegar en una coordinación
    # regional el ajuste de sedes de los coordinadores sin darle además la
    # capacidad de ascender a nadie a Administrador.
    DefinicionPermiso("usuarios.sedes", "usuarios", "Asignar el alcance por sede de un usuario (usuario_sedes)", sensible=True),

    # --- Roles y permisos --------------------------------------------------
    DefinicionPermiso("roles.ver", "roles", "Ver los roles y qué permisos tiene cada uno"),
    DefinicionPermiso("roles.gestionar", "roles", "Crear roles y activar/desactivar sus permisos", sensible=True),

    # --- Sesiones -----------------------------------------------------------
    DefinicionPermiso("sesiones.ver", "sesiones", "Ver las sesiones/dispositivos de cualquier usuario"),
    DefinicionPermiso("sesiones.revocar", "sesiones", "Cerrar la sesión de cualquier usuario", sensible=True),

    # --- Estudiantes --------------------------------------------------------
    DefinicionPermiso("estudiantes.ver", "estudiantes", "Ver el listado y la ficha del estudiante"),
    DefinicionPermiso("estudiantes.crear", "estudiantes", "Matricular estudiantes"),
    DefinicionPermiso("estudiantes.editar", "estudiantes", "Editar los datos del estudiante"),
    DefinicionPermiso("estudiantes.eliminar", "estudiantes", "Eliminar un estudiante", sensible=True),
    DefinicionPermiso("estudiantes.ver_documentos", "estudiantes", "Ver/descargar documentos escaneados (cédula, matrícula...)", sensible=True),
    DefinicionPermiso("estudiantes.documentos_gestionar", "estudiantes", "Subir o eliminar documentos escaneados", sensible=True),
    # Decisión del colegio (22/09/2026): el director de grupo (AsignacionDocente
    # con area_id IS NULL) puede ver y editar la ficha de matrícula completa de
    # los estudiantes de su propio grupo, sin necesitar estudiantes.editar (que
    # da acceso a TODA la institución). El backend re-valida "es director de
    # ESE grupo" en cada petición (ver crud.docente_es_director_del_grupo);
    # este permiso solo habilita que el docente pueda intentarlo.
    DefinicionPermiso("estudiantes.editar_ficha_grupo", "estudiantes", "Editar la ficha de matrícula de su propio grupo (solo director de grupo)", sensible=True),

    # --- Catálogos y académico ------------------------------------------
    DefinicionPermiso("sedes.ver", "catalogos", "Ver las sedes"),
    DefinicionPermiso("catalogos.ver", "catalogos", "Ver áreas, grados y demás catálogos"),
    DefinicionPermiso("catalogos.gestionar", "catalogos", "Editar sedes, áreas y catálogos"),
    DefinicionPermiso("docentes.ver", "academico", "Ver el listado de docentes"),
    DefinicionPermiso("docentes.gestionar", "academico", "Editar datos de docentes"),
    DefinicionPermiso("docentes.evaluar", "academico", "Ver la evaluación de rendimiento por docente (indicadores, semáforo y puntos de atención)", sensible=True),
    DefinicionPermiso("grupos.ver", "academico", "Ver los grupos y sus asignaciones"),
    DefinicionPermiso("grupos.gestionar", "academico", "Asignar docentes a grupos"),

    # --- Horarios --------------------------------------------------------
    DefinicionPermiso("horario.ver", "horario", "Consultar la rejilla de horarios"),
    DefinicionPermiso("horario.gestionar", "horario", "Editar bloques, ausencias y reemplazos"),
    DefinicionPermiso("horario.exportar", "horario", "Exportar el reporte de horario en Word"),

    # --- Boletines y notas -------------------------------------------------
    DefinicionPermiso("boletines.ver", "boletines", "Consultar pendientes, notas y reportes de boletines"),
    DefinicionPermiso("boletines.gestionar", "boletines", "Gestionar pendientes y revisiones de boletines"),
    DefinicionPermiso("boletines.exportar", "boletines", "Exportar boletines/notas a Excel"),
    DefinicionPermiso("sapred.importar", "boletines", "Importar PDF de SAPRED a mano", sensible=True),
    DefinicionPermiso("sapred.ejecutar", "boletines", "Ejecutar la automatización de SAPRED (Playwright)", sensible=True),

    # --- Constancias ---------------------------------------------------------
    DefinicionPermiso("constancias.ver", "constancias", "Ver el registro de constancias generadas"),
    DefinicionPermiso("constancias.generar", "constancias", "Generar una constancia nueva"),

    # --- Reportes --------------------------------------------------------
    DefinicionPermiso("reportes.ver", "reportes", "Ver reportes (sedes, conciliación SIMAC/SAPRED)"),
    DefinicionPermiso("reportes.exportar", "reportes", "Exportar reportes a Excel"),

    # --- Asistencia (el módulo llega en una fase posterior) ------------------
    DefinicionPermiso("asistencia.registrar", "asistencia", "Registrar la asistencia de sus grupos", fase="asistencia"),
    DefinicionPermiso("asistencia.ver_propia", "asistencia", "Ver la asistencia que uno mismo registró", fase="asistencia"),
    DefinicionPermiso("asistencia.ver", "asistencia", "Ver la asistencia de cualquier grupo", fase="asistencia"),
    DefinicionPermiso("asistencia.corregir", "asistencia", "Corregir un registro de asistencia ajeno", sensible=True, fase="asistencia"),
    DefinicionPermiso("asistencia.anular", "asistencia", "Anular un registro de asistencia", sensible=True, fase="asistencia"),
    DefinicionPermiso("asistencia.exportar", "asistencia", "Exportar reportes de asistencia", fase="asistencia"),
    DefinicionPermiso("asistencia.estadisticas", "asistencia", "Ver estadísticas de inasistencia", fase="asistencia"),
    DefinicionPermiso("asistencia.cumplimiento", "asistencia", "Ver qué grupos no han tomado asistencia", fase="asistencia"),
    DefinicionPermiso("asistencia.resolver_conflictos", "asistencia", "Resolver conflictos de sincronización de asistencia", fase="asistencia"),

    # --- Observaciones y seguimiento (fase posterior) -----------------------
    DefinicionPermiso("observaciones.ver", "observaciones", "Ver observaciones de los estudiantes", fase="observaciones"),
    DefinicionPermiso("observaciones.crear", "observaciones", "Crear una observación", fase="observaciones"),
    DefinicionPermiso("observaciones.editar_propias", "observaciones", "Editar las observaciones propias", fase="observaciones"),
    DefinicionPermiso("observaciones.editar", "observaciones", "Editar cualquier observación", fase="observaciones"),
    DefinicionPermiso("observaciones.eliminar", "observaciones", "Eliminar una observación", sensible=True, fase="observaciones"),
    DefinicionPermiso("observaciones.ver_confidenciales", "observaciones", "Ver observaciones marcadas como confidenciales", sensible=True, fase="observaciones"),
    DefinicionPermiso("seguimientos.gestionar", "observaciones", "Registrar seguimientos individuales", fase="observaciones"),

    # --- Alertas de inasistencia (fase posterior) --------------------------
    DefinicionPermiso("alertas.ver", "alertas", "Ver alertas de inasistencia", fase="alertas"),
    DefinicionPermiso("alertas.atender", "alertas", "Marcar una alerta como atendida", fase="alertas"),
    DefinicionPermiso("alertas.configurar", "alertas", "Configurar los umbrales de alerta", sensible=True, fase="alertas"),
    DefinicionPermiso("promocion.autorizar", "alertas", "Aprobar o rechazar solicitudes de promoción (pasar de grado con materias perdidas, saltar o bajar de grado)", sensible=True),

    # --- Sistema (fase posterior) --------------------------------------------
    DefinicionPermiso("auditoria.ver", "sistema", "Ver el registro de auditoría", sensible=True, fase="sistema"),
    DefinicionPermiso("configuracion.gestionar", "sistema", "Configurar parámetros generales del sistema", sensible=True, fase="sistema"),

    # --- Diagnóstico de orientación/psicología (Excel por grado) -------------
    DefinicionPermiso("diagnosticos.ver", "diagnosticos", "Ver los diagnósticos de grado y las menciones de estudiantes"),
    DefinicionPermiso("diagnosticos.importar", "diagnosticos", "Importar el Excel de diagnóstico de orientación", sensible=True),
    DefinicionPermiso("diagnosticos.vincular", "diagnosticos", "Vincular o corregir a qué estudiante corresponde una mención"),
    DefinicionPermiso("diagnosticos.observar", "diagnosticos", "Agregar observaciones y notas de seguimiento a un grupo o estudiante"),
    DefinicionPermiso("diagnosticos.exportar", "diagnosticos", "Imprimir/exportar el reporte del diagnóstico"),
]

CODIGOS: set[str] = {p.codigo for p in CATALOGO}

assert len(CODIGOS) == len(CATALOGO), "hay códigos de permiso repetidos en CATALOGO"


@dataclass(frozen=True)
class DefinicionRol:
    codigo: str
    nombre: str
    descripcion: str
    permisos: list[str] = field(default_factory=list)


# Los 5 roles del sistema (es_sistema=True: no se pueden borrar ni
# desactivar). Esta es solo la SEMILLA: se aplica una única vez, la primera
# vez que cada rol se crea. Ediciones posteriores del administrador nunca se
# revierten en un reinicio (ver migraciones.sembrar_roles_sistema).
ROLES_SISTEMA: list[DefinicionRol] = [
    DefinicionRol(
        codigo="administrador",
        nombre="Administrador",
        descripcion="Control total: usuarios, roles, permisos, configuración, auditoría y todo lo académico.",
        permisos=[
            "usuarios.ver", "usuarios.crear", "usuarios.editar", "usuarios.estado",
            "usuarios.restablecer_clave", "usuarios.roles", "usuarios.sedes",
            "roles.ver", "roles.gestionar",
            "sesiones.ver", "sesiones.revocar",
            "estudiantes.ver", "estudiantes.crear", "estudiantes.editar", "estudiantes.eliminar",
            "estudiantes.ver_documentos", "estudiantes.documentos_gestionar",
            "sedes.ver", "catalogos.ver", "catalogos.gestionar",
            "docentes.ver", "docentes.evaluar", "docentes.gestionar", "grupos.ver", "grupos.gestionar",
            "horario.ver", "horario.gestionar", "horario.exportar",
            "boletines.ver", "boletines.gestionar", "boletines.exportar",
            "sapred.importar", "sapred.ejecutar",
            "constancias.ver", "constancias.generar",
            "reportes.ver", "reportes.exportar",
            # Asistencia: administra el módulo pero no registra clase (no es docente).
            "asistencia.ver", "asistencia.corregir", "asistencia.anular", "asistencia.exportar",
            "asistencia.estadisticas", "asistencia.cumplimiento", "asistencia.resolver_conflictos",
            # Observaciones: el Administrador NO recibe ver_confidenciales por
            # defecto (mínimo privilegio; decisión aprobada 12/09/2026, punto
            # 2). Puede concedérselo desde la pantalla de roles, y cuando
            # exista la auditoría quedará registrado que lo hizo.
            "observaciones.ver", "observaciones.crear", "observaciones.editar", "observaciones.eliminar",
            "alertas.ver", "alertas.atender", "promocion.autorizar", "alertas.configurar",
            "auditoria.ver", "configuracion.gestionar",
            "diagnosticos.ver", "diagnosticos.importar", "diagnosticos.vincular",
            "diagnosticos.observar", "diagnosticos.exportar",
        ],
    ),
    DefinicionRol(
        codigo="secretaria",
        nombre="Secretaría",
        descripcion="La operación de hoy: matrícula, boletines, notas, constancias, horarios y SAPRED. Sin usuarios, roles ni auditoría.",
        permisos=[
            "estudiantes.ver", "estudiantes.crear", "estudiantes.editar",
            "estudiantes.ver_documentos", "estudiantes.documentos_gestionar",
            "sedes.ver", "catalogos.ver", "catalogos.gestionar",
            "docentes.ver", "docentes.gestionar", "grupos.ver", "grupos.gestionar",
            "horario.ver", "horario.gestionar", "horario.exportar",
            "boletines.ver", "boletines.gestionar", "boletines.exportar",
            "sapred.importar", "sapred.ejecutar",
            "constancias.ver", "constancias.generar",
            "reportes.ver", "reportes.exportar",
            # Secretaría NO registra asistencia (decisión aprobada
            # 12/09/2026): solo consulta y exporta.
            "asistencia.ver", "asistencia.exportar",
        ],
    ),
    DefinicionRol(
        codigo="coordinador",
        nombre="Coordinador",
        descripcion="Gestión académica y seguimiento de asistencia. Todas las sedes por ahora (usuario_sedes queda preparada para restringir después).",
        permisos=[
            "estudiantes.ver",
            "sedes.ver", "catalogos.ver", "docentes.ver", "docentes.evaluar", "grupos.ver",
            "horario.ver", "horario.gestionar",
            "boletines.ver", "boletines.exportar",
            "constancias.ver",
            "reportes.ver", "reportes.exportar",
            "asistencia.ver", "asistencia.corregir", "asistencia.anular", "asistencia.exportar",
            "asistencia.estadisticas", "asistencia.cumplimiento", "asistencia.resolver_conflictos",
            "observaciones.ver", "observaciones.crear", "observaciones.editar_propias",
            "alertas.ver", "alertas.atender", "promocion.autorizar",
        ],
    ),
    DefinicionRol(
        codigo="orientacion",
        nombre="Orientación/Psicología",
        descripcion="Seguimiento estudiantil: historial de inasistencias, observaciones y seguimientos, incluidos los confidenciales.",
        permisos=[
            "estudiantes.ver",
            "sedes.ver", "catalogos.ver", "grupos.ver",
            "reportes.ver",
            "asistencia.ver", "asistencia.estadisticas",
            "observaciones.ver", "observaciones.crear", "observaciones.editar_propias",
            "observaciones.ver_confidenciales", "seguimientos.gestionar",
            "alertas.ver", "alertas.atender",
            "diagnosticos.ver", "diagnosticos.vincular", "diagnosticos.observar", "diagnosticos.exportar",
        ],
    ),
    DefinicionRol(
        codigo="docente",
        nombre="Docente",
        descripcion="Registrar la asistencia de sus grupos y consultar lo suyo. Interfaz mínima.",
        permisos=[
            "catalogos.ver", "grupos.ver",
            "asistencia.registrar", "asistencia.ver_propia",
            "observaciones.ver", "observaciones.crear", "observaciones.editar_propias",
            "estudiantes.editar_ficha_grupo",
        ],
    ),
]
