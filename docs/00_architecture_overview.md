
# Architecture Overview
## Poker Engine: Home Game Edition
### Version 1.3

---

## Purpose

This document defines the overall architecture of the poker engine. It is the first document handed to any developer or AI coding assistant before any layer-specific requirements documents. It establishes the layered structure, the evaluator family pattern, the modifier system, shared interfaces, the house rules configuration system, and the technology stack. All layer-specific requirements documents are subordinate to and consistent with this document.

---

## Design Goals

- Support a rotating home game with a large and evolving set of variants including both poker hand ranking games, numeric point total games, and trick-taking games
- Handle non-standard deck configurations including a fifth suit (Orbs) and a zero-rank card (Null)
- Support composable game modifiers that layer on top of base variants without combinatorial explosion of variant definitions
- Provide a computer opponent capable of playing all supported variants
- Track chip stacks persistently across sessions
- Run entirely locally with no internet dependency
- Be extensible: adding a new game variant or modifier should not require modifying existing layers
- Be configurable: house rules are stored in a single JSON file and respected throughout the system

---

## Technology Stack

```
Backend:        Python 3.11+
Web Framework:  Flask (synchronous mode, no async)
Database:       SQLite via Python standard library sqlite3
Hand Eval:      PokerKit (wrapped and extended, not used directly)
Frontend:       SvelteKit
Config:         JSON, loaded at startup
Testing:        pytest
```

### Technology Constraints

- No async/await anywhere in the Python backend. The application is single-user, local, and has no concurrent request concern. Synchronous Python is correct and sufficient.
- Flask is run in synchronous mode explicitly. FastAPI is not used.
- SQLite is accessed via the Python standard library only. No ORM.
- PokerKit is used as a library dependency of PokerHandEvaluator only. No other layer imports PokerKit directly.
- The SvelteKit frontend communicates with the Flask backend via a local REST API. The frontend has no direct database access.
- No Node.js backend. SvelteKit is used for the frontend only and compiles to static assets served by Flask.

---

## Layered Architecture

The system is organized into four layers. Each layer communicates only with the layer directly below it. No layer skips a layer to communicate with a non-adjacent layer.

```
+--------------------------------------------------+
|                   UI Layer                       |
|         SvelteKit frontend, browser-based        |
+--------------------------------------------------+
                        |
                        | REST API (local Flask server)
                        |
+--------------------------------------------------+
|                  Game Layer                      |
|  Variant state machines, modifiers, betting,     |
|  pot management, declare enforcement             |
+--------------------------------------------------+
                        |
                        | Python function calls
                        |
+--------------------------------------------------+
|              Evaluation Layer                    |
|   BaseEvaluator interface + evaluator family     |
+--------------------------------------------------+
                        |
                        | Python function calls
                        |
+--------------------------------------------------+
|                  Deck Layer                      |
|       Card representation, deck operations       |
+--------------------------------------------------+
                        |
                        | Python function calls
                        |
+--------------------------------------------------+
|               Persistence Layer                  |
|         SQLite, chip ledger, session history     |
+--------------------------------------------------+
```

### Layer Responsibilities Summary

**Deck Layer**: Card representation, deck construction, deck configuration, shuffle, deal, burn, peek, reset. No knowledge of hand rankings, game variants, modifiers, or players.

**Evaluation Layer**: Hand evaluation, hand comparison, winner determination, hand frequency reporting. Implemented as a family of four evaluators behind a common interface. No knowledge of game variants, modifiers, betting, or players.

**Game Layer**: Game variant state machines, modifier system, betting round management, pot management, community card layout, declare enforcement, player seat management, bot invocation. Selects the correct evaluator and applies active modifiers for the active variant configuration. No knowledge of UI concerns.

**Persistence Layer**: SQLite database, chip ledger, session history, hand history. Accessed only by the Game Layer. No knowledge of evaluation or UI concerns.

**UI Layer**: SvelteKit frontend. Displays game state, accepts player input, renders hand reference card, displays chip ledger. Communicates with Game Layer exclusively via REST API. No direct database access.

---

## Evaluator Family Pattern

The Evaluation Layer is implemented as a family of evaluators sharing a common abstract base class. The Game Layer selects the correct evaluator based on the active game variant via a registry. No other layer is aware of which evaluator is active.

### BaseEvaluator Interface

