"""Run the packaged Artist model on this computer with llama.cpp's llama-server.

The first start downloads two things into the data folder, then reuses them:
  - llama-server for this system (CPU build, about 12 to 20 MB, pinned release)
  - the packaged model file (GGUF)

llama-server then listens on 127.0.0.1 only and speaks the OpenAI API.
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
PACKAGED_REPO = ""   # e.g. "https://huggingface.co/OWNER/botc-artist/resolve/main"
MODEL_FILE = "botc-artist.gguf"


def default_model_url() -> str:
    """Phones get the 4-bit file (271 MB), computers the 8-bit one (386 MB)."""
    if os.environ.get("BOTC_PACKAGED_MODEL_URL"):
        return os.environ["BOTC_PACKAGED_MODEL_URL"]
    if not PACKAGED_REPO:
        return ""
    small = "ANDROID_ROOT" in os.environ or hasattr(sys, "getandroidapilevel")
    return f"{PACKAGED_REPO}/botc-artist-{'q4' if small else 'q8'}.gguf"
PORT = 8779


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


def model_file(root: Path, source: str = "") -> Path:
    source = source or default_model_url()
    if source and Path(source).expanduser().is_file():
        return Path(source).expanduser()
    path = root / MODEL_FILE
    if path.exists():
        return path
    if not source:
        raise RuntimeError("The packaged model is not published yet. Set BOTC_PACKAGED_MODEL_URL to a URL or a "
                           ".gguf file, or choose another model with --setup.")
    download(source, path, "the packaged Artist model")
    return path


class LocalServer:
    """A llama-server child process. Stops when botc-automod exits."""

    def __init__(self, root: Path, source: str = "", port: int = PORT):
        self.root, self.source, self.port = root, source, port
        self.proc: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def start(self, timeout: float = 90) -> None:
        exe = server_binary(self.root)
        model = model_file(self.root, self.source)
        threads = str(max(1, min(4, (os.cpu_count() or 2) - 1)))
        env = dict(os.environ)
        lib = str(exe.parent)
        env["LD_LIBRARY_PATH"] = lib + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        env["DYLD_LIBRARY_PATH"] = lib + os.pathsep + env.get("DYLD_LIBRARY_PATH", "")
        log = open(self.root / "llama-server.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [str(exe), "-m", str(model), "--host", "127.0.0.1", "--port", str(self.port), "-c", "2048",
             "-t", threads, "-np", "1", "--no-webui"],
            stdout=log, stderr=subprocess.STDOUT, env=env, cwd=exe.parent)
        atexit.register(self.stop)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"llama-server stopped; see {self.root / 'llama-server.log'}")
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
