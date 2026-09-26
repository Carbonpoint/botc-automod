"""Synthetic questions for training and testing the Artist translator.

Each example is a random game world (names in seat order, characters,
who is alive, who is drunk or poisoned), an asker, a question, and the
gold query. Two phrasing sets exist: "train" and "test". They share no
templates and no player names, so a model scored on "test" must
generalise rather than recall.

Seat words: players sit in a circle facing inward, so "my left" is the
next player clockwise (cw) and "my right" is counter-clockwise (ccw).
"""

from __future__ import annotations

import json
import random

from ..editions import EDITIONS
from .query import World, Seat, evaluate, validate

NAMES_TRAIN = """Ann Ben Cat Dan Eve Fay Gus Hal Ivy Jon Kim Lee Max Ned Oli Pam Quinn Rob Sue Tom Uma Vic
Wes Xena Yuri Zoe Alex Bea Carl Dora Emil Fern Gabe Hana Ivo Jess Kofi Lena Milo Nia Omar Priya Raj Sara
Theo Ugo Vera Will Yara Zack Aiko Bruno Chen Dev Elif Femi Greta Hugo Inez Jamal Kira Luca Mei Nour Olga
Pablo Rosa Sven Tara Ulla Wang Ximena Yusuf Zara""".split()
NAMES_TEST = """Aria Blake Cyrus Delia Ezra Flora Gideon Hazel Isaac Juno Kai Lila Marcus Nadia Orion Penny
Rhys Selma Tobias Una Vince Wren Yasmin Zeke Amara Boris Clara Dmitri Esme Felix Gwen Hiro Ingrid Jasper
Kenji Leona Mateo Noor Otis Paula Ravi Sofia Tariq Ursula Viktor Willa""".split()

# Casual names for characters and types, as players say them.
ROLE_ALIASES = {"fortuneteller": ["FT", "fortune teller"], "scarletwoman": ["SW", "scarlet woman"],
                "devilsadvocate": ["DA", "devil's advocate"], "snakecharmer": ["snake charmer"],
                "eviltwin": ["evil twin"], "pithag": ["pit hag", "pithag"], "fanggu": ["fang gu"],
                "nodashii": ["no dashii"], "tealady": ["tea lady"], "towncrier": ["town crier"],
                "washerwoman": ["washer woman", "washerwoman"]}
TYPE_WORDS = {"townsfolk": ["a townsfolk", "a Townsfolk", "townsfolk", "a townie"],
              "outsider": ["an outsider", "an Outsider", "outsider"],
              "minion": ["a minion", "a Minion", "minion", "one of the minions"],
              "demon": ["the demon", "the Demon", "a demon", "demon"]}
PLURAL = {"townsfolk": ["townsfolk", "townies"], "outsider": ["outsiders", "Outsiders"],
          "minion": ["minions", "Minions"], "demon": ["demons", "Demons"],
          "good": ["good players", "good people", "goodies"], "evil": ["evil players", "evil people", "evils"]}

