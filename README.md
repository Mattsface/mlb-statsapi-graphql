# MLB Stats API GraphQL

> **Work in Progress (WIP)** — An experimental, actively developed GraphQL interface to MLB data. Intended for learning and local development; **not production-ready**.

A lightweight Python service that exposes selected MLB Stats API data through [GraphQL](https://graphql.org/). Built with [Strawberry](https://strawberry.rocks/) and [FastAPI](https://fastapi.tiangolo.com/), using [python-mlb-statsapi](https://github.com/zero-sum-seattle/python-mlb-statsapi) as its asynchronous upstream client.

Instead of building separate REST calls for a team and its active roster, request only the fields you need in a single GraphQL operation. The service resolves those fields through the existing Python library; it is **not** a replacement for or fork of that library.

![Baseball stadium — MLB Stats API project](https://user-images.githubusercontent.com/2068393/203456246-dfdbdf0f-1e43-4329-aaa9-1c4008f9800d.jpg)

## Current capabilities

- **Team lookup** by MLB team ID: `id`, `name`, and `abbreviation`
- **Person lookup** by MLB person ID: `id` and `fullName` (the upstream endpoint may include non-players)
- **Active team rosters** with nested player and position fields, loaded only when requested
- **Async upstream access** with a shared per-process `AsyncMlb` client and HTTP connection pool
- **Request-scoped DataLoaders** that deduplicate repeated team, person, and active-roster lookups
- **Query safeguards** for depth, cost, aliases, and document size
- **Client-safe GraphQL errors** and an offline test suite

**Not included yet:** authentication, deployment configuration, rate limiting, bounded upstream concurrency, production metrics, mutations, historical rosters, or a comprehensive MLB GraphQL schema.

## Quick start

**Requirements:** Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/zero-sum-seattle/mlb-statsapi-graphql.git
cd mlb-statsapi-graphql

uv python install 3.12
uv sync --locked --python 3.12
uv run uvicorn mlb_statsapi_graphql.app:app --reload
```

Open **http://127.0.0.1:8000/graphql** to explore queries in GraphiQL. Live requests require outbound HTTPS access to `statsapi.mlb.com`.

### Example: team and active roster

```graphql
query {
  team(id: 136) {
    id
    name
    abbreviation
    roster {
      player {
        id
        fullName
      }
      position {
        abbreviation
      }
    }
  }
}
```

This requests the Seattle Mariners and their **current active roster**. Roster membership varies; it is not a historical or 40-man roster query.

### Example: individual person

```graphql
query {
  player(id: 605141) {
    id
    fullName
  }
}
```

You can also call the endpoint directly:

```bash
curl http://127.0.0.1:8000/graphql \
  -H 'Content-Type: application/json' \
  --data '{"query":"{ team(id: 136) { id name abbreviation } }"}'
```

A successful request returns a `data` object containing the selected fields. Missing teams or people resolve to `null`; GraphQL execution errors may still use HTTP 200, so clients should inspect the `errors` array.

## How it works

```text
GraphQL request
      |
      v
FastAPI / Strawberry
      |
      +-- Query validation and complexity limits
      |
      v
Request context + per-request DataLoaders
      |
      v
Shared AsyncMlb client (per application worker)
      |
      v
MLB Stats API
```

The application shares an asynchronous MLB client and connection pool for its lifetime. Each GraphQL request gets fresh DataLoaders, so repeated IDs within that request reuse a result **without retaining cached data across requests**. Roster results already contain player names, avoiding one person lookup per roster entry.

The DataLoaders **deduplicate**, but distinct IDs currently still require individual upstream calls. Concurrent calls are not the same as true HTTP batching.

### Resource limits

Defaults are intentionally simple and configurable:

| Setting | Default | Environment variable |
| --- | ---: | --- |
| Maximum query depth | 6 | `MLB_GRAPHQL_MAX_DEPTH` |
| Maximum estimated query cost | 100 | `MLB_GRAPHQL_MAX_COST` |
| Maximum aliases | 30 | `MLB_GRAPHQL_MAX_ALIASES` |
| Maximum document tokens | 1,000 | `MLB_GRAPHQL_MAX_TOKENS` |

The cost estimator currently charges **5** per distinct root team or person lookup and **10** per distinct requested team roster. These are relative weights, **not** exact request counts or latency predictions. Duplicate selections of the same ID are counted once to reflect DataLoader caching.

Example override:

```bash
MLB_GRAPHQL_MAX_COST=150 uv run uvicorn mlb_statsapi_graphql.app:app --reload
```

These controls limit individual operations; they do **not** provide rate limiting or enforce an application-wide limit on concurrent upstream calls.

### Error behavior

| Error code | Meaning |
| --- | --- |
| `BAD_USER_INPUT` | An ID must be a positive integer |
| `UPSTREAM_ERROR` | An MLB lookup or response failed |
| `QUERY_COMPLEXITY_LIMIT` | Estimated operation cost exceeds the configured limit |

Unexpected resolver errors are masked from clients and logged server-side. GraphQL syntax, validation, depth, alias, and token-limit errors may use standard GraphQL error messages rather than these codes.

## Development

Run the offline tests and build the package:

```bash
uv sync --locked
uv run --locked pytest
uv build
```

Tests mock the upstream `AsyncMlb` client; they do not require live MLB API access. GitHub Actions runs the test suite for pull requests and changes to `main`.

### Project layout

| Module | Responsibility |
| --- | --- |
| `app.py` | FastAPI application, GraphQL route, and client lifecycle |
| `schema.py` / `types.py` | GraphQL schema and public types |
| `resolvers.py` | Root query resolution |
| `context.py` / `loaders.py` | Request context and DataLoader caching |
| `complexity.py` / `settings.py` | Query cost estimation and configurable limits |
| `errors.py` | Shared client-safe error helpers |

Source files live under `src/mlb_statsapi_graphql/`; tests live under `tests/`.

## Roadmap

- [x] **M0** — GraphQL service foundation and team lookups
- [x] **M1** — Person queries and nested active rosters
- [x] **M1.1** — Input validation and error handling cleanup
- [x] **M2.1** — Request-scoped DataLoader caching
- [x] **M2.2** — Query depth, cost, alias, and token limits
- [ ] **M2.3** — Bounded upstream concurrency and observability
- [ ] **Future** — Assess broader queries, real batching where safe, operational hardening, and deployment

Roadmap items are goals, not delivery commitments. The project is evolving and breaking changes remain possible.

## Limitations and project status

This repository is a **WIP learning project**, not a production service. The GraphQL schema exposes a small subset of the capabilities of [python-mlb-statsapi](https://github.com/zero-sum-seattle/python-mlb-statsapi). Live responses depend on MLB availability and may change over time. Active roster data may be empty or unavailable; the upstream library may treat a roster 404 as an empty list.

If you add a new field that performs upstream I/O, **review its query-cost weight**; otherwise the existing estimator could undercount its work.

Feedback and contributions are welcome through GitHub issues and pull requests.

---

*Unofficial project; not affiliated with or endorsed by Major League Baseball.*
