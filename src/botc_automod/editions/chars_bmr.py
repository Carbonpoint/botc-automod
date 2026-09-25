"""Bad Moon Rising characters.

Automod choices where a human storyteller would decide:
- Sailor: a chosen Townsfolk gets drunk; otherwise the Sailor does.
- Innkeeper: one of the two protected players, at random, is drunk.
- Gossip: a true statement kills a random living, killable player tonight.
- Tinker: dies at night with chance `tinker_chance`.
- Pacifist: an executed good player survives with chance `pacifist_save`.
- Shabaloth: regurgitates with chance `shabaloth_regurgitate`.
- Godfather: the Outsider change (-1 or +1) is random.
"""

from __future__ import annotations

from .chars_tb import demon_attack, demon_blocked, lunatic_report
from .rules import Char, choose, choose_character, choose_player_character, everyone, others


def alive_ids(game):
    return everyone(game, alive=True)


class Grandmother(Char):
    id, name, type, style, first_night = "grandmother", "Grandmother", "townsfolk", "chill", True

    def setup(self, R, game, p):
        good = [x for x in game.seated() if x.id != p.id and R.roles[x.role].team == "good"]
        if good:
            game.estate["grandchild"] = game.rng.choice(good).id

    def resolve(self, R, ctx, p, ans):
        g = ctx.game
        gc = g.estate.get("grandchild")
        if not gc:
            return
        t = g.p(gc)
        role = R.roles[t.role]
        if not R.truthful(g, p, self.id):
            t = R.pick_other(g, {p.id}) or t
            role = g.rng.choice([r for r in R.roles.values() if r.team == "good" and r.id != t.role])
        ctx.tell(p, self.name, [f"Your grandchild is {t.name}, the {role.name}."], self.id)

    def on_any_death(self, R, game, holder, dead, cause, ctx):
        if (holder.role == self.id and cause == "demon" and dead.id == game.estate.get("grandchild")
                and holder.alive and not R.malfunction(game, holder)):
            R.die(game, holder, "grandmother", None, ctx, force=True)


class Sailor(Char):
    id, name, type, style = "sailor", "Sailor", "townsfolk", "chill"
    first_night = other_nights = True

    def task(self, R, game, p, first):
        return choose(self.id, self.name, "Choose an alive player: you or they are drunk until dusk.",
                      1, alive_ids(game))

    def resolve(self, R, ctx, p, ans):
        if not ans:
            return
        g = ctx.game
        t = g.p(ans[0])
        R.chose(g, p, [t])
        if not R.works(g, p, self.id):
            return
        drunk = t if (t.id != p.id and R.type_of(t.role) == "townsfolk") else p
        R.add_status(g, drunk.id, "drunk", "Sailor", "dusk")


class Chambermaid(Char):
    id, name, type, style = "chambermaid", "Chambermaid", "townsfolk", "think"
    first_night = other_nights = True

    def task(self, R, game, p, first):
        return choose(self.id, self.name, "Choose 2 alive players (not yourself): you learn how many "
                      "woke tonight due to their ability.", 2, others(game, p))

    def resolve(self, R, ctx, p, ans):
        if not ans:
            return
        g = ctx.game
        targets = [g.p(x) for x in ans]
        R.chose(g, p, targets)
        woke = set(g.estate.get("woke", []))
        for pid, tasks in ctx.out.items():
            if any(t["key"] in R.chars for t in tasks):
                woke.add(pid)
        count = sum(1 for t in targets if t.id in woke)
        if not R.truthful(g, p, self.id):
            count = g.rng.choice([k for k in range(3) if k != count])
        ctx.tell(p, self.name, [f"{count} of {' and '.join(t.name for t in targets)} woke tonight."], self.id)


class Exorcist(Char):
    id, name, type, style, other_nights = "exorcist", "Exorcist", "townsfolk", "think", True

    def task(self, R, game, p, first):
        last = game.estate.get("exorcist_last", {}).get(p.id)
        return choose(self.id, self.name, "Choose a player (not the one from last night). "
                      "If they are the Demon, they do not act tonight.", 1,
                      [x for x in everyone(game, alive=True) if x != last])

    def resolve(self, R, ctx, p, ans):
        g = ctx.game
        if not ans:
            return
        t = g.p(ans[0])
        g.estate.setdefault("exorcist_last", {})[p.id] = t.id
        R.chose(g, p, [t])
        if R.works(g, p, self.id) and R.type_of(t.role) == "demon":
            g.estate["exorcised"] = [t.id]
            ctx.tell(t, "The Exorcist", [f"{p.name} is the Exorcist and chose you. You do not act tonight."],
                     self.id)


