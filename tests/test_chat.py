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
