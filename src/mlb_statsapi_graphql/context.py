"""Request context: the shared MLB client is supplied by the application."""

from mlbstatsapi import AsyncMlb
from strawberry.fastapi import BaseContext


class Context(BaseContext):
    def __init__(self, mlb: AsyncMlb) -> None:
        super().__init__()
        self.mlb = mlb
