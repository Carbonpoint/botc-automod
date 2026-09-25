"""The interface every edition (script) implements.

The engine in game.py runs phases, timers, nominations and votes. It asks
the edition for everything that depends on characters: the deal, the
night tasks, how night choices resolve, and who has won.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..game import Game, Player

GOOD_TYPES = ("townsfolk", "outsider")
EVIL_TYPES = ("minion", "demon")


@dataclass(frozen=True)
class Role:
    id: str
    name: str
    type: str          # townsfolk | outsider | minion | demon
    ability: str
    style: str         # chill | think  (matches the player questionnaire)
    tip: str = ""      # a short how-to-play hint shown on the role card

    @property
    def team(self) -> str:
        return "good" if self.type in GOOD_TYPES else "evil"

    def card(self) -> dict:
        return {"id": self.id, "name": self.name, "type": self.type, "team": self.team,
                "ability": self.ability, "style": self.style, "tip": self.tip}


class Edition:
    id = ""
    name = ""
    min_players = 5
    max_players = 15
    roles: dict[str, Role] = {}
    wiki: dict[str, dict] = {}   # per character: flavour, summary, how_to_run, examples, tips, source

    def almanac(self) -> dict:
        return {"id": self.id, "name": self.name,
                "roles": [{**r.card(), "wiki": self.wiki.get(r.id, {})} for r in self.roles.values()]}

    # Human storyteller -----------------------------------------------------
    def st_status(self, game: Game) -> list[dict]:
        """Grimoire facts the human storyteller sees (poison, red herring...)."""
        return []

    def st_set(self, game: Game, key: str, value) -> None:
        """Let the human storyteller change an edition setting (red herring...)."""
        raise NotImplementedError

    # Setup ---------------------------------------------------------------
    def setup(self, game: Game) -> None:
        raise NotImplementedError

    # Night ---------------------------------------------------------------
    def on_dusk(self, game: Game) -> None:
        """Called as each night begins, before any task."""

    def stage_a(self, game: Game) -> dict[str, list[dict]]:
        """Tasks for the first half of the night: choices and evil info."""
        raise NotImplementedError

    def resolve_a(self, game: Game, answers: dict[str, dict]) -> dict[str, list[dict]]:
        """Resolve choices in night order. Return tasks for stage B."""
        raise NotImplementedError

    def resolve_b(self, game: Game, answers: dict[str, dict]) -> dict[str, list[str]]:
        """Resolve stage B (for example the Ravenkeeper). Return private messages."""
        return {}

    # Day -----------------------------------------------------------------
    def on_nominate(self, game: Game, nominator: Player, nominee: Player) -> bool:
        """Return True when the nomination ends the day at once (Virgin)."""
        return False

    def count_votes(self, game: Game, votes: dict[str, bool]) -> int:
        return sum(1 for v in votes.values() if v)

    def on_execution(self, game: Game, player: Player) -> None:
        game.kill(player.id, "execution")

    def on_no_execution(self, game: Game) -> None:
        pass

    def slayer_shot(self, game: Game, shooter: Player, target: Player) -> None:
        game.announce(f"{shooter.name} claims a Slayer shot at {target.name}. Nothing happens.")

    def check_win(self, game: Game) -> tuple[str, str] | None:
        raise NotImplementedError
