# Game Layer Requirements
## Poker Engine: Home Game Edition
### Version 1.1

---

## Overview

The Game Layer sits above the Evaluation Layer and below the UI Layer via the REST API. It is the most complex layer in the system. It is responsible for:

- Variant state machine definitions and execution
- Modifier system integration
- Betting round management across all betting structures
- Community card layout management
- Pot management and chip distribution
- Declare mechanic enforcement including scoop-or-bust
- Player seat management
- Bot invocation and decision integration
- Game state visibility management per player
- Persistence Layer integration for chip ledger and hand history

The Game Layer has no knowledge of UI rendering. It produces game state objects that the REST API serializes and delivers to the frontend.

---

## Technology

- Language: Python 3.11+
- No external dependencies beyond the Evaluation Layer, Deck Layer, and Persistence Layer
- Full type hints throughout
- State machines implemented as explicit phase enumerations with transition functions, not implicit control flow
- No async/await

---

## Core Data Structures

### GameState

The single authoritative representation of a hand in progress. Maintained internally by the Game Layer. Never exposed directly to the UI or bot. Player-specific views are derived from GameState via the visibility system.

```
GameState {
    hand_id: int
    session_id: int
    variant: GameVariant
    modifiers: list[GameModifier]
    deck_config: DeckConfig
    active_game_config: ActiveGameConfig
    phase: GamePhase
    players: list[PlayerState]
    dealer_index: int
    active_player_index: int
    pot: Pot
    community_layout: CommunityLayout | None
    betting_state: BettingState
    wild_ranks: list[int]
    wild_suits: list[Suit]
    action_has_occurred: bool
    redeal_count: int
    hand_history: list[GameEvent]
    four_card_buy_count: int
}
```

`four_card_buy_count` tracks how many 4s have appeared at the table this hand, regardless of whether players bought or passed. Used by NightBaseballVariant and JoesBaseballVariant for escalating buy price calculation. Initialized to 0 at hand start. 0 in all other variants.

### PlayerState

```
PlayerState {
    player_id: str
    name: str
    is_bot: bool
    seat_index: int
    chip_stack: int
    hole_cards: list[PositionedCard]
    is_folded: bool
    is_standing: bool
    is_eliminated_this_hand: bool
    current_bet: int
    total_bet_this_round: int
    declaration: Declaration | None
    in_guts: bool | None
    cards_to_discard: list[Card]
    personal_wild_rank: int | None
}
```

`personal_wild_rank` is the current personal wild rank for this player. None if the player has no face-down cards or the variant does not use personal wilds. Recalculated after every deal or reveal event. ChicagoVariant only. None in all other variants.

### PositionedCard

A card with visibility metadata attached. This is how the Game Layer tracks which cards are face up versus face down.

```
PositionedCard {
    card: Card
    is_face_up: bool
    position_index: int
    revealed_at_phase: GamePhase | None
}
```

### Pot

```
Pot {
    main_pot: int
    side_pots: list[SidePot]
    carry_amount: int
    ante_amount: int
    total() -> int
}

SidePot {
    amount: int
    eligible_player_ids: list[str]
}
```

Side pots are created automatically when a player goes all-in for less than the full bet. The pot manager handles side pot creation and eligibility tracking.

### CommunityLayout

```
CommunityLayout {
    layout_type: LayoutType
    cards: list[PositionedCard]
    rows: list[list[int]]
    columns: list[list[int]]
    diagonals_active: bool
    center_index: int | None
    get_valid_selections(layout_type) -> list[list[int]]
}

LayoutType {
    NONE
    POOL
    CROSS
    ELEVATOR
    GRID_3x3
}
```

`get_valid_selections()` returns the list of valid card index groups a player may use given the layout type. For ELEVATOR it returns three row selections plus two diagonal selections if `diagonals_active` is True. For CROSS it returns the horizontal and vertical selections. For POOL it returns all possible combinations up to the variant's maximum community card use count.

### BettingState

```
BettingState {
    structure: BettingStructure
    small_blind: int | None
    big_blind: int | None
    ante: int | None
    bring_in: int | None
    current_bet: int
    minimum_raise: int
    betting_round: int
    players_acted: list[str]
    last_aggressor_id: str | None
    auction_state: AuctionState | None
    guts_state: GutsState | None
}

BettingStructure {
    LIMIT
    NO_LIMIT
    POT_LIMIT
    BRING_IN
    AUCTION
    GUTS_DECLARE
}
```

### AuctionState

```
AuctionState {
    current_card: PositionedCard
    current_high_bid: int
    current_high_bidder_id: str | None
    bidding_order: list[str]
    current_bidder_index: int
    cards_acquired: dict[str, list[Card]]
    auction_round: int
    total_auction_rounds: int
}
```

### GutsState

```
GutsState {
    declarations: dict[str, bool]
    declarations_revealed: bool
    cascade_round: int
    burn_amounts: dict[str, int]
    burn_limit: float
    players_at_limit: list[str]
}
```

### GamePhase

Each variant defines its own valid phase sequence. The following phases are available across all variants. Not all variants use all phases.

```
GamePhase {
    SETUP
    ANTE
    INITIAL_DEAL
    DEAL_ROUND
    BET_ROUND
    DRAW_ROUND
    FLIP_ROUND
    AUCTION_ROUND
    COMMUNITY_REVEAL
    FORCED_DISCARD
    GUTS_DECLARE
    GUTS_CASCADE
    NUMERIC_DRAW
    NUMERIC_BET
    TAKE_LAST_UP_OFFER
    DECLARE
    SHOWDOWN
    POT_DISTRIBUTION
    COMPLETE
}
```

`TAKE_LAST_UP_OFFER` is the phase during which each player is offered the TAKE_LAST_CARD_UP action before their final river card is dealt. Used by ChicagoVariant and JoesBaseballVariant.

### GameEvent

Every state transition is recorded as a GameEvent for hand history, debugging, and bot reasoning.

