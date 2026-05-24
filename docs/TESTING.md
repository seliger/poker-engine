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

### Bot Layer

```bash
python -m pytest tests/bot/
```

Covers RuleBasedBot. Includes personality parameter clamping, action
validity (decide() always returns a legal action type, never returns an
action outside the legal list), strong hand prefers betting, weak hand
prefers fold, check preferred over fold when free, bot view never contains
other players' face-down cards, and bot action always in legal list.

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

As of Phase 1 Step 3:

```
tests/deck/           58 tests    Card, DeckConfig, Deck
tests/evaluators/     58 tests    PokerHandEvaluator
tests/game/           62 tests    Betting, Pot, Visibility, SevenCardStud
tests/bot/            10 tests    RuleBasedBot
Total                188 tests
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