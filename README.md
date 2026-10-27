# Sistema IETABA

Sistema para reemplazar los Excel manuales de la secretaría de la
**Institución Educativa Técnica Agroambiental Bilingüe Awá (IETABA)**: base
de datos de estudiantes de las 48 sedes, listas por sede/grado, y registro de
asistencia diaria para detectar rápido quién falta.

Es una app web que corre en un PC (por ejemplo el de secretaría) y se puede
abrir desde cualquier navegador de la misma red del colegio entrando a la IP
de esa máquina.

## Datos reales cargados

Hay dos fuentes y **no tienen la misma prioridad**:

1. **B.D. MATRICULA INST. IETABA** (`B.D. MATRICULA INST. IETABA - última
   Actualización ABRIL 22.xlsx`) es la base de datos oficial de matrícula →
   **fuente autoritativa**. Hoy solo cubre la sede principal (965
   estudiantes), pero todo lo que traiga manda sobre la otra fuente.
2. **LISTA DE ASISTENCIA** (`1 LISTA DE ASISTENCIA INST. EDU. IETABA X
   GRADOS.xlsx`) es solo un formato/reporte derivado, así que **solo se usa
   para completar las 47 sedes rurales que todavía no tienen su propio Excel
   de matrícula** (1,184 estudiantes más).

Total actual: **2,149 estudiantes en 48 sedes**. Cada estudiante queda
marcado con `verificado_matricula`:
- `true` = confirmado contra B.D. MATRICULA (hoy, los 965 de la sede
  principal).
- `false` = está en la lista de asistencia de una sede que sí tiene Excel de
  matrícula, pero no aparece en ese Excel → posible error a revisar (el
  importador lo imprime en consola al final).
- `null` = todavía no hay un Excel de matrícula propio para esa sede con el
  cual comparar (las 47 sedes rurales).

> Nota: falta confirmar con el colegio cómo registran a quienes se retiran o
> trasladan (si se borran de la lista o quedan en otro estado/archivo), para
> que el filtro de activo/inactivo refleje la realidad.

## Estado actual

- Gestión de sedes (48, con código DANE, resguardo, institución/centro
  educativo), cada una desglosada por grado y división (ej. "Sexto - Uno").
- Listado de estudiantes filtrable por sede, grado, división, estado y
  búsqueda por nombre/documento, con **paginación** (25/50/100/200 por
  página).
- **Verificación cruzada entre los dos Excel del colegio**: cada estudiante
  importado de la lista de asistencia se compara contra el Excel de
  matrícula (cuando hay una segunda fuente para su sede) y queda marcado
  como "✓ OK" o "⚠ no está en matrícula", con un filtro para ver solo los
  no verificados.
- **Agregar estudiante** con verificación previa por documento: si ya existe
  no lo duplica, si no existe advierte que hay que confirmarlo con el
  coordinador antes de matricularlo.
- **Impresión de listas en el formato oficial exacto** (mismo membrete,
  logos, color institucional y columnas que el Excel real), disponible
  directamente desde la vista de Estudiantes al filtrar por sede + grado.
- **Reportes**: clasificación editable de qué sedes pertenecen realmente a
  IETABA (autodetectado desde el Excel, pero corregible a mano), con conteo
  de estudiantes por sede y por género, solo sobre las sedes IETABA.
- **Ficha del estudiante** (clic en cualquier fila de Estudiantes):
  - Tipo de documento (C.C./T.I./R.C./Otro con texto libre) y lugar de
    expedición, editables y reutilizados en las constancias.
  - Fotos/documentos escaneados (cédula, ficha de matrícula, etc.), en
    cantidad libre — una, dos o las que hagan falta, cada una con su
    etiqueta.
  - **Generación de constancias de estudio** en el formato oficial exacto
    (`plantillas/constancia_estudio.docx`, copia fiel del formato del
    colegio): solo se completan nombre, documento, grado, jornada, año
    escolar, fecha de expedición y el propósito ("Válido para...", con
    opciones predefinidas + "Otro" en texto libre). El resto del documento
    (membrete, logos, firma del rector) no se toca.
  - **Vista previa en vivo** (datos a la izquierda, vista previa del texto a
    la derecha) mientras se llena el formulario de la constancia.
  - Cada constancia generada se guarda en Word **y en PDF** (convertido con
    Word instalado en el PC — si Word no está disponible, sigue funcionando
    solo con Word/.docx).
- **Registro de constancias** (pestaña "Constancias"): historial de todas
  las constancias generadas, filtrable por nombre/documento, rango de
  fechas y propósito, con enlaces para volver a descargar el Word o el PDF
  ya generado (no se puede editar, es un archivo histórico).

