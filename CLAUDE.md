# CLAUDE.md
## Poker Engine: Home Game Edition

---

## What This Project Is

A local poker practice and home game engine supporting approximately
20 game variants with non-standard deck configurations including a
fifth suit (Orbs, symbol ✦) and a zero-rank card (Null, rank 0).
The engine tracks chip stacks persistently across sessions, supports
a configurable bot opponent system with three tiers of intelligence,
and is designed to be run locally or deployed as a Docker container
for remote play with friends.

This is not an online gambling platform. There is no real money
involved. The chip ledger tracks play money only.

Full specification is in the docs/ folder. Read all documents before
writing any code.

---

## Read These Documents First, In Order

Before writing any code, read all requirements documents in this
exact order. The Architecture Overview is the authority. All other
documents are subordinate to it.

```
1. docs/00_architecture_overview.md
   The north star. Defines layer structure, evaluator family pattern,
   modifier system, technology stack, house rules config, and build
   order. Read this first. Read it completely.

2. docs/01_deck_layer.md
   Card representation, deck construction, Null cards, Orbs suit,
   DeckConfig, and all physical deck operations.

3. docs/02_poker_hand_evaluator.md
   PokerHandEvaluator implementing BaseEvaluator. Hand rankings,
   wild card resolution, Null semantics, Orbs awareness, Ace duality,
   five of a kind, best hand selection from n cards.

4. docs/03_numeric_evaluator.md
   NumericEvaluator implementing BaseEvaluator. Point total games,
   float-safe arithmetic, Ace as 1 or 11, face cards as 0.5, target
   comparison, bust detection, both-ways Ace duality.

5. docs/04_trick_taking_evaluator.md
   TrickTakingEvaluator implementing BaseEvaluator. Trump suit and
   led suit mechanics, trick winner determination, trick count
   tracking, hand strength estimation for stay-in decisions.
   No PokerKit dependency. No high-low declare support.

6. docs/05_game_layer.md
   All variant state machines including Poulet, modifier system
   integration, betting round management, community card layouts,
   pot management, declare enforcement, visibility system,
   bot integration, follow suit enforcement.

7. docs/06_rest_api_layer.md
   Flask REST API, WebSocket architecture via Flask-SocketIO, response
   envelope, error codes, identity model, Docker support.

8. docs/07_ui_layer.md
   SvelteKit frontend, Svelte stores, WebSocket client, all views
   and components, visual design principles including trump reveal
   and stay-in declaration UI for Poulet.
```

---

## Build Order

Follow the phased build order defined in docs/00_architecture_overview.md
exactly. The phases are:

```
Phase 1: Foundation (start here)
Phase 2: Modifier System
Phase 3: Deck Extensions
Phase 4: Variant Expansion
Phase 5: Numeric Variants
Phase 6: Trick-Taking Variants
Phase 7: Polish
```

Do not begin a phase until the previous phase is complete and all
unit tests for that phase pass. Do not skip steps within a phase.
Do not implement features from a later phase while working on an
earlier one.

When given a task, implement exactly that task and its associated
unit tests. Stop and report completion. Wait for confirmation before
proceeding to the next step.

---

## Technology Stack (Non-Negotiable)

```
Backend language:   Python 3.11+
Web framework:      Flask, synchronous mode only
WebSocket:          Flask-SocketIO, synchronous mode with eventlet
Database:           SQLite via Python standard library sqlite3
Hand evaluation:    PokerKit (PokerHandEvaluator only, nowhere else)
Frontend:           SvelteKit
Styling:            Tailwind CSS
Testing:            pytest
```

### Hard Constraints

- No async/await anywhere in the Python backend. This constraint
  is absolute. The application is single-user and local. Synchronous
  Python is correct and sufficient. If you find yourself reaching for
  async, stop and find a synchronous solution.

- No async/await. Stated twice intentionally.

- Flask in synchronous mode only. FastAPI is not used. Do not suggest
  FastAPI as an alternative.

- SQLite via standard library sqlite3 only. No SQLAlchemy. No other
  ORM. No other database library.

- PokerKit is imported only inside backend/evaluators/poker_hand_evaluator.py.
  No other file imports PokerKit directly. The Deck Layer does not
  use PokerKit. The Game Layer does not use PokerKit. The API does
  not use PokerKit.

- SvelteKit for the frontend only. No React. No Vue. No other
  frontend framework.

- No TypeScript requirement but strongly encouraged for type safety
  in the frontend stores and API client.

---

## Project Structure

