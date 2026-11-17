from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
from pydantic import ValidationError

from gta_viral_collector.config import Settings
from gta_viral_collector.language import estimate_language
from gta_viral_collector.models import Issue, ProfileRequest, Video


class ProviderError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.issue = Issue(code=code, message=message)


@dataclass
class Page:
    items: list[Video] = field(default_factory=list)
    has_more: bool = False
    next_cursor: str | None = None
    complete: bool = True
    errors: list[Issue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Adapter(ABC):
    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    @abstractmethod
    async def fetch_page(
        self, profile: ProfileRequest, since: datetime, until: datetime, cursor: str | None
    ) -> Page:
        """Return one page. Each adapter instance belongs to a single profile."""

    async def get_json(self, url: str, *, params: dict, headers: dict | None = None) -> dict:
        try:
            response = await self.client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "provider_timeout", "Tempo limite ao consultar o provedor."
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError("provider_unavailable", "Falha de conexão com o provedor.") from exc
        if not response.is_success:
            code = {
                401: "provider_unauthorized",
                403: "provider_forbidden",
                404: "profile_not_found",
                429: "rate_limited",
            }.get(response.status_code, "provider_error")
            try:
                reasons = response.json().get("error", {}).get("errors", [])
                if any(e.get("reason") in {"quotaExceeded", "dailyLimitExceeded"} for e in reasons):
                    code = "quota_exceeded"
            except (ValueError, AttributeError, TypeError):
                pass
            raise ProviderError(code, f"O provedor retornou HTTP {response.status_code}.")
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(
                "invalid_provider_response", "O provedor não retornou JSON."
            ) from exc
        if not isinstance(data, dict):
            raise ProviderError("invalid_provider_response", "Esperado um objeto JSON do provedor.")
        if data.get("success") is False or data.get("status_code", 0) != 0:
            raise ProviderError("provider_error", "O provedor informou falha na coleta.")
        if "error" in data and data["error"]:
            raise ProviderError("provider_error", "O provedor informou erro na coleta.")
        return data


def require_list(data: dict, key: str) -> list:
    value = data.get(key)
    if not isinstance(value, list):
        raise ProviderError("invalid_provider_response", f"Campo {key} ausente ou inválido.")
    return value


def require_bool(data: dict, key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, (bool, int)) or value not in (0, 1):
        raise ProviderError("invalid_provider_response", f"Campo {key} ausente ou inválido.")
    return bool(value)


def parse_items(page: Page, items: list, converter: Callable[[Any], Video | None]) -> Page:
    for item in items:
        try:
            video = converter(item)
            if video is not None:
                page.items.append(video)
        except (ValidationError, KeyError, TypeError, ValueError, AttributeError, IndexError):
            page.errors.append(
                Issue(
                    code="invalid_video",
                    message=(
                        "Um registro de vídeo foi ignorado por conter campos ausentes ou inválidos."
                    ),
                )
            )
    return page


def make_video(profile: ProfileRequest, *, language: str | None = None, **fields) -> Video:
    code, source = estimate_language(fields.get("title"), language)
    return Video(
        platform=profile.platform,
        username=profile.username,
        language=code,
        language_source=source,
        **fields,
    )


def cursor_string(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ProviderError("invalid_provider_response", "Cursor de paginação inválido.")
    return str(value)


def identifier(value: Any) -> str:
    """Reject missing IDs before constructing a canonical publication URL."""
    if not isinstance(value, (str, int)) or isinstance(value, bool) or not str(value).strip():
        raise ValueError("Identificador ausente ou inválido.")
    return str(value).strip()
