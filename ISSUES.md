# Claude Code Issues & Notes
## Poker Engine: Home Game Edition

A running list of items to raise with Claude Code at phase boundaries.
Check off items as they are addressed. Add new items as they are discovered.

Format: phase discovered, file/location, description, priority (H/M/L).

---

## Open Items

_No open items at this time._

---

## Standing Instructions for All Phases

- [ ] **H** Before writing any new code, read the existing code to understand
  patterns already established. Extend these patterns consistently rather
  than reinventing them.

- [ ] **H** Do not access private attributes (leading underscore) in test
  files. If a private attribute needs to be inspected in a test, add a
  public method or property to the class and test through that instead.

- [ ] **H** No async/await anywhere. If you find yourself reaching for async,
  stop and find a synchronous solution.

- [ ] **H** PokerKit is imported only in
  `backend/evaluators/poker_hand_evaluator.py`. No other file imports
  PokerKit directly under any circumstances.

- [ ] **M** Every new module must have a docstring explaining its scope and
  which layer it belongs to. See existing files for the pattern.

---

## Items Discovered During Review (Add Phase Here)

_Add new items here as they are discovered during code review._

---

## Completed Items

- [x] **M** `backend/evaluators/poker_hand_evaluator.py`: Bare `except Exception`
  in `calculate_hand_frequencies()` silently swallowed errors.
  Fixed: now emits `logger.warning()` with the exception detail.

- [x] **M** `backend/evaluators/poker_hand_evaluator.py` `_evaluate_best_five()`:
  `best.all_combinations = all_combos` mutated the dataclass after construction.
  Fixed: replaced with `dataclasses.replace(best, all_combinations=all_combos)`.

- [x] **H** `backend/evaluators/poker_hand_evaluator.py` `_from_pk_card()`:
  card_index built from input cards only; wild resolution would KeyError.
  Fixed: added Phase 3 docstring warning documenting the hazard and
  the two acceptable remediation strategies.

- [x] **M** `backend/config.py`: DeckConfig mutated after construction.
  Addressed in Phase 2: load_deck_config() now constructs DeckConfig
  with all values in a single call.

- [x] **L** `tests/deck/test_deck.py`: Private `_available` access in tests.
  Deck.cards() public method added. Pattern not repeated in Phase 2 tests.

- [x] **L** `tests/deck/test_deck.py` TestDeckSerialization: Missing pool
  correctness test. Added `test_cards_restored_to_correct_pools` in Phase 2.

## Current Status
Phase 1 Step 2 complete. Next: Phase 1 Step 3 (Tier 1 bot).
