"""Prueba manual del módulo Horarios contra la base real (colegio.db).

Uso:
    ./venv/Scripts/python.exe probar_horario.py

Recorre el checklist de la especificación: import, consulta, disponibilidad,
ausencias, reemplazos (candidatos, orden, conflictos, asignar, cambiar,
cancelar) e integridad. Crea una ausencia y unos reemplazos de prueba en una
fecha futura y los borra al final (no deja basura en la base).
"""

import datetime as dt
import sys

from sqlalchemy import select

from app import models, schemas
from app.database import SessionLocal
from app import horario

ANIO = 2026
OK = "  \033[92mOK\033[0m"


def _fecha_con_weekday(wd: int) -> dt.date:
    """Una fecha de 2026 (futura respecto a hoy si se puede) cuyo weekday sea wd."""
    d = max(dt.date.today() + dt.timedelta(days=1), dt.date(2026, 9, 1))
    while d.weekday() != wd:
        d += dt.timedelta(days=1)
    return d


def main() -> None:
    db = SessionLocal()
    creado_ausencia = None
    creados_reemplazo: list[int] = []
    fallos = 0

    try:
        # ---- 1. IMPORT ---------------------------------------------------
        print("\n[1] Importación")
        n = db.query(models.BloqueHorario).filter_by(anio_lectivo=ANIO).count()
        assert n > 500, f"pocos bloques importados: {n}"
        print(f"  bloques {ANIO}: {n}{OK}")

        cusis = db.scalar(select(models.Docente).where(models.Docente.nombre_completo.like("%CUSIS%")))
        b = db.scalar(
            select(models.BloqueHorario).where(
                models.BloqueHorario.anio_lectivo == ANIO,
                models.BloqueHorario.docente_id == cusis.id,
                models.BloqueHorario.dia == 1,
                models.BloqueHorario.hora == 1,
            )
        )
        assert b is not None and b.area_label == "MATEMATICAS" and b.grado == 10 and b.curso == 1, b
        print(f"  muestra CUSIS lunes h1 = {b.area_label} {b.grado}-{b.curso}{OK}")

        # ---- 2. CONSULTA ----------------------------------------------------
        print("\n[2] Consulta")
        sem = horario.horario_docente(db, cusis.id, ANIO)
        assert len(sem.filas) == 6 and all(len(f.celdas) == 5 for f in sem.filas)
        ocupadas = sum(1 for f in sem.filas for c in f.celdas if c)
        libres = sum(1 for f in sem.filas for c in f.celdas if c is None)
        assert ocupadas == sem.total_bloques and ocupadas + libres == 30
        print(f"  horario_docente CUSIS: {ocupadas} clases, {libres} LIBRE{OK}")

        g = horario.horario_grupo(db, 8, 1, ANIO)
        assert len(g.bloques) > 0
        print(f"  horario_grupo 8-1: {len(g.bloques)} clases, {g.total_estudiantes} estudiantes{OK}")

        dia_bloques = horario.listar_bloques(db, ANIO, dia=2)
        assert len(dia_bloques) > 0
        print(f"  horario por día (martes): {len(dia_bloques)} clases{OK}")

        # ---- 3. DISPONIBILIDAD -------------------------------------------
        print("\n[3] Disponibilidad")
        casos = [
            (dt.datetime(2026, 9, 8, 8, 0), "en_franja", 1),   # martes 8:00
            (dt.datetime(2026, 9, 8, 10, 40), "descanso", None),
            (dt.datetime(2026, 9, 8, 6, 0), "fuera_jornada", None),
            (dt.datetime(2026, 9, 8, 19, 0), "fuera_jornada", None),
            (dt.datetime(2026, 9, 12, 9, 0), "fin_de_semana", None),  # sábado
        ]
        for ahora, esperado, hora in casos:
            fr = horario.franja_actual(ahora)
            assert fr["estado"] == esperado, (ahora, fr)
            assert fr["hora"] == hora, (ahora, fr)
        print(f"  franja_actual: {len(casos)} casos (jornada/descanso/fuera/fin de semana){OK}")

        # elegir (dia, hora) con clases; comprobar que ningún "libre" tiene clase ahí
        dia, hora = 2, 2
        fecha_mar = _fecha_con_weekday(1)
        libres_list = horario.docentes_libres(db, dia, hora, fecha_mar, ANIO)
        ids_con_clase = {
            r.docente_id
            for r in db.scalars(
                select(models.BloqueHorario).where(
                    models.BloqueHorario.anio_lectivo == ANIO,
                    models.BloqueHorario.dia == dia,
                    models.BloqueHorario.hora == hora,
                )
            )
        }
        assert not ({x.docente_id for x in libres_list} & ids_con_clase), "un 'libre' tiene clase esa franja"
        print(f"  docentes_libres martes h2: {len(libres_list)} (ninguno con clase){OK}")

        # estado_docente: un docente con clase a esa hora -> en_clase
        con_clase = next(iter(ids_con_clase))
        est = horario.estado_docente(
            db, con_clase, fecha_mar, ahora=dt.datetime.combine(fecha_mar, dt.time(8, 45))
        )
        assert est["estado"] == "en_clase", est
        print(f"  estado_docente (con clase, martes 8:45) = {est['estado']}{OK}")

        # ---- 4. AUSENCIAS ---------------------------------------------------
        print("\n[4] Ausencias")
        # docente con más clases un martes
        filas = db.execute(
            select(models.BloqueHorario.docente_id)
            .where(models.BloqueHorario.anio_lectivo == ANIO, models.BloqueHorario.dia == 1)
        ).all()
        from collections import Counter

        docente_test = Counter(x[0] for x in filas).most_common(1)[0][0]
        fecha_lun = _fecha_con_weekday(0)  # lunes
        bloques_lun = db.query(models.BloqueHorario).filter_by(
            anio_lectivo=ANIO, docente_id=docente_test, dia=1
        ).count()

        ausencia = horario.registrar_ausencia(
            db,
            schemas.AusenciaCrear(
                docente_id=docente_test, fecha=fecha_lun, motivo="Prueba automática", registrado_por="probar_horario"
            ),
        )
        creado_ausencia = ausencia.id
        assert len(ausencia.clases_afectadas) == bloques_lun, (len(ausencia.clases_afectadas), bloques_lun)
        sin_conflicto = [c for c in ausencia.clases_afectadas if not c.conflicto]
        con_conflicto = [c for c in ausencia.clases_afectadas if c.conflicto]
        print(
            f"  ausencia de docente #{docente_test} el {fecha_lun}: "
            f"{len(ausencia.clases_afectadas)} clases afectadas "
            f"({len(con_conflicto)} en conflicto){OK}"
        )
        # se crea un Reemplazo pendiente por cada clase afectada SIN conflicto
        pend = db.query(models.Reemplazo).filter_by(ausencia_id=creado_ausencia).all()
        creados_reemplazo = [r.id for r in pend]
        assert len(pend) == len(sin_conflicto) and all(r.estado == "pendiente" for r in pend), (
            len(pend), len(sin_conflicto))
        assert all(c.conflicto_opciones for c in con_conflicto)
        print(f"  {len(pend)} reemplazos 'pendiente' creados (las clases en conflicto se saltan){OK}")

        # ---- 5. REEMPLAZOS ------------------------------------------------
        print("\n[5] Reemplazos")
        clase = sin_conflicto[0]
        resp = horario.candidatos_reemplazo(db, clase.bloque_horario_id, fecha_lun)
        assert len(resp.candidatos) > 0, "sin candidatos"
        pcts = [c.porcentaje for c in resp.candidatos]
        assert pcts == sorted(pcts, reverse=True), f"candidatos no ordenados: {pcts}"
        print(f"  candidatos para {clase.area_label} {clase.grupo} h{clase.hora}: "
              f"{len(resp.candidatos)} (top {pcts[0]}%, orden desc){OK}")

        # ninguno tiene clase esa franja, ninguno es el ausente
        cand_ids = {c.docente_id for c in resp.candidatos}
        ocupados_slot = {
            r.docente_id
            for r in db.scalars(
                select(models.BloqueHorario).where(
                    models.BloqueHorario.anio_lectivo == ANIO,
                    models.BloqueHorario.dia == clase.dia,
                    models.BloqueHorario.hora == clase.hora,
                )
            )
        }
        assert not (cand_ids & ocupados_slot) and docente_test not in cand_ids
        print(f"  ningún candidato con conflicto de horario ni el ausente{OK}")

        # conflicto: intentar asignar a alguien que SÍ tiene clase esa franja
        if ocupados_slot:
            ocupado = next(iter(ocupados_slot))
            try:
                horario.asignar_reemplazo(
                    db,
                    schemas.ReemplazoAsignar(
                        bloque_horario_id=clase.bloque_horario_id,
                        fecha=fecha_lun,
                        docente_reemplazo_id=ocupado,
                    ),
                )
                raise AssertionError("debió rechazar un docente ocupado")
            except ValueError as e:
                print(f"  rechazo de docente ocupado: '{str(e)[:60]}...'{OK}")

        # asignar el mejor candidato
        elegido = resp.candidatos[0]
        r_asig = horario.asignar_reemplazo(
            db,
            schemas.ReemplazoAsignar(
                bloque_horario_id=clase.bloque_horario_id,
                fecha=fecha_lun,
                docente_reemplazo_id=elegido.docente_id,
                asignado_por="probar_horario",
            ),
        )
        assert r_asig.estado == "asignado" and r_asig.docente_reemplazo_id == elegido.docente_id
        assert r_asig.compatibilidad == elegido.porcentaje and len(r_asig.razones) > 0
        print(f"  asignado a {r_asig.docente_reemplazo} ({r_asig.compatibilidad}%){OK}")

        # el reemplazante ya no aparece como libre en esa franja
        libres_despues = {
            x.docente_id for x in horario.docentes_libres(db, clase.dia, clase.hora, fecha_lun, ANIO)
        }
        assert elegido.docente_id not in libres_despues, "el reemplazante sigue apareciendo como libre"
        est_cubre = horario.estado_docente(
            db, elegido.docente_id, fecha_lun,
            ahora=dt.datetime.combine(fecha_lun, dt.time(8, 45)),
            _franja={"estado": "en_franja", "dia": clase.dia, "hora": clase.hora,
                     "dia_nombre": "", "jornada": "mañana", "franja": None},
        )
        assert est_cubre["estado"] == "cubriendo", est_cubre
        print(f"  disponibilidad actualizada: reemplazante = '{est_cubre['estado']}'{OK}")

        # cambiar a otro candidato
        if len(resp.candidatos) > 1:
            otro = resp.candidatos[1]
            r_cambio = horario.actualizar_reemplazo(
                db, r_asig.id, schemas.ReemplazoActualizar(docente_reemplazo_id=otro.docente_id)
            )
            assert r_cambio.docente_reemplazo_id == otro.docente_id and r_cambio.estado == "asignado"
            print(f"  cambiado a {r_cambio.docente_reemplazo}{OK}")

        # cancelar
        r_cancel = horario.actualizar_reemplazo(
            db, r_asig.id, schemas.ReemplazoActualizar(estado="cancelado")
        )
        assert r_cancel.estado == "cancelado" and r_cancel.docente_reemplazo_id is None
        print(f"  cancelado{OK}")

        # ---- 6. INTEGRIDAD ------------------------------------------------
        print("\n[6] Integridad")
        # el bloque original sigue intacto
        b_orig = db.get(models.BloqueHorario, clase.bloque_horario_id)
        assert b_orig is not None and b_orig.docente_id == docente_test
        print(f"  el horario original no se tocó (bloque #{b_orig.id} sigue con el docente ausente){OK}")
        n_final = db.query(models.BloqueHorario).filter_by(anio_lectivo=ANIO).count()
        assert n_final == n, f"cambió el número de bloques: {n} -> {n_final}"
        print(f"  bloques totales sin cambios: {n_final}{OK}")

        print("\n\033[92mTODO OK\033[0m\n")

    except AssertionError as e:
        fallos += 1
        print(f"\n\033[91mFALLO:\033[0m {e}")
    finally:
        # limpieza
        for rid in creados_reemplazo:
            r = db.get(models.Reemplazo, rid)
            if r:
                db.delete(r)
        if creado_ausencia:
            a = db.get(models.AusenciaDocente, creado_ausencia)
            # borra también reemplazos que quedaran ligados y no estén en la lista
            for r in db.scalars(select(models.Reemplazo).where(models.Reemplazo.ausencia_id == creado_ausencia)):
                db.delete(r)
            db.flush()  # reemplazos antes que la ausencia (claves foráneas activas)
            if a:
                db.delete(a)
        db.commit()
        db.close()
        print("(datos de prueba eliminados)")

    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
