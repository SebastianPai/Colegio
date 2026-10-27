"""Orquestación de la auditoría de notas contra SAPRED: crear una corrida,
lanzar el proceso de Playwright (en herramientas/importar_sapred/) como
subproceso, y recibir su progreso. La extracción/navegación en sí vive en
ese script Node (no se reescribe aquí — este módulo solo la dirige).

No hay cola/worker/Redis: es un solo BackgroundTask de FastAPI más un
subproceso, alcanza de sobra para el volumen real de esta app (una persona,
unas pocas corridas por período). El progreso se expone por polling, no por
WebSocket, porque nada más en esta app usa WebSocket todavía."""

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import generacion_boletines, models, schemas, seguridad

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent.parent
DIR_HERRAMIENTA = RAIZ_PROYECTO / "herramientas" / "importar_sapred"
SCRIPT_HEADLESS = DIR_HERRAMIENTA / "importar_sapred_headless.js"
# La automatización del Boletín (llena el formulario sola: sede, grado,
# curso, período) tuvo un bug real que la dejaba trabada en el campo Curso
# — la regex que buscaba la opción "[TODOS LAS SECCIONES]" también hacía
# match con el propio placeholder "[ESCOJA UNA SECCIÓN]" (contiene la
# palabra "SECCIÓN"), así que "elegía" el placeholder y nunca avanzaba.
# Corregido en sapred_core.js (_elegirOpcionQueContenga ya descarta la
# opción [0]) y confirmado con herramientas/importar_sapred/
# probar_boletin_en_vivo.js: el reporte se genera completo. Un bug aparte
# de la propia SAPRED (su mostrar() revienta con un campo que no se usa,
# "filDef3") queda ahí pero es inofensivo — no impide nada.
#
# Si algún día vuelve a fallar y hace falta un respaldo sin automatizar el
# formulario, existe capturar_boletin_headless.js (captura manual: la
# persona navega y genera cada boletín ella misma en SAPRED, el script solo
# vigila y captura) — ver LEEME.txt.
SCRIPT_HEADLESS_BOLETIN = DIR_HERRAMIENTA / "importar_boletin_headless.js"
# Generación del boletín general (PDF por sede) — no importa nada, solo
# produce archivos. Ver app/generacion_boletines.py y el propio script.
SCRIPT_HEADLESS_BOLETIN_PDF = DIR_HERRAMIENTA / "generar_boletines_headless.js"
DIR_LOGS = DIR_HERRAMIENTA / "logs"

ESTADOS_EN_CURSO = {"pendiente", "esperando_login", "en_proceso"}
ESTADOS_TERMINALES = {"completada", "error"}


def _detalle_sedes_a_lista(texto: str | None) -> list[schemas.AuditoriaSapredDetalleSede]:
    if not texto:
        return []
    try:
        return [schemas.AuditoriaSapredDetalleSede(**d) for d in json.loads(texto)]
    except (json.JSONDecodeError, TypeError):
        return []


def a_schema(auditoria: models.AuditoriaSapred) -> schemas.AuditoriaSapred:
    return schemas.AuditoriaSapred(
        id=auditoria.id,
        creado_en=auditoria.creado_en,
        terminado_en=auditoria.terminado_en,
        anio_lectivo=auditoria.anio_lectivo,
        periodo=auditoria.periodo,
        grado=auditoria.grado,
        periodos=auditoria.periodos or [auditoria.periodo],
        grados=auditoria.grados or ([auditoria.grado] if auditoria.grado is not None else []),
        tipo=getattr(auditoria, "tipo", "notas") or "notas",
        estado=auditoria.estado,
        sede_actual=auditoria.sede_actual,
        grado_actual=auditoria.grado_actual,
        sedes_totales=auditoria.sedes_totales,
        sedes_completadas=auditoria.sedes_completadas,
        estudiantes_revisados=auditoria.estudiantes_revisados,
        pendientes_encontrados=auditoria.pendientes_encontrados,
        carpeta_salida=getattr(auditoria, "carpeta_salida", None),
        detalle_sedes=_detalle_sedes_a_lista(auditoria.detalle_sedes),
        error=auditoria.error,
    )


