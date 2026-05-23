"""Card representation, Suit enumeration, and DeckConfig for the Deck Layer."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Deck Layer exceptions
# ---------------------------------------------------------------------------

class DeckConfigurationError(Exception):
    """Raised when a DeckConfig produces an invalid state."""


class InsufficientCardsError(Exception):
    """Raised when deal(), burn(), or peek() cannot be fulfilled."""


class InvalidCardError(Exception):
    """Raised when attempting to construct a Card with an invalid rank or suit."""


# ---------------------------------------------------------------------------
# Suit
# ---------------------------------------------------------------------------

class Suit(Enum):
    """The five suits, including the non-standard Orbs suit."""

    CLUBS = "♣"
    DIAMONDS = "♦"
    HEARTS = "♥"
    SPADES = "♠"
    ORBS = "✦"

    @property
    def symbol(self) -> str:
        """Unicode symbol for this suit."""
        return self.value

    def __str__(self) -> str:
        return self.value


# ---------------------------------------------------------------------------
# Rank display helpers
# ---------------------------------------------------------------------------

_RANK_ABBR: dict[int, str] = {
    0: "0",
    1: "A",
    **{r: str(r) for r in range(2, 11)},
    11: "J",
    12: "Q",
    13: "K",
    14: "A",
}

_RANK_DISPLAY: dict[int, str] = {
    0: "Null",
    1: "Ace",
    2: "Two",
    3: "Three",
    4: "Four",
    5: "Five",
    6: "Six",
    7: "Seven",
    8: "Eight",
    9: "Nine",
    10: "Ten",
    11: "Jack",
    12: "Queen",
    13: "King",
    14: "Ace",
}


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Card:
    """Immutable value object representing a single playing card.

    Equality and hashing are based on rank and suit only; is_intrinsic_wild
    does not affect identity.

    Rank 0 is a Null card; ranks 1-13 are standard (Ace stored as 1 at rest).
    Rank 14 (high Ace) must not appear in a live deck and is rejected here.
    """

    rank: int
    suit: Suit
    is_intrinsic_wild: bool = field(default=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        if not isinstance(self.suit, Suit):
            raise InvalidCardError(
                f"suit must be a Suit member, got {self.suit!r}"
            )
        if not isinstance(self.rank, int) or not (0 <= self.rank <= 13):
            raise InvalidCardError(
                f"rank must be an integer in 0-13 at construction time, got {self.rank!r}"
            )

    @property
    def is_null(self) -> bool:
        """True when this card has rank 0 (Null)."""
        return self.rank == 0

    def display(self) -> str:
        """Human-readable name, e.g. 'Jack of Orbs' or 'Null of Spades'."""
        rank_name = _RANK_DISPLAY[self.rank]
        suit_name = self.suit.name.title()
        return f"{rank_name} of {suit_name}"

    def shorthand(self) -> str:
        """Compact display string, e.g. 'J✦' or '0♠'."""
        return f"{_RANK_ABBR[self.rank]}{self.suit.symbol}"

    def __repr__(self) -> str:
        return f"Card({self.shorthand()!r})"


# ---------------------------------------------------------------------------
# DeckConfig
# ---------------------------------------------------------------------------

@dataclass
class DeckConfig:
    """Configuration object that determines deck composition.

    Pass an instance to Deck() at construction time.  The three named presets
    (STANDARD, WITH_NULLS, WITH_ORBS) are available as classmethods.
    """

    include_orbs: bool = False
    include_nulls: bool = False
    null_exists_in_orbs: bool = False
    nulls_match_each_other: bool = False
    wilds_can_become_null: bool = False
    low_card_warning_threshold: int = 10

    # ------------------------------------------------------------------
    # Named preset factories
    # ------------------------------------------------------------------

    @classmethod
    def STANDARD(cls) -> "DeckConfig":
        """52-card deck; 5-6 players."""
        return cls()

    @classmethod
    def WITH_NULLS(cls) -> "DeckConfig":
        """56-card deck (adds 4 Null cards); 7 players."""
        return cls(include_nulls=True)

    @classmethod
    def WITH_ORBS(cls) -> "DeckConfig":
        """65-card deck (adds full Orbs suit); 8-9 players."""
        return cls(include_orbs=True)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "include_orbs": self.include_orbs,
            "include_nulls": self.include_nulls,
            "null_exists_in_orbs": self.null_exists_in_orbs,
            "nulls_match_each_other": self.nulls_match_each_other,
            "wilds_can_become_null": self.wilds_can_become_null,
            "low_card_warning_threshold": self.low_card_warning_threshold,
        }

    def to_json(self) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeckConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json(cls, s: str) -> "DeckConfig":
        """Deserialize from a JSON string produced by to_json()."""
        return cls.from_dict(json.loads(s))


# ---------------------------------------------------------------------------
# Deck Layer constants consumed by the Evaluation Layer
# ---------------------------------------------------------------------------

# All valid 5-card straight rank sequences.
# Ace appears as 1 (low) at the wheel end and 14 (high) at Broadway.
# Sequences containing 0 (Null) are only valid when include_nulls is True.
STRAIGHT_RANK_SEQUENCES: list[list[int]] = [
    [0, 1, 2, 3, 4],    # Null-Ace-2-3-4 (requires Nulls)
    [1, 2, 3, 4, 5],    # Wheel
    [2, 3, 4, 5, 6],
    [3, 4, 5, 6, 7],
    [4, 5, 6, 7, 8],
    [5, 6, 7, 8, 9],
    [6, 7, 8, 9, 10],
    [7, 8, 9, 10, 11],
    [8, 9, 10, 11, 12],
    [9, 10, 11, 12, 13],
    [10, 11, 12, 13, 14],  # Broadway (Ace high)
]

# Best possible low hand when Nulls are active.
# Null-A-2-3-5 (Null-A-2-3-4 is excluded because it forms a straight).
BEST_LOW_HAND_WITH_NULLS: list[int] = [0, 1, 2, 3, 5]
