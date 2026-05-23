# NumericEvaluator Requirements
## Poker Engine: Home Game Edition
### Version 1.0

---

## Overview

The NumericEvaluator is one of three concrete evaluators in the poker engine's evaluation family. It implements the BaseEvaluator interface defined in the Architecture Overview document. It handles all variants where winner determination is based on point total comparison against fixed targets rather than poker hand rankings.

The NumericEvaluator is used for:

- Six-and-a-Half / Twenty-one-and-a-Half (targets 6.5 and 21.5)
- Seven / Twenty-Seven (targets 7 and 27)

It does not use PokerKit. It has no knowledge of poker hand ranks, straights, flushes, or any poker hand evaluation concept. Its sole concern is summing card point values, comparing totals to targets, and determining which player is closest without exceeding each target.

---

## Technology

- Language: Python 3.11+
- No external dependencies beyond the Python standard library
- No PokerKit dependency
- Full type hints throughout
- All evaluation functions are pure functions where possible
- Internal arithmetic uses integer representation exclusively to avoid floating point errors. All values are multiplied by 2 internally and divided by 2 only for display purposes.

---

## Card Point Values

The following point values apply to all NumericEvaluator variants. Internal values are the display values multiplied by 2.

```
Card Rank       Display Value       Internal Value
Null (0)        0                   0
Ace (1)         1 or 11             2 or 22
2               2                   4
3               3                   6
4               4                   8
5               5                   10
6               6                   12
7               7                   14
8               8                   16
9               9                   18
10              10                  20
Jack (11)       0.5                 1
Queen (12)      0.5                 1
King (13)       0.5                 1
```

Face cards (Jack, Queen, King) are worth 0.5 points each. This is the defining characteristic of the six-and-a-half and seven/twenty-seven family of games.

Null cards are worth 0 points in all directions. They do not help or hurt a hand total in these games. They are dead cards for numeric evaluation purposes.

Orbs suit cards follow the same point values as standard suit cards. Suit is irrelevant to NumericEvaluator. Only rank determines point value.

---

## Target Configuration

Targets are configured per variant in variant_config and passed to the NumericEvaluator at evaluation time. They are not hardcoded in the evaluator.

```
SixHalfTwentyOneHalf:
    targets: [6.5, 21.5]
    internal_targets: [13, 43]

SevenTwentySeven:
    targets: [7, 27]
    internal_targets: [14, 54]
```

The evaluator treats all targets generically. Adding a new numeric variant with different targets requires only a new variant_config entry and a new GameVariant registry entry. The NumericEvaluator itself requires no modification.

---

## Internal Arithmetic

All arithmetic is performed in integer space using internal values. Display values are derived only when constructing the display_name or current_total fields of NumericEvaluatedHand.

```python
def to_internal(display_value: float) -> int:
    return round(display_value * 2)

def to_display(internal_value: int) -> float:
    return internal_value / 2
```

The round() call in to_internal() handles the single case of 0.5 face card values. All other display values are whole numbers and the multiplication is exact.

Comparison operations, bust detection, and distance-to-target calculations are performed exclusively on internal values. This ensures that a hand totaling 6.5 display points (13 internal) compares correctly to a target of 6.5 display points (13 internal) without floating point ambiguity.

---

## Ace Handling

Ace has two possible internal values: 2 (display: 1) and 22 (display: 11).

Ace value is not declared during the hand. It is declared at showdown as part of the declare mechanic, simultaneously with the high/low direction declaration.

### Single Direction Declaration

When a player declares HIGH or LOW, they also declare their Ace value at showdown:

- Declaring HIGH: Ace is typically declared as 22 (display: 11) to maximize the total toward the high target
- Declaring LOW: Ace is typically declared as 2 (display: 1) to minimize the total toward the low target
- The player may declare any value regardless of direction if it produces a better result

The declared Ace value is the player's binding choice. It cannot be changed after the chip reveal.

### Both-Ways Declaration

When a player declares BOTH, at least one Ace in the hand automatically assumes duality per the Architecture Overview specification:

