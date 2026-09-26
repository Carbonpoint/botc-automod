"""Keyword tasks: meet a player in person and enter their keyword."""

import pytest
from test_engine import lobby

from botc_automod import keywords
from botc_automod.game import GameError


def day_game(n=5, on=True):
    g = lobby(n)
    g.settings["irl_tasks"] = int(on)
    g.start()
    while g.phase != "day":
        g.advance()
    return g, g.seated()


def test_one_loop_with_distinct_words():
    g, ps = day_game(7)
    st = g.estate["irl"]
    assert len(set(st["words"].values())) == 7
    seen, cur = [], ps[0].id
    for _ in range(7):                      # following targets visits everyone once
        seen.append(cur)
        cur = st["target"][cur]
    assert sorted(seen) == sorted(p.id for p in ps) and cur == ps[0].id
    assert all("Keyword task" in p.log[-1]["text"] for p in ps)
    v = keywords.view(g, ps[0].id)
    assert v["word"] == st["words"][ps[0].id] and st["target"][v["give_to"]] == ps[0].id


def test_off_by_default():
    g, ps = day_game(on=False)
    assert "irl" not in g.estate and keywords.view(g, ps[0].id) is None


def test_right_word_gives_karma_then_extras():
    g, ps = day_game()
    st = g.estate["irl"]
    a = ps[0]
    t = st["target"][a.id]
    other = next(x for x in st["words"] if x not in (a.id, t))
    with pytest.raises(GameError, match="First get"):
        keywords.submit(g, a.id, other, st["words"][other])
    assert "Right" in keywords.submit(g, a.id, t, "  " + st["words"][t].upper() + " ")
    assert a.karma == keywords.WIN
    owner, receiver = g.p(other), g.p(next(x for x, y in st["target"].items() if y == other))
    before = (owner.karma, receiver.karma)
    keywords.submit(g, a.id, other, st["words"][other])      # a snoop
    assert a.karma == keywords.WIN + keywords.SNOOP
    if receiver is not a:
        assert (owner.karma, receiver.karma) == (before[0] + keywords.LEAK, before[1] + keywords.LEAK)
    with pytest.raises(GameError, match="already"):
        keywords.submit(g, a.id, other, st["words"][other])


def test_three_wrong_tries_and_small_penalty():
    g, ps = day_game()
    st = g.estate["irl"]
    a = ps[1]
    t = st["target"][a.id]
    assert "2 tries left" in keywords.submit(g, a.id, t, "nope")
    keywords.submit(g, a.id, t, "nope")
    assert "no tries left" in keywords.submit(g, a.id, t, "nope")
    assert a.karma == keywords.MISS
    with pytest.raises(GameError, match="no tries"):
        keywords.submit(g, a.id, t, st["words"][t])
    keywords.close(g)
    assert a.karma == keywords.MISS                            # not punished twice


def test_day_end_misses_and_new_words_next_day():
    g, ps = day_game()
    first = dict(g.estate["irl"]["words"])
    while g.phase != "night":
        g.advance()
    assert all(p.karma == keywords.MISS for p in ps)
    assert keywords.view(g, ps[0].id) is None                  # nothing to do at night
    with pytest.raises(GameError):
        keywords.submit(g, ps[0].id, ps[1].id, "x")
    while g.phase != "day":
        g.advance()
    if g.phase == "day":
        assert g.estate["irl"]["day"] == g.day and g.estate["irl"]["words"] != first


def test_no_karma_change_with_karma_off():
    g, ps = day_game()
    g.settings["karma"] = 0
    st = g.estate["irl"]
    keywords.submit(g, ps[0].id, st["target"][ps[0].id], st["words"][st["target"][ps[0].id]])
    assert ps[0].karma == 0
