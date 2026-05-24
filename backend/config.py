"""House rules configuration loader and validator.

Phase 1 scope: loads the deck, betting, and bot sections of house_rules.json.
Full house rules validation is added in later phases.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.deck.card import DeckConfig

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path.home() / ".config" / "poker_engine" / "house_rules.json"
_FALLBACK_CONFIG_PATH = Path(__file__).parent.parent / "config" / "house_rules.json"


class HouseRulesConfigurationError(Exception):
    """Raised when house_rules.json is missing, malformed, or invalid."""


@dataclass
class BettingConfig:
    """Betting amounts loaded from house_rules.json."""
    ante_amount: int
    bring_in_amount: int
    small_bet: int
    big_bet: int


@dataclass
class BotConfig:
    """Bot behavior parameters loaded from house_rules.json."""
    count: int
    aggression: float
    bluff_frequency: float
    risk_tolerance: float
    personality_variance: float
    use_monte_carlo: bool
    use_claude_api: bool
    claude_model: str
    claude_api_timeout_seconds: int


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


def load_betting_config() -> BettingConfig:
    """Return a BettingConfig built from house_rules.json, or sensible defaults."""
    rules = load_house_rules()
    b: dict[str, Any] = rules.get("betting", {})
    return BettingConfig(
        ante_amount=b.get("ante_amount", 1),
        bring_in_amount=b.get("bring_in_amount", 1),
        small_bet=b.get("small_bet", 2),
        big_bet=b.get("big_bet", 4),
    )


def load_bot_config() -> BotConfig:
    """Return a BotConfig built from house_rules.json, or sensible defaults."""
    rules = load_house_rules()
    b: dict[str, Any] = rules.get("bot", {})
    return BotConfig(
        count=b.get("count", 5),
        aggression=b.get("aggression", 0.5),
        bluff_frequency=b.get("bluff_frequency", 0.15),
        risk_tolerance=b.get("risk_tolerance", 0.5),
        personality_variance=b.get("personality_variance", 0.1),
        use_monte_carlo=b.get("use_monte_carlo", False),
        use_claude_api=b.get("use_claude_api", False),
        claude_model=b.get("claude_model", "claude-sonnet-4-20250514"),
        claude_api_timeout_seconds=b.get("claude_api_timeout_seconds", 5),
    )
