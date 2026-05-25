"""REST API Layer: configuration endpoints.

Blueprint prefix: /api/config

Endpoints:
    GET  /           — return full house rules configuration
    POST /           — update house rules configuration (requires restart)
    GET  /variants   — return enabled variants with metadata
    GET  /modifiers  — return available modifiers with metadata

Layer: REST API.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, request

from backend.config import load_house_rules

from ..errors import APIError, make_success_envelope
from ..validators import require_json

bp = Blueprint("config", __name__, url_prefix="/api/config")


def _config_path() -> Path:
    env = os.environ.get("POKER_CONFIG_PATH")
    if env:
        return Path(env)
    fallback = Path(__file__).parent.parent.parent.parent / "config" / "house_rules.json"
    return fallback


@bp.route("", methods=["GET"])
def get_config() -> tuple:
    """GET /api/config — return current house rules configuration."""
    try:
        rules = load_house_rules()
    except Exception as exc:
        raise APIError(500, "CONFIGURATION_ERROR", f"Failed to load config: {exc}") from exc
    return make_success_envelope(rules), 200


@bp.route("", methods=["POST"])
def update_config() -> tuple:
    """POST /api/config — update house rules configuration fields."""
    data = require_json(request)

    path = _config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            current: dict[str, Any] = json.load(f)
    except FileNotFoundError:
        current = {}
    except json.JSONDecodeError as exc:
        raise APIError(500, "CONFIGURATION_ERROR", f"Config file is malformed: {exc}") from exc

    changed_keys: list[str] = []
    for key, value in data.items():
        if current.get(key) != value:
            changed_keys.append(key)
        current[key] = value

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
    except OSError as exc:
        raise APIError(500, "CONFIGURATION_ERROR", f"Failed to write config: {exc}") from exc

    return make_success_envelope({
        "updated": True,
        "restart_required": True,
        "message": "Configuration updated. Restart the server for changes to take effect.",
        "changed_keys": changed_keys,
    }), 200


@bp.route("/variants", methods=["GET"])
def get_variants() -> tuple:
    """GET /api/config/variants — list enabled variants with metadata."""
    variants = current_app.game_manager.get_variant_meta()
    return make_success_envelope({"variants": variants}), 200


@bp.route("/modifiers", methods=["GET"])
def get_modifiers() -> tuple:
    """GET /api/config/modifiers — list available modifiers with metadata."""
    modifiers = current_app.game_manager.get_modifier_meta()
    return make_success_envelope({"modifiers": modifiers}), 200