# Templates: {p} {q} {r} players, {role} a character, {type} a type phrase, {n} a number.
T = {
    "train": {
        "is_role": ["Is {p} the {role}?", "is {p} really the {role}", "Is {p} actually the {role}?",
                    "{p} is the {role}, right?", "is {p} the {role}?", "Is it true that {p} is the {role}?",
                    "Does {p} have the {role}?", "{p} the {role}?"],
        "is_type": ["Is {p} {type}?", "is {p} {type}", "Is {p} secretly {type}?", "{p} is {type}, yes?",
                    "Would {p} be {type}?"],
        "is_team": ["Is {p} {team}?", "is {p} {team}", "Is {p} on the {team} team?", "{p} {team}?",
                    "Is {p} playing for {team}?"],
        "in_play": ["Is the {role} in play?", "Is there a {role} in this game?", "is the {role} in the game",
                    "Does someone have the {role}?", "Is anyone the {role}?"],
        "is_malfunctioning": ["Is {p} drunk or poisoned?", "Is {p} poisoned?", "is {p} drunk",
                              "Is {p}'s ability broken right now?", "Is {p} poisoned or drunk?"],
        "me_malfunctioning": ["Am I drunk or poisoned?", "Am I poisoned?", "am i drunk",
                              "Is my ability working badly?"],
        "me_team": ["Am I {team}?", "Am I on the {team} team?"],
        "count_ge": ["Are there at least {n} {plural}?", "Are there {n} or more {plural}?",
                     "at least {n} {plural}?"],
        "count_alive_ge": ["Are at least {n} {plural} still alive?", "Are {n} or more {plural} alive?"],
        "count_eq": ["Are there exactly {n} {plural}?", "Is the number of {plural} exactly {n}?"],
        "or_type": ["Is the demon {p} or {q}?", "Is either {p} or {q} the demon?", "Is {p} or {q} the Demon?"],
        "or3_type": ["Is the demon one of {p}, {q} and {r}?", "Is one of {p}, {q}, {r} the demon?"],
        "or_role": ["Is {p} or {q} the {role}?", "Is either {p} or {q} the {role}?"],
        "and_team": ["Are both {p} and {q} good?", "Are {p} and {q} both good?"],
        "and_evil": ["Are {p} and {q} both evil?", "Are both {p} and {q} evil?"],
        "not_type": ["Is {p} not the demon?", "Is it true that {p} isn't the demon?"],
        "left": ["Is the player on my left {team}?", "Is my left neighbour {team}?",
                 "is the person to my left {team}"],
        "right": ["Is the player on my right {team}?", "Is my right neighbour {team}?"],
        "neighbours": ["Is either of my neighbours evil?", "Is one of my neighbours evil?",
                       "Are any of my neighbours evil?"],
        "their_left": ["Is {p}'s left neighbour {type}?", "Is the player to the left of {p} {type}?"],
        "unanswerable": ["Who is the demon?", "What character is {p}?", "Will good win?",
                         "Should we execute {p}?", "What is the weather like?", "Who killed {p}?",
                         "How many minions are there?", "Which player is the {role}?",
                         "Is {p} going to die tonight?", "What should I do?", "Tell me who is evil.",
                         "Why did {p} nominate me?", "What did {p} learn last night?"],
    },
    "test": {
        "is_role": ["hey is {p} the {role} or are they lying", "Can you tell me if {p} is the {role}?",
                    "{p} claims {role} - is that true?", "Yes or no: {p} is the {role}.",
                    "I want to know whether {p} is the {role}."],
        "is_type": ["Is {p} one of the {plural_type}?", "Can you confirm {p} is {type}?",
                    "Yes or no: {p} is {type}.", "i think {p} is {type}, am i right?"],
        "is_team": ["Can I trust {p}? Are they {team}?", "Yes or no, {p} is {team}.",
                    "I need to know if {p} is {team}.", "is {p} {team} or not"],
        "in_play": ["Is somebody playing the {role}?", "Yes or no: the {role} is in play.",
                    "Can you confirm there's a {role} around?"],
        "is_malfunctioning": ["Has {p} been poisoned?", "Is something wrong with {p}'s ability, drunk or poisoned?",
                              "Yes or no: {p} is drunk or poisoned."],
        "me_malfunctioning": ["Is my info bad because I'm drunk or poisoned?", "Have I been poisoned?"],
        "me_team": ["Yes or no: I am {team}.", "Is my alignment {team}?"],
        "count_ge": ["Do we have {n} or more {plural} in this game?", "Yes or no: at least {n} {plural}."],
        "count_alive_ge": ["Do at least {n} {plural} remain alive?", "Yes or no, {n}+ {plural} alive?"],
        "count_eq": ["Is it exactly {n} {plural}?", "Yes or no: there are exactly {n} {plural}."],
        "or_type": ["Is our demon either {p} or {q}?", "One of {p} and {q} is the demon, yes?"],
        "or3_type": ["Is the demon among {p}, {q} and {r}?", "Is the demon someone out of {p}, {q} and {r}?"],
        "or_role": ["Is the {role} {p} or {q}?", "Does {p} or {q} hold the {role}?"],
        "and_team": ["Can I trust both {p} and {q}? Are they both good?", "Are {p} and {q} each good?"],
        "and_evil": ["Are {p} and {q} evil together?", "Yes or no: {p} and {q} are both evil."],
        "not_type": ["Can you confirm {p} is not the demon?", "Yes or no: {p} is not the demon."],
        "left": ["The person sitting to my left, are they {team}?", "My left-hand neighbour: {team}?"],
        "right": ["The person sitting to my right, are they {team}?", "My right-hand neighbour: {team}?"],
        "neighbours": ["Is anyone sitting next to me evil?", "Do I have an evil neighbour?"],
        "their_left": ["Whoever sits left of {p}, are they {type}?", "Is {p}'s left-hand neighbour {type}?"],
        "unanswerable": ["Which one of us is the demon?", "Tell me {p}'s character.", "Are we going to win?",
                         "Who should I nominate?", "What time is it?", "Which minion is {p}?",
                         "How many outsiders are there exactly?", "Can you give me a hint?",
                         "What will the demon do tonight?", "Who did the Imp kill?",
                         "Why is {p} so quiet?", "Tell me something useful."],
    },
}


