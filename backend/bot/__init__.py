"""Bot system package for the Game Layer.

Three tiers of bot intelligence:
  Tier 1: rule_based.py  — always available, uses aggression/bluff/risk config
  Tier 2: monte_carlo.py — Phase 7 optional upgrade
  Tier 3: claude_api.py  — Phase 7 optional, falls back to Tier 1 on timeout
"""
