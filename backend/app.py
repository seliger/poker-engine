"""Flask application entry point.

Creates and configures the Flask application via the create_app() factory.
Attaches the SocketIO instance, registers blueprints, and configures CORS.
The GameManager instance is stored on app.game_manager and accessed by
route handlers via current_app.game_manager.

Layer: REST API.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from flask import Flask, jsonify
from flask_cors import CORS

from backend.api.errors import APIError, INTERNAL_ERROR, make_error_envelope
from backend.api.game_manager import GameManager
from backend.api.socket import socketio

logger = logging.getLogger(__name__)


def create_app(db_path: str | None = None, testing: bool = False) -> Flask:
    """Application factory.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file. Defaults to POKER_DB_PATH env var
        or 'data/poker.db' relative to the project root. Pass ':memory:' for
        an in-memory database in tests.
    testing:
        When True, sets TESTING=True and disables SocketIO message queue.
    """
    app = Flask(__name__)
    app.config["TESTING"] = testing

    _configure_logging()

    # ------------------------------------------------------------------ #
    # Database path
    # ------------------------------------------------------------------ #
    if db_path is None:
        db_path = os.environ.get("POKER_DB_PATH", "data/poker.db")

    # ------------------------------------------------------------------ #
    # CORS
    # ------------------------------------------------------------------ #
    cors_origins_raw = os.environ.get("POKER_CORS_ORIGINS", "http://localhost:5173")
    if cors_origins_raw == "*":
        cors_origins: Any = "*"
    else:
        cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]
    CORS(app, origins=cors_origins)

    # ------------------------------------------------------------------ #
    # SocketIO
    # ------------------------------------------------------------------ #
    if testing:
        socketio.init_app(app, async_mode="threading", cors_allowed_origins=cors_origins)
    else:
        socketio.init_app(app, async_mode="eventlet", cors_allowed_origins=cors_origins)

    # ------------------------------------------------------------------ #
    # Game Manager
    # ------------------------------------------------------------------ #
    gm = GameManager(db_path=db_path)
    gm.connect()
    app.game_manager = gm  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ #
    # Blueprints
    # ------------------------------------------------------------------ #
    from backend.api.routes.session import bp as session_bp
    from backend.api.routes.hand import bp as hand_bp
    from backend.api.routes.chips import bp as chips_bp
    from backend.api.routes.reference import bp as reference_bp
    from backend.api.routes.config import bp as config_bp

    app.register_blueprint(session_bp)
    app.register_blueprint(hand_bp)
    app.register_blueprint(chips_bp)
    app.register_blueprint(reference_bp)
    app.register_blueprint(config_bp)

    # ------------------------------------------------------------------ #
    # Global error handler
    # ------------------------------------------------------------------ #
    @app.errorhandler(APIError)
    def handle_api_error(exc: APIError):
        return jsonify(exc.to_envelope()), exc.http_status

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc: Exception):
        logger.exception("Unhandled exception: %s", exc)
        envelope = make_error_envelope(
            INTERNAL_ERROR,
            "An unexpected error occurred. See server logs.",
        )
        return jsonify(envelope), 500

    # ------------------------------------------------------------------ #
    # WebSocket handlers
    # ------------------------------------------------------------------ #
    @socketio.on("connect", namespace="/game")
    def on_connect():
        from flask import request as ws_request
        player_id = ws_request.args.get("player_id")
        if not player_id or not app.game_manager.is_known_player(player_id):
            return False  # Reject connection

        hand_info = _current_hand_room(app)
        if hand_info is not None:
            from flask_socketio import join_room
            join_room(str(hand_info))
        logger.debug("WebSocket connect: player_id=%s", player_id)

    @socketio.on("disconnect", namespace="/game")
    def on_disconnect():
        from flask import request as ws_request
        player_id = ws_request.args.get("player_id", "unknown")
        logger.debug("WebSocket disconnect: player_id=%s", player_id)

    @socketio.on("submit_action", namespace="/game")
    def on_submit_action(data: dict):
        from flask import request as ws_request
        player_id = ws_request.args.get("player_id")
        if not player_id or not app.game_manager.is_known_player(player_id):
            socketio.emit(
                "error_event",
                {"code": "UNKNOWN_PLAYER", "message": "Unknown player."},
                namespace="/game",
            )
            return

        action_type = data.get("action_type", "")
        amount = data.get("amount") or 0
        cards = data.get("cards") or []

        try:
            app.game_manager.submit_action(player_id, action_type, amount, cards, socketio)
        except APIError as exc:
            socketio.emit(
                "error_event",
                {"code": exc.code, "message": exc.message},
                namespace="/game",
            )
        except Exception as exc:
            logger.exception("WebSocket submit_action error: %s", exc)
            socketio.emit(
                "error_event",
                {"code": INTERNAL_ERROR, "message": "An unexpected error occurred."},
                namespace="/game",
            )

    # ------------------------------------------------------------------ #
    # Teardown
    # ------------------------------------------------------------------ #
    @app.teardown_appcontext
    def close_db(exc: BaseException | None) -> None:
        pass  # GameManager connection is long-lived; not torn down per request.

    return app


def _current_hand_room(app: Flask) -> int | None:
    gm: GameManager = app.game_manager  # type: ignore[attr-defined]
    if gm._game_state is not None:  # noqa: SLF001
        return gm._game_state.hand_id
    return None


def _configure_logging() -> None:
    level_name = os.environ.get("POKER_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
