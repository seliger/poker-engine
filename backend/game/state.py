"""Game Layer core data structures and enumerations.

Defines GameState and all supporting types used throughout the Game Layer.
This module is the single source of truth for in-progress hand state.
No UI, REST, or persistence concerns belong here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from backend.deck.card import Card, DeckConfig, Suit
from backend.deck.deck import Deck

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Game Layer errors
# ---------------------------------------------------------------------------

class IllegalActionError(Exception):
    """Raised when a submitted action is not in the legal actions list."""


class InvalidPhaseTransitionError(Exception):
    """Raised when advance_phase() is called in an invalid state."""


class DeckExhaustionError(Exception):
    """Raised when deck exhaustion cannot be recovered from per variant rules."""


class ModifierEffectError(Exception):
    """Raised when a modifier effect produces an invalid game state."""


class BurnLimitExceededError(Exception):
    """Raised when a Guts cascade payment would exceed a player's burn limit."""


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class GameVariant(Enum):
    """All supported game variants."""
    SEVEN_CARD_STUD = "SEVEN_CARD_STUD"
    FIVE_CARD_DRAW = "FIVE_CARD_DRAW"
    CHICAGO = "CHICAGO"
    LOW_CHICAGO = "LOW_CHICAGO"
    NIGHT_BASEBALL = "NIGHT_BASEBALL"
    JOES_BASEBALL = "JOES_BASEBALL"
    ELEVATOR = "ELEVATOR"
    PILOT = "PILOT"
    ANACONDA = "ANACONDA"
    CHASING_QUEENS = "CHASING_QUEENS"
    AUCTION = "AUCTION"
    GUTS = "GUTS"
    SCREW_YOUR_NEIGHBOR = "SCREW_YOUR_NEIGHBOR"
    CRISS_CROSS = "CRISS_CROSS"
    ROLL_YOUR_OWN = "ROLL_YOUR_OWN"
    SIX_HALF_TWENTYONE_HALF = "SIX_HALF_TWENTYONE_HALF"
    SEVEN_TWENTYSEVEN = "SEVEN_TWENTYSEVEN"
    POULET = "POULET"


class GamePhase(Enum):
    """All possible game phases across all variants."""
    SETUP = "SETUP"
    ANTE = "ANTE"
    INITIAL_DEAL = "INITIAL_DEAL"
    DEAL_ROUND = "DEAL_ROUND"
    BET_ROUND = "BET_ROUND"
    DRAW_ROUND = "DRAW_ROUND"
    FLIP_ROUND = "FLIP_ROUND"
    AUCTION_ROUND = "AUCTION_ROUND"
    COMMUNITY_REVEAL = "COMMUNITY_REVEAL"
    FORCED_DISCARD = "FORCED_DISCARD"
    GUTS_DECLARE = "GUTS_DECLARE"
    GUTS_CASCADE = "GUTS_CASCADE"
    NUMERIC_DRAW = "NUMERIC_DRAW"
    NUMERIC_BET = "NUMERIC_BET"
    DECLARE = "DECLARE"
    SHOWDOWN = "SHOWDOWN"
    POT_DISTRIBUTION = "POT_DISTRIBUTION"
    COMPLETE = "COMPLETE"


class BettingStructure(Enum):
    """Betting structures available across variants."""
    LIMIT = "LIMIT"
    NO_LIMIT = "NO_LIMIT"
    POT_LIMIT = "POT_LIMIT"
    BRING_IN = "BRING_IN"
    AUCTION = "AUCTION"
    GUTS_DECLARE = "GUTS_DECLARE"


class EventType(Enum):
    """Types of game events recorded in hand history."""
    ANTE_POSTED = "ANTE_POSTED"
    CARD_DEALT = "CARD_DEALT"
    CARD_REVEALED = "CARD_REVEALED"
    CARD_FLIPPED = "CARD_FLIPPED"
    BET_PLACED = "BET_PLACED"
    CALL_MADE = "CALL_MADE"
    RAISE_MADE = "RAISE_MADE"
    FOLD = "FOLD"
    CHECK = "CHECK"
    DRAW_REQUESTED = "DRAW_REQUESTED"
    CARD_DISCARDED = "CARD_DISCARDED"
    BID_PLACED = "BID_PLACED"
    AUCTION_WON = "AUCTION_WON"
    GUTS_DECLARED = "GUTS_DECLARED"
    GUTS_CASCADE_FIRED = "GUTS_CASCADE_FIRED"
    FORCED_DISCARD = "FORCED_DISCARD"
    WILD_CHANGED = "WILD_CHANGED"
    MODIFIER_FIRED = "MODIFIER_FIRED"
    DECLARATION_MADE = "DECLARATION_MADE"
    SHOWDOWN = "SHOWDOWN"
    POT_AWARDED = "POT_AWARDED"
    REDEAL_TRIGGERED = "REDEAL_TRIGGERED"
    HAND_COMPLETE = "HAND_COMPLETE"


