from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from md_cspan.config import Settings


class CSpanApiError(RuntimeError):
    pass


class CSpanClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "MajorityDemocrats-CSPAN-Archive/0.1",
        }

        if self.settings.auth_mode == "bearer":
            headers["Authorization"] = f"Bearer {self.settings.api_key}"

        if self.settings.auth_mode == "header":
            headers[self.settings.api_key_header] = self.settings.api_key

        return headers

    def _build_params(self, params: dict[str, Any] | None) -> dict[str, Any]:
        merged: dict[str, Any] = dict(params or {})

        if self.settings.auth_mode == "query_param":
            merged[self.settings.api_key_param] = self.settings.api_key

        return merged

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        clean_path = path.strip()

        if not clean_path:
            raise ValueError("API path cannot be empty.")

        if clean_path.startswith("http://") or clean_path.startswith("https://"):
            url = clean_path
        else:
            if not clean_path.startswith("/"):
                clean_path = f"/{clean_path}"
            url = f"{self.settings.base_url}{clean_path}"

        response = requests.get(
            url,
            headers=self._build_headers(),
            params=self._build_params(params),
            timeout=self.settings.timeout_seconds,
        )

        if response.status_code >= 400:
            raise CSpanApiError(
                f"C-SPAN API request failed.\n"
                f"Status: {response.status_code}\n"
                f"URL: {response.url}\n"
                f"Body: {response.text[:2000]}"
            )

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise CSpanApiError(
                f"C-SPAN API did not return JSON.\n"
                f"Status: {response.status_code}\n"
                f"URL: {response.url}\n"
                f"Body: {response.text[:2000]}"
            ) from exc

    @staticmethod
    def save_json(data: dict[str, Any] | list[Any], output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )