"""Artist settings and translator backends, against a local stand-in server."""

import http.server
import json
import threading

import pytest

from botc_automod.artist import config
from botc_automod.artist.query import Seat, World
from botc_automod.artist.translate import (OllamaTranslator, OpenAITranslator, extract_json, make_translator,
                                           user_message, wrapped_schema)

WORLD = World([Seat(n, "chef", "townsfolk", "good", True, False) for n in ("Ann", "Ben", "Cat", "Dan", "Eve")],
              {"chef": ("Chef", "townsfolk"), "imp": ("Imp", "demon")})
REPLY = {"query": {"op": "is_team", "player": "Ben", "team": "evil"}}


class Stub(http.server.BaseHTTPRequestHandler):
    seen: list = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Stub.seen.append((self.path, body, self.headers.get("Authorization")))
        text = json.dumps(REPLY)
        if self.path.endswith("/api/chat"):
            out = {"message": {"content": text}}
        else:
            out = {"choices": [{"message": {"content": "```json\n" + text + "\n```"}}]}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def stub():
    srv = http.server.HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_ollama_backend(stub):
    q, _ = OllamaTranslator(stub, "tiny").translate(WORLD, "Ann", "Is Ben evil?")
    assert q == REPLY["query"]
    path, body, _ = Stub.seen[-1]
    assert path == "/api/chat" and body["format"]["type"] == "object" and body["options"]["temperature"] == 0


def test_openai_backend_sends_key_and_schema(stub):
    q, _ = OpenAITranslator(stub + "/v1", "m", api_key="sk-test").translate(WORLD, "Ann", "Is Ben evil?")
    assert q == REPLY["query"]
    path, body, auth = Stub.seen[-1]
    assert path == "/v1/chat/completions" and auth == "Bearer sk-test"
    assert body["response_format"]["type"] == "json_schema"


def test_invalid_model_output_means_ask_again(stub):
    global REPLY
    old, REPLY = REPLY, {"query": {"op": "is_team", "player": "Zed", "team": "evil"}}
    try:
        q, _ = OllamaTranslator(stub, "tiny").translate(WORLD, "Ann", "Is Zed evil?")
        assert q is None
    finally:
        REPLY = old


def test_prompt_lists_players_in_order_and_characters():
    m = user_message(WORLD, "Ann", "hi")
    assert "Players (clockwise): Ann, Ben, Cat, Dan, Eve" in m and "imp=Imp" in m and m.endswith("Question: hi")
    assert wrapped_schema(WORLD)["required"] == ["query"]


def test_extract_json_unwraps_query():
    assert extract_json('noise {"query": {"op": "unanswerable"}} more') == {"query": {"op": "unanswerable"}}


def test_config_env_overrides_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(config.sys, "platform", "linux")
    config.save({"kind": "ollama", "url": "http://x:11434", "model": "a"})
    assert config.load()["kind"] == "ollama"
    assert (config.config_file().stat().st_mode & 0o777) == 0o600
    monkeypatch.setenv("BOTC_ARTIST", "openai")
    monkeypatch.setenv("BOTC_ARTIST_KEY", "k")
    assert config.load() == {"kind": "openai", "url": "", "model": "", "api_key": "k"}


def test_make_translator_kinds():
    assert make_translator({"kind": "none"}) is None
    t = make_translator({"kind": "gemini", "api_key": "k"})
    assert isinstance(t, OpenAITranslator) and "generativelanguage" in t.base
    t = make_translator({"kind": "ollama", "url": "http://h:11434/", "model": "m"})
    assert isinstance(t, OllamaTranslator) and t.url == "http://h:11434"
