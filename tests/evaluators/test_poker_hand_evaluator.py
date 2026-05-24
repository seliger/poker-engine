"""Unit tests for PokerHandEvaluator — Phase 1 scope.

Phase 1: standard 52-card evaluation, no wilds, no Null cards, no Orbs.
All tests use DeckConfig.STANDARD().  Wild, Null, and Orbs cases are Phase 3.
"""

import pytest

from backend.deck.card import Card, DeckConfig, Suit
from backend.evaluators.base import (
    ComparisonResult,
    Declaration,
    EvalDirection,
    HandRank,
)
from backend.evaluators.poker_hand_evaluator import (
    EvaluatedHand,
    IncomparableHandError,
    InvalidHandError,
    PokerHandEvaluator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def evaluator() -> PokerHandEvaluator:
    return PokerHandEvaluator()


@pytest.fixture
def deck_config() -> DeckConfig:
    return DeckConfig.STANDARD()


# ---------------------------------------------------------------------------
# Helper card factories
# ---------------------------------------------------------------------------

def c(rank: int, suit: Suit) -> Card:
    return Card(rank=rank, suit=suit)


def make_hand(*specs: tuple[int, Suit]) -> list[Card]:
    return [c(r, s) for r, s in specs]


# ---------------------------------------------------------------------------
# Hand rank identification — all 9 standard ranks
# ---------------------------------------------------------------------------

class TestHandRankIdentification:

    def test_high_card(self, evaluator: PokerHandEvaluator, deck_config: DeckConfig) -> None:
        hand = make_hand((2, Suit.CLUBS), (4, Suit.DIAMONDS), (7, Suit.HEARTS),
                         (9, Suit.SPADES), (11, Suit.CLUBS))
        result = evaluator.evaluate(hand, deck_config)
        assert result.hand_rank == HandRank.HIGH_CARD

    def test_one_pair(self, evaluator: PokerHandEvaluator, deck_config: DeckConfig) -> None:
        hand = make_hand((5, Suit.CLUBS), (5, Suit.DIAMONDS), (7, Suit.HEARTS),
                         (9, Suit.SPADES), (11, Suit.CLUBS))
        result = evaluator.evaluate(hand, deck_config)
        assert result.hand_rank == HandRank.ONE_PAIR

    def test_two_pair(self, evaluator: PokerHandEvaluator, deck_config: DeckConfig) -> None:
        hand = make_hand((5, Suit.CLUBS), (5, Suit.DIAMONDS), (9, Suit.HEARTS),
                         (9, Suit.SPADES), (11, Suit.CLUBS))
        result = evaluator.evaluate(hand, deck_config)
        assert result.hand_rank == HandRank.TWO_PAIR

    def test_three_of_a_kind(self, evaluator: PokerHandEvaluator, deck_config: DeckConfig) -> None:
        hand = make_hand((8, Suit.CLUBS), (8, Suit.DIAMONDS), (8, Suit.HEARTS),
                         (3, Suit.SPADES), (6, Suit.CLUBS))
        result = evaluator.evaluate(hand, deck_config)
        assert result.hand_rank == HandRank.THREE_OF_A_KIND

    def test_straight(self, evaluator: PokerHandEvaluator, deck_config: DeckConfig) -> None:
        hand = make_hand((5, Suit.CLUBS), (6, Suit.DIAMONDS), (7, Suit.HEARTS),
                         (8, Suit.SPADES), (9, Suit.CLUBS))
        result = evaluator.evaluate(hand, deck_config)
        assert result.hand_rank == HandRank.STRAIGHT

    def test_flush(self, evaluator: PokerHandEvaluator, deck_config: DeckConfig) -> None:
        hand = make_hand((2, Suit.HEARTS), (5, Suit.HEARTS), (7, Suit.HEARTS),
                         (9, Suit.HEARTS), (11, Suit.HEARTS))
        result = evaluator.evaluate(hand, deck_config)
        assert result.hand_rank == HandRank.FLUSH

    def test_full_house(self, evaluator: PokerHandEvaluator, deck_config: DeckConfig) -> None:
        hand = make_hand((10, Suit.CLUBS), (10, Suit.DIAMONDS), (10, Suit.HEARTS),
                         (4, Suit.SPADES), (4, Suit.CLUBS))
        result = evaluator.evaluate(hand, deck_config)
        assert result.hand_rank == HandRank.FULL_HOUSE

    def test_four_of_a_kind(self, evaluator: PokerHandEvaluator, deck_config: DeckConfig) -> None:
        hand = make_hand((7, Suit.CLUBS), (7, Suit.DIAMONDS), (7, Suit.HEARTS),
                         (7, Suit.SPADES), (2, Suit.CLUBS))
        result = evaluator.evaluate(hand, deck_config)
        assert result.hand_rank == HandRank.FOUR_OF_A_KIND

    def test_straight_flush(self, evaluator: PokerHandEvaluator, deck_config: DeckConfig) -> None:
        hand = make_hand((5, Suit.SPADES), (6, Suit.SPADES), (7, Suit.SPADES),
                         (8, Suit.SPADES), (9, Suit.SPADES))
        result = evaluator.evaluate(hand, deck_config)
        assert result.hand_rank == HandRank.STRAIGHT_FLUSH


# ---------------------------------------------------------------------------
# Royal Flush
# ---------------------------------------------------------------------------

class TestRoyalFlush:

    def test_royal_flush_identified(self, evaluator: PokerHandEvaluator, deck_config: DeckConfig) -> None:
        hand = make_hand((1, Suit.HEARTS), (10, Suit.HEARTS), (11, Suit.HEARTS),
                         (12, Suit.HEARTS), (13, Suit.HEARTS))
        result = evaluator.evaluate(hand, deck_config)
        assert result.hand_rank == HandRank.ROYAL_FLUSH

    def test_royal_flush_display_name(self, evaluator: PokerHandEvaluator, deck_config: DeckConfig) -> None:
        hand = make_hand((1, Suit.SPADES), (10, Suit.SPADES), (11, Suit.SPADES),
                         (12, Suit.SPADES), (13, Suit.SPADES))
        result = evaluator.evaluate(hand, deck_config)
        assert "Royal" in result.display_name

    def test_royal_flush_beats_straight_flush_default_flag_false(
        self, deck_config: DeckConfig
    ) -> None:
        """Default: RF and SF both have effective rank STRAIGHT_FLUSH; RF wins via high_value."""
        ev = PokerHandEvaluator(royal_flush_beats_straight_flush=False)
        rf = ev.evaluate(
            make_hand((1, Suit.CLUBS), (10, Suit.CLUBS), (11, Suit.CLUBS),
                      (12, Suit.CLUBS), (13, Suit.CLUBS)),
            deck_config,
        )
        sf = ev.evaluate(
            make_hand((9, Suit.DIAMONDS), (10, Suit.DIAMONDS), (11, Suit.DIAMONDS),
                      (12, Suit.DIAMONDS), (13, Suit.DIAMONDS)),
            deck_config,
        )
        assert ev.compare(rf, sf, EvalDirection.HIGH) == ComparisonResult.WIN

    def test_royal_flush_beats_straight_flush_flag_true(
        self, deck_config: DeckConfig
    ) -> None:
        """flag=True: RF HandRank(10) > SF HandRank(9) at rank level."""
        ev = PokerHandEvaluator(royal_flush_beats_straight_flush=True)
        rf = ev.evaluate(
            make_hand((1, Suit.CLUBS), (10, Suit.CLUBS), (11, Suit.CLUBS),
                      (12, Suit.CLUBS), (13, Suit.CLUBS)),
            deck_config,
        )
        sf = ev.evaluate(
            make_hand((9, Suit.DIAMONDS), (10, Suit.DIAMONDS), (11, Suit.DIAMONDS),
                      (12, Suit.DIAMONDS), (13, Suit.DIAMONDS)),
            deck_config,
        )
        assert ev.compare(rf, sf, EvalDirection.HIGH) == ComparisonResult.WIN

    def test_non_royal_sf_is_not_royal_flush(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand = make_hand((9, Suit.CLUBS), (10, Suit.CLUBS), (11, Suit.CLUBS),
                         (12, Suit.CLUBS), (13, Suit.CLUBS))
        result = evaluator.evaluate(hand, deck_config)
        assert result.hand_rank == HandRank.STRAIGHT_FLUSH


# ---------------------------------------------------------------------------
# Ace duality
# ---------------------------------------------------------------------------

class TestAceDuality:

    def test_ace_value_high_direction(self, evaluator: PokerHandEvaluator) -> None:
        val = evaluator.ace_dual_value(EvalDirection.HIGH, Declaration.HIGH)
        assert val == 14

    def test_ace_value_low_direction(self, evaluator: PokerHandEvaluator) -> None:
        val = evaluator.ace_dual_value(EvalDirection.LOW, Declaration.LOW)
        assert val == 1

    def test_ace_value_both_declaration(self, evaluator: PokerHandEvaluator) -> None:
        val = evaluator.ace_dual_value(EvalDirection.HIGH, Declaration.BOTH)
        assert isinstance(val, tuple)
        low_rank, high_rank = val
        assert low_rank == 1
        assert high_rank == 14

    def test_wheel_straight_identified(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        """A-2-3-4-5 is the lowest straight (wheel)."""
        hand = make_hand((1, Suit.CLUBS), (2, Suit.DIAMONDS), (3, Suit.HEARTS),
                         (4, Suit.SPADES), (5, Suit.CLUBS))
        result = evaluator.evaluate(hand, deck_config)
        assert result.hand_rank == HandRank.STRAIGHT

    def test_broadway_straight_identified(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        """10-J-Q-K-A is the highest straight (Broadway)."""
        hand = make_hand((10, Suit.CLUBS), (11, Suit.DIAMONDS), (12, Suit.HEARTS),
                         (13, Suit.SPADES), (1, Suit.CLUBS))
        result = evaluator.evaluate(hand, deck_config)
        assert result.hand_rank == HandRank.STRAIGHT

    def test_broadway_beats_wheel_high(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        broadway = evaluator.evaluate(
            make_hand((10, Suit.CLUBS), (11, Suit.DIAMONDS), (12, Suit.HEARTS),
                      (13, Suit.SPADES), (1, Suit.CLUBS)),
            deck_config,
        )
        wheel = evaluator.evaluate(
            make_hand((1, Suit.CLUBS), (2, Suit.DIAMONDS), (3, Suit.HEARTS),
                      (4, Suit.SPADES), (5, Suit.CLUBS)),
            deck_config,
        )
        assert evaluator.compare(broadway, wheel, EvalDirection.HIGH) == ComparisonResult.WIN

    def test_wheel_beats_broadway_low(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        """In LOW direction, wheel (A-2-3-4-5) should beat Broadway (10-J-Q-K-A)."""
        broadway = evaluator.evaluate(
            make_hand((10, Suit.CLUBS), (11, Suit.DIAMONDS), (12, Suit.HEARTS),
                      (13, Suit.SPADES), (1, Suit.CLUBS)),
            deck_config,
            direction=EvalDirection.LOW,
        )
        wheel = evaluator.evaluate(
            make_hand((1, Suit.CLUBS), (2, Suit.DIAMONDS), (3, Suit.HEARTS),
                      (4, Suit.SPADES), (5, Suit.CLUBS)),
            deck_config,
            direction=EvalDirection.LOW,
        )
        assert evaluator.compare(wheel, broadway, EvalDirection.LOW) == ComparisonResult.WIN


# ---------------------------------------------------------------------------
# Best-5 selection from more than 5 cards
# ---------------------------------------------------------------------------

class TestBestFiveSelection:

    def test_best_five_from_seven_picks_strongest(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        """7 cards including a flush; best 5 should be the flush."""
        cards = make_hand(
            (2, Suit.HEARTS), (5, Suit.HEARTS), (7, Suit.HEARTS),
            (9, Suit.HEARTS), (11, Suit.HEARTS),
            (3, Suit.CLUBS), (6, Suit.DIAMONDS),
        )
        result = evaluator.evaluate(cards, deck_config)
        assert result.hand_rank == HandRank.FLUSH
        assert len(result.best_five) == 5

    def test_best_five_from_ten_cards(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        """10 cards; evaluator should find the best hand without error."""
        cards = make_hand(
            (1, Suit.SPADES), (10, Suit.SPADES), (11, Suit.SPADES),
            (12, Suit.SPADES), (13, Suit.SPADES),
            (2, Suit.CLUBS), (3, Suit.HEARTS), (4, Suit.DIAMONDS),
            (5, Suit.CLUBS), (6, Suit.HEARTS),
        )
        result = evaluator.evaluate(cards, deck_config)
        # Royal Flush is present in the 10 cards; it must be found.
        assert result.hand_rank == HandRank.ROYAL_FLUSH

    def test_best_five_high_vs_low_may_differ(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        """HIGH and LOW directions may select different best-5 subsets."""
        # 7 cards: contains both a pair of aces and high cards.
        # HIGH direction: pair of aces should be valued more than pair of 2s.
        # LOW direction: lower ranks are better; the hand with lower cards
        # should score higher as a low hand.
        cards = make_hand(
            (1, Suit.CLUBS), (1, Suit.DIAMONDS),   # pair of aces
            (2, Suit.HEARTS), (3, Suit.SPADES),
            (4, Suit.CLUBS), (5, Suit.DIAMONDS), (6, Suit.HEARTS),
        )
        high_result = evaluator.evaluate(cards, deck_config, direction=EvalDirection.HIGH)
        low_result = evaluator.evaluate(cards, deck_config, direction=EvalDirection.LOW)
        # High result should use the pair of aces (strong high hand).
        # Low result should prefer the low cards and potentially avoid the pair.
        # We just assert they're valid, not necessarily identical best_five.
        assert not high_result.is_partial
        assert not low_result.is_partial

    def test_best_five_from_seven_avoids_worse_hand(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        """Selecting different 5 cards produces a worse result; evaluator picks best."""
        # A four-of-a-kind is present; the remaining two cards are garbage.
        cards = make_hand(
            (7, Suit.CLUBS), (7, Suit.DIAMONDS), (7, Suit.HEARTS), (7, Suit.SPADES),
            (2, Suit.CLUBS), (3, Suit.DIAMONDS), (4, Suit.HEARTS),
        )
        result = evaluator.evaluate(cards, deck_config)
        assert result.hand_rank == HandRank.FOUR_OF_A_KIND

    def test_all_combinations_populated_for_multi_card_hand(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        cards = make_hand(
            (2, Suit.CLUBS), (4, Suit.DIAMONDS), (6, Suit.HEARTS),
            (8, Suit.SPADES), (10, Suit.CLUBS), (12, Suit.DIAMONDS), (1, Suit.HEARTS),
        )
        result = evaluator.evaluate(cards, deck_config)
        # C(7,5) = 21 combinations
        assert len(result.all_combinations) == 21


# ---------------------------------------------------------------------------
# compare() — high and low direction
# ---------------------------------------------------------------------------

class TestCompare:

    def test_flush_beats_straight_high(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        flush = evaluator.evaluate(
            make_hand((2, Suit.HEARTS), (5, Suit.HEARTS), (7, Suit.HEARTS),
                      (9, Suit.HEARTS), (11, Suit.HEARTS)),
            deck_config,
        )
        straight = evaluator.evaluate(
            make_hand((5, Suit.CLUBS), (6, Suit.DIAMONDS), (7, Suit.HEARTS),
                      (8, Suit.SPADES), (9, Suit.CLUBS)),
            deck_config,
        )
        assert evaluator.compare(flush, straight, EvalDirection.HIGH) == ComparisonResult.WIN

    def test_same_rank_kicker_decides_high(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        pair_aces = evaluator.evaluate(
            make_hand((1, Suit.CLUBS), (1, Suit.DIAMONDS), (10, Suit.HEARTS),
                      (9, Suit.SPADES), (8, Suit.CLUBS)),
            deck_config,
        )
        pair_kings = evaluator.evaluate(
            make_hand((13, Suit.CLUBS), (13, Suit.DIAMONDS), (10, Suit.HEARTS),
                      (9, Suit.SPADES), (8, Suit.CLUBS)),
            deck_config,
        )
        assert evaluator.compare(pair_aces, pair_kings, EvalDirection.HIGH) == ComparisonResult.WIN

    def test_identical_hands_are_tie(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand_a = evaluator.evaluate(
            make_hand((5, Suit.CLUBS), (5, Suit.DIAMONDS), (7, Suit.HEARTS),
                      (9, Suit.SPADES), (11, Suit.CLUBS)),
            deck_config,
        )
        hand_b = evaluator.evaluate(
            make_hand((5, Suit.HEARTS), (5, Suit.SPADES), (7, Suit.CLUBS),
                      (9, Suit.DIAMONDS), (11, Suit.HEARTS)),
            deck_config,
        )
        assert evaluator.compare(hand_a, hand_b, EvalDirection.HIGH) == ComparisonResult.TIE

    def test_high_card_beats_lower_high_card(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand_a = evaluator.evaluate(
            make_hand((1, Suit.CLUBS), (7, Suit.DIAMONDS), (5, Suit.HEARTS),
                      (3, Suit.SPADES), (2, Suit.CLUBS)),
            deck_config,
        )
        hand_b = evaluator.evaluate(
            make_hand((13, Suit.CLUBS), (7, Suit.HEARTS), (5, Suit.SPADES),
                      (3, Suit.DIAMONDS), (2, Suit.HEARTS)),
            deck_config,
        )
        assert evaluator.compare(hand_a, hand_b, EvalDirection.HIGH) == ComparisonResult.WIN

    def test_low_direction_lower_rank_wins(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        pair = evaluator.evaluate(
            make_hand((5, Suit.CLUBS), (5, Suit.DIAMONDS), (7, Suit.HEARTS),
                      (9, Suit.SPADES), (11, Suit.CLUBS)),
            deck_config,
            direction=EvalDirection.LOW,
        )
        high_card = evaluator.evaluate(
            make_hand((2, Suit.CLUBS), (4, Suit.DIAMONDS), (7, Suit.HEARTS),
                      (9, Suit.SPADES), (11, Suit.CLUBS)),
            deck_config,
            direction=EvalDirection.LOW,
        )
        # High card beats pair in low direction (lower hand rank wins).
        assert evaluator.compare(high_card, pair, EvalDirection.LOW) == ComparisonResult.WIN

    def test_low_direction_lower_cards_win_same_rank(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        """Two high-card hands: lower cards win in LOW direction."""
        hand_a = evaluator.evaluate(
            make_hand((2, Suit.CLUBS), (3, Suit.DIAMONDS), (4, Suit.HEARTS),
                      (5, Suit.SPADES), (7, Suit.CLUBS)),
            deck_config,
            direction=EvalDirection.LOW,
        )
        hand_b = evaluator.evaluate(
            make_hand((8, Suit.CLUBS), (9, Suit.DIAMONDS), (10, Suit.HEARTS),
                      (11, Suit.SPADES), (13, Suit.CLUBS)),
            deck_config,
            direction=EvalDirection.LOW,
        )
        assert evaluator.compare(hand_a, hand_b, EvalDirection.LOW) == ComparisonResult.WIN

    def test_compare_returns_lose_from_weaker_hand_perspective(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        flush = evaluator.evaluate(
            make_hand((2, Suit.HEARTS), (5, Suit.HEARTS), (7, Suit.HEARTS),
                      (9, Suit.HEARTS), (11, Suit.HEARTS)),
            deck_config,
        )
        straight = evaluator.evaluate(
            make_hand((5, Suit.CLUBS), (6, Suit.DIAMONDS), (7, Suit.HEARTS),
                      (8, Suit.SPADES), (9, Suit.CLUBS)),
            deck_config,
        )
        assert evaluator.compare(straight, flush, EvalDirection.HIGH) == ComparisonResult.LOSE


# ---------------------------------------------------------------------------
# determine_winners()
# ---------------------------------------------------------------------------

class TestDetermineWinners:

    def test_single_winner_high(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        # Alice: full house (tens full of fours) — beats Bob's straight.
        hands = {
            "alice": evaluator.evaluate(
                make_hand((10, Suit.CLUBS), (10, Suit.DIAMONDS), (10, Suit.HEARTS),
                          (4, Suit.SPADES), (4, Suit.CLUBS)),
                deck_config,
            ),
            "bob": evaluator.evaluate(
                make_hand((5, Suit.CLUBS), (6, Suit.DIAMONDS), (7, Suit.HEARTS),
                          (8, Suit.SPADES), (9, Suit.CLUBS)),
                deck_config,
            ),
        }
        result = evaluator.determine_winners(hands, EvalDirection.HIGH)
        assert result.winners == ["alice"]
        assert not result.is_tie
        assert not result.pot_split

    def test_tie_both_win(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        shared = make_hand((5, Suit.CLUBS), (5, Suit.DIAMONDS), (7, Suit.HEARTS),
                           (9, Suit.SPADES), (11, Suit.CLUBS))
        same_hand_b = make_hand((5, Suit.HEARTS), (5, Suit.SPADES), (7, Suit.CLUBS),
                                (9, Suit.DIAMONDS), (11, Suit.HEARTS))
        hands = {
            "alice": evaluator.evaluate(shared, deck_config),
            "bob": evaluator.evaluate(same_hand_b, deck_config),
        }
        result = evaluator.determine_winners(hands, EvalDirection.HIGH)
        assert set(result.winners) == {"alice", "bob"}
        assert result.is_tie
        assert result.pot_split

    def test_three_way_with_one_winner(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hands = {
            "alice": evaluator.evaluate(
                make_hand((7, Suit.CLUBS), (7, Suit.DIAMONDS), (7, Suit.HEARTS),
                          (7, Suit.SPADES), (2, Suit.CLUBS)),
                deck_config,
            ),
            "bob": evaluator.evaluate(
                make_hand((1, Suit.CLUBS), (1, Suit.DIAMONDS), (1, Suit.HEARTS),
                          (13, Suit.SPADES), (12, Suit.CLUBS)),
                deck_config,
            ),
            "carol": evaluator.evaluate(
                make_hand((5, Suit.CLUBS), (6, Suit.DIAMONDS), (7, Suit.HEARTS),
                          (8, Suit.SPADES), (9, Suit.CLUBS)),
                deck_config,
            ),
        }
        result = evaluator.determine_winners(hands, EvalDirection.HIGH)
        assert result.winners == ["alice"]

    def test_winners_low_direction(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hands = {
            "alice": evaluator.evaluate(
                make_hand((2, Suit.CLUBS), (3, Suit.DIAMONDS), (4, Suit.HEARTS),
                          (5, Suit.SPADES), (7, Suit.CLUBS)),
                deck_config,
                direction=EvalDirection.LOW,
            ),
            "bob": evaluator.evaluate(
                make_hand((8, Suit.CLUBS), (9, Suit.DIAMONDS), (10, Suit.HEARTS),
                          (11, Suit.SPADES), (13, Suit.CLUBS)),
                deck_config,
                direction=EvalDirection.LOW,
            ),
        }
        result = evaluator.determine_winners(hands, EvalDirection.LOW)
        assert result.winners == ["alice"]


# ---------------------------------------------------------------------------
# evaluate_for_declare()
# ---------------------------------------------------------------------------

class TestEvaluateForDeclare:

    def test_declare_high(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        cards = make_hand((5, Suit.CLUBS), (5, Suit.DIAMONDS), (7, Suit.HEARTS),
                          (9, Suit.SPADES), (11, Suit.CLUBS))
        result = evaluator.evaluate_for_declare(cards, deck_config, Declaration.HIGH)
        assert result.declaration == Declaration.HIGH
        assert result.high_hand is not None
        assert result.low_hand is None
        assert not result.is_both_ways
        assert not result.must_win_both

    def test_declare_low(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        cards = make_hand((2, Suit.CLUBS), (4, Suit.DIAMONDS), (6, Suit.HEARTS),
                          (8, Suit.SPADES), (10, Suit.CLUBS))
        result = evaluator.evaluate_for_declare(cards, deck_config, Declaration.LOW)
        assert result.declaration == Declaration.LOW
        assert result.high_hand is None
        assert result.low_hand is not None
        assert not result.is_both_ways
        assert not result.must_win_both

    def test_declare_both_returns_two_hands(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        cards = make_hand((2, Suit.CLUBS), (4, Suit.DIAMONDS), (6, Suit.HEARTS),
                          (8, Suit.SPADES), (10, Suit.CLUBS))
        result = evaluator.evaluate_for_declare(cards, deck_config, Declaration.BOTH)
        assert result.declaration == Declaration.BOTH
        assert result.high_hand is not None
        assert result.low_hand is not None
        assert result.is_both_ways
        assert result.must_win_both

    def test_declare_both_hands_are_evaluated(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        cards = make_hand((1, Suit.CLUBS), (2, Suit.DIAMONDS), (3, Suit.HEARTS),
                          (4, Suit.SPADES), (5, Suit.CLUBS))
        result = evaluator.evaluate_for_declare(cards, deck_config, Declaration.BOTH)
        assert isinstance(result.high_hand, EvaluatedHand)
        assert isinstance(result.low_hand, EvaluatedHand)
        assert not result.high_hand.is_partial
        assert not result.low_hand.is_partial


# ---------------------------------------------------------------------------
# Partial hand evaluation
# ---------------------------------------------------------------------------

class TestPartialHand:

    def test_partial_is_partial_true(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand = make_hand((5, Suit.CLUBS), (5, Suit.DIAMONDS), (7, Suit.HEARTS),
                         (9, Suit.SPADES))
        result = evaluator.evaluate(hand, deck_config)
        assert result.is_partial is True

    def test_partial_two_cards(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand = make_hand((7, Suit.CLUBS), (7, Suit.DIAMONDS))
        result = evaluator.evaluate(hand, deck_config)
        assert result.is_partial is True
        assert result.hand_rank == HandRank.ONE_PAIR

    def test_partial_display_name_contains_partial(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand = make_hand((5, Suit.CLUBS), (5, Suit.DIAMONDS), (7, Suit.HEARTS),
                         (9, Suit.SPADES))
        result = evaluator.evaluate(hand, deck_config)
        assert "partial" in result.display_name.lower()

    def test_compare_partial_raises(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand_a = evaluator.evaluate(
            make_hand((5, Suit.CLUBS), (5, Suit.DIAMONDS), (7, Suit.HEARTS),
                      (9, Suit.SPADES)),
            deck_config,
        )
        hand_b = evaluator.evaluate(
            make_hand((10, Suit.CLUBS), (10, Suit.DIAMONDS), (7, Suit.HEARTS),
                      (9, Suit.SPADES)),
            deck_config,
        )
        with pytest.raises(IncomparableHandError):
            evaluator.compare(hand_a, hand_b, EvalDirection.HIGH)

    def test_partial_three_of_a_kind_detected(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand = make_hand((8, Suit.CLUBS), (8, Suit.DIAMONDS), (8, Suit.HEARTS),
                         (3, Suit.SPADES))
        result = evaluator.evaluate(hand, deck_config)
        assert result.is_partial is True
        assert result.hand_rank == HandRank.THREE_OF_A_KIND

    def test_partial_two_pair_detected(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand = make_hand((5, Suit.CLUBS), (5, Suit.DIAMONDS), (9, Suit.HEARTS),
                         (9, Suit.SPADES))
        result = evaluator.evaluate(hand, deck_config)
        assert result.is_partial is True
        assert result.hand_rank == HandRank.TWO_PAIR


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def test_invalid_duplicate_cards(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand = [
            Card(rank=5, suit=Suit.CLUBS),
            Card(rank=5, suit=Suit.CLUBS),  # exact duplicate
            Card(rank=7, suit=Suit.HEARTS),
            Card(rank=9, suit=Suit.SPADES),
            Card(rank=11, suit=Suit.CLUBS),
        ]
        with pytest.raises(InvalidHandError):
            evaluator.evaluate(hand, deck_config)

    def test_too_few_cards_raises(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        with pytest.raises(InvalidHandError):
            evaluator.evaluate([Card(rank=5, suit=Suit.CLUBS)], deck_config)

    def test_too_many_cards_raises(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        cards = [Card(rank=r, suit=Suit.CLUBS) for r in range(2, 13)]  # 11 cards
        with pytest.raises(InvalidHandError):
            evaluator.evaluate(cards, deck_config)

    def test_empty_hands_raises(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        with pytest.raises(InvalidHandError):
            evaluator.determine_winners({}, EvalDirection.HIGH)


# ---------------------------------------------------------------------------
# Hand frequency calculation
# ---------------------------------------------------------------------------

class TestHandFrequencies:

    def test_frequencies_sum_to_one(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        freqs = evaluator.calculate_hand_frequencies(deck_config, hand_size=5)
        total = sum(freqs.values())
        assert abs(total - 1.0) < 0.01

    def test_frequencies_include_common_ranks(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        freqs = evaluator.calculate_hand_frequencies(deck_config, hand_size=5)
        assert freqs.get(HandRank.HIGH_CARD, 0) > 0
        assert freqs.get(HandRank.ONE_PAIR, 0) > 0

    def test_royal_flush_frequency_is_very_low(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        freqs = evaluator.calculate_hand_frequencies(deck_config, hand_size=5)
        assert freqs.get(HandRank.ROYAL_FLUSH, 0) < 0.0002

    def test_cache_hit_returns_same_result(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        freqs_a = evaluator.calculate_hand_frequencies(deck_config, hand_size=5)
        freqs_b = evaluator.calculate_hand_frequencies(deck_config, hand_size=5)
        assert freqs_a is freqs_b  # same object returned from cache

    def test_cache_invalidation_recomputes(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        freqs_a = evaluator.calculate_hand_frequencies(deck_config, hand_size=5)
        evaluator.invalidate_frequency_cache()
        freqs_b = evaluator.calculate_hand_frequencies(deck_config, hand_size=5)
        assert freqs_a is not freqs_b  # different object after invalidation


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

class TestPerformance:

    def test_ten_card_evaluation_under_500ms(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        """C(10,5) = 252 combinations; this should complete well under 500ms."""
        import time

        cards = make_hand(
            (1, Suit.SPADES), (2, Suit.HEARTS), (3, Suit.CLUBS), (4, Suit.DIAMONDS),
            (5, Suit.SPADES), (6, Suit.HEARTS), (7, Suit.CLUBS), (8, Suit.DIAMONDS),
            (9, Suit.SPADES), (10, Suit.HEARTS),
        )
        start = time.monotonic()
        evaluator.evaluate(cards, deck_config)
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms < 500, f"10-card evaluation took {elapsed_ms:.1f}ms"


# ---------------------------------------------------------------------------
# NATURAL_SEVENS (Joe's Baseball, PokerHandEvaluator Amendment v1.3)
# ---------------------------------------------------------------------------

class TestNaturalSevens:
    """Tests for the NATURAL_SEVENS hand rank added in Amendment v1.3.

    NATURAL_SEVENS requires two physical (non-wild) 7-ranked cards of different
    suits when natural_sevens_active=True is passed in variant_config.

    The public check_natural_sevens() static method is used for cases where
    evaluate() cannot be called (e.g. same-suit duplicates are invalid inputs).
    """

    def test_detected_two_sevens_different_suits(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand = make_hand(
            (7, Suit.CLUBS), (7, Suit.HEARTS), (1, Suit.SPADES),
            (13, Suit.DIAMONDS), (9, Suit.CLUBS),
        )
        result = evaluator.evaluate(hand, deck_config, natural_sevens_active=True)
        assert result.hand_rank == HandRank.NATURAL_SEVENS

    def test_not_detected_two_sevens_same_suit(self) -> None:
        # Two 7♣ are the same card — evaluate() would reject them as duplicates.
        # Test the public predicate directly instead.
        seven_clubs = c(7, Suit.CLUBS)
        cards = [seven_clubs, seven_clubs, c(1, Suit.SPADES)]
        result = PokerHandEvaluator.check_natural_sevens(
            cards, {"natural_sevens_active": True}
        )
        assert result is False

    def test_not_detected_only_one_physical_seven(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand = make_hand(
            (7, Suit.CLUBS), (1, Suit.SPADES), (13, Suit.DIAMONDS),
            (9, Suit.HEARTS), (2, Suit.CLUBS),
        )
        result = evaluator.evaluate(hand, deck_config, natural_sevens_active=True)
        assert result.hand_rank != HandRank.NATURAL_SEVENS

    def test_not_detected_when_flag_false(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand = make_hand(
            (7, Suit.CLUBS), (7, Suit.HEARTS), (1, Suit.SPADES),
            (13, Suit.DIAMONDS), (9, Suit.CLUBS),
        )
        result = evaluator.evaluate(hand, deck_config, natural_sevens_active=False)
        assert result.hand_rank != HandRank.NATURAL_SEVENS

    def test_not_detected_when_flag_absent(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand = make_hand(
            (7, Suit.CLUBS), (7, Suit.HEARTS), (1, Suit.SPADES),
            (13, Suit.DIAMONDS), (9, Suit.CLUBS),
        )
        result = evaluator.evaluate(hand, deck_config)
        assert result.hand_rank != HandRank.NATURAL_SEVENS

    def test_not_detected_wild_substitutes_for_seven(self) -> None:
        # Wild 7♣ + physical 7♥ → only one physical seven; must not trigger.
        wild_seven = Card(rank=7, suit=Suit.CLUBS, is_intrinsic_wild=True)
        real_seven = c(7, Suit.HEARTS)
        hand = [wild_seven, real_seven, c(1, Suit.SPADES), c(13, Suit.DIAMONDS), c(9, Suit.CLUBS)]
        result = PokerHandEvaluator.check_natural_sevens(
            hand, {"natural_sevens_active": True}
        )
        assert result is False

    def test_beats_royal_flush_in_high_direction(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        natural_hand = make_hand(
            (7, Suit.CLUBS), (7, Suit.HEARTS), (1, Suit.SPADES),
            (13, Suit.DIAMONDS), (9, Suit.CLUBS),
        )
        royal_hand = make_hand(
            (1, Suit.SPADES), (10, Suit.SPADES), (11, Suit.SPADES),
            (12, Suit.SPADES), (13, Suit.SPADES),
        )
        ns = evaluator.evaluate(natural_hand, deck_config, natural_sevens_active=True)
        rf = evaluator.evaluate(royal_hand, deck_config)
        assert evaluator.compare(ns, rf, EvalDirection.HIGH) == ComparisonResult.WIN

    def test_beats_straight_flush_in_high_direction(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        natural_hand = make_hand(
            (7, Suit.CLUBS), (7, Suit.HEARTS), (1, Suit.SPADES),
            (13, Suit.DIAMONDS), (9, Suit.CLUBS),
        )
        sf_hand = make_hand(
            (2, Suit.HEARTS), (3, Suit.HEARTS), (4, Suit.HEARTS),
            (5, Suit.HEARTS), (6, Suit.HEARTS),
        )
        ns = evaluator.evaluate(natural_hand, deck_config, natural_sevens_active=True)
        sf = evaluator.evaluate(sf_hand, deck_config)
        assert evaluator.compare(ns, sf, EvalDirection.HIGH) == ComparisonResult.WIN

    def test_beats_five_of_a_kind_in_high_direction(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        from backend.evaluators.poker_hand_evaluator import EvaluatedHand
        natural_hand = make_hand(
            (7, Suit.CLUBS), (7, Suit.HEARTS), (1, Suit.SPADES),
            (13, Suit.DIAMONDS), (9, Suit.CLUBS),
        )
        ns = evaluator.evaluate(natural_hand, deck_config, natural_sevens_active=True)
        five_oak = EvaluatedHand(
            is_partial=False,
            deck_config=deck_config,
            display_name="Five of a kind",
            high_value=999_999,
            low_value=0,
            hand_rank=HandRank.FIVE_OF_A_KIND,
            best_five=[],
            wild_assignments={},
            kickers=[],
            is_null_anchored=False,
        )
        assert evaluator.compare(ns, five_oak, EvalDirection.HIGH) == ComparisonResult.WIN

    def test_two_natural_sevens_hands_tie(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand_a = make_hand(
            (7, Suit.CLUBS), (7, Suit.HEARTS), (1, Suit.SPADES),
            (13, Suit.DIAMONDS), (9, Suit.CLUBS),
        )
        hand_b = make_hand(
            (7, Suit.DIAMONDS), (7, Suit.SPADES), (2, Suit.HEARTS),
            (10, Suit.CLUBS), (3, Suit.DIAMONDS),
        )
        ns_a = evaluator.evaluate(hand_a, deck_config, natural_sevens_active=True)
        ns_b = evaluator.evaluate(hand_b, deck_config, natural_sevens_active=True)
        assert evaluator.compare(ns_a, ns_b, EvalDirection.HIGH) == ComparisonResult.TIE

    def test_two_natural_sevens_split_pot(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand_a = make_hand(
            (7, Suit.CLUBS), (7, Suit.HEARTS), (1, Suit.SPADES),
            (13, Suit.DIAMONDS), (9, Suit.CLUBS),
        )
        hand_b = make_hand(
            (7, Suit.DIAMONDS), (7, Suit.SPADES), (2, Suit.HEARTS),
            (10, Suit.CLUBS), (3, Suit.DIAMONDS),
        )
        ns_a = evaluator.evaluate(hand_a, deck_config, natural_sevens_active=True)
        ns_b = evaluator.evaluate(hand_b, deck_config, natural_sevens_active=True)
        result = evaluator.determine_winners(
            {"alice": ns_a, "bob": ns_b}, EvalDirection.HIGH
        )
        assert result.is_tie is True
        assert result.pot_split is True
        assert set(result.winners) == {"alice", "bob"}

    def test_display_name_is_natural_pair_of_sevens(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand = make_hand(
            (7, Suit.CLUBS), (7, Suit.HEARTS), (1, Suit.SPADES),
            (13, Suit.DIAMONDS), (9, Suit.CLUBS),
        )
        result = evaluator.evaluate(hand, deck_config, natural_sevens_active=True)
        assert result.display_name == "Natural Pair of Sevens"

    def test_natural_sevens_detected_in_seven_card_hand(
        self, evaluator: PokerHandEvaluator, deck_config: DeckConfig
    ) -> None:
        hand = make_hand(
            (7, Suit.CLUBS), (7, Suit.HEARTS), (1, Suit.SPADES),
            (13, Suit.DIAMONDS), (9, Suit.CLUBS),
            (2, Suit.HEARTS), (5, Suit.DIAMONDS),
        )
        result = evaluator.evaluate(hand, deck_config, natural_sevens_active=True)
        assert result.hand_rank == HandRank.NATURAL_SEVENS
