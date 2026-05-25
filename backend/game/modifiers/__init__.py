"""Game Layer modifier system package.

Exports the public modifier interface: GameModifier, ModifierEffect,
EffectType, PotInstruction, MODIFIER_REGISTRY, apply_modifier_effect(),
and run_modifier_hook(). Concrete modifiers are added in Phase 2 Steps 2-4.
"""

from backend.game.modifiers.base import (
    MODIFIER_REGISTRY,
    EffectType,
    GameModifier,
    ModifierEffect,
    PotInstruction,
    apply_modifier_effect,
    run_modifier_hook,
)

__all__ = [
    "MODIFIER_REGISTRY",
    "EffectType",
    "GameModifier",
    "ModifierEffect",
    "PotInstruction",
    "apply_modifier_effect",
    "run_modifier_hook",
]
