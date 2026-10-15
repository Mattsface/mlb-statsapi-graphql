from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from mlbstatsapi import AsyncMlb
from mlbstatsapi.exceptions import (
    MlbDecodeError, MlbHttpError, MlbTimeoutError, MlbTransportError,
)
from mlbstatsapi.models.people import Person, Player
from pydantic import ValidationError
from mlbstatsapi.models.teams import Team

from mlb_statsapi_graphql.app import create_app


@pytest.fixture
def mlb():
    client = AsyncMock(spec=AsyncMlb)
    client.__aenter__.return_value = client
    client.get_team.return_value = Team(
        id=136, link="/api/v1/teams/136", name="Seattle Mariners", abbreviation="SEA"
    )
    return client


@pytest.fixture
def api(mlb):
    with TestClient(create_app(mlb_factory=lambda: mlb)) as client:
        yield client
    mlb.__aenter__.assert_awaited_once()
    mlb.__aexit__.assert_awaited_once()


def test_successful_team_lookup(api, mlb):
    response = api.post("/graphql", json={"query": "{ team(id: 136) { id name abbreviation } }"})
    assert response.status_code == 200
    assert response.json() == {"data": {"team": {
        "id": 136, "name": "Seattle Mariners", "abbreviation": "SEA"
    }}}
    mlb.get_team.assert_awaited_once_with(136)


def test_team_not_found(api, mlb):
    mlb.get_team.return_value = None
    response = api.post("/graphql", json={"query": "{ team(id: 999999) { id } }"})
    assert response.json() == {"data": {"team": None}}
    mlb.get_team.assert_awaited_once_with(999999)


def test_field_selection(api):
    response = api.post("/graphql", json={"query": "{ team(id: 136) { abbreviation } }"})
    assert response.json() == {"data": {"team": {"abbreviation": "SEA"}}}


@pytest.mark.parametrize("error", [
    MlbTimeoutError("private timeout detail"),
    MlbTransportError("private transport detail"),
    MlbHttpError(503, "private response detail"),
    MlbDecodeError("private payload detail"),
])
def test_upstream_error(api, mlb, error):
    mlb.get_team.side_effect = error
    response = api.post("/graphql", json={"query": "{ team(id: 136) { id } }"})
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == {"team": None}
    assert len(body["errors"]) == 1
    assert body["errors"][0]["message"] == (
        "The MLB service is currently unavailable. Please try again later."
    )
    assert body["errors"][0]["extensions"] == {"code": "UPSTREAM_ERROR"}
    assert body["errors"][0]["path"] == ["team"]
    assert "private" not in response.text


def test_optional_upstream_attributes(api, mlb):
    mlb.get_team.return_value = Team(id=136, link="/api/v1/teams/136")
    response = api.post("/graphql", json={"query": "{ team(id: 136) { id name abbreviation } }"})
    assert response.json() == {"data": {"team": {
        "id": 136, "name": None, "abbreviation": None
    }}}


def test_invalid_field_is_rejected_without_upstream_call(api, mlb):
    response = api.post("/graphql", json={"query": "{ team(id: 136) { unknownField } }"})
    assert response.json()["errors"]
    mlb.get_team.assert_not_awaited()


def test_graphql_ide(api):
    response = api.get("/graphql", headers={"accept": "text/html"})
    assert response.status_code == 200
    assert "graphiql" in response.text.lower()


ROSTER_QUERY = """{ team(id: 136) {
    id name roster { player { id fullName } position { abbreviation } }
} }"""


@pytest.fixture
def roster_player():
    return Player(
        id=605141, link="/api/v1/people/605141", fullName="Mookie Betts",
        jerseyNumber="50", status={"code": "A", "description": "Active"},
        position={"code": "6", "name": "Shortstop", "type": "Infielder", "abbreviation": "SS"},
    )


def test_player_lookup(api, mlb):
    mlb.get_person.return_value = Person(
        id=605141, link="/api/v1/people/605141", fullName="Mookie Betts"
    )
    response = api.post("/graphql", json={"query": "{ player(id: 605141) { id fullName } }"})
    assert response.json() == {"data": {"player": {"id": 605141, "fullName": "Mookie Betts"}}}
    mlb.get_person.assert_awaited_once_with(605141)
    mlb.get_team.assert_not_awaited()
    mlb.get_team_roster.assert_not_awaited()


