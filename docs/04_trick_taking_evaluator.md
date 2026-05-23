# TrickTakingEvaluator Requirements
## Poker Engine: Home Game Edition
### Version 1.0

---

## Overview

The TrickTakingEvaluator is the fourth concrete evaluator in the poker engine's evaluation family. It implements the BaseEvaluator interface defined in the Architecture Overview document. It handles all variants where winner determination is based on trick-taking mechanics rather than poker hand rankings or point totals.

The TrickTakingEvaluator is currently used for:

- Poulet

It does not use PokerKit. It has no knowledge of poker hand ranks, straights, flushes, point totals, or any poker or numeric evaluation concept. Its sole concern is determining which card wins a trick given a led suit and a trump suit, tracking trick counts per player, and determining hand outcomes based on trick thresholds.

---

## Technology

- Language: Python 3.11+
- No external dependencies beyond the Python standard library
- No PokerKit dependency
- Full type hints throughout
- All evaluation functions are pure functions where possible
- Trump suit and led suit are first-class concepts at this layer

---

## Core Concepts

### Trump Suit

The trump suit is designated at the start of each hand by flipping the top card of the remaining deck after the deal. Cards of the trump suit beat all cards of non-trump suits regardless of rank. Among trump cards, higher rank wins.

Trump suit is passed to the evaluator as part of variant_config on every evaluate() and determine_trick_winner() call. It is not stored on the evaluator instance since it changes each hand.

### Led Suit

The led suit is the suit of the first card played to a trick. Players must follow suit if they hold a card of the led suit. If a player cannot follow suit they may play any card including a trump. The Game Layer enforces the follow suit requirement. The TrickTakingEvaluator assumes the cards passed to it are legally played.

### Trump Ordering

Within the trump suit, cards rank in standard order:

```
Null(0) < A(1) < 2 < 3 < 4 < 5 < 6 < 7 < 8 < 9 < 10 < J < Q < K < A(14)
```

There are no Bower mechanics. The Jack of trumps has no special status. It ranks as a standard Jack within the trump suit.

### Non-Trump Ordering

Within a non-trump suit, cards rank in the same standard order. However a non-trump card of any rank loses to a trump card of any rank including Null of trumps if Nulls are active.

### Null Card in Trick Taking

When Nulls are active (WITH_NULLS deck config), a Null of the trump suit is the lowest trump. It beats all non-trump cards but loses to all other trump cards including the Two of trumps.

A Null of a non-trump suit is the lowest card of that suit. It contributes to following suit (a player holding only the Null of Hearts must play it when Hearts is led) but loses to all other cards of that suit and to all trumps.

### Orbs in Trick Taking

When Orbs are active (WITH_ORBS deck config), Orbs is a valid suit. It may be designated as the trump suit if the flipped card is an Orbs card. Players holding Orbs cards must follow suit when Orbs is led. Orbs trump cards beat all non-trump cards identically to standard trump suits.

---

## TrickEvaluatedHand Object

Extends BaseEvaluatedHand for trick-taking evaluation results.

```
TrickEvaluatedHand {
    is_partial: bool
    deck_config: DeckConfig
    display_name: str
    high_value: int
    low_value: int

    trump_suit: Suit
    tricks_won: int
    tricks_played: int
    tricks_remaining: int
    cards_remaining: list[Card]
    has_won_hand: bool
    has_lost_hand: bool
    is_void_in_trump: bool
    trump_card_count: int
    hand_strength_estimate: float
}
```

### Field Definitions

**tricks_won**: Number of tricks won so far in the current hand.

**tricks_played**: Number of tricks played so far.

**tricks_remaining**: Total tricks minus tricks_played. For Poulet this is always 5 minus tricks_played.

**cards_remaining**: Cards still in the player's hand not yet played.

**has_won_hand**: True when tricks_won reaches the win threshold (3 for Poulet).

**has_lost_hand**: True when tricks_remaining is less than the number of tricks still needed to win, meaning the player mathematically cannot reach the win threshold.

**is_void_in_trump**: True when the player holds no trump cards. Relevant for bot decision making on the stay-in declaration.

**trump_card_count**: Number of trump cards in the player's hand. Key metric for Poulet stay-in decision.