## Horarios (Sede #01)

Módulo **Horarios** en el menú (Gestión → Horarios): convierte el horario
oficial de la sede principal en una herramienta de consulta rápida y gestión
de reemplazos. No crea catálogos nuevos — cada docente, grupo (grado+curso) y
área se enlaza con los registros que ya existen; lo que no empareje con
confianza se reporta al importar, nunca se inventa.

- **Fuentes** (carpeta `...\HORARIO ULTIMO ultimo AJUSTE 21 DE ABRIL 2026\VD\`,
  última entrega): un Word con los 42 cuadros de docente + un Excel con los
  docentes agregados después. `backend/importar_horario.py` lee las dos y las
  combina en `BloqueHorario` (jornada única de mañana, 6 horas). Es idempotente
  (borra e inserta el año, y re-enlaza ausencias/reemplazos existentes), así que
  se puede re-correr cuando cambien los archivos. Al final imprime un informe de
  inconsistencias: hojas omitidas (borradores/vistas por grupo), docentes sin
  emparejar, áreas sin catálogo, correcciones de rótulo aplicadas, docentes que
  quedaron sin horario, y **conflictos** (dos docentes para el mismo grupo a la
  misma hora). `--sin-xlsx` importa solo el Word; `--docx`/`--xlsx` aceptan otras
  rutas.
- **Vistas**: Hoy (panel con conteos reales, ausencias del día y sus clases
  afectadas, reemplazos del día), Libres ahora (reloj en vivo + estados
  🟢🔵🟡⚪🔴🟠 y consulta "¿quién está libre?" por día/hora), Docente (rejilla
  semanal con celdas LIBRE), Grupo (cronológico por día, enlazado al grupo
  real), Día, Reemplazos de hoy, General. Búsqueda rápida de docente / grupo
  (`8-1`) / área arriba de todo.
- **Ausencias**: se registra `docente + fecha + motivo`; el sistema deduce las
  clases afectadas del horario y crea un reemplazo "pendiente" por cada una.
- **Reemplazos**: candidatos ordenados por una puntuación **transparente**
  (libre + sin conflictos 40 % · misma área 25 · trabaja con el grado 15 ·
  con el grupo 10 · continuidad 6 · misma sede 4), cada uno con el detalle
  de por qué. Nunca propone a alguien con clase esa franja, ausente o ya
  cubriendo; revalida al asignar. Se puede cambiar o cancelar sin tocar el
  horario original.
- **Conflictos**: cuando los archivos ponen dos docentes en el mismo grupo a
  la misma hora, los dos quedan en el horario (marcados con ⚠) y en la pestaña
  **Conflictos** el administrativo confirma cuál es el oficial (el otro se
  descarta, pero sigue visible tachado) o decide dejar los dos. Una ausencia
  cuya clase está en conflicto no genera reemplazo hasta que se resuelve.
- Pruebas: `backend/probar_horario.py`.

## Importación desde SAPRED

Dos reportes distintos, con el mismo patrón (importación manual de PDF o
automatización con navegador — el usuario/contraseña de SAPRED se escriben
solo en la ventana de Chrome, la app nunca los ve):

1. **Consolidado de Asignaturas por periodo** → notas numéricas y el
   Director de Grupo. Alimenta Notas → Grilla y la Conciliación SIMAC ↔
   SAPRED.
2. **Boletín informativo** (Reportes → Reportes y Resultados Académicos) →
   el **profesor de cada materia** (asignación por área), el **concepto**
   descriptivo de cada área y la **observación** del director de grupo. Lo
   que falta (concepto o observación) queda como `PendienteBoletin` y se ve
   ordenado en Boletines → Pendientes y en Notas → Grilla (con la opción
   "Solo lo que falta" y un informe imprimible de faltantes por
   grupo/materia/profesor/estudiante). El texto real se guarda en
   `TextoBoletin`.

Nada se duplica al reimportar. Ver `herramientas/importar_sapred/LEEME.txt`
para el detalle y `backend/probar_boletin.py` para afinar el lector del
boletín contra un PDF real.

## Generar boletines por sede (PDF)

**Boletines → SAPRED → "Generar boletines por sede"**. No importa nada: para
cada sede rural genera en SAPRED el boletín de calificaciones de todos sus
grados (todas las secciones) y los **une en un único PDF por sede, ordenado
por grado** (Primero, Segundo, Tercero…), listo para entregar al docente. En
"Opciones de impresión" deja siempre activados **Mostrar Sede** e **Incluir
Puesto**.

- Se elige período y una o varias sedes (o todas), igual que la Auditoría:
  barra de progreso, historial y "🔁 Reintentar solo las que fallaron".
  Reutiliza `AuditoriaSapred` con `tipo='boletin_pdf'`.
- Los archivos quedan en `backend/boletines_sedes/<año>-P<n>/SEDE ## NOMBRE.pdf`
  y se descargan también desde la misma pantalla.
- Backend: `app/generacion_boletines.py` (une los PDF por grado con PyMuPDF),
  endpoints `POST/GET /api/boletines/generar-pdf` (+ `/{id}/ensamblar-sede`
  interno y `/{id}/archivo` para descargar). Automatización:
  `herramientas/importar_sapred/generar_boletines_headless.js` +
  `sapred_core.js` (`abrirPestanaBoletinGeneral`,
  `configurarOpcionesImpresionBoletin`, `generarBoletinPdfSede`).
- **SAPRED confirmado** (`descubrir_boletin_general.js`, sep-2026): no hay un
  menú de boletín aparte — es el mismo `reportes/boletin/sel.php` (id 186)
  pero con salida **PDF (`#des2`)**. "Opciones de impresión" es la pantalla
  global `config/index.php?tipo=b`; los radios son `sede_cur` (Mostrar Sede)
  e `inc_puesto` (Incluir Puesto), que en IETABA ya están en Sí.
- **Falta 1 corrida real** para ver cómo entrega SAPRED el PDF al darle
  "Generar" (descarga directa vs. ventana emergente); `generarBoletinPdfSede`
  contempla ambas.

## Usuarios y sesiones (Fase 2: identidad)

Existe la infraestructura de autenticación, pero **todavía no protege nada**:
la aplicación sigue funcionando sin iniciar sesión, igual que antes. Lo único
que exige sesión son los propios endpoints de `/api/auth`. Los roles y
permisos llegan en la fase siguiente.

- **Crear el primer usuario** (no hay pantalla todavía; se hace en el PC
  servidor, y la contraseña se escribe por teclado, no queda en el historial):

  ```powershell
  cd backend
  ./venv/Scripts/python.exe crear_usuario.py crear --documento 1087654321 --nombre "Ana Pai"
  ./venv/Scripts/python.exe crear_usuario.py listar
  ./venv/Scripts/python.exe crear_usuario.py clave --documento 1087654321 --clave-temporal
  ./venv/Scripts/python.exe crear_usuario.py estado --documento 1087654321 --valor inactivo
  ```

  Para un docente que ya existe en la tabla `docentes`, se enlaza con
  `--docente-documento <documento>`: el usuario no duplica sus datos.

- **Endpoints**: `POST /api/auth/login`, `/refresh`, `/logout`,
  `/logout-todos`, `/cambiar-clave`; `GET /api/auth/yo`, `/sesiones`;
  `DELETE /api/auth/sesiones/{id}`.
- **Cómo se sostiene la sesión**: token de acceso de 15 minutos (firmado) y
  token de renovación rotatorio, los dos en cookies HttpOnly — nada se guarda
  en `localStorage`. De las contraseñas solo queda su hash scrypt y de los
  tokens de renovación solo su SHA-256. Con "confiar en este dispositivo" la
  sesión dura hasta 180 días sin volver a pedir la contraseña; en equipos
  compartidos, 12 horas.
- **Revocar**: `/logout` (este dispositivo), `/logout-todos`,
  `DELETE /api/auth/sesiones/{id}`, o desactivar el usuario con
  `crear_usuario.py estado`. Surte efecto en la siguiente petición.
- La clave con la que se firman los tokens vive en
  `backend/certs/secreto_sesiones.key` (se crea sola). **No compartir.** Si se
  borra, todos tienen que volver a iniciar sesión.
- Sobre HTTP (puerto 8000) las cookies no pueden marcarse `Secure`, así que
  viajan en claro por la red del colegio: para usar el login de verdad,
  entrar por HTTPS (`iniciar_https.ps1`, puerto 8443).
- Pruebas: `./venv/Scripts/python.exe probar_autenticacion.py` (trabaja sobre
  una copia temporal; no toca `colegio.db`).

## Pendiente (próximas fases)

- Confirmar con el colegio el manejo de estudiantes retirados/trasladados.
- Horarios: exportar la rejilla en PDF con el formato oficial; ampliar a las
  sedes rurales cuando exista un archivo de horario para ellas (hoy el módulo
  cubre la Sede #01, que es la única con horario por franjas).
- Automatización con navegador del "Boletín informativo": la ruta ya está
  puesta (`reportes/boletin/sel.php`, id 186); falta la primera corrida real
  para afinar dos detalles del formulario (ver LEEME.txt).
- "Generar boletines por sede (PDF)": SAPRED ya descubierto
  (`reportes/boletin/sel.php` id 186, salida PDF `#des2`; opciones en
  `config/index.php?tipo=b`). Falta una corrida real para confirmar cómo
  entrega el PDF (descarga vs. popup).
- Roles de usuario si hace falta restringir quién edita qué.

## Cómo ejecutar

Requiere Python 3.12+.

```powershell
cd backend
python -m venv venv
./venv/Scripts/Activate.ps1
pip install -r requirements.txt

# Importar los datos reales (solo la primera vez, o para refrescar datos)
python importar_matricula.py "D:\ietaba\ARCHIVO INGENIERO\1 LISTA DE ASISTENCIA INST. EDU. IETABA X GRADOS.xlsx"

# Importar el horario de la Sede #01 (Word + Excel de la carpeta VD por defecto).
# Imprime al final el informe de inconsistencias / conflictos.
python importar_horario.py --anio 2026

# Arrancar el servidor
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Al arrancar, `app/migraciones.py` pone la base al día sola (idempotente) y,
antes de recrear cualquier tabla, deja un respaldo `colegio.db.bak_*`.
Pruebas de esa base: `./venv/Scripts/python.exe probar_cimientos.py` (trabaja
sobre una copia temporal, nunca sobre `colegio.db`).

> **Respaldos con la base en modo WAL:** mientras el servidor corre, los
> cambios recientes pueden estar todavía en `colegio.db-wal`. Copiar solo
> `colegio.db` puede dejar un respaldo incompleto: copia los tres archivos
> (`colegio.db`, `-wal`, `-shm`) con el servidor detenido, o usa la API de
> backup de SQLite (`migraciones.respaldar("motivo")`), que es segura en
> cualquier momento.

Luego abre http://localhost:8000 en el navegador. Para que otras personas de
la red del colegio lo usen desde su propio computador, deben entrar a
`http://<IP-de-este-PC>:8000` (la IP se ve con `ipconfig` en este PC).

La documentación interactiva de la API queda disponible en
http://localhost:8000/docs.

## Escanear documentos desde el celular (HTTPS local)

El escáner de documentos (cámara del celular) solo funciona si el navegador
lo ve como una conexión segura (HTTPS) — por diseño de iOS/Android, no hay
forma de evitarlo. Como el colegio no tiene internet, no se puede sacar un
certificado público normal (Let's Encrypt, etc.): en vez de eso se genera
una Autoridad Certificadora (CA) propia, una sola vez, que después se
instala en cada celular.

**1. Generar el certificado** (una sola vez; repetir solo si cambia la IP
de este equipo, por ejemplo si el router se la reasigna):

```powershell
cd backend
./venv/Scripts/python.exe generar_certificado_https.py
```

**2. Arrancar el servidor HTTPS** (queda en el puerto 8443, aparte del
puerto 8000 de siempre — no reemplaza nada, ambos pueden correr a la vez):

```powershell
./iniciar_https.ps1
```

**3. Instalar el certificado en cada celular** (una sola vez por celular).
Desde el navegador del celular, conectado al wifi del colegio, entrar a
`http://<IP-de-este-PC>:8000/static/ca.crt` (por HTTP normal, sin "s" —
todavía no hay nada que confiar) y descargar el archivo:

- **iPhone (Safari):** al abrir el enlace aparece "Perfil descargado" →
  Ajustes → General → VPN y gestión de dispositivos → tocar el perfil →
  Instalar. Después ir a Ajustes → General → Información → Ajustes de
  confianza de certificados y activar la confianza total para
  "IETABA Local CA" (este segundo paso es obligatorio en iOS, si se
  omite Safari sigue sin confiar en el certificado).
- **Android (Chrome):** al descargar el archivo, Android pide un nombre y
  el uso ("VPN y aplicaciones" o "Wi-Fi") — cualquiera sirve. Si no
  aparece el diálogo automáticamente: Ajustes → Seguridad → Más ajustes de
  seguridad → Cifrado y credenciales → Instalar un certificado →
  Certificado de CA, y seleccionar el archivo descargado.

**4. Usar el escáner:** entrar en el celular a `https://<IP-de-este-PC>:8443`
(con "s"). Debe verse el candado sin advertencias — desde ahí "Escanear
documento" ya puede usar la cámara.

**5. Computadores de la red (modo sin conexión):** en cada PC, entrar una
vez a `http://<IP-de-este-PC>:8000`, iniciar sesión, abrir **Usar sin wifi**
y tocar **Instalar en este computador** (descarga `/instalar-pc.cmd`). Ese
archivo instala el certificado del colegio para el usuario de Windows (sin
Administrador; Windows pregunta si confía en "IETABA Local CA": Sí) y deja en
el escritorio el acceso directo **IETABA** a `https://<IP>:8443`. Desde ese
acceso el PC funciona sin conexión igual que el celular (Chrome y Edge; en
Firefox hay que activar `security.enterprise_roots.enabled`).

### Qué funciona sin conexión

No hay hosting: el PC servidor tiene la base de datos y los demás
dispositivos trabajan con su copia y se sincronizan al volver a la red.

- **Ver**: lo último que se abrió en ese dispositivo, más lo descargado con
  "Usar sin wifi" → Descargar.
- **Guardar**: cualquier cambio hecho sin red (asistencia, observaciones,
  ficha, notas…) queda en una cola del dispositivo y se envía solo, en
  orden, al volver la conexión con la app abierta. Cada envío lleva
  `X-Id-Operacion` y el servidor recuerda la respuesta
  (`app/operaciones_cliente.py`, tabla `operaciones_cliente`), así que un
  reenvío nunca se ejecuta dos veces. Si el servidor rechaza un cambio (por
  ejemplo, alguien más ya lo modificó), queda marcado en "Usar sin wifi" para
  reintentarlo o descartarlo.
- **No** funciona sin conexión lo que depende del servidor en el momento:
  generar constancias/PDF, importar archivos o la automatización con SAPRED.
- Pruebas: `./venv/Scripts/python.exe probar_operaciones_cliente.py`.

Si el equipo cambia de IP, repite solo el paso 1 (la CA no cambia, los
celulares no necesitan reinstalar nada) y vuelve a arrancar el paso 2.
Para no tener que repetir esto nunca, pídele al encargado de la red del
colegio una IP fija (reserva DHCP) para este equipo.

## Estructura del proyecto

```
backend/
  app/
    main.py                Arranque de la app y montaje del frontend
    migraciones.py          Migraciones idempotentes que corren en cada arranque (columnas,
                              claves foráneas rotas, índices, datos semilla); respaldo .bak_* automático
                              antes de recrear una tabla
    fechas.py               Única fuente de "hoy"/"ahora" en hora de Colombia (America/Bogota)
    database.py             Conexión a la base de datos (SQLite: WAL, busy_timeout, foreign_keys=ON)
    models.py                Tablas: Sede, Estudiante, FotoEstudiante, Asistencia,
                              Docente, Area, ..., BloqueHorario, AusenciaDocente, Reemplazo
    horario.py                Lógica de Horarios (consulta, disponibilidad, ausencias, reemplazos)
    schemas.py                Esquemas de entrada/salida (Pydantic)
    crud.py                    Operaciones sobre la base de datos
    certificados.py             Genera las constancias (.docx) a partir de la plantilla
    generacion_boletines.py    Une los boletines PDF por grado en un archivo por sede (PyMuPDF)
    routers/                   Endpoints agrupados por tema (incluye fotos, certificados)
  plantillas/
    constancia_estudio.docx   Copia fiel del formato oficial de constancia
  uploads/fotos/{id}/          Fotos subidas por estudiante (no versionar)
  certs/                        CA local + certificado HTTPS (se genera con
                                 generar_certificado_https.py) — NO compartir
                                 ca-key.pem ni server-key.pem, son privados
    importador_sapred.py      Lee el PDF "Consolidado de Asignaturas por periodo"
    importador_boletin.py     Lee el PDF "Boletín informativo" (conceptos/observaciones/profesor por materia)
  importar_matricula.py       Importa el Excel oficial de matrícula
  importar_horario.py         Importa el horario de la Sede #01 (Word + Excel de la carpeta VD) a BloqueHorario
  probar_horario.py           Prueba manual del módulo Horarios
  probar_boletin.py            Prueba manual del lector del "Boletín informativo"
  colegio.db                    Base de datos SQLite (se genera al importar)
frontend/
  index.html
  static/js/                  Una vista por archivo (core.js + estudiantes/boletines/horario/…)
  static/style.css
```

## Siguiente paso

Confirmar con el colegio el tema de estados de retiro/traslado, y exportar la
rejilla de Horarios en PDF con el formato oficial.
