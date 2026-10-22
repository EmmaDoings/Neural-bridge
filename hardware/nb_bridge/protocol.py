"""Wire format shared with ``backend/app/models.py``.

Keeping the frame construction in one place makes it trivial to unit-test the
exact JSON the backend will validate, and to keep values inside the Pydantic
constraints (every metric/wave is ``ge=0, le=1``).
"""

from __future__ import annotations

import math
import time

from .intent import IntentState
from .metrics import Metrics

VALID_PRESETS = frozenset(
    {
        "surgery",
        "gaming",
        "meditation",
        "conversation",
        "creative",
        "navigation",
        "idle",
    }
)


def _clamp01(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def build_telemetry_frame(
    *,
    preset: str,
    metrics: Metrics,
    intent: IntentState,
    source: str | None = None,
    triggered: bool | None = None,
    now: float | None = None,
) -> dict:
    """Return a JSON-ready telemetry frame.

    ``triggered`` defaults to the intent's own flag, so callers cannot
    accidentally desynchronise the two.
    """

    if preset not in VALID_PRESETS:
        raise ValueError(f"unknown preset {preset!r}")

    timestamp = time.time() if now is None else float(now)
    if not math.isfinite(timestamp):
        raise ValueError("timestamp must be finite")

    fire = intent.triggered if triggered is None else bool(triggered)

    return {
        "timestamp": timestamp,
        "preset": preset,
        "metrics": {
            "focus": _clamp01(metrics.focus),
            "meditation": _clamp01(metrics.meditation),
            "attention": _clamp01(metrics.attention),
        },
        "waves": {
            "alpha": _clamp01(metrics.alpha),
            "beta": _clamp01(metrics.beta),
            "theta": _clamp01(metrics.theta),
        },
        "intent": {
            "label": intent.label,
            "confidence": _clamp01(intent.confidence),
            "action": intent.action,
            "color": intent.color,
        },
        "source": source,
        "triggered": fire,
    }
