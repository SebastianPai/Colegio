"""Regla de promoción de grado y permisos de coordinación.

Lo normal al matricular para el año siguiente:
  · aprobó el año (ninguna materia perdida)  → sube UN grado (0 → 1, no 0 → 2);
  · repite                                   → se queda en el mismo grado.
Cualquier otra cosa necesita permiso de coordinación (SolicitudPromocion):
  · "perdidas":  sube de grado llevando materias perdidas (una perdida = año perdido);
  · "salto":     sube más de un grado;
  · "retroceso": baja de grado.
Mientras la solicitud no esté aprobada, la ficha de matrícula no se genera
con ese grado (ver routers/certificados.py) — decisión de la institución."""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import fechas, models, reporte_notas, schemas

GRADO_MAXIMO = 11

MOTIVOS_TEXTO = {
    "perdidas": "Sube de grado con materias perdidas",
    "salto": "Salta grados (lo normal es subir uno)",
    "retroceso": "Baja de grado",
}


def motivos_para(grado_actual: int, grado_destino: int, hay_perdidas: bool) -> list[str]:
    motivos: list[str] = []
    if grado_destino > grado_actual + 1:
        motivos.append("salto")
    if grado_destino < grado_actual:
        motivos.append("retroceso")
    if grado_destino > grado_actual and hay_perdidas:
        motivos.append("perdidas")
    return motivos


def solicitud_a_salida(s: models.SolicitudPromocion) -> schemas.SolicitudPromocionOut:
    e = s.estudiante
    return schemas.SolicitudPromocionOut(
        id=s.id, estudiante_id=s.estudiante_id, estudiante_nombre=e.nombre_completo,
        estudiante_documento=e.documento, estudiante_grupo=e.grupo,
        anio_lectivo=s.anio_lectivo, grado_actual=s.grado_actual, grado_destino=s.grado_destino,
        motivos=[m for m in s.motivos.split(",") if m], materias_perdidas=s.materias_perdidas,
        detalle=json.loads(s.detalle or "[]"), justificacion=s.justificacion,
        solicitado_por_nombre=s.solicitado_por.nombre if s.solicitado_por else "",
        solicitado_en=s.solicitado_en, estado=s.estado,
        decidido_por_nombre=s.decidido_por.nombre if s.decidido_por else None,
        decidido_en=s.decidido_en, nota_decision=s.nota_decision, usada_en=s.usada_en,
    )


def solicitud_vigente(
    db: Session, estudiante_id: int, grado_destino: int, anio: int
) -> models.SolicitudPromocion | None:
    """La más reciente (no anulada) para ese estudiante, grado destino y año."""
    return db.scalar(
        select(models.SolicitudPromocion)
        .where(
            models.SolicitudPromocion.estudiante_id == estudiante_id,
            models.SolicitudPromocion.grado_destino == grado_destino,
            models.SolicitudPromocion.anio_lectivo == anio,
            models.SolicitudPromocion.estado != "anulada",
        )
        .order_by(models.SolicitudPromocion.solicitado_en.desc(), models.SolicitudPromocion.id.desc())
    )


def evaluar(db: Session, estudiante: models.Estudiante, grado_destino: int) -> schemas.EvaluacionPromocion:
    anio = fechas.anio_lectivo_actual()
    riesgo = reporte_notas.riesgo_promocion(db, estudiante.id, anio)
    motivos = motivos_para(estudiante.grado, grado_destino, bool(riesgo.perdidas))
    solicitud = solicitud_vigente(db, estudiante.id, grado_destino, anio) if motivos else None
    requiere = bool(motivos)
    return schemas.EvaluacionPromocion(
        estudiante_id=estudiante.id, anio_lectivo=anio,
        grado_actual=estudiante.grado, grado_destino=grado_destino,
        grado_esperado=min(estudiante.grado + 1, GRADO_MAXIMO),
        motivos=motivos, requiere_autorizacion=requiere,
        puede_generar=not requiere or (solicitud is not None and solicitud.estado == "aprobada"),
        solicitud=solicitud_a_salida(solicitud) if solicitud else None,
        riesgo=riesgo,
    )


def crear_solicitud(
    db: Session, estudiante: models.Estudiante, grado_destino: int, justificacion: str, usuario_id: int
) -> tuple[models.SolicitudPromocion | None, str | None]:
    """(solicitud, error). Si ya hay una pendiente o aprobada para ese grado
    y año, se devuelve esa en vez de crear otra."""
    ev = evaluar(db, estudiante, grado_destino)
    if not ev.requiere_autorizacion:
        return None, "Ese grado no necesita permiso de coordinación: se puede generar la ficha directamente."
    previa = solicitud_vigente(db, estudiante.id, grado_destino, ev.anio_lectivo)
    if previa is not None and previa.estado in ("pendiente", "aprobada"):
        return previa, None
    detalle = [
        {"area": m.area_nombre, "docente": m.docente_nombre, "promedio": m.promedio,
         "notas": [[n.periodo, n.valor] for n in m.notas]}
        for m in ev.riesgo.perdidas
    ]
    s = models.SolicitudPromocion(
        estudiante_id=estudiante.id, anio_lectivo=ev.anio_lectivo,
        grado_actual=estudiante.grado, grado_destino=grado_destino,
        motivos=",".join(ev.motivos), materias_perdidas=len(ev.riesgo.perdidas),
        detalle=json.dumps(detalle, ensure_ascii=False), justificacion=justificacion.strip(),
        solicitado_por_id=usuario_id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s, None


def decidir(
    db: Session, s: models.SolicitudPromocion, aprobar: bool, nota: str | None, usuario_id: int
) -> str | None:
    """Devuelve un mensaje de error, o None si quedó decidida."""
    if s.estado != "pendiente":
        return f"Esta solicitud ya está {s.estado}."
    nota = (nota or "").strip() or None
    if not aprobar and not nota:
        return "Para rechazar hay que escribir el motivo (queda en el registro y lo ve quien pidió el permiso)."
    s.estado = "aprobada" if aprobar else "rechazada"
    s.decidido_por_id = usuario_id
    s.decidido_en = fechas.ahora_utc()
    s.nota_decision = nota
    db.commit()
    return None


def marcar_usada(db: Session, estudiante_id: int, grado_destino: int) -> None:
    s = solicitud_vigente(db, estudiante_id, grado_destino, fechas.anio_lectivo_actual())
    if s is not None and s.estado == "aprobada" and s.usada_en is None:
        s.usada_en = fechas.ahora_utc()
        db.commit()
