"""The morning narrator: a random player reads a story of the night before the day starts."""

import pytest
from test_engine import lobby

from botc_automod.game import GameError
from botc_automod.narrator import story


def to_dawn(n=7, night=2):
    g = lobby(n)
    g.settings["narrator"] = 1
    g.start()
    while not (g.phase == "day" and g.night >= night):
        g.advance()
    return g


def test_dawn_waits_for_the_narrator():
    g = to_dawn()
    assert g.stage == "narration" and g.deadline is None
    n = g.estate["narration"]
    narrator = n["pid"]
    other = next(p.id for p in g.seated() if p.id != narrator)
    assert g.view_for(narrator)["narration"]["story"]                 # the narrator sees the story
    assert "story" not in g.view_for(other)["narration"]              # the others only see who reads
    assert g.view_for(other)["narration"]["narrator"] == narrator
    for p in g.seated():                                              # no day actions during the story
        assert all(a.get("forced") for a in g.edition.day_actions(g, p))
    with pytest.raises(GameError):
        g.finish_narration(other if not g.p(other).is_host else
                           next(p.id for p in g.seated() if p.id not in (narrator, other) and not p.is_host))
    g.finish_narration(narrator)
    assert g.stage == "" and g.deadline is not None and "narration" not in g.estate


def test_host_can_start_the_day_and_narrator_can_ask_for_another_story():
    g = to_dawn()
    n = g.estate["narration"]
    g.new_story(n["pid"])
    assert g.estate["narration"]["story"]
    g.finish_narration(g.host.id)
    assert g.stage == "" and g.phase == "day"


def test_advance_ends_the_story_first():
    g = to_dawn()
    g.advance()
    assert g.phase == "day" and g.stage == ""
    g.advance()
    assert g.phase == "nominations"


def test_off_switch():
    g = lobby(7)
    g.start()
    while g.phase != "day":
        g.advance()
    assert g.stage == "" and "narration" not in g.estate


def test_story_names_the_dead_and_only_players():
    living = ["Ann", "Ben", "Cat", "Dan", "Eve"]
    for _ in range(200):
        text = " ".join(story(["Fay"], living, 3))
        assert "Fay" in text
        text = " ".join(story(["Fay", "Gus"], living, 3))
        assert "Fay" in text and "Gus" in text
        assert "{" not in text
    assert story([], living, 1) and story([], living, 4)
    assert story(["Ann"], ["Ann"], 2)       # a tiny town still gets a story


def test_theme_picks_the_story_setting():
    g = lobby(7)
    g.settings["narrator"] = 1
    with pytest.raises(GameError):
        g.set_theme("nope")
    g.set_theme("jojo")
    assert g.view_for(g.host.id)["game"]["theme"]["name"] == "Jo Jo's Mid-Autumn Festival"
    g.start()
    with pytest.raises(GameError):
        g.set_theme("default")
    while not (g.phase == "day" and g.stage == "narration"):
        g.advance()
    text = " ".join(g.estate["narration"]["story"])
    assert "Jo Jo" in text or "Ames" in text or "mooncake" in text
    assert "Ravenswood" not in text
