"""Backward-compatible import surface for the shared device client.

The implementation lives in :mod:`nb_common.client` so the haptics bridge can
reuse the same registration, reconnect, and command handling without importing
BrainFlow.
"""

from nb_common.client import (
    ClientConfig,
    CommandHandler,
    DeviceClient,
    FrameProducer,
    RegistrationError,
    device_ws_url,
)

__all__ = [
    "ClientConfig",
    "CommandHandler",
    "DeviceClient",
    "FrameProducer",
    "RegistrationError",
    "device_ws_url",
]
