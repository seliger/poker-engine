# Claude Code Issues & Notes
## Poker Engine: Home Game Edition

A running list of items to raise with Claude Code at phase boundaries.
Check off items as they are addressed. Add new items as they are discovered.

Format: phase discovered, file/location, description, priority (H/M/L).

**Workflow:** Items move to "Completed" only after the PR is merged and
confirmed. "Pending Merge" items are observations for after the merge,
not tasks for the next step.

---

## Current Status

Phase 2 Step 2 complete. All 427 tests pass.
Next: Phase 2 Step 3 (FollowTheQueenModifier).

Do NOT begin any frontend or UI work. The SvelteKit frontend is Phase 7.
Phases 2 through 6 are all backend only.

Build order reminder:

- Phase 2: Modifier System
    - Step 1: GameModifier interface and modifier hook (COMPLETE)
    - Step 2: HighLowDeclareModifier (COMPLETE)
    - Step 3: FollowTheQueenModifier (next)
    - Step 3: FollowTheQueenModifier
    - Step 4: DirtyBitchModifier
    - Step 5: Modifier selection exposed via REST API
- Phase 3: Deck Extensions
    - Step 1: Deck Layer WITH_NULLS config
    - Step 2: PokerHandEvaluator Null card evaluation rules
    - Step 3: Deck Layer WITH_ORBS config
    - Step 4: PokerHandEvaluator Orbs awareness
    - Step 5: PokerHandEvaluator wild card resolution
- Phase 4: Variant Expansion
    - Step 1: Five Card Draw
    - Step 2: Chicago and Low Chicago
    - Step 3: Night Baseball and Joe's Baseball
    - Step 4: Guts with burn limit and cascade logic
    - Step 5: Criss-Cross and Roll Your Own
    - Step 6: Elevator
    - Step 7: Pilot
    - Step 8: Anaconda and Chasing Queens
    - Step 9: Auction
    - Step 10: Screw Your Neighbor (includes SingleCardEvaluator)
- Phase 5: Numeric Variants
    - Step 1: NumericEvaluator
    - Step 2: Seven/Twenty-Seven
    - Step 3: Six-and-a-Half/Twenty-one-and-a-Half
- Phase 6: Trick-Taking Variants
    - Step 1: TrickTakingEvaluator
    - Step 2: PouletVariant state machine
    - Step 3: Follow suit enforcement
    - Step 4: Trump reveal and stay-in declaration via REST API
- Phase 7: Polish and SvelteKit frontend (NOT YET)
    - Step 1: Hand reference card with frequency adjustment
    - Step 2: Tier 2 Monte Carlo bot
    - Step 3: Claude API bot (optional)
    - Step 4: SvelteKit frontend
    - Step 5: Configuration UI in frontend
    - Step 6: Session history and statistics view

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
    (already implemented and tested as of Phase 1)

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

## Open - Deferred to Phase 3

- [ ] **H** `backend/evaluators/poker_hand_evaluator.py` `_from_pk_card()`:
  card_index dict built from input cards only. When wild card resolution
  is added in Phase 3, a wild card may resolve to a card not in the
  original input, causing a KeyError. Extend card_index to cover the full
  deck universe or handle wild assignments separately from PokerKit objects.
  Deferred: no wild resolution in current codebase yet.

---

## Open - Address in Phase 2 Step 5

- [ ] **L** `backend/api/game_manager.py` `_on_hand_complete()`:
  Balance computed as `ledger.get_player_balance() + delta`. Correct for a
  single-user synchronous app but relies on no concurrent writes between
  the read and the write. Document this assumption explicitly in the method
  docstring. No code change needed unless concurrency is ever introduced.

---

## Standing Instructions for All Phases

- [ ] **H** Before writing any new code, read the existing code to understand
  patterns already established. Extend those patterns consistently rather
  than reinventing them.

- [ ] **H** Do not access private attributes (leading underscore) in test
  files. If inspection is needed, add a public method or property instead.

