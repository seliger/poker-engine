# Claude Code Issues & Notes
## Poker Engine: Home Game Edition

A running list of items to raise with Claude Code at phase boundaries.
Check off items as they are addressed. Add new items as they are discovered.

Format: phase discovered, file/location, description, priority (H/M/L).

**Workflow:** Items move from "Review Pending Merge" to "Completed" only
after the PR is merged and confirmed. Do not action "Review Pending Merge"
items in the next step; they are observations for after the merge.

---

## Current Status

Phase 1 Step 3 complete. PR under review. Next step after merge: Phase 1
Step 4 (Persistence Layer: SQLite, chip ledger, session tracking).

---

## Phase 3 Review - Pending Merge

Items found during Step 3 code review. Address these in Step 4 after merge.

- [ ] **M** `backend/game/variants/seven_card_stud.py` lines 343-345:
  Bring-in round detection uses `_PHASE_SEQUENCE.index(GamePhase.BET_ROUND)`
  to find index 3, then separately hardcodes `first_bet_round_index = 3`.
  These two references can silently diverge if the phase sequence changes.
  Derive first_bet_round_index from the sequence once and use it as the
  single source of truth. Remove the hardcoded 3.

- [ ] **L** `backend/bot/rule_based.py` `_select_action()`: Implicit return
  None at the bottom if the fold/check fallback finds no matching action.
  Since decide() promises to always return a PlayerAction, add an explicit
  raise ValueError("No fallback action found") as a defensive guard at the
  end rather than falling through to an implicit None return.

- [ ] **L** `memory/` folder: Claude Code created its own session continuity
  system in memory/. This is functional and accurate. Decide whether to
  keep it in version control or add memory/ to .gitignore. Either is fine.
  If kept, treat memory/project_phase_status.md as the canonical current
  status and keep it updated alongside ISSUES.md.

---

## Phase 2 Review - Pending Confirmation

Items found during Step 2 code review. Carry into Step 4 if not yet
addressed. Verify during Step 4 review and move to Completed if resolved.

- [ ] **M** `backend/evaluators/poker_hand_evaluator.py` line 368:
  Bare `except Exception: continue` in `calculate_hand_frequencies()`
  silently swallows all errors. Replace with specific exception types or
  add a logger.warning() so errors surface during development.

- [ ] **M** `backend/evaluators/poker_hand_evaluator.py` `_evaluate_best_five()`
  line 455: `best.all_combinations = all_combos` mutates the EvaluatedHand
  after construction. Consider building all_combinations into the constructor
  call rather than setting it after.

- [ ] **H** `backend/evaluators/poker_hand_evaluator.py` `_from_pk_card()`:
  card_index dict built from input cards only. When wild card resolution
  is added in Phase 3, a wild card may resolve to a card not in the
  original input, causing a KeyError. Extend card_index to cover the full
  deck universe or handle wild assignments separately from PokerKit objects.

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

- [x] **M** `backend/config.py`: DeckConfig mutated after construction.
  Addressed in Phase 1 Step 2: load_deck_config() now constructs DeckConfig
  with all values in a single call. Confirmed in Step 2 review.

- [x] **L** `tests/deck/test_deck.py`: Private `_available` access in tests.
  Deck.cards() public method added. Pattern not repeated in Step 2 tests.
  Confirmed in Step 2 review.

- [x] **L** `tests/deck/test_deck.py` TestDeckSerialization: Missing pool
  correctness test. test_cards_restored_to_correct_pools added in Step 2.
  Confirmed in Step 2 review.