- That Ace counts as internal value 2 for the LOW target calculation
- That Ace counts as internal value 22 for the HIGH target calculation simultaneously
- If multiple Aces are present, the duality Ace is whichever produces the best result in both directions simultaneously
- The remaining Aces (if any) take a single declared value applied to both calculations

### ace_dual_value() Implementation

```
ace_dual_value() behavior:
    HIGH direction:      Ace internal value is 22 (display: 11)
    LOW direction:       Ace internal value is 2 (display: 1)
    BOTH declaration:    At least one Ace is 2 for LOW calculation
                         and 22 for HIGH calculation simultaneously
                         Remaining Aces take the value that best serves
                         both calculations simultaneously
```

### Optimal Ace Assignment

When a player has multiple Aces and is not declaring BOTH, the evaluator determines the optimal Ace value assignment automatically at evaluation time:

```
def optimal_ace_assignment(
    ace_count: int,
    other_cards_internal_total: int,
    target_internal: int,
    direction: EvalDirection
) -> list[int]:
```

The function tries all 2^ace_count combinations of Ace values (each Ace independently 2 or 22) and returns the assignment that produces the total closest to target_internal without exceeding it. In the case of multiple equally optimal assignments, it prefers the assignment that stays furthest below the target to maximize safety margin.

For the BOTH direction, optimal_ace_assignment is called twice independently (once per target) with the duality constraint applied to at least one Ace.

---

## NumericEvaluatedHand Object

Extends BaseEvaluatedHand for numeric evaluation results.

```
NumericEvaluatedHand {
    is_partial: bool
    deck_config: DeckConfig
    display_name: str
    high_value: int
    low_value: int

    internal_total: int
    display_total: float
    ace_assignments: list[int]
    target_high_internal: int
    target_low_internal: int
    distance_to_high: int | None
    distance_to_low: int | None
    is_bust_high: bool
    is_bust_low: bool
    is_bust_both: bool
    card_count: int
    declaration: Declaration | None
}
```

### Field Definitions

**internal_total**: The sum of all card internal values using the declared or optimal Ace assignment. For partial hands this reflects the current total with optimal Ace assignment.

**display_total**: internal_total divided by 2. Used for display only.

**ace_assignments**: List of internal values assigned to each Ace in the hand, in card order. Empty if no Aces present.

**distance_to_high**: target_high_internal minus internal_total. None if is_bust_high is True. Lower distance is better for HIGH direction.

**distance_to_low**: target_low_internal minus internal_total. None if is_bust_low is True. Lower distance is better for LOW direction.

**is_bust_high**: True when internal_total exceeds target_high_internal regardless of Ace assignment. A hand is bust high only when even with all Aces at their minimum value (2) the total still exceeds the high target.

**is_bust_low**: True when internal_total exceeds target_low_internal regardless of Ace assignment. A hand is bust low when even with all Aces at minimum value the total still exceeds the low target.

**is_bust_both**: True when both is_bust_high and is_bust_low are True. A player who is bust both is eliminated from the hand. Their ante is not returned.

**high_value and low_value**: Inherited from BaseEvaluatedHand. For NumericEvaluatedHand these are derived as follows:

```
high_value: target_high_internal - distance_to_high
            0 if is_bust_high
            Higher is better for HIGH direction comparison

low_value:  target_low_internal - distance_to_low
            0 if is_bust_low
            Higher is better for LOW direction comparison
            (a total of 6 display toward a target of 6.5 has
            low_value of 13-1=12, better than a total of 5
            which has low_value of 13-3=10)
```

This encoding allows the standard BaseEvaluator compare() logic to work correctly for NumericEvaluatedHand without modification. Higher high_value wins HIGH direction. Higher low_value wins LOW direction. Bust hands have value 0 and lose to all non-bust hands.

---

## Core Evaluation Function

```
evaluate(
    cards: list[Card],
    deck_config: DeckConfig,
    direction: EvalDirection = EvalDirection.HIGH,
    declaration: Declaration = Declaration.HIGH,
    **variant_config
) -> NumericEvaluatedHand
```

### Required variant_config Keys

```
targets: list[float]    the display target values, e.g. [6.5, 21.5]
```

### Behavior

