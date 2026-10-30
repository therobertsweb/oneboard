# Revisión actual de equivalencia — 2026-10-30

Fuente: `app.py`, `templates/` y cliente Flutter `oneboard_MacOS/` de este repositorio.
La implementación SwiftUI de `macos-native/` no recibió estas modificaciones.

## Resultado actual

Se corrigieron diferencias funcionales locales, pero **no se certifica paridad total ni superioridad global**.
Las pruebas automatizadas no sustituyen los recorridos con cuentas reales y un servicio compartido.
La auditoría de 2026-10-29 que aparece debajo es histórica: varios de sus bloqueos ya estaban corregidos antes de esta revisión.

## Cambios de esta revisión

- Calendario mensual con navegación, selección de fecha, eventos de varios días y filtro para ver todos.
- Crear eventos usa la fecha seleccionada; editar permite tipo, título, descripción, página y ambas fechas, precargadas. La fecha final es opcional.
- Corregido backend: actualizar solo el título ya no sustituye la fecha inicial por hoy ni borra la fecha final. Vaciar explícitamente la fecha final sigue permitido.
- Editar monitores precarga nombre, activación y umbral; convierte correctamente el booleano SQLite.
- Site & Brand precarga datos guardados y expone dirección, colores y tipografías como campos individuales, conservando su estructura JSON interna.
- Studio permite cambiar directamente entre proyectos guardados y compartidos autorizados. La sugerencia de terminal cita el nombre de archivo para evitar interpretación del shell.
- Seguridad muestra el historial que antes quedaba anidado en la respuesta. “Prepare repair” obtiene el mismo prompt que la web y abre el asistente para revisión antes de ejecutar. El backend exige permiso de edición y vinculación con el proyecto activo.
- Verificación de email y restablecimiento de contraseña tienen diálogo propio para pegar el enlace recibido; el token se extrae localmente, sin navegar al dominio pegado.
- Los reportes nuevos usan el mes actual en lugar de octubre de 2026 fijo.

## Funciones existentes revisadas

| Área | Estado observado en el código actual |
|---|---|
| Dashboard / Search Console | Panel propio, selección de propiedad y oportunidades SEO; requiere validar OAuth real |
| Studio / Preview | Archivos, terminal, backups, actualizaciones, selector visual y comparaciones |
| Salud | Hallazgos y acciones Apply/Ignore/Reopen; backend cubierto por pruebas |
| Solicitudes / contactos | Hilos, adjuntos y acciones por registro; acceso externo depende de servidor público |
| Alertas / reportes | Colecciones visibles y acciones contextuales; edición mejorada en esta revisión |
| Social / Buffer | Compositor, canales, borradores y publicación; no se publicaron posts reales |
| Teams | Miembros, roles, invitaciones y proyectos; no hay sincronización automática de SQLite entre Macs |
| Ajustes | Perfil, empresa, proveedores IA y Buffer; persistencia backend ya corregida antes de esta revisión |
| Notificaciones | Lectura y navegación; entrega APNs real pendiente |

## Límites pendientes

1. El usuario eligió `https://museboard.theroberts.io`. Se añadió selección persistente de servidor HTTPS, configurado como predeterminado, con modo local opcional. Se comprobó `/api/session`: HTTP 401 y JSON válido de sesión no autenticada. La validación con cuenta y proyectos reales sigue pendiente. En modo servidor las rutas y comandos corresponden al servidor; no se migran proyectos locales.
2. El servidor desplegado responde 404 al nuevo endpoint `/api/security-scan/1/repair`. Se añadió compatibilidad con el análisis actual del proyecto mediante `/api/site-manager/intelligence`; los análisis antiguos requieren desplegar el backend actualizado. Las correcciones Python de esta revisión están empaquetadas localmente, no desplegadas en el servidor.
3. Google, Buffer, proveedores IA, Firebase Storage y APNs necesitan pruebas de extremo a extremo con cuentas y configuración válidas; no se enviaron correos ni se publicaron contenidos reales como parte de esta revisión.
4. La galería de imágenes y algunos resultados siguen usando vistas genéricas; no se afirma una experiencia visual superior en todos los módulos.
5. La compilación de desarrollo no equivale a una distribución notarizada ni valida por sí sola el helper empaquetado.

## Validación

