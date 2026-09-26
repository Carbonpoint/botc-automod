"""Trouble Brewing characters."""

from __future__ import annotations

from .rules import Char, choose, everyone, info, others, wrong_number


class Washerwoman(Char):
    id, name, type, style, first_night = "washerwoman", "Washerwoman", "townsfolk", "chill", True
    tip = "You get your info on the first night. Share it when it helps."
    kind = "townsfolk"

    def resolve(self, R, ctx, p, ans):
        ctx.tell(p, self.name, ping(R, ctx.game, p, self.kind, self.id), self.id)


class Librarian(Washerwoman):
    id, name, kind = "librarian", "Librarian", "outsider"
    tip = "You get your info on the first night. Outsiders often hide; find them."


class Investigator(Washerwoman):
    id, name, kind = "investigator", "Investigator", "minion"
    tip = "You get your info on the first night. One of your two players is evil."


def ping(R, game, p, kind: str, cid: str) -> list[str]:
    rng = game.rng
    rest = [x for x in game.seated() if x.id != p.id]
    pool = [r for r in R.roles.values() if r.type == kind]
    if R.truthful(game, p, cid):
        # A player of this type is always findable. The Spy or Recluse may add a false
        # match (registering as this type), but misregistration never hides a true one.
        hits = [x for x in rest if R.type_of(x.role) == kind or R.reg(game, x, p)["type"] == kind]
        if not hits:
            return ["There are no Outsiders in play."] if kind == "outsider" else \
                [f"There are no {kind.capitalize()}s in play."]
        hit = rng.choice(hits)
        shown_role = hit.role if R.type_of(hit.role) == kind else R.reg(game, hit, p)["role"]
        role = R.roles[shown_role]
        pair = [hit, rng.choice([x for x in rest if x is not hit])]
    else:
        if kind == "outsider" and any(R.type_of(x.role) == kind for x in rest) and rng.random() < 0.3:
            return ["There are no Outsiders in play."]
        pair = rng.sample(rest, 2)
        wrong = [r for r in pool if r.id not in (pair[0].role, pair[1].role)]
        role = rng.choice(wrong or pool)
    rng.shuffle(pair)
    return [f"One of {pair[0].name} and {pair[1].name} is the {role.name}."]


class Chef(Char):
    id, name, type, style, first_night = "chef", "Chef", "townsfolk", "think", True
    tip = "A pair means two evil players sitting next to each other."

    def resolve(self, R, ctx, p, ans):
        g = ctx.game
        seated = g.seated()
        n = len(seated)
        evil = [R.reg(g, x, p)["team"] == "evil" for x in seated]
        pairs = sum(1 for i in range(n) if evil[i] and evil[(i + 1) % n])
        if not R.truthful(g, p, self.id):
            pairs = wrong_number(g.rng, pairs, 3)
        ctx.tell(p, self.name, [f"There {'is' if pairs == 1 else 'are'} {pairs} "
                                f"pair{'' if pairs == 1 else 's'} of evil players."], self.id)


class Empath(Char):
    id, name, type, style = "empath", "Empath", "townsfolk", "think"
    first_night = other_nights = True
    tip = "Your number changes when your neighbours die. Track it every night."

    def resolve(self, R, ctx, p, ans):
        if not p.alive:
            return
        g = ctx.game
        count = sum(1 for x in R.alive_neighbours(g, p) if R.reg(g, x, p)["team"] == "evil")
        if not R.truthful(g, p, self.id):
            count = wrong_number(g.rng, count, 2)
        ctx.tell(p, self.name, [f"{count} of your alive neighbours {'is' if count == 1 else 'are'} evil."],
                 self.id)


