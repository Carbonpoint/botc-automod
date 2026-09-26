"""Karma arcade: daily karma, boards, score checks and the shared pool table."""

import math

import pytest

from botc_automod import arcade
from botc_automod.arcade import Arcade, ArcadeError


def test_first_real_game_of_the_day_and_records_give_karma(tmp_path):
    a = Arcade(tmp_path / "arcade.json")
    r = a.submit("Ana", "snake", 2, 30)      # below a real try, but a record
    assert r["record"] and r["karma"] == 1 and r["why"] == ["new record"]
    r = a.submit("Ana", "snake", 6, 30)      # first real try today, and a new record
    assert r["karma"] == 2
    r = a.submit("Ana", "snake", 7, 30)      # a record again, but the daily cap (3) is reached
    assert r["record"] and r["karma"] == 0 and r["today"] == arcade.DAILY_CAP
    r = a.submit("Bo", "snake", 5, 30)       # not a record: only the first-game karma
    assert r["karma"] == 1 and not r["record"]


def test_board_keeps_one_best_score_per_name_and_survives_a_restart(tmp_path):
    a = Arcade(tmp_path / "arcade.json")
    a.submit("Ana", "flappy", 5, 30)
    a.submit("ana", "flappy", 3, 30)
    a.submit("Bo", "flappy", 9, 30)
    b = Arcade(tmp_path / "arcade.json")
    assert [(e["name"], e["score"]) for e in b.boards["flappy"]] == [("Bo", 9), ("Ana", 5)]
    assert b.summary("ANA")["today"] == a.summary("Ana")["today"]


def test_the_daily_cap_resets_on_a_new_day(tmp_path, monkeypatch):
    a = Arcade(tmp_path / "arcade.json")
    for s in (10, 20, 30):
        a.submit("Ana", "snake", s, 60)
    assert a.summary("Ana")["today"] == 3
    monkeypatch.setattr(arcade, "today", lambda: "2099-01-01")
    assert a.submit("Ana", "snake", 40, 60)["karma"] == 2


@pytest.mark.parametrize("game,score,secs", [("flappy", 100, 10), ("snake", 5, 0), ("snake", -1, 10), ("nope", 1, 1)])
def test_impossible_scores_are_refused(tmp_path, game, score, secs):
    with pytest.raises(ArcadeError):
        Arcade(tmp_path / "a.json").submit("Ana", game, score, secs)


def test_a_name_is_needed(tmp_path):
    with pytest.raises(ArcadeError):
        Arcade(tmp_path / "a.json").submit("  ", "snake", 5, 10)


def test_pool_shot_pockets_a_ball_and_scores(tmp_path):
    a = Arcade(tmp_path / "a.json")
    balls = [None] * 16
    balls[0] = [50.0, 25.0]
    balls[5] = [90.0, 45.0]                 # near the bottom-right pocket (100, 50)
    a.pool.balls = balls
    angle = math.atan2(45 - 25, 90 - 50)
    r = a.shoot("Ana", 0, angle, 0.6)
    assert r["points"] == 1 and 5 in r["pool"]["pocketed"]
    assert a.pool_points["ana"] == 1 and a.pool.version == 1
    # The last ball went down: a new rack.
    assert sum(b is not None for b in a.pool.balls) == 16 and a.pool.racks == 1


def test_pool_shots_take_turns_and_need_the_current_table(tmp_path):
    a = Arcade(tmp_path / "a.json")
    a.shoot("Ana", 0, 0.0, 0.3)
    with pytest.raises(ArcadeError, match="Someone shot first"):
        a.shoot("Bo", 0, 0.0, 0.3)
    with pytest.raises(ArcadeError, match="Let someone else"):
        a.shoot("Ana", 1, 0.0, 0.3)
    a.shoot("Bo", 1, 3.0, 0.3)
    a.shoot("Ana", 2, 0.5, 0.3)             # someone else shot: Ana may go again


def test_sinking_the_cue_ball_costs_a_point_and_puts_it_back(tmp_path):
    a = Arcade(tmp_path / "a.json")
    balls = [None] * 16
    balls[0] = [50.0, 25.0]
    balls[3] = [20.0, 25.0]
    a.pool.balls = balls
    a.pool_points["ana"] = 2
    r = a.shoot("Ana", 0, math.atan2(-25, -50), 0.7)   # straight at the top-left pocket
    assert 0 in r["pool"]["pocketed"] and r["points"] == -1
    assert a.pool_points["ana"] == 1 and a.pool.balls[0] is not None


def test_pool_karma_every_few_balls_and_not_twice(tmp_path):
    a = Arcade(tmp_path / "a.json")
    key = "ana"
    a.pool_points[key] = arcade.POOL_PER_KARMA - 1
    balls = [None] * 16
    balls[0], balls[1], balls[2] = [50.0, 25.0], [90.0, 45.0], [10.0, 10.0]
    a.pool.balls = balls
    r = a.shoot("Ana", 0, math.atan2(20, 40), 0.6)
    assert r["karma"] == 1 and a.pool_paid[key] == 1


def test_physics_keeps_balls_on_the_table():
    end, frames, pocketed = arcade.simulate(arcade.rack(), 0.02, 1.0)
    for b in end:
        if b is not None:
            assert arcade.R - 1e-6 <= b[0] <= arcade.W - arcade.R + 1e-6
            assert arcade.R - 1e-6 <= b[1] <= arcade.H - arcade.R + 1e-6
    assert len(frames) > 2 and all(len(f) == 16 for f in frames)
