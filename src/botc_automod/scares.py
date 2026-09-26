"""Jump scares: a spooky screen, and the falling pipe sound, on one phone at a time.

Two host options:

    scares  0 off, 1 low (about once a game per player), 2 medium,
            3 high (about once a day per player)
    pipe    1 on: one player hears a falling metal pipe, about once a game.
            The host picks the player (estate["pipe_target"]). With no pick,
            it is the player named Tommy, if there is one.

At the start of each day (after the morning story) every human player may get
a scare at a random moment of the discussion, so phones never go off together.
The phone shows it only when nothing needs the player (static/app.js); an
unused scare is dropped at nightfall. The random source is not the game's rng,
so scares never change a game. State lives in game.estate["scares"].
"""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .game import Game

_rng = random.SystemRandom()

OFF, LOW, MEDIUM, HIGH = 0, 1, 2, 3
CHANCE = {LOW: 0.25, MEDIUM: 0.5, HIGH: 1.0}   # per player per day
PIPE_CHANCE = (0.3, 0.5, 1.0)                  # day 1, day 2, day 3 onward: once a game
EARLIEST, LATEST, GAP = 20, 240, 5             # s after the day starts; s between two phones


def pipe_target(game: Game) -> str | None:
    """The player who hears the pipe: the host's pick, else a seated Tommy."""
    from .game import is_tommy
    pick = game.estate.get("pipe_target")
    if pick in game.players:
        return pick
    return next((p.id for p in game.seated() if is_tommy(p.name) and not p.agent), None)


def set_pipe_target(game: Game, pid: str | None) -> None:
    if pid is not None:
        game.p(pid)
    game.estate["pipe_target"] = pid


def plan(game: Game, now: float | None = None) -> None:
    """A new day: choose who gets a scare today, and when."""
    now = now or time.time()
    st = game.estate.setdefault("scares", {"next": 1, "pipe_done": False})
    st["due"] = {}
    level = int(game.settings.get("scares", OFF))
    humans = [p for p in game.seated() if not p.agent]

    # Each scare gets its own slot, so no two phones go off together.
    slots = list(range(EARLIEST, LATEST, GAP))
    _rng.shuffle(slots)

    def add(pid: str, kind: str) -> None:
        st["due"].setdefault(pid, []).append({"id": st["next"], "kind": kind, "at": now + slots.pop()})
        st["next"] += 1

    if level in CHANCE:
        for p in humans:
            if _rng.random() < CHANCE[level]:
                add(p.id, "screen")
    target = pipe_target(game)
    if game.settings.get("pipe", 1) and not st["pipe_done"] and target and any(p.id == target for p in humans):
        if _rng.random() < PIPE_CHANCE[min(game.day, len(PIPE_CHANCE)) - 1]:
            add(target, "pipe")
            st["pipe_done"] = True


def clear(game: Game) -> None:
    """Night falls: unused scares are dropped."""
    st = game.estate.get("scares")
    if st:
        st["due"] = {}


def view(game: Game, pid: str, now: float | None = None) -> list[dict]:
    """This player's scares for today, with seconds until each one ("in")."""
    now = now or time.time()
    st = game.estate.get("scares") or {}
    return [{"id": s["id"], "kind": s["kind"], "in": max(0, round(s["at"] - now))}
            for s in st.get("due", {}).get(pid, [])]
