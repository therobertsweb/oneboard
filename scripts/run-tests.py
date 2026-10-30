"""Run each test module with isolated imports and without deployment credentials."""

import os
from pathlib import Path
import subprocess
import sys

from dotenv import dotenv_values


def main():
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    # Explicit empty overrides prevent app's dotenv loader from using real keys.
    for key in dotenv_values(root / ".env"):
        environment[key] = ""
    for key in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM",
                "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI",
                "ONEBOARD_SITE_DIRECTORY", "WEBSITE_DIRECTORY", "ONEBOARD_SERVICE_TOKEN"):
        environment[key] = ""
    environment["SMTP_PORT"] = "587"
    environment["SMTP_USE_TLS"] = "1"
    failed = []
    modules = sorted((root / "tests").glob("test_*.py"))
    for module in modules:
        print(f"\n{module.name}", flush=True)
        result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests",
                                 "-p", module.name, "-q"], cwd=root, env=environment)
        if result.returncode:
            failed.append(module.name)
    print(f"\n{len(modules) - len(failed)}/{len(modules)} modules passed.")
    if failed:
        print("Failed: " + ", ".join(failed))
    return bool(failed)


if __name__ == "__main__":
    sys.exit(main())
