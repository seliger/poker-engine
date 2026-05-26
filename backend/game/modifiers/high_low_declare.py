"""HighLowDeclareModifier: chip-declare phase insertion for the Modifier System.

Phase 2 Step 2 scope: inserts a DECLARE phase before SHOWDOWN when active.
Players declare HIGH, LOW, or BOTH. Scoop-or-bust enforcement is the
Game Layer variant's responsibility.

Layer: Game Layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.deck.card import Card
from backend.game.modifiers.base import (
    EffectType,
    GameModifier,
    ModifierEffect,
    PotInstruction,
)

if TYPE_CHECKING:
    from backend.game.state import GamePhase, GameState


class HighLowDeclareModifier(GameModifier):
    """Inserts a chip-declare phase before showdown.

    trigger_condition() always returns False — this modifier does not fire
    on card events. Instead, get_phase_injection() intercepts the transition
    to SHOWDOWN and redirects to DECLARE when declarations are still pending.

    both_ways_requires_scoop controls whether BOTH declarants must win both
    directions outright or receive nothing. Read from house_rules.json at
    construction time; defaults to True per spec.
    """

    def __init__(self, both_ways_requires_scoop: bool = True) -> None:
        self._both_ways_requires_scoop = both_ways_requires_scoop

    @property
    def both_ways_requires_scoop(self) -> bool:
        """Whether BOTH declarants must win both directions or receive nothing."""
        return self._both_ways_requires_scoop

    def trigger_condition(self, card: Card, game_state: GameState) -> bool:
        """Never fires on card events."""
        return False

    def execute_effect(self, game_state: GameState) -> ModifierEffect:
        """Returns a NO_OP effect; this modifier does not fire on card events."""
        return ModifierEffect(
            effect_type=EffectType.NO_OP,
            requires_player_action=True,
            pot_instruction=PotInstruction.CARRY,
            message="Declare high, low, or both.",
        )

    def get_phase_injection(
        self,
        upcoming_phase: GamePhase,
        game_state: GameState,
    ) -> GamePhase | None:
        """Return DECLARE when the hand is about to enter SHOWDOWN.

        Returns None if declarations are already complete (declare_done is
        True in variant_config) or if the upcoming phase is not SHOWDOWN.
        """
        from backend.game.state import GamePhase as GP

        if upcoming_phase != GP.SHOWDOWN:
            return None
        if game_state.active_game_config.variant_config.get("declare_done", False):
            return None
        return GP.DECLARE
