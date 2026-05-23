# PokerHandEvaluator Requirements
## Poker Engine: Home Game Edition
### Version 1.2

---

## Overview

The PokerHandEvaluator is one of potentially multiple evaluators in the poker engine's evaluation family. It implements the BaseEvaluator interface defined in the Architecture Overview document. It is responsible for poker hand ranking evaluation, hand comparison, winner determination, and hand frequency reporting for all variants in the game rotation that use standard poker hand rankings.

The PokerHandEvaluator wraps PokerKit for standard hand evaluation cases and extends it explicitly for non-standard cases introduced by Null cards, Orbs, wild cards, and five of a kind. It has no knowledge of game variants, betting sequences, player behavior, numeric point total evaluation, or UI concerns.

---

## Technology

- Language: Python 3.11+
- Primary dependency: PokerKit for standard hand evaluation
- No database concern at this layer
- Full type hints throughout
- All evaluation functions are pure functions where possible, meaning same input always produces same output with no side effects
- Computationally hot paths, specifically wild card resolution and best hand selection, must be optimized for repeated calls during Monte Carlo bot simulation

---

## Hand Rank Hierarchy

The following hand ranks are defined in ascending order of strength. Higher index beats lower index.

```
0   HIGH_CARD
1   ONE_PAIR
2   TWO_PAIR
3   THREE_OF_A_KIND
4   STRAIGHT
5   FLUSH
6   FULL_HOUSE
7   FOUR_OF_A_KIND
8   FIVE_OF_A_KIND
9   STRAIGHT_FLUSH
10  ROYAL_FLUSH
```

### Notes on Hierarchy

- FIVE_OF_A_KIND sits above FOUR_OF_A_KIND and below STRAIGHT_FLUSH
- FIVE_OF_A_KIND is possible when wild cards are in play, or when nulls_match_each_other is True and sufficient Null cards are present
- Four Null cards constitute FOUR_OF_A_KIND at rank zero when nulls_match_each_other is True. This hand loses to any FOUR_OF_A_KIND of rank two or higher but beats any FULL_HOUSE.
- ROYAL_FLUSH is a special case of STRAIGHT_FLUSH (10-J-Q-K-A of same suit) and is separated for display purposes only. It does not outrank a non-royal STRAIGHT_FLUSH for pot purposes unless the house rules JSON explicitly enables royal_flush_beats_straight_flush. Default is False.
- With Orbs in play, a Royal Flush of Orbs is valid.

---

## EvaluatedHand Object

The PokerHandEvaluator's primary return type is an EvaluatedHand implementing the BaseEvaluatedHand interface:

```
EvaluatedHand {
    hand_rank: HandRank
    best_five: list[Card]
    wild_assignments: dict[Card, Card]
    kickers: list[Card]
    display_name: str
    high_value: int
    low_value: int
    is_null_anchored: bool
    is_partial: bool
    deck_config: DeckConfig
    all_combinations: list[tuple[list[Card], EvaluatedHand]]
}
```

EvaluatedHand must implement comparison operators based on high_value for HIGH direction and low_value for LOW direction. The direction of comparison is passed as a parameter to comparison operations.

all_combinations stores every evaluated five card subset for reference by the UI layer, which may want to show why particular cards were chosen as the best five.

---

## Core Evaluation Function

```
evaluate(
    cards: list[Card],
    deck_config: DeckConfig,
    wild_ranks: list[int] = [],
    wild_suits: list[Suit] = [],
    direction: EvalDirection = EvalDirection.HIGH,
    declaration: Declaration = Declaration.HIGH
) -> EvaluatedHand
```

### Parameters

- `cards`: between 2 and 10 cards. Fewer than 5 cards are valid for partial hand evaluation during active betting rounds.
- `deck_config`: the active DeckConfig, consumed for Null semantics and Orbs awareness
- `wild_ranks`: list of ranks that are wild due to game rules, e.g. [3, 9] for Baseball. Separate from intrinsic wilds on the Card object itself.
- `wild_suits`: list of suits that are wild due to game rules. Rare but supported.
- `direction`: HIGH or LOW, determines optimization target for wild card resolution and best hand selection
- `declaration`: HIGH, LOW, or BOTH. When BOTH, triggers dual Ace behavior per the Ace Duality section below.

