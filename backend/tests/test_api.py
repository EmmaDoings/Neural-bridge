from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.device_bus import bus
from app.llm import intent_service
from app.main import app


@pytest.fixture(autouse=True)
def clean_state(monkeypatch: pytest.MonkeyPatch) -> None:
    bus._devices.clear()  # type: ignore[attr-defined]
    bus._channels.clear()  # type: ignore[attr-defined]
    bus._commands.clear()  # type: ignore[attr-defined]
    intent_service.reset()
    monkeypatch.setattr(settings, "device_registration_key", None)
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "intent_rate_limit_seconds", 0.0)


def frame(*, triggered: bool = True) -> dict:
    return {
        "timestamp": 1.0,
        "preset": "conversation",
        "metrics": {"focus": 0.7, "meditation": 0.4, "attention": 0.8},
        "waves": {"alpha": 0.3, "beta": 0.5, "theta": 0.2},
        "intent": {
            "label": "precision_execution",
            "confidence": 0.9,
            "action": "select",
            "color": "#38bdf8",
        },
        "triggered": triggered,
    }


def test_registration_secret_and_device_key_protect_mutations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "device_registration_key", "enroll-me")
    with TestClient(app) as client:
        rejected = client.post("/devices", json={"name": "headset", "kind": "eeg"})
        assert rejected.status_code == 401

        registered = client.post(
            "/devices",
            json={"name": "headset", "kind": "eeg"},
            headers={"X-Registration-Key": "enroll-me"},
        )
        assert registered.status_code == 200
        device = registered.json()

        unauthorized = client.delete(f"/devices/{device['id']}")
        assert unauthorized.status_code == 401
        removed = client.delete(
            f"/devices/{device['id']}", headers={"X-Api-Key": device["api_key"]}
        )
        assert removed.status_code == 200


def test_intent_response_uses_fallback_without_a_server_key() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/intent/respond",
            json={"frame": frame(), "transcript": "What should I focus on?"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "fallback"
    assert "What should I focus on?" in body["text"]
    assert body["latency_ms"] >= 0


def test_intent_response_requires_an_event_or_voice_transcript() -> None:
    with TestClient(app) as client:
        response = client.post("/intent/respond", json={"frame": frame(triggered=False)})
    assert response.status_code == 400


def test_intent_response_rate_limits_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "intent_rate_limit_seconds", 60.0)
    with TestClient(app) as client:
        first = client.post("/intent/respond", json={"frame": frame()})
        second = client.post("/intent/respond", json={"frame": frame()})
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["retry-after"] == "60"


def test_intent_rate_limit_is_per_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "intent_rate_limit_seconds", 60.0)
    with TestClient(app) as client:
        first = client.post(
            "/intent/respond",
            json={"frame": frame()},
            headers={"X-Forwarded-For": "203.0.113.10"},
        )
        other = client.post(
            "/intent/respond",
            json={"frame": frame()},
            headers={"X-Forwarded-For": "203.0.113.11"},
        )
        repeat = client.post(
            "/intent/respond",
            json={"frame": frame()},
            headers={"X-Forwarded-For": "203.0.113.10"},
        )
    assert first.status_code == 200
    assert other.status_code == 200
    assert repeat.status_code == 429
