"""Evaluation Layer abstract base classes and shared types.

Defines the BaseEvaluator interface and BaseEvaluatedHand that every concrete
evaluator (PokerHandEvaluator, NumericEvaluator, TrickTakingEvaluator, etc.)
must implement.  The Game Layer communicates with evaluators exclusively through
these types and never imports a concrete evaluator directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, IntEnum

from backend.deck.card import Card, DeckConfig, Suit


# ---------------------------------------------------------------------------
# Shared enumerations
# ---------------------------------------------------------------------------

class EvalDirection(Enum):
    """Which direction a hand is being evaluated toward."""
    HIGH = "HIGH"
    LOW = "LOW"


class Declaration(Enum):
    """The player's declared direction in a high-low declare game."""
    HIGH = "HIGH"
    LOW = "LOW"
    BOTH = "BOTH"


class ComparisonResult(Enum):
    """Result of a two-hand comparison from hand_a's perspective."""
    WIN = "WIN"
    LOSE = "LOSE"
    TIE = "TIE"


class HandRank(IntEnum):
    """Poker hand rank hierarchy.

    Higher integer value means a stronger hand in HIGH direction.
    FIVE_OF_A_KIND requires wild cards or nulls_match_each_other (Phase 3+).
    ROYAL_FLUSH is separated for display purposes; whether it outranks a
    non-royal STRAIGHT_FLUSH for pot purposes depends on the house rules flag
    royal_flush_beats_straight_flush (default False).
    """
    HIGH_CARD = 0
    ONE_PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    FIVE_OF_A_KIND = 8
    STRAIGHT_FLUSH = 9
    ROYAL_FLUSH = 10


# ---------------------------------------------------------------------------
# Shared data classes
# ---------------------------------------------------------------------------

@dataclass
class BaseEvaluatedHand:
    """Fields common to all evaluated hands across all evaluator types.

    Concrete evaluators return subclasses that extend this with
    evaluator-specific fields.
    """
    is_partial: bool
    deck_config: DeckConfig
    display_name: str
    high_value: int
    low_value: int


@dataclass
class WinnerResult:
    """The result returned by BaseEvaluator.determine_winners()."""
    winners: list[str]
    winning_hand: BaseEvaluatedHand
    is_tie: bool
    pot_split: bool


@dataclass
class DeclareResult:
    """The result returned by BaseEvaluator.evaluate_for_declare().

    The PokerHandEvaluator returns both evaluations when declaration is BOTH.
    Scoop-or-bust enforcement is the Game Layer's responsibility.
    """
    declaration: Declaration
    high_hand: BaseEvaluatedHand | None
    low_hand: BaseEvaluatedHand | None
    is_both_ways: bool
    must_win_both: bool


# Ace dual-value return type.
# Single direction: int (14 for HIGH, 1 for LOW).
# BOTH declaration:  tuple[int, int] = (low_rank=1, high_rank=14).
AceDualValue = int | tuple[int, int]


# ---------------------------------------------------------------------------
# Abstract base evaluator
# ---------------------------------------------------------------------------

class BaseEvaluator(ABC):
    """Abstract interface for all evaluators in the evaluation family.

    The Game Layer selects the correct evaluator via EVALUATOR_REGISTRY and
    calls it through this interface.  No Game Layer code is aware of which
    concrete evaluator is active.
    """

    @abstractmethod
    def evaluate(
        self,
        cards: list[Card],
        deck_config: DeckConfig,
        wild_ranks: list[int] | None = None,
        wild_suits: list[Suit] | None = None,
        direction: EvalDirection = EvalDirection.HIGH,
        declaration: Declaration = Declaration.HIGH,
    ) -> BaseEvaluatedHand:
        """Evaluate the best possible hand from the provided cards.

        Accepts 2-10 cards.  Fewer than 5 cards produce a partial evaluation.
        """

    @abstractmethod
    def compare(
        self,
        hand_a: BaseEvaluatedHand,
        hand_b: BaseEvaluatedHand,
        direction: EvalDirection,
    ) -> ComparisonResult:
        """Compare two hands.  Returns WIN, LOSE, or TIE from hand_a's perspective."""

    @abstractmethod
    def determine_winners(
        self,
        evaluated_hands: dict[str, BaseEvaluatedHand],
        direction: EvalDirection,
    ) -> WinnerResult:
        """Determine the winner(s) across all player hands for the given direction."""

    @abstractmethod
    def evaluate_for_declare(
        self,
        cards: list[Card],
        deck_config: DeckConfig,
        declaration: Declaration,
        wild_ranks: list[int] | None = None,
    ) -> DeclareResult:
        """Evaluate a hand in the context of a high-low chip-declare."""

    @abstractmethod
    def ace_dual_value(
        self,
        direction: EvalDirection,
        declaration: Declaration,
    ) -> AceDualValue:
        """Return the rank integer(s) Ace assumes for the given direction/declaration."""

    @abstractmethod
    def calculate_hand_frequencies(
        self,
        deck_config: DeckConfig,
        wild_ranks: list[int] | None = None,
        hand_size: int = 5,
    ) -> dict[HandRank, float]:
        """Return approximate probability of each HandRank for the given config."""
