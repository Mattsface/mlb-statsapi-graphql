"""The small public GraphQL model, independent of the upstream model."""

import strawberry
from strawberry.types import Info

from .context import Context


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
        # Import here because resolvers also construct these GraphQL types.
        from .resolvers import resolve_roster

        return await resolve_roster(info, self.id)
