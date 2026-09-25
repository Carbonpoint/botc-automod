import random
import time

import pytest

from botc_automod.assign import deal
from botc_automod.editions.trouble_brewing import DISTRIBUTION, ROLES
from botc_automod.game import Game, GameError
from botc_automod.seating import layout

NAMES = "Ann Ben Cat Dan Eve Fay Gus Hal Ivy Jon Kim Lee Max Ned Oli".split()


def lobby(n: int, seed: int = 1) -> Game:
    g = Game("TEST", seed=seed)
    g.set_room("circle", seats=max(n, 5))
    for i in range(n):
        p = g.join(NAMES[i], is_host=(i == 0))
        g.claim_seat(p.id, i)
    return g


def rigged(roles: list[str], shown: dict[int, str] | None = None, seed: int = 1) -> Game:
    """A game with fixed characters, at the start of night 1."""
    g = lobby(len(roles), seed)
    for i, (p, r) in enumerate(zip(g.seated(), roles)):
        p.role = r
        p.shown = (shown or {}).get(i, r)
    good = [p for p in g.seated() if ROLES[p.role].team == "good"]
    g.estate.update({"bluffs": ["mayor", "soldier", "chef"], "red_herring": good[-1].id})
    g.settings["misregister"] = 0.0
    g.settings["mayor_bounce"] = 0.0
    g.begin_night()
    return g


def by(g: Game, role: str):
    return next(p for p in g.seated() if p.role == role)


def finish_night(g: Game, picks: dict[str, list[str]] | None = None) -> None:
    """Answer every task (picks by role id, else random) through both stages."""
    picks = picks or {}
    for _ in range(2):
        assert g.phase == "night"
        for p in g.seated():
            for t in p.tasks:
                if t["kind"] == "choose":
                    want = picks.get(p.shown if t["key"] == p.shown else t["key"])
                    resp = want if want else g.rng.sample(t["candidates"], t["pick"])
                elif t["kind"] == "decoy":
                    resp = t["options"][0]
                else:
                    resp = True
                g.submit_task(p.id, t["id"], resp)
        g.advance()


def test_distribution_table_matches_rulebook():
    for n, (t, o, m, d) in DISTRIBUTION.items():
        assert t + o + m + d == n
    assert DISTRIBUTION[7] == (5, 0, 1, 1)
    assert DISTRIBUTION[15] == (9, 2, 3, 1)


@pytest.mark.parametrize("n", range(5, 16))
def test_setup_counts_and_drunk(n):
    for seed in range(20):
        g = lobby(n, seed)
        g.start()
        roles = [p.role for p in g.seated()]
        t, o, m, _ = DISTRIBUTION[n]
        if "baron" in roles:
            t, o = t - 2, o + 2
        types = [ROLES[r].type for r in roles]
        assert types.count("townsfolk") == t
        assert types.count("outsider") == o
        assert types.count("minion") == m
        assert roles.count("imp") == 1
        assert len(set(roles)) == n
        for p in g.seated():
            if p.role == "drunk":
                assert ROLES[p.shown].type == "townsfolk"
                assert p.shown not in roles
            else:
                assert p.shown == p.role
        assert not set(g.estate["bluffs"]) & set(roles)


def test_preferences_are_mostly_honoured():
    rng = random.Random(3)
    prefs = [{"team": "evil", "style": "any"}] * 2 + [{"team": "good", "style": "think"}] * 8
    slots = [("evil", "think"), ("evil", "chill")] + [("good", "think")] * 4 + [("good", "chill")] * 4
    perm = deal(prefs, slots, rng)
    assert all(slots[perm[i]][0] == "evil" for i in range(2))
    thinkers = sum(1 for i in range(2, 10) if slots[perm[i]][1] == "think")
    assert thinkers == 4


def test_layouts():
    for shape in ("circle", "horseshoe", "square"):
        seats = layout(shape, seats=9)
        assert len(seats) == 9
        assert all(0 <= s["x"] <= 1 and 0 <= s["y"] <= 1 for s in seats)
    grid = layout("grid", rows=3, cols=4, cells=[[0, 0], [0, 3], [2, 3], [2, 0], [1, 1]])
    assert [s["index"] for s in grid] == [0, 1, 2, 3, 4]


