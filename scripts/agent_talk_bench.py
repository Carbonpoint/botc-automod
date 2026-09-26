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
