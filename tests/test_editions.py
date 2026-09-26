"""Bad Moon Rising and Sects & Violets: random full games and rule checks."""

import json
import random

import pytest

from botc_automod.editions import EDITIONS
from botc_automod.game import Game

NAMES = "Ann Ben Cat Dan Eve Fay Gus Hal Ivy Jon Kim Lee Max Ned Oli".split()


def lobby(n, edition, seed=1, mode="auto"):
    g = Game("TEST", edition_id=edition, seed=seed)
    g.set_room("circle", seats=max(n, 5))
    if mode == "human":
        g.join("Storyteller", is_host=True)
        g.set_mode("human")
    for i in range(n):
        p = g.join(NAMES[i], is_host=(mode == "auto" and i == 0))
        g.claim_seat(p.id, i)
    return g


def rigged(roles, edition, shown=None, seed=1, settings=None):
    g = lobby(len(roles), edition, seed)
    R = g.edition
    for i, (p, r) in enumerate(zip(g.seated(), roles)):
        p.role = r
        p.shown = (shown or {}).get(i, r)
        p.alignment = R.roles[r].team
    good = [p for p in g.seated() if R.roles[p.role].team == "good"]
    g.estate.update({"bluffs": [], "red_herring": good[-1].id, "status": [], "used": {}, "abnormal": []})
    for p in g.seated():
        R.chars[p.role].setup(R, g, p)
    g.settings.update({"misregister": 0.0, "mayor_bounce": 0.0, "pacifist_save": 0.0, "tinker_chance": 0.0,
                       "shabaloth_regurgitate": 0.0, **(settings or {})})
    g.begin_night()
    return g


def by(g, role):
    return next(p for p in g.seated() if p.role == role)


def answer(g, rng, picks=None):
    picks = picks or {}
    for p in g.seated():
        for t in p.tasks:
            if t["done"]:
                continue
            k = t["kind"]
            want = picks.get(t["key"])
            if want is not None:
                r = want
            elif k == "choose":
                r = [] if t.get("allow_none") and rng.random() < 0.4 else rng.sample(t["candidates"], t["pick"])
            elif k == "character":
                r = None if t.get("allow_none") and rng.random() < 0.4 else rng.choice(t["options"])["id"]
            elif k == "player_character":
                r = {"player": rng.choice(t["candidates"]), "character": rng.choice(t["options"])["id"]}
            elif k == "decoy":
                r = t["options"][0]
            else:
                r = True
            g.submit_task(p.id, t["id"], r)


def night(g, picks=None, rng=None):
    """Play the night. A Sailor drinks alone unless told otherwise, so tests stay predictable."""
    rng = rng or random.Random(0)
    picks = dict(picks or {})
    sailor = next((p for p in g.seated() if p.role == "sailor"), None)
    if sailor and "sailor" not in picks:
        picks["sailor"] = [sailor.id]
    while g.phase == "night":
        answer(g, rng, picks)
        g.advance()


def to_night(g):
    """From day: open nominations, execute nobody, go to night."""
    while g.phase in ("day", "nominations"):
        g.advance()


def execute(g, target, nominator=None):
    if g.phase == "day":
        g.advance()
    nom = nominator or next(p for p in g.seated() if g.living(p) and p.id not in g.nominators_today
                            and p is not target)
    g.nominate(nom.id, target.id)
    if g.phase == "defense":
        g.advance()
        for v in g.seated():
            if g.phase == "vote" and g.can_vote(v):
                g.vote(v.id, True)
        if g.phase == "vote":
            g.advance()
    if g.phase == "nominations":
        g.advance()


def payload_for(g, rng, action):
    kind = action["kind"]
    alive = [p.id for p in g.seated() if g.living(p)]
    roles = list(g.edition.roles)
    if kind == "target":
        return {"target": rng.choice(action.get("candidates") or alive)}
    if kind in ("statement", "question"):
        return {"kind": rng.choice(["is_evil", "is_role", "in_play", "is_type"]),
                "player": rng.choice(alive), "role": rng.choice(roles), "type": "demon"}
    if kind == "guesses":
        return {"guesses": [{"player": rng.choice(alive), "character": rng.choice(roles)} for _ in range(3)]}
    return {}


