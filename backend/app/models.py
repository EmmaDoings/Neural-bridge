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
    label: str
    confidence: float = Field(ge=0, le=1)
    action: str
    color: str


class TelemetryFrame(BaseModel):
    timestamp: float
    preset: PresetName
    metrics: CognitiveMetrics
    waves: WaveBands
    intent: Intent
    source: str | None = None


DeviceKind = Literal["eeg", "hologram", "haptics", "audio", "vision", "mock"]


class DeviceRegistration(BaseModel):
    name: str
    kind: DeviceKind = "eeg"


class DeviceCommand(BaseModel):
    action: str
    payload: dict = Field(default_factory=dict)
