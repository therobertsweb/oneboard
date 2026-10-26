"""Development launcher for the native macOS version of ONEBoard.

The previous launcher started Flask and opened the user's default browser.  It
now opens a native ONEBoard.app when one has been built, or runs the SwiftUI
package during development.
"""

import os
import plistlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EXPECTED_BUNDLE_ID = "com.robertocastillo.oneboard"


def is_native_oneboard(app_path):
    info_path = app_path / "Contents" / "Info.plist"
    try:
        with info_path.open("rb") as info_file:
            return plistlib.load(info_file).get("CFBundleIdentifier") == EXPECTED_BUNDLE_ID
    except (OSError, plistlib.InvalidFileException):
        return False


def built_applications():
    candidates = list((ROOT / "dist").glob("native-macos-*/ONEBoard.app"))
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    candidates.append(Path("/Applications/ONEBoard.app"))
    return candidates


if __name__ == "__main__":
    if sys.platform != "darwin":
        raise SystemExit("The native ONEBoard launcher is available only on macOS.")

    for application in built_applications():
        if application.is_dir() and is_native_oneboard(application):
            subprocess.run(["open", str(application)], check=True)
            raise SystemExit(0)

    package_path = ROOT / "macos-native" / "ONEBoardNative"
    environment = os.environ.copy()
    environment["ONEBOARD_SERVICE_ROOT"] = str(ROOT)
    raise SystemExit(
        subprocess.call(
            ["swift", "run", "--package-path", str(package_path), "ONEBoardNative"],
            env=environment,
        )
    )
