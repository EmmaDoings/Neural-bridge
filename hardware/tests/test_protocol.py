from __future__ import annotations

import pytest

from nb_bridge.intent import IntentState
from nb_bridge.metrics import Metrics
from nb_bridge.protocol import build_telemetry_frame


def metrics() -> Metrics:
    return Metrics(
        focus=0.7,
        meditation=0.4,
        attention=0.8,
        alpha=0.3,
        beta=0.5,
        theta=0.2,
        emg=5.0,
    )


def intent(triggered: bool = False) -> IntentState:
    return IntentState(
        label="precision_execution",
        confidence=0.9,
        action="select",
        color="#38bdf8",
        triggered=triggered,
    )


def test_frame_matches_backend_contract() -> None:
    frame = build_telemetry_frame(
        preset="conversation",
        metrics=metrics(),
        intent=intent(),
        source="device-1",
        now=1234.5,
    )
    assert set(frame) == {
        "timestamp",
        "preset",
        "metrics",
        "waves",
        "intent",
        "source",
        "triggered",
    }
    assert frame["timestamp"] == 1234.5
    assert frame["preset"] == "conversation"
    assert frame["metrics"] == {"focus": 0.7, "meditation": 0.4, "attention": 0.8}
    assert frame["waves"] == {"alpha": 0.3, "beta": 0.5, "theta": 0.2}
    assert frame["intent"]["label"] == "precision_execution"
    assert frame["intent"]["action"] == "select"
    assert frame["source"] == "device-1"
    assert frame["triggered"] is False


def test_frame_clamps_out_of_range_values() -> None:
    wild = Metrics(
        focus=2.0,
        meditation=-1.0,
        attention=float("nan"),
        alpha=100.0,
        beta=-2.0,
        theta=0.5,
        emg=0.0,
    )
    frame = build_telemetry_frame(
        preset="gaming",
        metrics=wild,
        intent=IntentState("x", 5.0, "select", "#fff", True),
        now=1.0,
    )
    assert frame["metrics"]["focus"] == 1.0
    assert frame["metrics"]["meditation"] == 0.0
    assert frame["metrics"]["attention"] == 0.0
    assert frame["waves"]["alpha"] == 1.0
    assert frame["waves"]["beta"] == 0.0
    assert frame["intent"]["confidence"] == 1.0
    assert frame["triggered"] is True


def test_triggered_flag_can_be_overridden() -> None:
    frame = build_telemetry_frame(
        preset="idle",
        metrics=metrics(),
        intent=intent(triggered=True),
        triggered=False,
        now=2.0,
    )
    assert frame["triggered"] is False


def test_invalid_preset_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_telemetry_frame(
            preset="not-a-preset",
            metrics=metrics(),
            intent=intent(),
            now=1.0,
        )


def test_non_finite_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_telemetry_frame(
            preset="idle",
            metrics=metrics(),
            intent=intent(),
            now=float("inf"),
        )
