"""The Android app's Python entry points, run on a desktop in the same mode (h11 + wsproto)."""

import json
import socket
import urllib.request

from botc_automod import android


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_start_serve_stop(tmp_path):
    port = free_port()
    url = android.start(str(tmp_path / "data"), port, f"http://192.168.43.1:{port}/", str(tmp_path / "nolibs"))
    try:
        assert url == f"http://192.168.43.1:{port}/" and android.running()
        info = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/info", timeout=5))
        assert info["join_url"] == url
        assert android.qr_png(url)[:4] == b"\x89PNG"
    finally:
        android.stop()
    assert not android.running()


def test_artist_settings_round_trip(tmp_path):
    d = str(tmp_path / "data")
    assert json.loads(android.get_artist(d))["kind"] == "none"
    android.set_artist(d, json.dumps({"kind": "ollama", "url": "http://h:11434", "model": "m"}))
    got = json.loads(android.get_artist(d))
    assert got == {"kind": "ollama", "url": "http://h:11434", "model": "m", "has_key": False}
