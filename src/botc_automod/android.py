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


def start(data_dir: str, port: int = 8000, public_url: str = "", native_dir: str = "") -> str:
    """Start the game server in a background thread. Returns the join address."""
    global _server, _thread, _url
    if _thread and _thread.is_alive():
        return _url
    _env(data_dir, native_dir)
    if public_url:
        os.environ["BOTC_PUBLIC_URL"] = public_url
    import uvicorn

    from . import public_url as detect, server, setup_artist

    server.DATA = __import__("pathlib").Path(data_dir)
    server.ARTIST = setup_artist(False, server.DATA)   # uses saved settings only; no questions on a phone
    server.CHAT = server.ARTIST if server.ARTIST is not None and server.ARTIST.can_chat else None
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


def _env(data_dir: str, native_dir: str = "") -> None:
    os.environ["BOTC_DATA"] = data_dir
    os.environ["XDG_CONFIG_HOME"] = os.path.join(data_dir, "config")
    if native_dir:
        os.environ["BOTC_LLAMA_DIR"] = native_dir


def get_artist(data_dir: str) -> str:
    """The saved Artist model settings as JSON (the API key is left out)."""
    import json

    from .artist import config

    _env(data_dir)
    cfg = dict(config.load() or {"kind": "none"})
    cfg["has_key"] = bool(cfg.pop("api_key", ""))
    return json.dumps(cfg)


def set_artist(data_dir: str, settings_json: str) -> str:
    """Save the Artist model settings from the app screen. An empty key keeps the saved one."""
    import json

    from .artist import config

    _env(data_dir)
    new = json.loads(settings_json)
    old = config.load() or {}
    if not new.get("api_key") and new.get("kind") == old.get("kind"):
        new["api_key"] = old.get("api_key", "")
    new = {k: v for k, v in new.items() if v not in ("", None)}
    config.save(new)
    return config.describe(new)


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
