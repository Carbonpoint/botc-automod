"""Simulate automod games and audit every piece of night info.

Usage: uv run python scripts/audit_info.py [GAMES_PER_EDITION] [EDITIONS...]
Prints a count of each problem kind with one example, then exits 1 if any.
"""
import collections
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from test_editions import lobby, play  # noqa: E402

from botc_automod.audit import check_game  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
editions = sys.argv[2:] or ["tb", "bmr", "snv"]
total_bad = 0
for ed in editions:
    kinds = collections.Counter()
    example = {}
    records = 0
    for seed in range(n):
        rng = random.Random(seed)
        g = lobby(rng.randint(5, 15), ed, seed, "auto")
        g.settings.update({"misregister": 0.5})
        g.estate["audit"] = []
        g.start()
        play(g, rng)
        records += len(g.estate["audit"])
        for b in check_game(g):
            kind = re.sub(r"\(.*?\)|\d+|: .*", "", b).strip()
            kinds[kind] += 1
            example.setdefault(kind, f"seed {seed}: {b}")
    total_bad += sum(kinds.values())
    print(f"{ed}: {n} games, {records} info records, {sum(kinds.values())} problems")
    for k, v in kinds.most_common():
        print(f"   {v:5}  {k}\n          e.g. {example[k]}")
sys.exit(1 if total_bad else 0)