```
poker-engine/
    CLAUDE.md                       this file
    docs/
        00_architecture_overview.md
        01_deck_layer.md
        02_poker_hand_evaluator.md
        03_numeric_evaluator.md
        04_trick_taking_evaluator.md
        05_game_layer.md
        06_rest_api_layer.md
        07_ui_layer.md
    backend/
        requirements.txt
        app.py                      Flask application entry point
        config.py                   house rules loader and validator
        deck/
            __init__.py
            card.py                 Card, Suit, DeckConfig
            deck.py                 Deck
        evaluators/
            __init__.py
            base.py                 BaseEvaluator, BaseEvaluatedHand
            poker_hand_evaluator.py PokerHandEvaluator
            numeric_evaluator.py    NumericEvaluator
            single_card_evaluator.py SingleCardEvaluator
            trick_taking_evaluator.py TrickTakingEvaluator
        game/
            __init__.py
            state.py                GameState and all core data structures
            visibility.py           Visibility system, PlayerView
            pot.py                  PotManager
            betting.py              Betting round management
            modifiers/
                __init__.py
                base.py             GameModifier interface
                dirty_bitch.py      DirtyBitchModifier
                follow_the_queen.py FollowTheQueenModifier
                high_low_declare.py HighLowDeclareModifier
            variants/
                __init__.py
                base.py             BaseVariant interface
                seven_card_stud.py
                five_card_draw.py
                chicago.py
                night_baseball.py
                joes_baseball.py
                elevator.py
                pilot.py
                anaconda.py
                auction.py
                guts.py
                screw_your_neighbor.py
                criss_cross.py
                roll_your_own.py
                six_half_twentyone_half.py
                seven_twentyseven.py
                poulet.py
            bot/
                __init__.py
                rule_based.py       Tier 1 bot
                monte_carlo.py      Tier 2 bot
                claude_api.py       Tier 3 bot
        api/
            __init__.py
            routes/
                session.py
                hand.py
                chips.py
                reference.py
                config.py
            validators.py
            serializers.py
            errors.py
        persistence/
            __init__.py
            database.py             SQLite connection and schema
            ledger.py               chip_ledger operations
            history.py              hand history operations
    frontend/
        src/
            lib/
                api/
                    rest.js
                    socket.js
                stores/
                    session.js
                    hand.js
                    chips.js
                    reference.js
                components/
                    (per docs/06_ui_layer.md)
            routes/
                +page.svelte
                session/+page.svelte
                chips/+page.svelte
                reference/+page.svelte
        package.json
        svelte.config.js
        vite.config.js
        tailwind.config.js
    config/
        house_rules.json            house rules configuration
    data/                           SQLite database (gitignored)
    tests/
        deck/
            test_card.py
            test_deck.py
            test_deck_config.py
        evaluators/
            test_poker_hand_evaluator.py
            test_numeric_evaluator.py
            test_single_card_evaluator.py
            test_trick_taking_evaluator.py
        game/
            test_visibility.py
            test_pot.py
            test_betting.py
            test_modifiers.py
            test_variants/
                test_seven_card_stud.py
                test_elevator.py
                test_pilot.py
                test_anaconda.py
                test_auction.py
                test_guts.py
                test_screw_your_neighbor.py
                test_numeric_variants.py
                test_poulet.py
        api/
            test_session_endpoints.py
            test_hand_endpoints.py
            test_chip_endpoints.py
            test_websocket.py
    Dockerfile
    docker-compose.yml
    .env.local
    .env.container
    .gitignore
    README.md
```

---

## Code Style

- Full type hints on all Python functions, methods, and class attributes
- Docstrings on all public classes and methods
- No commented-out code in committed files
- No print() statements for debugging. Use the Python logging module.
  Configure logging level via environment variable POKER_LOG_LEVEL,
  default INFO.
- All exceptions typed and namespaced to their layer of origin
  (e.g. DeckLayer.InsufficientCardsError, not just InsufficientCardsError)
- Tests in tests/ directory mirroring the backend/ source structure
- One class per file where practical
- No circular imports between layers

---

## Configuration

All configurable values live in config/house_rules.json. Do not
hardcode any value that appears or could appear in house_rules.json.

The config is loaded once at startup by backend/config.py and
validated against the schema defined in that module. The application
does not start with an invalid configuration. Invalid configuration
raises HouseRulesConfigurationError with a descriptive message.

Config file location is overridable via environment variable:

```
POKER_CONFIG_PATH=/path/to/house_rules.json
```

Default: ~/.config/poker_engine/house_rules.json
Fallback: config/house_rules.json in the project root

---

## Environment Variables

All environment variables are documented in .env.local (local mode)
and .env.container (container mode). Never hardcode values that
belong in environment variables.

```
POKER_ENV               local or container
POKER_HOST              binding host, 127.0.0.1 or 0.0.0.0
POKER_PORT              default 5000
POKER_CONFIG_PATH       path to house_rules.json
POKER_DB_PATH           path to poker.db
POKER_LOG_LEVEL         DEBUG, INFO, WARNING, ERROR
POKER_CORS_ORIGINS      comma-separated allowed origins
```

