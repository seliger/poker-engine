"""Unit tests for PotManager — Phase 1 scope.

Covers pot contribution tracking, side pot creation on all-in, and
distribution to single winners and tied winners.
"""

import pytest

from backend.evaluators.base import WinnerResult
from backend.evaluators.poker_hand_evaluator import EvaluatedHand
from backend.deck.card import DeckConfig, Card, Suit
from backend.evaluators.base import HandRank
from backend.game.pot import PotManager
from backend.game.state import Pot, SidePot


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _dummy_hand() -> EvaluatedHand:
    """Return a minimal EvaluatedHand for WinnerResult construction."""
    return EvaluatedHand(
        is_partial=False,
        deck_config=DeckConfig.STANDARD(),
        display_name="One Pair",
        high_value=1000,
        low_value=500,
        hand_rank=HandRank.ONE_PAIR,
        best_five=[],
        wild_assignments={},
        kickers=[],
        is_null_anchored=False,
    )


# ---------------------------------------------------------------------------
# Basic contribution tests
# ---------------------------------------------------------------------------

class TestBasicContributions:

    def test_ante_adds_to_main_pot(self) -> None:
        pm = PotManager()
        pm.add_ante("alice", 2)
        assert pm.get_total() == 2

    def test_multiple_antes(self) -> None:
        pm = PotManager()
        pm.add_ante("alice", 2)
        pm.add_ante("bob", 2)
        pm.add_ante("carol", 2)
        assert pm.get_total() == 6

    def test_bet_adds_to_main_pot(self) -> None:
        pm = PotManager()
        pm.add_bet("alice", 4)
        assert pm.get_total() == 4

    def test_carry_included_in_total(self) -> None:
        pm = PotManager(carry_amount=10)
        pm.add_ante("alice", 2)
        assert pm.get_total() == 12

    def test_apply_carry_adds_to_carry_amount(self) -> None:
        pm = PotManager()
        pm.apply_carry(8)
        assert pm.get_total() == 8

    def test_cascade_payment_adds_to_main_pot(self) -> None:
        pm = PotManager()
        pm.apply_cascade_payment("alice", 6)
        assert pm.get_total() == 6


# ---------------------------------------------------------------------------
# Side pot tests
# ---------------------------------------------------------------------------

class TestSidePots:

    def test_side_pot_created_on_all_in(self) -> None:
        pm = PotManager()
        # alice goes all-in for 3; bob has 10.
        pm.add_ante("alice", 3)
        pm.add_ante("bob", 10)
        pm.create_side_pot("alice", 3, ["alice", "bob"])
        pot = pm.get_pot()
        assert len(pot.side_pots) == 1

    def test_all_in_player_excluded_from_side_pot(self) -> None:
        pm = PotManager()
        pm.add_ante("alice", 3)
        pm.add_ante("bob", 10)
        pm.create_side_pot("alice", 3, ["alice", "bob"])
        pot = pm.get_pot()
        assert "alice" not in pot.side_pots[0].eligible_player_ids
        assert "bob" in pot.side_pots[0].eligible_player_ids

    def test_side_pot_amount_is_excess_over_all_in_cap(self) -> None:
        pm = PotManager()
        # alice all-in for 3; bob puts in 10; excess = (10-3) = 7 in side pot.
        pm.add_ante("alice", 3)
        pm.add_ante("bob", 10)
        pm.create_side_pot("alice", 3, ["alice", "bob"])
        pot = pm.get_pot()
        assert pot.side_pots[0].amount == 7

    def test_main_pot_capped_at_all_in_contributions(self) -> None:
        pm = PotManager()
        pm.add_ante("alice", 3)
        pm.add_ante("bob", 10)
        pm.create_side_pot("alice", 3, ["alice", "bob"])
        pot = pm.get_pot()
        # main pot should be alice(3) + bob(min 3) = 6
        assert pot.main_pot == 6


# ---------------------------------------------------------------------------
# Distribution tests
# ---------------------------------------------------------------------------

class TestDistribution:

    def test_single_winner_takes_full_pot(self) -> None:
        pm = PotManager()
        pm.add_ante("alice", 5)
        pm.add_ante("bob", 5)
        winner_result = WinnerResult(
            winners=["alice"],
            winning_hand=_dummy_hand(),
            is_tie=False,
            pot_split=False,
        )
        dist = pm.distribute(winner_result)
        assert dist["alice"] == 10

    def test_tied_winners_split_pot_evenly(self) -> None:
        pm = PotManager()
        pm.add_ante("alice", 5)
        pm.add_ante("bob", 5)
        winner_result = WinnerResult(
            winners=["alice", "bob"],
            winning_hand=_dummy_hand(),
            is_tie=True,
            pot_split=True,
        )
        dist = pm.distribute(winner_result)
        assert dist["alice"] == 5
        assert dist["bob"] == 5

    def test_odd_chip_goes_to_first_winner(self) -> None:
        pm = PotManager()
        pm.add_ante("alice", 5)
        pm.add_ante("bob", 4)  # 9 total, split between 2 = 4+1 remainder
        winner_result = WinnerResult(
            winners=["alice", "bob"],
            winning_hand=_dummy_hand(),
            is_tie=True,
            pot_split=True,
        )
        dist = pm.distribute(winner_result)
        assert dist["alice"] + dist["bob"] == 9
        # First winner gets the odd chip.
        assert dist["alice"] == 5

    def test_carry_amount_included_in_distribution(self) -> None:
        pm = PotManager(carry_amount=10)
        pm.add_ante("alice", 5)
        winner_result = WinnerResult(
            winners=["alice"],
            winning_hand=_dummy_hand(),
            is_tie=False,
            pot_split=False,
        )
        dist = pm.distribute(winner_result)
        assert dist["alice"] == 15

    def test_side_pot_distributed_to_eligible_winner(self) -> None:
        pm = PotManager()
        pm.add_ante("alice", 3)
        pm.add_ante("bob", 10)
        pm.create_side_pot("alice", 3, ["alice", "bob"])
        # Bob wins both main and side pot (alice was all-in).
        winner_result = WinnerResult(
            winners=["bob"],
            winning_hand=_dummy_hand(),
            is_tie=False,
            pot_split=False,
        )
        dist = pm.distribute(winner_result)
        # Bob should win the side pot amount too.
        assert dist.get("bob", 0) >= 7
