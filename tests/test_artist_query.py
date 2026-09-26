"""The Artist query language: validation, evaluation, rendering, and the datasets."""

import random

import pytest

from botc_automod.artist import dataset
from botc_automod.artist.data import natural
from botc_automod.artist.query import BadQuery, Seat, World, evaluate, render, validate
from botc_automod.artist.translate import extract_json

ROLES = {"imp": ("Imp", "demon"), "poisoner": ("Poisoner", "minion"), "chef": ("Chef", "townsfolk"),
         "saint": ("Saint", "outsider"), "fortuneteller": ("Fortune Teller", "townsfolk")}


def world():
    return World([Seat("Ann", "chef", "townsfolk", "good", True, False),
                  Seat("Ben", "imp", "demon", "evil", True, False),
                  Seat("Cat", "poisoner", "minion", "evil", False, False),
                  Seat("Dan", "saint", "outsider", "good", True, True)], ROLES)


@pytest.mark.parametrize("q,truth", [
    ({"op": "is_role", "player": "Ben", "role": "imp"}, True),
    ({"op": "is_role", "player": "ben", "role": "Fortune Teller"}, False),   # names and ids are forgiving
    ({"op": "is_type", "player": "Cat", "type": "minion"}, True),
    ({"op": "is_team", "player": "me", "team": "good"}, True),
    ({"op": "in_play", "role": "fortuneteller"}, False),
    ({"op": "is_malfunctioning", "player": "Dan"}, True),
    ({"op": "is_team", "player": "cw:me", "team": "evil"}, True),       # Ann's left is Ben
    ({"op": "is_role", "player": "ccw:me", "role": "saint"}, True),     # Ann's right is Dan (wraps)
    ({"op": "count", "of": "evil", "alive_only": True, "cmp": "==", "n": 1}, True),
    ({"op": "count", "of": "evil", "alive_only": False, "cmp": ">=", "n": 2}, True),
    ({"op": "or", "args": [{"op": "is_type", "player": "Ann", "type": "demon"},
                           {"op": "is_type", "player": "Ben", "type": "demon"}]}, True),
    ({"op": "and", "args": [{"op": "is_team", "player": "Ann", "team": "good"},
                            {"op": "not", "arg": {"op": "is_team", "player": "Dan", "team": "evil"}}]}, True),
])
def test_evaluate(q, truth):
    w = world()
    v = validate(q, w, "Ann")
    assert evaluate(v, w, "Ann") is truth
    assert render(v, w, "Ann")


@pytest.mark.parametrize("q", [
    {"op": "is_role", "player": "Zed", "role": "imp"},
    {"op": "is_role", "player": "Ann", "role": "wizard"},
    {"op": "is_type", "player": "Ann", "type": "god"},
    {"op": "or", "args": [{"op": "or", "args": []}]},
    {"op": "count", "of": "evil", "cmp": "~", "n": 1},
    {"op": "or", "args": [{"op": "unanswerable"}, {"op": "in_play", "role": "imp"}]},
    "not a dict",
])
def test_invalid(q):
    with pytest.raises(BadQuery):
        validate(q, world(), "Ann")


def test_unanswerable_has_no_answer():
    assert evaluate(validate({"op": "unanswerable"}, world(), "Ann"), world(), "Ann") is None


def test_render_words():
    w = world()
    q = validate({"op": "is_team", "player": "cw:me", "team": "evil"}, w, "Ann")
    assert render(q, w, "Ann") == "the player on your left (Ben) is evil"


def test_extract_json_handles_fences_and_thinking():
    assert extract_json('<think>hmm</think>```json\n{"op": "unanswerable"}\n```') == {"op": "unanswerable"}
    assert extract_json("no json here") is None


def test_datasets_are_valid_and_disjoint():
    train = dataset.generate(3000, "train", 7)
    test = dataset.generate(500, "test", 99)
    train_names = {s["name"] for e in train for s in e["world"]["seats"]}
    test_names = {s["name"] for e in test for s in e["world"]["seats"]}
    assert not train_names & test_names
    assert not {e["question"] for e in train} & {e["question"] for e in test}
    assert not set(natural.PLAYERS) & (train_names | test_names)


def test_gold_is_equivalent_to_itself_and_not_to_its_negation():
    rng = random.Random(1)
    for e in dataset.generate(200, "test", 5):
        w = dataset.world_from_json(e["world"])
        assert dataset.equivalent(e["gold"], e["gold"], w, e["asker"], rng)
        if e["gold"]["op"] != "unanswerable":
            assert not dataset.equivalent({"op": "not", "arg": e["gold"]} if e["gold"]["op"] not in ("or", "and", "not")
                                          else e["gold"], e["gold"], w, e["asker"], rng) or e["gold"]["op"] in ("or", "and", "not")


def test_natural_set_is_valid():
    w = World([Seat(n, "chef", "townsfolk", "good", True, False) for n in natural.PLAYERS],
              {**ROLES, **{r: ("x", "townsfolk") for r in ("empath", "drunk", "spy", "virgin", "scarletwoman", "baron",
                                                         "slayer", "mayor", "undertaker", "washerwoman", "ravenkeeper",
                                                         "monk", "recluse", "soldier", "butler", "investigator",
                                                         "librarian")}})
    for q, gold in natural.QUESTIONS:
        validate(gold, w, natural.ASKER)
