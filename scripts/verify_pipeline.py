"""End-to-end verification for the backend contract and the hardware bridge.

Run with the hardware environment (it needs ``websockets``):

    hardware/.venv/Scripts/python.exe scripts/verify_pipeline.py

The script starts a throw-away backend in live mode on a free port, then:

1. **Contract** - registers a device, pushes telemetry over the device socket,
   asserts ``triggered`` survives the round trip, asserts a malformed frame is
   ignored without closing the socket, asserts commands are delivered, and
   asserts the device never receives its own telemetry echo.
2. **Pipeline** - runs the synthetic BrainFlow bridge and asserts real frames
   arrive on ``/ws/telemetry`` with valid ranges.

Exit code 0 means every assertion passed.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import websockets

REPO = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO / "backend"


def venv_python() -> Path:
    candidates = [
        REPO / ".venv" / "Scripts" / "python.exe",
        REPO / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit("could not find the backend virtualenv (.venv)")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def post_json(url: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_health(base: str, timeout: float = 40.0) -> dict:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return get_json(f"{base}/health")
        except Exception as exc:  # server still booting
            last_error = exc
            time.sleep(0.3)
    raise RuntimeError(f"backend never became healthy: {last_error}")


def sample_frame(label: str, triggered: bool) -> dict:
    return {
        "timestamp": time.time(),
        "preset": "conversation",
        "metrics": {"focus": 0.7, "meditation": 0.4, "attention": 0.8},
        "waves": {"alpha": 0.3, "beta": 0.5, "theta": 0.2},
        "intent": {
            "label": label,
            "confidence": 0.9,
            "action": "select",
            "color": "#38bdf8",
        },
        "source": None,
        "triggered": triggered,
    }


async def contract_check(base: str, port: int) -> None:
    registration = post_json(
        f"{base}/devices",
        {"name": "verify-device", "kind": "eeg"},
        {"X-Registration-Key": "verify-registration-key"},
    )
    device_id = registration["id"]
    api_key = registration["api_key"]
    telemetry_url = f"ws://127.0.0.1:{port}/ws/telemetry?kind=eeg"
    device_url = (
        f"ws://127.0.0.1:{port}/ws/devices/{device_id}?api_key={api_key}"
    )

    try:
        async with (
            websockets.connect(telemetry_url, open_timeout=10) as telemetry,
            websockets.connect(device_url, open_timeout=10) as device,
        ):
            # Both sockets have been accepted; the server subscribes right
            # after accept(), so a short yield avoids a race on the first send.
            await asyncio.sleep(0.1)

            await device.send(
                json.dumps({"type": "telemetry", "payload": sample_frame("first", True)})
            )
            first = json.loads(await asyncio.wait_for(telemetry.recv(), 5))
            assert first["intent"]["label"] == "first", first
            assert first["triggered"] is True, first
            assert first["source"] == device_id, first

            # Malformed frame must be dropped, then the socket must still work.
            await device.send(
                json.dumps({"type": "telemetry", "payload": {"timestamp": "nope"}})
            )
            await device.send(
                json.dumps({"type": "telemetry", "payload": sample_frame("second", False)})
            )
            second = json.loads(await asyncio.wait_for(telemetry.recv(), 5))
            assert second["intent"]["label"] == "second", second
            assert second["triggered"] is False, second

            # A device credential is required to issue physical commands.
            try:
                post_json(
                    f"{base}/devices/{device_id}/command",
                    {"action": "set_preset", "payload": {"preset": "gaming"}},
                )
            except urllib.error.HTTPError as exc:
                assert exc.code == 401, exc
            else:
                raise AssertionError("unauthenticated command was accepted")

            post_json(
                f"{base}/devices/{device_id}/command",
                {"action": "set_preset", "payload": {"preset": "gaming"}},
                {"X-Api-Key": api_key},
            )
            command = json.loads(await asyncio.wait_for(device.recv(), 5))
            assert command["type"] == "command", command
            assert command["action"] == "set_preset", command
            assert command["payload"]["preset"] == "gaming", command

            # The device socket must not echo the device's own frames.
            try:
                extra = await asyncio.wait_for(device.recv(), 1.0)
            except asyncio.TimeoutError:
                extra = None
            assert extra is None, f"device received its own echo: {extra}"
    finally:
        try:
            request = urllib.request.Request(
                f"{base}/devices/{device_id}",
                headers={"X-Api-Key": api_key},
                method="DELETE",
            )
            with urllib.request.urlopen(request, timeout=10):
                pass
        except Exception:
            pass


async def collect_frames(url: str, seconds: float) -> list[dict]:
    frames: list[dict] = []
    async with websockets.connect(url, open_timeout=10) as socket:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if isinstance(raw, bytes):
                continue
            frames.append(json.loads(raw))
    return frames


def run_bridge_check(base: str, port: int, bridge_python: Path) -> list[dict]:
    bridge_env = os.environ.copy()
    bridge_env.update(
        {
            "NB_API_BASE": base,
            "NB_BOARD": "synthetic",
            "NB_UPDATE_HZ": "5",
            "NB_CALIBRATION_SECONDS": "0",
            "NB_LOG_LEVEL": "WARNING",
            "NB_DEVICE_REGISTRATION_KEY": "verify-registration-key",
        }
    )
    bridge = subprocess.Popen(
        [str(bridge_python), "-m", "nb_bridge", "--duration", "12"],
        cwd=REPO / "hardware",
        env=bridge_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        frames = asyncio.run(
            collect_frames(f"ws://127.0.0.1:{port}/ws/telemetry", 10.0)
        )
    finally:
        if bridge.poll() is None:
            bridge.terminate()
            try:
                bridge.wait(timeout=10)
            except subprocess.TimeoutExpired:
                bridge.kill()

    assert len(frames) >= 20, f"expected >=20 frames, got {len(frames)}"
    sources = {frame.get("source") for frame in frames}
    assert len(sources) == 1 and None not in sources, sources
    timestamps = [frame["timestamp"] for frame in frames]
    assert timestamps == sorted(timestamps), "timestamps must be monotonic"

    for frame in frames:
        assert frame["preset"] == "conversation", frame
        assert isinstance(frame["triggered"], bool), frame
        for key in ("focus", "meditation", "attention"):
            assert 0.0 <= frame["metrics"][key] <= 1.0, frame
        for key in ("alpha", "beta", "theta"):
            assert 0.0 <= frame["waves"][key] <= 1.0, frame
        assert 0.0 <= frame["intent"]["confidence"] <= 1.0, frame
        assert frame["intent"]["color"].startswith("#"), frame
    return frames


def main() -> int:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    backend_env = os.environ.copy()
    backend_env["NEURAL_BRIDGE_MODE"] = "live"
    # The verifier has no browser origin and must never spend a Gemini call.
    backend_env["CORS_ORIGINS"] = "http://localhost:3000"
    backend_env["GEMINI_API_KEY"] = ""
    backend_env["DEVICE_REGISTRATION_KEY"] = "verify-registration-key"

    backend = subprocess.Popen(
        [
            str(venv_python()),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=BACKEND_DIR,
        env=backend_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        health = wait_for_health(base)
        print(f"health: {health}")
        assert health["status"] == "ok", health
        assert health["mode"] == "live", health

        asyncio.run(contract_check(base, port))
        print("contract: OK (triggered, malformed frames, commands, no self-echo)")

        frames = run_bridge_check(base, port, Path(sys.executable))
        print(f"pipeline: OK ({len(frames)} frames, source {frames[0]['source']})")
        print("E2E VERIFICATION PASSED")
        return 0
    finally:
        backend.terminate()
        try:
            backend.wait(timeout=10)
        except subprocess.TimeoutExpired:
            backend.kill()


if __name__ == "__main__":
    raise SystemExit(main())
