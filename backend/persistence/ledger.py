"""Persistence Layer: chip ledger operations.

Every chip movement is recorded as a row in chip_ledger with a reason field.
The balance field is the player's running total after the delta is applied,
allowing point-in-time balance reconstruction without summing the full ledger.

All functions accept an open sqlite3.Connection. Callers are responsible for
acquiring connections via database.get_connection() and closing them when done.

No game logic or evaluation belongs here.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def record_chip_movement(
    conn: sqlite3.Connection,
    player_id: int,
    delta: int,
    balance: int,
    reason: str,
    session_id: int | None = None,
    hand_id: int | None = None,
) -> int:
    """Insert a chip_ledger row and return its assigned id.

    Parameters
    ----------
    player_id:
        The player whose stack changed.
    delta:
        Positive = chips gained (pot win, stack-up), negative = chips lost
        (ante, call, cascade payment).
    balance:
        The player's running chip total *after* this delta is applied.
    reason:
        Human-readable explanation: e.g. "ante", "pot win", "cascade payment",
        "take-last-up cost".
    session_id:
        The session this movement belongs to.  May be None for out-of-session
        adjustments (rare).
    hand_id:
        The hand this movement belongs to.  None for session-level adjustments
        such as initial top-up.
    """
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        """
        INSERT INTO chip_ledger
            (player_id, hand_id, session_id, delta, balance, reason, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (player_id, hand_id, session_id, delta, balance, reason, now),
    )
    conn.commit()
    logger.debug(
        "Ledger: player_id=%d delta=%+d balance=%d reason=%r",
        player_id, delta, balance, reason,
    )
    row_id: int = cursor.lastrowid  # type: ignore[assignment]
    return row_id


def get_player_balance(conn: sqlite3.Connection, player_id: int) -> int:
    """Return the player's current chip balance from the most recent ledger row.

    Returns 0 if the player has no ledger entries yet.
    """
    row = conn.execute(
        "SELECT balance FROM chip_ledger WHERE player_id = ? ORDER BY id DESC LIMIT 1",
        (player_id,),
    ).fetchone()
    return int(row["balance"]) if row else 0


def get_session_ledger(
    conn: sqlite3.Connection, session_id: int
) -> list[dict[str, Any]]:
    """Return all chip_ledger rows for a session, ordered by insertion id."""
    rows = conn.execute(
        "SELECT * FROM chip_ledger WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_player_ledger(
    conn: sqlite3.Connection, player_id: int
) -> list[dict[str, Any]]:
    """Return all chip_ledger rows for a player across all sessions, ordered by id."""
    rows = conn.execute(
        "SELECT * FROM chip_ledger WHERE player_id = ? ORDER BY id",
        (player_id,),
    ).fetchall()
    return [dict(r) for r in rows]
