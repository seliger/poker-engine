"""Tests for backend/persistence/ledger.py."""

from __future__ import annotations

import sqlite3

import pytest

from backend.persistence.database import get_connection, initialize_schema
from backend.persistence.ledger import (
    get_player_balance,
    get_player_ledger,
    get_session_ledger,
    record_chip_movement,
)


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = get_connection(":memory:")
    initialize_schema(c)
    # Insert a player so foreign key constraints are satisfied.
    c.execute(
        "INSERT INTO players (name, is_bot, created_at) VALUES (?, ?, ?)",
        ("Alice", 0, "2026-01-01T00:00:00+00:00"),
    )
    c.execute(
        "INSERT INTO players (name, is_bot, created_at) VALUES (?, ?, ?)",
        ("Bob", 0, "2026-01-01T00:00:00+00:00"),
    )
    c.execute(
        "INSERT INTO sessions (started_at, deck_config) VALUES (?, ?)",
        ("2026-01-01T00:00:00+00:00", '{"variant":"STANDARD"}'),
    )
    c.execute(
        "INSERT INTO sessions (started_at, deck_config) VALUES (?, ?)",
        ("2026-01-02T00:00:00+00:00", '{"variant":"STANDARD"}'),
    )
    c.commit()
    yield c
    c.close()


def _player_id(conn: sqlite3.Connection, name: str) -> int:
    return int(conn.execute("SELECT id FROM players WHERE name=?", (name,)).fetchone()["id"])


def _session_id(conn: sqlite3.Connection, nth: int) -> int:
    rows = conn.execute("SELECT id FROM sessions ORDER BY id").fetchall()
    return int(rows[nth]["id"])


class TestRecordChipMovement:
    def test_returns_integer_id(self, conn: sqlite3.Connection) -> None:
        pid = _player_id(conn, "Alice")
        row_id = record_chip_movement(conn, pid, 100, 100, "top-up")
        assert isinstance(row_id, int)
        assert row_id > 0

    def test_stores_correct_values(self, conn: sqlite3.Connection) -> None:
        pid = _player_id(conn, "Alice")
        sid = _session_id(conn, 0)
        record_chip_movement(conn, pid, -25, 75, "ante", session_id=sid)
        row = conn.execute("SELECT * FROM chip_ledger WHERE player_id=?", (pid,)).fetchone()
        assert row["delta"] == -25
        assert row["balance"] == 75
        assert row["reason"] == "ante"
        assert row["session_id"] == sid
        assert row["hand_id"] is None

    def test_stores_hand_id(self, conn: sqlite3.Connection) -> None:
        pid = _player_id(conn, "Alice")
        sid = _session_id(conn, 0)
        conn.execute(
            "INSERT INTO hands (session_id, variant, modifiers, dealer_id, started_at, deck_config) VALUES (?,?,?,?,?,?)",
            (sid, "SEVEN_CARD_STUD", "[]", pid, "2026-01-01T00:00:00+00:00", "{}"),
        )
        conn.commit()
        hid = int(conn.execute("SELECT id FROM hands WHERE session_id=?", (sid,)).fetchone()["id"])
        record_chip_movement(conn, pid, 200, 300, "pot win", session_id=sid, hand_id=hid)
        row = conn.execute("SELECT * FROM chip_ledger WHERE player_id=?", (pid,)).fetchone()
        assert row["hand_id"] == hid

    def test_null_session_and_hand_allowed(self, conn: sqlite3.Connection) -> None:
        pid = _player_id(conn, "Alice")
        row_id = record_chip_movement(conn, pid, 500, 500, "initial top-up")
        row = conn.execute("SELECT * FROM chip_ledger WHERE id=?", (row_id,)).fetchone()
        assert row["session_id"] is None
        assert row["hand_id"] is None

    def test_sequential_ids_are_distinct(self, conn: sqlite3.Connection) -> None:
        pid = _player_id(conn, "Alice")
        id1 = record_chip_movement(conn, pid, 100, 100, "top-up")
        id2 = record_chip_movement(conn, pid, -10, 90, "ante")
        assert id1 != id2

    def test_recorded_at_is_set(self, conn: sqlite3.Connection) -> None:
        pid = _player_id(conn, "Alice")
        record_chip_movement(conn, pid, 100, 100, "top-up")
        row = conn.execute("SELECT recorded_at FROM chip_ledger WHERE player_id=?", (pid,)).fetchone()
        assert row["recorded_at"] is not None
        assert len(row["recorded_at"]) > 0


