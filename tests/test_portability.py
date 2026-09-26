"""Text files must name their encoding: Windows defaults to cp1252, not UTF-8."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CALL = re.compile(r"\.(read_text|write_text)\(([^()]|\([^()]*\))*\)|(?<![.\w])open\(([^()]|\([^()]*\))*\)")


def test_text_io_names_encoding():
    bad = []
    for f in [*ROOT.glob("src/**/*.py"), *ROOT.glob("scripts/*.py"), *ROOT.glob("tests/*.py")]:
        for m in CALL.finditer(f.read_text(encoding="utf-8")):
            call = m.group(0)
            if "urlopen" in call or "encoding=" in call or re.search(r"['\"][rwa]?b['\"]", call):
                continue
            bad.append(f"{f.relative_to(ROOT)}: {call[:60]}")
    assert not bad, "text I/O without encoding=:\n" + "\n".join(bad)


def test_wiki_data_loads_as_utf8():
    from botc_automod.editions import EDITIONS

    for e in EDITIONS.values():
        assert all(r.ability for r in e.roles.values()), e.id