# Etiqueta SAPRED del grado -> número (igual que GRADOS en
# herramientas/importar_sapred/sapred_core.js). detalle_sedes guarda
# "<nombre sede> (<ETIQUETA GRADO>)".
SAPRED_GRADOS = {
    "TRANSICION": 0, "PRIMERO": 1, "SEGUNDO": 2, "TERCERO": 3, "CUARTO": 4,
    "QUINTO": 5, "SEXTO": 6, "SEPTIMO": 7, "OCTAVO": 8, "NOVENO": 9,
    "DECIMO": 10, "ONCE": 11,
}


def _partir_etiqueta_sede(etiqueta: str) -> tuple[str, int | None, int | None]:
    """'SEDE # 01 I.E.T.A.B.A. (PRIMERO)' -> ('SEDE # 01 I.E.T.A.B.A.', 1, None).
    Las corridas de varios periodos lo marcan adentro:
    'SEDE # 01 I.E.T.A.B.A. (PRIMERO · periodo 3)' -> (..., 1, 3)."""
    m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", etiqueta or "")
    if not m:
        return (etiqueta or "").strip(), None, None
    partes = [x.strip() for x in m.group(2).split("·")]
    grado = SAPRED_GRADOS.get(partes[0].upper())
    m_periodo = re.search(r"periodo\s*(\d)", " ".join(partes[1:]), re.I)
    return m.group(1).strip(), grado, int(m_periodo.group(1)) if m_periodo else None


def scope_reintento(db: Session, auditoria: models.AuditoriaSapred) -> dict | None:
    """A partir de detalle_sedes arma el alcance para reintentar SOLO lo que no
    quedó 'completada' (advertencia/error). Devuelve None si no hay nada que
    reintentar; lanza ValueError si hay fallos pero no se pudo identificar la
    sede (para no re-correr todo sin querer)."""
    fallidas = [
        d for d in _detalle_sedes_a_lista(auditoria.detalle_sedes) if d.estado != "completada"
    ]
    if not fallidas:
        return None

    nombres: set[str] = set()
    grados: set[int | None] = set()
    periodos: set[int] = set()
    for d in fallidas:
        nombre, grado, periodo = _partir_etiqueta_sede(d.sede)
        nombres.add(nombre)
        grados.add(grado)
        periodos.add(periodo if periodo is not None else auditoria.periodo)

    por_nombre = {s.nombre: s.id for s in db.scalars(select(models.Sede)).all()}
    sede_ids = sorted({por_nombre[n] for n in nombres if n in por_nombre})
    if not sede_ids:
        raise ValueError(
            "No pude identificar las sedes que fallaron para acotar el reintento; "
            "vuelve a lanzar la auditoría manualmente."
        )

    # Se acota a los grados y periodos que fallaron (el subproceso acepta
    # varios). Si de algún fallo no se supo el grado, se reintentan todos.
    return {
        "anio_lectivo": auditoria.anio_lectivo,
        "periodos": sorted(periodos),
        "tipo": getattr(auditoria, "tipo", "notas") or "notas",
        "sede_ids": sede_ids,
        "grados": None if None in grados else sorted(grados),
        "n_fallidas": len(fallidas),
        "sedes_fallidas": sorted(nombres),
    }


def cancelar_auditoria(db: Session, auditoria: models.AuditoriaSapred) -> models.AuditoriaSapred:
    """Marca una corrida como terminada en error ('Cancelada'). Sirve de
    salida cuando quedó trabada en 'pendiente'/'esperando_login' (Chrome
    cerrado sin iniciar sesión, subproceso muerto, reinicio del PC…) y no
    deja empezar otra. No mata el subproceso —si sigue vivo, su próximo
    reporte de progreso volverá a mover el estado; por eso el front solo
    ofrece cancelar en las corridas trabadas."""
    auditoria.estado = "error"
    auditoria.error = auditoria.error or "Cancelada por el usuario"
    auditoria.terminado_en = dt.datetime.utcnow()
    db.commit()
    db.refresh(auditoria)
    return auditoria


