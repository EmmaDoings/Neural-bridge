"""Shared configuration helpers for the local device bridges."""

from __future__ import annotations

import os
from urllib.parse import urlparse


class ConfigError(ValueError):
    """Raised when an environment variable cannot be turned into a config."""


def get_env(name: str, default: str | None = None) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    return raw or default


def get_float(
    name: str,
    default: float,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    raw = get_env(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {value}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"{name} must be <= {maximum}, got {value}")
    return value


def get_int(
    name: str,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    value = get_float(name, float(default), minimum=minimum, maximum=maximum)
    return int(value)


def get_bool(name: str, default: bool) -> bool:
    raw = get_env(name)
    if raw is None:
        return default
    lowered = raw.lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} must be a boolean, got {raw!r}")


def validate_http_url(name: str, value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ConfigError(f"{name} must be an http(s) URL, got {value!r}")
    return value.rstrip("/")