**hand_strength_estimate**: A float from 0.0 to 1.0 estimating the probability of winning three tricks given the current hand and trump suit. Used by the bot for the stay-in declaration. 0.0 means certain loss, 1.0 means certain win.

**high_value and low_value**: Inherited from BaseEvaluatedHand. For TrickTakingEvaluatedHand:

```
high_value: tricks_won * 100 + sum of ranks of won trick cards
            Encodes trick count primarily, card ranks as tiebreaker
            Higher is better

low_value:  Not used for trick-taking games in the current
            implementation. Defaults to 0.
            Trick-taking games do not have a low direction.
```

---

## Core Trick Winner Function

The primary function of TrickTakingEvaluator is determining which card wins a trick.

```
determine_trick_winner(
    played_cards: dict[str, Card],
    led_suit: Suit,
    trump_suit: Suit,
    deck_config: DeckConfig
) -> str
```

Returns the player_id of the trick winner.

### Winner Determination Logic

1. Identify all trump cards played (cards whose suit matches trump_suit)
2. If any trump cards were played, the highest trump card wins
3. If no trump cards were played, the highest card of the led suit wins
4. Cards of non-led, non-trump suits never win a trick regardless of rank
5. In the case of equal rank (only possible with wild cards, not applicable to Poulet by default), the first card played of that rank wins

### Rank Comparison

For both trump and non-trump comparison, rank ordering follows the canonical sequence from the Deck Layer:

```
Null(0) < A(1) < 2 < 3 < 4 < 5 < 6 < 7 < 8 < 9 < 10 < J(11) < Q(12) < K(13) < A(14)
```

Ace is always high in trick-taking evaluation. There is no low Ace concept in trick-taking games. Ace has rank 14 for all comparison purposes within TrickTakingEvaluator.

---

## Core Evaluation Function

```
evaluate(
    cards: list[Card],
    deck_config: DeckConfig,
    direction: EvalDirection = EvalDirection.HIGH,
    declaration: Declaration = Declaration.HIGH,
    **variant_config
) -> TrickEvaluatedHand
```

### Required variant_config Keys

```
trump_suit: Suit            the active trump suit for this hand
win_threshold: int          tricks needed to win, 3 for Poulet
total_tricks: int           total tricks in the hand, 5 for Poulet
tricks_won: int             tricks won so far, 0 at hand start
tricks_played: int          tricks played so far, 0 at hand start
```

### Behavior

The evaluate() function for TrickTakingEvaluator operates differently from the poker and numeric evaluators. Rather than evaluating a final hand at showdown, it is called:

1. At the stay-in declaration phase to estimate hand strength
2. After each trick to update the TrickEvaluatedHand state
3. At hand completion to determine final outcome

At declaration phase, tricks_won and tricks_played are both 0. The evaluator uses hand_strength_estimate to support the bot's stay-in decision.

At hand completion, has_won_hand and has_lost_hand reflect the final state.

### Hand Strength Estimation

For the stay-in declaration, the evaluator computes hand_strength_estimate as follows:

```
def estimate_hand_strength(
    cards: list[Card],
    trump_suit: Suit,
    win_threshold: int,
    total_tricks: int,
    player_count: int
) -> float:
```

The estimate uses a simplified heuristic rather than full Monte Carlo simulation for Tier 1 bot:

- Count trump cards in hand (trump_card_count)
- Count high non-trump cards (rank 11 or above, Ace high)
- Estimate probability of winning win_threshold tricks based on trump count, high card count, and player count

A hand with trump_card_count >= win_threshold has a high strength estimate. A hand with no trumps and no high cards has a low estimate. The formula is configurable via variant_config for future variant extensibility.

For Tier 2 Monte Carlo bot, estimate_hand_strength runs full simulation dealing remaining cards to opponents and simulating trick play thousands of times.

---

## Follow Suit Enforcement

The TrickTakingEvaluator does not enforce the follow suit rule. That responsibility belongs to the Game Layer, which has visibility into the player's full hand and can verify that a played card is legal before passing it to the evaluator.

The TrickTakingEvaluator assumes all cards passed to determine_trick_winner() are legally played. It does not validate follow suit compliance.

---

## Declare Evaluation

Trick-taking games do not use the high-low chip declare mechanic. The evaluate_for_declare() method is implemented as a pass-through returning a DeclareResult with only the HIGH direction populated and must_win_both set to False.