- Backend: 19/19 módulos pasan mediante `.build-tools/macos-packager/bin/python scripts/run-tests.py`, con credenciales externas neutralizadas.
- Flutter: análisis sin incidencias y batería de widgets/helpers. Incluye regresiones de fechas, precarga, calendario y enlaces de autenticación.
- Los resultados de compilación se registran en el README tras finalizar la validación.

---

# Auditoría histórica (2026-10-29; no describe el estado actual completo)

# Auditoría de equivalencia funcional: web y macOS

Fecha: 2026-10-29. Actualizada contra la versión descargada del servidor en `oneboard 2`.

## Resultado

**La app macOS todavía no ofrece todas las funciones de la web con flujos completos.**
Hay pantallas propias para autenticación, resumen y exploración de carpetas; la mayor parte de los demás módulos se basa en un catálogo de acciones y formularios genéricos. La existencia de una ruta HTTP o un botón no demuestra que el usuario pueda completar la tarea.

Revisión estática del código local: `/Users/hackathon/Desktop/oneboard 2/app.py`, plantillas web y recursos de esa carpeta; archivos Dart, configuración nativa y scripts de `/Users/hackathon/Desktop/oneboard 2/oneboard_MacOS`. No se enviaron correos, publicaciones, invitaciones ni solicitudes de IA. No se verificaron cuentas externas ni la entrega real de push. Esta revisión no sustituye pruebas de extremo a extremo.

## Hallazgos que bloquean flujos

1. **Las credenciales de IA no se guardan en modo nativo.** En `app.py:5303`, `api_settings_ai_credentials` devuelve `ok: true` cuando existe `NATIVE_SERVICE_TOKEN` antes del `UPDATE users`. Flutter envía el formulario, pero no tiene una implementación alternativa de guardado en Keychain. La operación puede aparentar éxito sin persistir la clave. El formulario solo expone Muse; la web admite además Anthropic, OpenRouter y Google.
2. **Buffer no se puede configurar desde la interfaz actual.** `app.py:5198` admite `buffer_api_key` en `/api/settings/account`, y `/api/social/buffer/posts` exige una clave guardada. El formulario macOS solo ofrece nombre y empresa. No hay un campo de Buffer ni un flujo de conexión equivalente al de la web. Las acciones solo podrán aprovechar una configuración que ya exista en la base local.
3. **El dashboard usa campos incorrectos.** `lib/workspace_dashboard.dart:22` busca `gsc.site_url`; las tarjetas buscan `gsc.clicks` y `gsc.impressions`. `app.py:7218` devuelve `selected_site_url` y `stats` como lista de elementos `{label,value}`. Puede mostrar “Not connected” y guiones aunque el servicio entregue estadísticas. Tampoco se representan CTR, posición, consultas, páginas, gráficas ni oportunidades SEO de la web.
4. **No hay vista previa visual del sitio.** La sección Preview consulta inteligencia y permite introducir selector, página e ID manualmente. No hay visor de páginas, selector visual de elementos ni comparación visual antes/después. La web tiene rutas `/site-manager/preview`, comparación de actualizaciones y `static/js/preview-picker.js`.
5. **La app ignora parte de los resultados de Studio.** `_runFeatureAction` guarda la respuesta en `_featureResult`, pero `_sitesView` no la presenta y tampoco actualiza `_sites` con el nuevo `manager`. Tras ejecutar IA, terminal, backup o sincronización, el resultado puede quedar invisible y el listado obsoleto hasta refrescarlo. Los archivos tienen `onTap: null`; solo se puede entrar en carpetas.
6. **Los enlaces compartidos no resuelven la operación entre dispositivos.** Las rutas de solicitudes, reportes y formularios construyen enlaces con `url_for(..., _external=True)`. Al llamar desde la app se generan URLs del servicio loopback. No son accesibles para un cliente desde otro equipo ni para un formulario publicado en Internet. Requieren un servicio público aislado y autorizado, sin exponer el servidor personal completo.
7. **El proyecto fuente aún depende del backend compartido, pero la estructura actual vuelve a ser compatible con la búsqueda por carpeta padre.** La app está ahora en `oneboard 2/oneboard_MacOS`; el script calcula correctamente `oneboard 2` como raíz y allí existen `requirements.txt`, `templates`, `static`, `app.py` y `oneboard_native_service.py`. Se retira el hallazgo anterior de rutas rotas por ser carpetas hermanas. Esto no hace autónoma a la carpeta Flutter ni verifica el arranque de los binarios antiguos: tras moverla deben regenerarse las rutas de compilación y comprobarse las dependencias de Python de macOS. La distribución requiere el helper empaquetado.

