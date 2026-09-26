"""Entry points for the Android app (called from Java through Chaquopy).

The app's foreground service calls start() on its own thread, and stop()
when the host turns the server off. The server is the same one the desktop
runs; only the network address comes from Android (it knows the Wi-Fi or
hotspot address better than Python does).
"""

from __future__ import annotations

import io
import os
import threading
import time

_server = None
_thread: threading.Thread | None = None
_url = ""


def start(data_dir: str, port: int = 8000, public_url: str = "") -> str:
    """Start the game server in a background thread. Returns the join address."""
    global _server, _thread, _url
    if _thread and _thread.is_alive():
        return _url
    os.environ["BOTC_DATA"] = data_dir
    os.environ.setdefault("XDG_CONFIG_HOME", os.path.join(data_dir, "config"))
    if public_url:
        os.environ["BOTC_PUBLIC_URL"] = public_url
    import uvicorn

    from . import public_url as detect, server, setup_artist

    server.DATA = __import__("pathlib").Path(data_dir)
    server.ARTIST = setup_artist(False, server.DATA)   # uses saved settings only; no questions on a phone
    config = uvicorn.Config(server.app, host="0.0.0.0", port=port, log_level="warning",
                            loop="asyncio", http="h11", ws="wsproto", lifespan="on")
    _server = uvicorn.Server(config)
    _thread = threading.Thread(target=_server.run, name="botc-server", daemon=True)
    _thread.start()
    for _ in range(100):
        if _server.started:
            break
        time.sleep(0.1)
    _url = detect(port)
    return _url


def stop() -> None:
    global _thread
    if _server is not None:
        _server.should_exit = True
    if _thread is not None:
        _thread.join(timeout=5)
    _thread = None


def running() -> bool:
    return bool(_thread and _thread.is_alive() and _server is not None and _server.started)


def qr_png(url: str, scale: int = 10) -> bytes:
    """The join QR code as PNG bytes, for the app screen."""
    import segno

    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="png", scale=scale, border=2)
    return buf.getvalue()
