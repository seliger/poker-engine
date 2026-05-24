"""Unit tests for SevenCardStudVariant — Phase 1 scope.

Covers: bring-in assignment, 7 cards dealt per player, deck exhaustion
community river, showdown evaluation, and the single-player-wins shortcut.
"""

from __future__ import annotations

import pytest

from backend.deck.card import Card, DeckConfig, Suit
from backend.deck.deck import Deck
from backend.game.state import (
    ActiveGameConfig,
    BettingState,
    BettingStructure,
    GamePhase,
    GameState,
    GameVariant,
    PlayerState,
    PositionedCard,
    Pot,
)
from backend.game.variants.base import PlayerAction
from backend.game.variants.seven_card_stud import SevenCardStudVariant
from backend.game.visibility import ActionType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_variant() -> SevenCardStudVariant:
    return SevenCardStudVariant(
        ante_amount=1,
        bring_in_amount=1,
        small_bet=2,
        big_bet=4,
    )


def _make_game_state(
    player_ids: list[str],
    deck: Deck | None = None,
    carry: int = 0,
) -> GameState:
    deck_config = DeckConfig.STANDARD()
    if deck is None:
        deck = Deck(deck_config)
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
    pot = Pot(carry_amount=carry)
    return GameState(
        hand_id=1,
        session_id=1,
        variant=GameVariant.SEVEN_CARD_STUD,
        deck_config=deck_config,
        active_game_config=ActiveGameConfig(
            variant=GameVariant.SEVEN_CARD_STUD,
            modifiers=[],
            deck_config=deck_config,
            variant_config={"phase_index": 0},
        ),
        phase=GamePhase.SETUP,
        players=players,
        dealer_index=0,
        active_player_index=0,
        pot=pot,
        betting_state=BettingState(structure=BettingStructure.BRING_IN),
        deck=deck,
    )


def _run_through_phase(
    variant: SevenCardStudVariant,
    state: GameState,
    phase: GamePhase,
) -> GameState:
    """Execute a phase and advance past it."""
    state = variant.execute_phase(state, phase)
    state = variant.advance_phase(state)
    return state


def _setup_ante_deal(
    variant: SevenCardStudVariant,
    state: GameState,
) -> GameState:
    """Run SETUP → ANTE → INITIAL_DEAL and return state at BET_ROUND."""
    state = variant.initialize(state, state.active_game_config)
    state = variant.execute_phase(state, GamePhase.SETUP)
    state = variant.advance_phase(state)
    state = variant.execute_phase(state, GamePhase.ANTE)
    state = variant.advance_phase(state)
    state = variant.execute_phase(state, GamePhase.INITIAL_DEAL)
    state = variant.advance_phase(state)
    return state


# ---------------------------------------------------------------------------
# Card deal tests
# ---------------------------------------------------------------------------

