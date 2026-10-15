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
- `context.py` makes that client available to resolvers through request context,
  together with a fresh set of DataLoaders for each request.
- `loaders.py` defines the request-scoped team, person, and active-roster
  DataLoaders (see M2.1 below).
- `schema.py` defines nullable root `Query.team` and `Query.player` fields.
- `resolvers.py` holds the root resolvers: it validates the ID, asynchronously
  calls `await info.context.loaders.team.load(id)` (which calls
  `get_team(id)` at most once per request), and maps the returned library
  model to the public GraphQL `Team` in `types.py`.
- `types.py` defines the GraphQL types, including the lazy `Team.roster` field
  resolver. `errors.py` holds the shared client-safe errors.

Imports flow one way: `app → schema → resolvers → types → errors/context → loaders`.
`types.py` never imports `resolvers.py`, so there is no circular import.

The installed library's 1.1.2 model was inspected: `id` is required, while `name`
and `abbreviation` are optional. Its default strict HTTP mode preserves 404 as
`None` and raises library exceptions for other upstream failures. The service
keeps those semantics. GraphQL field selection controls the response shape;
Each team lookup still fetches a complete upstream team model.

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
  - **M2.1:** Request-scoped caching with DataLoaders (below).

This service is intended for local development. GraphiQL is enabled; query
complexity controls are deferred to later milestones.

## M1: players and nested rosters

Look up a person by MLB ID:

```graphql
query {
  player(id: 605141) {
    id
    fullName
  }
}
```

```json
{"data":{"player":{"id":605141,"fullName":"Mookie Betts"}}}
```

A missing player returns `{"data":{"player":null}}`. `Player` deliberately
exposes just `id` and nullable `fullName`, which are present on both upstream
person and roster models. The person endpoint can also return coaches and
umpires; this milestone does not filter by person category.

Follow the roster relationship from a team:

