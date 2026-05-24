"""GameModifier abstract base class stub for the Game Layer.

Phase 1 stub: defines the interface that Phase 2 concrete modifiers
(DirtyBitchModifier, FollowTheQueenModifier, HighLowDeclareModifier) will
implement. GameState.modifiers is always an empty list in Phase 1.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from backend.deck.card import Card

if TYPE_CHECKING:
    from backend.game.state import GameState


class EffectType(Enum):
    """Types of effects a modifier can produce."""
    REDEAL = "REDEAL"
    REDEAL_REANTE = "REDEAL_REANTE"
    CHANGE_WILD = "CHANGE_WILD"
    NO_OP = "NO_OP"


class PotInstruction(Enum):
    """How the pot is handled when a modifier fires."""
    CARRY = "CARRY"
    SPLIT = "SPLIT"
    REANTE_ON_TOP = "REANTE_ON_TOP"
    DISCARD = "DISCARD"


@dataclass
class ModifierEffect:
    """The effect produced by a modifier that has fired."""
    effect_type: EffectType
    requires_player_action: bool
    pot_instruction: PotInstruction
    message: str


class GameModifier(ABC):
    """Abstract interface for all game modifiers.

    Modifiers are composable rules layered on top of base variants.
    They are checked after every card deal or reveal event.
    """

    @abstractmethod
    def trigger_condition(self, card: Card, game_state: GameState) -> bool:
        """Return True when this modifier should fire for the given card."""

    @abstractmethod
    def execute_effect(self, game_state: GameState) -> ModifierEffect:
        """Produce the ModifierEffect for this modifier when triggered."""