class TestInitialDeal:

    def test_initial_deal_gives_three_cards_per_player(self) -> None:
        variant = _make_variant()
        state = _make_game_state(["alice", "bob", "carol"])
        state = _setup_ante_deal(variant, state)

        for player in state.players:
            assert len(player.hole_cards) == 3

    def test_initial_deal_has_two_down_one_up(self) -> None:
        variant = _make_variant()
        state = _make_game_state(["alice", "bob"])
        state = _setup_ante_deal(variant, state)

        for player in state.players:
            face_up_count = sum(1 for pc in player.hole_cards if pc.is_face_up)
            face_down_count = sum(1 for pc in player.hole_cards if not pc.is_face_up)
            assert face_up_count == 1
            assert face_down_count == 2

    def test_seven_cards_dealt_across_all_rounds(self) -> None:
        """Each player ends up with 7 cards after all four deal rounds."""
        variant = _make_variant()
        state = _make_game_state(["alice", "bob"])
        state = variant.initialize(state, state.active_game_config)

        # Run all phases automatically (no bets to process).
        phases = variant.get_phase_sequence()
        # Skip phases that require interactive betting; just process deals and setup.
        deal_phases = {GamePhase.SETUP, GamePhase.ANTE, GamePhase.INITIAL_DEAL, GamePhase.DEAL_ROUND}

        for phase in phases:
            if phase in deal_phases:
                state.active_game_config.variant_config["phase_index"] = phases.index(phase)
                # Fixup: find current index from hand history isn't needed;
                # use the sequence index directly.
                break

        # Manually advance through all non-bet phases.
        state = variant.execute_phase(state, GamePhase.SETUP)
        state.active_game_config.variant_config["phase_index"] = 0
        state = variant.advance_phase(state)

        state = variant.execute_phase(state, GamePhase.ANTE)
        state.active_game_config.variant_config["phase_index"] = 1
        state = variant.advance_phase(state)

        state = variant.execute_phase(state, GamePhase.INITIAL_DEAL)
        state.active_game_config.variant_config["phase_index"] = 2
        state = variant.advance_phase(state)

        # BET_ROUND 1: skip by marking all players acted.
        state = variant.execute_phase(state, GamePhase.BET_ROUND)
        state.active_game_config.variant_config["phase_index"] = 3
        state.betting_state.players_acted = [p.player_id for p in state.players]
        state.betting_state.current_bet = 0
        for p in state.players:
            p.total_bet_this_round = 0
        state = variant.advance_phase(state)

        # DEAL_ROUND 1 (phase_index=4)
        state.active_game_config.variant_config["phase_index"] = 4
        state = variant.execute_phase(state, GamePhase.DEAL_ROUND)
        state = variant.advance_phase(state)

        # BET_ROUND 2
        state.active_game_config.variant_config["phase_index"] = 5
        state = variant.execute_phase(state, GamePhase.BET_ROUND)
        state.betting_state.players_acted = [p.player_id for p in state.players]
        state.betting_state.current_bet = 0
        for p in state.players:
            p.total_bet_this_round = 0
        state = variant.advance_phase(state)

        # DEAL_ROUND 2
        state.active_game_config.variant_config["phase_index"] = 6
        state = variant.execute_phase(state, GamePhase.DEAL_ROUND)
        state = variant.advance_phase(state)

        # BET_ROUND 3
        state.active_game_config.variant_config["phase_index"] = 7
        state = variant.execute_phase(state, GamePhase.BET_ROUND)
        state.betting_state.players_acted = [p.player_id for p in state.players]
        state.betting_state.current_bet = 0
        for p in state.players:
            p.total_bet_this_round = 0
        state = variant.advance_phase(state)

        # DEAL_ROUND 3
        state.active_game_config.variant_config["phase_index"] = 8
        state = variant.execute_phase(state, GamePhase.DEAL_ROUND)
        state = variant.advance_phase(state)

        # BET_ROUND 4
        state.active_game_config.variant_config["phase_index"] = 9
        state = variant.execute_phase(state, GamePhase.BET_ROUND)
        state.betting_state.players_acted = [p.player_id for p in state.players]
        state.betting_state.current_bet = 0
        for p in state.players:
            p.total_bet_this_round = 0
        state = variant.advance_phase(state)

        # DEAL_ROUND 4 (river)
        state.active_game_config.variant_config["phase_index"] = 10
        state = variant.execute_phase(state, GamePhase.DEAL_ROUND)

        # Each player should have 7 cards.
        for player in state.players:
            assert len(player.hole_cards) == 7, (
                f"{player.player_id} has {len(player.hole_cards)} cards, expected 7"
            )

    def test_river_card_is_face_down(self) -> None:
        """The final (river) deal round deals a face-down card."""
        variant = _make_variant()
        state = _make_game_state(["alice", "bob"])
        state = variant.initialize(state, state.active_game_config)

        # Get state to river deal.
        state = variant.execute_phase(state, GamePhase.SETUP)
        state.active_game_config.variant_config["phase_index"] = 0
        state = variant.advance_phase(state)
        state = variant.execute_phase(state, GamePhase.ANTE)
        state.active_game_config.variant_config["phase_index"] = 1
        state = variant.advance_phase(state)
        state = variant.execute_phase(state, GamePhase.INITIAL_DEAL)
        state.active_game_config.variant_config["phase_index"] = 2
        state = variant.advance_phase(state)

        # Skip betting rounds and earlier deal rounds.
        for phase_idx in [3, 4, 5, 6, 7, 8, 9]:
            state.active_game_config.variant_config["phase_index"] = phase_idx
            phase = variant.get_phase_sequence()[phase_idx]
            state = variant.execute_phase(state, phase)
            if phase == GamePhase.BET_ROUND:
                state.betting_state.players_acted = [p.player_id for p in state.players]
                state.betting_state.current_bet = 0
                for p in state.players:
                    p.total_bet_this_round = 0
            state = variant.advance_phase(state)

        # Execute river deal (phase_index=10).
        state.active_game_config.variant_config["phase_index"] = 10
        state = variant.execute_phase(state, GamePhase.DEAL_ROUND)

        # River card (7th card) should be face-down.
        for player in state.players:
            river_card = player.hole_cards[-1]
            assert not river_card.is_face_up, (
                f"River card for {player.player_id} should be face-down"
            )


