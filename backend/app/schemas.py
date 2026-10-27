import datetime as dt

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


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


class ReporteNivel(BaseModel):
    clave: str
    nombre: str
    grados: str
    total_estudiantes: int
    hombres: int
    mujeres: int


class ReporteGeneral(BaseModel):
    total_sedes: int
    total_estudiantes: int
    hombres: int
    mujeres: int
    por_sede: list[ReporteSede]
    por_nivel: list[ReporteNivel] = []


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
    resguardo: bool = True
    sede_id: int | None = None


class EstudianteCreate(EstudianteBase):
    pass


class MatriculaNuevaSolicitud(BaseModel):
    """Matrícula → estudiante nuevo: los datos del estudiante y, en `campos_ficha`,
    lo de la ficha de matrícula con los mismos nombres de casilla que usa la
    ficha oficial (datos_ficha.campos_a_datos: acudiente, resguardo, etnia,
    awapit_si/no, discapacidad, ingreso_dia/mes/anio...)."""

    estudiante: EstudianteCreate
    campos_ficha: dict[str, str] = {}


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
    resguardo: bool | None = None
    sede_id: int | None = None


class FotoEstudiante(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    etiqueta: str
    anio_lectivo: int | None
    orden: int
    es_pdf: bool = False
    subido_en: dt.datetime | None = None  # UTC (models usa utcnow)
    tamano_bytes: int | None = None
    nombre_descarga: str | None = None


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
    pendiente_simat: bool = False
    creado_por_nombre: str | None = None  # quién lo matriculó aquí (Matrícula → nuevo)
    creado_en: dt.datetime | None = None
    matricula_nueva_este_anio: bool = False
    anio_ficha_matricula: int | None = None  # año escolar de su ficha de matrícula
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


class PazYSalvoEstudiante(BaseModel):
    id: int
    nombre_completo: str
    documento: str
    tipo_documento: str | None
    lugar_expedicion: str | None
    genero: str | None
    sede_id: int
    sede_nombre: str
    grupo: str


class PazYSalvoSolicitud(BaseModel):
    estudiante_ids: list[int]
    fecha_expedicion: dt.date
    # Lugar de expedición del documento escrito en pantalla, por estudiante.
    # Si el estudiante no lo tenía guardado, se le guarda.
    lugares: dict[int, str] = {}


class PazYSalvoEstudianteSolicitud(BaseModel):
    estudiante_id: int
    lugar_expedicion: str = ""
    fecha_expedicion: dt.date
    tipo_documento: str | None = None  # si se manda, reemplaza el del estudiante solo para este paz y salvo


class PazYSalvoResultado(BaseModel):
    estudiantes: int
    archivo: str  # nombre para /api/certificados/paz-y-salvo/descargar/{archivo}
    pdf: bool  # si Word pudo convertirlo también a PDF


class FichaMatriculaSolicitud(BaseModel):
    estudiante_id: int
    # Todo lo que aparece en el formulario en pantalla (ya editado por la
    # persona), por nombre de campo — ver ficha_matricula.MAPA_CAMPOS. Nada
    # de esto se guarda en el estudiante, solo se usa para esta ficha.
    campos: dict[str, str] = {}
    formato: str = "docx"  # docx | pdf


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


class AsignacionDocenteResumen(BaseModel):
    sede_id: int
    sede_nombre: str
    grado: int
    grado_nombre: str
    curso: int | None = None
    grupo_label: str
    area_id: int | None = None
    area_nombre: str | None = None
    tipo: str  # AREA | DIRECTOR | GRUPO (ver crud.listar_docentes_reporte)


class DocenteReporte(Docente):
    asignaciones: list[AsignacionDocenteResumen] = []
    es_responsable_grupo: bool = False  # director de grupo o maestro único (rural)
    grupos_dirige: list[str] = []


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


def _lista_enteros(valor):
    """'1,2,3' (como se guarda en la base) o [1, 2, 3] -> [1, 2, 3]."""
    if valor is None or valor == "":
        return []
    if isinstance(valor, str):
        return [int(x) for x in valor.split(",") if x.strip()]
    return list(valor)


class AuditoriaSapredCrear(BaseModel):
    anio_lectivo: int | None = None
    # Uno o varios periodos. `periodo` solo se conserva para los clientes
    # viejos: si llega `periodos`, manda esa lista.
    periodo: int | None = None
    periodos: list[int] | None = None
    # None / vacío = todos los grados. `grados` permite escoger varios (ej.
    # 5, 7 y 9); `grado` es la forma vieja de escoger uno solo.
    grado: int | None = None
    grados: list[int] | None = None
    sede_ids: list[int] | None = None  # None = todas las sedes IETABA
    tipo: str = "notas"  # notas (Consolidado) | boletin (Boletín informativo) | ambos | boletin_pdf
    # Credenciales de SAPRED: SOLO se usan para esta corrida (se pasan al
    # subproceso por variable de entorno). NO se guardan en la base ni en los
    # logs. Si se dejan vacías, el usuario inicia sesión a mano como siempre.
    usuario: str | None = None
    clave: str | None = None

    @model_validator(mode="after")
    def _normalizar_periodos_y_grados(self):
        periodos = sorted(set(self.periodos or ([self.periodo] if self.periodo is not None else [])))
        if not periodos:
            raise ValueError("Escoge al menos un periodo.")
        if any(p not in (1, 2, 3, 4) for p in periodos):
            raise ValueError("Los periodos van del 1 al 4.")
        grados = sorted(set(self.grados or ([self.grado] if self.grado is not None else [])))
        if any(g < 0 or g > 11 for g in grados):
            raise ValueError("Los grados van de 0 (Transición) a 11 (Once).")
        self.periodos, self.periodo = periodos, periodos[0]
        self.grados = grados or None
        self.grado = grados[0] if len(grados) == 1 else None
        return self


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
    periodos: list[int] = []  # [] en corridas viejas: solo `periodo`
    grados: list[int] = []  # [] = todos los grados (o solo `grado`)
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

    @field_validator("periodos", "grados", mode="before")
    @classmethod
    def _desde_texto(cls, valor):
        return _lista_enteros(valor)


class DocentePeriodo(BaseModel):
    docente_id: int | None  # None = el nombre del boletín no coincide con ningún docente de la base
    docente_nombre: str | None
    nombre_sapred: str  # tal cual lo trae el boletín


class DocenteMateriaPeriodos(BaseModel):
    """Una materia de un grupo, con su profesor en cada periodo importado."""

    sede_id: int
    sede_nombre: str
    grado: int
    curso: int | None
    area_id: int | None  # None = director de grupo
    area_codigo: str | None
    area_nombre: str
    asignado_anio: str | None  # el docente asignado para el año (panel docente, reportes)
    periodos: dict[int, DocentePeriodo] = {}
    cambia: bool = False  # no es el mismo profesor en todos los periodos
    sin_docente: bool = False  # en algún periodo el nombre no se pudo enlazar


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


# --- Módulo docente: mis cursos / mis estudiantes -----------------------------


class CursoDocente(BaseModel):
    sede_id: int
    sede_nombre: str
    grado: int
    nombre_grado: str
    curso: int | None
    nombre_grupo: str
    area_id: int | None
    area_nombre: str  # "Director de grupo" cuando area_id es None
    total_estudiantes: int


class EstudianteDocentePerfil(BaseModel):
    """Ficha acotada para el docente: solo lo que necesita para su trabajo,
    sin documentos ni datos de la ficha de matrícula (punto 6 del encargo)."""

    id: int
    documento: str
    nombre_completo: str
    genero: str | None
    fecha_nacimiento: dt.date | None
    grado: int
    nombre_grado: str
    curso: int | None
    nombre_grupo: str
    sede_id: int
    sede_nombre: str
    estado: str


class ClaseHoyDocente(BaseModel):
    bloque_horario_id: int
    hora: int
    sede_id: int
    grado: int
    curso: int | None
    area_id: int | None
    area_nombre: str
    nombre_grupo: str
    es_ahora: bool
    asistencia_tomada: bool


class InicioDocente(BaseModel):
    fecha: dt.date
    dia_nombre: str
    estado_jornada: str  # en_franja | descanso | fuera_jornada | fin_de_semana
    hora_actual: int | None
    clases: list[ClaseHoyDocente]


class HistorialAsistenciaItem(BaseModel):
    fecha: dt.date
    sede_id: int
    grado: int
    curso: int | None
    nombre_grupo: str
    area_id: int | None
    area_nombre: str
    presentes: int
    ausentes: int
    tardanzas: int
    excusas: int
    total: int


# --- Asistencia (por bloque de horario) --------------------------------------

ESTADOS_ASISTENCIA = {"presente", "ausente", "tardanza", "excusa"}


class AsistenciaRegistroItem(BaseModel):
    estudiante_id: int
    estado: str  # presente | ausente | tardanza | excusa
    observacion: str | None = None
    uuid_cliente: str | None = None


class AsistenciaRegistroLote(BaseModel):
    """Guarda de una vez toda la asistencia de un bloque (o de la toma
    general del director si area_id es None) — "marcar todos presentes y
    luego las excepciones" en una sola llamada."""

    sede_id: int
    grado: int
    curso: int | None = None
    area_id: int | None = None
    bloque_horario_id: int | None = None
    fecha: dt.date
    registros: list[AsistenciaRegistroItem]


class AsistenciaEstudianteVista(BaseModel):
    estudiante_id: int
    nombres: str
    apellidos: str
    documento: str
    estado: str | None = None  # None = todavía no se ha tomado
    observacion: str | None = None
    registrado_en: dt.datetime | None = None
    en_conflicto: bool = False


class AsistenciaBloqueVista(BaseModel):
    sede_id: int
    grado: int
    curso: int | None
    area_id: int | None
    area_nombre: str | None
    bloque_horario_id: int | None
    fecha: dt.date
    puede_registrar: bool
    motivo_solo_lectura: str | None = None  # p.ej. "fuera de la ventana de corrección"
    estudiantes: list[AsistenciaEstudianteVista]


class AsistenciaAnular(BaseModel):
    motivo: str


class AsistenciaRegistroResultado(BaseModel):
    estudiante_id: int
    estado: str
    registrado_en: dt.datetime
    en_conflicto: bool = False


class AsistenciaCorregir(BaseModel):
    estado: str
    observacion: str | None = None
    motivo: str


class PanelAsistenciaGrupo(BaseModel):
    """Un renglón del panel de coordinación: ¿el director de grupo ya marcó
    la asistencia general de hoy? (ver asistencia.panel_dia)."""

    sede_id: int
    sede_nombre: str
    grado: int
    curso: int | None
    nombre_grupo: str
    docente_id: int
    docente_nombre: str
    total_estudiantes: int
    registrados: int
    presentes: int
    ausentes: int
    tardanzas: int
    excusas: int
    estado: str  # pendiente | parcial | completo
    ultimo_registro: dt.datetime | None


class AlertaAsistenciaEstudiante(BaseModel):
    """Un estudiante con racha de inasistencia o excusas recientes (ver
    asistencia.alertas_estudiantes)."""

    estudiante_id: int
    nombre_completo: str
    documento: str
    sede_id: int
    grado: int
    curso: int | None
    nombre_grupo: str
    racha_ausente: int
    excusas_recientes: int
    ultima_fecha: dt.date
    ultimo_estado: str


# --- Observaciones -------------------------------------------------------------

TIPOS_OBSERVACION = {"academica", "convivencia", "general", "psicologia"}


class ObservacionCrear(BaseModel):
    estudiante_id: int
    tipo: str  # academica | convivencia | general | psicologia
    titulo: str | None = None
    detalle: str
    fecha: dt.date | None = None
    uuid_cliente: str | None = None


class SeguimientoCrear(BaseModel):
    nota: str


class SeguimientoVista(BaseModel):
    id: int
    autor_nombre: str
    nota: str
    creado_en: dt.datetime


class ObservacionVista(BaseModel):
    id: int
    estudiante_id: int
    estudiante_nombre: str
    estudiante_documento: str
    nombre_grupo: str
    tipo: str
    confidencial: bool
    titulo: str | None
    detalle: str
    autor_nombre: str
    fecha: dt.date
    creado_en: dt.datetime
    estado: str
    atendida_por_nombre: str | None = None
    atendida_en: dt.datetime | None = None
    nota_atencion: str | None = None
    # Solo se llena para quien tiene observaciones.ver_confidenciales o
    # seguimientos.gestionar (orientación) — ver crud.observacion_a_vista.
    seguimientos: list[SeguimientoVista] = []


class ObservacionEstado(BaseModel):
    estado: str  # abierta | atendida | cerrada
    nota_atencion: str | None = None


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


# --- Tendencia entre periodos (riesgo sostenido, no solo un período bajo) ---


class NotaPorPeriodo(BaseModel):
    periodo: int
    valor: float


class TendenciaAreaEstudiante(BaseModel):
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
    docente: str | None = None
    notas: list[NotaPorPeriodo]  # ordenadas por período, TODAS las que hay (no solo las bajas)
    riesgo_sostenido: bool  # todas sus notas registradas en esta área quedaron <= umbral_bajo


class ReporteTendencia(BaseModel):
    anio_lectivo: int
    umbral_bajo: float
    periodos_minimo: int
    total_combinaciones_evaluadas: int  # estudiante+área con >= periodos_minimo notas
    en_riesgo_sostenido: list[TendenciaAreaEstudiante]


# --- Análisis comparativo entre períodos (Período A -> Período B, genérico) ---
# Ver backend/app/comparacion_academica.py: el motor arma UNA lista de filas
# estudiante+área comparables y todo lo demás (resumen, por área/grupo/
# docente/sede, matriz de transición, alertas) se agrega desde esa misma
# lista, nunca con consultas repetidas — así cada indicador es auditable
# hasta el registro real que lo compone (nunca un porcentaje "mágico").

NIVELES_DESEMPENO = ("BAJO", "BASICO", "ALTO", "SUPERIOR")
CATEGORIAS_VARIACION = ("MEJORA_SIGNIFICATIVA", "MEJORA", "ESTABLE", "DESCENSO", "DESCENSO_SIGNIFICATIVO")


class PeriodoDisponible(BaseModel):
    anio_lectivo: int
    periodo: int
    revisiones: int  # cuántos RevisionBoletin tiene (indicador rápido de cobertura)


class ConfigComparacion(BaseModel):
    """Umbrales configurables, con los defaults acordados (escala MEN
    1.0-5.0, ya verificada contra los datos reales del colegio)."""

    escala_min: float = 1.0
    escala_max: float = 5.0
    nivel_bajo_hasta: float = 2.9
    nivel_basico_hasta: float = 3.9
    nivel_alto_hasta: float = 4.5  # de aquí hasta escala_max es SUPERIOR
    umbral_mejora_significativa: float = 1.0
    umbral_mejora: float = 0.3
    umbral_descenso: float = 0.3
    umbral_descenso_significativo: float = 1.0


class FilaComparacionAcademica(BaseModel):
    """Un estudiante + un área, en el grano más fino: la unidad de auditoría
    de todo el módulo. comparable=False cuando falta un extremo (nunca
    cuenta como empeoramiento — sección 18 del pedido)."""

    estudiante_id: int
    documento: str
    nombre_completo: str
    area_id: int
    area_codigo: str
    area_nombre: str
    sede_id: int
    sede_nombre: str
    grado: int
    nombre_grado: str
    curso: int | None
    nombre_grupo: str
    docente_id: int | None
    docente_nombre: str | None
    valor_base: float | None
    valor_comparado: float | None
    delta: float | None
    categoria_variacion: str | None
    nivel_base: str | None
    nivel_comparado: str | None
    comparable: bool


class ResumenComparacion(BaseModel):
    """Agregado a nivel ESTUDIANTE (el promedio de sus áreas comparables
    dentro del filtro actual), no a nivel fila: así un estudiante con 8
    materias no pesa 8 veces más que uno con 2 — coincide con la forma en
    que el pedido describe el resumen global ("824 estudiantes
    analizados")."""

    periodo_base: PeriodoDisponible
    periodo_comparado: PeriodoDisponible
    config: ConfigComparacion
    total_estudiantes: int
    estudiantes_comparables: int
    estudiantes_sin_comparar: int
    promedio_base: float | None
    promedio_comparado: float | None
    variacion_promedio: float | None
    mejoraron: int
    empeoraron: int
    estables: int
    pct_mejoraron: float
    pct_empeoraron: float
    pct_estables: float
    salieron_de_bajo: int
    entraron_a_bajo: int
    permanecen_en_bajo: int
    informe_texto: str
    # Población: quién entra en cada número (nunca un % sin su base).
    # "comparables" = nota en ambos períodos (el cambio sale de ellos);
    # "actual" = todos los que tienen nota en el período comparado (el
    # "cómo estamos hoy" sale de ellos, aunque no tengan período base).
    solo_en_base: int = 0
    solo_en_comparado: int = 0
    distribucion_base: dict[str, int] = {}
    distribucion_comparado: dict[str, int] = {}
    actual_evaluados: int = 0
    actual_promedio: float | None = None
    actual_n_bajo: int = 0
    actual_distribucion: dict[str, int] = {}
    sedes_sin_comparacion: list[str] = []
    grupos_sin_comparacion: list[str] = []
    # Problemas de los DATOS (no del cálculo) que la pantalla debe mostrar,
    # nunca esconder: p. ej. un grupo importado con un grado que no existe.
    avisos_datos: list[str] = []


class ComparacionPorArea(BaseModel):
    """total_evaluados/promedios/variación: filas COMPARABLES (nota en ambos
    períodos). actual_*: todas las filas con nota en el período comparado."""

    area_id: int
    area_codigo: str
    area_nombre: str
    total_evaluados: int
    promedio_base: float | None
    promedio_comparado: float | None
    variacion: float | None
    mejoraron: int
    empeoraron: int
    estables: int
    pct_mejoraron: float
    pct_empeoraron: float
    pct_estables: float
    n_bajo_base: int = 0
    n_bajo_comparado: int = 0
    actual_evaluados: int = 0
    actual_promedio: float | None = None
    actual_n_bajo: int = 0


class ComparacionPorGrupo(BaseModel):
    """También se usa por grado (sede_id=None si el grado junta varias
    sedes, curso=None). Mismas reglas de población que ResumenComparacion."""

    sede_id: int | None
    sede_nombre: str
    grado: int
    nombre_grado: str
    curso: int | None
    nombre_grupo: str
    total_estudiantes: int
    promedio_base: float | None
    promedio_comparado: float | None
    variacion: float | None
    mejoraron: int
    empeoraron: int
    estables: int
    pct_mejoraron: float
    pct_empeoraron: float
    pct_estables: float
    salieron_de_bajo: int
    entraron_a_bajo: int
    permanecen_en_bajo: int
    estudiantes_comparables: int = 0
    actual_evaluados: int = 0
    actual_promedio: float | None = None
    actual_n_bajo: int = 0


class ComparacionPorDocente(BaseModel):
    """Descriptivo de los resultados asociados al grupo/área del docente —
    NUNCA una evaluación de su desempeño (el motor no atribuye causalidad,
    ver comparacion_academica.py)."""

    docente_id: int
    docente_nombre: str
    area_id: int | None
    area_nombre: str | None
    grado: int | None
    nombre_grado: str | None
    curso: int | None
    total_evaluados: int
    promedio_base: float
    promedio_comparado: float
    variacion: float
    mejoraron: int
    empeoraron: int
    estables: int
    pct_mejoraron: float
    pct_empeoraron: float
    pct_estables: float
    salieron_de_bajo: int
    entraron_a_bajo: int
    permanecen_en_bajo: int


class ComparacionPorSede(BaseModel):
    sede_id: int
    sede_nombre: str
    total_estudiantes: int
    promedio_base: float | None
    promedio_comparado: float | None
    variacion: float | None
    pct_mejoraron: float
    pct_empeoraron: float
    pct_estables: float
    estudiantes_comparables: int = 0
    actual_evaluados: int = 0
    actual_promedio: float | None = None
    actual_n_bajo: int = 0


class EstudianteComparacion(BaseModel):
    """Un estudiante con el promedio de sus áreas comparables (la misma
    unidad que cuenta el resumen: "mejoraron 33" son exactamente estas
    filas, no filas estudiante+área)."""

    estudiante_id: int
    documento: str
    nombre_completo: str
    sede_id: int
    sede_nombre: str
    grado: int
    nombre_grado: str
    curso: int | None
    nombre_grupo: str
    promedio_base: float | None
    promedio_comparado: float | None
    delta: float | None
    categoria_variacion: str | None
    nivel_base: str | None
    nivel_comparado: str | None
    comparable: bool
    areas_comparables: int
    areas_en_bajo: list[str]  # nota del período comparado en nivel Bajo
    areas_bajaron: list[str]  # descenso (normal o significativo) en esa área
    areas_en_minima: list[str] = []  # nota mínima de la escala (1.0) = no presentó nada
    areas_actuales: int = 0  # materias con nota en el período comparado
    riesgo_retiro: str | None = None  # MUY_PROBABLE | POSIBLE (ver comparacion_academica._riesgo_retiro)
    motivo_retiro: str | None = None


class MateriaRiesgoAnio(BaseModel):
    """Una materia y lo que le falta para ganarla en el año (promedio de
    los PERIODOS_POR_ANIO períodos con el mismo peso)."""

    area_id: int
    area_nombre: str
    notas: list[NotaPorPeriodo]
    promedio: float  # de los períodos con nota
    necesita: float | None  # promedio que necesita en lo que falta para cerrar en la mínima (None = ya no falta nada)
    final: float | None  # solo cuando ya están todos los períodos
    categoria: str | None  # NO_RECUPERA | POSIBLE_PERDIDA | CUIDADO | None (va ganando)
    sin_cargar: bool = False  # la nota mínima es masiva en su grupo: parece nota no cargada


class EstudianteRiesgoAnio(BaseModel):
    estudiante_id: int
    documento: str
    nombre_completo: str
    sede_id: int
    sede_nombre: str
    grado: int
    nombre_grado: str
    curso: int | None
    nombre_grupo: str
    categoria: str  # la peor de sus materias
    periodos_con_nota: int
    materias: list[MateriaRiesgoAnio]  # solo las que tienen categoría, de la peor a la mejor


class RiesgoAnio(BaseModel):
    anio_lectivo: int
    hasta_periodo: int
    periodos_anio: int
    nota_minima: float
    nota_maxima: float
    umbral_posible_perdida: float
    total_estudiantes: int
    estudiantes: list[EstudianteRiesgoAnio]


class PuntoEvolucion(BaseModel):
    """Un período de la serie. *_cohorte = los MISMOS estudiantes en todos
    los períodos de la serie (promediando solo las áreas que tienen en
    todos): es la línea honesta de tendencia. *_todos = quien tenga nota en
    ese período (la población cambia si un período está incompleto)."""

    anio_lectivo: int
    periodo: int
    evaluados_todos: int
    promedio_todos: float | None
    distribucion_todos: dict[str, int]
    evaluados_cohorte: int
    promedio_cohorte: float | None
    distribucion_cohorte: dict[str, int]


class EstudianteDescensoConsecutivo(BaseModel):
    estudiante_id: int
    nombre_completo: str
    nombre_grupo: str
    sede_nombre: str
    valores: list[float]  # promedio en cada uno de los 3 últimos períodos


class EvolucionAcademica(BaseModel):
    anio_lectivo: int
    puntos: list[PuntoEvolucion]
    cohorte: int  # estudiantes presentes en todos los períodos de la serie
    descenso_consecutivo: list[EstudianteDescensoConsecutivo] | None  # None = menos de 3 períodos


class LecturaGeneral(BaseModel):
    """La frase que responde "¿estamos mejorando o empeorando?", calculada
    (umbrales en comparacion_academica.TENDENCIA_*)."""

    tendencia: str  # sube | baja | estable | sin_datos
    titulo: str
    frase: str


class Hallazgo(BaseModel):
    """Un hecho calculado, nunca redactado a mano: tipo decide el ícono y
    accion el drill-down que lo sustenta en pantalla."""

    tipo: str  # alerta | baja | sube | ok
    titulo: str
    detalle: str
    accion: dict[str, str | int | None] = {}  # ej. {"filtro": "area_id", "valor": 8} o {"cambio": "entraron_bajo"}
    evidencia: list[list[str]] = []  # filas [etiqueta, valor, ...] con los datos que lo sustentan


class PanoramaAcademico(BaseModel):
    """Todo lo que la pantalla de Resumen/Áreas/Grados necesita en UNA
    llamada (una sola pasada de comparar())."""

    resumen: ResumenComparacion
    lectura: LecturaGeneral
    evolucion: EvolucionAcademica
    areas: list[ComparacionPorArea]
    grados: list[ComparacionPorGrupo]
    grupos: list[ComparacionPorGrupo]
    sedes: list[ComparacionPorSede]
    hallazgos: list[Hallazgo]


class CeldaMatrizTransicion(BaseModel):
    nivel_base: str
    nivel_comparado: str
    cantidad: int


class MatrizTransicion(BaseModel):
    total_comparables: int
    celdas: list[CeldaMatrizTransicion]


class AlertaAcademica(BaseModel):
    tipo: str  # descenso_significativo | entro_a_bajo | permanece_en_bajo | mejora_significativa
    estudiante_id: int
    nombre_completo: str
    documento: str
    sede_nombre: str
    nombre_grupo: str
    area_nombre: str
    valor_base: float
    valor_comparado: float
    delta: float


# --- Evaluación por docente (evaluacion_docente.py) ---------------------------


class IndicadorDocente(BaseModel):
    clave: str  # promedio | bajo | variacion | brecha | pendientes
    nombre: str
    valor: float | None
    texto: str  # ya formateado: "3.12", "18%", "-0.24"...
    semaforo: str  # verde | amarillo | rojo | gris (sin datos suficientes)
    explicacion: str


class EstudianteEvidencia(BaseModel):
    estudiante_id: int
    nombre_completo: str
    documento: str
    nombre_grupo: str
    valor_base: float | None
    valor_comparado: float | None
    delta: float | None
    nivel_comparado: str | None


class PuntoAtencion(BaseModel):
    nivel: str  # rojo | amarillo | fortaleza
    titulo: str
    detalle: str
    area_nombre: str | None = None
    nombre_grupo: str | None = None
    estudiantes: list[EstudianteEvidencia] = []


class AsignacionEvaluada(BaseModel):
    """Una materia en un grupo, con los números que la describen."""

    docente_id: int | None
    docente_nombre: str | None
    area_id: int
    area_nombre: str
    sede_nombre: str
    grado: int
    curso: int | None
    nombre_grupo: str
    evaluados: int
    promedio_base: float | None
    promedio_comparado: float | None
    variacion: float | None
    n_bajo: int
    pct_bajo: float
    entraron_a_bajo: int
    salieron_de_bajo: int
    # Mismos estudiantes, sus OTRAS materias académicas (período comparado):
    # controla por "qué tan fuerte es el grupo". brecha = esta - otras.
    promedio_otras_materias: float | None
    brecha_grupo: float | None


class FichaDocenteResumen(BaseModel):
    docente_id: int
    docente_nombre: str
    areas: list[str]
    grupos: list[str]
    evaluados: int
    indicadores: list[IndicadorDocente]
    rojos: int
    amarillos: int
    puntos_atencion: int
    fortalezas: int
    dicta_actitudinal: bool
    promedio_actitudinal: float | None


class FichaDocente(FichaDocenteResumen):
    periodo_base: PeriodoDisponible
    periodo_comparado: PeriodoDisponible
    asignaciones: list[AsignacionEvaluada]
    actitudinal: list[AsignacionEvaluada]
    puntos: list[PuntoAtencion]
    fortalezas_detalle: list[PuntoAtencion]
    pendientes_por_tipo: dict[str, int]


class EstadoDocentes(BaseModel):
    """"¿Cómo estamos?" + la lista de docentes con su semáforo."""

    periodo_base: PeriodoDisponible
    periodo_comparado: PeriodoDisponible
    docentes_analizados: int
    con_rojo: int
    con_amarillo: int
    sin_alertas: int
    promedio_academico: float | None
    pct_bajo: float
    variacion: float | None
    pendientes_total: int
    promedio_actitudinal: float | None
    pct_bajo_actitudinal: float
    umbrales: list[str]  # cómo se pinta cada semáforo, en palabras
    informe_texto: str
    docentes: list[FichaDocenteResumen]


class EstadoActitudinal(BaseModel):
    """Desempeño Actitudinal (DESM): aparte de lo académico, por decisión del colegio."""

    periodo_base: PeriodoDisponible
    periodo_comparado: PeriodoDisponible
    evaluados: int
    promedio_base: float | None
    promedio_comparado: float | None
    variacion: float | None
    n_bajo: int
    pct_bajo: float
    grupos: list[AsignacionEvaluada]
    estudiantes_bajo: list[EstudianteEvidencia]
    estudiantes_descenso: list[EstudianteEvidencia]


class SerieAreaEstudiante(BaseModel):
    area_id: int
    area_codigo: str
    area_nombre: str
    notas: list[NotaPorPeriodo]
    variacion_reciente: float | None
    categoria_variacion_reciente: str | None


class PerfilAcademicoEstudiante(BaseModel):
    estudiante_id: int
    documento: str
    nombre_completo: str
    grado: int
    nombre_grado: str
    curso: int | None
    nombre_grupo: str
    anio_lectivo: int
    areas: list[SerieAreaEstudiante]


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
    # True cuando la diferencia de grupo es un ASCENSO (SAPRED tiene al
    # estudiante en un grado mayor al de SIMAC): no es un error de
    # digitación sino una promoción que ya ocurrió en la práctica y que la
    # matrícula debe corregir en el siguiente año (promoción anticipada).
    candidato_promocion_anticipada: bool = False


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
    candidatos_promocion_anticipada: int = 0


class ConciliacionResultado(BaseModel):
    generado_en: dt.datetime
    resumen: ConciliacionResumen
    estudiantes: list[ConciliacionEstudiante]
    grupos: list[ConciliacionGrupo]
    docentes: list[ConciliacionDocente] = []


class HallazgoConciliacion(BaseModel):
    id: int
    estudiante_id: int
    documento: str
    nombre_completo: str
    sede_id: int
    sede_nombre: str
    anio_lectivo: int
    periodo: int
    grado_simac: int
    curso_simac: int | None
    nombre_grupo_simac: str
    grado_sapred: int
    curso_sapred: int | None
    nombre_grupo_sapred: str
    es_promocion_anticipada: bool
    detectado_en: dt.datetime
    visto_en: dt.datetime
    resuelto: bool
    resuelto_en: dt.datetime | None = None
    resuelto_por: str | None = None
    nota: str | None = None


class HallazgoConciliacionResolver(BaseModel):
    resuelto_por: str | None = None
    nota: str | None = None


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


# --- Riesgo de promoción (materias perdidas) y alertas a coordinación ------


class MateriaPerdida(BaseModel):
    area_codigo: str
    area_nombre: str
    notas: list[NotaPorPeriodo]
    promedio: float
    # Quién dicta esa materia en el grupo del estudiante (asignación docente
    # del año). None si no hay asignación registrada — nunca se inventa.
    docente_nombre: str | None = None
    # perdida (< nota_minima) | en_riesgo (< nota_minima + 0.5) | aprobada
    estado: str = "perdida"


class RiesgoPromocion(BaseModel):
    estudiante_id: int
    anio_lectivo: int
    nota_minima: float
    periodos_con_notas: list[int]
    areas_evaluadas: int
    perdidas: list[MateriaPerdida]
    # TODAS las materias con nota (perdidas, en riesgo y aprobadas), de la
    # peor a la mejor — para mostrar el panorama completo, no solo lo perdido.
    materias: list[MateriaPerdida] = []


class AsistenciaResumen(BaseModel):
    dias: int  # ventana contada (últimos N días)
    ausencias: int
    tardanzas: int
    excusas: int


class EstudianteSeguimientoDocente(BaseModel):
    """Una fila de "mis estudiantes": cómo va en MI materia (profesor de
    área) o en todas (director de grupo), y sus faltas recientes."""

    id: int
    documento: str
    nombre_completo: str
    genero: str | None
    # En la materia con la que el docente entró al grupo (None si es director
    # de grupo sin área, o si no hay notas).
    notas_area: list[NotaPorPeriodo] = []
    promedio_area: float | None = None
    estado_area: str | None = None  # perdida | en_riesgo | aprobada
    # Solo para el director de grupo: panorama de TODAS las materias.
    materias_perdidas: list[MateriaPerdida] | None = None
    materias_en_riesgo: int | None = None
    asistencia: AsistenciaResumen


class SeguimientoGrupoDocente(BaseModel):
    es_director: bool
    area_id: int | None
    area_nombre: str | None
    anio_lectivo: int
    nota_minima: float
    periodos: list[int]
    estudiantes: list[EstudianteSeguimientoDocente]


class RendimientoEstudianteDocente(BaseModel):
    riesgo: RiesgoPromocion
    asistencia: AsistenciaResumen
    ultimas_faltas: list[dict]  # [{fecha, estado, area}] — ausencias/tardanzas/excusas recientes


class SolicitudPromocionOut(BaseModel):
    id: int
    estudiante_id: int
    estudiante_nombre: str
    estudiante_documento: str
    estudiante_grupo: str
    anio_lectivo: int
    grado_actual: int
    grado_destino: int
    motivos: list[str]
    materias_perdidas: int
    detalle: list[dict]
    justificacion: str
    solicitado_por_nombre: str
    solicitado_en: dt.datetime
    estado: str
    decidido_por_nombre: str | None
    decidido_en: dt.datetime | None
    nota_decision: str | None
    usada_en: dt.datetime | None


class EvaluacionPromocion(BaseModel):
    """¿Se puede generar la ficha con este grado, o hace falta permiso de
    coordinación? Lo usa la ficha antes de generar (y el backend lo vuelve a
    verificar al generar: la UI no es la que manda)."""

    estudiante_id: int
    anio_lectivo: int
    grado_actual: int
    grado_destino: int
    grado_esperado: int  # actual + 1 (lo normal si aprueba el año)
    motivos: list[str]  # perdidas | salto | retroceso — vacío = no requiere permiso
    requiere_autorizacion: bool
    puede_generar: bool
    solicitud: SolicitudPromocionOut | None  # la más reciente para ese grado destino y año
    riesgo: RiesgoPromocion


class SolicitudPromocionCrear(BaseModel):
    estudiante_id: int
    grado_destino: int
    justificacion: str


class SolicitudPromocionDecidir(BaseModel):
    aprobar: bool
    nota: str | None = None


class AlertaPromocionOut(BaseModel):
    id: int
    creado_en: dt.datetime
    estudiante_id: int
    estudiante_nombre: str
    estudiante_documento: str
    usuario_nombre: str | None
    anio_lectivo: int
    grado_actual: int
    grado_destino: int
    materias_perdidas: int
    detalle: list[dict]
    estado: str
    atendida_por_nombre: str | None = None
    atendida_en: dt.datetime | None = None
    nota_atencion: str | None = None


class AlertaAtender(BaseModel):
    nota: str | None = None


class DatosFichaCampos(BaseModel):
    campos: dict[str, str] = {}


# --- Diagnóstico de orientación/psicología (Excel por grado) ---------------


class CandidatoVinculo(BaseModel):
    id: int
    nombre_completo: str


class DiagnosticoMencionVista(BaseModel):
    id: int
    categoria: str
    texto: str
    nombre_detectado: str | None
    estudiante_id: int | None
    estudiante_nombre: str | None = None
    estudiante_documento: str | None = None
    vinculo_automatico: bool
    # alta | media | baja — qué tan segura es la vinculación (o por qué no
    # se hizo). candidatos: cuando confianza="media", los estudiantes
    # empatados entre los que habría que elegir. Uso interno de la app,
    # nunca aparece en el informe PDF.
    confianza: str
    texto_compartido: bool
    candidatos: list[CandidatoVinculo] = []
    # Si ya se abrió un Caso a partir de esta mención, su id — así la app
    # ofrece "Ver caso" en vez de "Abrir caso" (nunca dos veces el mismo).
    caso_id: int | None = None


class DiagnosticoGradoResumen(BaseModel):
    id: int
    sede_id: int
    grado: int
    curso: int | None
    grado_nombre: str
    hoja_excel: str
    fecha_diligenciado: dt.date | None
    periodo: str | None  # "Marzo 2026", derivado de fecha_diligenciado (nunca inventado)
    importado_en: dt.datetime
    n_en_lista: int | None
    n_asisten: int | None
    # Conteos SEPARADOS a propósito (nunca mezclarlos en la UI):
    total_menciones: int  # situaciones detectadas (una mención = una situación)
    estudiantes_mencionados: int  # personas distintas detrás de esas situaciones
    menciones_pendientes: int  # de esas situaciones, cuántas sin vincular a un estudiante real
    casos_abiertos: int
    casos_en_seguimiento: int
    seguimientos_pendientes: int  # casos con próximo seguimiento hoy o vencido
    es_version_actual: bool


class CasoSeguimientoCrear(BaseModel):
    fecha: dt.date | None = None
    tipo_atencion: str | None = None
    situacion: str
    accion_realizada: str | None = None
    compromisos: str | None = None
    observaciones: str | None = None
    proxima_fecha: dt.date | None = None


class CasoSeguimientoVista(BaseModel):
    id: int
    fecha: dt.date
    tipo_atencion: str | None
    situacion: str
    accion_realizada: str | None
    compromisos: str | None
    observaciones: str | None
    proxima_fecha: dt.date | None
    autor_nombre: str
    creado_en: dt.datetime


class CasoCrear(BaseModel):
    estudiante_id: int
    tipo: str
    titulo: str | None = None
    descripcion: str
    acciones: str | None = None
    observaciones: str | None = None
    fecha_apertura: dt.date | None = None
    proximo_seguimiento: dt.date | None = None
    mencion_origen_id: int | None = None  # se llenó desde "Abrir caso" en una mención


class CasoVista(BaseModel):
    id: int
    estudiante_id: int
    estudiante_nombre: str
    estudiante_documento: str
    grado_nombre: str
    tipo: str
    titulo: str | None
    estado: str
    fecha_apertura: dt.date
    proximo_seguimiento: dt.date | None
    origen: str  # importado | manual
    autor_nombre: str
    creado_en: dt.datetime
    total_seguimientos: int


class CasoDetalle(CasoVista):
    sede_id: int
    grado: int
    curso: int | None
    descripcion: str
    acciones: str | None
    observaciones: str | None
    cerrado_en: dt.datetime | None
    cerrado_por_nombre: str | None
    mencion_origen_id: int | None
    seguimientos: list[CasoSeguimientoVista]


class CasoEstadoCambiar(BaseModel):
    estado: str  # abierto | en_seguimiento | cerrado


class DiagnosticoGradoDetalle(DiagnosticoGradoResumen):
    no_asisten_texto: str | None
    desplazados_texto: str | None
    embarazadas_texto: str | None
    victimas_conflicto_texto: str | None
    dificultades_academicas: str | None
    dificultades_comportamiento: str | None
    acompanamiento_padres: str | None
    problemas_salud: str | None
    tematicas_trabajar: str | None
    estrategias_conflicto: str | None
    estrategias_aprendizaje: str | None
    resguardos_atendidos: str | None
    recomendaciones_docentes: str | None
    llamados_atencion: str | None
    orientacion_brindada: str | None
    transporte_escolar: str | None
    observaciones_generales: str | None
    director_grado_nombre: str | None
    orientador_escolar_nombre: str | None
    seguimiento_nota: str | None
    texto_crudo: str | None
    menciones: list[DiagnosticoMencionVista]
    historial: list[DiagnosticoGradoResumen]
    casos: list[CasoVista]


class DiagnosticoEstudianteMencion(DiagnosticoMencionVista):
    diagnostico_id: int
    grado: int
    curso: int | None
    grado_nombre: str
    fecha_diligenciado: dt.date | None
    periodo: str | None
    importado_en: dt.datetime


class DiagnosticoVincular(BaseModel):
    estudiante_id: int | None


class EstudianteBasicoOrientacion(BaseModel):
    """Lo mínimo para el encabezado del perfil de orientación — sin tener
    que pedir aparte /api/estudiantes/{id} (que trae fotos, historial...)."""

    id: int
    documento: str
    tipo_documento: str | None
    nombre_completo: str
    genero: str | None
    fecha_nacimiento: dt.date | None
    estado: str
    retirado: bool
    grado: int
    curso: int | None
    grupo: str
    sede_id: int | None
    sede_nombre: str | None


class DiagnosticoEstudianteResumen(BaseModel):
    menciones: list[DiagnosticoEstudianteMencion]
    casos: list[CasoVista]
    estudiante: EstudianteBasicoOrientacion | None = None


class GeneralesGrupo(BaseModel):
    """Lo general que reporta el director de cada grupo (no de un estudiante):
    qué temáticas trabajar, qué estrategias usa, qué resguardos atiende..."""

    diagnostico_id: int
    sede_id: int
    grado: int
    curso: int | None
    grado_nombre: str
    periodo: str | None
    director_grado_nombre: str | None
    tematicas_trabajar: str | None
    estrategias_conflicto: str | None
    estrategias_aprendizaje: str | None
    resguardos_atendidos: str | None
    recomendaciones_docentes: str | None
    orientacion_brindada: str | None
    acompanamiento_padres: str | None


class GrupoOrientacion(BaseModel):
    """Un grupo tal como lo ve orientación: sale de la MATRÍCULA real (así
    un grupo sin hoja en el Excel, ej. 6-6, igual se puede trabajar), con el
    diagnóstico vigente enganchado si existe. curso=None significa "todo el
    grado" cuando el Excel trae una sola hoja para el grado (Preescolar), o
    "estudiantes sin curso asignado" cuando no hay tal hoja — ver
    `grado_completo`."""

    sede_id: int
    grado: int
    curso: int | None
    grado_nombre: str
    grado_completo: bool  # True = la fila agrupa todas las secciones del grado
    n_estudiantes: int  # activos en matrícula
    diagnostico_id: int | None  # versión vigente del Excel, None si no hay hoja
    periodo: str | None
    fecha_diligenciado: dt.date | None
    estudiantes_mencionados: int
    menciones_pendientes: int
    casos_abiertos: int
    casos_en_seguimiento: int
    seguimientos_vencidos: int  # casos no cerrados con próximo seguimiento hoy o antes


class EstudianteOrientacion(BaseModel):
    id: int
    documento: str
    nombre_completo: str
    genero: str | None
    estado: str
    grupo: str
    # False = no está activo en este grupo según matrícula, pero aparece
    # porque el Excel lo menciona o tiene un caso abierto aquí (se retiró,
    # cambió de grupo...): se muestra igual para no esconder trabajo real.
    en_matricula_del_grupo: bool
    situaciones: list[str]  # categorías distintas detectadas en el Excel vigente
    total_situaciones: int
    casos_activos: int
    casos_total: int
    proximo_seguimiento: dt.date | None


class GrupoOrientacionDetalle(GrupoOrientacion):
    sede_nombre: str
    director_grado_nombre: str | None
    estudiantes: list[EstudianteOrientacion]
    casos: list[CasoVista]


class OrientacionResumen(BaseModel):
    """Conteos reales para el panel de arriba de la lista de diagnósticos —
    nunca estimados: cada número sale de una consulta directa."""

    diagnosticos: int
    casos_abiertos: int
    casos_en_seguimiento: int
    seguimientos_pendientes: int
