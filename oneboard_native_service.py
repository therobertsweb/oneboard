"""Private local service used by the native macOS application.

This entry point deliberately never opens a browser.  The SwiftUI application
starts it as a bundled helper and communicates with it over loopback only.
"""

import os
import secrets
import sys


initial_environment_keys = set(os.environ)
SYSTEM_SHARED_CONFIG_DIRECTORY = "/Library/Application Support/ONEBoard"
USER_SHARED_CONFIG_DIRECTORY = "/Users/Shared/ONEBoard"


def read_env_file(path):
    """Return the values declared in a private configuration file."""
    if not os.path.isabs(path):
        base_directory = (
            os.path.dirname(sys.executable)
            if getattr(sys, "frozen", False)
            else os.path.abspath(os.path.dirname(__file__))
        )
        path = os.path.join(base_directory, path)
    if not os.path.exists(path):
        return {}

    values = {}
    with open(path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_env_file(path, override_loaded_values=False):
    """Load private configuration without overriding the process environment."""
    for key, value in read_env_file(path).items():
        if key not in initial_environment_keys and (override_loaded_values or key not in os.environ):
            os.environ[key] = value


data_directory = os.environ.get("ONEBOARD_DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
os.makedirs(data_directory, exist_ok=True)
os.chmod(data_directory, 0o700)
bundled_config_directory = os.environ.get(
    "ONEBOARD_BUNDLED_CONFIG_DIR",
    os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.abspath(os.path.dirname(__file__)),
)
bundled_env_path = os.path.join(bundled_config_directory, ".env")
user_env_path = os.path.join(data_directory, ".env")
system_shared_env_path = os.path.join(
    os.environ.get("ONEBOARD_SHARED_CONFIG_DIR", SYSTEM_SHARED_CONFIG_DIRECTORY),
    ".env",
)
user_shared_env_path = os.path.join(
    os.environ.get("ONEBOARD_USER_SHARED_CONFIG_DIR", USER_SHARED_CONFIG_DIRECTORY),
    ".env",
)
load_env_file(bundled_env_path)
load_env_file(system_shared_env_path)
load_env_file(user_shared_env_path)
load_env_file(user_env_path, override_loaded_values=True)

if not os.environ.get("SECRET_KEY"):
    secret_path = os.path.join(data_directory, ".secret-key")
    if os.path.exists(secret_path):
        with open(secret_path, "r", encoding="utf-8") as secret_file:
            os.environ["SECRET_KEY"] = secret_file.read().strip()
    else:
        secret_value = secrets.token_hex(32)
        with open(secret_path, "w", encoding="utf-8") as secret_file:
            secret_file.write(secret_value)
        os.chmod(secret_path, 0o600)
        os.environ["SECRET_KEY"] = secret_value

from app import app
from waitress import serve


for private_filename in (".env", ".secret-key", "oneboard.db"):
    private_path = os.path.join(data_directory, private_filename)
    if os.path.isfile(private_path):
        os.chmod(private_path, 0o600)


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "51249"))
    serve(app, host=host, port=port, threads=8)
