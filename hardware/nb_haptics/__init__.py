"""Local haptics bridge for the Neural Bridge backend."""

from .config import HapticsConfig
from .controller import HapticsController
from .drivers import (
    HapticDriver,
    HapticsUnavailable,
    MockDriver,
    SerialDriver,
    build_driver,
    normalize_pulse,
)

__all__ = [
    "HapticDriver",
    "HapticsConfig",
    "HapticsController",
    "HapticsUnavailable",
    "MockDriver",
    "SerialDriver",
    "build_driver",
    "normalize_pulse",
]
