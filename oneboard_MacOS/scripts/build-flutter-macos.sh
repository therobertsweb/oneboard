#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FLUTTER_ROOT="$ROOT/oneboard_MacOS"
PACKAGING_VENV="${ONEBOARD_PACKAGING_VENV:-$ROOT/.build-tools/macos-packager}"
PACKAGING_PYTHON="${ONEBOARD_PACKAGING_PYTHON:-/usr/bin/python3}"
BUILD_MODE="${ONEBOARD_BUILD_MODE:-release}"
# The bundled helper cannot read the repository's .env after the app is
# installed. Copy the selected private configuration next to the helper so
# oneboard_native_service.py loads it from its frozen executable directory.
CONFIG_ENV_FILE="${ONEBOARD_NATIVE_ENV_FILE:-${ONEBOARD_NATIVE_SMTP_ENV_FILE:-$ROOT/.env}}"
case "$BUILD_MODE" in
  debug) PRODUCT_CONFIGURATION="Debug" ;;
  release) PRODUCT_CONFIGURATION="Release" ;;
  *) echo "ONEBOARD_BUILD_MODE must be debug or release." >&2; exit 1 ;;
esac

if ! command -v flutter >/dev/null 2>&1; then
  echo "Flutter is required on PATH." >&2
  exit 1
fi
if [ ! -x "$PACKAGING_PYTHON" ]; then
  echo "Packaging Python is not executable: $PACKAGING_PYTHON" >&2
  exit 1
fi
if [ ! -f "$CONFIG_ENV_FILE" ]; then
  echo "ONEBoard configuration file not found: $CONFIG_ENV_FILE" >&2
  exit 1
fi
if ! grep -q '^SMTP_HOST=.' "$CONFIG_ENV_FILE" || ! grep -q '^SMTP_FROM=.' "$CONFIG_ENV_FILE"; then
  if [ "${ONEBOARD_DISTRIBUTION:-0}" = "1" ]; then
    echo "Distribution build: no SMTP bundled; verification links complete inside the app." >&2
  else
    echo "ONEBoard requires SMTP_HOST and SMTP_FROM in $CONFIG_ENV_FILE." >&2
    exit 1
  fi
fi

if [ ! -x "$PACKAGING_VENV/bin/python" ]; then
  mkdir -p "$(dirname "$PACKAGING_VENV")"
  "$PACKAGING_PYTHON" -m venv "$PACKAGING_VENV"
fi
if ! "$PACKAGING_VENV/bin/python" -c 'import PyInstaller, flask, waitress' >/dev/null 2>&1; then
  "$PACKAGING_VENV/bin/python" -m pip install --upgrade pip
  "$PACKAGING_VENV/bin/python" -m pip install -r "$ROOT/requirements.txt" 'pyinstaller>=6,<7'
fi

BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/oneboard-flutter-build.XXXXXX")"
trap 'rm -rf "$BUILD_ROOT"' EXIT
SERVICE_DIST="$BUILD_ROOT/service-dist"

echo "[1/3] Building the private local service"
"$PACKAGING_VENV/bin/python" -m PyInstaller \
  --noconfirm --clean --onedir --name ONEBoardService --target-arch arm64 \
  --distpath "$SERVICE_DIST" --workpath "$BUILD_ROOT/work" --specpath "$BUILD_ROOT" \
  --add-data "$ROOT/templates:templates" --add-data "$ROOT/static:static" \
  "$ROOT/oneboard_native_service.py"

echo "[2/3] Building the macOS app"
cd "$FLUTTER_ROOT"
# Firebase project values come from the owner's GoogleService-Info.plist so
# nobody has to paste secrets anywhere. Values are never echoed.
FIREBASE_PLIST="${ONEBOARD_FIREBASE_PLIST:-$FLUTTER_ROOT/GoogleService-Info.plist}"
FIREBASE_DEFINES=()
if [ -f "$FIREBASE_PLIST" ]; then
  while IFS='=' read -r key value; do
    if [ -n "$key" ] && [ -n "$value" ]; then
      FIREBASE_DEFINES+=("--dart-define=$key=$value")
    fi
  done < <("$PACKAGING_PYTHON" - "$FIREBASE_PLIST" <<'EOF'
import plistlib, sys
data = plistlib.load(open(sys.argv[1], 'rb'))
for src, dst in (
    ('API_KEY', 'FIREBASE_API_KEY'),
    ('GOOGLE_APP_ID', 'FIREBASE_APP_ID'),
    ('GCM_SENDER_ID', 'FIREBASE_MESSAGING_SENDER_ID'),
    ('PROJECT_ID', 'FIREBASE_PROJECT_ID'),
    ('STORAGE_BUCKET', 'FIREBASE_STORAGE_BUCKET'),
):
    value = (data.get(src) or '').strip()
    if value:
        print(f'{dst}={value}')
EOF
)
  echo "Firebase: using ${#FIREBASE_DEFINES[@]} defines from $FIREBASE_PLIST"
else
  echo "Firebase: no plist at $FIREBASE_PLIST; building without Firebase." >&2
fi
flutter pub get
flutter build macos "--$BUILD_MODE" "${FIREBASE_DEFINES[@]}"

APP="$FLUTTER_ROOT/build/macos/Build/Products/$PRODUCT_CONFIGURATION/ONEBoard.app"
if [ ! -d "$APP" ]; then
  echo "Flutter did not produce ONEBoard.app at the expected path: $APP" >&2
  exit 1
fi

echo "[3/3] Bundling and signing the private service"
SERVICE="$APP/Contents/Resources/service"
mkdir -p "$SERVICE"
ditto "$SERVICE_DIST/ONEBoardService" "$SERVICE"
# This file is local app configuration, not source code. It is copied only
# into the generated .app and is excluded from git by the repository rules.
install -m 600 "$CONFIG_ENV_FILE" "$SERVICE/.env"
chmod +x "$SERVICE/ONEBoardService"
while IFS= read -r -d '' candidate; do
  if file "$candidate" | grep -q 'Mach-O'; then
    codesign --force --sign - "$candidate"
  fi
done < <(find "$SERVICE" -type f -print0)
# Push notifications require a real Apple Developer identity: aps-environment
# is invalid on an ad-hoc signature. Without ONEBOARD_SIGN_IDENTITY the app
# builds ad-hoc (no push); with it, the top-level bundle is signed for push
# while the private service helpers stay ad-hoc.
SIGN_IDENTITY="${ONEBOARD_SIGN_IDENTITY:--}"
if [ "$SIGN_IDENTITY" = "-" ]; then
  codesign --force --deep --sign - "$APP"
else
  codesign --force --deep --sign - "$APP"
  codesign --force --sign "$SIGN_IDENTITY" \
    --entitlements "$FLUTTER_ROOT/macos/Runner/Release.push.entitlements" \
    "$APP"
fi
codesign --verify --deep --strict "$APP"
echo "App: $APP"
