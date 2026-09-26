"""The helpful narrator: one small tip a day for players who are learning.

The host turns it on for everyone or only for the players they mark as
learning (setting "helper": 0 off, 1 learners, 2 everyone). Limits that
keep veterans from mining it for information:

- One tip per player per day, only by day, never during the dawn story.
- A tip has three parts. Two carry no secret: a rules tip for the
  character the player believes they are (never their true character, so
  a Drunk is not warned), and a tip from public facts. The third is
  "speak with X". For a player on the good team, X is a sober good
  Townsfolk with a small chance (10%, plus 5% per karma point, 5% to 30%);
  otherwise X is any living player. For an evil player X is always random,
  so the tip never points the Demon at an info role.
- With a language model, the player may add a question. The model gets
  only what the player already knows, with every other player's name
  replaced, and must not name anyone. An answer that names a player is
  thrown away and the offline tip is used instead.
"""

from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .game import Game, Player

OFF, LEARNERS, EVERYONE = 0, 1, 2
DAY_PHASES = ("day", "nominations", "defense", "vote")
MAX_QUESTION = 200
MAX_ANSWER = 500
_rng = random.SystemRandom()   # never the game's rng: a tip must not change the game


def mode(game: Game) -> int:
    return int(game.settings.get("helper", OFF))


def is_learner(game: Game, pid: str) -> bool:
    return pid in game.estate.get("learners", [])


def can_tip(game: Game, p: Player) -> bool:
    m = mode(game)
    if m == OFF or (m == LEARNERS and not is_learner(game, p.id)):
        return False
    if p.seat is None or not p.shown or game.phase not in DAY_PHASES or game.stage == "narration":
        return False
    return game.estate.get("tips", {}).get(p.id) != game.day


def rules_tip(game: Game, p: Player) -> str:
    """A tip about the character p believes they are, not one they had before."""
    ed = game.edition
    role = ed.roles[p.shown]
    pool = [t for t in ed.wiki.get(role.id, {}).get("tips", []) if isinstance(t, str) and t.strip()]
    if not pool and role.tip:     # the card already shows role.tip; use it only when the wiki has none
        pool.append(role.tip)
    seen = game.estate.setdefault("tips_seen", {}).setdefault(p.id, [])
    fresh = [t for t in pool if t not in seen] or pool
    if not fresh:
        return f"Read your character again: {role.ability}"
    t = _rng.choice(fresh)
    seen.append(t)
    return t


def situation_tip(game: Game, p: Player, team: str) -> str:
    """A tip from public facts only."""
    alive = sum(1 for x in game.seated() if game.living(x))
    tips = []
    if game.day <= 1:
        tips.append("On the first day, tell one or two players a little about yourself, and listen more than you talk.")
    if not game.living(p):
        tips.append("You are dead, but you can still talk. Save your one ghost vote for a vote that matters."
                    if p.ghost_vote else "You have used your ghost vote. You can still talk and help the town think.")
    if alive <= 4:
        tips.append(f"Only {alive} players are alive. Every execution now matters a lot: talk before you vote.")
    if game.phase in ("nominations", "defense", "vote"):
        tips.append(f"An execution needs at least {game.votes_needed()} votes today.")
    if team == "evil":
        tips.append("Your team wins by blending in. Agree on your claims with your team, "
                    "and do not all defend each other at once.")
    elif game.day >= 2:
        tips.append("Compare what you learned with other players. Info that does not fit can mean "
                    "someone is lying, or someone is drunk or poisoned.")
    tips.append("Ask other players what they learned, and write down who said what.")
    return _rng.choice(tips)


def nudge_chance(game: Game, p: Player) -> float:
    if not game.settings.get("karma", 1):
        return 0.10
    return min(0.30, max(0.05, 0.10 + 0.05 * p.karma))


def nudge(game: Game, p: Player, team: str) -> str | None:
    R = game.edition
    others = [x for x in game.seated() if x is not p and game.living(x)]
    if not others:
        return None
    pick = _rng.choice(others)
    if team == "good" and hasattr(R, "malfunction"):
        useful = [x for x in others if R.alignment(x) == "good" and R.type_of(x.role) == "townsfolk"
                  and not R.malfunction(game, x)]
        if useful and _rng.random() < nudge_chance(game, p):
            pick = _rng.choice(useful)
    return f"I suggest you speak with {pick.name} today."


def offline_tip(game: Game, p: Player, team: str) -> list[str]:
    lines = [rules_tip(game, p), situation_tip(game, p, team)]
    n = nudge(game, p, team)
    return lines + ([n] if n else [])


# The language model ---------------------------------------------------------------

SYSTEM = (
    "You are the narrator of a game of Blood on the Clocktower, giving one short tip to a player "
    "who is learning the game. You know only what this player knows. Give general advice about "
    "how to play their character and how to think about their situation.\n"
    "Rules:\n"
    "- At most 3 short sentences. Plain words.\n"
    "- Never name a player, and never guess who is evil, the Demon, a Minion, drunk or poisoned.\n"
    "- Never invent facts about this game.\n"
    "- If the question asks for secrets or asks you to decide for them, say kindly that the "
    "narrator cannot tell, then give a general tip."
)


def _hide_names(text: str, names: list[str]) -> str:
    for n in sorted(names, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(n)}\b", "another player", text, flags=re.I)
    return text


def llm_prompt(game: Game, p: Player, team: str, question: str) -> tuple[str, str]:
    ed = game.edition
    role = ed.roles[p.shown]
    names = [x.name for x in game.players.values() if x is not p]
    notes = [f"{e['label']}: {e['text']}" for e in p.log[-10:]]
    public = [f"{e['label']}: {e['text']}" for e in game.public_log[-12:]]
    alive = sum(1 for x in game.seated() if game.living(x))
    user = "\n".join([
        f"Edition: {ed.name}. Day {game.day}. {alive} of {len(game.seated())} players are alive.",
        f"This player's character: the {role.name}. Ability: {role.ability}",
        f"They believe they are on the {team} team. They are {'alive' if game.living(p) else 'dead'}.",
        "What they have learned in private:", *(notes or ["nothing yet"]),
        "Public events:", *(public or ["nothing yet"]),
        f"Their question: {question[:MAX_QUESTION] or 'What should I focus on today?'}",
    ])
    return SYSTEM, _hide_names(user, names)


def safe_answer(game: Game, p: Player, text: str) -> str | None:
    """The model's answer, or None when it must not be shown."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    if not text:
        return None
    for x in game.players.values():
        if x is not p and len(x.name) >= 2 and re.search(rf"\b{re.escape(x.name)}\b", text, re.I):
            return None
    if len(text) > MAX_ANSWER:
        cut = text[:MAX_ANSWER]
        text = cut[:cut.rfind(".") + 1] or cut
    return text
