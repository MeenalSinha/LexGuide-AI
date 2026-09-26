"""
Central configuration.

In production this reads from environment variables (see .env.example at
the repo root). For the prototype we default to local/demo-friendly values
so the app runs with zero external services.
"""
import os

class Settings:
    APP_NAME: str = "LexGuide AI"
    ENV: str = os.getenv("ENV", "development")

    # --- Database -----------------------------------------------------
    # Prototype uses SQLite for zero-setup local/demo runs. The schema is
    # written in portable SQLAlchemy so swapping DATABASE_URL to a Postgres
    # DSN (e.g. postgresql+psycopg://user:pass@host/db) requires no model
    # changes. See docs/architecture.md for the pgvector upgrade path.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./lexguide.db")

    # --- Storage --------------------------------------------------------
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./storage/uploads")
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "25"))
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

    # --- AI provider ------------------------------------------------------
    # "demo" = deterministic, offline, no external API calls (used by default
    # so the whole product is demonstrable without credentials).
    # "anthropic" = calls the real Claude API if ANTHROPIC_API_KEY is set.
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "demo")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # --- Retrieval -------------------------------------------------------
    CHUNK_SIZE_CHARS: int = 1200
    CHUNK_OVERLAP_CHARS: int = 150
    RETRIEVAL_TOP_K: int = 6
    GROUNDING_MIN_SCORE: float = 0.12  # below this -> "not found in document"

    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8080,*").split(",")

    # --- Rate limiting ----------------------------------------------------
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))

settings = Settings()
