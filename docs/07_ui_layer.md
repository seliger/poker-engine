# UI Layer Requirements
## Poker Engine: Home Game Edition
### Version 1.0

---

## Overview

The UI Layer is a SvelteKit application that runs in the browser. It communicates with the Flask backend exclusively via REST endpoints and WebSocket events. It has no direct database access and no game logic. Its responsibilities are display, input collection, and state management on the client side.

The UI is designed to be functional and clear first, polished second. Phase 1 is a minimal table that works. Phase 6 polish makes it look good. The requirements here describe the full target state, with notes indicating what is Phase 1 versus later.

---

## Technology

```
Framework:          SvelteKit
Styling:            Tailwind CSS
WebSocket client:   socket.io-client
State management:   Svelte stores
Build:              Vite
```

### Technology Constraints

- No React. No Vue. SvelteKit only.
- Tailwind core utility classes only. No custom CSS framework.
- No TypeScript requirement but strongly encouraged for store and API types.
- socket.io-client version must match Flask-SocketIO server version.
- No external UI component library in Phase 1. Simple hand-rolled components.
- The backend URL is configured via VITE_API_URL environment variable. Never hardcoded.

---

## Application Structure

```
src/
    lib/
        api/
            rest.js         REST client wrapper
            socket.js       WebSocket client and event handlers
        stores/
            session.js      session and player state
            hand.js         current hand state
            chips.js        chip ledger and balances
            reference.js    hand rankings reference data
        components/
            table/
                Table.svelte            main game table
                PlayerSeat.svelte       individual player position
                CommunityLayout.svelte  community card area
                Pot.svelte              pot display
            cards/
                Card.svelte             single card display
                CardBack.svelte         face-down card display
                Hand.svelte             player hand display
            betting/
                ActionBar.svelte        bet, call, fold controls
                BettingHistory.svelte   round betting summary
            auction/
                AuctionPanel.svelte     auction bid interface
            guts/
                GutsPanel.svelte        in/out declaration interface
            declare/
                DeclarePanel.svelte     high/low/both declaration
            numeric/
                NumericPanel.svelte     draw and stand for numeric variants
            chips/
                ChipLedger.svelte       session chip tracking
                Balance.svelte          current balance display
            reference/
                HandReference.svelte    hand ranking quick reference
                VariantRules.svelte     active variant rules display
            session/
                SessionSetup.svelte     session and player configuration
                HandSetup.svelte        variant and modifier selection
            layout/
                Header.svelte
                Sidebar.svelte
                Notification.svelte     modifier fired and other alerts
    routes/
        +page.svelte            main game view
        session/
            +page.svelte        session setup
        chips/
            +page.svelte        chip ledger view
        reference/
            +page.svelte        hand reference and variant rules
```

---

## State Management

Client state is managed via Svelte stores. Stores are updated by WebSocket events and REST responses. Components subscribe to stores and re-render reactively.

### session store

```javascript
{
    session_id: null,
    players: [],
    my_player_id: null,
    my_player_name: null,
    balances: {},
    hands_played: 0,
    hand_in_progress: false
}
```

### hand store

```javascript
{
    hand_id: null,
    phase: null,
    variant: null,
    modifiers: [],
    my_cards: [],
    other_players: [],
    community_layout: null,
    pot_total: 0,
    my_stack: 0,
    betting_state: {},
    wild_ranks: [],
    wild_suits: [],
    legal_actions: [],
    hand_strength: null,
    last_event: null,
    bot_thinking: false,
    notifications: []
}
```

### chips store

```javascript
{
    balances: {},
    ledger: [],
    ledger_total: 0
}
```

### reference store

```javascript
{
    rankings: [],
    deck_config: null,
    wild_ranks: [],
    notes: []
}
```

---

## WebSocket Client

The WebSocket client connects to the backend on session start and maintains the connection for the session duration. It handles reconnection automatically with exponential backoff.

```javascript
socket.on('game_state_update', (data) => {
    hand.update(state => ({ ...state, ...data }))
})

socket.on('modifier_fired', (data) => {
    hand.update(state => ({
        ...state,
        notifications: [...state.notifications, data]
    }))
})

socket.on('bot_thinking', (data) => {
    hand.update(state => ({ ...state, bot_thinking: true }))
})

socket.on('bot_action', (data) => {
    hand.update(state => ({
        ...state,
        bot_thinking: false,
        last_event: data
    }))
})

socket.on('hand_complete', (data) => {
    hand.update(state => ({ ...state, last_event: data }))
    chips.refresh()
})
```