```
BaseEvaluator (abstract)

    evaluate(
        cards: list[Card],
        deck_config: DeckConfig,
        direction: EvalDirection,
        declaration: Declaration,
        **variant_config
    ) -> BaseEvaluatedHand

    compare(
        hand_a: BaseEvaluatedHand,
        hand_b: BaseEvaluatedHand,
        direction: EvalDirection
    ) -> ComparisonResult

    determine_winners(
        evaluated_hands: dict[str, BaseEvaluatedHand],
        direction: EvalDirection
    ) -> WinnerResult

    evaluate_for_declare(
        cards: list[Card],
        deck_config: DeckConfig,
        declaration: Declaration,
        **variant_config
    ) -> DeclareResult

    ace_dual_value(
        direction: EvalDirection,
        declaration: Declaration
    ) -> AceDualValue

    calculate_hand_frequencies(
        deck_config: DeckConfig,
        **variant_config
    ) -> dict[str, float]
```

### Shared Declare Mechanic

The declare mechanic is identical across all evaluators that support it and is implemented on BaseEvaluator rather than duplicated in each subclass.

**Chip reveal**: Simultaneous. Chip in fist means HIGH. No chip means LOW. Two chips means BOTH.

**Scoop-or-bust rule**: When declaration is BOTH, the player must win or tie both directions independently. If the player wins one direction and loses the other, they receive nothing from either direction. This rule is enforced by the Game Layer using the DeclareResult returned by the evaluator. The evaluator returns the evaluation only and does not distribute the pot.

**Ace duality in both-ways declaration**: Each evaluator subclass implements ace_dual_value() to define how Ace behaves when declaration is BOTH. BaseEvaluator calls ace_dual_value() at the appropriate point during evaluate_for_declare(). Subclasses may not skip this call.

**TrickTakingEvaluator does not use the chip declare mechanic.** Its evaluate_for_declare() is a pass-through. The stay-in or fold declaration in trick-taking games is a Game Layer concern, not an evaluator concern.

### BaseEvaluatedHand Interface

```
BaseEvaluatedHand (abstract)

    is_partial: bool
    deck_config: DeckConfig
    display_name: str
    high_value: int
    low_value: int
```

Each evaluator subclass extends BaseEvaluatedHand with its own fields appropriate to its evaluation paradigm.

### Concrete Evaluator Implementations

**PokerHandEvaluator(BaseEvaluator)**

Handles all variants using standard poker hand rankings. Wraps and extends PokerKit. Full specification in PokerHandEvaluator Requirements v1.2.

```
ace_dual_value() behavior:
    HIGH direction:      Ace is rank 14
    LOW direction:       Ace is rank 1
    BOTH declaration:    Ace is rank 1 for LOW calculation,
                         rank 14 for HIGH calculation simultaneously
    Straight detection:  Ace tried in both positions regardless of direction
```

**NumericEvaluator(BaseEvaluator)**

Handles variants using point total evaluation rather than poker hand rankings. Full specification in NumericEvaluator Requirements v1.0.

```
ace_dual_value() behavior:
    HIGH direction:      Ace is worth 11 points
    LOW direction:       Ace is worth 1 point
    BOTH declaration:    At least one Ace automatically assumes duality,
                         counting as 1 for LOW total and 11 for HIGH total
                         simultaneously. If multiple Aces are present,
                         the duality Ace is whichever produces the best
                         result in both directions simultaneously.
```

**SingleCardEvaluator(BaseEvaluator)**

Handles variants where winner determination is based on single card rank comparison only. Does not use PokerKit. Implements the full BaseEvaluator interface with no-op or simplified behavior for methods that do not apply to single card comparison.

```
ace_dual_value() behavior:
    All directions: Ace is rank 14 (always high)
    Null is rank 0 (always lowest possible card)
```

**TrickTakingEvaluator(BaseEvaluator)**

Handles variants using trick-taking mechanics. Does not use PokerKit. Determines trick winners based on led suit and trump suit. Tracks trick counts. Does not support the high-low chip declare mechanic. Full specification in TrickTakingEvaluator Requirements v1.0.

```
ace_dual_value() behavior:
    All directions:      Ace is rank 14 (always high in trick taking)
    All declarations:    Ace is rank 14
    No duality exists in trick-taking evaluation
```

### Evaluator Registry

The Game Layer maintains a registry mapping each GameVariant to its evaluator class. The registry is the single authoritative source of which evaluator handles which game. Modifiers are not registered here. They are applied by the Game Layer on top of the base variant after evaluator selection.