def play(g, rng, steps=500):
    for _ in range(steps):
        if g.phase == "ended":
            return
        for p in g.seated():  # views must always build and serialise
            json.dumps(g.view_for(p.id))
        if g.phase == "setup":
            g.begin_game()
        elif g.phase == "night":
            answer(g, rng)
            g.advance()
        elif g.phase in ("day", "nominations"):
            for p in g.seated():
                for a in g.edition.day_actions(g, p):
                    if (a.get("forced") or rng.random() < 0.15) and g.phase in ("day", "nominations"):
                        g.day_action(p.id, a["key"], payload_for(g, rng, a))
            if g.phase == "ended":
                return
            if g.phase == "nominations":
                noms = [p for p in g.seated() if g.living(p) and p.id not in g.nominators_today]
                free = [p for p in g.seated() if p.id not in g.nominees_today]
                if noms and free and rng.random() < 0.8:
                    g.nominate(rng.choice(noms).id, rng.choice(free).id)
                    if g.phase == "defense":
                        g.advance()
                        for v in g.seated():
                            if g.phase == "vote" and g.can_vote(v):
                                g.vote(v.id, rng.random() < 0.6)
                        if g.phase == "vote":
                            g.advance()
                    continue
            g.advance()
        else:
            g.advance()


@pytest.mark.parametrize("edition", ["tb", "bmr", "snv"])
@pytest.mark.parametrize("seed", range(40))
def test_random_games_finish(edition, seed):
    rng = random.Random(seed)
    n = rng.randint(5, 15)
    mode = "human" if seed % 4 == 0 else "auto"
    g = lobby(n, edition, seed, mode)
    g.settings.update({"misregister": 0.5, "tinker_chance": 0.2, "pacifist_save": 0.5,
                       "shabaloth_regurgitate": 0.5})
    g.start()
    play(g, rng)
    assert g.phase == "ended", f"stuck in {g.phase} {g.stage} day {g.day}"
    assert g.winner in ("good", "evil")
    for p in g.seated():
        v = g.view_for(p.id)
        assert len(v["grimoire"]) == n


@pytest.mark.parametrize("edition", ["bmr", "snv"])
def test_setup_counts(edition):
    R = EDITIONS[edition]
    for seed in range(60):
        for mode in ("auto", "human"):
            g = lobby(9, edition, seed, mode)
            g.start()
            roles = [p.role for p in g.seated()]
            assert len(set(roles)) == 9
            assert sum(R.type_of(r) == "demon" for r in roles) == 1
            assert sum(R.type_of(r) == "minion" for r in roles) == 1
            if mode == "auto":
                assert not {"mutant", "cerenovus"} & set(roles)
            lun = next((p for p in g.seated() if p.role == "lunatic"), None)
            if lun:
                assert R.type_of(lun.shown) == "demon"


def test_views_hide_roles():
    g = lobby(9, "snv", 3)
    g.start()
    for p in g.seated():
        text = json.dumps(g.view_for(p.id)["players"])
        assert all(q.role not in text for q in g.seated())


# Bad Moon Rising rules ---------------------------------------------------------------------------

BMR7 = ["pukka", "godfather", "chambermaid", "gambler", "innkeeper", "tealady", "fool"]


def test_pukka_poisons_then_kills():
    g = rigged(BMR7, "bmr")
    R = g.edition
    gambler, cm = by(g, "gambler"), by(g, "chambermaid")
    night(g, {"pukka": [gambler.id]})
    assert gambler.alive and R.malfunction(g, gambler)
    to_night(g)
    night(g, {"pukka": [cm.id], "innkeeper": [by(g, "fool").id, by(g, "tealady").id],
              "gambler": {"player": by(g, "pukka").id, "character": "pukka"}})
    assert not gambler.alive
    assert cm.alive and R.malfunction(g, cm)


def test_po_charges_to_three():
    g = rigged(["po", "assassin", "chambermaid", "gambler", "innkeeper", "sailor", "fool"], "bmr")
    ids = lambda *r: [by(g, x).id for x in r]
    night(g)
    to_night(g)
    night(g, {"po": [], "assassin": [], "innkeeper": ids("sailor", "fool"),
              "gambler": {"player": by(g, "po").id, "character": "po"}})
    assert all(p.alive for p in g.seated())
    to_night(g)
    task = next(t for t in by(g, "po").tasks if t["key"] == "po")
    assert task["pick"] == 3
    night(g, {"po": ids("chambermaid", "gambler", "innkeeper"), "assassin": [],
              "innkeeper": ids("sailor", "fool"), "gambler": {"player": by(g, "po").id, "character": "po"}})
    assert not any(by(g, r).alive for r in ("chambermaid", "gambler", "innkeeper"))