```
evaluate_for_declare(
    cards: list[Card],
    deck_config: DeckConfig,
    declaration: Declaration,
    **variant_config
) -> DeclareResult:
    return DeclareResult(
        declaration=Declaration.HIGH,
        high_hand=self.evaluate(cards, deck_config, **variant_config),
        low_hand=None,
        is_both_ways=False,
        must_win_both=False
    )
```

---

## Ace Duality

Trick-taking games have no Ace duality concept. Ace is always rank 14 (high) in trick-taking evaluation. The ace_dual_value() method returns 14 for all directions and declarations.

```
ace_dual_value() behavior:
    All directions:      Ace is rank 14
    All declarations:    Ace is rank 14
    No duality exists in trick-taking evaluation
```

---

## Hand Frequency Reporting

For TrickTakingEvaluator, calculate_hand_frequencies() reports the approximate probability of winning the hand (reaching the trick threshold) given a random five-card deal with a random trump suit.

```json
{
    "win_probability": 0.34,
    "zero_tricks_probability": 0.28,
    "partial_win_probability": 0.38,
    "average_tricks_won": 1.7,
    "trump_void_probability": 0.22
}
```

These frequencies inform the hand reference UI and help players calibrate their stay-in decisions. Calculated via Monte Carlo simulation with 100,000 sample hands.

---

## Winner Determination

```
determine_winners(
    evaluated_hands: dict[str, TrickEvaluatedHand],
    direction: EvalDirection
) -> WinnerResult
```

At hand completion:

1. Find the player(s) with has_won_hand True (tricks_won >= win_threshold)
2. If exactly one player has won, that player wins the pot
3. If multiple players reached the threshold in the same trick (impossible in strict trick-taking since only one player wins each trick), the player who reached the threshold first wins
4. If no player reached the threshold (nobody won three tricks), return WinnerResult with all_threshold_failed True and pot_carries True

```
WinnerResult {
    winners: list[str]
    winning_hand: TrickEvaluatedHand | None
    is_tie: bool
    pot_split: bool
    all_threshold_failed: bool
    pot_carries: bool
}
```

The all_threshold_failed scenario is a normal and frequent outcome in Poulet. It is not an error condition. The Game Layer handles the pot carry and redeal.

---

## Zero Trick Penalty

The TrickTakingEvaluator identifies players who stayed in and won zero tricks:

```
identify_zero_trick_players(
    evaluated_hands: dict[str, TrickEvaluatedHand],
    stayed_in: list[str]
) -> list[str]
```

Returns player IDs from stayed_in whose tricks_won is 0. These players are subject to the zero trick penalty. The penalty amount and burn limit enforcement are handled by the Game Layer and PotManager, not by the evaluator.

---

## Error Types

```
TrickTakingEvaluator.InvalidTrickError
    Raised when determine_trick_winner receives an empty played_cards dict
    or a dict with cards of impossible suits given the deck config
    Includes the played_cards and deck_config in the message

TrickTakingEvaluator.InvalidTrumpSuitError
    Raised when trump_suit is not a valid suit in the active deck config
    Includes the invalid suit and active config in the message

TrickTakingEvaluator.IncomparableHandError
    Raised when determine_winners is called before the hand is complete
    A hand is complete when tricks_played equals total_tricks or
    a player has reached win_threshold
```

---

## Unit Test Requirements

### Trump and Led Suit Tests

- Trump card beats non-trump card of any rank including Ace
- Null of trump beats non-trump Ace
- Two of trump beats Ace of non-trump
- Highest trump wins when multiple trumps played
- Highest led suit card wins when no trump played
- Non-led non-trump card never wins regardless of rank
- Ace of trumps beats King of trumps
- Ace of led suit beats King of led suit when no trump played
- Null of trump loses to Two of trump
- Null of non-trump suit loses to all trump cards
- Orbs correctly functions as trump when designated
- Orbs card correctly follows suit when Orbs is led

### Trick Winner Tests

- Correct player identified as winner in all suit combinations
- Single player plays only card, wins trick
- All players play trump, highest trump wins
- Mixed trump and non-trump, highest trump wins
- No trump played, highest led suit card wins
- No trump played, non-led suit cards correctly ignored

### Hand Strength Estimation Tests