### Behavior

1. Identify all wild cards in the hand, both intrinsic and game-conferred
2. If no wilds are present, delegate to PokerKit for standard evaluation with Null and Orbs extensions applied
3. If wilds are present, resolve wild cards via the wild resolution algorithm described below
4. If more than five cards are present, select the best five via the best hand selection algorithm described below
5. Return a fully populated EvaluatedHand

### Partial Hand Evaluation

When fewer than five cards are provided:

- Evaluate what is currently present
- Return the best currently achievable hand rank given the cards in hand
- Mark the EvaluatedHand as is_partial: True
- Partial hands are used by the bot for in-progress hand strength estimation
- Partial hands are not valid for showdown comparison

---

## Ace Duality

Ace duality is the behavior of the Ace card when it may function as either rank 1 (low) or rank 14 (high) depending on context. The PokerHandEvaluator implements ace_dual_value() as required by BaseEvaluator.

### Standard Direction Behavior

```
HIGH direction: Ace is treated as rank 14 for all non-straight evaluation
LOW direction:  Ace is treated as rank 1 for all non-straight evaluation
```

### Straight Detection Behavior

Regardless of direction, when evaluating straights the evaluator always tries the Ace in both positions. The rank sequence is expanded:

```
def ace_expanded_ranks(ranks):
    if 1 in ranks:
        return ranks + [14]
    return ranks
```

This allows detection of both the wheel (A-2-3-4-5) and Broadway (10-J-Q-K-A) and with Nulls active, the Null-wheel (Null-A-2-3-4).

### Both-Ways Declaration Behavior

When declaration is BOTH, at least one Ace in the hand assumes duality simultaneously:

- That Ace counts as rank 1 for the LOW direction evaluation
- That Ace counts as rank 14 for the HIGH direction evaluation
- If multiple Aces are present, the duality Ace is whichever produces the best result in both directions simultaneously
- This duality is automatic and does not require a separate player declaration
- The scoop-or-bust rule still applies: the player must win or tie both directions or receives nothing

### Ace and Null Interaction

With Nulls active the rank ordering at the low end is unambiguous:

```
Null(0) < A(1) < 2 < 3 ...
```

Null and low Ace do not conflict. Null is always rank 0 with no duality. Ace is rank 1 in LOW direction and rank 14 in HIGH direction. They occupy distinct positions in all cases.

---

## Wild Card Resolution Algorithm

Wild card resolution finds the assignment of wild cards to specific rank and suit combinations that maximizes hand strength in the specified direction.

### Resolution Steps

1. Identify all wild cards in the provided card list
2. Build the candidate card universe from the active DeckConfig. For STANDARD this is 52 cards. For WITH_ORBS this is 65 cards.
3. If wilds_can_become_null is True, Null cards are included in the candidate universe. If wilds_can_become_null is False, Null cards are excluded from the candidate universe entirely regardless of deck configuration.
4. For each wild card, generate all possible assignments from the candidate universe subject to the physical uniqueness constraint described below.
5. Enumerate all combinations of wild assignments across all wild cards
6. For each combination, evaluate the resulting hand without wilds using standard evaluation
7. Return the assignment combination that produces the highest hand rank in the specified direction
8. In case of tie between assignment combinations, prefer the combination with the highest kicker sequence for HIGH direction or lowest kicker sequence for LOW direction

### Physical Uniqueness Constraint

A wild card may not be assigned to a specific card identity that already exists in the non-wild portion of the hand. Card identity is defined as the combination of rank AND suit together, not rank alone.

Examples of correct behavior:

