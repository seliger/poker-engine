"""Tests for the Phase 2 modifier system interface and HighLowDeclareModifier.

Covers EffectType, PotInstruction, ModifierEffect, GameModifier, MODIFIER_REGISTRY,
apply_modifier_effect(), run_modifier_hook(), HighLowDeclareModifier behaviour,
and integration of HighLowDeclareModifier with SevenCardStudVariant.

Layer: Game Layer.
"""

from __future__ import annotations

import pytest

from backend.deck.card import Card, DeckConfig, Suit
from backend.deck.deck import Deck
from backend.evaluators.base import Declaration
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
    PositionedCard,
)
from backend.game.variants.base import PlayerAction
from backend.game.variants.seven_card_stud import SevenCardStudVariant
from backend.game.visibility import ActionType


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

    def test_registry_has_high_low_declare(self) -> None:
        assert "HIGH_LOW_DECLARE" in MODIFIER_REGISTRY

    def test_registry_not_empty_after_step_2(self) -> None:
        assert len(MODIFIER_REGISTRY) >= 1

    def test_registry_values_are_game_modifier_subclasses(self) -> None:
        for key, cls in MODIFIER_REGISTRY.items():
            assert isinstance(key, str)
            assert issubclass(cls, GameModifier)

    def test_registry_high_low_declare_class(self) -> None:
        assert MODIFIER_REGISTRY["HIGH_LOW_DECLARE"] is HighLowDeclareModifier


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


# ---------------------------------------------------------------------------
# HighLowDeclareModifier unit tests
# ---------------------------------------------------------------------------

class TestHighLowDeclareModifier:
    def test_trigger_condition_always_false(self) -> None:
        modifier = HighLowDeclareModifier()
        gs = _make_game_state()
        card = Card(rank=7, suit=Suit.HEARTS)
        assert modifier.trigger_condition(card, gs) is False

    def test_execute_effect_returns_no_op(self) -> None:
        modifier = HighLowDeclareModifier()
        gs = _make_game_state()
        effect = modifier.execute_effect(gs)
        assert effect.effect_type is EffectType.NO_OP

    def test_execute_effect_requires_player_action(self) -> None:
        modifier = HighLowDeclareModifier()
        gs = _make_game_state()
        effect = modifier.execute_effect(gs)
        assert effect.requires_player_action is True

    def test_get_phase_injection_before_showdown_returns_declare(self) -> None:
        modifier = HighLowDeclareModifier()
        gs = _make_game_state()
        result = modifier.get_phase_injection(GamePhase.SHOWDOWN, gs)
        assert result is GamePhase.DECLARE

    def test_get_phase_injection_other_phases_return_none(self) -> None:
        modifier = HighLowDeclareModifier()
        gs = _make_game_state()
        for phase in (GamePhase.ANTE, GamePhase.BET_ROUND, GamePhase.POT_DISTRIBUTION):
            assert modifier.get_phase_injection(phase, gs) is None

    def test_get_phase_injection_no_reinject_after_declare_done(self) -> None:
        modifier = HighLowDeclareModifier()
        gs = _make_game_state()
        gs.active_game_config.variant_config["declare_done"] = True
        assert modifier.get_phase_injection(GamePhase.SHOWDOWN, gs) is None

    def test_both_ways_requires_scoop_defaults_true(self) -> None:
        modifier = HighLowDeclareModifier()
        assert modifier.both_ways_requires_scoop is True

    def test_both_ways_requires_scoop_configurable_false(self) -> None:
        modifier = HighLowDeclareModifier(both_ways_requires_scoop=False)
        assert modifier.both_ways_requires_scoop is False

    def test_is_game_modifier_subclass(self) -> None:
        assert isinstance(HighLowDeclareModifier(), GameModifier)


# ---------------------------------------------------------------------------
# SevenCardStudVariant + HighLowDeclareModifier integration tests
# ---------------------------------------------------------------------------

def _make_stud_variant() -> SevenCardStudVariant:
    return SevenCardStudVariant(ante_amount=1, bring_in_amount=1, small_bet=2, big_bet=4)


