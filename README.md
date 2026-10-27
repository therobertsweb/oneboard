# ONEBoard

ONEBoard es una aplicación Flask para administrar, revisar y actualizar sitios web con ayuda de IA. Está pensada para optimizar la actualización continua de websites: conectar un directorio del sitio, pedir cambios con Muse, generar imágenes y contenido para el sitio y redes sociales, usar imágenes del cliente, revisar historial/diffs, restaurar cambios, preparar deploy remoto y monitorear seguridad básica.

## Windows 11

Requisitos recomendados:

- Windows 11 actualizado.
- Python 3.11 o superior instalado desde python.org o Microsoft Store.
- Git for Windows.
- OpenSSH Client habilitado si vas a usar conexiones SSH/SFTP.

### Arranque rápido con PowerShell

```powershell
cd C:\path\to\ONEBoard
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\start-windows.ps1
```

### Arranque rápido con CMD

```bat
cd C:\path\to\ONEBoard
scripts\start-windows.bat
```

La app abrirá en el host/puerto definidos en `.env`. Si no configuras nada, usa `http://127.0.0.1:5002`.

## Configuración

1. Copia `.env.example` como `.env`.
2. Ajusta `SECRET_KEY`, `HOST`, `PORT` y, si aplica, credenciales de Google Search Console.
3. Para verificación por email, completa `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` y `SMTP_USE_TLS`. No uses una contraseña expuesta: crea una nueva contraseña de aplicación o credencial SMTP antes de poner la app en producción.
3. Usa una ruta Windows para el sitio:

```env
ONEBOARD_SITE_DIRECTORY=C:\Sites\example.com
```

No guardes tu API key de Muse en `.env`. Cada usuario debe agregar su propia key en `Settings -> API de Muse`. El catálogo de modelos se obtiene dinámico desde la API; al guardar la key se valida y se cachea la lista.

### Google Search Console en macOS

La aplicación nativa requiere un cliente OAuth de tipo **Desktop** en Google
Cloud, no uno de tipo Web. Define sus credenciales en el archivo privado usado
para ejecutar `scripts/build-macos-native.sh`; el build las incorpora en
`ONEBoard.app`:

```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

ONEBoard usa un callback loopback privado en
`http://127.0.0.1:PUERTO/api/google-search-console/callback`; no configures
`GOOGLE_REDIRECT_URI` ni `GOOGLE_NATIVE_REDIRECT_URI` para la aplicación
nativa. Si el consentimiento OAuth sigue en modo *Testing*, agrega cada cuenta
que vaya a conectarse como usuario de prueba. Para permitir cuentas externas
sin esa lista, publica la aplicación y completa los requisitos de verificación
de Google que correspondan al alcance de Search Console.

## Ejecutar en desarrollo

Windows:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

## Producción en Windows

En Windows se usa Waitress porque Gunicorn no soporta Windows.

```powershell
.\.venv\Scripts\python.exe run_waitress.py
```

Para producción real, ejecuta Waitress detrás de IIS, Caddy, Nginx para Windows o un proxy equivalente con HTTPS.

## Crear ONEBoard.exe en Windows 11

El ejecutable se debe construir en Windows. PyInstaller no genera un `.exe` funcional de Windows desde macOS o Linux.

PowerShell:

```powershell
cd C:\path\to\ONEBoard
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\build-windows-exe.ps1
```

CMD:

```bat
cd C:\path\to\ONEBoard
scripts\build-windows-exe.bat
```

El build queda en:

```text
dist\ONEBoard\ONEBoard.exe
```

El icono del `.exe` se genera desde `logo.jpeg`. El script lo convierte a `build-assets\logo.ico` antes de ejecutar PyInstaller.

