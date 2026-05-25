"""REST API Layer: request validation helpers.

All validation raises APIError directly so callers need no conditional logic.
The Flask error handler in app.py catches APIError and returns the correct
HTTP status with the error envelope.

Layer: REST API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flask import Request

from .errors import (
    APIError,
    MISSING_PLAYER_ID,
    UNKNOWN_PLAYER,
)

if TYPE_CHECKING:
    from .game_manager import GameManager


def require_player_id(request: Request, game_manager: "GameManager") -> str:
    """Extract X-Player-ID header and confirm the player is in the current session.

    Returns the player_id string on success. Raises APIError(401) otherwise.
    """
    player_id = request.headers.get("X-Player-ID")
    if not player_id:
        raise APIError(401, MISSING_PLAYER_ID, "X-Player-ID header is required.")
    if not game_manager.is_known_player(player_id):
        raise APIError(
            401,
            UNKNOWN_PLAYER,
            f"Player {player_id!r} is not in the current session.",
        )
    return player_id


def require_json(request: Request) -> dict[str, Any]:
    """Parse and return the JSON request body. Raises APIError(400) if absent or invalid."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError(400, "INVALID_REQUEST", "Request body must be a JSON object.")
    return data
