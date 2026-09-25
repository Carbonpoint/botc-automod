"""Trouble Brewing, the beginner edition.

Night order (official):
  First night:  Minion info, Demon info (7+ players), Poisoner, Spy,
                Washerwoman, Librarian, Investigator, Chef, Empath,
                Fortune Teller, Butler
  Other nights: Poisoner, Monk, Scarlet Woman, Imp, Ravenkeeper,
                Undertaker, Empath, Fortune Teller, Butler, Spy

On a phone night everybody acts at the same time, so the night runs in
two stages. Stage A collects all choices. They then resolve in the order
above. Stage B gives out information and wakes a dead Ravenkeeper.
Everyone has a task in both stages, so nobody can tell who acts.

"Truthful" means the player really has the character they believe they
have, and is not poisoned. A Drunk or poisoned player gets false info.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from .base import Edition, Role

if TYPE_CHECKING:
    from ..game import Game, Player

R = Role
ROLES = {r.id: r for r in [
    R("washerwoman", "Washerwoman", "townsfolk",
      "You start knowing that 1 of 2 players is a particular Townsfolk.", "chill",
      "You get your info on the first night. Share it when it helps."),
    R("librarian", "Librarian", "townsfolk",
      "You start knowing that 1 of 2 players is a particular Outsider. (Or that zero are in play.)", "chill",
      "You get your info on the first night. Outsiders often hide; find them."),
    R("investigator", "Investigator", "townsfolk",
      "You start knowing that 1 of 2 players is a particular Minion.", "chill",
      "You get your info on the first night. One of your two players is evil."),
    R("chef", "Chef", "townsfolk",
      "You start knowing how many pairs of evil players there are.", "think",
      "A pair means two evil players sitting next to each other."),
    R("empath", "Empath", "townsfolk",
      "Each night, you learn how many of your 2 alive neighbours are evil.", "think",
      "Your number changes when your neighbours die. Track it every night."),
    R("fortuneteller", "Fortune Teller", "townsfolk",
      "Each night, choose 2 players: you learn if either is a Demon. "
      "There is a good player that registers as a Demon to you.", "think",
      "One good player always shows 'yes' to you: the red herring."),
    R("undertaker", "Undertaker", "townsfolk",
      "Each night*, you learn which character died by execution today.", "think",
      "You learn the true character of each executed player."),
    R("monk", "Monk", "townsfolk",
      "Each night*, choose a player (not yourself): they are safe from the Demon tonight.", "think",
      "Protect players you think the Demon wants dead."),
    R("ravenkeeper", "Ravenkeeper", "townsfolk",
      "If you die at night, you are woken to choose a player: you learn their character.", "chill",
      "If the Demon kills you, you get one strong piece of info."),
    R("virgin", "Virgin", "townsfolk",
      "The 1st time you are nominated, if the nominator is a Townsfolk, they are executed immediately.", "chill",
      "Invite a nomination: it can prove who is a Townsfolk."),
    R("slayer", "Slayer", "townsfolk",
      "Once per game, during the day, publicly choose a player: if they are the Demon, they die.", "chill",
      "Use the Slayer button on the Town screen. Anyone may bluff it."),
    R("soldier", "Soldier", "townsfolk",
      "You are safe from the Demon.", "chill",
      "The Demon cannot kill you at night."),
    R("mayor", "Mayor", "townsfolk",
      "If only 3 players live & no execution occurs, your team wins. "
      "If you die at night, another player might die instead.", "chill",
      "With 3 players left, ask the town not to execute."),
    R("butler", "Butler", "outsider",
      "Each night, choose a player (not yourself): tomorrow, you may only vote if they are voting too.", "think",
      "Your yes vote only counts if your master also votes yes."),
    R("drunk", "Drunk", "outsider",
      "You do not know you are the Drunk. You think you are a Townsfolk character, but you are not.", "chill",
      "Your information may be wrong."),
    R("recluse", "Recluse", "outsider",
      "You might register as evil & as a Minion or Demon, even if dead.", "chill",
      "Others may get info that you are evil."),
    R("saint", "Saint", "outsider",
      "If you die by execution, your team loses.", "chill",
      "Stay off the chopping block."),
    R("poisoner", "Poisoner", "minion",
      "Each night, choose a player: they are poisoned tonight and tomorrow day.", "think",
      "Poison the players whose info could expose your team."),
    R("spy", "Spy", "minion",
      "Each night, you see the Grimoire. You might register as good & as a Townsfolk or Outsider, even if dead.", "think",
      "You see every character. Feed your Demon the truth and lie to the town."),
    R("scarletwoman", "Scarlet Woman", "minion",
      "If there are 5 or more players alive & the Demon dies, you become the Demon. (Travellers don't count.)",
      "chill", "Keep yourself alive. If the Demon dies early, you take over."),
    R("baron", "Baron", "minion",
      "There are extra Outsiders in play. [+2 Outsiders]", "chill",
      "Two more Outsiders are in play because of you."),
    R("imp", "Imp", "demon",
      "Each night*, choose a player: they die. If you kill yourself this way, a Minion becomes the Imp.", "think",
      "Kill at night. Bluff a good character by day."),
]}

TOWNSFOLK = [r.id for r in ROLES.values() if r.type == "townsfolk"]
OUTSIDERS = [r.id for r in ROLES.values() if r.type == "outsider"]
MINIONS = [r.id for r in ROLES.values() if r.type == "minion"]

# players: (townsfolk, outsiders, minions, demons)
DISTRIBUTION = {
    5: (3, 0, 1, 1), 6: (3, 1, 1, 1), 7: (5, 0, 1, 1), 8: (5, 1, 1, 1),
    9: (5, 2, 1, 1), 10: (7, 0, 2, 1), 11: (7, 1, 2, 1), 12: (7, 2, 2, 1),
    13: (9, 0, 3, 1), 14: (9, 1, 3, 1), 15: (9, 2, 3, 1),
}


def choose(key: str, title: str, text: str, pick: int, candidates: list[str]) -> dict:
    return {"kind": "choose", "key": key, "title": title, "text": text,
            "pick": pick, "candidates": candidates}


def info(key: str, title: str, lines: list[str]) -> dict:
    return {"kind": "info", "key": key, "title": title, "lines": lines}


class TroubleBrewing(Edition):
    id = "tb"
    name = "Trouble Brewing"
    min_players = 5
    max_players = 15
    roles = ROLES

    # Status helpers ------------------------------------------------------------
    def poisoned(self, game: Game, p: Player) -> bool:
        return game.estate.get("poisoned") == p.id

    def works(self, game: Game, p: Player, role: str) -> bool:
        """p truly has this character, is alive and is not poisoned."""
        return p.role == role and p.alive and not self.poisoned(game, p)

    def truthful(self, game: Game, p: Player) -> bool:
        return p.role == p.shown and not self.poisoned(game, p)

    def reg(self, game: Game, p: Player) -> dict:
        """How p registers to abilities now. The Spy and Recluse may misregister.

        One answer per player per night or day, so two abilities agree.
        """
        cache = game.estate.setdefault("reg", {})
        key = f"{game.label()}:{p.id}"
        if key in cache:
            return cache[key]
        role = ROLES[p.role]
        out = {"team": role.team, "type": role.type, "role": role.id}
        chance = game.settings["misregister"]
        if p.role == "spy" and not self.poisoned(game, p) and game.rng.random() < chance:
            fake = game.rng.choice(TOWNSFOLK + OUTSIDERS)
            out = {"team": "good", "type": ROLES[fake].type, "role": fake}
        elif p.role == "recluse" and not self.poisoned(game, p) and game.rng.random() < chance:
            fake = game.rng.choice(MINIONS + ["imp"])
            out = {"team": "evil", "type": ROLES[fake].type, "role": fake}
        cache[key] = out
        return out

    # Setup ---------------------------------------------------------------------
    def setup(self, game: Game) -> None:
        from ..assign import deal

        rng = game.rng
        players = game.seated()
        t, o, m, _ = DISTRIBUTION[len(players)]
        minions = rng.sample(MINIONS, m)
        if "baron" in minions:
            t, o = t - 2, o + 2
        outsiders = rng.sample(OUTSIDERS, o)
        townsfolk = rng.sample(TOWNSFOLK, t)
        in_play = townsfolk + outsiders + minions + ["imp"]
        drunk_as = None
        if "drunk" in outsiders:
            drunk_as = rng.choice([x for x in TOWNSFOLK if x not in townsfolk])
        shown = [drunk_as if r == "drunk" else r for r in in_play]
        slots = [(ROLES[r].team, ROLES[s].style) for r, s in zip(in_play, shown)]
        perm = deal([p.prefs for p in players], slots, rng)
        for p, j in zip(players, perm):
            p.role, p.shown = in_play[j], shown[j]
        pool = [x for x in TOWNSFOLK if x not in townsfolk and x != drunk_as]
        good = [p for p in players if ROLES[p.role].team == "good"]
        game.estate.update({
            "bluffs": rng.sample(pool, 3),
            "red_herring": rng.choice(good).id,
            "poisoned": None, "protected": None, "master": None,
            "virgin_used": [], "slayer_used": False,
        })

    # Night ---------------------------------------------------------------------
    def on_dusk(self, game: Game) -> None:
        game.estate.update({"poisoned": None, "protected": None, "master": None, "reg": {}})

    def stage_a(self, game: Game) -> dict[str, list[dict]]:
        tasks: dict[str, list[dict]] = defaultdict(list)
        seated, alive = game.seated(), game.alive()
        first = game.night == 1
        ids = [p.id for p in alive]
        if first and len(seated) >= 7:
            demon = next(p for p in seated if p.role == "imp")
            minions = [p for p in seated if ROLES[p.role].type == "minion"]
            bluffs = ", ".join(ROLES[b].name for b in game.estate["bluffs"])
            for mp in minions:
                others = [x.name for x in minions if x is not mp]
                lines = [f"The Demon is {demon.name}."]
                if others:
                    lines.append("Your fellow Minions: " + ", ".join(others) + ".")
                tasks[mp.id].append(info("minion_info", "Your evil team", lines))
            tasks[demon.id].append(info("demon_info", "Your evil team", [
                "Your Minions: " + ", ".join(x.name for x in minions) + ".",
                f"These good characters are not in play, so they are safe to bluff: {bluffs}."]))
        for p in alive:
            others = [x for x in ids if x != p.id]
            s = p.shown
            if s == "poisoner":
                tasks[p.id].append(choose("poisoner", "Poisoner", "Choose a player to poison.", 1, ids))
            elif s == "monk" and not first:
                tasks[p.id].append(choose("monk", "Monk", "Choose a player to protect from the Demon.",
                                          1, others))
            elif s == "imp" and not first:
                tasks[p.id].append(choose("imp", "Imp", "Choose a player to kill. "
                                          "Choose yourself to pass the Demon to a Minion.", 1, ids))
            elif s == "fortuneteller":
                tasks[p.id].append(choose("fortuneteller", "Fortune Teller",
                                          "Choose 2 players. You learn if either is a Demon.",
                                          2, [x.id for x in seated]))
            elif s == "butler":
                tasks[p.id].append(choose("butler", "Butler",
                                          "Choose your master. Tomorrow your vote counts only if they vote too.",
                                          1, others))
        return tasks

    def resolve_a(self, game: Game, answers: dict[str, dict]) -> dict[str, list[dict]]:
        es, rng = game.estate, game.rng
        first = game.night == 1
        out: dict[str, list[dict]] = defaultdict(list)

        def pick(p: Player, key: str) -> list[str] | None:
            return answers.get(p.id, {}).get(key)

        # Poisoner
        for p in game.alive():
            if p.role == "poisoner" and (c := pick(p, "poisoner")):
                es["poisoned"] = c[0]
        # Monk
        for p in game.alive():
            if p.shown == "monk" and (c := pick(p, "monk")) and self.works(game, p, "monk"):
                es["protected"] = c[0]
        # Imp
        if not first:
            imp = next((p for p in game.alive() if p.role == "imp"), None)
            c = pick(imp, "imp") if imp else None
            if imp and c and not self.poisoned(game, imp):
                self._imp_kill(game, imp, game.p(c[0]), out)
        # Ravenkeeper: woken if killed tonight
        for pid in game.tonight_deaths:
            p = game.p(pid)
            if p.shown == "ravenkeeper":
                out[p.id].append(choose("ravenkeeper", "Ravenkeeper",
                                        "You died tonight. Choose a player: you learn their character.",
                                        1, [x.id for x in game.seated()]))
        # Information, in night order
        for p in game.seated():
            if not p.alive:
                continue
            s = p.shown
            lines: list[str] = []
            if first and s == "washerwoman":
                lines = self._ping(game, p, "townsfolk")
            elif first and s == "librarian":
                lines = self._ping(game, p, "outsider")
            elif first and s == "investigator":
                lines = self._ping(game, p, "minion")
            elif first and s == "chef":
                lines = self._chef(game, p)
            elif not first and s == "undertaker" and game.executed_today:
                lines = self._undertaker(game, p)
            elif s == "empath":
                lines = self._empath(game, p)
            elif s == "fortuneteller" and (c := pick(p, "fortuneteller")):
                lines = self._fortune(game, p, c)
            elif s == "spy":
                lines = self._spy(game, p)
            if lines:
                out[p.id].append(info(s, ROLES[s].name, lines))
                for line in lines:
                    p.note(game.label(), line)
        # Butler
        for p in game.alive():
            if p.shown == "butler" and (c := pick(p, "butler")):
                es["master"] = c[0]
                p.note(game.label(), f"Your master tomorrow is {game.p(c[0]).name}.")
        return out

    def resolve_b(self, game: Game, answers: dict[str, dict]) -> None:
        for pid, ans in answers.items():
            if "ravenkeeper" in ans:
                p, t = game.p(pid), game.p(ans["ravenkeeper"][0])
                role = self.reg(game, t)["role"]
                if not self.truthful(game, p):
                    role = game.rng.choice([r for r in ROLES if r != role])
                p.note(game.label(), f"{t.name} is the {ROLES[role].name}.")

    def _imp_kill(self, game: Game, imp: Player, target: Player, out: dict) -> None:
        es = game.estate
        if target.id == imp.id:
            alive_before = len(game.alive())
            game.kill(imp.id, "demon")
            new = self._pass_demon(game, imp, alive_before, starpass=True)
            if new:
                out[new.id].append(info("new_imp", "You are now the Imp",
                                        ["The Imp died. You are now the Imp. From tomorrow night you kill."]))
            return
        if not target.alive or es.get("protected") == target.id or self.works(game, target, "soldier"):
            return
        if self.works(game, target, "mayor") and game.rng.random() < game.settings["mayor_bounce"]:
            pool = [x for x in game.alive() if x.id not in (target.id, imp.id)
                    and es.get("protected") != x.id and not self.works(game, x, "soldier")]
            if pool:
                target = game.rng.choice(pool)
        game.kill(target.id, "demon")

    def _pass_demon(self, game: Game, old: Player, alive_before: int, starpass: bool) -> Player | None:
        minions = [x for x in game.alive() if ROLES[x.role].type == "minion"]
        sw = next((x for x in minions if x.role == "scarletwoman" and not self.poisoned(game, x)), None)
        if sw and alive_before >= 5:
            new = sw
        elif starpass and minions:
            new = game.rng.choice(minions)
        else:
            return None
        new.role = new.shown = "imp"
        new.note(game.label(), "The Demon died. You are now the Imp. "
                 "Each night from now on you choose a player to kill.")
        return new

    # Information builders ------------------------------------------------------------
    def _ping(self, game: Game, p: Player, kind: str) -> list[str]:
        rng = game.rng
        others = [x for x in game.seated() if x.id != p.id]
        pool = [r for r in ROLES.values() if r.type == kind]
        if self.truthful(game, p):
            hits = [x for x in others if self.reg(game, x)["type"] == kind]
            if not hits:
                return ["There are no Outsiders in play."] if kind == "outsider" else []
            hit = rng.choice(hits)
            role = ROLES[self.reg(game, hit)["role"]]
            other = rng.choice([x for x in others if x is not hit])
            pair = [hit, other]
        else:
            has_kind = any(ROLES[x.role].type == kind for x in others)
            if kind == "outsider" and has_kind and rng.random() < 0.3:
                return ["There are no Outsiders in play."]
            pair = rng.sample(others, 2)
            wrong = [r for r in pool if r.id not in (pair[0].role, pair[1].role)]
            role = rng.choice(wrong or pool)
        rng.shuffle(pair)
        return [f"One of {pair[0].name} and {pair[1].name} is the {role.name}."]

    def _chef(self, game: Game, p: Player) -> list[str]:
        seated = game.seated()
        n = len(seated)
        evil = [self.reg(game, x)["team"] == "evil" for x in seated]
        pairs = sum(1 for i in range(n) if evil[i] and evil[(i + 1) % n])
        if not self.truthful(game, p):
            pairs = game.rng.choice([k for k in range(4) if k != pairs])
        return [f"There {'is' if pairs == 1 else 'are'} {pairs} pair{'' if pairs == 1 else 's'} of evil players."]

    def _neighbours(self, game: Game, p: Player) -> list[Player]:
        seated = game.seated()
        i, n = seated.index(p), len(seated)
        found: list[Player] = []
        for step in (-1, 1):
            for k in range(1, n):
                x = seated[(i + step * k) % n]
                if x.alive and x is not p:
                    if x not in found:
                        found.append(x)
                    break
        return found

    def _empath(self, game: Game, p: Player) -> list[str]:
        count = sum(1 for x in self._neighbours(game, p) if self.reg(game, x)["team"] == "evil")
        if not self.truthful(game, p):
            count = game.rng.choice([k for k in range(3) if k != count])
        return [f"{count} of your alive neighbours {'is' if count == 1 else 'are'} evil."]

    def _fortune(self, game: Game, p: Player, chosen: list[str]) -> list[str]:
        targets = [game.p(x) for x in chosen]
        yes = any(self.reg(game, t)["type"] == "demon" or t.id == game.estate["red_herring"]
                  for t in targets)
        if not self.truthful(game, p):
            yes = game.rng.random() < 0.5
        names = " and ".join(t.name for t in targets)
        return [f"{names}: {'YES, one of them is' if yes else 'NO, neither is'} the Demon."]

    def _undertaker(self, game: Game, p: Player) -> list[str]:
        t = game.p(game.executed_today)
        role = self.reg(game, t)["role"]
        if not self.truthful(game, p):
            role = game.rng.choice([r for r in ROLES if r != role])
        return [f"Today's executed player, {t.name}, was the {ROLES[role].name}."]

    def _spy(self, game: Game, p: Player) -> list[str]:
        es = game.estate
        rows = [(x, ROLES[x.role].name) for x in game.seated()]
        if self.poisoned(game, p) and len(rows) > 2:
            i, j = game.rng.sample(range(len(rows)), 2)
            rows[i], rows[j] = (rows[i][0], rows[j][1]), (rows[j][0], rows[i][1])
        lines = ["The Grimoire:"]
        for x, name in rows:
            tags = []
            if x.shown != x.role and not self.poisoned(game, p):
                tags.append(f"thinks they are the {ROLES[x.shown].name}")
            if not x.alive:
                tags.append("dead")
            if es.get("poisoned") == x.id:
                tags.append("poisoned")
            if es.get("red_herring") == x.id:
                tags.append("Fortune Teller red herring")
            lines.append(f"{x.name}: {name}" + (f" ({', '.join(tags)})" if tags else ""))
        return lines

    # Day -------------------------------------------------------------------------------
    def on_nominate(self, game: Game, nominator: Player, nominee: Player) -> bool:
        es = game.estate
        if nominee.shown != "virgin" or nominee.id in es["virgin_used"]:
            return False
        es["virgin_used"].append(nominee.id)
        if self.works(game, nominee, "virgin") and self.reg(game, nominator)["type"] == "townsfolk":
            game.executed_today = nominator.id
            game.announce(f"{nominator.name} is executed immediately! The day is over.")
            game.kill(nominator.id, "execution")
            return True
        return False

    def count_votes(self, game: Game, votes: dict[str, bool]) -> int:
        master = game.estate.get("master")
        count = 0
        for pid, yes in votes.items():
            if not yes:
                continue
            v = game.p(pid)
            if self.works(game, v, "butler") and not (master and votes.get(master)):
                continue
            count += 1
        return count

    def on_execution(self, game: Game, player: Player) -> None:
        if not player.alive:
            return
        alive_before = len(game.alive())
        game.kill(player.id, "execution")
        if player.role == "saint" and not self.poisoned(game, player):
            game.estate["saint_executed"] = True
        if player.role == "imp":
            self._pass_demon(game, player, alive_before, starpass=False)

    def on_no_execution(self, game: Game) -> None:
        alive = game.alive()
        if len(alive) == 3 and any(self.works(game, x, "mayor") for x in alive):
            game.estate["mayor_win"] = True

    def slayer_shot(self, game: Game, shooter: Player, target: Player) -> None:
        es = game.estate
        text = f"{shooter.name} claims to be the Slayer and shoots {target.name}."
        if self.works(game, shooter, "slayer") and not es["slayer_used"]:
            es["slayer_used"] = True
            if target.alive and self.reg(game, target)["type"] == "demon":
                alive_before = len(game.alive())
                game.kill(target.id, "slayer")
                game.announce(f"{text} {target.name} dies!")
                if target.role == "imp":
                    self._pass_demon(game, target, alive_before, starpass=False)
                return
        game.announce(f"{text} Nothing happens.")

    def check_win(self, game: Game) -> tuple[str, str] | None:
        es = game.estate
        if es.get("saint_executed"):
            return "evil", "The Saint was executed."
        if not any(p.role == "imp" for p in game.alive()):
            return "good", "The Demon is dead."
        if len(game.alive()) <= 2:
            return "evil", "Only two players are left alive."
        if es.get("mayor_win"):
            return "good", "Three players live, nobody was executed, and the Mayor is alive."
        return None
