#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NATIVE_ROOT="$ROOT/macos-native"
PROJECT="$NATIVE_ROOT/ONEBoardNativeApp/ONEBoardNativeApp.xcodeproj"
STAMP="$(date +%Y%m%d-%H%M%S)"
BUILD_ROOT="$ROOT/dist/native-macos-$STAMP"
DERIVED_DATA="$BUILD_ROOT/DerivedData"
APP="$BUILD_ROOT/ONEBoard.app"
SERVICE_DIST="$BUILD_ROOT/service-dist"
SERVICE_WORK="$BUILD_ROOT/service-work"
DMG_ROOT="$BUILD_ROOT/dmg-root"
DMG="$ROOT/dist/ONEBoard-Native-$STAMP.dmg"
PACKAGING_VENV="${ONEBOARD_PACKAGING_VENV:-$ROOT/.build-tools/macos-packager}"
PACKAGING_PYTHON="${ONEBOARD_PACKAGING_PYTHON:-/usr/bin/python3}"
XCODE_DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
SIGN_IDENTITY="${ONEBOARD_SIGN_IDENTITY:--}"
NOTARY_PROFILE="${ONEBOARD_NOTARY_PROFILE:-}"
NOTARY_KEYCHAIN="${ONEBOARD_NOTARY_KEYCHAIN:-}"
BUILD_MODE="${ONEBOARD_BUILD_MODE:-development}"
SMTP_ENV_FILE="${ONEBOARD_NATIVE_SMTP_ENV_FILE:-$ROOT/.env}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

for command_name in ditto file hdiutil codesign plutil; do
  require_command "$command_name"
done

case "$BUILD_MODE" in
  development|production) ;;
  *)
    echo "ONEBOARD_BUILD_MODE must be either development or production." >&2
    exit 1
    ;;
esac

if [ "$BUILD_MODE" = "production" ]; then
  require_command security
  require_command xcrun
  if [ "$SIGN_IDENTITY" = "-" ] || [ -z "$NOTARY_PROFILE" ]; then
    echo "Production builds require ONEBOARD_SIGN_IDENTITY and ONEBOARD_NOTARY_PROFILE." >&2
    exit 1
  fi
  if ! security find-identity -v -p codesigning | grep -Fq "$SIGN_IDENTITY"; then
    echo "The requested Developer ID signing identity is not installed in the keychain." >&2
    exit 1
  fi
fi

if [ -n "$NOTARY_PROFILE" ]; then
  require_command xcrun
  if [ "$SIGN_IDENTITY" = "-" ]; then
    echo "ONEBOARD_NOTARY_PROFILE requires ONEBOARD_SIGN_IDENTITY to use a Developer ID certificate." >&2
    exit 1
  fi
fi

NOTARY_ARGS=()
if [ -n "$NOTARY_KEYCHAIN" ]; then
  NOTARY_ARGS+=(--keychain "$NOTARY_KEYCHAIN")
fi

if [ ! -d "$XCODE_DEVELOPER_DIR" ]; then
  echo "Full Xcode is required. Install Xcode, then rerun this script." >&2
  exit 1
fi

if [ ! -x "$PACKAGING_PYTHON" ]; then
  echo "Packaging Python is not executable: $PACKAGING_PYTHON" >&2
  exit 1
fi

mkdir -p "$BUILD_ROOT" "$ROOT/dist" "$ROOT/.build-tools"

echo "[1/6] Preparing the private Python service"
if [ ! -x "$PACKAGING_VENV/bin/python" ]; then
  "$PACKAGING_PYTHON" -m venv "$PACKAGING_VENV"
fi

if ! "$PACKAGING_VENV/bin/python" -c 'import PyInstaller, flask, waitress' >/dev/null 2>&1; then
  "$PACKAGING_VENV/bin/python" -m pip install --upgrade pip
  "$PACKAGING_VENV/bin/python" -m pip install -r "$ROOT/requirements.txt" 'pyinstaller>=6,<7'
fi

"$PACKAGING_VENV/bin/python" -m PyInstaller \
  --noconfirm \
  --clean \
  --onedir \
  --name ONEBoardService \
  --target-arch arm64 \
  --distpath "$SERVICE_DIST" \
  --workpath "$SERVICE_WORK" \
  --specpath "$BUILD_ROOT" \
  --add-data "$ROOT/templates:templates" \
  --add-data "$ROOT/static:static" \
  "$ROOT/oneboard_native_service.py"