- Hand contains Ace of Spades, Ace of Hearts, Ace of Clubs plus one wild card. The wild may become Ace of Diamonds, completing four Aces. It may not become Ace of Spades, Ace of Hearts, or Ace of Clubs as those specific cards are already physically present.
- Hand contains three real Aces plus one wild. The wild becomes the fourth Ace using whichever Ace suit is not already represented. Four Aces is the correct and intended result.
- Hand contains two wild cards and Ace of Spades. The first wild may become Ace of Hearts, the second wild may become Ace of Diamonds, yielding four Aces. Both wilds may target the Ace rank provided they resolve to different suits from each other and from the real Ace of Spades.

The constraint is per specific card identity, not per rank. Multiple wild cards may share a target rank provided each resolves to a distinct suit.

### Wild Cards as Null

- wilds_can_become_null defaults to True
- When True, a wild card may declare itself as a Null of any suit
- The assigned suit is meaningful: a wild declared as Null of Hearts is a Hearts card for flush evaluation purposes
- A wild declared as Null contributes to straights as rank zero
- A wild declared as Null contributes to flushes of its assigned suit
- When nulls_match_each_other is True, a wild declared as Null matches other Null cards for pair and set evaluation
- When nulls_match_each_other is False, a wild declared as Null does not match other Null cards for pair and set evaluation, but still contributes to straights and flushes
- Four Null cards, whether real or wild-assigned, constitute FOUR_OF_A_KIND at rank zero when nulls_match_each_other is True

### Wild Cards in Flush Situations

When wild card resolution determines that contributing to a flush maximizes hand strength, the following directional logic applies to suit rank selection:

- In HIGH direction: the wild becomes the highest available rank of the needed suit that is not already physically present in the hand. A wild contributing to a spade flush becomes King of Spades if available, not Null of Spades.
- In LOW direction: the wild becomes the lowest available rank of the needed suit that is not already physically present in the hand. A wild contributing to a spade flush for low hand construction becomes Null of Spades if wilds_can_become_null is True, otherwise becomes the Two of Spades or lowest available rank.
- This directional optimization applies consistently across all flush and straight flush resolution scenarios.

### Performance Requirement

Wild card resolution for a single hand with up to three wild cards must complete in under 50 milliseconds on modern consumer hardware. This is required for Monte Carlo bot simulation to remain responsive.

---

## Best Hand Selection Algorithm

When more than five cards are provided the evaluator must find the best five card combination.

### Selection Steps

1. Generate all C(n, 5) combinations of five cards from the n provided cards
2. For each combination, run full evaluation including wild resolution
3. Return the combination and its EvaluatedHand that scores highest in the specified direction
4. Store all evaluated combinations in all_combinations on the returned EvaluatedHand

### Combination Counts by Card Count

```
5 cards:   1 combination
6 cards:   6 combinations
7 cards:   21 combinations
8 cards:   56 combinations
9 cards:   126 combinations
10 cards:  252 combinations
```

Ten card evaluation at 252 combinations with wild resolution per combination is the computational ceiling. This must remain under 500 milliseconds on modern consumer hardware.

---

## Null Card Evaluation Rules

The following rules apply whenever include_nulls is True in the active DeckConfig.

### Rank Ordering

Null has rank 0. It is lower than all standard ranks including low Ace. The canonical rank sequence is:

```
Null(0), A(1), 2, 3, 4, 5, 6, 7, 8, 9, 10, J, Q, K, A(14)
```

### Null in Straights

- Null may anchor the bottom of a straight as rank 0
- Null-A-2-3-4 is a valid straight
- Null-A-2-3-4 of the same suit is a valid straight flush
- A hand may contain at most one Null anchor in a straight since there is only one rank below Ace

### Null in Flushes

- A Null card contributes to a flush if it shares a suit with four other cards
- Null of Spades counts as a Spade for flush evaluation purposes
- This applies regardless of nulls_match_each_other setting
- A wild card assigned as Null of a given suit contributes to flushes of that suit identically to a real Null of that suit

### Null Pair Semantics

