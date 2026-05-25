"""REST API Layer: reference information endpoints.

Blueprint prefix: /api/reference

Endpoints:
    GET /hands   — hand rankings for the given deck config
    GET /variant — plain language rules for a variant/modifier combo

Layer: REST API.
"""

from __future__ import annotations

from flask import Blueprint, current_app, request

from ..errors import APIError, make_success_envelope

bp = Blueprint("reference", __name__, url_prefix="/api/reference")

# Static hand rankings table. Extended in later phases with deck-config
# adjustments and wild-card notes.
_HAND_RANKINGS: list[dict] = [
    {"rank": 10, "name": "Royal Flush",
     "description": "A, K, Q, J, 10 of the same suit",
     "example": "A♠ K♠ Q♠ J♠ 10♠"},
    {"rank": 9, "name": "Straight Flush",
     "description": "Five sequential cards of the same suit",
     "example": "9♥ 8♥ 7♥ 6♥ 5♥"},
    {"rank": 8, "name": "Four of a Kind",
     "description": "Four cards of the same rank",
     "example": "K♠ K♥ K♦ K♣ 7♠"},
    {"rank": 7, "name": "Full House",
     "description": "Three of a kind plus a pair",
     "example": "A♠ A♥ A♦ K♣ K♠"},
    {"rank": 6, "name": "Flush",
     "description": "Five cards of the same suit, not sequential",
     "example": "A♣ J♣ 8♣ 5♣ 2♣"},
    {"rank": 5, "name": "Straight",
     "description": "Five sequential cards of mixed suits",
     "example": "10♠ 9♥ 8♦ 7♣ 6♠"},
    {"rank": 4, "name": "Three of a Kind",
     "description": "Three cards of the same rank",
     "example": "Q♠ Q♥ Q♦ 8♣ 3♠"},
    {"rank": 3, "name": "Two Pair",
     "description": "Two different pairs",
     "example": "J♠ J♥ 7♦ 7♣ K♠"},
    {"rank": 2, "name": "One Pair",
     "description": "Two cards of the same rank",
     "example": "A♠ A♥ K♦ Q♣ 9♠"},
    {"rank": 1, "name": "High Card",
     "description": "No qualifying hand; highest card plays",
     "example": "A♠ K♥ Q♦ J♣ 9♠"},
]

# Static variant rule summaries. Expanded in Phase 4.
_VARIANT_RULES: dict[str, dict] = {
    "SEVEN_CARD_STUD": {
        "title": "Seven Card Stud",
        "summary": (
            "Each player receives seven cards: two face-down, four face-up, "
            "and one final face-down card. Best five-card hand wins."
        ),
        "rules": [
            "Two hole cards dealt face-down.",
            "Four cards dealt face-up, one per betting round.",
            "One final card dealt face-down.",
            "No community cards.",
            "Best five of seven cards plays.",
        ],
        "wild_rules": None,
    },
}

_MODIFIER_RULES: dict[str, str] = {
    "DIRTY_BITCH": "If the Queen of Spades appears face-up, the hand is immediately redealt.",
    "FOLLOW_THE_QUEEN": (
        "When a Queen is dealt face-up, the next face-up card determines the wild rank "
        "for the remainder of the hand."
    ),
    "HIGH_LOW_DECLARE": (
        "At showdown, players simultaneously declare high, low, or both ways. "
        "A both-ways player must win both directions outright."
    ),
}


@bp.route("/hands", methods=["GET"])
def hand_rankings() -> tuple:
    """GET /api/reference/hands — hand rankings for the given deck config."""
    deck_config = request.args.get("deck_config", "STANDARD")
    valid_configs = {"STANDARD", "WITH_NULLS", "WITH_ORBS"}
    if deck_config not in valid_configs:
        raise APIError(
            400, "INVALID_REQUEST",
            f"deck_config must be one of: {', '.join(sorted(valid_configs))}."
        )

    wild_ranks_raw = request.args.get("wild_ranks", "")
    wild_ranks: list[int] = []
    if wild_ranks_raw:
        for token in wild_ranks_raw.split(","):
            try:
                wild_ranks.append(int(token.strip()))
            except ValueError:
                raise APIError(400, "INVALID_REQUEST", "wild_ranks must be comma-separated integers.")

    notes: list[str] = []
    if deck_config == "WITH_ORBS":
        notes.append("With Orbs active, flush probability is reduced.")
    if deck_config == "WITH_NULLS":
        notes.append("Null cards (rank 0) rank below all standard cards including low Ace.")
    if wild_ranks:
        notes.append("Five of a Kind is possible with wild cards.")

    rankings = [dict(r) for r in _HAND_RANKINGS]

    return make_success_envelope({
        "deck_config": deck_config,
        "wild_ranks": wild_ranks,
        "rankings": rankings,
        "notes": notes,
    }), 200


@bp.route("/variant", methods=["GET"])
def variant_rules() -> tuple:
    """GET /api/reference/variant — plain language rules for a variant."""
    variant = request.args.get("variant")
    if not variant:
        raise APIError(400, "INVALID_REQUEST", "variant query parameter is required.")

    variant = variant.upper()
    enabled = current_app.game_manager.get_enabled_variants()
    if variant not in enabled:
        raise APIError(400, "INVALID_VARIANT", f"Unknown or disabled variant: {variant!r}.")

    info = _VARIANT_RULES.get(variant, {
        "title": variant.replace("_", " ").title(),
        "summary": "Rules summary not yet available.",
        "rules": [],
        "wild_rules": None,
    })

    modifiers_raw = request.args.get("modifiers", "")
    modifier_names = [m.strip().upper() for m in modifiers_raw.split(",") if m.strip()]
    modifier_rules = [_MODIFIER_RULES[m] for m in modifier_names if m in _MODIFIER_RULES]

    return make_success_envelope({
        "variant": variant,
        "modifiers": modifier_names,
        "title": info["title"],
        "summary": info["summary"],
        "rules": info["rules"],
        "wild_rules": info.get("wild_rules"),
        "modifier_rules": modifier_rules,
    }), 200
