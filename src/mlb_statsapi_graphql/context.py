"""Request context: the shared MLB client plus this request's DataLoaders."""

import asyncio

from mlbstatsapi import AsyncMlb
from strawberry.fastapi import BaseContext

from .loaders import Loaders
from .upstream import RequestLookups


class Context(BaseContext):
    def __init__(self, mlb: AsyncMlb, semaphore: asyncio.Semaphore) -> None:
        super().__init__()
        self.mlb = mlb
        # Built per request, so DataLoader caches never outlive one operation.
        self.lookups = RequestLookups(semaphore)
        self.loaders = Loaders(mlb, self.lookups)
