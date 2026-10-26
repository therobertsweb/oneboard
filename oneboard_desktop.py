import os
import threading
import webbrowser

from run import load_env_file


load_env_file()

from app import app
from waitress import serve


def open_browser(url):
    webbrowser.open(url, new=2)


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5002"))
    url = f"http://{host}:{port}"
    threading.Timer(1.2, open_browser, args=(url,)).start()
    serve(app, host=host, port=port, threads=8)
