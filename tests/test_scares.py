"""Jump scares and the falling pipe: who gets one, and when."""

import pytest
from test_engine import lobby

from botc_automod import scares
from botc_automod.game import GameError


def day_game(n=5, level=scares.HIGH, pipe=1, names=None):
    g = lobby(n)
    if names:
        for p, name in zip(g.seated(), names):
            p.name = name
    g.settings["scares"] = level
    g.settings["pipe"] = pipe
    g.settings["narrator"] = 0
    g.start()
    while g.phase != "day":
        g.advance()
    return g, g.seated()


def test_off_means_no_screens():
    g, ps = day_game(level=scares.OFF)
    assert all(scares.view(g, p.id) == [] for p in ps)


def test_high_gives_everyone_one_a_day_at_different_times():
    g, ps = day_game(7)
    due = [scares.view(g, p.id) for p in ps]
    assert all(len(d) == 1 and d[0]["kind"] == "screen" for d in due)
    assert all(scares.EARLIEST - 1 <= d[0]["in"] <= scares.LATEST for d in due)
    assert len({d[0]["id"] for d in due}) == 7
    times = sorted(s["at"] for d in g.estate["scares"]["due"].values() for s in d)
    assert all(b - a >= scares.GAP for a, b in zip(times, times[1:]))
    assert g.view_for(ps[0].id)["me"]["scares"] == due[0]


def test_low_is_rare():
    got = 0
    for _ in range(40):
        g, ps = day_game(level=scares.LOW, pipe=0)
        got += sum(len(scares.view(g, p.id)) for p in ps)
    assert 20 < got < 80          # 200 player-days at 0.25


def test_scares_drop_at_night():
    g, ps = day_game()
    while g.phase != "night":
        g.advance()
    assert all(scares.view(g, p.id) == [] for p in ps)


def test_pipe_goes_to_tommy_once_a_game():
    g, ps = day_game(level=scares.OFF, names=["Ana", "Tommy", "Cy", "Di", "Ed"])
    tommy = ps[1]
    assert scares.pipe_target(g) == tommy.id
    pipes = 0
    for _ in range(5):
        pipes += sum(s["kind"] == "pipe" for s in scares.view(g, tommy.id))
        while g.phase != "night":
            g.advance()
        if g.phase == "ended":
            break
        while g.phase not in ("day", "ended"):
            g.advance()
        if g.phase == "ended":
            break
    assert pipes <= 1
    assert all(s["kind"] != "pipe" for p in ps if p is not tommy for s in scares.view(g, p.id))


def test_pipe_always_comes_by_day_three():
    g, ps = day_game(level=scares.OFF, names=["Ana", "Tommy", "Cy", "Di", "Ed"])
    g.day = 3
    g.estate["scares"]["pipe_done"] = False
    scares.plan(g)
    assert [s["kind"] for s in scares.view(g, ps[1].id)] == ["pipe"]


def test_no_tommy_no_pipe_unless_the_host_picks_one():
    g, ps = day_game(level=scares.OFF)
    assert scares.pipe_target(g) is None
    scares.set_pipe_target(g, ps[2].id)
    g.day = 3
    scares.plan(g)
    assert [s["kind"] for s in scares.view(g, ps[2].id)] == ["pipe"]


def test_pipe_off():
    g, ps = day_game(level=scares.OFF, pipe=0, names=["Tommy"])
    g.day = 3
    scares.plan(g)
    assert scares.view(g, ps[0].id) == []


def test_setting_checks():
    g = lobby(5)
    g.set_setting("scares", 2)
    with pytest.raises(GameError):
        g.set_setting("scares", 4)
    with pytest.raises(GameError):
        g.set_setting("pipe", 2)
