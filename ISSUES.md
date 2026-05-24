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

Phase 1 Step 4 complete. PR under review. Next step after merge: Phase 1
Step 5 (REST API Layer: Flask routes, WebSocket, session/hand/chip endpoints).

Spec updates completed (reflected in docs/ and config/):
- docs/02_poker_hand_evaluator.md amended to v1.3 (NATURAL_SEVENS hand rank)
- docs/05_game_layer.md updated to v1.1 (Chicago personal wild, Joe's Baseball
  rewrite, Night Baseball escalating buy, TAKE_LAST_CARD_UP shared action,
  new GameState/PlayerState/ActionType/EventType/GamePhase fields)
- config/house_rules.json updated to v1.2 (chicago, joes_baseball sections
  added, night_baseball corrected)

---

## Spec Change Notices - Read Before Phase 4

These are not code review items. They are spec changes that affect Phase 4
implementation. Claude Code must read the updated documents before
implementing any Phase 4 variant.

- [ ] **H** Read docs/02_poker_hand_evaluator.md Amendment v1.3 before
  implementing JoesBaseballVariant. NATURAL_SEVENS is a new hand rank (11)
  that sits above ROYAL_FLUSH. It requires exactly two physical 7-ranked
  cards of different suits. Wild cards may not substitute. The evaluator
  pre-checks for NATURAL_SEVENS before any other evaluation when
  natural_sevens_active is True in variant_config.

- [ ] **H** Read docs/05_game_layer.md v1.1 in full before implementing any
  Phase 4 variant. Key changes from v1.0:
  - GameState has new field: four_card_buy_count (int, reset to 0 each hand)
  - PlayerState has new field: personal_wild_rank (int | None)
  - GamePhase has new value: TAKE_LAST_UP_OFFER
  - ActionType has new values: TAKE_LAST_CARD_UP, PASS_LAST_CARD_UP,
    BUY_FOUR_CARD, PASS_FOUR_CARD
  - EventType has new values: FOUR_CARD_BUY_OFFERED, FOUR_CARD_BUY_ACCEPTED,
    FOUR_CARD_BUY_PASSED, TAKE_LAST_UP_ACCEPTED, TAKE_LAST_UP_DECLINED
  - PlayerView has new field: my_personal_wild_rank (int | None)
  - PotManager has new methods: add_buy_payment(), add_take_last_up_payment()
    (Note: these are already implemented and tested as of Step 3a.)

- [ ] **H** ChicagoVariant is NOT SevenCardStudVariant with a modifier.
  It requires its own state machine per docs/05_game_layer.md v1.1.
  Chicago has a personal wild card system (lowest face-down card is wild
  for that player only), a TAKE_LAST_UP_OFFER phase before the river, and
  a $1 cost to take the river card face-up. Each player's evaluate() call
  uses their own personal wild_ranks. This is the only variant where
  wild_ranks differs per player within the same hand.

- [ ] **H** JoesBaseballVariant wild cards are NOT 3s and 9s. The correct
  wild cards are: 2s (rank 2), Jacks (rank 11), and King of Diamonds
  (rank 13, suit DIAMONDS) as a specific card wild. The King of Diamonds
  is passed as wild_cards in variant_config, not as a wild_rank. Other
  Kings are not wild. natural_sevens_active must be True in variant_config.

- [ ] **H** NightBaseballVariant 4 card mechanic is an optional escalating
  buy, not a free automatic extra card. When a 4 is flipped, four_card_buy_count
  increments immediately, the player is offered BUY_FOUR_CARD or
  PASS_FOUR_CARD, and the price is determined by the active price schedule
  from house_rules.json night_baseball.four_card_price_schedule. The player
  may pass. Either way four_card_buy_count has already incremented.

- [ ] **M** Read house_rules.json v1.2 before implementing Phase 4 variants.
  New sections: chicago, joes_baseball. Updated section: night_baseball.
  All variant-specific costs and wild card configurations must be read
  from house_rules.json, never hardcoded.

---

## Phase 2 Review - Pending Confirmation

Items found during Step 2 code review. Verified and resolved during Step 4 review.