class FortuneTeller(Char):
    id, name, type, style = "fortuneteller", "Fortune Teller", "townsfolk", "think"
    first_night = other_nights = True
    tip = "One good player always shows 'yes' to you: the red herring."

    def task(self, R, game, p, first):
        return choose(self.id, self.name, "Choose 2 players. You learn if either is a Demon.", 2, everyone(game))

    def resolve(self, R, ctx, p, ans):
        if not ans or not p.alive:
            return
        g = ctx.game
        targets = [g.p(x) for x in ans]
        R.chose(g, p, targets)
        yes = any(R.reg(g, t, p)["type"] == "demon" or t.id == g.estate.get("red_herring") for t in targets)
        if not R.truthful(g, p, self.id):
            yes = not yes
        names = " and ".join(t.name for t in targets)
        ctx.tell(p, self.name, [f"{names}: {'YES, one of them is' if yes else 'NO, neither is'} the Demon."],
                 self.id)


class Undertaker(Char):
    id, name, type, style, other_nights = "undertaker", "Undertaker", "townsfolk", "think", True
    tip = "You learn the true character of each executed player."

    def resolve(self, R, ctx, p, ans):
        g = ctx.game
        executed = g.estate.get("executed_died")  # only a player who died by execution counts
        if not p.alive or not executed:
            return
        t = g.p(executed)
        role = R.reg(g, t, p)["role"]
        if not R.truthful(g, p, self.id):
            role = g.rng.choice([r for r in R.roles if r != role])
        ctx.tell(p, self.name, [f"Today's executed player, {t.name}, was the {R.roles[role].name}."], self.id)


class Monk(Char):
    id, name, type, style, other_nights = "monk", "Monk", "townsfolk", "think", True
    tip = "Protect players you think the Demon wants dead."

    def task(self, R, game, p, first):
        return choose(self.id, self.name, "Choose a player to protect from the Demon.", 1, others(game, p))

    def resolve(self, R, ctx, p, ans):
        if not ans:
            return
        t = ctx.game.p(ans[0])
        R.chose(ctx.game, p, [t])
        if R.works(ctx.game, p, self.id):
            R.add_status(ctx.game, t.id, "safe_demon", "Monk", "dawn")


class Ravenkeeper(Char):
    id, name, type, style = "ravenkeeper", "Ravenkeeper", "townsfolk", "chill"
    tip = "If the Demon kills you, you get one strong piece of info."

    def on_death(self, R, game, p, cause, ctx):
        if game.phase == "night" and ctx is not None and ctx.stage == "A" and R.holds(p, self.id):
            ctx.out[p.id].append(choose(self.id, self.name,
                                        "You died tonight. Choose a player: you learn their character.",
                                        1, everyone(game)))

    def resolve_b(self, R, ctx, p, ans):
        g = ctx.game
        t = g.p(ans[0])
        R.chose(g, p, [t])
        role = R.reg(g, t, p)["role"]
        if R.malfunction(g, p) or (R.vortox_active(g)):
            R.abnormal(g, p)
            role = g.rng.choice([r for r in R.roles if r != role])
        ctx.tell(p, self.name, [f"{t.name} is the {R.roles[role].name}."], self.id)


class Virgin(Char):
    id, name, type, style = "virgin", "Virgin", "townsfolk", "chill"
    tip = "Invite a nomination: it can prove who is a Townsfolk."

    def on_nominate(self, R, game, nominator, nominee):
        es = game.estate
        if nominee.shown != self.id or nominee.id in es.setdefault("virgin_used", []):
            return False
        es["virgin_used"].append(nominee.id)
        if R.works(game, nominee, self.id) and R.reg(game, nominator)["type"] == "townsfolk":
            game.executed_today = nominator.id
            game.announce(f"{nominator.name} is executed immediately! The day is over.")
            if R.die(game, nominator, "execution"):
                game.estate["executed_died"] = nominator.id
            return True
        return False


