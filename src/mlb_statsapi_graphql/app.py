"""FastAPI entry point and ownership of the asynchronous MLB client."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import strawberry
from fastapi import FastAPI, Request
from mlbstatsapi import AsyncMlb
from strawberry.fastapi import GraphQLRouter

from .context import Context
from .schema import schema as default_schema
from .settings import UpstreamSettings


def create_app(
    mlb_factory: Callable[[], AsyncMlb] = AsyncMlb,
    schema: strawberry.Schema = default_schema,
    upstream_settings: UpstreamSettings | None = None,
) -> FastAPI:
    settings = (
        upstream_settings if upstream_settings is not None else UpstreamSettings.from_env()
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.upstream_semaphore = asyncio.Semaphore(settings.max_concurrency)
        async with mlb_factory() as mlb:
            app.state.mlb = mlb
            yield

    async def get_context(request: Request) -> AsyncIterator[Context]:
        context = Context(request.app.state.mlb, request.app.state.upstream_semaphore)
        try:
            yield context
        finally:
            await context.lookups.aclose()
            context.lookups.log_summary()

    app = FastAPI(title="MLB Stats API GraphQL", lifespan=lifespan)
    app.include_router(
        GraphQLRouter(schema, context_getter=get_context, graphql_ide="graphiql"),
        prefix="/graphql",
    )
    return app


app = create_app()
