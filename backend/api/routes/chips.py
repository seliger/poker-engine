"""REST API Layer: chip management endpoints.

Blueprint prefix: /api/chips

Endpoints:
    GET /balance     — current balances for all session players
    GET /ledger      — chip ledger for the current session
    GET /ledger/all  — chip ledger across all sessions

Layer: REST API.
"""

from __future__ import annotations

from flask import Blueprint, current_app, request

from ..errors import APIError, make_success_envelope
from ..validators import require_player_id

bp = Blueprint("chips", __name__, url_prefix="/api/chips")


@bp.route("/balance", methods=["GET"])
def get_balance() -> tuple:
    """GET /api/chips/balance — current balances for all players."""
    require_player_id(request, current_app.game_manager)
    result = current_app.game_manager.get_balances()
    return make_success_envelope(result), 200


@bp.route("/ledger", methods=["GET"])
def get_ledger() -> tuple:
    """GET /api/chips/ledger — chip ledger for the current session."""
    require_player_id(request, current_app.game_manager)

    filter_player_id = request.args.get("player_id") or None
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        raise APIError(400, "INVALID_REQUEST", "limit and offset must be integers.")

    result = current_app.game_manager.get_session_ledger(filter_player_id, limit, offset)
    return make_success_envelope(result), 200


@bp.route("/ledger/all", methods=["GET"])
def get_ledger_all() -> tuple:
    """GET /api/chips/ledger/all — chip ledger across all sessions."""
    require_player_id(request, current_app.game_manager)

    filter_player_id = request.args.get("player_id") or None
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        raise APIError(400, "INVALID_REQUEST", "limit and offset must be integers.")

    result = current_app.game_manager.get_all_ledger(filter_player_id, limit, offset)
    return make_success_envelope(result), 200
