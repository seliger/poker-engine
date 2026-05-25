"""REST API Layer: session management endpoints.

Blueprint prefix: /api/session

Endpoints:
    POST /start  — start a new session
    POST /end    — end the current session
    GET  /current — return current session state

Layer: REST API.
"""

from __future__ import annotations

from flask import Blueprint, current_app, request

from ..errors import (
    APIError,
    SESSION_NOT_STARTED,
    make_success_envelope,
)
from ..validators import require_json

bp = Blueprint("session", __name__, url_prefix="/api/session")


@bp.route("/start", methods=["POST"])
def start_session() -> tuple:
    """POST /api/session/start — start a new session."""
    data = require_json(request)

    human_players_raw = data.get("human_players", [])
    if not isinstance(human_players_raw, list) or len(human_players_raw) == 0:
        raise APIError(400, "INVALID_REQUEST", "human_players must be a non-empty list.")

    human_names: list[str] = []
    for entry in human_players_raw:
        if not isinstance(entry, dict) or "name" not in entry:
            raise APIError(400, "INVALID_REQUEST", "Each human_players entry must have a 'name'.")
        human_names.append(str(entry["name"]))

    bot_count = data.get("bot_count", 0)
    if not isinstance(bot_count, int) or bot_count < 0:
        raise APIError(400, "INVALID_REQUEST", "bot_count must be a non-negative integer.")

    result = current_app.game_manager.start_session(human_names, bot_count)
    return make_success_envelope(result), 200


@bp.route("/end", methods=["POST"])
def end_session() -> tuple:
    """POST /api/session/end — end the current session."""
    if not current_app.game_manager.is_session_active():
        raise APIError(409, SESSION_NOT_STARTED, "No active session to end.")
    result = current_app.game_manager.end_session()
    return make_success_envelope(result), 200


@bp.route("/current", methods=["GET"])
def current_session() -> tuple:
    """GET /api/session/current — return current session state."""
    state = current_app.game_manager.get_current_session()
    if state is None:
        raise APIError(404, SESSION_NOT_STARTED, "No active session.")
    return make_success_envelope(state), 200
