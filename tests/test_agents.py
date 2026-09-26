"""Agents: computer players in empty seats."""

import random

import pytest

from botc_automod import agents
from botc_automod.game import Game, GameError


def table(n_seats=8, edition="tb", mode="auto"):
    g = Game("TEST", edition_id=edition, seed=1)
    g.set_room("circle", seats=n_seats)
    host = g.join("Hana", is_host=True)
    if mode == "human":
        g.set_mode("human")
    else:
        g.claim_seat(host.id, 0)
    g.fill_with_agents()
    return g, host


def test_fill_and_flag():
    g, host = table()
    ags = [p for p in g.players.values() if p.agent]
    assert len(ags) == 7 and len({p.seat for p in ags}) == 7
    assert all(x["agent"] for x in g.view_for(host.id)["players"] if x["id"] != host.id)
    with pytest.raises(GameError, match="no empty seat"):
        g.add_agent()
    with pytest.raises(GameError, match="agent"):
        g.rejoin(ags[0].name)                   # nobody can take over an agent
    g.kick(ags[0].id)
    assert g.add_agent().seat == ags[0].seat


def test_evil_agent_never_targets_its_team():
    g, host = table()
    g.start()
    R = g.edition
    demon = next(p for p in g.seated() if R.type_of(p.role) == "demon")
    if not demon.agent:
        pytest.skip("the human drew the Demon")
    task = {"kind": "choose", "key": demon.role, "candidates": [p.id for p in g.seated()], "pick": 1}
    rng = random.Random(1)
    for _ in range(200):
        pick = g.p(agents._answer(g, demon, task, rng)[0])
        assert R.alignment(pick) == "good"


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.mark.parametrize("edition", ["tb", "bmr", "snv"])
@pytest.mark.parametrize("seed", range(3))
@pytest.mark.parametrize("mode", ["auto", "human"])
def test_one_human_and_agents_finish_a_game(monkeypatch, edition, seed, mode):
    clock = Clock(1_000_000.0)
    monkeypatch.setattr("time.time", clock)
    g, host = table(8, edition, mode)
    g.settings["narrator"] = 1
    g.start()
    rng = random.Random(seed)
    said = []
    for _ in range(40_000):                      # 20,000 game seconds at most
        if g.phase == "ended":
            break
        clock.t += 0.5
        if mode == "human":                      # the storyteller only confirms
            if g.phase == "setup":
                g.begin_game()
            elif g.phase == "night" and g.stage in ("review", "review_b"):
                g.send_pending()
        n = g.estate.get("narration")
        if g.stage == "narration" and n and not g.p(n["pid"]).agent and clock.t % 10 == 0:
            g.finish_narration(n["pid"])         # the human narrator taps done
        g.tick(clock.t)
        agents.act(g, clock.t, rng, speak=lambda pid, reason, text, to=None: (said.append(text), agents._post(g, pid, text, clock.t, to)))
    assert g.phase == "ended", f"stuck in {g.phase}/{g.stage} day {g.day}"
    assert said                                 # the agents talked
    assert g.estate.get("chat")


def test_teams_win_about_equally(monkeypatch):
    clock = Clock(1_000_000.0)
    monkeypatch.setattr("time.time", clock)
    wins = {"good": 0, "evil": 0}
    for seed in range(30):
        g = Game("T", edition_id=("tb", "bmr", "snv")[seed % 3], seed=seed)
        g.set_room("circle", seats=7 + seed % 4)
        h = g.join("Hana", is_host=True)
        g.claim_seat(h.id, 0)
        g.fill_with_agents()
        g.start()
        rng = random.Random(seed)
        for _ in range(40_000):
            if g.phase == "ended":
                break
            clock.t += 0.5
            if g.stage == "narration":
                g.finish_narration(g.estate["narration"]["pid"])
            g.tick(clock.t)
            agents.act(g, clock.t, rng)
        wins[g.winner] += 1
    assert 0.25 <= wins["good"] / 30 <= 0.75, wins


# Chat replies ------------------------------------------------------------------------------
def chat_day(monkeypatch):
    clock = Clock(1_000_000.0)
    monkeypatch.setattr("time.time", clock)
    g, host = table()
    g.settings["narrator"] = 0
    g.start()
    rng = random.Random(3)
    while g.phase != "day":
        clock.t += 0.5
        g.tick(clock.t)
        agents.act(g, clock.t, rng)
    for p in agents.agents(g):
        agents._mem(g, p)["claimed_day"] = g.day                 # no claims: only replies in the chat below
    return g, host, clock, rng


def run(g, clock, rng, seconds=10):
    for _ in range(int(seconds * 2)):
        clock.t += 0.5
        agents.act(g, clock.t, rng)


def test_named_agent_answers_its_claim(monkeypatch):
    g, host, clock, rng = chat_day(monkeypatch)
    ada = next(p for p in g.seated() if p.agent)
    q = g.send_chat(host.id, f"{ada.name}, what's your character?", now=clock.t)
    run(g, clock, rng)
    out = [m for m in g.estate["chat"] if m["from"] == ada.id and m["id"] > q["id"]]
    assert len(out) == 1 and out[0]["text"] == f"I'm the {agents._claim(g, ada, rng)}." and out[0]["to"] is None


def test_private_message_gets_a_private_answer(monkeypatch):
    g, host, clock, rng = chat_day(monkeypatch)
    ag = next(p for p in g.seated() if p.agent)
    q = g.send_chat(host.id, "hey, who do you suspect?", to=ag.id, now=clock.t)
    run(g, clock, rng)
    out = [m for m in g.estate["chat"] if m["from"] == ag.id and m["id"] > q["id"]]
    assert len(out) == 1 and out[0]["to"] == host.id


