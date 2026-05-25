"""Tests for /api/chips/* endpoints.

Layer: REST API.
"""

from __future__ import annotations

import pytest


class TestGetBalance:
    def test_401_missing_header(self, client, started_session):
        resp = client.get("/api/chips/balance")
        assert resp.status_code == 401

    def test_200_returns_balances(self, client, started_session, player_headers):
        resp = client.get("/api/chips/balance", headers=player_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        balances = body["data"]["balances"]
        assert isinstance(balances, dict)
        assert len(balances) > 0

    def test_balance_entry_has_required_fields(self, client, started_session, player_headers):
        resp = client.get("/api/chips/balance", headers=player_headers)
        balances = resp.get_json()["data"]["balances"]
        for player_id, info in balances.items():
            assert "name" in info
            assert "balance" in info
            assert "delta_this_session" in info

    def test_default_stack_assigned(self, client, started_session, player_headers):
        resp = client.get("/api/chips/balance", headers=player_headers)
        balances = resp.get_json()["data"]["balances"]
        for player_id, info in balances.items():
            assert info["balance"] > 0, "All players should have a positive starting balance"


class TestGetLedger:
    def test_401_missing_header(self, client, started_session):
        resp = client.get("/api/chips/ledger")
        assert resp.status_code == 401

    def test_200_returns_ledger(self, client, started_session, player_headers):
        resp = client.get("/api/chips/ledger", headers=player_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        data = body["data"]
        assert "entries" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

    def test_400_invalid_limit(self, client, started_session, player_headers):
        resp = client.get("/api/chips/ledger?limit=abc", headers=player_headers)
        assert resp.status_code == 400

    def test_pagination_defaults(self, client, started_session, player_headers):
        resp = client.get("/api/chips/ledger", headers=player_headers)
        data = resp.get_json()["data"]
        assert data["limit"] == 50
        assert data["offset"] == 0


class TestGetLedgerAll:
    def test_401_missing_header(self, client, started_session):
        resp = client.get("/api/chips/ledger/all")
        assert resp.status_code == 401

    def test_200_returns_all_ledger(self, client, started_session, player_headers):
        resp = client.get("/api/chips/ledger/all", headers=player_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        data = body["data"]
        assert "entries" in data
        assert "total" in data

    def test_entries_have_required_fields(self, client, started_session, player_headers):
        resp = client.get("/api/chips/ledger/all", headers=player_headers)
        entries = resp.get_json()["data"]["entries"]
        for entry in entries:
            assert "id" in entry
            assert "player_name" in entry
            assert "delta" in entry
            assert "balance" in entry
            assert "reason" in entry