```
EVALUATOR_REGISTRY = {
    GameVariant.SEVEN_CARD_STUD:            PokerHandEvaluator,
    GameVariant.FIVE_CARD_DRAW:             PokerHandEvaluator,
    GameVariant.CHICAGO:                    PokerHandEvaluator,
    GameVariant.LOW_CHICAGO:                PokerHandEvaluator,
    GameVariant.NIGHT_BASEBALL:             PokerHandEvaluator,
    GameVariant.JOES_BASEBALL:              PokerHandEvaluator,
    GameVariant.ELEVATOR:                   PokerHandEvaluator,
    GameVariant.PILOT:                      PokerHandEvaluator,
    GameVariant.ANACONDA:                   PokerHandEvaluator,
    GameVariant.CHASING_QUEENS:             PokerHandEvaluator,
    GameVariant.AUCTION:                    PokerHandEvaluator,
    GameVariant.GUTS:                       PokerHandEvaluator,
    GameVariant.SCREW_YOUR_NEIGHBOR:        SingleCardEvaluator,
    GameVariant.CRISS_CROSS:               PokerHandEvaluator,
    GameVariant.ROLL_YOUR_OWN:             PokerHandEvaluator,
    GameVariant.SIX_HALF_TWENTYONE_HALF:   NumericEvaluator,
    GameVariant.SEVEN_TWENTYSEVEN:          NumericEvaluator,
    GameVariant.POULET:                     TrickTakingEvaluator,
}
```

Note that Follow the Queen is not a standalone GameVariant. It is Seven Card Stud with the FOLLOW_THE_QUEEN modifier applied. See the Modifier System section below.

Adding a new game variant requires adding one entry to this registry and implementing the variant's state machine in the Game Layer. No other change is required unless the new variant introduces a fifth evaluation paradigm, in which case a new evaluator subclass is also added.

---

## Modifier System

### Purpose

Modifiers are composable rules that layer on top of base variants without requiring new variant definitions. Without a modifier system, combining rules produces combinatorial explosion:

```
Without modifiers:
    DIRTY_BITCH_CHICAGO
    DIRTY_BITCH_FOLLOW_THE_QUEEN
    DIRTY_BITCH_FOLLOW_THE_QUEEN_HIGH_LOW
    FOLLOW_THE_QUEEN_HIGH_LOW
    ... and so on indefinitely

With modifiers:
    CHICAGO + [DIRTY_BITCH]
    SEVEN_CARD_STUD + [FOLLOW_THE_QUEEN]
    SEVEN_CARD_STUD + [FOLLOW_THE_QUEEN, HIGH_LOW_DECLARE]
    CHICAGO + [DIRTY_BITCH, HIGH_LOW_DECLARE]
```

The dealer picks a base variant and toggles modifiers, exactly as at the physical table.

### Active Game Configuration

The active game is represented as a configuration object rather than a flat enum:

```
ActiveGameConfig {
    variant: GameVariant
    modifiers: list[GameModifier]
    deck_config: DeckConfig
    variant_config: dict
}
```

The Game Layer constructs an ActiveGameConfig at the start of each hand based on the dealer's selection and the active house rules.

### GameModifier Interface

```
GameModifier (abstract)

    trigger_condition(
        card: Card,
        game_state: GameState
    ) -> bool

    execute_effect(
        game_state: GameState
    ) -> ModifierEffect
```

### ModifierEffect Object

```
ModifierEffect {
    effect_type: EffectType
    requires_player_action: bool
    pot_instruction: PotInstruction
    message: str
}
```

### EffectType Enumeration

```
EffectType {
    REDEAL
    REDEAL_REANTE
    CHANGE_WILD
    NO_OP
}
```

### PotInstruction Enumeration

```
PotInstruction {
    CARRY
    SPLIT
    REANTE_ON_TOP
    DISCARD
}
```

### Modifier Hook in Game Layer State Machine

The Game Layer state machine checks active modifiers after every card deal or reveal event. This is the single integration point between the modifier system and the base variant state machine:

```
after each card deal or reveal:
    for modifier in active_game_config.modifiers:
        if modifier.trigger_condition(card, game_state):
            effect = modifier.execute_effect(game_state)
            game_layer.apply_effect(effect)
            break
```

