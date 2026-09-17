import datetime as dt

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import fechas
from .database import Base

GRADOS_NOMBRES = {
    0: "Preescolar",
    1: "Primero",
    2: "Segundo",
    3: "Tercero",
    4: "Cuarto",
    5: "Quinto",
    6: "Sexto",
    7: "Séptimo",
    8: "Octavo",
    9: "Noveno",
    10: "Décimo",
    11: "Once",
}

# Nombre de la division dentro de un grado (ej. "Sexto - Uno"), no es una
# seccion con identidad propia, solo un numero en palabras.
DIVISIONES_NOMBRES = {
    1: "Uno",
    2: "Dos",
    3: "Tres",
    4: "Cuatro",
    5: "Cinco",
    6: "Seis",
    7: "Siete",
    8: "Ocho",
}


class Sede(Base):
    __tablename__ = "sedes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    codigo_dane_sede: Mapped[str | None] = mapped_column(String(30), nullable=True)
    codigo_dane_consecutivo: Mapped[str | None] = mapped_column(String(30), nullable=True)
    institucion_centro_educativo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resguardo: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # Se detecta solo desde "INSTITUCIÓN Y/O CENTRO EDUCATIVO" al importar,
    # pero queda editable a mano por si algún caso puntual está mal
    # etiquetado en el Excel departamental.
    pertenece_ietaba: Mapped[bool] = mapped_column(Boolean, default=True)

    estudiantes: Mapped[list["Estudiante"]] = relationship(back_populates="sede")


class Estudiante(Base):
    __tablename__ = "estudiantes"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_estud: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    documento: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    tipo_documento: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lugar_expedicion_documento: Mapped[str | None] = mapped_column(String(150), nullable=True)
    primer_apellido: Mapped[str] = mapped_column(String(100))
    segundo_apellido: Mapped[str | None] = mapped_column(String(100), nullable=True)
    primer_nombre: Mapped[str] = mapped_column(String(100))
    segundo_nombre: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fecha_nacimiento: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    genero: Mapped[str | None] = mapped_column(String(5), nullable=True)
    grado: Mapped[int] = mapped_column(default=0)  # 0=Preescolar ... 11=Once
    curso: Mapped[int | None] = mapped_column(nullable=True)  # seccion dentro del grado: 6-1, 6-2, ...
    estado: Mapped[str] = mapped_column(String(30), default="ACTIVO")  # ACTIVO/RETIRADO/TRASLADADO/...
    observaciones: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # True = se encontró este documento en la otra fuente (Excel de matrícula);
    # False = se buscó y NO aparece (posible inconsistencia entre los dos Excel);
    # None = todavía no se ha podido cruzar (no hay una segunda fuente para su sede).
    verificado_matricula: Mapped[bool | None] = mapped_column(nullable=True)

    # True = la secretaría marcó a este estudiante como "posible retirado":
    # sigue apareciendo en el sistema, pero NO se cuenta en los pendientes de
    # boletín (ni se le crean nuevos) para que no ensucie el reporte "¿qué
    # falta?". No es un retiro formal (eso es estado="RETIRADO").
    posible_retirado: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    # True = marcado como "retirado" (ya se confirmó que se fue), pero SIN
    # retirarlo del sistema: sigue ACTIVO, se ve en la grilla con su etiqueta
    # y la marca se puede quitar. Siempre va junto con posible_retirado=True
    # (lo garantiza crud.actualizar_estudiante), así todo lo que ya excluye a
    # los posibles retirados de los pendientes también lo excluye a él.
    retirado: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    sede_id: Mapped[int | None] = mapped_column(ForeignKey("sedes.id"), nullable=True)
    sede: Mapped[Sede | None] = relationship(back_populates="estudiantes")

    fotos: Mapped[list["FotoEstudiante"]] = relationship(
        back_populates="estudiante", cascade="all, delete-orphan", order_by="FotoEstudiante.orden"
    )

    historial_documento: Mapped[list["HistorialDocumentoEstudiante"]] = relationship(
        cascade="all, delete-orphan", order_by="HistorialDocumentoEstudiante.vigente_hasta.desc()"
    )

    asistencias: Mapped[list["Asistencia"]] = relationship(
        back_populates="estudiante", cascade="all, delete-orphan"
    )

    @property
    def nombre_completo(self) -> str:
        partes = [self.primer_nombre, self.segundo_nombre, self.primer_apellido, self.segundo_apellido]
        return " ".join(p for p in partes if p)

    @property
    def activo(self) -> bool:
        return self.estado.upper() == "ACTIVO"

    @property
    def grupo(self) -> str:
        nombre_grado = GRADOS_NOMBRES.get(self.grado, str(self.grado))
        if not self.curso:
            return nombre_grado
        nombre_division = DIVISIONES_NOMBRES.get(self.curso, str(self.curso))
        return f"{nombre_grado} - {nombre_division}"


