"""Tests for backend/persistence/history.py."""

from __future__ import annotations

import sqlite3

import pytest

from backend.persistence.database import get_connection, initialize_schema
from backend.persistence.history import (
    end_hand,
    end_session,
    get_current_session,
    get_hand,
    get_hand_players,
    get_or_create_player,
    get_player,
    get_session,
    list_players,
    record_hand_player,
    start_hand,
    start_session,
    update_hand_wild_ranks,
)


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = get_connection(":memory:")
    initialize_schema(c)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_player(conn: sqlite3.Connection, name: str = "Alice", is_bot: bool = False) -> int:
    return get_or_create_player(conn, name, is_bot)


def _add_session(conn: sqlite3.Connection) -> int:
    return start_session(conn, '{"variant":"STANDARD"}')


def _add_hand(conn: sqlite3.Connection, session_id: int, dealer_id: int) -> int:
    return start_hand(
        conn, session_id, "SEVEN_CARD_STUD", "[]", dealer_id, '{"variant":"STANDARD"}'
    )


# ---------------------------------------------------------------------------
# Player operations
# ---------------------------------------------------------------------------

class TestGetOrCreatePlayer:
    def test_creates_new_player(self, conn: sqlite3.Connection) -> None:
        pid = get_or_create_player(conn, "Alice", False)
        assert isinstance(pid, int)
        assert pid > 0

    def test_returns_same_id_on_second_call(self, conn: sqlite3.Connection) -> None:
        pid1 = get_or_create_player(conn, "Alice", False)
        pid2 = get_or_create_player(conn, "Alice", False)
        assert pid1 == pid2

    def test_different_names_get_different_ids(self, conn: sqlite3.Connection) -> None:
        pid_a = get_or_create_player(conn, "Alice", False)
        pid_b = get_or_create_player(conn, "Bob", False)
        assert pid_a != pid_b

    def test_is_bot_stored_for_human(self, conn: sqlite3.Connection) -> None:
        pid = get_or_create_player(conn, "Alice", False)
        row = conn.execute("SELECT is_bot FROM players WHERE id=?", (pid,)).fetchone()
        assert row["is_bot"] == 0

    def test_is_bot_stored_for_bot(self, conn: sqlite3.Connection) -> None:
        pid = get_or_create_player(conn, "RobotOne", True)
        row = conn.execute("SELECT is_bot FROM players WHERE id=?", (pid,)).fetchone()
        assert row["is_bot"] == 1

    def test_created_at_is_set(self, conn: sqlite3.Connection) -> None:
        pid = get_or_create_player(conn, "Alice", False)
        row = conn.execute("SELECT created_at FROM players WHERE id=?", (pid,)).fetchone()
        assert row["created_at"] is not None


