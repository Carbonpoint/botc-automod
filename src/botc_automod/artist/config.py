"""Where the Artist's language model comes from: saved settings and the first-run questions.

Settings live in a JSON file in the user's config folder (chmod 600, since
it may hold an API key). Environment variables override the file, which
suits Docker:

    BOTC_ARTIST        none | packaged | ollama | anthropic | openai | gemini | openrouter | custom
    BOTC_ARTIST_URL    server address (ollama, custom, packaged)
    BOTC_ARTIST_MODEL  model name
    BOTC_ARTIST_KEY    API key (cloud)
    BOTC_CHAT          none | packaged: a small local chat model for agents and tips
"""

from __future__ import annotations

import getpass
import json
import os
import sys
import urllib.request
from pathlib import Path

PROVIDERS = [
    ("anthropic", "Anthropic (Claude)", "claude-opus-5"),
    ("openai", "OpenAI", "gpt-5-mini"),
    ("gemini", "Google Gemini", "gemini-2.5-flash"),
    ("openrouter", "OpenRouter", "qwen/qwen3-8b"),
    ("custom", "Another OpenAI-compatible server", ""),
]


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "botc-automod"


def config_file() -> Path:
    return config_dir() / "config.json"


def load() -> dict:
    """The Artist settings: environment first, then the saved file, else none."""
    if os.environ.get("BOTC_ARTIST"):
        return {"kind": os.environ["BOTC_ARTIST"], "url": os.environ.get("BOTC_ARTIST_URL", ""),
                "model": os.environ.get("BOTC_ARTIST_MODEL", ""), "api_key": os.environ.get("BOTC_ARTIST_KEY", "")}
    try:
        return json.loads(config_file().read_text(encoding="utf-8")).get("artist", {"kind": "none"})
    except (OSError, ValueError):
        return {}


def load_chat() -> dict:
    """The chat model settings ({"kind": "none" | "packaged"}), or {} if never asked."""
    if os.environ.get("BOTC_CHAT"):
        return {"kind": os.environ["BOTC_CHAT"]}
    try:
        return json.loads(config_file().read_text(encoding="utf-8")).get("chat", {})
    except (OSError, ValueError):
        return {}


def save(artist: dict, key: str = "artist") -> None:
    f = config_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data[key] = artist
    f.write_text(json.dumps(data, indent=1), encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass


def describe(cfg: dict) -> str:
    kind = cfg.get("kind", "none")
    if kind == "none" or not kind:
        return "no model (the Artist is left out of automated games)"
    if kind == "packaged":
        return "the packaged local model"
    if kind == "ollama":
        return f"Ollama model {cfg.get('model')} at {cfg.get('url')}"
    name = dict((k, n) for k, n, _ in PROVIDERS).get(kind, kind)
    return f"{name}, model {cfg.get('model') or 'default'}"


def describe_chat(cfg: dict) -> str:
    return "the local chat model (Qwen3 1.7B)" if cfg.get("kind") == "packaged" else "off"


# Questions ------------------------------------------------------------------------

def ask(prompt: str, choices: list[str] | None = None, default: str = "") -> str:
    while True:
        shown = f" [{default}]" if default else ""
        ans = input(f"{prompt}{shown}: ").strip() or default
        if not choices or ans in choices:
            return ans
        print(f"  Please type one of: {', '.join(choices)}")


def ollama_models(url: str) -> list[str]:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=5) as r:
            return [m["name"] for m in json.load(r).get("models", [])]
    except (OSError, ValueError):
        return []


def wizard() -> dict:
    """Ask how the automated storyteller should answer the Artist. Returns the settings."""
    print("""
The Artist may ask the Storyteller any yes/no question. The automated storyteller
needs a language model to understand the question. (The game engine, not the
model, decides the answer, so the model cannot lie.)

  1  No model   - the Artist is left out of automated games
  2  Local model - runs on this computer or your own network
  3  Cloud model - an online AI service (needs an API key)""")
    choice = ask("Choose", ["1", "2", "3"], "1")
    if choice == "1":
        return {"kind": "none"}
    if choice == "2":
        print("""
  a  The packaged botc-automod model (downloaded once, then runs here on the CPU)
  b  An Ollama server you already run""")
        if ask("Choose", ["a", "b"], "a") == "a":
            return {"kind": "packaged"}
        url = ask("Ollama address", default="http://localhost:11434")
        models = ollama_models(url)
        if models:
            print("  Models on that server:")
            for i, m in enumerate(models, 1):
                print(f"   {i:2}  {m}")
            pick = ask("Model number or name", default="1")
            model = models[int(pick) - 1] if pick.isdigit() and 0 < int(pick) <= len(models) else pick
        else:
            print("  (Could not list models there; type the name.)")
            model = ask("Model name", default="qwen3:4b")
        return {"kind": "ollama", "url": url, "model": model}
    print()
    for i, (_, name, _) in enumerate(PROVIDERS, 1):
        print(f"  {i}  {name}")
    k, name, default_model = PROVIDERS[int(ask("Provider", [str(i) for i in range(1, len(PROVIDERS) + 1)], "1")) - 1]
    cfg = {"kind": k}
    if k == "custom":
        cfg["url"] = ask("Server address (ending in /v1)", default="http://localhost:1234/v1")
    key = getpass.getpass(f"{name} API key (hidden; leave empty to use an environment variable): ").strip()
    cfg["api_key"] = key
    cfg["model"] = ask("Model", default=default_model)
    return cfg


def wizard_chat(artist: dict) -> dict:
    """Ask whether to run the small chat model. Not needed when the Artist's model can chat."""
    if artist.get("kind") not in ("none", "packaged", None, ""):
        return {"kind": "none"}
    print("""
Agents (computer players) and the helpful narrator can talk in their own words
with a small chat model. Without it, agents answer with fixed lines.

  1  No chat model
  2  The local chat model (Qwen3 1.7B: downloaded once, 1.1 GB; runs here on
     the CPU next to the Artist model and needs about 2.5 GB of memory)""")
    return {"kind": "packaged" if ask("Choose", ["1", "2"], "1") == "2" else "none"}
