"""Migraciones de la base SQLite: idempotentes, corren en cada arranque.

No hay Alembic: cada paso revisa el estado real de la base y solo actúa si
hace falta (el mismo patrón que antes vivía en main.py). Orden en ejecutar():

  1. create_all ................. tablas nuevas del modelo.
  2. asegurar_columnas_sqlite ... columnas agregadas después y tablas que
                                   hubo que recrear.
  3. reparar_claves_foraneas_rotas  tablas cuyo FOREIGN KEY apunta a una
                                   tabla que ya no existe.
  4. asegurar_indices ........... índices declarados en models.py que falten.
  5. Datos semilla y backfills.

Antes de recrear una tabla se hace un respaldo colegio.db.bak_* con la API
de backup de SQLite (consistente aunque la app esté usando la base).
"""

import sqlite3
import unicodedata

from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from . import fechas, models
from . import permisos as permisos_catalogo
from .database import DB_PATH, Base, engine


def _log(mensaje: str) -> None:
    print(f"[migraciones] {mensaje}", flush=True)


# --- Herramientas ------------------------------------------------------------


def respaldar(motivo: str) -> str:
    """Copia consistente de la base a colegio.db.bak_<motivo>_<fecha_hora>."""
    sello = fechas.ahora_colombia().strftime("%Y%m%d_%H%M%S")
    destino = DB_PATH.with_name(f"{DB_PATH.name}.bak_{motivo}_{sello}")
    origen = engine.raw_connection()
    try:
        copia = sqlite3.connect(destino)
        try:
            origen.driver_connection.backup(copia)
        finally:
            copia.close()
    finally:
        origen.close()
    _log(f"respaldo creado: {destino.name}")
    return str(destino)


