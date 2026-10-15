"""Root query; add future fields alongside team."""

import strawberry

from .resolvers import resolve_team
from .types import Team


@strawberry.type
class Query:
    team: Team | None = strawberry.field(resolver=resolve_team)


schema = strawberry.Schema(query=Query)
