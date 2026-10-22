"""Signal processing against the verified BrainFlow 5.23 API.

Important, empirically confirmed details:

* ``DataFilter.get_custom_band_powers(data, bands, channels, sr, True)``
  returns ``(average, std_dev)`` and the average is already **normalised**
  (the five bands sum to 1.0). We re-normalise defensively anyway.
* ``DataFilter.perform_bandpass`` and ``remove_environmental_noise`` operate
  on a single contiguous 1-D channel, never a 2-D matrix.
* ``get_psd_welch`` returns ``(amplitudes, frequencies)`` in that order.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from brainflow.data_filter import DataFilter, NoiseTypes
from brainflow.board_shim import BrainFlowError

# BrainFlow's built-in bands, kept identical so our numbers match its docs.
BANDS: tuple[tuple[float, float], ...] = (
    (2.0, 4.0),    # delta
    (4.0, 8.0),    # theta
    (8.0, 13.0),   # alpha
    (13.0, 30.0),  # beta
    (30.0, 45.0),  # gamma
)

BAND_NAMES = ("delta", "theta", "alpha", "beta", "gamma")

# One second at 250 Hz. Shorter windows make Welch unstable.
MIN_SAMPLES = 250

# Signals below this RMS (microvolts) are treated as disconnected electrodes.
MIN_RMS_UV = 1e-6

# Band-passed EMG needs far fewer samples than a spectral estimate.
MIN_EMG_SAMPLES = 64

_EPSILON = 1e-9


@dataclass(frozen=True)
class BandPowers:
    """Relative (unit-sum) band powers for one electrode group."""

    delta: float
    theta: float
    alpha: float
    beta: float
    gamma: float

    def total(self) -> float:
        return self.delta + self.theta + self.alpha + self.beta + self.gamma

    def normalised(self) -> "BandPowers":
        total = self.total()
        if total <= _EPSILON:
            return BandPowers(0.0, 0.0, 0.0, 0.0, 0.0)
        return BandPowers(
            self.delta / total,
            self.theta / total,
            self.alpha / total,
            self.beta / total,
            self.gamma / total,
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "delta": self.delta,
            "theta": self.theta,
            "alpha": self.alpha,
            "beta": self.beta,
            "gamma": self.gamma,
        }


def _contiguous(data: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(data, dtype=np.float64)


def relative_band_powers(
    data: np.ndarray,
    channels: tuple[int, ...] | list[int],
    sampling_rate: int,
) -> BandPowers | None:
    """Spectral band powers for the given row indices.

    Returns ``None`` when the window is too short or the data is unusable,
    which lets the bridge skip a frame instead of publishing garbage.
    """

    if data.ndim != 2 or data.shape[1] < MIN_SAMPLES or not channels:
        return None
    matrix = _contiguous(data)
    if any(channel < 0 or channel >= matrix.shape[0] for channel in channels):
        return None
    selected = matrix[list(channels)]
    if not np.isfinite(selected).all():
        return None
    # A flat or disconnected electrode would otherwise be normalised into
    # meaningless band powers by the FFT's numerical noise floor.
    if float(np.sqrt(np.mean(np.square(selected)))) < MIN_RMS_UV:
        return None
    try:
        averages, _ = DataFilter.get_custom_band_powers(
            matrix, list(BANDS), list(channels), sampling_rate, True
        )
    except (BrainFlowError, ValueError, IndexError):
        return None
    values = np.asarray(averages, dtype=np.float64)
    if values.shape != (len(BANDS),) or not np.isfinite(values).all():
        return None
    total = float(values.sum())
    if total <= _EPSILON:
        return None
    values = values / total
    return BandPowers(*[float(value) for value in values])


def emg_rms(
    data: np.ndarray,
    channel: int,
    sampling_rate: int,
    band: tuple[float, float] = (30.0, 100.0),
) -> float:
    """RMS amplitude of a band-passed lateral channel.

    Jaw clenching produces broadband high-frequency power; RMS over 30-100 Hz
    is a simple, robust proxy that needs no training.
    """

    if data.ndim != 2 or data.shape[1] < MIN_EMG_SAMPLES:
        return 0.0
    if channel < 0 or channel >= data.shape[0]:
        return 0.0
    low, high = band
    nyquist = sampling_rate / 2.0
    high = min(high, nyquist - 1.0)
    if high <= low:
        return 0.0
    signal = np.array(data[channel], dtype=np.float64, copy=True)
    try:
        DataFilter.perform_bandpass(
            np.ascontiguousarray(signal),
            sampling_rate,
            low,
            high,
            4,
            0,
            0.0,
        )
    except (BrainFlowError, ValueError):
        return 0.0
    return float(np.sqrt(np.mean(np.square(signal))))


def notch(signal: np.ndarray, sampling_rate: int) -> np.ndarray:
    """Return a copy with 50/60 Hz line noise removed (1-D input)."""

    if signal.ndim != 1 or signal.size < MIN_EMG_SAMPLES:
        return signal
    cleaned = np.array(signal, dtype=np.float64, copy=True)
    try:
        DataFilter.remove_environmental_noise(
            np.ascontiguousarray(cleaned),
            sampling_rate,
            NoiseTypes.FIFTY_AND_SIXTY.value,
        )
    except (BrainFlowError, ValueError):
        return signal
    return cleaned
