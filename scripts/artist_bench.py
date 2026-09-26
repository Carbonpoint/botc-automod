"""Benchmark a translator on the Artist test sets.

Usage:
  uv run python scripts/artist_bench.py ollama URL MODEL [--n 300] [--compact] [--out FILE]
  uv run python scripts/artist_bench.py openai BASE_URL MODEL [--key KEY] [--compact] ...

Sets: "test" (generated, held-out wording and names) and "natural"
(hand-written, see artist/data/natural.py). Outcomes per question:
  right      same meaning as the gold query (checked on 25 worlds)
  refused    gold is answerable, model said "ask another" or gave invalid output (safe)
  misread    gold is answerable, model gave a valid query with another meaning (dangerous)
  false_ok   gold is unanswerable, model gave a query anyway (dangerous if the player confirms)
"""
import argparse
import concurrent.futures as cf
import json
import random
import statistics
import sys
import time

from botc_automod.artist import dataset
from botc_automod.artist.data import natural
from botc_automod.artist.query import Seat, World, validate
from botc_automod.artist.translate import OllamaTranslator, OpenAITranslator, timed
from botc_automod.editions import EDITIONS


def natural_items(rng: random.Random) -> list[dict]:
    tb = EDITIONS["tb"]
    roles = {r.id: (r.name, r.type) for r in tb.roles.values()}
    ids = list(roles)
    out = []
    for q, gold in natural.QUESTIONS:
        assigned = rng.sample(ids, len(natural.PLAYERS))
        seats = [Seat(n, r, roles[r][1], "evil" if roles[r][1] in ("minion", "demon") else "good",
                      rng.random() < 0.8, rng.random() < 0.15) for n, r in zip(natural.PLAYERS, assigned)]
        w = World(seats, roles)
        out.append({"world": dataset.world_json(w), "asker": natural.ASKER, "question": q,
                    "gold": validate(gold, w, natural.ASKER), "intent": gold["op"]})
    return out


def score(t, items: list[dict], workers: int) -> dict:
    rng = random.Random(5)

    def one(ex):
        w = dataset.world_from_json(ex["world"])
        pred, raw, secs = timed(t, w, ex["asker"], ex["question"])
        gold = ex["gold"]
        if gold["op"] == "unanswerable":
            outcome = "right" if pred is None or pred["op"] == "unanswerable" else "false_ok"
        elif pred is None or pred["op"] == "unanswerable":
            outcome = "refused"
        else:
            outcome = "right" if dataset.equivalent(pred, gold, w, ex["asker"], random.Random(rng.random())) \
                else "misread"
        return {"q": ex["question"], "intent": ex["intent"], "gold": gold, "pred": pred, "raw": raw[:300],
                "outcome": outcome, "secs": secs}

    with cf.ThreadPoolExecutor(workers) as pool:
        rows = list(pool.map(one, items))
    counts = {k: sum(r["outcome"] == k for r in rows) for k in ("right", "refused", "misread", "false_ok")}
    secs = [r["secs"] for r in rows]
    return {"n": len(rows), **counts, "right_pct": round(100 * counts["right"] / len(rows), 1),
            "dangerous_pct": round(100 * (counts["misread"] + counts["false_ok"]) / len(rows), 1),
            "median_s": round(statistics.median(secs), 2), "p90_s": round(sorted(secs)[int(0.9 * len(secs))], 2),
            "rows": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("backend", choices=["ollama", "openai"])
    ap.add_argument("url")
    ap.add_argument("model")
    ap.add_argument("--key", default="")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--compact", action="store_true")
    ap.add_argument("--no-schema", action="store_true", help="plain decoding, no constrained output")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    t = (OllamaTranslator(a.url, a.model, compact=a.compact) if a.backend == "ollama"
         else OpenAITranslator(a.url, a.model, a.key, compact=a.compact, use_schema=not a.no_schema))
    sets = {"test": dataset.generate(a.n, "test", seed=99), "natural": natural_items(random.Random(3))}
    report = {"model": a.model, "backend": a.backend, "compact": a.compact, "when": time.strftime("%F %T")}
    for name, items in sets.items():
        r = score(t, items, a.workers)
        report[name] = r
        print(f"{a.model:28} {name:8} right {r['right_pct']:5}%  refused {r['refused']:3}  misread {r['misread']:3}"
              f"  false_ok {r['false_ok']:3}  dangerous {r['dangerous_pct']:4}%  median {r['median_s']}s",
              flush=True)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1)


if __name__ == "__main__":
    sys.exit(main())
