"""Command handling for the haptics bridge.

The backend sends ``{"type": "command", "action": "pulse", "payload": {...}}``
over the same device socket the EEG bridge uses. The controller validates the
payload and hands it to the selected actuator driver.
"""

from __future__ import annotations

import logging

from .drivers import HapticDriver, HapticsUnavailable

logger = logging.getLogger("nb_haptics.controller")


class HapticsController:
    """Dispatches backend commands to one actuator driver."""

    def __init__(self, driver: HapticDriver) -> None:
        self.driver = driver
        self.pulse_count = 0
        self.last_pulse: tuple[float, int] | None = None

    def on_command(self, action: str, payload: dict) -> None:
        if action in ("pulse", "haptic_pulse"):
            intensity = payload.get("intensity", 0.7)
            duration_ms = payload.get("duration_ms", 200)
            try:
                self.last_pulse = self.driver.pulse(intensity, duration_ms)
            except (ValueError, HapticsUnavailable) as exc:
                # A bad command or a disconnected actuator must not tear down
                # the device socket. The next pulse can retry.
                logger.warning("rejected haptic pulse: %s", exc)
                return
            self.pulse_count += 1
            logger.info(
                "pulse delivered intensity=%.2f duration=%dms (total=%d)",
                self.last_pulse[0],
                self.last_pulse[1],
                self.pulse_count,
            )
        elif action == "ping":
            logger.debug("ping from backend")
        else:
            logger.info("unhandled command %r", action)
