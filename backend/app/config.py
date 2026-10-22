import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings:
    mode: str = os.getenv("NEURAL_BRIDGE_MODE", "mock")
    host: str = os.getenv("NEURAL_BRIDGE_HOST", "0.0.0.0")
    port: int = int(os.getenv("NEURAL_BRIDGE_PORT", "8000"))
    cors_origins: list[str] = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ]
    # Optional regex for origins that cannot be listed explicitly, e.g. Vercel
    # preview deployments: https://.*\.vercel\.app
    cors_origin_regex: str | None = os.getenv("CORS_ORIGIN_REGEX") or None
    # Optional shared secret for enrolling new hardware bridges. Leave unset
    # for a local demo; set it for any internet-facing deployment.
    device_registration_key: str | None = os.getenv("DEVICE_REGISTRATION_KEY") or None
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_timeout_seconds: float = max(
        1.0, float(os.getenv("GEMINI_TIMEOUT_SECONDS", "8"))
    )
    gemini_max_output_tokens: int = max(
        32, int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "160"))
    )
    # 0 disables Gemini "thinking" so short replies are not truncated. Set -1
    # to omit the thinkingConfig field entirely for models that reject it.
    gemini_thinking_budget: int = int(os.getenv("GEMINI_THINKING_BUDGET", "0"))
    intent_rate_limit_seconds: float = max(
        0.0, float(os.getenv("INTENT_RATE_LIMIT_SECONDS", "3"))
    )
    secret_key: str | None = os.getenv("SECRET_KEY") or None
    jwt_secret: str | None = os.getenv("JWT_SECRET") or None


settings = Settings()