def _tablas_existentes(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def reconstruir_tabla(nombre: str, columnas: list[str]) -> None:
    """Recrea `nombre` con la definición ACTUAL del modelo conservando sus
    filas (las `columnas` indicadas). Es la receta de SQLite para cambios que
    ALTER TABLE no permite (quitar un NOT NULL, cambiar un UNIQUE o un
    FOREIGN KEY):
      · foreign_keys=OFF mientras dura: si no, DROP TABLE chocaría con las
        filas hijas.
      · legacy_alter_table=ON: sin esto, SQLite ≥ 3.26 reescribe las
        referencias de OTRAS tablas hacia el nombre temporal "<tabla>_old" y
        las deja apuntando a una tabla borrada (así quedó pendientes_boletin
        → revisiones_boletin_old).
      · Todo en una transacción; si al final la tabla tiene filas que violan
        sus claves foráneas, se deshace."""
    respaldar(f"antes_reconstruir_{nombre}")
    ddl = str(CreateTable(Base.metadata.tables[nombre]).compile(dialect=engine.dialect))
    cols = ", ".join(f'"{c}"' for c in columnas)
    raw = engine.raw_connection()
    con = raw.driver_connection
    nivel_previo = con.isolation_level
    try:
        con.isolation_level = None  # transacción manual (BEGIN/COMMIT explícitos)
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("PRAGMA legacy_alter_table=ON")
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute(f'ALTER TABLE "{nombre}" RENAME TO "{nombre}_old"')
            con.execute(ddl)
            con.execute(f'INSERT INTO "{nombre}" ({cols}) SELECT {cols} FROM "{nombre}_old"')
            con.execute(f'DROP TABLE "{nombre}_old"')
            violaciones = con.execute(f'PRAGMA foreign_key_check("{nombre}")').fetchall()
            if violaciones:
                raise RuntimeError(
                    f"{nombre}: {len(violaciones)} filas violan sus claves foráneas; no se recreó la tabla"
                )
            con.execute("COMMIT")
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.execute("PRAGMA legacy_alter_table=OFF")
            con.execute("PRAGMA foreign_keys=ON")
    finally:
        con.isolation_level = nivel_previo
        raw.close()
    _log(f"tabla recreada: {nombre}")


# --- 2. Columnas agregadas después ------------------------------------------


def asegurar_columnas_sqlite() -> None:
    inspector = inspect(engine)
    tablas = inspector.get_table_names()

    if "sedes" in tablas:
        columnas = {c["name"] for c in inspector.get_columns("sedes")}
        if "pertenece_ietaba" not in columnas:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE sedes ADD COLUMN pertenece_ietaba BOOLEAN DEFAULT 1 NOT NULL")
                )

    if "estudiantes" in tablas:
        columnas = {c["name"] for c in inspector.get_columns("estudiantes")}
        if "lugar_expedicion_documento" not in columnas:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE estudiantes ADD COLUMN lugar_expedicion_documento VARCHAR(150)"))
        if "posible_retirado" not in columnas:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE estudiantes ADD COLUMN posible_retirado BOOLEAN DEFAULT 0 NOT NULL")
                )
        if "retirado" not in columnas:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE estudiantes ADD COLUMN retirado BOOLEAN DEFAULT 0 NOT NULL"))
        if "resguardo" not in columnas:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE estudiantes ADD COLUMN resguardo BOOLEAN DEFAULT 1 NOT NULL"))
        for columna, tipo in (
            ("pendiente_simat", "BOOLEAN DEFAULT 0 NOT NULL"),
            ("anio_matricula", "INTEGER"),
            ("creado_por_id", "INTEGER REFERENCES usuarios(id)"),
            ("creado_en", "DATETIME"),
        ):
            if columna not in columnas:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE estudiantes ADD COLUMN {columna} {tipo}"))

    if "fotos_estudiante" in tablas:
        columnas_info = {c["name"]: c for c in inspector.get_columns("fotos_estudiante")}
        if "anio_lectivo" not in columnas_info:
            with engine.begin() as conn:
                anio_actual = fechas.anio_lectivo_actual()
                conn.execute(
                    text(f"ALTER TABLE fotos_estudiante ADD COLUMN anio_lectivo INTEGER DEFAULT {anio_actual} NOT NULL")
                )
        elif columnas_info["anio_lectivo"]["nullable"] is False:
            # anio_lectivo pasó a ser opcional (NULL = documento permanente,
            # no ligado a un año). SQLite no deja quitar el NOT NULL con
            # ALTER COLUMN, así que se recrea la tabla preservando los datos.
            reconstruir_tabla(
                "fotos_estudiante",
                ["id", "estudiante_id", "etiqueta", "anio_lectivo", "nombre_archivo", "orden", "subido_en"],
            )
        columnas_fotos = {c["name"] for c in inspect(engine).get_columns("fotos_estudiante")}
        if "uuid_cliente" not in columnas_fotos:
            # Subidas desde el celular sin conexión (cola en el navegador): si
            # la respuesta se pierde y el celular reintenta, el mismo
            # uuid_cliente evita guardar el documento dos veces.
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE fotos_estudiante ADD COLUMN uuid_cliente VARCHAR(36)"))

    if "revisiones_boletin" in tablas:
        columnas = {c["name"] for c in inspector.get_columns("revisiones_boletin")}
        if "estudiantes_pendientes" not in columnas:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE revisiones_boletin ADD COLUMN estudiantes_pendientes VARCHAR(1000)"))
        if "revisado_por" not in columnas:
            # De paso se corrige el UNIQUE original (no incluía "periodo",
            # lo que habría impedido tener revisiones de distintos períodos
            # para el mismo grupo/año) — se recrea la tabla preservando filas.
            reconstruir_tabla(
                "revisiones_boletin",
                [
                    "id", "sede_id", "grado", "curso", "anio_lectivo", "periodo", "completo",
                    "materias_faltantes", "observaciones_completas", "notas", "estudiantes_pendientes",
                    "revisado_en",
                ],
            )

    if "notas_sapred" in tablas:
        columnas = {c["name"] for c in inspector.get_columns("notas_sapred")}
        if "nombre_sapred" not in columnas:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE notas_sapred ADD COLUMN nombre_sapred VARCHAR(200)"))

    if "auditorias_sapred" in tablas:
        columnas = {c["name"] for c in inspector.get_columns("auditorias_sapred")}
        if "tipo" not in columnas:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE auditorias_sapred ADD COLUMN tipo VARCHAR(20) DEFAULT 'notas' NOT NULL")
                )
        if "carpeta_salida" not in columnas:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE auditorias_sapred ADD COLUMN carpeta_salida VARCHAR(300)"))
        for columna, tipo in (("periodos", "VARCHAR(50)"), ("grados", "VARCHAR(100)")):
            if columna not in columnas:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE auditorias_sapred ADD COLUMN {columna} {tipo}"))

    if "asignaciones_docente" in tablas:
        columnas = {c["name"] for c in inspector.get_columns("asignaciones_docente")}
        if "area_id" not in columnas:
            # También se quita el UNIQUE por grupo: ahora puede haber varias
            # asignaciones por grupo (una por área) cuando aplique.
            reconstruir_tabla(
                "asignaciones_docente", ["id", "docente_id", "sede_id", "grado", "curso", "anio_lectivo"]
            )

    if "diagnosticos_observaciones" in tablas:
        columnas = {c["name"] for c in inspector.get_columns("diagnosticos_observaciones")}
        if "estado" not in columnas:
            # Nace la entidad Caso (antes era una nota plana): además de
            # columnas nuevas, estudiante_id pasa a ser NOT NULL (un caso
            # siempre es de un estudiante puntual) — SQLite no deja quitar
            # ni poner NOT NULL con ALTER TABLE, así que se reconstruye. La
            # tabla nace vacía en producción (se verificó antes de este
            # cambio), así que no hay filas que pudieran violar el NOT NULL.
            reconstruir_tabla(
                "diagnosticos_observaciones",
                [
                    "id", "sede_id", "grado", "curso", "estudiante_id", "categoria", "titulo", "detalle",
                    "fecha", "autor_usuario_id", "creado_en",
                ],
            )

    if "diagnosticos_mencion" in tablas:
        columnas = {c["name"] for c in inspector.get_columns("diagnosticos_mencion")}
        nuevas = {
            "confianza": "ALTER TABLE diagnosticos_mencion ADD COLUMN confianza VARCHAR(10) DEFAULT 'alta' NOT NULL",
            "texto_compartido": "ALTER TABLE diagnosticos_mencion ADD COLUMN texto_compartido BOOLEAN DEFAULT 0 NOT NULL",
            "candidatos_json": "ALTER TABLE diagnosticos_mencion ADD COLUMN candidatos_json TEXT",
        }
        faltantes = [sql for col, sql in nuevas.items() if col not in columnas]
        if faltantes:
            with engine.begin() as conn:
                for sql in faltantes:
                    conn.execute(text(sql))

    if "datos_ficha_estudiante" in tablas:
        columnas = {c["name"] for c in inspector.get_columns("datos_ficha_estudiante")}
        nuevas = {
            "padres": "ALTER TABLE datos_ficha_estudiante ADD COLUMN padres VARCHAR(250)",
            "telefono": "ALTER TABLE datos_ficha_estudiante ADD COLUMN telefono VARCHAR(40)",
            "huerfano": "ALTER TABLE datos_ficha_estudiante ADD COLUMN huerfano BOOLEAN",
            "necesita_albergue": "ALTER TABLE datos_ficha_estudiante ADD COLUMN necesita_albergue BOOLEAN",
            "grado_anterior": "ALTER TABLE datos_ficha_estudiante ADD COLUMN grado_anterior VARCHAR(20)",
            "retiro_anio_anterior": "ALTER TABLE datos_ficha_estudiante ADD COLUMN retiro_anio_anterior BOOLEAN",
            "motivo_retiro": "ALTER TABLE datos_ficha_estudiante ADD COLUMN motivo_retiro VARCHAR(10)",
            "promovido": "ALTER TABLE datos_ficha_estudiante ADD COLUMN promovido BOOLEAN",
            "repitente": "ALTER TABLE datos_ficha_estudiante ADD COLUMN repitente BOOLEAN",
        }
        faltantes = [sql for col, sql in nuevas.items() if col not in columnas]
        if faltantes:
            with engine.begin() as conn:
                for sql in faltantes:
                    conn.execute(text(sql))

    if "bloques_horario" in tablas:
        columnas = {c["name"] for c in inspector.get_columns("bloques_horario")}
        nuevas = {
            "estado": "ALTER TABLE bloques_horario ADD COLUMN estado VARCHAR(20) DEFAULT 'activo' NOT NULL",
            "conflicto_revisado": "ALTER TABLE bloques_horario ADD COLUMN conflicto_revisado BOOLEAN DEFAULT 0 NOT NULL",
            "resuelto_por": "ALTER TABLE bloques_horario ADD COLUMN resuelto_por VARCHAR(100)",
            "resuelto_en": "ALTER TABLE bloques_horario ADD COLUMN resuelto_en DATETIME",
        }
        faltantes = [sql for col, sql in nuevas.items() if col not in columnas]
        if faltantes:
            with engine.begin() as conn:
                for sql in faltantes:
                    conn.execute(text(sql))


