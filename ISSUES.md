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

Phase 1 Step 3 merged. Phase 3 review items and Phase 2 confirmation items
addressed in this session. Next step: Phase 1 Step 4 (Persistence Layer:
SQLite, chip ledger, session tracking).

Spec updates completed in this session (not yet reflected in any code):
- docs/02_poker_hand_evaluator.md amended to v1.3 (NATURAL_SEVENS hand rank)
- docs/05_game_layer.md updated to v1.1 (Chicago personal wild, Joe's Baseball
  rewrite, Night Baseball escalating buy, TAKE_LAST_CARD_UP shared action,
  new GameState/PlayerState/ActionType/EventType/GamePhase fields)
- config/house_rules.json updated to v1.2 (chicago, joes_baseball sections
  added, night_baseball corrected, joes_baseball wild cards corrected)

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
  may pass. Either way four_card_buy_count has incremented for the next 4.

- [ ] **M** Read house_rules.json v1.2 before implementing Phase 4 variants.
  New sections: chicago, joes_baseball. Updated section: night_baseball.
  The four_card_price_schedules are defined in night_baseball and referenced
  by joes_baseball. All variant-specific costs and wild card configurations
  must be read from house_rules.json, never hardcoded.

---

## Phase 3 Review - Resolved

Items found during Step 3 code review. All resolved in this session.

- [x] **M** `backend/game/variants/seven_card_stud.py` lines 343-345:
  Bring-in round detection used `_PHASE_SEQUENCE.index(GamePhase.BET_ROUND)`
  to find the index but then separately hardcoded `first_bet_round_index = 3`.
  Fixed: removed the hardcoded 3 and the unused `is_bring_in_round` variable.
  `first_bet_round_index` is now derived solely from `_PHASE_SEQUENCE.index()`.

- [x] **L** `backend/bot/rule_based.py` `_select_action()`: Implicit return
  None at the bottom if the fold/check fallback finds no matching action.
  Fixed: added explicit `raise ValueError("No fallback action found. Available
  actions: {action_types}")` as a defensive guard at the end of `_select_action()`.

- [x] **L** `memory/` folder: Claude Code session continuity system. Decision:
  `memory/` is already listed in `.gitignore` and is excluded from version
  control. No action required.

---

## Phase 2 Review - Confirmed

Items found during Step 2 code review. Verified in this session.

- [x] **M** `backend/evaluators/poker_hand_evaluator.py` line 368:
  Bare `except Exception: continue` was replaced with `except Exception as exc:`
  plus `logger.warning(...)` in the existing code. Confirmed resolved.

- [x] **M** `backend/evaluators/poker_hand_evaluator.py` `_evaluate_best_five()`:
  `best.all_combinations = all_combos` post-construction mutation was replaced
  with `return _dc_replace(best, all_combinations=all_combos)` (dataclasses.replace).
  Confirmed resolved.

- [ ] **H** `backend/evaluators/poker_hand_evaluator.py` `_from_pk_card()`:
  card_index dict built from input cards only. When wild card resolution
  is added in Phase 3, a wild card may resolve to a card not in the
  original input, causing a KeyError. Extend card_index to cover the full
  deck universe or handle wild assignments separately from PokerKit objects.
  A `Phase 3 note` comment is already present in the function. Remains open
  until Phase 3 wild card resolution is implemented.

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

- [x] **M** `backend/evaluators/poker_hand_evaluator.py` line 368:
  Bare `except Exception: continue` replaced with `except Exception as exc:`
  plus `logger.warning(...)`. Confirmed present and correct in Phase 3 review.

- [x] **M** `backend/evaluators/poker_hand_evaluator.py` `_evaluate_best_five()`:
  Post-construction mutation `best.all_combinations = all_combos` replaced
  with `_dc_replace(best, all_combinations=all_combos)`. Confirmed in Phase 3 review.

- [x] **M** `backend/game/variants/seven_card_stud.py` bring-in round index:
  Removed hardcoded `first_bet_round_index = 3` and unused `is_bring_in_round`
  variable. Index now derived exclusively from `_PHASE_SEQUENCE.index(GamePhase.BET_ROUND)`.

- [x] **L** `backend/bot/rule_based.py` `_select_action()`: Added explicit
  `raise ValueError("No fallback action found...")` at the end of the method
  to guard against implicit None return if FOLD and CHECK are both absent.

- [x] **L** `memory/` folder: Already listed in `.gitignore`. No code changes needed.