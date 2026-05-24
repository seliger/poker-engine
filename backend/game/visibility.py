"""Visibility system for the Game Layer.

Derives player-specific views from the authoritative GameState. This is the
mechanism for information asymmetry: hole cards belonging to one player never
appear in another player's view.

The Game Layer calls get_player_view() for every player action and for bot
decision-making. The REST API serializes PlayerView for the UI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.evaluators.base import HandRank
from backend.game.state import (
    BettingState,
    GamePhase,
    GameState,
    PlayerState,
    PositionedCard,
    Suit,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Action types and legal action
# ---------------------------------------------------------------------------

class ActionType(Enum):
    """All possible action types a player may take."""
    FOLD = "FOLD"
    CHECK = "CHECK"
    CALL = "CALL"
    RAISE = "RAISE"
    BET = "BET"
    DRAW = "DRAW"
    STAND = "STAND"
    FLIP = "FLIP"
    BID = "BID"
    PASS_BID = "PASS_BID"
    GUTS_IN = "GUTS_IN"
    GUTS_OUT = "GUTS_OUT"
    DECLARE_HIGH = "DECLARE_HIGH"
    DECLARE_LOW = "DECLARE_LOW"
    DECLARE_BOTH = "DECLARE_BOTH"
    DISCARD = "DISCARD"
    POST_ANTE = "POST_ANTE"
    POST_BRING_IN = "POST_BRING_IN"


@dataclass
class LegalAction:
    """Describes one legal action available to a player."""
    action_type: ActionType
    min_amount: int | None = None
    max_amount: int | None = None
    available_cards: list[Any] | None = None


# ---------------------------------------------------------------------------
# View types
# ---------------------------------------------------------------------------

@dataclass
class PartialHandStrength:
    """A partial evaluation of the player's current visible hand.

    Shown to the human player as a training aid.
    """
    display_name: str
    hand_rank: HandRank | None
    current_total: float | None
    is_partial: bool
    notes: str | None = None


@dataclass
class BettingStateView:
    """A sanitized view of BettingState for inclusion in PlayerView."""
    current_bet: int
    minimum_raise: int
    betting_round: int
    pot_total: int
    structure: str


@dataclass
class OpponentView:
    """What one player can see of an opponent.

    Never includes face-down cards belonging to the opponent.
    """
    player_id: str
    name: str
    is_bot: bool
    seat_index: int
    chip_stack: int
    visible_cards: list[PositionedCard]
    is_folded: bool
    is_standing: bool
    current_bet: int
    declaration_made: bool


@dataclass
class PlayerView:
    """Everything a player is allowed to see at a given moment."""
    hand_id: int
    phase: GamePhase
    my_cards: list[PositionedCard]
    other_players: list[OpponentView]
    pot_total: int
    my_stack: int
    betting_state: BettingStateView
    wild_ranks: list[int]
    wild_suits: list[Suit]
    active_modifiers: list[str]
    legal_actions: list[LegalAction]
    community_layout: Any | None = None
    hand_strength: PartialHandStrength | None = None


# ---------------------------------------------------------------------------
# View derivation
# ---------------------------------------------------------------------------

def get_player_view(
    game_state: GameState,
    requesting_player_id: str,
    legal_actions: list[LegalAction] | None = None,
    hand_strength: PartialHandStrength | None = None,
) -> PlayerView:
    """Derive a PlayerView for the requesting player from the authoritative GameState.

    Face-down cards belonging to other players are never included. The requesting
    player always sees all of their own cards, including face-down.
    """
    my_player = game_state.get_player(requesting_player_id)

    other_players: list[OpponentView] = []
    for player in game_state.players:
        if player.player_id == requesting_player_id:
            continue
        # Only include face-up cards for opponents.
        visible = [pc for pc in player.hole_cards if pc.is_face_up]
        other_players.append(
            OpponentView(
                player_id=player.player_id,
                name=player.name,
                is_bot=player.is_bot,
                seat_index=player.seat_index,
                chip_stack=player.chip_stack,
                visible_cards=visible,
                is_folded=player.is_folded,
                is_standing=player.is_standing,
                current_bet=player.current_bet,
                declaration_made=player.declaration is not None,
            )
        )

    betting_view = BettingStateView(
        current_bet=game_state.betting_state.current_bet,
        minimum_raise=game_state.betting_state.minimum_raise,
        betting_round=game_state.betting_state.betting_round,
        pot_total=game_state.pot.total(),
        structure=game_state.betting_state.structure.value,
    )

    return PlayerView(
        hand_id=game_state.hand_id,
        phase=game_state.phase,
        my_cards=list(my_player.hole_cards),
        other_players=other_players,
        pot_total=game_state.pot.total(),
        my_stack=my_player.chip_stack,
        betting_state=betting_view,
        wild_ranks=list(game_state.wild_ranks),
        wild_suits=list(game_state.wild_suits),
        active_modifiers=[],
        legal_actions=legal_actions or [],
        community_layout=game_state.community_layout,
        hand_strength=hand_strength,
    )
