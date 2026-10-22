"""Metric derivation: regional band powers -> focus / meditation / attention.

The pipeline is deliberately transparent:

1. Compute *relative* band powers for the central and occipital groups.
2. Form three bounded ratios so every metric lives in ``[0, 1]`` by
   construction:
       focus      = beta_c / (beta_c + theta_c)
       meditation = alpha_o / (alpha_o + beta_o)
       attention  = beta_c / (beta_c + alpha_c + theta_c)
3. Smooth the ratios with an EMA to remove frame-to-frame jitter.
4. Map the smoothed ratios onto the full 0..1 range using either a default
   logistic curve or a personal calibration percentile range.

Calibration is optional. When enabled it collects ``calibration_seconds`` of
resting data (eyes open, then closed, guided by the operator) and stretches
the observed 5th..95th percentile onto 0..1. If fewer than half the expected
samples arrive, the engine keeps using the default curve.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .signal import BandPowers

_EPSILON = 1e-6
# Logistic steepness for the uncalibrated mapping. At ratio 0.5 the output is
# 0.5; at 0.3 it is ~0.17 and at 0.7 it is ~0.83, which spreads the narrow
# band of real-world ratios across the UI without clipping.
DEFAULT_STEEPNESS = 6.0
MIN_CALIBRATION_SAMPLES = 20
# A calibration range narrower than this is treated as degenerate (the user
# sat still and every sample looked identical) and is widened.
MIN_CALIBRATION_SPAN = 0.05


def _clamp(value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, min(1.0, number))


def _non_negative(value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, number)


def _logistic(ratio: float) -> float:
    return 1.0 / (1.0 + float(np.exp(-DEFAULT_STEEPNESS * (ratio - 0.5))))


@dataclass(frozen=True)
class RawReading:
    """Un-smoothed ratios for one window."""

    focus: float
    meditation: float
    attention: float
    alpha: float
    beta: float
    theta: float
    emg: float


@dataclass(frozen=True)
class Metrics:
    """Smoothed, normalised metrics plus the waves the UI draws."""

    focus: float
    meditation: float
    attention: float
    alpha: float
    beta: float
    theta: float
    emg: float


def ratios_from_bands(
    central: BandPowers,
    occipital: BandPowers,
    emg: float,
) -> RawReading:
    """Combine two electrode groups into the three cognitive ratios."""

    c_beta = max(0.0, central.beta)
    c_theta = max(0.0, central.theta)
    c_alpha = max(0.0, central.alpha)
    o_alpha = max(0.0, occipital.alpha)
    o_beta = max(0.0, occipital.beta)

    return RawReading(
        focus=c_beta / (c_beta + c_theta + _EPSILON),
        meditation=o_alpha / (o_alpha + o_beta + _EPSILON),
        attention=c_beta / (c_beta + c_alpha + c_theta + _EPSILON),
        alpha=o_alpha,
        beta=c_beta,
        theta=c_theta,
        emg=max(0.0, float(emg)),
    )


@dataclass
class Calibration:
    """Collects resting-state ratios and derives percentile ranges."""

    capacity: int
    focus: list[float] = field(default_factory=list)
    meditation: list[float] = field(default_factory=list)
    attention: list[float] = field(default_factory=list)
    _ranges: dict[str, tuple[float, float]] | None = None

    def add(self, reading: RawReading) -> None:
        if self._ranges is not None or len(self.focus) >= self.capacity:
            return
        self.focus.append(reading.focus)
        self.meditation.append(reading.meditation)
        self.attention.append(reading.attention)

    @property
    def ready(self) -> bool:
        return self._ranges is not None

    @property
    def samples(self) -> int:
        return len(self.focus)

    def finalise(self) -> bool:
        """Compute ranges. Returns True when calibration became usable."""

        if self._ranges is not None:
            return True
        if len(self.focus) < MIN_CALIBRATION_SAMPLES:
            return False

        def span(values: list[float]) -> tuple[float, float]:
            low, high = np.percentile(np.asarray(values), [5.0, 95.0])
            low = float(low)
            high = float(high)
            if high - low < MIN_CALIBRATION_SPAN:
                centre = (high + low) / 2.0
                low = centre - MIN_CALIBRATION_SPAN / 2.0
                high = centre + MIN_CALIBRATION_SPAN / 2.0
            return low, high

        self._ranges = {
            "focus": span(self.focus),
            "meditation": span(self.meditation),
            "attention": span(self.attention),
        }
        return True

    def map(self, name: str, value: float) -> float | None:
        if self._ranges is None:
            return None
        low, high = self._ranges[name]
        return _clamp((value - low) / (high - low))


class MetricsEngine:
    """EMA smoothing + optional calibration for one bridge session."""

    def __init__(
        self,
        ema_alpha: float = 0.2,
        calibration_seconds: float = 60.0,
        sample_hz: float = 5.0,
    ) -> None:
        if not 0.0 < ema_alpha <= 1.0:
            raise ValueError("ema_alpha must be in (0, 1]")
        self.ema_alpha = ema_alpha
        capacity = max(0, int(round(calibration_seconds * sample_hz)))
        self.calibration = Calibration(capacity=capacity)
        self._smoothed: tuple[float, float, float] | None = None

    @property
    def calibration_active(self) -> bool:
        return self.calibration.ready

    def update(self, reading: RawReading) -> Metrics:
        ratios = (reading.focus, reading.meditation, reading.attention)
        if self._smoothed is None:
            smoothed = ratios
        else:
            alpha = self.ema_alpha
            smoothed = tuple(
                alpha * new + (1.0 - alpha) * old
                for new, old in zip(ratios, self._smoothed)
            )
        self._smoothed = smoothed

        # Calibration must collect smoothed values so the percentiles reflect
        # the same signal the runtime sees.
        if self.calibration.capacity > 0:
            self.calibration.add(
                RawReading(
                    focus=smoothed[0],
                    meditation=smoothed[1],
                    attention=smoothed[2],
                    alpha=reading.alpha,
                    beta=reading.beta,
                    theta=reading.theta,
                    emg=reading.emg,
                )
            )
            if (
                self.calibration.samples >= self.calibration.capacity
                and not self.calibration.ready
            ):
                self.calibration.finalise()

        mapped_focus = self.calibration.map("focus", smoothed[0])
        mapped_meditation = self.calibration.map("meditation", smoothed[1])
        mapped_attention = self.calibration.map("attention", smoothed[2])

        focus = _logistic(smoothed[0]) if mapped_focus is None else mapped_focus
        meditation = (
            _logistic(smoothed[1]) if mapped_meditation is None else mapped_meditation
        )
        attention = (
            _logistic(smoothed[2]) if mapped_attention is None else mapped_attention
        )

        return Metrics(
            focus=_clamp(focus),
            meditation=_clamp(meditation),
            attention=_clamp(attention),
            alpha=_clamp(reading.alpha),
            beta=_clamp(reading.beta),
            theta=_clamp(reading.theta),
            emg=_non_negative(reading.emg),
        )
