"""Unit tests for Deck (Deck Layer)."""

import pytest

from backend.deck.card import Card, DeckConfig, Suit
from backend.deck.deck import Deck
from backend.deck.card import DeckConfigurationError, InsufficientCardsError


class TestDeckCardCounts:
    def test_standard_deck_exactly_52_cards(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        assert deck.remaining() == 52

    def test_nulls_deck_exactly_56_cards(self) -> None:
        deck = Deck(DeckConfig.WITH_NULLS())
        assert deck.remaining() == 56

    def test_orbs_deck_exactly_65_cards(self) -> None:
        deck = Deck(DeckConfig.WITH_ORBS())
        assert deck.remaining() == 65

    def test_standard_deck_52_unique_cards(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        all_cards = deck._available[:]
        assert len(set(all_cards)) == 52

    def test_nulls_deck_56_unique_cards(self) -> None:
        deck = Deck(DeckConfig.WITH_NULLS())
        all_cards = deck._available[:]
        assert len(set(all_cards)) == 56

    def test_orbs_deck_65_unique_cards(self) -> None:
        deck = Deck(DeckConfig.WITH_ORBS())
        all_cards = deck._available[:]
        assert len(set(all_cards)) == 65

    def test_nulls_deck_contains_exactly_4_null_cards(self) -> None:
        deck = Deck(DeckConfig.WITH_NULLS())
        nulls = [c for c in deck._available if c.is_null]
        assert len(nulls) == 4

    def test_orbs_deck_contains_exactly_13_orbs_cards(self) -> None:
        deck = Deck(DeckConfig.WITH_ORBS())
        orbs = [c for c in deck._available if c.suit == Suit.ORBS]
        assert len(orbs) == 13

    def test_standard_deck_no_duplicates(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        cards = deck._available[:]
        assert len(cards) == len(set(cards))

    def test_nulls_deck_no_duplicates(self) -> None:
        deck = Deck(DeckConfig.WITH_NULLS())
        cards = deck._available[:]
        assert len(cards) == len(set(cards))

    def test_orbs_deck_no_duplicates(self) -> None:
        deck = Deck(DeckConfig.WITH_ORBS())
        cards = deck._available[:]
        assert len(cards) == len(set(cards))

    def test_standard_deck_contains_no_orbs(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        orbs = [c for c in deck._available if c.suit == Suit.ORBS]
        assert len(orbs) == 0

    def test_standard_deck_contains_no_nulls(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        nulls = [c for c in deck._available if c.is_null]
        assert len(nulls) == 0


class TestDeckOperations:
    def test_deal_reduces_remaining_by_n(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        before = deck.remaining()
        deck.deal(5)
        assert deck.remaining() == before - 5

    def test_deal_returns_correct_count(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        cards = deck.deal(7)
        assert len(cards) == 7

    def test_deal_returns_card_objects(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        cards = deck.deal(1)
        assert isinstance(cards[0], Card)

    def test_burn_reduces_remaining_by_1(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        before = deck.remaining()
        deck.burn()
        assert deck.remaining() == before - 1

    def test_burn_returns_card(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        card = deck.burn()
        assert isinstance(card, Card)

    def test_peek_does_not_reduce_remaining(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        before = deck.remaining()
        deck.peek()
        assert deck.remaining() == before

    def test_peek_returns_same_card_on_repeat(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        assert deck.peek() == deck.peek()

    def test_peek_returns_card_that_deal_returns_next(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        top = deck.peek()
        dealt = deck.deal(1)
        assert top == dealt[0]

    def test_reset_restores_full_deck_after_deal(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        deck.deal(10)
        deck.reset()
        assert deck.remaining() == 52

    def test_reset_restores_full_deck_after_burn(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        deck.burn()
        deck.reset()
        assert deck.remaining() == 52

    def test_reset_restores_full_deck_after_deal_and_burn(self) -> None:
        deck = Deck(DeckConfig.WITH_NULLS())
        deck.deal(7)
        deck.burn()
        deck.reset()
        assert deck.remaining() == 56

    def test_deal_all_then_reset(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        deck.deal(52)
        assert deck.remaining() == 0
        deck.reset()
        assert deck.remaining() == 52

    def test_shuffle_does_not_change_remaining(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        deck.deal(10)
        before = deck.remaining()
        deck.shuffle()
        assert deck.remaining() == before

    def test_config_property(self) -> None:
        cfg = DeckConfig.WITH_ORBS()
        deck = Deck(cfg)
        assert deck.config is cfg


class TestDeckErrors:
    def test_deal_raises_when_insufficient_cards(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        deck.deal(52)
        with pytest.raises(InsufficientCardsError):
            deck.deal(1)

    def test_deal_raises_with_remaining_count_in_message(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        deck.deal(50)
        with pytest.raises(InsufficientCardsError, match="2"):
            deck.deal(3)

    def test_burn_raises_on_empty_deck(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        deck.deal(52)
        with pytest.raises(InsufficientCardsError):
            deck.burn()

    def test_peek_raises_on_empty_deck(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        deck.deal(52)
        with pytest.raises(InsufficientCardsError):
            deck.peek()

    def test_deal_zero_raises_value_error(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        with pytest.raises(ValueError):
            deck.deal(0)

    def test_deal_negative_raises_value_error(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        with pytest.raises(ValueError):
            deck.deal(-1)


class TestLowCardWarning:
    def test_warning_false_above_threshold(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        assert deck.low_card_warning() is False

    def test_warning_true_below_threshold(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        deck.deal(52 - 9)  # 9 remaining, default threshold is 10
        assert deck.low_card_warning() is True

    def test_warning_true_at_threshold_minus_one(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        deck.deal(52 - 9)  # 9 left; 9 < 10
        assert deck.low_card_warning() is True

    def test_warning_false_at_threshold(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        deck.deal(52 - 10)  # exactly 10 remaining; 10 is not < 10
        assert deck.low_card_warning() is False

    def test_custom_threshold(self) -> None:
        cfg = DeckConfig(low_card_warning_threshold=5)
        deck = Deck(cfg)
        deck.deal(52 - 5)  # 5 remaining; 5 is not < 5
        assert deck.low_card_warning() is False
        deck.deal(1)  # 4 remaining; 4 < 5
        assert deck.low_card_warning() is True


class TestDeckSerialization:
    def test_to_dict_and_from_dict_roundtrip(self) -> None:
        deck = Deck(DeckConfig.WITH_NULLS())
        deck.deal(5)
        deck.burn()
        snapshot = deck.to_dict()
        restored = Deck.from_dict(snapshot)
        assert restored.remaining() == deck.remaining()
        assert restored.config.include_nulls == deck.config.include_nulls

    def test_serialized_available_count_matches(self) -> None:
        deck = Deck(DeckConfig.STANDARD())
        deck.deal(3)
        deck.burn()
        d = deck.to_dict()
        assert len(d["available"]) == 48
        assert len(d["dealt"]) == 3
        assert len(d["burned"]) == 1
