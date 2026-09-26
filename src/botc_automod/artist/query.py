"""The Artist's query language.

A language model translates a player's yes/no question into one query.
The engine, not the model, then decides the answer from the true game
state. So the model can misunderstand a question, but it cannot lie.

A query is a JSON object. Atoms:

    {"op": "is_role", "player": P, "role": R}          Is Ann the Imp?
    {"op": "is_type", "player": P, "type": T}          Is Ann a Minion?
    {"op": "is_team", "player": P, "team": "evil"}     Is Ann evil?
    {"op": "in_play", "role": R}                       Is the Vortox in play?
    {"op": "is_malfunctioning", "player": P}           Is Ann drunk or poisoned?
    {"op": "count", "of": X, "alive_only": bool, "cmp": C, "n": int}
                                                       Are 2 or more evil players alive?

Combinations, one level deep (args are atoms or {"op": "not", "arg": atom}):

    {"op": "or", "args": [...]}    {"op": "and", "args": [...]}    {"op": "not", "arg": atom}

And {"op": "unanswerable"} for anything else: not yes/no, about the
future, about strategy, or outside the game.

P is a player name exactly as listed, "me" (the asker), or a seat
reference "cw:NAME" / "ccw:NAME": the player seated next to NAME
clockwise / counter-clockwise. R is a character id. T is townsfolk,
outsider, minion or demon. X is a type, "good" or "evil". C is one of
== != >= <= > <.
"""

from __future__ import annotations

from dataclasses import dataclass

TYPES = ("townsfolk", "outsider", "minion", "demon")
TEAMS = ("good", "evil")
CMPS = ("==", "!=", ">=", "<=", ">", "<")
ATOMS = ("is_role", "is_type", "is_team", "in_play", "is_malfunctioning", "count")


class BadQuery(ValueError):
    """The model's output is not a valid query for this game."""


@dataclass
class Seat:
    name: str
    role: str          # true character id
    type: str
    team: str          # true alignment
    alive: bool        # alive as everyone sees it
    malfunctioning: bool


@dataclass
class World:
    """What a query is evaluated against: the true state, in seat order."""
    seats: list[Seat]
    roles: dict[str, tuple[str, str]]   # id -> (name, type)

    def seat(self, name: str) -> Seat:
        for s in self.seats:
            if s.name.lower() == name.lower():
                return s
        raise BadQuery(f"unknown player {name!r}")

    @classmethod
    def from_game(cls, game) -> World:
        R = game.edition
        seats = [Seat(p.name, p.role, R.type_of(p.role), R.alignment(p), game.living(p),
                      bool(getattr(R, "malfunction", None) and R.malfunction(game, p)))
                 for p in game.seated()]
        return cls(seats, {r.id: (r.name, r.type) for r in R.roles.values()})


def resolve(world: World, ref: str, asker: str) -> Seat:
    ref = str(ref).strip()
    if ref.lower() == "me":
        return world.seat(asker)
    for prefix, step in (("cw:", 1), ("ccw:", -1)):
        if ref.lower().startswith(prefix):
            base = world.seat(resolve(world, ref[len(prefix):], asker).name)
            i = world.seats.index(base)
            return world.seats[(i + step) % len(world.seats)]
    return world.seat(ref)


def _role(world: World, rid) -> str:
    rid = str(rid).lower().replace(" ", "").replace("'", "").replace("-", "")
    if rid not in world.roles:
        by_name = {n.lower().replace(" ", "").replace("'", "").replace("-", ""): k
                   for k, (n, _) in world.roles.items()}
        if rid not in by_name:
            raise BadQuery(f"unknown character {rid!r}")
        rid = by_name[rid]
    return rid


def validate(q: dict, world: World, asker: str, depth: int = 0) -> dict:
    """Check and normalise a query. Raises BadQuery."""
    if not isinstance(q, dict) or "op" not in q:
        raise BadQuery("not a query object")
    op = q["op"]
    if op == "unanswerable":
        if depth:
            raise BadQuery("unanswerable inside a combination")
        return {"op": op}
    if op in ("or", "and"):
        if depth:
            raise BadQuery("combinations are one level deep")
        args = q.get("args")
        if not isinstance(args, list) or not 2 <= len(args) <= 6:
            raise BadQuery("or/and need 2 to 6 arguments")
        return {"op": op, "args": [validate(a, world, asker, 1) for a in args]}
    if op == "not":
        if depth > 1:
            raise BadQuery("not is too deep")
        return {"op": "not", "arg": validate(q.get("arg"), world, asker, 2)}
    if op not in ATOMS:
        raise BadQuery(f"unknown op {op!r}")
    out = {"op": op}
    if op in ("is_role", "is_type", "is_team", "is_malfunctioning"):
        resolve(world, q.get("player", ""), asker)
        out["player"] = str(q["player"])
    if op in ("is_role", "in_play"):
        out["role"] = _role(world, q.get("role", ""))
    if op == "is_type":
        if q.get("type") not in TYPES:
            raise BadQuery("bad type")
        out["type"] = q["type"]
    if op == "is_team":
        if q.get("team") not in TEAMS:
            raise BadQuery("bad team")
        out["team"] = q["team"]
    if op == "count":
        if q.get("of") not in TYPES + TEAMS or q.get("cmp") not in CMPS:
            raise BadQuery("bad count")
        try:
            n = int(q.get("n"))
        except (TypeError, ValueError):
            raise BadQuery("bad count number") from None
        out.update({"of": q["of"], "alive_only": bool(q.get("alive_only", False)), "cmp": q["cmp"], "n": n})
    return out


