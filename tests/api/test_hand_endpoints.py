"""Tests for /api/hand/* endpoints.

Layer: REST API.
"""

from __future__ import annotations

import pytest


class TestPostHandStart:
    def test_401_missing_player_id_header(self, client, started_session):
        resp = client.post(
            "/api/hand/start",
            json={"variant": "SEVEN_CARD_STUD", "modifiers": []},
        )
        assert resp.status_code == 401
        assert resp.get_json()["error"]["code"] == "MISSING_PLAYER_ID"

    def test_401_unknown_player_id(self, client, started_session):
        resp = client.post(
            "/api/hand/start",
            json={"variant": "SEVEN_CARD_STUD", "modifiers": []},
            headers={"X-Player-ID": "not-a-real-id"},
        )
        assert resp.status_code == 401
        assert resp.get_json()["error"]["code"] == "UNKNOWN_PLAYER"

    def test_200_starts_hand_successfully(self, client, started_session, player_headers):
        resp = client.post(
            "/api/hand/start",
            json={"variant": "SEVEN_CARD_STUD", "modifiers": []},
            headers=player_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert "hand_id" in body["data"]
        assert body["data"]["variant"] == "SEVEN_CARD_STUD"

    def test_400_invalid_variant(self, client, started_session, player_headers):
        resp = client.post(
            "/api/hand/start",
            json={"variant": "NOT_A_VARIANT", "modifiers": []},
            headers=player_headers,
        )
        assert resp.status_code in (400, 409)
        body = resp.get_json()
        assert body["success"] is False

    def test_400_missing_variant(self, client, started_session, player_headers):
        resp = client.post(
            "/api/hand/start",
            json={"modifiers": []},
            headers=player_headers,
        )
        assert resp.status_code == 400

    def test_409_hand_already_in_progress(self, client, started_session, player_headers, active_hand):
        resp = client.post(
            "/api/hand/start",
            json={"variant": "SEVEN_CARD_STUD", "modifiers": []},
            headers=player_headers,
        )
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "HAND_IN_PROGRESS"

    def test_response_has_envelope_shape(self, client, started_session, player_headers):
        resp = client.post(
            "/api/hand/start",
            json={"variant": "SEVEN_CARD_STUD", "modifiers": []},
            headers=player_headers,
        )
        body = resp.get_json()
        assert "success" in body
        assert "data" in body
        assert "error" in body
        assert "timestamp" in body


class TestGetHandState:
    def test_401_missing_header(self, client, started_session):
        resp = client.get("/api/hand/state")
        assert resp.status_code == 401

    def test_200_returns_player_view(self, client, started_session, player_headers, active_hand):
        resp = client.get("/api/hand/state", headers=player_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        data = body["data"]
        assert "hand_id" in data
        assert "phase" in data
        assert "my_cards" in data
        assert "other_players" in data
        assert "pot_total" in data
        assert "my_stack" in data
        assert "legal_actions" in data

    def test_no_hole_cards_in_other_players(self, client, started_session, player_headers, active_hand):
        resp = client.get("/api/hand/state", headers=player_headers)
        data = resp.get_json()["data"]
        for opp in data["other_players"]:
            for card in opp["visible_cards"]:
                assert card["is_face_up"] is True, (
                    "Opponent face-down cards must not appear in player view"
                )

    def test_409_no_hand_in_progress(self, client, started_session, player_headers):
        resp = client.get("/api/hand/state", headers=player_headers)
        assert resp.status_code == 409


class TestPostHandAction:
    def _get_legal_actions(self, client, player_headers):
        resp = client.get("/api/hand/state", headers=player_headers)
        if resp.status_code != 200:
            return []
        data = resp.get_json().get("data") or {}
        return data.get("legal_actions", [])

    def test_401_missing_header(self, client, started_session):
        resp = client.post(
            "/api/hand/action",
            json={"action_type": "CALL", "amount": 0},
        )
        assert resp.status_code == 401

    def test_400_missing_action_type(self, client, started_session, player_headers, active_hand):
        resp = client.post(
            "/api/hand/action",
            json={"amount": 0},
            headers=player_headers,
        )
        assert resp.status_code == 400

    def test_200_valid_action_accepted(self, client, started_session, player_headers, active_hand):
        legal = self._get_legal_actions(client, player_headers)
        if not legal:
            pytest.skip("No legal actions available")
        action_type = legal[0]["action_type"]
        amount = legal[0].get("min_amount") or 0
        resp = client.post(
            "/api/hand/action",
            json={"action_type": action_type, "amount": amount},
            headers=player_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["action_accepted"] is True

    def test_422_illegal_action(self, client, started_session, player_headers, active_hand):
        legal = self._get_legal_actions(client, player_headers)
        if not legal:
            pytest.skip("No legal actions available")
        # DRAW is never legal in Seven Card Stud
        all_types = {la["action_type"] for la in legal}
        if "DRAW" not in all_types:
            resp = client.post(
                "/api/hand/action",
                json={"action_type": "DRAW", "amount": 0},
                headers=player_headers,
            )
            assert resp.status_code == 422
            assert resp.get_json()["error"]["code"] == "ILLEGAL_ACTION"


class TestGetHandResult:
    def test_401_missing_header(self, client, started_session):
        resp = client.get("/api/hand/result")
        assert resp.status_code == 401

    def test_404_no_completed_hand(self, client, started_session, player_headers):
        resp = client.get("/api/hand/result", headers=player_headers)
        assert resp.status_code == 404
