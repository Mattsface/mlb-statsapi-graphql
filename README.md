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
- `schema.py` defines nullable root `Query.team` and `Query.player` fields.
- `resolvers.py` asynchronously calls `await info.context.mlb.get_team(id)` and
  maps the returned library model to the public GraphQL `Team` in `types.py`.

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

This service is intended for local development. GraphiQL is enabled; caching, batching,
and query complexity controls are deferred to later milestones.

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
reduce the payload downloaded for an individual upstream request. Repeating a
relationship under different aliases may issue multiple calls; batching and
caching remain outside M1.

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