## Comparación de la nueva fuente con la auditoría anterior

Se compararon archivos locales por contenido, sin usar fechas como prueba de equivalencia:

- Las 34 plantillas web son idénticas a la copia anterior.
- Los 2 archivos encontrados en `static/` son idénticos.
- `app.py` añade únicamente `current_app.logger.exception("SMTP verification email delivery failed.")` en el manejo de fallos SMTP. Mejora el diagnóstico, pero no cambia los flujos ni las rutas.
- Se repitió el inventario contra la nueva carpeta: 120 combinaciones API y 110 referencias coincidentes desde el cliente. Los hallazgos de credenciales, dashboard, Buffer, Preview y resultados de Studio siguen presentes en el código actual.

La fuente de referencia pasa a ser exclusivamente `oneboard 2`. Las huellas SHA-256 de los archivos auditados y las diferencias con la fuente anterior están en `docs/source-comparison.json`.


## Matriz por módulo

| Módulo | Lo que existe en macOS | Lo que falta para equivalencia |
|---|---|---|
| Registro e inicio de sesión | Formularios y llamadas al servicio local | Verificación y restablecimiento completos dentro de la app; dependencia actual de correo y páginas locales; sincronización consistente entre cuenta local y Firebase |
| Dashboard / Search Console | Solicitud de datos y tarjetas; autorización Google abre navegador | Corregir esquema de datos; tablas, gráficas, CTR, posición, oportunidades SEO y selección guiada de propiedad |
| Studio / proyectos | Selector nativo de carpeta y listado de directorios | Abrir contenido de archivos; selector e historial de proyectos; presentar resultados, actualizaciones, backups y estado remoto |
| IA y SEO | Acciones para instrucciones, contenido, tareas e imágenes | Guardado efectivo de credenciales; selección guiada de proveedor/modelo; conversación, resultados y reuso de imágenes/contenido integrados |
| Preview | Consulta de inteligencia; selección textual y comparación por ID | Render del sitio, selección con ratón, tamaños de vista y comparación visual |
| Site & Brand | Formulario con marca anidada y carga de logo | Edición precargada, campos nativos de marca, galería visual y selección de imágenes |
| Salud del sitio | Endpoints para escanear, resumir, corregir e ignorar | Acciones sobre cada hallazgo, explicaciones y seguimiento del resultado sin copiar IDs |
| Solicitudes | Crear/revocar enlaces, leer conversación, comentar y cambiar estado | Portal accesible externamente, adjuntos, conversación propia y selección de solicitudes |
| Calendario | Crear, actualizar, ejecutar, cancelar y eliminar mediante formularios | Calendario visual, fechas seleccionables, edición completa precargada y acciones por evento |
| Contactos | Listado, snippet, tokens y estados mediante acciones | Formulario externo accesible; vista de mensaje, selección de token y acciones directas |
| Alertas | Reglas, comprobación y estados | Mostrar reglas y alertas simultáneamente; edición completa y acciones por alerta |
| Reportes | Crear, consultar y revocar | Presentación de reporte, apertura/compartición y enlace accesible a destinatarios |
| Social / Buffer | Canales, ideas, texto, carga de imágenes y creación de posts | Configurar clave, seleccionar canales visualmente, compositor, previsualización y traslado del texto generado al post |
| Equipos | CRUD, invitaciones, miembros, proyectos y transferencia mediante formularios | Revocar invitaciones, selección de usuarios/proyectos, permisos claros y coordinación real entre instalaciones |
| Seguridad | Solicitud de escaneo y datos | Flujo de reparación desde un escaneo y presentación guiada de hallazgos equivalente a `/security-scan/<id>/repair` |
| Notificaciones | Listado y marcar leído; receptor Firebase | APNs firmado/configurado, emisor de eventos push y comprobación de recepción; atención al arranque desde una notificación |
| Ajustes | Nombre, empresa, Muse y política IA mediante acciones | Email, cambio de contraseña, avatar, logo de empresa, email/web de empresa, clave Buffer y demás proveedores IA |
| Ayuda | Lista de secciones | Instrucciones y ayuda contextual de los flujos |

