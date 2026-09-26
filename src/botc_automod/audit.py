"""Check night information for accuracy, completeness and delivery.

The rules engine records every piece of night info with a snapshot of the
game at that moment (when game.estate["audit"] is a list). This checker
re-derives each fact from the snapshot on its own, without the engine's
info code, and reports anything wrong.

Rules the checker applies:
- Only "sober" info must be true: the player is not drunk or poisoned, and
  the Vortox does not falsify it.
- The Spy and Recluse may register as another character, type or team.
  The snapshot holds how they registered that night; either their true
  identity or that registration is accepted.
- A player whose true type is Townsfolk/Outsider/Minion is never hidden
  from the Washerwoman/Librarian/Investigator.
"""

from __future__ import annotations

import re

from .game import Game

FIRST_NIGHT_INFO = {"washerwoman", "librarian", "investigator", "chef", "clockmaker", "grandmother", "godfather"}
EVERY_NIGHT_INFO = {"empath", "spy", "mathematician"}
OTHER_NIGHT_INFO = {"oracle", "flowergirl", "towncrier"}
CHOICE_INFO = {"fortuneteller", "dreamer", "chambermaid", "seamstress"}


class Snap:
    def __init__(self, rec: dict, roles: dict):
        self.rec = rec
        self.roles = roles
        self.players = rec["players"]
        self.by_name = {p["name"]: p for p in self.players}
        self.by_id = {p["id"]: p for p in self.players}

    def reg(self, p: dict) -> dict:
        return self.rec["reg"].get(p["id"]) or {"team": p["align"], "type": self.roles[p["role"]].type,
                                                "role": p["role"], "false": False}

    def roles_ok(self, p: dict) -> set[str]:
        return {p["role"], self.reg(p)["role"]}

    def types_ok(self, p: dict) -> set[str]:
        return {self.roles[p["role"]].type, self.reg(p)["type"]}

    def team(self, p: dict) -> str:
        return self.reg(p)["team"]

    def role_id(self, name: str) -> str | None:
        return next((r.id for r in self.roles.values() if r.name == name), None)

    def living(self, p: dict) -> bool:
        return p["alive"] and not p["fake_dead"]

    def neighbours(self, p: dict) -> list[dict]:
        seats = self.players
        i, n = seats.index(p), len(seats)
        out: list[dict] = []
        for step in (-1, 1):
            for k in range(1, n):
                x = seats[(i + step * k) % n]
                if x is p:
                    break
                if self.living(x):
                    if x not in out:
                        out.append(x)
                    break
        return out


def names(text: str) -> list[str]:
    return [x.strip() for x in re.split(r",| and ", text) if x.strip() and x.strip() != "none"]