def _make_stud_state(
    player_ids: list[str],
    modifiers: list[GameModifier] | None = None,
) -> GameState:
    deck_config = DeckConfig.STANDARD()
    mods = modifiers or []
    players = [
        PlayerState(
            player_id=pid,
            name=pid,
            is_bot=False,
            seat_index=i,
            chip_stack=100,
        )
        for i, pid in enumerate(player_ids)
    ]
    return GameState(
        hand_id=1,
        session_id=1,
        variant=GameVariant.SEVEN_CARD_STUD,
        deck_config=deck_config,
        active_game_config=ActiveGameConfig(
            variant=GameVariant.SEVEN_CARD_STUD,
            modifiers=mods,
            deck_config=deck_config,
            variant_config={"phase_index": 0},
        ),
        phase=GamePhase.SETUP,
        players=players,
        dealer_index=0,
        active_player_index=0,
        pot=Pot(),
        betting_state=BettingState(structure=BettingStructure.BRING_IN),
        deck=Deck(deck_config),
    )


def _give_player_seven_cards(player: PlayerState, start_rank: int = 2) -> None:
    """Assign 7 known cards to a player (all face-up for test simplicity)."""
    suits = [Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS, Suit.SPADES,
             Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS]
    player.hole_cards = [
        PositionedCard(Card(rank=start_rank + i, suit=suits[i]), is_face_up=True, position_index=i)
        for i in range(7)
    ]