---

## Layer Boundaries (Never Violate These)

```
UI Layer
    communicates with: Game Layer via REST API and WebSocket only
    never: direct database access
    never: game logic of any kind

REST API Layer
    communicates with: Game Layer (Python function calls)
    never: direct database access
    never: evaluation logic
    never: deck operations

Game Layer
    communicates with: Evaluation Layer (Python function calls)
                       Deck Layer (Python function calls)
                       Persistence Layer (Python function calls)
    never: UI concerns
    never: HTTP or WebSocket concerns

Evaluation Layer
    communicates with: Deck Layer (Python function calls)
    never: game variant logic
    never: betting logic
    never: player tracking

Deck Layer
    communicates with: nothing below it
    never: hand rankings
    never: game variants
    never: players

Persistence Layer
    communicates with: SQLite only
    never: evaluation
    never: game logic
    never: UI concerns
```

---

## Things That Must Never Happen

- Hole cards belonging to Player A appear in Player B's API response
  or WebSocket emission under any circumstances
- Float arithmetic inside NumericEvaluator. Internal values are
  always integers. Display values are derived only for output.
- PokerKit imported outside of poker_hand_evaluator.py
- async/await in any Python file
- Game logic in the REST API layer
- Evaluation logic in the Game Layer
- Direct SQLite queries outside the Persistence Layer
- A layer communicating with a non-adjacent layer
- Configuration values hardcoded in source files
- The bot receiving hidden information (hole cards of other players)

---

## Key Domain Concepts

Read the full specifications in the docs. These are quick reminders
only, not complete definitions.

**Null card**: Rank 0. Below all standard ranks including low Ace.
Has a suit. Contributes to flushes. Can anchor straights. Whether
two Nulls form a pair is controlled by nulls_match_each_other in
house_rules.json. Default: False.

**Orbs suit**: Fifth suit, symbol ✦. First-class suit. Participates
in flushes and straight flushes identically to standard suits. Active
when include_orbs is True in DeckConfig. Deck has 65 cards with Orbs.

**Wild cards**: Two kinds. Intrinsic wilds (the card itself is wild,
set on Card.is_intrinsic_wild). Game-conferred wilds (a rank or suit
is wild due to the active variant rules, passed as wild_ranks or
wild_suits to the evaluator). Never bake game-conferred wildness
into the Card object.

**Modifiers**: Composable rules layered on top of base variants.
Follow the Queen, Dirty Bitch, and High-Low Declare are modifiers,
not standalone variants. See docs/00_architecture_overview.md.

**Deck configurations**:
- STANDARD: 52 cards, 5-6 players
- WITH_NULLS: 56 cards (52 + 4 Nulls), 7 players
- WITH_ORBS: 65 cards (52 + 13 Orbs), 8-9 players

**Evaluator selection**: The Game Layer selects the correct evaluator
via EVALUATOR_REGISTRY based on the active GameVariant. See
docs/00_architecture_overview.md for the full registry.

**TrickTakingEvaluator**: Used for Poulet. Determines trick winners
based on led suit and trump suit. Ace is always rank 14 (always high).
No high-low declare support. No PokerKit dependency. Trump suit beats
all non-trump suits regardless of rank. Follow suit is enforced by
the Game Layer, not the evaluator.

**Poulet**: A trick-taking game. Five cards dealt, one card flipped
to reveal trump suit, players declare in or out sequentially, then
play tricks. First to win three tricks wins the pot. Zero-trick
players match the pot up to the $6 burn limit. No player winning
three tricks triggers a redeal with pot carry. Modifiers do not
apply to Poulet.

**Scoop-or-bust**: When a player declares BOTH in a high-low game,
they must win both directions outright or they receive nothing.
Enforced by the Game Layer using DeclareResult from the evaluator.

---

## When In Doubt

1. Re-read docs/00_architecture_overview.md
2. The Architecture Overview is the authority
3. If a requirements document seems to conflict with the Architecture
   Overview, stop, flag the conflict, and ask before resolving it
4. Do not resolve ambiguity silently with an assumption
5. Do not implement features not specified in the requirements
   documents without asking first

---

## Starting Point

Begin with Phase 1, Step 1: the Deck Layer.

Read docs/01_deck_layer.md completely before writing any code.
Implement backend/deck/card.py, backend/deck/deck.py, and
backend/config.py (DeckConfig only) per that specification.
Write all unit tests specified in the Deck Layer document in
tests/deck/.

Report completion and test results. Wait for confirmation before
proceeding to Phase 1, Step 2.