class Innkeeper(Char):
    id, name, type, style, other_nights = "innkeeper", "Innkeeper", "townsfolk", "think", True

    def task(self, R, game, p, first):
        return choose(self.id, self.name, "Choose 2 players: they can't die tonight, but 1 is drunk until dusk.",
                      2, everyone(game, alive=True))

    def resolve(self, R, ctx, p, ans):
        if not ans:
            return
        g = ctx.game
        targets = [g.p(x) for x in ans]
        R.chose(g, p, targets)
        if not R.works(g, p, self.id):
            return
        for t in targets:
            R.add_status(g, t.id, "safe_all", "Innkeeper", "dawn")
        R.add_status(g, g.rng.choice(targets).id, "drunk", "Innkeeper", "dusk")


class Gambler(Char):
    id, name, type, style, other_nights = "gambler", "Gambler", "townsfolk", "think", True

    def task(self, R, game, p, first):
        return choose_player_character(self.id, self.name, "Choose a player and guess their character. "
                                       "If you guess wrong, you die.", everyone(game), list(R.roles.values()))

    def resolve(self, R, ctx, p, ans):
        if not ans:
            return
        g = ctx.game
        t = g.p(ans["player"])
        R.chose(g, p, [t])
        if R.works(g, p, self.id) and t.role != ans["character"]:
            R.die(g, p, "gambler", p, ctx)


class Gossip(Char):
    id, name, type, style, other_nights = "gossip", "Gossip", "townsfolk", "chill", True

    def public_action(self, R, game):
        return {"key": "gossip", "label": "Make a Gossip statement", "kind": "statement", "public": True,
                "help": "Anyone may claim to be the Gossip. If the real Gossip's statement is true, "
                        "a player dies tonight."}

    def do_action(self, R, game, p, payload):
        es = game.estate
        es.setdefault("claimed", {}).setdefault(p.id, []).append("gossip")
        text = R.statement_text(game, payload)
        if not text:
            from ..game import GameError
            raise GameError("Make a statement first.")
        game.announce(f"{p.name}, as the Gossip, states: “{text}.”")
        truth = R.statement_true(game, payload)
        if p.shown == self.id or self.id in p.gained:
            es["gossip_true"] = bool(truth)

    def step(self, R, ctx):
        g = ctx.game
        es = g.estate
        if not es.pop("gossip_true", False):
            return
        if not any(R.works(g, x, self.id) for x in g.seated()):
            return
        pool = [x for x in R.living(g) if not R.protected(g, x, "ability")]
        if pool:
            R.die(g, g.rng.choice(pool), "gossip", None, ctx)


class Courtier(Char):
    id, name, type, style = "courtier", "Courtier", "townsfolk", "think"
    first_night = other_nights = True

    def task(self, R, game, p, first):
        if R.used(game, p, self.id):
            return None
        return choose_character(self.id, self.name, "Once per game: choose a character. They are drunk for "
                                "3 nights & 3 days. Or choose no one to wait.", list(R.roles.values()),
                                allow_none=True)

    def resolve(self, R, ctx, p, ans):
        if not ans:
            return
        g = ctx.game
        R.use(g, p, self.id)
        if not R.works(g, p, self.id):
            return
        for t in g.seated():
            if t.role == ans:
                R.chose(g, p, [t])
                R.add_status(g, t.id, "drunk", "Courtier", "dusk+3", source_pid=p.id)


class Professor(Char):
    id, name, type, style, other_nights = "professor", "Professor", "townsfolk", "think", True

    def task(self, R, game, p, first):
        if R.used(game, p, self.id):
            return None
        dead = [x.id for x in game.seated() if not x.alive or x.fake_dead]
        if not dead:
            return None
        return choose(self.id, self.name, "Once per game: choose a dead player. If they are a Townsfolk, "
                      "they are resurrected. Or choose no one to wait.", 1, dead, allow_none=True)

    def resolve(self, R, ctx, p, ans):
        if not ans:
            return
        g = ctx.game
        R.use(g, p, self.id)
        t = g.p(ans[0])
        R.chose(g, p, [t])
        if R.works(g, p, self.id) and R.type_of(t.role) == "townsfolk" and not t.alive:
            R.revive(g, t)


class Minstrel(Char):
    id, name, type, style = "minstrel", "Minstrel", "townsfolk", "chill"

    def after_execution(self, R, game, player, died):
        if not died or R.type_of(player.role) != "minion":
            return
        m = next((x for x in game.seated() if R.works(game, x, self.id)), None)
        if not m:
            return
        for x in game.seated():
            if x.id != m.id:
                R.add_status(game, x.id, "drunk", "Minstrel", "dusk+2")


class TeaLady(Char):
    id, name, type, style = "tealady", "Tea Lady", "townsfolk", "chill"


class Pacifist(Char):
    id, name, type, style = "pacifist", "Pacifist", "townsfolk", "chill"


