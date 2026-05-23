# Poker Engine: Home Game Edition

A local poker practice and home game engine supporting a rotating
home game with approximately 20 variants, non-standard deck
configurations, and persistent chip tracking.

---

## What It Is

- Practice poker variants you play with friends at home
- Track chip stacks across sessions (play money only)
- Play against configurable bot opponents
- Support for a fifth suit (Orbs) and zero-rank card (Null)
- Run locally or deploy as a Docker container for remote play

## What It Is Not

- An online gambling platform
- A real money system of any kind
- A commercial poker client

---

## Quick Start (Local)

### Prerequisites

- Python 3.11+
- Node.js 18+
- pip

### Backend

```bash
cd backend
pip install -r requirements.txt
cp ../.env.local ../.env
python app.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 in your browser.

---

## Quick Start (Docker)

```bash
cp .env.container .env
docker-compose up --build
```

Open http://localhost:5173 in your browser.
Share your machine's IP address with friends on the same network.

---

## Configuration

Edit config/house_rules.json to configure:

- Deck configuration and Null/Orbs rules
- Bot count, aggression, and AI tier
- Guts burn limit
- Starting chip stack
- Enabled variants and modifiers
- Betting amounts

See docs/00_architecture_overview.md for full configuration reference.

---

## Documentation

All requirements and architecture documentation is in docs/:

```
docs/00_architecture_overview.md    System architecture
docs/01_deck_layer.md               Card and deck implementation
docs/02_poker_hand_evaluator.md     Poker hand evaluation
docs/03_numeric_evaluator.md        Point total game evaluation
docs/04_game_layer.md               Game variants and state machines
docs/05_rest_api_layer.md           REST API and WebSocket
docs/06_ui_layer.md                 SvelteKit frontend
```

---

## Supported Variants

### Poker Hand Variants
- Seven Card Stud
- Five Card Draw
- Chicago / Low Chicago
- Night Baseball
- Joe's Baseball
- Elevator
- Pilot
- Anaconda
- Chasing Queens
- Auction
- Guts
- Screw Your Neighbor
- Criss-Cross
- Roll Your Own

### Numeric Variants
- Six-and-a-Half / Twenty-one-and-a-Half
- Seven / Twenty-Seven

### Modifiers (stack on any compatible variant)
- Follow the Queen (wild card changes on Queen reveal)
- Dirty Bitch (Queen of Spades triggers redeal)
- High-Low Declare (chip reveal, scoop-or-bust)

---

## Deck Configurations

| Players | Deck           | Cards |
|---------|----------------|-------|
| 5-6     | Standard       | 52    |
| 7       | With Nulls     | 56    |
| 8-9     | With Orbs (✦)  | 65    |

Nulls are rank-0 cards (one per suit). They contribute to flushes
and can anchor straights but do not form pairs by default.

Orbs is a fifth suit. All standard ranks apply. Five of a Kind
becomes possible with wild cards.

---

## Bot Tiers

**Tier 1 (default)**: Rule-based. Configurable aggression, bluff
frequency, and risk tolerance. Fast, always available.

**Tier 2**: Monte Carlo simulation. Evaluates thousands of possible
outcomes before deciding. Activate via use_monte_carlo in house_rules.json.

**Tier 3**: Claude API. Reasons about your specific variant rules
in natural language. Shows reasoning in UI. Requires Anthropic API
access. Activate via use_claude_api in house_rules.json.

---

## License

MIT License with Commons Clause. Copyright © 2026 Corey Seliger.

Personal use, educational use, self-hosted use among friends and family, and open source contributions are all permitted and encouraged.

Commercial use, including incorporation into a product or service offered for a fee, requires written permission from the author. See the LICENSE file for full terms or reach out directly via GitHub.
