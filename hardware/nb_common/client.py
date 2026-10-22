"""Generic device registration + resilient WebSocket client.

Both the EEG bridge and the haptics bridge are clients of the same backend:

    POST /devices                      -> {id, api_key}
    WS   /ws/devices/{id}?api_key=...  <- commands
                                       -> telemetry frames (optional)

Reconnect rules, derived from the backend implementation:

* The device registry is in-memory, so a backend restart invalidates the key.
  Starlette closes an unauthenticated socket *before* accepting, which surfaces
  to the client as an HTTP 403 handshake (``InvalidStatus``), not a 4401 close
  frame. Both cases must re-register.
* A device socket may receive telemetry from other devices. Receivers ignore
  everything except ``type == "command"``.
* A command-only device (the haptics bridge) passes no producer. The client then
  skips the send loop and only reads commands.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from typing import Callable, Protocol
from urllib.parse import quote, urlparse

import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

logger = logging.getLogger("nb_common.client")

CommandHandler = Callable[[str, dict], None]
FrameProducer = Callable[[], dict | None]


class ClientConfig(Protocol):
    """The subset of a bridge config needed by :class:`DeviceClient`."""

    api_base: str
    device_name: str
    device_kind: str
    request_timeout: float
    registration_key: str | None
    interval_seconds: float


def device_ws_url(api_base: str, device_id: str, api_key: str) -> str:
    parsed = urlparse(api_base)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return (
        f"{scheme}://{parsed.netloc}/ws/devices/{quote(device_id)}"
        f"?api_key={quote(api_key)}"
    )


class RegistrationError(RuntimeError):
    """POST /devices failed."""


class DeviceClient:
    def __init__(
        self,
        config: ClientConfig,
        on_command: CommandHandler | None = None,
        producer: FrameProducer | None = None,
        fatal_exceptions: tuple[type[BaseException], ...] = (),
    ) -> None:
        self.config = config
        self.on_command = on_command
        self.producer = producer
        self.fatal_exceptions = fatal_exceptions
        self._registration: dict | None = None
        self._stopped = asyncio.Event()

    # -- registration ------------------------------------------------------
    def _register_sync(self) -> dict:
        payload = json.dumps(
            {"name": self.config.device_name, "kind": self.config.device_kind}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.config.api_base}/devices",
            data=payload,
            headers={
                "Content-Type": "application/json",
                **(
                    {"X-Registration-Key": self.config.registration_key}
                    if self.config.registration_key
                    else {}
                ),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.config.request_timeout
            ) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RegistrationError(
                f"POST /devices returned HTTP {exc.code}: {detail}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RegistrationError(
                f"could not reach {self.config.api_base}: {exc}"
            ) from exc

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RegistrationError(
                f"POST /devices returned non-JSON: {body[:200]!r}"
            ) from exc
        if not isinstance(data, dict) or "id" not in data or "api_key" not in data:
            raise RegistrationError(f"unexpected registration response: {data!r}")
        return data

    async def _ensure_registration(self) -> dict:
        if self._registration is None:
            self._registration = await asyncio.to_thread(self._register_sync)
            logger.info(
                "registered device %s (%s) as %s",
                self._registration["name"],
                self._registration["kind"],
                self._registration["id"],
            )
        return self._registration

    # -- streaming ---------------------------------------------------------
    async def _send_loop(self, socket, producer: FrameProducer) -> None:
        interval = self.config.interval_seconds
        while True:
            frame = await asyncio.to_thread(producer)
            if frame is not None:
                await socket.send(json.dumps({"type": "telemetry", "payload": frame}))
            await asyncio.sleep(interval)

    async def _recv_loop(self, socket) -> None:
        async for raw in socket:
            if isinstance(raw, bytes):
                continue
            try:
                message = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(message, dict):
                continue
            if message.get("type") != "command":
                # Telemetry from other devices may arrive here; commands only.
                continue
            action = message.get("action")
            payload = message.get("payload") or {}
            if not isinstance(action, str) or not isinstance(payload, dict):
                continue
            if self.on_command is None:
                continue
            try:
                self.on_command(action, payload)
            except Exception:  # a bad command must not kill the stream
                logger.exception("command handler failed for %r", action)

    async def _stream_once(self, producer: FrameProducer | None) -> None:
        registration = await self._ensure_registration()
        url = device_ws_url(
            self.config.api_base, registration["id"], registration["api_key"]
        )
        logger.info("connecting to %s", self.config.api_base)
        async with websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=20,
            open_timeout=self.config.request_timeout,
            max_size=1 << 20,
        ) as socket:
            if producer is None:
                logger.info("device socket connected; waiting for commands")
            else:
                logger.info(
                    "streaming telemetry at %.1f Hz",
                    getattr(self.config, "update_hz", 0.0),
                )
            sender = (
                asyncio.create_task(self._send_loop(socket, producer))
                if producer is not None
                else None
            )
            receiver = asyncio.create_task(self._recv_loop(socket))
            tasks = [receiver] + ([sender] if sender is not None else [])
            try:
                done, _ = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    error = task.exception()
                    if error is not None:
                        raise error
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self, producer: FrameProducer | None = None) -> None:
        producer = producer or self.producer
        backoff = 1.0
        while not self._stopped.is_set():
            try:
                await self._stream_once(producer)
            except InvalidStatus as exc:
                # Handshake rejected: the device registry was wiped (backend
                # restart) or the key is stale. Register again immediately.
                logger.warning("handshake rejected (%s); re-registering", exc)
                self._registration = None
                backoff = 1.0
            except ConnectionClosed as exc:
                if exc.code == 4401:
                    logger.warning("device key rejected (4401); re-registering")
                    self._registration = None
                    backoff = 1.0
                else:
                    logger.warning(
                        "socket closed (code %s): %s", exc.code, exc.reason
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # network, DNS, TLS, backend cold start
                if self.fatal_exceptions and isinstance(exc, self.fatal_exceptions):
                    # A physical disconnect is not a network problem; retrying
                    # would hammer a board that needs the operator's attention.
                    raise
                logger.warning("stream error: %s: %s", type(exc).__name__, exc)

            if self._stopped.is_set():
                break
            delay = max(1.0, min(backoff, 30.0))
            logger.info("reconnecting in %.0fs", delay)
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2.0, 30.0)

    def stop(self) -> None:
        self._stopped.set()
