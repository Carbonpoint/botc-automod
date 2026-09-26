"""Game files: one Markdown file per game, in three folders.

    DATA/games/running/    games in play; saved after each change, reloaded after a crash
    DATA/games/paused/     games the host paused; resume them from the Archive
    DATA/games/completed/  games that ended

A file is plain Markdown that people can read. It starts with a short
header, then a summary. At the end is a save block that the server reads
to resume the game. Copy a file to the same folder on another server, or
import it from the Archive page.

The summary of a running or paused game shows only public facts, so an
exported file does not spoil the game. The save block holds everything,
but it is compressed and base64-encoded: not readable at a glance, and
not encrypted. The summary of a completed game shows the whole Grimoire
and every player's notebook.
"""

from __future__ import annotations

import base64
import io
import pickle
import random
import re
import time
import zlib
from pathlib import Path

from .game import SCHEMA, Game, Player

FOLDERS = ("running", "paused", "completed")
SAVE_START = "```botc-save"
MAX_FILE = 5_000_000   # bytes; a long game is about 30 kB


class ArchiveError(Exception):
    """A game file that cannot be read. The message goes to the user."""


# The only classes a save block may contain. A normal unpickler runs any
# code a file asks for; this one refuses everything else.
_ALLOWED = {("botc_automod.game", "Game"): Game, ("botc_automod.game", "Player"): Player,
            ("random", "Random"): random.Random}


class _SafeUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        try:
            return _ALLOWED[(module, name)]
        except KeyError:
            raise ArchiveError(f"The save block contains a forbidden object ({module}.{name}).") from None


def unpickle(data: bytes) -> Game:
    try:
        g = _SafeUnpickler(io.BytesIO(data)).load()
    except ArchiveError:
        raise
    except Exception as e:
        raise ArchiveError(f"The save block is damaged ({e}).") from None
    if not isinstance(g, Game):
        raise ArchiveError("The save block does not hold a game.")
    if getattr(g, "schema", 1) != SCHEMA:
        raise ArchiveError("This game was saved by an older version of the server.")
    return g


def folder(data: Path, name: str) -> Path:
    return data / "games" / name


def status(g: Game, paused: bool = False) -> str:
    return "completed" if g.phase == "ended" else "paused" if paused else "running"


def _when(t: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t))


def file_name(g: Game) -> str:
    """The name of a paused or completed game's file: its start date and code."""
    return f"{time.strftime('%Y-%m-%d', time.localtime(g.created))}-{g.code}.md"


def free_path(d: Path, name: str) -> Path:
    """`name` in folder `d`, with -2, -3 ... added when a file has that name already."""
    p, n = d / name, 2
    while p.exists():
        p = d / f"{Path(name).stem}-{n}.md"
        n += 1
    return p


def _cell(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def to_markdown(g: Game, paused: bool = False) -> str:
    st = status(g, paused)
    ed = g.edition
    host = g.host.name if g.host else ""
    seated = g.seated()
    head = [
        "---",
        "botc-automod: 1",
        f"code: {g.code}",
        f"status: {st}",
        f"edition: {ed.name}",
        f"host: {host}",
        f"players: {len(seated) or len(g.players)}",
        f"started: {_when(g.created)}",
        f"saved: {_when(time.time())}",
        f"where: {g.label()}",
    ]
    if g.winner:
        head.append(f"winner: {g.winner}")
    head.append("---")
    out = head + ["", f"# {ed.name}: game {g.code}", ""]
    storyteller = " with a human storyteller" if g.mode == "human" else ""
    out.append(f"Hosted by {host}{storyteller}. Started {_when(g.created)}.")
    if st == "completed":
        who = "Nobody" if g.winner == "nobody" else f"{(g.winner or '').capitalize()}"
        out += ["", f"**{who} wins.** {g.win_reason}"]
    else:
        out += ["", f"**{st.capitalize()}** at {g.label()}."]

    out += ["", "## Players", ""]
    if st == "completed":
        out += ["| Seat | Player | Character | Team | Alive |", "|---|---|---|---|---|"]
        for p in seated:
            role = ed.roles[p.role].name if p.role else ""
            if p.role and p.shown and p.shown != p.role:
                role += f" (thought they were the {ed.roles[p.shown].name})"
            team = ed.alignment(p) if p.role else ""
            out.append(f"| {p.seat + 1} | {_cell(p.name)} | {_cell(role)} | {team} | {'yes' if p.alive else 'no'} |")
    else:
        out += ["| Seat | Player | Alive |", "|---|---|---|"]
        for p in seated:
            out.append(f"| {p.seat + 1} | {_cell(p.name)} | {'yes' if g.living(p) else 'no'} |")
    unseated = [p.name for p in g.players.values() if p.seat is None]
    if unseated:
        out += ["", "Not seated: " + ", ".join(unseated)]

    out += ["", "## Town log", ""]
    out += [f"- **{e['label']}**: {e['text']}" for e in g.public_log] or ["Nothing yet."]

    if st == "completed":
        out += ["", "## Notebooks", ""]
        for p in seated:
            out += [f"### {p.name}", ""]
            out += [f"- **{e['label']}**: {e['text']}" for e in p.log] or ["Empty."]
            out.append("")

    blob = base64.b64encode(zlib.compress(pickle.dumps(g), 9)).decode()
    lines = [blob[i:i + 76] for i in range(0, len(blob), 76)]
    out += ["", "## Save data", "",
            "The server reads this block to resume the game. Do not change it.", "",
            f"{SAVE_START} schema={SCHEMA}", *lines, "```", ""]
    return "\n".join(out)


def header(text: str) -> dict:
    """The key: value lines between the first two --- lines."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip()
    return meta


def from_markdown(text: str) -> Game:
    m = re.search(r"^```botc-save[^\n]*\n(.*?)^```", text, re.S | re.M)
    if not m:
        raise ArchiveError("This is not a game file: it has no save block.")
    try:
        data = zlib.decompress(base64.b64decode("".join(m.group(1).split()), validate=True))
    except Exception:
        raise ArchiveError("The save block is damaged.") from None
    return unpickle(data)


def write(path: Path, g: Game, paused: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(to_markdown(g, paused), encoding="utf-8")
    tmp.replace(path)


def listing(data: Path, name: str) -> list[dict]:
    """The files in one folder, newest first, with their headers."""
    d = folder(data, name)
    if not d.exists():
        return []
    rows = []
    for f in d.glob("*.md"):
        try:
            with f.open(encoding="utf-8") as fh:
                meta = header(fh.read(4096))
        except (OSError, UnicodeDecodeError):
            continue
        if meta.get("botc-automod"):
            rows.append({"file": f.name, **{k: meta.get(k, "") for k in
                         ("code", "edition", "host", "players", "started", "saved", "where", "winner")}})
    return sorted(rows, key=lambda r: r["started"], reverse=True)


def safe_name(name: str) -> str:
    """A file name from a request, with no way out of its folder."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.md", name):
        raise ArchiveError("Bad file name.")
    return name
