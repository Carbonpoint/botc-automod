"""The packaged-model runtime: platform choice, model source, bundled llama-server."""

from pathlib import Path

import pytest

from botc_automod.artist import runtime


def test_asset_names_match_the_release_files():
    assert runtime.asset() in {"ubuntu-x64.tar.gz", "ubuntu-arm64.tar.gz", "macos-arm64.tar.gz",
                               "macos-x64.tar.gz", "win-cpu-x64.zip", "win-cpu-arm64.zip", "android-arm64.tar.gz"}


def test_local_server_defaults():
    s = runtime.LocalServer(Path("/nonexistent"))
    assert s.port == runtime.PORT and s.url == f"http://127.0.0.1:{runtime.PORT}/v1"


def test_model_source(tmp_path, monkeypatch):
    f = tmp_path / "m.gguf"
    f.write_bytes(b"GGUF")
    monkeypatch.setenv("BOTC_PACKAGED_MODEL_URL", str(f))
    assert runtime.model_file(tmp_path / "root") == f
    monkeypatch.delenv("BOTC_PACKAGED_MODEL_URL")
    monkeypatch.setattr(runtime, "PACKAGED_REPO", "")
    with pytest.raises(RuntimeError, match="not published"):
        runtime.model_file(tmp_path / "root")
    monkeypatch.setattr(runtime, "PACKAGED_REPO", "https://example.org/r")
    assert runtime.default_model_url() == "https://example.org/r/botc-artist.gguf"


def test_bundled_server_is_used_when_present(tmp_path, monkeypatch):
    exe = tmp_path / "libllama-server-exec.so"
    exe.write_bytes(b"x")
    monkeypatch.setenv("BOTC_LLAMA_DIR", str(tmp_path))
    assert runtime.server_binary(tmp_path / "root") == exe
