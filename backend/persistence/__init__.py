"""Persistence Layer for the Poker Engine.

Provides SQLite-backed storage for players, sessions, hands, chip ledger
entries, and hand history. Accessed exclusively by the Game Layer.

No game logic, evaluation logic, or UI concerns belong in this layer.
"""
