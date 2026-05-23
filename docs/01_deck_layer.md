# Deck Layer Requirements
## Poker Engine: Home Game Edition
### Version 1.0

---

## Overview

The Deck Layer is the lowest layer of the poker engine stack. It is responsible for card representation, deck construction, configuration, and physical deck operations. It has no knowledge of game variants, hand rankings, player state, or betting. It exposes a clean interface consumed exclusively by the Game Layer above it.

---

## Technology

- Language: Python 3.11+
- No external dependencies at this layer except the Python standard library
- PokerKit is explicitly NOT used at this layer; it enters at the Engine Layer
- All classes are dataclasses or standard classes, no ORM, no database concern at this layer
- Full type hints throughout
- Unit testable in isolation with no mocking required

---

## Card Representation

### Requirements

- A Card is an immutable value object once created
- A Card has exactly four attributes:
  - `rank`: an integer from 0 to 14 inclusive
    - 0 represents a Null card
    - 1 represents a low Ace
    - 2 through 13 represent standard ranks Two through King
    - 14 represents a high Ace
    - Ace is stored as 1 at rest; high/low duality is resolved by the Engine Layer, not here
  - `suit`: a member of the Suit enumeration
  - `is_null`: a boolean, True only when rank is 0
  - `is_intrinsic_wild`: a boolean representing whether the card is wild by its own nature, as opposed to being made wild by a game rule. Game-conferred wildness is NOT stored on the card.
- A Card must be hashable so it can be stored in sets and used as dictionary keys
- A Card must implement equality based on rank and suit only
- A Card must implement a `display()` method returning a human readable string such as "Jack of Orbs" or "Null of Spades"
- A Card must implement a `shorthand()` method returning a compact string for terminal and UI display. Format is rank abbreviation followed by suit symbol. Examples below.
- A Null card's display is "Null of [Suit]" and shorthand is "0" followed by the suit symbol
- Ace displays as "Ace" not "One" regardless of stored rank value

### Rank Abbreviations for Shorthand

```
0  = "0"   (Null)
1  = "A"   (Ace)
2  = "2"
...
10 = "10"
11 = "J"
12 = "Q"
13 = "K"
14 = "A"   (high Ace, should not appear in deck at rest)
```

### Suit Enumeration

```
CLUBS    = "♣"
DIAMONDS = "♦"
HEARTS   = "♥"
SPADES   = "♠"
ORBS     = "✦"
```

Orbs is a first-class suit, not a special case. It participates in flushes, straight flushes, and suit-based hand evaluation identically to the four standard suits.

### Null Card Suit Behavior

- Null cards have suits
- A Null of Spades is a Spade with rank zero
- A Null of Spades contributes to spade flushes
- A Null card can anchor the low end of a straight or straight flush
- Null-A-2-3-4 of the same suit is a valid straight flush
- Null-A-2-3-4 of mixed suits is a valid straight

---

## Suit Enumeration Requirements

- Suit is a Python Enum
- Must support iteration for deck construction
- Must support equality and hashing
- Must expose a symbol property for display
- Must expose a name property for human readable output
- ORBS is always a valid member of the enumeration regardless of deck configuration. Deck configuration determines whether Orbs cards are included in a constructed deck, not whether the suit exists as a concept.

---

## Deck Configuration

### DeckConfig Object

DeckConfig is an immutable configuration object passed at deck construction time. It has the following fields:

```
include_orbs: bool
    Default: False
    When True, adds all 13 Orbs suit cards to the deck (ranks 1-13)
    When combined with include_nulls, also adds Null of Orbs if null_exists_in_orbs is True

include_nulls: bool
    Default: False
    When True, adds one Null card per active suit
    Active suits are the four standard suits plus Orbs if include_orbs is True and null_exists_in_orbs is True

null_exists_in_orbs: bool
    Default: False
    Only meaningful when both include_orbs and include_nulls are True
    When True, a Null of Orbs is added to the deck
    When False, Nulls are limited to the four standard suits even with Orbs active

nulls_match_each_other: bool
    Default: False
    Passed through to the Engine Layer for hand evaluation purposes
    Stored here for reference but not enforced at the Deck Layer
    When False, two Null cards do not form a pair
    When True, two Null cards form a pair

wilds_can_become_null: bool
    Default: False
    Passed through to the Engine Layer for hand evaluation purposes
    Stored here for reference but not enforced at the Deck Layer
    When True, a wild card may declare itself as a Null during hand evaluation
    When False, a wild card may not declare itself as Null
```

### Named Preset Configurations

The following named presets must be available as class methods or module-level constants on DeckConfig:

```
STANDARD
    include_orbs: False
    include_nulls: False
    null_exists_in_orbs: False
    nulls_match_each_other: False
    wilds_can_become_null: False
    Result: 52 card deck
    Intended use: 5-6 players

WITH_NULLS
    include_orbs: False
    include_nulls: True
    null_exists_in_orbs: False
    nulls_match_each_other: False
    wilds_can_become_null: False
    Result: 56 card deck
    Intended use: 7 players

WITH_ORBS
    include_orbs: True
    include_nulls: False
    null_exists_in_orbs: False
    nulls_match_each_other: False
    wilds_can_become_null: False
    Result: 65 card deck
    Intended use: 8-9 players
```

