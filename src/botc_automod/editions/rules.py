"""The shared rules engine for character-based editions.

Every character is a `Char` subclass with hooks. `ScriptEdition` runs any
list of characters: the setup, the two-stage night in official night
order, deaths and their triggers, day actions and win checks. Trouble
Brewing, Bad Moon Rising and Sects & Violets are three such lists.

Terms used in this file:
    role       the true character of a player (p.role)
    shown      the character a player believes they are (p.shown). It
               differs for the Drunk and the Lunatic.
    acting     a player "acts as" X if X is their shown character or an
               ability they gained (Philosopher). Tasks come from this.
    works      the player truly has the ability, is alive (or the ability
               works while dead), and is not drunk or poisoned.
    status     a timed effect on a player: poisoned, drunk, safe, cursed,
               mad. It ends at a dusk or a dawn, or never.
    abnormal   an ability that worked abnormally because of another
               character. The Mathematician counts these.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from .base import Edition, Role

if TYPE_CHECKING:
    from ..game import Game, Player

DATA = Path(__file__).parent / "data"

# players: (townsfolk, outsiders, minions, demons)
DISTRIBUTION = {
    5: (3, 0, 1, 1), 6: (3, 1, 1, 1), 7: (5, 0, 1, 1), 8: (5, 1, 1, 1),
    9: (5, 2, 1, 1), 10: (7, 0, 2, 1), 11: (7, 1, 2, 1), 12: (7, 2, 2, 1),
    13: (9, 0, 3, 1), 14: (9, 1, 3, 1), 15: (9, 2, 3, 1),
}

INFO_KEYS = ("minion_info", "demon_info", "storyteller", "new_character")


def load_wiki(name: str) -> dict:
    f = DATA / f"{name}.json"
    return json.loads(f.read_text(encoding="utf-8"))["characters"] if f.exists() else {}


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def choose(key: str, title: str, text: str, pick: int, candidates: list[str],
           allow_none: bool = False) -> dict:
    return {"kind": "choose", "key": key, "title": title, "text": text, "pick": pick,
            "candidates": candidates, "allow_none": allow_none}


def choose_character(key: str, title: str, text: str, options: list[Role],
                     allow_none: bool = False) -> dict:
    return {"kind": "character", "key": key, "title": title, "text": text,
            "options": [{"id": r.id, "name": r.name, "type": r.type} for r in options],
            "allow_none": allow_none}


def choose_player_character(key: str, title: str, text: str, candidates: list[str],
                            options: list[Role]) -> dict:
    return {"kind": "player_character", "key": key, "title": title, "text": text,
            "candidates": candidates,
            "options": [{"id": r.id, "name": r.name, "type": r.type} for r in options]}


def info(key: str, title: str, lines: list[str]) -> dict:
    return {"kind": "info", "key": key, "title": title, "lines": lines}


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------

class Char:
    """One character. Subclasses override only the hooks they need."""

    id = ""
    name = ""
    type = ""            # townsfolk | outsider | minion | demon
    style = "chill"      # chill | think (for the preference deal)
    tip = ""
    first_night = False  # wakes on the first night
    other_nights = False  # wakes on other nights
    works_dead = False   # the ability still works while dead
    auto_ok = True       # False: needs a human storyteller (madness)
    outsider_mod: tuple[int, ...] = ()  # setup change to the Outsider count, one is picked

    def role(self, ability: str) -> Role:
        return Role(self.id, self.name, self.type, ability, self.style, self.tip)

    # Setup -------------------------------------------------------------
    def setup(self, R: ScriptEdition, game: Game, p: Player) -> None:
        """After the deal, for the player who truly has this character."""

    # Night -------------------------------------------------------------
    def task(self, R: ScriptEdition, game: Game, p: Player, first: bool) -> dict | None:
        """Stage A task for a player acting as this character."""
        return None

    def step(self, R: ScriptEdition, ctx: Ctx) -> None:
        """This character's place in the night order."""
        for p in R.acting(ctx.game, self.id):
            self.resolve(R, ctx, p, ctx.answer(p, self.id))

    def resolve(self, R: ScriptEdition, ctx: Ctx, p: Player, ans) -> None:
        pass

    def resolve_b(self, R: ScriptEdition, ctx: Ctx, p: Player, ans) -> None:
        """A stage B answer with this character's key (Ravenkeeper, Barber...)."""
        self.resolve(R, ctx, p, ans)

    # Deaths --------------------------------------------------------------
    def on_death(self, R: ScriptEdition, game: Game, p: Player, cause: str, ctx: Ctx | None) -> None:
        """p truly had this character and just died."""

    # Day -------------------------------------------------------------------
    def day_action(self, R: ScriptEdition, game: Game, p: Player) -> dict | None:
        """A day action a player acting as this character may take now."""
        return None

    def public_action(self, R: ScriptEdition, game: Game) -> dict | None:
        """A public day action any living player may claim (Slayer, Gossip, Juggler)."""
        return None

    def do_action(self, R: ScriptEdition, game: Game, p: Player, payload: dict) -> None:
        pass


