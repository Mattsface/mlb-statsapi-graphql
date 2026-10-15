"""The small public GraphQL model, independent of the upstream model.

Root query resolvers live in resolvers.py, which imports these types. Nested
field resolvers, such as Team.roster, live on their type so this module never
imports resolvers.py.
"""

import logging

import strawberry
from mlbstatsapi.exceptions import TheMlbStatsApiException
from pydantic import ValidationError
from strawberry.types import Info

from .context import Context
from .errors import upstream_error

logger = logging.getLogger(__name__)


@strawberry.type
class Player:
    id: int
    full_name: str | None


@strawberry.type
class Position:
    abbreviation: str | None


@strawberry.type
class RosterEntry:
    player: Player
    position: Position | None


@strawberry.type
class Team:
    id: int
    name: str | None
    abbreviation: str | None

    @strawberry.field
    async def roster(self, info: Info[Context, None]) -> list[RosterEntry] | None:
        # Runs only when roster is selected, after the team itself has resolved.
        try:
            roster = await info.context.mlb.get_team_roster(self.id, rosterType="active")
        except (TheMlbStatsApiException, ValidationError) as exc:
            logger.warning("MLB roster lookup failed for team %s", self.id, exc_info=True)
            raise upstream_error() from exc

        # The roster already contains person details; no get_person calls are needed.
        return [
            RosterEntry(
                player=Player(id=person.id, full_name=person.full_name),
                position=(
                    Position(abbreviation=person.primary_position.abbreviation)
                    if person.primary_position is not None else None
                ),
            )
            for person in roster
        ]