def test_lobby_rules():
    g = lobby(5)
    with pytest.raises(GameError):
        g.join("ann")  # duplicate name, any case
    p = g.join("Zed")
    with pytest.raises(GameError):
        g.claim_seat(p.id, 0)  # taken
    with pytest.raises(GameError):
        g.start()  # Zed is not seated


@pytest.mark.parametrize("seed", range(40))
def test_random_games_always_finish(seed):
    rng = random.Random(seed)
    n = rng.randint(5, 15)
    g = lobby(n, seed)
    g.settings["misregister"] = 0.5
    g.start()
    for _ in range(200):
        if g.phase == "ended":
            break
        if g.phase == "night":
            finish_night(g)
        elif g.phase == "day":
            shooters = [p for p in g.alive() if not p.slayer_claimed]
            if shooters and rng.random() < 0.2:
                g.slayer_claim(rng.choice(shooters).id, rng.choice(g.seated()).id)
            if g.phase == "day":
                g.advance()
        elif g.phase == "nominations":
            alive = [p for p in g.alive() if p.id not in g.nominators_today]
            free = [p for p in g.seated() if p.id not in g.nominees_today]
            if alive and free and rng.random() < 0.8:
                g.nominate(rng.choice(alive).id, rng.choice(free).id)
                if g.phase == "defense":
                    g.advance()
                    for v in g.seated():
                        if g.phase == "vote" and g.can_vote(v):
                            g.vote(v.id, rng.random() < 0.6)
                    if g.phase == "vote":
                        g.advance()
            else:
                g.advance()
    assert g.phase == "ended", "game did not finish"
    assert g.winner in ("good", "evil")
    view = g.view_for(g.seated()[0].id)
    assert len(view["grimoire"]) == n


def test_views_hide_secrets():
    g = lobby(8)
    g.start()
    a, b = g.seated()[0], g.seated()[1]
    view = g.view_for(a.id)
    text = repr(view)
    assert "grimoire" not in view
    assert b.role not in text or ROLES[b.role].name in repr(view["me"]) or b.role == a.shown
    assert all("role" not in p for p in view["players"])


def test_imp_kills_and_monk_protects():
    g = rigged(["imp", "poisoner", "monk", "empath", "chef", "soldier", "mayor"])
    finish_night(g, {"poisoner": [by(g, "chef").id]})
    assert g.phase == "day" and all(p.alive for p in g.seated())
    g.advance(); g.advance()  # to nominations, then nobody executed
    assert g.phase == "night"
    finish_night(g, {"imp": [by(g, "empath").id], "monk": [by(g, "empath").id],
                     "poisoner": [by(g, "chef").id]})
    assert by(g, "empath").alive
    g.advance(); g.advance()
    finish_night(g, {"imp": [by(g, "empath").id], "monk": [by(g, "chef").id],
                     "poisoner": [by(g, "chef").id]})
    assert not by(g, "empath").alive


def test_soldier_survives_unless_poisoned():
    g = rigged(["imp", "poisoner", "soldier", "empath", "chef", "monk", "virgin"])
    finish_night(g)
    g.advance(); g.advance()
    finish_night(g, {"imp": [by(g, "soldier").id], "poisoner": [by(g, "chef").id]})
    assert by(g, "soldier").alive
    g.advance(); g.advance()
    finish_night(g, {"imp": [by(g, "soldier").id], "poisoner": [by(g, "soldier").id]})
    assert not by(g, "soldier").alive


def test_starpass_to_scarlet_woman():
    g = rigged(["imp", "scarletwoman", "monk", "empath", "chef", "soldier", "virgin"])
    finish_night(g)
    g.advance(); g.advance()
    imp, sw = by(g, "imp"), by(g, "scarletwoman")
    finish_night(g, {"imp": [imp.id]})
    assert not imp.alive
    assert sw.role == "imp" and sw.shown == "imp"
    assert g.phase == "day"


def test_executing_imp_with_scarlet_woman_continues():
    g = rigged(["imp", "scarletwoman", "monk", "empath", "chef", "soldier", "virgin"])
    finish_night(g)
    g.advance()
    imp, sw = by(g, "imp"), by(g, "scarletwoman")
    g.nominate(by(g, "chef").id, imp.id)
    g.advance()
    for p in g.alive():
        g.vote(p.id, True) if g.phase == "vote" else None
    g.advance()  # close nominations -> execution
    assert not imp.alive
    assert sw.role == "imp"
    assert g.phase == "night"


