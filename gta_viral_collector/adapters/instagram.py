from datetime import datetime

from gta_viral_collector.models import ProfileRequest, Video

from .base import (
    Adapter,
    Page,
    ProviderError,
    cursor_string,
    identifier,
    make_video,
    parse_items,
    require_bool,
    require_list,
)
from .http_provider import HTTPProvider


class InstagramAdapter(Adapter):
    async def fetch_page(
        self, profile: ProfileRequest, since: datetime, until: datetime, cursor: str | None
    ) -> Page:
        if self.settings.instagram_provider == "http":
            return await HTTPProvider(self.client, self.settings).fetch_page(
                profile, since, until, cursor
            )
        key = self.settings.instagram_api_key or self.settings.scrapecreators_api_key
        if not key or not key.get_secret_value():
            raise ProviderError(
                "not_configured", "Configure SCRAPECREATORS_API_KEY ou INSTAGRAM_API_KEY."
            )
        params = {"handle": profile.username}
        if cursor is not None:
            params["next_max_id"] = cursor
        data = await self.get_json(
            f"{self.settings.scrapecreators_base_url.rstrip('/')}/v2/instagram/user/posts",
            params=params,
            headers={"x-api-key": key.get_secret_value()},
        )
        if (data.get("user") or {}).get("is_private"):
            raise ProviderError("private_profile", "O perfil do Instagram é privado.")
        if data.get("status", "ok") != "ok" or data.get("message"):
            raise ProviderError(
                "provider_error", "O Instagram informou restrição ou falha de acesso."
            )
        page = Page(
            has_more=require_bool(data, "more_available"),
            next_cursor=cursor_string(data.get("next_max_id")),
            warnings=[
                "Instagram: views refletem play_count do provedor e excluem views do Facebook."
            ],
        )

        def convert(item: dict) -> Video | None:
            if item["media_type"] != 2:
                return None
            if (item.get("user") or {}).get("is_private"):
                return None
            caption = item.get("caption") or {}
            thumbnails = (item.get("image_versions2") or {}).get("candidates") or []
            code = identifier(item["code"])
            return make_video(
                profile,
                id=identifier(item["id"]),
                title=caption.get("text"),
                url=item.get("url") or f"https://www.instagram.com/p/{code}/",
                views=item.get("play_count"),
                likes=item.get("like_count"),
                comments=item.get("comment_count"),
                published_at=item.get("created_at") or item["taken_at"],
                thumbnail=thumbnails[0].get("url") if thumbnails else item.get("display_uri"),
            )

        return parse_items(page, require_list(data, "items"), convert)
