"""Run the packaged models on this computer with llama.cpp's llama-server.

The first start downloads these into the data folder, then reuses them:
  - llama-server for this system (CPU build, about 12 to 20 MB, pinned release)
  - the packaged Artist model file (GGUF, 145 MB)
  - with the chat option on: a small chat model (Qwen3 1.7B, 4-bit, 1.1 GB)

Each model gets its own llama-server. It listens on 127.0.0.1 only and
speaks the OpenAI API.
"""

from __future__ import annotations

import atexit
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

LLAMA_TAG = "b11193"
LLAMA_URL = "https://github.com/ggml-org/llama.cpp/releases/download/{tag}/llama-{tag}-bin-{asset}"
# Where the published model lives (a Hugging Face repository). Empty until it is published.
# BOTC_PACKAGED_MODEL_URL overrides it with a URL or a local .gguf file.
PACKAGED_REPO = "https://huggingface.co/carbonpoint/botc-artist/resolve/main"
MODEL_FILE = "botc-artist.gguf"
PORT = 8779
# The chat model for agents and the helpful narrator (Apache-2.0), pinned to one commit.
# BOTC_CHAT_MODEL_URL overrides it with a URL or a local .gguf file.
CHAT_MODEL_URL = ("https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/"
                  "d7f544eead698dbd1f15126ef60b45a1e1933222/Qwen3-1.7B-Q4_K_M.gguf")
CHAT_MODEL_FILE = "qwen3-1.7b-q4_k_m.gguf"
CHAT_PORT = 8780


def default_model_url() -> str:
    """The published model file (SmolLM2 135M, 8-bit, 145 MB): the same for computers and phones."""
    if os.environ.get("BOTC_PACKAGED_MODEL_URL"):
        return os.environ["BOTC_PACKAGED_MODEL_URL"]
    return f"{PACKAGED_REPO}/{MODEL_FILE}" if PACKAGED_REPO else ""


def asset() -> str:
    mach = platform.machine().lower()
    arm = mach in ("arm64", "aarch64")
    if "ANDROID_ROOT" in os.environ or hasattr(sys, "getandroidapilevel"):
        return "android-arm64.tar.gz"
    if sys.platform == "win32":
        return "win-cpu-arm64.zip" if arm else "win-cpu-x64.zip"
    if sys.platform == "darwin":
        return "macos-arm64.tar.gz" if arm else "macos-x64.tar.gz"
    return "ubuntu-arm64.tar.gz" if arm else "ubuntu-x64.tar.gz"


def download(url: str, dest: Path, label: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"  Downloading {label} ...", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "botc-automod"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done >> 20} / {total >> 20} MB", end="", flush=True)
    print()
    tmp.replace(dest)


def server_binary(root: Path) -> Path:
    bundled = os.environ.get("BOTC_LLAMA_DIR")  # the Android app ships llama-server as a native library
    if bundled and (Path(bundled) / "libllama-server-exec.so").exists():
        return Path(bundled) / "libllama-server-exec.so"
    home = root / f"llama-{LLAMA_TAG}"
    exe = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    found = next(home.rglob(exe), None) if home.exists() else None
    if found:
        return found
    archive = root / f"llama-{LLAMA_TAG}-{asset()}"
    download(LLAMA_URL.format(tag=LLAMA_TAG, asset=asset()), archive, f"llama.cpp {LLAMA_TAG} ({asset()})")
    home.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(home)
    else:
        with tarfile.open(archive) as t:
            t.extractall(home, filter="data")
    archive.unlink()
    found = next(home.rglob(exe), None)
    if not found:
        raise RuntimeError(f"llama-server not found in the {asset()} download")
    found.chmod(0o755)
    return found


def model_file(root: Path, source: str = "", name: str = MODEL_FILE, label: str = "the packaged Artist model") -> Path:
    source = source or (default_model_url() if name == MODEL_FILE else "")
    if source and Path(source).expanduser().is_file():
        return Path(source).expanduser()
    path = root / name
    if path.exists():
        return path
    if not source:
        raise RuntimeError("The packaged model is not published yet. Set BOTC_PACKAGED_MODEL_URL to a URL or a "
                           ".gguf file, or choose another model with --setup.")
    download(source, path, label)
    return path


class LocalServer:
    """A llama-server child process. Stops when botc-automod exits."""

    def __init__(self, root: Path, source: str = "", port: int = PORT, name: str = MODEL_FILE,
                 label: str = "the packaged Artist model", context: int = 2048, extra: tuple[str, ...] = ()):
        self.root, self.source, self.port = root, source, port
        self.name, self.label, self.context, self.extra = name, label, context, extra
        self.proc: subprocess.Popen | None = None

    @classmethod
    def chat(cls, root: Path) -> "LocalServer":
        """The chat model's server. --jinja applies Qwen3's own chat template (thinking off per request)."""
        return cls(root, os.environ.get("BOTC_CHAT_MODEL_URL") or CHAT_MODEL_URL, CHAT_PORT, CHAT_MODEL_FILE,
                   "the chat model (Qwen3 1.7B)", 4096, ("--jinja",))

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def start(self, timeout: float = 90) -> None:
        exe = server_binary(self.root)
        model = model_file(self.root, self.source, self.name, self.label)
        threads = str(max(1, min(4, (os.cpu_count() or 2) - 1)))
        env = dict(os.environ)
        lib = str(exe.parent)
        env["LD_LIBRARY_PATH"] = lib + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        env["DYLD_LIBRARY_PATH"] = lib + os.pathsep + env.get("DYLD_LIBRARY_PATH", "")
        log = open(self.root / f"llama-server-{self.port}.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [str(exe), "-m", str(model), "--host", "127.0.0.1", "--port", str(self.port), "-c", str(self.context),
             "-t", threads, "-np", "1", "--no-webui", *self.extra],
            stdout=log, stderr=subprocess.STDOUT, env=env, cwd=exe.parent)
        atexit.register(self.stop)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"llama-server stopped; see {self.root / f'llama-server-{self.port}.log'}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=2) as r:
                    if r.status == 200:
                        return
            except OSError:
                pass
            time.sleep(0.5)
        raise RuntimeError("llama-server did not start in time")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def remove_downloads(root: Path) -> None:
    shutil.rmtree(root / f"llama-{LLAMA_TAG}", ignore_errors=True)
