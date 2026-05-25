"""Shared fixtures for REST API tests.

Creates a Flask test client backed by an in-memory SQLite database so tests
are fully isolated from the filesystem and from each other.
"""

from __future__ import annotations

import pytest

from backend.app import create_app


@pytest.fixture()
def app():
    """Flask application with in-memory SQLite."""
    application = create_app(db_path=":memory:", testing=True)
    application.config["TESTING"] = True
    yield application
    application.game_manager.close()


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture()
def started_session(client):
    """Start a session and return the first human player_id."""
    resp = client.post(
        "/api/session/start",
        json={"human_players": [{"name": "Tester"}], "bot_count": 1},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    human = next(p for p in data["data"]["players"] if not p["is_bot"])
    return human["player_id"]


@pytest.fixture()
def player_headers(started_session):
    """X-Player-ID header dict for the human test player."""
    return {"X-Player-ID": started_session}


@pytest.fixture()
def active_hand(client, player_headers):
    """Start hands in a loop until one stays active.

    In a 2-player Seven Card Stud game, if the bot holds the bring-in and
    folds immediately, the hand auto-completes during start_hand. This
    fixture retries until the human has legal actions to take.
    """
    for _ in range(20):
        state_check = client.get("/api/hand/state", headers=player_headers)
        if state_check.status_code == 200:
            return  # already active

        resp = client.post(
            "/api/hand/start",
            json={"variant": "SEVEN_CARD_STUD", "modifiers": []},
            headers=player_headers,
        )
        if resp.status_code not in (200, 409):
            pytest.fail(f"Unexpected start_hand status: {resp.status_code} {resp.get_json()}")

        state_check = client.get("/api/hand/state", headers=player_headers)
        if state_check.status_code == 200:
            return

    pytest.skip("Could not get an active hand after 20 retries (bot wins every bring-in)")