- If nulls_match_each_other is False: Null cards do not match each other for pair, three of a kind, or four of a kind evaluation. They may still contribute to straights and flushes normally.
- If nulls_match_each_other is True: Null cards match each other for all pair and set evaluation. Four Null cards constitute FOUR_OF_A_KIND at rank zero, beating any FULL_HOUSE and losing to any FOUR_OF_A_KIND of rank two or higher.
- This flag does not affect Null behavior in straights or flushes under either setting.

### Best Low Hand with Nulls

The best possible low hand when Nulls are in play is Null-A-2-3-5 of mixed suits with no pair. Null-A-2-3-4 is excluded as the best low hand because it constitutes a straight. This constant is defined at the Deck Layer and referenced here for evaluation purposes.

---

## Hand Comparison

```
compare(
    hand_a: EvaluatedHand,
    hand_b: EvaluatedHand,
    direction: EvalDirection
) -> ComparisonResult
```

Returns WIN, LOSE, or TIE from hand_a's perspective.

### Comparison Rules

1. Compare hand_rank values. Higher rank wins in HIGH direction. Lower rank wins in LOW direction.
2. If hand_rank is equal, compare kicker sequences card by card from highest to lowest in HIGH direction, lowest to highest in LOW direction.
3. If all kickers are equal, return TIE.
4. TIE results in pot splitting between tied players.

### Low Hand Comparison

For LOW direction evaluation:

- Lower is better
- Hands are compared by their highest card first, then next highest, and so on
- A hand with no pair, no straight, no flush always beats a hand with any of those in LOW direction
- Null-A-2-3-5 beats A-2-3-4-6 in LOW direction because Null(0) is lower than A(1)

---

## High-Low Declare Evaluation

```
evaluate_for_declare(
    cards: list[Card],
    deck_config: DeckConfig,
    wild_ranks: list[int],
    declaration: Declaration
) -> DeclareResult
```

### DeclareResult Object

```
DeclareResult {
    declaration: Declaration
    high_hand: EvaluatedHand | None
    low_hand: EvaluatedHand | None
    is_both_ways: bool
    must_win_both: bool
}
```

### Both Ways Evaluation

When declaration is BOTH:

- Evaluate the hand independently for HIGH and LOW directions
- The best five cards for HIGH and the best five cards for LOW may be different subsets of the player's cards
- Ace duality is applied automatically per the Ace Duality section above
- Both evaluations are returned in the DeclareResult
- must_win_both is always True per house rules
- The PokerHandEvaluator does not enforce the scoop-or-bust rule. It returns the evaluation only. Pot distribution is the Game Layer's responsibility.

---

## Winner Determination

```
determine_winners(
    evaluated_hands: dict[str, EvaluatedHand],
    direction: EvalDirection
) -> WinnerResult
```

```
WinnerResult {
    winners: list[str]
    winning_hand: EvaluatedHand
    is_tie: bool
    pot_split: bool
}
```

For high-low games, determine_winners is called twice, once per direction, and the Game Layer combines the results for pot distribution.

---

## Hand Frequency Reporting

```
calculate_hand_frequencies(
    deck_config: DeckConfig,
    wild_ranks: list[int] = [],
    hand_size: int = 5
) -> dict[HandRank, float]
```

Returns approximate probability of each hand rank occurring given the current deck configuration and wild card rules. Used by the UI layer to generate the reference card showing adjusted hand rankings for the active configuration.

### Requirements

- Frequencies must sum to approximately 1.0
- Calculation uses Monte Carlo sampling for non-standard configurations
- Sample size for Monte Carlo frequency calculation is configurable, default 100,000 hands
- Results are cached per unique DeckConfig and wild_ranks combination
- Cache is invalidated when DeckConfig changes
- Frequency calculation runs at startup or on configuration change, not during active hand evaluation
- Reported frequencies reflect the impact of Orbs on flush probability, wild cards on upper hand rank probability, and Null cards on low hand construction probability

---

## Error Types

All errors are namespaced under PokerEvaluator to avoid collision with other evaluator error types.

