import os

from run import load_env_file


load_env_file()

from app import app
from waitress import serve


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5002"))
    serve(app, host=host, port=port, threads=8)
