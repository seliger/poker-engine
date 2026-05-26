"""SevenCardStudVariant: Seven Card Stud state machine for the Game Layer.

Phase 1 scope: standard Seven Card Stud with optional modifiers.
Chicago and Low Chicago are deferred to Phase 4.

Phase sequence (base):
    SETUP → ANTE → INITIAL_DEAL → BET_ROUND ×5 / DEAL_ROUND ×4
    → SHOWDOWN → POT_DISTRIBUTION → COMPLETE

With HighLowDeclareModifier active, DECLARE is injected before SHOWDOWN.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.deck.card import Card
from backend.deck.card import InsufficientCardsError
from backend.evaluators.base import Declaration, EvalDirection, WinnerResult
from backend.evaluators.poker_hand_evaluator import PokerHandEvaluator
from backend.game.betting import (
    apply_betting_action,
    assign_bring_in,
    find_best_visible_hand_player,
    get_legal_betting_actions,
    initialize_betting_round,
    is_betting_round_complete,
)
from backend.game.pot import PotManager
from backend.game.state import (
    ActiveGameConfig,
    BettingState,
    BettingStructure,
    EventType,
    GamePhase,
    GameState,
    GameVariant,
    Pot,
    PositionedCard,
)
from backend.game.variants.base import BaseVariant, PlayerAction, ShowdownResult
from backend.game.visibility import ActionType, LegalAction

logger = logging.getLogger(__name__)

# Full phase sequence for Seven Card Stud (indices used to track progress).
_PHASE_SEQUENCE: list[GamePhase] = [
    GamePhase.SETUP,
    GamePhase.ANTE,
    GamePhase.INITIAL_DEAL,
    GamePhase.BET_ROUND,    # round 1, bring-in
    GamePhase.DEAL_ROUND,   # street 2, 1 up
    GamePhase.BET_ROUND,    # round 2
    GamePhase.DEAL_ROUND,   # street 3, 1 up
    GamePhase.BET_ROUND,    # round 3
    GamePhase.DEAL_ROUND,   # street 4, 1 up
    GamePhase.BET_ROUND,    # round 4
    GamePhase.DEAL_ROUND,   # river (street 5), 1 down
    GamePhase.BET_ROUND,    # round 5
    GamePhase.SHOWDOWN,
    GamePhase.POT_DISTRIBUTION,
    GamePhase.COMPLETE,
]

# Index of each DEAL_ROUND in the sequence, plus whether the card is face-up.
# Indices 4, 6, 8 are face-up; index 10 is the river (face-down).
_DEAL_ROUND_FACE_UP: dict[int, bool] = {4: True, 6: True, 8: True, 10: False}


class SevenCardStudVariant(BaseVariant):
    """Seven Card Stud state machine.

    Drives one complete hand from SETUP through COMPLETE. The caller is
    responsible for constructing the initial GameState and for persisting
    chip movements after each hand.
    """

    variant = GameVariant.SEVEN_CARD_STUD
    evaluator_class = PokerHandEvaluator
    default_betting_structure = BettingStructure.BRING_IN
    min_players = 2
    max_players = 9

    def __init__(
        self,
        ante_amount: int = 1,
        bring_in_amount: int = 1,
        small_bet: int = 2,
        big_bet: int = 4,
    ) -> None:
        self._ante = ante_amount
        self._bring_in = bring_in_amount
        self._small_bet = small_bet
        self._big_bet = big_bet
        self._evaluator = PokerHandEvaluator()
        # PotManager is created fresh in initialize().
        self._pot_manager: PotManager | None = None

    # ------------------------------------------------------------------
    # BaseVariant interface
    # ------------------------------------------------------------------

    def initialize(
        self,
        game_state: GameState,
        active_game_config: ActiveGameConfig,
    ) -> GameState:
        """Attach variant_config defaults and create a fresh PotManager."""
        vc = active_game_config.variant_config
        vc.setdefault("phase_index", 0)
        vc.setdefault("deal_round_index", 0)
        vc.setdefault("community_river", None)

        self._pot_manager = PotManager(carry_amount=game_state.pot.carry_amount)
        game_state.active_game_config = active_game_config
        return game_state

    def get_phase_sequence(self) -> list[GamePhase]:
        return list(_PHASE_SEQUENCE)

    def execute_phase(
        self,
        game_state: GameState,
        phase: GamePhase,
    ) -> GameState:
        """Execute the given phase to completion (or initialize interactive phases)."""
        vc = game_state.active_game_config.variant_config

        if phase == GamePhase.SETUP:
            game_state.phase = GamePhase.SETUP
            # Nothing to do here; deck is already built and shuffled in the caller.

        elif phase == GamePhase.ANTE:
            game_state.phase = GamePhase.ANTE
            self._collect_antes(game_state)

        elif phase == GamePhase.INITIAL_DEAL:
            game_state.phase = GamePhase.INITIAL_DEAL
            self._deal_initial(game_state)

        elif phase == GamePhase.BET_ROUND:
            game_state.phase = GamePhase.BET_ROUND
            self._setup_bet_round(game_state)

        elif phase == GamePhase.DEAL_ROUND:
            game_state.phase = GamePhase.DEAL_ROUND
            self._deal_street(game_state)

        elif phase == GamePhase.DECLARE:
            game_state.phase = GamePhase.DECLARE
            self._setup_declare_round(game_state)

        elif phase == GamePhase.SHOWDOWN:
            game_state.phase = GamePhase.SHOWDOWN
            # Actual evaluation happens in resolve_showdown(); phase is a signal.

        elif phase == GamePhase.POT_DISTRIBUTION:
            game_state.phase = GamePhase.POT_DISTRIBUTION
            self._distribute_pot(game_state)

        elif phase == GamePhase.COMPLETE:
            game_state.phase = GamePhase.COMPLETE
            game_state.record_event(EventType.HAND_COMPLETE)

        return game_state

    def get_legal_actions(
        self,
        game_state: GameState,
        player_id: str,
    ) -> list[LegalAction]:
        """Return legal actions for the given player in the current phase."""
        if game_state.phase == GamePhase.BET_ROUND:
            return get_legal_betting_actions(
                game_state, player_id, self._small_bet, self._big_bet
            )
        if game_state.phase == GamePhase.ANTE:
            player = game_state.get_player(player_id)
            if player.chip_stack > 0:
                return [LegalAction(
                    action_type=ActionType.POST_ANTE,
                    min_amount=min(self._ante, player.chip_stack),
                    max_amount=min(self._ante, player.chip_stack),
                )]
        if game_state.phase == GamePhase.DECLARE:
            current = game_state.players[game_state.active_player_index]
            if current.player_id != player_id:
                return []
            return [
                LegalAction(action_type=ActionType.DECLARE_HIGH),
                LegalAction(action_type=ActionType.DECLARE_LOW),
                LegalAction(action_type=ActionType.DECLARE_BOTH),
            ]
        return []

    def apply_action(
        self,
        game_state: GameState,
        player_id: str,
        action: PlayerAction,
    ) -> GameState:
        """Apply a player action during a BET_ROUND or DECLARE phase."""
        if game_state.phase == GamePhase.DECLARE:
            return self._apply_declare_action(game_state, player_id, action)

        if game_state.phase != GamePhase.BET_ROUND:
            raise ValueError(
                f"apply_action called in phase {game_state.phase}; expected BET_ROUND or DECLARE"
            )
        if self._pot_manager is None:
            raise RuntimeError("PotManager not initialized; call initialize() first")

        apply_betting_action(
            game_state,
            player_id,
            action.action_type,
            action.amount,
            self._pot_manager,
        )
        return game_state

    def is_phase_complete(
        self,
        game_state: GameState,
        phase: GamePhase,
    ) -> bool:
        """Return True when the current phase has finished."""
        if phase == GamePhase.BET_ROUND:
            return is_betting_round_complete(game_state)

        if phase == GamePhase.DECLARE:
            active = game_state.active_players()
            return all(p.declaration is not None for p in active)

        # Non-interactive phases complete immediately after execute_phase().
        return game_state.phase == phase

    def advance_phase(self, game_state: GameState) -> GameState:
        """Advance to the next phase in the sequence.

        Handles DECLARE→SHOWDOWN transition and modifier-injected phases.
        If only one active player remains, skips directly to POT_DISTRIBUTION.
        """
        vc = game_state.active_game_config.variant_config

        # DECLARE is not in _PHASE_SEQUENCE; it transitions directly to SHOWDOWN.
        if game_state.phase == GamePhase.DECLARE:
            vc["declare_done"] = True
            showdown_index = _PHASE_SEQUENCE.index(GamePhase.SHOWDOWN)
            vc["phase_index"] = showdown_index
            game_state.phase = GamePhase.SHOWDOWN
            return game_state

        active = game_state.active_players()
        if len(active) == 1 and game_state.phase not in (
            GamePhase.SHOWDOWN,
            GamePhase.POT_DISTRIBUTION,
            GamePhase.COMPLETE,
        ):
            game_state.phase = GamePhase.POT_DISTRIBUTION
            vc["phase_index"] = _PHASE_SEQUENCE.index(GamePhase.POT_DISTRIBUTION)
            return game_state

        current_index: int = vc.get("phase_index", 0)
        next_index = current_index + 1

        if next_index >= len(_PHASE_SEQUENCE):
            game_state.phase = GamePhase.COMPLETE
            vc["phase_index"] = next_index
            return game_state

        next_phase = _PHASE_SEQUENCE[next_index]

        # Allow modifiers to inject a phase before the computed next phase.
        for modifier in game_state.active_game_config.modifiers:
            injected = modifier.get_phase_injection(next_phase, game_state)
            if injected is not None:
                game_state.phase = injected
                # phase_index stays at current_index so it still points to SHOWDOWN
                # when we exit the injected phase.
                return game_state

        game_state.phase = next_phase
        vc["phase_index"] = next_index
        return game_state

    def resolve_showdown(self, game_state: GameState) -> ShowdownResult:
        """Evaluate all active players' hands and determine winners."""
        active = game_state.active_players()
        community_river: Card | None = game_state.active_game_config.variant_config.get(
            "community_river"
        )

        evaluated: dict[str, Any] = {}
        for player in active:
            all_cards = [pc.card for pc in player.hole_cards]
            if community_river is not None:
                all_cards.append(community_river)
            result = self._evaluator.evaluate(
                all_cards, game_state.deck_config, direction=EvalDirection.HIGH
            )
            evaluated[player.player_id] = result
            game_state.record_event(
                EventType.SHOWDOWN,
                player_id=player.player_id,
                metadata={"hand": result.display_name},
            )

        winner_result: WinnerResult = self._evaluator.determine_winners(
            evaluated, EvalDirection.HIGH
        )

        pot_distribution: dict[str, int] = {}
        if self._pot_manager is not None:
            pot_distribution = self._pot_manager.distribute(winner_result)

        return ShowdownResult(
            winner_ids=winner_result.winners,
            winning_hands=evaluated,
            pot_distribution=pot_distribution,
            is_tie=winner_result.is_tie,
        )

    # ------------------------------------------------------------------
    # Internal phase execution helpers
    # ------------------------------------------------------------------

    def _collect_antes(self, game_state: GameState) -> None:
        """Collect ante from every active player."""
        if self._pot_manager is None:
            raise RuntimeError("PotManager not initialized")
        for player in game_state.players:
            if player.is_eliminated_this_hand:
                continue
            amount = min(self._ante, player.chip_stack)
            player.chip_stack -= amount
            self._pot_manager.add_ante(player.player_id, amount)
            game_state.record_event(EventType.ANTE_POSTED, player.player_id, amount=amount)
        game_state.pot = self._pot_manager.get_pot()

    def _deal_initial(self, game_state: GameState) -> None:
        """Deal 2 face-down and 1 face-up card to each active player."""
        active = [p for p in game_state.players if not p.is_eliminated_this_hand]
        card_index = 0

        # Deal round: two face-down cards.
        for _ in range(2):
            for player in active:
                card = game_state.deck.deal(1)[0]
                player.hole_cards.append(
                    PositionedCard(
                        card=card,
                        is_face_up=False,
                        position_index=card_index,
                        revealed_at_phase=None,
                    )
                )
                card_index += 1
                game_state.record_event(EventType.CARD_DEALT, player.player_id)

        # Deal one face-up card (the door card).
        for player in active:
            card = game_state.deck.deal(1)[0]
            player.hole_cards.append(
                PositionedCard(
                    card=card,
                    is_face_up=True,
                    position_index=card_index,
                    revealed_at_phase=GamePhase.INITIAL_DEAL,
                )
            )
            card_index += 1
            game_state.record_event(
                EventType.CARD_DEALT, player.player_id, card=card
            )

    def _setup_bet_round(self, game_state: GameState) -> None:
        """Initialize a betting round: set active player, current bet, etc."""
        vc = game_state.active_game_config.variant_config
        phase_index: int = vc["phase_index"]

        first_bet_round_index = _PHASE_SEQUENCE.index(GamePhase.BET_ROUND)

        if phase_index == first_bet_round_index:
            # Bring-in round: assign bring-in to lowest face-up card.
            bring_in_player = assign_bring_in(game_state)
            initialize_betting_round(
                game_state,
                first_to_act_id=bring_in_player,
                is_bring_in_round=True,
                ante=self._ante,
                bring_in_amount=self._bring_in,
                small_bet=self._small_bet,
                big_bet=self._big_bet,
            )
        else:
            # Subsequent rounds: best visible hand acts first.
            first_player = find_best_visible_hand_player(game_state)
            initialize_betting_round(
                game_state,
                first_to_act_id=first_player,
                is_bring_in_round=False,
                ante=self._ante,
                bring_in_amount=self._bring_in,
                small_bet=self._small_bet,
                big_bet=self._big_bet,
            )
        game_state.pot = self._pot_manager.get_pot() if self._pot_manager else game_state.pot

    def _deal_street(self, game_state: GameState) -> None:
        """Deal one card to each active player for a subsequent street."""
        vc = game_state.active_game_config.variant_config
        phase_index: int = vc["phase_index"]

        is_face_up = _DEAL_ROUND_FACE_UP.get(phase_index, True)
        is_river = not is_face_up
        active = [p for p in game_state.players if not p.is_folded and not p.is_eliminated_this_hand]

        # River deck-exhaustion check: if fewer cards than players, use community card.
        if is_river and game_state.deck.remaining() < len(active):
            self._deal_community_river(game_state)
            vc["deal_round_index"] = vc.get("deal_round_index", 0) + 1
            return

        for player in active:
            try:
                card = game_state.deck.deal(1)[0]
            except InsufficientCardsError:
                if is_river:
                    # Ran out mid-river deal; community card covers remaining players.
                    self._deal_community_river(game_state)
                    vc["deal_round_index"] = vc.get("deal_round_index", 0) + 1
                    return
                raise
            pos_idx = len(player.hole_cards)
            player.hole_cards.append(
                PositionedCard(
                    card=card,
                    is_face_up=is_face_up,
                    position_index=pos_idx,
                    revealed_at_phase=GamePhase.DEAL_ROUND,
                )
            )
            game_state.record_event(
                EventType.CARD_DEALT,
                player_id=player.player_id,
                card=card if is_face_up else None,
            )

        vc["deal_round_index"] = vc.get("deal_round_index", 0) + 1

    def _deal_community_river(self, game_state: GameState) -> None:
        """Deal one face-up community card shared by all when deck is exhausted.

        This handles the deck exhaustion edge case in Seven Card Stud with
        the maximum number of players: a shared community river is dealt
        face-up and all remaining players use it as their seventh card.
        """
        if game_state.deck.remaining() < 1:
            logger.warning(
                "Deck exhausted before community river; dealing from burned cards is "
                "not implemented. Hand will proceed without the river card."
            )
            return

        card = game_state.deck.deal(1)[0]
        game_state.active_game_config.variant_config["community_river"] = card
        game_state.record_event(
            EventType.CARD_REVEALED,
            card=card,
            metadata={"community_river": True},
        )
        logger.info("Deck exhaustion: community river %s dealt face-up.", card.shorthand())

    def _distribute_pot(self, game_state: GameState) -> None:
        """Resolve the showdown and award chips to winners."""
        active = game_state.active_players()

        # All others folded: award pot directly without evaluating partial hands.
        if len(active) == 1 and self._pot_manager is not None:
            winner = active[0]
            total = self._pot_manager.get_total()
            if total > 0:
                winner.chip_stack += total
                game_state.record_event(EventType.POT_AWARDED, winner.player_id, amount=total)
            game_state.pot = self._pot_manager.get_pot()
            return

        # If declarations are present, use high-low declare distribution.
        if any(p.declaration is not None for p in active):
            self._distribute_with_declare(game_state)
            return

        result = self.resolve_showdown(game_state)

        for player_id, amount in result.pot_distribution.items():
            player = game_state.get_player(player_id)
            player.chip_stack += amount
            game_state.record_event(EventType.POT_AWARDED, player_id, amount=amount)

        # Update pot to reflect distribution.
        if self._pot_manager:
            game_state.pot = self._pot_manager.get_pot()

    def _setup_declare_round(self, game_state: GameState) -> None:
        """Reset all active player declarations and set the first active player."""
        active = game_state.active_players()
        for player in active:
            player.declaration = None
        if active:
            game_state.active_player_index = game_state.players.index(active[0])

    def _apply_declare_action(
        self,
        game_state: GameState,
        player_id: str,
        action: PlayerAction,
    ) -> GameState:
        """Map DECLARE_HIGH/LOW/BOTH action to Declaration, store on PlayerState."""
        _declaration_map = {
            ActionType.DECLARE_HIGH: Declaration.HIGH,
            ActionType.DECLARE_LOW: Declaration.LOW,
            ActionType.DECLARE_BOTH: Declaration.BOTH,
        }
        if action.action_type not in _declaration_map:
            raise ValueError(f"Invalid declare action: {action.action_type}")

        player = game_state.get_player(player_id)
        player.declaration = _declaration_map[action.action_type]
        game_state.record_event(
            EventType.DECLARATION_MADE,
            player_id=player_id,
            metadata={"declaration": player.declaration.value},
        )

        # Advance active_player_index to the next undeclared active player.
        active = game_state.active_players()
        undeclared = [p for p in active if p.declaration is None]
        if undeclared:
            game_state.active_player_index = game_state.players.index(undeclared[0])

        return game_state

    def _distribute_with_declare(self, game_state: GameState) -> None:
        """Distribute the pot respecting HIGH/LOW/BOTH declarations.

        Evaluates each active player in their declared direction(s), determines
        winners per direction, applies scoop-or-bust for BOTH declarants who
        did not win both directions, then distributes via PotManager.
        """
        if self._pot_manager is None:
            raise RuntimeError("PotManager not initialized; call initialize() first")

        active = game_state.active_players()
        community_river = game_state.active_game_config.variant_config.get("community_river")

        high_evaluated: dict[str, Any] = {}
        low_evaluated: dict[str, Any] = {}

        for player in active:
            if player.declaration is None:
                continue
            all_cards = [pc.card for pc in player.hole_cards]
            if community_river is not None:
                all_cards.append(community_river)

            if player.declaration in (Declaration.HIGH, Declaration.BOTH):
                high_evaluated[player.player_id] = self._evaluator.evaluate(
                    all_cards, game_state.deck_config, direction=EvalDirection.HIGH
                )
            if player.declaration in (Declaration.LOW, Declaration.BOTH):
                low_evaluated[player.player_id] = self._evaluator.evaluate(
                    all_cards, game_state.deck_config, direction=EvalDirection.LOW
                )

        high_result: WinnerResult | None = (
            self._evaluator.determine_winners(high_evaluated, EvalDirection.HIGH)
            if high_evaluated else None
        )
        low_result: WinnerResult | None = (
            self._evaluator.determine_winners(low_evaluated, EvalDirection.LOW)
            if low_evaluated else None
        )

        # Scoop-or-bust: BOTH declarants who don't win both get nothing.
        if self._get_both_ways_requires_scoop(game_state):
            both_pids = {p.player_id for p in active if p.declaration == Declaration.BOTH}
            disqualified = set()
            for pid in both_pids:
                won_high = high_result is not None and pid in high_result.winners
                won_low = low_result is not None and pid in low_result.winners
                if not (won_high and won_low):
                    disqualified.add(pid)

            if disqualified:
                high_remaining = {pid: h for pid, h in high_evaluated.items() if pid not in disqualified}
                low_remaining = {pid: l for pid, l in low_evaluated.items() if pid not in disqualified}
                high_result = (
                    self._evaluator.determine_winners(high_remaining, EvalDirection.HIGH)
                    if high_remaining else None
                )
                low_result = (
                    self._evaluator.determine_winners(low_remaining, EvalDirection.LOW)
                    if low_remaining else None
                )

        # Record showdown events.
        for player in active:
            display_hand = high_evaluated.get(player.player_id) or low_evaluated.get(player.player_id)
            if display_hand and player.declaration is not None:
                game_state.record_event(
                    EventType.SHOWDOWN,
                    player_id=player.player_id,
                    metadata={
                        "hand": display_hand.display_name,
                        "declaration": player.declaration.value,
                    },
                )

        # Distribute chips.
        if high_result is None and low_result is None:
            return

        if high_result is None:
            pot_distribution = self._pot_manager.distribute(low_result)  # type: ignore[arg-type]
        elif low_result is None:
            pot_distribution = self._pot_manager.distribute(high_result)
        else:
            pot_distribution = self._pot_manager.distribute(high_result, low_result)

        for player_id, amount in pot_distribution.items():
            player = game_state.get_player(player_id)
            player.chip_stack += amount
            game_state.record_event(EventType.POT_AWARDED, player_id, amount=amount)

        game_state.pot = self._pot_manager.get_pot()

    def _get_both_ways_requires_scoop(self, game_state: GameState) -> bool:
        """Return whether BOTH declarants must win both directions or receive nothing."""
        from backend.game.modifiers.high_low_declare import HighLowDeclareModifier
        for modifier in game_state.active_game_config.modifiers:
            if isinstance(modifier, HighLowDeclareModifier):
                return modifier.both_ways_requires_scoop
        return True  # default per spec
