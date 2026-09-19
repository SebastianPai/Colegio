import datetime as dt

from pydantic import BaseModel, ConfigDict


class SedeBase(BaseModel):
    nombre: str
    codigo_dane_sede: str | None = None
    codigo_dane_consecutivo: str | None = None
    institucion_centro_educativo: str | None = None
    resguardo: str | None = None
    pertenece_ietaba: bool = True


class SedeCreate(SedeBase):
    pass


class SedeUpdate(BaseModel):
    pertenece_ietaba: bool | None = None


class Sede(SedeBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class SedeResumen(Sede):
    total_estudiantes: int = 0
    total_activos: int = 0


class ReporteSede(BaseModel):
    id: int
    nombre: str
    total_estudiantes: int
    hombres: int
    mujeres: int


class ReporteGeneral(BaseModel):
    total_sedes: int
    total_estudiantes: int
    hombres: int
    mujeres: int
    por_sede: list[ReporteSede]


class EstudianteBase(BaseModel):
    id_estud: str | None = None
    documento: str
    tipo_documento: str | None = None
    lugar_expedicion_documento: str | None = None
    primer_apellido: str
    segundo_apellido: str | None = None
    primer_nombre: str
    segundo_nombre: str | None = None
    fecha_nacimiento: dt.date | None = None
    genero: str | None = None
    grado: int = 0
    curso: int | None = None
    estado: str = "ACTIVO"
    observaciones: str | None = None
    posible_retirado: bool = False
    retirado: bool = False
    sede_id: int | None = None


class EstudianteCreate(EstudianteBase):
    pass


class EstudianteUpdate(BaseModel):
    id_estud: str | None = None
    documento: str | None = None
    tipo_documento: str | None = None
    lugar_expedicion_documento: str | None = None
    primer_apellido: str | None = None
    segundo_apellido: str | None = None
    primer_nombre: str | None = None
    segundo_nombre: str | None = None
    fecha_nacimiento: dt.date | None = None
    genero: str | None = None
    grado: int | None = None
    curso: int | None = None
    estado: str | None = None
    observaciones: str | None = None
    posible_retirado: bool | None = None
    retirado: bool | None = None
    sede_id: int | None = None


class FotoEstudiante(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    etiqueta: str
    anio_lectivo: int | None
    orden: int
    es_pdf: bool = False


class HistorialDocumento(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tipo_documento: str | None
    documento: str | None
    vigente_hasta: dt.datetime


class Estudiante(EstudianteBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool
    grupo: str
    verificado_matricula: bool | None = None
    sede: Sede | None = None
    fotos: list[FotoEstudiante] = []
    historial_documento: list[HistorialDocumento] = []


class PaginaEstudiantes(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    items: list[Estudiante]


class VerificacionEstudiante(BaseModel):
    existe: bool
    estudiante: Estudiante | None = None


class ConstanciaSolicitud(BaseModel):
    estudiante_id: int
    lugar_expedicion: str
    jornada: str = "Diurna"
    anio_escolar: int
    fecha_expedicion: dt.date
    proposito: str
    tipo_documento: str | None = None  # si se manda, sobreescribe el del estudiante solo para esta constancia


class ConstanciaRegistro(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    generado_en: dt.datetime
    fecha_expedicion: dt.date
    proposito: str
    jornada: str
    anio_escolar: int
    lugar_expedicion: str
    tipo_documento_usado: str | None
    archivo_pdf: str | None
    estudiante: Estudiante


class Docente(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    documento: str
    nombre_completo: str
    fecha_nacimiento: dt.date | None = None
    telefono: str | None = None
    email: str | None = None
    direccion: str | None = None


class AsignacionDocenteCrear(BaseModel):
    docente_id: int | None  # None = quitar la asignación (de ese grupo, o de esa área si area_id viene)
    sede_id: int
    grado: int
    curso: int | None = None
    area_id: int | None = None  # None = el docente enseña TODO el grupo (sedes rurales)
    anio_lectivo: int


class Area(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    nombre: str


class AreaConGrados(Area):
    grados: list[int] = []


class EstudianteMini(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    documento: str
    nombre_completo: str
    posible_retirado: bool = False
    retirado: bool = False


class PendienteCrear(BaseModel):
    sede_id: int
    grado: int
    curso: int | None = None
    anio_lectivo: int
    periodo: int = 1
    area_id: int | None = None  # None = pendiente general del grupo (ej. observaciones)
    estudiante_id: int | None = None  # None = afecta a todo el grupo, no a un estudiante puntual
    tipo: str = "nota"  # nota | concepto | observacion
    detalle: str | None = None
    revisado_por: str | None = None


class PendienteActualizar(BaseModel):
    resuelto: bool | None = None
    detalle: str | None = None
    revisado_por: str | None = None


class PendientesLote(BaseModel):
    ids: list[int]
    resuelto: bool = True


class Pendiente(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tipo: str
    detalle: str | None
    resuelto: bool
    creado_en: dt.datetime
    resuelto_en: dt.datetime | None
    area: Area | None = None
    estudiante: EstudianteMini | None = None


class PendienteConGrupo(Pendiente):
    sede_id: int
    sede_nombre: str
    grado: int
    curso: int | None = None
    nombre_grupo: str
    periodo: int
    anio_lectivo: int
    docente: Docente | None = None


class ResumenPorClave(BaseModel):
    id: int
    nombre: str
    total_grupos: int
    completos: int
    pendientes: int


class ResumenBoletines(BaseModel):
    anio_lectivo: int
    periodo: int
    total_grupos: int
    completos: int
    en_proceso: int
    pendientes: int
    sin_informacion: int
    porcentaje_completo: float
    total_pendientes_individuales: int
    por_sede: list[ResumenPorClave]
    por_docente: list[ResumenPorClave]
    por_area: list[ResumenPorClave]


class ImportarSapredResultadoBloque(BaseModel):
    grado: int
    curso: int | None
    sede_corta: str
    sede_id: int | None = None
    sede_nombre: str | None = None
    periodo: int
    anio_lectivo: int
    reconocido: bool
    motivo_no_reconocido: str | None = None
    areas_nuevas: list[str] = []
    pendientes_creados: int = 0
    pendientes_ya_existian: int = 0
    pendientes_resueltos_auto: int = 0  # pendientes viejos que esta corrida cerró (ya estaban en SAPRED)
    estudiantes_no_encontrados: list[str] = []
    docente_asignado: str | None = None


class SapredNotaEstudiante(BaseModel):
    documento: str
    nombre: str
    notas: dict[str, str | None] = {}


class SapredAreaBloque(BaseModel):
    codigo: str
    nombre: str


class SapredBloqueEntrada(BaseModel):
    """Un bloque (un curso) ya extraído en el navegador desde el reporte
    HTML en vivo de SAPRED — misma forma que produce el parser de PDF, para
    poder reusar exactamente la misma lógica de importación."""

    grado: int
    curso: int
    sede_corta: str
    sede_id: int | None = None  # si se sabe de antemano (ej. la automatización ya sabe qué sede eligió), se usa directo sin adivinar por nombre
    periodo: int
    anio_lectivo: int | None = None
    director_grupo: str | None = None
    areas: list[SapredAreaBloque]
    estudiantes: list[SapredNotaEstudiante]


class ImportarSapredResultado(BaseModel):
    bloques: list[ImportarSapredResultadoBloque]
    total_pendientes_creados: int
    total_pendientes_resueltos_auto: int = 0
    total_estudiantes_no_encontrados: int


class ImportacionSapredPdfHistorial(BaseModel):
    id: int
    nombre_archivo: str
    importado_en: dt.datetime
    total_pendientes_creados: int
    total_estudiantes_no_encontrados: int
    bloques: list[ImportarSapredResultadoBloque] = []
    error: str | None = None


# --- Importación del "Boletín informativo" de SAPRED -----------------------
# Flujo paralelo al del "Consolidado por periodo": en vez de notas numéricas,
# trae el concepto de cada área, la observación del director de grupo y el
# profesor de cada materia.


class BoletinAreaBloque(BaseModel):
    codigo: str
    nombre: str
    docente: str | None = None  # "PROFESOR: ..." del bloque de esa área


class BoletinAreaNota(BaseModel):
    nota: str | None = None    # nota numérica del período actual, si aparece
    nivel: str | None = None   # palabra: Wari / Pichin Wai / ...
    concepto: str | None = None


class BoletinEstudianteEntrada(BaseModel):
    documento: str
    nombre: str
    observacion: str | None = None
    areas: dict[str, BoletinAreaNota] = {}  # codigo_area -> datos


class BoletinBloqueEntrada(BaseModel):
    """Un bloque (un curso) ya extraído en el navegador desde el reporte HTML
    en vivo del "Boletín informativo" — misma forma que produce el parser de
    PDF (importador_boletin.parsear_pdf_boletin)."""

    grado: int
    curso: int
    sede_corta: str
    sede_id: int | None = None
    periodo: int
    anio_lectivo: int | None = None
    director_grupo: str | None = None
    areas: list[BoletinAreaBloque]
    estudiantes: list[BoletinEstudianteEntrada]


class ImportarBoletinResultadoBloque(BaseModel):
    grado: int
    curso: int | None
    sede_corta: str
    sede_id: int | None = None
    sede_nombre: str | None = None
    periodo: int
    anio_lectivo: int
    reconocido: bool
    motivo_no_reconocido: str | None = None
    areas_nuevas: list[str] = []
    conceptos_pendientes_creados: int = 0
    conceptos_pendientes_ya_existian: int = 0
    notas_pendientes_creados: int = 0
    notas_pendientes_ya_existian: int = 0
    observaciones_pendientes_creadas: int = 0
    observaciones_pendientes_ya_existian: int = 0
    pendientes_resueltos_auto: int = 0  # pendientes viejos que esta corrida cerró (ya estaban en SAPRED)
    docentes_area_asignados: list[str] = []  # "MATE: NOMBRE DEL DOCENTE"
    docente_grupo_asignado: str | None = None
    estudiantes_no_encontrados: list[str] = []


class ImportarBoletinResultado(BaseModel):
    bloques: list[ImportarBoletinResultadoBloque]
    total_conceptos_pendientes: int
    total_notas_pendientes: int = 0
    total_observaciones_pendientes: int
    total_pendientes_resueltos_auto: int = 0
    total_estudiantes_no_encontrados: int


class ImportacionBoletinPdfHistorial(BaseModel):
    id: int
    nombre_archivo: str
    importado_en: dt.datetime
    total_conceptos_pendientes: int
    total_observaciones_pendientes: int
    total_estudiantes_no_encontrados: int
    bloques: list[ImportarBoletinResultadoBloque] = []
    error: str | None = None


class AuditoriaSapredCrear(BaseModel):
    anio_lectivo: int | None = None
    periodo: int
    grado: int | None = None  # None = todos los grados
    sede_ids: list[int] | None = None  # None = todas las sedes IETABA
    tipo: str = "notas"  # notas (Consolidado) | boletin (Boletín informativo) | ambos | boletin_pdf
    # Credenciales de SAPRED: SOLO se usan para esta corrida (se pasan al
    # subproceso por variable de entorno). NO se guardan en la base ni en los
    # logs. Si se dejan vacías, el usuario inicia sesión a mano como siempre.
    usuario: str | None = None
    clave: str | None = None


class AuditoriaSapredDetalleSede(BaseModel):
    sede: str
    estado: str  # completada | advertencia | error
    detalle: str | None = None
    # Solo para las corridas de tipo 'boletin_pdf': nombre del archivo PDF que
    # quedó para esa sede (dentro de AuditoriaSapred.carpeta_salida) y cuántos
    # estudiantes trae.
    archivo: str | None = None
    n_estudiantes: int | None = None
    n_paginas: int | None = None


class ReintentoAuditoriaSapred(BaseModel):
    """Cuerpo (opcional) del reintento: credenciales para el auto-login, que
    NO se guardaron de la corrida original. Vacías = login manual."""

    usuario: str | None = None
    clave: str | None = None


class AuditoriaSapred(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    creado_en: dt.datetime
    terminado_en: dt.datetime | None
    anio_lectivo: int
    periodo: int
    grado: int | None
    tipo: str = "notas"
    estado: str
    sede_actual: str | None
    grado_actual: str | None
    sedes_totales: int
    sedes_completadas: int
    estudiantes_revisados: int
    pendientes_encontrados: int
    carpeta_salida: str | None = None
    detalle_sedes: list[AuditoriaSapredDetalleSede] = []
    error: str | None = None


class ParteBoletinSede(BaseModel):
    """Un PDF de un grado (ya generado por el proceso de Playwright) que el
    backend tiene que unir al boletín consolidado de la sede."""

    grado: int
    ruta: str  # ruta absoluta en disco del PDF de ese grado
    n_estudiantes: int = 0


class EnsamblarBoletinSede(BaseModel):
    """Cuerpo del endpoint interno que llama el proceso de Playwright cuando ya
    tiene todos los PDF de una sede: el backend los une en orden de grado y
    deja un solo archivo 'SEDE ## - NOMBRE.pdf' en la carpeta de la corrida."""

    sede_id: int
    sede_nombre: str
    partes: list[ParteBoletinSede]


class EnsamblarBoletinSedeResultado(BaseModel):
    archivo: str
    n_paginas: int
    n_estudiantes: int


class UnirPdfs(BaseModel):
    """Une PDF sueltos (por la captura manual del boletín) en uno solo."""

    archivos: list[str]
    salida: str


class SepararPorSeccion(BaseModel):
    """Divide el PDF de un grado (generado con 'todas las secciones') en un
    PDF por sección, usando el .html capturado (mismo orden de páginas) para
    saber a qué sección pertenece cada página. Dinámico: sirve igual para una
    sede rural (1 sección) que para la sede principal (varias por grado)."""

    html: str  # ruta del .html capturado (al lado del .pdf)
    pdf: str  # ruta del PDF del grado completo
    carpeta_salida: str  # carpeta donde deja <seccion>.pdf (se crea si falta)


class SepararPorSeccionResultado(BaseModel):
    separado: bool  # False = no se pudo parear páginas con secciones (se deja el PDF combinado)
    secciones: dict[str, int] = {}  # {"4-1": 25, "4-2": 28, ...} -> nº de estudiantes


class AuditoriaSapredProgreso(BaseModel):
    """Lo que el propio proceso de Playwright reporta mientras corre."""

    estado: str | None = None
    sede_actual: str | None = None
    grado_actual: str | None = None
    sedes_totales: int | None = None
    sedes_completadas: int | None = None
    estudiantes_revisados_delta: int = 0
    pendientes_encontrados_delta: int = 0
    detalle_sede: AuditoriaSapredDetalleSede | None = None
    error: str | None = None


class RevisionBoletinGuardar(BaseModel):
    sede_id: int
    grado: int
    curso: int | None = None
    anio_lectivo: int
    periodo: int = 1
    completo: bool = False
    materias_faltantes: str | None = None
    observaciones_completas: bool = False
    notas: str | None = None
    estudiantes_pendientes: str | None = None


class RevisionBoletin(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    periodo: int
    completo: bool
    materias_faltantes: str | None
    observaciones_completas: bool
    notas: str | None
    estudiantes_pendientes: str | None
    revisado_en: dt.datetime


class GrupoAcademico(BaseModel):
    sede_id: int
    sede_nombre: str
    grado: int
    nombre_grado: str
    curso: int | None
    nombre_grupo: str
    total_estudiantes: int
    docente: Docente | None = None
    revision: RevisionBoletin | None = None
    estado: str = "sin_informacion"  # completo | en_proceso | pendiente | sin_informacion
    pendientes_abiertos: int = 0


# --- Autenticación (Fase 2) -------------------------------------------------


class LoginSolicitud(BaseModel):
    usuario: str  # documento o correo
    clave: str
    confiar_en_dispositivo: bool = False
    dispositivo_id: str | None = None  # UUID que guarda el cliente
    nombre_dispositivo: str | None = None


class UsuarioActual(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    documento: str
    nombre: str
    email: str | None = None
    estado: str
    docente_id: int | None = None
    debe_cambiar_clave: bool
    ultimo_acceso: dt.datetime | None = None
    # Se llenan a mano en el router (no son columnas de Usuario): códigos de
    # rol y la unión de sus permisos. Solo para que el menú del frontend
    # muestre lo que corresponde — el backend vuelve a validar cada permiso.
    roles: list[str] = []
    permisos: list[str] = []


class SesionResumen(BaseModel):
    id: str
    dispositivo_id: str
    dispositivo_nombre: str | None = None
    confiable: bool
    creada_en: dt.datetime
    ultimo_uso: dt.datetime
    expira_en: dt.datetime
    expira_absoluta_en: dt.datetime


class SesionActual(BaseModel):
    usuario: UsuarioActual
    sesion: SesionResumen
    expira_acceso_en: dt.datetime


class SesionListada(BaseModel):
    id: str
    dispositivo_nombre: str | None = None
    confiable: bool
    creada_en: dt.datetime
    ultimo_uso: dt.datetime
    expira_en: dt.datetime
    ip: str | None = None
    es_la_actual: bool = False


class CambiarClave(BaseModel):
    clave_actual: str
    clave_nueva: str


# --- Administración: roles y permisos (Fase 3) ------------------------------


class PermisoInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    codigo: str
    modulo: str
    descripcion: str
    sensible: bool
    activo: bool


class RolResumen(BaseModel):
    id: int
    codigo: str
    nombre: str
    descripcion: str | None = None
    es_sistema: bool
    activo: bool
    total_usuarios: int
    total_permisos: int


class RolDetalle(RolResumen):
    permisos: list[str]


class RolCrear(BaseModel):
    codigo: str
    nombre: str
    descripcion: str | None = None


class RolActualizar(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    activo: bool | None = None


class RolPermisosActualizar(BaseModel):
    permisos: list[str]


class UsuarioAdminResumen(BaseModel):
    id: int
    documento: str
    nombre: str
    email: str | None = None
    estado: str
    docente_id: int | None = None
    debe_cambiar_clave: bool
    ultimo_acceso: dt.datetime | None = None
    creado_en: dt.datetime
    roles: list[str]
    sesiones_activas: int


class UsuarioAdminDetalle(UsuarioAdminResumen):
    sedes: list[int]  # usuario_sedes; [] = sin restricción (todas las sedes)


class UsuarioCrear(BaseModel):
    documento: str
    nombre: str
    email: str | None = None
    docente_id: int | None = None
    roles: list[str] = []


class UsuarioCreado(BaseModel):
    usuario: UsuarioAdminResumen
    clave_temporal: str


class UsuarioEditar(BaseModel):
    nombre: str | None = None
    email: str | None = None
    documento: str | None = None
    docente_id: int | None = None
    quitar_docente: bool = False  # True = desenlazar (docente_id se ignora)


class UsuarioEstado(BaseModel):
    estado: str  # activo | inactivo | bloqueado


class ClaveTemporalRespuesta(BaseModel):
    clave_temporal: str


class UsuarioRolesActualizar(BaseModel):
    roles: list[str]  # códigos; reemplaza la lista completa


class UsuarioSedesActualizar(BaseModel):
    sedes: list[int]  # ids de Sede; [] = sin restricción (todas)


class AsistenciaMarcar(BaseModel):
    estudiante_id: int
    fecha: dt.date
    presente: bool


class Asistencia(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    estudiante_id: int
    fecha: dt.date
    presente: bool


# --- Auditoría de continuidad académica (P1 vs P2) --------------------------


class NovedadContinuidad(BaseModel):
    estudiante_id: int
    documento: str
    nombre_completo: str
    curso: int | None
    estado: str  # activo | sin_evidencia_p1 | posible_retiro | posible_retiro_prioritario | p2_sin_auditar | p1_sin_auditar | sin_auditar
    evidencia: str


class ContinuidadPorGrado(BaseModel):
    grado: int
    nombre_grado: str
    matriculados: int
    con_notas_p1: int
    sin_notas_p1: int
    activos_p2: int
    posibles_retiros: int
    observaciones: int
    p1_auditado: bool
    p2_auditado: bool
    cursos_sin_notas_p2: list[str] = []  # cursos donde NADIE tiene nota en P2 (probable atraso de cargue, no retiro individual)
    novedades: list[NovedadContinuidad] = []


class ResumenContinuidad(BaseModel):
    sede_id: int
    sede_nombre: str
    anio_lectivo: int
    total_matriculados: int
    total_con_notas_p1: int
    total_sin_evidencia_p1: int
    total_activos_p2: int
    total_posibles_retiros: int
    porcentaje_continuidad: float  # activos_p2 / con_notas_p1, entre los grupos auditados en ambos períodos
    por_grado: list[ContinuidadPorGrado]


# --- Grilla de notas (vista tipo SAPRED, estudiante x área) -----------------


class GrillaArea(BaseModel):
    id: int
    codigo: str
    nombre: str
    docente: Docente | None = None  # profesor de esta materia (del "Boletín informativo"), si se sabe


# Estado de un texto (concepto de área u observación del director) en la grilla:
#   tiene       = el boletín trae el texto
#   falta       = el boletín trae la fila pero sin texto (pendiente abierto)
#   revisado    = faltaba, pero se marcó como revisado
#   sin_auditar = el grupo/período no se ha importado del "Boletín informativo"
#   sin_dato    = se importó, pero de este punto no quedó nada
class GrillaCelda(BaseModel):
    valor: str | None = None  # la nota real, tal cual está en SAPRED, si existe
    # nota            = hay valor real
    # falta           = SAPRED no tiene esta nota (pendiente abierto, se puede resolver desde aquí)
    # revisado        = faltaba, pero ya se marcó como revisado/validado administrativamente
    # sin_auditar     = este grupo/período todavía no se ha revisado contra SAPRED
    # sin_dato        = el grupo sí se auditó pero esta celda puntual no quedó registrada ni como nota ni como falta
    estado: str
    pendiente_id: int | None = None
    concepto_estado: str = "sin_auditar"
    concepto_texto: str | None = None
    concepto_pendiente_id: int | None = None


class GrillaFila(BaseModel):
    estudiante_id: int
    documento: str
    nombre_completo: str
    posible_retirado: bool = False
    retirado: bool = False
    celdas: dict[int, GrillaCelda]  # area_id -> celda
    observacion_estado: str = "sin_auditar"
    observacion_texto: str | None = None
    observacion_pendiente_id: int | None = None


class GrillaGrupo(BaseModel):
    sede_id: int
    sede_nombre: str
    grado: int
    nombre_grado: str
    curso: int | None
    nombre_grupo: str
    periodo: int
    anio_lectivo: int
    auditado: bool  # existe una RevisionBoletin para este grupo/período
    docente: Docente | None = None
    areas: list[GrillaArea]
    filas: list[GrillaFila]


# --- Reporte de notas (bajas / altas / estudiantes en riesgo) ---------------


class NotaDestacada(BaseModel):
    estudiante_id: int
    documento: str
    nombre_completo: str
    sede_id: int
    sede_nombre: str
    grado: int
    nombre_grado: str
    curso: int | None
    nombre_grupo: str
    area_codigo: str
    area_nombre: str
    valor: float
    docente: str | None = None


class EstudianteEnRiesgo(BaseModel):
    estudiante_id: int
    documento: str
    nombre_completo: str
    sede_id: int
    sede_nombre: str
    grado: int
    nombre_grado: str
    curso: int | None
    nombre_grupo: str
    cantidad_notas_bajas: int
    areas_bajas: list[str]
    promedio: float  # promedio de TODAS sus notas evaluadas en este filtro (no solo las bajas)


class ReporteNotas(BaseModel):
    periodo: int
    anio_lectivo: int
    umbral_bajo: float
    umbral_alto: float
    riesgo_minimo: int
    total_notas_evaluadas: int
    notas_bajas: list[NotaDestacada]
    notas_altas: list[NotaDestacada]
    estudiantes_en_riesgo: list[EstudianteEnRiesgo]


# --- Estudiantes que SAPRED reporta pero que no están en la base local ------


class SapredSinCoincidencia(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    documento: str
    nombre_sapred: str
    sede_id: int
    sede_nombre: str = ""
    grado: int
    nombre_grado: str = ""
    curso: int | None
    periodo: int
    anio_lectivo: int
    tiene_notas: bool
    primera_vez_visto: dt.datetime
    ultima_vez_visto: dt.datetime
    resuelto: bool


class SapredSinCoincidenciaActualizar(BaseModel):
    resuelto: bool


# --- Conciliación SIMAC (matrícula local) ↔ SAPRED --------------------------


class ConciliacionDiferencia(BaseModel):
    campo: str  # "nombre" | "grupo" | "documento"
    valor_simac: str
    valor_sapred: str


class ConciliacionEstudiante(BaseModel):
    estudiante_id: int | None = None  # None = el registro solo existe en SAPRED, sin match local
    documento: str
    nombre_completo: str
    sede_id: int | None = None
    sede_nombre: str = ""
    grado: int | None = None
    nombre_grado: str = ""
    curso: int | None = None
    nombre_grupo: str = ""
    docente: str | None = None
    estado_conciliacion: str  # coincide | solo_simac | solo_sapred | diferencia
    diferencias: list[ConciliacionDiferencia] = []


class ConciliacionGrupo(BaseModel):
    sede_id: int
    sede_nombre: str
    grado: int
    nombre_grado: str
    curso: int | None
    nombre_grupo: str
    docente: str | None = None
    total_simac: int
    total_sapred: int
    coinciden: int
    solo_simac: int
    solo_sapred: int
    diferencias: int
    estado: str  # correcto | requiere_revision


class ConciliacionDocente(BaseModel):
    docente_id: int | None
    nombre_completo: str
    grupos: list[ConciliacionGrupo]
    total_diferencias: int


class ConciliacionResumen(BaseModel):
    anio_lectivo: int
    periodo: int
    total_simac: int
    total_sapred: int
    coinciden: int
    solo_simac: int
    solo_sapred: int
    diferencias: int
    grupos_con_inconsistencias: int
    docentes_pendientes: int
    calidad_pct: float


class ConciliacionResultado(BaseModel):
    generado_en: dt.datetime
    resumen: ConciliacionResumen
    estudiantes: list[ConciliacionEstudiante]
    grupos: list[ConciliacionGrupo]


# --- Horarios --------------------------------------------------------------


class BloqueHorario(BaseModel):
    id: int
    anio_lectivo: int
    docente_id: int
    docente_nombre: str
    sede_id: int
    grado: int
    curso: int | None
    grupo: str
    nombre_grupo: str
    area_id: int | None
    area_label: str
    area_nombre: str
    dia: int
    dia_nombre: str
    hora: int
    aula: str | None = None
    origen: str = ""
    estado: str = "activo"  # activo | descartado
    en_conflicto: bool = False  # el grupo+día+hora tiene otro docente sin confirmar


class FilaHorario(BaseModel):
    hora: int
    inicio: str
    fin: str
    celdas: list[BloqueHorario | None]  # 5 celdas: Lu..Vi (None = LIBRE)


class HorarioDocenteSemana(BaseModel):
    docente_id: int
    docente_nombre: str
    anio_lectivo: int
    total_bloques: int
    filas: list[FilaHorario]


class HorarioGrupo(BaseModel):
    grado: int
    curso: int | None
    grupo: str
    nombre_grupo: str
    anio_lectivo: int
    total_estudiantes: int
    bloques: list[BloqueHorario]


class DocenteLibre(BaseModel):
    docente_id: int
    nombre_completo: str
    bloques_ese_dia: int
    cubriendo_reemplazo: bool = False
    niveles: list[str] = []  # "primaria" / "secundaria" (según sus clases)


class HorasLibresDocente(BaseModel):
    docente_id: int
    nombre_completo: str
    # "dia-hora" -> "6-2 COE" (lo que dicta); si la clave no está, esa franja está libre
    celdas: dict[str, str] = {}
    libres_por_dia: dict[int, int] = {}
    niveles: list[str] = []  # "primaria" / "secundaria" (según los grados que dicta)
    total_libres: int = 0
    total_clases: int = 0


class HorasLibresReporte(BaseModel):
    anio_lectivo: int
    franjas: list[dict] = []
    docentes: list[HorasLibresDocente] = []


class EstadoDocente(BaseModel):
    docente_id: int
    nombre_completo: str
    # libre | en_clase | descanso | fuera_jornada | ausente | cubriendo
    estado: str
    detalle: str | None = None


class OpcionConflicto(BaseModel):
    bloque_id: int
    docente_id: int
    docente_nombre: str
    area_label: str
    origen: str = ""


class ClaseAfectada(BaseModel):
    bloque_horario_id: int  # el primero del bloque (para compatibilidad)
    bloque_ids: list[int] = []  # todos los bloques de la clase (bloque doble = 2)
    hora: int  # la primera hora
    horas: list[int] = []  # todas las horas de la clase (bloque doble = [1, 2])
    dia: int
    grado: int
    curso: int | None
    grupo: str
    nombre_grupo: str
    area_id: int | None
    area_label: str
    conflicto: bool = False  # este grupo+hora tiene dos docentes sin confirmar
    conflicto_opciones: list[OpcionConflicto] = []
    reemplazo_id: int | None = None
    reemplazo_estado: str | None = None  # pendiente | asignado | parcial
    reemplazo_docente: str | None = None


class ConflictoHorario(BaseModel):
    grado: int
    curso: int | None
    grupo: str
    nombre_grupo: str
    dia: int
    dia_nombre: str
    hora: int
    opciones: list[OpcionConflicto]


class ResolverConflicto(BaseModel):
    anio_lectivo: int
    grado: int
    curso: int | None = None
    dia: int
    hora: int
    accion: str  # "oficial" (elige uno) | "ambos" (deja los dos)
    bloque_id: int | None = None  # requerido si accion == "oficial"
    resuelto_por: str | None = None


class AusenciaCrear(BaseModel):
    docente_id: int
    fecha: dt.date
    motivo: str | None = None
    registrado_por: str | None = None


class Ausencia(BaseModel):
    id: int
    docente_id: int
    docente_nombre: str
    fecha: dt.date
    motivo: str | None
    registrado_por: str | None
    registrado_en: dt.datetime
    clases_afectadas: list[ClaseAfectada]


class DocentePendientesResumen(BaseModel):
    docente: Docente
    grupos: list[str]
    dirige: list[str] = []  # grupos de los que es director de grupo
    sedes: list[str] = []  # sedes en las que tiene carga
    areas: list[str]
    abiertos: int
    por_tipo: dict[str, int]  # {"nota": n, "concepto": n, "observacion": n}
    al_dia: bool


class PendientesPorDocente(BaseModel):
    periodo: int | None
    hay_auditoria: bool  # ¿ya se auditó/importó algo de este período?
    docentes: list[DocentePendientesResumen]


class ReporteFaltanteItem(BaseModel):
    sede_nombre: str
    grado: int
    curso: int | None
    nombre_grupo: str
    periodo: int
    area_id: int | None
    area_nombre: str
    tipo: str  # nota | concepto | observacion
    alcance: str  # "grupo" (le falta a TODO el grupo) | "parcial" (solo a algunos)
    n_faltan: int
    total_grupo: int
    estudiantes: list[str] = []  # vacío cuando alcance == "grupo"


class ReporteFaltantesDocente(BaseModel):
    docente: Docente
    dirige: list[str] = []
    sedes: list[str] = []
    grupos: list[str] = []  # todos los grupos que tiene a cargo (con o sin pendiente)
    grupos_ok: list[str] = []  # grupos a cargo sin nada pendiente
    total_faltantes: int
    items: list[ReporteFaltanteItem]


class ReporteFaltantes(BaseModel):
    anio_lectivo: int
    periodo: int | None
    generado_en: dt.datetime
    docentes: list[ReporteFaltantesDocente]
    sin_docente: list[ReporteFaltanteItem] = []  # pendientes que ningún docente cubre


class RazonReemplazo(BaseModel):
    tipo: str  # ok | warn
    texto: str


class OcupaSlot(BaseModel):
    bloque_id: int
    docente_id: int
    docente_nombre: str
    area_label: str
    horas_area_semana: int  # cuántas horas/semana tiene esa área ese grupo (para saber si "duele" quitar una)


class HuecoHorario(BaseModel):
    dia: int
    nombre_dia: str
    hora: int
    hora_fin: int
    franja: str
    horas: int
    puntaje: int  # 0-100, qué tan buena es la ubicación
    continuidad: bool  # queda pegada a otra clase del profe con ese grupo
    libre: bool  # True = el grupo tiene esa franja libre; False = hay que desplazar una clase
    ocupa: list[OcupaSlot] = []  # qué clase(s) del grupo se desplazarían (si libre=False)
    razones: list[RazonReemplazo]


class HuecosRespuesta(BaseModel):
    docente_id: int
    docente_nombre: str
    grado: int
    curso: int | None
    grupo: str
    nombre_grupo: str
    area_id: int | None
    area_label: str
    horas: int
    total_libres: int
    huecos: list[HuecoHorario]
    ocupados: list[list[int]] = []  # [[dia,hora], ...] del grupo — para pintar la rejilla


class CrearBloqueHorario(BaseModel):
    anio_lectivo: int | None = None
    docente_id: int
    grado: int
    curso: int | None = None
    area_id: int | None = None
    area_label: str | None = None
    dia: int
    hora: int
    horas: int = 1  # 1 o 2 (bloque doble seguido)
    aula: str | None = None
    crear_asignacion: bool = True  # también crea AsignacionDocente para boletines
    desplazar_bloque_ids: list[int] = []  # bloques del grupo a QUITAR para abrir el hueco


class CandidatoReemplazo(BaseModel):
    docente_id: int
    nombre_completo: str
    porcentaje: int
    bloques_ese_dia: int
    razones: list[RazonReemplazo]
    nivel: str = ""  # "primaria" / "secundaria" / "" — el nivel de la clase
    trabaja_ese_nivel: bool = True
    horas_libres: int = 1  # de cuántas horas de la clase está libre
    horas_total: int = 1
    cubre_bloque_completo: bool = True


class RespuestaCandidatos(BaseModel):
    bloque: BloqueHorario
    fecha: dt.date
    horas: list[int] = []  # todas las horas de la clase (bloque doble = [1, 2])
    bloque_ids: list[int] = []
    nivel: str = ""
    candidatos: list[CandidatoReemplazo]


class ReemplazoAsignar(BaseModel):
    bloque_horario_id: int
    fecha: dt.date
    docente_reemplazo_id: int
    asignado_por: str | None = None


class ReemplazoActualizar(BaseModel):
    estado: str | None = None  # "cancelado" para cancelar
    docente_reemplazo_id: int | None = None  # nuevo reemplazante (cambiar)
    asignado_por: str | None = None


class Reemplazo(BaseModel):
    id: int
    fecha: dt.date
    dia: int
    dia_nombre: str
    hora: int
    grado: int
    curso: int | None
    grupo: str
    nombre_grupo: str
    area_id: int | None
    area_label: str
    docente_ausente_id: int
    docente_ausente: str
    docente_reemplazo_id: int | None
    docente_reemplazo: str | None
    bloque_horario_id: int | None
    estado: str
    compatibilidad: int | None
    razones: list[RazonReemplazo] = []
    asignado_por: str | None
    actualizado_en: dt.datetime
    horas: list[int] = []  # bloque doble colapsado = [1, 2]
    ids: list[int] = []  # todos los ids de reemplazo del bloque (para cambiar/cancelar)


class PanelHoy(BaseModel):
    fecha: dt.date
    dia: int | None
    dia_nombre: str
    franja: dict
    docentes_libres: int
    docentes_en_clase: int
    docentes_ausentes: int
    docentes_cubriendo: int
    docentes_descanso: int
    docentes_fuera_jornada: int
    clases_programadas: int
    clases_necesitan_reemplazo: int
    conflictos_pendientes: int = 0
    ausencias: list[Ausencia]
    reemplazos: list[Reemplazo]


class BusquedaItem(BaseModel):
    tipo: str  # docente | grupo | area
    id: int | None = None
    texto: str
    con_horario: bool | None = None
    grado: int | None = None
    curso: int | None = None
    area_label: str | None = None


class ResultadoBusqueda(BaseModel):
    docentes: list[BusquedaItem]
    grupos: list[BusquedaItem]
    areas: list[BusquedaItem]
    docentes: list[ConciliacionDocente]