def test_zombuul_fakes_first_death():
    g = rigged(["zombuul", "godfather", "gambler", "chambermaid", "sailor", "exorcist", "innkeeper"], "bmr")
    z = by(g, "zombuul")
    night(g)
    execute(g, z)
    assert z.alive and z.fake_dead and g.phase == "night"
    other = by(g, "gambler")
    assert {p["id"]: p["alive"] for p in g.view_for(other.id)["players"]}[z.id] is False
    assert not any(t["key"] == "zombuul" for t in z.tasks)  # someone died today
    night(g, {"exorcist": [by(g, "sailor").id], "gambler": {"player": z.id, "character": "zombuul"},
              "innkeeper": [by(g, "sailor").id, by(g, "exorcist").id]})
    execute(g, z)
    assert not z.alive and g.winner == "good"


def test_fool_survives_once():
    g = rigged(["shabaloth", "godfather", "fool", "gambler", "innkeeper", "sailor", "exorcist"], "bmr")
    fool, gam = by(g, "fool"), by(g, "gambler")
    night(g)
    to_night(g)
    night(g, {"shabaloth": [fool.id, gam.id], "exorcist": [by(g, "sailor").id],
              "innkeeper": [by(g, "sailor").id, by(g, "exorcist").id],
              "gambler": {"player": gam.id, "character": "gambler"}})
    assert fool.alive and not gam.alive


def test_tea_lady_protects_good_neighbours():
    g = rigged(["po", "godfather", "gambler", "tealady", "chambermaid", "sailor", "exorcist"], "bmr")
    cm = by(g, "chambermaid")
    night(g)
    to_night(g)
    night(g, {"po": [cm.id], "exorcist": [by(g, "sailor").id],
              "gambler": {"player": by(g, "gambler").id, "character": "gambler"}})
    assert cm.alive


def test_exorcist_stops_demon_and_tells_it():
    g = rigged(["po", "godfather", "gambler", "exorcist", "chambermaid", "sailor", "innkeeper"], "bmr")
    po, cm = by(g, "po"), by(g, "chambermaid")
    night(g)
    to_night(g)
    night(g, {"po": [cm.id], "exorcist": [po.id], "innkeeper": [by(g, "sailor").id, by(g, "gambler").id],
              "gambler": {"player": by(g, "gambler").id, "character": "gambler"}})
    assert cm.alive
    assert any("Exorcist" in e["text"] for e in po.log)
    assert not g.estate.get("po_charged", {}).get(po.id)


def test_gambler_dies_on_wrong_guess():
    g = rigged(BMR7, "bmr")
    gam = by(g, "gambler")
    night(g, {"pukka": [by(g, "fool").id]})
    to_night(g)
    night(g, {"pukka": [by(g, "fool").id], "innkeeper": [by(g, "fool").id, by(g, "tealady").id],
              "gambler": {"player": by(g, "pukka").id, "character": "godfather"}})
    assert not gam.alive


def test_professor_resurrects_townsfolk():
    g = rigged(["po", "godfather", "professor", "gambler", "chambermaid", "sailor", "exorcist"], "bmr")
    cm = by(g, "chambermaid")
    night(g)
    execute(g, cm)
    assert not cm.alive
    night(g, {"professor": [cm.id], "po": [], "exorcist": [by(g, "po").id],
              "gambler": {"player": by(g, "gambler").id, "character": "gambler"}})
    assert cm.alive
    assert any("alive again" in e["text"] for e in g.public_log)


def test_godfather_kills_after_outsider_dies_by_day():
    g = rigged(["po", "godfather", "tinker", "gambler", "chambermaid", "sailor", "exorcist"], "bmr")
    gf, cm = by(g, "godfather"), by(g, "chambermaid")
    night(g)
    assert any("Tinker" in e["text"] for e in gf.log)
    execute(g, by(g, "tinker"))
    assert any(t["key"] == "godfather" for t in gf.tasks)
    night(g, {"godfather": [cm.id], "po": [], "exorcist": [by(g, "po").id],
              "gambler": {"player": by(g, "gambler").id, "character": "gambler"}})
    assert not cm.alive


