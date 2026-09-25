from .bad_moon_rising import BadMoonRising
from .base import Edition, Role
from .sects_and_violets import SectsAndViolets
from .trouble_brewing import TroubleBrewing

EDITIONS: dict[str, Edition] = {e.id: e for e in (TroubleBrewing(), BadMoonRising(), SectsAndViolets())}

__all__ = ["EDITIONS", "Edition", "Role"]
