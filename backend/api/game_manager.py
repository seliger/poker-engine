"""REST API Layer: in-memory game state manager.

Holds the current session, active hand, and player roster. Bridges REST
route handlers to Game Layer variant state machines and the Persistence
Layer. One GameManager instance is created per Flask application and stored
on app.game_manager. Routes access it via current_app.game_manager.

Chip stacks persist across sessions via the ledger. New players receive the
default starting stack from house_rules.json; returning players carry their
existing balance forward.

Layer: REST API (calls Game Layer and Persistence Layer; no UI or eval logic).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.bot.rule_based import RuleBasedBot, get_bot_action
from backend.config import load_betting_config, load_bot_config, load_house_rules
from backend.deck.card import DeckConfig
from backend.deck.deck import Deck
from backend.game.modifiers.base import run_modifier_hook
from backend.game.state import (
    ActiveGameConfig,
    BettingState,
    BettingStructure,
    EventType,
    GamePhase,
    GameState,
    GameVariant,
    PlayerState,
    Pot,
)
from backend.game.variants.base import BaseVariant, PlayerAction, ShowdownResult
from backend.game.variants.seven_card_stud import SevenCardStudVariant
from backend.game.visibility import ActionType, LegalAction, get_player_view
from backend.persistence import database, ledger, history

from .errors import (
    APIError,
    HAND_IN_PROGRESS,
    ILLEGAL_ACTION,
    INTERNAL_ERROR,
    INVALID_VARIANT,
    NO_HAND_IN_PROGRESS,
    NOT_YOUR_TURN,
    SESSION_NOT_STARTED,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Variant registry — Phase 1: Seven Card Stud only.
# Phase 4 adds remaining variants here.
# ---------------------------------------------------------------------------

def _make_seven_card_stud() -> SevenCardStudVariant:
    cfg = load_betting_config()
    return SevenCardStudVariant(
        ante_amount=cfg.ante_amount,
        bring_in_amount=cfg.bring_in_amount,
        small_bet=cfg.small_bet,
        big_bet=cfg.big_bet,
    )


_VARIANT_FACTORIES: dict[str, Any] = {
    "SEVEN_CARD_STUD": _make_seven_card_stud,
}

# Display metadata used by /api/config/variants.
_VARIANT_META: dict[str, dict[str, Any]] = {
    "SEVEN_CARD_STUD": {
        "display_name": "Seven Card Stud",
        "evaluator": "PokerHandEvaluator",
        "min_players": 2,
        "max_players": 9,
    },
}

# Display metadata used by /api/config/modifiers.
_MODIFIER_META: dict[str, dict[str, Any]] = {
    "DIRTY_BITCH": {
        "display_name": "Dirty Bitch",
        "description": "Queen of Spades triggers an immediate redeal.",
        "enabled_by_default": False,
    },
    "FOLLOW_THE_QUEEN": {
        "display_name": "Follow the Queen",
        "description": "A face-up Queen changes the wild rank to the next card dealt.",
        "enabled_by_default": False,
    },
    "HIGH_LOW_DECLARE": {
        "display_name": "High-Low Declare",
        "description": "Players declare high, low, or both ways at showdown.",
        "enabled_by_default": False,
    },
}


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

@dataclass
class PlayerInfo:
    """Per-player data held for the lifetime of a session."""
    player_id: str          # UUID string used as key throughout game state
    db_id: int              # Integer primary key in the players table
    name: str
    is_bot: bool
    bot: RuleBasedBot | None = None
    chip_stack: int = 0     # Current balance; synced at session start and hand end


@dataclass
class HandInfo:
    """Metadata for the current or most recently completed hand."""
    hand_id: int
    variant_name: str
    modifiers: list[str]
    started_at: datetime
    starting_stacks: dict[str, int] = field(default_factory=dict)
    chip_deltas: dict[str, int] = field(default_factory=dict)
    winner_ids: list[str] = field(default_factory=list)
    winners_detail: list[dict[str, Any]] = field(default_factory=list)
    redeal_count: int = 0


@dataclass
class SessionInfo:
    """In-memory session state."""
    session_id: int
    players: list[PlayerInfo]
    deck_config: DeckConfig
    dealer_index: int = 0
    hands_played: int = 0

    def find_player(self, player_id: str) -> PlayerInfo | None:
        for p in self.players:
            if p.player_id == player_id:
                return p
        return None

    def find_player_by_db_id(self, db_id: int) -> PlayerInfo | None:
        for p in self.players:
            if p.db_id == db_id:
                return p
        return None


# ---------------------------------------------------------------------------
# GameManager
# ---------------------------------------------------------------------------

class GameManager:
    """In-memory manager for one active session and one active hand.

    Instantiated once per Flask app in create_app(). Routes access it via
    current_app.game_manager. Not thread-safe; single-user synchronous app.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path: str | Path | None = db_path
        self._conn: sqlite3.Connection | None = None
        self._session: SessionInfo | None = None
        self._game_state: GameState | None = None
        self._variant: BaseVariant | None = None
        self._hand_info: HandInfo | None = None
        self._last_result: HandInfo | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the SQLite connection and initialize the schema."""
        self._conn = database.get_connection(self._db_path)
        database.initialize_schema(self._conn)
        logger.debug("GameManager connected to %s", self._db_path or "default path")

    def close(self) -> None:
        """Close the SQLite connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("GameManager.connect() must be called before use.")
        return self._conn

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def start_session(self, human_names: list[str], bot_count: int) -> dict[str, Any]:
        """Start a new session. Ends any currently active session first.

        Assigns default starting stacks to new players; returning players
        carry their existing ledger balance forward.
        """
        if self._session is not None:
            self._end_session_internal()

        rules = load_house_rules()
        default_stack: int = rules.get("chips", {}).get("default_starting_stack", 100)
        bot_cfg = load_bot_config()

        deck_config = DeckConfig.STANDARD()
        session_id = history.start_session(self._db, deck_config_json=deck_config.to_json())

        players: list[PlayerInfo] = []

        for name in human_names:
            db_id = history.get_or_create_player(self._db, name, is_bot=False)
            balance = ledger.get_player_balance(self._db, db_id)
            if balance == 0:
                ledger.record_chip_movement(
                    self._db, db_id, default_stack, default_stack,
                    "initial stack", session_id=session_id,
                )
                balance = default_stack
            players.append(PlayerInfo(
                player_id=str(uuid.uuid4()),
                db_id=db_id,
                name=name,
                is_bot=False,
                chip_stack=balance,
            ))

        for i in range(bot_count):
            name = f"Bot {i + 1}"
            db_id = history.get_or_create_player(self._db, name, is_bot=True)
            balance = ledger.get_player_balance(self._db, db_id)
            if balance == 0:
                ledger.record_chip_movement(
                    self._db, db_id, default_stack, default_stack,
                    "initial stack", session_id=session_id,
                )
                balance = default_stack
            bot = RuleBasedBot(
                aggression=bot_cfg.aggression,
                bluff_frequency=bot_cfg.bluff_frequency,
                risk_tolerance=bot_cfg.risk_tolerance,
                personality_variance=getattr(bot_cfg, "personality_variance", 0.1),
            )
            players.append(PlayerInfo(
                player_id=str(uuid.uuid4()),
                db_id=db_id,
                name=name,
                is_bot=True,
                bot=bot,
                chip_stack=balance,
            ))

        self._session = SessionInfo(
            session_id=session_id,
            players=players,
            deck_config=deck_config,
        )
        logger.info("Session %d started with %d players", session_id, len(players))

        return {
            "session_id": session_id,
            "players": [
                {
                    "player_id": p.player_id,
                    "name": p.name,
                    "is_bot": p.is_bot,
                    "starting_stack": p.chip_stack,
                }
                for p in players
            ],
        }

    def end_session(self) -> dict[str, Any]:
        """End the current session and return a summary."""
        if self._session is None:
            raise APIError(409, SESSION_NOT_STARTED, "No active session to end.")
        return self._end_session_internal()

    def _end_session_internal(self) -> dict[str, Any]:
        assert self._session is not None

        if self._game_state is not None and self._game_state.phase != GamePhase.COMPLETE:
            logger.warning(
                "Session %d ended while hand %d was in progress; hand state discarded.",
                self._session.session_id,
                self._game_state.hand_id,
            )
        self._game_state = None
        self._variant = None
        self._hand_info = None

        session_id = self._session.session_id
        session_row = history.get_session(self._db, session_id)
        history.end_session(self._db, session_id)

        final_balances: dict[str, int] = {
            p.name: ledger.get_player_balance(self._db, p.db_id)
            for p in self._session.players
        }

        duration_minutes = 0
        if session_row and session_row.get("started_at"):
            try:
                started = datetime.fromisoformat(session_row["started_at"])
                duration_minutes = int(
                    (datetime.now(timezone.utc) - started).total_seconds() / 60
                )
            except Exception:
                pass

        result = {
            "session_id": session_id,
            "hands_played": self._session.hands_played,
            "duration_minutes": duration_minutes,
            "final_balances": final_balances,
        }

        self._session = None
        logger.info("Session %d ended. Hands played: %d", session_id, result["hands_played"])
        return result

    def get_current_session(self) -> dict[str, Any] | None:
        """Return current session state or None if no session is active."""
        if self._session is None:
            return None

        balances: dict[str, int] = {
            p.player_id: ledger.get_player_balance(self._db, p.db_id)
            for p in self._session.players
        }
        session_row = history.get_session(self._db, self._session.session_id) or {}

        return {
            "session_id": self._session.session_id,
            "started_at": session_row.get("started_at"),
            "players": [
                {"player_id": p.player_id, "name": p.name, "is_bot": p.is_bot}
                for p in self._session.players
            ],
            "balances": balances,
            "hands_played": self._session.hands_played,
            "hand_in_progress": self.is_hand_active(),
        }

    # ------------------------------------------------------------------
    # Hand management
    # ------------------------------------------------------------------

    def start_hand(
        self,
        dealer_player_id: str,
        variant_name: str,
        modifiers: list[str],
        options: dict[str, Any],
        socketio: Any = None,
    ) -> dict[str, Any]:
        """Start a new hand. The calling player must be the designated dealer."""
        if self._session is None:
            raise APIError(409, SESSION_NOT_STARTED, "No active session.")
        if self.is_hand_active():
            raise APIError(409, HAND_IN_PROGRESS, "A hand is already in progress.")
        if variant_name not in _VARIANT_FACTORIES:
            raise APIError(400, INVALID_VARIANT, f"Unknown variant: {variant_name!r}.")

        session = self._session
        dealer_info = session.find_player(dealer_player_id)
        if dealer_info is None:
            raise APIError(401, "UNKNOWN_PLAYER", f"Player {dealer_player_id!r} not in session.")

        self._variant = _VARIANT_FACTORIES[variant_name]()

        player_states: list[PlayerState] = [
            PlayerState(
                player_id=pi.player_id,
                name=pi.name,
                is_bot=pi.is_bot,
                seat_index=idx,
                chip_stack=pi.chip_stack,
            )
            for idx, pi in enumerate(session.players)
        ]

        active_config = ActiveGameConfig(
            variant=GameVariant(variant_name),
            modifiers=[],
            deck_config=session.deck_config,
            variant_config={"phase_index": 0},
        )

        self._game_state = GameState(
            hand_id=0,
            session_id=session.session_id,
            variant=GameVariant(variant_name),
            deck_config=session.deck_config,
            active_game_config=active_config,
            phase=GamePhase.SETUP,
            players=player_states,
            dealer_index=session.dealer_index,
            active_player_index=session.dealer_index,
            pot=Pot(),
            betting_state=BettingState(structure=BettingStructure.BRING_IN),
            deck=Deck(session.deck_config),
        )

        starting_stacks = {ps.player_id: ps.chip_stack for ps in player_states}

        hand_id = history.start_hand(
            self._db,
            session_id=session.session_id,
            variant=variant_name,
            modifiers_json=json.dumps(modifiers),
            dealer_id=dealer_info.db_id,
            deck_config_json=session.deck_config.to_json(),
        )
        self._game_state.hand_id = hand_id

        self._hand_info = HandInfo(
            hand_id=hand_id,
            variant_name=variant_name,
            modifiers=modifiers,
            started_at=datetime.now(timezone.utc),
            starting_stacks=starting_stacks,
        )

        self._game_state = self._variant.initialize(self._game_state, active_config)
        self._drive_to_interactive(socketio)

        logger.info("Hand %d started: variant=%s", hand_id, variant_name)
        return {
            "hand_id": hand_id,
            "variant": variant_name,
            "modifiers": modifiers,
            "deck_config": "STANDARD",
            "dealer_id": dealer_player_id,
        }

    def get_hand_state(self, player_id: str) -> Any:
        """Return a PlayerView for the given player.

        Returns the PlayerView object; callers are responsible for serializing it.
        """
        if self._session is None:
            raise APIError(409, SESSION_NOT_STARTED, "No active session.")
        if self._game_state is None:
            raise APIError(409, NO_HAND_IN_PROGRESS, "No hand is in progress.")

        legal = (
            self._variant.get_legal_actions(self._game_state, player_id)
            if self._variant else []
        )
        return get_player_view(self._game_state, player_id, legal)

    def submit_action(
        self,
        player_id: str,
        action_type_str: str,
        amount: int,
        cards_shorthands: list[str],
        socketio: Any = None,
    ) -> dict[str, Any]:
        """Apply a player action and advance the game state.

        Runs bot turns automatically after the human action until the next
        human-interactive state or the hand completes.
        """
        if self._session is None:
            raise APIError(409, SESSION_NOT_STARTED, "No active session.")
        if self._game_state is None:
            raise APIError(409, NO_HAND_IN_PROGRESS, "No hand is in progress.")
        if self._variant is None:
            raise APIError(500, INTERNAL_ERROR, "Variant not initialized.")

        try:
            action_type = ActionType(action_type_str)
        except ValueError:
            raise APIError(400, ILLEGAL_ACTION, f"Unknown action type: {action_type_str!r}.")

        current = self._game_state.players[self._game_state.active_player_index]
        if current.player_id != player_id:
            raise APIError(403, NOT_YOUR_TURN, "It is not your turn.")

        legal = self._variant.get_legal_actions(self._game_state, player_id)
        if action_type not in {la.action_type for la in legal}:
            raise APIError(
                422, ILLEGAL_ACTION,
                f"{action_type_str} is not a legal action at this phase.",
            )

        action = PlayerAction(action_type=action_type, amount=amount)
        event_idx = len(self._game_state.hand_history)
        self._game_state = self._variant.apply_action(self._game_state, player_id, action)
        self._game_state = self._run_modifier_hook(self._game_state, event_idx)

        if self._variant.is_phase_complete(self._game_state, self._game_state.phase):
            self._game_state = self._variant.advance_phase(self._game_state)

        self._drive_to_interactive(socketio)

        if self._game_state is None:
            return {
                "action_accepted": True,
                "next_player_id": None,
                "phase": GamePhase.COMPLETE.value,
            }

        next_player = self._game_state.players[self._game_state.active_player_index]
        return {
            "action_accepted": True,
            "next_player_id": next_player.player_id,
            "phase": self._game_state.phase.value,
        }

    def get_hand_result(self) -> dict[str, Any]:
        """Return the result of the most recently completed hand."""
        if self._last_result is None:
            raise APIError(404, NO_HAND_IN_PROGRESS, "No completed hand is available.")
        return self._build_result_response(self._last_result)

    # ------------------------------------------------------------------
    # Chip operations
    # ------------------------------------------------------------------

    def get_balances(self) -> dict[str, Any]:
        """Return current chip balances for all players in the session."""
        if self._session is None:
            raise APIError(409, SESSION_NOT_STARTED, "No active session.")

        session_entries = ledger.get_session_ledger(self._db, self._session.session_id)

        balances: dict[str, Any] = {}
        for p in self._session.players:
            current_balance = ledger.get_player_balance(self._db, p.db_id)
            session_delta = sum(
                e["delta"] for e in session_entries if e["player_id"] == p.db_id
            )
            balances[p.player_id] = {
                "name": p.name,
                "balance": current_balance,
                "delta_this_session": session_delta,
            }
        return {"balances": balances}

    def get_session_ledger(
        self,
        filter_player_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return chip ledger entries for the current session."""
        if self._session is None:
            raise APIError(409, SESSION_NOT_STARTED, "No active session.")

        all_entries = ledger.get_session_ledger(self._db, self._session.session_id)

        if filter_player_id is not None:
            pi = self._session.find_player(filter_player_id)
            if pi is None:
                raise APIError(401, "UNKNOWN_PLAYER", f"Player {filter_player_id!r} not found.")
            all_entries = [e for e in all_entries if e["player_id"] == pi.db_id]

        total = len(all_entries)
        page = all_entries[offset: offset + limit]

        return {
            "entries": [self._enrich_ledger_entry(e) for e in page],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_all_ledger(
        self,
        filter_player_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return chip ledger entries across all sessions for known players."""
        if self._session is None:
            raise APIError(409, SESSION_NOT_STARTED, "No active session.")

        all_entries: list[dict[str, Any]] = []
        for p in self._session.players:
            for e in ledger.get_player_ledger(self._db, p.db_id):
                entry = dict(e)
                entry["_player_name"] = p.name
                all_entries.append(entry)

        all_entries.sort(key=lambda e: e["id"])

        if filter_player_id is not None:
            pi = self._session.find_player(filter_player_id)
            if pi is None:
                raise APIError(401, "UNKNOWN_PLAYER", f"Player {filter_player_id!r} not found.")
            all_entries = [e for e in all_entries if e["player_id"] == pi.db_id]

        total = len(all_entries)
        page = all_entries[offset: offset + limit]

        return {
            "entries": [
                {
                    "id": e["id"],
                    "player_name": e.get("_player_name", "Unknown"),
                    "session_id": e.get("session_id"),
                    "hand_id": e.get("hand_id"),
                    "delta": e["delta"],
                    "balance": e["balance"],
                    "reason": e["reason"],
                    "recorded_at": e["recorded_at"],
                }
                for e in page
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    # ------------------------------------------------------------------
    # State queries (used by validators and routes)
    # ------------------------------------------------------------------

    def is_known_player(self, player_id: str) -> bool:
        """Return True if player_id is in the current session."""
        if self._session is None:
            return False
        return self._session.find_player(player_id) is not None

    def is_session_active(self) -> bool:
        return self._session is not None

    def is_hand_active(self) -> bool:
        return (
            self._game_state is not None
            and self._game_state.phase != GamePhase.COMPLETE
        )

    def get_enabled_variants(self) -> list[str]:
        """Return the list of currently registered variant names."""
        rules = load_house_rules()
        enabled = rules.get("variants", {}).get("enabled", list(_VARIANT_FACTORIES.keys()))
        return [v for v in enabled if v in _VARIANT_FACTORIES]

    def get_variant_meta(self) -> list[dict[str, Any]]:
        enabled = self.get_enabled_variants()
        return [
            {"id": v, **_VARIANT_META[v]}
            for v in enabled
            if v in _VARIANT_META
        ]

    def get_modifier_meta(self) -> list[dict[str, Any]]:
        return [
            {"id": k, **v}
            for k, v in _MODIFIER_META.items()
        ]

    # ------------------------------------------------------------------
    # Internal: game driving
    # ------------------------------------------------------------------

    def _run_modifier_hook(
        self, game_state: GameState, event_index_before: int
    ) -> GameState:
        """Load modifier_stacking from house rules and run the modifier hook."""
        rules = load_house_rules()
        modifier_stacking: bool = rules.get("modifiers", {}).get("modifier_stacking", False)
        return run_modifier_hook(game_state, event_index_before, modifier_stacking)

    def _drive_to_interactive(self, socketio: Any = None) -> None:
        """Advance game state until the next human action is required or the hand ends.

        Case 1 (entered mid-interactive phase): runs bot turns until the human
        player is active or the phase completes. Interactive phases are BET_ROUND
        and DECLARE.

        The outer loop advances through non-interactive phases (SETUP, ANTE,
        INITIAL_DEAL, DEAL_ROUND, SHOWDOWN, POT_DISTRIBUTION) and handles
        interactive-phase setup and bot execution until either a human must act
        or the hand reaches COMPLETE.
        """
        _INTERACTIVE_PHASES = {GamePhase.BET_ROUND, GamePhase.DECLARE}

        if self._game_state is None or self._variant is None:
            return

        # Case 1: currently mid-interactive phase (after a human action that didn't
        # end the phase, or at hand start when bring-in is already set up).
        if self._game_state.phase in _INTERACTIVE_PHASES:
            current_phase = self._game_state.phase
            while not self._variant.is_phase_complete(self._game_state, current_phase):
                current = self._game_state.players[self._game_state.active_player_index]
                if not current.is_bot:
                    return  # human's turn
                self._execute_bot_action(current, socketio)
            # Phase complete: advance to next phase and fall through.
            self._game_state = self._variant.advance_phase(self._game_state)

        # Outer loop: execute non-interactive phases; set up and run interactive phases.
        while True:
            if self._game_state is None:
                return

            phase = self._game_state.phase

            if phase == GamePhase.COMPLETE:
                self._game_state = self._variant.execute_phase(
                    self._game_state, GamePhase.COMPLETE
                )
                self._on_hand_complete(socketio)
                return

            if phase not in _INTERACTIVE_PHASES:
                # Non-interactive phase: execute it, run modifier hook, and advance.
                event_idx = len(self._game_state.hand_history)
                self._game_state = self._variant.execute_phase(self._game_state, phase)
                self._game_state = self._run_modifier_hook(self._game_state, event_idx)
                self._game_state = self._variant.advance_phase(self._game_state)
                continue

            # Interactive phase (BET_ROUND or DECLARE): execute setup, then run bots.
            self._game_state = self._variant.execute_phase(self._game_state, phase)

            # Run bots until human is active or phase completes.
            while not self._variant.is_phase_complete(self._game_state, phase):
                current = self._game_state.players[self._game_state.active_player_index]
                if not current.is_bot:
                    return  # human's turn: wait for submit_action
                self._execute_bot_action(current, socketio)

            # Phase complete: advance and continue outer loop.
            self._game_state = self._variant.advance_phase(self._game_state)

    def _execute_bot_action(
        self, player_state: PlayerState, socketio: Any = None
    ) -> None:
        """Run one bot decision and apply the resulting action to the game state."""
        if self._game_state is None or self._variant is None or self._session is None:
            return

        pi = self._session.find_player(player_state.player_id)

        if socketio is not None:
            socketio.emit(
                "bot_thinking",
                {"player_id": player_state.player_id, "player_name": player_state.name},
                namespace="/game",
            )

        if pi is None or pi.bot is None:
            logger.warning(
                "Bot player %s has no RuleBasedBot instance; defaulting to FOLD.",
                player_state.player_id,
            )
            action = PlayerAction(action_type=ActionType.FOLD)
        else:
            action = get_bot_action(
                self._game_state, player_state.player_id, self._variant, pi.bot
            )

        if socketio is not None:
            socketio.emit(
                "bot_action",
                {
                    "player_id": player_state.player_id,
                    "player_name": player_state.name,
                    "action_type": action.action_type.value,
                    "amount": action.amount,
                    "reasoning": None,
                },
                namespace="/game",
            )

        self._game_state = self._variant.apply_action(
            self._game_state, player_state.player_id, action
        )

    def _on_hand_complete(self, socketio: Any = None) -> None:
        """Persist hand results, update chip stacks, and emit hand_complete event."""
        if self._game_state is None or self._hand_info is None or self._session is None:
            return

        hand_id = self._hand_info.hand_id
        pot_total = self._game_state.pot.total()
        chip_deltas: dict[str, int] = {}
        winners_detail: list[dict[str, Any]] = []

        # Compute per-player chip deltas and update ledger.
        for ps in self._game_state.players:
            starting = self._hand_info.starting_stacks.get(ps.player_id, 0)
            delta = ps.chip_stack - starting
            chip_deltas[ps.player_id] = delta

            pi = self._session.find_player(ps.player_id)
            if pi is not None:
                pi.chip_stack = ps.chip_stack
                if delta != 0:
                    new_balance = ledger.get_player_balance(self._db, pi.db_id) + delta
                    ledger.record_chip_movement(
                        self._db, pi.db_id, delta, new_balance,
                        f"hand {hand_id} result",
                        session_id=self._session.session_id,
                        hand_id=hand_id,
                    )

        # Build winners list from POT_AWARDED events.
        for event in self._game_state.hand_history:
            if event.event_type == EventType.POT_AWARDED and event.player_id:
                pi = self._session.find_player(event.player_id)
                winners_detail.append({
                    "player_id": event.player_id,
                    "player_name": pi.name if pi else "Unknown",
                    "direction": "HIGH",
                    "hand_description": None,
                    "amount_won": event.amount or 0,
                })

        # Finalize hand record in DB.
        history.end_hand(
            self._db,
            hand_id=hand_id,
            pot_total=pot_total,
            redeal_count=self._game_state.redeal_count,
        )

        # Record per-player hand result.
        for ps in self._game_state.players:
            pi = self._session.find_player(ps.player_id)
            if pi is None:
                continue
            history.record_hand_player(
                self._db,
                hand_id=hand_id,
                player_id=pi.db_id,
                starting_stack=self._hand_info.starting_stacks.get(ps.player_id, 0),
                ending_stack=ps.chip_stack,
            )

        self._hand_info.chip_deltas = chip_deltas
        self._hand_info.winner_ids = [w["player_id"] for w in winners_detail]
        self._hand_info.winners_detail = winners_detail
        self._hand_info.redeal_count = self._game_state.redeal_count
        self._last_result = self._hand_info

        self._session.hands_played += 1
        self._session.dealer_index = (
            (self._session.dealer_index + 1) % len(self._session.players)
        )

        if socketio is not None:
            socketio.emit(
                "hand_complete",
                {
                    "hand_id": hand_id,
                    "winners": winners_detail,
                    "chip_deltas": chip_deltas,
                },
                namespace="/game",
            )

        logger.info(
            "Hand %d complete. Winners: %s. Pot: %d.",
            hand_id,
            [w["player_id"] for w in winners_detail],
            pot_total,
        )

        self._game_state = None
        self._variant = None
        self._hand_info = None

    def _build_result_response(self, info: HandInfo) -> dict[str, Any]:
        duration = int((datetime.now(timezone.utc) - info.started_at).total_seconds())
        return {
            "hand_id": info.hand_id,
            "variant": info.variant_name,
            "modifiers": info.modifiers,
            "winners": info.winners_detail,
            "chip_deltas": info.chip_deltas,
            "redeal_count": info.redeal_count,
            "duration_seconds": duration,
        }

    def _enrich_ledger_entry(self, e: dict[str, Any]) -> dict[str, Any]:
        pi = self._session.find_player_by_db_id(e["player_id"]) if self._session else None
        variant = None
        if e.get("hand_id"):
            hand_row = history.get_hand(self._db, e["hand_id"])
            variant = hand_row["variant"] if hand_row else None
        return {
            "id": e["id"],
            "player_name": pi.name if pi else "Unknown",
            "hand_id": e.get("hand_id"),
            "variant": variant,
            "delta": e["delta"],
            "balance": e["balance"],
            "reason": e["reason"],
            "recorded_at": e["recorded_at"],
        }