# --- 3. Claves foráneas rotas -------------------------------------------------


def reparar_claves_foraneas_rotas() -> list[str]:
    """Recrea, con la definición del modelo, las tablas cuyas claves foráneas
    apuntan a una tabla que ya no existe. Caso real (encontrado el
    11/09/2026): al recrear revisiones_boletin (RENAME a _old, crear, DROP
    _old) SQLite reescribió la referencia de pendientes_boletin hacia
    "revisiones_boletin_old"; con foreign_keys=ON cada pendiente nuevo
    fallaría con "no such table". Las filas no se pierden: se copian tal cual."""
    raw = engine.raw_connection()
    try:
        con = raw.driver_connection
        existentes = _tablas_existentes(con)
        rotas: list[tuple[str, list[str], list[str]]] = []
        for tabla in Base.metadata.sorted_tables:
            if tabla.name not in existentes:
                continue
            destinos = {fk[2] for fk in con.execute(f'PRAGMA foreign_key_list("{tabla.name}")')}
            faltantes = sorted(destinos - existentes)
            if faltantes:
                columnas_bd = {c[1] for c in con.execute(f'PRAGMA table_info("{tabla.name}")')}
                columnas = [c.name for c in tabla.columns if c.name in columnas_bd]
                rotas.append((tabla.name, columnas, faltantes))
    finally:
        raw.close()

    for nombre, columnas, faltantes in rotas:
        _log(f"{nombre}: clave foránea hacia tabla inexistente {faltantes} → se recrea")
        reconstruir_tabla(nombre, columnas)
    return [nombre for nombre, _, _ in rotas]


