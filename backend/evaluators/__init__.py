"""Evaluation Layer public interface.

Exports the abstract base classes and shared types consumed by the Game Layer.
Concrete evaluators are imported directly from their own modules.
"""

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

__all__ = [
    "EvalDirection",
    "Declaration",
    "ComparisonResult",
    "HandRank",
    "AceDualValue",
    "BaseEvaluatedHand",
    "WinnerResult",
    "DeclareResult",
    "BaseEvaluator",
]
