"""Karma arcade: small games on the start page that earn a little karma.

The games run in the browser (static/arcade.js). The server keeps the score
boards, gives the karma, and runs the shared pool table.

Karma from the arcade, per name, per day (local date):

    first finished round of the day (any game, a real try)   +1
    a new record on a game's board (top score of all time)   +1
    every POOL_PER_KARMA balls pocketed at the pool table     +1

The arcade gives at most DAILY_CAP karma per name per day. A night question
gives ±1 a night, so the arcade stays a small push, not the main source.

Scores come from the browser, so the server only rejects the impossible: a
score too high for the time the round took (RATE). This is a home LAN game.

Pool: one table for everyone. Anyone may take the next shot, but the last
shooter waits REPEAT_WAIT seconds unless someone else shoots first. A shot
names the table version it aimed at, so two shots at once cannot both land.
The server runs the physics and keeps the frames of the last shot, so every
phone can play it back.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

DAILY_CAP = 3
POOL_PER_KARMA = 3
BOARD_SIZE = 10
REPEAT_WAIT = 20.0

# game id -> (name, lowest score that counts as a real try, max score per second, slack)
GAMES = {
    "flappy": ("Flappy Bat", 3, 1.0, 2),
    "dino": ("Night Runner", 100, 15.0, 50),
    "odd": ("2047", 200, 300.0, 500),
    "blocks": ("Blocks", 100, 150.0, 400),
    "snake": ("Snake", 5, 3.0, 3),
}


class ArcadeError(Exception):
    pass


def today() -> str:
    return date.today().isoformat()


# ---------- pool physics ----------
# Table units: the play area is W x H, origin at the top-left corner.
W, H = 100.0, 50.0
R = 1.25                       # ball radius
POCKET_R = 2.6                 # a ball whose centre comes this close to a pocket drops
POCKETS = [(0, 0), (W / 2, -0.6), (W, 0), (0, H), (W / 2, H + 0.6), (W, H)]
MAX_SPEED = 160.0              # units per second at full power
FRICTION = 38.0                # units per second, lost each second
CUSHION = 0.8                  # speed kept after a cushion
DT = 1 / 240
FRAME_EVERY = 8                # one frame each 8 steps: 30 frames a second
MAX_TIME = 14.0


def rack() -> list[list[float] | None]:
    """Cue ball (index 0) and 15 balls in a triangle."""
    balls: list[list[float] | None] = [[W * 0.25, H / 2]]
    x0, gap = W * 0.72, R * 2 * 0.87 + 0.02
    for col in range(5):
        for row in range(col + 1):
            balls.append([x0 + col * gap, H / 2 + (row - col / 2) * (R * 2 + 0.02)])
    return balls


def simulate(balls: list[list[float] | None], angle: float, power: float):
    """Hit the cue ball. Returns (end positions, frames, pocketed ball indexes in order)."""
    pos = [None if b is None else [b[0], b[1]] for b in balls]
    vel = [[0.0, 0.0] for _ in pos]
    power = max(0.05, min(1.0, power))
    vel[0] = [math.cos(angle) * MAX_SPEED * power, math.sin(angle) * MAX_SPEED * power]
    frames, pocketed = [], []

    def snap():
        frames.append([None if p is None else [round(p[0], 2), round(p[1], 2)] for p in pos])

    snap()
    steps = int(MAX_TIME / DT)
    for step in range(1, steps + 1):
        moving = False
        for i, p in enumerate(pos):
            if p is None:
                continue
            v = vel[i]
            sp = math.hypot(v[0], v[1])
            if sp == 0:
                continue
            ns = max(0.0, sp - FRICTION * DT)
            if ns < 0.3:
                ns = 0.0
            v[0], v[1] = v[0] * ns / sp, v[1] * ns / sp
            if ns == 0:
                continue
            moving = True
            p[0] += v[0] * DT
            p[1] += v[1] * DT
        # pockets
        for i, p in enumerate(pos):
            if p is not None and any(math.hypot(p[0] - px, p[1] - py) < POCKET_R for px, py in POCKETS):
                pos[i] = None
                vel[i] = [0.0, 0.0]
                pocketed.append(i)
        # cushions
        for i, p in enumerate(pos):
            if p is None:
                continue
            v = vel[i]
            if p[0] < R:
                p[0], v[0] = R, abs(v[0]) * CUSHION
            elif p[0] > W - R:
                p[0], v[0] = W - R, -abs(v[0]) * CUSHION
            if p[1] < R:
                p[1], v[1] = R, abs(v[1]) * CUSHION
            elif p[1] > H - R:
                p[1], v[1] = H - R, -abs(v[1]) * CUSHION
        # ball on ball: equal masses, elastic
        live = [i for i, p in enumerate(pos) if p is not None]
        for a_i, a in enumerate(live):
            pa = pos[a]
            for b in live[a_i + 1:]:
                pb = pos[b]
                dx, dy = pb[0] - pa[0], pb[1] - pa[1]
                d2 = dx * dx + dy * dy
                if d2 >= 4 * R * R or d2 == 0:
                    continue
                d = math.sqrt(d2)
                nx, ny = dx / d, dy / d
                overlap = 2 * R - d
                pa[0] -= nx * overlap / 2
                pa[1] -= ny * overlap / 2
                pb[0] += nx * overlap / 2
                pb[1] += ny * overlap / 2
                va, vb = vel[a], vel[b]
                rel = (va[0] - vb[0]) * nx + (va[1] - vb[1]) * ny
                if rel <= 0:
                    continue
                va[0] -= rel * nx
                va[1] -= rel * ny
                vb[0] += rel * nx
                vb[1] += rel * ny
                moving = True
        if step % FRAME_EVERY == 0:
            snap()
        if not moving:
            break
    snap()
    return pos, frames, pocketed


def free_spot(balls, x: float, y: float) -> list[float]:
    """The first place near (x, y), moving left, where a ball can go."""
    for k in range(200):
        cx = x - k * 0.5
        if cx < R:
            cx = W - R - (R - cx)
        if all(b is None or math.hypot(b[0] - cx, b[1] - y) >= 2 * R + 0.05 for b in balls):
            return [cx, y]
    return [x, y]


# ---------- the arcade state ----------
@dataclass
class Pool:
    balls: list = field(default_factory=rack)
    version: int = 0
    last_by: str = ""
    last_at: float = 0.0
    last_frames: list = field(default_factory=list)
    last_pocketed: list = field(default_factory=list)
    last_note: str = ""
    racks: int = 0


class Arcade:
    """Boards, daily karma and the pool table. Saved to one JSON file."""

    def __init__(self, path: Path | None = None):
        self.path = path
        self.boards: dict[str, list[dict]] = {g: [] for g in GAMES}
        self.days: dict[str, dict] = {}        # name (lower case) -> {"date", "karma", "played"}
        self.pool_points: dict[str, int] = {}  # name (lower case) -> balls pocketed, all time
        self.pool_paid: dict[str, int] = {}    # name (lower case) -> pool points already turned into karma
        self.names: dict[str, str] = {}        # name (lower case) -> name as typed
        self.pool = Pool()
        self.load()

    # ----- saving -----
    def load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for g in GAMES:
            self.boards[g] = list(d.get("boards", {}).get(g, []))[:BOARD_SIZE]
        self.days = dict(d.get("days", {}))
        self.pool_points = dict(d.get("pool_points", {}))
        self.pool_paid = dict(d.get("pool_paid", {}))
        self.names = dict(d.get("names", {}))
        t = d.get("pool")
        if isinstance(t, dict) and isinstance(t.get("balls"), list) and len(t["balls"]) == 16:
            self.pool.balls = t["balls"]
            self.pool.version = int(t.get("version", 0))
            self.pool.racks = int(t.get("racks", 0))

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "boards": self.boards, "days": self.days, "pool_points": self.pool_points,
            "pool_paid": self.pool_paid, "names": self.names,
            "pool": {"balls": self.pool.balls, "version": self.pool.version, "racks": self.pool.racks},
        }, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    # ----- karma -----
    def _day(self, key: str) -> dict:
        d = self.days.get(key)
        if not d or d.get("date") != today():
            d = self.days[key] = {"date": today(), "karma": 0, "played": False}
        return d

    def _grant(self, key: str, want: int) -> int:
        d = self._day(key)
        got = max(0, min(want, DAILY_CAP - d["karma"]))
        d["karma"] += got
        return got

    def summary(self, name: str) -> dict:
        key = clean(name).lower() if name.strip() else ""
        d = self._day(key) if key else {"karma": 0, "played": False}
        return {"today": d["karma"], "cap": DAILY_CAP, "played": d["played"],
                "pool_points": self.pool_points.get(key, 0), "pool_per_karma": POOL_PER_KARMA}

    # ----- scores -----
    def submit(self, name: str, game: str, score, secs) -> dict:
        """A finished round. Returns what happened and the karma it gave."""
        name = clean(name)
        if game not in GAMES:
            raise ArcadeError("Unknown game.")
        if not isinstance(score, (int, float)) or not isinstance(secs, (int, float)):
            raise ArcadeError("Bad score.")
        score, secs = int(score), float(secs)
        _, real_try, rate, slack = GAMES[game]
        if score < 0 or secs <= 0 or secs > 6 * 3600 or score > rate * secs + slack:
            raise ArcadeError("That score does not fit the time played.")
        key = name.lower()
        self.names[key] = name
        board = self.boards[game]
        record = score > 0 and (not board or score > board[0]["score"])
        mine = next((e for e in board if e["name"].lower() == key), None)
        if mine is None or score > mine["score"]:
            if mine is not None:
                board.remove(mine)
            board.append({"name": name, "score": score, "at": today()})
            board.sort(key=lambda e: -e["score"])
            del board[BOARD_SIZE:]
        karma, why = 0, []
        d = self._day(key)
        if score >= real_try and not d["played"]:
            d["played"] = True
            if self._grant(key, 1):
                karma += 1
                why.append("first game today")
        if record and self._grant(key, 1):
            karma += 1
            why.append("new record")
        self.save()
        return {"karma": karma, "why": why, "record": record, "board": board,
                "real_try": real_try, **self.summary(name)}

    # ----- pool -----
    def pool_view(self, since: int = -1) -> dict:
        t = self.pool
        v = {"version": t.version, "balls": t.balls, "last_by": t.last_by, "last_note": t.last_note,
             "wait": max(0.0, REPEAT_WAIT - (time.time() - t.last_at)) if t.last_by else 0.0,
             "board": sorted(({"name": self.names.get(k, k), "score": s} for k, s in self.pool_points.items() if s > 0),
                             key=lambda e: -e["score"])[:BOARD_SIZE]}
        if since != t.version:
            v["frames"], v["pocketed"] = t.last_frames, t.last_pocketed
        return v

    def shoot(self, name: str, version, angle, power) -> dict:
        name = clean(name)
        key = name.lower()
        t = self.pool
        if version != t.version:
            raise ArcadeError("Someone shot first. Look at the table again.")
        if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (angle, power)):
            raise ArcadeError("Bad shot.")
        if t.last_by.lower() == key and time.time() - t.last_at < REPEAT_WAIT:
            raise ArcadeError(f"Let someone else shoot, or wait {math.ceil(REPEAT_WAIT - (time.time() - t.last_at))} s.")
        end, frames, pocketed = simulate(t.balls, float(angle), float(power))
        balls = [x for x in pocketed if x != 0]
        scratch = 0 in pocketed
        points = len(balls) - (1 if scratch else 0)
        self.names[key] = name
        before = self.pool_points.get(key, 0)
        self.pool_points[key] = max(0, before + points)
        if scratch:
            end[0] = free_spot(end, W * 0.25, H / 2)
        note = []
        if balls:
            note.append(f"{name} pocketed {len(balls)} ball{'s' if len(balls) > 1 else ''}")
        if scratch:
            note.append(f"{name} sank the cue ball (−1)")
        if all(b is None for b in end[1:]):
            end = rack()
            t.racks += 1
            note.append("new rack")
        # Every POOL_PER_KARMA points pays one karma (points lost to a scratch are not paid twice).
        paid = self.pool_paid.get(key, 0)
        due = self.pool_points[key] // POOL_PER_KARMA - paid
        karma = self._grant(key, due) if due > 0 else 0
        self.pool_paid[key] = paid + max(0, due)   # capped karma is lost, not saved for tomorrow
        t.balls = [None if b is None else [round(b[0], 3), round(b[1], 3)] for b in end]
        t.version += 1
        t.last_by, t.last_at = name, time.time()
        t.last_frames, t.last_pocketed = frames, pocketed
        t.last_note = "; ".join(note) or f"{name} took a shot"
        self.save()
        return {"karma": karma, "points": points, "pool": self.pool_view(), **self.summary(name)}


def clean(name) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ArcadeError("Enter your name first.")
    return " ".join(name.split())[:24]