def test_executing_imp_wins_for_good():
    g = rigged(["imp", "poisoner", "monk", "empath", "chef"])
    finish_night(g)
    g.advance()
    g.nominate(by(g, "chef").id, by(g, "imp").id)
    g.advance()
    for p in g.alive():
        if g.phase == "vote":
            g.vote(p.id, True)
    g.advance()
    assert g.phase == "ended" and g.winner == "good"


def test_saint_execution_loses():
    g = rigged(["imp", "poisoner", "saint", "empath", "chef", "monk"])
    finish_night(g, {"poisoner": [by(g, "chef").id]})
    g.advance()
    g.nominate(by(g, "chef").id, by(g, "saint").id)
    g.advance()
    for p in g.alive():
        if g.phase == "vote":
            g.vote(p.id, True)
    g.advance()
    assert g.winner == "evil"


def test_virgin_executes_townsfolk_nominator():
    g = rigged(["imp", "poisoner", "virgin", "empath", "chef", "monk", "butler"])
    finish_night(g, {"poisoner": [by(g, "butler").id]})
    g.advance()
    chef = by(g, "chef")
    g.nominate(chef.id, by(g, "virgin").id)
    assert not chef.alive
    assert g.phase == "night"
    assert g.executed_today == chef.id


def test_virgin_ignores_outsider_and_is_used_up():
    g = rigged(["imp", "poisoner", "virgin", "empath", "chef", "monk", "butler"])
    finish_night(g, {"poisoner": [by(g, "chef").id]})
    g.advance()
    g.nominate(by(g, "butler").id, by(g, "virgin").id)
    assert g.phase == "defense"
    assert by(g, "butler").alive


def test_slayer_kills_demon_only_for_real_slayer():
    g = rigged(["imp", "poisoner", "slayer", "empath", "chef", "monk"])
    finish_night(g, {"poisoner": [by(g, "chef").id]})
    g.slayer_claim(by(g, "empath").id, by(g, "imp").id)   # a bluff: nothing
    assert by(g, "imp").alive
    g.slayer_claim(by(g, "slayer").id, by(g, "imp").id)
    assert g.winner == "good"


def test_mayor_win():
    g = rigged(["imp", "poisoner", "mayor", "empath", "chef"])
    finish_night(g, {"poisoner": [by(g, "chef").id]})
    g.advance()
    g.nominate(by(g, "chef").id, by(g, "empath").id)
    g.advance()
    for p in g.alive():
        if g.phase == "vote":
            g.vote(p.id, True)
    g.advance()  # empath executed; 4 alive
    finish_night(g, {"imp": [by(g, "chef").id], "poisoner": [by(g, "poisoner").id]})
    assert len(g.alive()) == 3
    g.advance(); g.advance()  # no execution
    assert g.winner == "good"


def test_butler_vote_needs_master():
    g = rigged(["imp", "poisoner", "butler", "empath", "chef", "monk", "virgin"])
    butler, chef = by(g, "butler"), by(g, "chef")
    finish_night(g, {"butler": [chef.id], "poisoner": [by(g, "monk").id]})
    g.advance()
    g.nominate(by(g, "empath").id, by(g, "imp").id)
    g.advance()
    assert g.edition.count_votes(g, {butler.id: True, chef.id: False}) == 0
    assert g.edition.count_votes(g, {butler.id: True, chef.id: True}) == 2


def test_empath_and_chef_info():
    # Seats: imp, poisoner next to each other = 1 evil pair.
    g = rigged(["imp", "poisoner", "chef", "empath", "monk", "soldier", "virgin"])
    finish_night(g, {"poisoner": [by(g, "monk").id]})
    chef, empath = by(g, "chef"), by(g, "empath")
    assert any("1 pair" in e["text"] for e in chef.log)
    assert any("0 of your alive neighbours" in e["text"] for e in empath.log)


def test_drunk_sees_townsfolk_and_gets_false_chef_info():
    g = rigged(["imp", "poisoner", "drunk", "empath", "monk", "soldier", "virgin"], shown={2: "chef"})
    finish_night(g, {"poisoner": [by(g, "monk").id]})
    drunk = by(g, "drunk")
    assert drunk.shown == "chef"
    assert not any("1 pair" in e["text"] for e in drunk.log)
    assert any("pair" in e["text"] for e in drunk.log)