class Slayer(Char):
    id, name, type, style = "slayer", "Slayer", "townsfolk", "chill"
    tip = "Use the Slayer button on the Town screen. Anyone may bluff it."

    def public_action(self, R, game):
        return {"key": "slayer", "label": "Claim a Slayer shot", "kind": "target", "public": True,
                "help": "Anyone may claim to be the Slayer. Only the real Slayer's shot can kill."}

    def do_action(self, R, game, p, payload):
        es = game.estate
        t = game.p(payload["target"])
        es.setdefault("claimed", {}).setdefault(p.id, []).append("slayer")
        p.slayer_claimed = True
        text = f"{p.name} claims to be the Slayer and shoots {t.name}."
        if R.works(game, p, self.id) and not R.used(game, p, self.id):
            R.use(game, p, self.id)
            if t.alive and not t.fake_dead and R.reg(game, t, p)["type"] == "demon":
                if R.die(game, t, "slayer", p):
                    game.announce(f"{text} {t.name} dies!")
                    return
        game.announce(f"{text} Nothing happens.")


class Soldier(Char):
    id, name, type, style = "soldier", "Soldier", "townsfolk", "chill"
    tip = "The Demon cannot kill you at night."


class Mayor(Char):
    id, name, type, style = "mayor", "Mayor", "townsfolk", "chill"
    tip = "With 3 players left, ask the town not to execute."

    def after_no_execution(self, R, game):
        alive = R.living(game)
        if len(alive) == 3 and any(R.works(game, x, self.id) for x in alive):
            game.estate["win"] = ("good", "Three players live, nobody was executed, and the Mayor is alive.")


class Butler(Char):
    id, name, type, style = "butler", "Butler", "outsider", "think"
    first_night = other_nights = True
    tip = "Your yes vote only counts if your master also votes yes."

    def task(self, R, game, p, first):
        return choose(self.id, self.name,
                      "Choose your master. Tomorrow your vote counts only if they vote too.", 1, others(game, p))

    def resolve(self, R, ctx, p, ans):
        if ans:
            R.chose(ctx.game, p, [ctx.game.p(ans[0])])
            ctx.game.estate.setdefault("master", {})[p.id] = ans[0]
            p.note(ctx.game.label(), f"Your master tomorrow is {ctx.game.p(ans[0]).name}.")


class Drunk(Char):
    id, name, type, style = "drunk", "Drunk", "outsider", "chill"
    tip = "Your information may be wrong."


class Recluse(Char):
    id, name, type, style = "recluse", "Recluse", "outsider", "chill"
    tip = "Others may get info that you are evil."


class Saint(Char):
    id, name, type, style = "saint", "Saint", "outsider", "chill"
    tip = "Stay off the chopping block."

    def on_death(self, R, game, p, cause, ctx):
        if cause == "execution" and R.holds(p, self.id) and not R.malfunction(game, p):
            game.estate["win"] = ("evil", "The Saint was executed.")


class Poisoner(Char):
    id, name, type, style = "poisoner", "Poisoner", "minion", "think"
    first_night = other_nights = True
    tip = "Poison the players whose info could expose your team."

    def task(self, R, game, p, first):
        return choose(self.id, self.name, "Choose a player to poison.", 1, everyone(game, alive=True))

    def resolve(self, R, ctx, p, ans):
        if ans:
            t = ctx.game.p(ans[0])
            R.chose(ctx.game, p, [t])
            if R.works(ctx.game, p, self.id):
                R.add_status(ctx.game, t.id, "poisoned", "Poisoner", "dusk", source_pid=p.id)


