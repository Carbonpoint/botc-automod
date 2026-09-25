"""Trouble Brewing, the beginner edition."""

from .chars_tb import CHARS
from .rules import DISTRIBUTION, ScriptEdition


class TroubleBrewing(ScriptEdition):
    id = "tb"
    name = "Trouble Brewing"
    wiki_name = "trouble_brewing"
    chars = {c.id: c for c in CHARS}
    first_order = ["poisoner", "spy", "washerwoman", "librarian", "investigator", "chef", "empath",
                   "fortuneteller", "butler"]
    other_order = ["poisoner", "monk", "scarletwoman", "imp", "ravenkeeper", "undertaker", "empath",
                   "fortuneteller", "butler", "spy"]


ROLES = TroubleBrewing().roles

__all__ = ["DISTRIBUTION", "ROLES", "TroubleBrewing"]
