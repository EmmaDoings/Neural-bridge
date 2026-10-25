from __future__ import annotations

import pytest

from nb_common.config import ConfigError
from nb_haptics.config import HapticsConfig
from nb_haptics.controller import HapticsController
from nb_haptics.drivers import (
    HapticsUnavailable,
    MockDriver,
    SerialDriver,
    build_driver,
    normalize_pulse,
)


ENV_VARS = (
    "NB_HAPTICS_API_BASE",
    "NB_API_BASE",
    "NB_HAPTICS_DRIVER",
    "NB_HAPTICS_SERIAL_PORT",
    "NB_HAPTICS_DEVICE_NAME",
    "NB_HAPTICS_BAUD",
    "NB_HAPTICS_REQUEST_TIMEOUT",
    "NB_HAPTICS_REGISTRATION_KEY",
    "NB_DEVICE_REGISTRATION_KEY",
    "NB_HAPTICS_LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def clear_haptics_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_config_defaults_to_mock_and_local_backend() -> None:
    config = HapticsConfig.from_env()
    assert config.api_base == "http://localhost:8000"
    assert config.device_name == "haptic-hologram"
    assert config.device_kind == "haptics"
    assert config.driver == "mock"
    assert config.serial_port is None
    assert config.baud_rate == 115200
    assert config.registration_key is None
    assert config.interval_seconds == 1.0


def test_config_uses_shared_api_base_and_registration_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NB_API_BASE", "https://example.test/")
    monkeypatch.setenv("NB_DEVICE_REGISTRATION_KEY", "enroll-me")
    config = HapticsConfig.from_env()
    assert config.api_base == "https://example.test"
    assert config.registration_key == "enroll-me"


def test_haptics_specific_values_override_shared_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NB_API_BASE", "https://shared.test")
    monkeypatch.setenv("NB_HAPTICS_API_BASE", "http://127.0.0.1:9000/")
    monkeypatch.setenv("NB_DEVICE_REGISTRATION_KEY", "shared")
    monkeypatch.setenv("NB_HAPTICS_REGISTRATION_KEY", "specific")
    monkeypatch.setenv("NB_HAPTICS_DEVICE_NAME", "desk-haptics")
    config = HapticsConfig.from_env()
    assert config.api_base == "http://127.0.0.1:9000"
    assert config.registration_key == "specific"
    assert config.device_name == "desk-haptics"


def test_config_rejects_unknown_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NB_HAPTICS_DRIVER", "usb-magic")
    with pytest.raises(ConfigError):
        HapticsConfig.from_env()


def test_config_rejects_invalid_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NB_HAPTICS_API_BASE", "ftp://example.test")
    with pytest.raises(ConfigError):
        HapticsConfig.from_env()


def test_build_driver_requires_serial_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NB_HAPTICS_DRIVER", "serial")
    config = HapticsConfig.from_env()
    with pytest.raises(HapticsUnavailable):
        build_driver(config)


@pytest.mark.parametrize(
    ("intensity", "duration"),
    [(-0.01, 100), (1.01, 100), ("x", 100), (0.5, 9), (0.5, 2001), (0.5, "x")],
)
def test_normalize_pulse_rejects_out_of_range(intensity: object, duration: object) -> None:
    with pytest.raises(ValueError):
        normalize_pulse(intensity, duration)


def test_normalize_pulse_accepts_boundaries() -> None:
    assert normalize_pulse(0.0, 10) == (0.0, 10)
    assert normalize_pulse(1.0, 2000) == (1.0, 2000)
    assert normalize_pulse("0.25", "100") == (0.25, 100)


def test_mock_driver_records_pulses() -> None:
    driver = MockDriver()
    assert driver.pulse(0.4, 120) == (0.4, 120)
    assert driver.pulse(1.0, 2000) == (1.0, 2000)
    assert driver.pulses == [(0.4, 120), (1.0, 2000)]
    assert "mock" in driver.describe()


class FakeDriver:
    def __init__(self) -> None:
        self.pulses: list[tuple[float, int]] = []

    def pulse(self, intensity: float, duration_ms: int) -> tuple[float, int]:
        value, duration = normalize_pulse(intensity, duration_ms)
        self.pulses.append((value, duration))
        return value, duration

    def close(self) -> None:
        pass

    def describe(self) -> str:
        return "fake"


def test_controller_dispatches_pulse_and_ignores_invalid() -> None:
    driver = FakeDriver()
    controller = HapticsController(driver)
    controller.on_command("pulse", {"intensity": 0.3, "duration_ms": 90})
    controller.on_command("haptic_pulse", {"intensity": 0.8, "duration_ms": 500})
    controller.on_command("pulse", {"intensity": 4.0, "duration_ms": 90})
    controller.on_command("ping", {})
    controller.on_command("unknown", {})
    assert driver.pulses == [(0.3, 90), (0.8, 500)]
    assert controller.pulse_count == 2
    assert controller.last_pulse == (0.8, 500)


class FakeSerial:
    def __init__(self, *, fail_write: bool = False, ack: bytes = b"OK\n") -> None:
        self.fail_write = fail_write
        self.ack = ack
        self.writes: list[bytes] = []
        self.closed = False
        self.input_resets = 0

    def reset_input_buffer(self) -> None:
        self.input_resets += 1

    def write(self, data: bytes) -> None:
        if self.fail_write:
            raise OSError("serial disappeared")
        self.writes.append(data)

    def flush(self) -> None:
        pass

    def readline(self) -> bytes:
        return self.ack

    def close(self) -> None:
        self.closed = True


def test_serial_driver_writes_line_protocol() -> None:
    created: list[FakeSerial] = []
    kwargs_seen: dict = {}

    def factory(**kwargs: object) -> FakeSerial:
        kwargs_seen.update(kwargs)
        serial = FakeSerial()
        created.append(serial)
        return serial

    driver = SerialDriver("COM4", 115200, serial_factory=factory)
    assert driver.pulse(0.7, 200) == (0.7, 200)
    assert kwargs_seen["port"] == "COM4"
    assert kwargs_seen["baudrate"] == 115200
    assert created[0].writes == [b"PULSE 0.70 200\n"]
    assert created[0].input_resets == 1
    driver.close()
    assert created[0].closed is True


def test_serial_driver_reopens_once_after_write_failure() -> None:
    first = FakeSerial(fail_write=True)
    second = FakeSerial()
    created = [first, second]

    def factory(**kwargs: object) -> FakeSerial:
        return created.pop(0)

    driver = SerialDriver("COM4", 115200, serial_factory=factory)
    assert driver.pulse(0.5, 150) == (0.5, 150)
    assert first.closed is True
    assert second.writes == [b"PULSE 0.50 150\n"]


def test_serial_driver_open_failure_is_clear() -> None:
    def factory(**kwargs: object) -> FakeSerial:
        raise OSError("access denied")

    with pytest.raises(HapticsUnavailable, match="could not open serial port"):
        SerialDriver("COM4", 115200, serial_factory=factory)