echo "[2/6] Building the native SwiftUI application"
DEVELOPER_DIR="$XCODE_DEVELOPER_DIR" \
  "$XCODE_DEVELOPER_DIR/usr/bin/xcodebuild" \
  -project "$PROJECT" \
  -scheme ONEBoard \
  -configuration Release \
  -derivedDataPath "$DERIVED_DATA" \
  -destination 'platform=macOS,arch=arm64' \
  CODE_SIGNING_ALLOWED=NO \
  ARCHS=arm64 \
  ONLY_ACTIVE_ARCH=YES \
  build

BUILT_APP="$DERIVED_DATA/Build/Products/Release/ONEBoard.app"
if [ ! -d "$BUILT_APP" ]; then
  echo "Xcode did not produce ONEBoard.app at the expected path." >&2
  exit 1
fi
ditto "$BUILT_APP" "$APP"
/usr/bin/plutil -insert LSMultipleInstancesProhibited -bool YES "$APP/Contents/Info.plist"

echo "[3/6] Bundling the local service"
mkdir -p "$APP/Contents/Resources/service"
ditto "$SERVICE_DIST/ONEBoardService" "$APP/Contents/Resources/service"
ditto "$ROOT/.env.example" "$APP/Contents/Resources/service/.env.example"
if [ ! -f "$SMTP_ENV_FILE" ]; then
  echo "SMTP configuration file not found: $SMTP_ENV_FILE" >&2
  exit 1
fi
if ! grep -q '^SMTP_HOST=.' "$SMTP_ENV_FILE" || ! grep -q '^SMTP_FROM=.' "$SMTP_ENV_FILE"; then
  echo "The native app requires SMTP_HOST and SMTP_FROM in $SMTP_ENV_FILE." >&2
  exit 1
fi
if ! grep -q '^GOOGLE_CLIENT_ID=.' "$SMTP_ENV_FILE" || ! grep -q '^GOOGLE_CLIENT_SECRET=.' "$SMTP_ENV_FILE"; then
  echo "The native app requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in $SMTP_ENV_FILE." >&2
  exit 1
fi
grep -E '^(SMTP_|GOOGLE_CLIENT_ID=|GOOGLE_CLIENT_SECRET=)' "$SMTP_ENV_FILE" > "$APP/Contents/Resources/service/.env"
chmod 644 "$APP/Contents/Resources/service/.env"
chmod +x "$APP/Contents/Resources/service/ONEBoardService"

echo "[4/6] Signing the application"
sign_path() {
  local target="$1"
  if [ "$SIGN_IDENTITY" = "-" ]; then
    codesign --force --sign - "$target"
  else
    codesign --force --options runtime --timestamp --sign "$SIGN_IDENTITY" "$target"
  fi
}

while IFS= read -r -d '' candidate; do
  if file "$candidate" | grep -q 'Mach-O'; then
    sign_path "$candidate"
  fi
done < <(find "$APP/Contents/Resources/service" -type f -print0)

sign_path "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

echo "[5/6] Creating the installer image"
mkdir -p "$DMG_ROOT"
ditto "$APP" "$DMG_ROOT/ONEBoard.app"
ln -s /Applications "$DMG_ROOT/Applications"
hdiutil create \
  -volname "ONEBoard" \
  -format UDZO \
  -srcfolder "$DMG_ROOT" \
  "$DMG" >/dev/null

if [ "$SIGN_IDENTITY" != "-" ]; then
  codesign --force --timestamp --sign "$SIGN_IDENTITY" "$DMG"
fi

if [ -n "$NOTARY_PROFILE" ]; then
  echo "[6/6] Notarizing the installer image"
  xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" "${NOTARY_ARGS[@]}" --wait
  xcrun stapler staple "$DMG"
  xcrun stapler validate "$DMG"
fi

echo "Native build complete"
echo "Application: $APP"
echo "Installer:   $DMG"
if [ "$SIGN_IDENTITY" = "-" ]; then
  echo "Signing:     local ad-hoc signature (Developer ID/notarization still required for public distribution)"
else
  echo "Signing:     $SIGN_IDENTITY"
fi
echo "Build mode:   $BUILD_MODE"
if [ -n "$NOTARY_PROFILE" ]; then
  echo "Notarized:   yes"
fi
