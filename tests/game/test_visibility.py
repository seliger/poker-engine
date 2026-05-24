"""Unit tests for the visibility system — Phase 1 scope.

Verifies the core information asymmetry invariants: no player ever sees
another player's face-down cards, while always seeing their own.
"""

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
from backend.game.visibility import ActionType, LegalAction, get_player_view


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _card(rank: int, suit: Suit = Suit.CLUBS) -> Card:
    return Card(rank=rank, suit=suit)


def _positioned(card: Card, face_up: bool, idx: int = 0) -> PositionedCard:
    return PositionedCard(card=card, is_face_up=face_up, position_index=idx)


def _make_game_state(players: list[PlayerState]) -> GameState:
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
            variant_config={"phase_index": 0},
        ),
        phase=GamePhase.BET_ROUND,
        players=players,
        dealer_index=0,
        active_player_index=0,
        pot=Pot(),
        betting_state=BettingState(structure=BettingStructure.BRING_IN),
        deck=Deck(deck_config),
    )


def _make_player(
    player_id: str,
    seat_index: int,
    hole_cards: list[PositionedCard],
    is_bot: bool = False,
) -> PlayerState:
    return PlayerState(
        player_id=player_id,
        name=player_id,
        is_bot=is_bot,
        seat_index=seat_index,
        chip_stack=100,
        hole_cards=hole_cards,
    )


# ---------------------------------------------------------------------------
# Visibility invariants
# ---------------------------------------------------------------------------

class TestVisibilityInvariants:

    def test_human_sees_all_own_cards_including_face_down(self) -> None:
        my_down = _positioned(_card(7, Suit.HEARTS), face_up=False, idx=0)
        my_up = _positioned(_card(10, Suit.SPADES), face_up=True, idx=1)
        me = _make_player("alice", 0, [my_down, my_up])
        other = _make_player("bob", 1, [])
        state = _make_game_state([me, other])

        view = get_player_view(state, "alice")
        assert len(view.my_cards) == 2
        card_objects = [pc.card for pc in view.my_cards]
        assert _card(7, Suit.HEARTS) in card_objects
        assert _card(10, Suit.SPADES) in card_objects

    def test_human_does_not_see_opponents_face_down_cards(self) -> None:
        their_down = _positioned(_card(7, Suit.HEARTS), face_up=False, idx=0)
        their_up = _positioned(_card(10, Suit.SPADES), face_up=True, idx=1)
        them = _make_player("bob", 1, [their_down, their_up])
        me = _make_player("alice", 0, [])
        state = _make_game_state([me, them])

        view = get_player_view(state, "alice")
        opponent_view = view.other_players[0]
        assert len(opponent_view.visible_cards) == 1
        assert opponent_view.visible_cards[0].card == _card(10, Suit.SPADES)

    def test_bot_player_view_never_contains_other_players_face_down_cards(self) -> None:
        their_secret = _positioned(_card(2, Suit.CLUBS), face_up=False, idx=0)
        their_public = _positioned(_card(5, Suit.DIAMONDS), face_up=True, idx=1)
        human = _make_player("alice", 0, [their_secret, their_public])
        bot = _make_player("bot1", 1, [], is_bot=True)
        state = _make_game_state([human, bot])

        view = get_player_view(state, "bot1")
        opponent = view.other_players[0]
        # Bot should only see face-up cards of human.
        for pc in opponent.visible_cards:
            assert pc.is_face_up

    def test_opponent_view_omits_face_down_cards(self) -> None:
        """OpponentView.visible_cards must contain only is_face_up=True cards."""
        cards = [
            _positioned(_card(3, Suit.CLUBS), face_up=False, idx=0),
            _positioned(_card(3, Suit.DIAMONDS), face_up=False, idx=1),
            _positioned(_card(9, Suit.HEARTS), face_up=True, idx=2),
        ]
        opponent = _make_player("bob", 1, cards)
        me = _make_player("alice", 0, [])
        state = _make_game_state([me, opponent])

        view = get_player_view(state, "alice")
        opp_view = view.other_players[0]
        assert all(pc.is_face_up for pc in opp_view.visible_cards)
        assert len(opp_view.visible_cards) == 1


# ---------------------------------------------------------------------------
# Legal action list invariants
# ---------------------------------------------------------------------------

class TestLegalActionInvariants:

    def test_legal_actions_empty_for_folded_player(self) -> None:
        folded = _make_player("alice", 0, [])
        folded.is_folded = True
        other = _make_player("bob", 1, [])
        state = _make_game_state([folded, other])
        state.active_player_index = 0

        view = get_player_view(state, "alice")
        # Folded player has no legal actions.
        assert view.legal_actions == []

    def test_legal_actions_passed_through_to_view(self) -> None:
        me = _make_player("alice", 0, [])
        state = _make_game_state([me])
        legal = [LegalAction(action_type=ActionType.CHECK)]

        view = get_player_view(state, "alice", legal_actions=legal)
        assert len(view.legal_actions) == 1
        assert view.legal_actions[0].action_type == ActionType.CHECK

    def test_pot_total_matches_game_state(self) -> None:
        me = _make_player("alice", 0, [])
        state = _make_game_state([me])
        state.pot.main_pot = 42

        view = get_player_view(state, "alice")
        assert view.pot_total == 42

    def test_my_stack_matches_player_chip_stack(self) -> None:
        me = _make_player("alice", 0, [])
        me.chip_stack = 77
        state = _make_game_state([me])

        view = get_player_view(state, "alice")
        assert view.my_stack == 77