The break after the first fired modifier prevents multiple modifiers from firing on the same card event. If future house rules require multiple modifiers to fire on the same event, this behavior is configurable via a modifier_stacking boolean in house_rules.json. Default is False.

**Note on modifiers and Poulet:** The modifier system is not applied to Poulet in the current implementation. Poulet does not support Dirty Bitch, Follow the Queen, or High-Low Declare. The modifier hook is bypassed for GameVariant.POULET. Future modifier support for trick-taking variants is possible but requires explicit specification.

### Concrete Modifier Implementations

**DirtyBitchModifier(GameModifier)**

Trigger condition: Queen of Spades is dealt or revealed at any point during the hand.

```
Pre-action trigger (Queen appears before any betting has occurred):
    effect_type: REDEAL_REANTE
    pot_instruction: REANTE_ON_TOP
    message: "Dirty Bitch! Queen of Spades before action. Re-ante and redeal."

Post-action trigger (Queen appears after any betting has occurred):
    effect_type: REDEAL
    pot_instruction: CARRY
    message: "Dirty Bitch! Queen of Spades mid-hand. Pot carries, redeal."
```

**FollowTheQueenModifier(GameModifier)**

Trigger condition: A Queen is dealt face up during a stud-style dealing round.

```
Effect:
    effect_type: CHANGE_WILD
    The card rank dealt immediately after the Queen becomes the new wild rank
    If a second Queen is dealt face up, the wild rank changes again
    If the last card dealt in a round is a Queen, there are no wilds
    requires_player_action: False
    message: "Queen up. [Next card rank] are now wild."
```

**HighLowDeclareModifier(GameModifier)**

Trigger condition: Showdown phase begins.

```
Effect:
    effect_type: NO_OP at card level
    Activates the declare mechanic at showdown
    Adds chip reveal step before winner determination
    Enforces scoop-or-bust rule via DeclareResult
    requires_player_action: True
    message: "Declare high, low, or both."
```

### Modifier Registry

```
MODIFIER_REGISTRY = {
    "DIRTY_BITCH":          DirtyBitchModifier,
    "FOLLOW_THE_QUEEN":     FollowTheQueenModifier,
    "HIGH_LOW_DECLARE":     HighLowDeclareModifier,
}
```

### Modifier Configuration in House Rules

```json
"modifiers": {
    "dirty_bitch": {
        "enabled": false,
        "trigger_card": {"rank": 12, "suit": "SPADES"},
        "pre_action_pot_instruction": "REANTE_ON_TOP",
        "post_action_pot_instruction": "CARRY"
    },
    "follow_the_queen": {
        "enabled": false
    },
    "high_low_declare": {
        "enabled": false,
        "both_ways_requires_scoop": true
    },
    "modifier_stacking": false
}
```

---

## House Rules Configuration

All house rules are stored in a single JSON file. The file is loaded at startup. Changes to the file require a restart to take effect. Per-hand modifier selections are made via the UI and do not modify the house rules file.

### Default Location

```
~/.config/poker_engine/house_rules.json
```

### Override via Environment Variable

```
POKER_CONFIG_PATH=/path/to/custom/house_rules.json
```

### Configuration Structure

```json
{
    "deck": {
        "default_config": "STANDARD",
        "player_count_thresholds": {
            "standard_max": 6,
            "nulls_max": 7,
            "orbs_max": 9
        },
        "null_rules": {
            "nulls_match_each_other": false,
            "wilds_can_become_null": true,
            "null_exists_in_orbs": false
        },
        "low_card_warning_threshold": 10
    },
    "evaluation": {
        "royal_flush_beats_straight_flush": false,
        "hand_frequency_sample_size": 100000
    },
    "declare": {
        "both_ways_requires_scoop": true
    },
    "guts": {
        "burn_limit_per_player": 6.00,
        "currency_unit": "dollars"
    },
    "poulet": {
        "win_threshold": 3,
        "total_tricks": 5,
        "burn_limit_per_player": 6.00,
        "currency_unit": "dollars",
        "all_fold_carries_pot": true
    },
    "chips": {
        "default_starting_stack": 100,
        "currency_label": "chips"
    },
    "bot": {
        "count": 5,
        "aggression": 0.5,
        "bluff_frequency": 0.15,
        "risk_tolerance": 0.5,
        "use_monte_carlo": false,
        "use_claude_api": false,
        "claude_model": "claude-sonnet-4-20250514",
        "claude_api_timeout_seconds": 5
    },
    "modifiers": {
        "dirty_bitch": {
            "enabled": false,
            "trigger_card": {"rank": 12, "suit": "SPADES"},
            "pre_action_pot_instruction": "REANTE_ON_TOP",
            "post_action_pot_instruction": "CARRY"
        },
        "follow_the_queen": {
            "enabled": false
        },
        "high_low_declare": {
            "enabled": false,
            "both_ways_requires_scoop": true
        },
        "modifier_stacking": false
    },
    "variants": {
        "enabled": [
            "SEVEN_CARD_STUD",
            "FIVE_CARD_DRAW",
            "CHICAGO",
            "LOW_CHICAGO",
            "NIGHT_BASEBALL",
            "JOES_BASEBALL",
            "ELEVATOR",
            "PILOT",
            "ANACONDA",
            "CHASING_QUEENS",
            "AUCTION",
            "GUTS",
            "SCREW_YOUR_NEIGHBOR",
            "CRISS_CROSS",
            "ROLL_YOUR_OWN",
            "SIX_HALF_TWENTYONE_HALF",
            "SEVEN_TWENTYSEVEN",
            "POULET"
        ]
    }
}
```