---

## Views

### Session Setup View (/session)

**Phase 1.**

Displayed before a session starts. Collects player name for the human player. Allows configuration of bot count. Displays current house rules summary. Start Session button calls POST /api/session/start and navigates to the main game view.

In container mode with multiple human players, each browser navigates to the session setup view and enters their name. The first player to start the session becomes the host. Subsequent players join by entering the session ID displayed to the host.

Session join flow is a future feature. In the current version, all human players are configured at session start by the host.

---

### Main Game View (/)

**Phase 1 (functional). Phase 6 (polished).**

The primary view. Displays the poker table, all player seats, community cards if applicable, pot, and the active player's action controls.

**Table layout:**

Players are arranged around a virtual oval table. The human player is always at the bottom center. Bot players fill the remaining seats clockwise. Seat positions are calculated based on player count.

**Per player seat display:**

- Player name and chip stack
- Face-up cards displayed with suit symbols and rank
- Face-down cards displayed as card backs
- Fold indicator when folded
- Active player indicator (subtle highlight)
- Bot thinking indicator (animated) when bot is deciding
- Current bet amount for the round
- Declaration indicator after declare phase (HIGH, LOW, or BOTH, revealed only after chip reveal)

**Community card area:**

Displayed in the center of the table when the variant has community cards. Renders the layout type from the hand store:

- ELEVATOR: 2x3+1 grid with G card visually centered and connected to all rows
- CRISS_CROSS: plus-sign layout with center card highlighted
- POOL: flat row of cards
- NONE: empty

Face-down community cards display as card backs. Cards flip visually when revealed, with a brief flip animation in Phase 6.

**Pot display:**

Total pot displayed prominently in the center. Side pots displayed separately when present. Carry amount displayed distinctly when a redeal has occurred.

**Hand strength indicator:**

Displayed above the human player's cards. Shows the current partial hand evaluation. Examples:

```
Two Pair, Aces and Eights
Null anchors a potential straight flush
Current total: 14.5 (going high toward 21.5)
```

This is the primary training feature. It tells the player what they have without telling them what to do.

**Action bar:**

Displayed at the bottom of the screen when it is the human player's turn. Renders only the legal actions from the hand store.

Standard poker actions:

```
[Fold]  [Check]  [Call $X]  [Raise] [amount input] [Confirm]
```

Draw action:

```
Select cards to discard, then [Draw]
```

Auction action:

```
Current bid: $X
[Pass]  [Bid] [amount input] [Confirm]
```

Guts declaration:

```
[I'm In]  [I'm Out]
Reveal is simultaneous. Your choice is locked until all players reveal.
```

Declare action:

```
[High]  [Low]  [Both Ways]
Remember: Both Ways requires winning both directions or you receive nothing.
```

Numeric draw:

```
Current total: 12.5
[Take a Card]  [Stand]
```

**Modifier notification:**

When modifier_fired WebSocket event is received, a prominent notification banner appears at the top of the table:

```
DIRTY BITCH!
Queen of Spades appeared mid-hand. Pot carries. Redealing.
```

The notification persists for 4 seconds or until dismissed. In Phase 6 it has a dramatic visual treatment appropriate to the chaos it signals.

**Bot action display:**

When bot_action WebSocket event is received, a brief notification shows what the bot did:

```
Bot 2 raised $50.
```

When Claude API bot is active and reasoning is present, an expandable panel shows the bot's reasoning. Collapsed by default to avoid slowing down the game flow.

**Hand complete display:**

When hand_complete WebSocket event is received, an overlay shows:

- Winner(s) and winning hand description
- All hands revealed at showdown
- Chip movements for each player
- Dismiss button to prepare for next hand

---

### Hand Setup Panel

**Phase 1.**

Displayed before each hand starts as a modal or slide-in panel. The active dealer selects the variant and any modifiers. Other players see a waiting indicator.

Components:

- Variant selector: dropdown or button grid of enabled variants
- Modifier toggles: one toggle per available modifier
- Diagonals toggle: visible only when ELEVATOR is selected
- Player count display: current players at table
- Deck config indicator: shows which deck will be used based on player count
- Start Hand button

