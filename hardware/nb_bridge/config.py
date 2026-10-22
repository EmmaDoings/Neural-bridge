"""Environment-driven configuration for the local hardware bridge.

Every value has a safe default so `python -m nb_bridge` works out of the box
against the BrainFlow synthetic board. Real hardware is opt-in:

    NB_BOARD=cyton
    NB_SERIAL_PORT=COM3
"""

from __future__ import annotations

from dataclasses import dataclass

from nb_common.config import (
    ConfigError,
    get_env,
    get_float,
    get_int,
    validate_http_url,
)

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
    registration_key: str | None
    log_level: str

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        api_base = validate_http_url(
            "NB_API_BASE",
            get_env("NB_API_BASE", DEFAULT_API_BASE) or DEFAULT_API_BASE,
        )

        board = (get_env("NB_BOARD", "synthetic") or "synthetic").lower()
        if board not in VALID_BOARDS:
            raise ConfigError(
                f"NB_BOARD must be one of {', '.join(VALID_BOARDS)}, got {board!r}"
            )

        serial_port = get_env("NB_SERIAL_PORT")
        if board != "synthetic" and not serial_port:
            raise ConfigError(
                f"NB_SERIAL_PORT is required when NB_BOARD={board} "
                "(for example COM3 on Windows or /dev/ttyUSB0 on Linux)"
            )

        preset = (get_env("NB_PRESET", "conversation") or "conversation").lower()
        if preset not in VALID_PRESETS:
            raise ConfigError(
                f"NB_PRESET must be one of {', '.join(VALID_PRESETS)}, got {preset!r}"
            )

        emg_low = get_float("NB_EMG_LOW_HZ", 30.0, minimum=1.0)
        emg_high = get_float("NB_EMG_HIGH_HZ", 100.0, minimum=emg_low + 1.0)

        update_hz = get_float("NB_UPDATE_HZ", 5.0, minimum=0.5)
        if update_hz > 30.0:
            raise ConfigError(f"NB_UPDATE_HZ must be <= 30, got {update_hz}")

        window_seconds = get_float("NB_WINDOW_SECONDS", 2.0, minimum=1.0)
        if window_seconds > 10.0:
            raise ConfigError(f"NB_WINDOW_SECONDS must be <= 10, got {window_seconds}")

        return cls(
            api_base=api_base,
            device_name=get_env("NB_DEVICE_NAME", "openbci-cyton") or "openbci-cyton",
            device_kind=get_env("NB_DEVICE_KIND", "eeg") or "eeg",
            board=board,
            serial_port=serial_port,
            preset=preset,
            update_hz=update_hz,
            window_seconds=window_seconds,
            ema_alpha=get_float("NB_EMA_ALPHA", 0.2, minimum=0.01),
            calibration_seconds=get_float("NB_CALIBRATION_SECONDS", 60.0, minimum=0.0),
            emg_band=(emg_low, emg_high),
            intent_focus_enter=get_float("NB_INTENT_FOCUS_ENTER", 0.85),
            intent_focus_release=get_float("NB_INTENT_FOCUS_RELEASE", 0.75),
            intent_sustain_seconds=get_float(
                "NB_INTENT_SUSTAIN_SECONDS", 1.5, minimum=0.0
            ),
            intent_cooldown_seconds=get_float(
                "NB_INTENT_COOLDOWN_SECONDS", 4.0, minimum=0.0
            ),
            emg_ratio_threshold=get_float(
                "NB_EMG_RATIO_THRESHOLD", 2.5, minimum=1.0
            ),
            emg_frames=get_int("NB_EMG_FRAMES", 2, minimum=1),
            request_timeout=get_float("NB_REQUEST_TIMEOUT", 60.0, minimum=1.0),
            registration_key=get_env("NB_DEVICE_REGISTRATION_KEY"),
            log_level=(get_env("NB_LOG_LEVEL", "INFO") or "INFO").upper(),
        )

    @property
    def interval_seconds(self) -> float:
        return 1.0 / self.update_hz

    @property
    def calibration_samples(self) -> int:
        return int(round(self.calibration_seconds * self.update_hz))