### Configuration Validation

On startup the application validates the house rules JSON against a schema. Invalid configuration raises a HouseRulesConfigurationError with a descriptive message before the application starts. The application does not start with an invalid configuration.

---

## Persistence Layer

### Database

SQLite database stored at:

```
~/.local/share/poker_engine/poker.db
```

Override via environment variable:

```
POKER_DB_PATH=/path/to/custom/poker.db
```

### Schema Overview

```
players
    id              INTEGER PRIMARY KEY
    name            TEXT NOT NULL
    is_bot          BOOLEAN NOT NULL
    created_at      DATETIME NOT NULL

sessions
    id              INTEGER PRIMARY KEY
    started_at      DATETIME NOT NULL
    ended_at        DATETIME
    deck_config     TEXT NOT NULL
    notes           TEXT

hands
    id              INTEGER PRIMARY KEY
    session_id      INTEGER REFERENCES sessions(id)
    variant         TEXT NOT NULL
    modifiers       TEXT NOT NULL
    dealer_id       INTEGER REFERENCES players(id)
    started_at      DATETIME NOT NULL
    ended_at        DATETIME
    pot_total       INTEGER NOT NULL DEFAULT 0
    deck_config     TEXT NOT NULL
    wild_ranks      TEXT
    redeal_count    INTEGER NOT NULL DEFAULT 0

chip_ledger
    id              INTEGER PRIMARY KEY
    player_id       INTEGER REFERENCES players(id)
    hand_id         INTEGER REFERENCES hands(id)
    session_id      INTEGER REFERENCES sessions(id)
    delta           INTEGER NOT NULL
    balance         INTEGER NOT NULL
    reason          TEXT NOT NULL
    recorded_at     DATETIME NOT NULL

hand_players
    hand_id         INTEGER REFERENCES hands(id)
    player_id       INTEGER REFERENCES players(id)
    starting_stack  INTEGER NOT NULL
    ending_stack    INTEGER NOT NULL
    declaration     TEXT
    cards_dealt     TEXT
    best_hand       TEXT
    won_high        BOOLEAN
    won_low         BOOLEAN
```

### Chip Ledger

Every chip movement is recorded as a row in chip_ledger with a reason field describing why the movement occurred. This provides a complete audit trail across sessions. The balance field is the player's running total after the delta is applied, enabling point-in-time balance reconstruction without summing the entire ledger.

The chip ledger is the source of truth for whether a player is up or down over time, which is the primary tracking goal stated at the outset of this project.

---

## Bot Architecture

The bot system is configured via house_rules.json and operates as a component of the Game Layer. The bot receives the same visible game state a human player would see. It does not receive hidden information.

### Tier 1: Rule-Based Bot (Default)

Available immediately. For poker hand variants, configured via aggression, bluff_frequency, and risk_tolerance. For trick-taking variants, uses hand_strength_estimate from TrickTakingEvaluator with aggression applied to the stay-in threshold.

### Tier 2: Monte Carlo Bot (Optional Upgrade)

Replaces Tier 1 decision making. For trick-taking variants, simulates full trick play against randomly dealt opponent hands. Activated by setting use_monte_carlo: true in house_rules.json.

