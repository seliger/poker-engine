# REST API Layer Requirements
## Poker Engine: Home Game Edition
### Version 1.0

---

## Overview

The REST API Layer is the boundary between the Python backend and the SvelteKit frontend. It is implemented as a Flask application running in synchronous mode. It translates HTTP requests and WebSocket messages into Game Layer function calls and serializes Game Layer responses into JSON.

The REST API has no business logic of its own. It validates requests, delegates to the Game Layer, and serializes responses. All game logic lives in the Game Layer and below.

---

## Technology

```
Framework:          Flask (synchronous mode)
WebSocket:          Flask-SocketIO (synchronous mode, eventlet or gevent)
CORS:               Flask-CORS
Serialization:      Python dataclasses + custom JSON encoder
Validation:         Custom request validators, no external library
```

### Technology Constraints

- No async/await. Flask-SocketIO in synchronous mode with eventlet handles WebSocket concurrency without async.
- No authentication middleware in this version. Identity is carried by player_id header only.
- No external validation library. Request validation is explicit Python code, not schema decorators.
- Flask-SocketIO is the only WebSocket dependency. No separate WebSocket server.

---

## Deployment Modes

The API supports two deployment modes controlled by environment variables.

### Local Mode (default)

```
POKER_ENV=local
POKER_HOST=127.0.0.1
POKER_PORT=5000
POKER_CORS_ORIGINS=http://localhost:5173
```

Flask binds to localhost only. CORS is restricted to the local SvelteKit dev server port.

### Container Mode

```
POKER_ENV=container
POKER_HOST=0.0.0.0
POKER_PORT=5000
POKER_CORS_ORIGINS=*
```

Flask binds to all interfaces so the container network can reach it. CORS is permissive within the container network. When a reverse proxy is added in front of the container, CORS_ORIGINS should be scoped to the proxy's origin.

A Dockerfile and docker-compose.yml are provided as part of the project. The docker-compose configuration mounts the house_rules.json and poker.db paths as volumes so data persists across container restarts and is editable without rebuilding the image.

---

## Identity Model

Every request to the API must include a player_id header identifying the requesting player.

```
Header: X-Player-ID: <player_id>
```

The API validates that the player_id refers to a known player in the current session. If the header is missing or the player_id is unknown, the API returns 401 with an error message.

This is not authentication. There is no password, token, or secret. The player_id is simply a stable identifier that tells the Game Layer which player is taking an action. When real authentication is added in a future version, the player_id will be derived from the auth token rather than sent directly.

Player IDs are UUIDs assigned at session start and communicated to each player via the session start response. In local single-player mode the human player's ID is also stored in house_rules.json as human_player_id for convenience.

---

## Response Envelope

All API responses use a consistent envelope:

```json
{
    "success": true,
    "data": { },
    "error": null,
    "timestamp": "2026-05-23T14:32:00Z"
}
```

On success, data contains the response payload and error is null.
On failure, data is null and error contains:

```json
{
    "code": "ILLEGAL_ACTION",
    "message": "Fold is not a legal action at this phase.",
    "details": { }
}
```

The timestamp field is always present and is the server time of the response. This helps the frontend order events correctly when multiple WebSocket messages arrive close together.

HTTP status codes are used correctly:

```
200     Success
400     Bad request, invalid parameters
401     Missing or unknown player_id
403     Action not permitted for this player at this time
404     Resource not found
409     Conflict, e.g. hand already in progress
422     Valid request but game rule violation
500     Internal server error
```

---

## Error Codes

The following error codes appear in the error.code field:

```
MISSING_PLAYER_ID           X-Player-ID header absent
UNKNOWN_PLAYER              player_id not found in current session
NOT_YOUR_TURN               action submitted by player who is not active
ILLEGAL_ACTION              action not in legal actions list for current state
INVALID_AMOUNT              bet or bid amount outside legal range
HAND_IN_PROGRESS            cannot start new hand while one is active
NO_HAND_IN_PROGRESS         action submitted when no hand is active
SESSION_NOT_STARTED         action submitted before session is started
INVALID_VARIANT             unknown or disabled game variant
INVALID_MODIFIER            unknown modifier name
DECK_EXHAUSTED              deck cannot fulfill required deal
CONFIGURATION_ERROR         house rules JSON is invalid
INTERNAL_ERROR              unhandled exception, see server logs
```

---

## WebSocket Architecture

Game state changes are pushed to connected clients via WebSocket. The REST endpoints handle player actions (writes). The WebSocket handles game state updates (reads).

### Connection

Clients connect to the WebSocket namespace /game on the Flask-SocketIO server. The player_id is sent as a query parameter on connection:

