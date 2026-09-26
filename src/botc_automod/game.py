"""The automated storyteller: game state, phases, timers and votes.

Phase cycle:
    lobby -> [setup] -> night (stage A, stage B) -> day -> nominations
          -> [defense -> vote -> nominations]* -> night -> ...
          -> ended

Character rules live in the edition (editions/). This module never
looks at a character by name.

Two modes, chosen by the host in the lobby:
    auto   the engine is the storyteller; the host is also a player.
    human  the host is the storyteller and does not play. The engine
           still does the work, but the storyteller checks the deal
           (the "setup" phase), sees every night choice, and edits the
           night results ("review" stages) before players get them.
"""

from __future__ import annotations

import math
import re
import random
import secrets
import string
import time
from dataclasses import dataclass, field

from . import seating
from .decoys import decoy_task
from . import helper, keywords
from .narrator import THEMES, story
from .editions import EDITIONS, Edition

DEFAULT_SETTINGS = {
    "discussion": 300,       # s of free talk at the start of each day
    "nominations": 150,      # s the nomination floor stays open
    "nomination_gap": 60,    # s the floor reopens for after each vote
    "defense": 60,           # s for accusation and defence
    "vote": 30,              # s to cast votes
    "night_min": 20,         # s every night stage lasts at least (hides who acts)
    "night_max": 120,        # s before unanswered choices are made at random
    "misregister": 0.35,     # chance the Spy/Recluse registers falsely per check
    "mayor_bounce": 0.5,     # chance a night kill on the Mayor hits another player
    "pacifist_save": 0.5,    # chance an executed good player survives with the Pacifist
    "tinker_chance": 0.1,    # chance per night the Tinker dies
    "shabaloth_regurgitate": 0.3,  # chance per night the Shabaloth brings back a victim
    "demon_bluffs": 1,       # 1: the Demon gets 3 safe bluffs even with fewer than 7 players
    "karma": 1,              # 1: karma from night questions tilts the automod's random choices
    "narrator": 1,           # 1: at dawn a random player reads a story of the night before the day starts
    "anon_chat": 0,          # 1: players may send chat messages without their name
    "show_votes": 1,         # 1: during a vote every seat shows its vote as it comes in (skull yes, angel no)
    "irl_tasks": 0,          # 1: keyword tasks each day: meet another player in person (keywords.py)
    "helper": 0,             # helpful narrator: 0 off, 1 players marked as learning, 2 everyone (helper.py)
}
TOGGLES = {"demon_bluffs", "karma", "narrator", "irl_tasks", "anon_chat", "show_votes"}
CHANCES = {"misregister", "mayor_bounce", "pacifist_save", "tinker_chance", "shabaloth_regurgitate"}
SCHEMA = 2  # bump when saved games from older versions cannot load

LOBBY_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def _first_word(name: str) -> str:
    word = (name.split() or [""])[0].lower()
    return "".join(c for c in word if c.isalpha())


