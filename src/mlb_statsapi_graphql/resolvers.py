"""Async root query resolvers translating library results into GraphQL values."""

from strawberry.types import Info

from .context import Context
from .errors import require_positive_id, upstream_error
from .loaders import UPSTREAM_EXCEPTIONS
from .types import Player, Team


async def resolve_team(info: Info[Context, None], id: int) -> Team | None:
    require_positive_id(id)
    try:
        team = await info.context.loaders.team.load(id)
    except UPSTREAM_EXCEPTIONS as exc:
        raise upstream_error() from exc

    if team is None:
        return None
    return Team(id=team.id, name=team.name, abbreviation=team.abbreviation)


async def resolve_player(info: Info[Context, None], id: int) -> Player | None:
    require_positive_id(id)
    try:
        person = await info.context.loaders.person.load(id)
    except UPSTREAM_EXCEPTIONS as exc:
        raise upstream_error() from exc

    if person is None:
        return None
    return Player(id=person.id, full_name=person.full_name)