---

### Chip Ledger View (/chips)

**Phase 1 (balance display). Phase 6 (full ledger).**

Two sections:

**Current balances:**

Table showing each player, their current stack, and their session delta (up or down from starting stack). Human player row highlighted. Updated in real time via session_update WebSocket events.

**Ledger history:**

Paginated table of chip_ledger entries for the current session. Columns: hand number, variant, player, delta, balance, reason. Filterable by player. This is the answer to "am I up or down and by how much."

The all-sessions ledger is accessible via a tab or toggle. Same structure but spans all recorded sessions.

---

### Hand Reference View (/reference)

**Phase 1.**

Two sections:

**Hand rankings:**

The hand reference card the table used to have before someone swapped it out. Displays hand rankings in order from highest to lowest with example hands and approximate frequencies. Adjusts dynamically based on the active deck configuration and wild card rules.

When Orbs are active, a note explains that flush frequency is lower than standard. When wild cards are active, Five of a Kind appears in the ranking table. When Nulls are active, the low hand section shows Null-A-2-3-5 as the best possible low hand.

This is the feature that replaces the physical reference card. It should be accessible on a phone or secondary monitor during an actual game night.

**Variant rules:**

Displays plain language rules for the currently selected variant and any active modifiers. Sourced from GET /api/reference/variant. Useful for explaining a new game to the table mid-session.

---

## Visual Design Principles

**Phase 1:** Functional and clear. Green table felt background. White card faces. Clear suit symbols using Unicode characters. Readable chip amounts. No animation. No flourish.

**Phase 6 targets:**

- Card flip animation on reveal
- Chip animation on pot distribution
- Dramatic Dirty Bitch notification with visual impact
- Suit-colored card borders (red for hearts and diamonds, black for clubs and spades, a distinct color for Orbs)
- Bot thinking animation
- Sound effects configurable and off by default
- Dark mode support

**Orbs suit display:**

The Orbs suit uses the ✦ symbol established in the Deck Layer requirements. The color for Orbs in Phase 6 is a deep purple or gold, distinct from both red and black suits. In Phase 1 it is simply rendered in a distinct color from the four standard suits with the ✦ symbol.

**Null card display:**

Null cards display their suit symbol at rank 0. A Null of Spades displays as 0♠. In Phase 6 the Null card has a slightly muted or ghosted visual treatment to distinguish it from standard cards while still being readable.

---

## Responsive Design

The application targets desktop and tablet primarily. Mobile is a secondary concern since home game use on a laptop or tablet is the primary scenario. The table layout collapses gracefully on smaller screens by reducing card size and player seat spacing. The hand reference view and chip ledger view are fully usable on mobile since they are the most likely to be pulled up on a phone during an actual game.

---

## Error Handling

REST errors are displayed as dismissible banners at the top of the active view. WebSocket error_event messages are displayed as notifications. Network disconnection triggers a reconnection attempt with a visible indicator. If reconnection fails after 5 attempts, a modal prompts the player to refresh the page.

---

## Unit Test Requirements

- Session store correctly initialized on session start
- Hand store correctly updated on game_state_update WebSocket event
- Hand store correctly updated on modifier_fired event
- Legal actions render correctly for each ActionType
- Face-down cards render as card backs
- Face-up cards render with correct rank and suit symbol
- Null card renders as 0 plus suit symbol
- Orbs suit renders with ✦ symbol
- Community layout renders ELEVATOR grid correctly with G centered
- Community layout renders CRISS_CROSS plus sign correctly
- Hand strength indicator updates on each game_state_update
- Modifier notification appears on modifier_fired and dismisses after 4 seconds
- Hand complete overlay shows correct winners and chip deltas
- Chip ledger renders entries in reverse chronological order
- Hand reference adjusts rankings when deck config changes
- WebSocket reconnection attempted on disconnect
- Action bar renders only legal actions
- Bot thinking indicator appears on bot_thinking event and clears on bot_action

---

## Explicitly Out of Scope for UI Layer

- Game logic of any kind
- Direct API calls to anything other than the Flask backend
- Authentication UI (future feature)
- Real money display or transaction UI
- Chat between players (future feature, would use WebSocket)
- Spectator mode (future feature)
- Mobile native app

---
