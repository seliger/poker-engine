"""Tier 1 rule-based bot for the Game Layer.

Configured via aggression, bluff_frequency, and risk_tolerance from
house_rules.json. Each bot instance has slight personality variance applied
at construction time so bots do not all behave identically.

The bot receives only a PlayerView (the same information a human player sees)
and returns a PlayerAction from the legal actions list.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any

from backend.evaluators.base import HandRank
from backend.game.variants.base import PlayerAction
from backend.game.visibility import ActionType, LegalAction, PlayerView

logger = logging.getLogger(__name__)

# Hand strength estimates by rank: 0.0 (worst) to 1.0 (best).
# Used to map the bot's current partial evaluation to a decision threshold.
_HAND_STRENGTH: dict[HandRank, float] = {
    HandRank.HIGH_CARD: 0.10,
    HandRank.ONE_PAIR: 0.30,
    HandRank.TWO_PAIR: 0.50,
    HandRank.THREE_OF_A_KIND: 0.65,
    HandRank.STRAIGHT: 0.75,
    HandRank.FLUSH: 0.80,
    HandRank.FULL_HOUSE: 0.88,
    HandRank.FOUR_OF_A_KIND: 0.94,
    HandRank.FIVE_OF_A_KIND: 0.97,
    HandRank.STRAIGHT_FLUSH: 0.97,
    HandRank.ROYAL_FLUSH: 0.99,
    HandRank.NATURAL_SEVENS: 1.00,
}


@dataclass
class BotPersonality:
    """Per-instance personality with variance applied from the base config."""
    aggression: float
    bluff_frequency: float
    risk_tolerance: float


class RuleBasedBot:
    """Tier 1 rule-based bot for all poker hand ranking variants.

    Parameters
    ----------
    aggression:
        Base aggression level (0.0–1.0). Higher → more likely to bet/raise.
    bluff_frequency:
        Probability of bluffing on a weak hand (0.0–1.0).
    risk_tolerance:
        Controls willingness to call or stay in weak positions (0.0–1.0).
    personality_variance:
        Random variance applied to each parameter at construction time.
    """

    def __init__(
        self,
        aggression: float = 0.5,
        bluff_frequency: float = 0.15,
        risk_tolerance: float = 0.5,
        personality_variance: float = 0.1,
    ) -> None:
        def _vary(base: float) -> float:
            delta = random.uniform(-personality_variance, personality_variance)
            return max(0.0, min(1.0, base + delta))

        self._personality = BotPersonality(
            aggression=_vary(aggression),
            bluff_frequency=_vary(bluff_frequency),
            risk_tolerance=_vary(risk_tolerance),
        )
        logger.debug(
            "RuleBasedBot created: aggression=%.2f bluff=%.2f risk=%.2f",
            self._personality.aggression,
            self._personality.bluff_frequency,
            self._personality.risk_tolerance,
        )

    @property
    def personality(self) -> BotPersonality:
        """Return this bot's personality parameters."""
        return self._personality

    def decide(
        self,
        player_view: PlayerView,
        legal_actions: list[LegalAction],
    ) -> PlayerAction:
        """Choose an action from legal_actions based on personality and hand strength.

        The returned action is always in the legal_actions list.
        """
        if not legal_actions:
            raise ValueError("decide() called with empty legal_actions list")

        action_types = {la.action_type for la in legal_actions}
        hand_score = self._estimate_hand_score(player_view)
        bluffing = random.random() < self._personality.bluff_frequency

        # Score to use for decision: actual strength or bluff score.
        effective_score = hand_score if not bluffing else min(1.0, hand_score + 0.4)

        return self._select_action(
            legal_actions, action_types, effective_score, player_view
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _estimate_hand_score(self, player_view: PlayerView) -> float:
        """Return a 0.0–1.0 score from the current hand strength hint."""
        if player_view.hand_strength is None:
            return 0.3  # Unknown hand; play cautiously.
        hs = player_view.hand_strength
        if hs.hand_rank is None:
            return 0.3
        base = _HAND_STRENGTH.get(hs.hand_rank, 0.3)
        # Partial hands are penalized since we don't know the final strength.
        if hs.is_partial:
            base *= 0.85
        return base

    def _select_action(
        self,
        legal_actions: list[LegalAction],
        action_types: set[ActionType],
        effective_score: float,
        player_view: PlayerView,
    ) -> PlayerAction:
        """Map effective hand score + personality to a concrete PlayerAction.

        DECLARE phase: bot prefers HIGH, then BOTH; falls back to LOW.
        Betting phase — three tiers:
          Strong  (score >= bet_threshold)  → bet or raise
          Medium  (score >= call_threshold) → call or check
          Weak    (score <  call_threshold) → fold if possible, else check
        """
        # DECLARE phase: prefer HIGH; use score to decide BOTH vs HIGH.
        if ActionType.DECLARE_HIGH in action_types:
            if effective_score >= 0.7 and ActionType.DECLARE_BOTH in action_types:
                return PlayerAction(action_type=ActionType.DECLARE_BOTH)
            return PlayerAction(action_type=ActionType.DECLARE_HIGH)
        if ActionType.DECLARE_LOW in action_types:
            return PlayerAction(action_type=ActionType.DECLARE_LOW)
        if ActionType.DECLARE_BOTH in action_types:
            return PlayerAction(action_type=ActionType.DECLARE_BOTH)
        p = self._personality
        # Higher aggression → willing to bet/raise with weaker hands.
        bet_threshold = 0.75 - (p.aggression * 0.35)
        # Higher risk_tolerance → willing to call with weaker hands.
        call_threshold = 0.40 - (p.risk_tolerance * 0.20)

        # Always check rather than fold when checking costs nothing.
        if ActionType.CHECK in action_types and ActionType.CALL not in action_types:
            # No bet to face; check is free. Only bet/raise if hand is strong enough.
            if effective_score >= bet_threshold:
                for action_type in (ActionType.RAISE, ActionType.BET):
                    if action_type in action_types:
                        la = _find_action(legal_actions, action_type)
                        return PlayerAction(action_type=action_type, amount=la.min_amount or 0)
            return PlayerAction(action_type=ActionType.CHECK)

        if effective_score >= bet_threshold:
            # Strong hand facing a bet: prefer raise, then call.
            for action_type in (ActionType.RAISE, ActionType.CALL):
                if action_type in action_types:
                    la = _find_action(legal_actions, action_type)
                    return PlayerAction(action_type=action_type, amount=la.min_amount or 0)

        elif effective_score >= call_threshold:
            # Medium hand facing a bet: call.
            if ActionType.CALL in action_types:
                la = _find_action(legal_actions, ActionType.CALL)
                return PlayerAction(action_type=ActionType.CALL, amount=la.min_amount or 0)

        # Weak hand or insufficient score: fold if possible.
        for action_type in (ActionType.FOLD, ActionType.CHECK):
            if action_type in action_types:
                return PlayerAction(action_type=action_type)

        raise ValueError(
            f"No fallback action found. Available actions: {action_types}"
        )


def get_bot_action(
    game_state: Any,
    bot_player_id: str,
    variant: Any,
    bot: RuleBasedBot,
) -> PlayerAction:
    """Invoke the bot for a decision and validate the result.

    Constructs a PlayerView for the bot (respecting the visibility system),
    calls bot.decide(), and asserts the result is a legal action.
    """
    from backend.game.visibility import get_player_view

    legal_actions = variant.get_legal_actions(game_state, bot_player_id)
    player_view = get_player_view(game_state, bot_player_id, legal_actions=legal_actions)

    action = bot.decide(player_view, legal_actions)

    # Defensive assertion: bot must never return an illegal action.
    legal_action_types = {la.action_type for la in legal_actions}
    assert action.action_type in legal_action_types, (
        f"Bot returned illegal action {action.action_type}; "
        f"legal: {legal_action_types}"
    )

    return action


def _find_action(legal_actions: list[LegalAction], action_type: ActionType) -> LegalAction:
    """Return the first LegalAction matching the given type."""
    for la in legal_actions:
        if la.action_type == action_type:
            return la
    raise ValueError(f"Action type {action_type} not in legal actions")
