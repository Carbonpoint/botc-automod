"""Sects & Violets characters.

Automod choices where a human storyteller would decide:
- Mutant and Cerenovus depend on judging "madness", so they are only
  dealt when a human storyteller runs the game.
- Savant: two generated statements about the game, one true, one false.
- Artist: the question is built from a menu (or free text, which gets
  "I don't know" from the automod).
- Pit-Hag: creating a Demon causes no extra deaths.
- Sweetheart: a random other living player becomes drunk.
- Vigormortis: which of two Townsfolk neighbours is poisoned is random.
"""

from __future__ import annotations

from .chars_tb import demon_attack, demon_blocked, lunatic_report
from .rules import Char, choose, choose_character, choose_player_character, everyone, info, others, wrong_number


def seat_distance(game, a, b) -> int:
    seated = game.seated()
    i, j, n = seated.index(a), seated.index(b), len(seated)
    d = abs(i - j)
    return min(d, n - d)


class Clockmaker(Char):
    id, name, type, style, first_night = "clockmaker", "Clockmaker", "townsfolk", "think", True

    def resolve(self, R, ctx, p, ans):
        g = ctx.game
        demons = [x for x in g.seated() if R.type_of(x.role) == "demon"]
        minions = [x for x in g.seated() if R.type_of(x.role) == "minion"]
        if not demons or not minions:
            return
        steps = min(seat_distance(g, demons[0], m) for m in minions)
        if not R.truthful(g, p, self.id):
            steps = g.rng.choice([k for k in range(1, max(2, len(g.seated()) // 2) + 1) if k != steps] or [steps])
        ctx.tell(p, self.name, [f"The Demon is {steps} step{'s' if steps != 1 else ''} from its nearest Minion."],
                 self.id)


class Dreamer(Char):
    id, name, type, style = "dreamer", "Dreamer", "townsfolk", "think"
    first_night = other_nights = True

    def task(self, R, game, p, first):
        return choose(self.id, self.name, "Choose a player (not yourself): you learn 1 good and 1 evil "
                      "character, 1 of which is correct.", 1, others(game, p, alive=False))

    def resolve(self, R, ctx, p, ans):
        if not ans:
            return
        g = ctx.game
        t = g.p(ans[0])
        R.chose(g, p, [t])
        true = R.roles[R.reg(g, t, p)["role"]]
        goods = [r for r in R.roles.values() if r.team == "good" and r.id != true.id]
        evils = [r for r in R.roles.values() if r.team == "evil" and r.id != true.id]
        if R.truthful(g, p, self.id):
            pair = [true, g.rng.choice(evils if true.team == "good" else goods)]
        else:
            pair = [g.rng.choice(goods), g.rng.choice(evils)]
        g.rng.shuffle(pair)
        ctx.tell(p, self.name, [f"{t.name} is the {pair[0].name} or the {pair[1].name}."], self.id)


def swap_characters(R, ctx, a, b, alignments: bool) -> None:
    g = ctx.game
    a.role, b.role = b.role, a.role
    a.shown, b.shown = b.shown, a.shown
    a.gained, b.gained = b.gained, a.gained
    if alignments:
        a.alignment, b.alignment = R.alignment(b), R.alignment(a)
    for x in (a, b):
        g.estate.setdefault("used", {}).pop(x.id, None)
        r = R.roles[x.shown]
        line = f"Your character changed. You are now the {r.name}. You are {R.alignment(x)}. {r.ability}"
        if ctx.stage == "A":
            ctx.out[x.id].append(info("new_character", "Your character changed", [line]))
        else:
            ctx.messages[x.id].append(line)


class SnakeCharmer(Char):
    id, name, type, style = "snakecharmer", "Snake Charmer", "townsfolk", "think"
    first_night = other_nights = True

    def task(self, R, game, p, first):
        return choose(self.id, self.name, "Choose an alive player. If they are the Demon, you swap "
                      "characters and alignments.", 1, everyone(game, alive=True))

    def resolve(self, R, ctx, p, ans):
        if not ans:
            return
        g = ctx.game
        t = g.p(ans[0])
        R.chose(g, p, [t])
        if t.id == p.id or not R.works(g, p, self.id) or R.type_of(t.role) != "demon":
            return
        swap_characters(R, ctx, p, t, alignments=True)
        R.add_status(g, t.id, "poisoned", "Snake Charmer", "never")


class Mathematician(Char):
    id, name, type, style = "mathematician", "Mathematician", "townsfolk", "think"
    first_night = other_nights = True

    def resolve(self, R, ctx, p, ans):
        g = ctx.game
        count = len([x for x in g.estate.get("abnormal", []) if x != p.id])
        if not R.truthful(g, p, self.id):
            count = wrong_number(g.rng, count, 3)
        ctx.tell(p, self.name, [f"{count} player{'s' if count != 1 else ''}' abilities worked abnormally "
                                "since dawn."], self.id)


class Flowergirl(Char):
    id, name, type, style, other_nights = "flowergirl", "Flowergirl", "townsfolk", "think", True

    def resolve(self, R, ctx, p, ans):
        g = ctx.game
        voters = {x for h in g.nom_history for x in h["yes"]}
        yes = any(R.type_of(g.p(x).role) == "demon" for x in voters)
        if not R.truthful(g, p, self.id):
            yes = not yes
        ctx.tell(p, self.name, [f"{'YES, a Demon voted' if yes else 'NO, no Demon voted'} today."], self.id)


class TownCrier(Char):
    id, name, type, style, other_nights = "towncrier", "Town Crier", "townsfolk", "think", True

    def resolve(self, R, ctx, p, ans):
        g = ctx.game
        yes = any(R.type_of(g.p(x).role) == "minion" for x in g.nominators_today)
        if not R.truthful(g, p, self.id):
            yes = not yes
        ctx.tell(p, self.name, [f"{'YES, a Minion nominated' if yes else 'NO, no Minion nominated'} today."],
                 self.id)


class Oracle(Char):
    id, name, type, style, other_nights = "oracle", "Oracle", "townsfolk", "think", True

    def resolve(self, R, ctx, p, ans):
        g = ctx.game
        count = sum(1 for x in g.seated() if (not x.alive or x.fake_dead) and R.alignment(x) == "evil")
        if not R.truthful(g, p, self.id):
            count = wrong_number(g.rng, count, 3)
        ctx.tell(p, self.name, [f"{count} dead player{'s are' if count != 1 else ' is'} evil."], self.id)


class Savant(Char):
    id, name, type, style = "savant", "Savant", "townsfolk", "think"

    def day_action(self, R, game, p):
        if game.estate.get("savant_day", {}).get(p.id) == game.day:
            return None
        return {"key": "savant", "label": "Visit the Storyteller (Savant)", "kind": "visit", "public": False,
                "help": "Learn 2 things in private: 1 is true and 1 is false."}

    def do_action(self, R, game, p, payload):
        game.estate.setdefault("savant_day", {})[p.id] = game.day
        if game.mode == "human":
            R.request(game, p, "Savant", "wants their 2 statements (1 true, 1 false).")
            return
        facts = savant_facts(R, game, p)
        rng = game.rng
        true = rng.choice([f for f in facts if f[1]])
        false = rng.choice([f for f in facts if not f[1]])
        if R.malfunction(game, p) or (R.vortox_active(game)):
            R.abnormal(game, p)
            pool = [f for f in facts if f[1]] if rng.random() < 0.5 else [f for f in facts if not f[1]]
            true, false = rng.sample(pool, 2) if len(pool) >= 2 else (true, false)
        pair = [true[0], false[0]]
        rng.shuffle(pair)
        p.note(game.label(), f"Savant: “{pair[0]}” and “{pair[1]}”. One is true, one is false.")


def savant_facts(R, game, p) -> list[tuple[str, bool]]:
    """Candidate statements with their truth."""
    rng = game.rng
    seated = game.seated()
    facts = []
    evil_alive = sum(1 for x in R.living(game) if R.alignment(x) == "evil")
    for k in range(0, 4):
        facts.append((f"There {'is' if k == 1 else 'are'} {k} evil player{'s' if k != 1 else ''} alive.",
                      k == evil_alive))
    for x in rng.sample(seated, min(4, len(seated))):
        for t in ("Townsfolk", "Outsider", "Minion", "Demon"):
            facts.append((f"{x.name} is a {t}.", R.type_of(x.role) == t.lower()))
    for _ in range(4):
        a, b = rng.sample(seated, 2)
        facts.append((f"{a.name} and {b.name} are on the same team.", R.alignment(a) == R.alignment(b)))
    demon = next((x for x in seated if R.type_of(x.role) == "demon"), None)
    if demon and demon is not p:
        d = seat_distance(game, p, demon)
        for k in (1, 2, 3):
            facts.append((f"The Demon sits within {k} seat{'s' if k > 1 else ''} of you.", d <= k))
    for r in rng.sample(list(R.roles.values()), 6):
        facts.append((f"The {r.name} is in play.", any(x.role == r.id for x in seated)))
    return facts


class Seamstress(Char):
    id, name, type, style = "seamstress", "Seamstress", "townsfolk", "think"
    first_night = other_nights = True

    def task(self, R, game, p, first):
        if R.used(game, p, self.id):
            return None
        return choose(self.id, self.name, "Once per game: choose 2 players (not yourself). You learn if they "
                      "are the same alignment. Or choose no one to wait.", 2, others(game, p, alive=False),
                      allow_none=True)

    def resolve(self, R, ctx, p, ans):
        if not ans:
            return
        g = ctx.game
        R.use(g, p, self.id)
        a, b = g.p(ans[0]), g.p(ans[1])
        R.chose(g, p, [a, b])
        same = R.reg(g, a, p)["team"] == R.reg(g, b, p)["team"]
        if not R.truthful(g, p, self.id):
            same = not same
        ctx.tell(p, self.name, [f"{a.name} and {b.name} are {'the SAME' if same else 'NOT the same'} alignment."],
                 self.id)


class Philosopher(Char):
    id, name, type, style = "philosopher", "Philosopher", "townsfolk", "think"
    first_night = other_nights = True

    def task(self, R, game, p, first):
        if R.used(game, p, self.id):
            return None
        good = [r for r in R.roles.values() if r.team == "good" and r.id != self.id]
        return choose_character(self.id, self.name, "Once per game: choose a good character and gain their "
                                "ability. Or choose no one to wait.", good, allow_none=True)

    def resolve(self, R, ctx, p, ans):
        if not ans:
            return
        g = ctx.game
        R.use(g, p, self.id)
        if not R.works(g, p, self.id):
            return
        p.gained = [*p.gained, ans]
        c = R.chars[ans]
        wakes = (ctx.first and c.first_night) or (not ctx.first and c.other_nights)
        t = c.task(R, g, p, ctx.first) if wakes else None
        if t:
            ctx.out[p.id].append(t)


class Artist(Char):
    id, name, type, style = "artist", "Artist", "townsfolk", "think"

    def day_action(self, R, game, p):
        if R.used(game, p, self.id):
            return None
        return {"key": "artist", "label": "Ask the Storyteller a yes/no question (Artist)", "kind": "question",
                "public": False, "help": "Once per game. The answer is private."}

    def do_action(self, R, game, p, payload):
        R.use(game, p, self.id)
        text = R.statement_text(game, payload)
        if game.mode == "human":
            R.request(game, p, "Artist", f"asks: “{text}?”")
            return
        truth = R.statement_true(game, payload)
        if truth is None:
            answer = "I don't know."
        else:
            if R.malfunction(game, p):
                R.abnormal(game, p)
                truth = game.rng.random() < 0.5
            answer = "Yes." if truth else "No."
        p.note(game.label(), f"Artist: you asked “Is it true that {text}?” The answer: {answer}")


class Juggler(Char):
    id, name, type, style, other_nights = "juggler", "Juggler", "townsfolk", "think", True

    def public_action(self, R, game):
        if game.day != 1:
            return None
        return {"key": "juggler", "label": "Make Juggler guesses", "kind": "guesses", "public": True,
                "help": "Anyone may claim to be the Juggler. Publicly guess up to 5 players' characters."}

    def do_action(self, R, game, p, payload):
        es = game.estate
        es.setdefault("claimed", {}).setdefault(p.id, []).append("juggler")
        guesses = [(game.p(x["player"]), R.roles[x["character"]]) for x in payload.get("guesses", [])][:5]
        text = "; ".join(f"{t.name} is the {r.name}" for t, r in guesses) or "no guesses"
        game.announce(f"{p.name}, as the Juggler, guesses: {text}.")
        if p.shown == self.id or self.id in p.gained:
            es.setdefault("juggler", {})[p.id] = sum(1 for t, r in guesses if R.reg(game, t, p)["role"] == r.id)

    def resolve(self, R, ctx, p, ans):
        g = ctx.game
        count = g.estate.get("juggler", {}).pop(p.id, None)
        if count is None or not p.alive:
            return
        if not R.truthful(g, p, self.id):
            count = wrong_number(g.rng, count, 5)
        ctx.tell(p, self.name, [f"You got {count} guess{'es' if count != 1 else ''} right."], self.id)


class Sage(Char):
    id, name, type, style = "sage", "Sage", "townsfolk", "chill"

    def on_death(self, R, game, p, cause, ctx):
        if cause != "demon" or p.shown != self.id or ctx is None:
            return
        demon = next((x for x in game.seated() if R.type_of(x.role) == "demon"), None)
        if not demon:
            return
        if R.malfunction(game, p):
            R.abnormal(game, p)
            pair = game.rng.sample([x for x in game.seated() if x is not demon and x is not p], 2)
        else:
            pair = [demon, R.pick_other(game, {demon.id, p.id})]
        game.rng.shuffle(pair)
        ctx.tell(p, self.name, [f"The Demon is {pair[0].name} or {pair[1].name}."], self.id)


class Mutant(Char):
    id, name, type, style, auto_ok = "mutant", "Mutant", "outsider", "chill", False


class Sweetheart(Char):
    id, name, type, style, works_dead = "sweetheart", "Sweetheart", "outsider", "chill", True

    def on_death(self, R, game, p, cause, ctx):
        if p.role != self.id or R.malfunction(game, p):
            return
        pool = [x for x in R.living(game) if x.id != p.id]
        if pool:
            R.add_status(game, game.rng.choice(pool).id, "drunk", "Sweetheart", "never")


class Barber(Char):
    id, name, type, style, works_dead = "barber", "Barber", "outsider", "chill", True
    other_nights = True

    def on_death(self, R, game, p, cause, ctx):
        if p.role != self.id or R.malfunction(game, p):
            return
        if game.phase == "night" and ctx is not None and ctx.stage == "A":
            for d in (x for x in game.seated() if R.type_of(x.role) == "demon" and x.alive):
                ctx.out[d.id].append(self._task(R, game, d))
        else:
            game.estate["haircut"] = True

    def _task(self, R, game, demon):
        cands = [x.id for x in game.seated() if x is demon or R.type_of(x.role) != "demon"]
        return choose(self.id, "The Barber died", "You may choose 2 players (not another Demon) to swap "
                      "characters. Or choose no one.", 2, cands, allow_none=True)

    def extra_tasks(self, R, game, first):
        if not game.estate.pop("haircut", False):
            return {}
        return {d.id: self._task(R, game, d) for d in game.seated()
                if R.type_of(d.role) == "demon" and d.alive}

    def step(self, R, ctx):
        for pid, keys in ctx.answers.items():
            if keys.get(self.id) and R.type_of(ctx.game.p(pid).role) == "demon":
                self.resolve_b(R, ctx, ctx.game.p(pid), keys[self.id])

    def resolve_b(self, R, ctx, p, ans):
        if not ans or len(ans) != 2:
            return
        a, b = ctx.game.p(ans[0]), ctx.game.p(ans[1])
        swap_characters(R, ctx, a, b, alignments=False)


class Klutz(Char):
    id, name, type, style, works_dead = "klutz", "Klutz", "outsider", "chill", True

    def on_death(self, R, game, p, cause, ctx):
        if p.shown != self.id:
            return
        key = "death_prompts_pending" if game.phase == "night" else "death_prompts"
        game.estate.setdefault(key, []).append(p.id)

    def death_prompt(self, R, game, p):
        return {"key": "klutz", "label": "You died: choose a player (Klutz)", "kind": "target",
                "public": True, "forced": True, "candidates": everyone(game, alive=True),
                "help": "Publicly choose 1 alive player. If they are evil, your team loses."}

    def do_action(self, R, game, p, payload):
        t = game.p(payload["target"])
        game.estate["death_prompts"].remove(p.id)
        game.announce(f"{p.name}, as the Klutz, chooses {t.name}.")
        if R.works(game, p, self.id) and R.alignment(t) == "evil":
            game.estate["win"] = ("evil", f"The Klutz chose {t.name}, an evil player.")
            game._check_win()


class EvilTwin(Char):
    id, name, type, style, first_night = "eviltwin", "Evil Twin", "minion", "think", True

    def setup(self, R, game, p):
        good = [x for x in game.seated() if R.roles[x.role].team == "good"]
        if good:
            game.estate["twins"] = [p.id, game.rng.choice(good).id]

    def step(self, R, ctx):
        g = ctx.game
        pair = g.estate.get("twins")
        if not pair or not ctx.first:
            return
        et, gt = g.p(pair[0]), g.p(pair[1])
        ctx.tell(et, "Your twin", [f"Your twin is {gt.name}, the {R.roles[gt.shown].name}."], self.id)
        ctx.tell(gt, "Your twin", [f"{et.name} is your twin, the {R.roles[et.role].name}. "
                                   "One of you is good, one is evil."], "storyteller")

    def after_execution(self, R, game, player, died):
        pair = game.estate.get("twins")
        if not pair or player.id != pair[1]:
            return
        et = game.p(pair[0])
        if et.alive and not R.malfunction(game, et) and R.alignment(player) == "good":
            game.estate["win"] = ("evil", f"{player.name}, the good twin, was executed.")


class Witch(Char):
    id, name, type, style = "witch", "Witch", "minion", "think"
    first_night = other_nights = True

    def task(self, R, game, p, first):
        if len(R.living(game)) <= 3:
            return None
        return choose(self.id, self.name, "Choose a player: if they nominate tomorrow, they die.", 1,
                      everyone(game, alive=True))

    def resolve(self, R, ctx, p, ans):
        if not ans:
            return
        g = ctx.game
        t = g.p(ans[0])
        R.chose(g, p, [t])
        if R.works(g, p, self.id):
            R.add_status(g, t.id, "cursed", "Witch", "dusk", source_pid=p.id)

    def on_nominate(self, R, game, nominator, nominee):
        if R.has(game, nominator, "cursed") and len(R.living(game)) > 3:
            R.die(game, nominator, "witch")
        return False


class Cerenovus(Char):
    id, name, type, style, auto_ok = "cerenovus", "Cerenovus", "minion", "think", False
    first_night = other_nights = True

    def task(self, R, game, p, first):
        return choose_player_character(self.id, self.name, "Choose a player and a good character: they are "
                                       "mad that they are this character tomorrow.", everyone(game, alive=True),
                                       [r for r in R.roles.values() if r.team == "good"])

    def resolve(self, R, ctx, p, ans):
        if not ans:
            return
        g = ctx.game
        t = g.p(ans["player"])
        R.chose(g, p, [t])
        if R.works(g, p, self.id):
            R.add_status(g, t.id, "mad", f"Cerenovus: {R.roles[ans['character']].name}", "dusk", source_pid=p.id)
            ctx.tell(t, "The Cerenovus", [f"The Cerenovus chose you. Tomorrow you must be “mad” that you "
                                          f"are the {R.roles[ans['character']].name}, or you might be executed."],
                     "storyteller")


class PitHag(Char):
    id, name, type, style, other_nights = "pithag", "Pit-Hag", "minion", "think", True

    def task(self, R, game, p, first):
        return choose_player_character(self.id, self.name, "Choose a player and a character they become "
                                       "(if it is not in play).", everyone(game, alive=True),
                                       list(R.roles.values()))

    def resolve(self, R, ctx, p, ans):
        if not ans:
            return
        g = ctx.game
        t = g.p(ans["player"])
        R.chose(g, p, [t])
        if not R.works(g, p, self.id) or any(x.role == ans["character"] for x in g.seated()):
            return
        R.become(g, t, ans["character"], keep_alignment=True, ctx=ctx)


class FangGu(Char):
    id, name, type, style, other_nights = "fanggu", "Fang Gu", "demon", "think", True
    outsider_mod = (1,)

    def task(self, R, game, p, first):
        return choose(self.id, self.name, "Choose a player: they die.", 1, everyone(game, alive=True))

    def resolve(self, R, ctx, p, ans):
        if not ans or lunatic_report(R, ctx, p, ans):
            return
        g = ctx.game
        t = g.p(ans[0])
        R.chose(g, p, [t])
        if demon_blocked(R, ctx, p):
            return
        if (R.type_of(t.role) == "outsider" and not g.estate.get("fanggu_jumped") and t.alive
                and not R.protected(g, t, "demon") and t.id != p.id):
            g.estate["fanggu_jumped"] = True
            R.become(g, t, "fanggu", tell="The Fang Gu chose you. ", ctx=ctx)
            R.die(g, p, "fanggu", None, ctx, force=True)
            return
        demon_attack(R, ctx, p, t)


class Vigormortis(Char):
    id, name, type, style, other_nights = "vigormortis", "Vigormortis", "demon", "think", True
    outsider_mod = (-1,)

    def task(self, R, game, p, first):
        return choose(self.id, self.name, "Choose a player: they die. Minions you kill keep their ability.", 1,
                      everyone(game, alive=True))

    def resolve(self, R, ctx, p, ans):
        if not ans or lunatic_report(R, ctx, p, ans):
            return
        g = ctx.game
        t = g.p(ans[0])
        R.chose(g, p, [t])
        if demon_blocked(R, ctx, p):
            return
        if demon_attack(R, ctx, p, t) and R.type_of(t.role) == "minion" and not t.alive:
            es = g.estate
            es.setdefault("vig_minions", []).append(t.id)
            nb = R.townsfolk_neighbours(g, t)
            if nb:
                es.setdefault("vig_poison", {})[t.id] = g.rng.choice(nb).id


class NoDashii(Char):
    id, name, type, style, other_nights = "nodashii", "No Dashii", "demon", "think", True

    def task(self, R, game, p, first):
        return choose(self.id, self.name, "Choose a player: they die.", 1, everyone(game, alive=True))

    def resolve(self, R, ctx, p, ans):
        if not ans or lunatic_report(R, ctx, p, ans):
            return
        t = ctx.game.p(ans[0])
        R.chose(ctx.game, p, [t])
        if not demon_blocked(R, ctx, p):
            demon_attack(R, ctx, p, t)


class Vortox(NoDashii):
    id, name = "vortox", "Vortox"

    def after_no_execution(self, R, game):
        if R.vortox_active(game):
            game.estate["win"] = ("evil", "Nobody was executed while the Vortox lives.")


CHARS = [Clockmaker(), Dreamer(), SnakeCharmer(), Mathematician(), Flowergirl(), TownCrier(), Oracle(),
         Savant(), Seamstress(), Philosopher(), Artist(), Juggler(), Sage(), Mutant(), Sweetheart(), Barber(),
         Klutz(), EvilTwin(), Witch(), Cerenovus(), PitHag(), FangGu(), Vigormortis(), NoDashii(), Vortox()]