def hay_auditoria_en_curso(db: Session) -> models.AuditoriaSapred | None:
    return db.scalar(
        select(models.AuditoriaSapred)
        .where(models.AuditoriaSapred.estado.in_(ESTADOS_EN_CURSO))
        .order_by(models.AuditoriaSapred.creado_en.desc())
    )


TIPOS_VALIDOS = {"notas", "boletin", "ambos", "boletin_pdf"}


def crear_auditoria(db: Session, datos: schemas.AuditoriaSapredCrear) -> models.AuditoriaSapred:
    tipo = datos.tipo if datos.tipo in TIPOS_VALIDOS else "notas"
    anio = datos.anio_lectivo or dt.date.today().year
    auditoria = models.AuditoriaSapred(
        anio_lectivo=anio,
        periodo=datos.periodo,
        grado=datos.grado,
        periodos=",".join(str(p) for p in datos.periodos) if len(datos.periodos) > 1 else None,
        grados=",".join(str(g) for g in datos.grados) if datos.grados and len(datos.grados) > 1 else None,
        tipo=tipo,
        sede_ids=",".join(str(i) for i in datos.sede_ids) if datos.sede_ids else None,
        estado="pendiente",
        carpeta_salida=(
            generacion_boletines.carpeta_relativa_para(anio, datos.periodo)
            if tipo == "boletin_pdf"
            else None
        ),
    )
    db.add(auditoria)
    db.commit()
    db.refresh(auditoria)
    return auditoria


def _limpiar_logs_viejos(horas: int = 24 * 7) -> None:
    """No deja acumular logs de auditorías viejas indefinidamente."""
    if not DIR_LOGS.exists():
        return
    limite = dt.datetime.now().timestamp() - horas * 3600
    for archivo in DIR_LOGS.glob("auditoria_*.log"):
        try:
            if archivo.stat().st_mtime < limite:
                archivo.unlink()
        except OSError:
            pass  # el archivo puede estar en uso justo en ese instante, no es grave


def lanzar_proceso(auditoria: models.AuditoriaSapred, credenciales: dict | None = None) -> None:
    """Arranca el/los subproceso(s) Node/Playwright para esta auditoría. No
    espera a que terminen — reportan su propio progreso llamando de vuelta a
    la API (ver /api/boletines/auditoria-sapred/{id}/progreso).

    `credenciales` = {"usuario": ..., "clave": ...} o None. Si viene, se pasa
    al subproceso SOLO por variable de entorno (nunca en argv ni en el log),
    y no se guarda en ningún lado. El script Node las usa para el login y,
    si fallan o no vienen, cae al login manual de siempre."""
    tipo = getattr(auditoria, "tipo", "notas") or "notas"
    if tipo == "ambos":
        # Consolidado (notas) y luego Boletín, encadenados, reportando ambos
        # al mismo audit id. El segundo espera a que termine el primero.
        import threading

        def _encadenar():
            p1 = _popen_script(auditoria, SCRIPT_HEADLESS, credenciales)
            if p1 is not None:
                p1.wait()
            _popen_script(auditoria, SCRIPT_HEADLESS_BOLETIN, credenciales)

        threading.Thread(target=_encadenar, daemon=True).start()
        return

    script = {
        "boletin": SCRIPT_HEADLESS_BOLETIN,
        "boletin_pdf": SCRIPT_HEADLESS_BOLETIN_PDF,
    }.get(tipo, SCRIPT_HEADLESS)
    _popen_script(auditoria, script, credenciales)