class Fool(Char):
    id, name, type, style = "fool", "Fool", "townsfolk", "chill"


class Tinker(Char):
    id, name, type, style, other_nights = "tinker", "Tinker", "outsider", "chill", True

    def step(self, R, ctx):
        g = ctx.game
        for p in g.seated():
            if R.works(g, p, self.id) and g.rng.random() < g.settings["tinker_chance"]:
                R.die(g, p, "tinker", None, ctx)


class Moonchild(Char):
    id, name, type, style, other_nights = "moonchild", "Moonchild", "outsider", "chill", True
    works_dead = True

    def on_death(self, R, game, p, cause, ctx):
        if p.shown != self.id:
            return
        key = "death_prompts_pending" if game.phase == "night" else "death_prompts"
        game.estate.setdefault(key, []).append(p.id)

    def death_prompt(self, R, game, p):
        return {"key": "moonchild", "label": "You died: choose a player (Moonchild)", "kind": "target",
                "public": True, "forced": True, "candidates": everyone(game, alive=True),
                "help": "Publicly choose 1 alive player. Tonight, if they are good, they die."}

    def do_action(self, R, game, p, payload):
        t = game.p(payload["target"])
        game.estate["death_prompts"].remove(p.id)
        game.announce(f"{p.name}, as the Moonchild, chooses {t.name}.")
        if R.works(game, p, self.id) and R.alignment(t) == "good":
            game.estate["moonchild_target"] = t.id

    def step(self, R, ctx):
        tid = ctx.game.estate.pop("moonchild_target", None)
        if tid:
            R.die(ctx.game, ctx.game.p(tid), "moonchild", None, ctx)


class Goon(Char):
    id, name, type, style = "goon", "Goon", "outsider", "chill"


class Lunatic(Char):
    id, name, type, style = "lunatic", "Lunatic", "outsider", "chill"


class Godfather(Char):
    id, name, type, style = "godfather", "Godfather", "minion", "think"
    first_night = other_nights = True
    outsider_mod = (-1, 1)

    def task(self, R, game, p, first):
        if first or not game.estate.get("outsider_died_today"):
            return None
        return choose(self.id, self.name, "An Outsider died today. Choose a player: they die.", 1,
                      everyone(game, alive=True))

    def step(self, R, ctx):
        g = ctx.game
        for p in R.acting(g, self.id):
            if ctx.first:
                outs = [R.roles[x.role].name for x in g.seated() if R.type_of(x.role) == "outsider"]
                if not R.truthful(g, p, self.id):
                    outs = [r.name for r in g.rng.sample([r for r in R.roles.values() if r.type == "outsider"], 2)]
                ctx.tell(p, self.name, ["Outsiders in play: " + (", ".join(outs) or "none") + "."], self.id)
                continue
            ans = ctx.answer(p, self.id)
            if ans:
                t = g.p(ans[0])
                R.chose(g, p, [t])
                if R.works(g, p, self.id):
                    R.die(g, t, "minion", p, ctx)


class DevilsAdvocate(Char):
    id, name, type, style = "devilsadvocate", "Devil's Advocate", "minion", "think"
    first_night = other_nights = True

    def task(self, R, game, p, first):
        last = game.estate.get("da_last", {}).get(p.id)
        return choose(self.id, self.name, "Choose a living player (not last night's): if executed tomorrow, "
                      "they don't die.", 1, [x for x in everyone(game, alive=True) if x != last])

    def resolve(self, R, ctx, p, ans):
        if not ans:
            return
        g = ctx.game
        t = g.p(ans[0])
        g.estate.setdefault("da_last", {})[p.id] = t.id
        R.chose(g, p, [t])
        if R.works(g, p, self.id):
            R.add_status(g, t.id, "safe_exec", "Devil's Advocate", "dusk", source_pid=p.id)


class Assassin(Char):
    id, name, type, style, other_nights = "assassin", "Assassin", "minion", "think", True

    def task(self, R, game, p, first):
        if R.used(game, p, self.id):
            return None
        return choose(self.id, self.name, "Once per game: choose a player. They die, even if they could not. "
                      "Or choose no one to wait.", 1, everyone(game, alive=True), allow_none=True)

    def resolve(self, R, ctx, p, ans):
        if not ans:
            return
        g = ctx.game
        R.use(g, p, self.id)
        t = g.p(ans[0])
        R.chose(g, p, [t])
        if R.works(g, p, self.id):
            R.die(g, t, "minion", p, ctx, force=True)


