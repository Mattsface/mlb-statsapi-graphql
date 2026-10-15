"""Request context: the shared MLB client plus this request's DataLoaders."""

from mlbstatsapi import AsyncMlb
from strawberry.fastapi import BaseContext

from .loaders import Loaders


class Context(BaseContext):
    def __init__(self, mlb: AsyncMlb) -> None:
        super().__init__()
        self.mlb = mlb
        # Built per request, so DataLoader caches never outlive one operation.
        self.loaders = Loaders(mlb)
