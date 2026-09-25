"""The automated storyteller: game state, phases, timers and votes.

Phase cycle:
    lobby -> night (stage A, stage B) -> day -> nominations
          -> [defense -> vote -> nominations]* -> night -> ...
          -> ended

Character rules live in the edition (editions/). This module never
looks at a character by name.
"""

from __future__ import annotations

import math
import random
import secrets
import string
import time
from dataclasses import dataclass, field

from . import seating
from .decoys import decoy_task
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
}

LOBBY_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ"


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
    alive: bool = True
    ghost_vote: bool = True
    connected: bool = False
    slayer_claimed: bool = False
    tasks: list = field(default_factory=list)
    log: list = field(default_factory=list)

    def note(self, label: str, text: str) -> None:
        self.log.append({"label": label, "text": text})


class GameError(Exception):
    """A player action the rules do not allow. The message goes to the player."""


class Game:
    def __init__(self, code: str, edition_id: str = "tb", seed: int | None = None):
        self.code = code
        self.edition_id = edition_id
        self.rng = random.Random(seed)
        self.created = time.time()
        self.players: dict[str, Player] = {}
        self.settings = dict(DEFAULT_SETTINGS)
        self.room = {"shape": "circle", "seats": 8, "rows": 0, "cols": 0, "cells": []}
        self.layout = seating.layout("circle", seats=8)
        self.phase = "lobby"
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

    def seated(self) -> list[Player]:
        """Players in clockwise seat order."""
        return sorted((p for p in self.players.values() if p.seat is not None),
                      key=lambda p: p.seat)

    def alive(self) -> list[Player]:
        return [p for p in self.seated() if p.alive]

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
        if self.phase != "lobby":
            raise GameError("This game has already started.")
        if any(p.name.lower() == name.lower() for p in self.players.values()):
            raise GameError("That name is taken in this game.")
        if len(self.players) >= self.edition.max_players:
            raise GameError("This game is full.")
        pid = secrets.token_hex(4)
        p = Player(id=pid, name=name, token=secrets.token_urlsafe(18), is_host=is_host)
        self.players[pid] = p
        return p

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

    def claim_seat(self, pid: str, seat: int | None) -> None:
        if self.phase != "lobby":
            raise GameError("Seats are fixed once the game starts.")
        p = self.p(pid)
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
        unseated = [p.name for p in self.players.values() if p.seat is None]
        if unseated:
            raise GameError("Not seated yet: " + ", ".join(unseated))
        n = len(self.players)
        ed = self.edition
        if not ed.min_players <= n <= ed.max_players:
            raise GameError(f"{ed.name} needs {ed.min_players} to {ed.max_players} players; there are {n}.")
        ed.setup(self)
        for p in self.players.values():
            role = ed.roles[p.shown]
            p.note("Setup", f"You are the {role.name}. {role.ability}")
        self.announce(f"Welcome to Blood on the Clocktower: {ed.name}. There are {n} players.")
        self.say("Everyone: look at your phone in private to learn your character. "
                 "Never show your screen to anyone.")
        self.begin_night()

    # Night -----------------------------------------------------------------------
    def begin_night(self) -> None:
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
            queue = tasks.get(p.id) or [decoy_task(self.rng)]
            for t in queue:
                n += 1
                t.setdefault("key", t["kind"])
                t["id"] = f"{self.night}{stage}{n}"
                t["done"] = False
                t["response"] = None
            p.tasks = queue
        self.stage_started = time.time()
        self.set_timer(self.settings["night_max"])

    def submit_task(self, pid: str, task_id: str, response) -> None:
        if self.phase != "night":
            raise GameError("It is not night.")
        p = self.p(pid)
        task = next((t for t in p.tasks if t["id"] == task_id), None)
        if task is None or task["done"]:
            return  # a double tap, or an answer that arrived after the stage ended
        if task["kind"] == "choose":
            picks = response if isinstance(response, list) else [response]
            if len(picks) != task["pick"] or len(set(picks)) != len(picks):
                raise GameError(f"Choose exactly {task['pick']} player(s).")
            if any(x not in task["candidates"] for x in picks):
                raise GameError("You cannot choose that player.")
            task["response"] = picks
        elif task["kind"] == "decoy":
            if response not in task["options"]:
                raise GameError("Tap one of the answers.")
            task["response"] = response
        else:
            task["response"] = True
        task["done"] = True

    def _stage_done(self) -> bool:
        return all(t["done"] for p in self.seated() for t in p.tasks)

    def _finish_stage(self) -> None:
        answers: dict[str, dict] = {}
        for p in self.seated():
            for t in p.tasks:
                if not t["done"] and t["kind"] == "choose":
                    t["response"] = self.rng.sample(t["candidates"], t["pick"])
                    p.note(self.label(), "Time ran out, so a choice was made for you: "
                           + ", ".join(self.p(x).name for x in t["response"]) + ".")
                t["done"] = True
                if t["kind"] == "choose":
                    answers.setdefault(p.id, {})[t["key"]] = t["response"]
            p.tasks = []
        if self.stage == "A":
            self._start_stage("B", self.edition.resolve_a(self, answers))
        else:
            self.edition.resolve_b(self, answers)
            self.dawn()

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
        if deaths:
            self.announce(" and ".join(deaths) + (" died" if len(deaths) > 1 else " died") + " in the night.")
        elif self.night > 1:
            self.announce("Nobody died last night.")
        if self._check_win():
            return
        self.say(f"Day {self.day} begins. Talk freely. Nominations open when the timer ends.")
        self.set_timer(self.settings["discussion"])

    # Day ---------------------------------------------------------------------------
    def open_nominations(self) -> None:
        self.phase = "nominations"
        self.current_nom = None
        needed = self.votes_needed()
        self.say("Nominations are open. To nominate, tap a player on the Town screen. "
                 f"An execution needs at least {needed} votes.")
        self.set_timer(self.settings["nominations"])

    def votes_needed(self) -> int:
        return math.ceil(len(self.alive()) / 2)

    def nominate(self, pid: str, target: str) -> None:
        if self.phase != "nominations":
            raise GameError("Nominations are not open.")
        nominator, nominee = self.p(pid), self.p(target)
        if not nominator.alive:
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
        return p.alive or p.ghost_vote

    def vote(self, pid: str, yes: bool) -> None:
        if self.phase != "vote":
            raise GameError("There is no vote now.")
        p = self.p(pid)
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
            if yes and not p.alive:
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
        if self.phase not in ("day", "nominations"):
            raise GameError("A Slayer shot can only be taken during the day, outside a vote.")
        p, t = self.p(pid), self.p(target)
        if not p.alive:
            raise GameError("Dead players cannot claim a Slayer shot.")
        if p.slayer_claimed:
            raise GameError("You have already claimed a Slayer shot.")
        p.slayer_claimed = True
        self.edition.slayer_shot(self, p, t)
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
        if self.phase == "night":
            self._finish_stage()
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
        if key in ("misregister", "mayor_bounce"):
            if not 0 <= value <= 1:
                raise GameError("A chance is between 0 and 1.")
        elif not 5 <= value <= 3600:
            raise GameError("A time is 5 to 3600 seconds.")
        self.settings[key] = value

    def tick(self, now: float | None = None) -> bool:
        """Advance on timeouts. Return True when the state changed."""
        now = now or time.time()
        if self.phase == "night":
            done_early = self._stage_done() and now >= self.stage_started + self.settings["night_min"]
            if done_early or (self.deadline is not None and now >= self.deadline):
                self._finish_stage()
                return True
            return False
        if self.phase in ("lobby", "ended") or self.deadline is None:
            return False
        if now >= self.deadline:
            self.advance()
            return True
        return False

    # Views -----------------------------------------------------------------------------
    def _public_alive(self, p: Player) -> bool:
        return p.alive or (self.phase == "night" and p.id in self.tonight_deaths)

    def grimoire(self) -> list[dict]:
        ed = self.edition
        return [{"id": p.id, "name": p.name, "role": ed.roles[p.role].card(),
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
                     "phase": self.phase, "stage": self.stage, "label": self.label(),
                     "night": self.night, "day": self.day,
                     "timer": None if remaining is None else round(remaining),
                     "paused": self.paused_left is not None,
                     "winner": self.winner, "win_reason": self.win_reason,
                     "min_players": ed.min_players, "max_players": ed.max_players},
            "me": {"id": me.id, "name": me.name, "is_host": me.is_host, "seat": me.seat,
                   "prefs": me.prefs, "ready": me.ready,
                   "alive": self._public_alive(me), "ghost_vote": me.ghost_vote,
                   "role": ed.roles[me.shown].card() if me.shown else None,
                   "log": me.log, "slayer_claimed": me.slayer_claimed,
                   "night_done": self.phase == "night" and task is None},
            "task": task,
            "room": self.room, "layout": self.layout,
            "players": [{"id": p.id, "name": p.name, "seat": p.seat, "alive": self._public_alive(p),
                         "ghost_vote": p.ghost_vote, "connected": p.connected,
                         "is_host": p.is_host, "ready": p.ready}
                        for p in sorted(self.players.values(), key=lambda p: (p.seat is None, p.seat or 0))],
            "day": {"nominators": sorted(self.nominators_today), "nominees": sorted(self.nominees_today),
                    "current": self._nom_view(pid), "block": self.block,
                    "needed": self.votes_needed() if self.phase != "lobby" else 0,
                    "history": self.nom_history},
            "public_log": self.public_log[-60:],
        }
        if me.is_host:
            view["host"] = {"script": self.script[-40:], "settings": self.settings}
        if self.phase == "ended":
            view["grimoire"] = self.grimoire()
        return view

    def _nom_view(self, pid: str) -> dict | None:
        if not self.current_nom:
            return None
        nom = self.current_nom
        return {"nominator": nom["nominator"], "nominee": nom["nominee"],
                "voted": sorted(nom["votes"]), "my_vote": nom["votes"].get(pid)}
