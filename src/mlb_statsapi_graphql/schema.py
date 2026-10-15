"""Root queries for teams and individual players."""

import strawberry

from .resolvers import resolve_player, resolve_team
from .types import Player, Team


@strawberry.type
class Query:
    player: Player | None = strawberry.field(resolver=resolve_player)
    team: Team | None = strawberry.field(resolver=resolve_team)


schema = strawberry.Schema(query=Query)
