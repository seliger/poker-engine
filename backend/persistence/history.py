"""Persistence Layer: player, session, hand, and hand_players history.

Provides CRUD operations for the structural records of the game: who played,
which variant, when, and how chips moved at the hand boundary. Per-movement
audit records are written by the ledger module.

The JSON TEXT fields (deck_config, modifiers, wild_ranks, cards_dealt,
best_hand) are stored as serialised JSON strings. Callers are responsible for
serialising before passing and deserialising after reading.

All functions accept an open sqlite3.Connection. Callers acquire connections
via database.get_connection() and are responsible for closing them.

No game logic or evaluation belongs here.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Player operations
# ---------------------------------------------------------------------------

def get_or_create_player(
    conn: sqlite3.Connection,
    name: str,
    is_bot: bool,
) -> int:
    """Return the player_id for name, creating the record if it does not exist.

    Player identity is keyed on name. Calling this twice with the same name
    returns the same id both times.
    """
    row = conn.execute(
        "SELECT id FROM players WHERE name = ?",
        (name,),
    ).fetchone()
    if row:
        return int(row["id"])
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO players (name, is_bot, created_at) VALUES (?, ?, ?)",
        (name, int(is_bot), now),
    )
    conn.commit()
    player_id: int = cursor.lastrowid  # type: ignore[assignment]
    logger.debug("Created player %r (id=%d is_bot=%s)", name, player_id, is_bot)
    return player_id


def get_player(conn: sqlite3.Connection, player_id: int) -> dict[str, Any] | None:
    """Return the player row as a dict, or None if not found."""
    row = conn.execute(
        "SELECT * FROM players WHERE id = ?",
        (player_id,),
    ).fetchone()
    return dict(row) if row else None


def list_players(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all player rows ordered by name."""
    rows = conn.execute("SELECT * FROM players ORDER BY name").fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Session operations
# ---------------------------------------------------------------------------

def start_session(
    conn: sqlite3.Connection,
    deck_config_json: str,
    notes: str | None = None,
) -> int:
    """Create a new session record and return its id.

    deck_config_json: JSON-serialised DeckConfig (use DeckConfig.to_json()).
    """
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO sessions (started_at, deck_config, notes) VALUES (?, ?, ?)",
        (now, deck_config_json, notes),
    )
    conn.commit()
    session_id: int = cursor.lastrowid  # type: ignore[assignment]
    logger.debug("Session started: id=%d", session_id)
    return session_id


def end_session(conn: sqlite3.Connection, session_id: int) -> None:
    """Set ended_at on the session record to now."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE sessions SET ended_at = ? WHERE id = ?",
        (now, session_id),
    )
    conn.commit()
    logger.debug("Session ended: id=%d", session_id)


def get_session(
    conn: sqlite3.Connection, session_id: int
) -> dict[str, Any] | None:
    """Return the session row as a dict, or None if not found."""
    row = conn.execute(
        "SELECT * FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    return dict(row) if row else None


def get_current_session(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Return the most recently started session that has not yet ended.

    Returns None when all sessions are closed or when no sessions exist.
    """
    row = conn.execute(
        "SELECT * FROM sessions WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1",
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Hand operations
# ---------------------------------------------------------------------------

def start_hand(
    conn: sqlite3.Connection,
    session_id: int,
    variant: str,
    modifiers_json: str,
    dealer_id: int,
    deck_config_json: str,
) -> int:
    """Create a new hand record and return its id.

    variant: GameVariant.value string, e.g. "SEVEN_CARD_STUD".
    modifiers_json: JSON array of active modifier names, e.g. '[]' or '["DIRTY_BITCH"]'.
    deck_config_json: JSON-serialised DeckConfig.
    """
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        """
        INSERT INTO hands
            (session_id, variant, modifiers, dealer_id, started_at, deck_config)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, variant, modifiers_json, dealer_id, now, deck_config_json),
    )
    conn.commit()
    hand_id: int = cursor.lastrowid  # type: ignore[assignment]
    logger.debug("Hand started: id=%d variant=%s", hand_id, variant)
    return hand_id


def end_hand(
    conn: sqlite3.Connection,
    hand_id: int,
    pot_total: int,
    redeal_count: int = 0,
    wild_ranks_json: str | None = None,
) -> None:
    """Finalise a hand: set ended_at, pot_total, redeal_count, and wild_ranks."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE hands
        SET ended_at = ?, pot_total = ?, redeal_count = ?, wild_ranks = ?
        WHERE id = ?
        """,
        (now, pot_total, redeal_count, wild_ranks_json, hand_id),
    )
    conn.commit()
    logger.debug(
        "Hand ended: id=%d pot=%d redeals=%d", hand_id, pot_total, redeal_count
    )


def get_hand(conn: sqlite3.Connection, hand_id: int) -> dict[str, Any] | None:
    """Return the hand row as a dict, or None if not found."""
    row = conn.execute(
        "SELECT * FROM hands WHERE id = ?",
        (hand_id,),
    ).fetchone()
    return dict(row) if row else None


def update_hand_wild_ranks(
    conn: sqlite3.Connection,
    hand_id: int,
    wild_ranks_json: str,
) -> None:
    """Update the wild_ranks field on an in-progress hand.

    Called by the Game Layer when FollowTheQueenModifier changes the wild rank
    mid-hand, so the final wild rank state is persisted.
    """
    conn.execute(
        "UPDATE hands SET wild_ranks = ? WHERE id = ?",
        (wild_ranks_json, hand_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Hand-player operations
# ---------------------------------------------------------------------------

def record_hand_player(
    conn: sqlite3.Connection,
    hand_id: int,
    player_id: int,
    starting_stack: int,
    ending_stack: int,
    declaration: str | None = None,
    cards_dealt_json: str | None = None,
    best_hand_json: str | None = None,
    won_high: bool | None = None,
    won_low: bool | None = None,
) -> None:
    """Insert or replace the hand_players record for one player in one hand.

    Uses INSERT OR REPLACE so this function is idempotent: calling it twice
    with the same hand_id / player_id updates the row in place.

    cards_dealt_json: JSON array of card shorthand strings, e.g. '["7♣","7♥","A♠"]'.
    best_hand_json: JSON object with hand rank and display name, e.g.
        '{"hand_rank": "ONE_PAIR", "display_name": "One Pair, Sevens"}'.
    declaration: 'HIGH', 'LOW', or 'BOTH'; None when not applicable.
    won_high / won_low: True/False for high-low declare games; None otherwise.
    """
    conn.execute(
        """
        INSERT OR REPLACE INTO hand_players
            (hand_id, player_id, starting_stack, ending_stack,
             declaration, cards_dealt, best_hand, won_high, won_low)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hand_id,
            player_id,
            starting_stack,
            ending_stack,
            declaration,
            cards_dealt_json,
            best_hand_json,
            None if won_high is None else int(won_high),
            None if won_low is None else int(won_low),
        ),
    )
    conn.commit()


def get_hand_players(
    conn: sqlite3.Connection, hand_id: int
) -> list[dict[str, Any]]:
    """Return all hand_players rows for a hand, ordered by player_id."""
    rows = conn.execute(
        "SELECT * FROM hand_players WHERE hand_id = ? ORDER BY player_id",
        (hand_id,),
    ).fetchall()
    return [dict(r) for r in rows]