class TestGetPlayerBalance:
    def test_returns_zero_for_unknown_player(self, conn: sqlite3.Connection) -> None:
        assert get_player_balance(conn, 9999) == 0

    def test_returns_latest_balance(self, conn: sqlite3.Connection) -> None:
        pid = _player_id(conn, "Alice")
        record_chip_movement(conn, pid, 100, 100, "top-up")
        record_chip_movement(conn, pid, -10, 90, "ante")
        record_chip_movement(conn, pid, 250, 340, "pot win")
        assert get_player_balance(conn, pid) == 340

    def test_does_not_mix_players(self, conn: sqlite3.Connection) -> None:
        pid_a = _player_id(conn, "Alice")
        pid_b = _player_id(conn, "Bob")
        record_chip_movement(conn, pid_a, 100, 100, "top-up")
        record_chip_movement(conn, pid_b, 200, 200, "top-up")
        assert get_player_balance(conn, pid_a) == 100
        assert get_player_balance(conn, pid_b) == 200

    def test_returns_int(self, conn: sqlite3.Connection) -> None:
        pid = _player_id(conn, "Alice")
        record_chip_movement(conn, pid, 50, 50, "top-up")
        result = get_player_balance(conn, pid)
        assert isinstance(result, int)


class TestGetSessionLedger:
    def test_returns_empty_for_no_entries(self, conn: sqlite3.Connection) -> None:
        sid = _session_id(conn, 0)
        assert get_session_ledger(conn, sid) == []

    def test_returns_rows_for_session(self, conn: sqlite3.Connection) -> None:
        pid = _player_id(conn, "Alice")
        sid = _session_id(conn, 0)
        record_chip_movement(conn, pid, 100, 100, "top-up", session_id=sid)
        record_chip_movement(conn, pid, -10, 90, "ante", session_id=sid)
        rows = get_session_ledger(conn, sid)
        assert len(rows) == 2

    def test_ordered_by_id(self, conn: sqlite3.Connection) -> None:
        pid = _player_id(conn, "Alice")
        sid = _session_id(conn, 0)
        record_chip_movement(conn, pid, 100, 100, "top-up", session_id=sid)
        record_chip_movement(conn, pid, -10, 90, "ante", session_id=sid)
        rows = get_session_ledger(conn, sid)
        assert rows[0]["id"] < rows[1]["id"]

    def test_excludes_other_session(self, conn: sqlite3.Connection) -> None:
        pid = _player_id(conn, "Alice")
        sid1 = _session_id(conn, 0)
        sid2 = _session_id(conn, 1)
        record_chip_movement(conn, pid, 100, 100, "top-up", session_id=sid1)
        record_chip_movement(conn, pid, 200, 200, "top-up", session_id=sid2)
        rows = get_session_ledger(conn, sid1)
        assert len(rows) == 1
        assert rows[0]["session_id"] == sid1

    def test_rows_are_dicts(self, conn: sqlite3.Connection) -> None:
        pid = _player_id(conn, "Alice")
        sid = _session_id(conn, 0)
        record_chip_movement(conn, pid, 100, 100, "top-up", session_id=sid)
        rows = get_session_ledger(conn, sid)
        assert isinstance(rows[0], dict)


class TestGetPlayerLedger:
    def test_returns_empty_for_no_entries(self, conn: sqlite3.Connection) -> None:
        pid = _player_id(conn, "Alice")
        assert get_player_ledger(conn, pid) == []

    def test_returns_all_rows_across_sessions(self, conn: sqlite3.Connection) -> None:
        pid = _player_id(conn, "Alice")
        sid1 = _session_id(conn, 0)
        sid2 = _session_id(conn, 1)
        record_chip_movement(conn, pid, 100, 100, "top-up", session_id=sid1)
        record_chip_movement(conn, pid, -10, 90, "ante", session_id=sid1)
        record_chip_movement(conn, pid, 200, 290, "top-up", session_id=sid2)
        rows = get_player_ledger(conn, pid)
        assert len(rows) == 3

    def test_ordered_by_id(self, conn: sqlite3.Connection) -> None:
        pid = _player_id(conn, "Alice")
        record_chip_movement(conn, pid, 100, 100, "top-up")
        record_chip_movement(conn, pid, -10, 90, "ante")
        rows = get_player_ledger(conn, pid)
        assert rows[0]["id"] < rows[1]["id"]

    def test_excludes_other_player(self, conn: sqlite3.Connection) -> None:
        pid_a = _player_id(conn, "Alice")
        pid_b = _player_id(conn, "Bob")
        record_chip_movement(conn, pid_a, 100, 100, "top-up")
        record_chip_movement(conn, pid_b, 200, 200, "top-up")
        rows = get_player_ledger(conn, pid_a)
        assert len(rows) == 1
        assert rows[0]["player_id"] == pid_a