Presets are starting points. Any field may be overridden when constructing a DeckConfig from a preset.

### Configuration Persistence

- DeckConfig must be serializable to and deserializable from JSON
- The JSON representation is the canonical house rules storage format
- A config file at a well-known path is loaded at startup if present
- If no config file is present, STANDARD preset is used
- Config file path is configurable via environment variable POKER_CONFIG_PATH
- Default config file path is ~/.config/poker_engine/house_rules.json

---

## Deck Object

### Construction

- Deck is constructed with a DeckConfig
- On construction the deck builds its full card list based on configuration
- On construction the deck shuffles automatically
- A Deck constructed with STANDARD config contains exactly 52 cards
- A Deck constructed with WITH_NULLS config contains exactly 56 cards
- A Deck constructed with WITH_ORBS config contains exactly 65 cards
- Card counts must be validated on construction and raise DeckConfigurationError if incorrect

### Core Operations

```
deal(n: int) -> list[Card]
    Returns exactly n cards from the top of the deck
    Removes dealt cards from the available pool
    Raises InsufficientCardsError if fewer than n cards remain
    n must be a positive integer

burn() -> Card
    Removes and returns the top card without dealing it to a player
    Raises InsufficientCardsError if deck is empty

peek() -> Card
    Returns the top card without removing it
    Required for Night Baseball and similar flip mechanics
    Raises InsufficientCardsError if deck is empty

remaining() -> int
    Returns count of undealt cards currently in deck

reset() -> None
    Returns all dealt and burned cards to the deck
    Reshuffles
    Does not change configuration

shuffle() -> None
    Reshuffles remaining undealt cards only
    Does not return dealt cards

low_card_warning() -> bool
    Returns True if remaining() is below a configurable threshold
    Default threshold is 10 cards
    Threshold is configurable via DeckConfig or house rules JSON
    Intended to alert the Game Layer before deck exhaustion occurs
    Critical for 9-player stud games
```

### Deck State

- Deck tracks three internal card pools: available, dealt, burned
- reset() moves all cards back to available and reshuffles
- Deck must be able to report its current configuration at any time
- Deck state must be serializable to support game state persistence

---

## Straight Rank Ordering with Nulls

When include_nulls is True the valid straight sequences extend as follows:

```
Null, A, 2, 3, 4    (lowest possible straight, Null anchors the bottom)
A, 2, 3, 4, 5       (standard wheel)
2, 3, 4, 5, 6
...continuing through...
10, J, Q, K, A      (Broadway, highest straight)
```

This ordering is defined at the Deck Layer as a constant and consumed by the Engine Layer. The Deck Layer does not evaluate straights but it does own the canonical rank ordering sequence.

---

## Low Hand Reference with Nulls

When include_nulls is True the best possible low hand is:

```
Null, A, 2, 3, 5    (no straight, no flush, unpaired)
```

This is analogous to A-2-3-4-6 in standard Razz. Null-A-2-3-4 is excluded as the best low hand because it constitutes a straight. This constant is defined at the Deck Layer and consumed by the Engine Layer.

---

## Error Types

The following exceptions are defined at the Deck Layer:

```
DeckConfigurationError
    Raised when a DeckConfig produces an invalid state
    Includes message describing the specific configuration conflict

InsufficientCardsError
    Raised when deal(), burn(), or peek() is called on an empty or
    near-empty deck that cannot fulfill the request
    Includes remaining card count in message

InvalidCardError
    Raised when attempting to construct a Card with invalid rank or suit
    Rank must be 0-13 at construction time
    Suit must be a valid Suit enumeration member
```

---

## Unit Test Requirements

The following must be covered by unit tests before the Deck Layer is considered complete:

- Standard deck contains exactly 52 unique cards
- Nulls deck contains exactly 56 unique cards, 4 of which are Null
- Orbs deck contains exactly 65 unique cards, 13 of which are Orbs suit
- No duplicate cards exist in any configuration
- deal(n) reduces remaining() by exactly n
- burn() reduces remaining() by exactly 1
- peek() does not reduce remaining()
- reset() restores remaining() to full deck size
- InsufficientCardsError raised correctly in all cases
- DeckConfig serializes and deserializes to JSON without data loss
- All three preset configurations produce correct card counts
- Null of Spades shorthand renders correctly
- Jack of Orbs shorthand renders correctly
- Null card is_null is True
- Standard card is_null is False
- Card equality is based on rank and suit only
- Cards are hashable and function correctly in sets and as dict keys
- low_card_warning() returns True below threshold and False above it

---

## Explicitly Out of Scope for Deck Layer

- Hand evaluation of any kind
- Knowledge of which cards are wild due to game rules
- Player assignment or tracking
- Pot or chip management
- Game variant logic
- UI rendering beyond display() and shorthand() string methods
- Network or multiplayer concerns
- Bot or AI logic

---