# ---------------------------------------------------------------------------
# Deck exhaustion
# ---------------------------------------------------------------------------

class TestDeckExhaustion:

    def test_community_river_dealt_when_deck_short(self) -> None:
        """Community river card used when deck can't cover all players at the river."""
        variant = _make_variant()
        state = _make_game_state(["alice", "bob", "carol"])
        state = variant.initialize(state, state.active_game_config)

        # Give each player 6 cards manually (simulating being at river deal phase).
        suits = [Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS]
        for i, player in enumerate(state.players):
            player.hole_cards = [
                PositionedCard(
                    Card(rank + 1, suits[i]), rank < 2, rank
                )
                for rank in range(6)
            ]

        # Drain the deck to 2 cards (fewer than 3 players).
        remaining_now = state.deck.remaining()
        if remaining_now > 2:
            state.deck.deal(remaining_now - 2)
        assert state.deck.remaining() == 2

        # Execute river deal (phase_index=10, face-down).
        state.active_game_config.variant_config["phase_index"] = 10
        state = variant.execute_phase(state, GamePhase.DEAL_ROUND)

        # Community river should be set since deck < player count.
        community_river = state.active_game_config.variant_config.get("community_river")
        assert community_river is not None, "Community river card should be set on deck exhaustion"

    def test_community_river_is_a_card(self) -> None:
        """Community river card should be a valid Card object."""
        variant = _make_variant()
        state = _make_game_state(["alice", "bob"])
        state = variant.initialize(state, state.active_game_config)

        # Give each player 6 cards.
        for i, player in enumerate(state.players):
            player.hole_cards = [
                PositionedCard(Card(rank + 1, Suit.CLUBS), True, rank)
                for rank in range(6)
            ]

        # Leave only 1 card in deck (fewer than 2 players).
        remaining_now = state.deck.remaining()
        if remaining_now > 1:
            state.deck.deal(remaining_now - 1)

        state.active_game_config.variant_config["phase_index"] = 10
        state = variant.execute_phase(state, GamePhase.DEAL_ROUND)

        from backend.deck.card import Card as CardType
        community_river = state.active_game_config.variant_config.get("community_river")
        assert isinstance(community_river, CardType)

    def test_community_river_key_set_in_variant_config(self) -> None:
        """Verify community_river key exists in variant_config after initialization."""
        variant = _make_variant()
        state = _make_game_state(["alice"])
        state = variant.initialize(state, state.active_game_config)
        assert "community_river" in state.active_game_config.variant_config


# ---------------------------------------------------------------------------
# Showdown evaluation
# ---------------------------------------------------------------------------

