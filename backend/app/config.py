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
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    secret_key: str | None = os.getenv("SECRET_KEY") or None
    jwt_secret: str | None = os.getenv("JWT_SECRET") or None


settings = Settings()
