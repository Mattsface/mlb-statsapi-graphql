"""Request-scoped DataLoaders over the shared AsyncMlb client.

A new Loaders instance is created for every GraphQL request (see context.py),
so its caches live exactly as long as one operation. Within that operation,
loading the same key twice returns the same pending future, so repeated or
aliased selections share one upstream call.

This is caching and deduplication, not backend batching: the upstream methods
used here fetch one entity per HTTP request, so a batch of distinct keys is
still one concurrent upstream call per key. See the README for why the
library's bulk people endpoint is not used.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from mlbstatsapi import AsyncMlb
from mlbstatsapi.exceptions import TheMlbStatsApiException
from mlbstatsapi.models.people import Person, Player
from mlbstatsapi.models.teams import Team
from pydantic import ValidationError
from strawberry.dataloader import DataLoader

logger = logging.getLogger(__name__)

# Library failures that resolvers report as UPSTREAM_ERROR.
UPSTREAM_EXCEPTIONS = (TheMlbStatsApiException, ValidationError)


async def _fetch_each[K, V](
    keys: list[K], fetch: Callable[[K], Awaitable[V]], what: str
) -> list[V | BaseException]:
    """Fetch every key concurrently, one upstream call per key.

    Exceptions are returned in place of values, so DataLoader fails only the
    futures for those keys: one failed ID never affects another. The failed
    future stays cached as an exception for the rest of the request, so a
    repeated selection sees the same error rather than an empty result.
    """
    results = await asyncio.gather(*(fetch(key) for key in keys), return_exceptions=True)
    for key, result in zip(keys, results):
        if isinstance(result, UPSTREAM_EXCEPTIONS):
            logger.warning("MLB %s lookup failed for %s", what, key, exc_info=result)
    return results


class Loaders:
    def __init__(self, mlb: AsyncMlb) -> None:
        self.team: DataLoader[int, Team | None] = DataLoader(
            lambda ids: _fetch_each(ids, mlb.get_team, "team")
        )
        self.person: DataLoader[int, Person | None] = DataLoader(
            lambda ids: _fetch_each(ids, mlb.get_person, "player")
        )
        self.active_roster: DataLoader[int, list[Player]] = DataLoader(
            lambda ids: _fetch_each(
                ids, lambda id: mlb.get_team_roster(id, rosterType="active"), "roster"
            )
        )
