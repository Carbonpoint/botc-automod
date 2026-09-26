"""Agents: computer players that the host seats in empty seats.

They let a few people play a bigger game, fill a room with fewer than 5
players, or let one person test everything alone. An agent is a normal
Player with agent=True. Once per server tick, `act` lets each agent do
what a player would do, after a short, random, human-like delay:

    night   answer its tasks. An evil agent never kills or poisons its
            own team; others choose at random.
    day     use a forced ability (Klutz, Moonchild...), visit the
            Storyteller as a Savant, and sometimes shoot as a Slayer.
            Talk: claim a character (a good one tells the truth, an evil
            one claims a Demon bluff), defend itself when nominated,
            give a reason when it nominates.
    noms    now and then nominate: evil agents pick a good player.
    vote    evil agents protect their team and vote out good players;
            good agents vote yes about half the time.
    dawn    an agent narrator posts the story into the chat, then starts
            the day.
    chat    answer players: a private message to an agent, a group
            message that names it, or a question to the town (one or two
            agents answer). The answer comes 2 to 6 s later.

Talk goes through `speak(pid, reason, fallback, to)`. By default it sends the
fallback text; the server passes a function that asks a language model
first (see server.agent_speak). Agents take no part in keyword tasks, the
helpful narrator or karma.
"""

from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .game import Game, Player

NAMES = ["Ada", "Basil", "Clover", "Dorian", "Edda", "Felix", "Greta", "Hugo", "Iris", "Jasper", "Kit",
         "Luna", "Milo", "Nell", "Otto", "Pip", "Quinn", "Rosa", "Silas", "Tess"]
DAY_PHASES = ("day", "nominations", "defense", "vote")
ACT_CHANCE = 0.25        # per tick (0.5 s) that a waiting agent acts: about 2 s on average
NOMINATE_CHANCE = 0.015  # per tick, per agent, while the nomination floor is open
TALK_GAP = 20.0          # s between messages from one agent
REPLY_DELAY = (2.0, 6.0) # s before an agent answers a chat message
REPLY_GAP = 4.0          # s between two answers from one agent
CHIME = 0.15             # chance an agent comments on a group message that asks nothing
ANSWER = "Answer them."  # ends the reason of a chat reply
DEFEND = "You are nominated for execution. Defend yourself."
# Good agents cannot reason about the talk like people do. Instead they get a hunch: a
# small lean toward the truth when they nominate and vote. Tuned so that games with
# only agents are won about as often by each team (see tests/test_agents.py).
HUNCH = 0.25

Speak = Callable[..., None]   # speak(pid, reason, fallback, to=None)


def is_agent(p: Player) -> bool:
    return bool(getattr(p, "agent", False))


def agents(game: Game) -> list[Player]:
    return [p for p in game.seated() if is_agent(p)]


def new_name(game: Game) -> str:
    taken = {p.name.lower() for p in game.players.values()}
    for n in NAMES:
        if n.lower() not in taken:
            return n
    i = 2
    while f"agent {i}" in taken:
        i += 1
    return f"Agent {i}"


def _mem(game: Game, p: Player) -> dict:
    return game.estate.setdefault("agent_mem", {}).setdefault(p.id, {})


def _evil(game: Game, p: Player) -> bool:
    return game.edition.alignment(p) == "evil"


# Night ---------------------------------------------------------------------------------
def _answer(game: Game, p: Player, t: dict, rng: random.Random):
    kind = t["kind"]
    R = game.edition
    role = R.roles.get(t.get("key"))
    if kind == "choose":
        cands = list(t["candidates"])
        if t.get("allow_none") and rng.random() < 0.15:
            return []
        if role is not None and role.team == "evil" and _evil(game, p):
            good = [c for c in cands if not _evil(game, game.p(c)) and c != p.id]
            if len(good) >= t["pick"]:
                cands = good
        elif len([c for c in cands if c != p.id]) >= t["pick"]:
            cands = [c for c in cands if c != p.id]
        return rng.sample(cands, t["pick"])
    if kind == "character":
        return None if t.get("allow_none") and rng.random() < 0.3 else rng.choice(t["options"])["id"]
    if kind == "player_character":
        return {"player": rng.choice(t["candidates"]), "character": rng.choice(t["options"])["id"]}
    if kind == "decoy":
        return rng.choice(t["options"])
    return True


