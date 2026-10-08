# Dependencias de terceros en `frontend/static/vendor/`

Alojadas localmente (no en un CDN) porque la app corre sin internet, en la
red del colegio. Se cargan solo cuando se abre el escáner documental
(`static/js/scanner.js`), nunca en la carga inicial de la página.

## opencv.js

- **Qué hace aquí:** detección de contorno del documento (Canny +
  findContours + approxPolyDP), corrección de perspectiva
  (getPerspectiveTransform/warpPerspective) y mejora de imagen (CLAHE,
  adaptiveThreshold) — ver `static/js/scanner.js`.
- **Origen:** build oficial `https://docs.opencv.org/4.x/opencv.js` (OpenCV 4.x).
- **Licencia:** Apache License 2.0 (OpenCV se relicenció de BSD-3-Clause a
  Apache 2.0 a partir de la versión 4.5). Uso comercial/administrativo
  permitido sin restricciones ni royalties.
- **Tamaño:** ~11 MB (incluye el binario WebAssembly embebido en base64 —
  es un único archivo, no requiere descargar nada más en tiempo de
  ejecución).

## jsPDF

- **Qué hace aquí:** ensambla las páginas ya procesadas (imágenes JPEG) en
  un único PDF — ver `generarPdf()` en `static/js/scanner.js`.
- **Origen:** build UMD oficial del proyecto `https://github.com/parallax/jsPDF`.
- **Licencia:** MIT. Uso comercial/administrativo permitido sin
  restricciones ni royalties.
- **Tamaño:** ~420 KB.

## PDF.js

- **Qué hace aquí:** lee un PDF ya existente que el usuario sube (subida
  masiva de documentos) y renderiza cada página como miniatura para poder
  elegir cuáles usar y a qué categoría asignar cada una — ver
  `paginasDePdfComoMiniaturas()` / `renderizarPaginaPdfAImagen()` en
  `static/js/ficha.js`. Es lo contrario del escáner (que genera un PDF
  nuevo con jsPDF): esto *lee* uno que ya existe.
- **Origen:** build oficial `pdfjs-dist@4.9.155` (Mozilla), módulos ES
  (`pdf.min.mjs` + `pdf.worker.min.mjs`), cargados con `import()` dinámico
  solo cuando el usuario sube un PDF — nunca en la carga inicial.
- **Licencia:** Apache License 2.0 (Mozilla Foundation). Uso
  comercial/administrativo permitido sin restricciones ni royalties.
- **Tamaño:** ~350 KB (pdf.min.mjs) + ~1.3 MB (pdf.worker.min.mjs, corre en
  un Web Worker aparte — no bloquea la interfaz mientras procesa).

## Por qué no se usaron alternativas comerciales o SaaS

Ambas resuelven todo el pipeline (visión por computadora y generación de
PDF) sin depender de un servicio externo de pago ni enviar documentos de
estudiantes fuera del navegador del usuario — requisito explícito del
sistema (los documentos son de menores de edad).

## lucide.min.js

- Lucide v0.469.0 (https://lucide.dev), licencia ISC. Íconos de línea usados en toda la interfaz en vez de emojis (ver `icono()` en js/comun.js).
- Descargado de https://cdn.jsdelivr.net/npm/lucide@0.469.0/dist/umd/lucide.min.js — vendorizado para que la app funcione sin internet en la red del colegio.