1. Extract internal targets from variant_config targets list
2. Identify Ace cards in the hand
3. Compute optimal Ace assignment for the specified direction and declaration
4. Sum all card internal values using the optimal Ace assignment
5. Compute distances to each target
6. Determine bust status for each target
7. Construct and return NumericEvaluatedHand

### Partial Hand Evaluation

When is_partial is True, the evaluation reflects the current hand total with optimal Ace assignment given cards dealt so far. The player has not yet stood. Additional cards may be taken. Partial evaluation is used for:

- The hand strength indicator in the UI (current_total display)
- Bot decision making during the draw phase

Partial NumericEvaluatedHand objects are valid for comparison during the draw phase for bot purposes but are not valid for showdown determination.

---

## Bust Detection

Bust detection must account for all possible Ace assignments before declaring a hand bust. A hand is only bust in a given direction if it exceeds the target even with all Aces assigned their minimum internal value of 2.

```
def is_bust(
    cards: list[Card],
    target_internal: int
) -> bool:
    non_ace_total = sum(card_internal_value(c) for c in cards
                        if c.rank != 1)
    ace_count = sum(1 for c in cards if c.rank == 1)
    minimum_total = non_ace_total + (ace_count * 2)
    return minimum_total > target_internal
```

A player who is bust in the HIGH direction but not the LOW direction is still eligible to win the LOW direction. They are not eliminated from the hand unless they are bust in both directions.

A player who is bust both is eliminated immediately. Their elimination is announced via a game_state_update WebSocket event. Their cards remain visible for informational purposes.

---

## Winner Determination

```
determine_winners(
    evaluated_hands: dict[str, NumericEvaluatedHand],
    direction: EvalDirection
) -> WinnerResult
```

### Winner Determination Logic

1. Exclude all hands where is_bust is True for the specified direction
2. If no hands remain (all players bust in this direction), the pot for this direction carries to the next hand. No winner is declared for this direction.
3. Among remaining hands, find the hand with the highest high_value (HIGH direction) or highest low_value (LOW direction)
4. If multiple hands share the highest value, all tied players are winners and split the pot for this direction
5. Return WinnerResult with winners list, is_tie flag, and pot_split flag

### All-Bust Handling

The all-bust scenario (all players bust in a given direction) must be handled explicitly. This is not an error condition. It is a valid game outcome, particularly in late draw rounds when everyone has taken too many cards chasing a target. The pot carry is handled by the Game Layer using the WinnerResult.

```
WinnerResult {
    winners: []
    winning_hand: None
    is_tie: False
    pot_split: False
    all_bust: True
    pot_carries: True
}
```

---

## Hand Comparison

```
compare(
    hand_a: NumericEvaluatedHand,
    hand_b: NumericEvaluatedHand,
    direction: EvalDirection
) -> ComparisonResult
```

Comparison uses high_value for HIGH direction and low_value for LOW direction as encoded in the NumericEvaluatedHand. Since these values are already encoded such that higher is better in both directions, the comparison logic is identical to PokerHandEvaluator's compare() at the value level.

A bust hand always loses to a non-bust hand because bust hands have value 0 and non-bust hands have value greater than 0.

Two bust hands compare as TIE since both have value 0. This is consistent with the all-bust scenario where neither player wins.

---

## High-Low Declare Evaluation

```
evaluate_for_declare(
    cards: list[Card],
    deck_config: DeckConfig,
    declaration: Declaration,
    **variant_config
) -> DeclareResult
```

### Behavior

When declaration is HIGH or LOW:

1. Evaluate the hand for the declared direction using optimal Ace assignment for that direction
2. Return DeclareResult with the appropriate evaluated hand populated and the other direction as None

When declaration is BOTH:

1. Apply Ace duality: identify the duality Ace per ace_dual_value() specification
2. Evaluate for HIGH direction with the duality Ace assigned internal value 22
3. Evaluate for LOW direction with the duality Ace assigned internal value 2
4. If multiple Aces exist, remaining Aces take the optimal value for each direction independently
5. Return DeclareResult with both high_hand and low_hand populated
6. Set must_win_both to True per house rules

### Ace Duality Example

Player holds: Ace, Ace, 7, Jack, 3 in Seven/Twenty-Seven (targets 7 and 27)

