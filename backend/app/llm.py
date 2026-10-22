"""Small, bounded Gemini integration with a deterministic local fallback."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Literal

from fastapi import HTTPException

from app.config import settings
from app.models import IntentRespondRequest, IntentRespondResult

logger = logging.getLogger("app.llm")


def fallback_response(request: IntentRespondRequest) -> str:
    """Produce a useful response when Gemini is unconfigured or unavailable."""

    intent = request.frame.intent.label.replace("_", " ")
    confidence = round(request.frame.intent.confidence * 100)
    if request.transcript:
        return (
            f"I heard: {request.transcript.strip()}. "
            f"Current state: {intent} at {confidence}% confidence. "
            f"Suggested action: {request.frame.intent.action}."
        )
    return (
        f"Current state: {intent} at {confidence}% confidence. "
        f"Suggested action: {request.frame.intent.action}."
    )


def _prompt(request: IntentRespondRequest) -> str:
    frame = request.frame
    spoken = request.transcript.strip() if request.transcript else "No spoken request was provided."
    return (
        "User request: " + spoken + "\n"
        "Telemetry context: "
        f"preset={frame.preset}; intent={frame.intent.label}; confidence={frame.intent.confidence:.2f}; "
        f"focus={frame.metrics.focus:.2f}; meditation={frame.metrics.meditation:.2f}; "
        f"attention={frame.metrics.attention:.2f}; "
        f"alpha={frame.waves.alpha:.2f}; beta={frame.waves.beta:.2f}; "
        f"theta={frame.waves.theta:.2f}; suggested_action={frame.intent.action}."
    )


def _extract_text(body: dict) -> str:
    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Gemini returned no candidates")
    candidate = candidates[0]
    if not isinstance(candidate, dict):
        raise ValueError("Gemini returned an invalid candidate")
    finish = candidate.get("finishReason")
    if finish in {
        "MAX_TOKENS",
        "SAFETY",
        "RECITATION",
        "BLOCKLIST",
        "PROHIBITED_CONTENT",
        "SPII",
    }:
        # Never surface a half sentence as if it were a complete reply.
        raise ValueError(f"Gemini stopped with finishReason={finish}")
    content = candidate.get("content", {})
    parts = content.get("parts", []) if isinstance(content, dict) else []
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not text.strip():
        raise ValueError("Gemini returned no text")
    return text.strip()


def _generate_sync(request: IntentRespondRequest) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    model = urllib.parse.quote(settings.gemini_model, safe="-._")
    key = urllib.parse.quote(settings.gemini_api_key, safe="")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    generation_config: dict = {
        "maxOutputTokens": settings.gemini_max_output_tokens,
        "temperature": 0.4,
    }
    # Flash models spend most of a small token budget on internal "thinking",
    # which can truncate the visible answer. Disabling it is faster and keeps
    # short replies whole. Set GEMINI_THINKING_BUDGET=-1 to omit the field for
    # models that do not support it.
    if settings.gemini_thinking_budget >= 0:
        generation_config["thinkingConfig"] = {
            "thinkingBudget": settings.gemini_thinking_budget
        }
    payload = {
        "contents": [{"role": "user", "parts": [{"text": _prompt(request)}]}],
        "systemInstruction": {
            "parts": [
                {
                    "text": (
                        "You are Neural Bridge, a concise assistant for an experimental "
                        "BCI dashboard. Use the telemetry only as interface context, never "
                        "as a medical diagnosis. Give one practical response in at most three sentences."
                    )
                }
            ]
        },
        "generationConfig": generation_config,
    }
    request_body = json.dumps(payload).encode("utf-8")
    http_request = urllib.request.Request(
        url,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            http_request, timeout=settings.gemini_timeout_seconds
        ) as response:
            return _extract_text(json.loads(response.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Gemini HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"Gemini request failed: {exc}") from exc


class IntentService:
    def __init__(self) -> None:
        self._last_request: dict[str, float] = {}

    def reset(self) -> None:
        """Clear the in-memory rate-limit state; used by backend tests."""

        self._last_request.clear()

    async def respond(
        self, request: IntentRespondRequest, *, client_key: str = "global"
    ) -> IntentRespondResult:
        if not request.frame.triggered and not request.transcript:
            raise HTTPException(
                status_code=400,
                detail="a response requires a triggered intent or a transcript",
            )

        now = time.monotonic()
        last = self._last_request.get(client_key, 0.0)
        retry_after = settings.intent_rate_limit_seconds - (now - last)
        if retry_after > 0:
            raise HTTPException(
                status_code=429,
                detail=f"try again in {retry_after:.1f} seconds",
                headers={"Retry-After": str(max(1, int(retry_after) + 1))},
            )
        self._last_request[client_key] = now
        if len(self._last_request) > 2048:
            cutoff = now - max(60.0, settings.intent_rate_limit_seconds * 4)
            self._last_request = {
                key: value
                for key, value in self._last_request.items()
                if value >= cutoff
            }
        started = time.monotonic()

        provider: Literal["gemini", "fallback"]
        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(_generate_sync, request),
                timeout=settings.gemini_timeout_seconds + 0.5,
            )
            provider = "gemini"
        except (
            asyncio.TimeoutError,
            urllib.error.URLError,
            urllib.error.HTTPError,
            OSError,
            ValueError,
            RuntimeError,
        ) as exc:
            # Log only the failure type and message. Never log the prompt,
            # transcript, or API key.
            logger.warning("Gemini unavailable (%s): %s", type(exc).__name__, exc)
            text = fallback_response(request)
            provider = "fallback"

        latency_ms = round((time.monotonic() - started) * 1000)
        logger.info("intent response provider=%s latency_ms=%d", provider, latency_ms)
        return IntentRespondResult(
            text=text,
            provider=provider,
            latency_ms=latency_ms,
        )


intent_service = IntentService()
