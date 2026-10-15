"""Async functions translating library results into GraphQL values."""

import logging

from graphql import GraphQLError
from mlbstatsapi.exceptions import TheMlbStatsApiException
from pydantic import ValidationError
from strawberry.types import Info

from .context import Context
from .types import Player, Position, RosterEntry, Team

logger = logging.getLogger(__name__)


async def resolve_team(info: Info[Context, None], id: int) -> Team | None:
    try:
        team = await info.context.mlb.get_team(id)
    except (TheMlbStatsApiException, ValidationError) as exc:
        logger.warning("MLB team lookup failed for team %s", id, exc_info=True)
        raise GraphQLError(
            "The MLB service is currently unavailable. Please try again later.",
            extensions={"code": "UPSTREAM_ERROR"},
        ) from exc

    if team is None:
        return None
    return Team(id=team.id, name=team.name, abbreviation=team.abbreviation)


async def resolve_player(info: Info[Context, None], id: int) -> Player | None:
    try:
        person = await info.context.mlb.get_person(id)
    except (TheMlbStatsApiException, ValidationError) as exc:
        logger.warning("MLB player lookup failed for player %s", id, exc_info=True)
        raise GraphQLError(
            "The MLB service is currently unavailable. Please try again later.",
            extensions={"code": "UPSTREAM_ERROR"},
        ) from exc

    if person is None:
        return None
    return Player(id=person.id, full_name=person.full_name)


async def resolve_roster(info: Info[Context, None], team_id: int) -> list[RosterEntry]:
    try:
        roster = await info.context.mlb.get_team_roster(team_id, rosterType="active")
    except (TheMlbStatsApiException, ValidationError) as exc:
        logger.warning("MLB roster lookup failed for team %s", team_id, exc_info=True)
        raise GraphQLError(
            "The MLB service is currently unavailable. Please try again later.",
            extensions={"code": "UPSTREAM_ERROR"},
        ) from exc

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
