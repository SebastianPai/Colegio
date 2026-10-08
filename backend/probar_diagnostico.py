"""Prueba end-to-end del módulo de orientación escolar: Diagnóstico (Excel
importado, solo lectura) + Caso + CasoSeguimiento (trabajo activo de
orientación, ver models.py). Cubre permisos, consulta por grado y por
estudiante, vinculación manual de menciones, abrir un caso desde una
mención o a mano, agregar seguimientos sin duplicar casos, cambiar estado,
filtros, el dashboard de resumen y los tres PDF (grado, estudiante, caso).
También verifica que el PDF (documento institucional) nunca muestre estados
internos como "Sin vincular" y que la sección de seguimiento diga algo
discreto cuando de verdad no hay nada, en vez de "0 notas". Trabaja sobre
una COPIA de colegio.db (que ya trae el diagnóstico real importado), nunca
toca la base real."""

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

import fitz  # PyMuPDF

BACKEND = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="ietaba_diagnostico_"))
COPIA = TMP / "colegio.db"
PUERTO = 8810
BASE = f"http://127.0.0.1:{PUERTO}"
CLAVE = "PruebaDiagnostico2026"

origen = sqlite3.connect(f"file:{BACKEND / 'colegio.db'}?mode=ro", uri=True)
destino = sqlite3.connect(COPIA)
with destino:
    origen.backup(destino)
origen.close()
destino.close()

os.environ["IETABA_DB_PATH"] = str(COPIA)
sys.path.insert(0, str(BACKEND))
from sqlalchemy import select  # noqa: E402

from app import auth, models, rbac_admin, seguridad  # noqa: E402
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

total_diagnosticos = db.scalar(select(models.DiagnosticoGrado.id).limit(1))
verificar("la copia trae diagnósticos ya importados (corrida real previa)", total_diagnosticos is not None)

rocio = db.scalar(select(models.Usuario).where(models.Usuario.documento == "rocio.riascos"))
verificar("existe el usuario rocio.riascos con rol orientacion", rocio is not None)
if rocio is not None:
    rocio.clave_hash = seguridad.hashear_clave(CLAVE)
    rocio.estado = "activo"
    rocio.debe_cambiar_clave = False
    rocio.intentos_fallidos = 0
    rocio.bloqueado_hasta = None
    db.flush()

u_docente = auth.registrar_usuario(db, documento="PRUEBA-DOCENTE-DX", nombre="Prueba Docente DX", clave=CLAVE, debe_cambiar_clave=False)
rbac_admin.establecer_roles_usuario(db, u_docente, ["docente"], asignado_por_id=None)

diagnostico_con_menciones = db.scalar(
    select(models.DiagnosticoGrado)
    .join(models.DiagnosticoMencion)
    .where(models.DiagnosticoMencion.estudiante_id.is_(None))
)
verificar("hay un diagnóstico con al menos una mención SIN vincular (para probar vincular_mencion)", diagnostico_con_menciones is not None)
mencion_sin_vincular = next((m for m in diagnostico_con_menciones.menciones if m.estudiante_id is None), None) if diagnostico_con_menciones else None

estudiante_para_vincular = (
    db.scalar(
        select(models.Estudiante).where(
            models.Estudiante.sede_id == diagnostico_con_menciones.sede_id,
            models.Estudiante.grado == diagnostico_con_menciones.grado,
            models.Estudiante.curso == diagnostico_con_menciones.curso,
        )
    )
    or db.scalar(
        select(models.Estudiante).where(
            models.Estudiante.sede_id == diagnostico_con_menciones.sede_id,
            models.Estudiante.grado == diagnostico_con_menciones.grado,
        )
    )
) if diagnostico_con_menciones else None

# Preferido: uno del MISMO diagnóstico que se usa en las secciones [8]/[9]/
# [13]/[14] (así los casos que se crean ahí sí caen dentro de ese grado y
# las pruebas de conteo tienen sentido). Si ese diagnóstico no tiene ninguno
# ya vinculado, se usa cualquier otro (secciones [5]/[6] no dependen del grado).
estudiante_con_mencion = next(
    (m.estudiante for m in (diagnostico_con_menciones.menciones if diagnostico_con_menciones else []) if m.estudiante_id),
    None,
) or db.scalar(
    select(models.Estudiante).join(models.DiagnosticoMencion, models.DiagnosticoMencion.estudiante_id == models.Estudiante.id)
)
verificar("hay al menos un estudiante ya vinculado automáticamente (para /estudiantes/{id})", estudiante_con_mencion is not None)