Si quieres configuración personalizada, coloca un archivo `.env` junto a `ONEBoard.exe`. La base de datos, uploads y backups se guardan junto al ejecutable dentro de `dist\ONEBoard\`.

## Aplicación nativa de macOS

ONEBoard para macOS usa SwiftUI y AppKit como interfaz visible. Se abre como una aplicación normal, con ventana, controles, menús, icono y presencia en el Dock; no abre el dashboard en Safari, Chrome o Firefox. El servicio Flask queda incluido y se ejecuta de forma privada en `127.0.0.1`.

Requisitos para construirla:

- Mac con Apple Silicon.
- macOS 14 o posterior.
- Xcode completo en `/Applications/Xcode.app`.
- Python 3 disponible. La primera compilación instala PyInstaller y las dependencias de empaquetado en `.build-tools/`.

```bash
scripts/build-macos-dmg.sh
```

El comando anterior delega al nuevo build nativo `scripts/build-macos-native.sh` y genera:

```text
dist/native-macos-YYYYMMDD-HHMMSS/ONEBoard.app
dist/ONEBoard-Native-YYYYMMDD-HHMMSS.dmg
```

Los datos, la base SQLite, los uploads y el log del servicio se guardan fuera de la app:

```text
~/Library/Application Support/ONEBoard
```

Para configurar variables privadas de un solo usuario, copia `.env.example` como `.env` dentro de ese directorio. La app genera además una `SECRET_KEY` persistente y privada la primera vez que se abre.

### Email incluido en la distribución de macOS

El build nativo incorpora las credenciales requeridas para distribución dentro
de `ONEBoard.app`: todas las variables `SMTP_*`, `GOOGLE_CLIENT_ID` y
`GOOGLE_CLIENT_SECRET`. Por tanto, las sesiones Guest y Standard no requieren
un archivo `.env` después de instalar el DMG. Por defecto el build toma esas
variables de `ONEBoard/.env`; para usar un archivo privado distinto:

```bash
ONEBOARD_NATIVE_SMTP_ENV_FILE=/ruta/privada/smtp.env \
scripts/build-macos-native.sh
```

El archivo fuente no se copia al paquete. `SECRET_KEY` se genera por
instalación y el servicio nativo establece su propio host, puerto y callback
local de Google; por eso no se incluyen. Quien tenga acceso a la app
distribuida podría extraer las credenciales incorporadas, así que usa una
cuenta SMTP y un cliente OAuth dedicados y con permisos mínimos. Las variables
de entorno del sistema aún pueden anular la configuración incorporada para
despliegues administrados.

### Desarrollo nativo

```bash
python3 oneboard_macos.py
```

El launcher abre el `.app` nativo más reciente. Si todavía no existe un build, compila y ejecuta el paquete SwiftUI. También puedes trabajar directamente con Swift:

```bash
cd macos-native/ONEBoardNative
swift build
swift run ONEBoardNative
```

Para editar firma, Team, Bundle Identifier y capacidades en Xcode:

```bash
open macos-native/ONEBoardNativeApp/ONEBoardNativeApp.xcodeproj
```

Sin un certificado de Apple, el script aplica una firma local ad-hoc que funciona para pruebas en este Mac. Para distribución pública debes configurar `ONEBOARD_SIGN_IDENTITY` con un certificado Developer ID Application y completar notarización y stapling antes de entregar el DMG. El modo de producción lo exige explícitamente:

```bash
ONEBOARD_BUILD_MODE=production \
ONEBOARD_SIGN_IDENTITY="Developer ID Application: Nombre (TEAMID)" \
ONEBOARD_NOTARY_PROFILE="oneboard-notary" \
scripts/build-macos-native.sh
```

## Notas Windows

- La terminal integrada ejecuta comandos del shell del sistema con los permisos del usuario que ejecuta ONEBoard. Cada comando empieza en la carpeta del proyecto, pero puede acceder a otras rutas y recursos disponibles para esa cuenta.
- La base de datos SQLite se crea automáticamente en `oneboard.db`.
- Los backups se guardan en `backups\`.
- Los uploads de usuario se guardan en `uploads\`.
