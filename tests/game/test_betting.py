"""Unit tests for betting utilities — Phase 1 scope.

Covers bring-in assignment, suit tiebreaking, and betting round completion
detection.
"""

import pytest

from backend.deck.card import Card, DeckConfig, Suit
from backend.deck.deck import Deck
from backend.game.betting import assign_bring_in, is_betting_round_complete
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _card(rank: int, suit: Suit) -> Card:
    return Card(rank=rank, suit=suit)


def _pc(card: Card, face_up: bool = True) -> PositionedCard:
    return PositionedCard(card=card, is_face_up=face_up, position_index=0)


def _make_state(players: list[PlayerState]) -> GameState:
    deck_config = DeckConfig.STANDARD()
    return GameState(
        hand_id=1,
        session_id=1,
        variant=GameVariant.SEVEN_CARD_STUD,
        deck_config=deck_config,
        active_game_config=ActiveGameConfig(
            variant=GameVariant.SEVEN_CARD_STUD,
            modifiers=[],
            deck_config=deck_config,
            variant_config={"phase_index": 3},
        ),
        phase=GamePhase.BET_ROUND,
        players=players,
        dealer_index=0,
        active_player_index=0,
        pot=Pot(),
        betting_state=BettingState(structure=BettingStructure.BRING_IN),
        deck=Deck(deck_config),
    )


def _player(pid: str, seat: int, door_card: Card) -> PlayerState:
    p = PlayerState(
        player_id=pid, name=pid, is_bot=False,
        seat_index=seat, chip_stack=100,
    )
    # In Seven Card Stud initial deal, index 2 is the door card (face-up).
    p.hole_cards = [
        _pc(_card(5, Suit.CLUBS), face_up=False),   # index 0, down
        _pc(_card(6, Suit.CLUBS), face_up=False),   # index 1, down
        _pc(door_card, face_up=True),                # index 2, up (door)
    ]
    return p


# ---------------------------------------------------------------------------
# Bring-in assignment: lowest card wins
# ---------------------------------------------------------------------------

class TestBringInAssignment:

    def test_lowest_rank_gets_bring_in(self) -> None:
        alice = _player("alice", 0, _card(7, Suit.HEARTS))
        bob = _player("bob", 1, _card(4, Suit.HEARTS))  # lowest
        carol = _player("carol", 2, _card(10, Suit.CLUBS))
        state = _make_state([alice, bob, carol])
        assert assign_bring_in(state) == "bob"

    def test_highest_rank_does_not_get_bring_in(self) -> None:
        alice = _player("alice", 0, _card(13, Suit.SPADES))  # King
        bob = _player("bob", 1, _card(2, Suit.CLUBS))        # lowest
        state = _make_state([alice, bob])
        assert assign_bring_in(state) == "bob"

    def test_ace_ranks_high_for_bring_in(self) -> None:
        # Ace is treated as rank 14 for bring-in (high card), so 2 < A.
        alice = _player("alice", 0, _card(1, Suit.HEARTS))  # Ace (high)
        bob = _player("bob", 1, _card(2, Suit.CLUBS))       # lowest
        state = _make_state([alice, bob])
        assert assign_bring_in(state) == "bob"

    def test_two_players_ace_vs_king(self) -> None:
        alice = _player("alice", 0, _card(1, Suit.HEARTS))   # Ace = 14
        bob = _player("bob", 1, _card(13, Suit.SPADES))      # King = 13
        state = _make_state([alice, bob])
        assert assign_bring_in(state) == "bob"


# ---------------------------------------------------------------------------
# Bring-in tiebreaking by suit (CLUBS < DIAMONDS < HEARTS < SPADES < ORBS)
# ---------------------------------------------------------------------------

class TestBringInSuitTiebreaking:

    def test_clubs_loses_suit_tiebreak(self) -> None:
        alice = _player("alice", 0, _card(7, Suit.CLUBS))     # same rank, CLUBS
        bob = _player("bob", 1, _card(7, Suit.DIAMONDS))
        state = _make_state([alice, bob])
        assert assign_bring_in(state) == "alice"  # CLUBS < DIAMONDS

    def test_spades_wins_tiebreak_over_clubs(self) -> None:
        alice = _player("alice", 0, _card(7, Suit.SPADES))
        bob = _player("bob", 1, _card(7, Suit.CLUBS))
        state = _make_state([alice, bob])
        # CLUBS < SPADES, so bob (clubs) posts bring-in.
        assert assign_bring_in(state) == "bob"

    def test_diamonds_beats_clubs_loses_to_hearts(self) -> None:
        alice = _player("alice", 0, _card(5, Suit.CLUBS))
        bob = _player("bob", 1, _card(5, Suit.DIAMONDS))
        carol = _player("carol", 2, _card(5, Suit.HEARTS))
        state = _make_state([alice, bob, carol])
        # alice (CLUBS) is lowest.
        assert assign_bring_in(state) == "alice"

    def test_full_suit_order(self) -> None:
        """All four suits with same rank; CLUBS should get bring-in."""
        players = [
            _player("spades", 0, _card(8, Suit.SPADES)),
            _player("hearts", 1, _card(8, Suit.HEARTS)),
            _player("diamonds", 2, _card(8, Suit.DIAMONDS)),
            _player("clubs", 3, _card(8, Suit.CLUBS)),
        ]
        state = _make_state(players)
        assert assign_bring_in(state) == "clubs"

    def test_folded_player_excluded_from_bring_in(self) -> None:
        alice = _player("alice", 0, _card(2, Suit.CLUBS))  # Would be lowest.
        alice.is_folded = True
        bob = _player("bob", 1, _card(5, Suit.HEARTS))
        state = _make_state([alice, bob])
        assert assign_bring_in(state) == "bob"


# ---------------------------------------------------------------------------
# Betting round completion detection
# ---------------------------------------------------------------------------

class TestBettingRoundComplete:

    def _two_player_state(self) -> GameState:
        alice = PlayerState(
            player_id="alice", name="alice", is_bot=False,
            seat_index=0, chip_stack=100,
        )
        bob = PlayerState(
            player_id="bob", name="bob", is_bot=False,
            seat_index=1, chip_stack=100,
        )
        return _make_state([alice, bob])

    def test_complete_when_all_have_checked(self) -> None:
        state = self._two_player_state()
        state.betting_state.players_acted = ["alice", "bob"]
        state.betting_state.current_bet = 0
        assert is_betting_round_complete(state)

    def test_not_complete_when_player_has_not_acted(self) -> None:
        state = self._two_player_state()
        state.betting_state.players_acted = ["alice"]
        state.betting_state.current_bet = 0
        assert not is_betting_round_complete(state)

    def test_complete_when_only_one_player_left(self) -> None:
        state = self._two_player_state()
        state.players[0].is_folded = True
        # Only bob remains.
        assert is_betting_round_complete(state)

    def test_not_complete_when_bet_unmatched(self) -> None:
        state = self._two_player_state()
        state.betting_state.players_acted = ["alice", "bob"]
        state.betting_state.current_bet = 4
        state.players[1].total_bet_this_round = 0  # bob hasn't matched
        assert not is_betting_round_complete(state)