def _night(game: Game, now: float, rng: random.Random) -> bool:
    changed = False
    for p in agents(game):
        task = next((t for t in p.tasks if not t["done"]), None)
        if task and rng.random() < ACT_CHANCE:
            game.submit_task(p.id, task["id"], _answer(game, p, task, rng))
            changed = True
    return changed


# Day -----------------------------------------------------------------------------------
def _claim(game: Game, p: Player, rng: random.Random) -> str:
    """The character this agent says it is."""
    mem = _mem(game, p)
    if "claim" not in mem:
        R = game.edition
        if _evil(game, p):
            bluffs = R.bluffs_for(game, p) or []
            taken = {m.get("claim") for m in game.estate.get("agent_mem", {}).values()}
            good = [r.name for r in R.roles.values() if r.type == "townsfolk" and r.name not in taken]
            mem["claim"] = rng.choice([b for b in bluffs if b not in taken] or good)
        else:
            mem["claim"] = R.roles[p.shown].name
    return mem["claim"]


def _info_line(p: Player) -> str | None:
    """The latest thing this agent learned in private, to share (good agents only)."""
    for e in reversed(p.log):
        text = e["text"]
        if not text.startswith(("You are the", "Keyword", "Narrator", "Time ran out")):
            return text
    return None


def _talk(game: Game, p: Player, now: float, reason: str, fallback: str, speak: Speak,
          force: bool = False) -> bool:
    mem = _mem(game, p)
    if game.phase == "night" or (not force and now - mem.get("talked", 0) < TALK_GAP):
        return False
    mem["talked"] = now
    speak(p.id, reason, fallback)
    return True


def _payload(game: Game, p: Player, a: dict, rng: random.Random) -> dict:
    alive = [x.id for x in game.seated() if game.living(x) and x is not p]
    roles = list(game.edition.roles)
    if a["kind"] == "target":
        cands = a.get("candidates") or alive
        if _evil(game, p):
            cands = [c for c in cands if not _evil(game, game.p(c))] or cands
        return {"target": rng.choice(cands)}
    if a["kind"] == "guesses":
        return {"guesses": [{"player": rng.choice(alive), "character": rng.choice(roles)} for _ in range(3)]}
    return {}


def _day(game: Game, now: float, rng: random.Random, speak: Speak) -> bool:
    changed = False
    for p in agents(game):
        if rng.random() >= ACT_CHANCE:
            continue
        mem = _mem(game, p)
        for a in game.edition.day_actions(game, p):
            if game.phase not in DAY_PHASES:
                break
            kind, key = a["kind"], a["key"]
            if not a.get("forced"):
                if key == "savant" or (kind == "guesses" and game.day == 1):
                    pass
                elif key == "slayer" and _claim(game, p, rng) == "Slayer" and rng.random() < 0.05:
                    pass
                else:
                    continue
            if kind in ("statement", "question"):
                continue   # Gossip and Artist need words: agents do not use them
            game.day_action(p.id, key, _payload(game, p, a, rng))
            changed = True
        # Say who we are, once a day.
        if mem.get("claimed_day") != game.day and game.phase in ("day", "nominations"):
            claim = _claim(game, p, rng)
            info = None if _evil(game, p) else _info_line(p)
            text = f"I'm the {claim}." + (f" I learned: {info}" if info and rng.random() < 0.7 else "")
            if _talk(game, p, now, f"Tell the town your character is the {claim}.", text, speak):
                mem["claimed_day"] = game.day
                changed = True
    return changed


