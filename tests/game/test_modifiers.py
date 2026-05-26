"""Tests for the Phase 2 modifier system interface.

Covers EffectType, PotInstruction, ModifierEffect, GameModifier, MODIFIER_REGISTRY,
apply_modifier_effect(), and run_modifier_hook().

No concrete modifiers exist in Phase 2 Step 1. A StubModifier is used to exercise
the hook without depending on DirtyBitch, FollowTheQueen, or HighLowDeclare.

Layer: Game Layer.
"""

from __future__ import annotations

import pytest

from backend.deck.card import Card, DeckConfig, Suit
from backend.deck.deck import Deck
from backend.game.modifiers.base import (
    MODIFIER_REGISTRY,
    EffectType,
    GameModifier,
    ModifierEffect,
    PotInstruction,
    apply_modifier_effect,
    run_modifier_hook,
)
from backend.game.state import (
    ActiveGameConfig,
    BettingState,
    BettingStructure,
    EventType,
    GamePhase,
    GameState,
    GameVariant,
    Pot,
    PlayerState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _AlwaysFireModifier(GameModifier):
    """Fires on every card regardless of game state."""

    def __init__(self) -> None:
        self.trigger_calls: list[Card] = []
        self.effect_calls: int = 0

    def trigger_condition(self, card: Card, game_state: GameState) -> bool:
        self.trigger_calls.append(card)
        return True

    def execute_effect(self, game_state: GameState) -> ModifierEffect:
        self.effect_calls += 1
        return ModifierEffect(
            effect_type=EffectType.NO_OP,
            requires_player_action=False,
            pot_instruction=PotInstruction.CARRY,
            message="StubModifier fired.",
        )


class _NeverFireModifier(GameModifier):
    """Never fires."""

    def trigger_condition(self, card: Card, game_state: GameState) -> bool:
        return False

    def execute_effect(self, game_state: GameState) -> ModifierEffect:
        raise AssertionError("_NeverFireModifier.execute_effect should never be called")


def _make_game_state(
    variant: GameVariant = GameVariant.SEVEN_CARD_STUD,
    modifiers: list[GameModifier] | None = None,
) -> GameState:
    deck_config = DeckConfig.STANDARD()
    active_config = ActiveGameConfig(
        variant=variant,
        modifiers=modifiers or [],
        deck_config=deck_config,
        variant_config={},
    )
    player = PlayerState(
        player_id="p1",
        name="Tester",
        is_bot=False,
        seat_index=0,
        chip_stack=100,
    )
    return GameState(
        hand_id=1,
        session_id=1,
        variant=variant,
        deck_config=deck_config,
        active_game_config=active_config,
        phase=GamePhase.INITIAL_DEAL,
        players=[player],
        dealer_index=0,
        active_player_index=0,
        pot=Pot(),
        betting_state=BettingState(structure=BettingStructure.BRING_IN),
        deck=Deck(deck_config),
    )


def _record_card_dealt(game_state: GameState, card: Card) -> None:
    game_state.record_event(EventType.CARD_DEALT, card=card)


def _record_card_revealed(game_state: GameState, card: Card) -> None:
    game_state.record_event(EventType.CARD_REVEALED, card=card)


# ---------------------------------------------------------------------------
# EffectType
# ---------------------------------------------------------------------------

class TestEffectType:
    def test_all_values_present(self) -> None:
        values = {e.value for e in EffectType}
        assert values == {"REDEAL", "REDEAL_REANTE", "CHANGE_WILD", "NO_OP"}

    def test_no_op_by_name(self) -> None:
        assert EffectType["NO_OP"] is EffectType.NO_OP


# ---------------------------------------------------------------------------
# PotInstruction
# ---------------------------------------------------------------------------

class TestPotInstruction:
    def test_all_values_present(self) -> None:
        values = {e.value for e in PotInstruction}
        assert values == {"CARRY", "SPLIT", "REANTE_ON_TOP", "DISCARD"}


# ---------------------------------------------------------------------------
# ModifierEffect
# ---------------------------------------------------------------------------

class TestModifierEffect:
    def test_fields_accessible(self) -> None:
        effect = ModifierEffect(
            effect_type=EffectType.NO_OP,
            requires_player_action=False,
            pot_instruction=PotInstruction.CARRY,
            message="Test.",
        )
        assert effect.effect_type is EffectType.NO_OP
        assert effect.requires_player_action is False
        assert effect.pot_instruction is PotInstruction.CARRY
        assert effect.message == "Test."

    def test_requires_player_action_true(self) -> None:
        effect = ModifierEffect(
            effect_type=EffectType.NO_OP,
            requires_player_action=True,
            pot_instruction=PotInstruction.DISCARD,
            message="Needs action.",
        )
        assert effect.requires_player_action is True


# ---------------------------------------------------------------------------
# GameModifier abstract class
# ---------------------------------------------------------------------------

class TestGameModifier:
    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            GameModifier()  # type: ignore[abstract]

    def test_concrete_subclass_works(self) -> None:
        m = _AlwaysFireModifier()
        assert isinstance(m, GameModifier)

    def test_trigger_condition_called(self) -> None:
        m = _AlwaysFireModifier()
        gs = _make_game_state()
        card = Card(rank=1, suit=Suit.SPADES)
        result = m.trigger_condition(card, gs)
        assert result is True
        assert card in m.trigger_calls

    def test_execute_effect_returns_modifier_effect(self) -> None:
        m = _AlwaysFireModifier()
        gs = _make_game_state()
        effect = m.execute_effect(gs)
        assert isinstance(effect, ModifierEffect)


# ---------------------------------------------------------------------------
# MODIFIER_REGISTRY
# ---------------------------------------------------------------------------

class TestModifierRegistry:
    def test_registry_is_dict(self) -> None:
        assert isinstance(MODIFIER_REGISTRY, dict)

    def test_registry_is_empty_in_step_1(self) -> None:
        # Concrete modifiers are added in Steps 2-4; registry is empty now.
        assert len(MODIFIER_REGISTRY) == 0

    def test_registry_values_are_game_modifier_subclasses(self) -> None:
        for key, cls in MODIFIER_REGISTRY.items():
            assert isinstance(key, str)
            assert issubclass(cls, GameModifier)


# ---------------------------------------------------------------------------
# apply_modifier_effect
# ---------------------------------------------------------------------------

class TestApplyModifierEffect:
    def test_no_op_records_modifier_fired_event(self) -> None:
        gs = _make_game_state()
        before = len(gs.hand_history)
        effect = ModifierEffect(
            effect_type=EffectType.NO_OP,
            requires_player_action=False,
            pot_instruction=PotInstruction.CARRY,
            message="No-op.",
        )
        result = apply_modifier_effect(gs, effect)
        assert len(result.hand_history) == before + 1
        event = result.hand_history[-1]
        assert event.event_type is EventType.MODIFIER_FIRED
        assert event.metadata["effect_type"] == "NO_OP"

    def test_no_op_returns_same_state_object(self) -> None:
        gs = _make_game_state()
        effect = ModifierEffect(
            effect_type=EffectType.NO_OP,
            requires_player_action=False,
            pot_instruction=PotInstruction.CARRY,
            message="No-op.",
        )
        result = apply_modifier_effect(gs, effect)
        assert result is gs

    def test_no_op_metadata_includes_pot_instruction(self) -> None:
        gs = _make_game_state()
        effect = ModifierEffect(
            effect_type=EffectType.NO_OP,
            requires_player_action=False,
            pot_instruction=PotInstruction.SPLIT,
            message="Split.",
        )
        apply_modifier_effect(gs, effect)
        assert gs.hand_history[-1].metadata["pot_instruction"] == "SPLIT"

    def test_redeal_raises_not_implemented(self) -> None:
        gs = _make_game_state()
        effect = ModifierEffect(
            effect_type=EffectType.REDEAL,
            requires_player_action=False,
            pot_instruction=PotInstruction.CARRY,
            message="Redeal.",
        )
        with pytest.raises(NotImplementedError):
            apply_modifier_effect(gs, effect)

    def test_redeal_reante_raises_not_implemented(self) -> None:
        gs = _make_game_state()
        effect = ModifierEffect(
            effect_type=EffectType.REDEAL_REANTE,
            requires_player_action=False,
            pot_instruction=PotInstruction.REANTE_ON_TOP,
            message="Redeal re-ante.",
        )
        with pytest.raises(NotImplementedError):
            apply_modifier_effect(gs, effect)

    def test_change_wild_raises_not_implemented(self) -> None:
        gs = _make_game_state()
        effect = ModifierEffect(
            effect_type=EffectType.CHANGE_WILD,
            requires_player_action=False,
            pot_instruction=PotInstruction.CARRY,
            message="Change wild.",
        )
        with pytest.raises(NotImplementedError):
            apply_modifier_effect(gs, effect)

    def test_non_no_op_still_records_event_before_raising(self) -> None:
        gs = _make_game_state()
        before = len(gs.hand_history)
        effect = ModifierEffect(
            effect_type=EffectType.REDEAL,
            requires_player_action=False,
            pot_instruction=PotInstruction.CARRY,
            message="Redeal.",
        )
        with pytest.raises(NotImplementedError):
            apply_modifier_effect(gs, effect)
        assert len(gs.hand_history) == before + 1


# ---------------------------------------------------------------------------
# run_modifier_hook
# ---------------------------------------------------------------------------

class TestRunModifierHookEmptyModifiers:
    def test_no_modifiers_is_no_op(self) -> None:
        gs = _make_game_state(modifiers=[])
        card = Card(rank=1, suit=Suit.SPADES)
        _record_card_dealt(gs, card)
        event_count = len(gs.hand_history)
        result = run_modifier_hook(gs, 0)
        assert len(result.hand_history) == event_count

    def test_no_modifiers_returns_same_state(self) -> None:
        gs = _make_game_state(modifiers=[])
        result = run_modifier_hook(gs, 0)
        assert result is gs


class TestRunModifierHookPoulet:
    def test_poulet_skipped_even_with_modifier(self) -> None:
        modifier = _AlwaysFireModifier()
        gs = _make_game_state(variant=GameVariant.POULET, modifiers=[modifier])
        card = Card(rank=5, suit=Suit.HEARTS)
        _record_card_dealt(gs, card)
        run_modifier_hook(gs, 0)
        assert modifier.trigger_calls == []
        assert modifier.effect_calls == 0


class TestRunModifierHookNoNewCards:
    def test_no_events_in_range_is_no_op(self) -> None:
        modifier = _AlwaysFireModifier()
        gs = _make_game_state(modifiers=[modifier])
        snapshot = len(gs.hand_history)
        run_modifier_hook(gs, snapshot)
        assert modifier.trigger_calls == []

    def test_events_before_snapshot_ignored(self) -> None:
        modifier = _AlwaysFireModifier()
        gs = _make_game_state(modifiers=[modifier])
        card = Card(rank=3, suit=Suit.CLUBS)
        _record_card_dealt(gs, card)
        # Snapshot taken after the card was dealt — no new cards after snapshot.
        snapshot = len(gs.hand_history)
        run_modifier_hook(gs, snapshot)
        assert modifier.trigger_calls == []

    def test_non_deal_events_do_not_trigger_modifier(self) -> None:
        modifier = _AlwaysFireModifier()
        gs = _make_game_state(modifiers=[modifier])
        snapshot = len(gs.hand_history)
        gs.record_event(EventType.BET_PLACED, amount=2)
        gs.record_event(EventType.FOLD)
        run_modifier_hook(gs, snapshot)
        assert modifier.trigger_calls == []


class TestRunModifierHookTriggers:
    def test_modifier_fires_on_dealt_card(self) -> None:
        modifier = _AlwaysFireModifier()
        gs = _make_game_state(modifiers=[modifier])
        snapshot = len(gs.hand_history)
        card = Card(rank=7, suit=Suit.DIAMONDS)
        _record_card_dealt(gs, card)
        run_modifier_hook(gs, snapshot)
        assert card in modifier.trigger_calls
        assert modifier.effect_calls == 1

    def test_modifier_fires_on_revealed_card(self) -> None:
        modifier = _AlwaysFireModifier()
        gs = _make_game_state(modifiers=[modifier])
        snapshot = len(gs.hand_history)
        card = Card(rank=12, suit=Suit.SPADES)
        _record_card_revealed(gs, card)
        run_modifier_hook(gs, snapshot)
        assert card in modifier.trigger_calls
        assert modifier.effect_calls == 1

    def test_never_fire_modifier_does_not_call_execute_effect(self) -> None:
        modifier = _NeverFireModifier()
        gs = _make_game_state(modifiers=[modifier])
        snapshot = len(gs.hand_history)
        _record_card_dealt(gs, Card(rank=5, suit=Suit.HEARTS))
        run_modifier_hook(gs, snapshot)
        # No assertion needed — _NeverFireModifier.execute_effect raises if called.

    def test_face_down_card_dealt_without_card_obj_skipped(self) -> None:
        modifier = _AlwaysFireModifier()
        gs = _make_game_state(modifiers=[modifier])
        snapshot = len(gs.hand_history)
        # Face-down deal records event without a Card object.
        gs.record_event(EventType.CARD_DEALT, card=None)
        run_modifier_hook(gs, snapshot)
        assert modifier.trigger_calls == []


class TestRunModifierHookStackingBehavior:
    def test_no_stacking_stops_after_first_fire(self) -> None:
        mod1 = _AlwaysFireModifier()
        mod2 = _AlwaysFireModifier()
        gs = _make_game_state(modifiers=[mod1, mod2])
        snapshot = len(gs.hand_history)
        _record_card_dealt(gs, Card(rank=4, suit=Suit.CLUBS))
        run_modifier_hook(gs, snapshot, modifier_stacking=False)
        # mod1 fires; mod2 is skipped because stacking is off.
        assert mod1.effect_calls == 1
        assert mod2.effect_calls == 0

    def test_stacking_allows_both_modifiers_to_fire(self) -> None:
        mod1 = _AlwaysFireModifier()
        mod2 = _AlwaysFireModifier()
        gs = _make_game_state(modifiers=[mod1, mod2])
        snapshot = len(gs.hand_history)
        _record_card_dealt(gs, Card(rank=4, suit=Suit.CLUBS))
        run_modifier_hook(gs, snapshot, modifier_stacking=True)
        assert mod1.effect_calls == 1
        assert mod2.effect_calls == 1

    def test_no_stacking_stops_after_first_card_match_within_modifier(self) -> None:
        modifier = _AlwaysFireModifier()
        gs = _make_game_state(modifiers=[modifier])
        snapshot = len(gs.hand_history)
        # Two cards dealt; with no stacking, only the first triggers the modifier.
        _record_card_dealt(gs, Card(rank=2, suit=Suit.HEARTS))
        _record_card_dealt(gs, Card(rank=3, suit=Suit.DIAMONDS))
        run_modifier_hook(gs, snapshot, modifier_stacking=False)
        assert modifier.effect_calls == 1

    def test_stacking_fires_for_each_matching_card(self) -> None:
        modifier = _AlwaysFireModifier()
        gs = _make_game_state(modifiers=[modifier])
        snapshot = len(gs.hand_history)
        _record_card_dealt(gs, Card(rank=2, suit=Suit.HEARTS))
        _record_card_dealt(gs, Card(rank=3, suit=Suit.DIAMONDS))
        run_modifier_hook(gs, snapshot, modifier_stacking=True)
        # With stacking enabled, the modifier fires for each matching card.
        assert modifier.effect_calls == 2

    def test_returns_updated_game_state(self) -> None:
        modifier = _AlwaysFireModifier()
        gs = _make_game_state(modifiers=[modifier])
        snapshot = len(gs.hand_history)
        _record_card_dealt(gs, Card(rank=9, suit=Suit.CLUBS))
        result = run_modifier_hook(gs, snapshot)
        # NO_OP modifier appends MODIFIER_FIRED event.
        assert any(e.event_type is EventType.MODIFIER_FIRED for e in result.hand_history)