def random_world(rng: random.Random, names: list[str]) -> World:
    ed = rng.choice(list(EDITIONS.values()))
    roles = {r.id: (r.name, r.type) for r in ed.roles.values()}
    n = rng.randint(5, 15)
    chosen = rng.sample(names, n)
    ids = list(roles)
    demon = rng.choice([r for r in ids if roles[r][1] == "demon"])
    minions = rng.sample([r for r in ids if roles[r][1] == "minion"], rng.randint(1, 3))
    good = rng.sample([r for r in ids if roles[r][1] in ("townsfolk", "outsider")], n - 1 - len(minions))
    assigned = [demon, *minions, *good]
    rng.shuffle(assigned)
    seats = []
    for name, r in zip(chosen, assigned):
        t = roles[r][1]
        team = "evil" if t in ("minion", "demon") else "good"
        if rng.random() < 0.05:
            team = "evil" if team == "good" else "good"
        seats.append(Seat(name, r, t, team, rng.random() < 0.75, rng.random() < 0.15))
    return World(seats, roles)


def role_word(rng, world: World, rid: str) -> str:
    name = world.roles[rid][0]
    options = [name, name.lower(), *ROLE_ALIASES.get(rid, [])]
    return rng.choice(options)


def make_example(rng: random.Random, split: str) -> dict:
    names = NAMES_TRAIN if split == "train" else NAMES_TEST
    w = random_world(rng, names)
    asker = rng.choice(w.seats).name
    others = [s.name for s in w.seats if s.name != asker]
    p, q, r = rng.sample(others, 3)
    role = rng.choice(list(w.roles))
    if rng.random() < 0.5:  # often ask about a character that is really there
        role = rng.choice(w.seats).role
    ty = rng.choice(["townsfolk", "outsider", "minion", "demon"])
    team = rng.choice(["good", "evil"])
    n = rng.randint(1, 4)
    of = rng.choice(["good", "evil", "minion", "outsider", "townsfolk"])
    intent = rng.choice(list(T[split]))
    if split == "train" and rng.random() < 0.08:
        intent = "unanswerable"  # about 12% of training questions are unanswerable
    tpl = rng.choice(T[split][intent])
    fill = {"p": p, "q": q, "r": r, "role": role_word(rng, w, role), "type": rng.choice(TYPE_WORDS[ty]),
            "team": team, "n": n, "plural": rng.choice(PLURAL[of]),
            "plural_type": rng.choice(PLURAL[ty] if ty != "demon" else ["demons"])}
    gold: dict
    if intent == "is_role":
        gold = {"op": "is_role", "player": p, "role": role}
    elif intent == "is_type":
        gold = {"op": "is_type", "player": p, "type": ty}
    elif intent == "is_team":
        gold = {"op": "is_team", "player": p, "team": team}
    elif intent == "in_play":
        gold = {"op": "in_play", "role": role}
    elif intent == "is_malfunctioning":
        gold = {"op": "is_malfunctioning", "player": p}
    elif intent == "me_malfunctioning":
        gold = {"op": "is_malfunctioning", "player": "me"}
    elif intent == "me_team":
        gold = {"op": "is_team", "player": "me", "team": team}
    elif intent == "count_ge":
        gold = {"op": "count", "of": of, "alive_only": False, "cmp": ">=", "n": n}
    elif intent == "count_alive_ge":
        gold = {"op": "count", "of": of, "alive_only": True, "cmp": ">=", "n": n}
    elif intent == "count_eq":
        gold = {"op": "count", "of": of, "alive_only": False, "cmp": "==", "n": n}
    elif intent == "or_type":
        gold = {"op": "or", "args": [{"op": "is_type", "player": x, "type": "demon"} for x in (p, q)]}
    elif intent == "or3_type":
        gold = {"op": "or", "args": [{"op": "is_type", "player": x, "type": "demon"} for x in (p, q, r)]}
    elif intent == "or_role":
        gold = {"op": "or", "args": [{"op": "is_role", "player": x, "role": role} for x in (p, q)]}
    elif intent == "and_team":
        gold = {"op": "and", "args": [{"op": "is_team", "player": x, "team": "good"} for x in (p, q)]}
    elif intent == "and_evil":
        gold = {"op": "and", "args": [{"op": "is_team", "player": x, "team": "evil"} for x in (p, q)]}
    elif intent == "not_type":
        gold = {"op": "not", "arg": {"op": "is_type", "player": p, "type": "demon"}}
    elif intent == "left":
        gold = {"op": "is_team", "player": "cw:me", "team": team}
    elif intent == "right":
        gold = {"op": "is_team", "player": "ccw:me", "team": team}
    elif intent == "neighbours":
        gold = {"op": "or", "args": [{"op": "is_team", "player": f"{d}:me", "team": "evil"} for d in ("cw", "ccw")]}
    elif intent == "their_left":
        gold = {"op": "is_type", "player": f"cw:{p}", "type": ty}
    else:
        gold = {"op": "unanswerable"}
    text = tpl.format(**fill)
    if rng.random() < 0.15:
        text = text.lower()
    return {"world": world_json(w), "asker": asker, "question": text, "gold": gold, "intent": intent}