def evaluate(q: dict, world: World, asker: str) -> bool | None:
    """The true answer to a validated query; None when unanswerable."""
    op = q["op"]
    if op == "unanswerable":
        return None
    if op == "or":
        return any(evaluate(a, world, asker) for a in q["args"])
    if op == "and":
        return all(evaluate(a, world, asker) for a in q["args"])
    if op == "not":
        return not evaluate(q["arg"], world, asker)
    if op == "in_play":
        return any(s.role == q["role"] for s in world.seats)
    if op == "count":
        match = [s for s in world.seats if (s.type == q["of"] or s.team == q["of"])
                 and (s.alive or not q["alive_only"])]
        n, c = len(match), q["cmp"]
        return {"==": n == q["n"], "!=": n != q["n"], ">=": n >= q["n"], "<=": n <= q["n"],
                ">": n > q["n"], "<": n < q["n"]}[c]
    s = resolve(world, q["player"], asker)
    if op == "is_role":
        return s.role == q["role"]
    if op == "is_type":
        return s.type == q["type"]
    if op == "is_team":
        return s.team == q["team"]
    if op == "is_malfunctioning":
        return s.malfunctioning
    raise BadQuery(op)


def _who(world: World, ref: str, asker: str) -> str:
    ref = str(ref)
    if ref.lower() == "me":
        return "you"
    for prefix, side in (("cw:", "left"), ("ccw:", "right")):
        if ref.lower().startswith(prefix):
            base = ref[len(prefix):]
            whose = "your" if base.lower() == "me" else f"{_who(world, base, asker)}'s"
            return f"the player on {whose} {side} ({resolve(world, ref, asker).name})"
    return resolve(world, ref, asker).name


def render(q: dict, world: World, asker: str) -> str:
    """The query in plain words, shown to the Artist before they confirm."""
    op = q["op"]
    if op == "unanswerable":
        return "(a question the Storyteller cannot answer yes or no)"
    if op in ("or", "and"):
        return f" {op} ".join(render(a, world, asker) for a in q["args"])
    if op == "not":
        return "it is not true that " + render(q["arg"], world, asker)
    if op == "in_play":
        return f"the {world.roles[q['role']][0]} is in play"
    if op == "count":
        words = {"==": "exactly", "!=": "not exactly", ">=": "at least", "<=": "at most",
                 ">": "more than", "<": "fewer than"}[q["cmp"]]
        what = q["of"] if q["of"] in TEAMS else (q["of"] if q["of"] == "townsfolk" else q["of"] + "s")
        noun = f"{what} players" if q["of"] in TEAMS else what
        return f"there are {words} {q['n']} {noun}{' alive' if q['alive_only'] else ' in the game'}"
    who = _who(world, q["player"], asker)
    verb = "are" if who == "you" else "is"
    if op == "is_role":
        return f"{who} {verb} the {world.roles[q['role']][0]}"
    if op == "is_type":
        return f"{who} {verb} {'a' if q['type'] != 'outsider' else 'an'} {q['type'].capitalize()}"
    if op == "is_team":
        return f"{who} {verb} {q['team']}"
    return f"{who} {verb} drunk or poisoned"


def schema(world: World) -> dict:
    """JSON schema for constrained decoding. Names and character ids are enums."""
    names = [s.name for s in world.seats]
    refs = {"type": "string"}   # names, me, cw:/ccw: - checked by validate()
    role = {"type": "string", "enum": sorted(world.roles)}
    atom_variants = [
        {"type": "object", "properties": {"op": {"const": "is_role"}, "player": refs, "role": role},
         "required": ["op", "player", "role"], "additionalProperties": False},
        {"type": "object", "properties": {"op": {"const": "is_type"}, "player": refs,
                                          "type": {"type": "string", "enum": list(TYPES)}},
         "required": ["op", "player", "type"], "additionalProperties": False},
        {"type": "object", "properties": {"op": {"const": "is_team"}, "player": refs,
                                          "team": {"type": "string", "enum": list(TEAMS)}},
         "required": ["op", "player", "team"], "additionalProperties": False},
        {"type": "object", "properties": {"op": {"const": "in_play"}, "role": role},
         "required": ["op", "role"], "additionalProperties": False},
        {"type": "object", "properties": {"op": {"const": "is_malfunctioning"}, "player": refs},
         "required": ["op", "player"], "additionalProperties": False},
        {"type": "object", "properties": {"op": {"const": "count"},
                                          "of": {"type": "string", "enum": list(TYPES + TEAMS)},
                                          "alive_only": {"type": "boolean"},
                                          "cmp": {"type": "string", "enum": list(CMPS)},
                                          "n": {"type": "integer", "minimum": 0, "maximum": 20}},
         "required": ["op", "of", "alive_only", "cmp", "n"], "additionalProperties": False},
    ]
    atom = {"anyOf": atom_variants}
    neg = {"type": "object", "properties": {"op": {"const": "not"}, "arg": atom},
           "required": ["op", "arg"], "additionalProperties": False}
    arg = {"anyOf": [*atom_variants, neg]}
    combo = [{"type": "object", "properties": {"op": {"const": k}, "args": {"type": "array", "items": arg,
                                                                            "minItems": 2, "maxItems": 6}},
              "required": ["op", "args"], "additionalProperties": False} for k in ("or", "and")]
    unans = {"type": "object", "properties": {"op": {"const": "unanswerable"}},
             "required": ["op"], "additionalProperties": False}
    return {"anyOf": [*atom_variants, neg, *combo, unans], "description": "players: " + ", ".join(names)}