# --- 3b. Tabla 'asistencias': esquema viejo -> esquema por bloque -----------


def _migrar_tabla_asistencias_v2() -> bool:
    """`asistencias` tenía un esquema mínimo (id, estudiante_id, fecha,
    presente, registrado_en): sin autor, sin bloque, sin historial, y
    confirmado con 0 filas en producción (el módulo nunca se usó). El
    esquema nuevo (asistencia por bloque de horario, con auditoría) es
    incompatible columna a columna, así que se recrea la tabla en vez de
    migrar datos — pero SOLO si de verdad sigue vacía; si alguna vez llega a
    tener filas, esto se detiene y avisa en vez de inventar en qué docente o
    bloque repartirlas."""
    inspector = inspect(engine)
    if "asistencias" not in inspector.get_table_names():
        return False
    columnas = {c["name"] for c in inspector.get_columns("asistencias")}
    if "uuid_cliente" in columnas:
        return False  # ya está en el esquema nuevo

    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM asistencias")).scalar_one()
    if total > 0:
        raise RuntimeError(
            f"La tabla 'asistencias' tiene {total} fila(s) con el esquema viejo "
            "(sin autor/bloque/estado). No se recrea sola para no perder datos: "
            "hace falta decidir a mano cómo repartirlas en las columnas nuevas."
        )

    respaldar("antes_recrear_asistencias_v2")
    raw = engine.raw_connection()
    try:
        con = raw.driver_connection
        nivel_previo = con.isolation_level
        con.isolation_level = None
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("DROP TABLE asistencias")
        con.execute("PRAGMA foreign_keys=ON")
        con.isolation_level = nivel_previo
    finally:
        raw.close()
    _log("tabla 'asistencias' (vacía) recreada con el esquema nuevo — asistencia por bloque de horario")
    return True


# --- 4. Índices ---------------------------------------------------------------


def asegurar_indices() -> list[str]:
    """Crea los índices declarados en models.py que todavía no existan en la
    base (create_all solo los crea junto con una tabla nueva). Si un índice
    único no se puede crear porque ya hay filas duplicadas, se avisa y la app
    arranca igual: nunca se borran datos para forzarlo."""
    with engine.connect() as conn:
        existentes = {
            r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))
        }
    creados: list[str] = []
    for tabla in Base.metadata.sorted_tables:
        for indice in sorted(tabla.indexes, key=lambda i: i.name):
            if indice.name in existentes:
                continue
            try:
                indice.create(bind=engine)
            except IntegrityError as e:
                _log(f"AVISO: no se creó el índice único {indice.name} por filas duplicadas ({e.orig})")
                continue
            creados.append(indice.name)
            _log(f"índice creado: {indice.name}")
    return creados


