"""Betting round management utilities for the Game Layer.

Handles bring-in assignment, betting round initialization, legal action
determination for betting phases, and betting round completion detection.
Used by variant state machines, not called directly from the REST API.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.deck.card import Suit
from backend.evaluators.base import EvalDirection
from backend.evaluators.poker_hand_evaluator import PokerHandEvaluator
from backend.game.state import (
    BettingState,
    BettingStructure,
    EventType,
    GameState,
    PlayerState,
    PositionedCard,
)
from backend.game.visibility import ActionType, LegalAction

logger = logging.getLogger(__name__)

# Suit ordering for bring-in tiebreaking: lower = posts bring-in (worst).
_SUIT_ORDER: dict[Suit, int] = {
    Suit.CLUBS: 0,
    Suit.DIAMONDS: 1,
    Suit.HEARTS: 2,
    Suit.SPADES: 3,
    Suit.ORBS: 4,
}

_EVALUATOR = PokerHandEvaluator()


def assign_bring_in(game_state: GameState) -> str:
    """Return the player_id who must post the bring-in.

    The player showing the lowest face-up card (by rank, then suit in
    CLUBS < DIAMONDS < HEARTS < SPADES < ORBS order) posts the bring-in.
    """
    best_player_id: str | None = None
    best_value: tuple[int, int] | None = None

    for player in game_state.players:
        if player.is_folded or player.is_eliminated_this_hand:
            continue
        face_up = [pc for pc in player.hole_cards if pc.is_face_up]
        if not face_up:
            continue
        # Door card is the first (and for initial deal, only) face-up card.
        door = face_up[0].card
        value = (door.rank if door.rank != 1 else 14, _SUIT_ORDER[door.suit])
        # Null (rank 0) is below everything.
        if door.rank == 0:
            value = (0, _SUIT_ORDER[door.suit])
        elif door.rank == 1:
            # Ace ranks high for bring-in comparison (14).
            value = (14, _SUIT_ORDER[door.suit])

        if best_value is None or value < best_value:
            best_value = value
            best_player_id = player.player_id

    if best_player_id is None:
        raise ValueError("No player with face-up cards to assign bring-in.")
    return best_player_id


def find_best_visible_hand_player(game_state: GameState) -> str:
    """Return the player_id whose visible (face-up) cards form the best hand.

    Used to determine first-to-act in Seven Card Stud betting rounds 2-5.
    If a player has fewer than 2 face-up cards, they are considered weakest.
    Ties resolved by seat order starting from left of dealer.
    """
    active = [p for p in game_state.players if not p.is_folded and not p.is_eliminated_this_hand]

    best_player_id: str | None = None
    best_value: int = -1

    for player in active:
        face_up_cards = [pc.card for pc in player.hole_cards if pc.is_face_up]
        if len(face_up_cards) < 2:
            # Can't evaluate; treat as worst (value 0).
            value = 0
        else:
            try:
                result = _EVALUATOR.evaluate(
                    face_up_cards,
                    game_state.deck_config,
                    direction=EvalDirection.HIGH,
                )
                value = result.high_value
            except Exception:
                value = 0

        if best_player_id is None or value > best_value:
            best_value = value
            best_player_id = player.player_id

    if best_player_id is None:
        raise ValueError("No active players to find best visible hand.")
    return best_player_id


def initialize_betting_round(
    game_state: GameState,
    first_to_act_id: str,
    is_bring_in_round: bool,
    ante: int,
    bring_in_amount: int,
    small_bet: int,
    big_bet: int,
) -> None:
    """Set up BettingState for the start of a betting round.

    For bring-in rounds: first_to_act_id posts the bring-in (forced),
    and active_player_index is set to the player after them.

    For standard rounds: first_to_act_id gets the first free action.
    """
    bs = game_state.betting_state
    bs.betting_round += 1
    bs.players_acted = []
    bs.last_aggressor_id = None

    # In Seven Card Stud, small bet applies to rounds 1-2, big bet to rounds 3-5.
    bet_size = small_bet if bs.betting_round <= 2 else big_bet
    bs.minimum_raise = bet_size

    if is_bring_in_round:
        bs.current_bet = bring_in_amount
        bs.bring_in = bring_in_amount
        # The bring-in is a forced action; record it immediately.
        poster = game_state.get_player(first_to_act_id)
        amount_paid = min(bring_in_amount, poster.chip_stack)
        poster.chip_stack -= amount_paid
        poster.current_bet = amount_paid
        poster.total_bet_this_round = amount_paid
        bs.players_acted.append(first_to_act_id)
        game_state.record_event(EventType.ANTE_POSTED, first_to_act_id, amount=amount_paid)

        # First free-action player is the one after the bring-in poster.
        _advance_to_next_active(game_state, first_to_act_id)
    else:
        bs.current_bet = 0
        bs.bring_in = None
        _set_active_player(game_state, first_to_act_id)

    # Reset per-round bet tracking for all players.
    for player in game_state.players:
        player.current_bet = 0
        player.total_bet_this_round = 0

    if is_bring_in_round:
        poster = game_state.get_player(first_to_act_id)
        poster.current_bet = min(bring_in_amount, poster.chip_stack)
        poster.total_bet_this_round = poster.current_bet


def get_legal_betting_actions(
    game_state: GameState,
    player_id: str,
    small_bet: int,
    big_bet: int,
) -> list[LegalAction]:
    """Return the list of legal betting actions for the given player.

    Returns an empty list if it is not the player's turn or the player is
    folded.
    """
    player = game_state.get_player(player_id)

    if player.is_folded or player.is_eliminated_this_hand:
        return []

    active = game_state.active_players()
    if not active:
        return []

    active_ids = [p.player_id for p in active]
    if not active_ids:
        return []

    if game_state.active_player_index >= len(game_state.players):
        return []

    current_active = game_state.players[game_state.active_player_index]
    if current_active.player_id != player_id:
        return []

    bs = game_state.betting_state
    bet_size = small_bet if bs.betting_round <= 2 else big_bet

    actions: list[LegalAction] = []

    to_call = bs.current_bet - player.total_bet_this_round
    to_call = max(0, to_call)

    # Always can fold.
    actions.append(LegalAction(action_type=ActionType.FOLD))

    if to_call == 0:
        # No bet to match; player can check or bet.
        actions.append(LegalAction(action_type=ActionType.CHECK))
        if player.chip_stack > 0:
            actions.append(LegalAction(
                action_type=ActionType.BET,
                min_amount=min(bet_size, player.chip_stack),
                max_amount=player.chip_stack,
            ))
    else:
        # There is a bet to call or raise.
        if to_call >= player.chip_stack:
            # All-in call.
            actions.append(LegalAction(
                action_type=ActionType.CALL,
                min_amount=player.chip_stack,
                max_amount=player.chip_stack,
            ))
        else:
            actions.append(LegalAction(
                action_type=ActionType.CALL,
                min_amount=to_call,
                max_amount=to_call,
            ))
            # Can raise if we have enough chips.
            raise_total = bs.current_bet + bet_size
            raise_additional = raise_total - player.total_bet_this_round
            if raise_additional < player.chip_stack:
                actions.append(LegalAction(
                    action_type=ActionType.RAISE,
                    min_amount=raise_additional,
                    max_amount=player.chip_stack,
                ))

    return actions


def apply_betting_action(
    game_state: GameState,
    player_id: str,
    action_type: ActionType,
    amount: int,
    pot_manager: Any,
) -> None:
    """Apply a single betting action and update GameState in place.

    pot_manager is the active PotManager for the hand.
    """
    from backend.game.pot import PotManager  # local import avoids circular ref

    player = game_state.get_player(player_id)
    bs = game_state.betting_state

    if action_type == ActionType.FOLD:
        player.is_folded = True
        bs.players_acted.append(player_id)
        game_state.action_has_occurred = True
        game_state.record_event(EventType.FOLD, player_id)

    elif action_type == ActionType.CHECK:
        bs.players_acted.append(player_id)
        game_state.action_has_occurred = True
        game_state.record_event(EventType.CHECK, player_id)

    elif action_type == ActionType.CALL:
        to_call = min(amount, player.chip_stack)
        player.chip_stack -= to_call
        player.current_bet += to_call
        player.total_bet_this_round += to_call
        pot_manager.add_bet(player_id, to_call)
        bs.players_acted.append(player_id)
        game_state.action_has_occurred = True
        game_state.record_event(EventType.CALL_MADE, player_id, amount=to_call)

    elif action_type == ActionType.BET:
        paid = min(amount, player.chip_stack)
        player.chip_stack -= paid
        player.current_bet = paid
        player.total_bet_this_round += paid
        bs.current_bet = player.total_bet_this_round
        bs.last_aggressor_id = player_id
        pot_manager.add_bet(player_id, paid)
        bs.players_acted = [player_id]
        game_state.action_has_occurred = True
        game_state.record_event(EventType.BET_PLACED, player_id, amount=paid)

    elif action_type == ActionType.RAISE:
        paid = min(amount, player.chip_stack)
        player.chip_stack -= paid
        player.current_bet += paid
        player.total_bet_this_round += paid
        bs.current_bet = player.total_bet_this_round
        bs.last_aggressor_id = player_id
        pot_manager.add_bet(player_id, paid)
        bs.players_acted = [player_id]
        game_state.action_has_occurred = True
        game_state.record_event(EventType.RAISE_MADE, player_id, amount=paid)

    # Handle all-in side pot creation.
    if player.chip_stack == 0 and not player.is_folded:
        all_player_ids = [p.player_id for p in game_state.players]
        pot_manager.create_side_pot(player_id, player.total_bet_this_round, all_player_ids)

    _advance_to_next_active(game_state, player_id)


def is_betting_round_complete(game_state: GameState) -> bool:
    """Return True when the betting round is over.

    The round ends when:
    - Only one active (non-folded) player remains, OR
    - All active players have acted and no player has an unmatched bet.
    """
    active = [
        p for p in game_state.players
        if not p.is_folded and not p.is_eliminated_this_hand
    ]

    if len(active) <= 1:
        return True

    bs = game_state.betting_state

    for player in active:
        if player.player_id not in bs.players_acted:
            return False
        if player.total_bet_this_round < bs.current_bet and player.chip_stack > 0:
            return False

    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _set_active_player(game_state: GameState, player_id: str) -> None:
    """Set active_player_index to the given player."""
    for i, p in enumerate(game_state.players):
        if p.player_id == player_id:
            game_state.active_player_index = i
            return


def _advance_to_next_active(game_state: GameState, after_player_id: str) -> None:
    """Advance active_player_index to the next non-folded, non-eliminated player."""
    n = len(game_state.players)
    start = None
    for i, p in enumerate(game_state.players):
        if p.player_id == after_player_id:
            start = i
            break
    if start is None:
        return

    for offset in range(1, n + 1):
        idx = (start + offset) % n
        p = game_state.players[idx]
        if not p.is_folded and not p.is_eliminated_this_hand:
            game_state.active_player_index = idx
            return
