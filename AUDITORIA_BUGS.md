# Auditoría de bugs — 29 de octubre de 2026

## Estado tras las correcciones

Los nueve hallazgos de esta auditoría tienen correcciones implementadas. Se añadieron
pruebas de regresión en `tests/test_security_regressions.py` y pruebas del cliente
macOS. La descripción y las referencias de líneas que siguen corresponden a la
versión auditada, antes de corregirla.

Cambios de comportamiento intencionales:

- Los cambios de correo quedan pendientes hasta verificar la dirección nueva.
- La recuperación de contraseña cierra sesiones anteriores, invalida enlaces de
  recuperación y cancela cambios de correo pendientes.
- Retirar un proyecto del equipo lo devuelve a su propietario original y desconecta
  las referencias activas de los miembros; no elimina los archivos del proyecto.
- Las carpetas padre e hijas no sirven para eludir permisos. La vista previa solo
  sirve recursos públicos y excluye archivos privados.
- Los bloqueos de operaciones ahora funcionan entre procesos del servidor.
- Los reenvíos fallidos conservan los enlaces de verificación anteriores.
- El cliente macOS conserva el estado de verificación pendiente cuando recibe HTTP 403.
- Los campos de empresa pueden vaciarse. Compartir por ruta un proyecto personal ya
  existente reutiliza su registro, evitando un error de unicidad.

La migración se comprobó sobre una copia de la base local: conservó los recuentos
de registros de las 33 tablas y pasó `PRAGMA integrity_check`. Las nuevas columnas
son aditivas; las sesiones previas se mantienen hasta un cambio de credenciales.

Validación final: 226 pruebas Python en 19 módulos y 2 pruebas macOS pasaron. El
cliente macOS compiló correctamente. El servidor local se reinició y respondió
HTTP 200 en acceso y registro, HTTP 401 en APIs privadas sin sesión y HTTP 404
ante una solicitud no autorizada de `.env` por vista previa. Después del reinicio
se verificó la integridad de la base real y que sus 33 tablas conservaran el número
de registros. Respaldo previo: `backups/before-security-fixes-20261029-1224.db`.

Las pruebas de integraciones usan simulaciones; no se enviaron correos reales ni
se realizaron publicaciones o despliegues externos durante esta corrección. El
cliente nativo se compiló para validación; no se reemplazó una aplicación instalada.

Comprobaciones reproducibles:

```sh
env/bin/python scripts/run-tests.py
cd macos-native/ONEBoardNative
swift test
```

El ejecutor Python separa los módulos para evitar el problema de importaciones
compartidas y elimina las credenciales reales del entorno de pruebas.

Se identificaron nueve hallazgos: ocho reproducidos mediante pruebas adicionales con SQLite, cuentas y archivos temporales, y uno confirmado por inspección del flujo de la aplicación macOS. No se modificó el código de la aplicación durante esta auditoría ni se utilizaron datos reales para las reproducciones.

## Validación y alcance

- Pasaron 206 pruebas existentes, distribuidas en 18 módulos y ejecutadas en procesos separados.
- La suite requiere aislar las variables de SMTP, Google y directorios del entorno real. Una primera ejecución falló en `test_suggested_uris_include_localhost_alternate` porque `.env` aporta `GOOGLE_REDIRECT_URI`. Al aislar esa configuración, pasó. La carga centralizada de `.env` añadida en la corrección anterior hace visible esta dependencia del entorno en las pruebas.
- La ejecución conjunta en un solo proceso tiene una limitación ya documentada en `TEST_READINESS.md`: los módulos comparten `app` aunque cambian el directorio temporal de la base de datos.
- Se revisaron autenticación, equipos, permisos de archivos, vista previa, recuperación de acceso, concurrencia, calendario, respaldos, publicación y cliente nativo.
- No se probaron envíos reales, despliegues SSH, publicaciones en Buffer, respuestas reales de IA ni interacciones visuales de macOS. Los resultados no certifican ausencia de otros errores.
- Script de reproducción utilizado: `/tmp/oneboard-audit-20261029.py`. Crea y elimina exclusivamente sus datos ficticios. No envía mensajes ni llama a integraciones externas.