```
GameEvent {
    event_type: EventType
    player_id: str | None
    card: Card | None
    amount: int | None
    phase: GamePhase
    timestamp: datetime
    modifier_triggered: str | None
    metadata: dict
}

EventType {
    ANTE_POSTED
    CARD_DEALT
    CARD_REVEALED
    CARD_FLIPPED
    BET_PLACED
    CALL_MADE
    RAISE_MADE
    FOLD
    CHECK
    DRAW_REQUESTED
    CARD_DISCARDED
    BID_PLACED
    AUCTION_WON
    GUTS_DECLARED
    GUTS_CASCADE_FIRED
    FORCED_DISCARD
    WILD_CHANGED
    MODIFIER_FIRED
    DECLARATION_MADE
    FOUR_CARD_BUY_OFFERED
    FOUR_CARD_BUY_ACCEPTED
    FOUR_CARD_BUY_PASSED
    TAKE_LAST_UP_ACCEPTED
    TAKE_LAST_UP_DECLINED
    SHOWDOWN
    POT_AWARDED
    REDEAL_TRIGGERED
    HAND_COMPLETE
}
```

---

## Visibility System

The visibility system derives player-specific views from the authoritative GameState. It is the Game Layer's mechanism for information asymmetry.

```
get_player_view(
    game_state: GameState,
    requesting_player_id: str
) -> PlayerView
```

### PlayerView

```
PlayerView {
    hand_id: int
    phase: GamePhase
    my_cards: list[PositionedCard]
    other_players: list[OpponentView]
    community_layout: CommunityLayoutView | None
    pot_total: int
    my_stack: int
    betting_state: BettingStateView
    wild_ranks: list[int]
    wild_suits: list[Suit]
    active_modifiers: list[str]
    legal_actions: list[LegalAction]
    hand_strength: PartialHandStrength | None
    my_personal_wild_rank: int | None
}
```

`my_personal_wild_rank` is the requesting player's current personal wild rank. None in all variants except Chicago. Included in PlayerView so the UI can display the active wild to the human player.

### OpponentView

```
OpponentView {
    player_id: str
    name: str
    is_bot: bool
    seat_index: int
    chip_stack: int
    visible_cards: list[PositionedCard]
    is_folded: bool
    is_standing: bool
    current_bet: int
    declaration_made: bool
}
```

OpponentView never includes hole cards that are face down. `visible_cards` contains only cards where `is_face_up` is True on the PositionedCard. OpponentView never includes `personal_wild_rank`. A player's personal wild rank is private information derived from their face-down cards, which are never visible to opponents.

### LegalAction

```
LegalAction {
    action_type: ActionType
    min_amount: int | None
    max_amount: int | None
    available_cards: list[Card] | None
}

ActionType {
    FOLD
    CHECK
    CALL
    RAISE
    BET
    DRAW
    STAND
    FLIP
    BID
    PASS_BID
    GUTS_IN
    GUTS_OUT
    DECLARE_HIGH
    DECLARE_LOW
    DECLARE_BOTH
    DISCARD
    TAKE_LAST_CARD_UP
    PASS_LAST_CARD_UP
    BUY_FOUR_CARD
    PASS_FOUR_CARD
}
```

The `legal_actions` list on PlayerView contains exactly the actions available to the requesting player at the current moment. The UI renders only these actions. The Game Layer rejects any submitted action not in the legal actions list for the current player.

### Hand Strength Hint

The PlayerView includes an optional `hand_strength` field containing a partial evaluation of the player's current visible hand. This is the training aid for the human player, showing what hand they currently hold without telling them what to do.

```
PartialHandStrength {
    display_name: str
    hand_rank: HandRank | None
    current_total: float | None
    is_partial: bool
    notes: str | None
}
```

For poker hand variants the `display_name` is something like "Two Pair, Aces and Eights." For numeric variants the `current_total` shows the current point total. The `notes` field can carry contextual information like "Null anchors a potential straight flush" or "Personal wild: 3s."

---

## Shared Action: TAKE_LAST_CARD_UP

TAKE_LAST_CARD_UP is a voluntary action available in ChicagoVariant and JoesBaseballVariant where a player may elect to receive their final card face-up instead of face-down. The motivation differs by variant but the Game Layer action is identical.

When a player selects TAKE_LAST_CARD_UP:

- The final card is dealt face-up and visible to all players
- Any cost associated with the action is paid into the pot
- The action is offered as a legal action before the final card is dealt, not after
- A player who selects PASS_LAST_CARD_UP receives their final card face-down per normal dealing rules
- The action is irrevocable once taken

Cost per variant:

```
ChicagoVariant:        $1, configurable via house_rules.json chicago.take_last_up_cost
JoesBaseballVariant:   free, no cost
```

---

## Shared Mechanic: Four Card Escalating Buy

NightBaseballVariant and JoesBaseballVariant share an escalating buy mechanic triggered when a player flips or is dealt a 4.

When a 4 appears:

1. `four_card_buy_count` on GameState increments immediately, before the buy offer is made
2. The current buy price is calculated from `four_card_buy_count` and the active price schedule
3. The player is offered BUY_FOUR_CARD or PASS_FOUR_CARD as legal actions
4. If BUY_FOUR_CARD is selected, the player pays the current price into the pot and receives one additional card face-down from the deck
5. If PASS_FOUR_CARD is selected, the 4 remains in the player's hand as a non-wild card and no card is received
6. Either way `four_card_buy_count` has already incremented for the next 4

Price schedule calculation:

```python
def get_four_card_buy_price(
    four_card_buy_count: int,
    price_schedule: list[float]
) -> float:
    index = min(four_card_buy_count - 1, len(price_schedule) - 1)
    return price_schedule[index]
```

Price schedules configured in house_rules.json:

```
QUARTER_SCHEDULE:   [0.25, 0.50, 0.75, 1.00]
DOLLAR_SCHEDULE:    [1.00, 2.00, 3.00, 4.00]
```

The price caps at the final schedule entry for all subsequent 4s. `four_card_buy_count` is reset to 0 at the start of each hand.

---

## Variant State Machines

Each variant is implemented as a state machine class inheriting from BaseVariant.

### BaseVariant Interface