class FotoEstudiante(Base):
    """Documentos escaneados/fotografiados del estudiante: cantidad libre
    (ficha de matrícula página 1 y 2, cédulas de los padres, certificado de
    notas, boletín del colegio anterior, etc.).

    La mayoría se repiten cada año (matrícula, notas, boletín), así que van
    ligados a un año lectivo. Pero otros no cambian año tras año (documento
    de identidad del estudiante, cédulas de los padres) — esos quedan con
    anio_lectivo=None ("documento permanente") y se muestran siempre, hasta
    que alguien suba uno nuevo porque de verdad cambió (ej. el estudiante
    pasa de T.I. a C.C.)."""

    __tablename__ = "fotos_estudiante"

    id: Mapped[int] = mapped_column(primary_key=True)
    estudiante_id: Mapped[int] = mapped_column(ForeignKey("estudiantes.id"))
    etiqueta: Mapped[str] = mapped_column(String(80), default="Documento")
    anio_lectivo: Mapped[int | None] = mapped_column(nullable=True)
    nombre_archivo: Mapped[str] = mapped_column(String(255))
    orden: Mapped[int] = mapped_column(default=0)
    subido_en: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    estudiante: Mapped["Estudiante"] = relationship(back_populates="fotos")

    @property
    def es_pdf(self) -> bool:
        return self.nombre_archivo.lower().endswith(".pdf")


class HistorialDocumentoEstudiante(Base):
    """Cada vez que cambia el tipo o número de documento del estudiante (ej.
    Registro Civil -> Tarjeta de Identidad -> Cédula, a medida que crece) se
    guarda aquí el valor ANTERIOR antes de sobrescribirlo, para no perder el
    dato con el que se expidieron constancias o certificados previos."""

    __tablename__ = "historial_documento_estudiante"

    id: Mapped[int] = mapped_column(primary_key=True)
    estudiante_id: Mapped[int] = mapped_column(ForeignKey("estudiantes.id"))
    tipo_documento: Mapped[str | None] = mapped_column(String(50), nullable=True)
    documento: Mapped[str | None] = mapped_column(String(30), nullable=True)
    vigente_hasta: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    estudiante: Mapped["Estudiante"] = relationship(back_populates="historial_documento")


class ConstanciaGenerada(Base):
    """Registro histórico de cada constancia generada: queda guardado el
    documento (Word y PDF, si se pudo convertir) tal como se entregó ese
    día, para poder consultarlo después sin volver a generarlo (y sin poder
    modificarlo)."""

    __tablename__ = "constancias_generadas"

    id: Mapped[int] = mapped_column(primary_key=True)
    estudiante_id: Mapped[int] = mapped_column(ForeignKey("estudiantes.id"))
    generado_en: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    fecha_expedicion: Mapped[dt.date] = mapped_column(Date)
    proposito: Mapped[str] = mapped_column(String(200))
    jornada: Mapped[str] = mapped_column(String(50))
    anio_escolar: Mapped[int] = mapped_column()
    lugar_expedicion: Mapped[str] = mapped_column(String(150))
    tipo_documento_usado: Mapped[str | None] = mapped_column(String(50), nullable=True)
    archivo_docx: Mapped[str] = mapped_column(String(255))
    archivo_pdf: Mapped[str | None] = mapped_column(String(255), nullable=True)

    estudiante: Mapped["Estudiante"] = relationship()


class Docente(Base):
    """Profesores del colegio, importados de la lista oficial (SAPRED)."""

    __tablename__ = "docentes"

    id: Mapped[int] = mapped_column(primary_key=True)
    documento: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    nombre_completo: Mapped[str] = mapped_column(String(200))
    fecha_nacimiento: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(60), nullable=True)
    email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    direccion: Mapped[str | None] = mapped_column(String(150), nullable=True)


class Area(Base):
    """Catálogo de áreas/materias (ej. MATE - Matemáticas). El currículo
    varía por grado, así que qué áreas aplican a qué grado se maneja aparte
    en AreaGrado, no se asume aquí."""

    __tablename__ = "areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)  # ej: "MATE"
    nombre: Mapped[str] = mapped_column(String(100))  # ej: "Matemáticas"