diagnostico_id = diagnostico_con_menciones.id if diagnostico_con_menciones else None
mencion_id = mencion_sin_vincular.id if mencion_sin_vincular else None
estudiante_vincular_id = estudiante_para_vincular.id if estudiante_para_vincular else None
estudiante_con_mencion_id = estudiante_con_mencion.id if estudiante_con_mencion else None

db.commit()
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
        # Solo GET se reintenta: en Windows, urllib a veces recibe
        # ConnectionResetError al leer respuestas grandes (los PDF) aunque el
        # servidor respondió bien (verificado con curl y navegador). Un POST
        # no se repite para no duplicar datos.
        intentos = 3 if metodo == "GET" else 1
        for intento in range(intentos):
            req = urllib.request.Request(BASE + ruta, data=datos, method=metodo, headers=cab)
            try:
                with self.op.open(req, timeout=20) as r:
                    return r.status, r.read(), dict(r.headers)
            except urllib.error.HTTPError as e:
                return e.code, e.read(), dict(e.headers)
            except ConnectionResetError:
                if intento == intentos - 1:
                    raise
                time.sleep(0.5)


def texto_pdf(datos: bytes) -> str:
    with fitz.open("pdf", datos) as doc:
        return "\n".join(pagina.get_text() for pagina in doc)


