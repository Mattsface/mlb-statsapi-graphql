"""FastAPI entry point and ownership of the asynchronous MLB client."""

from collections.abc import Callable
from contextlib import asynccontextmanager

import strawberry
from fastapi import FastAPI, Request
from mlbstatsapi import AsyncMlb
from strawberry.fastapi import GraphQLRouter

from .context import Context
from .schema import schema as default_schema


def create_app(
    mlb_factory: Callable[[], AsyncMlb] = AsyncMlb,
    schema: strawberry.Schema = default_schema,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mlb_factory() as mlb:
            app.state.mlb = mlb
            yield

    async def get_context(request: Request) -> Context:
        return Context(mlb=request.app.state.mlb)

    app = FastAPI(title="MLB Stats API GraphQL", lifespan=lifespan)
    app.include_router(
        GraphQLRouter(schema, context_getter=get_context, graphql_ide="graphiql"),
        prefix="/graphql",
    )
    return app


app = create_app()
