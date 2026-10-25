"""Environment-driven configuration for the local haptics bridge.

Defaults are safe for a mock actuator, so the full pipeline can be tested
without hardware:

    python -m nb_haptics --check --pulse

A real serial actuator is opt-in:

    NB_HAPTICS_DRIVER=serial
    NB_HAPTICS_SERIAL_PORT=COM4
"""

from __future__ import annotations

from dataclasses import dataclass

from nb_common.config import ConfigError, get_env, get_float, get_int, validate_http_url

DEFAULT_API_BASE = "http://localhost:8000"

VALID_DRIVERS = ("mock", "serial")


@dataclass(frozen=True)
class HapticsConfig:
    """Immutable, validated haptics bridge configuration."""

    api_base: str
    device_name: str
    device_kind: str
    driver: str
    serial_port: str | None
    baud_rate: int
    request_timeout: float
    registration_key: str | None
    log_level: str

    @classmethod
    def from_env(cls) -> "HapticsConfig":
        api_base = validate_http_url(
            "NB_HAPTICS_API_BASE",
            get_env("NB_HAPTICS_API_BASE")
            or get_env("NB_API_BASE", DEFAULT_API_BASE)
            or DEFAULT_API_BASE,
        )

        driver = (get_env("NB_HAPTICS_DRIVER", "mock") or "mock").lower()
        if driver not in VALID_DRIVERS:
            raise ConfigError(
                f"NB_HAPTICS_DRIVER must be one of {', '.join(VALID_DRIVERS)}, "
                f"got {driver!r}"
            )

        # The port is checked when the driver is built, after CLI overrides.
        serial_port = get_env("NB_HAPTICS_SERIAL_PORT")

        return cls(
            api_base=api_base,
            device_name=get_env(
                "NB_HAPTICS_DEVICE_NAME", "haptic-hologram"
            )
            or "haptic-hologram",
            device_kind="haptics",
            driver=driver,
            serial_port=serial_port,
            baud_rate=get_int("NB_HAPTICS_BAUD", 115200, minimum=1200),
            request_timeout=get_float(
                "NB_HAPTICS_REQUEST_TIMEOUT", 60.0, minimum=1.0
            ),
            registration_key=get_env("NB_HAPTICS_REGISTRATION_KEY")
            or get_env("NB_DEVICE_REGISTRATION_KEY"),
            log_level=(get_env("NB_HAPTICS_LOG_LEVEL", "INFO") or "INFO").upper(),
        )

    @property
    def interval_seconds(self) -> float:
        """Command-only client: the send loop is not used."""

        return 1.0
