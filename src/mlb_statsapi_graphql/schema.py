"""Root queries for teams and individual players."""

import strawberry
from strawberry.extensions import MaskErrors

from .errors import should_mask_error
from .resolvers import resolve_player, resolve_team
from .types import Player, Team


@strawberry.type
class Query:
    player: Player | None = strawberry.field(resolver=resolve_player)
    team: Team | None = strawberry.field(resolver=resolve_team)


# Strawberry logs every error with its traceback before MaskErrors replaces
# unexpected exceptions with a generic message for the client.
schema = strawberry.Schema(
    query=Query, extensions=[lambda: MaskErrors(should_mask_error=should_mask_error)]
)