- Hand with three or more trumps has strength estimate above 0.6
- Hand with zero trumps has strength estimate below 0.3
- Hand with two trumps and two high non-trump cards has moderate estimate
- Estimate varies correctly with player count
- Estimate is always between 0.0 and 1.0 inclusive

### Trick Count Tests

- tricks_won increments correctly after each won trick
- tricks_played increments correctly after each trick regardless of winner
- tricks_remaining decrements correctly
- has_won_hand True when tricks_won reaches win_threshold
- has_lost_hand True when tricks_remaining less than tricks still needed
- has_won_hand and has_lost_hand mutually exclusive

### Winner Determination Tests

- Player with three tricks correctly identified as winner
- all_threshold_failed True when no player reaches three tricks
- pot_carries True on all_threshold_failed
- zero trick players correctly identified from stayed_in list
- Folded players not included in zero trick penalty

### Ace Tests

- Ace always rank 14 in all comparison contexts
- Ace of trump beats King of trump
- Ace of led suit beats King of led suit when no trump played
- ace_dual_value returns 14 for all directions

### Null and Orbs Tests

- Null of trump correctly lowest trump
- Null of non-trump correctly lowest of that suit
- Null of trump beats Null of non-trump
- Orbs trump card correctly beats non-trump Orbs card when Orbs is trump

---

## Explicitly Out of Scope for TrickTakingEvaluator

- Follow suit enforcement (Game Layer responsibility)
- Stay-in or fold declaration management (Game Layer responsibility)
- Pot management and burn limit enforcement (Game Layer and PotManager)
- Bower mechanics of any kind (not in Poulet)
- Trump bidding or calling (not in Poulet)
- High-low declare mechanic (not applicable to trick-taking games)
- Poker hand ranking of any kind
- Numeric point total evaluation of any kind
- UI rendering of any kind
- Network or multiplayer concerns

---

Now the Poulet variant section to append to the Game Layer document, followed by the updated Architecture Overview and config files.

---

## Poulet Variant (Addition to Game Layer Requirements)

### PouletVariant

**Evaluator**: TrickTakingEvaluator

**Description**: A trick-taking game where players ante, receive five cards, observe the trump suit revealed by a card flip, declare in or out, then play tricks. First player to win three tricks wins the pot. Players who stay in and win zero tricks match the pot up to the burn limit. If no player wins three tricks, the hand redeals with the pot carrying.

**Phase sequence:**

```
SETUP
ANTE
INITIAL_DEAL        (5 down per player)
TRUMP_REVEAL        (flip top card of remaining deck, suit becomes trump)
STAY_IN_DECLARE     (each player declares in or out, in seat order)
TRICK_ROUND         (repeating, one trick per round, up to 5 total)
HAND_RESOLUTION     (determine winner or trigger redeal)
POT_DISTRIBUTION    (on win) or POT_CARRY (on redeal)
COMPLETE
```

**TRUMP_REVEAL phase:**

The top card of the deck is flipped face-up and placed beside the deck. Its suit is the trump suit for this hand. The card itself is not dealt to any player and takes no part in play. The trump suit is stored in variant_config and passed to the TrickTakingEvaluator on every evaluate() and determine_trick_winner() call.

The trump reveal card is visible to all players and included in all PlayerView objects as trump_card and trump_suit fields added to the hand store.

**STAY_IN_DECLARE phase:**

Players declare in or out in seat order starting from the player left of the dealer. This is sequential, not simultaneous, unlike the Guts declaration. Each player sees the trump suit and their own five cards before deciding.

A player who declares out discards their hand face-down and takes no further part in the hand. They neither win nor lose beyond their ante.

If all players declare out, the pot carries to the next hand of Poulet and a new hand is dealt. All players re-ante.

If exactly one player declares in, that player wins the pot automatically without playing tricks. No tricks are played.

If two or more players declare in, trick play proceeds.

The sequential declaration creates an information leak: a player declaring in early signals hand strength. A player declaring in after seeing others fold has additional information. This is intentional and part of the game's strategic texture.

**TRICK_ROUND phase:**

A trick round proceeds as follows:

