# ONEBoard para macOS con Flutter

## Revisión de equivalencia y servidor compartido (2026-10-30)

La app inicia ahora contra **https://museboard.theroberts.io**, elegido por el
usuario. En la pantalla de acceso se puede cambiar el servidor o seleccionar
“Use this Mac” para usar el helper local. La elección se conserva en macOS;
las cookies de sesión no se transfieren entre conexiones y la caché se separa
por servidor. Inicia sesión con la cuenta que utilizas en esa web.

En modo compartido, archivos, proyectos y comandos corresponden al servidor.
El selector permite abrir proyectos ya registrados o indicar una ruta del
servidor. No se envían rutas del selector local de Finder ni se migran proyectos
locales automáticamente. Los enlaces de clientes se generan en el servidor
compartido. La comprobación pública de `/api/session` pasó; los recorridos con
una cuenta autenticada y las integraciones externas siguen pendientes.

Cambios: calendario mensual y edición completa precargada, conservación de
fechas en actualizaciones parciales, edición de alertas, campos completos de
marca, cambio rápido de proyectos, preparación de reparación de seguridad y
verificación/reset dentro de la app mediante el enlace recibido.

El servidor desplegado aún no incluye el nuevo endpoint de reparación; el
cliente usa la API de inteligencia para su análisis actual. Reparar análisis
históricos requiere actualizar el backend del servidor. Los cambios Python
están incluidos en el helper local, no desplegados automáticamente en producción.

Validación: análisis Flutter sin incidencias; 47 pruebas generales más una
regresión adicional de compatibilidad con servidor antiguo; 19/19 módulos del
backend. Se genera una app Debug con helper incluido y firma local, no una
distribución notarizada.

La auditoría actual y los límites pendientes están en
[`docs/FUNCTIONAL_PARITY_AUDIT.md`](docs/FUNCTIONAL_PARITY_AUDIT.md).

Las secciones siguientes documentan también el modo local y el historial.

La interfaz principal es Flutter, con el diseño de escritorio inspirado en la
referencia de OneBoard: tipografía del sistema, barra lateral clara, superficies
suaves y tarjetas azules, violetas y verdes. El arranque muestra esa interfaz;
no sustituye las pantallas por la web dentro de WebKit.

La aplicación empaqueta el servicio Python y los recursos de la aplicación web.
Flutter reutiliza su API local para ejecutar las funciones existentes. El servicio
escucha únicamente en `127.0.0.1`, utiliza un token aleatorio por ejecución y guarda
sus datos en `~/Library/Application Support/ONEBoard`. No depende de la instancia
del servidor personal. Empaquetar el servicio no implica cambiar el diseño.

Los enlaces de verificación apuntan al helper local; abre el correo en este Mac
y deja ONEBoard abierto hasta completar la verificación.

## Abrir y ejecutar en Xcode

```bash
cd oneboard_MacOS
flutter pub get
open macos/Runner.xcworkspace
```

Para ejecutar desde Flutter durante el desarrollo, el repo raíz necesita sus
dependencias Python en `.venv` (se pueden instalar con
`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`):

```bash
cd oneboard_MacOS
flutter run -d macos
```

Al distribuir la app, construye y empaqueta el helper privado con:

```bash
./oneboard_MacOS/scripts/build-flutter-macos.sh
```

El resultado es `oneboard_MacOS/build/macos/Build/Products/Release/ONEBoard.app`.
El helper empaquetado incluye el código y recursos de ONEBoard; no copia el
archivo `.env` de desarrollo ni credenciales del repositorio. Los proveedores
externos (correo, Google, Muse y Buffer) requieren sus credenciales en los
ajustes de la app o en la configuración local del usuario.

## Integraciones externas y alcance

El contenedor reutiliza las integraciones de la web, incluyendo Google Search
Console, Buffer y proveedores de IA. Sus credenciales deben configurarse; el
empaquetado nunca copia `.env` ni claves privadas del repositorio. Google OAuth
requiere registrar el callback local mostrado en Settings.

Flutter conserva la integración de Firebase, incluidos los flujos de sesión y
carga de imágenes a Storage cuando está configurado. Las operaciones del servicio
siguen usando SQLite local; no hay migración automática a Firestore. Buffer
necesita una URL HTTPS pública para acceder a las imágenes; una URL loopback
no sirve. Los enlaces públicos y la colaboración entre equipos también requieren
un servicio compartido independiente del servidor personal.

Push requiere configurar Firebase, APNs y firma Apple. Compilar el contenedor
no valida estas integraciones ni implica que funcionen sin esa configuración.

