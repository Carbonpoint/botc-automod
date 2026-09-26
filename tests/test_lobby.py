"""Rejoining, leaving and karma."""

import pytest

from botc_automod.game import Game, GameError, NameTaken


def lobby(n=5):
    g = Game("TEST", seed=2)
    g.set_room("circle", seats=8)
    ps = [g.join(f"P{i}", is_host=(i == 0)) for i in range(n)]
    for i, p in enumerate(ps):
        g.claim_seat(p.id, i)
    return g, ps


def test_rejoin_in_lobby_keeps_seat_and_gives_new_token():
    g, ps = lobby()
    old = ps[2].token
    with pytest.raises(NameTaken):
        g.join("p2")
    kind, token = g.rejoin("p2")
    assert kind == "token" and token != old and ps[2].token == token and ps[2].seat == 2


def test_rejoin_refused_while_connected():
    g, ps = lobby()
    ps[1].connected = True
    with pytest.raises(GameError):
        g.rejoin("P1")


def test_rejoin_in_game_needs_approval():
    g, ps = lobby()
    g.start()
    kind, rid = g.rejoin("P3")
    assert kind == "pending"
    assert g.rejoin_status(rid) == {"status": "pending"}
    assert [r["name"] for r in g.view_for(ps[0].id)["rejoins"]] == ["P3"]   # the host sees it
    assert g.view_for(ps[1].id)["rejoins"] == []                          # other players do not
    g.answer_rejoin(rid, True)
    out = g.rejoin_status(rid)
    assert out["status"] == "approved" and out["token"] == ps[3].token


def test_leave_frees_the_name_in_the_lobby():
    g, ps = lobby()
    g.leave(ps[4].id)
    assert ps[4].id not in g.players
    g.join("P4")


def test_karma_for_the_scored_night_question():
    g, ps = lobby()
    g.start()
    while g.stage == "A":
        for p in g.seated():
            for t in p.tasks:
                if not t["done"]:
                    r = (t["candidates"][:t["pick"]] if t["kind"] == "choose"
                         else t["options"][0] if t["kind"] == "decoy" else True)
                    g.submit_task(p.id, t["id"], r)
        g.advance()
    for p in g.seated():
        scored = [t for t in p.tasks if t.get("scored")]
        assert len(scored) == 1                     # exactly one scored question each
        for t in p.tasks:
            if t["kind"] == "choose":
                g.submit_task(p.id, t["id"], t["candidates"][:t["pick"]])
            elif t["kind"] == "info":
                g.submit_task(p.id, t["id"], True)
        q = scored[0]
        right = p is ps[0]
        g.submit_task(p.id, q["id"], q["answer"] if right else next(o for o in q["options"] if o != q["answer"]))
        assert p.karma == (1 if right else -1)
        assert g.view_for(p.id)["me"]["last_answer"] == ("right" if right else "wrong")
    assert "answer" not in (g.view_for(ps[0].id)["task"] or {})


def test_karma_tilts_bad_luck():
    g, ps = lobby()
    g.start()
    R = g.edition
    ps[1].karma, ps[2].karma = 10, -10
    hits = [R.pick_victim(g, [ps[1], ps[2]]).id for _ in range(2000)]
    assert hits.count(ps[2].id) > 3 * hits.count(ps[1].id)
    g.set_setting("karma", 0)
    assert R.favor(g, ps[1]) == 1.0
