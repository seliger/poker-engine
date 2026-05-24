"""Unit tests for the Tier 1 rule-based bot — Phase 1 scope.

Covers: bot decision validity, legal action adherence, hand strength
estimation, and information hiding (bot never gets hidden info).
"""

from __future__ import annotations

import pytest

from backend.deck.card import Card, DeckConfig, Suit
from backend.deck.deck import Deck
from backend.evaluators.base import HandRank
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
from backend.game.visibility import ActionType, LegalAction, PartialHandStrength, PlayerView, BettingStateView, get_player_view
from backend.bot.rule_based import RuleBasedBot, get_bot_action


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _card(rank: int, suit: Suit = Suit.CLUBS) -> Card:
    return Card(rank=rank, suit=suit)


def _legal(action: ActionType, min_amt: int = 0, max_amt: int = 100) -> LegalAction:
    return LegalAction(action_type=action, min_amount=min_amt, max_amount=max_amt)


def _make_view(
    legal_actions: list[LegalAction],
    hand_rank: HandRank | None = None,
    pot_total: int = 10,
    current_bet: int = 0,
) -> PlayerView:
    hs = None
    if hand_rank is not None:
        hs = PartialHandStrength(
            display_name="test",
            hand_rank=hand_rank,
            current_total=None,
            is_partial=False,
        )
    return PlayerView(
        hand_id=1,
        phase=GamePhase.BET_ROUND,
        my_cards=[],
        other_players=[],
        pot_total=pot_total,
        my_stack=100,
        betting_state=BettingStateView(
            current_bet=current_bet,
            minimum_raise=2,
            betting_round=1,
            pot_total=pot_total,
            structure="BRING_IN",
        ),
        wild_ranks=[],
        wild_suits=[],
        active_modifiers=[],
        legal_actions=legal_actions,
        hand_strength=hs,
    )


def _make_game_state(player_ids: list[str]) -> GameState:
    deck_config = DeckConfig.STANDARD()
    players = [
        PlayerState(
            player_id=pid, name=pid, is_bot=True,
            seat_index=i, chip_stack=100,
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
            modifiers=[],
            deck_config=deck_config,
            variant_config={"phase_index": 3},
        ),
        phase=GamePhase.BET_ROUND,
        players=players,
        dealer_index=0,
        active_player_index=0,
        pot=Pot(main_pot=5),
        betting_state=BettingState(
            structure=BettingStructure.BRING_IN,
            current_bet=0,
            betting_round=1,
        ),
        deck=Deck(deck_config),
    )


# ---------------------------------------------------------------------------
# Bot construction
# ---------------------------------------------------------------------------

class TestBotConstruction:

    def test_bot_personality_clamped_to_valid_range(self) -> None:
        bot = RuleBasedBot(aggression=1.0, personality_variance=0.5)
        assert 0.0 <= bot.personality.aggression <= 1.0
        assert 0.0 <= bot.personality.bluff_frequency <= 1.0
        assert 0.0 <= bot.personality.risk_tolerance <= 1.0

    def test_default_parameters_accepted(self) -> None:
        bot = RuleBasedBot()
        assert bot.personality is not None


# ---------------------------------------------------------------------------
# Action validity
# ---------------------------------------------------------------------------