class Mastermind(Char):
    id, name, type, style = "mastermind", "Mastermind", "minion", "chill"

    def after_execution(self, R, game, player, died):
        es = game.estate
        if es.get("mastermind_day") and game.day == es["mastermind_day"]:
            team = R.alignment(player)
            es["win"] = ("evil", f"The Mastermind's extra day: {player.name}, a good player, was executed.") \
                if team == "good" else ("good", f"The Mastermind's extra day: {player.name} was evil.")
            es["mastermind_day"] = None
            return
        if not died or R.type_of(player.role) != "demon":
            return
        if any(R.type_of(x.role) == "demon" for x in game.seated() if x.alive):
            return
        if any(R.works(game, x, self.id) for x in game.seated()):
            es["mastermind_day"] = game.day + 1

    def after_no_execution(self, R, game):
        es = game.estate
        if es.get("mastermind_day") and game.day == es["mastermind_day"]:
            es["win"] = ("good", "The Mastermind's extra day ended with no execution.")
            es["mastermind_day"] = None


class Zombuul(Char):
    id, name, type, style, other_nights = "zombuul", "Zombuul", "demon", "think", True

    def task(self, R, game, p, first):
        if game.estate.get("died_today"):
            return None
        return choose(self.id, self.name, "Nobody died today. Choose a player: they die.", 1,
                      everyone(game, alive=True))

    def resolve(self, R, ctx, p, ans):
        if not ans or lunatic_report(R, ctx, p, ans):
            return
        g = ctx.game
        t = g.p(ans[0])
        R.chose(g, p, [t])
        if not demon_blocked(R, ctx, p):
            demon_attack(R, ctx, p, t)


class Pukka(Char):
    id, name, type, style = "pukka", "Pukka", "demon", "think"
    first_night = other_nights = True

    def task(self, R, game, p, first):
        return choose(self.id, self.name, "Choose a player: they are poisoned. "
                      "Your previous choice dies.", 1, everyone(game, alive=True))

    def step(self, R, ctx):
        g = ctx.game
        es = g.estate
        for p in R.acting(g, self.id):
            ans = ctx.answer(p, self.id)
            if lunatic_report(R, ctx, p, ans):
                continue
            if R.malfunction(g, p):
                # A drunk Pukka neither poisons nor kills; the old victim waits.
                R.abnormal(g, p)
                continue
            exorcised = p.id in es.get("exorcised", [])
            victim = es.pop("pukka_victim", None)
            if ans and not exorcised:
                t = g.p(ans[0])
                R.chose(g, p, [t])
                es["pukka_victim"] = t.id
            if victim and victim != es.get("pukka_victim"):
                R.die(g, g.p(victim), "demon", p, ctx)


class Shabaloth(Char):
    id, name, type, style, other_nights = "shabaloth", "Shabaloth", "demon", "think", True

    def task(self, R, game, p, first):
        return choose(self.id, self.name, "Choose 2 players: they die.", 2, everyone(game, alive=True))

    def resolve(self, R, ctx, p, ans):
        if lunatic_report(R, ctx, p, ans):
            return
        g = ctx.game
        es = g.estate
        if R.works(g, p, self.id):
            last = [g.p(x) for x in es.get("shabaloth_last", []) if not g.p(x).alive]
            if last and g.rng.random() < g.settings["shabaloth_regurgitate"]:
                R.revive(g, g.rng.choice(last))
        es["shabaloth_last"] = list(ans or [])
        if not ans or demon_blocked(R, ctx, p):
            return
        targets = [g.p(x) for x in ans]
        R.chose(g, p, targets)
        for t in targets:
            demon_attack(R, ctx, p, t)


class Po(Char):
    id, name, type, style, other_nights = "po", "Po", "demon", "think", True

    def task(self, R, game, p, first):
        if game.estate.get("po_charged", {}).get(p.id):
            return choose(self.id, self.name, "You chose no one last time. Choose 3 players: they die.", 3,
                          everyone(game, alive=True))
        return choose(self.id, self.name, "Choose a player: they die. Or choose no one, and choose 3 "
                      "next time.", 1, everyone(game, alive=True), allow_none=True)

    def resolve(self, R, ctx, p, ans):
        if lunatic_report(R, ctx, p, ans):
            return
        g = ctx.game
        es = g.estate
        if p.id in es.get("exorcised", []):
            return
        charged = es.setdefault("po_charged", {})
        charged[p.id] = not ans
        if not ans or demon_blocked(R, ctx, p):
            return
        targets = [g.p(x) for x in ans]
        R.chose(g, p, targets)
        for t in targets:
            demon_attack(R, ctx, p, t)


CHARS = [Grandmother(), Sailor(), Chambermaid(), Exorcist(), Innkeeper(), Gambler(), Gossip(), Courtier(),
         Professor(), Minstrel(), TeaLady(), Pacifist(), Fool(), Tinker(), Moonchild(), Goon(), Lunatic(),
         Godfather(), DevilsAdvocate(), Assassin(), Mastermind(), Zombuul(), Pukka(), Shabaloth(), Po()]
