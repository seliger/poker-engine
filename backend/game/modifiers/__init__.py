"""Game Layer modifier system package.

Exports the public modifier interface and all concrete modifier implementations.
MODIFIER_REGISTRY is populated here to avoid circular imports in base.py.
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
from backend.game.modifiers.high_low_declare import HighLowDeclareModifier

# Populate registry: concrete modifiers added in Phase 2 Steps 2-4.
MODIFIER_REGISTRY["HIGH_LOW_DECLARE"] = HighLowDeclareModifier

__all__ = [
    "MODIFIER_REGISTRY",
    "EffectType",
    "GameModifier",
    "HighLowDeclareModifier",
    "ModifierEffect",
    "PotInstruction",
    "apply_modifier_effect",
    "run_modifier_hook",
]
