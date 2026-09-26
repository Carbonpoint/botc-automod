"""The helpful narrator (tips) and the Savant's richer facts."""

import asyncio
import random

import pytest
from test_editions import answer, rigged

from botc_automod import helper, server
from botc_automod.editions.chars_snv import savant_facts
from botc_automod.game import GameError


def to_day(g, rng=None):
    rng = rng or random.Random(3)
    while g.phase != "day":
        answer(g, rng)
        g.advance()


def day_game(roles=("washerwoman", "empath", "chef", "spy", "imp"), shown=None):
    g = rigged(list(roles), "tb", shown=shown)
    to_day(g)
    return g, g.seated()


def test_off_by_default_and_learners_only():
    g, ps = day_game()
    assert not helper.can_tip(g, ps[0])
    g.set_setting("helper", helper.LEARNERS)
    assert not helper.can_tip(g, ps[0])
    g.set_learner(ps[0].id, True)
    assert helper.can_tip(g, ps[0]) and not helper.can_tip(g, ps[1])
    assert g.view_for(ps[0].id)["me"]["tip"]["on"] and not g.view_for(ps[1].id)["me"]["tip"]["on"]
    g.set_learner(ps[0].id, False)
    assert not helper.can_tip(g, ps[0])
    with pytest.raises(GameError):
        g.set_setting("helper", 3)


def test_one_tip_a_day_and_never_at_night():
    g, ps = day_game()
    g.set_setting("helper", helper.EVERYONE)
    lines, team = g.take_tip(ps[1].id)
    assert team == "good" and 2 <= len(lines) <= 3
    with pytest.raises(GameError):
        g.take_tip(ps[1].id)
    g.advance()                                  # nominations: still the same day
    assert not helper.can_tip(g, ps[1])
    g.advance()                                  # end of the day, into the night
    assert g.phase == "night" and not helper.can_tip(g, ps[2])
    to_day(g)
    assert helper.can_tip(g, ps[1])              # a new day, a new tip


def test_rules_tip_is_for_the_believed_character():
    g, ps = day_game(("drunk", "empath", "chef", "spy", "imp"), shown={0: "empath"})
    ed = g.edition
    pool = set(ed.wiki.get("empath", {}).get("tips", [])) | {ed.roles["empath"].tip}
    for _ in range(5):
        assert helper.rules_tip(g, ps[0]) in pool | {f"Read your character again: {ed.roles['empath'].ability}"}


def test_nudge_chance_follows_karma():
    g, ps = day_game()
    p = ps[0]
    for karma, want in ((-5, 0.05), (0, 0.10), (2, 0.20), (10, 0.30)):
        p.karma = karma
        assert helper.nudge_chance(g, p) == pytest.approx(want)
    g.settings["karma"] = 0
    assert helper.nudge_chance(g, p) == 0.10


def test_nudge_names_a_living_other_player():
    g, ps = day_game()
    for p in ps:
        for team in ("good", "evil"):
            line = helper.nudge(g, p, team)
            name = line.removeprefix("I suggest you speak with ").removesuffix(" today.")
            assert name != p.name and name in {x.name for x in ps if g.living(x)}


def test_llm_prompt_hides_names_and_answers_are_checked():
    g, ps = day_game()
    me = ps[1]
    me.note("Night 1", f"{ps[0].name} and {ps[2].name}: 1 of your neighbours is evil.")
    system, user = helper.llm_prompt(g, me, "good", f"Is {ps[4].name} the Demon?")
    for x in ps:
        if x is not me:
            assert x.name not in user
    assert "Never name a player" in system
    assert helper.safe_answer(g, me, f"I think {ps[4].name} is suspicious.") is None
    assert helper.safe_answer(g, me, "<think>hmm</think>Compare your number with others.") == \
        "Compare your number with others."
    assert len(helper.safe_answer(g, me, "Talk to people. " * 100)) <= helper.MAX_ANSWER


class FakeModel:
    can_chat = True

    def __init__(self, reply):
        self.reply = reply

    def chat(self, system, user):
        return self.reply


@pytest.mark.parametrize("reply, shown", [
    ("Your number counts evil living neighbours. Watch it change when a neighbour dies.", True),
    ("The Imp is Eve.", False),          # names a player: thrown away, the offline tip is used
])
def test_server_tip_with_a_model(monkeypatch, reply, shown):
    g, ps = day_game()
    ps[4].name = "Eve"
    g.set_setting("helper", helper.EVERYONE)
    g.helper_llm = True
    monkeypatch.setattr(server, "ARTIST", FakeModel(reply))
    me = ps[1]
    asyncio.run(server.give_tip(g, me, "How do I use my info?"))
    text = " ".join(e["text"] for e in me.log if e["text"].startswith("Narrator's tip"))
    assert (reply in text) is shown
    assert "I suggest you speak with" in text
    if not shown:
        assert "cannot answer that" in text


def test_savant_facts_are_true_or_false_as_labelled():
    g = rigged(["savant", "dreamer", "seamstress", "witch", "fanggu", "mutant", "clockmaker"], "snv")
    to_day(g)
    sav = g.seated()[0]
    facts = savant_facts(g.edition, g, sav)
    assert any(t for _, t in facts) and any(not t for _, t in facts)
    assert len({f.split()[0] for f, _ in facts}) > 5          # many kinds of statement
    truth = dict(facts)
    assert truth.get("There is 1 Outsider in play.") is True
    assert truth.get("There are 2 evil players alive.") is True
    names = [p.name for p in g.seated()]
    assert truth.get(f"{names[3]} is a Minion.", True) is True
    assert truth.get(f"{names[4]} is a Demon.", True) is True
