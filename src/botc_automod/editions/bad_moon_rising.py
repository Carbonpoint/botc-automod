"""Bad Moon Rising, the intermediate edition: death, resurrection and protection."""

from .chars_bmr import CHARS
from .rules import ScriptEdition


class BadMoonRising(ScriptEdition):
    id = "bmr"
    name = "Bad Moon Rising"
    wiki_name = "bad_moon_rising"
    chars = {c.id: c for c in CHARS}
    first_order = ["lunatic", "sailor", "courtier", "godfather", "devilsadvocate", "pukka", "grandmother",
                   "chambermaid"]
    other_order = ["sailor", "courtier", "innkeeper", "gambler", "devilsadvocate", "lunatic", "exorcist",
                   "zombuul", "pukka", "shabaloth", "po", "assassin", "godfather", "gossip", "professor",
                   "tinker", "moonchild", "grandmother", "chambermaid"]