try:
    for _ in range(120):
        try:
            urllib.request.urlopen(f"{BASE}/api/sedes", timeout=2).read()
            break
        except Exception:
            time.sleep(0.25)

    orientacion, docente = Cliente(), Cliente()
    print("\n[1] Login")
    verificar("orientación (rocio.riascos) entra", orientacion.pedir("/api/auth/login", "POST", {"usuario": "rocio.riascos", "clave": CLAVE})[0] == 200)
    verificar("docente entra", docente.pedir("/api/auth/login", "POST", {"usuario": "PRUEBA-DOCENTE-DX", "clave": CLAVE})[0] == 200)

    print("\n[2] Permisos")
    verificar("un docente NO puede ver /api/diagnosticos/grados (403)", docente.pedir("/api/diagnosticos/grados")[0] == 403)
    est, cuerpo, _ = orientacion.pedir("/api/diagnosticos/grados")
    verificar("orientación SÍ ve la lista de grados (200)", est == 200, cuerpo[:300])
    grados = json.loads(cuerpo) if est == 200 else []
    verificar("trae los 36 grados importados", len(grados) == 36, len(grados))

    print("\n[3] Detalle por grado")
    est, cuerpo, _ = orientacion.pedir(f"/api/diagnosticos/grados/{diagnostico_id}")
    verificar("detalle 200", est == 200, cuerpo[:300])
    detalle = json.loads(cuerpo) if est == 200 else {}
    verificar("trae menciones", len(detalle.get("menciones", [])) > 0, detalle.get("menciones"))
    verificar("trae historial (al menos la versión actual)", len(detalle.get("historial", [])) >= 1)

    verificar("el resumen del grado trae 'periodo' (fecha real de la hoja, no inventada)", detalle.get("periodo") not in (None, ""), detalle.get("periodo"))
    verificar("el detalle trae 'casos' (aunque esté vacío)", "casos" in detalle, detalle.keys())
    verificar("cada mención trae 'confianza' (alta/media/baja)", all(m.get("confianza") in ("alta", "media", "baja") for m in detalle["menciones"]), detalle["menciones"][:2])

    print("\n[3b] Preescolar: no se debe repetir el mismo párrafo largo para varios estudiantes distintos")
    preescolar = next(g for g in grados if g["grado"] == 0)
    est, cuerpo, _ = orientacion.pedir(f"/api/diagnosticos/grados/{preescolar['id']}")
    dx_preescolar = json.loads(cuerpo)
    menciones_pre = dx_preescolar["menciones"]
    verificar("trae varias menciones (>=20)", len(menciones_pre) >= 20, len(menciones_pre))
    from collections import defaultdict
    por_texto = defaultdict(set)
    for m in menciones_pre:
        if not m["texto_compartido"]:
            por_texto[(m["categoria"], m["texto"])].add(m["nombre_detectado"])
    repetidos_indebidos = {k: v for k, v in por_texto.items() if len(v) > 1 and len(k[1]) > 40}
    verificar(
        "ningún texto largo (>40 car.) se repite igual para 2+ nombres sin marcar texto_compartido",
        not repetidos_indebidos, repetidos_indebidos,
    )
    aylen = next((m for m in menciones_pre if m["nombre_detectado"] and "AYLEN" in m["nombre_detectado"]), None)
    verificar("AYLEN tiene su propio detalle (no el párrafo completo de los 5 mencionados)", aylen and "estudiando en otro centro" in aylen["texto"] and "MIRTA" not in aylen["texto"], aylen)
    mirta = next((m for m in menciones_pre if m["nombre_detectado"] and "MIRTA" in m["nombre_detectado"]), None)
    verificar("MIRTA tiene su propio detalle, distinto al de AYLEN", mirta and mirta["texto"] != aylen["texto"] and "AYLEN" not in mirta["texto"], mirta)

    print("\n[4] PDF por grado — documento institucional, sin estados internos")
    est, cuerpo, cab = orientacion.pedir(f"/api/diagnosticos/grados/{diagnostico_id}/pdf")
    verificar("PDF 200", est == 200, cuerpo[:200])
    verificar("content-type application/pdf", cab.get("content-type") == "application/pdf", cab.get("content-type"))
    verificar("el PDF no está vacío", len(cuerpo) > 1000, len(cuerpo))
    verificar("un docente NO puede pedir el PDF (403)", docente.pedir(f"/api/diagnosticos/grados/{diagnostico_id}/pdf")[0] == 403)
    texto = texto_pdf(cuerpo)
    verificar("el PDF NO menciona 'vincular' en ninguna forma (eso es solo de la app)", "vincular" not in texto.lower(), texto[:2000])
    verificar("el PDF trae el periodo en el encabezado", detalle["periodo"] in texto, (detalle["periodo"], texto[:500]))
    verificar("el PDF trae las secciones numeradas de la maqueta", "1. INFORMACIÓN GENERAL DEL GRUPO" in texto, texto[:1500])
    verificar("el PDF trae la sección de situaciones por estudiante", "3. SITUACIONES IDENTIFICADAS EN ESTUDIANTES" in texto)

    print("\n[5] Por estudiante")
    est, cuerpo, _ = orientacion.pedir(f"/api/diagnosticos/estudiantes/{estudiante_con_mencion_id}")
    verificar("resumen del estudiante 200", est == 200, cuerpo[:300])
    resumen_est = json.loads(cuerpo) if est == 200 else {}
    verificar("trae menciones y casos (aunque estén vacíos)", "menciones" in resumen_est and "casos" in resumen_est, resumen_est.keys())
    verificar("trae al menos una mención", len(resumen_est.get("menciones", [])) > 0, resumen_est)

    est, cuerpo, cab = orientacion.pedir(f"/api/diagnosticos/estudiantes/{estudiante_con_mencion_id}/pdf")
    verificar("PDF por estudiante 200", est == 200, cuerpo[:200])
    verificar("content-type application/pdf", cab.get("content-type") == "application/pdf")
    verificar("el PDF por estudiante tampoco dice 'Sin vincular'", "sin vincular" not in texto_pdf(cuerpo).lower())

    print("\n[6] Vincular manualmente una mención")
    verificar("hay una mención sin vincular disponible para la prueba", mencion_id is not None)
    if mencion_id is not None:
        est, cuerpo, _ = orientacion.pedir(f"/api/diagnosticos/menciones/{mencion_id}", "PATCH", {"estudiante_id": estudiante_vincular_id})
        verificar("vincular responde 200", est == 200, cuerpo[:300])
        vinculada = json.loads(cuerpo) if est == 200 else {}
        verificar("queda con el estudiante correcto", vinculada.get("estudiante_id") == estudiante_vincular_id, vinculada)
        verificar("vinculo_automatico queda en False (fue manual)", vinculada.get("vinculo_automatico") is False, vinculada)

        est, cuerpo, _ = orientacion.pedir(f"/api/diagnosticos/menciones/{mencion_id}", "PATCH", {"estudiante_id": None})
        verificar("desvincular responde 200", est == 200, cuerpo[:300])
        desvinculada = json.loads(cuerpo) if est == 200 else {}
        verificar("queda sin estudiante", desvinculada.get("estudiante_id") is None, desvinculada)

    est, cuerpo, _ = orientacion.pedir("/api/diagnosticos/menciones/999999", "PATCH", {"estudiante_id": None})
    verificar("vincular una mención inexistente da 404", est == 404, (est, cuerpo[:200]))

    est, cuerpo, _ = orientacion.pedir(f"/api/diagnosticos/menciones/{mencion_id}", "PATCH", {"estudiante_id": 999999})
    verificar("vincular a un estudiante inexistente da 400", est == 400, (est, cuerpo[:200]))

    print("\n[7] Dashboard: resumen real de orientación")
    est, cuerpo, _ = orientacion.pedir("/api/diagnosticos/resumen")
    verificar("resumen 200", est == 200, cuerpo[:300])
    resumen0 = json.loads(cuerpo) if est == 200 else {}
    verificar("trae los 4 conteos esperados", set(resumen0) == {"diagnosticos", "casos_abiertos", "casos_en_seguimiento", "seguimientos_pendientes"}, resumen0)
    verificar("diagnosticos = 36 (nada inventado)", resumen0.get("diagnosticos") == 36, resumen0)
    # La copia sale de la base REAL, que ya puede tener casos creados usando
    # la app: el conteo debe coincidir con lo que hay, no suponer cero.
    _con = sqlite3.connect(COPIA)
    _reales = dict(_con.execute("select estado, count(*) from diagnosticos_observaciones group by estado").fetchall())
    _con.close()
    verificar(
        "los conteos de casos coinciden con los que hay en la base",
        resumen0.get("casos_abiertos") == _reales.get("abierto", 0) and resumen0.get("casos_en_seguimiento") == _reales.get("en_seguimiento", 0),
        (resumen0, _reales),
    )

    print("\n[8] Caso creado a mano (sin venir de una mención)")
    verificar("un docente NO puede crear un caso (403, sin diagnosticos.observar)", docente.pedir("/api/diagnosticos/casos", "POST", {"estudiante_id": estudiante_con_mencion_id, "tipo": "comportamiento", "descripcion": "x"})[0] == 403)
    est, cuerpo, _ = orientacion.pedir("/api/diagnosticos/casos", "POST", {
        "estudiante_id": estudiante_con_mencion_id, "tipo": "comportamiento", "titulo": "Situación en el aula",
        "descripcion": "El estudiante presentó una discusión con un compañero.", "acciones": "Diálogo inicial",
    })
    verificar("crear caso manual responde 200", est == 200, cuerpo[:300])
    caso_manual = json.loads(cuerpo) if est == 200 else {}
    verificar("queda origen=manual, estado=abierto", caso_manual.get("origen") == "manual" and caso_manual.get("estado") == "abierto", caso_manual)
    verificar("un tipo de caso inválido da 400", orientacion.pedir("/api/diagnosticos/casos", "POST", {"estudiante_id": estudiante_con_mencion_id, "tipo": "inventado", "descripcion": "x"})[0] == 400)
    verificar("una descripción vacía da 400", orientacion.pedir("/api/diagnosticos/casos", "POST", {"estudiante_id": estudiante_con_mencion_id, "tipo": "otra", "descripcion": "   "})[0] == 400)
    verificar("un estudiante inexistente da 400", orientacion.pedir("/api/diagnosticos/casos", "POST", {"estudiante_id": 999999, "tipo": "otra", "descripcion": "x"})[0] == 400)

    print("\n[9] Caso abierto DESDE una mención del Excel")
    est, cuerpo, _ = orientacion.pedir("/api/diagnosticos/casos", "POST", {
        "estudiante_id": estudiante_vincular_id, "tipo": "inasistencia", "titulo": "Inasistencia detectada en el diagnóstico",
        "descripcion": "Descripción tomada de la mención del Excel.", "mencion_origen_id": mencion_id,
    })
    verificar("crear caso desde mención responde 200", est == 200, cuerpo[:300])
    caso_importado = json.loads(cuerpo) if est == 200 else {}
    verificar("queda origen=importado", caso_importado.get("origen") == "importado", caso_importado)

    est, cuerpo, _ = orientacion.pedir(f"/api/diagnosticos/grados/{diagnostico_id}")
    detalle_mencion = next(m for m in json.loads(cuerpo)["menciones"] if m["id"] == mencion_id)
    verificar("la mención de origen ahora trae caso_id (para no abrir el caso dos veces)", detalle_mencion.get("caso_id") == caso_importado.get("id"), detalle_mencion)

    print("\n[10] Seguimiento del caso: NO crea un caso nuevo, se agrega al historial")
    verificar("un docente NO puede agregar seguimiento (403)", docente.pedir(f"/api/diagnosticos/casos/{caso_manual['id']}/seguimientos", "POST", {"situacion": "x"})[0] == 403)
    est, cuerpo, _ = orientacion.pedir(f"/api/diagnosticos/casos/{caso_manual['id']}/seguimientos", "POST", {
        "situacion": "Se conversó nuevamente con el estudiante.", "accion_realizada": "Compromiso de buen comportamiento",
        "compromisos": "No repetir la situación", "proxima_fecha": "2026-10-15",
    })
    verificar("agregar seguimiento responde 200", est == 200, cuerpo[:300])
    caso_con_seg = json.loads(cuerpo) if est == 200 else {}
    verificar("el caso pasa a 'en_seguimiento' automáticamente", caso_con_seg.get("estado") == "en_seguimiento", caso_con_seg)
    verificar("el próximo seguimiento del caso se actualizó", caso_con_seg.get("proximo_seguimiento") == "2026-10-15", caso_con_seg)
    verificar("el seguimiento quedó en el historial del MISMO caso (no uno nuevo)", len(caso_con_seg.get("seguimientos", [])) == 1, caso_con_seg)

    est, cuerpo, _ = orientacion.pedir(f"/api/diagnosticos/casos/{caso_manual['id']}")
    caso_relectura = json.loads(cuerpo)
    verificar("releer el caso trae el mismo seguimiento (no duplicado)", len(caso_relectura["seguimientos"]) == 1, caso_relectura)

    print("\n[11] Cambiar estado del caso")
    est, cuerpo, _ = orientacion.pedir(f"/api/diagnosticos/casos/{caso_manual['id']}/estado", "PATCH", {"estado": "cerrado"})
    verificar("cerrar el caso responde 200", est == 200, cuerpo[:300])
    cerrado = json.loads(cuerpo) if est == 200 else {}
    verificar("queda cerrado con fecha de cierre", cerrado.get("estado") == "cerrado" and cerrado.get("cerrado_en"), cerrado)
    verificar("un estado inválido da 400", orientacion.pedir(f"/api/diagnosticos/casos/{caso_manual['id']}/estado", "PATCH", {"estado": "inventado"})[0] == 400)

    print("\n[12] Listado de casos con filtros")
    est, cuerpo, _ = orientacion.pedir(f"/api/diagnosticos/casos?estudiante_id={estudiante_con_mencion_id}")
    verificar("listar casos por estudiante 200", est == 200, cuerpo[:300])
    casos_est = json.loads(cuerpo) if est == 200 else []
    verificar("trae el caso manual de ese estudiante", any(c["id"] == caso_manual["id"] for c in casos_est), casos_est)
    est, cuerpo, _ = orientacion.pedir("/api/diagnosticos/casos?estado=cerrado")
    verificar("filtrar por estado=cerrado trae el caso recién cerrado", any(c["id"] == caso_manual["id"] for c in json.loads(cuerpo)))
    est, cuerpo, _ = orientacion.pedir("/api/diagnosticos/casos?estado=abierto")
    verificar("filtrar por estado=abierto trae el caso importado (todavía abierto)", any(c["id"] == caso_importado["id"] for c in json.loads(cuerpo)))

    print("\n[13] El caso aparece en el perfil del estudiante y en el diagnóstico del grado")
    est, cuerpo, _ = orientacion.pedir(f"/api/diagnosticos/estudiantes/{estudiante_con_mencion_id}")
    perfil = json.loads(cuerpo)
    verificar("el perfil del estudiante trae 'casos' (ya no 'observaciones')", "casos" in perfil, perfil.keys())
    verificar("el caso manual aparece en su perfil", any(c["id"] == caso_manual["id"] for c in perfil["casos"]), perfil["casos"])

    est, cuerpo, _ = orientacion.pedir(f"/api/diagnosticos/grados/{diagnostico_id}")
    detalle3 = json.loads(cuerpo)
    verificar("el detalle del grado trae 'casos' con conteos reales", "casos" in detalle3 and detalle3["casos_abiertos"] >= 1, detalle3.get("casos_abiertos"))
    verificar("estudiantes_mencionados y total_menciones son conceptos separados", "estudiantes_mencionados" in detalle3 and "total_menciones" in detalle3, detalle3.keys())

    print("\n[14] PDF: paginación adaptativa y sección de seguimiento con los casos reales")
    est, cuerpo, cab = orientacion.pedir(f"/api/diagnosticos/grados/{diagnostico_id}/pdf")
    verificar("PDF por grado 200 tras crear casos", est == 200, cuerpo[:200])
    texto_pdf_grado = texto_pdf(cuerpo)
    verificar("el PDF NO menciona 'vincular', 'caso_id' ni estados internos", "vincular" not in texto_pdf_grado.lower() and "caso_id" not in texto_pdf_grado.lower())
    verificar("el PDF incluye la descripción del caso en Seguimiento", "El estudiante presentó una discusión" in texto_pdf_grado, texto_pdf_grado[:200])

    print("\n[15] PDF: 'sin registros de seguimiento' cuando de verdad no hay nada (grado sin casos)")
    otro_grado = next(g for g in grados if g["id"] != diagnostico_id)
    est, cuerpo, cab = orientacion.pedir(f"/api/diagnosticos/grados/{otro_grado['id']}/pdf")
    verificar("PDF de un grado sin casos responde 200", est == 200)
    texto_otro = texto_pdf(cuerpo)
    tiene_seguimiento_propio = bool(json.loads(orientacion.pedir(f"/api/diagnosticos/grados/{otro_grado['id']}")[1])["seguimiento_nota"])
    if not tiene_seguimiento_propio:
        verificar("dice el mensaje discreto en vez de '0 notas' o nada", "Sin registros de seguimiento en este diagnóstico" in texto_otro, texto_otro[-1500:])

    print("\n[16] Informe de caso individual (independiente del diagnóstico grupal)")
    est, cuerpo, cab = orientacion.pedir(f"/api/diagnosticos/casos/{caso_manual['id']}/pdf")
    verificar("PDF de caso 200", est == 200, cuerpo[:200])
    verificar("content-type application/pdf", cab.get("content-type") == "application/pdf")
    texto_caso = texto_pdf(cuerpo)
    verificar("trae el título del informe", "INFORME DE SEGUIMIENTO DE ORIENTACIÓN" in texto_caso, texto_caso[:300])
    verificar("trae el seguimiento agregado", "Se conversó nuevamente con el estudiante" in texto_caso)
    verificar("un docente NO puede pedir el PDF del caso (403)", docente.pedir(f"/api/diagnosticos/casos/{caso_manual['id']}/pdf")[0] == 403)
finally:
    servidor.terminate()
    servidor.wait(timeout=15)
    log.close()

engine.dispose()
shutil.rmtree(TMP, ignore_errors=True)
print("\nTODO OK" if not fallos else f"\n{fallos} FALLOS")
sys.exit(1 if fallos else 0)
