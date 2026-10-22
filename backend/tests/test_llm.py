from __future__ import annotations

import asyncio

import pytest

from app.config import settings
from app.llm import _extract_text, _prompt, intent_service
from app.models import IntentRespondRequest, TelemetryFrame


def request(*, transcript: str | None = None) -> IntentRespondRequest:
    return IntentRespondRequest(
        frame=TelemetryFrame(
            timestamp=1.0,
            preset="conversation",
            metrics={"focus": 0.7, "meditation": 0.4, "attention": 0.8},
            waves={"alpha": 0.3, "beta": 0.5, "theta": 0.2},
            intent={
                "label": "precision_execution",
                "confidence": 0.9,
                "action": "select",
                "color": "#38bdf8",
            },
            triggered=True,
        ),
        transcript=transcript,
    )


def test_extract_text_accepts_a_complete_response() -> None:
    body = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {"parts": [{"text": " Focus on the next breath. "}]},
            }
        ]
    }
    assert _extract_text(body) == "Focus on the next breath."


def test_extract_text_rejects_a_truncated_response() -> None:
    body = {
        "candidates": [
            {
                "finishReason": "MAX_TOKENS",
                "content": {"parts": [{"text": "Expand your mental"}]},
            }
        ]
    }
    with pytest.raises(ValueError, match="MAX_TOKENS"):
        _extract_text(body)


def test_extract_text_rejects_an_empty_response() -> None:
    with pytest.raises(ValueError):
        _extract_text({"candidates": []})
    with pytest.raises(ValueError):
        _extract_text({"candidates": [{"finishReason": "STOP", "content": {"parts": []}}]})


def test_prompt_carries_preset_waves_and_metrics() -> None:
    prompt = _prompt(request(transcript="One cue."))
    assert "preset=conversation" in prompt
    assert "alpha=0.30" in prompt
    assert "beta=0.50" in prompt
    assert "theta=0.20" in prompt
    assert "One cue." in prompt


def test_service_returns_gemini_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "intent_rate_limit_seconds", 0.0)
    monkeypatch.setattr("app.llm._generate_sync", lambda _request: "Stay with the breath.")
    intent_service.reset()

    result = asyncio.run(intent_service.respond(request(), client_key="unit"))

    assert result.provider == "gemini"
    assert result.text == "Stay with the breath."


def test_service_falls_back_on_a_network_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "intent_rate_limit_seconds", 0.0)
    intent_service.reset()

    def timeout(_request: IntentRespondRequest) -> str:
        raise TimeoutError("simulated socket timeout")

    monkeypatch.setattr("app.llm._generate_sync", timeout)

    result = asyncio.run(
        intent_service.respond(request(transcript="One cue."), client_key="unit")
    )

    assert result.provider == "fallback"
    assert "One cue." in result.text
