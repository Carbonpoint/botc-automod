"""Give characters to players.

The deal is random, but it leans toward what each player asked for:
their team (good or evil) first, then their style (chill or thinking).
A random start plus random swaps that never lower the score gives a
deal that honours preferences where it can and stays random elsewhere.
"""

import random

TEAM_WEIGHT = 3.0
STYLE_WEIGHT = 1.0


def _fit(pref: dict, team: str, style: str) -> float:
    return _raw_fit(pref, team, style) * pref.get("_w", 1.0)


def _raw_fit(pref: dict, team: str, style: str) -> float:
    score = 0.0
    t = pref.get("team", "any")
    if t in ("good", "evil"):
        score += TEAM_WEIGHT if t == team else -TEAM_WEIGHT
    s = pref.get("style", "any")
    if s in ("chill", "think"):
        score += STYLE_WEIGHT if s == style else -STYLE_WEIGHT
    return score


def deal(prefs: list[dict], slots: list[tuple[str, str]], rng: random.Random,
         iterations: int = 3000, weights: list[float] | None = None) -> list[int]:
    """Match players to character slots.

    prefs[i] is player i's preference dict. slots[j] is (team, style) of
    character j. weights[i] (karma favour, 1.0 is neutral) makes player i's
    wishes count more or less when two players want the same thing.
    Returns perm where player i gets slot perm[i].
    """
    n = len(prefs)
    assert len(slots) == n
    w = weights or [1.0] * n
    prefs = [{**p, "_w": w[i]} for i, p in enumerate(prefs)]
    perm = list(range(n))
    rng.shuffle(perm)
    if n < 2:
        return perm
    for _ in range(iterations):
        i, j = rng.sample(range(n), 2)
        before = _fit(prefs[i], *slots[perm[i]]) + _fit(prefs[j], *slots[perm[j]])
        after = _fit(prefs[i], *slots[perm[j]]) + _fit(prefs[j], *slots[perm[i]])
        if after >= before:
            perm[i], perm[j] = perm[j], perm[i]
    return perm