```
BaseVariant (abstract)

    variant: GameVariant
    evaluator_class: type[BaseEvaluator]
    default_betting_structure: BettingStructure
    min_players: int
    max_players: int

    initialize(
        game_state: GameState,
        active_game_config: ActiveGameConfig
    ) -> GameState

    get_phase_sequence() -> list[GamePhase]

    execute_phase(
        game_state: GameState,
        phase: GamePhase
    ) -> GameState

    get_legal_actions(
        game_state: GameState,
        player_id: str
    ) -> list[LegalAction]

    apply_action(
        game_state: GameState,
        player_id: str,
        action: PlayerAction
    ) -> GameState

    is_phase_complete(
        game_state: GameState,
        phase: GamePhase
    ) -> bool

    advance_phase(
        game_state: GameState
    ) -> GameState

    resolve_showdown(
        game_state: GameState
    ) -> ShowdownResult
```

After each `execute_phase()` and `apply_action()` call the Game Layer runs the modifier hook before returning the updated GameState:

```
for modifier in game_state.active_game_config.modifiers:
    for card in newly_dealt_or_revealed_cards:
        if modifier.trigger_condition(card, game_state):
            effect = modifier.execute_effect(game_state)
            game_state = apply_modifier_effect(game_state, effect)
            if not house_rules.modifier_stacking:
                break
```

### Variant Implementations

---

#### SevenCardStudVariant

**Phase sequence:**
```
SETUP
ANTE
INITIAL_DEAL     (2 down, 1 up per player)
BET_ROUND        (bring-in from lowest face-up card, then standard betting)
DEAL_ROUND       (1 up per player)
BET_ROUND
DEAL_ROUND       (1 up per player)
BET_ROUND
DEAL_ROUND       (1 up per player)
BET_ROUND
DEAL_ROUND       (1 down per player, the river)
BET_ROUND
SHOWDOWN
POT_DISTRIBUTION
COMPLETE
```

**Bring-in rule:** The player showing the lowest face-up card by rank posts the bring-in. Ties broken by suit in order CLUBS, DIAMONDS, HEARTS, SPADES, ORBS (lowest to highest). The bring-in amount is defined in house_rules.json. The first bring-in round is identified by deriving its index from the phase sequence using a single source of truth rather than a hardcoded constant.

**Deck exhaustion:** With 9 players and no folds, deck exhaustion is possible before the river card. If the deck cannot fulfill the river deal, a single community card is dealt face-up as a shared river card for all remaining players. The `low_card_warning` from the Deck Layer triggers before this point.

---

#### FiveCardDrawVariant

**Phase sequence:**
```
SETUP
ANTE
INITIAL_DEAL     (5 down per player)
BET_ROUND
DRAW_ROUND       (each player discards 0-3 cards, receives replacements)
BET_ROUND
SHOWDOWN
POT_DISTRIBUTION
COMPLETE
```

**Draw rules:** Each player may discard and replace up to 3 cards. A player holding an Ace may discard 4 cards and keep the Ace. A player may stand pat (draw 0). Draw requests are processed in seat order. The player states how many cards they are discarding before discarding, so opponents know the draw count without seeing the discarded cards.

---

#### ChicagoVariant

Chicago is Seven Card Stud with two additional mechanics: the high spade pot split and a personal wild card system. It requires its own variant state machine rather than being a simple modifier on SevenCardStudVariant.

LowChicago is identical with the lowest spade in the hole instead of the highest.

**Personal Wild Card Rule:**

Each player's lowest-ranked face-down card determines their personal wild card rank for that hand. Wild cards are personal: they apply only to the individual player's hand evaluation and are not table-wide.

Rules:

- At any point during the hand, a player's wild rank is the lowest rank among all of their currently face-down cards
- If multiple face-down cards share the lowest rank, all cards of that rank in the player's hand are wild simultaneously. Two 3s face-down means both 3s are wild.
- As new face-down cards are dealt, the wild designation shifts if the new card has a lower rank than the current wild
- As face-down cards are revealed (voluntarily or at showdown), the wild designation recalculates based on remaining face-down cards
- A player with no face-down cards has no personal wild card
- Wild cards apply to hand building only. They have no bearing on the high spade split determination. The high spade split is determined by the actual physical card, not its wild value.

Wild rank recalculation runs after every deal or reveal event:

```python
def calculate_personal_wild_rank(
    player_state: PlayerState
) -> int | None:

    face_down_ranks = [
        c.card.rank
        for c in player_state.hole_cards
        if not c.is_face_up
    ]

    if not face_down_ranks:
        return None

    return min(face_down_ranks)
```

The personal wild rank is stored on `PlayerState.personal_wild_rank` and passed to the evaluator as `wild_ranks: [personal_wild_rank]` on each `evaluate()` call for that player. Each player's `evaluate()` call uses their own `wild_ranks`. This is the only variant where `wild_ranks` differs per player within the same hand.

**High Spade Split:**

The high spade in the hole wins half the pot. Determination is by the actual physical card only. Wild cards do not affect spade split eligibility. A player holding both the high spade in the hole AND the best poker hand wins the entire pot outright (scoops both halves). If no player holds a spade in the hole, the high spade half of the pot carries to the next hand of Chicago.

**TAKE_LAST_CARD_UP in Chicago:**

Before the river card is dealt face-down, each player is offered the TAKE_LAST_CARD_UP action at a cost of $1 (configurable via `house_rules.json chicago.take_last_up_cost`). A player who takes this action receives their river card face-up. Since the river card will not be face-down, it cannot become or displace their personal wild card. This is the primary strategic motivation: protecting the existing wild designation. A player who selects PASS_LAST_CARD_UP receives their river card face-down per normal rules.

**Phase sequence:**
```
SETUP
ANTE
INITIAL_DEAL         (2 down, 1 up per player)
BET_ROUND            (bring-in from lowest face-up card)
DEAL_ROUND           (1 up)
BET_ROUND
DEAL_ROUND           (1 up)
BET_ROUND
DEAL_ROUND           (1 up)
BET_ROUND
TAKE_LAST_UP_OFFER   (each player offered TAKE_LAST_CARD_UP at $1)
DEAL_ROUND           (river: face-down unless TAKE_LAST_CARD_UP taken)
BET_ROUND
SHOWDOWN
POT_DISTRIBUTION
COMPLETE
```

---

#### NightBaseballVariant

**Phase sequence:**
```
SETUP
ANTE
INITIAL_DEAL     (all cards dealt face-down, count per house rules, typically 7)
FLIP_ROUND       (repeating until all players stand)
BET_ROUND        (after each flip round)
SHOWDOWN
POT_DISTRIBUTION
COMPLETE
```

