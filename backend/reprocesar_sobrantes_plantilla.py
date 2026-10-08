"""Corrige los diagnósticos YA importados que absorbieron sobrante de
plantilla del Excel (ver diagnostico_import.detectar_sobrantes_plantilla):
en 2026, 26 hojas se armaron copiando la de Preescolar y arrastraron textos
suyos (nombres de estudiantes de Preescolar en "intermitencia", una frase en
"estrategias de aprendizaje" y dos resguardos).

Relee el Excel con el importador corregido y, en la VERSIÓN VIGENTE de cada
grado (sin crear versiones nuevas: el contenido real no cambió, cambió cómo
se lee):
  · actualiza los campos que cambiaron, texto_crudo y contenido_hash;
  · borra las menciones que ya no existen (las del sobrante), conservando
    intactas las que siguen (con su vinculación y su caso, si lo tienen);
  · agrega las menciones nuevas, si las hubiera.
Si una mención a borrar tiene vinculación manual o un caso abierto a partir
de ella, se salta ese grado (trabajo humano) salvo --forzar; el caso nunca se
borra, solo pierde el enlace a la mención de origen.

Por defecto solo muestra qué cambiaría. Con --aplicar guarda (antes deja un
respaldo colegio.db.bak_antes_sobrantes_plantilla_*).

    python reprocesar_sobrantes_plantilla.py                 (vista previa)
    python reprocesar_sobrantes_plantilla.py --aplicar
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select  # noqa: E402

from app import diagnostico_import, migraciones, models  # noqa: E402
from app.database import SessionLocal  # noqa: E402

EXCEL_POR_DEFECTO = r"D:\sebas\DIAGNOSTICO IETABA 2026...xlsx"
CAMPOS = [
    "no_asisten_texto", "desplazados_texto", "embarazadas_texto", "victimas_conflicto_texto",
    "dificultades_academicas", "dificultades_comportamiento", "acompanamiento_padres", "problemas_salud",
    "tematicas_trabajar", "estrategias_conflicto", "estrategias_aprendizaje", "resguardos_atendidos",
    "recomendaciones_docentes", "llamados_atencion", "orientacion_brindada", "transporte_escolar",
    "observaciones_generales", "director_grado_nombre", "orientador_escolar_nombre", "seguimiento_nota",
]


def _clave(m) -> tuple:
    return (m.categoria, (m.nombre_detectado or "").strip(), (m.texto or "").strip())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--excel", default=EXCEL_POR_DEFECTO)
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--forzar", action="store_true")
    args = ap.parse_args()

    hojas = {h.hoja_excel: h for h in diagnostico_import.leer_libro(args.excel)}
    if args.aplicar:
        print(f"Respaldo: {migraciones.respaldar('antes_sobrantes_plantilla')}")
    db = SessionLocal()
    vigentes: dict[tuple, models.DiagnosticoGrado] = {}
    for d in db.scalars(select(models.DiagnosticoGrado).order_by(models.DiagnosticoGrado.importado_en.desc())):
        vigentes.setdefault((d.sede_id, d.grado, d.curso), d)

    total_campos = total_borradas = total_nuevas = saltados = 0
    cambios_por_grado = []
    for d in sorted(vigentes.values(), key=lambda x: (x.grado, x.curso or 0)):
        hoja = hojas.get(d.hoja_excel)
        if hoja is None:
            continue
        nuevos = diagnostico_import.hoja_a_diagnostico(db, hoja, d.sede_id, d.archivo_origen or args.excel, None)
        campos_cambiados = [c for c in CAMPOS if (getattr(d, c) or None) != (getattr(nuevos, c) or None)]
        claves_nuevas = {_clave(m): m for m in nuevos.menciones}
        claves_viejas = {_clave(m): m for m in d.menciones}
        a_borrar = [m for k, m in claves_viejas.items() if k not in claves_nuevas]
        a_agregar = [m for k, m in claves_nuevas.items() if k not in claves_viejas]
        # hoja_a_diagnostico creó un objeto nuevo en la sesión: no se guarda.
        for m in nuevos.menciones:
            if m in db:
                db.expunge(m)
        if nuevos in db:
            db.expunge(nuevos)
        if not campos_cambiados and not a_borrar and not a_agregar:
            continue

        con_trabajo = [
            m for m in a_borrar
            if (m.estudiante_id and not m.vinculo_automatico)
            or db.scalar(select(models.Caso.id).where(models.Caso.mencion_origen_id == m.id))
        ]
        estado = ""
        if con_trabajo and not args.forzar:
            estado = f"  SALTADO: {len(con_trabajo)} mención(es) con trabajo manual (usa --forzar)"
            saltados += 1
        cambios_por_grado.append((d.hoja_excel, campos_cambiados, a_borrar, a_agregar, estado))
        if estado:
            continue

        total_campos += len(campos_cambiados)
        total_borradas += len(a_borrar)
        total_nuevas += len(a_agregar)
        if args.aplicar:
            for c in campos_cambiados:
                setattr(d, c, getattr(nuevos, c))
            d.texto_crudo = hoja.texto_crudo
            d.contenido_hash = diagnostico_import.contenido_hash(hoja)
            for m in a_borrar:
                for caso in db.scalars(select(models.Caso).where(models.Caso.mencion_origen_id == m.id)):
                    caso.mencion_origen_id = None  # el caso se conserva; solo pierde el origen falso
                db.delete(m)
            for m in a_agregar:
                m.diagnostico = d  # colgar del diagnóstico vigente, no del temporal
                db.add(m)

    for hoja_excel, campos, borrar, agregar, estado in cambios_por_grado:
        print(f"\n{hoja_excel}: campos {campos or '—'} · menciones a quitar {len(borrar)} · nuevas {len(agregar)}{estado}")
        for m in borrar[:6]:
            print(f"    - {m.categoria}: {(m.nombre_detectado or m.texto or '')[:70]}")
        if len(borrar) > 6:
            print(f"    ... y {len(borrar) - 6} más")

    print(
        f"\nResumen: {len(cambios_por_grado)} grado(s) con cambios, {total_campos} campo(s), "
        f"{total_borradas} mención(es) a quitar, {total_nuevas} nueva(s), {saltados} saltado(s)."
    )
    if args.aplicar:
        db.commit()
        print("APLICADO.")
    else:
        db.rollback()
        print("Vista previa: no se guardó nada. Usa --aplicar para guardar.")


if __name__ == "__main__":
    main()
