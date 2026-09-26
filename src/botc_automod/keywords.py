"""Keyword tasks: an in-person meeting game played alongside Blood on the Clocktower.

With the host's option "irl_tasks" on, each day starts with a keyword for
every human player (agents take no part). The players form one loop:
each player must meet the next one in person and get their keyword. Each
player learns their own keyword and who needs it.

    right keyword from your target      +2 karma
    3 wrong tries, or the day ends      -1 karma (once)
    another player's keyword, correct   +1 for you; -1 for its owner and
                                        for the player meant to get it
                                        (only after your own task is done)

Three wrong tries end your tries for the day. Keywords never travel
through the chat (Game.hide_keywords). Karma changes apply only with the
karma option on. State lives in game.estate["irl"].
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .game import Game, Player

TRIES = 3
WIN, MISS, SNOOP, LEAK = 2, -1, 1, -1
WORDS = """
acorn anchor apple arrow badger banjo barrel beacon bishop blanket bonfire bramble bucket
button cabbage candle canyon carrot castle cellar cherry chimney cinder clover cobweb comet
compass copper cricket crown dagger daisy dragon ember falcon feather fiddle forest fossil
garden ghost goblet granite harbor harvest hazel hedgehog helmet hermit honey hourglass
iceberg ivory jasper kettle lantern lemon lighthouse lizard locket maple marble meadow
mitten moonbeam mortar mushroom nectar nutmeg oyster paddle parsley pebble pepper pickle
pillow pirate plum pocket potion pumpkin quill raven ribbon riddle rocket saddle sapphire
scarecrow shadow shovel silver sparrow spindle squirrel teacup thimble thistle thunder
tulip turnip velvet walnut whistle willow window wizard yarrow zephyr
""".split()

_rng = random.SystemRandom()   # never the game's rng: tasks must not change the game


def on(game: Game) -> bool:
    return bool(game.settings.get("irl_tasks", 0))


def humans(game: Game) -> list[Player]:
    return [p for p in game.seated() if not getattr(p, "agent", False)]


def assign(game: Game) -> None:
    """A new loop and new keywords for today."""
    game.estate.pop("irl", None)
    people = humans(game)
    if not on(game) or len(people) < 2:
        return
    _rng.shuffle(people)
    words = _rng.sample(WORDS, len(people))
    st = game.estate["irl"] = {"day": game.day, "words": {}, "target": {}, "done": {}, "wrong": {},
                               "found": {}, "missed": []}
    for i, p in enumerate(people):
        st["words"][p.id] = words[i]
        st["target"][p.id] = people[(i + 1) % len(people)].id
    for p in people:
        receiver = next(x for x, t in st["target"].items() if t == p.id)
        p.note(game.label(), f"Keyword task: your keyword today is {st['words'][p.id].upper()}. "
                             f"{game.p(receiver).name} needs it: tell only them, in person. "
                             f"Your task: meet {game.p(st['target'][p.id]).name} and get their keyword.")


def active(game: Game) -> dict | None:
    st = game.estate.get("irl")
    return st if st and st["day"] == game.day else None


def _karma(game: Game, p: Player, delta: int) -> None:
    if game.settings.get("karma", 1):
        p.karma += delta


def submit(game: Game, pid: str, owner: str, word: str) -> str:
    """Enter `owner`'s keyword. Returns the message for the player."""
    from .game import GameError

    st = active(game)
    if st is None or game.phase not in ("day", "nominations", "defense", "vote") or game.stage == "narration":
        raise GameError("There is no keyword task now.")
    if pid not in st["words"]:
        raise GameError("You have no keyword task today.")
    if owner not in st["words"] or owner == pid:
        raise GameError("Choose another player who has a keyword today.")
    if st["wrong"].get(pid, 0) >= TRIES:
        raise GameError("You have no tries left today.")
    p, o = game.p(pid), game.p(owner)
    right = " ".join(str(word).split()).lower() == st["words"][owner]
    mine = owner == st["target"][pid]
    if mine and st["done"].get(pid):
        raise GameError(f"You already have {o.name}'s keyword.")
    if not mine:
        if not st["done"].get(pid):
            raise GameError(f"First get the keyword of {game.p(st['target'][pid]).name}.")
        if owner in st["found"].get(pid, []):
            raise GameError(f"You already found {o.name}'s keyword.")
    if not right:
        st["wrong"][pid] = st["wrong"].get(pid, 0) + 1
        left = TRIES - st["wrong"][pid]
        if left == 0 and not st["done"].get(pid) and pid not in st["missed"]:
            st["missed"].append(pid)
            _karma(game, p, MISS)
            p.note(game.label(), "Keyword task: no tries left today. You missed your keyword (karma −1).")
            return "Wrong. You have no tries left today (karma −1)."
        return f"Wrong. {left} {'try' if left == 1 else 'tries'} left today."
    if mine:
        st["done"][pid] = True
        _karma(game, p, WIN)
        p.note(game.label(), f"Keyword task: you got {o.name}'s keyword (karma +{WIN}). "
                             "You may now try other players' keywords.")
        return f"Right! Karma +{WIN}. You may now try other players' keywords."
    st["found"].setdefault(pid, []).append(owner)
    receiver = game.p(next(x for x, t in st["target"].items() if t == owner))
    _karma(game, p, SNOOP)
    p.note(game.label(), f"Keyword task: you found {o.name}'s keyword (karma +{SNOOP}).")
    for x in (o, receiver):
        _karma(game, x, LEAK)
        x.note(game.label(), f"Keyword task: someone else found {o.name}'s keyword (karma {LEAK}).")
    return f"Right! That was {o.name}'s keyword. Karma +{SNOOP}."


def close(game: Game) -> None:
    """The day ends: whoever did not get their keyword misses it."""
    st = game.estate.get("irl")
    if not st or st.get("closed"):
        return
    st["closed"] = True
    for pid in st["words"]:
        if not st["done"].get(pid) and pid not in st["missed"] and pid in game.players:
            st["missed"].append(pid)
            p = game.p(pid)
            _karma(game, p, MISS)
            p.note(game.label(), "Keyword task: the day ended before you got your keyword (karma −1).")


def view(game: Game, pid: str) -> dict | None:
    st = active(game)
    if st is None or pid not in st["words"] or st.get("closed"):
        return None
    receiver = next(x for x, t in st["target"].items() if t == pid)
    return {"word": st["words"][pid], "give_to": receiver, "target": st["target"][pid],
            "done": bool(st["done"].get(pid)), "left": TRIES - st["wrong"].get(pid, 0),
            "found": st["found"].get(pid, []), "players": [x for x in st["words"] if x != pid]}