def test_question_to_the_town_gets_one_or_two_answers(monkeypatch):
    g, host, clock, rng = chat_day(monkeypatch)
    q = g.send_chat(host.id, "Anyone learn anything last night?", now=clock.t)
    after = lambda: [m for m in g.estate["chat"] if m["id"] > q["id"]]
    run(g, clock, rng, 1)
    assert not after()                          # not at once
    run(g, clock, rng)
    assert 1 <= len(after()) <= 2


def test_evil_agent_never_suspects_its_team(monkeypatch):
    g, host, clock, rng = chat_day(monkeypatch)
    evil = next(p for p in g.seated() if p.agent and agents._evil(g, p))
    for i in range(30):
        m = {"text": "who do you suspect?", "to": evil.id, "from": host.id}
        text = agents._reply_text(g, evil, m, rng)
        named = [x for x in g.seated() if x.name in text]
        assert all(not agents._evil(g, x) for x in named), text


def test_no_answers_at_night(monkeypatch):
    g, host, clock, rng = chat_day(monkeypatch)
    ag = next(p for p in g.seated() if p.agent)
    q = g.send_chat(host.id, f"{ag.name}?", now=clock.t)
    agents.act(g, clock.t, rng)
    assert g.estate["agent_replies"]            # queued, not sent yet
    while g.phase != "night":
        g.advance()
    run(g, clock, rng, 10)
    assert not g.estate["agent_replies"]
    assert not [m for m in g.estate["chat"] if m["id"] > q["id"]]


def test_llm_check_drops_evil_names_from_evil_agents():
    g, host = table()
    g.start()
    R = g.edition
    evil = next(p for p in g.seated() if p.agent and agents._evil(g, p))
    good = next(p for p in g.seated() if p.agent and not agents._evil(g, p))
    demon = next(p for p in g.seated() if R.type_of(p.role) == "demon")
    leak = f"Basil is a monk, {demon.name} is an {R.roles[demon.role].name.lower()}."
    assert agents.llm_check(g, evil, leak) is None
    assert agents.llm_check(g, evil, "I'm not the Demon, promise.") == "I'm not the Demon, promise."
    mate = next(p for p in g.seated() if agents._evil(g, p) and p is not evil)
    assert agents.llm_check(g, evil, f"I think the evil ones are {mate.name} and me.") is None
    assert agents.llm_check(g, evil, f"Leave {mate.name} alone.") is None
    assert agents.llm_check(g, evil, "I'll stay quiet about my real identity.") is None
    assert agents.llm_check(g, evil, "Hana’s right, I'm not trustworthy.") is None
    assert agents.llm_check(g, good, "I think the Demon is hiding.") is not None


def test_model_reply_to_a_private_message_stays_private(monkeypatch):
    import asyncio

    from botc_automod import server

    class Fake:
        can_chat = True

        def chat(self, system, user):
            assert 'sent you a private message: "who is evil?"' in user
            return "No idea yet, honestly."

    g, host = table()
    g.settings["narrator"] = 0
    g.start()
    while g.phase != "day":
        g.advance()
    ag = next(p for p in g.seated() if p.agent and not agents._evil(g, p))
    monkeypatch.setattr(server, "CHAT", Fake())
    monkeypatch.setitem(server.games, g.code, g)
    g.helper_llm = True
    g.send_chat(host.id, "who is evil?", to=ag.id)

    async def go():
        server.agent_speak(g, ag.id, f'{host.name} sent you a private message: "who is evil?". Answer them.',
                           "fallback", host.id)
        for _ in range(100):
            await asyncio.sleep(0.01)
            if any(m["from"] == ag.id for m in g.estate["chat"]):
                return
    asyncio.run(go())
    out = [m for m in g.estate["chat"] if m["from"] == ag.id]
    assert [(m["text"], m["to"]) for m in out] == [("No idea yet, honestly.", host.id)]


def test_model_talk_queue_puts_replies_first_and_skips_stale_talk(monkeypatch):
    import asyncio

    from botc_automod import server

    order = []

    class Slow:
        can_chat = True

        def chat(self, system, user):
            order.append(user.splitlines()[-1])
            return "Model words."

    g, host = table()
    g.settings["narrator"] = 0
    g.start()
    while g.phase != "day":
        g.advance()
    ags = agents.agents(g)
    monkeypatch.setattr(server, "CHAT", Slow())
    monkeypatch.setitem(server.games, g.code, g)
    g.helper_llm = True

    async def go():
        server.agent_speak(g, ags[0].id, "Tell the town your character is the Chef.", "claim 0")
        server.agent_speak(g, ags[1].id, "Tell the town your character is the Monk.", "claim 1")
        server.agent_speak(g, ags[2].id, f'Hana said in the group chat: "hi?". {agents.ANSWER}', "reply")
        stale = [i for i, item in enumerate(server._talk["queue"]._queue) if item[3][3] == "claim 1"][0]
        item = server._talk["queue"]._queue[stale]
        server._talk["queue"]._queue[stale] = (item[0], item[1], item[2] - 60, item[3])   # waited a minute
        for _ in range(200):
            await asyncio.sleep(0.01)
            if server._talk["queue"].empty() and len([m for m in g.estate["chat"] if m["from"] in
                                                      {a.id for a in ags[:3]}]) >= 3:
                break
    asyncio.run(go())
    assert order[0].endswith(agents.ANSWER)                 # the reply went first
    said = {m["from"]: m["text"] for m in g.estate["chat"] if m["from"] in {a.id for a in ags[:3]}}
    assert said[ags[2].id] == "Model words." and said[ags[1].id] == "claim 1"