“Existe una acción” significa que hay código que intenta invocar el endpoint; no significa que la tarea esté validada con datos reales.

## Problemas transversales

- `_findList` devuelve únicamente la primera lista no vacía de una respuesta. Solicitudes contiene `links` y `requests`; Alertas contiene `rules` y `alerts`. Según el contenido y orden, una colección oculta a la otra en la pantalla principal.
- Las acciones por registro siguen pidiendo IDs manuales. Los campos anidados y las listas todavía requieren JSON; booleanos y fechas se editan como texto. Los valores iniciales son ejemplos, no los datos actuales del registro.
- Firestore almacena perfiles, dispositivos, notificaciones y copias de lectura. Los datos operativos siguen en SQLite local; no existe un motor de sincronización de equipos/proyectos entre los Mac. Tener las acciones de equipos no reproduce por sí solo una base central compartida.
- Firebase se activa mediante `--dart-define`. El script de distribución no pasa estas opciones y no reenvía argumentos. Los entitlements revisados no incluyen APNs. Hay código receptor de mensajes y registro de dispositivos, pero no se identificó un emisor de eventos de ONEBoard hacia FCM en este repositorio.
- El flujo de imagen para Buffer sí contempla subir un archivo elegido a Firebase Storage y usar su URL HTTPS. Requiere proyecto/bucket/cuenta válidos. La URL elegida queda en memoria; el resultado de editar o generar una imagen no se integra automáticamente en ese flujo. No se comprobó una descarga real desde Buffer.
- La cuenta local y Firebase Auth son dos identidades: el inicio de sesión local intenta además iniciar/crear cuenta Firebase y captura errores. Cambios de contraseña o email necesitan reconciliación; actualmente Firebase no es la autoridad única de la sesión.

## Inventario de rutas

El análisis de decoradores de Flask encontró **120 combinaciones de método y ruta API**; el catálogo y las llamadas explícitas Dart hacen referencia a **110** de ellas. Esto **no es un porcentaje de funciones terminadas**: una ruta puede servir múltiples campos o flujos, y callbacks o selectores nativos pueden sustituir rutas de forma válida.

Archivo reproducible de resultados del análisis estático: `docs/api-route-audit.json`. Se normalizaron parámetros de ruta y se excluyeron query strings. La referencia dinámica `/api/site-manager$query` se cubre por la ruta base del catálogo.

Rutas no referenciadas directamente:

- POST `/api/auth/verify-email` y `/api/auth/reset-password`: se depende de páginas del servicio, sin flujo nativo completo.
- GET `/api/google-search-console/callback`: su ausencia como llamada Dart es esperable para el callback del navegador; no constituye por sí sola una función faltante.
- GET `/api/site-manager/browse-directory`: el selector nativo cubre la selección inicial de carpeta.
- GET `/api/site-manager/files/raw` y `/api/site-manager/assets/raw`: no hay lector/visor equivalente integrado.
- POST `/api/seo-suggestions/create`: falta la acción contextual de oportunidad SEO.
- DELETE `/api/teams/<team_id>/invites/<invite_id>`: falta revocar invitaciones.
- POST `/api/teams/invites/<invite_id>/accept`: existe aceptación por token, pero no aceptación contextual por ID.
- GET `/api/settings/ai`: otras llamadas consultan proveedores/política parcialmente; no se considera automáticamente una función independiente faltante.

## Orden recomendado para completar la app

1. Regenerar las rutas de compilación en la ubicación actual y comprobar el empaquetado autónomo del servicio para distribución.
2. Corregir autenticación/configuración y persistencia de credenciales; habilitar Buffer desde la app.
3. Corregir contratos de datos del dashboard y actualización/resultados de Studio.
4. Completar Studio y Preview con contenido y acciones contextuales.
5. Reemplazar formularios genéricos por flujos propios en Social, Calendario, Solicitudes y Equipos.
6. Definir backend compartido para colaboración, enlaces externos y push, separado del servidor personal.
7. Validar los flujos completos con cuentas de prueba y servicios configurados antes de afirmar paridad funcional.