class TestActionValidity:

    def test_decide_always_returns_legal_action_type(self) -> None:
        bot = RuleBasedBot(aggression=0.5)
        legal = [_legal(ActionType.CHECK), _legal(ActionType.BET)]
        view = _make_view(legal, hand_rank=HandRank.ONE_PAIR)
        action = bot.decide(view, legal)
        assert action.action_type in {ActionType.CHECK, ActionType.BET}

    def test_decide_never_returns_action_not_in_legal_list(self) -> None:
        bot = RuleBasedBot(aggression=1.0, bluff_frequency=1.0)
        legal = [_legal(ActionType.FOLD), _legal(ActionType.CALL, 2, 2)]
        view = _make_view(legal, hand_rank=HandRank.HIGH_CARD, current_bet=2)

        for _ in range(50):
            action = bot.decide(view, legal)
            assert action.action_type in {ActionType.FOLD, ActionType.CALL}

    def test_decide_raises_on_empty_legal_actions(self) -> None:
        bot = RuleBasedBot()
        view = _make_view([])
        with pytest.raises(ValueError, match="empty"):
            bot.decide(view, [])

    def test_strong_hand_prefers_betting(self) -> None:
        """Bot with high aggression and a Royal Flush should bet."""
        bot = RuleBasedBot(aggression=1.0, bluff_frequency=0.0, personality_variance=0.0)
        legal = [_legal(ActionType.FOLD), _legal(ActionType.CHECK), _legal(ActionType.BET)]
        view = _make_view(legal, hand_rank=HandRank.ROYAL_FLUSH)
        action = bot.decide(view, legal)
        assert action.action_type == ActionType.BET

    def test_weak_hand_prefers_fold(self) -> None:
        """Bot with low risk tolerance and a high card hand facing a bet should fold."""
        bot = RuleBasedBot(
            aggression=0.0, bluff_frequency=0.0, risk_tolerance=0.0, personality_variance=0.0
        )
        legal = [_legal(ActionType.FOLD), _legal(ActionType.CALL, 4, 4)]
        view = _make_view(legal, hand_rank=HandRank.HIGH_CARD, current_bet=4)
        action = bot.decide(view, legal)
        assert action.action_type == ActionType.FOLD

    def test_check_preferred_over_fold_when_free(self) -> None:
        """Bot should never fold when checking is available (no cost)."""
        bot = RuleBasedBot(
            aggression=0.0, bluff_frequency=0.0, risk_tolerance=0.0, personality_variance=0.0
        )
        legal = [_legal(ActionType.FOLD), _legal(ActionType.CHECK)]
        view = _make_view(legal, hand_rank=HandRank.HIGH_CARD, current_bet=0)
        action = bot.decide(view, legal)
        assert action.action_type == ActionType.CHECK


# ---------------------------------------------------------------------------
# Information hiding
# ---------------------------------------------------------------------------

class TestInformationHiding:

    def test_bot_view_never_contains_other_players_face_down_cards(self) -> None:
        """get_player_view called for bot must not expose face-down opponent cards."""
        deck_config = DeckConfig.STANDARD()
        deck = Deck(deck_config)
        human = PlayerState(
            player_id="human", name="human", is_bot=False,
            seat_index=0, chip_stack=100,
            hole_cards=[
                PositionedCard(Card(7, Suit.HEARTS), False, 0),   # face-down
                PositionedCard(Card(10, Suit.SPADES), True, 1),   # face-up
            ],
        )
        bot_player = PlayerState(
            player_id="bot1", name="bot1", is_bot=True,
            seat_index=1, chip_stack=100,
            hole_cards=[],
        )
        state = GameState(
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
            players=[human, bot_player],
            dealer_index=0,
            active_player_index=1,
            pot=Pot(),
            betting_state=BettingState(structure=BettingStructure.BRING_IN),
            deck=deck,
        )

        bot_view = get_player_view(state, "bot1")
        opponent = bot_view.other_players[0]
        for pc in opponent.visible_cards:
            assert pc.is_face_up, "Bot must not see face-down opponent cards"

    def test_bot_action_always_in_legal_list(self) -> None:
        """get_bot_action result must always be in the legal actions list."""
        variant = SevenCardStudVariant()
        state = _make_game_state(["bot1", "bot2"])
        state = variant.initialize(state, state.active_game_config)

        # Give each bot 3 hole cards so they have a valid hand.
        for i, player in enumerate(state.players):
            player.hole_cards = [
                PositionedCard(Card(2 + i, Suit.CLUBS), False, 0),
                PositionedCard(Card(4 + i, Suit.DIAMONDS), False, 1),
                PositionedCard(Card(6 + i, Suit.HEARTS), True, 2),
            ]
        state.phase = GamePhase.BET_ROUND
        state.active_game_config.variant_config["phase_index"] = 3
        state.betting_state.current_bet = 0
        state.betting_state.betting_round = 1
        state.active_player_index = 0

        bot = RuleBasedBot()
        legal = variant.get_legal_actions(state, "bot1")
        assert legal, "Expected at least one legal action for bot1"

        bot_view = get_player_view(state, "bot1", legal_actions=legal)
        action = bot.decide(bot_view, legal)

        legal_types = {la.action_type for la in legal}
        assert action.action_type in legal_types
