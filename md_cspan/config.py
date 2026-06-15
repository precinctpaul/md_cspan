from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    auth_mode: str
    api_key_header: str
    api_key_param: str
    timeout_seconds: int


def load_settings() -> Settings:
    load_dotenv(ENV_PATH)

    api_key = os.getenv("CSPAN_API_KEY", "").strip()
    base_url = os.getenv("CSPAN_API_BASE_URL", "").strip().rstrip("/")
    auth_mode = os.getenv("CSPAN_AUTH_MODE", "bearer").strip().lower()
    api_key_header = os.getenv("CSPAN_API_KEY_HEADER", "X-API-Key").strip()
    api_key_param = os.getenv("CSPAN_API_KEY_PARAM", "api_key").strip()

    timeout_raw = os.getenv("CSPAN_TIMEOUT_SECONDS", "30").strip()
    try:
        timeout_seconds = int(timeout_raw)
    except ValueError as exc:
        raise ValueError("CSPAN_TIMEOUT_SECONDS must be an integer.") from exc

    if not api_key:
        raise ValueError("Missing CSPAN_API_KEY. Create a .env file and add your API key.")

    if not base_url:
        raise ValueError("Missing CSPAN_API_BASE_URL. Add the API base URL from the C-SPAN docs.")

    if auth_mode not in {"bearer", "header", "query_param"}:
        raise ValueError(
            "CSPAN_AUTH_MODE must be one of: bearer, header, query_param."
        )

    return Settings(
        api_key=api_key,
        base_url=base_url,
        auth_mode=auth_mode,
        api_key_header=api_key_header,
        api_key_param=api_key_param,
        timeout_seconds=timeout_seconds,
    )