class AreaGrado(Base):
    """A qué grado aplica cada área. Un área puede aplicar a varios grados,
    y un grado puede tener varias áreas — se configura, no se hardcodea."""

    __tablename__ = "areas_grado"
    __table_args__ = (UniqueConstraint("area_id", "grado", name="uq_area_grado"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"))
    grado: Mapped[int]

    area: Mapped[Area] = relationship()


class AsignacionDocente(Base):
    """A qué grupo (sede + grado + división) está asignado un docente, por
    año lectivo. Cuando area_id es NULL, el docente enseña TODO el grupo
    (típico de las sedes rurales con un solo maestro). Cuando area_id tiene
    valor, el docente enseña solo esa materia dentro del grupo (típico de
    secundaria en la sede principal, con un profesor por materia) — puede
    haber varias filas para un mismo grupo, una por área."""

    __tablename__ = "asignaciones_docente"

    id: Mapped[int] = mapped_column(primary_key=True)
    docente_id: Mapped[int] = mapped_column(ForeignKey("docentes.id"))
    sede_id: Mapped[int] = mapped_column(ForeignKey("sedes.id"))
    grado: Mapped[int]
    curso: Mapped[int | None] = mapped_column(nullable=True)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"), nullable=True)
    anio_lectivo: Mapped[int] = mapped_column(default=lambda: dt.date.today().year)

    docente: Mapped[Docente] = relationship()
    sede: Mapped["Sede"] = relationship()
    area: Mapped[Area | None] = relationship()


class RevisionBoletin(Base):
    """Contenedor de la revisión de un grupo en un período: agrupa los
    pendientes puntuales (PendienteBoletin). Los campos completo/
    materias_faltantes/observaciones_completas/estudiantes_pendientes se
    mantienen por ahora para no romper la vista actual mientras el backend
    (Fase 3) pasa a calcular el estado desde PendienteBoletin en vez de
    depender de que alguien los escriba a mano."""

    __tablename__ = "revisiones_boletin"
    __table_args__ = (
        UniqueConstraint("sede_id", "grado", "curso", "anio_lectivo", "periodo", name="uq_revision_grupo_anio"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sede_id: Mapped[int] = mapped_column(ForeignKey("sedes.id"))
    grado: Mapped[int]
    curso: Mapped[int | None] = mapped_column(nullable=True)
    anio_lectivo: Mapped[int] = mapped_column(default=lambda: dt.date.today().year)
    periodo: Mapped[int] = mapped_column(default=1)  # periodo academico (1,2,3,4)

    completo: Mapped[bool] = mapped_column(default=False)
    materias_faltantes: Mapped[str | None] = mapped_column(String(300), nullable=True)
    observaciones_completas: Mapped[bool] = mapped_column(default=False)
    notas: Mapped[str | None] = mapped_column(String(500), nullable=True)
    estudiantes_pendientes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    revisado_por: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revisado_en: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    pendientes: Mapped[list["PendienteBoletin"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )


class PendienteBoletin(Base):
    """Un pendiente puntual y consultable dentro de una revisión: en qué
    área, para qué estudiante (o para todo el grupo si es None), y de qué
    tipo. Reemplaza a los textos libres materias_faltantes/
    estudiantes_pendientes con filas que sí se pueden agregar y contar
    (por sede, por área, por docente, etc.)."""

    __tablename__ = "pendientes_boletin"

    id: Mapped[int] = mapped_column(primary_key=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey("revisiones_boletin.id"))
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"), nullable=True)
    estudiante_id: Mapped[int | None] = mapped_column(ForeignKey("estudiantes.id"), nullable=True)
    tipo: Mapped[str] = mapped_column(String(20), default="nota")  # nota | concepto | observacion
    detalle: Mapped[str | None] = mapped_column(String(300), nullable=True)
    resuelto: Mapped[bool] = mapped_column(default=False)
    creado_en: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    resuelto_en: Mapped[dt.datetime | None] = mapped_column(nullable=True)

    revision: Mapped[RevisionBoletin] = relationship(back_populates="pendientes")
    area: Mapped[Area | None] = relationship()
    estudiante: Mapped[Estudiante | None] = relationship()


class NotaSapred(Base):
    """El valor real de una nota que SÍ está registrada en SAPRED (lo
    contrario de PendienteBoletin, que registra lo que falta). Se llena
    aparte, sin tocar la lógica de pendientes que ya funciona — sirve para
    auditorías que necesitan el valor real (ej. detectar bajo rendimiento),
    no solo si falta o no."""

    __tablename__ = "notas_sapred"
    __table_args__ = (
        UniqueConstraint("revision_id", "area_id", "estudiante_id", name="uq_nota_revision_area_estudiante"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey("revisiones_boletin.id"))
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"))
    estudiante_id: Mapped[int] = mapped_column(ForeignKey("estudiantes.id"))
    valor: Mapped[str] = mapped_column(String(20))  # tal cual viene de SAPRED, ej "1.2", "3.1"
    # Nombre del estudiante tal cual lo reporta SAPRED en este bloque, para
    # poder comparar contra el nombre local (conciliación SIMAC/SAPRED) sin
    # tener que volver a parsear el PDF/HTML. Nullable: notas importadas
    # antes de que existiera este campo se quedan sin él.
    nombre_sapred: Mapped[str | None] = mapped_column(String(200), nullable=True)
    actualizado_en: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    revision: Mapped[RevisionBoletin] = relationship()
    area: Mapped[Area] = relationship()
    estudiante: Mapped[Estudiante] = relationship()


class TextoBoletin(Base):
    """El texto real del CONCEPTO de una área (o de la OBSERVACIÓN del
    director de grupo) tal como sale en el reporte "Boletín informativo" de
    SAPRED. Espejo de NotaSapred pero para texto libre, no para la nota
    numérica. Cuando `texto` es NULL o vacío, significa "el reporte trae la
    fila pero sin concepto/observación" — eso también se marca como
    PendienteBoletin (tipo concepto/observacion), igual que una nota que
    falta. area_id NULL = observación del director de grupo (no es de un
    área)."""

    __tablename__ = "textos_boletin"
    __table_args__ = (
        UniqueConstraint(
            "revision_id", "area_id", "estudiante_id", "tipo", name="uq_texto_boletin"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey("revisiones_boletin.id"))
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"), nullable=True)
    estudiante_id: Mapped[int] = mapped_column(ForeignKey("estudiantes.id"))
    tipo: Mapped[str] = mapped_column(String(20))  # concepto | observacion
    texto: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    nombre_sapred: Mapped[str | None] = mapped_column(String(200), nullable=True)
    actualizado_en: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    revision: Mapped["RevisionBoletin"] = relationship()
    area: Mapped["Area | None"] = relationship()
    estudiante: Mapped["Estudiante"] = relationship()


class ImportacionBoletinPdf(Base):
    """Historial de cada PDF del reporte "Boletín informativo" importado a
    mano (Boletines > SAPRED > Importar > Boletín informativo). Mismo patrón
    que ImportacionSapredPdf, pero para el flujo de conceptos/observaciones/
    docentes por materia en vez del de notas."""

    __tablename__ = "importaciones_boletin_pdf"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre_archivo: Mapped[str] = mapped_column(String(255))
    importado_en: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    total_conceptos_pendientes: Mapped[int] = mapped_column(default=0)
    total_observaciones_pendientes: Mapped[int] = mapped_column(default=0)
    total_estudiantes_no_encontrados: Mapped[int] = mapped_column(default=0)
    detalle_bloques: Mapped[str | None] = mapped_column(String(8000), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ImportacionSapredPdf(Base):
    """Historial de cada PDF de SAPRED importado a mano (Boletines > SAPRED >
    Importar > Importación manual). Antes de esto el resultado solo se veía
    en pantalla y se perdía apenas se cerraba el aviso o se recargaba la
    página — esto guarda ese mismo resultado (ImportarSapredResultado) para
    poder consultarlo después. No duplica nada de lo que ya se guarda en
    NotaSapred/PendienteBoletin, es solo el registro de "qué se importó y
    cuándo"."""

    __tablename__ = "importaciones_sapred_pdf"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre_archivo: Mapped[str] = mapped_column(String(255))
    importado_en: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    total_pendientes_creados: Mapped[int] = mapped_column(default=0)
    total_estudiantes_no_encontrados: Mapped[int] = mapped_column(default=0)
    # Lista de bloques (uno por curso reconocido en el PDF), serializada como
    # JSON en texto — mismo patrón que AuditoriaSapred.detalle_sedes de abajo.
    detalle_bloques: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)  # si el PDF no se pudo leer


class AuditoriaSapred(Base):
    """Una corrida de la auditoría de notas contra SAPRED: qué se pidió
    revisar, en qué va, y el resumen final. Los resultados en sí (qué nota
    falta, a quién) NO se duplican aquí — se guardan como PendienteBoletin,
    igual que cualquier otro pendiente del módulo de Boletines. Esta tabla
    es solo para mostrar progreso en vivo y guardar el historial de corridas."""

    __tablename__ = "auditorias_sapred"

    id: Mapped[int] = mapped_column(primary_key=True)
    creado_en: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    terminado_en: Mapped[dt.datetime | None] = mapped_column(nullable=True)

    # Filtros con los que se pidió la auditoría.
    anio_lectivo: Mapped[int] = mapped_column(default=lambda: dt.date.today().year)
    periodo: Mapped[int] = mapped_column(default=1)
    grado: Mapped[int | None] = mapped_column(nullable=True)  # None = todos los grados
    sede_ids: Mapped[str | None] = mapped_column(String(500), nullable=True)  # ids separados por coma, None = todas

    # Qué reporte de SAPRED audita/genera esta corrida:
    #   'notas'       = "Consolidado de Asignaturas por periodo" (notas numéricas)
    #   'boletin'     = "Boletín informativo" (conceptos, observaciones, docente por materia)
    #   'ambos'       = Consolidado y luego Boletín, encadenados
    #   'boletin_pdf' = genera el boletín general (PDF) de cada sede y lo guarda
    #                   en disco — NO importa nada, solo produce archivos.
    tipo: Mapped[str] = mapped_column(String(20), default="notas")

    # Solo para tipo == 'boletin_pdf': carpeta (relativa a backend/) donde
    # quedaron los PDF de esta corrida, uno por sede.
    carpeta_salida: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # estado: pendiente | esperando_login | en_proceso | completada | error
    estado: Mapped[str] = mapped_column(String(30), default="pendiente")
    sede_actual: Mapped[str | None] = mapped_column(String(150), nullable=True)
    grado_actual: Mapped[str | None] = mapped_column(String(30), nullable=True)
    sedes_totales: Mapped[int] = mapped_column(default=0)
    sedes_completadas: Mapped[int] = mapped_column(default=0)
    estudiantes_revisados: Mapped[int] = mapped_column(default=0)
    pendientes_encontrados: Mapped[int] = mapped_column(default=0)

    # Detalle por sede/error, como JSON en texto (ej. [{"sede": "...", "estado":
    # "advertencia", "detalle": "..."}]) — se lee/escribe como lista de dicts
    # desde crud.py, no hace falta una tabla aparte para esto.
    detalle_sedes: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class EstudianteSapredSinCoincidencia(Base):
    """Un estudiante que SAPRED reporta en un curso, pero cuyo documento no
    existe en nuestra base local (SIMAC/matrícula) — nunca se crea el
    estudiante ni se inventa nada, solo queda como observación consultable
    para que alguien la revise (puede ser un documento mal digitado en
    cualquiera de las dos fuentes, un estudiante nuevo sin matricular aquí
    todavía, o que corresponde a otra sede)."""

    __tablename__ = "sapred_sin_coincidencia"
    __table_args__ = (
        UniqueConstraint(
            "documento", "sede_id", "grado", "curso", "periodo", "anio_lectivo",
            name="uq_sapred_sin_coincidencia",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    documento: Mapped[str] = mapped_column(String(30))
    nombre_sapred: Mapped[str] = mapped_column(String(200))
    sede_id: Mapped[int] = mapped_column(ForeignKey("sedes.id"))
    grado: Mapped[int]
    curso: Mapped[int | None] = mapped_column(nullable=True)
    periodo: Mapped[int]
    anio_lectivo: Mapped[int]
    tiene_notas: Mapped[bool] = mapped_column(default=False)  # True = SAPRED ya tiene notas de este estudiante (más urgente de revisar)
    primera_vez_visto: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    ultima_vez_visto: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    resuelto: Mapped[bool] = mapped_column(default=False)

    sede: Mapped["Sede"] = relationship()


class Asistencia(Base):
    __tablename__ = "asistencias"
    __table_args__ = (
        UniqueConstraint("estudiante_id", "fecha", name="uq_asistencia_estudiante_fecha"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    estudiante_id: Mapped[int] = mapped_column(ForeignKey("estudiantes.id"))
    fecha: Mapped[dt.date] = mapped_column(Date, default=fechas.hoy_colombia)
    presente: Mapped[bool] = mapped_column(Boolean, default=True)
    registrado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    estudiante: Mapped[Estudiante] = relationship(back_populates="asistencias")


# --- Horarios -------------------------------------------------------------
# El horario oficial de la Sede #01 vive en un Word (un cuadro por docente).
# Se importa a BloqueHorario, que enlaza con los registros ya existentes
# (Docente, Sede, Area) y con la convención de grupo grado+curso que usan
# Estudiante/AsignacionDocente — no se crea un catálogo paralelo de nada.


class BloqueHorario(Base):
    """Una clase concreta en la rejilla semanal: un docente, un día y una
    hora fija, con su grupo (grado + curso) y su área. area_id puede quedar
    en NULL si el rótulo del archivo no se pudo emparejar con el catálogo
    Area; area_label conserva SIEMPRE el texto tal cual vino del Word (es la
    fuente de verdad de lo que dice el horario oficial). aula queda para el
    futuro: el archivo actual no trae salón."""

    __tablename__ = "bloques_horario"
    __table_args__ = (
        UniqueConstraint(
            "anio_lectivo", "docente_id", "dia", "hora", name="uq_bloque_docente_dia_hora"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    anio_lectivo: Mapped[int] = mapped_column(default=lambda: dt.date.today().year)
    docente_id: Mapped[int] = mapped_column(ForeignKey("docentes.id"))
    sede_id: Mapped[int] = mapped_column(ForeignKey("sedes.id"))
    grado: Mapped[int]
    curso: Mapped[int | None] = mapped_column(nullable=True)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"), nullable=True)
    area_label: Mapped[str] = mapped_column(String(80))
    dia: Mapped[int]  # 1 = Lunes ... 5 = Viernes
    hora: Mapped[int]  # 1 ... 6 (índice de franja, ver horario.FRANJAS)
    aula: Mapped[str | None] = mapped_column(String(40), nullable=True)
    origen: Mapped[str] = mapped_column(String(120), default="")

    # Cuando dos archivos/cuadros ponen dos docentes en el mismo grupo+día+hora,
    # los DOS bloques se guardan (no se descarta nada al importar). El
    # administrativo confirma cuál es el oficial: el elegido queda 'activo', los
    # otros 'descartado' (siguen visibles, tachados, pero no cuentan para
    # disponibilidad/reemplazos). 'conflicto_revisado' marca que ya se miró
    # (incluida la opción "dejar los dos").
    estado: Mapped[str] = mapped_column(String(20), default="activo")  # activo | descartado
    conflicto_revisado: Mapped[bool] = mapped_column(Boolean, default=False)
    resuelto_por: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resuelto_en: Mapped[dt.datetime | None] = mapped_column(nullable=True)

    docente: Mapped[Docente] = relationship()
    sede: Mapped["Sede"] = relationship()
    area: Mapped[Area | None] = relationship()


class AusenciaDocente(Base):
    """Registro de que un docente no asiste un día. Las clases afectadas NO
    se guardan aquí: se deducen de su BloqueHorario para ese día (ver
    horario.clases_afectadas)."""

    __tablename__ = "ausencias_docente"
    __table_args__ = (
        UniqueConstraint("docente_id", "fecha", name="uq_ausencia_docente_fecha"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    docente_id: Mapped[int] = mapped_column(ForeignKey("docentes.id"))
    fecha: Mapped[dt.date] = mapped_column(Date)
    motivo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    registrado_por: Mapped[str | None] = mapped_column(String(100), nullable=True)
    registrado_en: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    docente: Mapped[Docente] = relationship()


class Reemplazo(Base):
    """Un reemplazo para una clase de un día concreto. Guarda todo lo que
    describe la clase cubierta (grupo, área, hora) además del bloque de
    origen, para que cancelar o cambiar el reemplazo nunca toque el horario
    original. compatibilidad/razones son la foto del cálculo al momento de
    asignar (puntuación transparente, no una caja negra)."""

    __tablename__ = "reemplazos"

    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[dt.date] = mapped_column(Date)
    dia: Mapped[int]
    hora: Mapped[int]
    grado: Mapped[int]
    curso: Mapped[int | None] = mapped_column(nullable=True)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"), nullable=True)
    area_label: Mapped[str] = mapped_column(String(80), default="")

    docente_ausente_id: Mapped[int] = mapped_column(ForeignKey("docentes.id"))
    docente_reemplazo_id: Mapped[int | None] = mapped_column(
        ForeignKey("docentes.id"), nullable=True
    )
    bloque_horario_id: Mapped[int | None] = mapped_column(
        ForeignKey("bloques_horario.id"), nullable=True
    )
    ausencia_id: Mapped[int | None] = mapped_column(
        ForeignKey("ausencias_docente.id"), nullable=True
    )

    estado: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente | asignado | cancelado
    compatibilidad: Mapped[int | None] = mapped_column(nullable=True)
    razones: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # JSON
    asignado_por: Mapped[str | None] = mapped_column(String(100), nullable=True)
    creado_en: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    actualizado_en: Mapped[dt.datetime] = mapped_column(
        default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    docente_ausente: Mapped[Docente] = relationship(foreign_keys=[docente_ausente_id])
    docente_reemplazo: Mapped[Docente | None] = relationship(foreign_keys=[docente_reemplazo_id])
    bloque_horario: Mapped[BloqueHorario | None] = relationship()
    area: Mapped[Area | None] = relationship()


# --- Índices ----------------------------------------------------------------
# Se declaran aquí, en el modelo, para que haya una sola fuente: create_all
# los crea en una base nueva y migraciones.asegurar_indices() agrega a una
# base existente los que falten.

# Consultas por grupo (sede + grado + curso), las más frecuentes de la app.
Index("ix_estudiantes_grupo", Estudiante.sede_id, Estudiante.grado, Estudiante.curso)
Index("ix_asignaciones_docente_anio", AsignacionDocente.docente_id, AsignacionDocente.anio_lectivo)
Index(
    "ix_asignaciones_grupo",
    AsignacionDocente.sede_id, AsignacionDocente.grado, AsignacionDocente.curso, AsignacionDocente.anio_lectivo,
)

# Columnas hijas de claves foráneas: con foreign_keys=ON, borrar un padre
# busca sus hijos, y sin índice eso es un recorrido completo de la tabla.
Index("ix_fotos_estudiante_estudiante", FotoEstudiante.estudiante_id)
Index("ix_historial_documento_estudiante", HistorialDocumentoEstudiante.estudiante_id)
Index("ix_constancias_estudiante", ConstanciaGenerada.estudiante_id)
Index("ix_pendientes_boletin_revision", PendienteBoletin.revision_id)
Index("ix_pendientes_boletin_estudiante", PendienteBoletin.estudiante_id)
Index("ix_notas_sapred_estudiante", NotaSapred.estudiante_id)
Index("ix_textos_boletin_estudiante", TextoBoletin.estudiante_id)
Index("ix_reemplazos_bloque", Reemplazo.bloque_horario_id)
Index("ix_reemplazos_ausencia", Reemplazo.ausencia_id)

# En SQLite dos NULL nunca "chocan" dentro de un UNIQUE, así que las
# restricciones que incluyen curso (NULL = grupo único de sede rural) o
# area_id (NULL = observación del director de grupo) no impedían duplicados
# en esos casos. Estos índices únicos sobre COALESCE(...) sí los impiden.
# Verificado el 11/09/2026: 0 duplicados en la base real.
Index(
    "uq_revision_grupo_anio_nn",
    RevisionBoletin.sede_id, RevisionBoletin.grado, func.coalesce(RevisionBoletin.curso, -1),
    RevisionBoletin.anio_lectivo, RevisionBoletin.periodo,
    unique=True,
)
Index(
    "uq_sapred_sin_coincidencia_nn",
    EstudianteSapredSinCoincidencia.documento, EstudianteSapredSinCoincidencia.sede_id,
    EstudianteSapredSinCoincidencia.grado, func.coalesce(EstudianteSapredSinCoincidencia.curso, -1),
    EstudianteSapredSinCoincidencia.periodo, EstudianteSapredSinCoincidencia.anio_lectivo,
    unique=True,
)
Index(
    "uq_texto_boletin_nn",
    TextoBoletin.revision_id, func.coalesce(TextoBoletin.area_id, -1), TextoBoletin.estudiante_id, TextoBoletin.tipo,
    unique=True,
)


# --- Identidad y sesiones (Fase 2) ------------------------------------------
# Solo identidad: quién es cada persona y si su sesión sigue viva. Los roles y
# permisos llegan en la fase siguiente, en sus propias tablas; por eso aquí NO
# hay ninguna columna de rol (sería una segunda fuente de verdad).


class Usuario(Base):
    """Una persona que puede entrar al sistema. Cuando es un profesor, se
    enlaza con el Docente que YA existe (docente_id) en vez de repetir sus
    datos: la tabla docentes sigue siendo la autoridad de los profesores."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    documento: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(150), unique=True, nullable=True)
    nombre: Mapped[str] = mapped_column(String(200))
    clave_hash: Mapped[str] = mapped_column(String(255))  # scrypt, nunca la clave

    # activo = puede entrar; inactivo = deshabilitado por la administración;
    # bloqueado = reservado para bloqueos manuales. Al salir de "activo" se
    # revocan sus sesiones.
    estado: Mapped[str] = mapped_column(String(20), default="activo")
    debe_cambiar_clave: Mapped[bool] = mapped_column(Boolean, default=True)

    docente_id: Mapped[int | None] = mapped_column(ForeignKey("docentes.id"), unique=True, nullable=True)

    ultimo_acceso: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    intentos_fallidos: Mapped[int] = mapped_column(default=0)
    bloqueado_hasta: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    creado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)
    actualizado_en: Mapped[dt.datetime] = mapped_column(
        DateTime, default=fechas.ahora_utc, onupdate=fechas.ahora_utc
    )
    desactivado_en: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    docente: Mapped["Docente | None"] = relationship()


class Dispositivo(Base):
    """Un equipo o celular desde el que alguien entró. Sirve para mostrar
    "mis dispositivos" y para revocar el acceso de uno solo. No se guarda
    ninguna huella del aparato (nada de fingerprinting): el id lo genera el
    cliente o el servidor, y la seguridad la dan los tokens, no este id."""

    __tablename__ = "dispositivos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    nombre: Mapped[str] = mapped_column(String(120), default="Dispositivo")
    confiable: Mapped[bool] = mapped_column(Boolean, default=False)
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)
    ultimo_acceso: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    ultima_ip: Mapped[str | None] = mapped_column(String(60), nullable=True)
    revocado_en: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    usuario: Mapped["Usuario"] = relationship()


class Sesion(Base):
    """Una sesión abierta en un dispositivo. Del token de renovación solo se
    guarda su SHA-256 (nunca el token). `refresh_hash_anterior` conserva el
    hash del token recién rotado: si alguien lo vuelve a presentar pasada la
    ventana de gracia, es que se lo copiaron y la sesión se revoca."""

    __tablename__ = "sesiones"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    dispositivo_id: Mapped[str] = mapped_column(ForeignKey("dispositivos.id"))

    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    refresh_hash_anterior: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rotada_en: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    rotaciones: Mapped[int] = mapped_column(default=0)

    confiable: Mapped[bool] = mapped_column(Boolean, default=False)  # "confiar en este dispositivo"
    creada_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)
    ultimo_uso: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)
    expira_en: Mapped[dt.datetime] = mapped_column(DateTime)  # se extiende con el uso
    expira_absoluta_en: Mapped[dt.datetime] = mapped_column(DateTime)  # tope, aunque se use

    revocada_en: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_revocacion: Mapped[str | None] = mapped_column(String(60), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(60), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)

    usuario: Mapped["Usuario"] = relationship()
    dispositivo: Mapped["Dispositivo"] = relationship()


Index("ix_dispositivos_usuario", Dispositivo.usuario_id)
Index("ix_sesiones_usuario_activas", Sesion.usuario_id, Sesion.revocada_en)
Index("ix_sesiones_dispositivo", Sesion.dispositivo_id)
# Para detectar la reutilización de un token ya rotado hay que poder buscarlo.
Index("ix_sesiones_refresh_anterior", Sesion.refresh_hash_anterior)


# --- Roles y permisos (Fase 3) -----------------------------------------------
# Solo la estructura RBAC: qué rol tiene qué permiso, y qué rol tiene cada
# usuario. Los códigos de permiso los define app/permisos.py; aquí solo se
# guarda la asignación, que es lo que edita el administrador. Ningún endpoint
# existente cambia de comportamiento por estas tablas: eso es la fase que
# sigue a esta.


class Rol(Base):
    """Un rol del sistema. Los 5 roles del colegio nacen con es_sistema=True
    (no se pueden borrar ni desactivar, aunque sí editar sus permisos); el
    administrador puede además crear roles propios."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    es_sistema: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    # Preparado para acortar la sesión de roles sensibles; sin efecto todavía
    # (auth.iniciar_sesion sigue usando los valores fijos de seguridad.py).
    max_dias_sesion: Mapped[int | None] = mapped_column(nullable=True)
    permite_confiar_dispositivo: Mapped[bool] = mapped_column(Boolean, default=True)

    creado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)
    actualizado_en: Mapped[dt.datetime] = mapped_column(
        DateTime, default=fechas.ahora_utc, onupdate=fechas.ahora_utc
    )


class Permiso(Base):
    """Espejo en base del catálogo de app/permisos.py. El código es la única
    fuente de los CÓDIGOS válidos; esta tabla existe para que rol_permisos
    tenga una clave foránea real y para mostrar la lista en la pantalla de
    roles. Un permiso que desaparezca del catálogo se marca activo=0, nunca
    se borra (para no perder el historial de qué tenía cada rol)."""

    __tablename__ = "permisos"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(60), unique=True)
    modulo: Mapped[str] = mapped_column(String(40))
    descripcion: Mapped[str] = mapped_column(String(200))
    sensible: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class RolPermiso(Base):
    """Qué permiso tiene cada rol. Esto es lo que edita el administrador
    desde la pantalla de roles (las casillas ☑/☐)."""

    __tablename__ = "rol_permisos"

    rol_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permiso_id: Mapped[int] = mapped_column(ForeignKey("permisos.id"), primary_key=True)
    asignado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)

    rol: Mapped["Rol"] = relationship()
    permiso: Mapped["Permiso"] = relationship()


class UsuarioRol(Base):
    """Qué rol(es) tiene cada usuario. Varios roles por usuario: en sedes
    pequeñas el coordinador también dicta clase. Los permisos efectivos son
    la unión de los permisos de todos sus roles."""

    __tablename__ = "usuario_roles"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)
    rol_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    asignado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    asignado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)

    usuario: Mapped["Usuario"] = relationship(foreign_keys=[usuario_id])
    rol: Mapped["Rol"] = relationship()


class UsuarioSede(Base):
    """A qué sedes queda limitado un usuario (típicamente un coordinador).
    Semántica: SIN FILAS = todas las sedes (sin restricción). Se crea y se
    administra desde esta fase, pero todavía ningún endpoint la consulta
    para restringir nada — es la preparación para cuando se necesite (ver
    rbac.sedes_permitidas)."""

    __tablename__ = "usuario_sedes"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)
    sede_id: Mapped[int] = mapped_column(ForeignKey("sedes.id"), primary_key=True)
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)

    usuario: Mapped["Usuario"] = relationship()
    sede: Mapped["Sede"] = relationship()


class ObservacionPermiso(Base):
    """Fase 4A (modo observación): una fila por cada petición a un endpoint
    ya cubierto por observar(codigo) — nunca bloquea nada, solo registra qué
    HABRÍA pasado si el permiso ya se exigiera de verdad. Sirve para revisar
    el patrón acumulado antes de activar el bloqueo real (Fase 4B).

    usuario_id = NULL significa "sin sesión" (nadie logueado hizo la
    petición), no un usuario borrado."""

    __tablename__ = "observaciones_permisos"

    id: Mapped[int] = mapped_column(primary_key=True)
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)
    endpoint: Mapped[str] = mapped_column(String(200))
    metodo: Mapped[str] = mapped_column(String(10))
    permiso: Mapped[str] = mapped_column(String(80))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    # "sin_sesion" | "habria_pasado" | "habria_sido_rechazado"
    resultado: Mapped[str] = mapped_column(String(30))
    ip: Mapped[str | None] = mapped_column(String(60), nullable=True)

    usuario: Mapped["Usuario | None"] = relationship()


Index("ix_rol_permisos_permiso", RolPermiso.permiso_id)
Index("ix_usuario_roles_rol", UsuarioRol.rol_id)
Index("ix_usuario_sedes_sede", UsuarioSede.sede_id)
Index("ix_observaciones_permiso", ObservacionPermiso.permiso)
Index("ix_observaciones_usuario", ObservacionPermiso.usuario_id)
