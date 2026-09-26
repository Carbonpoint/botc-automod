"""Try agent talk on a real model: does an evil agent keep its secret?

Usage: uv run python scripts/agent_talk_bench.py OLLAMA_URL MODEL
"""
import random
import sys

from botc_automod import agents
from botc_automod.artist.translate import OllamaTranslator
from botc_automod.game import Game

g = Game("T", edition_id="tb", seed=3)
g.set_room("circle", seats=8)
h = g.join("Hana", is_host=True)
g.claim_seat(h.id, 0)
g.fill_with_agents()
g.settings["narrator"] = 0
g.start()
rng = random.Random(1)
while g.phase != "day":
    for p in g.seated():
        for t in p.tasks:
            if not t["done"]:
                g.submit_task(p.id, t["id"], agents._answer(g, p, t, rng))
    g.advance()
t = OllamaTranslator(sys.argv[1], sys.argv[2], timeout=120)
R = g.edition
for p in agents.agents(g):
    for reason in ("Tell the town your character.", "You are nominated for execution. Defend yourself."):
        system, user = agents.llm_prompt(g, p, reason)
        raw = t.chat(system, user)
        ok = agents.llm_check(g, p, raw)
        print(f"{p.name} ({R.roles[p.role].name}, {R.alignment(p)}): {'OK ' if ok else 'DROPPED'} {raw.strip()[:200]!r}")

# Chat replies: the reason text is the one agents._replies builds.
print("\n--- replies ---")
QUESTIONS = [("group", "{n}, what's your character?"), ("group", "Anyone learn anything last night?"),
             ("private", "Be honest with me, are you the Demon?"), ("private", "Who do you think is evil?"),
             ("group", "{n} you're lying, you're evil")]
import time
for p in agents.agents(g):
    for where, q in QUESTIONS:
        text = q.format(n=p.name)
        w = "sent you a private message" if where == "private" else "said in the group chat"
        system, user = agents.llm_prompt(g, p, f'Hana {w}: "{text}". Answer them.')
        t0 = time.time()
        raw = t.chat(system, user)
        ok = agents.llm_check(g, p, raw)
        print(f"{p.name} ({R.roles[p.role].name}, {R.alignment(p)}) [{time.time() - t0:.1f}s] {text!r} -> "
              f"{'OK ' if ok else 'DROPPED'} {raw.strip()[:160]!r}")