def test_mastermind_extra_day():
    g = rigged(["po", "mastermind", "gambler", "chambermaid", "sailor", "exorcist", "innkeeper"], "bmr")
    night(g)
    execute(g, by(g, "po"))
    assert g.phase == "night" and g.winner is None
    night(g, {"exorcist": [by(g, "sailor").id], "innkeeper": [by(g, "sailor").id, by(g, "exorcist").id],
              "gambler": {"player": by(g, "gambler").id, "character": "gambler"}})
    execute(g, by(g, "chambermaid"))
    assert g.winner == "evil"


def test_goon_drunks_first_chooser_and_turns():
    g = rigged(["po", "devilsadvocate", "goon", "gambler", "chambermaid", "sailor", "exorcist"], "bmr")
    goon, da = by(g, "goon"), by(g, "devilsadvocate")
    night(g, {"devilsadvocate": [goon.id], "sailor": [by(g, "sailor").id],
              "chambermaid": [by(g, "gambler").id, by(g, "exorcist").id]})
    assert g.edition.alignment(goon) == "evil"
    assert g.edition.malfunction(g, da)


def test_assassin_kills_through_protection():
    g = rigged(["po", "assassin", "gambler", "innkeeper", "chambermaid", "sailor", "exorcist"], "bmr")
    cm = by(g, "chambermaid")
    night(g)
    to_night(g)
    night(g, {"assassin": [cm.id], "innkeeper": [cm.id, by(g, "gambler").id], "po": [],
              "exorcist": [by(g, "po").id], "gambler": {"player": by(g, "gambler").id, "character": "gambler"}})
    assert not cm.alive


def test_lunatic_thinks_demon_and_is_reported():
    g = rigged(["zombuul", "godfather", "lunatic", "gambler", "chambermaid", "sailor", "exorcist"], "bmr",
               shown={2: "zombuul"})
    z, lun, cm = by(g, "zombuul"), by(g, "lunatic"), by(g, "chambermaid")
    assert g.view_for(lun.id)["me"]["role"]["id"] == "zombuul"
    assert g.view_for(lun.id)["me"]["team"] == "evil"
    night(g)
    assert any("Lunatic" in e["text"] for e in z.log)
    to_night(g)
    night(g, {"zombuul": [cm.id], "exorcist": [by(g, "sailor").id],
              "gambler": {"player": by(g, "gambler").id, "character": "gambler"}})
    # Both "Zombuul" choices went to the chambermaid; only the real one kills.
    assert not cm.alive
    assert any("The Lunatic" in e["text"] for e in z.log)


def test_moonchild_curse():
    g = rigged(["po", "godfather", "moonchild", "gambler", "chambermaid", "sailor", "exorcist"], "bmr")
    mc, cm = by(g, "moonchild"), by(g, "chambermaid")
    night(g)
    execute(g, mc)
    assert g.phase == "night"
    acts = g.edition.day_actions(g, mc)
    assert acts and acts[0]["key"] == "moonchild" and acts[0]["forced"]
    g.day_action(mc.id, "moonchild", {"target": cm.id})
    night(g, {"po": [], "exorcist": [by(g, "po").id],
              "gambler": {"player": by(g, "gambler").id, "character": "gambler"}})
    assert not cm.alive


def test_grandmother_dies_with_grandchild():
    g = rigged(["po", "godfather", "grandmother", "gambler", "chambermaid", "sailor", "exorcist"], "bmr")
    gm = by(g, "grandmother")
    gc = g.p(g.estate["grandchild"])
    night(g)
    assert any(gc.name in e["text"] for e in gm.log)
    to_night(g)
    if gc.role == "sailor":
        pytest.skip("the sailor cannot die")
    night(g, {"po": [gc.id], "exorcist": [by(g, "godfather").id], "sailor": [by(g, "sailor").id],
              "gambler": {"player": by(g, "gambler").id, "character": "gambler"}})
    assert not gc.alive and not gm.alive


def test_minstrel_makes_everyone_drunk():
    g = rigged(["po", "godfather", "minstrel", "gambler", "chambermaid", "sailor", "exorcist"], "bmr")
    night(g)
    execute(g, by(g, "godfather"))
    R = g.edition
    assert all(R.malfunction(g, p) for p in g.seated() if p.role != "minstrel" and p.alive)


# Sects & Violets rules --------------------------------------------------------------------------

