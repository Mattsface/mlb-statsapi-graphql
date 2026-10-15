"""The small public GraphQL model, independent of the upstream model."""

import strawberry


@strawberry.type
class Team:
    id: int
    name: str | None
    abbreviation: str | None
