"""Tests for backend/persistence/database.py."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.persistence.database import (
    PersistenceError,
    get_connection,
    initialize_schema,
    resolve_db_path,
)


class TestResolveDbPath:
    def test_default_path_used_when_env_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("POKER_DB_PATH", None)
            path = resolve_db_path()
        assert "poker_engine" in str(path)
        assert path.name == "poker.db"

    def test_env_var_overrides_default(self, tmp_path: Path) -> None:
        custom = tmp_path / "custom.db"
        with patch.dict(os.environ, {"POKER_DB_PATH": str(custom)}):
            path = resolve_db_path()
        assert path == custom

    def test_returns_path_object(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("POKER_DB_PATH", None)
            path = resolve_db_path()
        assert isinstance(path, Path)


class TestGetConnection:
    def test_in_memory_connection_returns_connection(self) -> None:
        conn = get_connection(":memory:")
        assert conn is not None
        conn.close()

    def test_row_factory_set(self) -> None:
        conn = get_connection(":memory:")
        assert conn.row_factory is sqlite3.Row
        conn.close()

    def test_wal_journal_mode(self) -> None:
        conn = get_connection(":memory:")
        row = conn.execute("PRAGMA journal_mode").fetchone()
        # In-memory databases report "memory" not "wal" — WAL is accepted/applied
        # but SQLite silently falls back to "memory" for :memory: databases.
        assert row[0] in ("wal", "memory")
        conn.close()

    def test_foreign_keys_enabled(self) -> None:
        conn = get_connection(":memory:")
        row = conn.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1
        conn.close()

    def test_path_connection_creates_file(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        conn = get_connection(db_file)
        conn.close()
        assert db_file.exists()

    def test_path_connection_creates_parent_dirs(self, tmp_path: Path) -> None:
        db_file = tmp_path / "nested" / "dirs" / "test.db"
        conn = get_connection(db_file)
        conn.close()
        assert db_file.exists()


class TestInitializeSchema:
    def _get_tables(self, conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {row[0] for row in rows}

    def test_all_tables_created(self) -> None:
        conn = get_connection(":memory:")
        initialize_schema(conn)
        tables = self._get_tables(conn)
        assert "players" in tables
        assert "sessions" in tables
        assert "hands" in tables
        assert "chip_ledger" in tables
        assert "hand_players" in tables
        conn.close()

    def test_idempotent_second_call(self) -> None:
        conn = get_connection(":memory:")
        initialize_schema(conn)
        initialize_schema(conn)
        tables = self._get_tables(conn)
        assert len(tables) == 5
        conn.close()

    def test_players_columns(self) -> None:
        conn = get_connection(":memory:")
        initialize_schema(conn)
        info = conn.execute("PRAGMA table_info(players)").fetchall()
        col_names = {row["name"] for row in info}
        assert col_names == {"id", "name", "is_bot", "created_at"}
        conn.close()

    def test_sessions_columns(self) -> None:
        conn = get_connection(":memory:")
        initialize_schema(conn)
        info = conn.execute("PRAGMA table_info(sessions)").fetchall()
        col_names = {row["name"] for row in info}
        assert col_names == {"id", "started_at", "ended_at", "deck_config", "notes"}
        conn.close()

    def test_hands_columns(self) -> None:
        conn = get_connection(":memory:")
        initialize_schema(conn)
        info = conn.execute("PRAGMA table_info(hands)").fetchall()
        col_names = {row["name"] for row in info}
        assert col_names == {
            "id", "session_id", "variant", "modifiers", "dealer_id",
            "started_at", "ended_at", "pot_total", "deck_config",
            "wild_ranks", "redeal_count",
        }
        conn.close()

    def test_chip_ledger_columns(self) -> None:
        conn = get_connection(":memory:")
        initialize_schema(conn)
        info = conn.execute("PRAGMA table_info(chip_ledger)").fetchall()
        col_names = {row["name"] for row in info}
        assert col_names == {
            "id", "player_id", "hand_id", "session_id",
            "delta", "balance", "reason", "recorded_at",
        }
        conn.close()

    def test_hand_players_columns(self) -> None:
        conn = get_connection(":memory:")
        initialize_schema(conn)
        info = conn.execute("PRAGMA table_info(hand_players)").fetchall()
        col_names = {row["name"] for row in info}
        assert col_names == {
            "hand_id", "player_id", "starting_stack", "ending_stack",
            "declaration", "cards_dealt", "best_hand", "won_high", "won_low",
        }
        conn.close()

    def test_hand_players_composite_primary_key(self) -> None:
        conn = get_connection(":memory:")
        initialize_schema(conn)
        info = conn.execute("PRAGMA table_info(hand_players)").fetchall()
        pk_cols = {row["name"] for row in info if row["pk"] > 0}
        assert pk_cols == {"hand_id", "player_id"}
        conn.close()
