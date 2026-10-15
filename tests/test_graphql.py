from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from mlbstatsapi import AsyncMlb
from mlbstatsapi.exceptions import MlbDecodeError, MlbHttpError, MlbTimeoutError
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
    MlbTimeoutError("private transport detail"),
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