class Ctx:
    """State for resolving one night stage."""

    def __init__(self, game: Game, answers: dict[str, dict], stage: str, R: ScriptEdition | None = None):
        self.game = game
        self.R = R
        self.first = game.night == 1
        self.answers = answers
        self.stage = stage
        self.out: dict[str, list[dict]] = defaultdict(list)   # stage B tasks
        self.messages: dict[str, list[str]] = defaultdict(list)  # stage B results

    def answer(self, p: Player, key: str):
        return self.answers.get(p.id, {}).get(key)

    def tell(self, p: Player, title: str, lines: list[str], key: str = "") -> None:
        if self.R is not None and self.game.estate.get("audit") is not None:
            self.R.audit_record(self.game, p, key, lines)
        if self.stage == "A":
            self.out[p.id].append(info(key or "storyteller", title, lines))
        else:
            self.messages[p.id].extend(lines)


# ---------------------------------------------------------------------------
# The edition
# ---------------------------------------------------------------------------

class ScriptEdition(Edition):
    """An edition defined by a list of characters and two night orders."""

    chars: dict[str, Char] = {}
    first_order: list[str] = []
    other_order: list[str] = []
    wiki_name = ""

    def __init__(self):
        self.wiki = load_wiki(self.wiki_name)
        self.roles = {c.id: c.role(self.wiki.get(c.id, {}).get("ability", "")) for c in self.chars.values()}

    # Basic facts -------------------------------------------------------------
    def of_type(self, t: str) -> list[str]:
        return [c.id for c in self.chars.values() if c.type == t]

    def type_of(self, role: str) -> str:
        return self.roles[role].type

    def alignment(self, p: Player) -> str:
        return p.alignment or self.roles[p.role].team

    def living(self, game: Game) -> list[Player]:
        """Players who count as alive to everyone (a fake-dead Zombuul does not)."""
        return [p for p in game.seated() if p.alive and not p.fake_dead]

    def in_play(self, game: Game, role: str) -> Player | None:
        return next((p for p in game.seated() if p.role == role), None)

    def acting(self, game: Game, cid: str) -> list[Player]:
        c = self.chars[cid]
        out = []
        for p in game.seated():
            if cid != p.shown and cid not in p.gained:
                continue
            if p.alive or c.works_dead or self.keeps_ability_dead(game, p):
                out.append(p)
        return out

    def keeps_ability_dead(self, game: Game, p: Player) -> bool:
        """Vigormortis: Minions it killed keep their ability while it lives."""
        if p.id not in game.estate.get("vig_minions", []) or self.type_of(p.role) != "minion":
            return False
        vig = self.in_play(game, "vigormortis")
        return bool(vig and vig.alive and not self.malfunction(game, vig))

    # Statuses -------------------------------------------------------------------
    def add_status(self, game: Game, pid: str, kind: str, source: str, until: str,
                   source_pid: str | None = None) -> None:
        """until: 'dusk' (next dusk), 'dawn' (next dawn), 'dusk+N' or 'never'.

        With source_pid, the status only holds while that player's ability works.
        """
        n = game.night if game.phase == "night" else game.night
        if until == "dusk":
            end = ("dusk", n + 1)
        elif until.startswith("dusk+"):
            end = ("dusk", n + int(until[5:]))
        elif until == "dawn":
            end = ("dawn", n)
        else:
            end = ("never", 0)
        game.estate.setdefault("status", []).append(
            {"pid": pid, "kind": kind, "source": source, "end": end, "src": source_pid})

    def expire(self, game: Game, event: str) -> None:
        n = game.night
        game.estate["status"] = [s for s in game.estate.get("status", [])
                                 if not (s["end"][0] == event and s["end"][1] <= n)]

    def statuses(self, game: Game, pid: str, _seen: frozenset = frozenset()) -> list[dict]:
        out = []
        for s in game.estate.get("status", []):
            if s["pid"] != pid:
                continue
            src = s.get("src")
            if src and (src in _seen or self.malfunction(game, game.p(src), _seen | {pid})
                        or not game.p(src).alive):
                continue
            out.append(s)
        return out

    def has(self, game: Game, p: Player, kind: str) -> bool:
        return any(s["kind"] == kind for s in self.statuses(game, p.id))

    def malfunction(self, game: Game, p: Player, _seen: frozenset = frozenset()) -> bool:
        """Drunk or poisoned, by any means."""
        if p.role in ("drunk", "lunatic") and p.shown != p.role:
            return True
        seen = _seen | {p.id}
        if any(s["kind"] in ("poisoned", "drunk") for s in self.statuses(game, p.id, seen)):
            return True
        return p.id in self.dynamic_poison(game, seen) or p.id in self.philosopher_drunk(game, seen)

    def dynamic_poison(self, game: Game, seen: frozenset) -> set[str]:
        """Poison that follows the Grimoire: No Dashii, Vigormortis, Pukka."""
        out: set[str] = set()
        es = game.estate
        for nd in (p for p in game.seated() if p.role == "nodashii" and p.alive):
            if nd.id not in seen and not self._malf_basic(game, nd, seen):
                out |= {x.id for x in self.townsfolk_neighbours(game, nd)}
        vig = self.in_play(game, "vigormortis")
        if vig and vig.alive and vig.id not in seen and not self._malf_basic(game, vig, seen):
            for mid, tid in es.get("vig_poison", {}).items():
                if self.type_of(game.p(mid).role) == "minion":
                    out.add(tid)
        pk = es.get("pukka_victim")
        if pk:
            out.add(pk)
        return out

    def _malf_basic(self, game: Game, p: Player, seen: frozenset) -> bool:
        return any(s["kind"] in ("poisoned", "drunk") for s in self.statuses(game, p.id, seen | {p.id}))

    def philosopher_drunk(self, game: Game, seen: frozenset) -> set[str]:
        out = set()
        for ph in game.seated():
            if ph.role != "philosopher" or not ph.gained or not ph.alive or ph.id in seen:
                continue
            if self._malf_basic(game, ph, seen):
                continue
            for c in ph.gained:
                for x in game.seated():
                    if x.role == c and x.id != ph.id:
                        out.add(x.id)
        return out

    def works(self, game: Game, p: Player, role: str) -> bool:
        if p.role != role and role not in p.gained:
            return False
        if not (p.alive or self.chars[role].works_dead or self.keeps_ability_dead(game, p)):
            return False
        return not self.malfunction(game, p)

    def townsfolk_neighbours(self, game: Game, p: Player) -> list[Player]:
        """Nearest Townsfolk each way, alive or dead (No Dashii, Vigormortis)."""
        seated = game.seated()
        i, n = seated.index(p), len(seated)
        found: list[Player] = []
        for step in (-1, 1):
            for k in range(1, n):
                x = seated[(i + step * k) % n]
                if x is p:
                    break
                if self.type_of(x.role) == "townsfolk":
                    if x not in found:
                        found.append(x)
                    break
        return found

    def alive_neighbours(self, game: Game, p: Player) -> list[Player]:
        seated = game.seated()
        i, n = seated.index(p), len(seated)
        found: list[Player] = []
        for step in (-1, 1):
            for k in range(1, n):
                x = seated[(i + step * k) % n]
                if x is p:
                    break
                if x.alive and not x.fake_dead:
                    if x not in found:
                        found.append(x)
                    break
        return found

    def abnormal(self, game: Game, p: Player | None) -> None:
        if p is not None:
            game.estate.setdefault("abnormal", [])
            if p.id not in game.estate["abnormal"]:
                game.estate["abnormal"].append(p.id)

    # Karma ------------------------------------------------------------------------
    def favor(self, game: Game, p: Player) -> float:
        """How strongly chance favours p: 1.0 is neutral. Karma comes from night questions."""
        if not game.settings.get("karma", 1):
            return 1.0
        return max(0.4, min(2.5, 1.0 + 0.15 * p.karma))

    def pick_victim(self, game: Game, players: list[Player]) -> Player:
        """A random pick that hurts the player: high karma makes it less likely."""
        return game.rng.choices(players, weights=[1.0 / self.favor(game, x) for x in players])[0]

    def pick_lucky(self, game: Game, players: list[Player]) -> Player:
        """A random pick that helps the player: high karma makes it more likely."""
        return game.rng.choices(players, weights=[self.favor(game, x) for x in players])[0]

    def lucky(self, game: Game, p: Player, chance: float) -> bool:
        """A chance of something good for p, scaled by karma."""
        return game.rng.random() < min(1.0, chance * self.favor(game, p))

    def unlucky(self, game: Game, p: Player, chance: float) -> bool:
        """A chance of something bad for p, scaled down by karma."""
        return game.rng.random() < chance / self.favor(game, p)

    # Audit (tests and scripts/audit_info.py) --------------------------------------
    def audit_record(self, game: Game, p: Player, key: str, lines: list[str]) -> None:
        es = game.estate
        es["audit"].append({
            "night": game.night, "stage": game.stage, "pid": p.id, "key": key, "lines": list(lines),
            "shown": p.shown, "role": p.role, "gained": list(p.gained),
            "sober": not self.malfunction(game, p) and not (
                self.vortox_active(game) and key in self.chars and self.chars[key].type == "townsfolk"),
            "players": [{"id": x.id, "name": x.name, "role": x.role, "shown": x.shown,
                         "align": self.alignment(x), "alive": x.alive, "fake_dead": x.fake_dead}
                        for x in game.seated()],
            "reg": {k.split(":", 1)[1]: v for k, v in es.get("reg", {}).items()
                    if k.startswith(game.label() + ":")},
            "red_herring": es.get("red_herring"), "grandchild": es.get("grandchild"),
            "twins": es.get("twins"), "executed_died": es.get("executed_died"),
            "nominators": sorted(game.nominators_today),
            "voters": sorted({x for h in game.nom_history for x in h["yes"]}),
            "bluffs": list(es.get("bluffs", [])),
        })

    # Registration and truth -------------------------------------------------------
    def reg(self, game: Game, p: Player, asker: Player | None = None) -> dict:
        """How p registers to abilities now. The Spy and Recluse may misregister."""
        cache = game.estate.setdefault("reg", {})
        key = f"{game.label()}:{p.id}"
        if key in cache:
            out = cache[key]
        else:
            role = self.roles[p.role]
            out = {"team": self.alignment(p), "type": role.type, "role": role.id, "false": False}
            chance = game.settings["misregister"]
            if p.role == "spy" and not self.malfunction(game, p) and game.rng.random() < chance:
                fake = game.rng.choice([r for r in self.roles.values() if r.team == "good"])
                out = {"team": "good", "type": fake.type, "role": fake.id, "false": True}
            elif p.role == "recluse" and not self.malfunction(game, p) and game.rng.random() < chance:
                fake = game.rng.choice([r for r in self.roles.values() if r.team == "evil"])
                out = {"team": "evil", "type": fake.type, "role": fake.id, "false": True}
            cache[key] = out
        if out["false"]:
            self.abnormal(game, asker)
        return out

    def truthful(self, game: Game, p: Player, cid: str) -> bool:
        """Should p's info from ability cid be true? Records abnormal results."""
        if self.chars[cid].type == "townsfolk" and self.vortox_active(game):
            self.abnormal(game, p)
            return False
        if self.malfunction(game, p):
            self.abnormal(game, p)
            return False
        return True

    def vortox_active(self, game: Game) -> bool:
        v = self.in_play(game, "vortox")
        return bool(v and v.alive and not self.malfunction(game, v))

    def pick_other(self, game: Game, not_ids: set[str] = frozenset(), alive_only: bool = False) -> Player | None:
        pool = [p for p in game.seated() if p.id not in not_ids and (p.alive or not alive_only)]
        return game.rng.choice(pool) if pool else None

    def not_in_play(self, game: Game, types: tuple[str, ...]) -> list[str]:
        used = {p.role for p in game.seated()} | {p.shown for p in game.seated()}
        return [r.id for r in self.roles.values() if r.type in types and r.id not in used]

    # Setup ----------------------------------------------------------------------
    def pool(self, game: Game, t: str) -> list[str]:
        return [c.id for c in self.chars.values()
                if c.type == t and (c.auto_ok or game.mode == "human")]

    def setup(self, game: Game) -> None:
        from ..assign import deal

        rng = game.rng
        players = game.seated()
        n = len(players)
        t, o, m, d = DISTRIBUTION[n]
        demon = rng.choice(self.pool(game, "demon"))
        minions = rng.sample(self.pool(game, "minion"), m)
        outsiders_pool = self.pool(game, "outsider")
        for cid in [demon, *minions]:
            mods = self.chars[cid].outsider_mod
            if mods:
                o += rng.choice(mods)
        o = max(0, min(o, len(outsiders_pool)))
        t = n - o - m - d
        townsfolk = rng.sample(self.pool(game, "townsfolk"), t)
        outsiders = rng.sample(outsiders_pool, o)
        in_play = townsfolk + outsiders + minions + [demon]
        shown = []
        free_tf = [x for x in self.of_type("townsfolk") if x not in townsfolk]
        for r in in_play:
            if r == "drunk":
                s = rng.choice(free_tf)
                free_tf.remove(s)
            elif r == "lunatic":
                s = demon
            else:
                s = r
            shown.append(s)
        slots = [(self.roles[r].team, self.roles[s].style) for r, s in zip(in_play, shown)]
        perm = deal([p.prefs for p in players], slots, rng, weights=[self.favor(game, p) for p in players])
        for p, j in zip(players, perm):
            p.role, p.shown = in_play[j], shown[j]
            p.alignment = self.roles[p.role].team
            p.gained = []
            p.fake_dead = False
        bluff_pool = [x for x in free_tf]
        if len(bluff_pool) < 3:
            bluff_pool += self.not_in_play(game, ("outsider",))
        good = [p for p in players if self.roles[p.role].team == "good"]
        game.estate.update({
            "bluffs": rng.sample(bluff_pool, min(3, len(bluff_pool))),
            "red_herring": rng.choice(good).id if good else None,
            "status": [], "used": {}, "abnormal": [],
            "lunatic_bluffs": [r.id for r in rng.sample([r for r in self.roles.values() if r.team == "good"], 3)],
        })
        for p in players:
            self.chars[p.role].setup(self, game, p)

    # Night --------------------------------------------------------------------------
    def on_dusk(self, game: Game) -> None:
        self.expire(game, "dusk")
        game.estate["reg"] = {}
        game.estate["woke"] = []
        game.estate["exorcised"] = []

    def on_dawn(self, game: Game) -> list[str]:
        self.expire(game, "dawn")
        game.estate["reg"] = {}
        es = game.estate
        es["died_today"] = False
        es["outsider_died_today"] = False
        es["executed_died"] = None
        lines = es.pop("dawn_lines", [])
        for pid in list(es.get("death_prompts_pending", [])):
            es.setdefault("death_prompts", []).append(pid)
        es["death_prompts_pending"] = []
        for claims in es.get("claimed", {}).values():  # the Gossip may speak every day
            while "gossip" in claims:
                claims.remove("gossip")
        return lines

    def request(self, game: Game, p: Player, kind: str, text: str) -> None:
        """A private question for the human storyteller (Artist, Savant)."""
        reqs = game.estate.setdefault("requests", [])
        reqs.append({"id": f"r{len(reqs) + 1}{game.day}", "pid": p.id, "name": p.name, "kind": kind,
                     "text": text, "label": game.label()})
        p.note(game.label(), f"{kind}: your request went to the Storyteller.")

    def used(self, game: Game, p: Player, key: str) -> bool:
        return key in game.estate.setdefault("used", {}).get(p.id, [])

    def use(self, game: Game, p: Player, key: str) -> None:
        game.estate.setdefault("used", {}).setdefault(p.id, []).append(key)

    def abilities(self, p: Player) -> list[str]:
        return [p.shown, *p.gained]

    def holds(self, p: Player, cid: str) -> bool:
        """p has this ability: their character (true or believed) or one they gained."""
        return cid in (p.role, p.shown) or cid in p.gained

    def stage_a(self, game: Game) -> dict[str, list[dict]]:
        tasks: dict[str, list[dict]] = defaultdict(list)
        first = game.night == 1
        seated = game.seated()
        if first and len(seated) >= 7:
            self._evil_info(game, tasks)
        elif first and game.settings.get("demon_bluffs", 1):
            self._bluffs_only(game, tasks)
        if game.estate.get("audit") is not None:
            for pid, ts in tasks.items():
                for t in ts:
                    self.audit_record(game, game.p(pid), t["key"], t["lines"])
        woke = []
        for p in seated:
            for cid in self.abilities(p):
                c = self.chars.get(cid)
                if not c or not (p.alive or c.works_dead or self.keeps_ability_dead(game, p)):
                    continue
                if (first and not c.first_night) or (not first and not c.other_nights):
                    continue
                t = c.task(self, game, p, first)
                if t:
                    tasks[p.id].append(t)
                    woke.append(p.id)
        for cid, c in self.chars.items():
            extra = getattr(c, "extra_tasks", None)
            if extra:
                for pid, t in extra(self, game, first).items():
                    tasks[pid].append(t)
                    woke.append(pid)
        game.estate["woke"] = sorted(set(woke))
        return tasks

    def _evil_info(self, game: Game, tasks: dict) -> None:
        seated = game.seated()
        demons = [p for p in seated if self.type_of(p.role) == "demon"]
        minions = [p for p in seated if self.type_of(p.role) == "minion"]
        bluffs = ", ".join(self.roles[b].name for b in game.estate["bluffs"])
        names = lambda ps: ", ".join(x.name for x in ps) or "none"
        for mp in minions:
            others = [x for x in minions if x is not mp]
            lines = [f"The Demon is {names(demons)}."]
            if others:
                lines.append(f"Your fellow Minions: {names(others)}.")
            tasks[mp.id].append(info("minion_info", "Your evil team", lines))
        for dp in demons:
            lines = [f"Your Minions: {names(minions)}.",
                     f"These good characters are not in play, so they are safe to bluff: {bluffs}."]
            lun = next((x for x in seated if x.role == "lunatic"), None)
            if lun:
                lines.append(f"{lun.name} is the Lunatic: they think they are the Demon.")
            tasks[dp.id].append(info("demon_info", "Your evil team", lines))
        for lun in (p for p in seated if p.role == "lunatic"):
            fake = game.rng.sample([x for x in seated if x is not lun], min(len(minions), len(seated) - 1))
            fb = ", ".join(self.roles[b].name for b in game.estate.get("lunatic_bluffs", []))
            tasks[lun.id].append(info("demon_info", "Your evil team", [
                f"Your Minions: {names(fake)}.",
                f"These good characters are not in play, so they are safe to bluff: {fb}."]))

    def _bluffs_only(self, game: Game, tasks: dict) -> None:
        """Small games skip evil info, but the host option still gives the Demon bluffs."""
        bluffs = ", ".join(self.roles[b].name for b in game.estate["bluffs"])
        for dp in game.seated():
            if self.type_of(dp.role) == "demon":
                tasks[dp.id].append(info("demon_info", "Your bluffs", [
                    f"These good characters are not in play, so they are safe to bluff: {bluffs}."]))
            elif dp.role == "lunatic":
                fb = ", ".join(self.roles[b].name for b in game.estate.get("lunatic_bluffs", []))
                tasks[dp.id].append(info("demon_info", "Your bluffs", [
                    f"These good characters are not in play, so they are safe to bluff: {fb}."]))

    def bluffs_for(self, game: Game, p: Player) -> list[str]:
        """The bluffs a player was told (the Demon), or believes they were told (the Lunatic)."""
        if not p.role or game.night < 1 or (len(game.seated()) < 7 and not game.settings.get("demon_bluffs", 1)):
            return []
        if p.role == "lunatic":
            return [self.roles[b].name for b in game.estate.get("lunatic_bluffs", [])]
        if self.type_of(p.role) == "demon" and p.role == p.shown:
            return [self.roles[b].name for b in game.estate.get("bluffs", [])]
        return []

    def resolve_a(self, game: Game, answers: dict[str, dict]) -> dict[str, list[dict]]:
        ctx = Ctx(game, answers, "A", self)
        if game.estate.get("audit") is not None:
            game.estate.setdefault("audit_nights", {})[game.night] = {
                "answers": answers, "deaths": [], "demon_kills": [],
                "executed_died": game.estate.get("executed_died"),
                "juggler": list(game.estate.get("juggler", {})),
                "start": [{"id": x.id, "alive": x.alive, "fake_dead": x.fake_dead, "abilities": self.abilities(x),
                           "role": x.role} for x in game.seated()]}
        game.estate["goon_hit"] = False
        order = self.first_order if ctx.first else self.other_order
        for cid in order:
            if cid in self.chars:
                self.chars[cid].step(self, ctx)
        return ctx.out

    def resolve_b(self, game: Game, answers: dict[str, dict]) -> dict[str, list[str]]:
        ctx = Ctx(game, answers, "B", self)
        for pid, keys in answers.items():
            p = game.p(pid)
            for key, ans in keys.items():
                if key in self.chars:
                    self.chars[key].resolve_b(self, ctx, p, ans)
        night = game.estate.get("audit_nights", {}).get(game.night)
        if night is not None:
            night["deaths"] = list(game.tonight_deaths)
            night["b_answers"] = answers
            night["end"] = {x.id: self.abilities(x) for x in game.seated()}
        return dict(ctx.messages)

    def chose(self, game: Game, chooser: Player, targets: list[Player]) -> None:
        """A player chose targets with their ability. Handles the Goon."""
        if game.phase != "night" or game.estate.get("goon_hit"):
            return
        for t in targets:
            if t.role == "goon" and t.alive and not self.malfunction(game, t):
                game.estate["goon_hit"] = True
                self.add_status(game, chooser.id, "drunk", "goon", "dusk")
                t.alignment = self.alignment(chooser)
                return

    # Deaths ---------------------------------------------------------------------
    def protected(self, game: Game, t: Player, cause: str) -> bool:
        night = game.phase == "night"
        if night and cause != "execution" and self.has(game, t, "safe_all"):
            return True
        if cause == "demon" and (self.has(game, t, "safe_demon") or self.works(game, t, "soldier")):
            return True
        if self.works(game, t, "sailor"):
            return True
        if cause == "execution" and self.has(game, t, "safe_exec"):
            return True
        for tl in (p for p in game.seated() if p.role == "tealady"):
            if tl.alive and not self.malfunction(game, tl):
                nb = self.alive_neighbours(game, tl)
                if t in nb and len(nb) == 2 and all(self.alignment(x) == "good" for x in nb):
                    return True
        return False

    def die(self, game: Game, t: Player, cause: str, source: Player | None = None,
            ctx: Ctx | None = None, force: bool = False) -> bool:
        """Try to kill t. Return True if t (appears to have) died."""
        if not t.alive:
            return False
        if t.fake_dead:  # a fake-dead Zombuul dies for real
            t.fake_dead = False
            game.kill(t.id, cause)
            self._after_death(game, t, cause, source, ctx, len(self.living(game)) + 1)
            return True
        if not force:
            if self.protected(game, t, cause):
                self.abnormal(game, source)
                return False
            if cause == "execution" and self.alignment(t) == "good" and any(
                    self.works(game, x, "pacifist") for x in game.seated()) \
                    and self.lucky(game, t, game.settings["pacifist_save"]):
                self.abnormal(game, t)
                return False
            if self.works(game, t, "fool") and not self.used(game, t, "fool"):
                self.use(game, t, "fool")
                return False
        if t.role == "zombuul" and not self.used(game, t, "zombuul") and not self.malfunction(game, t):
            self.use(game, t, "zombuul")
            t.fake_dead = True
            if game.phase == "night":
                game.tonight_deaths.append(t.id)
            game.estate["died_today"] = True
            return True
        before = len(self.living(game))
        game.kill(t.id, cause)
        night = game.estate.get("audit_nights", {}).get(game.night)
        if night is not None and game.phase == "night" and cause == "demon":
            night["demon_kills"].append(t.id)
        self._after_death(game, t, cause, source, ctx, before)
        return True

    def _after_death(self, game: Game, t: Player, cause: str, source, ctx, before: int) -> None:
        es = game.estate
        if game.phase != "night":
            es["died_today"] = True
            if self.type_of(t.role) == "outsider":
                es["outsider_died_today"] = True
        for x in game.seated():
            for cid in {x.role, *x.gained}:
                c = self.chars.get(cid)
                watcher = getattr(c, "on_any_death", None) if c else None
                if watcher:
                    watcher(self, game, x, t, cause, ctx)
        for cid in {t.role, *t.gained, t.shown}:
            if cid in self.chars:
                self.chars[cid].on_death(self, game, t, cause, ctx)
        if self.type_of(t.role) == "demon":
            self._demon_died(game, t, before)

    def _demon_died(self, game: Game, demon: Player, before: int) -> None:
        sw = next((x for x in game.seated() if x.role == "scarletwoman" and x.alive
                   and not self.malfunction(game, x)), None)
        if sw and before >= 5 and not any(self.type_of(x.role) == "demon" for x in self.living(game)):
            self.become(game, sw, demon.role, tell="The Demon died. ")

    def become(self, game: Game, p: Player, role: str, tell: str = "", keep_alignment: bool = False,
               ctx: Ctx | None = None) -> None:
        p.role = p.shown = role
        p.gained = []
        if not keep_alignment:
            p.alignment = self.roles[role].team
        game.estate.setdefault("used", {}).pop(p.id, None)
        r = self.roles[role]
        line = f"{tell}You are now the {r.name}. You are {self.alignment(p)}. {r.ability}"
        if ctx is not None and ctx.stage == "A":
            ctx.out[p.id].append(info("new_character", "Your character changed", [line]))
        elif ctx is not None:
            ctx.messages[p.id].append(line)
        else:
            p.note(game.label(), line)

    def revive(self, game: Game, p: Player) -> None:
        if p.alive and not p.fake_dead:
            return
        p.alive = True
        p.fake_dead = False
        p.ghost_vote = True
        game.estate.setdefault("used", {}).pop(p.id, None)
        game.estate.setdefault("dawn_lines", []).append(f"{p.name} is alive again.")
        if p.id in game.tonight_deaths:
            game.tonight_deaths.remove(p.id)

    # Day ----------------------------------------------------------------------------
    def on_nominate(self, game: Game, nominator: Player, nominee: Player) -> bool:
        for c in self.chars.values():
            hook = getattr(c, "on_nominate", None)
            if hook and hook(self, game, nominator, nominee):
                return True
        return False

    def count_votes(self, game: Game, votes: dict[str, bool]) -> int:
        count = 0
        for pid, yes in votes.items():
            if not yes:
                continue
            v = game.p(pid)
            if self.works(game, v, "butler"):
                master = game.estate.get("master", {}).get(v.id)
                if not (master and votes.get(master)):
                    self.abnormal(game, v)
                    continue
            count += 1
        return count

    def on_execution(self, game: Game, player: Player) -> None:
        es = game.estate
        was_alive = player.alive  # a fake-dead Zombuul is alive and dies for real now
        if not was_alive:
            game.announce(f"{player.name} is already dead.", read=False)
        died = was_alive and self.die(game, player, "execution")
        if died and not player.fake_dead:
            game.estate["executed_died"] = player.id
        if was_alive and not died and not player.fake_dead:
            game.announce(f"{player.name} does not die.")
        for c in self.chars.values():
            hook = getattr(c, "after_execution", None)
            if hook:
                hook(self, game, player, died)

    def on_no_execution(self, game: Game) -> None:
        for c in self.chars.values():
            hook = getattr(c, "after_no_execution", None)
            if hook:
                hook(self, game)

    def day_actions(self, game: Game, p: Player) -> list[dict]:
        out = []
        es = game.estate
        if p.id in es.get("death_prompts", []):
            for cid in self.abilities(p):
                c = self.chars.get(cid)
                if c and getattr(c, "death_prompt", None):
                    out.append(c.death_prompt(self, game, p))
                    break
        if p.alive and not p.fake_dead and game.phase in ("day", "nominations"):
            for c in self.chars.values():
                a = c.public_action(self, game)
                if a and a["key"] not in es.get("claimed", {}).get(p.id, []):
                    out.append(a)
            for cid in self.abilities(p):
                c = self.chars.get(cid)
                a = c.day_action(self, game, p) if c else None
                if a:
                    out.append(a)
        return out

    def do_day_action(self, game: Game, p: Player, key: str, payload: dict) -> None:
        from ..game import GameError

        allowed = {a["key"] for a in self.day_actions(game, p)}
        if key not in allowed:
            raise GameError("You cannot do that now.")
        cid = key.split(":")[0]
        self.chars[cid].do_action(self, game, p, payload or {})

    def slayer_shot(self, game: Game, shooter: Player, target: Player) -> None:
        self.chars["slayer"].do_action(self, game, shooter, {"target": target.id})

    # Statements (Gossip, Artist) --------------------------------------------------
    def statement_text(self, game: Game, s: dict) -> str:
        pname = game.p(s["player"]).name if s.get("player") in game.players else "?"
        role = self.roles.get(s.get("role", ""))
        kind = s.get("kind")
        if kind == "is_role":
            return f"{pname} is the {role.name if role else '?'}"
        if kind == "is_evil":
            return f"{pname} is evil"
        if kind == "is_type":
            return f"{pname} is a {s.get('type', '?')}"
        if kind == "in_play":
            return f"the {role.name if role else '?'} is in play"
        return str(s.get("text", "")).strip()

    def statement_true(self, game: Game, s: dict) -> bool | None:
        kind = s.get("kind")
        p = game.players.get(s.get("player", ""))
        if kind == "is_role" and p:
            return p.role == s.get("role")
        if kind == "is_evil" and p:
            return self.alignment(p) == "evil"
        if kind == "is_type" and p:
            return self.type_of(p.role) == s.get("type")
        if kind == "in_play":
            return any(x.role == s.get("role") for x in game.seated())
        return None  # free text: only a human storyteller can judge

    # Win ------------------------------------------------------------------------------
    def check_win(self, game: Game) -> tuple[str, str] | None:
        es = game.estate
        if es.get("win"):
            return tuple(es["win"])
        if es.get("mastermind_day"):
            return None
        demons = [p for p in game.seated() if p.alive and self.type_of(p.role) == "demon"]
        if not demons:
            twin = self.twins_block(game)
            if not twin:
                return "good", "The Demon is dead."
        alive = [p for p in game.seated() if p.alive]
        if len(alive) <= 2 and demons:
            return "evil", "Only two players are left alive."
        return None

    def twins_block(self, game: Game) -> bool:
        pair = game.estate.get("twins")
        if not pair:
            return False
        et, gt = game.p(pair[0]), game.p(pair[1])
        return et.alive and gt.alive and not self.malfunction(game, et)

    # Human storyteller -------------------------------------------------------------
    def st_status(self, game: Game) -> list[dict]:
        es = game.estate
        name = lambda pid: game.p(pid).name if pid and pid in game.players else "nobody"
        rows = []
        if "red_herring" in es and "fortuneteller" in self.chars:
            rows.append({"label": "Fortune Teller red herring", "value": name(es.get("red_herring")),
                         "key": "red_herring"})
        rows.append({"label": "Demon bluffs", "value": ", ".join(self.roles[b].name for b in es.get("bluffs", [])),
                     "key": "bluffs", "ids": es.get("bluffs", [])})
        if es.get("twins"):
            rows.append({"label": "Twins (evil, good)", "value": " & ".join(name(x) for x in es["twins"])})
        if es.get("grandchild"):
            rows.append({"label": "Grandchild", "value": name(es["grandchild"])})
        return rows

    def player_notes(self, game: Game, p: Player) -> list[str]:
        notes = []
        if self.malfunction(game, p):
            notes.append("drunk or poisoned")
        for s in self.statuses(game, p.id):
            if s["kind"] not in ("poisoned", "drunk"):
                notes.append(f"{s['kind'].replace('_', ' ')} ({s['source']})")
        if p.fake_dead:
            notes.append("registers as dead")
        if p.gained:
            notes.append("gained: " + ", ".join(self.roles[g].name for g in p.gained))
        if self.alignment(p) != self.roles[p.role].team:
            notes.append(f"alignment {self.alignment(p)}")
        return notes

    def st_set(self, game: Game, key: str, value) -> None:
        from ..game import GameError

        if key == "red_herring":
            game.p(value)
            game.estate["red_herring"] = value
        elif key == "bluffs":
            if not (isinstance(value, list) and len(value) == 3 and all(v in self.roles for v in value)):
                raise GameError("Pick 3 characters as bluffs.")
            game.estate["bluffs"] = value
        else:
            raise GameError("Unknown Grimoire setting.")


# ---------------------------------------------------------------------------
# Shared helpers for character files
# ---------------------------------------------------------------------------

def others(game: Game, p: Player, alive: bool = True) -> list[str]:
    return [x.id for x in game.seated() if x.id != p.id and (not alive or (x.alive and not x.fake_dead))]


def everyone(game: Game, alive: bool = False) -> list[str]:
    return [x.id for x in game.seated() if not alive or (x.alive and not x.fake_dead)]


def wrong_number(rng: random.Random, true: int, top: int) -> int:
    choices = [k for k in range(0, max(top, 2) + 1) if k != true]
    return rng.choice(choices)