```
ws://host:port/game?player_id=<player_id>
```

The server validates the player_id on connection and rejects unknown players with a connection error event.

### Room Management

Each hand has a room identified by hand_id. Players are joined to the room for the current hand automatically on connection. When a new hand starts, all connected players are moved to the new hand's room.

In container mode with multiple human players, each player connects from their own browser and receives only their own player view via WebSocket. The server never broadcasts another player's hole cards.

### Server-to-Client Events

The server emits the following events to connected clients:

**game_state_update**

Emitted after every game state change. Each connected player receives their own player-specific view. The server emits to each player individually, not as a broadcast, to ensure information asymmetry is maintained.

```json
{
    "event": "game_state_update",
    "data": {
        "hand_id": 42,
        "phase": "BET_ROUND",
        "my_cards": [ ],
        "other_players": [ ],
        "community_layout": null,
        "pot_total": 150,
        "my_stack": 850,
        "betting_state": { },
        "wild_ranks": [],
        "wild_suits": [],
        "active_modifiers": ["FOLLOW_THE_QUEEN"],
        "legal_actions": [ ],
        "hand_strength": {
            "display_name": "Two Pair, Aces and Eights",
            "hand_rank": 2,
            "is_partial": true,
            "notes": null
        }
    }
}
```

**modifier_fired**

Emitted immediately when a modifier trigger fires, before the resulting game_state_update. Gives the frontend a moment to display a dramatic notification before the state changes.

```json
{
    "event": "modifier_fired",
    "data": {
        "modifier": "DIRTY_BITCH",
        "message": "Dirty Bitch! Queen of Spades mid-hand. Pot carries, redeal.",
        "triggering_card": {"rank": 12, "suit": "SPADES"},
        "effect_type": "REDEAL",
        "pot_instruction": "CARRY"
    }
}
```

**bot_thinking**

Emitted when a bot begins its decision process. Gives the frontend a signal to display a thinking indicator.

```json
{
    "event": "bot_thinking",
    "data": {
        "player_id": "bot-uuid",
        "player_name": "Bot 1"
    }
}
```

**bot_action**

Emitted when a bot completes its decision. Includes the action taken and optionally the bot's reasoning when Claude API bot is active.

```json
{
    "event": "bot_action",
    "data": {
        "player_id": "bot-uuid",
        "player_name": "Bot 1",
        "action_type": "RAISE",
        "amount": 50,
        "reasoning": "Strong hand with two pair. Pot odds favor aggression."
    }
}
```

**hand_complete**

Emitted when a hand reaches the COMPLETE phase. Includes the showdown result and chip movements.

```json
{
    "event": "hand_complete",
    "data": {
        "hand_id": 42,
        "winners": [
            {
                "player_id": "uuid",
                "player_name": "Corey",
                "direction": "HIGH",
                "hand_description": "Full House, Aces over Kings",
                "amount_won": 300
            }
        ],
        "all_hands": [ ],
        "chip_deltas": {
            "player-uuid-1": -150,
            "player-uuid-2": 300,
            "bot-uuid-1": -150
        }
    }
}
```

**session_update**

Emitted when session-level state changes, such as a player joining or leaving.

```json
{
    "event": "session_update",
    "data": {
        "session_id": 1,
        "players": [ ],
        "balances": { }
    }
}
```

**error_event**

Emitted when the server encounters an error processing a WebSocket message.

```json
{
    "event": "error_event",
    "data": {
        "code": "ILLEGAL_ACTION",
        "message": "Fold is not a legal action at this phase."
    }
}
```

### Client-to-Server Events

Player actions may be submitted via either the REST POST /api/hand/action endpoint or the WebSocket submit_action event. Both routes are supported. The WebSocket route is preferred in container mode for lower latency.

**submit_action**

```json
{
    "event": "submit_action",
    "data": {
        "action_type": "RAISE",
        "amount": 50,
        "cards": null
    }
}
```

The player_id is taken from the WebSocket connection, not from the event data. A player may only submit actions for themselves.

---

## REST Endpoints

### Session Endpoints

**POST /api/session/start**

Starts a new session. Creates player records for the human player and all configured bots. Returns player IDs for all players.

Request body:

```json
{
    "human_players": [
        {"name": "Corey"}
    ],
    "bot_count": 5
}
```

Response data:

```json
{
    "session_id": 1,
    "players": [
        {
            "player_id": "uuid",
            "name": "Corey",
            "is_bot": false,
            "starting_stack": 100
        },
        {
            "player_id": "bot-uuid-1",
            "name": "Bot 1",
            "is_bot": true,
            "starting_stack": 100
        }
    ]
}
```