def test_player_not_found(api, mlb):
    mlb.get_person.return_value = None
    response = api.post("/graphql", json={"query": "{ player(id: 999999) { id } }"})
    assert response.json() == {"data": {"player": None}}
    mlb.get_person.assert_awaited_once_with(999999)


def test_player_optional_name(api, mlb):
    mlb.get_person.return_value = Person(id=605141, link="/api/v1/people/605141")
    response = api.post("/graphql", json={"query": "{ player(id: 605141) { fullName } }"})
    assert response.json() == {"data": {"player": {"fullName": None}}}


def test_roster(api, mlb, roster_player):
    mlb.get_team_roster.return_value = [roster_player]
    response = api.post("/graphql", json={"query": ROSTER_QUERY})
    assert response.json() == {"data": {"team": {
        "id": 136, "name": "Seattle Mariners", "roster": [{
            "player": {"id": 605141, "fullName": "Mookie Betts"},
            "position": {"abbreviation": "SS"},
        }],
    }}}
    mlb.get_team.assert_awaited_once_with(136)
    mlb.get_team_roster.assert_awaited_once_with(136, rosterType="active")
    mlb.get_person.assert_not_awaited()


def test_empty_roster(api, mlb):
    mlb.get_team_roster.return_value = []
    response = api.post("/graphql", json={"query": ROSTER_QUERY})
    assert response.json()["data"]["team"]["roster"] == []
    assert "errors" not in response.json()


def test_optional_roster_fields(api, mlb, roster_player):
    roster_player.full_name = None
    roster_player.primary_position = None
    mlb.get_team_roster.return_value = [roster_player]
    response = api.post("/graphql", json={"query": ROSTER_QUERY})
    assert response.json()["data"]["team"]["roster"] == [{
        "player": {"id": 605141, "fullName": None}, "position": None,
    }]
    assert "errors" not in response.json()


def test_nested_field_selection(api, mlb, roster_player):
    mlb.get_team_roster.return_value = [roster_player]
    response = api.post("/graphql", json={"query": """{
        team(id: 136) { roster { player { fullName } } }
    }"""})
    assert response.json() == {"data": {"team": {"roster": [
        {"player": {"fullName": "Mookie Betts"}}
    ]}}}
    mlb.get_team_roster.assert_awaited_once_with(136, rosterType="active")
    mlb.get_person.assert_not_awaited()


@pytest.mark.parametrize("query", [
    "{ team(id: 136) { id name } }",
    "{ team(id: 136) { id roster @skip(if: true) { player { id } } } }",
])
def test_roster_is_lazy(api, mlb, query):
    response = api.post("/graphql", json={"query": query})
    assert "errors" not in response.json()
    mlb.get_team.assert_awaited_once_with(136)
    mlb.get_team_roster.assert_not_awaited()
    mlb.get_person.assert_not_awaited()


def test_missing_team_does_not_fetch_roster(api, mlb):
    mlb.get_team.return_value = None
    response = api.post("/graphql", json={"query": ROSTER_QUERY})
    assert response.json() == {"data": {"team": None}}
    mlb.get_team_roster.assert_not_awaited()


@pytest.mark.parametrize("field", ["player", "roster"])
@pytest.mark.parametrize("error", [
    MlbTimeoutError("private timeout"), MlbTransportError("private transport"),
    MlbHttpError(503, "private HTTP"), MlbDecodeError("private JSON"),
    ValidationError.from_exception_data("Person", [
        {"type": "missing", "loc": ("id",), "input": {"private": "payload"}},
    ]),
])
def test_new_upstream_errors(api, mlb, field, error):
    if field == "player":
        mlb.get_person.side_effect = error
        query = "{ player(id: 605141) { id } team(id: 136) { name } }"
        data = {"player": None, "team": {"name": "Seattle Mariners"}}
        path = ["player"]
    else:
        mlb.get_team_roster.side_effect = error
        query = ROSTER_QUERY
        data = {"team": {"id": 136, "name": "Seattle Mariners", "roster": None}}
        path = ["team", "roster"]
    response = api.post("/graphql", json={"query": query})
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == data
    assert len(body["errors"]) == 1
    assert body["errors"][0]["extensions"] == {"code": "UPSTREAM_ERROR"}
    assert body["errors"][0]["path"] == path
    assert body["errors"][0]["message"] == (
        "The MLB service is currently unavailable. Please try again later."
    )
    assert "private" not in response.text


# M1.1: input validation, error sanitization, and module structure.

@pytest.mark.parametrize("field", ["team", "player"])
@pytest.mark.parametrize("id", [0, -1, -136])
def test_non_positive_id_is_rejected_without_upstream_call(api, mlb, field, id):
    response = api.post("/graphql", json={"query": f"{{ {field}(id: {id}) {{ id }} }}"})
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == {field: None}
    assert body["errors"] == [{
        "message": "Argument 'id' must be a positive integer.",
        "locations": [{"line": 1, "column": 3}],
        "path": [field],
        "extensions": {"code": "BAD_USER_INPUT"},
    }]
    mlb.get_team.assert_not_awaited()
    mlb.get_person.assert_not_awaited()
    mlb.get_team_roster.assert_not_awaited()


def test_non_positive_id_via_variable(api, mlb):
    response = api.post("/graphql", json={
        "query": "query($id: Int!) { team(id: $id) { roster { player { id } } } }",
        "variables": {"id": -1},
    })
    body = response.json()
    assert body["data"] == {"team": None}
    assert [e["extensions"] for e in body["errors"]] == [{"code": "BAD_USER_INPUT"}]
    mlb.get_team.assert_not_awaited()
    mlb.get_team_roster.assert_not_awaited()


def test_invalid_and_valid_ids_in_one_query(api, mlb):
    response = api.post("/graphql", json={
        "query": "{ bad: team(id: 0) { id } good: team(id: 136) { id } }"
    })
    body = response.json()
    assert body["data"] == {"bad": None, "good": {"id": 136}}
    assert [e["extensions"]["code"] for e in body["errors"]] == ["BAD_USER_INPUT"]
    mlb.get_team.assert_awaited_once_with(136)


def test_minimum_positive_id_is_forwarded(api, mlb):
    mlb.get_person.return_value = None
    response = api.post("/graphql", json={"query": "{ player(id: 1) { id } }"})
    assert response.json() == {"data": {"player": None}}
    mlb.get_person.assert_awaited_once_with(1)


@pytest.mark.parametrize("query, method", [
    ("{ team(id: 136) { id } }", "get_team"),
    ("{ player(id: 605141) { id } }", "get_person"),
    (ROSTER_QUERY, "get_team_roster"),
])
def test_unexpected_exception_is_sanitized(api, mlb, caplog, query, method):
    getattr(mlb, method).side_effect = RuntimeError("secret internal detail")
    response = api.post("/graphql", json={"query": query})
    assert response.status_code == 200
    body = response.json()
    assert len(body["errors"]) == 1
    assert body["errors"][0]["message"] == "Unexpected error."
    assert "extensions" not in body["errors"][0]
    assert "secret" not in response.text
    assert "RuntimeError" not in response.text
    # The original exception and traceback are still logged server-side.
    assert any(
        "secret internal detail" in str(record.exc_info[1])
        for record in caplog.records if record.exc_info
    )


def test_upstream_error_is_not_masked(api, mlb):
    mlb.get_person.side_effect = MlbTimeoutError("private")
    response = api.post("/graphql", json={"query": "{ player(id: 605141) { id } }"})
    assert response.json()["errors"][0]["extensions"] == {"code": "UPSTREAM_ERROR"}


def test_validation_errors_are_not_masked(api):
    response = api.post("/graphql", json={"query": "{ team(id: 136) { unknownField } }"})
    assert "unknownField" in response.json()["errors"][0]["message"]


def test_public_schema_is_unchanged():
    from mlb_statsapi_graphql.schema import schema

    assert schema.as_str() == """\
type Player {
  id: Int!
  fullName: String
}

type Position {
  abbreviation: String
}

type Query {
  player(id: Int!): Player
  team(id: Int!): Team
}

type RosterEntry {
  player: Player!
  position: Position
}

type Team {
  id: Int!
  name: String
  abbreviation: String
  roster: [RosterEntry!]
}"""


def test_types_module_does_not_import_resolvers():
    import ast
    from pathlib import Path

    import mlb_statsapi_graphql.types as types_module

    tree = ast.parse(Path(types_module.__file__).read_text())
    imported = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not imported & {"resolvers", "schema", "app"}
