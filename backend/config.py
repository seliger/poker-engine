"""House rules configuration loader and validator.

Phase 1 scope: loads the deck section of house_rules.json and returns a
DeckConfig.  Full house rules validation is added in later phases.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from backend.deck.card import DeckConfig

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path.home() / ".config" / "poker_engine" / "house_rules.json"
_FALLBACK_CONFIG_PATH = Path(__file__).parent.parent / "config" / "house_rules.json"


class HouseRulesConfigurationError(Exception):
    """Raised when house_rules.json is missing, malformed, or invalid."""


def _resolve_config_path() -> Path:
    env = os.environ.get("POKER_CONFIG_PATH")
    if env:
        return Path(env)
    if _DEFAULT_CONFIG_PATH.exists():
        return _DEFAULT_CONFIG_PATH
    return _FALLBACK_CONFIG_PATH


def load_house_rules() -> dict[str, Any]:
    """Load and return the raw house rules JSON as a dict."""
    path = _resolve_config_path()
    if not path.exists():
        logger.info("No house rules file found at %s; using defaults", path)
        return {}
    try:
        with path.open() as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise HouseRulesConfigurationError(
            f"house_rules.json at {path} is not valid JSON: {exc}"
        ) from exc
    logger.info("Loaded house rules from %s", path)
    return data


def load_deck_config() -> DeckConfig:
    """Return a DeckConfig built from house_rules.json, or the STANDARD preset."""
    rules = load_house_rules()
    deck_section: dict[str, Any] = rules.get("deck", {})

    null_rules: dict[str, Any] = deck_section.get("null_rules", {})
    preset_name: str = deck_section.get("default_config", "STANDARD")

    # Base include_orbs / include_nulls flags come from the named preset.
    _preset_bases: dict[str, dict[str, bool]] = {
        "STANDARD":   {"include_orbs": False, "include_nulls": False},
        "WITH_NULLS": {"include_orbs": False, "include_nulls": True},
        "WITH_ORBS":  {"include_orbs": True,  "include_nulls": False},
    }
    if preset_name not in _preset_bases:
        raise HouseRulesConfigurationError(
            f"Unknown deck default_config '{preset_name}'; "
            f"must be one of {list(_preset_bases)}"
        )

    base = _preset_bases[preset_name]
    return DeckConfig(
        include_orbs=base["include_orbs"],
        include_nulls=base["include_nulls"],
        null_exists_in_orbs=null_rules.get("null_exists_in_orbs", False),
        nulls_match_each_other=null_rules.get("nulls_match_each_other", False),
        wilds_can_become_null=null_rules.get("wilds_can_become_null", False),
        low_card_warning_threshold=deck_section.get("low_card_warning_threshold", 10),
    )
