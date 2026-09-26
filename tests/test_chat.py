"""Chat: group and private messages."""

import pytest
from test_engine import lobby

from botc_automod.game import GameError


def day_game():
    g = lobby(5)
    g.start()
    while g.phase != "day":
        g.advance()
    return g, g.seated()


def test_group_and_private_messages():
    g, ps = day_game()
    a, b, c = ps[0], ps[1], ps[2]
    g.send_chat(a.id, "Hello town", now=1)
    g.send_chat(a.id, "Psst, I am the Chef", to=b.id, now=3)
    assert [m["text"] for m in g.view_for(b.id)["chat"]] == ["Hello town", "Psst, I am the Chef"]
    assert [m["text"] for m in g.view_for(c.id)["chat"]] == ["Hello town"]
    assert [m["text"] for m in g.view_for(a.id)["chat"]] == ["Hello town", "Psst, I am the Chef"]


def test_limits():
    g, ps = day_game()
    a, b = ps[0], ps[1]
    with pytest.raises(GameError):
        g.send_chat(a.id, "   ", now=1)
    with pytest.raises(GameError):
        g.send_chat(a.id, "me again", to=a.id, now=1)
    g.send_chat(a.id, "x" * 1000, now=1)
    assert len(g.estate["chat"][-1]["text"]) == g.CHAT_TEXT
    with pytest.raises(GameError, match="Slow down"):
        g.send_chat(a.id, "too fast", now=1.5)
    g.send_chat(b.id, "fine", now=1.5)          # the limit is per player


def test_closed_at_night():
    g, ps = day_game()
    while g.phase != "night":
        g.advance()
    with pytest.raises(GameError, match="night"):
        g.send_chat(ps[0].id, "anyone awake?")


def test_anonymous_messages_hide_the_sender():
    g, ps = day_game()
    a, b, c = ps[0], ps[1], ps[2]
    with pytest.raises(GameError, match="turned off"):
        g.send_chat(a.id, "boo", anon=True, now=1)
    g.set_setting("anon_chat", 1)
    g.send_chat(a.id, "someone here is lying", anon=True, now=2)
    g.send_chat(a.id, "watch your back", to=b.id, anon=True, now=4)
    for viewer in (b, c):
        for m in g.view_for(viewer.id)["chat"]:
            assert m["from"] is None and m["anon"]
    assert all(m["from"] == a.id for m in g.view_for(a.id)["chat"])   # the sender sees their own
    assert [m["text"] for m in g.view_for(c.id)["chat"]] == ["someone here is lying"]
    assert g.estate["chat"][0]["from"] == a.id                        # the server still knows


def test_keywords_never_travel_through_chat():
    g, ps = day_game()
    g.estate["irl"] = {"day": g.day, "words": {ps[0].id: "lantern"}}
    g.send_chat(ps[1].id, "Her word is Lantern, trust me", now=1)
    assert g.estate["chat"][-1]["text"] == "Her word is •••, trust me"


@pytest.mark.parametrize("show", [0, 1])
def test_show_votes_on_seats(show):
    g, ps = day_game()
    g.set_setting("show_votes", show)
    while g.phase != "nominations":
        g.advance()
    g.nominate(ps[0].id, ps[1].id)
    g.advance()   # defence -> vote
    assert g.phase == "vote"
    g.vote(ps[2].id, True)
    g.vote(ps[3].id, False)
    cur = g.view_for(ps[4].id)["day"]["current"]
    if show:
        assert cur["votes"] == {ps[2].id: True, ps[3].id: False}
    else:
        assert "votes" not in cur
