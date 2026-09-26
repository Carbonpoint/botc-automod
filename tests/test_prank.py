"""Emma's hidden button: Tommy is poisoned for the rest of the game, as quietly as possible."""

import random

import pytest
from test_editions import answer, rigged

from botc_automod.game import GameError, is_emma, is_tommy


@pytest.mark.parametrize("name", ["Emma", "emma", "EMMA", "Emmy", "Em", "Emma W.", "Ema", "Emmaa", "Emmie"])
def test_emma_names(name):
    assert is_emma(name)


@pytest.mark.parametrize("name", ["Gemma", "Ella", "Emily", "Anna", "Tommy"])
def test_not_emma(name):
    assert not is_emma(name)


@pytest.mark.parametrize("name", ["Tommy", "tommy", "Tom", "Thomas", "Tomy", "Tommie", "Tom B", "Tommmy"])
def test_tommy_names(name):
    assert is_tommy(name)


@pytest.mark.parametrize("name", ["Tammy", "Timmy", "Tony", "Toby", "Emma"])
def test_not_tommy(name):
    assert not is_tommy(name)


def to_day(g, rng):
    while g.phase != "day":
        answer(g, rng)
        g.advance()


def game(roles, emma=0, tommy=1):
    g = rigged(roles, "tb")
    ps = g.seated()
    ps[emma].name, ps[tommy].name = "Emma", "Tommy"
    return g, ps[emma], ps[tommy], random.Random(4)


def test_button_only_for_emma_by_day_and_once():
    g, emma, tommy, rng = game(["washerwoman", "empath", "chef", "spy", "imp"])
    assert not g.can_annoy(emma.id)                      # night
    to_day(g, rng)
    assert g.view_for(emma.id)["me"]["annoy"] is True
    assert g.view_for(tommy.id)["me"]["annoy"] is False
    with pytest.raises(GameError):
        g.annoy(tommy.id)
    g.annoy(emma.id)
    assert g.view_for(emma.id)["me"]["annoy"] is False   # the button disappears
    with pytest.raises(GameError):
        g.annoy(emma.id)
    R = g.edition
    assert R.malfunction(g, tommy)
    assert not R.truthful(g, tommy, "empath")
    assert tommy.id not in g.estate.get("abnormal", [])   # the Mathematician does not count it
    # The public log says nothing.
    assert not any("Tommy" in e["text"] and "poison" in e["text"].lower() for e in g.public_log)


def test_poison_lasts_the_game():
    g, emma, tommy, rng = game(["washerwoman", "empath", "chef", "spy", "imp"])
    to_day(g, rng)
    g.annoy(emma.id)
    for _ in range(3):
        g.advance()                       # nominations, end of the day, into the night
        while g.phase != "day" and g.phase != "ended":
            answer(g, rng)
            g.advance()
        if g.phase == "ended":
            break
        assert g.edition.malfunction(g, tommy)


def test_spy_does_not_see_it_but_the_storyteller_notes_do():
    g, emma, tommy, rng = game(["washerwoman", "empath", "chef", "spy", "imp"])
    to_day(g, rng)
    g.annoy(emma.id)
    R = g.edition
    assert "drunk or poisoned" not in R.player_notes(g, tommy, spy=True)
    assert "drunk or poisoned" in R.player_notes(g, tommy)


def test_a_demon_tommy_still_kills():
    g, emma, tommy, rng = game(["washerwoman", "imp", "chef", "spy", "empath"])
    to_day(g, rng)
    g.annoy(emma.id)
    assert not g.edition.malfunction(g, tommy)
    tommy.role = tommy.shown = "chef"     # no longer the Demon: the poison works again
    assert g.edition.malfunction(g, tommy)


def test_no_button_without_a_tommy():
    g, emma, other, rng = game(["washerwoman", "empath", "chef", "spy", "imp"])
    other.name = "Ben"
    to_day(g, rng)
    assert not g.can_annoy(emma.id)