class LayoutType(Enum):
    """Community card layout types used by community layout variants."""
    NONE = "NONE"
    POOL = "POOL"
    CROSS = "CROSS"
    ELEVATOR = "ELEVATOR"
    GRID_3X3 = "GRID_3X3"


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------

@dataclass
class PositionedCard:
    """A card with visibility metadata attached."""
    card: Card
    is_face_up: bool
    position_index: int
    revealed_at_phase: GamePhase | None = None


@dataclass
class SidePot:
    """A side pot created when a player goes all-in for less than the full bet."""
    amount: int
    eligible_player_ids: list[str]


@dataclass
class Pot:
    """The pot structure for an active hand."""
    main_pot: int = 0
    side_pots: list[SidePot] = field(default_factory=list)
    carry_amount: int = 0
    ante_amount: int = 0

    def total(self) -> int:
        """Return the total chips in all pots including carry."""
        return self.main_pot + sum(sp.amount for sp in self.side_pots) + self.carry_amount


@dataclass
class BettingState:
    """Current state of the betting round."""
    structure: BettingStructure
    small_blind: int | None = None
    big_blind: int | None = None
    ante: int | None = None
    bring_in: int | None = None
    current_bet: int = 0
    minimum_raise: int = 0
    betting_round: int = 0
    players_acted: list[str] = field(default_factory=list)
    last_aggressor_id: str | None = None
    # Phase 4+ fields; None in Phase 1.
    auction_state: Any | None = None
    guts_state: Any | None = None


@dataclass
class PlayerState:
    """Per-player state within a hand."""
    player_id: str
    name: str
    is_bot: bool
    seat_index: int
    chip_stack: int
    hole_cards: list[PositionedCard] = field(default_factory=list)
    is_folded: bool = False
    is_standing: bool = False
    is_eliminated_this_hand: bool = False
    current_bet: int = 0
    total_bet_this_round: int = 0
    declaration: Any | None = None
    in_guts: bool | None = None
    cards_to_discard: list[Card] = field(default_factory=list)


@dataclass
class GameEvent:
    """A recorded game state transition for hand history."""
    event_type: EventType
    phase: GamePhase
    timestamp: datetime
    player_id: str | None = None
    card: Card | None = None
    amount: int | None = None
    modifier_triggered: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActiveGameConfig:
    """The complete configuration for the active hand."""
    variant: GameVariant
    # list[GameModifier] — modifiers are implemented in Phase 2; empty list in Phase 1.
    modifiers: list[Any]
    deck_config: DeckConfig
    variant_config: dict[str, Any] = field(default_factory=dict)


@dataclass
class GameState:
    """The single authoritative representation of a hand in progress.

    Never exposed directly to the UI or bot; player-specific views are
    derived from this via the visibility system.
    """
    hand_id: int
    session_id: int
    variant: GameVariant
    deck_config: DeckConfig
    active_game_config: ActiveGameConfig
    phase: GamePhase
    players: list[PlayerState]
    dealer_index: int
    active_player_index: int
    pot: Pot
    betting_state: BettingState
    deck: Deck
    # list[GameModifier] — Phase 2+; always empty in Phase 1.
    modifiers: list[Any] = field(default_factory=list)
    # CommunityLayout — Phase 4+; None in Phase 1.
    community_layout: Any | None = None
    wild_ranks: list[int] = field(default_factory=list)
    wild_suits: list[Suit] = field(default_factory=list)
    action_has_occurred: bool = False
    redeal_count: int = 0
    hand_history: list[GameEvent] = field(default_factory=list)

    def active_players(self) -> list[PlayerState]:
        """Return players who have not folded and are not eliminated."""
        return [p for p in self.players if not p.is_folded and not p.is_eliminated_this_hand]

    def get_player(self, player_id: str) -> PlayerState:
        """Return the PlayerState for the given player_id."""
        for p in self.players:
            if p.player_id == player_id:
                return p
        raise KeyError(f"No player with id {player_id!r}")

    def record_event(
        self,
        event_type: EventType,
        player_id: str | None = None,
        card: Card | None = None,
        amount: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Append a GameEvent to hand_history."""
        self.hand_history.append(
            GameEvent(
                event_type=event_type,
                phase=self.phase,
                timestamp=datetime.now(timezone.utc),
                player_id=player_id,
                card=card,
                amount=amount,
                metadata=metadata or {},
            )
        )