# --- 5. Datos semilla y backfills ------------------------------------------------


def sembrar_areas_secundaria() -> None:
    """Catálogo de áreas para 6°-11° (básica secundaria y media), con base
    en el boletín real de SAPRED. Preescolar/primaria (0-5) se dejan sin
    sembrar hasta tener un boletín real de esos grados — no se inventa
    currículo."""
    AREAS_SECUNDARIA = [
        ("COE", "Comunicación, Oralidad y Escritura"),
        ("DESM", "Desempeño Actitudinal"),
        ("ETIC", "Ética y Valores"),
        ("FIS", "Física"),
        ("JTD", "Juegos Tradicionales y Deporte"),
        ("LEI", "Lengua Extranjera Inglés"),
        ("LM", "Lengua Materna"),
        ("MATE", "Matemáticas"),
        ("NAP", "Naturaleza, Ambiente y Protección"),
        ("PSA", "Producción y Soberanía Alimentaria"),
        ("QUIM", "Química"),
        ("TPEC", "Talento Propio y Expresión Cultural"),
        ("TPI", "Tecnología Propia e Informática"),
        ("TAL", "Territorio, Autonomía y Liderazgo"),
    ]
    GRADOS_SECUNDARIA_MEDIA = range(6, 12)  # 6° a 11°

    with Session(engine) as db:
        if db.query(models.Area).count() > 0:
            return  # ya sembrado
        for codigo, nombre in AREAS_SECUNDARIA:
            area = models.Area(codigo=codigo, nombre=nombre)
            db.add(area)
            db.flush()
            for grado in GRADOS_SECUNDARIA_MEDIA:
                db.add(models.AreaGrado(area_id=area.id, grado=grado))
        db.commit()


def sembrar_areas_primaria_confirmadas() -> None:
    """Áreas confirmadas por grado en primaria/preescolar, a medida que se
    ven reportes reales de SAPRED (Reportes > Resultados Académicos >
    Consolidado de Asignaturas por periodo). No se inventa: cada grado que
    aparece aquí es porque ya se vio su reporte real. Reutiliza las Area que
    ya existen (mismos códigos que en secundaria), solo agrega el vínculo
    AreaGrado que falte — es seguro correrlo en cada arranque."""
    # Grado 1 (Primero) confirmado con el reporte real de SEDE#01 IETABA,
    # curso 1-1, período 2 (2026-08-20): esas y solo esas 8 áreas aparecen.
    AREAS_POR_GRADO_CONFIRMADO = {
        1: ["COE", "DESM", "JTD", "LM", "MATE", "NAP", "TPEC", "TAL"],
    }

    with Session(engine) as db:
        areas = {a.codigo: a for a in db.query(models.Area).all()}
        existentes = {(ag.area_id, ag.grado) for ag in db.query(models.AreaGrado).all()}
        cambios = False
        for grado, codigos in AREAS_POR_GRADO_CONFIRMADO.items():
            for codigo in codigos:
                area = areas.get(codigo)
                if area is None or (area.id, grado) in existentes:
                    continue
                db.add(models.AreaGrado(area_id=area.id, grado=grado))
                cambios = True
        if cambios:
            db.commit()


