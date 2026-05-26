# Testing Guide
## Poker Engine: Home Game Edition

---

## Prerequisites

Python 3.11+ and the backend dependencies must be installed before running
any tests. From the project root:

```bash
pip install -r backend/requirements.txt
pip install pytest pytest-cov
```

All test commands below are run from the project root unless noted otherwise.

---

## Running the Full Test Suite

```bash
python -m pytest tests/
```

This runs all tests across all layers. Expect the run to take approximately
25-30 seconds due to the Monte Carlo hand frequency calculation in the
PokerHandEvaluator tests (100,000 sample hands). Everything else is fast.

---

## Running Tests by Layer

### Deck Layer

```bash
python -m pytest tests/deck/
```

Covers Card, Suit, DeckConfig, and Deck. Includes card representation,
deck construction for all three configurations (STANDARD, WITH_NULLS,
WITH_ORBS), deal/burn/peek/reset operations, serialization roundtrips,
and low card warning behavior.

### Evaluation Layer

```bash
python -m pytest tests/evaluators/
```

Covers PokerHandEvaluator. Includes all nine standard hand ranks, Royal
Flush detection, Ace duality, wheel and Broadway straights, best-five
selection from up to ten cards, HIGH and LOW direction comparison,
determine_winners, evaluate_for_declare, partial hand evaluation, hand
frequency Monte Carlo sampling, frequency cache behavior, and the 500ms
performance requirement for ten-card evaluation.

### Game Layer

```bash
python -m pytest tests/game/
```

Covers the Game Layer in four sub-areas:

```bash
python -m pytest tests/game/test_betting.py
```
Bring-in assignment by lowest face-up card, suit tiebreaking order,
folded player exclusion, and betting round completion detection.

```bash
python -m pytest tests/game/test_pot.py
```
Ante and bet contributions, side pot creation on all-in, side pot
eligibility, pot distribution to single winner and tied winners, odd
chip handling, and carry amount inclusion.

```bash
python -m pytest tests/game/test_visibility.py
```
Visibility system invariants: human player sees all own cards including
face-down, human never sees opponents' face-down cards, bot player view
never contains other players' face-down cards, opponent view omits
face-down cards, legal actions empty for folded players.

```bash
python -m pytest tests/game/test_variants/
```
SevenCardStudVariant: initial deal card counts and face-up/face-down
distribution, seven cards dealt across all streets, river card face-down,
deck exhaustion community river fallback, showdown evaluation, tied
showdown, phase sequence structure, and single-player advance behavior.

### Modifier System (Phase 2 Steps 1-2)

```bash
python -m pytest tests/game/test_modifiers.py
```

Covers the GameModifier interface, modifier hook, and HighLowDeclareModifier:

**Step 1 — interface and hook:** EffectType enum values, PotInstruction enum
values, ModifierEffect dataclass fields, GameModifier abstract class (cannot
instantiate, concrete subclass works, trigger_condition and execute_effect
callable), MODIFIER_REGISTRY (is dict, has HIGH_LOW_DECLARE, values are
GameModifier subclasses), apply_modifier_effect (NO_OP records MODIFIER_FIRED
event and returns unchanged state, non-NO_OP raises NotImplementedError with
event still recorded), run_modifier_hook (empty modifiers is no-op, POULET
skipped even with modifier, no new events is no-op, events before snapshot
ignored, non-deal events do not trigger, modifier fires on CARD_DEALT event,
modifier fires on CARD_REVEALED event, never-fire modifier does not call
execute_effect, face-down deal without card object skipped, no-stacking stops
after first fire, stacking allows both modifiers to fire, no-stacking stops
after first matching card per modifier, stacking fires for each matching card,
returns updated state).

**Step 2 — HighLowDeclareModifier:** trigger_condition always False,
execute_effect returns NO_OP with requires_player_action=True,
get_phase_injection returns DECLARE before SHOWDOWN, returns None for
non-SHOWDOWN phases, returns None after declare_done=True, both_ways_requires_scoop
defaults True and is configurable, is a GameModifier subclass.

