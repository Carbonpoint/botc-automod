"""Every piece of night info in simulated automod games is accurate, complete and delivered."""

import random

import pytest

from botc_automod.audit import check_game
from test_editions import lobby, play


@pytest.mark.parametrize("edition", ["tb", "bmr", "snv"])
def test_info_audit(edition):
    problems = []
    for seed in range(60):
        rng = random.Random(1000 + seed)
        g = lobby(rng.randint(5, 15), edition, 1000 + seed, "auto")
        g.settings["misregister"] = 0.5
        g.estate["audit"] = []
        g.start()
        play(g, rng)
        problems += [f"seed {1000 + seed}: {b}" for b in check_game(g)]
    assert not problems, "\n".join(problems[:20])


def test_small_game_demon_gets_bluffs():
    g = lobby(5, "tb", 3)
    g.start()
    demon = next(p for p in g.seated() if g.edition.type_of(p.role) == "demon")
    assert any(t["key"] == "demon_info" for t in demon.tasks)
    assert len(g.view_for(demon.id)["me"]["bluffs"]) == 3


def test_small_game_bluffs_can_be_turned_off():
    g = lobby(5, "tb", 3)
    g.set_setting("demon_bluffs", 0)
    g.start()
    demon = next(p for p in g.seated() if g.edition.type_of(p.role) == "demon")
    assert not any(t["key"] == "demon_info" for t in demon.tasks)
    assert g.view_for(demon.id)["me"]["bluffs"] == []
