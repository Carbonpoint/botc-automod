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
        agents.act(g, clock.t, rng, speak=lambda pid, reason, text: (said.append(text), agents._post(g, pid, text, clock.t)))
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