**Step 2 — Integration (SevenCardStudVariant + HighLowDeclareModifier):**
DECLARE phase injected before SHOWDOWN, not injected when declare_done=True,
legal actions during DECLARE (HIGH/LOW/BOTH for active player, empty for
others), DECLARE_HIGH/LOW/BOTH stored on PlayerState, DECLARATION_MADE event
recorded, active_player_index advances after declaration, is_phase_complete
True when all declared and False when some undeclared, advance_phase from
DECLARE sets declare_done and advances to SHOWDOWN, pot split correctly between
HIGH and LOW declarants, scoop-or-bust: BOTH winner who wins both scoops pot,
scoop-or-bust: BOTH declarant who fails gets nothing (others win their halves),
scoop-or-bust disabled allows partial wins.

### Bot Layer

```bash
python -m pytest tests/bot/
```

Covers RuleBasedBot. Includes personality parameter clamping, action
validity (decide() always returns a legal action type, never returns an
action outside the legal list), strong hand prefers betting, weak hand
prefers fold, check preferred over fold when free, bot view never contains
other players' face-down cards, and bot action always in legal list.

### REST API Layer

```bash
python -m pytest tests/api/
```

Covers Flask REST endpoints, WebSocket handlers, and the GameManager
integration in four sub-areas:

```bash
python -m pytest tests/api/test_session_endpoints.py
```
POST /api/session/start (200 with valid body, player_id assignment, human
not marked as bot, 400 for empty human_players, 400 for missing JSON body,
400 for missing name field, envelope shape, session replacement on restart),
POST /api/session/end (summary returned, 409 when no session),
GET /api/session/current (session state returned, 404 when no session,
hand_in_progress initially false).

```bash
python -m pytest tests/api/test_hand_endpoints.py
```
POST /api/hand/start (401 missing header, 401 unknown player, 200 success,
400 invalid variant, 400 missing variant, 409 hand already in progress,
envelope shape), GET /api/hand/state (401 missing header, 200 player view
shape, information asymmetry — opponent face-down cards never exposed,
409 no hand in progress), POST /api/hand/action (401 missing header, 400
missing action_type, 200 action accepted, 422 illegal action),
GET /api/hand/result (401 missing header, 404 no completed hand).

```bash
python -m pytest tests/api/test_chip_endpoints.py
```
GET /api/chips/balance (401 missing header, 200 with balances dict,
required fields present, positive default stack), GET /api/chips/ledger
(401 missing header, 200 with entries/total/limit/offset, 400 invalid limit,
default pagination values), GET /api/chips/ledger/all (401 missing header,
200 with entries, required entry fields).

```bash
python -m pytest tests/api/test_websocket.py
```
WebSocket connection: known player connects successfully, unknown player
rejected, empty player_id rejected. WebSocket action submission: valid
action does not crash server, invalid action type emits error_event.
Config/reference endpoints: GET /api/config returns 200, GET /api/config/variants
returns variant list, GET /api/config/modifiers returns modifier list,
GET /api/reference/hands returns 10 rankings, GET /api/reference/variant
returns rules summary.

### Persistence Layer

```bash
python -m pytest tests/persistence/
```

Covers the SQLite persistence layer in three sub-areas:

```bash
python -m pytest tests/persistence/test_database.py
```
Database path resolution (POKER_DB_PATH env var override, default path,
Path return type), connection settings (Row factory, WAL journal mode,
foreign key enforcement), parent directory auto-creation, schema
initialization (all five tables created, idempotent on second call, column
names verified, composite primary key on hand_players).

```bash
python -m pytest tests/persistence/test_ledger.py
```
record_chip_movement (row inserted, delta and balance stored, row id
returned), get_player_balance (most recent balance returned, zero when
no entries), get_session_ledger (all rows for session ordered by id),
get_player_ledger (all rows for player across all sessions ordered by id,
excludes other players).

```bash
python -m pytest tests/persistence/test_history.py
```
get_or_create_player (new player created, same id on second call,
distinct ids for distinct names, is_bot flag stored, created_at set),
get_player / list_players (None for unknown, dict with expected keys,
ordered by name), start_session / end_session / get_session /
get_current_session (lifecycle, ended_at set, most recent open session
returned, ignores ended sessions), start_hand / end_hand / get_hand /
update_hand_wild_ranks (lifecycle, pot_total and redeal_count stored,
wild_ranks updated mid-hand), record_hand_player (INSERT OR REPLACE
idempotency, won_high/won_low stored as integers), get_hand_players.

---

## Running a Single Test File

```bash
python -m pytest tests/deck/test_card.py
python -m pytest tests/evaluators/test_poker_hand_evaluator.py
python -m pytest tests/game/test_variants/test_seven_card_stud.py
```

---

## Running a Single Test Class or Test

