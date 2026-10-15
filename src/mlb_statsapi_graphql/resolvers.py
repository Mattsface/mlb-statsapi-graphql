"""Async root query resolvers translating library results into GraphQL values."""

import logging

from mlbstatsapi.exceptions import TheMlbStatsApiException
from pydantic import ValidationError
from strawberry.types import Info

from .context import Context
from .errors import require_positive_id, upstream_error
from .types import Player, Team

logger = logging.getLogger(__name__)


async def resolve_team(info: Info[Context, None], id: int) -> Team | None:
    require_positive_id(id)
    try:
        team = await info.context.mlb.get_team(id)
    except (TheMlbStatsApiException, ValidationError) as exc:
        logger.warning("MLB team lookup failed for team %s", id, exc_info=True)
        raise upstream_error() from exc

    if team is None:
        return None
    return Team(id=team.id, name=team.name, abbreviation=team.abbreviation)


async def resolve_player(info: Info[Context, None], id: int) -> Player | None:
    require_positive_id(id)
    try:
        person = await info.context.mlb.get_person(id)
    except (TheMlbStatsApiException, ValidationError) as exc:
        logger.warning("MLB player lookup failed for player %s", id, exc_info=True)
        raise upstream_error() from exc

    if person is None:
        return None
    return Player(id=person.id, full_name=person.full_name)
