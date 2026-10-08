"""Prueba del importador del diagnóstico frente al sobrante de plantilla del
Excel real 2026 (hojas armadas copiando Preescolar). Solo LEE el Excel: no
toca ninguna base de datos.

    python probar_sobrantes_plantilla.py ["ruta al Excel"]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import diagnostico_import as di  # noqa: E402

EXCEL = sys.argv[1] if len(sys.argv) > 1 else r"D:\sebas\DIAGNOSTICO IETABA 2026...xlsx"
fallos = 0


def verificar(desc, cond, detalle=""):
    global fallos
    print(f"  {desc} -> {'OK' if cond else 'FALLO ' + str(detalle)}")
    if not cond:
        fallos += 1


if not Path(EXCEL).exists():
    print(f"No está el Excel ({EXCEL}); se omite la prueba.")
    sys.exit(0)

hojas = {h.hoja_excel.strip(): h for h in di.leer_libro(EXCEL)}
pre = hojas.get("DX PREESCOLAR")
otros = [h for n, h in hojas.items() if n != "DX PREESCOLAR"]
todo = lambda h: " ".join(h.campos.values())  # noqa: E731

print("\n[1] Preescolar (hoja original) conserva su texto")
verificar("Preescolar existe", pre is not None)
verificar("Preescolar sigue teniendo 'Se siente muy bien…'", pre and "desempeño de sus tejidos" in (pre.campos.get("estrategias_aprendizaje") or ""))
verificar("Preescolar sigue nombrando a Claudia Yisela en intermitencia", pre and "Claudia Yisela" in (pre.campos.get("no_asisten_texto") or ""))

print("\n[2] Las hojas copiadas ya no arrastran el sobrante")
contaminadas = [h.hoja_excel for h in otros if any(t in todo(h) for t in ("desempeño de sus tejidos", "Claudia Yisela", "Jhon James Guanga", "Erick Andrey Nastacuas"))]
verificar("ninguna otra hoja trae el texto o los nombres de Preescolar", not contaminadas, contaminadas)
verificar("ninguna hoja tiene 'DX' suelto como respuesta", not [h.hoja_excel for h in hojas.values() if any(v.strip() == "DX" for v in h.campos.values())])

print("\n[3] Las respuestas reales se conservan")
h62 = hojas.get("DX 6.2")
verificar("6.2 conserva sus temáticas reales", h62 and "proyecto de vida" in (h62.campos.get("tematicas_trabajar") or "").lower())
verificar("6.2 conserva sus resguardos reales (sin el copiado)", h62 and "Saunde Guaiguay" in (h62.campos.get("resguardos_atendidos") or "") and "Guelmambi" not in (h62.campos.get("resguardos_atendidos") or ""))
h81 = hojas.get("DX 8-1")
verificar("8-1 (no copiada) conserva su propio 'Guelmambi Caraño'", h81 and "Guelmambi" in (h81.campos.get("resguardos_atendidos") or ""))
verificar("las firmas del orientador se conservan en todas las hojas", all(h.campos.get("orientador_escolar_nombre") for h in hojas.values() if "RIASCOS" in h.texto_crudo.upper()))
verificar("respuestas cortas legítimas (ej. '0') no se tocan", any((h.campos.get("desplazados_texto") or "").strip() == "0" for h in hojas.values()))

print("\nTODO OK" if not fallos else f"\n{fallos} FALLOS")
sys.exit(1 if fallos else 0)