class TestShowdown:

    def test_showdown_evaluates_best_five_of_seven(self) -> None:
        """Resolve showdown with 7-card hands and verify winner is determined."""
        variant = _make_variant()
        state = _make_game_state(["alice", "bob"])
        state = variant.initialize(state, state.active_game_config)

        # Manually give each player 7 cards with known hands.
        # Alice: Royal Flush — A,K,Q,J,10 of spades + 2c, 3h
        # Bob: High card only — 2,4,6,8,9 mixed suits
        alice_cards = [
            PositionedCard(Card(1, Suit.SPADES), True, 0),
            PositionedCard(Card(13, Suit.SPADES), True, 1),
            PositionedCard(Card(12, Suit.SPADES), True, 2),
            PositionedCard(Card(11, Suit.SPADES), True, 3),
            PositionedCard(Card(10, Suit.SPADES), True, 4),
            PositionedCard(Card(2, Suit.CLUBS), True, 5),
            PositionedCard(Card(3, Suit.HEARTS), True, 6),
        ]
        bob_cards = [
            PositionedCard(Card(2, Suit.DIAMONDS), True, 0),
            PositionedCard(Card(4, Suit.CLUBS), True, 1),
            PositionedCard(Card(6, Suit.HEARTS), True, 2),
            PositionedCard(Card(8, Suit.SPADES), True, 3),
            PositionedCard(Card(9, Suit.CLUBS), True, 4),
            PositionedCard(Card(7, Suit.DIAMONDS), True, 5),
            PositionedCard(Card(5, Suit.HEARTS), True, 6),
        ]
        state.players[0].hole_cards = alice_cards
        state.players[1].hole_cards = bob_cards
        state.phase = GamePhase.SHOWDOWN

        result = variant.resolve_showdown(state)
        assert "alice" in result.winner_ids
        assert "bob" not in result.winner_ids

    def test_tied_showdown_includes_both_players(self) -> None:
        """Two identical hands result in both players as winners."""
        variant = _make_variant()
        state = _make_game_state(["alice", "bob"])
        state = variant.initialize(state, state.active_game_config)

        # Give both players identical best 5 cards (only 7cs not 5cs).
        same_cards_alice = [
            PositionedCard(Card(2, Suit.CLUBS), True, 0),
            PositionedCard(Card(4, Suit.DIAMONDS), True, 1),
            PositionedCard(Card(6, Suit.HEARTS), True, 2),
            PositionedCard(Card(8, Suit.SPADES), True, 3),
            PositionedCard(Card(10, Suit.CLUBS), True, 4),
            PositionedCard(Card(3, Suit.HEARTS), True, 5),
            PositionedCard(Card(5, Suit.DIAMONDS), True, 6),
        ]
        same_cards_bob = [
            PositionedCard(Card(2, Suit.SPADES), True, 0),
            PositionedCard(Card(4, Suit.CLUBS), True, 1),
            PositionedCard(Card(6, Suit.DIAMONDS), True, 2),
            PositionedCard(Card(8, Suit.HEARTS), True, 3),
            PositionedCard(Card(10, Suit.DIAMONDS), True, 4),
            PositionedCard(Card(3, Suit.SPADES), True, 5),
            PositionedCard(Card(5, Suit.CLUBS), True, 6),
        ]
        state.players[0].hole_cards = same_cards_alice
        state.players[1].hole_cards = same_cards_bob
        state.phase = GamePhase.SHOWDOWN

        result = variant.resolve_showdown(state)
        assert result.is_tie
        assert "alice" in result.winner_ids
        assert "bob" in result.winner_ids


# ---------------------------------------------------------------------------
# Phase management
# ---------------------------------------------------------------------------

class TestPhaseManagement:

    def test_advance_skips_to_pot_distribution_on_single_player(self) -> None:
        """When only one player remains, advance_phase jumps to POT_DISTRIBUTION."""
        variant = _make_variant()
        state = _make_game_state(["alice", "bob"])
        state = variant.initialize(state, state.active_game_config)
        state.phase = GamePhase.BET_ROUND
        state.active_game_config.variant_config["phase_index"] = 3
        # Fold bob.
        state.players[1].is_folded = True

        state = variant.advance_phase(state)
        assert state.phase == GamePhase.POT_DISTRIBUTION

    def test_phase_sequence_length_is_correct(self) -> None:
        variant = _make_variant()
        seq = variant.get_phase_sequence()
        assert len(seq) == 15  # SETUP ... COMPLETE

    def test_phase_sequence_starts_with_setup(self) -> None:
        variant = _make_variant()
        seq = variant.get_phase_sequence()
        assert seq[0] == GamePhase.SETUP

    def test_phase_sequence_ends_with_complete(self) -> None:
        variant = _make_variant()
        seq = variant.get_phase_sequence()
        assert seq[-1] == GamePhase.COMPLETE
