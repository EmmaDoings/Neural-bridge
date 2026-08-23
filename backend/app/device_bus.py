import asyncio
import secrets
import time
from typing import Any


class DeviceBus:
    """In-memory device registry and pub/sub broker.

    Devices push telemetry into named channels; subscribers (web clients,
    holograms, haptics, etc.) receive broadcasts. Commands are queued per
    connected device.
    """

    def __init__(self) -> None:
        self._devices: dict[str, dict[str, Any]] = {}
        self._channels: dict[str, list[asyncio.Queue]] = {}
        self._commands: dict[str, asyncio.Queue] = {}

    def register(self, name: str, kind: str) -> dict[str, Any]:
        device = {
            "id": secrets.token_hex(4),
            "name": name,
            "kind": kind,
            "api_key": secrets.token_hex(32),
            "connected": False,
            "last_seen": 0.0,
            "metadata": {},
        }
        self._devices[device["id"]] = device
        return device

    def list_devices(self) -> list[dict[str, Any]]:
        return [
            {
                "id": device["id"],
                "name": device["name"],
                "kind": device["kind"],
                "connected": device["connected"],
                "last_seen": device["last_seen"],
            }
            for device in self._devices.values()
        ]

    def get(self, device_id: str) -> dict[str, Any] | None:
        return self._devices.get(device_id)

    def remove(self, device_id: str) -> bool:
        if device_id not in self._devices:
            return False
        del self._devices[device_id]
        self._commands.pop(device_id, None)
        return True

    def authenticate(self, device_id: str, api_key: str | None) -> bool:
        device = self._devices.get(device_id)
        return bool(device and device["api_key"] == api_key)

    def mark_connected(self, device_id: str, connected: bool) -> None:
        device = self._devices.get(device_id)
        if device:
            device["connected"] = connected
            device["last_seen"] = time.time()

    def subscribe(self, topic: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._channels.setdefault(topic, []).append(queue)
        return queue

    def unsubscribe(self, topic: str, queue: asyncio.Queue) -> None:
        try:
            self._channels[topic].remove(queue)
        except (KeyError, ValueError):
            pass

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        for queue in list(self._channels.get(topic, [])):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(payload)
        if topic != "*":
            await self.publish("*", payload)

    def command_queue(self, device_id: str) -> asyncio.Queue:
        return self._commands.setdefault(device_id, asyncio.Queue(maxsize=64))

    async def send_command(self, device_id: str, payload: dict[str, Any]) -> bool:
        if device_id not in self._commands:
            return False
        self._commands[device_id].put_nowait(payload)
        return True


bus = DeviceBus()
