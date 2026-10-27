import datetime as dt
import re
import unicodedata
from pathlib import Path

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, LargeBinary, String, Text, UniqueConstraint, func
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

    # True = el estudiante pertenece a un resguardo indígena (lo normal en el
    # colegio); False = no pertenece a ninguno.
    resguardo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    # Matriculado aquí (Matrícula → estudiante nuevo) y todavía sin confirmar
    # que ya está en SIMAT: se muestra el aviso "Nuevo · pendiente SIMAT" en
    # la ficha y en el listado hasta que alguien lo confirma. También queda
    # quién lo matriculó (su sesión) y cuándo. Los importados del Excel
    # oficial no tienen nada de esto.
    pendiente_simat: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    creado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    creado_en: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    creado_por: Mapped["Usuario | None"] = relationship(foreign_keys=[creado_por_id])

    @property
    def creado_por_nombre(self) -> str | None:
        return self.creado_por.nombre if self.creado_por else None

    @property
    def matricula_nueva_este_anio(self) -> bool:
        """Recién matriculado aquí este año lectivo (y aún pendiente SIMAT):
        su ficha es la de ESTE año (Est. NUEVO), no la renovación del año
        siguiente que llevan los antiguos."""
        return bool(
            self.pendiente_simat
            and self.creado_en
            and fechas.hoy_colombia(instante=self.creado_en).year == fechas.anio_lectivo_actual()
        )

    @property
    def anio_ficha_matricula(self) -> int:
        """Año escolar de su ficha de matrícula: el actual para un estudiante
        nuevo de este año; el siguiente (renovación) para los demás."""
        actual = fechas.anio_lectivo_actual()
        return actual if self.matricula_nueva_este_anio else actual + 1

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


CARPETA_DOCUMENTOS = Path(__file__).resolve().parent.parent / "uploads" / "fotos"


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
    # Lo pone el celular a cada subida (cola sin conexión, ver
    # frontend/static/js/sin_conexion.js): un reintento con el mismo valor
    # devuelve el documento ya guardado en vez de duplicarlo.
    uuid_cliente: Mapped[str | None] = mapped_column(String(36), nullable=True)

    estudiante: Mapped["Estudiante"] = relationship(back_populates="fotos")

    @property
    def es_pdf(self) -> bool:
        return self.nombre_archivo.lower().endswith(".pdf")

    @property
    def nombre_descarga(self) -> str:
        """Nombre legible del archivo ("Ficha de matrícula - Página 1" →
        "ficha_de_matricula_pagina_1.jpg") en vez del uuid con que se guarda."""
        base = unicodedata.normalize("NFKD", self.etiqueta or "").encode("ascii", "ignore").decode()
        base = re.sub(r"[^a-z0-9]+", "_", base.lower()).strip("_") or "documento"
        return base + Path(self.nombre_archivo).suffix.lower()

    @property
    def tamano_bytes(self) -> int | None:
        """Tamaño del archivo en disco (ya comprimido), para mostrarlo en la
        tabla de documentos. None si el archivo ya no está."""
        try:
            return (CARPETA_DOCUMENTOS / self.nombre_archivo).stat().st_size
        except OSError:
            return None


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