def _near(a: str, b: str) -> bool:
    """One letter added, dropped or changed."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    short, long = sorted((a, b), key=len)
    return any(long[:i] + long[i + 1:] == short for i in range(len(long)))


def _like(name: str, target: str, also: set[str]) -> bool:
    w = _first_word(name)
    return w in also or (w[:2] == target[:2] and _near(w, target))


def is_emma(name: str) -> bool:
    return _like(name, "emma", {"em", "emmy", "emmie", "emmi", "ems", "emms"})


def is_tommy(name: str) -> bool:
    return _like(name, "tommy", {"tom", "thomas", "tomas", "thom", "tommie", "tommi", "tomm", "tomy"})


def new_code(taken: set[str]) -> str:
    while True:
        code = "".join(secrets.choice(LOBBY_CODE_CHARS) for _ in range(4))
        if code not in taken:
            return code


@dataclass
class Player:
    id: str
    name: str
    token: str
    is_host: bool = False
    seat: int | None = None
    prefs: dict = field(default_factory=lambda: {"team": "any", "style": "any"})
    ready: bool = False
    role: str | None = None       # the true character
    shown: str | None = None      # the character the player believes they are
    alignment: str = ""           # good | evil; "" means the team of the true character
    gained: list = field(default_factory=list)  # abilities gained (Philosopher)
    alive: bool = True
    fake_dead: bool = False       # alive, but registers as dead (Zombuul)
    ghost_vote: bool = True
    connected: bool = False
    slayer_claimed: bool = False
    karma: int = 0                # +1 per right night question, -1 per wrong one
    agent: bool = False           # a computer player (agents.py)
    tasks: list = field(default_factory=list)
    log: list = field(default_factory=list)

    def note(self, label: str, text: str) -> None:
        self.log.append({"label": label, "text": text})


class GameError(Exception):
    """A player action the rules do not allow. The message goes to the player."""


class NameTaken(GameError):
    """The name belongs to a player already in this game."""


class Game:
    mode = "auto"          # class defaults keep older saved games loadable
    theme = "default"      # the narrator's setting (narrator.THEMES)
    artist_ready = False   # the server has a question translator for the Artist
    helper_llm = False     # the server has a language model that can write tips (helper.py)
    pending: dict | None = None

    def __init__(self, code: str, edition_id: str = "tb", seed: int | None = None):
        self.schema = SCHEMA
        self.code = code
        self.edition_id = edition_id
        self.rng = random.Random(seed)
        self.created = time.time()
        self.players: dict[str, Player] = {}
        self.settings = dict(DEFAULT_SETTINGS)
        self.room = {"shape": "circle", "seats": 8, "rows": 0, "cols": 0, "cells": []}
        self.layout = seating.layout("circle", seats=8)
        self.phase = "lobby"
        self.mode = "auto"
        self.theme = "default"
        self.pending = None                  # night results the storyteller is reviewing
        self.stage = ""
        self.night = 0
        self.day = 0
        self.deadline: float | None = None
        self.paused_left: float | None = None
        self.stage_started = 0.0
        self.estate: dict = {}               # edition-owned state
        self.tonight_deaths: list[str] = []
        self.executed_today: str | None = None
        self.nominators_today: set[str] = set()
        self.nominees_today: set[str] = set()
        self.current_nom: dict | None = None
        self.block: dict | None = None       # {"pid", "votes"} on the chopping block
        self.nom_history: list[dict] = []
        self.public_log: list[dict] = []
        self.script: list[dict] = []
        self.winner: str | None = None
        self.win_reason = ""
        self.version = 0

    # Helpers ---------------------------------------------------------------
    @property
    def edition(self) -> Edition:
        return EDITIONS[self.edition_id]

    @property
    def host(self) -> Player | None:
        return next((p for p in self.players.values() if p.is_host), None)

    def is_storyteller(self, pid: str) -> bool:
        return self.mode == "human" and self.p(pid).is_host

    def _need_storyteller(self) -> None:
        if self.mode != "human":
            raise GameError("Only a human storyteller can do that.")

    def _need_seat(self, p: Player) -> None:
        if p.seat is None:
            raise GameError("The storyteller does not play.")

    def seated(self) -> list[Player]:
        """Players in clockwise seat order."""
        return sorted((p for p in self.players.values() if p.seat is not None),
                      key=lambda p: p.seat)

    def alive(self) -> list[Player]:
        return [p for p in self.seated() if p.alive]

    def living(self, p: Player) -> bool:
        """Alive as everyone sees it: a fake-dead Zombuul counts as dead."""
        return p.alive and not p.fake_dead

    def p(self, pid: str) -> Player:
        try:
            return self.players[pid]
        except KeyError:
            raise GameError("No such player.") from None

    def label(self) -> str:
        if self.phase == "night":
            return f"Night {self.night}"
        if self.phase in ("day", "nominations", "defense", "vote"):
            return f"Day {self.day}"
        return self.phase.capitalize()

    def say(self, text: str) -> None:
        """A line for the host to read aloud. The host learns nothing secret from it."""
        self.script.append({"n": len(self.script) + 1, "label": self.label(), "text": text})

    def announce(self, text: str, read: bool = True) -> None:
        """A public event: in the town log, and read aloud by the host."""
        self.public_log.append({"label": self.label(), "text": text})
        if read:
            self.say(text)

    def kill(self, pid: str, cause: str) -> None:
        p = self.p(pid)
        if not p.alive:
            return
        p.alive = False
        if self.phase == "night":
            self.tonight_deaths.append(pid)

    # Timer -------------------------------------------------------------------
    def set_timer(self, seconds: float | None) -> None:
        self.paused_left = None
        self.deadline = None if seconds is None else time.time() + seconds

    def remaining(self) -> float | None:
        if self.paused_left is not None:
            return self.paused_left
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - time.time())

    # Lobby ---------------------------------------------------------------------
    def join(self, name: str, is_host: bool = False) -> Player:
        name = " ".join(name.split())[:24]
        if not name:
            raise GameError("Please enter a name.")
        if any(p.name.lower() == name.lower() for p in self.players.values()):
            raise NameTaken("That name is taken in this game.")
        if self.phase != "lobby":
            raise GameError("This game has already started.")
        if len(self.players) >= self.edition.max_players + 1:
            raise GameError("This game is full.")
        pid = secrets.token_hex(4)
        p = Player(id=pid, name=name, token=secrets.token_urlsafe(18), is_host=is_host)
        self.players[pid] = p
        return p

    def by_name(self, name: str) -> Player | None:
        name = " ".join(name.split()).lower()
        return next((p for p in self.players.values() if p.name.lower() == name), None)

    def rejoin(self, name: str) -> tuple[str, str]:
        """Return to the game as an existing player, for example after losing the page.

        In the lobby this works at once. After the start the host must approve it,
        because the player's private notebook is at stake. Returns ("token", token)
        or ("pending", request id).
        """
        p = self.by_name(name)
        if p is None:
            raise GameError("There is no player with that name here.")
        if p.agent:
            raise GameError(f"{p.name} is an agent. Please choose another name.")
        if p.connected:
            raise GameError(f"{p.name} is connected on another device. Close the game there first.")
        if self.phase == "lobby":
            p.token = secrets.token_urlsafe(18)
            return "token", p.token
        reqs = self.estate.setdefault("rejoins", {})
        rid = secrets.token_hex(4)
        reqs[rid] = {"pid": p.id, "name": p.name, "status": "pending"}
        return "pending", rid

    def rejoin_status(self, rid: str) -> dict:
        req = self.estate.get("rejoins", {}).get(rid)
        if req is None:
            raise GameError("Unknown request.")
        if req["status"] == "approved":
            p = self.p(req["pid"])
            del self.estate["rejoins"][rid]
            return {"status": "approved", "token": p.token}
        return {"status": req["status"]}

    def answer_rejoin(self, rid: str, allow: bool) -> None:
        req = self.estate.get("rejoins", {}).get(rid)
        if req is None or req["status"] != "pending":
            raise GameError("That request is already answered.")
        if allow:
            p = self.p(req["pid"])
            p.token = secrets.token_urlsafe(18)  # the old device's token stops working
            req["status"] = "approved"
        else:
            req["status"] = "denied"

    def leave(self, pid: str) -> None:
        """Leave the lobby, which frees the name and the seat."""
        p = self.p(pid)
        if self.phase == "lobby" and not p.is_host:
            del self.players[pid]

    def set_room(self, shape: str, seats: int = 0, rows: int = 0, cols: int = 0,
                 cells: list | None = None) -> None:
        if self.phase != "lobby":
            raise GameError("The room can only change in the lobby.")
        if shape not in seating.SHAPES:
            raise GameError("Unknown room shape.")
        if shape == "grid":
            rows, cols = int(rows), int(cols)
            if not (1 <= rows <= 12 and 1 <= cols <= 12):
                raise GameError("The grid must be 1 to 12 rows and columns.")
            cells = [[int(r), int(c)] for r, c in (cells or [])]
            if len(cells) != len({tuple(c) for c in cells}):
                raise GameError("A grid cell is selected twice.")
            if any(not (0 <= r < rows and 0 <= c < cols) for r, c in cells):
                raise GameError("A selected cell is outside the grid.")
            seats = len(cells)
        seats = int(seats)
        if not (self.edition.min_players <= seats <= 20):
            raise GameError(f"A room needs {self.edition.min_players} to 20 seats.")
        self.room = {"shape": shape, "seats": seats, "rows": rows, "cols": cols, "cells": cells or []}
        self.layout = seating.layout(shape, seats=seats, rows=rows, cols=cols, cells=cells)
        for p in self.players.values():
            if p.seat is not None and p.seat >= seats:
                p.seat = None

    def set_edition(self, edition_id: str) -> None:
        if self.phase != "lobby":
            raise GameError("The edition is fixed once the game starts.")
        if edition_id not in EDITIONS:
            raise GameError("Unknown edition.")
        self.edition_id = edition_id

    def set_theme(self, theme: str) -> None:
        if self.phase != "lobby":
            raise GameError("The theme is fixed once the game starts.")
        if theme not in THEMES:
            raise GameError("Unknown theme.")
        self.theme = theme

    def set_mode(self, mode: str) -> None:
        if self.phase != "lobby":
            raise GameError("The storyteller mode is fixed once the game starts.")
        if mode not in ("auto", "human"):
            raise GameError("Unknown storyteller mode.")
        self.mode = mode
        if mode == "human" and self.host:
            self.host.seat = None
            self.host.ready = True

    def claim_seat(self, pid: str, seat: int | None) -> None:
        if self.phase != "lobby":
            raise GameError("Seats are fixed once the game starts.")
        p = self.p(pid)
        if self.is_storyteller(pid) and seat is not None:
            raise GameError("The storyteller does not take a seat.")
        if seat is None:
            p.seat = None
            return
        seat = int(seat)
        if not 0 <= seat < len(self.layout):
            raise GameError("No such seat.")
        if any(o.seat == seat and o.id != pid for o in self.players.values()):
            raise GameError("Someone already sits there.")
        p.seat = seat

    def set_prefs(self, pid: str, team: str, style: str) -> None:
        if self.phase != "lobby":
            raise GameError("The characters are already dealt.")
        if team not in ("good", "evil", "any") or style not in ("chill", "think", "any"):
            raise GameError("Unknown preference.")
        p = self.p(pid)
        p.prefs = {"team": team, "style": style}
        p.ready = True

    def add_agent(self, seat: int | None = None) -> Player:
        """Seat a computer player (agents.py) in an empty seat."""
        from .agents import new_name

        if self.phase != "lobby":
            raise GameError("Agents can only join in the lobby.")
        taken = {p.seat for p in self.players.values() if p.seat is not None}
        free = [s for s in range(len(self.layout)) if s not in taken]
        if seat is None:
            if not free:
                raise GameError("There is no empty seat.")
            seat = free[0]
        elif seat not in free:
            raise GameError("That seat is taken.")
        p = self.join(new_name(self))
        p.agent = True
        self.claim_seat(p.id, seat)
        return p

    def fill_with_agents(self) -> int:
        n = 0
        while True:
            try:
                self.add_agent()
            except GameError:
                return n
            n += 1

    def kick(self, pid: str) -> None:
        if self.phase != "lobby":
            raise GameError("Players can only be removed in the lobby.")
        p = self.p(pid)
        if p.is_host:
            raise GameError("The host cannot remove themself.")
        del self.players[pid]

    def start(self) -> None:
        if self.phase != "lobby":
            raise GameError("The game has already started.")
        unseated = [p.name for p in self.players.values() if p.seat is None and not self.is_storyteller(p.id)]
        if unseated:
            raise GameError("Not seated yet: " + ", ".join(unseated))
        n = len(self.seated())
        ed = self.edition
        if not ed.min_players <= n <= ed.max_players:
            raise GameError(f"{ed.name} needs {ed.min_players} to {ed.max_players} players; there are {n}.")
        ed.setup(self)
        if self.mode == "human":
            self.phase = "setup"
            self.say("The Storyteller is preparing the Grimoire. Please wait.")
            return
        self._reveal_and_begin()

    def begin_game(self) -> None:
        """The human storyteller has checked the deal: reveal and start night 1."""
        if self.phase != "setup":
            raise GameError("The game is not waiting for the Storyteller.")
        self._reveal_and_begin()

    def _reveal_and_begin(self) -> None:
        ed = self.edition
        for p in self.seated():
            role = ed.roles[p.shown]
            p.note("Setup", f"You are the {role.name}. {role.ability}")
        self.announce(f"Welcome to Blood on the Clocktower: {ed.name}. There are {len(self.seated())} players.")
        self.say("Everyone: look at your phone in private to learn your character. "
                 "Never show your screen to anyone.")
        self.begin_night()

    # Night -----------------------------------------------------------------------
    def begin_night(self) -> None:
        keywords.close(self)
        self.phase = "night"
        self.night += 1
        self.tonight_deaths = []
        self.current_nom = None
        self.edition.on_dusk(self)
        self.say(f"Night {self.night} falls. Everyone, pick up your phone and do your night task. "
                 "Keep your screen hidden. Put your phone face down when it says you are done.")
        self._start_stage("A", self.edition.stage_a(self))

    def _start_stage(self, stage: str, tasks: dict[str, list[dict]]) -> None:
        self.stage = stage
        n = 0
        for p in self.seated():
            queue = [t for t in tasks.get(p.id, []) if self._fits(t)]
            if stage == "A":
                queue = queue or [decoy_task(self.rng)]
            else:
                # Everyone ends the night with one scored question: the same karma chance for all.
                queue.append({**decoy_task(self.rng), "scored": True, "title": "Night question"})
            for t in queue:
                n += 1
                t.setdefault("key", t["kind"])
                t["id"] = f"{self.night}{stage}{n}"
                t["done"] = False
                t["response"] = None
                if t["kind"] == "info":
                    for line in t["lines"]:
                        p.note(self.label(), line)
            p.tasks = queue
        self.stage_started = time.time()
        self.set_timer(self.settings["night_max"])

    @staticmethod
    def _fits(t: dict) -> bool:
        """Shrink a choice when too few players remain; drop it when none do."""
        if t["kind"] == "choose" and len(t["candidates"]) < t["pick"]:
            if not t["candidates"]:
                return bool(t.get("allow_none"))
            t["pick"] = len(t["candidates"])
        if t["kind"] == "player_character" and not t["candidates"]:
            return False
        return True

    def submit_task(self, pid: str, task_id: str, response) -> None:
        if self.phase != "night":
            raise GameError("It is not night.")
        p = self.p(pid)
        task = next((t for t in p.tasks if t["id"] == task_id), None)
        if task is None or task["done"]:
            return  # a double tap, or an answer that arrived after the stage ended
        if task["kind"] == "choose":
            picks = [] if response is None else response if isinstance(response, list) else [response]
            if not (task.get("allow_none") and not picks):
                if len(picks) != task["pick"] or len(set(picks)) != len(picks):
                    raise GameError(f"Choose exactly {task['pick']} player(s).")
                if any(x not in task["candidates"] for x in picks):
                    raise GameError("You cannot choose that player.")
            task["response"] = picks
        elif task["kind"] == "character":
            ids = [o["id"] for o in task["options"]]
            if response is None and task.get("allow_none"):
                task["response"] = None
            elif response in ids:
                task["response"] = response
            else:
                raise GameError("Choose a character.")
        elif task["kind"] == "player_character":
            if not isinstance(response, dict) or response.get("player") not in task["candidates"] \
                    or response.get("character") not in [o["id"] for o in task["options"]]:
                raise GameError("Choose a player and a character.")
            task["response"] = {"player": response["player"], "character": response["character"]}
        elif task["kind"] == "decoy":
            if response not in task["options"]:
                raise GameError("Tap one of the answers.")
            task["response"] = response
            if task.get("scored"):
                right = response == task["answer"]
                p.karma += 1 if right else -1
                task["result"] = "right" if right else "wrong"
        else:
            task["response"] = True
        task["done"] = True

    def _stage_done(self) -> bool:
        return all(t["done"] for p in self.seated() for t in p.tasks)

    def _finish_stage(self) -> None:
        answers: dict[str, dict] = {}
        for p in self.seated():
            for t in p.tasks:
                if not t["done"]:
                    self._auto_answer(p, t)
                t["done"] = True
                if t["kind"] in ("choose", "character", "player_character"):
                    answers.setdefault(p.id, {})[t["key"]] = t["response"]
            p.tasks = []
        if self.stage == "A":
            tasks = self.edition.resolve_a(self, answers)
            if self.mode == "human":
                chosen = [{"name": self.p(pid).name, "key": key, "picks": self._describe(picks)}
                          for pid, keys in answers.items() for key, picks in keys.items()]
                self._review("review", {"tasks": dict(tasks), "choices": chosen})
            else:
                self._start_stage("B", tasks)
        else:
            messages = self.edition.resolve_b(self, answers) or {}
            if self.mode == "human" and messages:
                self._review("review_b", {"messages": dict(messages)})
            else:
                self._deliver(messages)
                self.dawn()

    def _describe(self, answer) -> list[str]:
        """A night answer in words, for the storyteller."""
        roles = self.edition.roles
        if not answer:
            return ["no one"]
        if isinstance(answer, str):
            return [roles[answer].name if answer in roles else answer]
        if isinstance(answer, dict):
            return [f"{self.p(answer['player']).name} as the {roles[answer['character']].name}"]
        return [self.p(x).name for x in answer]

    def _auto_answer(self, p: Player, t: dict) -> None:
        """Time ran out: optional abilities pass, required ones choose at random."""
        kind, rng = t["kind"], self.rng
        if kind == "choose":
            t["response"] = [] if t.get("allow_none") else rng.sample(t["candidates"], t["pick"])
            text = ", ".join(self.p(x).name for x in t["response"]) or "no one"
        elif kind == "character":
            t["response"] = None if t.get("allow_none") else rng.choice(t["options"])["id"]
            text = t["response"] or "no one"
        elif kind == "player_character":
            t["response"] = {"player": rng.choice(t["candidates"]), "character": rng.choice(t["options"])["id"]}
            text = self.p(t["response"]["player"]).name
        else:
            return
        p.note(self.label(), f"Time ran out, so a choice was made for you: {text}.")

    def _review(self, stage: str, pending: dict) -> None:
        """Hold the night results for the human storyteller. No timer runs."""
        self.stage = stage
        self.pending = pending
        self.set_timer(None)

    def _deliver(self, messages: dict[str, list[str]]) -> None:
        for pid, lines in messages.items():
            for line in lines:
                self.p(pid).note(self.label(), line)

    def edit_pending(self, pid: str, index: int, lines: list[str]) -> None:
        self._need_storyteller()
        lines = [str(x).strip() for x in lines if str(x).strip()]
        if self.stage == "review":
            tasks = self.pending["tasks"].get(pid, [])
            if not 0 <= index < len(tasks) or tasks[index]["kind"] != "info":
                raise GameError("There is no such message.")
            if lines:
                tasks[index]["lines"] = lines
            else:
                tasks.pop(index)
        elif self.stage == "review_b":
            if lines:
                self.pending["messages"][pid] = lines
            else:
                self.pending["messages"].pop(pid, None)
        else:
            raise GameError("There are no night results to edit now.")

    def add_pending(self, pid: str, text: str) -> None:
        self._need_storyteller()
        self._need_seat(self.p(pid))
        text = str(text).strip()
        if not text:
            raise GameError("The message is empty.")
        if self.stage == "review":
            self.pending["tasks"].setdefault(pid, []).append(
                {"kind": "info", "key": "storyteller", "title": "The Storyteller", "lines": [text]})
        elif self.stage == "review_b":
            self.pending["messages"].setdefault(pid, []).append(text)
        else:
            raise GameError("There are no night results to add to now.")

    def send_pending(self) -> None:
        self._need_storyteller()
        pending, self.pending = self.pending, None
        if self.stage == "review":
            self._start_stage("B", pending["tasks"])
        elif self.stage == "review_b":
            self._deliver(pending["messages"])
            self.dawn()
        else:
            raise GameError("There are no night results to send now.")

    # Storyteller powers --------------------------------------------------------------
    def set_character(self, pid: str, role: str, shown: str | None = None) -> None:
        self._need_storyteller()
        p = self.p(pid)
        self._need_seat(p)
        roles = self.edition.roles
        if role not in roles:
            raise GameError("Unknown character.")
        if role == "drunk":
            shown = shown or p.shown
            if shown not in roles or roles[shown].type != "townsfolk":
                raise GameError("The Drunk must believe they are a Townsfolk.")
        else:
            shown = role
        changed = p.shown != shown
        p.role, p.shown = role, shown
        if self.phase not in ("lobby", "setup") and changed:
            p.note("Storyteller", f"Your character has changed. You are now the {roles[shown].name}. "
                   f"{roles[shown].ability}")

    def st_set(self, key: str, value) -> None:
        self._need_storyteller()
        self.edition.st_set(self, key, value)

    def st_kill(self, pid: str) -> None:
        self._need_storyteller()
        p = self.p(pid)
        self._need_seat(p)
        if not p.alive:
            raise GameError(f"{p.name} is already dead.")
        self.kill(pid, "storyteller")
        if self.phase != "night":
            self.public_log.append({"label": self.label(), "text": f"{p.name} dies."})

    def st_revive(self, pid: str) -> None:
        self._need_storyteller()
        p = self.p(pid)
        if p.alive:
            raise GameError(f"{p.name} is alive.")
        p.alive = True
        p.ghost_vote = True
        if pid in self.tonight_deaths:
            self.tonight_deaths.remove(pid)
        elif self.phase != "night":
            self.public_log.append({"label": self.label(), "text": f"{p.name} is alive again."})

    def st_message(self, pid: str, text: str) -> None:
        self._need_storyteller()
        text = str(text).strip()
        if not text:
            raise GameError("The message is empty.")
        self.p(pid).note("Storyteller", text)

    def st_answer(self, req_id: str, text: str) -> None:
        """Answer a private request (Artist, Savant) and clear it."""
        self._need_storyteller()
        reqs = self.estate.get("requests", [])
        req = next((r for r in reqs if r["id"] == req_id), None)
        if not req:
            raise GameError("That request is already answered.")
        text = str(text).strip()
        if text:
            self.p(req["pid"]).note("Storyteller", f"{req['kind']}: {text}")
        reqs.remove(req)

    def st_execute(self, pid: str) -> None:
        """Execute a player now (madness). It is the day's execution, so the day ends."""
        self._need_storyteller()
        p = self.p(pid)
        self._need_seat(p)
        if self.phase not in ("day", "nominations", "defense", "vote"):
            raise GameError("Executions happen during the day.")
        if self.executed_today:
            raise GameError("There has already been an execution today.")
        self.current_nom = None
        self.block = {"pid": pid, "votes": 0}
        self.announce(f"The Storyteller executes {p.name}.", read=False)
        self.end_day()

    def st_win(self, team: str, reason: str = "") -> None:
        self._need_storyteller()
        if team not in ("good", "evil"):
            raise GameError("The winner is good or evil.")
        if self.phase in ("lobby", "ended"):
            raise GameError("There is no game running.")
        self.winner, self.win_reason = team, reason or "The Storyteller has decided."
        self._check_win()

    def dawn(self) -> None:
        self.phase = "day"
        self.stage = ""
        self.day = self.night
        self.executed_today = None
        self.nominators_today = set()
        self.nominees_today = set()
        self.block = None
        self.nom_history = []
        deaths = [self.p(x).name for x in self.tonight_deaths]
        self.tonight_deaths = []
        self.say("Dawn breaks. Everyone, put your phone down and open your eyes.")
        facts = []
        if deaths:
            facts.append(" and ".join(deaths) + " died in the night.")
        elif self.night > 1:
            facts.append("Nobody died last night.")
        facts += self.edition.on_dawn(self)
        for line in facts:
            self.announce(line)
        if self._check_win():
            return
        if self.settings.get("narrator", 1) and self.seated():
            self._start_narration(deaths, facts)
            return
        self._start_day()

    def _start_day(self) -> None:
        self.stage = ""
        self.say(f"Day {self.day} begins. Talk freely. Nominations open when the timer ends.")
        self.set_timer(self.settings["discussion"])
        keywords.assign(self)

    # Chat ----------------------------------------------------------------------------
    # Messages live in estate["chat"]. A message has "to": None for everyone, or one
    # player's id. Nobody can send at night: the town is asleep.
    CHAT_TEXT = 300
    CHAT_KEEP = 500

    def send_chat(self, pid: str, text: str, to: str | None = None, now: float | None = None,
                  anon: bool = False) -> dict:
        p = self.p(pid)
        if anon and not self.settings.get("anon_chat", 0):
            raise GameError("The host has turned off anonymous messages.")
        if self.phase == "night":
            raise GameError("Chat is closed at night. Talk again at dawn.")
        text = " ".join(str(text).split())[:self.CHAT_TEXT]
        if not text:
            raise GameError("Type a message first.")
        if to is not None and (to == pid or to not in self.players):
            raise GameError("Choose someone else to message.")
        now = now or time.time()
        last = self.estate.setdefault("chat_last", {})
        if now - last.get(pid, 0) < 1.0:
            raise GameError("Slow down a little.")
        last[pid] = now
        chat = self.estate.setdefault("chat", [])
        msg = {"id": (chat[-1]["id"] + 1) if chat else 1, "from": p.id, "to": to,
               "text": self.hide_keywords(text), "label": self.label(), "anon": bool(anon)}
        chat.append(msg)
        del chat[:-self.CHAT_KEEP]
        return msg

    def hide_keywords(self, text: str) -> str:
        """Today's secret keywords (keyword tasks) never travel through the chat."""
        for w in self.estate.get("irl", {}).get("words", {}).values():
            text = re.sub(rf"\b{re.escape(w)}\b", "•••", text, flags=re.I)
        return text

    def chat_for(self, pid: str) -> list[dict]:
        """The messages pid may see. An anonymous message loses its sender, except for the sender."""
        out = []
        for m in self.estate.get("chat", []):
            if m["to"] is None or pid in (m["to"], m["from"]):
                out.append({**m, "from": None} if m.get("anon") and m["from"] != pid else m)
        return out[-200:]

    # Helpful narrator (helper.py) ------------------------------------------------------
    def set_learner(self, pid: str, on: bool) -> None:
        """The host marks a player as learning the game (or not)."""
        self.p(pid)
        learners = self.estate.setdefault("learners", [])
        if on and pid not in learners:
            learners.append(pid)
        elif not on and pid in learners:
            learners.remove(pid)

    def take_tip(self, pid: str) -> tuple[list[str], str]:
        """Use today's tip. Returns the offline tip lines and the team the player believes in."""
        p = self.p(pid)
        if not helper.can_tip(self, p):
            raise GameError("The narrator has no tip for you right now.")
        self.estate.setdefault("tips", {})[pid] = self.day
        team = self._believed_team(p)
        return helper.offline_tip(self, p, team), team

    # Easter egg: Emma can quietly poison Tommy for the rest of the game ----------------
    # The poison is a normal status, so every rule treats Tommy as poisoned. Two
    # exceptions keep it hidden: the Spy's Grimoire does not show it, and it pauses
    # while Tommy is a Demon (a Demon whose kills always fail is easy to notice).
    def can_annoy(self, pid: str) -> bool:
        if self.estate.get("annoyed") or self.phase not in ("day", "nominations", "defense", "vote"):
            return False
        if not hasattr(self.edition, "add_status") or not is_emma(self.p(pid).name):
            return False
        return any(is_tommy(p.name) and p.id != pid for p in self.seated())

    def annoy(self, pid: str) -> None:
        if not self.can_annoy(pid):
            raise GameError("You cannot do that now.")
        for t in self.seated():
            if is_tommy(t.name) and t.id != pid:
                self.edition.add_status(self, t.id, "poisoned", "Emma", "never")
                self.estate["status"][-1]["prank"] = True
        self.estate["annoyed"] = True

    # Narration: a random player tells the story of the night -----------------------
    def _start_narration(self, deaths: list[str], facts: list[str]) -> None:
        seated = self.seated()
        pool = [p for p in seated if p.connected] or [p for p in seated if not p.agent] or seated
        narrator = secrets.choice(pool)   # not self.rng: the pick must say nothing and change nothing
        self.stage = "narration"
        self.estate["narration"] = {"pid": narrator.id, "deaths": deaths, "facts": facts,
                                    "story": self._story(deaths)}
        self.set_timer(None)
        self.say(f"{narrator.name} tells the story of the night. Listen.")

    def _story(self, deaths: list[str]) -> list[str]:
        return story(deaths, [p.name for p in self.seated() if self.living(p)], self.night, self.theme)

    def _need_narration(self, pid: str, host_may: bool) -> dict:
        n = self.estate.get("narration")
        if self.phase != "day" or self.stage != "narration" or n is None:
            raise GameError("The morning story is over.")
        if pid != n["pid"] and not (host_may and self.p(pid).is_host):
            raise GameError("Only the narrator can do that.")
        return n

    def new_story(self, pid: str) -> None:
        n = self._need_narration(pid, host_may=False)
        n["story"] = self._story(n["deaths"])

    def finish_narration(self, pid: str | None = None) -> None:
        """The narrator is done (or the host skips the story). The day starts."""
        if pid is not None:
            self._need_narration(pid, host_may=True)
        self.estate.pop("narration", None)
        self._start_day()

    # Day ---------------------------------------------------------------------------
    def open_nominations(self) -> None:
        self.phase = "nominations"
        self.current_nom = None
        needed = self.votes_needed()
        self.say("Nominations are open. To nominate, tap a player on the Town screen. "
                 f"An execution needs at least {needed} votes.")
        self.set_timer(self.settings["nominations"])

    def votes_needed(self) -> int:
        return math.ceil(sum(1 for p in self.seated() if self.living(p)) / 2)

    def nominate(self, pid: str, target: str) -> None:
        if self.phase != "nominations":
            raise GameError("Nominations are not open.")
        nominator, nominee = self.p(pid), self.p(target)
        self._need_seat(nominator)
        self._need_seat(nominee)
        if not self.living(nominator):
            raise GameError("Dead players cannot nominate.")
        if pid in self.nominators_today:
            raise GameError("You have already nominated today.")
        if target in self.nominees_today:
            raise GameError(f"{nominee.name} has already been nominated today.")
        self.nominators_today.add(pid)
        self.nominees_today.add(target)
        self.announce(f"{nominator.name} nominates {nominee.name}.")
        if self.edition.on_nominate(self, nominator, nominee):
            self.end_day(skip_block=True)
            return
        self.phase = "defense"
        self.current_nom = {"nominator": pid, "nominee": target, "votes": {}}
        self.say(f"{nominator.name}, say why. Then {nominee.name}, give your defence.")
        self.set_timer(self.settings["defense"])

    def start_vote(self) -> None:
        self.phase = "vote"
        nominee = self.p(self.current_nom["nominee"])
        self.say(f"Voting is open on {nominee.name}. Vote on your phone. "
                 f"{self.votes_needed()} votes are needed.")
        self.set_timer(self.settings["vote"])

    def can_vote(self, p: Player) -> bool:
        return self.living(p) or p.ghost_vote

    def vote(self, pid: str, yes: bool) -> None:
        if self.phase != "vote":
            raise GameError("There is no vote now.")
        p = self.p(pid)
        self._need_seat(p)
        if not self.can_vote(p):
            raise GameError("You have used your ghost vote.")
        self.current_nom["votes"][pid] = bool(yes)
        if all(v.id in self.current_nom["votes"] for v in self.seated() if self.can_vote(v)):
            self.close_vote()

    def close_vote(self) -> None:
        nom = self.current_nom
        votes = nom["votes"]
        for pid, yes in votes.items():
            p = self.p(pid)
            if yes and not self.living(p):
                p.ghost_vote = False
        count = self.edition.count_votes(self, votes)
        nominee = self.p(nom["nominee"])
        needed = self.votes_needed()
        yes_names = [self.p(x).name for x, v in votes.items() if v]
        record = {"nominator": nom["nominator"], "nominee": nom["nominee"], "votes": count,
                  "yes": [x for x, v in votes.items() if v]}
        self.nom_history.append(record)
        top = self.block["votes"] if self.block else self.estate.get("tie_votes", 0)
        who = ", ".join(yes_names) if yes_names else "nobody"
        if count >= needed and count > top:
            self.block = {"pid": nominee.id, "votes": count}
            self.estate["tie_votes"] = 0
            self.announce(f"{nominee.name} gets {count} votes ({who}). "
                          f"{nominee.name} is about to die.")
        elif count >= needed and count == top:
            self.block = None
            self.estate["tie_votes"] = count
            self.announce(f"{nominee.name} gets {count} votes ({who}). That is a tie: nobody is about to die.")
        else:
            self.announce(f"{nominee.name} gets {count} votes ({who}). Not enough.")
        self.current_nom = None
        self.phase = "nominations"
        self.set_timer(self.settings["nomination_gap"])

    def end_day(self, skip_block: bool = False) -> None:
        self.current_nom = None
        self.estate["tie_votes"] = 0
        if not skip_block:
            if self.block:
                p = self.p(self.block["pid"])
                self.executed_today = p.id
                self.announce(f"{p.name} is executed.")
                self.edition.on_execution(self, p)
            else:
                self.announce("Nobody is executed today.")
                self.edition.on_no_execution(self)
        self.block = None
        if self._check_win():
            return
        self.begin_night()

    def slayer_claim(self, pid: str, target: str) -> None:
        p = self.p(pid)
        if p.slayer_claimed:
            raise GameError("You have already claimed a Slayer shot.")
        self.day_action(pid, "slayer", {"target": target})

    def day_action(self, pid: str, key: str, payload: dict | None = None) -> None:
        """A day ability: Slayer shot, Gossip statement, Juggler guesses, Klutz choice..."""
        p = self.p(pid)
        self._need_seat(p)
        payload = payload or {}
        for k in ("target", "player"):
            if k in payload:
                self._need_seat(self.p(payload[k]))
        actions = {a["key"]: a for a in self.edition.day_actions(self, p)}
        action = actions.get(key)
        if action is None:
            raise GameError("You cannot do that now.")
        if not action.get("forced") and self.phase not in ("day", "nominations"):
            raise GameError("Day abilities are used during the day, outside a vote.")
        if "candidates" in action and payload.get("target") not in action["candidates"]:
            raise GameError("You cannot choose that player.")
        self.edition.do_day_action(self, p, key, payload)
        if self.phase not in ("ended", "lobby"):
            self._check_win()

    # Ending --------------------------------------------------------------------------
    def _check_win(self) -> bool:
        if self.winner is None:
            result = self.edition.check_win(self)
            if result is None:
                return False
            self.winner, self.win_reason = result
        self.phase = "ended"
        self.stage = ""
        self.set_timer(None)
        self.announce(f"{self.winner.capitalize()} wins! {self.win_reason}")
        self.say("The game is over. Everyone can now see the full Grimoire on their phone.")
        return True

    def force_end(self) -> None:
        self.winner = "nobody"
        self.win_reason = "The host ended the game."
        self._check_win()

    # Host controls ---------------------------------------------------------------------
    def advance(self) -> None:
        """Move on from the current phase (the host button, or the timer)."""
        if self.phase == "setup":
            self.begin_game()
        elif self.phase == "night":
            if self.stage in ("review", "review_b"):
                self.send_pending()
            else:
                self._finish_stage()
        elif self.phase == "day" and self.stage == "narration":
            self.finish_narration()
        elif self.phase == "day":
            self.open_nominations()
        elif self.phase == "nominations":
            self.end_day()
        elif self.phase == "defense":
            self.start_vote()
        elif self.phase == "vote":
            self.close_vote()

    def pause(self) -> None:
        if self.paused_left is None and self.deadline is not None:
            self.paused_left = self.remaining()
            self.deadline = None

    def resume(self) -> None:
        if self.paused_left is not None:
            self.deadline = time.time() + self.paused_left
            self.paused_left = None

    def add_time(self, seconds: float) -> None:
        if self.paused_left is not None:
            self.paused_left = max(0.0, self.paused_left + seconds)
        elif self.deadline is not None:
            self.deadline = max(time.time(), self.deadline + seconds)

    def set_setting(self, key: str, value) -> None:
        if key not in DEFAULT_SETTINGS:
            raise GameError("Unknown setting.")
        value = float(value)
        if key in TOGGLES:
            if value not in (0, 1):
                raise GameError("This option is on (1) or off (0).")
        elif key == "helper":
            if value not in (helper.OFF, helper.LEARNERS, helper.EVERYONE):
                raise GameError("The helpful narrator is off (0), for learners (1) or for everyone (2).")
        elif key in CHANCES:
            if not 0 <= value <= 1:
                raise GameError("A chance is between 0 and 1.")
        elif not 5 <= value <= 3600:
            raise GameError("A time is 5 to 3600 seconds.")
        self.settings[key] = value

    def tick(self, now: float | None = None) -> bool:
        """Advance on timeouts. Return True when the state changed."""
        now = now or time.time()
        if self.phase == "night":
            if self.stage not in ("A", "B"):
                return False  # the human storyteller is reviewing
            done_early = self._stage_done() and now >= self.stage_started + self.settings["night_min"]
            if done_early or (self.deadline is not None and now >= self.deadline):
                self._finish_stage()
                return True
            return False
        if self.phase in ("lobby", "setup", "ended") or self.deadline is None:
            return False
        if now >= self.deadline:
            self.advance()
            return True
        return False

    # Views -----------------------------------------------------------------------------
    def _public_alive(self, p: Player) -> bool:
        return self.living(p) or (self.phase == "night" and p.id in self.tonight_deaths)

    def grimoire(self) -> list[dict]:
        ed = self.edition
        return [{"id": p.id, "name": p.name, "role": ed.roles[p.role].card(),
                 "alignment": ed.alignment(p),
                 "shown": ed.roles[p.shown].name if p.shown != p.role else None,
                 "alive": p.alive} for p in self.seated() if p.role]

    def view_for(self, pid: str) -> dict:
        me = self.p(pid)
        ed = self.edition
        task = next((t for t in me.tasks if not t["done"]), None)
        if task:
            task = {k: v for k, v in task.items() if k not in ("answer", "response")}
        remaining = self.remaining()
        view = {
            "game": {"code": self.code, "edition": {"id": ed.id, "name": ed.name},
                     "anon_chat": bool(self.settings.get("anon_chat", 0)),
                     "theme": {"id": self.theme, "name": THEMES.get(self.theme, THEMES["default"])["name"]},
                     "mode": self.mode, "phase": self.phase, "artist_ready": self.artist_ready, "stage": self.stage, "label": self.label(),
                     "night": self.night, "day": self.day,
                     "timer": None if remaining is None else round(remaining),
                     "paused": self.paused_left is not None,
                     "winner": self.winner, "win_reason": self.win_reason,
                     "min_players": ed.min_players, "max_players": ed.max_players},
            "me": {"id": me.id, "name": me.name, "is_host": me.is_host, "seat": me.seat,
                   "prefs": me.prefs, "ready": me.ready,
                   "alive": self._public_alive(me), "ghost_vote": me.ghost_vote,
                   "role": ed.roles[me.shown].card() if me.shown and self.phase != "setup" else None,
                   "team": self._believed_team(me) if me.shown and self.phase != "setup" else None,
                   "day_actions": ed.day_actions(self, me) if me.seat is not None
                   and self.phase not in ("lobby", "setup", "ended") else [],
                   "storyteller": self.is_storyteller(pid),
                   "log": me.log, "slayer_claimed": me.slayer_claimed,
                   "karma": me.karma if self.settings.get("karma", 1) else None,
                   "last_answer": self._last_answer(me),
                   "bluffs": ed.bluffs_for(self, me) if self.phase not in ("lobby", "setup") else [],
                   "night_done": self.phase == "night" and task is None,
                   "annoy": self.can_annoy(pid),
                   "irl": keywords.view(self, pid),
                   "tip": {"can": helper.can_tip(self, me), "ask": self.helper_llm,
                           "on": helper.mode(self) == helper.EVERYONE
                           or (helper.mode(self) == helper.LEARNERS and helper.is_learner(self, pid))}},
            "task": task,
            "room": self.room, "layout": self.layout,
            "players": [{"id": p.id, "name": p.name, "seat": p.seat, "alive": self._public_alive(p),
                         "ghost_vote": p.ghost_vote, "connected": p.connected,
                         "is_host": p.is_host, "ready": p.ready, "agent": p.agent}
                        for p in sorted(self.players.values(), key=lambda p: (p.seat is None, p.seat or 0))],
            "day": {"nominators": sorted(self.nominators_today), "nominees": sorted(self.nominees_today),
                    "current": self._nom_view(pid), "block": self.block,
                    "needed": self.votes_needed() if self.phase != "lobby" else 0,
                    "history": self.nom_history},
            "public_log": self.public_log[-60:],
            "chat": self.chat_for(pid),
        }
        rejoins = [{"id": k, "name": v["name"]} for k, v in self.estate.get("rejoins", {}).items()
                   if v["status"] == "pending" and v["pid"] != pid
                   and (me.is_host or self.p(v["pid"]).is_host)]
        view["rejoins"] = rejoins
        if me.is_host:
            view["host"] = {"script": self.script[-40:], "settings": self.settings,
                            "learners": list(self.estate.get("learners", []))}
        n = self.estate.get("narration") if self.stage == "narration" else None
        if n:
            view["narration"] = {"narrator": n["pid"]}
            if n["pid"] == pid:
                view["narration"].update(story=n["story"], facts=n["facts"])
        if self.is_storyteller(pid) and self.phase != "lobby":
            view["st"] = self._storyteller_view()
        if self.phase == "ended":
            view["grimoire"] = self.grimoire()
        return view

    @staticmethod
    def _last_answer(p: Player) -> str | None:
        done = [t for t in p.tasks if t.get("scored") and t["done"]]
        return done[-1].get("result") if done else None

    def _believed_team(self, p: Player) -> str:
        """The team the player believes they are on (a Lunatic thinks evil)."""
        if p.role != p.shown and p.role in ("drunk", "lunatic"):
            return self.edition.roles[p.shown].team
        return self.edition.alignment(p)

    def _storyteller_view(self) -> dict:
        ed = self.edition
        name = lambda pid: self.p(pid).name if pid in self.players else "?"

        def said(t: dict):
            r = t.get("response")
            if not t["done"]:
                return None
            if t["kind"] == "choose":
                return ", ".join(name(x) for x in r)
            return r if t["kind"] == "decoy" else "read"

        choices = []
        if self.phase == "night" and self.stage in ("A", "B"):
            for p in self.seated():
                real = [t for t in p.tasks if t["kind"] != "decoy"]
                choices.append({"pid": p.id, "name": p.name, "decoy": not real,
                                "done": all(t["done"] for t in p.tasks),
                                "tasks": [{"title": t["title"], "kind": t["kind"], "text": t.get("text", ""),
                                           "lines": t.get("lines", []), "answer": said(t)} for t in real]})
        pending = []
        if self.stage == "review":
            for pid, tasks in self.pending["tasks"].items():
                for i, t in enumerate(tasks):
                    pending.append({"pid": pid, "name": name(pid), "index": i, "kind": t["kind"],
                                    "title": t["title"], "lines": t.get("lines", []), "text": t.get("text", "")})
        elif self.stage == "review_b":
            for pid, lines in self.pending["messages"].items():
                pending.append({"pid": pid, "name": name(pid), "index": 0, "kind": "info",
                                "title": "Message", "lines": lines, "text": ""})
        return {
            "grimoire": [{"id": p.id, "name": p.name, "seat": p.seat, "role": p.role, "shown": p.shown,
                          "team": ed.alignment(p), "alive": p.alive, "ghost_vote": p.ghost_vote,
                          "notes": ed.player_notes(self, p), "karma": p.karma}
                         for p in self.seated()],
            "requests": self.estate.get("requests", []),
            "status": ed.st_status(self),
            "choices": choices,
            "pending": pending,
            "tonight_deaths": [name(x) for x in self.tonight_deaths],
            "night_choices": (self.pending or {}).get("choices", []),
        }

    def _nom_view(self, pid: str) -> dict | None:
        if not self.current_nom:
            return None
        nom = self.current_nom
        v = {"nominator": nom["nominator"], "nominee": nom["nominee"],
             "voted": sorted(nom["votes"]), "my_vote": nom["votes"].get(pid)}
        if self.settings.get("show_votes", 1) and self.phase == "vote":
            v["votes"] = dict(nom["votes"])   # pid -> True (execute) / False
        return v