## 1. Crítico: eludir permisos de equipo mediante rutas padre o hijas

Código: `app.py:8066` (`find_team_projects_by_path`), `app.py:8102` (`require_project_permission`), `app.py:8171` (`connect_site_project`).

La pertenencia a un equipo se comprueba comparando exactamente la ruta de la carpeta. Una subcarpeta o carpeta padre del proyecto no coincide y se interpreta como carpeta personal, sin aplicar los permisos del equipo.

Reproducción: un lector intenta borrar `subdir/dummy.txt` desde el proyecto y recibe HTTP 403. Conecta `proyecto/subdir` como carpeta y borra `dummy.txt`: ambas peticiones devuelven HTTP 200. Un usuario ajeno al equipo también puede conectar la carpeta padre y leer `site/private.txt` con HTTP 200.

Impacto: lectura y modificación de archivos compartidos sin los permisos previstos. No requiere conocer contraseñas ajenas; sí disponer de una cuenta y conocer o encontrar la ruta.

Corrección propuesta: autorización por proyecto y rutas canónicas, comprobando también ancestros y descendientes; impedir que conectar otra ruta amplíe permisos sobre archivos ya protegidos. Definir raíces permitidas por usuario para las carpetas personales.

## 2. Crítico: aceptar invitaciones usando un correo sin verificar

Código: `app.py:5174`, `app.py:5220`, `app.py:5822`, `app.py:7891`, `app.py:7934`.

Cambiar el correo conserva `email_verified=1`. La aceptación de invitaciones compara ese correo con el destinatario. Además, se puede aceptar una invitación por su identificador, sin presentar el token enviado por correo.

Reproducción: se invita a `unclaimed@example.test` como administrador. Otra cuenta verificada cambia su correo a esa dirección utilizando su propia contraseña. La API devuelve `email_verified: true`; aceptar la invitación por ID devuelve HTTP 200 y rol `admin`.

Condición: el correo de destino no debe pertenecer ya a otra cuenta, porque existe una restricción de unicidad. Esto afecta especialmente a invitaciones a usuarios nuevos.

Corrección propuesta: mantener el correo nuevo pendiente hasta verificarlo, ligar los tokens a la dirección concreta y exigir identidad verificada al aceptar invitaciones. Revisar tanto el formulario web como la API.

## 3. Alto: retirar un proyecto puede dar escritura a antiguos lectores

Código: `app.py:8301`, especialmente `app.py:8314`; también `app.py:8102`.

Al retirar un proyecto del equipo se elimina su registro y solo se limpia la carpeta activa del usuario que realiza la acción. Otros miembros conservan su carpeta activa. Al desaparecer el registro compartido, la comprobación de permisos la interpreta como personal.

Reproducción: un lector tiene abierto el proyecto; el propietario lo retira del equipo; el lector borra un archivo de prueba y obtiene HTTP 200.

Corrección propuesta: retirar referencias activas de todos los usuarios afectados y conservar una política explícita de propiedad del directorio. La ausencia de un registro de equipo no debe convertir una carpeta en accesible para cualquiera.

## 4. Alto: el token de vista previa permite descargar archivos privados

Código: `app.py:3240`, `app.py:9156`, `app.py:13692`, `app.py:13722`.

El token permite acceder sin sesión a la vista previa. El servidor entrega cualquier archivo regular resuelto en el proyecto; bloquea `.git` y algunas carpetas internas, pero no `.env`, bases de datos ni otros archivos privados.

Reproducción: una petición sin sesión a `/site-manager/preview/.env` con un token válido devuelve HTTP 200 y el contenido de un `.env` ficticio.

Condición: hace falta poseer un token válido de vista previa, que tiene una duración máxima de una hora. No se afirma acceso anónimo sin token ni exposición demostrada del `.env` real de ONEBoard.

Corrección propuesta: limitar la vista previa a recursos públicos y excluir secretos y archivos internos, de forma coherente con el filtro que ya utiliza el portal de clientes.

## 5. Alto: recuperar la contraseña no revoca sesiones ni otros enlaces de recuperación

Código: `app.py:2255`, `app.py:2391`, `app.py:1990`, `app.py:15631`.

