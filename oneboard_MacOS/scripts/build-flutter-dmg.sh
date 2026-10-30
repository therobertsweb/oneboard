#!/bin/bash
# Distribution packaging for the Flutter ONEBoard macOS app.
#
# Produces dist/ONEBoard-<stamp>.dmg containing ONEBoard.app.
#
# Signing:
#   - Default: ad-hoc signature. Runs on this Mac; other Macs need
#     right-click > Open once (Gatekeeper), and push notifications
#     do NOT work.
#   - With ONEBOARD_SIGN_IDENTITY set (Apple Developer certificate):
#     signs for distribution. Add ONEBOARD_NOTARY_PROFILE for
#     Apple notarization via notarytool.
#
# The bundled .env is SANITIZED: only the keys another install needs.
# SMTP credentials, SECRET_KEY, and local paths never ship.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FLUTTER_ROOT="$ROOT/oneboard_MacOS"
STAMP="$(date +%Y%m%d-%H%M%S)"
DIST_DIR="$ROOT/dist"
DMG_ROOT="$(mktemp -d /tmp/oneboard-dmg.XXXXXX)"
DMG="$DIST_DIR/ONEBoard-$STAMP.dmg"
SANITIZED_ENV="$DMG_ROOT/dist.env"
SIGN_IDENTITY="${ONEBOARD_SIGN_IDENTITY:--}"
NOTARY_PROFILE="${ONEBOARD_NOTARY_PROFILE:-}"

for command_name in ditto hdiutil codesign; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command not found: $command_name" >&2
    exit 1
  fi
done

# --- 1. Sanitized env for other people's machines. ---
"${PACKAGING_PYTHON:-/usr/bin/python3}" - "$ROOT/.env" "$SANITIZED_ENV" <<'EOF'
import sys
src, dst = sys.argv[1], sys.argv[2]
keep = {
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REDIRECT_URI",
    "GOOGLE_NATIVE_REDIRECT_URI",
    "ONEBOARD_NATIVE_PORT",
    "ONEBOARD_MEDIA_URL",
    "ONEBOARD_MEDIA_TOKEN",
    "HOST",
    "PORT",
}
out = []
with open(src) as handle:
    for line in handle:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name = stripped.split("=", 1)[0].strip()
        if name in keep:
            out.append(line if line.endswith("\n") else line + "\n")
with open(dst, "w") as handle:
    handle.writelines(out)
names = sorted(line.split("=", 1)[0] for line in out)
print(f"Bundled env keys ({len(names)}): {', '.join(names)}")
EOF
chmod 600 "$SANITIZED_ENV"

# --- 2. Build the app with the sanitized env. ---
export ONEBOARD_NATIVE_ENV_FILE="$SANITIZED_ENV"
export ONEBOARD_DISTRIBUTION=1
export ONEBOARD_BUILD_MODE="${ONEBOARD_BUILD_MODE:-release}"
export ONEBOARD_SIGN_IDENTITY="$SIGN_IDENTITY"
bash "$FLUTTER_ROOT/scripts/build-flutter-macos.sh"

case "$ONEBOARD_BUILD_MODE" in
  debug) PRODUCT_CONFIGURATION="Debug" ;;
  *) PRODUCT_CONFIGURATION="Release" ;;
esac
APP="$FLUTTER_ROOT/build/macos/Build/Products/$PRODUCT_CONFIGURATION/ONEBoard.app"

# --- 3. Notarize when credentials are provided. ---
if [ -n "$NOTARY_PROFILE" ]; then
  if [ "$SIGN_IDENTITY" = "-" ]; then
    echo "Notarization needs ONEBOARD_SIGN_IDENTITY." >&2
    exit 1
  fi
  xcrun notarytool submit "$APP" --wait --keychain-profile "$NOTARY_PROFILE"
  xcrun stapler staple "$APP"
elif [ "$SIGN_IDENTITY" = "-" ]; then
  echo "WARNING: ad-hoc signature. Other Macs need right-click > Open; no push." >&2
fi

# --- 4. DMG. ---
mkdir -p "$DIST_DIR" "$DMG_ROOT/root"
ditto "$APP" "$DMG_ROOT/root/ONEBoard.app"
ln -s /Applications "$DMG_ROOT/root/Applications"
hdiutil create -volname "ONEBoard" -srcfolder "$DMG_ROOT/root" \
  -ov -format UDZO "$DMG" >/dev/null
rm -rf "$DMG_ROOT"
echo "DMG: $DMG"
