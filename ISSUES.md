# Issues & Notes
## Poker Engine: Home Game Edition

A running list of items to raise with Claude Code at phase boundaries.
Check off items as they are addressed. Add new items as they are discovered.

Format: phase discovered, file/location, description, priority (H/M/L).

---

## Phase 1 Completion - Items to Address before Phase 2

- [x] **M** `backend/config.py` lines 74-85: DeckConfig is mutated after
  construction rather than built with all values at once. Spec intent is
  that DeckConfig be immutable once created. Refactor load_deck_config()
  to construct DeckConfig with all values in a single call rather than
  setting attributes after the fact. Example pattern:
  ```python
  config = DeckConfig(
      include_nulls=preset.include_nulls,
      nulls_match_each_other=null_rules.get("nulls_match_each_other", False),
      ...
  )
  ```

- [x] **L** `tests/deck/test_deck.py`: Several tests access `deck._available`
  directly to inspect card contents. This couples tests to a private
  implementation detail. Consider adding a public `cards()` or `snapshot()`
  method to Deck that returns the current available cards for inspection.
  Do not change existing tests retroactively but do not repeat this pattern
  in future test files.

- [x] **L** `tests/deck/test_deck.py` TestDeckSerialization: The roundtrip
  test verifies remaining() count and config flags but does not verify that
  specific cards are restored to the correct pool (available vs dealt vs
  burned). Add a test that deals specific cards, burns one, serializes,
  deserializes, and confirms each card is in the expected pool.

---

## Standing Instructions for All Phases

- [ ] **H** Before writing any new code, read the existing Phase 1 code to
  understand patterns already established: the three-pool Deck, the frozen
  Card dataclass, the config loader fallback chain. Extend these patterns
  consistently rather than reinventing them.

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

- **M** `backend/config.py`: `load_deck_config()` now constructs `DeckConfig`
  in a single call using a `_preset_bases` lookup dict; no post-construction
  mutation. (Phase 1 review)

- **L** `backend/deck/deck.py`: Added public `cards()` method returning a copy
  of the available pool. Existing tests that access `_available` directly are
  not changed; new tests must use `cards()` or `to_dict()` instead. (Phase 1
  review)

- **L** `tests/deck/test_deck.py` TestDeckSerialization: Added
  `test_cards_restored_to_correct_pools` which deals 3 cards, burns 1,
  serializes, deserializes, and asserts each specific card lands in the
  correct pool (dealt/burned/available). (Phase 1 review)