- [x] **M** `backend/evaluators/poker_hand_evaluator.py` line 368:
  Bare `except Exception: continue` in `calculate_hand_frequencies()`
  silently swallows all errors. Fixed in Step 4: now `except Exception as exc:
  logger.warning(...)` so errors surface during development.

- [x] **M** `backend/evaluators/poker_hand_evaluator.py` `_evaluate_best_five()`
  line 455: `best.all_combinations = all_combos` mutates the EvaluatedHand
  after construction. Fixed in Step 4: replaced with `return _dc_replace(best,
  all_combinations=all_combos)` — immutable dataclass copy semantics.

- [ ] **H** `backend/evaluators/poker_hand_evaluator.py` `_from_pk_card()`:
  card_index dict built from input cards only. When wild card resolution
  is added in Phase 3, a wild card may resolve to a card not in the
  original input, causing a KeyError. Extend card_index to cover the full
  deck universe or handle wild assignments separately from PokerKit objects.
  (Deferred to Phase 3 — no wild resolution in current codebase.)

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

## Architectural Considerations (Future, No Immediate Action)

- [ ] **L** `backend/evaluators/poker_hand_evaluator.py`: NATURAL_SEVENS
  detection is currently implemented inside PokerHandEvaluator gated by
  the natural_sevens_active flag in variant_config. This works correctly
  but introduces variant-specific logic into a general-purpose evaluator.
  If additional variant-specific special cases are added in the future,
  consider refactoring to a JoesBaseballEvaluator subclass that extends
  PokerHandEvaluator and overrides evaluate() to pre-check for natural
  sevens before delegating to the parent. No action needed now. Revisit
  if the pattern recurs.

---

## Items Discovered During Review (Add Phase Here)

_Add new items here as they are discovered during code review._

---

## Completed Items

- [x] **M** `backend/evaluators/poker_hand_evaluator.py` line 368:
  `except Exception: continue` in `calculate_hand_frequencies()`. Fixed in
  Step 4: now `except Exception as exc: logger.warning(...)`. Confirmed passing.

- [x] **M** `backend/evaluators/poker_hand_evaluator.py` `_evaluate_best_five()`
  post-construction mutation. Fixed in Step 4: `_dc_replace(best, all_combinations=
  all_combos)` — immutable copy. Confirmed passing.

- [x] **H** Phase 1 Step 4: Persistence Layer implemented.
  `backend/persistence/database.py` (schema, connection, WAL/FK/Row settings),
  `backend/persistence/ledger.py` (chip_ledger CRUD), `backend/persistence/history.py`
  (player/session/hand/hand_players CRUD). 96 new tests. All 314 tests pass.

- [x] **M** `backend/config.py`: DeckConfig mutated after construction.
  Addressed in Step 2. Confirmed in Step 2 review.

- [x] **L** `tests/deck/test_deck.py`: Private `_available` access in tests.
  Deck.cards() public method added. Confirmed in Step 2 review.

- [x] **L** `tests/deck/test_deck.py` TestDeckSerialization: Missing pool
  correctness test. test_cards_restored_to_correct_pools added in Step 2.
  Confirmed in Step 2 review.

- [x] **M** `backend/game/variants/seven_card_stud.py` lines 343-345:
  Hardcoded first_bet_round_index = 3. Removed in Step 3a. Now derived
  from phase sequence as single source of truth. Confirmed passing.

- [x] **L** `backend/bot/rule_based.py` `_select_action()`: Implicit None
  return. Explicit raise ValueError added in Step 3a. Confirmed passing.

- [x] **L** `memory/` folder: Retained in version control as useful session
  continuity context. Treated as canonical current status alongside ISSUES.md.

- [x] **H** NATURAL_SEVENS hand rank: Implemented in Step 3a per
  docs/02_poker_hand_evaluator.md Amendment v1.3. All 13 TestNaturalSevens
  tests pass. Confirmed in Step 3a review.

- [x] **M** PotManager add_buy_payment() and add_take_last_up_payment():
  Implemented proactively in Step 3a ahead of Phase 4. All 8
  TestPhase4PotMethods tests pass. Confirmed in Step 3a review.