"""REST API Layer: error codes, APIError exception, and response envelope helpers.

All route handlers raise APIError on validation failures. The Flask error
handler registered in app.py converts it to a JSON response with the standard
envelope shape. Success responses are wrapped with make_success_envelope().

Layer: REST API.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Error code constants (appears in error.code field of the response envelope)
# ---------------------------------------------------------------------------

MISSING_PLAYER_ID = "MISSING_PLAYER_ID"
UNKNOWN_PLAYER = "UNKNOWN_PLAYER"
NOT_YOUR_TURN = "NOT_YOUR_TURN"
ILLEGAL_ACTION = "ILLEGAL_ACTION"
INVALID_AMOUNT = "INVALID_AMOUNT"
HAND_IN_PROGRESS = "HAND_IN_PROGRESS"
NO_HAND_IN_PROGRESS = "NO_HAND_IN_PROGRESS"
SESSION_NOT_STARTED = "SESSION_NOT_STARTED"
INVALID_VARIANT = "INVALID_VARIANT"
INVALID_MODIFIER = "INVALID_MODIFIER"
DECK_EXHAUSTED = "DECK_EXHAUSTED"
CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
INTERNAL_ERROR = "INTERNAL_ERROR"


class APIError(Exception):
    """Raised by route handlers and the game manager when an API-level error occurs.

    The global Flask error handler converts this to a JSON response with the
    standard error envelope and the specified HTTP status code.
    """

    def __init__(
        self,
        http_status: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.code = code
        self.message = message
        self.details = details or {}

    def to_envelope(self) -> dict[str, Any]:
        """Return the full response envelope for this error."""
        return make_error_envelope(self.code, self.message, self.details)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_success_envelope(data: Any) -> dict[str, Any]:
    """Wrap a successful response payload in the standard envelope."""
    return {
        "success": True,
        "data": data,
        "error": None,
        "timestamp": _now(),
    }


def make_error_envelope(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Wrap an error in the standard envelope."""
    return {
        "success": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
        "timestamp": _now(),
    }
