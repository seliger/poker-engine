"""Persistence Layer: SQLite connection and schema management.

Resolves the database file path from the environment, opens connections with
the correct settings (WAL journal mode, Row factory, foreign keys), and creates
the schema on first use.

All other persistence modules acquire connections via get_connection() and
pass them explicitly through function arguments. No global connection state
is maintained here.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "poker_engine" / "poker.db"

_IN_MEMORY = ":memory:"


class PersistenceError(Exception):
    """Raised when a database operation fails in an unrecoverable way."""


def resolve_db_path() -> Path:
    """Return the database file path from POKER_DB_PATH env var or the default location."""
    env = os.environ.get("POKER_DB_PATH")
    if env:
        return Path(env)
    return _DEFAULT_DB_PATH


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open and return a SQLite connection configured for production use.

    Settings applied:
    - sqlite3.Row factory so rows are accessible by column name.
    - WAL journal mode for safer concurrent reads.
    - Foreign key enforcement ON.

    Pass db_path=":memory:" to obtain an in-memory connection (useful in tests).
    Otherwise the parent directory is created automatically if absent.
    """
    if db_path is None:
        path_str = str(resolve_db_path())
        _ensure_db_dir(Path(path_str))
    elif str(db_path) == _IN_MEMORY:
        path_str = _IN_MEMORY
    else:
        path_str = str(db_path)
        _ensure_db_dir(Path(path_str))

    conn = sqlite3.connect(path_str)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_db_dir(path: Path) -> None:
    """Create the parent directory for the database file if it does not exist."""
    path.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS players (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    is_bot     INTEGER NOT NULL CHECK (is_bot IN (0, 1)),
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT    NOT NULL,
    ended_at    TEXT,
    deck_config TEXT    NOT NULL,
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS hands (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER REFERENCES sessions(id),
    variant      TEXT    NOT NULL,
    modifiers    TEXT    NOT NULL,
    dealer_id    INTEGER REFERENCES players(id),
    started_at   TEXT    NOT NULL,
    ended_at     TEXT,
    pot_total    INTEGER NOT NULL DEFAULT 0,
    deck_config  TEXT    NOT NULL,
    wild_ranks   TEXT,
    redeal_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chip_ledger (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   INTEGER NOT NULL REFERENCES players(id),
    hand_id     INTEGER REFERENCES hands(id),
    session_id  INTEGER REFERENCES sessions(id),
    delta       INTEGER NOT NULL,
    balance     INTEGER NOT NULL,
    reason      TEXT    NOT NULL,
    recorded_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS hand_players (
    hand_id        INTEGER NOT NULL REFERENCES hands(id),
    player_id      INTEGER NOT NULL REFERENCES players(id),
    starting_stack INTEGER NOT NULL,
    ending_stack   INTEGER NOT NULL,
    declaration    TEXT,
    cards_dealt    TEXT,
    best_hand      TEXT,
    won_high       INTEGER,
    won_low        INTEGER,
    PRIMARY KEY (hand_id, player_id)
);
"""


def initialize_schema(conn: sqlite3.Connection) -> None:
    """Create all tables if they do not already exist.

    Idempotent: safe to call on every startup or in tests with a fresh
    in-memory connection.
    """
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    logger.debug("Persistence schema initialized")
