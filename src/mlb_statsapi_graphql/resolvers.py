"""Async functions translating library results into GraphQL values."""

import logging

from graphql import GraphQLError
from mlbstatsapi.exceptions import TheMlbStatsApiException
from strawberry.types import Info

from .context import Context
from .types import Team

logger = logging.getLogger(__name__)


async def resolve_team(info: Info[Context, None], id: int) -> Team | None:
    try:
        team = await info.context.mlb.get_team(id)
    except TheMlbStatsApiException as exc:
        logger.warning("MLB team lookup failed for team %s", id, exc_info=True)
        raise GraphQLError(
            "The MLB service is currently unavailable. Please try again later.",
            extensions={"code": "UPSTREAM_ERROR"},
        ) from exc

    if team is None:
        return None
    return Team(id=team.id, name=team.name, abbreviation=team.abbreviation)