def check_record(rec: dict, roles: dict) -> list[str]:
    """Problems with one sober info record."""
    if not rec["sober"]:
        return []
    S = Snap(rec, roles)
    me = S.by_id[rec["pid"]]
    key = rec["key"]
    bad = []
    kinds = {"washerwoman": "townsfolk", "librarian": "outsider", "investigator": "minion"}
    for line in rec["lines"]:
        where = f"{key} ({me['name']}, night {rec['night']}): {line}"
        m = re.fullmatch(r"One of (.+) and (.+) is the (.+)\.", line)
        if key in kinds and m:
            a, b, rname = S.by_name[m[1]], S.by_name[m[2]], S.role_id(m[3])
            if roles[rname].type != kinds[key]:
                bad.append(f"wrong type shown: {where}")
            elif not any(rname in S.roles_ok(x) for x in (a, b)):
                bad.append(f"neither player is that character: {where}")
            continue
        m = re.fullmatch(r"There are no (Outsider|Townsfolk|Minion)s? in play\.", line)
        if key in kinds and m:
            kind = kinds[key]
            if any(kind in S.types_ok(x) for x in S.players if x is not me):
                bad.append(f"says none, but one is in play: {where}")
            continue
        m = re.fullmatch(r"There (?:is|are) (\d+) pairs? of evil players\.", line)
        if key == "chef" and m:
            n = len(S.players)
            evil = [S.team(x) == "evil" for x in S.players]
            true = sum(1 for i in range(n) if evil[i] and evil[(i + 1) % n])
            if int(m[1]) != true:
                bad.append(f"expected {true}: {where}")
            continue
        m = re.fullmatch(r"(\d+) of your alive neighbours (?:is|are) evil\.", line)
        if key == "empath" and m:
            true = sum(1 for x in S.neighbours(me) if S.team(x) == "evil")
            if int(m[1]) != true:
                bad.append(f"expected {true}: {where}")
            continue
        m = re.fullmatch(r"(.+) and (.+): (YES|NO).*", line)
        if key == "fortuneteller" and m:
            ts = [S.by_name[m[1]], S.by_name[m[2]]]
            true = any("demon" in S.types_ok(t) or t["id"] == rec["red_herring"] for t in ts)
            if (m[3] == "YES") != true:
                bad.append(f"expected {'YES' if true else 'NO'}: {where}")
            continue
        m = re.fullmatch(r"Today's executed player, (.+), was the (.+)\.", line)
        if key == "undertaker" and m:
            t = S.by_name[m[1]]
            if t["id"] != rec["executed_died"]:
                bad.append(f"that player did not die by execution today: {where}")
            elif S.role_id(m[2]) not in S.roles_ok(t):
                bad.append(f"wrong character: {where}")
            continue
        m = re.fullmatch(r"(.+) is the (.+)\.", line)
        if key == "ravenkeeper" and m:
            if S.role_id(m[2]) not in S.roles_ok(S.by_name[m[1]]):
                bad.append(f"wrong character: {where}")
            continue
        m = re.fullmatch(r"Your grandchild is (.+), the (.+)\.", line)
        if key == "grandmother" and m:
            t = S.by_name[m[1]]
            if t["id"] != rec["grandchild"] or S.role_id(m[2]) != t["role"]:
                bad.append(f"wrong grandchild or character: {where}")
            continue
        m = re.fullmatch(r"Outsiders in play: (.+)\.", line)
        if key == "godfather" and m:
            got = sorted(names(m[1]))
            true = sorted(roles[x["role"]].name for x in S.players if roles[x["role"]].type == "outsider")
            if got != true:
                bad.append(f"expected {true}: {where}")
            continue
        m = re.fullmatch(r"The Demon is (\d+) steps? from its nearest Minion\.", line)
        if key == "clockmaker" and m:
            seats, n = S.players, len(S.players)
            demon = next(x for x in seats if roles[x["role"]].type == "demon")
            dist = lambda a, b: min(abs(seats.index(a) - seats.index(b)), n - abs(seats.index(a) - seats.index(b)))
            true = min(dist(demon, x) for x in seats if roles[x["role"]].type == "minion")
            if int(m[1]) != true:
                bad.append(f"expected {true}: {where}")
            continue
        m = re.fullmatch(r"(.+) is the (.+) or the (.+)\.", line)
        if key == "dreamer" and m:
            t = S.by_name[m[1]]
            pair = [S.role_id(m[2]), S.role_id(m[3])]
            right = [r for r in pair if r in S.roles_ok(t)]
            if not right:
                bad.append(f"neither character is right: {where}")
            elif len(right) == 1:
                other = pair[1 - pair.index(right[0])]
                if roles[other].team == roles[right[0]].team:
                    bad.append(f"the wrong one is on the same team: {where}")
            continue
        m = re.fullmatch(r"(YES|NO), .* voted today\.", line)
        if key == "flowergirl" and m:
            true = any(roles[S.by_id[x]["role"]].type == "demon" for x in rec["voters"])
            if (m[1] == "YES") != true:
                bad.append(f"expected {true}: {where}")
            continue
        m = re.fullmatch(r"(YES|NO), .* nominated today\.", line)
        if key == "towncrier" and m:
            true = any(roles[S.by_id[x]["role"]].type == "minion" for x in rec["nominators"])
            if (m[1] == "YES") != true:
                bad.append(f"expected {true}: {where}")
            continue
        m = re.fullmatch(r"(\d+) dead players? (?:is|are) evil\.", line)
        if key == "oracle" and m:
            true = sum(1 for x in S.players if not S.living(x) and x["align"] == "evil")
            if int(m[1]) != true:
                bad.append(f"expected {true}: {where}")
            continue
        m = re.fullmatch(r"(.+) and (.+) are (the SAME|NOT the same) alignment\.", line)
        if key == "seamstress" and m:
            same = S.team(S.by_name[m[1]]) == S.team(S.by_name[m[2]])
            if (m[3] == "the SAME") != same:
                bad.append(f"expected same={same}: {where}")
            continue
        m = re.fullmatch(r"The Demon is (.+) or (.+)\.", line)
        if key == "sage" and m:
            if not any(roles[S.by_name[x]["role"]].type == "demon" for x in (m[1], m[2])):
                bad.append(f"neither is the Demon: {where}")
            continue
        m = re.fullmatch(r"(\d+) of .+ woke tonight\.", line)
        if key == "chambermaid" and m:
            if not 0 <= int(m[1]) <= 2:
                bad.append(f"impossible count: {where}")
            continue
        if key == "spy":
            m = re.fullmatch(r"(.+?): ([^(]+?)(?: \(.*\))?", line)
            if m and m[1] in S.by_name and S.role_id(m[2]) != S.by_name[m[1]]["role"]:
                bad.append(f"wrong Grimoire entry: {where}")
            continue
        if key == "minion_info":
            m = re.fullmatch(r"The Demon is (.+)\.", line)
            if m and sorted(names(m[1])) != sorted(x["name"] for x in S.players
                                                   if roles[x["role"]].type == "demon"):
                bad.append(f"wrong Demon: {where}")
            m = re.fullmatch(r"Your fellow Minions: (.+)\.", line)
            if m and sorted(names(m[1])) != sorted(x["name"] for x in S.players if x is not me
                                                   and roles[x["role"]].type == "minion"):
                bad.append(f"wrong Minions: {where}")
            continue
        if key == "demon_info":
            m = re.fullmatch(r"Your Minions: (.+)\.", line)
            if m and sorted(names(m[1])) != sorted(x["name"] for x in S.players
                                                   if roles[x["role"]].type == "minion"):
                bad.append(f"wrong Minions: {where}")
            m = re.fullmatch(r"These good characters are not in play, so they are safe to bluff: (.*)\.", line)
            if m:
                used = {x["role"] for x in S.players} | {x["shown"] for x in S.players}
                shown = [S.role_id(x) for x in names(m[1])]
                if len(shown) != 3 or any(r in used or roles[r].team != "good" for r in shown):
                    bad.append(f"unsafe bluffs: {where}")
            continue
    return bad