class TestGetPlayer:
    def test_returns_none_for_unknown_id(self, conn: sqlite3.Connection) -> None:
        assert get_player(conn, 9999) is None

    def test_returns_dict_for_known_player(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        result = get_player(conn, pid)
        assert isinstance(result, dict)
        assert result["name"] == "Alice"

    def test_dict_contains_expected_keys(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        result = get_player(conn, pid)
        assert result is not None
        assert set(result.keys()) == {"id", "name", "is_bot", "created_at"}


class TestListPlayers:
    def test_returns_empty_list_when_no_players(self, conn: sqlite3.Connection) -> None:
        assert list_players(conn) == []

    def test_returns_all_players(self, conn: sqlite3.Connection) -> None:
        _add_player(conn, "Alice")
        _add_player(conn, "Bob")
        rows = list_players(conn)
        assert len(rows) == 2

    def test_ordered_by_name(self, conn: sqlite3.Connection) -> None:
        _add_player(conn, "Zelda")
        _add_player(conn, "Alice")
        _add_player(conn, "Mallory")
        rows = list_players(conn)
        names = [r["name"] for r in rows]
        assert names == sorted(names)

    def test_rows_are_dicts(self, conn: sqlite3.Connection) -> None:
        _add_player(conn)
        rows = list_players(conn)
        assert isinstance(rows[0], dict)


# ---------------------------------------------------------------------------
# Session operations
# ---------------------------------------------------------------------------

class TestStartSession:
    def test_returns_positive_integer(self, conn: sqlite3.Connection) -> None:
        sid = start_session(conn, '{"variant":"STANDARD"}')
        assert isinstance(sid, int)
        assert sid > 0

    def test_session_row_exists(self, conn: sqlite3.Connection) -> None:
        sid = start_session(conn, '{"variant":"STANDARD"}')
        row = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        assert row is not None

    def test_stores_deck_config(self, conn: sqlite3.Connection) -> None:
        deck_json = '{"variant":"WITH_ORBS"}'
        sid = start_session(conn, deck_json)
        row = conn.execute("SELECT deck_config FROM sessions WHERE id=?", (sid,)).fetchone()
        assert row["deck_config"] == deck_json

    def test_stores_notes(self, conn: sqlite3.Connection) -> None:
        sid = start_session(conn, '{}', notes="Friday night game")
        row = conn.execute("SELECT notes FROM sessions WHERE id=?", (sid,)).fetchone()
        assert row["notes"] == "Friday night game"

    def test_ended_at_is_null_on_start(self, conn: sqlite3.Connection) -> None:
        sid = start_session(conn, '{}')
        row = conn.execute("SELECT ended_at FROM sessions WHERE id=?", (sid,)).fetchone()
        assert row["ended_at"] is None

    def test_multiple_sessions_get_distinct_ids(self, conn: sqlite3.Connection) -> None:
        sid1 = start_session(conn, '{}')
        sid2 = start_session(conn, '{}')
        assert sid1 != sid2


class TestEndSession:
    def test_sets_ended_at(self, conn: sqlite3.Connection) -> None:
        sid = _add_session(conn)
        end_session(conn, sid)
        row = conn.execute("SELECT ended_at FROM sessions WHERE id=?", (sid,)).fetchone()
        assert row["ended_at"] is not None

    def test_only_affects_target_session(self, conn: sqlite3.Connection) -> None:
        sid1 = _add_session(conn)
        sid2 = _add_session(conn)
        end_session(conn, sid1)
        row2 = conn.execute("SELECT ended_at FROM sessions WHERE id=?", (sid2,)).fetchone()
        assert row2["ended_at"] is None


class TestGetSession:
    def test_returns_none_for_unknown_id(self, conn: sqlite3.Connection) -> None:
        assert get_session(conn, 9999) is None

    def test_returns_dict_for_known_session(self, conn: sqlite3.Connection) -> None:
        sid = _add_session(conn)
        result = get_session(conn, sid)
        assert isinstance(result, dict)
        assert result["id"] == sid

    def test_dict_contains_expected_keys(self, conn: sqlite3.Connection) -> None:
        sid = _add_session(conn)
        result = get_session(conn, sid)
        assert result is not None
        assert set(result.keys()) == {"id", "started_at", "ended_at", "deck_config", "notes"}


class TestGetCurrentSession:
    def test_returns_none_when_no_sessions(self, conn: sqlite3.Connection) -> None:
        assert get_current_session(conn) is None

    def test_returns_none_when_all_ended(self, conn: sqlite3.Connection) -> None:
        sid = _add_session(conn)
        end_session(conn, sid)
        assert get_current_session(conn) is None

    def test_returns_open_session(self, conn: sqlite3.Connection) -> None:
        sid = _add_session(conn)
        result = get_current_session(conn)
        assert result is not None
        assert result["id"] == sid

    def test_returns_most_recent_open_session(self, conn: sqlite3.Connection) -> None:
        sid1 = _add_session(conn)
        sid2 = _add_session(conn)
        result = get_current_session(conn)
        assert result is not None
        assert result["id"] == sid2

    def test_ignores_ended_sessions(self, conn: sqlite3.Connection) -> None:
        sid1 = _add_session(conn)
        end_session(conn, sid1)
        sid2 = _add_session(conn)
        result = get_current_session(conn)
        assert result is not None
        assert result["id"] == sid2


# ---------------------------------------------------------------------------
# Hand operations
# ---------------------------------------------------------------------------

class TestStartHand:
    def test_returns_positive_integer(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        assert isinstance(hid, int)
        assert hid > 0

    def test_hand_row_exists(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        row = conn.execute("SELECT * FROM hands WHERE id=?", (hid,)).fetchone()
        assert row is not None

    def test_stores_variant(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = start_hand(conn, sid, "CHICAGO", "[]", pid, "{}")
        row = conn.execute("SELECT variant FROM hands WHERE id=?", (hid,)).fetchone()
        assert row["variant"] == "CHICAGO"

    def test_stores_modifiers(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        mods = '["DIRTY_BITCH"]'
        hid = start_hand(conn, sid, "SEVEN_CARD_STUD", mods, pid, "{}")
        row = conn.execute("SELECT modifiers FROM hands WHERE id=?", (hid,)).fetchone()
        assert row["modifiers"] == mods

    def test_ended_at_is_null_on_start(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        row = conn.execute("SELECT ended_at FROM hands WHERE id=?", (hid,)).fetchone()
        assert row["ended_at"] is None

    def test_pot_total_defaults_to_zero(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        row = conn.execute("SELECT pot_total FROM hands WHERE id=?", (hid,)).fetchone()
        assert row["pot_total"] == 0

    def test_redeal_count_defaults_to_zero(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        row = conn.execute("SELECT redeal_count FROM hands WHERE id=?", (hid,)).fetchone()
        assert row["redeal_count"] == 0


class TestEndHand:
    def test_sets_ended_at(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        end_hand(conn, hid, pot_total=150)
        row = conn.execute("SELECT ended_at FROM hands WHERE id=?", (hid,)).fetchone()
        assert row["ended_at"] is not None

    def test_sets_pot_total(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        end_hand(conn, hid, pot_total=250)
        row = conn.execute("SELECT pot_total FROM hands WHERE id=?", (hid,)).fetchone()
        assert row["pot_total"] == 250

    def test_sets_redeal_count(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        end_hand(conn, hid, pot_total=0, redeal_count=2)
        row = conn.execute("SELECT redeal_count FROM hands WHERE id=?", (hid,)).fetchone()
        assert row["redeal_count"] == 2

    def test_sets_wild_ranks(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        end_hand(conn, hid, pot_total=0, wild_ranks_json='[12]')
        row = conn.execute("SELECT wild_ranks FROM hands WHERE id=?", (hid,)).fetchone()
        assert row["wild_ranks"] == '[12]'

    def test_wild_ranks_defaults_to_null(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        end_hand(conn, hid, pot_total=0)
        row = conn.execute("SELECT wild_ranks FROM hands WHERE id=?", (hid,)).fetchone()
        assert row["wild_ranks"] is None


class TestGetHand:
    def test_returns_none_for_unknown_id(self, conn: sqlite3.Connection) -> None:
        assert get_hand(conn, 9999) is None

    def test_returns_dict_for_known_hand(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        result = get_hand(conn, hid)
        assert isinstance(result, dict)
        assert result["id"] == hid

    def test_dict_contains_all_columns(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        result = get_hand(conn, hid)
        assert result is not None
        expected_keys = {
            "id", "session_id", "variant", "modifiers", "dealer_id",
            "started_at", "ended_at", "pot_total", "deck_config",
            "wild_ranks", "redeal_count",
        }
        assert set(result.keys()) == expected_keys


class TestUpdateHandWildRanks:
    def test_updates_wild_ranks(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        update_hand_wild_ranks(conn, hid, '[12]')
        row = conn.execute("SELECT wild_ranks FROM hands WHERE id=?", (hid,)).fetchone()
        assert row["wild_ranks"] == '[12]'

    def test_overwrites_previous_wild_ranks(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        update_hand_wild_ranks(conn, hid, '[12]')
        update_hand_wild_ranks(conn, hid, '[1]')
        row = conn.execute("SELECT wild_ranks FROM hands WHERE id=?", (hid,)).fetchone()
        assert row["wild_ranks"] == '[1]'


# ---------------------------------------------------------------------------
# Hand-player operations
# ---------------------------------------------------------------------------

class TestRecordHandPlayer:
    def test_inserts_row(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        record_hand_player(conn, hid, pid, starting_stack=1000, ending_stack=1200)
        rows = conn.execute(
            "SELECT * FROM hand_players WHERE hand_id=? AND player_id=?", (hid, pid)
        ).fetchall()
        assert len(rows) == 1

    def test_stores_stacks(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        record_hand_player(conn, hid, pid, starting_stack=500, ending_stack=750)
        row = conn.execute(
            "SELECT starting_stack, ending_stack FROM hand_players WHERE hand_id=? AND player_id=?",
            (hid, pid),
        ).fetchone()
        assert row["starting_stack"] == 500
        assert row["ending_stack"] == 750

    def test_stores_declaration(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        record_hand_player(conn, hid, pid, starting_stack=0, ending_stack=0, declaration="HIGH")
        row = conn.execute(
            "SELECT declaration FROM hand_players WHERE hand_id=? AND player_id=?",
            (hid, pid),
        ).fetchone()
        assert row["declaration"] == "HIGH"

    def test_stores_cards_dealt_json(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        cards_json = '["7♣","7♥","A♠"]'
        record_hand_player(conn, hid, pid, starting_stack=0, ending_stack=0, cards_dealt_json=cards_json)
        row = conn.execute(
            "SELECT cards_dealt FROM hand_players WHERE hand_id=? AND player_id=?",
            (hid, pid),
        ).fetchone()
        assert row["cards_dealt"] == cards_json

    def test_stores_best_hand_json(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        best = '{"hand_rank":"ONE_PAIR","display_name":"One Pair, Sevens"}'
        record_hand_player(conn, hid, pid, starting_stack=0, ending_stack=0, best_hand_json=best)
        row = conn.execute(
            "SELECT best_hand FROM hand_players WHERE hand_id=? AND player_id=?",
            (hid, pid),
        ).fetchone()
        assert row["best_hand"] == best

    def test_stores_won_high_and_won_low(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        record_hand_player(conn, hid, pid, starting_stack=0, ending_stack=0, won_high=True, won_low=False)
        row = conn.execute(
            "SELECT won_high, won_low FROM hand_players WHERE hand_id=? AND player_id=?",
            (hid, pid),
        ).fetchone()
        assert row["won_high"] == 1
        assert row["won_low"] == 0

    def test_won_high_low_none_when_not_applicable(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        record_hand_player(conn, hid, pid, starting_stack=0, ending_stack=0)
        row = conn.execute(
            "SELECT won_high, won_low FROM hand_players WHERE hand_id=? AND player_id=?",
            (hid, pid),
        ).fetchone()
        assert row["won_high"] is None
        assert row["won_low"] is None

    def test_idempotent_on_second_call(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        record_hand_player(conn, hid, pid, starting_stack=1000, ending_stack=900)
        record_hand_player(conn, hid, pid, starting_stack=1000, ending_stack=1300)
        rows = conn.execute(
            "SELECT * FROM hand_players WHERE hand_id=? AND player_id=?", (hid, pid)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["ending_stack"] == 1300

    def test_multiple_players_in_same_hand(self, conn: sqlite3.Connection) -> None:
        pid_a = _add_player(conn, "Alice")
        pid_b = _add_player(conn, "Bob")
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid_a)
        record_hand_player(conn, hid, pid_a, starting_stack=1000, ending_stack=1200)
        record_hand_player(conn, hid, pid_b, starting_stack=1000, ending_stack=800)
        rows = conn.execute(
            "SELECT * FROM hand_players WHERE hand_id=?", (hid,)
        ).fetchall()
        assert len(rows) == 2


class TestGetHandPlayers:
    def test_returns_empty_for_no_players(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        assert get_hand_players(conn, hid) == []

    def test_returns_all_players_for_hand(self, conn: sqlite3.Connection) -> None:
        pid_a = _add_player(conn, "Alice")
        pid_b = _add_player(conn, "Bob")
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid_a)
        record_hand_player(conn, hid, pid_a, starting_stack=1000, ending_stack=1200)
        record_hand_player(conn, hid, pid_b, starting_stack=1000, ending_stack=800)
        rows = get_hand_players(conn, hid)
        assert len(rows) == 2

    def test_ordered_by_player_id(self, conn: sqlite3.Connection) -> None:
        pid_a = _add_player(conn, "Alice")
        pid_b = _add_player(conn, "Bob")
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid_a)
        record_hand_player(conn, hid, pid_b, starting_stack=1000, ending_stack=800)
        record_hand_player(conn, hid, pid_a, starting_stack=1000, ending_stack=1200)
        rows = get_hand_players(conn, hid)
        assert rows[0]["player_id"] < rows[1]["player_id"]

    def test_rows_are_dicts(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid = _add_hand(conn, sid, pid)
        record_hand_player(conn, hid, pid, starting_stack=0, ending_stack=0)
        rows = get_hand_players(conn, hid)
        assert isinstance(rows[0], dict)

    def test_excludes_other_hand(self, conn: sqlite3.Connection) -> None:
        pid = _add_player(conn)
        sid = _add_session(conn)
        hid1 = _add_hand(conn, sid, pid)
        hid2 = _add_hand(conn, sid, pid)
        record_hand_player(conn, hid1, pid, starting_stack=1000, ending_stack=1200)
        record_hand_player(conn, hid2, pid, starting_stack=1200, ending_stack=900)
        rows = get_hand_players(conn, hid1)
        assert len(rows) == 1
        assert rows[0]["hand_id"] == hid1