## Organización

Esta carpeta contiene la aplicación Flutter de macOS, el proyecto Xcode (`macos/`),
las pruebas (`test/`), las reglas Firebase y su script de empaquetado (`scripts/`).
La vista del diseño está en `docs/design-preview.png`.

El servicio Python sigue compartido con el resto del repositorio en la carpeta
superior (`oneboard_native_service.py`, `app.py`, `templates/`, `static/` y
`requirements.txt`). La app encuentra ese servicio durante desarrollo y el script
de distribución lo incorpora al paquete `.app`. Esta carpeta de código fuente
por sí sola todavía no constituye un proyecto independiente del repositorio.

## Compilación de desarrollo con servicio incluido

```bash
ONEBOARD_BUILD_MODE=debug bash scripts/build-flutter-macos.sh
```

Genera `build/macos/Build/Products/Debug/ONEBoard.app` con el helper dentro de
`Contents/Resources/service/ONEBoardService`. La firma es local, no notarizada
para distribución pública.

## Estado: Studio, Preview y formularios (2026-10-29)

Hecho en la app Flutter, sin cambiar el diseño (`apple_design.dart`,
`workspace_chrome.dart`, `workspace_dashboard.dart` intactos):

- Studio: abrir archivos (texto con fuente monoespaciada, imágenes, HTML como
  código con salto a Preview), resultados de terminal/IA en tarjetas
  dedicadas, refresco conservando la carpeta actual, acciones contextuales por
  archivo y secciones de backups y updates con acciones directas.
- Preview: página renderizada real (WebView con cookies de sesión), selector
  visual de elementos, aplicar cambios con el asistente, tamaños
  desktop/tablet/mobile y comparación antes/después por update.
- Formularios: controles nativos por tipo (fecha, mes, desplegables, booleanos,
  enteros, listas) en vez de JSON libre, desplegables de IDs desde los datos
  visibles y subformulario para objetos anidados. Corregidos valores inválidos:
  `kind: promotion` → `promo` en calendario y `auth_method: ssh_key` → `key`
  en remoto.
- Nuevos archivos: `lib/board_api.dart`, `lib/studio_file_view.dart`,
  `lib/studio_terminal_view.dart`, `lib/preview_panel.dart`;
  tests en `test/studio_panels_test.dart` (21 tests en verde).

Requisitos externos pendientes de validar con cuentas reales:

- Google Search Console: registrar en Google Cloud Console la URI
  `http://127.0.0.1:51249/api/google-search-console/callback` y probar OAuth
  con una cuenta real.
- Firebase/APNs: pendiente configurar APNs para macOS y probar recepción y
  apertura de notificaciones. Sin backend público no hay colaboración real
  entre Macs (los enlaces loopback no sirven fuera del equipo).
- Buffer: falta compositor visual con canales e imagen; no se ha publicado nada
  real en pruebas.
- Compilación: el Flutter de Homebrew (`/opt/homebrew/share/flutter`) no es
  escribible por este usuario; se compiló con una copia en `/tmp/flutter-sdk`.
  Para compilar con el Flutter del sistema: darle propiedad al usuario actual.

## Estado: Buffer, Settings, operativas, Teams, notificaciones (2026-10-30)

- Social/Buffer: canales con selección múltiple, compositor (texto, tipo,
  borrador/cola/publicación con confirmación), generación IA hacia el
  compositor, imagen desde el Mac con URL HTTPS de Firebase Storage y aviso.
  Sin publicar nada real en pruebas.
- Settings: perfil y empresa pre-rellenados, cambio de contraseña, avatar y
  logo, clave de Buffer, claves de Muse/Anthropic/OpenRouter/Google AI (solo
  se envían las rellenas), proveedor por defecto y URI de Google con copia.
- Site Health: tarjetas por hallazgo (severidad, detalle, propuesta) con
  Apply/Ignore/Reopen y acciones Scan/Fix-all/IA; ignored en sección propia.
- Requests: vista de hilo (contexto, adjuntos con descarga, conversación,
  comentar, estado, borrar). Calendar/Contacts/Alerts/Reports/Security/
  Notifications: botones de acción por registro con IDs pre-rellenados.
- Resultados: enlaces generados (http/https) se listan con botón Open.
- Teams: lista, invitaciones pendientes con aceptar, detalle (miembros y
  roles, revocar invitaciones, proyectos, invitar, transferir con desplegable,
  salir, borrar). Añadidas al catálogo: revocar invitación y aceptar por ID.