def _nominate(game: Game, now: float, rng: random.Random, speak: Speak) -> bool:
    if game.phase != "nominations" or game.current_nom:
        return False
    for p in agents(game):
        if not game.living(p) or p.id in game.nominators_today or rng.random() >= NOMINATE_CHANCE:
            continue
        free = [x for x in game.seated() if x is not p and x.id not in game.nominees_today and game.living(x)]
        if _evil(game, p):
            free = [x for x in free if not _evil(game, x)] or free
        elif rng.random() < HUNCH:
            free = [x for x in free if _evil(game, x)] or free
        if not free:
            continue
        target = rng.choice(free)
        game.nominate(p.id, target.id)
        _talk(game, p, now, f"You nominated {target.name}. Say why you suspect them.",
              rng.choice([f"{target.name}'s story doesn't add up for me.",
                          f"I don't trust {target.name}. Let's hear them out.",
                          f"Something about {target.name} feels off today."]), speak)
        return True
    return False


def _defend_and_vote(game: Game, now: float, rng: random.Random, speak: Speak) -> bool:
    changed = False
    nom = game.current_nom
    if not nom:
        return False
    nominee = game.p(nom["nominee"])
    for p in agents(game):
        mem = _mem(game, p)
        key = f"{game.day}:{nom['nominee']}"
        if p is nominee and game.phase == "defense" and mem.get("defended") != key:
            mem["defended"] = key
            claim = _claim(game, p, rng)
            _talk(game, p, now, DEFEND,
                  rng.choice([f"I'm the {claim}, I promise. Executing me helps the Demon.",
                              f"Not me! I'm the {claim}. Look elsewhere.",
                              f"I'm a good {claim}. Please don't waste today's execution on me."]), speak, force=True)
            changed = True
        if game.phase != "vote" or p.id in nom["votes"] or not game.can_vote(p) or rng.random() >= ACT_CHANCE:
            continue
        if _evil(game, p):
            yes = not _evil(game, nominee)
        elif p is nominee:
            yes = False
        else:
            lean = HUNCH if _evil(game, nominee) else -HUNCH
            yes = rng.random() < (0.5 if game.living(p) else 0.25) + lean
        game.vote(p.id, yes)
        changed = True
    return changed


def _narrate(game: Game, now: float, speak: Speak) -> bool:
    n = game.estate.get("narration")
    if game.stage != "narration" or not n:
        return False
    p = game.p(n["pid"])
    if not is_agent(p):
        return False
    mem = _mem(game, p)
    if mem.get("narrated") != game.day:
        mem["narrated"] = game.day
        mem["narrate_at"] = now + 6
        for line in n["story"] + n["facts"]:
            speak(p.id, "", line)
        return True
    if now >= mem.get("narrate_at", 0):
        game.finish_narration(p.id)
        return True
    return False


# Chat replies ----------------------------------------------------------------------------
_ASK_ROLE = ("who are you", "what are you", "your role", "your character", "claim", "what's your", "whats your")
_ASK_INFO = ("learn", "info", "know", "see", "saw", "what did you", "find out", "found")
_ASK_SUS = ("who", "suspect", "sus", "demon", "evil", "minion", "trust", "think", "vote", "nominate")
_BLAME = ("you're evil", "you are evil", "youre evil", "you're the demon", "you are the demon", "lying", "liar",
          "don't trust you", "dont trust you", "you're sus", "you are sus", "youre sus")
_HELLO = ("hi", "hey", "hello", "morning", "yo")


def _names_in(game: Game, text: str) -> list[Player]:
    return [p for p in agents(game) if re.search(rf"\b{re.escape(p.name)}\b", text, re.I)]


def _heard(game: Game, now: float, rng: random.Random) -> None:
    """Queue answers to new chat messages from people."""
    chat = game.estate.get("chat", [])
    seen = game.estate.get("agent_chat_seen", 0)
    game.estate["agent_chat_seen"] = chat[-1]["id"] if chat else 0
    queue = game.estate.setdefault("agent_replies", [])
    for m in chat:
        if m["id"] <= seen or is_agent(game.p(m["from"])):
            continue
        low = m["text"].lower()
        if m["to"] is not None:
            who = [game.p(m["to"])] if is_agent(game.p(m["to"])) else []
        else:
            who = _names_in(game, m["text"])
            if not who:
                chance = 1.0 if "?" in low else CHIME
                pool = [p for p in agents(game) if rng.random() < chance]
                who = rng.sample(pool, min(len(pool), 2 if "?" in low else 1))
        for p in who:
            queue.append({"pid": p.id, "msg": m["id"], "at": now + rng.uniform(*REPLY_DELAY)})
    del queue[:-40]


