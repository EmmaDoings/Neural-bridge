import asyncio
import json
import secrets
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from app.config import settings
from app.device_bus import bus
from app.llm import intent_service
from app.models import (
    DeviceCommand,
    DeviceRegistration,
    IntentRespondRequest,
    IntentRespondResult,
    PresetName,
    TelemetryFrame,
)
from app.simulator import PRESETS, generate_frame


async def mock_generator(device_id: str, interval: float = 0.18) -> None:
    while True:
        device = bus.get(device_id)
        preset: PresetName = "conversation"
        if device:
            preset = device.get("preset", "conversation")
        frame = generate_frame(preset)
        frame.source = device_id
        await bus.publish(device_id, frame.model_dump())
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.mode == "mock":
        device = bus.register("simulator", "mock")
        app.state.mock_device_id = device["id"]
        task = asyncio.create_task(mock_generator(device["id"]))
        yield
        task.cancel()
    else:
        yield


app = FastAPI(title="Neural Bridge API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": settings.mode}


@app.get("/presets")
async def presets() -> list[str]:
    return list(PRESETS.keys())


@app.get("/telemetry/{preset}")
async def telemetry(preset: PresetName = "conversation"):
    return generate_frame(preset)


@app.post("/intent/respond", response_model=IntentRespondResult)
async def respond_to_intent(
    request: IntentRespondRequest, http_request: Request
) -> IntentRespondResult:
    forwarded = http_request.headers.get("x-forwarded-for", "")
    client_key = forwarded.split(",")[0].strip()
    if not client_key:
        client_key = http_request.client.host if http_request.client else "unknown"
    return await intent_service.respond(request, client_key=client_key)


@app.put("/simulation/preset/{preset}")
async def set_simulation_preset(preset: PresetName) -> dict[str, str]:
    mock_id = getattr(app.state, "mock_device_id", None)
    if not mock_id:
        raise HTTPException(status_code=404, detail="mock simulator is not running")
    device = bus.get(mock_id)
    if device:
        device["preset"] = preset
    return {"status": "ok", "preset": preset}


@app.get("/devices")
async def list_devices() -> list[dict]:
    return bus.list_devices()


@app.post("/devices")
async def register_device(
    registration: DeviceRegistration,
    x_registration_key: str | None = Header(default=None),
) -> dict:
    if settings.device_registration_key is not None and not secrets.compare_digest(
        x_registration_key or "", settings.device_registration_key
    ):
        raise HTTPException(status_code=401, detail="invalid registration key")
    device = bus.register(registration.name, registration.kind)
    return {
        "id": device["id"],
        "api_key": device["api_key"],
        "name": device["name"],
        "kind": device["kind"],
    }


@app.delete("/devices/{device_id}")
async def remove_device(
    device_id: str, x_api_key: str | None = Header(default=None)
) -> dict[str, str]:
    if not bus.authenticate(device_id, x_api_key):
        raise HTTPException(status_code=401, detail="invalid api key")
    if not bus.remove(device_id):
        raise HTTPException(status_code=404, detail="device not found")
    return {"status": "removed"}


@app.post("/devices/{device_id}/telemetry")
async def ingest_telemetry(
    device_id: str,
    frame: TelemetryFrame,
    x_api_key: str | None = Header(default=None),
) -> dict[str, str]:
    if not bus.authenticate(device_id, x_api_key):
        raise HTTPException(status_code=401, detail="invalid api key")
    frame.source = device_id
    await bus.publish(device_id, frame.model_dump())
    return {"status": "ok", "device": device_id}


@app.post("/devices/{device_id}/command")
async def send_device_command(
    device_id: str,
    command: DeviceCommand,
    x_api_key: str | None = Header(default=None),
) -> dict[str, str]:
    if not bus.authenticate(device_id, x_api_key):
        raise HTTPException(status_code=401, detail="invalid api key")
    status = await bus.send_command(device_id, command.model_dump())
    if status == "not_connected":
        raise HTTPException(status_code=404, detail="device is not connected")
    if status == "full":
        raise HTTPException(status_code=429, detail="device command queue is full")
    return {"status": "queued", "device": device_id}


@app.websocket("/ws/telemetry")
async def telemetry_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    source_kind = websocket.query_params.get("kind")
    channel = bus.subscribe("*")
    get_task: asyncio.Task | None = None
    recv_task = asyncio.create_task(websocket.receive())
    try:
        while True:
            get_task = asyncio.create_task(channel.get())
            done, _ = await asyncio.wait(
                {get_task, recv_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if recv_task in done:
                message = recv_task.result()
                if message.get("type") == "websocket.disconnect":
                    return
                recv_task = asyncio.create_task(websocket.receive())
                get_task.cancel()
                continue
            payload = get_task.result()
            if source_kind is not None and bus.kind(payload.get("source")) != source_kind:
                continue
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        pass
    finally:
        if get_task:
            get_task.cancel()
        recv_task.cancel()
        bus.unsubscribe("*", channel)


@app.websocket("/ws/devices/{device_id}")
async def device_socket(websocket: WebSocket, device_id: str) -> None:
    api_key = websocket.query_params.get("api_key")
    if not bus.authenticate(device_id, api_key):
        await websocket.close(code=4401)
        return

    await websocket.accept()
    bus.mark_connected(device_id, True)
    commands = bus.command_queue(device_id)
    channel = bus.subscribe("*")

    async def handle_message(message: dict) -> None:
        if message.get("type") != "websocket.receive":
            return
        try:
            data = json.loads(message.get("text", "{}"))
        except (json.JSONDecodeError, TypeError):
            return
        if data.get("type") == "telemetry":
            try:
                frame = TelemetryFrame(**data.get("payload", {}))
            except (ValidationError, TypeError, ValueError):
                # A malformed frame from one device must not tear down its
                # command/telemetry socket.
                return
            frame.source = device_id
            await bus.publish(device_id, frame.model_dump())

    async def pump() -> None:
        command_task = asyncio.create_task(commands.get())
        event_task = asyncio.create_task(channel.get())
        recv_task = asyncio.create_task(websocket.receive())
        try:
            while True:
                done, _ = await asyncio.wait(
                    {command_task, event_task, recv_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    if task is recv_task:
                        message = task.result()
                        if message.get("type") == "websocket.disconnect":
                            return
                        await handle_message(message)
                        recv_task = asyncio.create_task(websocket.receive())
                    elif task is command_task:
                        payload = task.result()
                        await websocket.send_json({"type": "command", **payload})
                        command_task = asyncio.create_task(commands.get())
                    else:
                        payload = task.result()
                        # Do not echo a device's own frames back to it: the
                        # device socket is for commands, not a mirror.
                        if payload.get("source") == device_id:
                            event_task = asyncio.create_task(channel.get())
                            continue
                        await websocket.send_json({"type": "telemetry", **payload})
                        event_task = asyncio.create_task(channel.get())
        finally:
            command_task.cancel()
            event_task.cancel()
            recv_task.cancel()

    try:
        await pump()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        bus.unsubscribe("*", channel)
        bus.mark_connected(device_id, False)
