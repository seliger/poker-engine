"""Deck object: construction, shuffle, deal, burn, peek, reset."""

from __future__ import annotations

import json
import logging
import random
from typing import Any

from backend.deck.card import (
    Card,
    DeckConfig,
    DeckConfigurationError,
    InsufficientCardsError,
    Suit,
)

logger = logging.getLogger(__name__)


class Deck:
    """A full playing deck whose composition is determined by DeckConfig.

    On construction the deck is built and shuffled automatically.  Three
    internal pools track card state: available, dealt, and burned.
    """

    def __init__(self, config: DeckConfig) -> None:
        self._config: DeckConfig = config
        self._available: list[Card] = []
        self._dealt: list[Card] = []
        self._burned: list[Card] = []
        self._build()
        self._validate_count()
        random.shuffle(self._available)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    def _build(self) -> None:
        """Populate _available with the correct set of cards for the config."""
        suits = [Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS, Suit.SPADES]
        if self._config.include_orbs:
            suits.append(Suit.ORBS)

        cards: list[Card] = []
        for suit in suits:
            for rank in range(1, 14):
                cards.append(Card(rank=rank, suit=suit))

        if self._config.include_nulls:
            null_suits = [Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS, Suit.SPADES]
            if self._config.include_orbs and self._config.null_exists_in_orbs:
                null_suits.append(Suit.ORBS)
            for suit in null_suits:
                cards.append(Card(rank=0, suit=suit))

        self._available = cards

    def _expected_count(self) -> int:
        """Return the number of cards that should be in a full deck."""
        suit_count = 4 + (1 if self._config.include_orbs else 0)
        count = suit_count * 13
        if self._config.include_nulls:
            null_suit_count = 4
            if self._config.include_orbs and self._config.null_exists_in_orbs:
                null_suit_count += 1
            count += null_suit_count
        return count

    def _validate_count(self) -> None:
        expected = self._expected_count()
        actual = len(self._available)
        if actual != expected:
            raise DeckConfigurationError(
                f"Deck built {actual} cards but expected {expected} for config {self._config}"
            )

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def deal(self, n: int) -> list[Card]:
        """Remove and return n cards from the top of the deck.

        Raises InsufficientCardsError if fewer than n cards remain.
        """
        if n <= 0:
            raise ValueError(f"n must be a positive integer, got {n!r}")
        if len(self._available) < n:
            raise InsufficientCardsError(
                f"Cannot deal {n} cards; {len(self._available)} remaining"
            )
        cards = self._available[:n]
        self._available = self._available[n:]
        self._dealt.extend(cards)
        logger.debug("Dealt %d card(s); %d remaining", n, self.remaining())
        return cards

    def burn(self) -> Card:
        """Remove and return the top card without dealing it to a player.

        Raises InsufficientCardsError if the deck is empty.
        """
        if not self._available:
            raise InsufficientCardsError("Cannot burn; 0 cards remaining")
        card = self._available.pop(0)
        self._burned.append(card)
        logger.debug("Burned %s; %d remaining", card.shorthand(), self.remaining())
        return card

    def peek(self) -> Card:
        """Return the top card without removing it.

        Raises InsufficientCardsError if the deck is empty.
        """
        if not self._available:
            raise InsufficientCardsError("Cannot peek; 0 cards remaining")
        return self._available[0]

    def remaining(self) -> int:
        """Number of undealt cards currently available."""
        return len(self._available)

    def reset(self) -> None:
        """Return all dealt and burned cards to the deck and reshuffle."""
        self._available = self._available + self._dealt + self._burned
        self._dealt = []
        self._burned = []
        random.shuffle(self._available)
        logger.debug("Deck reset; %d cards available", self.remaining())

    def shuffle(self) -> None:
        """Reshuffle the remaining undealt cards only."""
        random.shuffle(self._available)

    def low_card_warning(self) -> bool:
        """True when remaining() is below the configured threshold."""
        return self.remaining() < self._config.low_card_warning_threshold

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def config(self) -> DeckConfig:
        """The DeckConfig this deck was constructed with."""
        return self._config

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize full deck state including all three card pools."""

        def _card(c: Card) -> dict[str, Any]:
            return {
                "rank": c.rank,
                "suit": c.suit.name,
                "is_intrinsic_wild": c.is_intrinsic_wild,
            }

        return {
            "config": self._config.to_dict(),
            "available": [_card(c) for c in self._available],
            "dealt": [_card(c) for c in self._dealt],
            "burned": [_card(c) for c in self._burned],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Deck":
        """Restore a Deck from a dict produced by to_dict()."""
        config = DeckConfig.from_dict(data["config"])
        deck = cls.__new__(cls)
        deck._config = config

        def _card(d: dict[str, Any]) -> Card:
            return Card(
                rank=d["rank"],
                suit=Suit[d["suit"]],
                is_intrinsic_wild=d.get("is_intrinsic_wild", False),
            )

        deck._available = [_card(c) for c in data["available"]]
        deck._dealt = [_card(c) for c in data["dealt"]]
        deck._burned = [_card(c) for c in data["burned"]]
        return deck
