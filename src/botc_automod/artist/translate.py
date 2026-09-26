"""Translate an Artist's question into a query with a language model.

Backends:
    ollama     any Ollama server (local or on the LAN)
    openai     any OpenAI-compatible server: OpenAI, Google Gemini, OpenRouter,
               LM Studio, or the packaged model run by llama.cpp's llama-server
    anthropic  Claude, through the official `anthropic` SDK (optional install)

Every backend returns a validated query or None ("ask another question").
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

from .query import BadQuery, World, schema, validate

SYSTEM_FULL = """You translate a player's yes/no question in the game Blood on the Clocktower into one JSON query.
You never answer the question. Output only the JSON object.

Atoms:
{"op":"is_role","player":P,"role":R}        is P that exact character?
{"op":"is_type","player":P,"type":T}        T is townsfolk, outsider, minion or demon. "the demon" means type demon.
{"op":"is_team","player":P,"team":"good"|"evil"}   "can I trust P" means team good.
{"op":"in_play","role":R}                   is character R in the game?
{"op":"is_malfunctioning","player":P}       is P drunk or poisoned?
{"op":"count","of":X,"alive_only":bool,"cmp":C,"n":N}   X is a type, "good" or "evil"; C is one of == != >= <= > <.
Combinations: {"op":"or","args":[...]}, {"op":"and","args":[...]}, {"op":"not","arg":atom}. Args are atoms or not-atoms.
{"op":"unanswerable"} for anything that is not a yes/no question about the current game state: who/what/which/how many
questions, the future, strategy, the past, or anything outside the game.

P is a player name exactly as listed (fix typos), "me" for the asker, or "cw:NAME"/"ccw:NAME" for the player seated next to
NAME clockwise/counter-clockwise. "My left" is cw:me, "my right" is ccw:me. "My neighbours" means both cw:me and ccw:me.
R is a character id from the list.

Examples (players Ann, Ben, Cat, Dan; asker Ann):
"is ben the FT" -> {"op":"is_role","player":"Ben","role":"fortuneteller"}
"Is the demon Ben or Cat?" -> {"op":"or","args":[{"op":"is_type","player":"Ben","type":"demon"},{"op":"is_type","player":"Cat","type":"demon"}]}
"am I poisoned" -> {"op":"is_malfunctioning","player":"me"}
"Is the player to my left evil?" -> {"op":"is_team","player":"cw:me","team":"evil"}
"Are there at least 2 outsiders?" -> {"op":"count","of":"outsider","alive_only":false,"cmp":">=","n":2}
"Is Dan not the demon?" -> {"op":"not","arg":{"op":"is_type","player":"Dan","type":"demon"}}
"Who is the demon?" -> {"op":"unanswerable"}"""

SYSTEM_COMPACT = "Translate the Blood on the Clocktower yes/no question into a JSON query."


def user_message(world: World, asker: str, question: str) -> str:
    chars = ", ".join(f"{rid}={name}" for rid, (name, _) in sorted(world.roles.items()))
    return (f"Players (clockwise): {', '.join(s.name for s in world.seats)}\n"
            f"Asker: {asker}\nCharacters: {chars}\nQuestion: {question}")


def wrapped_schema(world: World) -> dict:
    """An object root: required by several providers' structured-output modes."""
    return {"type": "object", "properties": {"query": schema(world)}, "required": ["query"],
            "additionalProperties": False}


def extract_json(text: str) -> dict | None:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        depth += ch == "{"
        depth -= ch == "}"
        if depth == 0:
            try:
                return json.loads(text[start:i + 1])
            except ValueError:
                return None
    return None


class Translator:
    name = "none"
    compact = False
    can_chat = False   # can write free text (the helpful narrator); the packaged model cannot

    def complete(self, system: str, user: str, world: World) -> str:
        raise NotImplementedError

    def chat(self, system: str, user: str) -> str:
        """A short free-text answer. Only when can_chat."""
        raise NotImplementedError

    def translate(self, world: World, asker: str, question: str) -> tuple[dict | None, str]:
        """Return (validated query or None, raw model text)."""
        system = SYSTEM_COMPACT if self.compact else SYSTEM_FULL
        raw = self.complete(system, user_message(world, asker, question), world)
        data = extract_json(raw)
        if isinstance(data, dict) and "query" in data and "op" not in data:
            data = data["query"]
        try:
            return (validate(data, world, asker) if data is not None else None), raw
        except BadQuery:
            return None, raw


def _post(url: str, body: dict, headers: dict | None = None, timeout: float = 60) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json",
                                                                  **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