def test_snake_charmer_swaps_with_demon():
    # Seats 1 and 6 are the No Dashii's poisoned neighbours; the Snake Charmer sits clear of them.
    g = rigged(["nodashii", "oracle", "witch", "snakecharmer", "clockmaker", "sweetheart", "juggler"], "snv")
    nd, sc = by(g, "nodashii"), by(g, "snakecharmer")
    night(g, {"snakecharmer": [nd.id], "witch": [by(g, "oracle").id]})
    assert sc.role == "nodashii" and g.edition.alignment(sc) == "evil"
    assert nd.role == "snakecharmer" and g.edition.alignment(nd) == "good"
    assert g.edition.malfunction(g, nd)


def test_fang_gu_jumps_to_outsider():
    g = rigged(["fanggu", "witch", "sweetheart", "oracle", "clockmaker", "dreamer", "juggler"], "snv")
    fg, sh = by(g, "fanggu"), next(p for p in g.seated() if p.role == "sweetheart")
    night(g)
    to_night(g)
    night(g, {"fanggu": [sh.id], "witch": [by(g, "oracle").id], "dreamer": [fg.id]})
    assert not fg.alive and sh.alive and sh.role == "fanggu" and g.edition.alignment(sh) == "evil"
    assert g.winner is None


def test_vigormortis_minion_keeps_ability():
    g = rigged(["vigormortis", "witch", "oracle", "clockmaker", "dreamer", "sweetheart", "juggler"], "snv")
    w = by(g, "witch")
    night(g)
    to_night(g)
    night(g, {"vigormortis": [w.id], "witch": [by(g, "oracle").id], "dreamer": [w.id]})
    assert not w.alive
    assert g.edition.works(g, w, "witch")
    poisoned = g.estate["vig_poison"][w.id]
    assert g.edition.malfunction(g, g.p(poisoned))
    to_night(g)
    assert any(t["key"] == "witch" for t in w.tasks)


def test_no_dashii_poisons_townsfolk_neighbours():
    g = rigged(["oracle", "nodashii", "sweetheart", "witch", "dreamer", "clockmaker", "juggler"], "snv")
    R = g.edition
    assert R.malfunction(g, by(g, "oracle"))       # clockwise neighbour
    assert R.malfunction(g, by(g, "dreamer"))      # skips the Sweetheart and the Witch
    assert not R.malfunction(g, by(g, "clockmaker"))


def test_vortox_needs_daily_execution():
    g = rigged(["vortox", "witch", "oracle", "clockmaker", "dreamer", "sweetheart", "juggler"], "snv")
    night(g)
    to_night(g)
    assert g.winner == "evil"


def test_evil_twin_blocks_good_win_and_good_twin_execution_loses():
    g = rigged(["nodashii", "eviltwin", "oracle", "clockmaker", "dreamer", "sweetheart", "juggler"], "snv")
    et, gt = g.p(g.estate["twins"][0]), g.p(g.estate["twins"][1])
    night(g)
    assert any("twin" in e["text"] for e in et.log) and any("twin" in e["text"] for e in gt.log)
    execute(g, by(g, "nodashii"))
    assert g.winner is None  # both twins live
    night(g, {"dreamer": [et.id]})
    execute(g, gt)
    assert g.winner == "evil"


def test_witch_curse_kills_nominator():
    g = rigged(["nodashii", "witch", "oracle", "clockmaker", "dreamer", "sweetheart", "juggler"], "snv")
    orc = by(g, "oracle")
    night(g, {"witch": [orc.id], "dreamer": [orc.id]})
    g.advance()
    g.nominate(orc.id, by(g, "juggler").id)
    assert not orc.alive and g.phase == "defense"


def test_klutz_choosing_evil_loses():
    g = rigged(["nodashii", "witch", "klutz", "oracle", "clockmaker", "dreamer", "juggler"], "snv")
    k = by(g, "klutz")
    night(g, {"witch": [by(g, "oracle").id]})
    execute(g, k)
    g.day_action(k.id, "klutz", {"target": by(g, "witch").id})
    assert g.winner == "evil"


def test_barber_death_lets_demon_swap():
    g = rigged(["nodashii", "witch", "barber", "oracle", "clockmaker", "dreamer", "juggler"], "snv")
    nd = by(g, "nodashii")
    night(g, {"witch": [by(g, "oracle").id]})
    execute(g, by(g, "barber"))
    a, b = by(g, "oracle"), by(g, "clockmaker")
    assert any(t["key"] == "barber" for t in nd.tasks)
    night(g, {"barber": [a.id, b.id], "nodashii": [by(g, "juggler").id], "witch": [by(g, "dreamer").id],
              "dreamer": [nd.id]})
    assert a.role == "clockmaker" and b.role == "oracle"
    assert any("You are now the Clockmaker" in e["text"] for e in a.log)


