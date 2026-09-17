"""Auditoría de continuidad académica: compara Período 1 contra Período 2
para saber qué estudiantes tienen evidencia real de actividad académica
(al menos una nota) en cada uno, sin inventar nada — si una combinación
sede+grado+curso+período nunca se auditó contra SAPRED (no existe
RevisionBoletin), esos estudiantes quedan como "sin auditar", NUNCA como
"sin evidencia" ni "posible retiro": ausencia de auditoría no es lo mismo
que ausencia de notas.

Clasificación por estudiante (ver GRADOS_NOMBRES para nombres de grado):
  activo                     — tiene nota en P1 y en P2
  sin_evidencia_p1           — P1 fue auditado y no tiene ninguna nota
  posible_retiro             — tuvo nota en P1, P2 fue auditado y no tiene ninguna
  posible_retiro_prioritario — igual que arriba, y además tuvo alguna nota muy
                                baja (<=2.0) en P1
  p2_sin_auditar             — tiene nota en P1 pero P2 todavía no se ha
                                auditado (no se puede saber si sigue activo)
  sin_auditar                — ni P1 ni P2 se han auditado para este grupo

Nunca se marca a nadie como "retirado" de forma oficial — eso lo decide una
persona, esto es una observación de auditoría (regla explícita del pedido).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas

UMBRAL_BAJO_RENDIMIENTO = 2.0


def _valores_numericos(valores: list[str]) -> list[float]:
    numeros = []
    for v in valores:
        try:
            numeros.append(float(v))
        except (TypeError, ValueError):
            continue
    return numeros


def _revisiones_por_grupo(db: Session, sede_id: int, anio_lectivo: int, periodo: int) -> dict[tuple[int, int | None], models.RevisionBoletin]:
    filas = db.scalars(
        select(models.RevisionBoletin).where(
            models.RevisionBoletin.sede_id == sede_id,
            models.RevisionBoletin.anio_lectivo == anio_lectivo,
            models.RevisionBoletin.periodo == periodo,
        )
    ).all()
    return {(r.grado, r.curso): r for r in filas}


def auditoria_continuidad(db: Session, sede_id: int, anio_lectivo: int) -> schemas.ResumenContinuidad:
    sede = db.get(models.Sede, sede_id)
    if sede is None:
        raise ValueError(f"Sede {sede_id} no encontrada")

    revisiones_p1 = _revisiones_por_grupo(db, sede_id, anio_lectivo, 1)
    revisiones_p2 = _revisiones_por_grupo(db, sede_id, anio_lectivo, 2)

    # Orden explícito por id: es el orden en que siempre salieron las
    # novedades (antes dependía de que SQLite recorriera la tabla completa;
    # con el índice por grupo cambiaría).
    estudiantes = db.scalars(
        select(models.Estudiante)
        .where(
            models.Estudiante.sede_id == sede_id,
            models.Estudiante.estado == "ACTIVO",
        )
        .order_by(models.Estudiante.id)
    ).all()

    # Notas por (revision_id, estudiante_id) -> lista de valores (puede tener
    # varias áreas). Se cargan todas las de esta sede/año de una sola vez.
    ids_revision = {r.id for r in list(revisiones_p1.values()) + list(revisiones_p2.values())}
    notas_por_revision_estudiante: dict[tuple[int, int], list[str]] = {}
    if ids_revision:
        filas_notas = db.execute(
            select(models.NotaSapred.revision_id, models.NotaSapred.estudiante_id, models.NotaSapred.valor).where(
                models.NotaSapred.revision_id.in_(ids_revision)
            )
        ).all()
        for revision_id, estudiante_id, valor in filas_notas:
            notas_por_revision_estudiante.setdefault((revision_id, estudiante_id), []).append(valor)

    # Cursos donde se auditó P2 pero NADIE tiene ninguna nota — casi siempre
    # significa que el/la docente no ha cargado notas todavía, no que el
    # curso entero se retiró. Se separa de los casos individuales para no
    # confundir una cosa con la otra en el informe.
    matriculados_por_grupo: dict[tuple[int, int | None], int] = {}
    for e in estudiantes:
        matriculados_por_grupo[(e.grado, e.curso)] = matriculados_por_grupo.get((e.grado, e.curso), 0) + 1

    cursos_vacios_p2: set[tuple[int, int | None]] = set()
    for (grado, curso), revision in revisiones_p2.items():
        total_notas_revision = sum(
            1 for (rev_id, _est_id) in notas_por_revision_estudiante if rev_id == revision.id
        )
        if total_notas_revision == 0 and matriculados_por_grupo.get((grado, curso), 0) > 0:
            cursos_vacios_p2.add((grado, curso))

    por_grado: dict[int, schemas.ContinuidadPorGrado] = {}
    for grado in range(0, 12):
        cursos_vacios_de_este_grado = sorted(
            [c for (g, c) in cursos_vacios_p2 if g == grado], key=lambda c: (c is None, c)
        )
        por_grado[grado] = schemas.ContinuidadPorGrado(
            grado=grado,
            nombre_grado=models.GRADOS_NOMBRES.get(grado, str(grado)),
            matriculados=0, con_notas_p1=0, sin_notas_p1=0, activos_p2=0,
            posibles_retiros=0, observaciones=0,
            p1_auditado=False, p2_auditado=False,
            cursos_sin_notas_p2=[
                f"{models.DIVISIONES_NOMBRES.get(c, c) if c else 'General'} ({matriculados_por_grupo.get((grado, c), 0)} estudiantes)"
                for c in cursos_vacios_de_este_grado
            ],
        )

    total_con_notas_p1 = 0
    total_sin_evidencia_p1 = 0
    total_activos_p2 = 0
    total_posibles_retiros = 0

    for e in estudiantes:
        if e.grado not in por_grado:
            continue  # grado fuera de 0-11, no debería pasar con datos reales
        resumen_grado = por_grado[e.grado]
        resumen_grado.matriculados += 1

        clave_grupo = (e.grado, e.curso)
        revision_p1 = revisiones_p1.get(clave_grupo)
        revision_p2 = revisiones_p2.get(clave_grupo)
        if revision_p1 is not None:
            resumen_grado.p1_auditado = True
        if revision_p2 is not None:
            resumen_grado.p2_auditado = True

        valores_p1 = notas_por_revision_estudiante.get((revision_p1.id, e.id), []) if revision_p1 else []
        valores_p2 = notas_por_revision_estudiante.get((revision_p2.id, e.id), []) if revision_p2 else []
        tiene_notas_p1 = len(valores_p1) > 0
        tiene_notas_p2 = len(valores_p2) > 0
        bajo_rendimiento_p1 = any(v <= UMBRAL_BAJO_RENDIMIENTO for v in _valores_numericos(valores_p1))

        # Los conteos "con_notas_p1" y "activos_p2" son independientes entre
        # sí (tal como se definieron: basta una nota en ESE período) — no se
        # exige que el otro período también esté auditado para contar aquí.
        if revision_p1 is not None:
            if tiene_notas_p1:
                resumen_grado.con_notas_p1 += 1
                total_con_notas_p1 += 1
            else:
                resumen_grado.sin_notas_p1 += 1
                total_sin_evidencia_p1 += 1
        if revision_p2 is not None and tiene_notas_p2:
            resumen_grado.activos_p2 += 1
            total_activos_p2 += 1

        # El "estado" (para las novedades) sí necesita mirar ambos períodos
        # juntos, en el orden de prioridad del pedido original.
        if revision_p1 is None and revision_p2 is None:
            estado = "sin_auditar"
        elif revision_p1 is not None and not tiene_notas_p1:
            estado = "sin_evidencia_p1"
        elif tiene_notas_p1 and revision_p2 is not None and not tiene_notas_p2:
            estado = "posible_retiro_prioritario" if bajo_rendimiento_p1 else "posible_retiro"
            resumen_grado.posibles_retiros += 1
            total_posibles_retiros += 1
        elif tiene_notas_p1 and tiene_notas_p2:
            estado = "activo"
        elif tiene_notas_p1 and revision_p2 is None:
            estado = "p2_sin_auditar"
        elif revision_p1 is None and tiene_notas_p2:
            # Caso real detectado: se auditó P2 antes que P1 (pasó en esta
            # institución) — hay evidencia de P2 pero no se sabe nada de P1.
            estado = "p1_sin_auditar"
        else:
            estado = "sin_auditar"

        if estado != "activo":
            resumen_grado.observaciones += 1
            evidencia_partes = []
            if revision_p1 is None:
                evidencia_partes.append("Período 1 no auditado todavía")
            else:
                evidencia_partes.append(f"{len(valores_p1)} nota(s) en P1" if tiene_notas_p1 else "sin notas en P1")
                if bajo_rendimiento_p1:
                    bajas = [v for v in _valores_numericos(valores_p1) if v <= UMBRAL_BAJO_RENDIMIENTO]
                    evidencia_partes.append(f"nota(s) baja(s) en P1: {', '.join(str(v) for v in bajas)}")
            if revision_p2 is None:
                evidencia_partes.append("Período 2 no auditado todavía")
            else:
                evidencia_partes.append(f"{len(valores_p2)} nota(s) en P2" if tiene_notas_p2 else "sin ninguna nota en P2")
                if (e.grado, e.curso) in cursos_vacios_p2:
                    evidencia_partes.append(
                        "⚠ TODO el curso está en cero en P2 (probable atraso de cargue del docente, no necesariamente retiro individual)"
                    )

            resumen_grado.novedades.append(
                schemas.NovedadContinuidad(
                    estudiante_id=e.id,
                    documento=e.documento,
                    nombre_completo=e.nombre_completo,
                    curso=e.curso,
                    estado=estado,
                    evidencia=" · ".join(evidencia_partes),
                )
            )

    porcentaje = round((total_activos_p2 / total_con_notas_p1) * 100, 1) if total_con_notas_p1 else 0.0

    return schemas.ResumenContinuidad(
        sede_id=sede_id,
        sede_nombre=sede.nombre,
        anio_lectivo=anio_lectivo,
        total_matriculados=sum(g.matriculados for g in por_grado.values()),
        total_con_notas_p1=total_con_notas_p1,
        total_sin_evidencia_p1=total_sin_evidencia_p1,
        total_activos_p2=total_activos_p2,
        total_posibles_retiros=total_posibles_retiros,
        porcentaje_continuidad=porcentaje,
        por_grado=sorted(por_grado.values(), key=lambda g: g.grado),
    )


ETIQUETAS_ESTADO = {
    "activo": "Activo",
    "sin_evidencia_p1": "Sin evidencia académica P1",
    "posible_retiro": "Posible retiro / requiere validación",
    "posible_retiro_prioritario": "Posible retiro (prioritario — bajo rendimiento P1)",
    "p2_sin_auditar": "Activo en P1 — P2 sin auditar todavía",
    "p1_sin_auditar": "Activo en P2 — P1 sin auditar todavía",
    "sin_auditar": "Sin auditar (ni P1 ni P2)",
}


def exportar_continuidad_excel(resumen: schemas.ResumenContinuidad) -> bytes:
    import io

    import openpyxl
    from openpyxl.styles import Font

    libro = openpyxl.Workbook()
    hoja_resumen = libro.active
    hoja_resumen.title = "Resumen General"

    hoja_resumen.append([f"Auditoría de continuidad académica — {resumen.sede_nombre}"])
    hoja_resumen.append([f"Año lectivo: {resumen.anio_lectivo}"])
    hoja_resumen.append([])
    hoja_resumen.append(["Total matriculados", resumen.total_matriculados])
    hoja_resumen.append(["Con actividad académica en P1", resumen.total_con_notas_p1])
    hoja_resumen.append(["Sin evidencia académica en P1", resumen.total_sin_evidencia_p1])
    hoja_resumen.append(["Activos en P2", resumen.total_activos_p2])
    hoja_resumen.append(["Posibles retiros detectados", resumen.total_posibles_retiros])
    hoja_resumen.append(["% continuidad P1 -> P2", f"{resumen.porcentaje_continuidad}%"])
    hoja_resumen.append([])
    hoja_resumen.append(["Grado", "Matriculados", "Con notas P1", "Sin notas P1", "Activos P2", "Posibles retiros", "Observaciones", "P1 auditado", "P2 auditado"])
    for celda in hoja_resumen[hoja_resumen.max_row]:
        celda.font = Font(bold=True)
    for g in resumen.por_grado:
        hoja_resumen.append([
            g.nombre_grado, g.matriculados, g.con_notas_p1, g.sin_notas_p1, g.activos_p2,
            g.posibles_retiros, g.observaciones, "Sí" if g.p1_auditado else "No", "Sí" if g.p2_auditado else "No",
        ])
    for columna, ancho in zip(hoja_resumen.columns, [16, 14, 12, 12, 10, 16, 14, 12, 12]):
        hoja_resumen.column_dimensions[columna[0].column_letter].width = ancho

    cursos_vacios = [(g.nombre_grado, c) for g in resumen.por_grado for c in g.cursos_sin_notas_p2]
    if cursos_vacios:
        hoja_vacios = libro.create_sheet("Cursos sin cargar P2")
        hoja_vacios.append(["⚠ Cursos completos sin NINGUNA nota en Período 2 — casi siempre significa que el"])
        hoja_vacios.append(["docente no ha cargado notas todavía, NO que todo el curso se haya retirado."])
        hoja_vacios.append([])
        hoja_vacios.append(["Grado", "Curso"])
        for celda in hoja_vacios[4]:
            celda.font = Font(bold=True)
        for nombre_grado, curso in cursos_vacios:
            hoja_vacios.append([nombre_grado, curso])
        for columna, ancho in zip(hoja_vacios.columns, [16, 30]):
            hoja_vacios.column_dimensions[columna[0].column_letter].width = ancho

    hoja_novedades = libro.create_sheet("Novedades")
    hoja_novedades.append(["Grado", "Documento", "Estudiante", "Curso", "Estado", "Evidencia"])
    for celda in hoja_novedades[1]:
        celda.font = Font(bold=True)
    for g in resumen.por_grado:
        for n in g.novedades:
            hoja_novedades.append([
                g.nombre_grado, n.documento, n.nombre_completo, n.curso or "",
                ETIQUETAS_ESTADO.get(n.estado, n.estado), n.evidencia,
            ])
    for columna, ancho in zip(hoja_novedades.columns, [14, 14, 30, 8, 34, 60]):
        hoja_novedades.column_dimensions[columna[0].column_letter].width = ancho

    for g in resumen.por_grado:
        nombre_hoja = g.nombre_grado[:31]  # límite de Excel para nombres de hoja
        hoja = libro.create_sheet(nombre_hoja)
        hoja.append([f"{g.nombre_grado} — Matriculados: {g.matriculados}"])
        hoja.append([
            f"P1 {'auditado' if g.p1_auditado else 'NO auditado'} · P2 {'auditado' if g.p2_auditado else 'NO auditado'}"
        ])
        if g.cursos_sin_notas_p2:
            hoja.append([f"⚠ Curso(s) sin ninguna nota en P2 (probable atraso de cargue): {', '.join(g.cursos_sin_notas_p2)}"])
        hoja.append([])
        hoja.append(["Documento", "Estudiante", "Curso", "Estado", "Evidencia"])
        for celda in hoja[hoja.max_row]:
            celda.font = Font(bold=True)
        if g.novedades:
            for n in g.novedades:
                hoja.append([n.documento, n.nombre_completo, n.curso or "", ETIQUETAS_ESTADO.get(n.estado, n.estado), n.evidencia])
        else:
            hoja.append(["(sin novedades — todos activos, o grado sin auditar)"])
        for columna, ancho in zip(hoja.columns, [14, 30, 8, 34, 60]):
            hoja.column_dimensions[columna[0].column_letter].width = ancho

    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()