- Notificaciones: al abrir una push se navega a la sección indicada
  (`message.data['section']`), incluyendo arranque en frío. Push real NO
  verificado: requiere cuenta de desarrollador Apple (cero identidades de
  firma en este equipo), capability Push + `aps-environment` (revertido porque
  rompe la firma ad-hoc) y clave APNs en Firebase.
- Auth: textos de registro/reset indican mantener la app abierta y volver a
  entrar; Settings muestra verificación pendiente y reenvío.
- Firebase/colaboración: sin cambios; no hay backend compartido ni sync
  completa. No prometer colaboración entre Macs.
- 38 tests en verde (`test/studio_panels_test.dart`,
  `test/ops_panels_test.dart`, `test/workspace_design_test.dart`).

## Nota: fix de Preview “opaque is not implemented on macOS” (2026-10-30)

El WebView de macOS (`webview_flutter_wkwebview`) no implementa
`setBackgroundColor`/`setOpaque`; llamarlo rompía el arranque del Preview con
`UnimplementedError`. El código actual ya no usa esa API (el fondo nativo es
blanco por defecto). Si ves ese error, estás ejecutando una compilación
anterior al fix: reconstruye con `scripts/build-flutter-macos.sh` (limpia
`build/` si el binario Dart queda obsoleto) y abre el `.app` generado en
`build/macos/Build/Products/Release/`.

## Estado: local-only, solo Muse, paridad total (2026-10-30)

- Local-only: eliminada la conexión a servidores compartidos/personales
  (Dart + Swift). La app solo habla con el servicio incluido en 127.0.0.1.
- Directorios 100% visuales: conectar carpeta, compartir carpeta de equipo y
  clave SSH usan el selector nativo; borrar archivo ofrece desplegable con los
  archivos de la carpeta actual. Nada de paths escritos a mano.
- Solo Muse: eliminados Anthropic/OpenRouter/Google AI de la interfaz
  (credenciales, desplegable de proveedor, lista de proveedores). `ai-policy`
  siempre envía `provider: muse`.
- Paridad web: 99/104 rutas API referenciadas literalmente. Las 5 restantes
  están cubiertas: `reports/:link_id` se llama como `:report_id` (misma ruta
  Flask), `browse-directory` se sustituye por el selector nativo superior,
  el callback OAuth lo abre el navegador, y `ai/providers` se retiró por
  diseño (solo Muse). Añadidos: galería de
  imágenes del sitio, actividad del asistente + prompts rápidos, estado
  remoto/SSH, insignia de equipo, miniaturas de avatar/logo y bloque de
  código de inserción.
- Backend verificado: suite Python 19/19 módulos en verde. Flutter: 52/52.
- Límites honestos: OAuth de Google, publicación real en Buffer y push con
  APNs requieren cuentas/servicios reales y debe validarlos el propietario;
  los enlaces públicos loopback solo abren en el propio Mac.

## Estado: Site & Brand visual (2026-10-30)

- Nueva vista dedicada (sección 3): identidad pre-rellenada, formulario
  completo de marca (10 textos, 3 colores, 2 fuentes), logo visible con
  subir/reemplazar desde el Mac, y librería de imágenes con miniaturas,
  prompt, fecha y descarga a `~/Downloads`.
- Flujo probado de extremo a extremo contra el servicio empaquetado (login,
  conexión, subida de logo multipart, bytes PNG, guardado de marca,
  forma de la librería): 8/8.
- Flutter: 55/55 tests en verde, `dart analyze` limpio.

## Corrección del editor visual (2026-10-30)

Se reprodujo `UnimplementedError: opaque is not implemented on macOS` en una
prueba real de WebKit. La causa era `WebViewController.setBackgroundColor`,
que utiliza una propiedad de UIKit no implementada por el plugin en macOS.
Se retiró del preview y de los visores de comparación; se usa el fondo nativo.

El arranque espera la configuración del canal JavaScript y del delegado. La
selección sigue la URL de la página realmente cargada, se limita a páginas del
proyecto y se vuelve a enviar antes de ejecutar el asistente. Tras el cambio,
el preview recarga la página y permanece abierto; un fallo de IA conserva la
instrucción y muestra el error.

Validación: `flutter test integration_test/preview_test.dart -d macos` verifica
WebKit real, cookies, navegación a otra página, selección del encabezado,
payload al asistente y recarga del contenido. La respuesta de IA y la API se
simulan; no modifica sitios ni consume créditos. La misma prueba reprodujo el
error de arranque antes de la corrección. Las pruebas unitarias y de widgets
también pasan.
