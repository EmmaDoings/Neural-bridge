from __future__ import annotations

import numpy as np

from nb_bridge.signal import (
    BANDS,
    BandPowers,
    MIN_SAMPLES,
    emg_rms,
    notch,
    relative_band_powers,
)

SR = 250


def make_matrix(seconds: float = 4.0, channels: int = 9) -> np.ndarray:
    samples = int(SR * seconds)
    t = np.arange(samples) / SR
    data = np.zeros((channels, samples), dtype=np.float64)
    data[0] = t  # timestamp row, as BrainFlow returns it
    return data, t


def test_relative_band_powers_detects_dominant_beta() -> None:
    data, t = make_matrix()
    # Channel 1: strong 20 Hz beta with a weak 6 Hz theta component.
    data[1] = 1.0 * np.sin(2 * np.pi * 20.0 * t) + 0.2 * np.sin(2 * np.pi * 6.0 * t)
    bands = relative_band_powers(data, [1], SR)
    assert bands is not None
    assert abs(bands.total() - 1.0) < 1e-6
    assert bands.beta > bands.theta
    assert bands.beta > bands.alpha
    assert bands.beta > bands.gamma
    assert bands.beta > 0.5


def test_relative_band_powers_detects_dominant_alpha() -> None:
    data, t = make_matrix()
    data[3] = 1.0 * np.sin(2 * np.pi * 10.0 * t)
    bands = relative_band_powers(data, [3], SR)
    assert bands is not None
    assert bands.alpha > bands.beta
    assert bands.alpha > bands.theta


def test_relative_band_powers_averages_channels() -> None:
    data, t = make_matrix()
    data[1] = np.sin(2 * np.pi * 20.0 * t)
    data[2] = np.sin(2 * np.pi * 20.0 * t)
    single = relative_band_powers(data, [1], SR)
    pair = relative_band_powers(data, [1, 2], SR)
    assert single is not None and pair is not None
    assert abs(single.beta - pair.beta) < 1e-6


def test_relative_band_powers_rejects_short_window() -> None:
    data, _ = make_matrix(seconds=0.5)
    assert data.shape[1] < MIN_SAMPLES
    assert relative_band_powers(data, [1], SR) is None


def test_relative_band_powers_rejects_bad_channel() -> None:
    data, _ = make_matrix()
    assert relative_band_powers(data, [99], SR) is None
    assert relative_band_powers(data, [], SR) is None


def test_relative_band_powers_rejects_flat_signal() -> None:
    data, _ = make_matrix()
    assert relative_band_powers(data, [1], SR) is None


def test_emg_rms_separates_high_frequency() -> None:
    data, t = make_matrix()
    data[4] = np.sin(2 * np.pi * 40.0 * t)
    data[5] = np.sin(2 * np.pi * 10.0 * t)
    high = emg_rms(data, 4, SR)
    low = emg_rms(data, 5, SR)
    assert high > 0.4
    assert low < 0.05
    assert high > low * 10


def test_emg_rms_guards_short_and_invalid_channels() -> None:
    data, _ = make_matrix()
    assert emg_rms(data, 4, SR, band=(100.0, 10.0)) == 0.0
    assert emg_rms(data[:, :10], 4, SR) == 0.0
    assert emg_rms(data, 99, SR) == 0.0


def test_band_powers_normalise_and_handle_zero() -> None:
    powers = BandPowers(1.0, 1.0, 2.0, 4.0, 2.0)
    normalised = powers.normalised()
    assert abs(normalised.total() - 1.0) < 1e-9
    assert abs(normalised.beta - 0.4) < 1e-9
    empty = BandPowers(0.0, 0.0, 0.0, 0.0, 0.0).normalised()
    assert empty.total() == 0.0
    assert set(powers.as_dict()) == {"delta", "theta", "alpha", "beta", "gamma"}
    assert len(BANDS) == 5


def test_notch_preserves_shape_and_values_finite() -> None:
    data, t = make_matrix()
    signal = np.sin(2 * np.pi * 10.0 * t)
    cleaned = notch(signal, SR)
    assert cleaned.shape == signal.shape
    assert np.isfinite(cleaned).all()
    assert notch(np.zeros(10), SR).shape == (10,)