def test_philosopher_gains_ability_same_night():
    g = rigged(["nodashii", "oracle", "witch", "philosopher", "clockmaker", "sweetheart", "juggler"], "snv")
    ph = by(g, "philosopher")
    for t in ph.tasks:
        g.submit_task(ph.id, t["id"], "dreamer")
    answer(g, random.Random(1), {"witch": [by(g, "oracle").id]})
    g.advance()
    assert g.stage == "B" and any(t["key"] == "dreamer" for t in ph.tasks)
    night(g, {"dreamer": [by(g, "nodashii").id]})
    assert any("No Dashii" in e["text"] for e in ph.log)


def test_juggler_count():
    g = rigged(["nodashii", "witch", "juggler", "oracle", "clockmaker", "sweetheart", "dreamer"], "snv")
    j = by(g, "juggler")
    night(g, {"witch": [by(g, "oracle").id], "dreamer": [j.id]})
    g.day_action(j.id, "juggler", {"guesses": [{"player": by(g, "witch").id, "character": "witch"},
                                               {"player": by(g, "oracle").id, "character": "dreamer"}]})
    night_answers = {"nodashii": [by(g, "sweetheart").id], "witch": [by(g, "oracle").id],
                     "dreamer": [by(g, "witch").id]}
    to_night(g)
    night(g, night_answers)
    j_true = not g.edition.malfunction(g, j)
    if j_true:
        assert any("1 guess right" in e["text"] for e in j.log)


def test_clockmaker_and_oracle():
    g = rigged(["nodashii", "dreamer", "witch", "clockmaker", "oracle", "sweetheart", "juggler"], "snv")
    ck = by(g, "clockmaker")
    night(g, {"witch": [by(g, "juggler").id], "dreamer": [by(g, "juggler").id]})
    assert any("2 steps" in e["text"] for e in ck.log)
    execute(g, by(g, "witch"))
    orc = by(g, "oracle")
    night(g, {"nodashii": [by(g, "juggler").id], "dreamer": [by(g, "juggler").id]})
    if not g.edition.malfunction(g, orc):
        assert any("1 dead player is evil" in e["text"] for e in orc.log)


def test_savant_and_artist_auto():
    g = rigged(["nodashii", "witch", "savant", "artist", "clockmaker", "sweetheart", "juggler"], "snv")
    sv, ar = by(g, "savant"), by(g, "artist")
    night(g, {"witch": [by(g, "clockmaker").id]})
    g.day_action(sv.id, "savant", {})
    assert "One is true, one is false" in sv.log[-1]["text"]
    g.day_action(ar.id, "artist", {"kind": "is_evil", "player": by(g, "witch").id})
    assert ar.log[-1]["text"].endswith("Yes.")
    assert not any(a["key"] == "artist" for a in g.edition.day_actions(g, ar))


def test_pit_hag_changes_character_not_alignment():
    g = rigged(["nodashii", "pithag", "oracle", "clockmaker", "dreamer", "sweetheart", "juggler"], "snv")
    orc = by(g, "oracle")
    night(g)
    to_night(g)
    night(g, {"pithag": {"player": orc.id, "character": "savant"}, "nodashii": [by(g, "juggler").id],
              "dreamer": [orc.id]})
    assert orc.role == "savant" and g.edition.alignment(orc) == "good"


def test_human_mode_snv_includes_madness_characters():
    seen = set()
    for seed in range(80):
        g = lobby(12, "snv", seed, "human")
        g.start()
        seen |= {p.role for p in g.seated()}
    assert {"mutant", "cerenovus"} <= seen


def test_philosopher_with_gained_sage_learns_when_killed():
    g = rigged(["nodashii", "oracle", "witch", "philosopher", "clockmaker", "sweetheart", "juggler"], "snv")
    ph, nd = by(g, "philosopher"), by(g, "nodashii")
    night(g, {"philosopher": "sage", "witch": [by(g, "juggler").id]})
    assert "sage" in ph.gained
    to_night(g)
    night(g, {"nodashii": [ph.id], "witch": [by(g, "juggler").id]})
    assert not ph.alive
    assert any("The Demon is" in e["text"] and nd.name in e["text"] for e in ph.log)