```
PokerEvaluator.InvalidHandError
    Raised when evaluate receives an impossible card combination
    Example: two identical cards in the same hand
    Includes the offending cards in the message

PokerEvaluator.WildResolutionError
    Raised when wild card resolution fails to find any valid assignment
    Should be extremely rare and indicates a configuration conflict
    Includes the wild cards and candidate universe in the message

PokerEvaluator.IncomparableHandError
    Raised when compare receives two partial hands
    Partial hands may not be compared at showdown
```

---

## Unit Test Requirements

The following must be covered before the PokerHandEvaluator is considered complete:

- Royal Flush beats Straight Flush when royal_flush_beats_straight_flush is True
- Five of a Kind beats Straight Flush when present
- Five of a Kind correctly identified with wild cards
- Five of a Kind correctly identified with four Nulls when nulls_match_each_other is True
- Four Nulls correctly identified as FOUR_OF_A_KIND at rank zero when nulls_match_each_other is True
- Four Nulls lose to four Twos in HIGH direction comparison
- Four Nulls beat any FULL_HOUSE in HIGH direction comparison
- Wild card resolves to best possible card in HIGH direction
- Wild card resolves to best possible card for LOW hand construction in LOW direction
- Wild card with three real Aces resolves to the fourth Ace using an unrepresented Ace suit
- Two wild cards with one real Ace correctly resolve to two additional Ace suits yielding four Aces
- Wild card does not duplicate a specific card identity already present in the non-wild hand
- Wild card may share a target rank with another wild card provided each uses a distinct suit
- Wild card does not become Null when wilds_can_become_null is False
- Wild card becomes Null when wilds_can_become_null is True and it improves the hand
- Wild card becoming Null of Hearts counts as a Hearts card for flush evaluation
- Wild card in HIGH direction flush resolves to highest available rank of needed suit, not Null
- Wild card in LOW direction flush resolves to lowest available rank of needed suit, preferring Null when wilds_can_become_null is True
- Two Nulls do not form a pair when nulls_match_each_other is False
- Two Nulls form a pair when nulls_match_each_other is True
- Null of Spades contributes to a spade flush
- Null-A-2-3-4 correctly identified as a straight
- Null-A-2-3-4 of same suit correctly identified as a straight flush
- Null-A-2-3-5 correctly identified as best possible low hand with Nulls in play
- Null-A-2-3-4 correctly excluded as best low hand because it is a straight
- Ace treated as rank 14 in HIGH direction non-straight evaluation
- Ace treated as rank 1 in LOW direction non-straight evaluation
- Ace tried in both positions during straight detection regardless of direction
- Ace assumes duality automatically when declaration is BOTH
- Dual Ace counts as 1 for LOW calculation and 14 for HIGH calculation simultaneously
- Null(0) and low Ace(1) occupy distinct positions in rank ordering with no conflict
- Best hand selection correctly identifies best five from seven cards
- Best hand selection correctly identifies best five from ten cards
- HIGH and LOW direction evaluation return different best five cards when appropriate
- Both-ways declaration returns independent HIGH and LOW evaluations using potentially different five card subsets
- Tie detection works correctly for identical hand ranks and kickers
- Pot split flagged correctly on tie
- Hand frequency reporting sums to approximately 1.0
- Hand frequencies shift correctly with Orbs in play relative to standard deck
- Hand frequencies shift correctly with wild cards in play
- Frequency cache invalidates correctly on configuration change
- Performance: single hand evaluation with three wilds completes under 50ms
- Performance: ten card evaluation completes under 500ms

---

## Explicitly Out of Scope for PokerHandEvaluator

- Numeric point total evaluation of any kind
- Game variant state machines
- Betting round management
- Pot tracking or chip management
- Player tracking or seat management
- Bot decision making
- UI rendering of any kind
- Network or multiplayer concerns
- Auction mechanics
- Declare enforcement, the scoop-or-bust rule is enforced by the Game Layer
- Community card layout logic, Elevator grid management belongs to the Game Layer

---