```
Non-ace internal total: 14 (7) + 1 (Jack) + 6 (3) = 21

For HIGH direction (target 54):
    Duality Ace: 22
    Second Ace optimized for HIGH: 22 (total: 21 + 22 + 22 = 65, bust)
    Second Ace at minimum: 2 (total: 21 + 22 + 2 = 45, distance 9)
    HIGH hand total: 45 internal (22.5 display)
    distance_to_high: 54 - 45 = 9

For LOW direction (target 14):
    Duality Ace: 2
    Second Ace optimized for LOW: 2 (total: 21 + 2 + 2 = 25, bust)
    Second Ace at minimum: 2 still busts (25 > 14)
    is_bust_low: True
    
DeclareResult:
    high_hand: 22.5 display, distance 9 to target 27
    low_hand: bust
    must_win_both: True
    
Scoop-or-bust outcome: player declared BOTH but is bust LOW.
Game Layer disqualifies player from both directions.
Player receives nothing.
```

This example illustrates why declaring BOTH is high-risk in numeric variants. The Ace duality helps but does not guarantee a viable low hand.

---

## Sleeper Cell Mechanic

The sleeper cell mechanic described in the Game Layer requirements is an information asymmetry concern, not an evaluation concern. The NumericEvaluator receives only the cards it is asked to evaluate and has no knowledge of which cards are face-up versus face-down.

However the NumericEvaluator supports the sleeper cell mechanic indirectly via partial evaluation. During the draw phase, the hand strength indicator in the UI calls evaluate() with is_partial implicitly True (fewer than a full hand of cards, or cards still being drawn). The current_total field of the resulting NumericEvaluatedHand is what the UI displays as the running total, showing only the cards that have been revealed.

The bot uses partial evaluation to estimate hand strength during the draw phase, incorporating the probability distribution of possible down card values into its decision to take another card or stand.

---

## Bot Considerations for Numeric Variants

The Tier 1 rule-based bot uses simplified heuristics for numeric variants:

```
if current partial total is within 2 of a target:
    stand
elif current partial total exceeds both targets:
    bust, stand (no choice)
elif distance to closest non-bust target > 4:
    take a card
else:
    take a card with probability proportional to distance
```

The Tier 2 Monte Carlo bot simulates possible card draws from the remaining deck and calculates the probability of improving versus busting for each target direction. This is more accurate than the rule-based heuristic, particularly in late draw rounds when the remaining deck composition is known.

The Claude API bot receives the current partial total, the targets, the remaining deck size, and the visible cards of all other players as context. It reasons about the draw decision in natural language. This is the most capable option for numeric variants because the strategy involves reading other players' visible totals and making inferences about their likely directions, which is difficult to encode in rule-based or Monte Carlo approaches.

---

## Hand Frequency Reporting

```
calculate_hand_frequencies(
    deck_config: DeckConfig,
    **variant_config
) -> dict[str, float]
```

For NumericEvaluator, hand frequencies are reported differently than for PokerHandEvaluator. Rather than hand rank frequencies, the NumericEvaluator reports approximate probability of reaching each target range given optimal play with a starting single down card.

```json
{
    "exact_low_target": 0.043,
    "within_1_of_low": 0.156,
    "within_2_of_low": 0.289,
    "bust_low_only": 0.134,
    "exact_high_target": 0.021,
    "within_1_of_high": 0.089,
    "within_2_of_high": 0.198,
    "bust_high_only": 0.089,
    "bust_both": 0.012
}
```

These frequencies are used by the UI reference view to set player expectations for these variants. Calculation uses Monte Carlo simulation with 100,000 sample hands defaulting to optimal play strategy.

---

## Error Types

All errors are namespaced under NumericEvaluator.

```
NumericEvaluator.InvalidTargetError
    Raised when variant_config contains invalid or missing targets
    Targets must be positive numbers
    At least two targets must be provided (low and high)
    Includes the invalid targets in the message

NumericEvaluator.InvalidCardValueError
    Raised when a card has no defined point value
    Should never occur with a correctly constructed Card from the Deck Layer
    Indicates a Deck Layer or configuration error

NumericEvaluator.IncomparableHandError
    Raised when compare() receives two partial hands
    Partial hands may not be compared at showdown
```

