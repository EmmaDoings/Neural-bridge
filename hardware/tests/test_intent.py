from __future__ import annotations

from nb_bridge.intent import COLORS, IntentEngine, classify
from nb_bridge.metrics import Metrics


def metrics(
    focus: float = 0.2,
    meditation: float = 0.2,
    attention: float = 0.2,
    emg: float = 10.0,
) -> Metrics:
    return Metrics(
        focus=focus,
        meditation=meditation,
        attention=attention,
        alpha=0.2,
        beta=0.4,
        theta=0.3,
        emg=emg,
    )


def make_engine(**kwargs) -> IntentEngine:
    defaults = dict(
        enter_threshold=0.85,
        release_threshold=0.75,
        sustain_seconds=1.0,
        cooldown_seconds=3.0,
        emg_ratio_threshold=2.5,
        emg_frames=2,
    )
    defaults.update(kwargs)
    return IntentEngine(**defaults)


def prime_baseline(engine: IntentEngine, emg: float = 10.0) -> None:
    for index in range(5):
        engine.update(metrics(focus=0.2, emg=emg), now=float(index) * 0.1)


def test_focus_requires_sustain_then_fires_once() -> None:
    engine = make_engine()
    prime_baseline(engine)
    assert engine.update(metrics(focus=0.9), now=10.0).triggered is False
    assert engine.update(metrics(focus=0.9), now=10.5).triggered is False
    fired = engine.update(metrics(focus=0.9), now=11.0)
    assert fired.triggered is True
    assert fired.label == "precision_execution"
    assert fired.action == "select"
    assert fired.color == COLORS["precision_execution"]
    # Staying focused never re-fires without dropping below release.
    assert engine.update(metrics(focus=0.95), now=12.0).triggered is False
    assert engine.update(metrics(focus=0.95), now=20.0).triggered is False


def test_release_then_rise_rearms_after_cooldown() -> None:
    engine = make_engine()
    prime_baseline(engine)
    engine.update(metrics(focus=0.9), now=0.0)
    assert engine.update(metrics(focus=0.9), now=1.0).triggered is True
    # Stay high: no re-fire even beyond the cooldown.
    assert engine.update(metrics(focus=0.9), now=10.0).triggered is False
    # Drop below release to re-arm.
    engine.update(metrics(focus=0.2), now=11.0)
    engine.update(metrics(focus=0.9), now=11.5)
    assert engine.update(metrics(focus=0.9), now=12.5).triggered is True


def test_release_between_enter_and_release_does_not_rearm() -> None:
    engine = make_engine()
    prime_baseline(engine)
    engine.update(metrics(focus=0.9), now=0.0)
    assert engine.update(metrics(focus=0.9), now=1.0).triggered is True
    # 0.80 is below enter but above release: still disarmed.
    engine.update(metrics(focus=0.80), now=2.0)
    engine.update(metrics(focus=0.9), now=2.5)
    assert engine.update(metrics(focus=0.9), now=10.0).triggered is False


def test_emg_clench_requires_consecutive_frames() -> None:
    engine = make_engine()
    prime_baseline(engine)
    assert engine.update(metrics(emg=30.0), now=1.0).triggered is False
    fired = engine.update(metrics(emg=30.0), now=1.1)
    assert fired.triggered is True
    assert fired.label == "motor_select"
    assert fired.action == "select"
    assert fired.color == COLORS["motor_select"]
    assert fired.confidence > 0.5


def test_emg_single_spike_does_not_trigger() -> None:
    engine = make_engine()
    prime_baseline(engine)
    assert engine.update(metrics(emg=30.0), now=1.0).triggered is False
    assert engine.update(metrics(emg=10.0), now=1.1).triggered is False
    assert engine.update(metrics(emg=10.0), now=1.2).triggered is False


def test_emg_cooldown_blocks_rapid_reclench() -> None:
    engine = make_engine(emg_cooldown_seconds=1.0)
    prime_baseline(engine)
    engine.update(metrics(emg=30.0), now=1.0)
    assert engine.update(metrics(emg=30.0), now=1.1).triggered is True
    engine.update(metrics(emg=30.0), now=1.2)
    assert engine.update(metrics(emg=30.0), now=1.3).triggered is False


def test_classify_vocabulary_matches_simulator() -> None:
    label, confidence, action = classify(
        metrics(focus=0.95, meditation=0.1, attention=0.95)
    )
    assert (label, action) == ("precision_execution", "stabilise")
    assert 0.0 <= confidence <= 1.0

    label, _, action = classify(metrics(focus=0.3, meditation=0.9, attention=0.4))
    assert (label, action) == ("calm_space", "breathe")

    label, _, action = classify(metrics(focus=0.65, meditation=0.7, attention=0.7))
    assert (label, action) == ("creative_synthesis", "compose")

    label, _, action = classify(metrics(focus=0.5, meditation=0.4, attention=0.85))
    assert (label, action) == ("spatial_navigation", "navigate")

    label, _, action = classify(metrics(focus=0.3, meditation=0.3, attention=0.3))
    assert (label, action) == ("ambient_monitoring", "observe")


def test_engine_rejects_invalid_thresholds() -> None:
    try:
        IntentEngine(enter_threshold=0.5, release_threshold=0.6)
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_baseline_adapts_only_when_quiet() -> None:
    engine = make_engine()
    prime_baseline(engine, emg=10.0)
    baseline = engine.emg_baseline
    assert baseline is not None
    engine.update(metrics(emg=100.0), now=1.0)  # clench frame: must not poison baseline
    assert engine.emg_baseline is not None
    assert engine.emg_baseline < 20.0