```graphql
query {
  team(id: 136) {
    id
    name
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

Illustrative response with one entry (the actual list and membership change):

```json
{
  "data": {
    "team": {
      "id": 136,
      "name": "Seattle Mariners",
      "roster": [
        {
          "player": {"id": 677594, "fullName": "Julio Rodríguez"},
          "position": {"abbreviation": "CF"}
        }
      ]
    }
  }
}
```

### How nested resolution works

Strawberry first runs the root `team` resolver, using the existing shared async
client from request context. It then resolves the selected fields on that Team.
`id` and `name` read values already fetched. `roster` has its own async field
resolver, which calls `get_team_roster(team_id, rosterType="active")` only when
selected. So `{ team(id: 136) { id name } }` makes one team request; adding
`roster` makes one additional roster request. A skipped roster field or a missing
team makes no roster request.

The upstream 1.1.2 roster parser flattens each entry's `person` into a library
`Player`, with the position stored as `primary_position`. We map this into explicit
GraphQL `RosterEntry`, `Player`, and `Position` types. Names and IDs already come
with the roster, so selecting nested `player` fields never calls `get_person`.
Field selection controls which resolvers run and the JSON shape; it does not
reduce the payload downloaded for an individual upstream request. In M1, repeating a
relationship under different aliases issued multiple calls; M2.1 deduplicates
them within a request.

With REST, a client would usually call a team endpoint and then a roster endpoint
and combine their results itself. GraphQL describes that relationship in one
query and returns a matching nested response; the server still makes those
upstream REST requests through the library. Nesting does not mean all related
data is fetched automatically.

### Availability and errors

M1 exposes the current **active** roster only, with no season, date, hydration,
or roster-type arguments. It is not the 40-man roster or a historical roster.
Membership and roster size follow MLB’s current response and can vary outside
the regular season. An empty upstream roster returns `[]`. The installed library also returns `[]`
for a roster 404, so these cases cannot be distinguished through its public
method. Other HTTP failures, timeouts, transport errors, invalid JSON, and model
validation failures become safe `UPSTREAM_ERROR` errors, never empty rosters.

The roster field is nullable: if its lookup fails, the team ID and name still
resolve, while `roster` is null and the error path is `["team", "roster"]`.
Player lookup failures similarly make `player` null. Internal exception details
are logged only on the server. An unavailable position becomes null and a missing
name becomes `fullName: null`. A present upstream Position requires all its
attributes, including abbreviation; malformed partial positions fail model
validation before reaching the resolver. Likewise, upstream roster entries
require an ID, link, jersey number, and status, even though our schema only
exposes a subset. We do not fabricate missing required data or alter the library.

The offline suite now covers players, empty and populated rosters, optional data,
nested field selection, skipped fields, lazy resolution, partial error responses,
and the original M0 behavior, using real upstream models and a mocked async client.

To validate packaging as well as tests:

```bash
uv build
```

## M1.1: input validation and errors

`team(id:)` and `player(id:)` require a positive ID. Zero or negative IDs are
rejected before any upstream request; the field is null and the error has
`extensions.code: "BAD_USER_INPUT"`:

```json
{
  "data": {"team": null},
  "errors": [{
    "message": "Argument 'id' must be a positive integer.",
    "path": ["team"],
    "extensions": {"code": "BAD_USER_INPUT"}
  }]
}
```

Error codes:

- `BAD_USER_INPUT`: the client sent an invalid argument; fix the request.
- `UPSTREAM_ERROR`: the MLB service failed or returned unusable data; retry later.

Any other exception is a server bug. Strawberry logs it with its traceback,
and its `MaskErrors` extension replaces the client-facing message with
`"Unexpected error."`, so internal details are not exposed. Query validation
errors (such as unknown fields) are not masked.

## M2.1: request-scoped caching with DataLoaders

### What a DataLoader does

A GraphQL resolver only knows about its own field. When a query selects the
same entity several times (aliases, repeated nested fields), each resolver
would normally make its own upstream call. A DataLoader sits between resolvers
and the data source: resolvers call `loader.load(key)` instead of the client,
and the loader:

1. **Caches** a future per key. A second `load(136)` returns the same pending
   or completed future, so it never reaches the upstream again.
2. **Collects** the distinct keys requested during one event-loop tick and
   hands them to a single *load function* as a list.

This project uses Strawberry's built-in `strawberry.dataloader.DataLoader`;
no new dependency is added. `loaders.py` defines three loaders:

| Loader | Key | Upstream call per key |
| --- | --- | --- |
| `team` | team ID | `get_team(id)` |
| `person` | person ID | `get_person(id)` |
| `active_roster` | team ID | `get_team_roster(id, rosterType="active")` |

### Where loaders live and why they are request-scoped

The shared `AsyncMlb` client is still opened once in the FastAPI lifespan. The
loaders are not: `get_context` builds a new `Context` for every GraphQL HTTP
request, and `Context.__init__` builds a new `Loaders(mlb)`. Root resolvers use
`info.context.loaders.team` / `.person`; `Team.roster` uses
`info.context.loaders.active_roster`.

The cache must not outlive the request because:

- **Freshness:** rosters change; a process-wide cache would serve stale data
  forever, since a DataLoader has no expiry.
- **Memory:** the cache map only grows; per request it is discarded with the context.
- **Failure isolation:** a failed lookup is cached *as a failure* for the rest of
  its request. A new request must try again, not replay an old error.

Within one request this is exactly what we want: every part of the response
sees the same snapshot of each entity.

### Duplicate aliases

```graphql
query {
  first: team(id: 136) { name roster { player { fullName } } }
  second: team(id: 136) { name roster { player { fullName } } }
}
```

Both `team` resolvers call `loaders.team.load(136)`; the second receives the
first's future. Both `roster` resolvers then call `loaders.active_roster.load(136)`
and share one roster fetch. The roster already includes player names, so
`get_person` is never called. Both aliases receive identical, correct data.

### Upstream call counts

Measured with a mocked client, before (M1.1) and after (M2.1):

| Query | Before | After |
| --- | --- | --- |
| Two `team(id: 136)` aliases, each with `roster` (above) | 2 × `get_team`, 2 × `get_team_roster` | 1 × `get_team`, 1 × `get_team_roster` |
| Three `team(id: 136)` aliases | 3 × `get_team` | 1 × `get_team` |
| Two `player(id: 605141)` aliases | 2 × `get_person` | 1 × `get_person` |
| One team with two aliased `roster` fields | 2 × `get_team_roster` | 1 × `get_team_roster` |
| `team(id: 136)` and `team(id: 147)` | 2 × `get_team` | 2 × `get_team` (different keys) |
| One team with `roster` | 1 + 1 | 1 + 1 (no change) |
| The same query sent as two HTTP requests | 2 × each | 2 × each (no shared cache) |

`test_upstream_call_counts` and the other M2.1 tests in `tests/test_graphql.py`
assert these numbers using a small `upstream_calls(mlb)` helper, which reads
`await_count` from the mocked `AsyncMlb` methods. No production metrics are added.

### Caching versus batching

- **Caching / deduplication** means the *same* key is fetched once. This is what
  M2.1 delivers.
- **Batching** means *different* keys are fetched in one upstream request, such
  as `GET /people?personIds=1,2,3` instead of three `GET /people/{id}` calls.

The load functions receive a list of distinct keys, but they call the
per-entity method once per key, concurrently (`asyncio.gather`). Two different
team IDs are still two HTTP requests to MLB, just issued in parallel. That is
not backend batching, and this project does not describe it as such.

What the installed library (python-mlb-statsapi 1.1.2) offers:

- **Teams:** no fetch-by-many-IDs method. `get_teams(sport_id)` returns every
  team in a sport, which is a different query rather than a batch.
- **Rosters:** one team per call; no bulk method.
- **People:** `get_persons(person_ids)` calls `GET /people?personIds=...`, a
  genuine bulk endpoint. It is deliberately not used yet:
  - Its error handling collapses any 4xx for the whole batch into `[]`, so one
    unknown ID in a batch could become indistinguishable from "all missing",
    turning valid players into `null` instead of reporting an error. That
    behaviour could not be verified offline.
  - Missing IDs would have to be inferred from absent entries, changing the
    current `get_person` semantics (a 404 → `null`).
  - In today's schema, distinct person IDs only appear as separate root
    `player(id:)` fields; roster players already come with names, so the gain
    is small.

  Switching the `person` loader's load function to `get_persons` is the
  natural next step if a query shape appears that loads many players by ID.

### Error behaviour

Errors are unchanged from M1.1:

- Non-positive IDs return `BAD_USER_INPUT` before any loader is called.
- Library failures (`TheMlbStatsApiException`, `ValidationError`) are returned by
  the load function for that key only, logged once per upstream call, and
  converted by each resolver into its own `UPSTREAM_ERROR` with its own path.
- Other exceptions are still masked as `"Unexpected error."`.
- `None` from the library (not found) is cached as `None`; fields stay nullable.
- An empty roster is cached as `[]`; a failed roster is cached as an *error*,
  never as `[]`.
- Each key has its own future, so a failure for team 147 does not affect team
  136, and a failed `roster` does not null its team's `name`.

### Known limitations

- Distinct IDs are not batched into one upstream request (see above).
- A failure is shared by every selection of that key within the request; there
  is no retry inside a request.
- The cache is per request only. Two clients asking for the same team at the
  same moment still make two upstream calls. A shared cache with expiry would
  be a separate, later decision.
- Upstream call counts are verified in tests with mocks; there is no runtime
  request-count metric.
