"""Tests for /api/session/* endpoints.

Layer: REST API.
"""

from __future__ import annotations

import pytest


class TestPostSessionStart:
    def test_returns_200_with_valid_body(self, client):
        resp = client.post(
            "/api/session/start",
            json={"human_players": [{"name": "Alice"}], "bot_count": 2},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert "session_id" in body["data"]
        assert len(body["data"]["players"]) == 3  # 1 human + 2 bots

    def test_returns_player_ids(self, client):
        resp = client.post(
            "/api/session/start",
            json={"human_players": [{"name": "Alice"}], "bot_count": 1},
        )
        players = resp.get_json()["data"]["players"]
        for p in players:
            assert "player_id" in p
            assert "name" in p
            assert "is_bot" in p
            assert "starting_stack" in p

    def test_human_players_not_bot(self, client):
        resp = client.post(
            "/api/session/start",
            json={"human_players": [{"name": "Corey"}], "bot_count": 1},
        )
        players = resp.get_json()["data"]["players"]
        human = next(p for p in players if p["name"] == "Corey")
        assert human["is_bot"] is False

    def test_400_when_human_players_empty(self, client):
        resp = client.post(
            "/api/session/start",
            json={"human_players": [], "bot_count": 1},
        )
        assert resp.status_code == 400

    def test_400_when_no_json_body(self, client):
        resp = client.post("/api/session/start", data="not json",
                           content_type="text/plain")
        assert resp.status_code == 400

    def test_400_when_human_player_missing_name(self, client):
        resp = client.post(
            "/api/session/start",
            json={"human_players": [{}], "bot_count": 0},
        )
        assert resp.status_code == 400

    def test_success_envelope_always_present(self, client):
        resp = client.post(
            "/api/session/start",
            json={"human_players": [{"name": "X"}], "bot_count": 0},
        )
        body = resp.get_json()
        assert "success" in body
        assert "data" in body
        assert "error" in body
        assert "timestamp" in body

    def test_restarting_session_replaces_old_one(self, client):
        client.post(
            "/api/session/start",
            json={"human_players": [{"name": "A"}], "bot_count": 0},
        )
        resp = client.post(
            "/api/session/start",
            json={"human_players": [{"name": "B"}], "bot_count": 0},
        )
        assert resp.status_code == 200
        players = resp.get_json()["data"]["players"]
        names = [p["name"] for p in players]
        assert "B" in names
        assert "A" not in names


class TestPostSessionEnd:
    def test_returns_summary(self, client, started_session):
        resp = client.post("/api/session/end")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert "session_id" in body["data"]
        assert "hands_played" in body["data"]
        assert "final_balances" in body["data"]

    def test_409_when_no_session(self, client):
        resp = client.post("/api/session/end")
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["success"] is False
        assert body["error"]["code"] == "SESSION_NOT_STARTED"


class TestGetSessionCurrent:
    def test_returns_session_state(self, client, started_session):
        resp = client.get("/api/session/current")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert "session_id" in body["data"]
        assert "players" in body["data"]
        assert "balances" in body["data"]
        assert "hands_played" in body["data"]
        assert "hand_in_progress" in body["data"]

    def test_404_when_no_session(self, client):
        resp = client.get("/api/session/current")
        assert resp.status_code == 404

    def test_hand_in_progress_false_initially(self, client, started_session, player_headers):
        resp = client.get("/api/session/current")
        assert resp.get_json()["data"]["hand_in_progress"] is False