def world_json(w: World) -> dict:
    return {"seats": [s.__dict__ for s in w.seats], "roles": w.roles}


def world_from_json(d: dict) -> World:
    return World([Seat(**s) for s in d["seats"]], {k: tuple(v) for k, v in d["roles"].items()})


PREFIXES = ["", "", "", "Hey storyteller, ", "ok so ", "Quick question: ", "Storyteller - ", "hmm ",
            "Right, ", "I'd like to ask: ", "My question is: ", "so "]
SUFFIXES = ["", "", "", " yes or no?", " thanks", " y/n", "??", " please", " I need to know.", " be honest"]
CHATTER = ["{x} has been really quiet. ", "I don't trust {x}. ", "{x} claimed something weird yesterday. ",
           "Everyone thinks {x} is lying. ", "Last night was chaos. "]


def typo(rng: random.Random, word: str) -> str:
    if len(word) < 4:
        return word
    i = rng.randrange(1, len(word) - 1)
    kind = rng.choice(["drop", "swap", "double"])
    if kind == "drop":
        return word[:i] + word[i + 1:]
    if kind == "swap":
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    return word[:i] + word[i] + word[i:]


def augment(rng: random.Random, ex: dict) -> dict:
    """Training-only noise: typos in names, chatty openings and endings, table talk."""
    text = ex["question"]
    names = [s["name"] for s in ex["world"]["seats"]]
    if rng.random() < 0.15:
        present = [n for n in names if n in text]
        if present:
            n = rng.choice(present)
            text = text.replace(n, typo(rng, n), 1)
    if rng.random() < 0.3:
        text = rng.choice(PREFIXES) + text[0].lower() + text[1:] if text else text
    if rng.random() < 0.25:
        text = text.rstrip("?.") + rng.choice(SUFFIXES)
    if rng.random() < 0.1:
        text = rng.choice(CHATTER).format(x=rng.choice(names)) + text
    return {**ex, "question": text}


def generate(n: int, split: str, seed: int) -> list[dict]:
    rng = random.Random(seed)
    out = []
    while len(out) < n:
        ex = make_example(rng, split)
        if split == "train":
            ex = augment(rng, ex)
        w = world_from_json(ex["world"])
        ex["gold"] = validate(ex["gold"], w, ex["asker"])
        out.append(ex)
    return out


def equivalent(pred: dict, gold: dict, world: World, asker: str, rng: random.Random, trials: int = 24) -> bool:
    """Do two queries give the same answer on this world and on reshuffled copies of it?"""
    if (pred["op"] == "unanswerable") != (gold["op"] == "unanswerable"):
        return False
    if gold["op"] == "unanswerable":
        return True
    worlds = [world]
    for _ in range(trials):
        seats = [Seat(**s.__dict__) for s in world.seats]
        roles = [(s.role, s.type, s.team) for s in seats]
        rng.shuffle(roles)
        for s, (ro, ty, te) in zip(seats, roles):
            s.role, s.type, s.team = ro, ty, te
            s.alive = rng.random() < 0.75
            s.malfunctioning = rng.random() < 0.3
        worlds.append(World(seats, world.roles))
    return all(evaluate(pred, w, asker) == evaluate(gold, w, asker) for w in worlds)


if __name__ == "__main__":
    import sys
    split, n = sys.argv[1], int(sys.argv[2])
    for ex in generate(n, split, seed=7 if split == "train" else 99):
        print(json.dumps(ex))