def backfill_pendientes_legacy() -> None:
    """Convierte los textos libres materias_faltantes/observaciones_completas
    de revisiones ya guardadas por la secretaria (antes de que existiera
    PendienteBoletin) en filas estructuradas y consultables. Es idempotente:
    solo crea un pendiente si esa revisión todavía no tiene uno equivalente,
    así que es seguro dejarla correr en cada arranque."""

    def _sin_acentos(texto: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))

    with Session(engine) as db:
        areas = db.scalars(select(models.Area)).all()
        revisiones = db.scalars(select(models.RevisionBoletin)).all()
        for r in revisiones:
            pendientes_actuales = db.scalars(
                select(models.PendienteBoletin).where(models.PendienteBoletin.revision_id == r.id)
            ).all()

            if r.materias_faltantes and r.materias_faltantes.strip():
                texto = r.materias_faltantes.strip()
                ya_existe = any(
                    p.tipo == "nota" and (p.detalle or "").strip().lower() == texto.lower()
                    for p in pendientes_actuales
                )
                if not ya_existe:
                    texto_norm = _sin_acentos(texto.lower())
                    area_coincide = next(
                        (
                            a
                            for a in areas
                            if _sin_acentos(a.nombre.lower()) in texto_norm
                            or texto_norm in _sin_acentos(a.nombre.lower())
                            or a.codigo.lower() in texto_norm.split()
                        ),
                        None,
                    )
                    nuevo = models.PendienteBoletin(
                        revision_id=r.id,
                        area_id=area_coincide.id if area_coincide else None,
                        tipo="nota",
                        detalle=texto,
                    )
                    db.add(nuevo)
                    pendientes_actuales.append(nuevo)

            if not r.observaciones_completas:
                ya_existe_obs = any(
                    p.tipo == "observacion" and p.area_id is None and p.estudiante_id is None
                    for p in pendientes_actuales
                )
                if not ya_existe_obs:
                    db.add(
                        models.PendienteBoletin(
                            revision_id=r.id,
                            tipo="observacion",
                            detalle=r.notas or "Observaciones del grupo pendientes por completar",
                        )
                    )
        db.commit()


# --- 6. RBAC: catálogo de permisos y roles del sistema (Fase 3) --------------


def sincronizar_catalogo_permisos() -> list[str]:
    """Inserta en `permisos` los códigos de app/permisos.py que falten,
    actualiza módulo/descripción/sensible de los que ya existen, y marca
    activo=0 los que quedaron en la base pero ya no están en el catálogo
    (nunca se borran: rol_permisos podría referenciarlos, y borrar perdería
    el historial de qué tenía cada rol). Idempotente."""
    creados: list[str] = []
    with Session(engine) as db:
        existentes = {p.codigo: p for p in db.scalars(select(models.Permiso)).all()}
        for definicion in permisos_catalogo.CATALOGO:
            fila = existentes.get(definicion.codigo)
            if fila is None:
                db.add(
                    models.Permiso(
                        codigo=definicion.codigo, modulo=definicion.modulo,
                        descripcion=definicion.descripcion, sensible=definicion.sensible, activo=True,
                    )
                )
                creados.append(definicion.codigo)
            else:
                fila.modulo = definicion.modulo
                fila.descripcion = definicion.descripcion
                fila.sensible = definicion.sensible
                if not fila.activo:
                    fila.activo = True  # volvió a aparecer en el catálogo
        for codigo, fila in existentes.items():
            if codigo not in permisos_catalogo.CODIGOS and fila.activo:
                fila.activo = False
                _log(f"permiso ya no está en el catálogo, se desactiva: {codigo}")
        db.commit()
    if creados:
        _log(f"permisos nuevos en el catálogo: {', '.join(creados)}")
    return creados


def sembrar_roles_sistema() -> list[str]:
    """Crea los 5 roles del sistema (app/permisos.py: ROLES_SISTEMA) SOLO si
    todavía no existen, con sus permisos iniciales. Si un rol ya existe, NO
    se tocan sus permisos: lo que haya decidido el administrador manda, y un
    reinicio del servidor nunca lo revierte. Debe correr DESPUÉS de
    sincronizar_catalogo_permisos()."""
    creados: list[str] = []
    with Session(engine) as db:
        permisos_por_codigo = {p.codigo: p for p in db.scalars(select(models.Permiso)).all()}
        for definicion in permisos_catalogo.ROLES_SISTEMA:
            existente = db.scalar(select(models.Rol).where(models.Rol.codigo == definicion.codigo))
            if existente is not None:
                if not existente.es_sistema:
                    existente.es_sistema = True  # corrige si por algo quedó en False
                continue
            rol = models.Rol(
                codigo=definicion.codigo, nombre=definicion.nombre,
                descripcion=definicion.descripcion, es_sistema=True, activo=True,
            )
            db.add(rol)
            db.flush()
            for codigo_permiso in definicion.permisos:
                permiso = permisos_por_codigo.get(codigo_permiso)
                if permiso is None:
                    raise RuntimeError(
                        f"El rol de sistema '{definicion.codigo}' referencia el permiso "
                        f"'{codigo_permiso}', que no existe en el catálogo de permisos."
                    )
                db.add(models.RolPermiso(rol_id=rol.id, permiso_id=permiso.id))
            creados.append(definicion.codigo)
        db.commit()
    if creados:
        _log(f"roles del sistema sembrados: {', '.join(creados)}")
    return creados