def _reply_text(game: Game, p: Player, m: dict, rng: random.Random) -> str:
    """An answer without a language model: pick lines by the words in the message."""
    low = m["text"].lower()
    words = set(re.findall(r"[a-z']+", low))
    claim = _claim(game, p, rng)
    named = bool(re.search(rf"\b{re.escape(p.name)}\b", m["text"], re.I)) or m["to"] == p.id
    if named and any(b in low for b in _BLAME):
        return rng.choice([f"I'm the {claim}, honestly. Look somewhere else.",
                           f"Why me? I'm the {claim}.", f"I get it, but I'm really the {claim}."])
    if any(k in low for k in _ASK_ROLE):
        return f"I'm the {claim}."
    if any(k in low for k in _ASK_INFO):
        info = None if _evil(game, p) else _info_line(p)
        return f"I learned: {info}" if info else rng.choice(["Nothing useful yet.", "Nothing I can share yet, sorry."])
    if any(k in words for k in _ASK_SUS) or any(k in low for k in _ASK_SUS[1:]):
        others = [x for x in game.seated() if x is not p and game.living(x)]
        if _evil(game, p):
            others = [x for x in others if not _evil(game, x)] or others
        elif rng.random() < HUNCH:
            others = [x for x in others if _evil(game, x)] or others
        if others:
            x = rng.choice(others)
            return rng.choice([f"I'd look at {x.name}.", f"{x.name} worries me a bit.",
                               f"Not sure yet. Maybe {x.name}?"])
    if words & set(_HELLO):
        return rng.choice(["Hey!", "Hi there.", "Hello!"])
    return rng.choice(["Hmm, not sure yet.", "Good point.", "Let's keep talking before we nominate.",
                       "I'm listening.", "Could be. What does everyone else think?"])


def _replies(game: Game, now: float, rng: random.Random, speak: Speak) -> bool:
    queue = game.estate.get("agent_replies", [])
    changed = False
    for r in list(queue):
        if now < r["at"]:
            continue
        p, mem = game.p(r["pid"]), _mem(game, game.p(r["pid"]))
        if now - mem.get("replied", 0) < REPLY_GAP:
            continue
        queue.remove(r)
        m = next((x for x in game.estate.get("chat", []) if x["id"] == r["msg"]), None)
        if m is None:
            continue
        sender = "Someone (anonymous)" if m.get("anon") else game.p(m["from"]).name
        to = m["from"] if m["to"] == p.id else None
        where = "sent you a private message" if to else "said in the group chat"
        mem["replied"] = mem["talked"] = now
        speak(p.id, f'{sender} {where}: "{m["text"]}". {ANSWER}', _reply_text(game, p, m, rng), to)
        changed = True
    return changed


def urgent(reason: str) -> bool:
    """A reply to a person or a defense: a language model writes these before other talk."""
    return reason.endswith(ANSWER) or reason == DEFEND


def act(game: Game, now: float, rng: random.Random | None = None, speak: Speak | None = None) -> bool:
    """Let every agent act once if it wants to. Returns True when the game changed."""
    if not agents(game) or game.phase in ("lobby", "setup", "ended"):
        return False
    rng = rng or random.SystemRandom()
    speak = speak or (lambda pid, reason, text, to=None: _post(game, pid, text, now, to))
    _heard(game, now, rng)
    if game.phase == "night":
        game.estate["agent_replies"] = []   # the town is asleep
        return _night(game, now, rng)
    changed = _replies(game, now, rng, speak)
    changed |= _narrate(game, now, speak)
    if game.stage == "narration":
        return changed
    changed |= _day(game, now, rng, speak)
    changed |= _nominate(game, now, rng, speak)
    changed |= _defend_and_vote(game, now, rng, speak)
    return changed