class DocenteAreaPeriodo(Base):
    """Quién dicta cada materia en cada grupo, PERIODO POR PERIODO, tal como
    lo dice el boletín de SAPRED ("PROFESOR: ..."). AsignacionDocente es una
    sola fila por año (y la primera que llegó se queda): si a mitad de año
    cambia el profesor de Matemáticas de 7-2, eso solo se ve aquí. area_id
    None = director de grupo. Se llena al importar el boletín (crud.
    importar_bloque_boletin); docente_id queda None cuando el nombre del
    boletín no coincide con ningún docente de la base, y nombre_sapred
    guarda el nombre tal cual para poder revisarlo."""

    __tablename__ = "docentes_area_periodo"
    __table_args__ = (
        Index("ix_docente_area_periodo_grupo", "anio_lectivo", "sede_id", "grado", "curso", "area_id", "periodo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    anio_lectivo: Mapped[int]
    periodo: Mapped[int]
    sede_id: Mapped[int] = mapped_column(ForeignKey("sedes.id"))
    grado: Mapped[int]
    curso: Mapped[int | None] = mapped_column(nullable=True)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"), nullable=True)
    docente_id: Mapped[int | None] = mapped_column(ForeignKey("docentes.id"), nullable=True)
    nombre_sapred: Mapped[str] = mapped_column(String(200))
    actualizado_en: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    sede: Mapped["Sede"] = relationship()
    area: Mapped[Area | None] = relationship()
    docente: Mapped[Docente | None] = relationship()


class HallazgoConciliacion(Base):
    """Historial persistente de discrepancias de GRUPO entre SIMAC y SAPRED
    (ver conciliacion.py, sección "diferencia" campo="grupo"). La
    conciliación en sí se recalcula en vivo y no guarda nada — pero eso
    significa que si alguien corrige el dato en SIMAC, o SAPRED cambia, el
    caso desaparece del reporte sin dejar rastro de que existió. Esta tabla
    es la memoria: se crea/actualiza cada vez que corre la conciliación
    (conciliacion._sincronizar_hallazgos) y NUNCA se borra, solo se marca
    resuelta — para no perder, de un año a otro, a quién hay que corregirle
    el grado en la matrícula (promoción anticipada)."""

    __tablename__ = "hallazgos_conciliacion"
    __table_args__ = (
        UniqueConstraint("estudiante_id", "anio_lectivo", "periodo", name="uq_hallazgo_estudiante_periodo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    estudiante_id: Mapped[int] = mapped_column(ForeignKey("estudiantes.id"))
    anio_lectivo: Mapped[int]
    periodo: Mapped[int]

    sede_id: Mapped[int] = mapped_column(ForeignKey("sedes.id"))
    grado_simac: Mapped[int]
    curso_simac: Mapped[int | None] = mapped_column(nullable=True)
    grado_sapred: Mapped[int]
    curso_sapred: Mapped[int | None] = mapped_column(nullable=True)
    # True si grado_sapred > grado_simac: no es un error de digitación sino
    # una promoción que ya ocurrió en la práctica (ver conciliacion.py).
    es_promocion_anticipada: Mapped[bool] = mapped_column(default=False)

    detectado_en: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    visto_en: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    resuelto: Mapped[bool] = mapped_column(default=False)
    resuelto_en: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    resuelto_por: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nota: Mapped[str | None] = mapped_column(String(500), nullable=True)

    estudiante: Mapped["Estudiante"] = relationship()
    sede: Mapped["Sede"] = relationship()


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
    # Varios periodos / grados en una sola corrida, separados por coma (ej.
    # "1,2,3" y "5,7,9"). None = solo `periodo` / `grado` de arriba (las
    # corridas viejas). `periodo` queda con el primero, para lo que ya lo lee.
    periodos: Mapped[str | None] = mapped_column(String(50), nullable=True)
    grados: Mapped[str | None] = mapped_column(String(100), nullable=True)

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
    """Un registro de asistencia de UN estudiante en UNA clase concreta
    (bloque de horario) o, cuando area_id es NULL, la toma general del día
    que hace el director de grupo — misma convención area_id=NULL que ya usa
    AsignacionDocente/BloqueHorario para "todo el grupo, sin materia puntual".

    No se borra nunca una fila para corregirla: se sobrescribe el estado y se
    deja rastro en AuditoriaCambio (entidad="asistencia"). anulado es un
    soft-delete (nunca se borra de verdad, para no perder auditoría).

    uuid_cliente es la idempotencia pensada para cuando el registro llegue
    desde una cola offline (todavía no construida): un mismo uuid nunca crea
    dos filas, así un reintento de red no duplica nada."""

    __tablename__ = "asistencias"
    __table_args__ = (
        # SQLite no trata dos NULL como iguales en un UNIQUE normal (ver la
        # nota junto a los índices con func.coalesce más abajo en este
        # archivo) — por eso la unicidad real de esta tabla vive en el índice
        # ix_asistencia_estudiante_area_fecha_nn, no aquí.
        UniqueConstraint("uuid_cliente", name="uq_asistencia_uuid_cliente"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid_cliente: Mapped[str | None] = mapped_column(String(36), nullable=True)

    estudiante_id: Mapped[int] = mapped_column(ForeignKey("estudiantes.id"))
    # Redundante con Estudiante.sede_id/grado/curso a propósito: es la foto
    # del grupo en el momento de tomar la asistencia, para que un traslado
    # posterior del estudiante no reescriba su historial.
    sede_id: Mapped[int] = mapped_column(ForeignKey("sedes.id"))
    grado: Mapped[int]
    curso: Mapped[int | None] = mapped_column(nullable=True)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"), nullable=True)
    bloque_horario_id: Mapped[int | None] = mapped_column(ForeignKey("bloques_horario.id"), nullable=True)

    fecha: Mapped[dt.date] = mapped_column(Date, default=fechas.hoy_colombia)
    estado: Mapped[str] = mapped_column(String(20), default="presente")  # presente|ausente|tardanza|excusa
    observacion: Mapped[str | None] = mapped_column(String(300), nullable=True)

    docente_id: Mapped[int] = mapped_column(ForeignKey("docentes.id"))
    registrado_por_usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    registrado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)

    modificado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    modificado_en: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_modificacion: Mapped[str | None] = mapped_column(String(300), nullable=True)

    anulado: Mapped[bool] = mapped_column(Boolean, default=False)
    anulado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    anulado_en: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_anulacion: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Fase offline futura: dos envíos con valores distintos para la misma
    # clave lógica fuera de la ventana normal de corrección quedan aquí
    # marcados en vez de sobrescribirse en silencio (ver asistencia.py).
    en_conflicto: Mapped[bool] = mapped_column(Boolean, default=False)

    estudiante: Mapped[Estudiante] = relationship(back_populates="asistencias")
    sede: Mapped["Sede"] = relationship()
    area: Mapped[Area | None] = relationship()
    bloque_horario: Mapped["BloqueHorario | None"] = relationship()
    docente: Mapped[Docente] = relationship(foreign_keys=[docente_id])


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
Index("ix_notas_sapred_revision", NotaSapred.revision_id)
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

    usuario_id = NULL significa que la petición llegó sin identidad, no un
    usuario borrado. El porqué lo dice `resultado` (ver abajo)."""

    __tablename__ = "observaciones_permisos"

    id: Mapped[int] = mapped_column(primary_key=True)
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)
    endpoint: Mapped[str] = mapped_column(String(200))
    metodo: Mapped[str] = mapped_column(String(10))
    permiso: Mapped[str] = mapped_column(String(80))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    # Con identidad:  "habria_pasado" | "habria_sido_rechazado"
    # Sin identidad:  "sin_sesion" (nadie inició sesión aquí)
    #                 "sesion_vencida" (Fase 4A': token de acceso caducado,
    #                  recuperable con un refresh)
    #                 "sesion_revocada" (Fase 4A': sesión cerrada o usuario
    #                  desactivado; hay que volver a iniciar sesión)
    # Ver rbac._por_que_no_hay_identidad(). La columna no tiene CHECK: añadir
    # un valor nuevo no exige migrar nada.
    resultado: Mapped[str] = mapped_column(String(30))
    ip: Mapped[str | None] = mapped_column(String(60), nullable=True)

    usuario: Mapped["Usuario | None"] = relationship()


class AlertaPromocion(Base):
    """Aviso a coordinación/administración: alguien generó la ficha de matrícula
    de un estudiante pasándolo a un grado más alto aunque en las notas del
    año lleva materias perdidas (regla del colegio: una materia perdida =
    año perdido). Solo informa; nunca bloquea la matrícula."""

    __tablename__ = "alertas_promocion"

    id: Mapped[int] = mapped_column(primary_key=True)
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)
    estudiante_id: Mapped[int] = mapped_column(ForeignKey("estudiantes.id"))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    anio_lectivo: Mapped[int]
    grado_actual: Mapped[int]
    grado_destino: Mapped[int]
    materias_perdidas: Mapped[int]
    detalle: Mapped[str] = mapped_column(Text)  # JSON: [{area, promedio, notas:[[periodo, valor]]}]
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente | atendida
    atendida_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    atendida_en: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    nota_atencion: Mapped[str | None] = mapped_column(Text, nullable=True)

    estudiante: Mapped["Estudiante"] = relationship()
    usuario: Mapped["Usuario | None"] = relationship(foreign_keys=[usuario_id])
    atendida_por: Mapped["Usuario | None"] = relationship(foreign_keys=[atendida_por_id])


class ConfiguracionSistema(Base):
    """Parámetros generales clave → valor (ver app/configuracion.py), con
    quién y cuándo los cambió. Hoy: si el módulo de Orientación está activo
    (se apaga, por ejemplo, entre años lectivos mientras no hay datos)."""

    __tablename__ = "configuracion_sistema"

    clave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[str] = mapped_column(String(500))
    actualizado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    actualizado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)

    actualizado_por: Mapped["Usuario | None"] = relationship()


class SolicitudPromocion(Base):
    """Permiso que se le pide a coordinación para matricular a un estudiante
    en un grado que NO es el que le corresponde por la regla normal:
      · subir de grado llevando materias perdidas (una perdida = año perdido);
      · saltarse grados (ej. de Preescolar a Segundo: lo normal es +1);
      · bajarlo de grado.
    Mientras no esté aprobada, la ficha de matrícula NO se genera con ese
    grado (routers/certificados.py) — decisión de la institución. Reemplaza
    al aviso informativo AlertaPromocion (que se conserva como historial).
    Guarda quién pidió, quién decidió, cuándo y por qué: nunca se borra."""

    __tablename__ = "solicitudes_promocion"

    id: Mapped[int] = mapped_column(primary_key=True)
    estudiante_id: Mapped[int] = mapped_column(ForeignKey("estudiantes.id"))
    anio_lectivo: Mapped[int]
    grado_actual: Mapped[int]
    grado_destino: Mapped[int]
    # Separados por coma: perdidas | salto | retroceso
    motivos: Mapped[str] = mapped_column(String(60))
    materias_perdidas: Mapped[int] = mapped_column(default=0)
    # JSON: [{area, docente, promedio, notas:[[periodo, valor]]}] — foto de las
    # notas en el momento de pedir (pueden cambiar después con otro import).
    detalle: Mapped[str] = mapped_column(Text, default="[]")
    justificacion: Mapped[str] = mapped_column(Text)
    solicitado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    solicitado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)
    # pendiente | aprobada | rechazada | anulada
    estado: Mapped[str] = mapped_column(String(20), default="pendiente", server_default="pendiente")
    decidido_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    decidido_en: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    nota_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Cuándo se generó por primera vez la ficha usando esta aprobación.
    usada_en: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    estudiante: Mapped["Estudiante"] = relationship()
    solicitado_por: Mapped["Usuario"] = relationship(foreign_keys=[solicitado_por_id])
    decidido_por: Mapped["Usuario | None"] = relationship(foreign_keys=[decidido_por_id])


Index("ix_alertas_promocion_estado", AlertaPromocion.estado)
Index("ix_solicitudes_promocion_estado", SolicitudPromocion.estado)
Index("ix_solicitudes_promocion_estudiante", SolicitudPromocion.estudiante_id)
Index("ix_rol_permisos_permiso", RolPermiso.permiso_id)
Index("ix_usuario_roles_rol", UsuarioRol.rol_id)
Index("ix_usuario_sedes_sede", UsuarioSede.sede_id)
Index("ix_observaciones_permiso", ObservacionPermiso.permiso)
Index("ix_observaciones_usuario", ObservacionPermiso.usuario_id)

# En SQLite dos NULL nunca "chocan" dentro de un UNIQUE (ver la nota de
# arriba, verificada 11/09/2026): area_id NULL = toma general del director
# de grupo, así que se usa func.coalesce(area_id, -1) para que sí choquen
# entre sí un segundo registro general del mismo estudiante el mismo día.
Index(
    "ix_asistencia_estudiante_area_fecha_nn",
    Asistencia.estudiante_id, func.coalesce(Asistencia.area_id, -1), Asistencia.fecha,
    unique=True,
)
Index("ix_asistencia_grupo_fecha", Asistencia.sede_id, Asistencia.grado, Asistencia.curso, Asistencia.fecha)
Index("ix_asistencia_docente", Asistencia.docente_id)
Index("ix_asistencia_bloque", Asistencia.bloque_horario_id)


class Observacion(Base):
    """Observación sobre un estudiante: académica, de convivencia, general o
    una remisión a psicología/orientación. confidencial se fuerza en
    backend (nunca se confía en lo que mande el cliente) cuando
    tipo="psicologia": el autor (típicamente un docente) sigue viendo lo que
    él mismo escribió, pero la ampliación/gestión del caso vive aparte en
    SeguimientoObservacion, visible solo con observaciones.ver_confidenciales
    o seguimientos.gestionar — así un docente puede remitir un caso sin poder
    leer después todo el seguimiento interno de orientación."""

    __tablename__ = "observaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid_cliente: Mapped[str | None] = mapped_column(String(36), nullable=True)

    estudiante_id: Mapped[int] = mapped_column(ForeignKey("estudiantes.id"))
    sede_id: Mapped[int] = mapped_column(ForeignKey("sedes.id"))
    grado: Mapped[int]
    curso: Mapped[int | None] = mapped_column(nullable=True)

    tipo: Mapped[str] = mapped_column(String(20))  # academica | convivencia | general | psicologia
    confidencial: Mapped[bool] = mapped_column(Boolean, default=False)
    titulo: Mapped[str | None] = mapped_column(String(150), nullable=True)
    detalle: Mapped[str] = mapped_column(Text)

    autor_usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[dt.date] = mapped_column(Date, default=fechas.hoy_colombia)
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)

    estado: Mapped[str] = mapped_column(String(20), default="abierta")  # abierta|atendida|cerrada
    atendida_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    atendida_en: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    nota_atencion: Mapped[str | None] = mapped_column(Text, nullable=True)

    estudiante: Mapped["Estudiante"] = relationship()
    sede: Mapped["Sede"] = relationship()
    autor: Mapped["Usuario"] = relationship(foreign_keys=[autor_usuario_id])
    atendida_por: Mapped["Usuario | None"] = relationship(foreign_keys=[atendida_por_usuario_id])
    seguimientos: Mapped[list["SeguimientoObservacion"]] = relationship(
        back_populates="observacion", cascade="all, delete-orphan", order_by="SeguimientoObservacion.creado_en"
    )


class SeguimientoObservacion(Base):
    """Nota interna de orientación/psicología sobre una observación (típico:
    ampliar una remisión hecha por un docente). NO la ve el autor de la
    observación original si no tiene observaciones.ver_confidenciales —
    es justo lo que separa "el docente remite" de "psicología gestiona"."""

    __tablename__ = "seguimientos_observacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    observacion_id: Mapped[int] = mapped_column(ForeignKey("observaciones.id"))
    autor_usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    nota: Mapped[str] = mapped_column(Text)
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)

    observacion: Mapped["Observacion"] = relationship(back_populates="seguimientos")
    autor: Mapped["Usuario"] = relationship()


class AuditoriaCambio(Base):
    """Rastro genérico de "quién cambió qué" para operaciones sensibles
    (punto 27 del encargo docente: asistencia, observaciones, y lo que haga
    falta después — no se hace una tabla nueva por cada dominio, sigue el
    mismo espíritu de ObservacionPermiso/AlertaPromocion de no duplicar
    infraestructura). entidad+entidad_id identifican la fila afectada."""

    __tablename__ = "auditoria_cambios"

    id: Mapped[int] = mapped_column(primary_key=True)
    entidad: Mapped[str] = mapped_column(String(40))
    entidad_id: Mapped[int]
    campo: Mapped[str] = mapped_column(String(60))
    valor_anterior: Mapped[str | None] = mapped_column(String(300), nullable=True)
    valor_nuevo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    motivo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)
    ip: Mapped[str | None] = mapped_column(String(60), nullable=True)

    usuario: Mapped["Usuario | None"] = relationship()


Index("ix_observaciones_estudiante", Observacion.estudiante_id)
Index("ix_observaciones_estudiante_tipo", Observacion.estudiante_id, Observacion.tipo)
Index("ix_observaciones_confidencial_estado", Observacion.confidencial, Observacion.estado)
Index("ix_seguimientos_observacion", SeguimientoObservacion.observacion_id)
Index("ix_auditoria_entidad", AuditoriaCambio.entidad, AuditoriaCambio.entidad_id)


class DatosFichaEstudiante(Base):
    """Datos que solo aparecen en la ficha de matrícula (acudiente, comunidad,
    etnia, discapacidad...). Se llenan al escribirlos en la ficha y quedan
    guardados para el próximo año y para el resto del programa. Los Si/No
    quedan como True/False, y None significa "no se ha dicho" (no es "No")."""

    __tablename__ = "datos_ficha_estudiante"

    id: Mapped[int] = mapped_column(primary_key=True)
    estudiante_id: Mapped[int] = mapped_column(ForeignKey("estudiantes.id"), unique=True)
    municipio_nacimiento: Mapped[str | None] = mapped_column(String(150), nullable=True)
    resguardo: Mapped[str | None] = mapped_column(String(150), nullable=True)
    procedencia: Mapped[str | None] = mapped_column(String(200), nullable=True)  # C.E. de donde proviene
    direccion: Mapped[str | None] = mapped_column(String(250), nullable=True)  # comunidad / predio
    etnia: Mapped[str | None] = mapped_column(String(20), nullable=True)  # INDIGENA | AFRO | MESTIZO
    habla_awapit: Mapped[bool | None] = mapped_column(nullable=True)
    madre_cabeza: Mapped[bool | None] = mapped_column(nullable=True)
    estudiante_sgp: Mapped[bool | None] = mapped_column(nullable=True)
    fecha_ingreso: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    traslado_horas: Mapped[str | None] = mapped_column(String(10), nullable=True)
    traslado_minutos: Mapped[str | None] = mapped_column(String(10), nullable=True)
    cruza_rios: Mapped[bool | None] = mapped_column(nullable=True)
    cruza_quebradas: Mapped[bool | None] = mapped_column(nullable=True)
    educacion_especial: Mapped[bool | None] = mapped_column(nullable=True)
    desplazamiento: Mapped[bool | None] = mapped_column(nullable=True)
    discapacidad: Mapped[str | None] = mapped_column(String(300), nullable=True)  # "NINGUNA" o los tipos
    discapacidad_detalle: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON de las casillas
    acudiente_nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    acudiente_parentesco: Mapped[str | None] = mapped_column(String(60), nullable=True)
    acudiente_documento: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actualizado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc, onupdate=fechas.ahora_utc)
    actualizado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)


class DiagnosticoGrado(Base):
    """Diagnóstico narrativo que el director de grupo llena por grado para
    orientación/psicología (Excel "DIAGNOSTICO IETABA", una hoja por grado),
    importado tal cual desde ahí (ver diagnostico_import.py). Cada import
    crea una VERSIÓN nueva — nunca se sobrescribe una anterior — así
    orientación conserva el historial de cómo iba el grado en marzo vs. mayo
    y decide ella misma si la versión vieja ya no aplica. `contenido_hash`
    evita crear una versión idéntica si el mismo archivo se importa dos veces
    sin cambios."""

    __tablename__ = "diagnosticos_grado"

    id: Mapped[int] = mapped_column(primary_key=True)
    sede_id: Mapped[int] = mapped_column(ForeignKey("sedes.id"))
    grado: Mapped[int]
    curso: Mapped[int | None] = mapped_column(nullable=True)
    hoja_excel: Mapped[str] = mapped_column(String(50))
    contenido_hash: Mapped[str] = mapped_column(String(64), index=True)

    fecha_diligenciado: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    importado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)
    importado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    archivo_origen: Mapped[str | None] = mapped_column(String(300), nullable=True)

    n_en_lista: Mapped[int | None] = mapped_column(nullable=True)
    n_asisten: Mapped[int | None] = mapped_column(nullable=True)
    no_asisten_texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    desplazados_texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    embarazadas_texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    victimas_conflicto_texto: Mapped[str | None] = mapped_column(Text, nullable=True)

    dificultades_academicas: Mapped[str | None] = mapped_column(Text, nullable=True)
    dificultades_comportamiento: Mapped[str | None] = mapped_column(Text, nullable=True)
    acompanamiento_padres: Mapped[str | None] = mapped_column(Text, nullable=True)
    problemas_salud: Mapped[str | None] = mapped_column(Text, nullable=True)

    tematicas_trabajar: Mapped[str | None] = mapped_column(Text, nullable=True)
    estrategias_conflicto: Mapped[str | None] = mapped_column(Text, nullable=True)
    estrategias_aprendizaje: Mapped[str | None] = mapped_column(Text, nullable=True)
    resguardos_atendidos: Mapped[str | None] = mapped_column(Text, nullable=True)

    recomendaciones_docentes: Mapped[str | None] = mapped_column(Text, nullable=True)
    llamados_atencion: Mapped[str | None] = mapped_column(Text, nullable=True)
    orientacion_brindada: Mapped[str | None] = mapped_column(Text, nullable=True)
    transporte_escolar: Mapped[str | None] = mapped_column(Text, nullable=True)

    observaciones_generales: Mapped[str | None] = mapped_column(Text, nullable=True)
    director_grado_nombre: Mapped[str | None] = mapped_column(String(150), nullable=True)
    orientador_escolar_nombre: Mapped[str | None] = mapped_column(String(150), nullable=True)
    seguimiento_nota: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Volcado crudo de toda celda no vacía de la hoja, como red de seguridad:
    # si la extracción por campos se le escapó algo (hojas mal diligenciadas
    # varían mucho entre sí), esto nunca se pierde y queda disponible para
    # que orientación lo revise en la pantalla o el PDF.
    texto_crudo: Mapped[str | None] = mapped_column(Text, nullable=True)

    sede: Mapped["Sede"] = relationship()
    importado_por: Mapped["Usuario | None"] = relationship()
    menciones: Mapped[list["DiagnosticoMencion"]] = relationship(
        back_populates="diagnostico", cascade="all, delete-orphan"
    )


class DiagnosticoMencion(Base):
    """Un estudiante nombrado dentro del texto libre de un DiagnosticoGrado
    (no asiste, intermitencia, desplazado, embarazada, víctima de conflicto
    armado, dificultad académica/de comportamiento, llamado de atención,
    salud). `texto` es el fragmento que le corresponde A ÉL — no el párrafo
    completo del campo: el importador divide el texto por dónde aparece
    cada nombre (ver diagnostico_import._segmentos_por_nombre), así que dos
    estudiantes mencionados en el mismo campo casi siempre quedan con
    `texto` distinto, salvo que el propio texto no permita separarlos (ver
    `texto_compartido`).

    Se intenta enlazar automáticamente con el Estudiante real del mismo
    grado por coincidencia de nombre (ver `diagnostico_import.
    vincular_estudiante`); si no hay una coincidencia confiable queda con
    estudiante_id=None y el nombre tal cual se escribió, para que
    orientación lo vincule a mano — nunca se inventa a quién pertenece."""

    __tablename__ = "diagnosticos_mencion"

    id: Mapped[int] = mapped_column(primary_key=True)
    diagnostico_id: Mapped[int] = mapped_column(ForeignKey("diagnosticos_grado.id"))
    # no_asiste | intermitencia | desplazado | embarazada | victima_conflicto |
    # dificultad_academica | dificultad_comportamiento | llamado_atencion | salud
    categoria: Mapped[str] = mapped_column(String(30))
    texto: Mapped[str] = mapped_column(Text)
    nombre_detectado: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # alta = único candidato claro en el grupo | media = 2+ candidatos
    # empatados (posible coincidencia, hace falta que una persona elija) |
    # baja = ningún estudiante del grupo coincide (puede ser un familiar,
    # docente, lugar u otra persona, o un estudiante que no está en la lista).
    confianza: Mapped[str] = mapped_column(String(10), default="alta", server_default="alta")
    # True = este `texto` es compartido con otras menciones del MISMO
    # fragmento del Excel porque el texto no permitía separar qué parte le
    # corresponde a cada quien (ej. "Jhon y Pedro tienen dificultades...") —
    # mejor eso que inventar dónde termina la parte de cada uno.
    texto_compartido: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # JSON con los ids de Estudiante empatados cuando confianza="media", para
    # ofrecer "¿es alguno de estos?" en vez de una búsqueda desde cero.
    candidatos_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    estudiante_id: Mapped[int | None] = mapped_column(ForeignKey("estudiantes.id"), nullable=True)
    vinculo_automatico: Mapped[bool] = mapped_column(Boolean, default=False)
    vinculado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    vinculado_en: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    diagnostico: Mapped["DiagnosticoGrado"] = relationship(back_populates="menciones")
    estudiante: Mapped["Estudiante | None"] = relationship()
    vinculado_por: Mapped["Usuario | None"] = relationship(foreign_keys=[vinculado_por_usuario_id])


class Caso(Base):
    """Caso de orientación: el trabajo ACTIVO sobre UN estudiante concreto,
    aparte de lo que trae el Excel importado (DiagnosticoGrado/
    DiagnosticoMencion, que nunca se editan — son la fotografía histórica).
    Un caso nace de dos maneras:
      · "Abrir caso" desde una mención detectada en el Excel
        (`mencion_origen_id` queda apuntando a ella — origen="importado").
      · Creado a mano por orientación sin que venga del Excel
        (origen="manual").
    Se liga al GRUPO (sede+grado+curso, igual que Observacion) tal como
    estaba al abrirse el caso, no a una versión puntual del diagnóstico: es
    un registro que debe sobrevivir a que se reimporte un Excel de un
    período nuevo, no algo que ese import reemplace o borre.

    Nota histórica: la tabla se llama `diagnosticos_observaciones` porque
    así nació (una nota plana, sin estado); se conserva el nombre físico
    para no reconstruir la tabla, pero el concepto ahora es Caso.

    No tiene su propio flag de confidencialidad: todo el módulo de
    diagnóstico ya está protegido detrás de diagnosticos.ver/observar con
    rbac.requiere() (bloqueo duro, igual que observaciones.ver_confidenciales),
    así que un segundo nivel de confidencialidad aquí sería una segunda
    fuente de verdad sin necesidad real."""

    __tablename__ = "diagnosticos_observaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    sede_id: Mapped[int] = mapped_column(ForeignKey("sedes.id"))
    grado: Mapped[int]
    curso: Mapped[int | None] = mapped_column(nullable=True)
    estudiante_id: Mapped[int] = mapped_column(ForeignKey("estudiantes.id"))

    # academica | comportamiento | inasistencia | intermitencia | familiar |
    # salud | convivencia | orientacion | riesgo | otra
    tipo: Mapped[str] = mapped_column("categoria", String(30))
    titulo: Mapped[str | None] = mapped_column(String(150), nullable=True)
    descripcion: Mapped[str] = mapped_column("detalle", Text)
    acciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_apertura: Mapped[dt.date] = mapped_column("fecha", Date, default=fechas.hoy_colombia)

    # abierto | en_seguimiento | cerrado
    estado: Mapped[str] = mapped_column(String(20), default="abierto", server_default="abierto")
    proximo_seguimiento: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    cerrado_en: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    cerrado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)

    # importado | manual — de dónde salió el caso.
    origen: Mapped[str] = mapped_column(String(10), default="manual", server_default="manual")
    mencion_origen_id: Mapped[int | None] = mapped_column(ForeignKey("diagnosticos_mencion.id"), nullable=True)

    autor_usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)

    sede: Mapped["Sede"] = relationship()
    estudiante: Mapped["Estudiante"] = relationship()
    autor: Mapped["Usuario"] = relationship(foreign_keys=[autor_usuario_id])
    cerrado_por: Mapped["Usuario | None"] = relationship(foreign_keys=[cerrado_por_usuario_id])
    mencion_origen: Mapped["DiagnosticoMencion | None"] = relationship()
    seguimientos: Mapped[list["CasoSeguimiento"]] = relationship(
        back_populates="caso", cascade="all, delete-orphan", order_by="CasoSeguimiento.fecha.desc()"
    )


class CasoSeguimiento(Base):
    """Una entrada del historial de un Caso: cada vez que orientación
    vuelve a atender la situación, sin abrir un caso nuevo. Varias de estas
    por caso (ver Caso.seguimientos)."""

    __tablename__ = "casos_seguimiento"

    id: Mapped[int] = mapped_column(primary_key=True)
    caso_id: Mapped[int] = mapped_column(ForeignKey("diagnosticos_observaciones.id"))
    fecha: Mapped[dt.date] = mapped_column(Date, default=fechas.hoy_colombia)
    tipo_atencion: Mapped[str | None] = mapped_column(String(60), nullable=True)
    situacion: Mapped[str] = mapped_column(Text)
    accion_realizada: Mapped[str | None] = mapped_column(Text, nullable=True)
    compromisos: Mapped[str | None] = mapped_column(Text, nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    proxima_fecha: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    autor_usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)

    caso: Mapped["Caso"] = relationship(back_populates="seguimientos")
    autor: Mapped["Usuario"] = relationship()


Index("ix_diagnosticos_grado_sede_grado_curso", DiagnosticoGrado.sede_id, DiagnosticoGrado.grado, DiagnosticoGrado.curso)
Index("ix_diagnosticos_mencion_diagnostico", DiagnosticoMencion.diagnostico_id)
Index("ix_diagnosticos_mencion_estudiante", DiagnosticoMencion.estudiante_id)
Index("ix_casos_grupo", Caso.sede_id, Caso.grado, Caso.curso)
Index("ix_casos_estudiante", Caso.estudiante_id)
Index("ix_casos_estado", Caso.estado)
Index("ix_casos_seguimiento_caso", CasoSeguimiento.caso_id)


class ResultadoIcfes(Base):
    """Resultado individual Saber 11 publicado por el ICFES (PRISMA → Publicación
    de Resultados → Consulta Plantel). Lo llena backend/importar_icfes.py; una
    fila por número de registro (AC...), que el ICFES no repite entre años.

    El ICFES no publica el documento del estudiante, solo el nombre: el vínculo
    con `estudiantes` es por nombre completo normalizado y únicamente cuando
    hay UNA coincidencia (ver icfes.vincular_estudiantes); si no, queda en None."""

    __tablename__ = "resultados_icfes"

    id: Mapped[int] = mapped_column(primary_key=True)
    registro: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    anio: Mapped[int] = mapped_column(index=True)
    periodo: Mapped[int]  # período de aplicación del ICFES (no es el período académico)
    nombre: Mapped[str] = mapped_column(String(200))
    estudiante_id: Mapped[int | None] = mapped_column(ForeignKey("estudiantes.id"), nullable=True, index=True)

    # Puntajes por prueba (0-100) y percentil nacional (1-100); None = "-" en el ICFES
    lc: Mapped[int | None] = mapped_column(nullable=True)
    mat: Mapped[int | None] = mapped_column(nullable=True)
    syc: Mapped[int | None] = mapped_column(nullable=True)
    cn: Mapped[int | None] = mapped_column(nullable=True)
    ing: Mapped[int | None] = mapped_column(nullable=True)
    pct_lc: Mapped[int | None] = mapped_column(nullable=True)
    pct_mat: Mapped[int | None] = mapped_column(nullable=True)
    pct_syc: Mapped[int | None] = mapped_column(nullable=True)
    pct_cn: Mapped[int | None] = mapped_column(nullable=True)
    pct_ing: Mapped[int | None] = mapped_column(nullable=True)
    puntaje_global: Mapped[int | None] = mapped_column(nullable=True)  # 0-500
    percentil_global: Mapped[int | None] = mapped_column(nullable=True)
    # Percentiles de "población especial" (casi siempre vacíos): JSON tal cual
    percentiles_especiales: Mapped[str | None] = mapped_column(Text, nullable=True)

    importado_en: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc)

    estudiante: Mapped["Estudiante | None"] = relationship()


class OperacionCliente(Base):
    """Escrituras recibidas con encabezado X-Id-Operacion y la respuesta que
    se dio, para no ejecutar dos veces lo que un dispositivo reenvía al volver
    la conexión (ver operaciones_cliente.py). estado_http None = en curso."""

    __tablename__ = "operaciones_cliente"

    clave: Mapped[str] = mapped_column(String(64), primary_key=True)
    metodo: Mapped[str] = mapped_column(String(10))
    ruta: Mapped[str] = mapped_column(String(300))
    estado_http: Mapped[int | None] = mapped_column(nullable=True)
    tipo_contenido: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cuerpo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    creado: Mapped[dt.datetime] = mapped_column(DateTime, default=fechas.ahora_utc, index=True)
