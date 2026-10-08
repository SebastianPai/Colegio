"""Prueba de la regla de promoción y los permisos de coordinación (materias
perdidas, saltos de grado, solicitudes aprobar/rechazar/anular, bloqueo de la ficha).
Trabaja sobre una COPIA de colegio.db en un servidor aparte: no toca la base real."""
import http.cookiejar
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="ietaba_alertas_"))
COPIA = TMP / "colegio.db"
PUERTO = 8806
BASE = f"http://127.0.0.1:{PUERTO}"
CLAVE = "PruebaAlertas2026"

origen = sqlite3.connect(f"file:{BACKEND / 'colegio.db'}?mode=ro", uri=True)
destino = sqlite3.connect(COPIA)
with destino:
    origen.backup(destino)
origen.close()
destino.close()

os.environ["IETABA_DB_PATH"] = str(COPIA)
sys.path.insert(0, str(BACKEND))
from sqlalchemy import select  # noqa: E402

from app import auth, fechas, rbac_admin, reporte_notas, models  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app import migraciones  # noqa: E402

migraciones.ejecutar()

fallos = 0


def verificar(desc, cond, detalle=""):
    global fallos
    print(f"  {desc} -> {'OK' if cond else 'FALLO ' + str(detalle)}")
    if not cond:
        fallos += 1


db = SessionLocal()
for doc, rol in (("PRUEBA-DOC-ALERTA", "docente"), ("PRUEBA-COORD-ALERTA", "coordinador")):
    u = auth.registrar_usuario(db, documento=doc, nombre=f"Prueba {rol}", clave=CLAVE, debe_cambiar_clave=False)
    rbac_admin.establecer_roles_usuario(db, u, [rol], asignado_por_id=None)

anio = fechas.anio_lectivo_actual()
ids = [i for (i,) in db.execute(select(models.NotaSapred.estudiante_id).distinct())]
con_perdidas = next((i for i in ids if reporte_notas.riesgo_promocion(db, i, anio).perdidas), None)
sin_perdidas = next((i for i in ids if not reporte_notas.riesgo_promocion(db, i, anio).perdidas), None)
grado_perdidas = db.get(models.Estudiante, con_perdidas).grado
grado_bien = db.get(models.Estudiante, sin_perdidas).grado
db.close()

log = open(TMP / "servidor.log", "w", encoding="utf-8")
servidor = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PUERTO), "--log-level", "warning"],
    cwd=str(BACKEND), env={**os.environ, "PYTHONUTF8": "1"}, stdout=log, stderr=subprocess.STDOUT,
)


class Cliente:
    def __init__(self):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def pedir(self, ruta, metodo="GET", cuerpo=None):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        cab = {"Origin": BASE}
        if datos:
            cab["Content-Type"] = "application/json"
        req = urllib.request.Request(BASE + ruta, data=datos, method=metodo, headers=cab)
        try:
            with self.op.open(req, timeout=20) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)


