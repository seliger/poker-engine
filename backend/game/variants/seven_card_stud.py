"""SevenCardStudVariant: Seven Card Stud state machine for the Game Layer.

Phase 1 scope: standard Seven Card Stud, no modifiers, no wild cards,
standard 52-card deck. Chicago and Low Chicago are deferred to Phase 4.

Phase sequence:
    SETUP → ANTE → INITIAL_DEAL → BET_ROUND ×5 / DEAL_ROUND ×4
    → SHOWDOWN → POT_DISTRIBUTION → COMPLETE
"""

from __future__ import annotations

import logging
from typing import Any

from backend.deck.card import Card
from backend.deck.card import InsufficientCardsError
from backend.evaluators.base import EvalDirection, WinnerResult
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
        return []

    def apply_action(
        self,
        game_state: GameState,
        player_id: str,
        action: PlayerAction,
    ) -> GameState:
        """Apply a player action during a BET_ROUND phase."""
        if game_state.phase != GamePhase.BET_ROUND:
            raise ValueError(
                f"apply_action called in phase {game_state.phase}; expected BET_ROUND"
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

        # Non-interactive phases complete immediately after execute_phase().
        return game_state.phase == phase

    def advance_phase(self, game_state: GameState) -> GameState:
        """Advance to the next phase in the sequence.

        If only one active player remains, skip directly to POT_DISTRIBUTION
        (the hand is already won).
        """
        active = game_state.active_players()
        if len(active) == 1 and game_state.phase not in (
            GamePhase.SHOWDOWN,
            GamePhase.POT_DISTRIBUTION,
            GamePhase.COMPLETE,
        ):
            game_state.phase = GamePhase.POT_DISTRIBUTION
            game_state.active_game_config.variant_config["phase_index"] = (
                _PHASE_SEQUENCE.index(GamePhase.POT_DISTRIBUTION)
            )
            return game_state

        vc = game_state.active_game_config.variant_config
        current_index: int = vc.get("phase_index", 0)
        next_index = current_index + 1

        if next_index >= len(_PHASE_SEQUENCE):
            game_state.phase = GamePhase.COMPLETE
            vc["phase_index"] = next_index
            return game_state

        game_state.phase = _PHASE_SEQUENCE[next_index]
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

        is_bring_in_round = (phase_index == _PHASE_SEQUENCE.index(GamePhase.BET_ROUND))
        # phase_index == 3 is the first BET_ROUND (bring-in).
        first_bet_round_index = 3

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
        result = self.resolve_showdown(game_state)

        for player_id, amount in result.pot_distribution.items():
            player = game_state.get_player(player_id)
            player.chip_stack += amount
            game_state.record_event(EventType.POT_AWARDED, player_id, amount=amount)

        # Update pot to reflect distribution.
        if self._pot_manager:
            game_state.pot = self._pot_manager.get_pot()
