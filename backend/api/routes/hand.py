"""REST API Layer: hand management endpoints.

Blueprint prefix: /api/hand

Endpoints:
    POST /start  — start a new hand
    GET  /state  — return the requesting player's current view
    POST /action — submit a player action
    GET  /result — return the most recently completed hand result

Layer: REST API.
"""

from __future__ import annotations

from flask import Blueprint, current_app, request

from ..errors import (
    APIError,
    make_success_envelope,
)
from ..serializers import serialize_player_view
from ..validators import require_json, require_player_id

bp = Blueprint("hand", __name__, url_prefix="/api/hand")


@bp.route("/start", methods=["POST"])
def start_hand() -> tuple:
    """POST /api/hand/start — start a new hand."""
    player_id = require_player_id(request, current_app.game_manager)
    data = require_json(request)

    variant = data.get("variant")
    if not isinstance(variant, str) or not variant:
        raise APIError(400, "INVALID_REQUEST", "variant is required.")

    modifiers = data.get("modifiers", [])
    if not isinstance(modifiers, list):
        raise APIError(400, "INVALID_REQUEST", "modifiers must be a list.")

    options: dict = {}
    if "diagonals_active" in data:
        options["diagonals_active"] = bool(data["diagonals_active"])

    socketio = current_app.extensions.get("socketio")
    result = current_app.game_manager.start_hand(
        player_id, variant, modifiers, options, socketio
    )
    return make_success_envelope(result), 200


@bp.route("/state", methods=["GET"])
def hand_state() -> tuple:
    """GET /api/hand/state — return the requesting player's current game view."""
    player_id = require_player_id(request, current_app.game_manager)
    view = current_app.game_manager.get_hand_state(player_id)
    return make_success_envelope(serialize_player_view(view)), 200


@bp.route("/action", methods=["POST"])
def submit_action() -> tuple:
    """POST /api/hand/action — submit a player action."""
    player_id = require_player_id(request, current_app.game_manager)
    data = require_json(request)

    action_type = data.get("action_type")
    if not isinstance(action_type, str) or not action_type:
        raise APIError(400, "INVALID_REQUEST", "action_type is required.")

    amount = data.get("amount") or 0
    if not isinstance(amount, int):
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            raise APIError(400, "INVALID_AMOUNT", "amount must be an integer.")

    cards = data.get("cards") or []
    if not isinstance(cards, list):
        raise APIError(400, "INVALID_REQUEST", "cards must be a list.")

    socketio = current_app.extensions.get("socketio")
    result = current_app.game_manager.submit_action(
        player_id, action_type, amount, cards, socketio
    )
    return make_success_envelope(result), 200


@bp.route("/result", methods=["GET"])
def hand_result() -> tuple:
    """GET /api/hand/result — return the most recently completed hand result."""
    require_player_id(request, current_app.game_manager)
    result = current_app.game_manager.get_hand_result()
    return make_success_envelope(result), 200
