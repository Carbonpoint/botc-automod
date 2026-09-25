from .base import Edition, Role
from .trouble_brewing import TroubleBrewing

EDITIONS: dict[str, Edition] = {e.id: e for e in (TroubleBrewing(),)}

__all__ = ["EDITIONS", "Edition", "Role"]