class TestHighLowDeclareIntegration:

    def test_declare_phase_injected_before_showdown(self) -> None:
        """advance_phase to SHOWDOWN injects DECLARE when modifier is active."""
        modifier = HighLowDeclareModifier()
        variant = _make_stud_variant()
        gs = _make_stud_state(["alice", "bob"], modifiers=[modifier])
        gs = variant.initialize(gs, gs.active_game_config)

        # Position at the last BET_ROUND (index 11) just before SHOWDOWN.
        showdown_index = 12  # SHOWDOWN is at index 12 in _PHASE_SEQUENCE
        gs.active_game_config.variant_config["phase_index"] = showdown_index - 1
        gs.phase = GamePhase.BET_ROUND

        gs = variant.advance_phase(gs)
        assert gs.phase is GamePhase.DECLARE

    def test_declare_phase_not_injected_after_declare_done(self) -> None:
        """Once declare_done=True, advance_phase goes straight to SHOWDOWN."""
        modifier = HighLowDeclareModifier()
        variant = _make_stud_variant()
        gs = _make_stud_state(["alice", "bob"], modifiers=[modifier])
        gs = variant.initialize(gs, gs.active_game_config)

        showdown_index = 12
        gs.active_game_config.variant_config["phase_index"] = showdown_index - 1
        gs.active_game_config.variant_config["declare_done"] = True
        gs.phase = GamePhase.BET_ROUND

        gs = variant.advance_phase(gs)
        assert gs.phase is GamePhase.SHOWDOWN

    def test_legal_actions_during_declare_for_active_player(self) -> None:
        """During DECLARE, active player gets HIGH, LOW, BOTH options."""
        modifier = HighLowDeclareModifier()
        variant = _make_stud_variant()
        gs = _make_stud_state(["alice", "bob"], modifiers=[modifier])
        gs = variant.initialize(gs, gs.active_game_config)
        gs.phase = GamePhase.DECLARE
        gs.active_player_index = 0  # alice's turn

        actions = variant.get_legal_actions(gs, "alice")
        action_types = {a.action_type for a in actions}
        assert ActionType.DECLARE_HIGH in action_types
        assert ActionType.DECLARE_LOW in action_types
        assert ActionType.DECLARE_BOTH in action_types

    def test_legal_actions_empty_for_non_active_player_in_declare(self) -> None:
        """During DECLARE, non-active player gets no legal actions."""
        modifier = HighLowDeclareModifier()
        variant = _make_stud_variant()
        gs = _make_stud_state(["alice", "bob"], modifiers=[modifier])
        gs = variant.initialize(gs, gs.active_game_config)
        gs.phase = GamePhase.DECLARE
        gs.active_player_index = 0  # alice's turn

        actions = variant.get_legal_actions(gs, "bob")
        assert actions == []

    def test_declare_action_stored_on_player(self) -> None:
        """Applying DECLARE_HIGH stores Declaration.HIGH on the player."""
        modifier = HighLowDeclareModifier()
        variant = _make_stud_variant()
        gs = _make_stud_state(["alice", "bob"], modifiers=[modifier])
        gs = variant.initialize(gs, gs.active_game_config)
        gs.phase = GamePhase.DECLARE
        gs.active_player_index = 0

        gs = variant.apply_action(gs, "alice", PlayerAction(action_type=ActionType.DECLARE_HIGH))
        assert gs.players[0].declaration is Declaration.HIGH

    def test_declare_low_stored_on_player(self) -> None:
        modifier = HighLowDeclareModifier()
        variant = _make_stud_variant()
        gs = _make_stud_state(["alice", "bob"], modifiers=[modifier])
        gs = variant.initialize(gs, gs.active_game_config)
        gs.phase = GamePhase.DECLARE
        gs.active_player_index = 0

        gs = variant.apply_action(gs, "alice", PlayerAction(action_type=ActionType.DECLARE_LOW))
        assert gs.players[0].declaration is Declaration.LOW

    def test_declare_both_stored_on_player(self) -> None:
        modifier = HighLowDeclareModifier()
        variant = _make_stud_variant()
        gs = _make_stud_state(["alice", "bob"], modifiers=[modifier])
        gs = variant.initialize(gs, gs.active_game_config)
        gs.phase = GamePhase.DECLARE
        gs.active_player_index = 0

        gs = variant.apply_action(gs, "alice", PlayerAction(action_type=ActionType.DECLARE_BOTH))
        assert gs.players[0].declaration is Declaration.BOTH

    def test_declare_records_declaration_made_event(self) -> None:
        modifier = HighLowDeclareModifier()
        variant = _make_stud_variant()
        gs = _make_stud_state(["alice", "bob"], modifiers=[modifier])
        gs = variant.initialize(gs, gs.active_game_config)
        gs.phase = GamePhase.DECLARE
        gs.active_player_index = 0

        before = len(gs.hand_history)
        gs = variant.apply_action(gs, "alice", PlayerAction(action_type=ActionType.DECLARE_HIGH))
        assert len(gs.hand_history) == before + 1
        assert gs.hand_history[-1].event_type is EventType.DECLARATION_MADE

    def test_active_player_advances_after_declare(self) -> None:
        """After alice declares, active_player_index moves to bob."""
        modifier = HighLowDeclareModifier()
        variant = _make_stud_variant()
        gs = _make_stud_state(["alice", "bob"], modifiers=[modifier])
        gs = variant.initialize(gs, gs.active_game_config)
        gs.phase = GamePhase.DECLARE
        gs.active_player_index = 0

        gs = variant.apply_action(gs, "alice", PlayerAction(action_type=ActionType.DECLARE_HIGH))
        assert gs.active_player_index == 1  # bob's turn now

    def test_declare_phase_complete_when_all_declared(self) -> None:
        modifier = HighLowDeclareModifier()
        variant = _make_stud_variant()
        gs = _make_stud_state(["alice", "bob"], modifiers=[modifier])
        gs = variant.initialize(gs, gs.active_game_config)
        gs.phase = GamePhase.DECLARE
        gs.players[0].declaration = Declaration.HIGH
        gs.players[1].declaration = Declaration.LOW

        assert variant.is_phase_complete(gs, GamePhase.DECLARE) is True

    def test_declare_phase_not_complete_until_all_declared(self) -> None:
        modifier = HighLowDeclareModifier()
        variant = _make_stud_variant()
        gs = _make_stud_state(["alice", "bob"], modifiers=[modifier])
        gs = variant.initialize(gs, gs.active_game_config)
        gs.phase = GamePhase.DECLARE
        gs.players[0].declaration = Declaration.HIGH
        # bob has not declared yet

        assert variant.is_phase_complete(gs, GamePhase.DECLARE) is False

    def test_declare_advance_sets_declare_done_and_goes_to_showdown(self) -> None:
        modifier = HighLowDeclareModifier()
        variant = _make_stud_variant()
        gs = _make_stud_state(["alice", "bob"], modifiers=[modifier])
        gs = variant.initialize(gs, gs.active_game_config)
        gs.phase = GamePhase.DECLARE

        gs = variant.advance_phase(gs)
        assert gs.phase is GamePhase.SHOWDOWN
        assert gs.active_game_config.variant_config.get("declare_done") is True

    def test_pot_split_high_and_low_declarants(self) -> None:
        """High declarant wins high half; low declarant wins low half; pot split 50/50."""
        modifier = HighLowDeclareModifier()
        variant = _make_stud_variant()
        gs = _make_stud_state(["alice", "bob"], modifiers=[modifier])
        gs = variant.initialize(gs, gs.active_game_config)

        # Alice: strong high hand (A-K-Q-J-10-9-8 of spades → Royal Flush for HIGH).
        alice_cards = [
            PositionedCard(Card(1, Suit.SPADES), True, 0),
            PositionedCard(Card(13, Suit.SPADES), True, 1),
            PositionedCard(Card(12, Suit.SPADES), True, 2),
            PositionedCard(Card(11, Suit.SPADES), True, 3),
            PositionedCard(Card(10, Suit.SPADES), True, 4),
            PositionedCard(Card(9, Suit.CLUBS), True, 5),
            PositionedCard(Card(8, Suit.DIAMONDS), True, 6),
        ]
        # Bob: strong low hand (A-2-3-4-5-7-8 mixed suits → wheel for LOW).
        bob_cards = [
            PositionedCard(Card(1, Suit.HEARTS), True, 0),
            PositionedCard(Card(2, Suit.CLUBS), True, 1),
            PositionedCard(Card(3, Suit.DIAMONDS), True, 2),
            PositionedCard(Card(4, Suit.HEARTS), True, 3),
            PositionedCard(Card(5, Suit.CLUBS), True, 4),
            PositionedCard(Card(7, Suit.DIAMONDS), True, 5),
            PositionedCard(Card(8, Suit.HEARTS), True, 6),
        ]
        gs.players[0].hole_cards = alice_cards
        gs.players[1].hole_cards = bob_cards

        # Set up pot (20 chips total).
        from backend.game.pot import PotManager
        variant._pot_manager = PotManager()
        variant._pot_manager.add_ante("alice", 10)
        variant._pot_manager.add_ante("bob", 10)

        # Set declarations.
        gs.players[0].declaration = Declaration.HIGH   # alice wins high
        gs.players[1].declaration = Declaration.LOW    # bob wins low
        gs.phase = GamePhase.POT_DISTRIBUTION

        starting_alice = gs.players[0].chip_stack
        starting_bob = gs.players[1].chip_stack

        gs = variant.execute_phase(gs, GamePhase.POT_DISTRIBUTION)

        # With 20 chips: high wins 10+1 (odd chip), low wins 10.
        # (Exact split: divmod(20, 2) = 10, 0 → each gets 10)
        alice_won = gs.players[0].chip_stack - starting_alice
        bob_won = gs.players[1].chip_stack - starting_bob
        assert alice_won > 0
        assert bob_won > 0
        assert alice_won + bob_won == 20

    def test_scoop_or_bust_both_wins_both(self) -> None:
        """BOTH declarant who wins both directions scoops the entire pot."""
        modifier = HighLowDeclareModifier(both_ways_requires_scoop=True)
        variant = _make_stud_variant()
        gs = _make_stud_state(["alice", "bob"], modifiers=[modifier])
        gs = variant.initialize(gs, gs.active_game_config)

        # Alice: strong high hand and strong low hand
        # Royal Flush for high + can be A-low for low; but it won't beat Bob's wheel.
        # Give alice a Royal Flush (best high); bob has terrible cards.
        alice_cards = [
            PositionedCard(Card(1, Suit.SPADES), True, 0),
            PositionedCard(Card(13, Suit.SPADES), True, 1),
            PositionedCard(Card(12, Suit.SPADES), True, 2),
            PositionedCard(Card(11, Suit.SPADES), True, 3),
            PositionedCard(Card(10, Suit.SPADES), True, 4),
            PositionedCard(Card(2, Suit.CLUBS), True, 5),
            PositionedCard(Card(3, Suit.CLUBS), True, 6),
        ]
        bob_cards = [
            PositionedCard(Card(9, Suit.HEARTS), True, 0),
            PositionedCard(Card(10, Suit.HEARTS), True, 1),
            PositionedCard(Card(11, Suit.HEARTS), True, 2),
            PositionedCard(Card(12, Suit.HEARTS), True, 3),
            PositionedCard(Card(6, Suit.DIAMONDS), True, 4),
            PositionedCard(Card(7, Suit.DIAMONDS), True, 5),
            PositionedCard(Card(8, Suit.DIAMONDS), True, 6),
        ]
        gs.players[0].hole_cards = alice_cards
        gs.players[1].hole_cards = bob_cards

        from backend.game.pot import PotManager
        variant._pot_manager = PotManager()
        variant._pot_manager.add_ante("alice", 10)
        variant._pot_manager.add_ante("bob", 10)

        # Alice declares BOTH; bob declares HIGH.
        # Alice has Royal Flush (best high). She also has A-2-3 (low potential).
        # We just need alice to win at least high. Bob won't win low since he doesn't declare it.
        # If alice wins both: she scoops all 20.
        gs.players[0].declaration = Declaration.BOTH
        gs.players[1].declaration = Declaration.HIGH
        gs.phase = GamePhase.POT_DISTRIBUTION

        starting_alice = gs.players[0].chip_stack
        starting_bob = gs.players[1].chip_stack

        gs = variant.execute_phase(gs, GamePhase.POT_DISTRIBUTION)

        alice_won = gs.players[0].chip_stack - starting_alice
        bob_won = gs.players[1].chip_stack - starting_bob
        # Alice declared BOTH and wins both (only alice declared LOW). She scoops.
        assert alice_won == 20
        assert bob_won == 0

    def test_scoop_or_bust_both_loses_gets_nothing(self) -> None:
        """BOTH declarant who fails to win both directions receives nothing."""
        modifier = HighLowDeclareModifier(both_ways_requires_scoop=True)
        variant = _make_stud_variant()
        gs = _make_stud_state(["alice", "bob", "carol"], modifiers=[modifier])
        gs = variant.initialize(gs, gs.active_game_config)

        # Alice: BOTH (will fail low — she has high cards only)
        alice_cards = [
            PositionedCard(Card(1, Suit.SPADES), True, 0),
            PositionedCard(Card(13, Suit.SPADES), True, 1),
            PositionedCard(Card(12, Suit.SPADES), True, 2),
            PositionedCard(Card(11, Suit.SPADES), True, 3),
            PositionedCard(Card(10, Suit.SPADES), True, 4),
            PositionedCard(Card(9, Suit.CLUBS), True, 5),
            PositionedCard(Card(8, Suit.DIAMONDS), True, 6),
        ]
        # Bob: HIGH only — decent high hand
        bob_cards = [
            PositionedCard(Card(2, Suit.HEARTS), True, 0),
            PositionedCard(Card(4, Suit.CLUBS), True, 1),
            PositionedCard(Card(6, Suit.DIAMONDS), True, 2),
            PositionedCard(Card(7, Suit.HEARTS), True, 3),
            PositionedCard(Card(9, Suit.SPADES), True, 4),
            PositionedCard(Card(10, Suit.DIAMONDS), True, 5),
            PositionedCard(Card(11, Suit.CLUBS), True, 6),
        ]
        # Carol: LOW only — wheel
        carol_cards = [
            PositionedCard(Card(1, Suit.CLUBS), True, 0),
            PositionedCard(Card(2, Suit.DIAMONDS), True, 1),
            PositionedCard(Card(3, Suit.HEARTS), True, 2),
            PositionedCard(Card(4, Suit.SPADES), True, 3),
            PositionedCard(Card(5, Suit.CLUBS), True, 4),
            PositionedCard(Card(6, Suit.HEARTS), True, 5),
            PositionedCard(Card(7, Suit.CLUBS), True, 6),
        ]
        gs.players[0].hole_cards = alice_cards  # alice
        gs.players[1].hole_cards = bob_cards    # bob
        gs.players[2].hole_cards = carol_cards  # carol

        from backend.game.pot import PotManager
        variant._pot_manager = PotManager()
        variant._pot_manager.add_ante("alice", 10)
        variant._pot_manager.add_ante("bob", 10)
        variant._pot_manager.add_ante("carol", 10)

        # Alice declares BOTH but has a terrible low hand (high cards only)
        # → she won't beat carol's wheel for low → disqualified.
        # Bob wins high; carol wins low.
        gs.players[0].declaration = Declaration.BOTH
        gs.players[1].declaration = Declaration.HIGH
        gs.players[2].declaration = Declaration.LOW
        gs.phase = GamePhase.POT_DISTRIBUTION

        starting = {p.player_id: p.chip_stack for p in gs.players}
        gs = variant.execute_phase(gs, GamePhase.POT_DISTRIBUTION)
        alice_won = gs.players[0].chip_stack - starting["alice"]
        bob_won = gs.players[1].chip_stack - starting["bob"]
        carol_won = gs.players[2].chip_stack - starting["carol"]

        assert alice_won == 0, "Alice (BOTH, fails low) should receive nothing"
        assert bob_won > 0, "Bob (HIGH winner) should receive high half"
        assert carol_won > 0, "Carol (LOW winner) should receive low half"
        assert bob_won + carol_won == 30

    def test_scoop_or_bust_disabled_both_gets_won_directions(self) -> None:
        """When both_ways_requires_scoop=False, BOTH declarant wins each direction independently."""
        modifier = HighLowDeclareModifier(both_ways_requires_scoop=False)
        variant = _make_stud_variant()
        gs = _make_stud_state(["alice", "bob"], modifiers=[modifier])
        gs = variant.initialize(gs, gs.active_game_config)

        # Alice declares BOTH; she has a great high hand but terrible low.
        # Bob declares LOW and has a better low hand.
        # With scoop-or-bust disabled: alice still wins high half; bob wins low half.
        alice_cards = [
            PositionedCard(Card(1, Suit.SPADES), True, 0),
            PositionedCard(Card(13, Suit.SPADES), True, 1),
            PositionedCard(Card(12, Suit.SPADES), True, 2),
            PositionedCard(Card(11, Suit.SPADES), True, 3),
            PositionedCard(Card(10, Suit.SPADES), True, 4),
            PositionedCard(Card(9, Suit.CLUBS), True, 5),
            PositionedCard(Card(8, Suit.DIAMONDS), True, 6),
        ]
        bob_cards = [
            PositionedCard(Card(1, Suit.HEARTS), True, 0),
            PositionedCard(Card(2, Suit.CLUBS), True, 1),
            PositionedCard(Card(3, Suit.DIAMONDS), True, 2),
            PositionedCard(Card(4, Suit.HEARTS), True, 3),
            PositionedCard(Card(5, Suit.CLUBS), True, 4),
            PositionedCard(Card(6, Suit.DIAMONDS), True, 5),
            PositionedCard(Card(7, Suit.HEARTS), True, 6),
        ]
        gs.players[0].hole_cards = alice_cards
        gs.players[1].hole_cards = bob_cards

        from backend.game.pot import PotManager
        variant._pot_manager = PotManager()
        variant._pot_manager.add_ante("alice", 10)
        variant._pot_manager.add_ante("bob", 10)

        gs.players[0].declaration = Declaration.BOTH
        gs.players[1].declaration = Declaration.LOW
        gs.phase = GamePhase.POT_DISTRIBUTION

        starting = {p.player_id: p.chip_stack for p in gs.players}
        gs = variant.execute_phase(gs, GamePhase.POT_DISTRIBUTION)
        alice_won = gs.players[0].chip_stack - starting["alice"]
        bob_won = gs.players[1].chip_stack - starting["bob"]

        # Alice wins high half; bob wins low half. Both get something.
        assert alice_won > 0, "Alice (BOTH, wins high) should receive high half"
        assert bob_won > 0, "Bob (LOW winner) should receive low half"
        assert alice_won + bob_won == 20