def _post(game: Game, pid: str, text: str, now: float, to: str | None = None) -> None:
    """Send an agent's message (to one player, or to everyone). Agents skip the one-message-a-second limit."""
    from .game import GameError

    game.estate.setdefault("chat_last", {}).pop(pid, None)
    try:
        game.send_chat(pid, text, to=to, now=now)
    except GameError:
        pass


# Talking with a language model ---------------------------------------------------------
# The model plays one agent. It gets only what that agent knows, like a human player.
_META = ("the user", "as an ai", "language model", "system prompt", "i am an agent", "i'm an agent")
# Hints that an evil agent is giving itself away, even without a character name.
_TELLS = ("evil team", "real identity", "true identity", "real character", "true character", "working together",
          "not trustworthy", "my team", "my teammate", "you're right", "you are right", "'s right")
_ME = re.compile(r"\b(i|i'm|im|me|my|we|we're|us|our)\b", re.I)


def llm_prompt(game: Game, p: Player, reason: str) -> tuple[str, str]:
    R = game.edition
    claim = _claim(game, p, random.SystemRandom())
    if _evil(game, p):
        team = [f"{x.name} ({R.roles[x.role].name})" for x in game.seated() if _evil(game, x) and x is not p]
        side = (f"You are secretly on the evil team: you are the {R.roles[p.role].name}. "
                f"Never reveal that. Claim to be the {claim} and act like a good player. "
                f"Your evil teammates: {', '.join(team) or 'none known'}. Never name or accuse them. "
                f"If someone asks or accuses you, calmly deny it and say you are the {claim}.")
    else:
        side = (f"You are on the good team. You are the {R.roles[p.shown].name}. "
                "Be honest about your character and what you learned. You want to find the Demon.")
    system = (f"You are {p.name}, a player in a game of Blood on the Clocktower, chatting with the other "
              f"players. {side} Write ONE short chat message: 1 or 2 sentences, under 40 words, casual, "
              "first person. No quotes, no name tag, no emojis.")
    chat = [f"{'Anonymous' if m.get('anon') else game.p(m['from']).name}: {m['text']}"
            for m in game.estate.get("chat", []) if m["to"] is None][-8:]
    notes = [e["text"] for e in p.log[-6:]]
    user = "\n".join([
        f"Day {game.day}. Alive: {', '.join(x.name for x in game.seated() if game.living(x))}.",
        "What you learned in private:", *(notes or ["nothing"]),
        "Recent public events:", *[f"{e['label']}: {e['text']}" for e in game.public_log[-8:]],
        "Recent chat:", *(chat or ["(quiet)"]),
        f"Now: {reason}",
    ])
    return system, user


def llm_check(game: Game, p: Player, text: str) -> str | None:
    """The model's message, or None when the fallback must be used instead."""
    text = (text or "").strip().strip('"').strip()
    if text.lower().startswith(f"{p.name.lower()}:"):
        text = text[len(p.name) + 1:].strip()
    low = text.lower()
    if not text or any(m in low for m in _META):
        return None
    if _evil(game, p):
        # An evil agent only claims good characters, so any evil character name in its
        # message gives away itself or a teammate (a Spy knows the whole Grimoire).
        evil = [r.name for r in game.edition.roles.values() if r.team == "evil"]
        mates = [x.name for x in game.seated() if x is not p and _evil(game, x)]
        names = evil + mates + [n[:-1] + "ies" for n in evil if n.endswith("y")]   # Spy: spies
        if any(re.search(rf"\b{re.escape(n)}s?\b", text, re.I) for n in names) \
                or any(t in low.replace("’", "'") for t in _TELLS) \
                or any("evil" in part and _ME.search(part) for part in re.split(r"[.!?]", low)):
            return None      # it gave itself or its team away
    return text[:300]