**Wild cards:** 3s and 9s are wild. These are configured as variant_config rather than hardcoded, allowing house rule variation.

**Flip mechanic:** On each FLIP_ROUND, the active player must flip cards from their face-down hand one at a time until their visible hand beats the current high visible hand at the table, or until they have no face-down cards remaining. The player pays to pass if they cannot or choose not to beat the current high hand. Pay-to-pass amount is configured in house_rules.json.

**4 card mechanic:** When a player flips a 4, the escalating buy mechanic is triggered per the Shared Mechanic section above. The player may buy one additional card from the deck at the current table price or pass. Either way `four_card_buy_count` increments.

**Standing:** A player may stand at any point during their flip turn, accepting their current hand. Standing is irrevocable.

**Peek mechanic:** The Deck Layer's `peek()` function is used when a player has a face-down card they are about to flip, allowing the Game Layer to check modifier trigger conditions before the card is officially revealed.

**Price schedule:** Configured in house_rules.json under `night_baseball.four_card_price_schedule`. Default is QUARTER_SCHEDULE.

---

#### JoesBaseballVariant

Joe's Baseball is a stud-style game with a fixed set of wild cards, an escalating 4 card buy mechanic, a special winning hand (natural pair of 7s), and a voluntary last card up action.

**Wild cards:** The following cards are wild in Joe's Baseball. These are table-wide wilds, not personal wilds.

```
2s:               all four 2s are wild
Jacks:            all four Jacks are wild
King of Diamonds: the single King of Diamonds is wild
                  (known as "the man with the axe")
```

The King of Diamonds is a specific card wild rather than a rank wild. It is handled as a special case: the Game Layer passes `wild_cards: [Card(rank=13, suit=DIAMONDS)]` in addition to `wild_ranks: [2, 11]` in variant_config. Other Kings are not wild.

**Natural Pair of Sevens:**

A natural pair of 7s is the best possible hand in Joe's Baseball. It beats all other hands including hands built with wild cards. Full specification in PokerHandEvaluator Requirements v1.3 Amendment.

The Game Layer passes `natural_sevens_active: True` in variant_config when invoking the evaluator for Joe's Baseball hands.

**4 card mechanic:** When a player is dealt a 4 face-up, the escalating buy mechanic is triggered per the Shared Mechanic section above. The player may buy one additional card from the deck at the current table price or pass. Either way `four_card_buy_count` increments.

**Price schedule:** Configured in house_rules.json under `joes_baseball.four_card_price_schedule`. Default is QUARTER_SCHEDULE.

**TAKE_LAST_CARD_UP in Joe's Baseball:**

Before the river card is dealt face-down, each player is offered the TAKE_LAST_CARD_UP action at no cost. The motivation is to expose the card to the DirtyBitchModifier trigger. A player hoping the river card is the Queen of Spades may elect to take it face-up. If the Queen of Spades appears face-up, the DirtyBitchModifier fires per its normal trigger condition.

**Phase sequence:**
```
SETUP
ANTE
INITIAL_DEAL         (2 down, 1 up per player)
BET_ROUND            (bring-in from lowest face-up card)
DEAL_ROUND           (1 up, check for 4s and offer buy)
BET_ROUND
DEAL_ROUND           (1 up, check for 4s and offer buy)
BET_ROUND
DEAL_ROUND           (1 up, check for 4s and offer buy)
BET_ROUND
TAKE_LAST_UP_OFFER   (each player offered TAKE_LAST_CARD_UP, free)
DEAL_ROUND           (river: face-down unless TAKE_LAST_CARD_UP taken)
BET_ROUND
SHOWDOWN
POT_DISTRIBUTION
COMPLETE
```

---

#### ElevatorVariant

**Phase sequence:**
```
SETUP
ANTE
INITIAL_DEAL     (4 down per player)
COMMUNITY_REVEAL (reveal A, bet)
COMMUNITY_REVEAL (reveal B, bet)
COMMUNITY_REVEAL (reveal C, bet)
COMMUNITY_REVEAL (reveal D, bet)
COMMUNITY_REVEAL (reveal E, bet)
COMMUNITY_REVEAL (reveal F, bet)
COMMUNITY_REVEAL (reveal G, the elevator card, bet)
SHOWDOWN
POT_DISTRIBUTION
COMPLETE
```

**Layout:** Seven community cards arranged in a 2x3+1 grid:

```
[A]   [B]
[C][G][D]
[E]   [F]
```

G is the elevator card. It services all three rows simultaneously. Valid floor selections are:

```
Top floor:    A, G, B
Middle floor: C, G, D
Bottom floor: E, G, F
```

