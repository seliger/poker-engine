"""BaseVariant abstract interface and shared types for the Game Layer.

All variant state machines inherit from BaseVariant and implement its full
interface. The Game Layer drives variants exclusively through this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from backend.deck.card import Card
from backend.evaluators.base import BaseEvaluatedHand, BaseEvaluator
from backend.game.state import (
    ActiveGameConfig,
    GamePhase,
    GameState,
    GameVariant,
)
from backend.game.visibility import ActionType, LegalAction


@dataclass
class PlayerAction:
    """A player's submitted action during a game phase."""
    action_type: ActionType
    amount: int = 0
    cards: list[Card] = field(default_factory=list)


@dataclass
class ShowdownResult:
    """The result of resolving a showdown."""
    winner_ids: list[str]
    winning_hands: dict[str, BaseEvaluatedHand]
    pot_distribution: dict[str, int]
    is_tie: bool


class BaseVariant(ABC):
    """Abstract base class for all variant state machines.

    Concrete implementations are registered in the evaluator registry and
    driven by the Game Layer. Each variant manages its own phase sequence.
    """

    variant: GameVariant
    evaluator_class: type[BaseEvaluator]
    default_betting_structure: Any
    min_players: int
    max_players: int

    @abstractmethod
    def initialize(
        self,
        game_state: GameState,
        active_game_config: ActiveGameConfig,
    ) -> GameState:
        """Perform one-time setup at the start of a hand.

        Sets variant_config defaults on active_game_config and returns the
        initialized GameState.
        """

    @abstractmethod
    def get_phase_sequence(self) -> list[GamePhase]:
        """Return the ordered list of phases for this variant, including repeats."""

    @abstractmethod
    def execute_phase(
        self,
        game_state: GameState,
        phase: GamePhase,
    ) -> GameState:
        """Execute a non-interactive phase (ANTE, DEAL, etc.) to completion.

        For interactive phases (BET_ROUND) this sets up the initial state
        without completing the round; apply_action() handles each player action.
        """

    @abstractmethod
    def get_legal_actions(
        self,
        game_state: GameState,
        player_id: str,
    ) -> list[LegalAction]:
        """Return the legal actions for the given player in the current phase."""

    @abstractmethod
    def apply_action(
        self,
        game_state: GameState,
        player_id: str,
        action: PlayerAction,
    ) -> GameState:
        """Apply a single player action and update GameState."""

    @abstractmethod
    def is_phase_complete(
        self,
        game_state: GameState,
        phase: GamePhase,
    ) -> bool:
        """Return True when the current phase has finished."""

    @abstractmethod
    def advance_phase(self, game_state: GameState) -> GameState:
        """Move game_state to the next phase in the sequence."""

    @abstractmethod
    def resolve_showdown(self, game_state: GameState) -> ShowdownResult:
        """Evaluate all hands and determine winners at showdown."""
