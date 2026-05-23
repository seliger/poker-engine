"""PokerHandEvaluator: standard poker hand ranking for the Evaluation Layer.

Wraps PokerKit for standard 52-card evaluation and extends it for non-standard
cases (wild cards, Null cards, Orbs) in later phases.  Phase 1 scope: standard
52-card evaluation with no wilds and no Null cards.

PokerKit is imported ONLY in this file.  No other module may import PokerKit.
"""

from __future__ import annotations

import logging
import random
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

# PokerKit import — this is the ONLY file in the project that imports PokerKit.
from pokerkit.hands import StandardHighHand
from pokerkit.lookups import Label as _PKLabel
from pokerkit.utilities import Rank as _PKRank, Suit as _PKSuit

from backend.deck.card import Card, DeckConfig, Suit
from backend.evaluators.base import (
    AceDualValue,
    BaseEvaluatedHand,
    BaseEvaluator,
    ComparisonResult,
    Declaration,
    DeclareResult,
    EvalDirection,
    HandRank,
    WinnerResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error types  (namespaced to PokerHandEvaluator per spec)
# ---------------------------------------------------------------------------

class InvalidHandError(Exception):
    """Raised when evaluate() receives an impossible card combination."""


class WildResolutionError(Exception):
    """Raised when wild card resolution finds no valid assignment (Phase 3+)."""


class IncomparableHandError(Exception):
    """Raised when compare() receives two partial hands."""


# ---------------------------------------------------------------------------
# Card conversion helpers
# ---------------------------------------------------------------------------

_OUR_RANK_TO_PK: dict[int, str] = {
    1: "A", 2: "2", 3: "3", 4: "4", 5: "5",
    6: "6", 7: "7", 8: "8", 9: "9", 10: "T",
    11: "J", 12: "Q", 13: "K",
}

_OUR_SUIT_TO_PK: dict[Suit, str] = {
    Suit.CLUBS: "c",
    Suit.DIAMONDS: "d",
    Suit.HEARTS: "h",
    Suit.SPADES: "s",
    # Suit.ORBS has no PokerKit equivalent; handled via extension in Phase 3.
}

_PK_RANK_TO_OURS: dict[_PKRank, int] = {
    _PKRank.ACE: 1,
    _PKRank.DEUCE: 2,
    _PKRank.TREY: 3,
    _PKRank.FOUR: 4,
    _PKRank.FIVE: 5,
    _PKRank.SIX: 6,
    _PKRank.SEVEN: 7,
    _PKRank.EIGHT: 8,
    _PKRank.NINE: 9,
    _PKRank.TEN: 10,
    _PKRank.JACK: 11,
    _PKRank.QUEEN: 12,
    _PKRank.KING: 13,
}

_PK_SUIT_TO_OURS: dict[_PKSuit, Suit] = {
    _PKSuit.CLUB: Suit.CLUBS,
    _PKSuit.DIAMOND: Suit.DIAMONDS,
    _PKSuit.HEART: Suit.HEARTS,
    _PKSuit.SPADE: Suit.SPADES,
}

# Map PokerKit Label → HandRank (ROYAL_FLUSH detection is done separately).
_PK_LABEL_TO_HAND_RANK: dict[_PKLabel, HandRank] = {
    _PKLabel.HIGH_CARD: HandRank.HIGH_CARD,
    _PKLabel.ONE_PAIR: HandRank.ONE_PAIR,
    _PKLabel.TWO_PAIR: HandRank.TWO_PAIR,
    _PKLabel.THREE_OF_A_KIND: HandRank.THREE_OF_A_KIND,
    _PKLabel.STRAIGHT: HandRank.STRAIGHT,
    _PKLabel.FLUSH: HandRank.FLUSH,
    _PKLabel.FULL_HOUSE: HandRank.FULL_HOUSE,
    _PKLabel.FOUR_OF_A_KIND: HandRank.FOUR_OF_A_KIND,
    _PKLabel.STRAIGHT_FLUSH: HandRank.STRAIGHT_FLUSH,
}

_HAND_RANK_DISPLAY: dict[HandRank, str] = {
    HandRank.HIGH_CARD: "High card",
    HandRank.ONE_PAIR: "One pair",
    HandRank.TWO_PAIR: "Two pair",
    HandRank.THREE_OF_A_KIND: "Three of a kind",
    HandRank.STRAIGHT: "Straight",
    HandRank.FLUSH: "Flush",
    HandRank.FULL_HOUSE: "Full house",
    HandRank.FOUR_OF_A_KIND: "Four of a kind",
    HandRank.FIVE_OF_A_KIND: "Five of a kind",
    HandRank.STRAIGHT_FLUSH: "Straight flush",
    HandRank.ROYAL_FLUSH: "Royal flush",
}

# ---------------------------------------------------------------------------
# EvaluatedHand
# ---------------------------------------------------------------------------

@dataclass
class EvaluatedHand(BaseEvaluatedHand):
    """The return type of PokerHandEvaluator.evaluate().

    Inherits is_partial, deck_config, display_name, high_value, low_value
    from BaseEvaluatedHand.

    high_value: PokerKit StandardHighHand entry index; higher = stronger.
    low_value:  Custom composite score; higher = better low hand.
    all_combinations: every evaluated C(n,5) subset; used by the UI to show
                      why the best five were chosen.
    """

    hand_rank: HandRank
    best_five: list[Card]
    wild_assignments: dict[Card, Card]
    kickers: list[Card]
    is_null_anchored: bool
    all_combinations: list[Any] = field(default_factory=list)


# ---------------------------------------------------------------------------
# PokerHandEvaluator
# ---------------------------------------------------------------------------

class PokerHandEvaluator(BaseEvaluator):
    """Standard poker hand evaluator using PokerKit for 52-card evaluation.

    Phase 1 scope: standard 52-card evaluation, no wilds, no Null cards.
    Wild card resolution and Null/Orbs extensions are added in Phase 3.

    Parameters
    ----------
    royal_flush_beats_straight_flush:
        When True, HandRank.ROYAL_FLUSH (10) is used in rank-level comparison,
        guaranteeing a Royal Flush always beats any Straight Flush.
        When False (default), both receive HandRank.STRAIGHT_FLUSH for rank
        comparison; the Royal Flush still wins via high_value since it carries
        the highest PokerKit entry index.
    """

    def __init__(self, royal_flush_beats_straight_flush: bool = False) -> None:
        self._royal_sf: bool = royal_flush_beats_straight_flush
        self._freq_cache: dict[tuple[Any, ...], dict[HandRank, float]] = {}

    # ------------------------------------------------------------------
    # Public interface — BaseEvaluator
    # ------------------------------------------------------------------

    def evaluate(
        self,
        cards: list[Card],
        deck_config: DeckConfig,
        wild_ranks: list[int] | None = None,
        wild_suits: list[Suit] | None = None,
        direction: EvalDirection = EvalDirection.HIGH,
        declaration: Declaration = Declaration.HIGH,
    ) -> EvaluatedHand:
        """Evaluate the best poker hand from the provided cards.

        Accepts 2–10 cards.  Fewer than 5 produce a partial evaluation.
        """
        if len(cards) < 2:
            raise InvalidHandError(
                f"At least 2 cards required; received {len(cards)}"
            )
        if len(cards) > 10:
            raise InvalidHandError(
                f"At most 10 cards supported; received {len(cards)}"
            )
        self._assert_no_duplicates(cards)

        is_partial = len(cards) < 5

        if is_partial:
            return self._evaluate_partial(cards, deck_config, direction, declaration)

        if len(cards) == 5:
            card_index = self._card_index(cards)
            hand = self._evaluate_exactly_five(cards, deck_config, direction, card_index)
            return hand

        # More than 5 cards — find best five.
        return self._evaluate_best_five(cards, deck_config, direction, declaration)

    def compare(
        self,
        hand_a: BaseEvaluatedHand,
        hand_b: BaseEvaluatedHand,
        direction: EvalDirection,
    ) -> ComparisonResult:
        """Compare two hands.  Raises IncomparableHandError for partial hands."""
        if hand_a.is_partial or hand_b.is_partial:
            raise IncomparableHandError(
                "Partial hands cannot be compared at showdown."
            )
        if not isinstance(hand_a, EvaluatedHand) or not isinstance(hand_b, EvaluatedHand):
            raise IncomparableHandError(
                "Both hands must be EvaluatedHand instances."
            )

        if direction == EvalDirection.HIGH:
            return self._compare_high(hand_a, hand_b)
        return self._compare_low(hand_a, hand_b)

    def determine_winners(
        self,
        evaluated_hands: dict[str, BaseEvaluatedHand],
        direction: EvalDirection,
    ) -> WinnerResult:
        """Find the winner(s) from a dict of player_id → EvaluatedHand."""
        if not evaluated_hands:
            raise InvalidHandError("No hands provided to determine_winners.")

        players = list(evaluated_hands.keys())
        best_hand = evaluated_hands[players[0]]

        for pid in players[1:]:
            hand = evaluated_hands[pid]
            if self.compare(hand, best_hand, direction) == ComparisonResult.WIN:
                best_hand = hand

        winners = [
            pid
            for pid, hand in evaluated_hands.items()
            if self.compare(hand, best_hand, direction) != ComparisonResult.LOSE
        ]

        is_tie = len(winners) > 1
        return WinnerResult(
            winners=winners,
            winning_hand=best_hand,
            is_tie=is_tie,
            pot_split=is_tie,
        )

    def evaluate_for_declare(
        self,
        cards: list[Card],
        deck_config: DeckConfig,
        declaration: Declaration,
        wild_ranks: list[int] | None = None,
    ) -> DeclareResult:
        """Evaluate a hand in the context of a high-low chip-declare.

        For BOTH declaration, the best five cards may differ between HIGH and
        LOW evaluations.  Scoop-or-bust enforcement is the Game Layer's job.
        """
        if declaration == Declaration.HIGH:
            high_hand = self.evaluate(
                cards, deck_config, direction=EvalDirection.HIGH,
                declaration=declaration,
            )
            return DeclareResult(
                declaration=declaration,
                high_hand=high_hand,
                low_hand=None,
                is_both_ways=False,
                must_win_both=False,
            )

        if declaration == Declaration.LOW:
            low_hand = self.evaluate(
                cards, deck_config, direction=EvalDirection.LOW,
                declaration=declaration,
            )
            return DeclareResult(
                declaration=declaration,
                high_hand=None,
                low_hand=low_hand,
                is_both_ways=False,
                must_win_both=False,
            )

        # BOTH: evaluate independently for each direction.
        high_hand = self.evaluate(
            cards, deck_config, direction=EvalDirection.HIGH,
            declaration=Declaration.BOTH,
        )
        low_hand = self.evaluate(
            cards, deck_config, direction=EvalDirection.LOW,
            declaration=Declaration.BOTH,
        )
        return DeclareResult(
            declaration=declaration,
            high_hand=high_hand,
            low_hand=low_hand,
            is_both_ways=True,
            must_win_both=True,
        )

    def ace_dual_value(
        self,
        direction: EvalDirection,
        declaration: Declaration,
    ) -> AceDualValue:
        """Return the rank integer(s) Ace assumes.

        HIGH direction → 14.
        LOW direction  → 1.
        BOTH           → (1, 14): Ace is 1 for LOW and 14 for HIGH simultaneously.
        """
        if declaration == Declaration.BOTH:
            return (1, 14)
        if direction == EvalDirection.LOW:
            return 1
        return 14

    def calculate_hand_frequencies(
        self,
        deck_config: DeckConfig,
        wild_ranks: list[int] | None = None,
        hand_size: int = 5,
    ) -> dict[HandRank, float]:
        """Return approximate hand frequency for each rank via Monte Carlo sampling.

        Results are cached by (deck_config, wild_ranks, hand_size).  Changing
        the DeckConfig or wild_ranks automatically yields a fresh result.
        """
        cache_key = (
            deck_config.to_json(),
            tuple(sorted(wild_ranks or [])),
            hand_size,
        )
        if cache_key in self._freq_cache:
            return self._freq_cache[cache_key]

        from backend.deck.deck import Deck  # local import to avoid circular dependency

        all_cards = Deck(deck_config).cards()
        sample_size = 100_000
        counts: dict[HandRank, int] = {rank: 0 for rank in HandRank}

        for _ in range(sample_size):
            sample = random.sample(all_cards, min(hand_size, len(all_cards)))
            try:
                result = self.evaluate(
                    sample, deck_config, direction=EvalDirection.HIGH
                )
                if not result.is_partial:
                    counts[result.hand_rank] += 1
            except Exception:
                continue

        total = sum(counts.values())
        if total == 0:
            return {}

        freqs: dict[HandRank, float] = {
            rank: count / total for rank, count in counts.items()
        }
        self._freq_cache[cache_key] = freqs
        logger.debug("Computed hand frequencies for %s (sample=%d)", cache_key, total)
        return freqs

    def invalidate_frequency_cache(self) -> None:
        """Clear the hand frequency cache."""
        self._freq_cache.clear()

    # ------------------------------------------------------------------
    # Internal evaluation helpers
    # ------------------------------------------------------------------

    def _evaluate_exactly_five(
        self,
        five: list[Card],
        deck_config: DeckConfig,
        direction: EvalDirection,
        card_index: dict[tuple[int, Suit], Card],
    ) -> EvaluatedHand:
        """Evaluate exactly 5 cards using PokerKit."""
        pk_str = "".join(self._to_pk_str(c) for c in five)
        try:
            pk_hand = StandardHighHand(pk_str)
        except ValueError as exc:
            raise InvalidHandError(
                f"PokerKit rejected card combination '{pk_str}': {exc}"
            ) from exc

        entry = StandardHighHand.lookup.get_entry(pk_str)
        hand_rank = self._resolve_hand_rank(entry.label, five)
        best_five = [
            self._from_pk_card(pkc, card_index) for pkc in pk_hand.cards
        ]
        low_value = self._compute_low_value(hand_rank, five)

        return EvaluatedHand(
            is_partial=False,
            deck_config=deck_config,
            display_name=_HAND_RANK_DISPLAY[hand_rank],
            high_value=entry.index,
            low_value=low_value,
            hand_rank=hand_rank,
            best_five=best_five,
            wild_assignments={},
            kickers=best_five,
            is_null_anchored=False,
        )

    def _evaluate_best_five(
        self,
        cards: list[Card],
        deck_config: DeckConfig,
        direction: EvalDirection,
        declaration: Declaration,
    ) -> EvaluatedHand:
        """Select the best 5-card combination from n > 5 cards."""
        card_index = self._card_index(cards)
        best: EvaluatedHand | None = None
        all_combos: list[Any] = []

        for five in combinations(cards, 5):
            hand = self._evaluate_exactly_five(
                list(five), deck_config, direction, card_index
            )
            all_combos.append((list(five), hand))

            if best is None:
                best = hand
            else:
                if direction == EvalDirection.HIGH:
                    if hand.high_value > best.high_value:
                        best = hand
                else:
                    if hand.low_value > best.low_value:
                        best = hand

        assert best is not None
        best.all_combinations = all_combos
        return best

    def _evaluate_partial(
        self,
        cards: list[Card],
        deck_config: DeckConfig,
        direction: EvalDirection,
        declaration: Declaration,
    ) -> EvaluatedHand:
        """Evaluate a hand of fewer than 5 cards for in-progress estimation."""
        rank_counts = Counter(c.rank for c in cards)
        max_group = max(rank_counts.values())
        pair_count = sum(1 for v in rank_counts.values() if v == 2)

        if max_group >= 4:
            hand_rank = HandRank.FOUR_OF_A_KIND
        elif max_group == 3:
            hand_rank = HandRank.THREE_OF_A_KIND
        elif max_group == 2:
            hand_rank = HandRank.TWO_PAIR if pair_count >= 2 else HandRank.ONE_PAIR
        else:
            hand_rank = HandRank.HIGH_CARD

        low_value = self._compute_low_value(hand_rank, cards)
        rough_high = hand_rank.value * 1_000

        return EvaluatedHand(
            is_partial=True,
            deck_config=deck_config,
            display_name=_HAND_RANK_DISPLAY[hand_rank] + " (partial)",
            high_value=rough_high,
            low_value=low_value,
            hand_rank=hand_rank,
            best_five=cards,
            wild_assignments={},
            kickers=cards,
            is_null_anchored=False,
        )

    # ------------------------------------------------------------------
    # Comparison helpers
    # ------------------------------------------------------------------

    def _compare_high(
        self, hand_a: EvaluatedHand, hand_b: EvaluatedHand
    ) -> ComparisonResult:
        """Compare two hands in HIGH direction."""
        rank_a = self._effective_rank(hand_a.hand_rank)
        rank_b = self._effective_rank(hand_b.hand_rank)

        if rank_a != rank_b:
            return ComparisonResult.WIN if rank_a > rank_b else ComparisonResult.LOSE

        if hand_a.high_value > hand_b.high_value:
            return ComparisonResult.WIN
        if hand_a.high_value < hand_b.high_value:
            return ComparisonResult.LOSE
        return ComparisonResult.TIE

    def _compare_low(
        self, hand_a: EvaluatedHand, hand_b: EvaluatedHand
    ) -> ComparisonResult:
        """Compare two hands in LOW direction.

        Lower HandRank = better low hand.  Within same rank, lower cards
        (higher low_value) = better.
        """
        if hand_a.hand_rank != hand_b.hand_rank:
            # Lower rank wins in LOW direction.
            return (
                ComparisonResult.WIN
                if hand_a.hand_rank < hand_b.hand_rank
                else ComparisonResult.LOSE
            )

        if hand_a.low_value > hand_b.low_value:
            return ComparisonResult.WIN
        if hand_a.low_value < hand_b.low_value:
            return ComparisonResult.LOSE
        return ComparisonResult.TIE

    def _effective_rank(self, rank: HandRank) -> HandRank:
        """Return the HandRank used for rank-level comparison in HIGH direction.

        When royal_flush_beats_straight_flush is False (default), ROYAL_FLUSH
        is treated as STRAIGHT_FLUSH for rank comparison.  The Royal Flush
        still wins via its superior high_value (PokerKit assigns it the highest
        possible Straight Flush index).
        """
        if rank == HandRank.ROYAL_FLUSH and not self._royal_sf:
            return HandRank.STRAIGHT_FLUSH
        return rank

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_pk_str(card: Card) -> str:
        """Convert a Card to a PokerKit card string such as 'Ac' or 'Td'."""
        return _OUR_RANK_TO_PK[card.rank] + _OUR_SUIT_TO_PK[card.suit]

    @staticmethod
    def _from_pk_card(
        pk_card: Any,
        card_index: dict[tuple[int, Suit], Card],
    ) -> Card:
        """Convert a PokerKit Card back to our Card using a pre-built index."""
        our_rank = _PK_RANK_TO_OURS[pk_card.rank]
        our_suit = _PK_SUIT_TO_OURS[pk_card.suit]
        return card_index[(our_rank, our_suit)]

    @staticmethod
    def _card_index(cards: list[Card]) -> dict[tuple[int, Suit], Card]:
        """Build a (rank, suit) → Card lookup for PokerKit reverse mapping."""
        return {(c.rank, c.suit): c for c in cards}

    def _resolve_hand_rank(
        self, pk_label: _PKLabel, cards: list[Card]
    ) -> HandRank:
        """Map a PokerKit label to our HandRank, detecting Royal Flush."""
        rank = _PK_LABEL_TO_HAND_RANK[pk_label]
        if rank == HandRank.STRAIGHT_FLUSH and self._is_royal_flush(cards):
            return HandRank.ROYAL_FLUSH
        return rank

    @staticmethod
    def _is_royal_flush(cards: list[Card]) -> bool:
        """True when the five cards form A-K-Q-J-T of the same suit."""
        ranks = {c.rank for c in cards}
        suits = {c.suit for c in cards}
        return ranks == {1, 10, 11, 12, 13} and len(suits) == 1

    @staticmethod
    def _compute_low_value(hand_rank: HandRank, cards: list[Card]) -> int:
        """Compute a single integer where higher = better low hand.

        Encoding:
          (MAX_HAND_RANK - hand_rank) * SCALE + inverted_kicker_score

        Lower HandRank → higher inverted component → higher low_value (better).
        Lower card rank → higher inverted kicker contribution → higher low_value.
        Ace is treated as rank 1 (lowest card) in low evaluation, which is
        already the stored rank on our Card objects.
        """
        BASE = 15          # > max card rank (13) + 1
        N = 5
        SCALE = BASE ** N  # 759375; separates hand rank tiers

        # Sort ranks descending: highest card first (per low comparison spec).
        # Ace = 1 stays as 1; it sorts to the end of a descending list, giving
        # it the highest inverted contribution (14 - 1 = 13), correctly marking
        # it as the best low card.
        ranks = sorted((c.rank for c in cards), reverse=True)
        # Pad or trim to N cards for a uniform encoding.
        while len(ranks) < N:
            ranks.append(14)   # worst possible padding rank
        ranks = ranks[:N]

        kicker_score = sum(
            (14 - r) * (BASE ** (N - 1 - i)) for i, r in enumerate(ranks)
        )

        max_rank = HandRank.ROYAL_FLUSH.value   # 10
        inverted_rank = max_rank - hand_rank.value

        return inverted_rank * SCALE + kicker_score

    @staticmethod
    def _assert_no_duplicates(cards: list[Card]) -> None:
        """Raise InvalidHandError if any two cards share rank+suit."""
        seen: set[Card] = set()
        for card in cards:
            if card in seen:
                raise InvalidHandError(
                    f"Duplicate card in hand: {card.shorthand()}"
                )
            seen.add(card)