In container mode with multiple human players, human_players contains one entry per human participant. Each receives their own player_id to use as their X-Player-ID header.

**POST /api/session/end**

Ends the current session. Finalizes all chip ledger entries. Returns session summary.

Response data:

```json
{
    "session_id": 1,
    "hands_played": 14,
    "duration_minutes": 87,
    "final_balances": {
        "Corey": -25,
        "Bot 1": 10,
        "Bot 2": 15
    }
}
```

**GET /api/session/current**

Returns current session state including all player balances.

Response data:

```json
{
    "session_id": 1,
    "started_at": "2026-05-23T19:00:00Z",
    "players": [ ],
    "balances": {
        "player-uuid": 75
    },
    "hands_played": 7,
    "hand_in_progress": true
}
```

---

### Hand Endpoints

**POST /api/hand/start**

Starts a new hand. The requesting player must be the designated dealer for this hand, determined by seat rotation from the previous hand.

Request body:

```json
{
    "variant": "SEVEN_CARD_STUD",
    "modifiers": ["FOLLOW_THE_QUEEN", "HIGH_LOW_DECLARE"],
    "diagonals_active": false
}
```

diagonals_active is only relevant for ELEVATOR and is ignored for all other variants.

Response data:

```json
{
    "hand_id": 42,
    "variant": "SEVEN_CARD_STUD",
    "modifiers": ["FOLLOW_THE_QUEEN", "HIGH_LOW_DECLARE"],
    "deck_config": "STANDARD",
    "dealer_id": "player-uuid"
}
```

A game_state_update WebSocket event is emitted to all players immediately after the hand starts and after each dealing phase completes.

**GET /api/hand/state**

Returns the current player view for the requesting player. This is the polling fallback for clients that cannot maintain a WebSocket connection.

Response data: PlayerView object as described in Game Layer Requirements.

**POST /api/hand/action**

Submits a player action. The requesting player must be the active player.

Request body:

```json
{
    "action_type": "RAISE",
    "amount": 50,
    "cards": null
}
```

The cards field is used for DRAW, DISCARD, and PASS actions where specific cards must be identified. Cards are identified by their shorthand representation.

```json
{
    "action_type": "DRAW",
    "amount": null,
    "cards": ["A♠", "7♦"]
}
```

Response data:

```json
{
    "action_accepted": true,
    "next_player_id": "bot-uuid-1",
    "phase": "BET_ROUND"
}
```

A game_state_update WebSocket event is emitted to all players after the action is processed and after any bot actions that follow.

**GET /api/hand/result**

Returns the result of the most recently completed hand. Available only after the hand reaches COMPLETE phase.

Response data:

```json
{
    "hand_id": 42,
    "variant": "SEVEN_CARD_STUD",
    "modifiers": ["FOLLOW_THE_QUEEN"],
    "winners": [ ],
    "all_hands": [ ],
    "chip_deltas": { },
    "redeal_count": 0,
    "duration_seconds": 145
}
```

---

### Chip Endpoints

**GET /api/chips/balance**

Returns current chip balance for all players in the current session.

Response data:

```json
{
    "balances": {
        "player-uuid": {
            "name": "Corey",
            "balance": 75,
            "delta_this_session": -25
        }
    }
}
```

**GET /api/chips/ledger**

Returns chip ledger for the current session ordered by recorded_at descending.

Query parameters:

```
player_id   optional, filter to specific player
limit       optional, default 50
offset      optional, default 0
```

Response data:

```json
{
    "entries": [
        {
            "id": 142,
            "player_name": "Corey",
            "hand_id": 42,
            "variant": "SEVEN_CARD_STUD",
            "delta": -50,
            "balance": 75,
            "reason": "Lost bet round 3",
            "recorded_at": "2026-05-23T19:45:00Z"
        }
    ],
    "total": 87,
    "limit": 50,
    "offset": 0
}
```

**GET /api/chips/ledger/all**

Returns chip ledger across all sessions. Same parameters and response shape as /ledger with an additional session_id field on each entry.

---

### Reference Endpoints

**GET /api/reference/hands**

Returns hand rankings adjusted for the active deck configuration and any active wild card rules. Used by the UI to render the reference card.

Query parameters:

```
deck_config     optional, one of STANDARD, WITH_NULLS, WITH_ORBS
                defaults to current session deck config
wild_ranks      optional, comma-separated rank numbers
```

Response data:

```json
{
    "deck_config": "WITH_ORBS",
    "wild_ranks": [],
    "rankings": [
        {
            "rank": 10,
            "name": "Royal Flush",
            "description": "A, K, Q, J, 10 of the same suit",
            "frequency": 0.000032,
            "example": "A♠ K♠ Q♠ J♠ 10♠"
        }
    ],
    "notes": [
        "With Orbs active, flush probability is reduced.",
        "Five of a Kind is possible with wild cards."
    ]
}
```

