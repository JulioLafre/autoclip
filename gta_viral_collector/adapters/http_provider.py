from datetime import datetime

from pydantic import BaseModel, StrictBool

from gta_viral_collector.models import ProfileRequest, Video

from .base import Adapter, Page, ProviderError, cursor_string, make_video, parse_items, require_bool


class ProviderRecord(BaseModel):
    """Contrato explícito do provedor HTTP normalizado."""

    id: str
    title: str | None = None
    url: str
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    published_at: str
    thumbnail: str | None = None
    language: str | None = None
    is_public: StrictBool


class HTTPProvider(Adapter):
    async def fetch_page(
        self, profile: ProfileRequest, since: datetime, until: datetime, cursor: str | None
    ) -> Page:
        prefix = profile.platform
        url = getattr(self.settings, f"{prefix}_api_url")
        if not url:
            raise ProviderError("not_configured", f"Configure {prefix.upper()}_API_URL.")
        key = getattr(self.settings, f"{prefix}_api_key")
        headers = {}
        if key and key.get_secret_value():
            headers[getattr(self.settings, f"{prefix}_api_key_header")] = (
                getattr(self.settings, f"{prefix}_api_key_prefix") + key.get_secret_value()
            )
        params = {
            "platform": prefix,
            "username": profile.username,
            "since": since.isoformat(),
            "until": until.isoformat(),
            "page_size": 50,
        }
        if cursor is not None:
            params["cursor"] = cursor
        data = await self.get_json(url, params=params, headers=headers)
        items = data.get("items")
        if not isinstance(items, list):
            raise ProviderError("invalid_provider_response", "Campo items ausente ou inválido.")
        page = Page(
            has_more=require_bool(data, "has_more"),
            next_cursor=cursor_string(data.get("next_cursor")),
            complete=require_bool(data, "complete") if "complete" in data else True,
        )

        def convert(item: dict) -> Video | None:
            record = ProviderRecord.model_validate(item)
            if not record.is_public:
                return None
            return make_video(profile, **record.model_dump(exclude={"is_public"}))

        return parse_items(page, items, convert)
