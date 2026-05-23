"""Unit tests for Card and Suit (Deck Layer)."""

import pytest

from backend.deck.card import Card, InvalidCardError, Suit


class TestSuit:
    def test_all_five_suits_exist(self) -> None:
        assert Suit.CLUBS
        assert Suit.DIAMONDS
        assert Suit.HEARTS
        assert Suit.SPADES
        assert Suit.ORBS

    def test_suit_symbols(self) -> None:
        assert Suit.CLUBS.symbol == "♣"
        assert Suit.DIAMONDS.symbol == "♦"
        assert Suit.HEARTS.symbol == "♥"
        assert Suit.SPADES.symbol == "♠"
        assert Suit.ORBS.symbol == "✦"

    def test_suit_str(self) -> None:
        assert str(Suit.ORBS) == "✦"

    def test_suit_iterable(self) -> None:
        suits = list(Suit)
        assert len(suits) == 5
        assert Suit.ORBS in suits

    def test_suit_equality(self) -> None:
        assert Suit.CLUBS == Suit.CLUBS
        assert Suit.CLUBS != Suit.SPADES

    def test_suit_hashable(self) -> None:
        s = {Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS, Suit.SPADES, Suit.ORBS}
        assert len(s) == 5


class TestCard:
    def test_standard_card_attributes(self) -> None:
        card = Card(rank=11, suit=Suit.ORBS)
        assert card.rank == 11
        assert card.suit == Suit.ORBS
        assert card.is_null is False
        assert card.is_intrinsic_wild is False

    def test_null_card_is_null_true(self) -> None:
        card = Card(rank=0, suit=Suit.SPADES)
        assert card.is_null is True

    def test_standard_card_is_null_false(self) -> None:
        card = Card(rank=5, suit=Suit.HEARTS)
        assert card.is_null is False

    def test_null_of_spades_shorthand(self) -> None:
        card = Card(rank=0, suit=Suit.SPADES)
        assert card.shorthand() == "0♠"

    def test_jack_of_orbs_shorthand(self) -> None:
        card = Card(rank=11, suit=Suit.ORBS)
        assert card.shorthand() == "J✦"

    def test_ace_shorthand(self) -> None:
        card = Card(rank=1, suit=Suit.CLUBS)
        assert card.shorthand() == "A♣"

    def test_ten_shorthand(self) -> None:
        card = Card(rank=10, suit=Suit.DIAMONDS)
        assert card.shorthand() == "10♦"

    def test_null_of_spades_display(self) -> None:
        card = Card(rank=0, suit=Suit.SPADES)
        assert card.display() == "Null of Spades"

    def test_jack_of_orbs_display(self) -> None:
        card = Card(rank=11, suit=Suit.ORBS)
        assert card.display() == "Jack of Orbs"

    def test_ace_display(self) -> None:
        card = Card(rank=1, suit=Suit.HEARTS)
        assert card.display() == "Ace of Hearts"

    def test_king_display(self) -> None:
        card = Card(rank=13, suit=Suit.SPADES)
        assert card.display() == "King of Spades"

    def test_equality_based_on_rank_and_suit(self) -> None:
        card_a = Card(rank=7, suit=Suit.CLUBS)
        card_b = Card(rank=7, suit=Suit.CLUBS)
        assert card_a == card_b

    def test_equality_ignores_is_intrinsic_wild(self) -> None:
        card_a = Card(rank=3, suit=Suit.DIAMONDS, is_intrinsic_wild=False)
        card_b = Card(rank=3, suit=Suit.DIAMONDS, is_intrinsic_wild=True)
        assert card_a == card_b

    def test_inequality_different_rank(self) -> None:
        assert Card(rank=2, suit=Suit.CLUBS) != Card(rank=3, suit=Suit.CLUBS)

    def test_inequality_different_suit(self) -> None:
        assert Card(rank=5, suit=Suit.CLUBS) != Card(rank=5, suit=Suit.HEARTS)

    def test_card_hashable(self) -> None:
        card = Card(rank=1, suit=Suit.SPADES)
        assert hash(card) is not None

    def test_cards_usable_in_set(self) -> None:
        cards = {Card(rank=1, suit=Suit.CLUBS), Card(rank=1, suit=Suit.CLUBS)}
        assert len(cards) == 1

    def test_cards_usable_as_dict_keys(self) -> None:
        card = Card(rank=12, suit=Suit.HEARTS)
        d = {card: "queen of hearts"}
        assert d[Card(rank=12, suit=Suit.HEARTS)] == "queen of hearts"

    def test_wild_cards_deduplicated_in_set(self) -> None:
        """Two cards with same rank/suit but different wild flag are identical."""
        a = Card(rank=9, suit=Suit.SPADES, is_intrinsic_wild=False)
        b = Card(rank=9, suit=Suit.SPADES, is_intrinsic_wild=True)
        s = {a, b}
        assert len(s) == 1

    def test_invalid_rank_too_high(self) -> None:
        with pytest.raises(InvalidCardError):
            Card(rank=14, suit=Suit.CLUBS)

    def test_invalid_rank_negative(self) -> None:
        with pytest.raises(InvalidCardError):
            Card(rank=-1, suit=Suit.CLUBS)

    def test_invalid_suit(self) -> None:
        with pytest.raises(InvalidCardError):
            Card(rank=5, suit="CLUBS")  # type: ignore[arg-type]

    def test_card_is_immutable(self) -> None:
        card = Card(rank=7, suit=Suit.HEARTS)
        with pytest.raises((AttributeError, TypeError)):
            card.rank = 8  # type: ignore[misc]

    def test_intrinsic_wild_flag_stored(self) -> None:
        card = Card(rank=2, suit=Suit.CLUBS, is_intrinsic_wild=True)
        assert card.is_intrinsic_wild is True
