# ONEBoard nativo para macOS

Esta carpeta contiene la interfaz real de macOS de ONEBoard. La aplicación visible está hecha con SwiftUI/AppKit; Flask se conserva como un helper privado incluido dentro de `ONEBoard.app` para reutilizar las operaciones, la base de datos y las integraciones existentes.

## Qué incluye

- Ventana y controles reales de macOS, sin semáforos HTML simulados.
- Tema navy/cyan inspirado en la referencia de ONE WEB.
- Login y registro nativos.
- Sidebar, Dashboard, Site Manager, Security Scan, Settings y Help en SwiftUI.
- Selectores nativos de carpetas e imágenes.
- Cliente JSON para los endpoints `/api/...` de ONEBoard.
- Servicio local autocontenido, empaquetado con PyInstaller y servido con Waitress.
- Datos persistentes en `~/Library/Application Support/ONEBoard`.
- Puerto loopback privado seleccionado entre `51249...51259` para evitar conflictos.

La aplicación no abre un navegador para mostrar su interfaz. Google OAuth sí puede abrir el navegador del sistema cuando el usuario inicia expresamente una autorización externa.

## Ejecutar durante desarrollo

Desde la raíz de `ONEBoard`:

```bash
python3 oneboard_macos.py
```

O directamente:

```bash
cd macos-native/ONEBoardNative
swift build
swift run ONEBoardNative
```

`ONEBoardService.swift` detecta la raíz del repositorio durante desarrollo. También puedes definirla explícitamente:

```bash
ONEBOARD_SERVICE_ROOT=/ruta/a/ONEBoard swift run ONEBoardNative
```

## Crear `.app` y `.dmg`

Se necesita Xcode completo y un Mac Apple Silicon:

```bash
scripts/build-macos-native.sh
```

El script:

1. Empaqueta `oneboard_native_service.py`, Flask, Waitress, templates y static como helper ARM64.
2. Compila el proyecto Xcode en Release.
3. Inserta el helper dentro de `ONEBoard.app`.
4. Firma localmente todo el código anidado.
5. Crea un DMG con acceso directo a Applications.

La primera ejecución del build crea un entorno de herramientas en `.build-tools/macos-packager`. No se copia ningún virtualenv del desarrollador dentro del producto.

## Configuración y datos

La app usa:

```text
~/Library/Application Support/ONEBoard
```

Allí se guardan `oneboard.db`, backups, uploads, workspaces remotos, llaves SSH, `service.log` y la clave de sesión local. Para Google u otras variables privadas, copia `.env.example` a `.env` en ese directorio.
Para la aplicación nativa registra un cliente OAuth de tipo **Desktop** en Google
Cloud. ONEBoard utiliza un callback loopback privado con un puerto dinámico; no
configures `GOOGLE_NATIVE_REDIRECT_URI` ni un esquema `oneboard://`.

## Firma y distribución

El build predeterminado usa firma ad-hoc para pruebas locales. Para firmar con Developer ID:

```bash
ONEBOARD_SIGN_IDENTITY="Developer ID Application: Nombre (TEAMID)" \
  scripts/build-macos-native.sh
```

Para notarizar el DMG, guarda primero las credenciales de Apple en un perfil de
Keychain y proporciona su nombre:

```bash
ONEBOARD_SIGN_IDENTITY="Developer ID Application: Nombre (TEAMID)" \
ONEBOARD_NOTARY_PROFILE="oneboard-notary" \
ONEBOARD_BUILD_MODE=production \
scripts/build-macos-native.sh
```

La primera distribución recomendada es fuera del Mac App Store: ONEBoard ejecuta Codex/SSH y modifica carpetas elegidas por el usuario, por lo que una versión para App Store necesita una fase adicional de sandbox y bookmarks de seguridad.
