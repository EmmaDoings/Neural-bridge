from __future__ import annotations

from nb_bridge.metrics import (
    Calibration,
    MetricsEngine,
    RawReading,
    _logistic,
    ratios_from_bands,
)
from nb_bridge.signal import BandPowers


def bands(delta: float, theta: float, alpha: float, beta: float, gamma: float) -> BandPowers:
    return BandPowers(delta, theta, alpha, beta, gamma)


def reading(focus: float, meditation: float, attention: float, emg: float = 1.0) -> RawReading:
    return RawReading(
        focus=focus,
        meditation=meditation,
        attention=attention,
        alpha=0.2,
        beta=0.4,
        theta=0.3,
        emg=emg,
    )


def test_ratios_from_bands_are_bounded_and_directional() -> None:
    central = bands(0.05, 0.10, 0.20, 0.40, 0.25)
    occipital = bands(0.05, 0.10, 0.50, 0.10, 0.25)
    result = ratios_from_bands(central, occipital, emg=12.0)
    assert 0.0 <= result.focus <= 1.0
    assert 0.0 <= result.meditation <= 1.0
    assert 0.0 <= result.attention <= 1.0
    assert abs(result.focus - 0.4 / 0.5) < 1e-4
    assert abs(result.meditation - 0.5 / 0.6) < 1e-4
    assert result.alpha == occipital.alpha
    assert result.beta == central.beta
    assert result.theta == central.theta
    assert result.emg == 12.0


def test_more_beta_increases_focus_and_attention() -> None:
    low = ratios_from_bands(bands(0.1, 0.4, 0.2, 0.2, 0.1), bands(0.1, 0.3, 0.3, 0.2, 0.1), 1.0)
    high = ratios_from_bands(bands(0.1, 0.1, 0.2, 0.5, 0.1), bands(0.1, 0.1, 0.3, 0.4, 0.1), 1.0)
    assert high.focus > low.focus
    assert high.attention > low.attention


def test_logistic_midpoint_and_bounds() -> None:
    assert abs(_logistic(0.5) - 0.5) < 1e-9
    assert _logistic(0.0) < 0.05
    assert _logistic(1.0) > 0.95


def test_engine_ema_smooths_a_step() -> None:
    engine = MetricsEngine(ema_alpha=0.2, calibration_seconds=0.0)
    first = engine.update(reading(0.5, 0.5, 0.5))
    assert abs(first.focus - 0.5) < 1e-9
    second = engine.update(reading(1.0, 1.0, 1.0))
    # 0.2 * 1.0 + 0.8 * 0.5 = 0.6 -> logistic(0.6)
    assert 0.5 < second.focus < _logistic(1.0)
    for _ in range(60):
        last = engine.update(reading(1.0, 1.0, 1.0))
    assert last.focus > 0.95


def test_engine_outputs_are_clamped() -> None:
    engine = MetricsEngine(ema_alpha=1.0, calibration_seconds=0.0)
    metrics = engine.update(reading(1.0, 1.0, 1.0, emg=-5.0))
    assert 0.0 <= metrics.focus <= 1.0
    assert 0.0 <= metrics.meditation <= 1.0
    assert 0.0 <= metrics.attention <= 1.0
    assert metrics.alpha == 0.2
    assert metrics.emg >= 0.0


def test_calibration_needs_minimum_samples() -> None:
    calibration = Calibration(capacity=5)
    for _ in range(5):
        calibration.add(reading(0.4, 0.4, 0.4))
    assert calibration.samples == 5
    assert calibration.finalise() is False
    assert calibration.ready is False


def test_calibration_maps_percentiles_onto_unit_range() -> None:
    points = [0.3 + 0.4 * index / 19.0 for index in range(20)]
    engine = MetricsEngine(ema_alpha=1.0, calibration_seconds=4.0, sample_hz=5.0)
    assert engine.calibration.capacity == 20
    for point in points:
        engine.update(reading(point, point, point))
        if engine.calibration.samples >= 20:
            break
    assert engine.calibration.ready is True
    low = engine.calibration.map("focus", 0.30)
    high = engine.calibration.map("focus", 0.70)
    assert low is not None and high is not None
    assert 0.0 <= low <= 0.1
    assert 0.9 <= high <= 1.0
    assert engine.calibration.map("focus", 2.0) == 1.0
    assert engine.calibration.map("focus", -2.0) == 0.0


def test_degenerate_calibration_is_widened() -> None:
    calibration = Calibration(capacity=20)
    for _ in range(20):
        calibration.add(reading(0.5, 0.5, 0.5))
    assert calibration.finalise() is True
    assert calibration.map("focus", 0.5) == 0.5
