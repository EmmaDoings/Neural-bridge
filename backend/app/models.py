from typing import Literal

from pydantic import BaseModel, Field


PresetName = Literal[
    "surgery",
    "gaming",
    "meditation",
    "conversation",
    "creative",
    "navigation",
    "idle",
]


class WaveBands(BaseModel):
    alpha: float = Field(ge=0, le=1)
    beta: float = Field(ge=0, le=1)
    theta: float = Field(ge=0, le=1)


class CognitiveMetrics(BaseModel):
    focus: float = Field(ge=0, le=1)
    meditation: float = Field(ge=0, le=1)
    attention: float = Field(ge=0, le=1)


class Intent(BaseModel):
    label: str = Field(max_length=64)
    confidence: float = Field(ge=0, le=1)
    action: str = Field(max_length=128)
    color: str = Field(max_length=32)


class TelemetryFrame(BaseModel):
    timestamp: float
    preset: PresetName
    metrics: CognitiveMetrics
    waves: WaveBands
    intent: Intent
    source: str | None = Field(default=None, max_length=64)
    # A one-frame pulse emitted when a discrete intent fires (sustained focus
    # or an EMG clench). The dashboard/hologram can react without re-firing.
    triggered: bool = False


DeviceKind = Literal["eeg", "hologram", "haptics", "audio", "vision", "mock"]


class DeviceRegistration(BaseModel):
    name: str = Field(max_length=64)
    kind: DeviceKind = "eeg"


class DeviceCommand(BaseModel):
    action: str = Field(max_length=64)
    payload: dict = Field(default_factory=dict)


class HapticPulse(BaseModel):
    """One bounded pulse for a connected haptics actuator."""

    intensity: float = Field(default=0.7, ge=0.0, le=1.0)
    duration_ms: int = Field(default=200, ge=10, le=2000)
    # Optional target when more than one haptics device is registered.
    device_id: str | None = Field(default=None, max_length=64)


class IntentRespondRequest(BaseModel):
    """Context sent by the dashboard for one cognitive or voice interaction."""

    frame: TelemetryFrame
    transcript: str | None = Field(default=None, max_length=1000)


class IntentRespondResult(BaseModel):
    text: str
    provider: Literal["gemini", "fallback"]
    latency_ms: int = Field(ge=0)
