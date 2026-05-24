"""PotManager: chip tracking and distribution for the Game Layer.

Manages the main pot, side pots, carry amounts, and ante amounts for one hand.
Distributes chips to winners at showdown. All chip movements are recorded here
and later written to the chip ledger by the caller.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.evaluators.base import WinnerResult
from backend.game.state import Pot, SidePot

logger = logging.getLogger(__name__)


class PotManager:
    """Tracks and distributes chips for one hand.

    Side pots are created automatically when a player goes all-in for less
    than the current bet. The all-in player is eligible for the main pot only.
    """

    def __init__(self, carry_amount: int = 0) -> None:
        self._pot = Pot(carry_amount=carry_amount)
        # Total chips contributed per player across the entire hand.
        self._contributions: dict[str, int] = {}
        # Caps per player: set when a player goes all-in.
        self._all_in_caps: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Chip input operations
    # ------------------------------------------------------------------

    def add_ante(self, player_id: str, amount: int) -> None:
        """Record an ante contribution from a player."""
        self._pot.ante_amount += amount
        self._pot.main_pot += amount
        self._contributions[player_id] = self._contributions.get(player_id, 0) + amount
        logger.debug("Ante: %s posted %d; pot total=%d", player_id, amount, self.get_total())

    def add_bet(self, player_id: str, amount: int) -> None:
        """Record a bet or call contribution from a player."""
        self._pot.main_pot += amount
        self._contributions[player_id] = self._contributions.get(player_id, 0) + amount
        logger.debug("Bet: %s added %d; pot total=%d", player_id, amount, self.get_total())

    def add_bid(self, player_id: str, amount: int) -> None:
        """Record an auction bid; goes directly into the pot."""
        self._pot.main_pot += amount
        self._contributions[player_id] = self._contributions.get(player_id, 0) + amount
        logger.debug("Bid: %s added %d; pot total=%d", player_id, amount, self.get_total())

    def apply_cascade_payment(self, player_id: str, amount: int) -> None:
        """Record a Guts cascade payment into the pot."""
        self._pot.main_pot += amount
        self._contributions[player_id] = self._contributions.get(player_id, 0) + amount
        logger.debug("Cascade: %s paid %d; pot total=%d", player_id, amount, self.get_total())

    def apply_carry(self, carry_amount: int) -> None:
        """Add a carried pot from a previous redeal."""
        self._pot.carry_amount += carry_amount
        logger.debug("Carry applied: +%d; pot total=%d", carry_amount, self.get_total())

    # ------------------------------------------------------------------
    # Side pot management
    # ------------------------------------------------------------------

    def create_side_pot(
        self, all_in_player_id: str, all_in_amount: int, all_player_ids: list[str]
    ) -> None:
        """Create a side pot when a player goes all-in for less than the full bet.

        Moves the excess from the main pot into a side pot that excludes the
        all-in player.
        """
        self._all_in_caps[all_in_player_id] = all_in_amount

        # The all-in player can only win the main pot capped at their total contribution.
        # Everything above that cap from other players goes into a side pot.
        capped_main = 0
        excess = 0

        for pid, contribution in self._contributions.items():
            capped = min(contribution, all_in_amount)
            capped_main += capped
            excess += contribution - capped

        side_eligible = [
            pid for pid in all_player_ids
            if pid != all_in_player_id
        ]

        if excess > 0:
            # Rebuild main pot to capped amount and create the side pot.
            old_main = self._pot.main_pot
            self._pot.main_pot = capped_main
            self._pot.side_pots.append(
                SidePot(amount=excess, eligible_player_ids=side_eligible)
            )
            logger.debug(
                "Side pot created: main=%d → %d, side=%d, eligible=%s",
                old_main, capped_main, excess, side_eligible,
            )

    # ------------------------------------------------------------------
    # Pot state
    # ------------------------------------------------------------------

    def get_total(self) -> int:
        """Return total chips across all pots including carry."""
        return self._pot.total()

    def get_pot(self) -> Pot:
        """Return the current Pot snapshot."""
        return self._pot

    def get_eligible_players(self, pot_index: int) -> list[str]:
        """Return the eligible player ids for a pot by index (0 = main pot)."""
        if pot_index == 0:
            return list(self._contributions.keys())
        side_index = pot_index - 1
        if 0 <= side_index < len(self._pot.side_pots):
            return self._pot.side_pots[side_index].eligible_player_ids
        return []

    # ------------------------------------------------------------------
    # Distribution
    # ------------------------------------------------------------------

    def distribute(
        self,
        high_result: WinnerResult,
        low_result: WinnerResult | None = None,
    ) -> dict[str, int]:
        """Distribute pots to winners and return a delta map: player_id → chips won.

        For a split-pot hand (high_result and low_result), distributes the
        main pot 50/50 between the high and low winners (each half going to
        the winner of that direction). Ties within a direction are split
        further among tied players.

        For a simple winner-takes-all hand pass only high_result.
        """
        winnings: dict[str, int] = {}

        total_distributable = self._pot.main_pot + self._pot.carry_amount

        if low_result is None:
            # Simple case: winner(s) split the full pot.
            _distribute_among(high_result.winners, total_distributable, winnings)
        else:
            # Split pot: high and low each get half.
            half, remainder = divmod(total_distributable, 2)
            _distribute_among(high_result.winners, half + remainder, winnings)
            _distribute_among(low_result.winners, half, winnings)

        # Distribute any side pots to their eligible winners.
        for side_pot in self._pot.side_pots:
            eligible_high_winners = [
                w for w in high_result.winners if w in side_pot.eligible_player_ids
            ]
            if not eligible_high_winners and low_result:
                eligible_low_winners = [
                    w for w in low_result.winners if w in side_pot.eligible_player_ids
                ]
                eligible_high_winners = eligible_low_winners
            if eligible_high_winners:
                _distribute_among(eligible_high_winners, side_pot.amount, winnings)

        logger.debug("Pot distribution: %s", winnings)
        return winnings


def _distribute_among(player_ids: list[str], amount: int, winnings: dict[str, int]) -> None:
    """Split amount among player_ids, adding integer chips to the winnings dict.

    Remainders go to the first player in the list.
    """
    if not player_ids or amount <= 0:
        return
    share, remainder = divmod(amount, len(player_ids))
    for i, pid in enumerate(player_ids):
        each = share + (remainder if i == 0 else 0)
        winnings[pid] = winnings.get(pid, 0) + each