La recuperación cambia el hash y marca únicamente el token usado. Las sesiones se aceptan por `user_id`, sin comprobar una versión de sesión; otros tokens no usados siguen vigentes.

Reproducción: se crean dos enlaces de recuperación y se usa el primero. La sesión anterior sigue respondiendo HTTP 200 en `/api/session`, y el segundo token continúa siendo válido.

Impacto: recuperar una cuenta no expulsa a quien conserve una sesión comprometida; un enlace previo aún puede cambiar otra vez la contraseña.

Corrección propuesta: versionar las sesiones y revocar todos los tokens de recuperación del usuario cuando se completa un cambio de contraseña sensible.

## 6. Alto en despliegues multiproceso: los bloqueos no coordinan workers

Código: `app.py:1887`; despliegue recomendado con varios workers en `DEPLOY_UBUNTU.md:60`.

Los bloqueos usan `threading.RLock` y un diccionario en memoria de cada proceso. No coordinan dos workers de Gunicorn.

Reproducción: manteniendo adquirido el bloqueo del usuario y su directorio en un proceso, un segundo intérprete importa la aplicación y adquiere los mismos bloqueos sin error.

Impacto potencial: ediciones, restauraciones o publicaciones simultáneas sobre el mismo proyecto pueden interferir o sobrescribirse. Se reprodujo la ausencia de exclusión mutua; no se provocó corrupción de archivos reales. El servidor local actual usa un solo proceso, por lo que esta condición corresponde al despliegue multiproceso.

Corrección propuesta: bloqueo compartido entre procesos, mediante archivos de bloqueo o un mecanismo transaccional adecuado, cubriendo también los cambios de proyecto durante una operación.

## 7. Medio: un reenvío fallido invalida el enlace de verificación anterior

Código: `app.py:15665`, `app.py:15723`.

Antes de intentar el envío SMTP se eliminan los tokens anteriores. Si el envío falla, el enlace que el usuario ya recibió deja de funcionar y el nuevo no le llega.

Reproducción: se crea un token válido, se simula un fallo SMTP al reenviar y se intenta consumir el token anterior. El resultado es inválido.

Corrección propuesta: conservar los enlaces vigentes hasta garantizar la creación y entrega del reemplazo, o permitir varios tokens válidos y revocarlos al verificar la cuenta. Evitar que una solicitud de reenvío bloquee la verificación ya iniciada.

## 8. Medio: el cliente macOS pierde el estado de verificación en un login rechazado

Código: `macos-native/ONEBoardNative/Sources/ONEBoardNative/ONEBoardAPI.swift:506` y `macos-native/ONEBoardNative/Sources/ONEBoardNative/ONEBoardNativeApp.swift:353`.

El servidor devuelve HTTP 403 con `verification_required: true` cuando la cuenta no está verificada. El cliente lanza una excepción por el 403 antes de devolver el JSON. Por eso la vista no llega a activar `verificationPending`, que muestra la opción de reenvío.

Caso: una cuenta pendiente intenta iniciar sesión tras abrir de nuevo la aplicación. Aparece el error, pero el flujo de verificación no se activa como después de un registro exitoso.

Estado de evidencia: confirmado por inspección del flujo servidor → cliente → vista; no se ejecutó la interfaz nativa.

Corrección propuesta: preservar el estado estructurado de verificación en el error de autenticación y procesarlo en la vista.

## 9. Medio: la API no permite vaciar campos de empresa

Código: `app.py:5179`.

La expresión `nuevo_valor or valor_anterior` interpreta una cadena vacía como ausencia de actualización.

Reproducción: guardar `company_name="Example"` y luego enviar `company_name=""` devuelve HTTP 200, pero el nombre sigue siendo `Example`. El mismo patrón afecta al correo y sitio web de empresa.

Corrección propuesta: distinguir entre una clave ausente y una clave presente con valor vacío.

## Orden sugerido

Resolver primero los hallazgos 1, 2 y 3, por su impacto directo en acceso entre usuarios. Después abordar exposición de archivos y recuperación de cuentas, y el bloqueo entre procesos antes de utilizar varios workers. Añadir pruebas de regresión para cada caso: las 206 pruebas existentes pasan sin detectar estos escenarios.