try:
    for _ in range(120):
        try:
            urllib.request.urlopen(f"{BASE}/api/sedes", timeout=2).read()
            break
        except Exception:
            time.sleep(0.25)

    docente, coord = Cliente(), Cliente()
    print("\n[1] Login")
    verificar("docente entra", docente.pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-DOC-ALERTA", "clave": CLAVE})[0] == 200)
    verificar("coordinador entra", coord.pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-COORD-ALERTA", "clave": CLAVE})[0] == 200)

    print("\n[2] Riesgo de promoción")
    est, cuerpo, _ = docente.pedir(f"/api/estudiantes/{con_perdidas}/riesgo-promocion")
    r = json.loads(cuerpo)
    verificar("responde 200 y trae materias perdidas", est == 200 and len(r["perdidas"]) > 0, cuerpo[:200])
    verificar("cada materia perdida tiene promedio menor a 3.0", all(m["promedio"] < 3.0 for m in r["perdidas"]))
    est, cuerpo, _ = docente.pedir(f"/api/estudiantes/{sin_perdidas}/riesgo-promocion")
    verificar("un estudiante sin perdidas no trae ninguna", est == 200 and json.loads(cuerpo)["perdidas"] == [])
    verificar("estudiante inexistente da 404", docente.pedir("/api/estudiantes/99999999/riesgo-promocion")[0] == 404)

    def ficha(cliente, est_id, grado):
        return cliente.pedir("/api/certificados/ficha-matricula", "POST",
                             {"estudiante_id": est_id, "campos": {"grado_2026": str(grado)}})

    def evaluar(cliente, est_id, grado):
        est, cuerpo, _ = cliente.pedir(f"/api/promocion/evaluar?estudiante_id={est_id}&grado_destino={grado}")
        return est, json.loads(cuerpo) if est == 200 else cuerpo

    print("\n[3] Regla de promoción al generar la ficha")
    est, _, cab = ficha(docente, sin_perdidas, grado_bien + 1)
    verificar("sin perdidas y sube UN grado: se genera normal", est == 200 and cab.get("x-promocion") == "normal", (est, cab))
    est, _, _ = ficha(docente, con_perdidas, grado_perdidas)
    verificar("con perdidas pero repite (mismo grado): se genera", est == 200)
    est, cuerpo, cab = ficha(docente, con_perdidas, grado_perdidas + 1)
    verificar("con perdidas y subiendo: NO se genera (409) hasta que coordinación autorice",
              est == 409 and cab.get("x-requiere-autorizacion") == "1", (est, cuerpo[:200]))
    if grado_bien + 2 <= 11:
        est, cuerpo, _ = ficha(docente, sin_perdidas, grado_bien + 2)
        verificar("sin perdidas pero salta un grado (ej. 0 a 2): NO se genera (409)", est == 409, (est, cuerpo[:200]))
        _, ev = evaluar(docente, sin_perdidas, grado_bien + 2)
        verificar("evaluar dice motivo 'salto' y grado esperado +1", ev["motivos"] == ["salto"] and ev["grado_esperado"] == grado_bien + 1, ev)
    if grado_bien >= 1:
        _, ev = evaluar(docente, sin_perdidas, grado_bien - 1)
        verificar("bajar de grado también necesita permiso ('retroceso')", "retroceso" in ev["motivos"] and not ev["puede_generar"], ev)
    _, ev = evaluar(docente, con_perdidas, grado_perdidas + 1)
    verificar("evaluar con perdidas: motivo 'perdidas', no se puede generar", "perdidas" in ev["motivos"] and not ev["puede_generar"], ev)
    verificar("cada materia trae su promedio y el campo de docente; 'materias' incluye todas",
              all("docente_nombre" in m for m in ev["riesgo"]["perdidas"]) and len(ev["riesgo"]["materias"]) >= len(ev["riesgo"]["perdidas"]))

    print("\n[4] Pedir permiso")
    est, _, _ = docente.pedir("/api/promocion/solicitudes", "POST", {"estudiante_id": con_perdidas, "grado_destino": grado_perdidas + 1, "justificacion": "corta"})
    verificar("sin justificación de verdad se rechaza (400)", est == 400)
    est, _, _ = docente.pedir("/api/promocion/solicitudes", "POST", {"estudiante_id": sin_perdidas, "grado_destino": grado_bien + 1, "justificacion": "No necesita permiso, es lo normal"})
    verificar("pedir permiso para el grado normal se rechaza (400: no hace falta)", est == 400)
    cuerpo_sol = {"estudiante_id": con_perdidas, "grado_destino": grado_perdidas + 1,
                  "justificacion": "Recuperó en el plan de mejoramiento según acta de comisión."}
    est, cuerpo, _ = docente.pedir("/api/promocion/solicitudes", "POST", cuerpo_sol)
    sol = json.loads(cuerpo) if est == 200 else {}
    verificar("se crea la solicitud pendiente, con quién la pidió",
              est == 200 and sol.get("estado") == "pendiente" and sol.get("solicitado_por_nombre") == "Prueba docente", cuerpo[:300])
    est, cuerpo, _ = docente.pedir("/api/promocion/solicitudes", "POST", cuerpo_sol)
    verificar("pedirla otra vez no duplica (devuelve la misma)", est == 200 and json.loads(cuerpo)["id"] == sol.get("id"))
    verificar("mientras está pendiente la ficha sigue bloqueada", ficha(docente, con_perdidas, grado_perdidas + 1)[0] == 409)

    print("\n[5] Quién ve y quién decide")
    verificar("el docente NO puede listar solicitudes (403)", docente.pedir("/api/promocion/solicitudes")[0] == 403)
    verificar("el docente NO puede aprobar (403)", docente.pedir(f"/api/promocion/solicitudes/{sol['id']}/decidir", "POST", {"aprobar": True})[0] == 403)
    est, cuerpo, _ = coord.pedir("/api/promocion/solicitudes")
    lista = json.loads(cuerpo) if est == 200 else []
    verificar("coordinación ve la solicitud pendiente", est == 200 and [x["id"] for x in lista] == [sol["id"]], cuerpo[:200])
    verificar("trae el detalle de materias perdidas", lista and lista[0]["materias_perdidas"] > 0 and len(lista[0]["detalle"]) == lista[0]["materias_perdidas"])

    print("\n[6] Rechazar y aprobar")
    verificar("rechazar sin motivo no se deja (400)", coord.pedir(f"/api/promocion/solicitudes/{sol['id']}/decidir", "POST", {"aprobar": False})[0] == 400)
    est, cuerpo, _ = coord.pedir(f"/api/promocion/solicitudes/{sol['id']}/decidir", "POST", {"aprobar": False, "nota": "Debe presentar el acta firmada."})
    r = json.loads(cuerpo) if est == 200 else {}
    verificar("coordinación rechaza: queda quién y por qué",
              r.get("estado") == "rechazada" and r.get("decidido_por_nombre") == "Prueba coordinador" and r.get("nota_decision"), cuerpo[:300])
    verificar("rechazada: la ficha sigue bloqueada", ficha(docente, con_perdidas, grado_perdidas + 1)[0] == 409)
    verificar("no se puede volver a decidir una ya rechazada (400)",
              coord.pedir(f"/api/promocion/solicitudes/{sol['id']}/decidir", "POST", {"aprobar": True})[0] == 400)
    est, cuerpo, _ = docente.pedir("/api/promocion/solicitudes", "POST",
                                   {**cuerpo_sol, "justificacion": "Se adjunta el acta firmada de la comisión de evaluación."})
    sol2 = json.loads(cuerpo) if est == 200 else {}
    verificar("tras un rechazo se puede pedir de nuevo (solicitud nueva)", est == 200 and sol2.get("id") != sol["id"] and sol2.get("estado") == "pendiente")
    est, cuerpo, _ = coord.pedir(f"/api/promocion/solicitudes/{sol2['id']}/decidir", "POST", {"aprobar": True, "nota": "Acta revisada."})
    verificar("coordinación aprueba", est == 200 and json.loads(cuerpo)["estado"] == "aprobada", cuerpo[:200])
    est, _, cab = ficha(docente, con_perdidas, grado_perdidas + 1)
    verificar("aprobada: la ficha ya se genera, marcada como autorizada", est == 200 and cab.get("x-promocion") == "autorizada", (est, cab))
    lista = json.loads(coord.pedir("/api/promocion/solicitudes?estado=aprobada")[1])
    verificar("queda registrado cuándo se usó el permiso", lista and lista[0]["usada_en"] is not None)
    verificar("ya no hay pendientes", json.loads(coord.pedir("/api/promocion/solicitudes")[1]) == [])

    print("\n[7] Retirar una solicitud")
    if grado_bien + 2 <= 11:
        est, cuerpo, _ = docente.pedir("/api/promocion/solicitudes", "POST",
                                       {"estudiante_id": sin_perdidas, "grado_destino": grado_bien + 2, "justificacion": "Validación por suficiencia académica."})
        s3 = json.loads(cuerpo)
        est, cuerpo, _ = docente.pedir(f"/api/promocion/solicitudes/{s3['id']}/anular", "POST")
        verificar("quien la pidió puede retirarla", est == 200 and json.loads(cuerpo)["estado"] == "anulada", cuerpo[:200])
        verificar("retirada: la ficha con ese grado sigue bloqueada", ficha(docente, sin_perdidas, grado_bien + 2)[0] == 409)
finally:
    servidor.terminate()
    servidor.wait(timeout=15)
    log.close()

engine.dispose()
shutil.rmtree(TMP, ignore_errors=True)
print("\nTODO OK" if not fallos else f"\n{fallos} FALLOS")
sys.exit(1 if fallos else 0)