class OllamaTranslator(Translator):
    name = "ollama"
    can_chat = True

    def __init__(self, url: str, model: str, compact: bool = False, timeout: float = 120):
        self.url, self.model, self.compact, self.timeout = url.rstrip("/"), model, compact, timeout

    def complete(self, system: str, user: str, world: World) -> str:
        body = {"model": self.model, "stream": False, "think": False, "keep_alive": "10m",
                "format": wrapped_schema(world), "options": {"temperature": 0, "num_predict": 300},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        try:
            out = _post(f"{self.url}/api/chat", body, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            if e.code != 400:
                raise
            body.pop("think")  # older Ollama or a model without a thinking switch
            out = _post(f"{self.url}/api/chat", body, timeout=self.timeout)
        return out["message"]["content"]

    def chat(self, system: str, user: str) -> str:
        body = {"model": self.model, "stream": False, "think": False, "keep_alive": "10m",
                "options": {"temperature": 0.7, "num_predict": 200},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        try:
            out = _post(f"{self.url}/api/chat", body, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            if e.code != 400:
                raise
            body.pop("think")
            out = _post(f"{self.url}/api/chat", body, timeout=self.timeout)
        return out["message"]["content"]


class OpenAITranslator(Translator):
    """OpenAI-compatible chat completions (OpenAI, Gemini, OpenRouter, llama-server...)."""
    name = "openai"

    def __init__(self, base_url: str, model: str, api_key: str = "", compact: bool = False,
                 timeout: float = 120, use_schema: bool = True):
        self.base, self.model, self.key = base_url.rstrip("/"), model, api_key
        self.compact, self.timeout, self.use_schema = compact, timeout, use_schema
        self.can_chat = model != "packaged"   # the packaged model only translates questions

    def complete(self, system: str, user: str, world: World) -> str:
        body = {"model": self.model, "temperature": 0, "max_tokens": 300,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.use_schema:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "query", "schema": wrapped_schema(world)}}
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        try:
            out = _post(f"{self.base}/chat/completions", body, headers, self.timeout)
        except urllib.error.HTTPError as e:
            if e.code != 400 or not self.use_schema:
                raise
            self.use_schema = False  # this provider rejects the schema: rely on the prompt
            body.pop("response_format")
            out = _post(f"{self.base}/chat/completions", body, headers, self.timeout)
        return out["choices"][0]["message"]["content"] or ""

    def chat(self, system: str, user: str) -> str:
        body = {"model": self.model, "temperature": 0.7, "max_tokens": 200,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        out = _post(f"{self.base}/chat/completions", body, headers, self.timeout)
        return out["choices"][0]["message"]["content"] or ""


class AnthropicTranslator(Translator):
    """Claude via the official SDK (`pip install anthropic`)."""
    name = "anthropic"
    can_chat = True

    def __init__(self, api_key: str, model: str = "claude-opus-5"):
        import anthropic  # optional dependency

        self.client = anthropic.Anthropic(api_key=api_key or None)
        self.model = model

    def complete(self, system: str, user: str, world: World) -> str:
        kwargs = dict(
            model=self.model,
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "low",
                           "format": {"type": "json_schema", "schema": wrapped_schema(world)}},
        )
        return self._create(kwargs)

    def chat(self, system: str, user: str) -> str:
        # max_tokens leaves room for thinking; the prompt asks for 3 sentences at most.
        return self._create(dict(model=self.model, max_tokens=2000, system=system,
                                 messages=[{"role": "user", "content": user}],
                                 output_config={"effort": "low"}))

    def _create(self, kwargs: dict) -> str:
        if self.model in ("claude-opus-5", "claude-fable-5-1"):
            # Server-side fallback: if the model declines, the API reruns the request on
            # another model inside the same call.
            response = self.client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        else:
            response = self.client.messages.create(**kwargs)
        if response.stop_reason == "refusal":
            return ""
        return next((b.text for b in response.content if b.type == "text"), "")


# Cloud providers that speak the OpenAI API.
OPENAI_PROVIDERS = {
    "openai": ("https://api.openai.com/v1", "gpt-5-mini"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
    "openrouter": ("https://openrouter.ai/api/v1", "qwen/qwen3-8b"),
}


def make_translator(cfg: dict) -> Translator | None:
    """Build a translator from the saved config (see artist/config.py)."""
    kind = cfg.get("kind", "none")
    if kind == "ollama":
        return OllamaTranslator(cfg["url"], cfg["model"], compact=cfg.get("compact", False))
    if kind == "packaged":
        return OpenAITranslator(cfg.get("url", "http://127.0.0.1:8779/v1"), "packaged", compact=True,
                                use_schema=False)
    if kind == "anthropic":
        return AnthropicTranslator(cfg.get("api_key", ""), cfg.get("model") or "claude-opus-5")
    if kind in OPENAI_PROVIDERS or kind == "custom":
        base, model = OPENAI_PROVIDERS.get(kind, (cfg.get("url", ""), ""))
        return OpenAITranslator(cfg.get("url") or base, cfg.get("model") or model, cfg.get("api_key", ""))
    return None


def timed(t: Translator, world: World, asker: str, question: str) -> tuple[dict | None, str, float]:
    start = time.time()
    try:
        q, raw = t.translate(world, asker, question)
    except Exception as e:  # network or server error: treat as "ask another"
        return None, f"ERROR {e}", time.time() - start
    return q, raw, time.time() - start