def _popen_script(
    auditoria: models.AuditoriaSapred, script: Path, credenciales: dict | None
) -> "subprocess.Popen | None":
    DIR_LOGS.mkdir(parents=True, exist_ok=True)
    _limpiar_logs_viejos()
    archivo_log = DIR_LOGS / f"auditoria_{auditoria.id}.log"

    args = [
        "node",
        str(script),
        f"--audit-id={auditoria.id}",
        f"--periodo={auditoria.periodo}",
    ]
    if auditoria.periodos:
        args.append(f"--periodos={auditoria.periodos}")
    if auditoria.grados:
        args.append(f"--grados={auditoria.grados}")
    elif auditoria.grado is not None:
        args.append(f"--grado={auditoria.grado}")
    if auditoria.sede_ids:
        args.append(f"--sedes={auditoria.sede_ids}")
    if getattr(auditoria, "carpeta_salida", None):
        # Node y el backend comparten disco: se le pasa la ruta ABSOLUTA de la
        # carpeta de salida para que deje ahí los PDF por grado.
        args.append(f"--carpeta={generacion_boletines.carpeta_abs(auditoria.carpeta_salida)}")

    # Las credenciales van SOLO por entorno (no en argv, que se ve en el
    # Administrador de tareas) y NO se escriben en el log. Si no vienen, el
    # script espera el login manual como siempre.
    entorno = dict(os.environ)
    if credenciales and credenciales.get("usuario") and credenciales.get("clave"):
        entorno["SAPRED_USUARIO"] = str(credenciales["usuario"])
        entorno["SAPRED_CLAVE"] = str(credenciales["clave"])
    # Fase 4.1: identidad de servicio para los endpoints internos que este
    # script llama de vuelta (/progreso, /ensamblar-sede, /*-bloques). Mismo
    # criterio que las credenciales de arriba: solo por entorno, nunca en
    # argv ni en el log.
    entorno["SAPRED_API_TOKEN"] = seguridad.token_servicio()

    with open(archivo_log, "a", encoding="utf-8") as log:
        return subprocess.Popen(
            args,
            cwd=str(DIR_HERRAMIENTA),
            stdout=log,
            stderr=subprocess.STDOUT,
            env=entorno,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )


def obtener_auditoria(db: Session, auditoria_id: int) -> models.AuditoriaSapred | None:
    return db.get(models.AuditoriaSapred, auditoria_id)


def listar_auditorias(
    db: Session,
    limite: int = 20,
    tipos: set[str] | None = None,
    excluir_tipos: set[str] | None = None,
) -> list[models.AuditoriaSapred]:
    consulta = select(models.AuditoriaSapred).order_by(models.AuditoriaSapred.creado_en.desc())
    if tipos:
        consulta = consulta.where(models.AuditoriaSapred.tipo.in_(tipos))
    if excluir_tipos:
        consulta = consulta.where(models.AuditoriaSapred.tipo.notin_(excluir_tipos))
    return list(db.scalars(consulta.limit(limite)).all())


def actualizar_progreso(
    db: Session, auditoria_id: int, datos: schemas.AuditoriaSapredProgreso
) -> models.AuditoriaSapred | None:
    auditoria = db.get(models.AuditoriaSapred, auditoria_id)
    if auditoria is None:
        return None

    if datos.estado is not None:
        auditoria.estado = datos.estado
        if datos.estado in ESTADOS_TERMINALES:
            auditoria.terminado_en = dt.datetime.utcnow()
    if datos.sede_actual is not None:
        auditoria.sede_actual = datos.sede_actual
    if datos.grado_actual is not None:
        auditoria.grado_actual = datos.grado_actual
    if datos.sedes_totales is not None:
        auditoria.sedes_totales = datos.sedes_totales
    if datos.sedes_completadas:
        auditoria.sedes_completadas += datos.sedes_completadas
    if datos.estudiantes_revisados_delta:
        auditoria.estudiantes_revisados += datos.estudiantes_revisados_delta
    if datos.pendientes_encontrados_delta:
        auditoria.pendientes_encontrados += datos.pendientes_encontrados_delta
    if datos.error is not None:
        auditoria.error = datos.error
    if datos.detalle_sede is not None:
        lista = _detalle_sedes_a_lista(auditoria.detalle_sedes)
        lista.append(datos.detalle_sede)
        auditoria.detalle_sedes = json.dumps([d.model_dump() for d in lista], ensure_ascii=False)

    db.commit()
    db.refresh(auditoria)
    return auditoria