---

## Unit Test Requirements

The following must be covered before the NumericEvaluator is considered complete.

### Card Value Tests

- Null card has internal value 0
- Ace has internal value 2 in LOW direction
- Ace has internal value 22 in HIGH direction
- Jack has internal value 1
- Queen has internal value 1
- King has internal value 1
- Number cards 2 through 10 have correct internal values
- Orbs suit cards have same values as standard suit cards
- to_internal and to_display are exact inverses for all valid card values

### Arithmetic Tests

- Hand total correctly sums internal values
- Hand total with multiple face cards correctly accumulates 0.5 per card
- Hand total with mix of face cards and number cards is correct
- Internal arithmetic never uses float operations
- to_display correctly returns 0.5 for a single face card internal value of 1
- to_display correctly returns 6.5 for internal value 13

### Ace Assignment Tests

- Single Ace assigned 22 in HIGH direction when it does not bust the hand
- Single Ace assigned 2 in HIGH direction when 22 would bust
- Single Ace assigned 2 in LOW direction
- Two Aces optimally assigned for HIGH: both 22 if possible, else one 22 one 2, else both 2
- Two Aces optimally assigned for LOW: both 2
- Three Aces correctly handled in all direction combinations
- Optimal assignment prefers maximum safety margin when multiple assignments produce equal distance

### Bust Detection Tests

- Hand is not bust when Ace as minimum (2) keeps total at or below target
- Hand is bust when Ace as minimum (2) still exceeds target
- is_bust_high correctly False when hand can reach high target with Ace as 22
- is_bust_low correctly True when hand exceeds low target even with Ace as 2
- is_bust_both correctly True only when bust in both directions simultaneously
- Player with is_bust_both excluded from both direction winner determination

### Both-Ways Ace Duality Tests

- Duality Ace correctly assigned 2 for LOW and 22 for HIGH simultaneously
- Remaining Aces optimized independently per direction after duality Ace assigned
- Hand with one Ace declaring BOTH: Ace is 2 for LOW and 22 for HIGH
- Hand with two Aces declaring BOTH: one Ace dual, second Ace optimized per direction
- Example from requirements (two Aces, 7, Jack, 3 in Seven/Twenty-Seven) produces correct results
- Both-ways bust LOW correctly results in DeclareResult with is_bust_low True
- Game Layer scoop-or-bust correctly applied when DeclareResult shows bust in one direction

### Winner Determination Tests

- Player closest to target without exceeding wins
- Exact hit beats near miss in both directions
- Bust player loses to any non-bust player
- Two bust players tie with value 0
- All-bust scenario returns WinnerResult with all_bust True and pot_carries True
- Tied non-bust players correctly split the pot
- HIGH and LOW direction determined independently with separate winner sets

### Comparison Tests

- Higher high_value wins HIGH direction comparison
- Higher low_value wins LOW direction comparison
- Bust hand value 0 loses to any positive value
- Two hands with equal value return TIE

### Partial Hand Tests

- Partial evaluation correctly reflects current total with optimal Ace assignment
- Partial hand is_partial flag is True
- Partial hand correctly excluded from showdown comparison
- Bot correctly uses partial evaluation during draw phase

### Frequency Tests

- Frequency keys cover all expected outcome categories
- Frequency values sum to approximately 1.0
- Frequencies differ correctly between SixHalfTwentyOneHalf and SevenTwentySeven configurations
- Frequencies differ correctly between STANDARD and WITH_NULLS deck configs

### Error Tests

- InvalidTargetError raised for missing targets in variant_config
- InvalidTargetError raised for negative target values
- IncomparableHandError raised when comparing two partial hands

---

## Explicitly Out of Scope for NumericEvaluator

- Poker hand ranking of any kind
- Flush, straight, pair, or any poker hand concept
- PokerKit dependency or usage
- Wild card resolution (wild cards have no special meaning in numeric variants)
- Community card layout logic
- Game variant state machines
- Betting round management
- UI rendering of any kind
- Network or multiplayer concerns
- Declare enforcement, the scoop-or-bust rule is enforced by the Game Layer

---