def test_fortune_teller_red_herring():
    g = rigged(["imp", "poisoner", "fortuneteller", "empath", "monk", "soldier", "virgin"])
    herring = g.p(g.estate["red_herring"])
    ft = by(g, "fortuneteller")
    finish_night(g, {"fortuneteller": [herring.id, ft.id], "poisoner": [by(g, "monk").id]})
    assert any("YES" in e["text"] for e in ft.log)


def test_night_hides_deaths_until_dawn():
    g = rigged(["imp", "poisoner", "monk", "empath", "chef", "soldier", "virgin"])
    finish_night(g)
    g.advance(); g.advance()
    chef = by(g, "chef")
    # stage A only
    for p in g.seated():
        for t in p.tasks:
            resp = [chef.id] if t["key"] == "imp" else (
                t["candidates"][:t["pick"]] if t["kind"] == "choose" else (
                    t["options"][0] if t["kind"] == "decoy" else True))
            if t["key"] == "monk":
                resp = [by(g, "soldier").id]
            if t["key"] == "poisoner":
                resp = [by(g, "virgin").id]
            g.submit_task(p.id, t["id"], resp)
    g.advance()
    assert g.stage == "B" and not chef.alive
    other = by(g, "virgin")
    seen = {p["id"]: p["alive"] for p in g.view_for(other.id)["players"]}
    assert seen[chef.id] is True


# Human storyteller mode -------------------------------------------------------

def human_lobby(n: int, seed: int = 1) -> tuple[Game, str]:
    g = Game("TEST", seed=seed)
    g.set_room("circle", seats=max(n, 5))
    st = g.join("Storyteller", is_host=True)
    g.set_mode("human")
    for i in range(n):
        p = g.join(NAMES[i])
        g.claim_seat(p.id, i)
    return g, st.id


def test_human_mode_setup_and_review():
    g, st = human_lobby(7)
    with pytest.raises(GameError):
        g.claim_seat(st, 6)
    g.start()
    assert g.phase == "setup"
    assert g.p(st).role is None and len(g.seated()) == 7
    a = g.seated()[0]
    assert g.view_for(a.id)["me"]["role"] is None       # hidden until the storyteller begins
    assert "st" in g.view_for(st) and "st" not in g.view_for(a.id)
    g.set_character(a.id, "drunk", "chef")
    g.set_character(g.seated()[1].id, "chef")
    assert a.role == "drunk" and a.shown == "chef"
    g.st_set("bluffs", ["mayor", "soldier", "monk"])
    g.begin_game()
    assert g.phase == "night" and g.view_for(a.id)["me"]["role"]["id"] == "chef"
    for p in g.seated():
        for t in p.tasks:
            resp = (t["candidates"][:t["pick"]] if t["kind"] == "choose"
                    else t["options"][0] if t["kind"] == "decoy" else True)
            g.submit_task(p.id, t["id"], resp)
    g.advance()
    assert g.stage == "review" and g.deadline is None
    assert not g.tick(time.time() + 10_000)                # no timer while reviewing
    pend = g.view_for(st)["st"]["pending"]
    chef_msg = next(m for m in pend if m["pid"] == a.id)
    g.edit_pending(a.id, chef_msg["index"], ["There are 3 pairs of evil players."])
    g.add_pending(g.seated()[2].id, "You feel watched.")
    g.send_pending()
    assert g.stage == "B"
    assert any("3 pairs" in e["text"] for e in a.log)
    assert any("watched" in e["text"] for e in g.seated()[2].log)


def test_storyteller_powers():
    g, st = human_lobby(5)
    g.start(); g.begin_game()
    while g.phase == "night":
        for p in g.seated():
            for t in p.tasks:
                resp = (t["candidates"][:t["pick"]] if t["kind"] == "choose"
                        else t["options"][0] if t["kind"] == "decoy" else True)
                g.submit_task(p.id, t["id"], resp)
        g.advance()
    victim = g.seated()[3]
    g.st_kill(victim.id)
    assert not victim.alive
    g.st_revive(victim.id)
    assert victim.alive
    g.st_message(victim.id, "Hello")
    assert victim.log[-1]["text"] == "Hello"
    with pytest.raises(GameError):
        g.vote(st, True)
    g.st_win("evil", "Test")
    assert g.phase == "ended" and g.winner == "evil"


def test_auto_mode_rejects_storyteller_actions():
    g = lobby(5)
    g.start()
    with pytest.raises(GameError):
        g.st_kill(g.seated()[1].id)