class Spy(Char):
    id, name, type, style = "spy", "Spy", "minion", "think"
    first_night = other_nights = True
    tip = "You see every character. Feed your Demon the truth and lie to the town."

    def resolve(self, R, ctx, p, ans):
        g = ctx.game
        if not p.alive:
            return
        rows = [(x, R.roles[x.role].name) for x in g.seated()]
        poisoned = R.malfunction(g, p)
        if poisoned and len(rows) > 2:
            i, j = g.rng.sample(range(len(rows)), 2)
            rows[i], rows[j] = (rows[i][0], rows[j][1]), (rows[j][0], rows[i][1])
        lines = ["The Grimoire:"]
        for x, name in rows:
            tags = []
            if x.shown != x.role and not poisoned:
                tags.append(f"thinks they are the {R.roles[x.shown].name}")
            if not x.alive:
                tags.append("dead")
            tags += [n for n in R.player_notes(g, x, spy=True) if n != "registers as dead"]
            if g.estate.get("red_herring") == x.id and "fortuneteller" in R.chars:
                tags.append("Fortune Teller red herring")
            lines.append(f"{x.name}: {name}" + (f" ({', '.join(tags)})" if tags else ""))
        ctx.tell(p, self.name, lines, self.id)


class ScarletWoman(Char):
    id, name, type, style = "scarletwoman", "Scarlet Woman", "minion", "chill"
    tip = "Keep yourself alive. If the Demon dies early, you take over."


class Baron(Char):
    id, name, type, style = "baron", "Baron", "minion", "chill"
    outsider_mod = (2,)
    tip = "Two more Outsiders are in play because of you."


def demon_attack(R, ctx, demon, target, cause="demon") -> bool:
    """A standard Demon kill with the Mayor's bounce. Returns True if someone died."""
    g = ctx.game
    if not target.alive and not target.fake_dead:
        return False
    if R.works(g, target, "mayor") and not R.protected(g, target, cause) \
            and R.lucky(g, target, g.settings["mayor_bounce"]):
        pool = [x for x in R.living(g) if x.id not in (target.id, demon.id) and not R.protected(g, x, cause)]
        if pool:
            target = R.pick_victim(g, pool)
    return R.die(g, target, cause, demon, ctx)


def demon_blocked(R, ctx, demon) -> bool:
    """The Demon does not act: Exorcist, drunk or poisoned, or no attack earned."""
    g = ctx.game
    if demon.id in g.estate.get("exorcised", []):
        return True
    if R.malfunction(g, demon):
        R.abnormal(g, demon)
        return True
    return False


def lunatic_report(R, ctx, p, ans) -> bool:
    """A Lunatic acting as a Demon: tell the real Demon. Return True if p is the Lunatic."""
    if p.role != "lunatic":
        return False
    g = ctx.game
    names = ", ".join(g.p(x).name for x in (ans or [])) or "nobody"
    for d in (x for x in g.seated() if R.type_of(x.role) == "demon" and x.alive):
        ctx.tell(d, "The Lunatic", [f"The Lunatic ({p.name}) chose: {names}."], "lunatic")
    return True


class Imp(Char):
    id, name, type, style, other_nights = "imp", "Imp", "demon", "think", True
    tip = "Kill at night. Bluff a good character by day."

    def task(self, R, game, p, first):
        return choose(self.id, self.name,
                      "Choose a player to kill. Choose yourself to pass the Demon to a Minion.", 1,
                      everyone(game, alive=True))

    def resolve(self, R, ctx, p, ans):
        if not ans or lunatic_report(R, ctx, p, ans):
            return
        g = ctx.game
        target = g.p(ans[0])
        R.chose(g, p, [target])
        if demon_blocked(R, ctx, p):
            return
        if target.id == p.id:
            if R.die(g, p, "demon", p, ctx) and not any(
                    R.type_of(x.role) == "demon" for x in R.living(g)):
                minions = [x for x in R.living(g) if R.type_of(x.role) == "minion"]
                if minions:
                    R.become(g, g.rng.choice(minions), "imp", tell="The Imp died. ", ctx=ctx)
            return
        demon_attack(R, ctx, p, target)


CHARS = [Washerwoman(), Librarian(), Investigator(), Chef(), Empath(), FortuneTeller(), Undertaker(),
         Monk(), Ravenkeeper(), Virgin(), Slayer(), Soldier(), Mayor(), Butler(), Drunk(), Recluse(),
         Saint(), Poisoner(), Spy(), ScarletWoman(), Baron(), Imp()]
