"""REST API Layer: serialization of Game Layer objects to JSON-compatible dicts.

All public functions accept typed Game Layer objects and return plain dicts
suitable for json.dumps(). No Flask or request context is required here.

Layer: REST API.
"""

from __future__ import annotations

from typing import Any

from backend.game.state import PositionedCard
from backend.game.visibility import (
    BettingStateView,
    LegalAction,
    OpponentView,
    PartialHandStrength,
    PlayerView,
)


def serialize_card(pc: PositionedCard) -> dict[str, Any]:
    """Serialize a PositionedCard to a JSON-compatible dict."""
    return {
        "rank": pc.card.rank,
        "suit": pc.card.suit.value,
        "is_face_up": pc.is_face_up,
        "position_index": pc.position_index,
        "shorthand": pc.card.shorthand(),
    }


def serialize_legal_action(la: LegalAction) -> dict[str, Any]:
    """Serialize a LegalAction descriptor."""
    return {
        "action_type": la.action_type.value,
        "min_amount": la.min_amount,
        "max_amount": la.max_amount,
    }


def serialize_betting_state(bs: BettingStateView) -> dict[str, Any]:
    """Serialize a BettingStateView for inclusion in a player view response."""
    return {
        "current_bet": bs.current_bet,
        "minimum_raise": bs.minimum_raise,
        "betting_round": bs.betting_round,
        "pot_total": bs.pot_total,
        "structure": bs.structure,
    }


def serialize_opponent(ov: OpponentView) -> dict[str, Any]:
    """Serialize an opponent's visible game state.

    Only face-up cards are included; face-down cards of opponents are never
    serialized regardless of caller identity.
    """
    return {
        "player_id": ov.player_id,
        "name": ov.name,
        "is_bot": ov.is_bot,
        "seat_index": ov.seat_index,
        "chip_stack": ov.chip_stack,
        "visible_cards": [serialize_card(c) for c in ov.visible_cards],
        "is_folded": ov.is_folded,
        "is_standing": ov.is_standing,
        "current_bet": ov.current_bet,
        "declaration_made": ov.declaration_made,
    }


def serialize_hand_strength(hs: PartialHandStrength | None) -> dict[str, Any] | None:
    """Serialize a PartialHandStrength hint, or return None."""
    if hs is None:
        return None
    return {
        "display_name": hs.display_name,
        "hand_rank": hs.hand_rank.value if hs.hand_rank else None,
        "current_total": hs.current_total,
        "is_partial": hs.is_partial,
        "notes": hs.notes,
    }


def serialize_player_view(view: PlayerView) -> dict[str, Any]:
    """Serialize a complete PlayerView to the game_state_update payload shape."""
    return {
        "hand_id": view.hand_id,
        "phase": view.phase.value,
        "my_cards": [serialize_card(c) for c in view.my_cards],
        "other_players": [serialize_opponent(op) for op in view.other_players],
        "pot_total": view.pot_total,
        "my_stack": view.my_stack,
        "betting_state": serialize_betting_state(view.betting_state),
        "wild_ranks": list(view.wild_ranks),
        "wild_suits": [s.value for s in view.wild_suits],
        "active_modifiers": list(view.active_modifiers),
        "legal_actions": [serialize_legal_action(la) for la in view.legal_actions],
        "community_layout": view.community_layout,
        "hand_strength": serialize_hand_strength(view.hand_strength),
        "my_personal_wild_rank": view.my_personal_wild_rank,
    }