```bash
python -m pytest tests/deck/test_card.py::TestCard
python -m pytest tests/deck/test_card.py::TestCard::test_null_card_is_null_true
python -m pytest tests/evaluators/test_poker_hand_evaluator.py::TestRoyalFlush
```

---

## Verbose Output

Add `-v` to any command for test-by-test output:

```bash
python -m pytest tests/ -v
python -m pytest tests/game/ -v
```

---

## Stop on First Failure

Add `-x` to stop immediately on the first failing test:

```bash
python -m pytest tests/ -x
```

Combine with `-v` for verbose output on failure:

```bash
python -m pytest tests/ -x -v
```

---

## Run Only Tests Matching a Keyword

```bash
python -m pytest tests/ -k "bring_in"
python -m pytest tests/ -k "royal_flush"
python -m pytest tests/ -k "visibility"
python -m pytest tests/ -k "not frequency"
```

The last example skips the slow Monte Carlo frequency tests when you want
a fast feedback loop during development.

---

## Skip Slow Tests

The Monte Carlo hand frequency tests take the majority of the test suite
runtime. Mark them to skip during rapid iteration:

```bash
python -m pytest tests/ -k "not frequencies and not frequency"
```

This typically reduces the full suite runtime from ~27 seconds to under 2
seconds.

---

## Coverage Report

```bash
python -m pytest tests/ --cov=backend --cov-report=term-missing
```

This shows line-by-line coverage for all backend modules. To generate an
HTML report instead:

```bash
python -m pytest tests/ --cov=backend --cov-report=html
```

The HTML report is written to `htmlcov/` in the project root. Open
`htmlcov/index.html` in a browser to browse coverage by file.

---

## Test Count by Phase

As of Phase 2 Step 2:

```
tests/deck/            81 tests    Card, DeckConfig, Deck
tests/evaluators/      70 tests    PokerHandEvaluator (incl. NATURAL_SEVENS)
tests/game/           118 tests    Betting, Pot, Visibility, SevenCardStud, Modifiers
tests/bot/             10 tests    RuleBasedBot
tests/persistence/     96 tests    Database, Ledger, History
tests/api/             52 tests    Session, Hand, Chip, WebSocket endpoints
Total                 427 tests
```

Note: counts will grow as new phases add evaluators, variants, and layers.

---

## Test File Locations by Phase

Tests mirror the source structure under `tests/`:

```
tests/
    deck/
        test_card.py            Card and Suit
        test_deck.py            Deck operations and serialization
        test_deck_config.py     DeckConfig presets and serialization
    evaluators/
        test_poker_hand_evaluator.py
        test_numeric_evaluator.py       (Phase 5)
        test_single_card_evaluator.py   (Phase 4)
        test_trick_taking_evaluator.py  (Phase 6)
    game/
        test_betting.py
        test_pot.py
        test_visibility.py
        test_modifiers.py               (Phase 2)
        test_variants/
            test_seven_card_stud.py
            test_elevator.py            (Phase 4)
            test_pilot.py               (Phase 4)
            test_anaconda.py            (Phase 4)
            test_auction.py             (Phase 4)
            test_guts.py                (Phase 4)
            test_screw_your_neighbor.py (Phase 4)
            test_numeric_variants.py    (Phase 5)
            test_poulet.py              (Phase 6)
    bot/
        test_rule_based.py
    persistence/
        test_database.py            SQLite connection and schema
        test_ledger.py              chip_ledger operations
        test_history.py             player/session/hand/hand_players CRUD
    api/
        test_session_endpoints.py       (Phase 1 Step 5)
        test_hand_endpoints.py          (Phase 1 Step 5)
        test_chip_endpoints.py          (Phase 1 Step 5)
        test_websocket.py               (Phase 1 Step 5)
```

---

## Common Issues

**ModuleNotFoundError: No module named 'backend'**

Run pytest from the project root, not from inside the `backend/` or
`tests/` directories. The `conftest.py` in the project root adds the
correct path automatically.

```bash
cd /path/to/poker-engine
python -m pytest tests/
```

**Tests take longer than expected**

The hand frequency Monte Carlo tests run 100,000 simulated hands each.
This is expected behavior. Use `-k "not frequenc"` to skip them during
development.

**ImportError related to PokerKit**

PokerKit must be installed. Run:

```bash
pip install -r backend/requirements.txt
```

**Pytest not found**

```bash
pip install pytest
```