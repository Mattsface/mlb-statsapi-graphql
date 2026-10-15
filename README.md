# MLB Stats API GraphQL

A small, educational GraphQL service built with Python 3.12+, Strawberry, and
FastAPI. It installs and consumes
[python-mlb-statsapi](https://github.com/zero-sum-seattle/python-mlb-statsapi)
with its `async` extra; the upstream library is not copied or modified.

## Run locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and then:

```bash
git clone https://github.com/Mattsface/mlb-statsapi-graphql.git
cd mlb-statsapi-graphql
uv python install 3.12
uv sync --locked --python 3.12
uv run uvicorn mlb_statsapi_graphql.app:app --reload
```

Open **http://127.0.0.1:8000/graphql** for the interactive GraphiQL IDE.
The server needs outbound HTTPS access to `statsapi.mlb.com` for actual lookups.
`uv.lock` records the tested dependencies; `uv sync --locked` installs the local
package and test dependencies into `.venv`.

## Queries

Paste this into the IDE:

```graphql
query {
  team(id: 136) {
    id
    name
    abbreviation
  }
}
```

Expected response (current MLB data may change):

```json
{
  "data": {
    "team": {
      "id": 136,
      "name": "Seattle Mariners",
      "abbreviation": "SEA"
    }
  }
}
```

GraphQL returns only requested fields. For example,
`{ team(id: 136) { abbreviation } }` returns
`{"data":{"team":{"abbreviation":"SEA"}}}`.

You can also send a POST request:

```bash
curl http://127.0.0.1:8000/graphql \
  -H 'Content-Type: application/json' \
  --data '{"query":"{ team(id: 136) { id name abbreviation } }"}'
```

A nonexistent team (for example, `team(id: 999999)`) returns
`{"data":{"team":null}}` without an error. A library transport, timeout, HTTP,
or decoding failure returns `data.team: null` plus an `errors` entry with a safe
message and `extensions.code: "UPSTREAM_ERROR"`. Upstream exception details are
logged server-side. GraphQL execution errors normally use HTTP 200, so clients
should inspect `errors`. `name` and `abbreviation` can be null when absent upstream.

## How it works

The package lives in `src/mlb_statsapi_graphql/`:

- `app.py` creates FastAPI, mounts Strawberry at `/graphql`, and opens one
  `AsyncMlb` client at startup using its async context manager. Shutdown closes
  the client and its HTTP connection pool.
- `context.py` makes that client available to resolvers through request context.
- `schema.py` defines the root `Query.team` field with a nullable result.
- `resolvers.py` asynchronously calls `await info.context.mlb.get_team(id)` and
  maps the returned library model to the public GraphQL `Team` in `types.py`.

The installed library's 1.1.2 model was inspected: `id` is required, while `name`
and `abbreviation` are optional. Its default strict HTTP mode preserves 404 as
`None` and raises library exceptions for other upstream failures. The service
keeps those semantics. GraphQL field selection controls the response shape;
M0 still fetches a complete upstream team model for each lookup.

Future query fields can reuse the same context and client. There is no database,
authentication, deployment infrastructure, or custom repository layer.
`create_app(mlb_factory=...)` allows tests to supply a mock without opening a real
HTTP client.

## Tests

```bash
uv sync --locked
uv run --locked pytest
```

All tests are offline: an `AsyncMock` replaces `AsyncMlb`, and fixtures use the
installed library's actual `Team` model. Tests exercise the `/graphql` route,
success, missing teams, selected fields, upstream failures, optional attributes,
invalid fields, the IDE, and application client lifecycle. GitHub Actions runs
the same test command on Python 3.12 for pull requests and pushes to `main`.

## Roadmap

- **M0:** Single team lookup.
- **M1:** Players, rosters, nested relationships.
- **M2:** Pagination, batching, caching, and query complexity.

M0 is intended for local development. GraphiQL is enabled; caching, batching,
and query complexity controls are deferred to later milestones.
