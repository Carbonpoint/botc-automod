"""Fetch character data from the official Blood on the Clocktower wiki.

Writes src/botc_automod/editions/data/<edition>.json with, per character:
ability (exact wording), flavour, summary, how_to_run, examples, tips.

Usage: uv run python scripts/fetch_wiki.py
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://wiki.bloodontheclocktower.com/api.php"
UA = "Mozilla/5.0 (X11; Linux x86_64) Chrome/140.0 botc-automod"
OUT = Path(__file__).resolve().parent.parent / "src/botc_automod/editions/data"

EDITIONS = {
    "trouble_brewing": [
        "Washerwoman", "Librarian", "Investigator", "Chef", "Empath", "Fortune Teller",
        "Undertaker", "Monk", "Ravenkeeper", "Virgin", "Slayer", "Soldier", "Mayor",
        "Butler", "Drunk", "Recluse", "Saint",
        "Poisoner", "Spy", "Scarlet Woman", "Baron", "Imp",
    ],
}


def wikitext(title: str) -> str:
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "wikitext", "format": "json"})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["parse"]["wikitext"]["*"]


def clean(s: str) -> str:
    s = re.sub(r"\{\{(?:Good|Evil|Traveller|Fabled|Loric)\|([^}|]+)(?:\|[^}]*)?\}\}", r"\1", s)
    s = re.sub(r"\{\{[^}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", s)
    s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", s)
    s = re.sub(r"'''?", "", s)
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in s.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def sections(text: str) -> dict[str, str]:
    parts = re.split(r"^==\s*([^=]+?)\s*==\s*$", text, flags=re.M)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def bullets(block: str) -> list[str]:
    out = []
    for item in re.split(r"^\*", clean(block), flags=re.M):
        item = " ".join(item.split())
        if item:
            out.append(item)
    return out


def parse(title: str, text: str) -> dict:
    sec = sections(text)
    flavour = re.search(r"<p class='flavour'>(.*?)<p>", text, flags=re.S)
    summary = clean(sec.get("Summary", ""))
    lines = summary.splitlines()
    ability = lines[0].strip().strip('"').strip("“”") if lines else ""
    examples = [" ".join(clean(e).split())
                for e in re.findall(r"<div class='example'>(.*?)</div>", sec.get("Examples", ""), flags=re.S)]
    return {
        "name": title,
        "ability": ability,
        "flavour": clean(flavour.group(1)).strip('"“”') if flavour else "",
        "summary": [ln.lstrip("* ").strip() for ln in lines[1:]],
        "how_to_run": clean(sec.get("How to Run", "")).split("\n"),
        "examples": examples,
        "tips": bullets(sec.get("Tips & Tricks", "")),
        "source": f"https://wiki.bloodontheclocktower.com/{title.replace(' ', '_')}",
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for edition, titles in EDITIONS.items():
        data = {"fetched": time.strftime("%Y-%m-%d"), "characters": {}}
        for t in titles:
            rid = t.lower().replace(" ", "")
            data["characters"][rid] = parse(t, wikitext(t))
            print(f"{t:15} {data['characters'][rid]['ability'][:70]}")
            time.sleep(0.5)
        (OUT / f"{edition}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