### Tier 3: Claude API Bot (Optional)

When use_claude_api is true in house_rules.json, the bot decision function sends the current visible game state as a structured prompt to the Claude API and receives a decision with reasoning. For Poulet, the prompt includes the five hole cards, trump suit, player count, and declarations made so far. The reasoning is optionally displayed in the UI.

API calls are made synchronously with a configurable timeout defaulting to 5 seconds. If the API call times out or fails, the bot falls back to Tier 1 behavior for that decision.

---

## REST API Surface

The Flask backend exposes the following endpoint groups to the SvelteKit frontend. Full endpoint specifications are in the REST API Layer Requirements document.

```
/api/session
    POST    /start
    POST    /end
    GET     /current

/api/hand
    POST    /start
    GET     /state
    POST    /action
    GET     /result

/api/chips
    GET     /ledger
    GET     /ledger/all
    GET     /balance

/api/reference
    GET     /hands
    GET     /variant

/api/config
    GET     /
    POST    /
    GET     /variants
    GET     /modifiers
```

---

## Build Order

The recommended implementation sequence minimizes rework and produces a playable result as early as possible.

```
Phase 1: Foundation
    1.  Deck Layer, STANDARD config only
    2.  PokerHandEvaluator, standard 52 card evaluation, no wilds, no Nulls
    3.  Game Layer, Seven Card Stud only, no modifiers
    4.  Tier 1 bot
    5.  Persistence Layer, chip ledger and session tracking
    6.  Flask REST API, hand and chip endpoints only
    7.  SvelteKit frontend, minimal table UI

    Milestone: playable Seven Card Stud against bot opponents
    with chip tracking across sessions

Phase 2: Modifier System
    8.  GameModifier interface and modifier hook in Game Layer
    9.  HighLowDeclareModifier
    10. FollowTheQueenModifier
    11. DirtyBitchModifier
    12. Modifier selection in UI at hand start

    Milestone: Seven Card Stud playable with any combination
    of the three core modifiers

Phase 3: Deck Extensions
    13. Deck Layer, WITH_NULLS config
    14. PokerHandEvaluator, Null card evaluation rules
    15. Deck Layer, WITH_ORBS config
    16. PokerHandEvaluator, Orbs awareness
    17. PokerHandEvaluator, wild card resolution

    Milestone: playable Baseball variants with wilds,
    Nulls, and Orbs in correct deck configurations

Phase 4: Variant Expansion
    18. Game Layer variants, one at a time in order of complexity:
        a.  Five Card Draw
        b.  Chicago and Low Chicago
        c.  Night Baseball and Joe's Baseball
        d.  Guts with burn limit and cascade logic
        e.  Criss-Cross and Roll Your Own
        f.  Elevator
        g.  Pilot
        h.  Anaconda and Chasing Queens
        i.  Auction
        j.  Screw Your Neighbor
            (includes SingleCardEvaluator implementation)

    Milestone: full poker variant rotation playable

Phase 5: Numeric Variants
    19. NumericEvaluator
    20. Game Layer variants for Seven/Twenty-Seven
        and Six-and-a-Half/Twenty-one-and-a-Half

    Milestone: full numeric game rotation playable

Phase 6: Trick-Taking Variants
    21. TrickTakingEvaluator
    22. PouletVariant state machine
    23. Follow suit enforcement in Game Layer
    24. Trump reveal UI component in SvelteKit
    25. Stay-in declaration UI component

    Milestone: Poulet playable

Phase 7: Polish
    26. Hand reference card in UI with frequency adjustment
    27. Tier 2 Monte Carlo bot
    28. Claude API bot, optional
    29. UI polish, SvelteKit table aesthetics
    30. Configuration UI in frontend
    31. Session history and statistics view
```

---

## Error Handling Philosophy

- All errors are typed and namespaced to their layer of origin
- No layer swallows exceptions silently
- The Game Layer is the last line of defense before the REST API boundary
- The REST API translates exceptions to appropriate HTTP error responses
- The frontend displays error states clearly without exposing stack traces
- Configuration errors fail loudly at startup rather than silently at runtime
- Modifier effects that produce invalid game states raise ModifierEffectError

---

## Explicitly Out of Scope for This Project

- Real money transactions of any kind
- Network multiplayer across machines
- Mobile native applications
- Account systems or authentication
- Online poker site integration
- Any feature requiring internet connectivity during play

---