def otorgar_permisos_nuevos(permisos_nuevos: list[str]) -> list[str]:
    """Cuando un permiso APARECE por primera vez en el catálogo, se le da a
    los roles del sistema que ya existían y que lo traen en su definición
    (sembrar_roles_sistema no toca roles existentes). Solo corre para los
    códigos recién creados — o sea, una única vez por permiso —, así nunca
    revierte que el administrador se lo haya quitado después a un rol."""
    if not permisos_nuevos:
        return []
    otorgados: list[str] = []
    with Session(engine) as db:
        permisos = {p.codigo: p for p in db.scalars(select(models.Permiso).where(models.Permiso.codigo.in_(permisos_nuevos)))}
        for definicion in permisos_catalogo.ROLES_SISTEMA:
            rol = db.scalar(select(models.Rol).where(models.Rol.codigo == definicion.codigo))
            if rol is None:
                continue
            ya = set(db.scalars(select(models.RolPermiso.permiso_id).where(models.RolPermiso.rol_id == rol.id)))
            for codigo in permisos_nuevos:
                p = permisos.get(codigo)
                if p is not None and codigo in definicion.permisos and p.id not in ya:
                    db.add(models.RolPermiso(rol_id=rol.id, permiso_id=p.id))
                    otorgados.append(f"{definicion.codigo}:{codigo}")
        db.commit()
    if otorgados:
        _log(f"permisos nuevos otorgados a roles existentes: {', '.join(otorgados)}")
    return otorgados


def administrador_con_todos_los_permisos() -> list[str]:
    """Decisión del colegio (19/10/2026): el rol Administrador ve TODO, sin
    excepciones (incluidas las observaciones confidenciales). Corre en cada
    arranque: si el catálogo trae un permiso que el Administrador no tiene,
    se le da. rbac_admin.establecer_permisos_rol impide quitárselos."""
    otorgados: list[str] = []
    with Session(engine) as db:
        rol = db.scalar(select(models.Rol).where(models.Rol.codigo == permisos_catalogo.ROL_TODOS_LOS_PERMISOS))
        if rol is None:
            return []
        ya = set(db.scalars(select(models.RolPermiso.permiso_id).where(models.RolPermiso.rol_id == rol.id)))
        for permiso in db.scalars(select(models.Permiso)).all():
            if permiso.id not in ya:
                db.add(models.RolPermiso(rol_id=rol.id, permiso_id=permiso.id))
                otorgados.append(permiso.codigo)
        db.commit()
    if otorgados:
        _log(f"permisos otorgados al Administrador (ve todo): {', '.join(otorgados)}")
    return otorgados


# --- Punto de entrada ---------------------------------------------------------------


def ejecutar() -> dict[str, list[str]]:
    _migrar_tabla_asistencias_v2()

    # Si el modelo trae tablas nuevas y la base ya está en uso, se respalda
    # antes de tocarla (crear tablas no borra nada, pero el respaldo deja un
    # punto de retorno claro para cada cambio de estructura).
    existentes = set(inspect(engine).get_table_names())
    faltantes = [t.name for t in Base.metadata.sorted_tables if t.name not in existentes]
    if faltantes:
        _log(f"tablas nuevas del modelo: {', '.join(faltantes)}")
        if existentes:
            respaldar("antes_crear_tablas")
    Base.metadata.create_all(bind=engine)
    if faltantes:
        _log(f"tablas creadas: {', '.join(faltantes)}")
    asegurar_columnas_sqlite()
    reparadas = reparar_claves_foraneas_rotas()
    indices = asegurar_indices()
    permisos_nuevos = sincronizar_catalogo_permisos()
    roles_nuevos = sembrar_roles_sistema()
    otorgar_permisos_nuevos(permisos_nuevos)
    administrador_con_todos_los_permisos()
    sembrar_areas_secundaria()
    sembrar_areas_primaria_confirmadas()
    backfill_pendientes_legacy()
    if not reparadas and not indices and not permisos_nuevos and not roles_nuevos:
        _log("base al día: nada que migrar")
    return {
        "tablas_reparadas": reparadas,
        "indices_creados": indices,
        "permisos_sincronizados": permisos_nuevos,
        "roles_sembrados": roles_nuevos,
    }