- [ ] **H** No async/await anywhere in the Python backend. If you find
  yourself reaching for async, stop and find a synchronous solution.

- [ ] **H** PokerKit is imported only in
  `backend/evaluators/poker_hand_evaluator.py`. No other file imports
  PokerKit directly under any circumstances.

- [ ] **H** Do NOT begin any SvelteKit or frontend work. The UI layer is
  Phase 7. All remaining phases through Phase 6 are backend only.

- [ ] **M** Every new module must have a docstring explaining its scope and
  which layer it belongs to. See existing files for the pattern.

---

## Architectural Considerations (Future, No Immediate Action)

- [ ] **L** `backend/evaluators/poker_hand_evaluator.py`: NATURAL_SEVENS
  detection is implemented inside PokerHandEvaluator gated by the
  natural_sevens_active flag in variant_config. Works correctly but
  introduces variant-specific logic into a general-purpose evaluator.
  If additional variant-specific special cases are added in the future,
  consider refactoring to a JoesBaseballEvaluator subclass. No action
  needed now. Revisit if the pattern recurs.

---

## Items Discovered During Review (Add Here)

_Add new items here as they are discovered during code review._

---

## Completed Items

- [x] **H** Phase 2 Step 2: HighLowDeclareModifier.
  backend/game/modifiers/high_low_declare.py: HighLowDeclareModifier with
  get_phase_injection() injecting DECLARE before SHOWDOWN. SevenCardStudVariant
  updated with DECLARE phase execution, get_legal_actions, apply_action,
  is_phase_complete, advance_phase injection, _distribute_with_declare() with
  scoop-or-bust enforcement. GameManager._drive_to_interactive() handles DECLARE
  as interactive phase. RuleBasedBot handles DECLARE_HIGH/LOW/BOTH. 27 new tests
  (7 unit + 4 registry + 16 integration). All 427 tests pass.

- [x] **H** Phase 2 Step 1: GameModifier interface and modifier hook.
  backend/game/modifiers/base.py: GameModifier ABC, EffectType, PotInstruction,
  ModifierEffect, MODIFIER_REGISTRY (empty, populated in Steps 2-4),
  apply_modifier_effect(), run_modifier_hook(). 34 new tests covering
  all enums, abstract interface, stacking behavior, Poulet bypass, face-down
  card exclusion, and event history scanning. All 400 tests pass.

- [x] **L** SQLite thread safety: check_same_thread=False added to
  sqlite3.connect() in backend/persistence/database.py. Server starts
  cleanly with flask --app backend.app run.

- [x] **H** Phase 1 Step 5: REST API Layer implemented. All routes, WebSocket,
  app factory, game_manager. 52 new tests. 366 total passing.

- [x] **H** Phase 1 Step 4: Persistence Layer implemented. database.py,
  ledger.py, history.py. 96 new tests. 314 total passing.

- [x] **M** backend/evaluators/poker_hand_evaluator.py bare except in
  calculate_hand_frequencies(). Fixed: logger.warning() on exception.

- [x] **M** backend/evaluators/poker_hand_evaluator.py _evaluate_best_five()
  post-construction mutation. Fixed: immutable copy via _dc_replace().

- [x] **H** NATURAL_SEVENS hand rank implemented. All 13 tests pass.

- [x] **M** PotManager add_buy_payment() and add_take_last_up_payment()
  implemented proactively. 8 tests pass.

- [x] **M** backend/game/variants/seven_card_stud.py hardcoded
  first_bet_round_index = 3. Fixed: derived from phase sequence.

- [x] **L** backend/bot/rule_based.py _select_action() implicit None return.
  Fixed: explicit raise ValueError.

- [x] **L** memory/ folder retained in version control.

- [x] **M** backend/config.py DeckConfig mutated after construction. Fixed.

- [x] **L** tests/deck/test_deck.py private _available access. Fixed.

- [x] **L** tests/deck/test_deck.py missing pool correctness test. Fixed.