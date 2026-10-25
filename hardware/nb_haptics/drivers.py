"""Actuator drivers for the haptics bridge.

The mock driver is the default and lets the whole registration/command pipeline
run without hardware. The serial driver speaks a tiny line protocol:

    PULSE <intensity 0.00-1.00> <duration_ms>\\n

The reference Arduino sketch in ``hardware/haptics_firmware/`` implements it.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

logger = logging.getLogger("nb_haptics.drivers")


class HapticsUnavailable(RuntimeError):
    """The actuator could not be opened or written."""


class HapticDriver(Protocol):
    def pulse(self, intensity: float, duration_ms: int) -> tuple[float, int]:
        """Fire one pulse and return the validated ``(intensity, duration)``."""

    def close(self) -> None:
        """Release the actuator."""

    def describe(self) -> str:
        """A short human-readable description for logs."""


def normalize_pulse(intensity: Any, duration_ms: Any) -> tuple[float, int]:
    """Validate a command payload; reject rather than silently overdrive."""

    try:
        value = float(intensity)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"intensity must be a number, got {intensity!r}") from exc
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"intensity must be between 0 and 1, got {value}")

    try:
        duration = int(duration_ms)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"duration_ms must be an integer, got {duration_ms!r}"
        ) from exc
    if not 10 <= duration <= 2000:
        raise ValueError(f"duration_ms must be between 10 and 2000, got {duration}")
    return value, duration


class MockDriver:
    """Records pulses so the pipeline can be verified without an actuator."""

    def __init__(self) -> None:
        self.pulses: list[tuple[float, int]] = []

    def pulse(self, intensity: float, duration_ms: int) -> tuple[float, int]:
        value, duration = normalize_pulse(intensity, duration_ms)
        self.pulses.append((value, duration))
        logger.info(
            "MOCK pulse intensity=%.2f duration=%dms (total=%d)",
            value,
            duration,
            len(self.pulses),
        )
        return value, duration

    def close(self) -> None:
        pass

    def describe(self) -> str:
        return "mock actuator (no hardware)"


class SerialDriver:
    """Line-protocol driver for an Arduino/ESP32 haptic controller."""

    def __init__(
        self,
        port: str,
        baud_rate: int,
        serial_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self._serial_factory = serial_factory or self._default_factory
        self._serial = self._open()

    @staticmethod
    def _default_factory(**kwargs: Any) -> Any:
        try:
            import serial
        except ImportError as exc:
            raise HapticsUnavailable(
                "pyserial is required for the serial driver; "
                "install it with: pip install pyserial"
            ) from exc
        return serial.Serial(**kwargs)

    def _open(self) -> Any:
        try:
            return self._serial_factory(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=0.2,
                write_timeout=1.0,
            )
        except HapticsUnavailable:
            raise
        except Exception as exc:
            raise HapticsUnavailable(
                f"could not open serial port {self.port} at {self.baud_rate} baud: {exc}"
            ) from exc

    def _reopen(self) -> None:
        try:
            self._serial.close()
        except Exception:
            pass
        self._serial = self._open()
        logger.warning("reopened serial port %s", self.port)

    def _write(self, line: bytes) -> None:
        try:
            # Drop stale acks/READY lines so readline() sees this pulse's reply.
            self._serial.reset_input_buffer()
        except Exception:
            pass
        try:
            self._serial.write(line)
            self._serial.flush()
        except Exception as exc:
            raise HapticsUnavailable(f"serial write failed: {exc}") from exc

        try:
            ack = self._serial.readline().decode("ascii", "replace").strip()
            if ack:
                logger.debug("actuator ack: %s", ack)
        except Exception:
            # Acks are useful but must not make a delivered pulse look failed.
            pass

    def pulse(self, intensity: float, duration_ms: int) -> tuple[float, int]:
        value, duration = normalize_pulse(intensity, duration_ms)
        line = f"PULSE {value:.2f} {duration}\n".encode("ascii")
        try:
            self._write(line)
        except HapticsUnavailable:
            # USB serial devices can disappear and return; retry once.
            self._reopen()
            self._write(line)
        logger.info(
            "serial pulse -> %s intensity=%.2f duration=%dms",
            self.port,
            value,
            duration,
        )
        return value, duration

    def close(self) -> None:
        try:
            self._serial.close()
        except Exception:
            pass

    def describe(self) -> str:
        return f"serial {self.port} @ {self.baud_rate} baud"


def build_driver(config: Any) -> HapticDriver:
    if config.driver == "mock":
        return MockDriver()
    if config.driver == "serial":
        if not config.serial_port:
            raise HapticsUnavailable(
                "NB_HAPTICS_SERIAL_PORT is required for the serial driver"
            )
        return SerialDriver(config.serial_port, config.baud_rate)
    raise HapticsUnavailable(f"unknown haptics driver: {config.driver!r}")