def check_game(g: Game) -> list[str]:
    """All accuracy, completeness and delivery problems in a finished automod game."""
    R = g.edition
    recs = g.estate.get("audit", [])
    bad = [b for r in recs for b in check_record(r, R.roles)]
    # Delivery: every recorded line reached the player's notebook.
    for r in recs:
        log = {e["text"] for e in g.p(r["pid"]).log}
        for line in r["lines"]:
            if line not in log:
                bad.append(f"not delivered to {g.p(r['pid']).name}: {line}")
    # Completeness: everyone who should get info got some.
    got = {(r["night"], r["pid"], r["key"]) for r in recs}
    n_players = len(g.seated())
    for night, info in g.estate.get("audit_nights", {}).items():
        deaths = set(info["deaths"])
        for x in info["start"]:
            if not x["alive"]:
                continue
            ends_alive = x["id"] not in deaths
            name = g.p(x["id"]).name
            ans = info["answers"].get(x["id"], {})
            want = set()
            # A character changed tonight (Imp star-pass, Pit-Hag, Barber, Snake Charmer)
            # acts as whatever it is when its turn comes, so expect only abilities held
            # at both dusk and dawn.
            held = [ab for ab in x["abilities"] if ab in info.get("end", {}).get(x["id"], x["abilities"])]
            for ab in held:
                if night == 1 and ab in FIRST_NIGHT_INFO:
                    if ab != "grandmother" or g.estate.get("grandchild"):
                        want.add(ab)
                if ab in EVERY_NIGHT_INFO and ends_alive:
                    want.add(ab)
                if night > 1 and ab in OTHER_NIGHT_INFO and ends_alive:
                    want.add(ab)
                if ab in CHOICE_INFO and ans.get(ab) and ends_alive:
                    want.add(ab)
                if ab == "undertaker" and night > 1 and info["executed_died"] and ends_alive:
                    want.add(ab)
                if ab == "juggler" and x["id"] in info["juggler"] and ends_alive:
                    want.add(ab)
                if ab == "ravenkeeper" and x["id"] in deaths:
                    want.add(ab)
                if ab == "sage" and x["id"] in info["demon_kills"]:
                    want.add(ab)
            if night == 1 and R.type_of(x["role"]) == "demon" and (n_players >= 7 or g.settings["demon_bluffs"]):
                want.add("demon_info")
            if night == 1 and R.type_of(x["role"]) == "minion" and n_players >= 7:
                want.add("minion_info")
            for k in want:
                if (night, x["id"], k) not in got:
                    bad.append(f"night {night}: {name} ({k}) got no info")
    return bad
