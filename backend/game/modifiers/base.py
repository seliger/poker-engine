"""GameModifier abstract base class and modifier system interface.

Phase 2 scope: defines the abstract GameModifier interface, ModifierEffect,
EffectType, PotInstruction, MODIFIER_REGISTRY, apply_modifier_effect(), and
run_modifier_hook(). Concrete implementations (DirtyBitchModifier,
FollowTheQueenModifier, HighLowDeclareModifier) are added in Steps 2-4.

Layer: Game Layer.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from backend.deck.card import Card

if TYPE_CHECKING:
    from backend.game.state import GameState

logger = logging.getLogger(__name__)


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
    They are checked after every card deal or reveal event via
    run_modifier_hook(). The modifier system is bypassed for POULET.

    Concrete implementations: DirtyBitchModifier (Step 2),
    FollowTheQueenModifier (Step 3), HighLowDeclareModifier (Step 4).
    """

    @abstractmethod
    def trigger_condition(self, card: Card, game_state: GameState) -> bool:
        """Return True when this modifier should fire for the given card."""

    @abstractmethod
    def execute_effect(self, game_state: GameState) -> ModifierEffect:
        """Produce the ModifierEffect for this modifier when triggered."""


# Populated by concrete modifier modules in Phase 2 Steps 2-4.
MODIFIER_REGISTRY: dict[str, type[GameModifier]] = {}


def apply_modifier_effect(
    game_state: GameState,
    effect: ModifierEffect,
) -> GameState:
    """Apply a ModifierEffect to the game state.

    Records a MODIFIER_FIRED event in hand history for all effect types.
    NO_OP returns the game state unchanged. Mechanical effects (REDEAL,
    REDEAL_REANTE, CHANGE_WILD) are implemented in Phase 2 Steps 2-4.
    """
    from backend.game.state import EventType  # deferred to avoid circular import

    game_state.record_event(
        EventType.MODIFIER_FIRED,
        metadata={
            "effect_type": effect.effect_type.value,
            "pot_instruction": effect.pot_instruction.value,
            "message": effect.message,
        },
    )

    if effect.effect_type == EffectType.NO_OP:
        return game_state

    raise NotImplementedError(
        f"Modifier effect {effect.effect_type.value!r} not yet implemented. "
        "Concrete handling is added in Phase 2 Steps 2-4."
    )


def run_modifier_hook(
    game_state: GameState,
    event_index_before: int,
    modifier_stacking: bool = False,
) -> GameState:
    """Run the modifier hook after a card deal or reveal.

    Scans hand_history events added since event_index_before for
    CARD_DEALT and CARD_REVEALED events, then checks each active
    modifier's trigger_condition against each newly dealt card.

    Skipped entirely for GameVariant.POULET. When modifier_stacking is
    False (the default), processing stops after the first modifier fires.
    Cards without an associated Card object (face-down deals that omit
    the card) are excluded from the trigger check.
    """
    from backend.game.state import EventType, GameVariant  # deferred to avoid circular import

    if game_state.variant == GameVariant.POULET:
        return game_state

    if not game_state.active_game_config.modifiers:
        return game_state

    deal_event_types = {EventType.CARD_DEALT, EventType.CARD_REVEALED}
    new_events = game_state.hand_history[event_index_before:]
    newly_dealt = [
        e.card
        for e in new_events
        if e.event_type in deal_event_types and e.card is not None
    ]

    if not newly_dealt:
        return game_state

    fired = False
    for modifier in game_state.active_game_config.modifiers:
        if fired:
            break
        for card in newly_dealt:
            if modifier.trigger_condition(card, game_state):
                effect = modifier.execute_effect(game_state)
                game_state = apply_modifier_effect(game_state, effect)
                logger.info(
                    "Modifier %s fired on %s: %s",
                    type(modifier).__name__,
                    card,
                    effect.message,
                )
                if not modifier_stacking:
                    fired = True
                    break

    return game_state