If `diagonals_active` is True (dealer's discretion, announced at hand start):

```
Diagonal 1:   A, G, F
Diagonal 2:   B, G, E
```

**Community card use rule:** Each player uses exactly two cards from their four hole cards plus exactly three cards from one valid floor selection. The player selects which floor to use at showdown. The evaluator receives the player's four hole cards plus the three floor cards and finds the best five card hand from the resulting seven cards.

**Flip order:** Cards are revealed in the sequence A, B, C, D, E, F with a betting round after each reveal. G is always revealed last. The betting round after G is the final betting round before showdown.

**Dealer diagonal announcement:** The dealer announces at hand start whether diagonals are active. This is stored in variant_config on the ActiveGameConfig and communicated to all players via the PlayerView.

---

#### PilotVariant

**Phase sequence:**
```
SETUP
ANTE
INITIAL_DEAL     (4 down per player)
COMMUNITY_REVEAL (reveal table card 1, bet, check forced discards)
FORCED_DISCARD   (if triggered)
COMMUNITY_REVEAL (reveal table card 2, bet, check forced discards)
FORCED_DISCARD   (if triggered)
... repeating for all 7 table cards ...
SHOWDOWN
POT_DISTRIBUTION
COMPLETE
```

**Objective:** Players are trying to either keep their highest cards (going high) or discard all of their cards to become the True Pilot (going low, holding no cards at showdown).

**Table cards:** Seven cards are dealt face-down to the center of the table at hand start. They are revealed one at a time with a betting round after each reveal.

**Forced discard rule:** When a table card is revealed, any player whose hole cards contain a card of the same rank must immediately discard that card from their hand. This is mandatory and irrevocable. The discard is public. The player has no choice.

**True Pilot:** A player who has discarded all of their hole cards due to forced discards is the True Pilot. At showdown the True Pilot wins regardless of other hands, provided at least one other player remains with cards. If multiple players achieve True Pilot status, the pot is split among them.

**Showdown evaluation:** Non-True-Pilot players are evaluated normally by the PokerHandEvaluator using their remaining hole cards. True Pilot status takes precedence over all poker hand ranks.

**Forced discard detection:**

```
after each community card reveal in Pilot:
    revealed_rank = community_card.rank
    for player in game_state.players:
        if not player.is_folded:
            matching_cards = [
                c for c in player.hole_cards
                if c.card.rank == revealed_rank
            ]
            for card in matching_cards:
                apply_forced_discard(player, card, game_state)
                record_event(FORCED_DISCARD, player, card)
```

**Strategic note for bot:** The bot must track its own forced discard exposure. A hand with multiple cards of ranks already appearing on the table is high-risk. The bot should factor forced discard probability into its betting decisions.

---

#### AnacondaVariant

**Phase sequence:**
```
SETUP
ANTE
INITIAL_DEAL     (7 down per player)
PASS_ROUND       (each player passes 3 cards left)
BET_ROUND
PASS_ROUND       (each player passes 2 cards left)
BET_ROUND
PASS_ROUND       (each player passes 1 card left)
BET_ROUND
SHOWDOWN
POT_DISTRIBUTION
COMPLETE
```

**Pass mechanic:** All players simultaneously select cards to pass and reveal their selections at the same time. Pass direction is always to the left (next player in seat order). Passed cards are received face-down.

**Card counts:** Players start with 7 cards. After three pass rounds they hold 7 cards again (passed 6, received 6). Best five of seven at showdown.

**Chasing Queens variant:** Chasing Queens is Anaconda with Queens wild. It is implemented as AnacondaVariant with `wild_ranks: [12]` in variant_config.

---

#### AuctionVariant

**Phase sequence:**
```
SETUP
ANTE
INITIAL_DEAL     (1 down per player)
AUCTION_ROUND    (card 1 auctioned face-up, bids go into pot)
AUCTION_ROUND    (card 2 auctioned face-up)
AUCTION_ROUND    (card 3 auctioned face-up)
AUCTION_ROUND    (card 4 auctioned face-up)
AUCTION_ROUND    (card 5 auctioned face-up)
DEAL_ROUND       (1 down per player, the final card)
DECLARE          (high-low chip reveal)
SHOWDOWN
POT_DISTRIBUTION
COMPLETE
```

**Auction mechanic:** One card is revealed from the deck face-up. The dealer offers it to the first player in bid order. That player may bid any amount or pass. If they pass, the next player may bid or pass. If all players pass, the card is discarded and the next card is revealed for auction.

If a player bids, other players may raise the bid in order. Bidding continues until no player raises. The highest bidder pays their bid into the pot and receives the card face-up.

A player may acquire multiple auctioned cards. A player may acquire zero auctioned cards (relying entirely on their hole cards). There is no minimum or maximum number of auctioned cards per player beyond the practical limits of the deck and betting.

**Bid payment:** All bid amounts go directly into the pot. This is the core mechanic: aggressive bidding inflates the pot that all players are competing for.

**Information:** All auctioned cards are face-up and visible to all players. Hole cards remain face-down. The combination of visible auctioned cards and bidding behavior provides significant information about each player's hand direction.

**High-low declare:** Auction is always played as a high-low declare game. The HighLowDeclareModifier is pre-applied as part of the AuctionVariant configuration.

**Showdown evaluation:** Each player's hand consists of their face-down hole cards plus their acquired auctioned cards. The evaluator receives all of these cards and finds the best five card hand.

---

#### GutsVariant

**Phase sequence:**
```
SETUP
ANTE
INITIAL_DEAL     (4 down per player, or configured count)
GUTS_DECLARE     (simultaneous in-or-out declaration)
GUTS_CASCADE     (losers match pot, redeal if cascade continues)
POT_DISTRIBUTION
COMPLETE
```

**Simultaneous declaration:** All players declare in or out simultaneously. Players hold a chip in their fist for in, open hand for out. All reveal together. A player who folds before declaration is treated as out.

**Winner determination:** If exactly one player declares in, that player wins the pot. No showdown required.

If multiple players declare in, all hands are evaluated. The player with the best hand wins the pot. All other players who declared in must match the current pot value (the cascade payment).

**Burn limit:** Each player has an individual burn limit configured in house_rules.json (default $6.00). The `burn_amounts` dict in GutsState tracks cumulative cascade payments per player across all cascade rounds in a session. A player who has reached their burn limit is treated as automatically out for subsequent cascade rounds and may not declare in.

**Cascade:** After cascade payments are collected, a new hand is dealt and the declare round repeats. The pot now contains the original pot plus all cascade payments. This continues until exactly one player declares in or all players declare out.

**All-out scenario:** If all players declare out simultaneously, the pot carries to the next hand of Guts. The ante is re-posted and a new hand is dealt.

**Hand size:** Configured in house_rules.json. Default is 4 cards. Your group has played with up to 10 cards. The evaluator receives however many cards were dealt and finds the best five card hand.

---

#### ScrewYourNeighborVariant

**Phase sequence:**
```
SETUP
ANTE
INITIAL_DEAL     (1 down per player)
SWAP_ROUND       (each player may swap with neighbor, repeating around table)
SHOWDOWN
POT_DISTRIBUTION
COMPLETE
```

**Objective:** Avoid holding the lowest card at showdown. Lowest card holder loses and posts to the pot (or loses a chip from their stack per house rules).

**Swap mechanic:** Starting from the player left of the dealer, each player may swap their card with the player to their left. The player to their left may not refuse unless they hold a King. Kings block the swap. If a swap is blocked by a King, the player who attempted the swap keeps their card.

**The dealer's option:** The dealer, being the last player, may swap their card with the top card of the deck rather than with a neighbor.

**King reveal:** When a King blocks a swap, the King holder reveals their King publicly. This is the only mandatory mid-round card reveal.

**Showdown:** All players reveal their cards simultaneously. The player with the lowest card value loses. Ace is high in this variant, therefore the worst card is a Two (or Null if Nulls are active).

**Ties:** If multiple players share the lowest card value, all tied players lose.

**This variant does not use the PokerHandEvaluator.** Winner determination is by single card rank comparison only. A simplified single-card comparison function handles this rather than the full evaluator stack.

**Note on Screw Your Neighbor and the evaluator registry:** The EVALUATOR_REGISTRY entry for SCREW_YOUR_NEIGHBOR points to a SingleCardEvaluator, a minimal third evaluator implementing BaseEvaluator for single-card rank comparison only. This is simpler to implement correctly than special-casing it inside PokerHandEvaluator.

---

#### CrissCrossVariant

**Phase sequence:**
```
SETUP
ANTE
INITIAL_DEAL     (2 down per player)
COMMUNITY_REVEAL (center card revealed, bet)
COMMUNITY_REVEAL (one arm card revealed, bet)
COMMUNITY_REVEAL (one arm card revealed, bet)
COMMUNITY_REVEAL (one arm card revealed, bet)
COMMUNITY_REVEAL (one arm card revealed, bet)
SHOWDOWN
POT_DISTRIBUTION
COMPLETE
```

**Layout:** Five community cards in a plus-sign pattern:

```
      [N]
[W]   [C]   [E]
      [S]
```

C is the center card. It appears in both the horizontal hand (W-C-E) and the vertical hand (N-C-S).

**Community card use rule:** Each player uses exactly two hole cards plus either the horizontal row (W-C-E) or the vertical column (N-C-S). The player selects their row or column at showdown. The center card C is always included regardless of selection. Players may not mix cards from both arms.

**Reveal order:** The center card C is revealed first. Then the four arm cards are revealed in dealer-chosen order with a betting round after each reveal. Revealing the center card first creates maximum tension since it affects both possible hands.

---

#### RollYourOwnVariant

**Phase sequence:**
```
SETUP
ANTE
INITIAL_DEAL     (all cards dealt face-down per configured count)
FLIP_ROUND       (each player flips one card of their choice, bet)
FLIP_ROUND       (each player flips one card of their choice, bet)
FLIP_ROUND       (each player flips one card of their choice, bet)
FLIP_ROUND       (each player flips one card of their choice, bet)
BET_ROUND        (final bet on remaining face-down cards)
SHOWDOWN
POT_DISTRIBUTION
COMPLETE
```

**Flip mechanic:** On each FLIP_ROUND, each player selects one of their face-down cards to reveal publicly. The player chooses which card to reveal. This is the information management game: reveal strength to build a betting narrative or conceal it to set up a trap.

**Hand count:** Configurable. Typically 7 cards with 4 flip rounds leaving 3 face-down at showdown.

**Showdown:** All remaining face-down cards are revealed. Best five of total cards dealt.

---

#### SixHalfTwentyOneHalfVariant

**Phase sequence:**
```
SETUP
ANTE
INITIAL_DEAL     (1 down per player)
NUMERIC_BET
NUMERIC_DRAW     (each player requests cards or stands, bet after each round)
NUMERIC_BET      (repeating until all players stand)
DECLARE          (high-low chip reveal for 6.5 vs 21.5)
SHOWDOWN
POT_DISTRIBUTION
COMPLETE
```

**Targets:** 6.5 and 21.5. Players declare which target they are going for.

**Card values:**

```
Null:           0
Ace:            1 or 11 (declared at showdown, or dual if declaring both)
2-10:           face value
Jack:           0.5
Queen:          0.5
King:           0.5
```

All internal arithmetic uses integer representation with values multiplied by 2 to avoid floating point errors. See NumericEvaluator Requirements for full specification.

**Draw mechanic:** The dealer goes around the table repeatedly. Each player who has not stood may request one card or stand. Standing is irrevocable. The round ends when all players have stood. There is no maximum card count per player, though going over the highest target (21.5 internal: 43) renders the player bust in both directions.

**Bust handling:** A player whose total exceeds both targets in both directions is bust and is eliminated from the hand. They neither win nor lose the pot for this hand. Their ante is not returned.

**Sleeper cell mechanic:** A player's down card is hidden. Their face-up cards accumulate publicly as they draw. A player who has been standing pat on a low visible total may be concealing a high or low Ace in the hole, changing their total dramatically at the declare reveal.

**Declare:** At showdown, players simultaneously declare LOW (going for 6.5) or HIGH (going for 21.5) or BOTH via the chip mechanic. Players also declare their Ace value at this moment if applicable. Both-ways Ace duality applies per the NumericEvaluator specification.

**Winner determination:** Closest to target without exceeding it wins that direction. Exact hits beat near misses. Both directions are evaluated independently. Scoop-or-bust applies to both-ways declarations.

---

#### SevenTwentySevenVariant

Identical structure to SixHalfTwentyOneHalfVariant with the following differences:

```
Targets:        7 and 27
Card values:
    Null:       0
    Ace:        1 or 11
    2-10:       face value
    Jack:       0.5
    Queen:      0.5
    King:       0.5
```

Internal integer representation multiplies all values by 2 identically to SixHalfTwentyOneHalfVariant.

The variant is a separate state machine entry in the registry but shares the NumericEvaluator. The only variant_config difference is the target values.

---

## Betting Round Management

### Standard Betting Round

A standard betting round proceeds as follows:

1. Identify the first player to act. In stud games this is the bring-in poster or the player showing the best face-up hand depending on the round. In draw games this is the player left of the dealer.
2. Present legal actions to the active player: FOLD, CHECK (if no bet), CALL (if bet exists), RAISE, BET.
3. Apply the player's action and update BettingState.
4. Advance to the next non-folded player.
5. The round ends when all non-folded players have acted and no unmatched bet exists.

### Bring-In Betting

Used in Seven Card Stud for the first betting round:

1. Identify the player showing the lowest face-up card. Ties broken by suit order.
2. That player must post the bring-in amount. This is a forced bet.
3. Subsequent players may call the bring-in, raise to the full small bet, or fold.
4. The bring-in poster may complete to the full small bet if all other players have only called.

### Auction Betting

See AuctionVariant state machine above. Auction rounds replace standard betting rounds entirely during the auction phase. Standard betting rounds do not occur during AUCTION_ROUND phases.

### Guts Declaration

See GutsVariant state machine above. Guts declaration replaces standard betting entirely.

### All-In Handling

When a player bets more than another player's remaining stack, a side pot is created. The all-in player is eligible for the main pot only. Other players continue betting into the side pot. The Pot manager handles side pot creation automatically.

---

## Pot Management

```
PotManager {
    add_ante(player_id: str, amount: int) -> None
    add_bet(player_id: str, amount: int) -> None
    add_bid(player_id: str, amount: int) -> None
    add_buy_payment(player_id: str, amount: int) -> None
    add_take_last_up_payment(player_id: str, amount: int) -> None
    create_side_pot(all_in_player_id: str) -> None
    apply_cascade_payment(player_id: str, amount: int) -> None
    apply_carry(carry_amount: int) -> None
    distribute(winners: dict[str, WinnerResult]) -> dict[str, int]
    get_total() -> int
    get_eligible_players(pot_index: int) -> list[str]
}
```

`distribute()` returns a dict mapping player_id to amount won. This dict is passed to the Persistence Layer to record chip_ledger entries.

---

## Declare Enforcement

The Game Layer enforces the scoop-or-bust rule using DeclareResult from the evaluator.

```
def enforce_declare(
    game_state: GameState,
    declare_results: dict[str, DeclareResult]
) -> dict[str, int]:

    high_winners = determine_winners(high_hands, EvalDirection.HIGH)
    low_winners = determine_winners(low_hands, EvalDirection.LOW)

    for player_id, result in declare_results.items():
        if result.is_both_ways:
            won_high = player_id in high_winners.winners
            won_low = player_id in low_winners.winners
            if not (won_high and won_low):
                disqualify_player(player_id, game_state)

    return pot_manager.distribute(high_winners, low_winners)
```

A disqualified both-ways declarant receives nothing. Their disqualification does not affect the pot available to other players in each direction.

---

## Bot Integration

The Game Layer invokes bot decisions by constructing a PlayerView for the bot player (respecting the visibility system, the bot sees only what a real player would see) and passing it to the active bot tier.

```
def get_bot_action(
    game_state: GameState,
    bot_player_id: str
) -> PlayerAction:

    player_view = get_player_view(game_state, bot_player_id)
    legal_actions = player_view.legal_actions

    if house_rules.bot.use_claude_api:
        action = claude_api_bot.decide(player_view, legal_actions)
    elif house_rules.bot.use_monte_carlo:
        action = monte_carlo_bot.decide(player_view, legal_actions, game_state)
    else:
        action = rule_based_bot.decide(player_view, legal_actions)

    assert action.action_type in [a.action_type for a in legal_actions]
    return action
```

The assertion ensures the bot never submits an illegal action regardless of which tier is active.

**Claude API bot prompt structure:**

The Claude API bot receives a structured natural language prompt including:

- The active variant name and a plain language description of the rules
- The active modifiers and their current state
- The bot's visible hand and its current evaluated strength
- The bot's personal wild rank if in Chicago
- All visible opponent cards and their chip stacks
- The current pot total, four_card_buy_count, and betting state
- The legal actions available
- The bot's chip stack and session history (up or down, by how much)
- A persona instruction: experienced but not unbeatable home game player

The prompt explicitly instructs the Claude API to return a JSON object containing action_type, amount if applicable, and reasoning. The reasoning is stored in the GameEvent metadata and optionally displayed in the UI.

---

## Modifier Integration

The modifier hook is called by the Game Layer after every card deal or reveal. This is the complete integration point between the modifier system and all variant state machines.

```
def run_modifier_checks(
    game_state: GameState,
    newly_revealed_cards: list[Card]
) -> GameState:

    for card in newly_revealed_cards:
        for modifier in game_state.active_game_config.modifiers:
            if modifier.trigger_condition(card, game_state):
                effect = modifier.execute_effect(game_state)
                game_state = apply_modifier_effect(game_state, effect)
                record_event(MODIFIER_FIRED, modifier, card, game_state)
                if not house_rules.modifier_stacking:
                    break

    return game_state
```

`apply_modifier_effect()` handles each EffectType:

```
REDEAL:
    preserve pot per PotInstruction
    reset game_state to SETUP phase
    increment redeal_count
    re-run INITIAL_DEAL

REDEAL_REANTE:
    preserve pot per PotInstruction
    collect antes from all players
    reset game_state to SETUP phase
    increment redeal_count
    re-run INITIAL_DEAL

CHANGE_WILD:
    update wild_ranks or wild_suits in game_state
    notify all players via next PlayerView

NO_OP:
    no state change
    record event for history
```

---

## Persistence Integration

The Game Layer writes to the Persistence Layer at the following moments:

- Hand start: create hands record
- Each GameEvent: append to hand_history (in-memory during hand, flushed to DB at hand end)
- Each chip movement: write chip_ledger record immediately, not deferred
- Hand end: update hands record with ended_at and pot_total, write all hand_players records

Chip ledger records are written immediately on each chip movement rather than deferred to hand end. This ensures the ledger is accurate even if the application crashes mid-hand.

---

## Error Types

```
GameLayer.IllegalActionError
    Raised when a submitted action is not in the legal actions list
    Includes the submitted action and the list of legal actions

GameLayer.InvalidPhaseTransitionError
    Raised when advance_phase() is called in an invalid state
    Includes the current phase and the attempted transition

GameLayer.DeckExhaustionError
    Raised when the Deck Layer raises InsufficientCardsError
    during a deal operation
    Game Layer handles this per variant rules (community card
    for stud, shuffle burned cards back for draw games)
    Only propagates to REST API if no recovery is possible

GameLayer.ModifierEffectError
    Raised when a modifier effect produces an invalid game state
    Includes the modifier, the triggering card, and full game state
    for debugging

GameLayer.BurnLimitExceededError
    Raised when a Guts cascade payment would exceed a player's
    burn limit
    Game Layer catches this and marks the player as automatically
    out rather than propagating to the REST API
```

---

## Unit Test Requirements

The following must be covered before the Game Layer is considered complete.

### Visibility System

- Bot player view never contains face-down cards belonging to other players
- Human player view never contains face-down cards belonging to other players
- Human player view always contains all of their own cards including face-down
- Legal actions list contains only valid actions for the current phase and player
- Legal actions list is empty for folded players
- Legal actions list is empty for players whose turn it is not
- OpponentView never includes personal_wild_rank

### Seven Card Stud

- Bring-in correctly assigned to lowest face-up card
- Bring-in tie broken by suit order
- First bet round index derived from phase sequence, not hardcoded
- 7 cards dealt to each player across all deal rounds
- Deck exhaustion triggers community river card correctly
- Showdown evaluates best five of seven correctly

### Chicago

- Personal wild rank correctly set to lowest face-down card rank on initial deal
- Personal wild rank updates when a lower face-down card is dealt
- Personal wild rank updates when current wild card is revealed face-up
- Two face-down cards of equal lowest rank both wild simultaneously
- Player with no face-down cards has personal_wild_rank of None
- Wild cards correctly passed per-player to evaluator at showdown
- Wild cards do not affect high spade split determination
- Player with high spade and best hand scoops entire pot
- Player with high spade but not best hand wins only the spade half
- No spade in hole causes spade half to carry
- TAKE_LAST_CARD_UP offered before river deal
- Player taking TAKE_LAST_CARD_UP pays configured cost into pot
- River card dealt face-up when TAKE_LAST_CARD_UP taken
- River card dealt face-down when PASS_LAST_CARD_UP selected
- Personal wild rank unaffected by face-up river card

### Night Baseball

- Flip mechanic correctly requires beating current high hand or paying to pass
- Wild cards 3 and 9 correctly passed to evaluator
- Standing is irrevocable
- Player with all cards face-up is automatically standing
- four_card_buy_count increments on 4 flip regardless of buy or pass
- Buy price correct for each position in QUARTER_SCHEDULE
- Buy price correct for each position in DOLLAR_SCHEDULE
- Buy price caps at final schedule entry for all subsequent 4s
- Player buying card receives one additional face-down card from deck
- Buy payment correctly added to pot
- Player passing buy keeps 4 as non-wild card, no additional card received

### Joe's Baseball

- 2s correctly passed as wild to evaluator
- Jacks correctly passed as wild to evaluator
- King of Diamonds correctly passed as wild card to evaluator
- Other Kings not wild
- natural_sevens_active correctly True in variant_config
- Four card buy price escalation identical to Night Baseball
- TAKE_LAST_CARD_UP offered before river deal at no cost
- River card dealt face-up when TAKE_LAST_CARD_UP taken
- DirtyBitchModifier fires correctly when Queen of Spades revealed via TAKE_LAST_CARD_UP

### Elevator

- Community layout correctly represents 2x3+1 grid
- get_valid_selections returns exactly 3 floor options without diagonals
- get_valid_selections returns exactly 5 floor options with diagonals active
- G card is always the last community card revealed
- Showdown correctly evaluates best five from hole cards plus chosen floor

### Pilot

- Forced discard correctly triggers on rank match between table card and hole card
- Forced discard fires for every matching hole card not just the first
- True Pilot status correctly awarded when all hole cards are discarded
- True Pilot beats all non-True-Pilot hands regardless of poker rank
- Multiple True Pilots split the pot

### Anaconda

- Pass direction is always left
- Card counts correct after each pass round (7, 7, 7, 7)
- Simultaneous pass reveal correctly prevents sequential information leakage
- Chasing Queens correctly sets wild_ranks to [12]

### Auction

- All bid amounts correctly added to pot
- Auctioned cards correctly assigned to winning bidder
- Card correctly discarded when all players pass
- High-low declare correctly applied at showdown
- Player with zero auctioned cards evaluated on hole cards only

### Guts

- Simultaneous declaration correctly prevents sequential reveal
- Single in-player wins pot without showdown
- Multiple in-players trigger cascade
- Cascade payment correctly added to pot
- Burn limit correctly prevents player from declaring in after limit reached
- All-out scenario correctly carries pot to next hand

### Screw Your Neighbor

- King correctly blocks swap
- Dealer correctly swaps with deck top card
- Lowest card holder correctly identified at showdown
- Ties correctly shared among all lowest card holders
- Null (rank 0) correctly identified as lowest possible card

### Numeric Variants

- Float-safe arithmetic correctly represents 0.5 face card values
- Bust condition correctly identified when total exceeds both targets
- Sleeper cell down card correctly hidden from opponents
- Declare correctly triggers Ace value selection
- Both-ways Ace duality correctly applied
- Closest-without-going-over correctly determines winner
- Exact hit correctly beats near miss

### Modifier Integration

- DirtyBitchModifier correctly distinguishes pre-action from post-action trigger
- DirtyBitchModifier redeal correctly resets phase to SETUP
- DirtyBitchModifier redeal_count correctly incremented
- FollowTheQueenModifier correctly changes wild rank on Queen reveal
- FollowTheQueenModifier correctly clears wild rank when last card is Queen
- HighLowDeclareModifier correctly activates chip reveal at showdown
- Modifier stacking false correctly fires only first triggered modifier per card
- Modifier stacking true correctly fires all triggered modifiers per card

### Bot

- Bot player view never contains hidden information
- Bot submitted action always in legal actions list
- Claude API bot fallback to Tier 1 on timeout
- Bot burn limit correctly observed in Guts
- Bot personal wild rank available in Chicago PlayerView

### Pot Management

- Side pot correctly created on all-in
- All-in player correctly excluded from side pot
- Cascade payment correctly added to pot in Guts
- Carry amount correctly preserved on redeal
- Re-ante correctly collected on REDEAL_REANTE effect
- distribute() correctly allocates main pot and side pots
- Buy payment correctly added to pot in Night Baseball and Joe's Baseball
- TAKE_LAST_CARD_UP payment correctly added to pot in Chicago
- TAKE_LAST_CARD_UP free in Joe's Baseball, no pot change

---

## Explicitly Out of Scope for Game Layer

- Card rendering or display of any kind
- REST API request and response handling
- Direct database queries, all persistence via PotManager and chip ledger interfaces
- Evaluator implementation details
- Deck shuffling or card construction
- Network or multiplayer concerns