**GET /api/reference/variant**

Returns a plain language rules summary for a given variant and modifier combination. Used by the UI to display rules at hand start.

Query parameters:

```
variant         required
modifiers       optional, comma-separated modifier names
```

Response data:

```json
{
    "variant": "ELEVATOR",
    "modifiers": ["DIRTY_BITCH"],
    "title": "Elevator with Dirty Bitch",
    "summary": "Four hole cards. Seven community cards in a 2x3+1 grid...",
    "rules": [ ],
    "wild_rules": null,
    "modifier_rules": [
        "If the Queen of Spades appears, the hand is immediately redealt."
    ]
}
```

---

### Configuration Endpoints

**GET /api/config**

Returns current house rules configuration.

Response data: the full house_rules.json contents as a JSON object.

**GET /api/config/variants**

Returns list of enabled variants with display names and evaluator types.

Response data:

```json
{
    "variants": [
        {
            "id": "SEVEN_CARD_STUD",
            "display_name": "Seven Card Stud",
            "evaluator": "PokerHandEvaluator",
            "min_players": 2,
            "max_players": 8
        }
    ]
}
```

**GET /api/config/modifiers**

Returns list of available modifiers with display names and current default enabled state.

Response data:

```json
{
    "modifiers": [
        {
            "id": "DIRTY_BITCH",
            "display_name": "Dirty Bitch",
            "description": "Queen of Spades triggers an immediate redeal.",
            "enabled_by_default": false
        }
    ]
}
```

**POST /api/config**

Updates house rules configuration. Requires a restart to take effect. Returns a warning to that effect.

Request body: partial or full house_rules.json structure. Only provided fields are updated.

Response data:

```json
{
    "updated": true,
    "restart_required": true,
    "message": "Configuration updated. Restart the server for changes to take effect.",
    "changed_keys": ["bot.aggression", "guts.burn_limit_per_player"]
}
```

---

## Request Validation

Every endpoint validates its request before delegating to the Game Layer. Validation failures return 400 with a descriptive error message. The following validations are applied:

- X-Player-ID header present and refers to known player
- Required body fields present and correct types
- Enum values (variant, modifier, action_type) are valid and enabled
- Numeric amounts within legal ranges
- Card shorthands in cards field are valid and parseable
- Actions are consistent with current game phase

Validation is explicit Python code in a validators module. No external schema validation library is used.

---

## Docker Support

The following files are provided as part of the project:

**Dockerfile**

```
Base image: python:3.11-slim
Installs backend dependencies from requirements.txt
Copies application code
Exposes port 5000
Entrypoint: flask run --host=0.0.0.0 --port=5000
```

**docker-compose.yml**

```
Services:
    backend:
        build: .
        ports: 5000:5000
        environment:
            POKER_ENV: container
            POKER_CONFIG_PATH: /config/house_rules.json
            POKER_DB_PATH: /data/poker.db
        volumes:
            ./config:/config
            ./data:/data

    frontend:
        build: ./frontend
        ports: 5173:5173
        environment:
            VITE_API_URL: http://backend:5000
```

The frontend Dockerfile builds the SvelteKit app and serves it. The backend and frontend communicate over the Docker internal network. External access is via the mapped ports.

Data persistence is via the mounted volumes. The house_rules.json and poker.db files survive container restarts and image rebuilds.

---

## Unit Test Requirements

- All endpoints return correct HTTP status codes for valid and invalid requests
- Missing X-Player-ID header returns 401
- Unknown player_id returns 401
- Action submitted by non-active player returns 403
- Illegal action returns 422 with ILLEGAL_ACTION error code
- Response envelope always present with correct shape
- WebSocket game_state_update emitted after every action
- WebSocket modifier_fired emitted before game_state_update on modifier trigger
- WebSocket bot_thinking emitted before bot decision
- WebSocket hand_complete emitted with correct chip deltas
- Player-specific WebSocket views never contain other players' hole cards
- Container mode binds to 0.0.0.0
- Local mode binds to 127.0.0.1
- CORS headers present and correctly scoped per deployment mode
- Configuration POST correctly identifies changed keys
- Configuration POST returns restart_required: true

---

## Explicitly Out of Scope for REST API Layer

- Business logic of any kind
- Direct database access
- Hand evaluation
- Bot decision making
- Authentication or authorization beyond player_id header validation
- Rate limiting (single user local app, container mode trusted network)
- HTTPS termination (handled by reverse proxy when needed in container mode)

---

