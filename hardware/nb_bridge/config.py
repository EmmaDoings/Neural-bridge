"""Environment-driven configuration for the local hardware bridge.

Every value has a safe default so `python -m nb_bridge` works out of the box
against the BrainFlow synthetic board. Real hardware is opt-in:

    NB_BOARD=cyton
    NB_SERIAL_PORT=COM3
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

DEFAULT_API_BASE = "https://neural-bridge-api.onrender.com"

VALID_BOARDS = ("synthetic", "cyton", "cyton_daisy")

VALID_PRESETS = (
    "surgery",
    "gaming",
    "meditation",
    "conversation",
    "creative",
    "navigation",
    "idle",
)


class ConfigError(ValueError):
    """Raised when an environment variable cannot be turned into a config."""


def _get(name: str, default: str | None = None) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    return raw or default


def _get_float(name: str, default: float, minimum: float | None = None) -> float:
    raw = _get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {value}")
    return value


def _get_int(name: str, default: int, minimum: int | None = None) -> int:
    value = _get_float(name, float(default))
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {value}")
    return int(value)


def _get_bool(name: str, default: bool) -> bool:
    raw = _get(name)
    if raw is None:
        return default
    lowered = raw.lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} must be a boolean, got {raw!r}")


@dataclass(frozen=True)
class BridgeConfig:
    """Immutable, validated bridge configuration."""

    api_base: str
    device_name: str
    device_kind: str
    board: str
    serial_port: str | None
    preset: str
    update_hz: float
    window_seconds: float
    ema_alpha: float
    calibration_seconds: float
    emg_band: tuple[float, float]
    intent_focus_enter: float
    intent_focus_release: float
    intent_sustain_seconds: float
    intent_cooldown_seconds: float
    emg_ratio_threshold: float
    emg_frames: int
    request_timeout: float
    log_level: str

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        api_base = (_get("NB_API_BASE", DEFAULT_API_BASE) or DEFAULT_API_BASE).rstrip("/")
        parsed = urlparse(api_base)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ConfigError(
                f"NB_API_BASE must be an http(s) URL, got {api_base!r}"
            )

        board = (_get("NB_BOARD", "synthetic") or "synthetic").lower()
        if board not in VALID_BOARDS:
            raise ConfigError(
                f"NB_BOARD must be one of {', '.join(VALID_BOARDS)}, got {board!r}"
            )

        serial_port = _get("NB_SERIAL_PORT")
        if board != "synthetic" and not serial_port:
            raise ConfigError(
                f"NB_SERIAL_PORT is required when NB_BOARD={board} "
                "(for example COM3 on Windows or /dev/ttyUSB0 on Linux)"
            )

        preset = (_get("NB_PRESET", "conversation") or "conversation").lower()
        if preset not in VALID_PRESETS:
            raise ConfigError(
                f"NB_PRESET must be one of {', '.join(VALID_PRESETS)}, got {preset!r}"
            )

        emg_low = _get_float("NB_EMG_LOW_HZ", 30.0, minimum=1.0)
        emg_high = _get_float("NB_EMG_HIGH_HZ", 100.0, minimum=emg_low + 1.0)

        update_hz = _get_float("NB_UPDATE_HZ", 5.0, minimum=0.5)
        if update_hz > 30.0:
            raise ConfigError(f"NB_UPDATE_HZ must be <= 30, got {update_hz}")

        window_seconds = _get_float("NB_WINDOW_SECONDS", 2.0, minimum=1.0)
        if window_seconds > 10.0:
            raise ConfigError(f"NB_WINDOW_SECONDS must be <= 10, got {window_seconds}")

        return cls(
            api_base=api_base,
            device_name=_get("NB_DEVICE_NAME", "openbci-cyton") or "openbci-cyton",
            device_kind=_get("NB_DEVICE_KIND", "eeg") or "eeg",
            board=board,
            serial_port=serial_port,
            preset=preset,
            update_hz=update_hz,
            window_seconds=window_seconds,
            ema_alpha=_get_float("NB_EMA_ALPHA", 0.2, minimum=0.01),
            calibration_seconds=_get_float("NB_CALIBRATION_SECONDS", 60.0, minimum=0.0),
            emg_band=(emg_low, emg_high),
            intent_focus_enter=_get_float("NB_INTENT_FOCUS_ENTER", 0.85),
            intent_focus_release=_get_float("NB_INTENT_FOCUS_RELEASE", 0.75),
            intent_sustain_seconds=_get_float(
                "NB_INTENT_SUSTAIN_SECONDS", 1.5, minimum=0.0
            ),
            intent_cooldown_seconds=_get_float(
                "NB_INTENT_COOLDOWN_SECONDS", 4.0, minimum=0.0
            ),
            emg_ratio_threshold=_get_float(
                "NB_EMG_RATIO_THRESHOLD", 2.5, minimum=1.0
            ),
            emg_frames=_get_int("NB_EMG_FRAMES", 2, minimum=1),
            request_timeout=_get_float("NB_REQUEST_TIMEOUT", 60.0, minimum=1.0),
            log_level=(_get("NB_LOG_LEVEL", "INFO") or "INFO").upper(),
        )

    @property
    def interval_seconds(self) -> float:
        return 1.0 / self.update_hz

    @property
    def calibration_samples(self) -> int:
        return int(round(self.calibration_seconds * self.update_hz))