1. The player who won the previous trick leads (the player left of the dealer leads the first trick)
2. Each remaining player in clockwise order plays one card
3. Follow suit rule: a player must play a card of the led suit if they hold one. If they hold no card of the led suit they may play any card including trump.
4. The Game Layer enforces follow suit. If a player submits a card that violates follow suit, the action is rejected with ILLEGAL_ACTION error.
5. After all active players have played, determine_trick_winner() is called
6. The trick winner's tricks_won is incremented
7. If the trick winner has reached three tricks, hand resolution proceeds immediately. Remaining tricks are not played.
8. If all five tricks have been played without anyone reaching three tricks, hand resolution proceeds.
9. Otherwise another TRICK_ROUND begins with the trick winner leading.

**Follow Suit Enforcement in the Game Layer:**

```
def validate_trick_card(
    game_state: GameState,
    player_id: str,
    played_card: Card
) -> bool:

    led_suit = game_state.current_trick_led_suit
    if led_suit is None:
        return True

    player_hand = get_player_hand(game_state, player_id)
    has_led_suit = any(
        c.card.suit == led_suit
        for c in player_hand
        if not c.is_played
    )

    if has_led_suit and played_card.suit != led_suit:
        return False

    return True
```

**HAND_RESOLUTION phase:**

Three possible outcomes:

```
Outcome 1: A player has won three tricks
    That player wins the pot
    Proceed to POT_DISTRIBUTION then COMPLETE

Outcome 2: All five tricks played, no player won three tricks
    Identify zero-trick players among stayed-in players
    Zero-trick players match the pot up to burn limit
    Cascade payments added to pot
    Pot carries to next hand
    Increment redeal_count
    Return to SETUP for redeal

Outcome 3: Only one player remained after declarations
    That player wins automatically
    Proceed to POT_DISTRIBUTION then COMPLETE
```

**Zero Trick Penalty:**

The zero trick penalty in Poulet uses the same burn limit infrastructure as Guts. The GutsState structure is reused as PouletPenaltyState with identical burn tracking:

```
PouletPenaltyState {
    zero_trick_players: list[str]
    penalty_amounts: dict[str, int]
    burn_amounts: dict[str, int]
    burn_limit: float
    players_at_limit: list[str]
}
```

A player who has reached the burn limit across Poulet hands in the session pays nothing for zero tricks. They are not eliminated from future Poulet hands. The burn limit is cumulative across the session identically to Guts.

**Pot carry on redeal:**

When no player wins three tricks the pot carries in full. All players at the table re-ante on top of the existing pot. This can produce large pots across multiple redeals, which is expected and intentional. There is no cap on pot size.

**Bot stay-in decision:**

The Tier 1 bot uses hand_strength_estimate from TrickTakingEvaluator to decide whether to stay in:

```
if hand_strength_estimate > (0.4 + aggression * 0.2):
    stay in
else:
    fold
```

A bot with aggression 0.5 stays in when hand_strength_estimate exceeds 0.5. A more aggressive bot stays in on weaker hands. A risk-averse bot requires a stronger estimate.

The Tier 2 Monte Carlo bot simulates full trick play against the likely hands of other stayed-in players.

The Claude API bot receives the five hole cards, the trump suit, the number of players who have already declared in or out, and their declaration choices, then reasons about the stay-in decision in natural language.

**Visibility:**

All cards in Poulet are played face-up to the trick. There are no face-down cards during trick play. The trump reveal card is face-up and visible to all. The only hidden information is each player's hole cards before the STAY_IN_DECLARE phase. Once a player plays a card to a trick it is face-up and visible to everyone.

PlayerView additions for Poulet:

```
trump_suit: Suit
trump_card: Card
current_trick: dict[str, Card]
tricks_won: dict[str, int]
stayed_in_players: list[str]
folded_players: list[str]
```

**Unit test additions for PouletVariant:**

- Trump reveal correctly sets trump_suit in game_state
- Sequential declaration correctly proceeds in seat order
- Folded player receives no further legal actions
- Single stayed-in player wins automatically without playing tricks
- All-fold scenario carries pot and redeals
- Follow suit correctly enforced, illegal plays rejected
- Trick winner correctly leads next trick
- Three-trick win correctly terminates hand before remaining tricks played
- Five tricks with no winner correctly triggers zero trick penalty
- Zero trick penalty correctly matched to pot up to burn limit
- Burn limit correctly prevents payment beyond limit
- Pot carry correctly accumulates across multiple redeals
- Bot stay-in threshold scales correctly with aggression setting
- Trump suit correctly passed to TrickTakingEvaluator on every trick

---
