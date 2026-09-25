"""Sects & Violets, the intermediate edition: madness and character changes."""

from .chars_snv import CHARS
from .rules import ScriptEdition


class SectsAndViolets(ScriptEdition):
    id = "snv"
    name = "Sects & Violets"
    wiki_name = "sects_and_violets"
    chars = {c.id: c for c in CHARS}
    first_order = ["philosopher", "snakecharmer", "eviltwin", "witch", "cerenovus", "clockmaker", "dreamer",
                   "seamstress", "mathematician"]
    other_order = ["philosopher", "snakecharmer", "witch", "cerenovus", "pithag", "fanggu", "nodashii",
                   "vortox", "vigormortis", "barber", "sweetheart", "sage", "dreamer", "flowergirl",
                   "towncrier", "oracle", "seamstress", "juggler", "mathematician"]
