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


class TikTokAdapter(Adapter):
    async def fetch_page(
        self, profile: ProfileRequest, since: datetime, until: datetime, cursor: str | None
    ) -> Page:
        if self.settings.tiktok_provider == "http":
            return await HTTPProvider(self.client, self.settings).fetch_page(
                profile, since, until, cursor
            )
        key = self.settings.tiktok_api_key or self.settings.scrapecreators_api_key
        if not key or not key.get_secret_value():
            raise ProviderError(
                "not_configured", "Configure SCRAPECREATORS_API_KEY ou TIKTOK_API_KEY."
            )
        params = {"handle": profile.username, "sort_by": "latest", "include_pinned": "true"}
        if cursor is not None:
            params["max_cursor"] = cursor
        data = await self.get_json(
            f"{self.settings.scrapecreators_base_url.rstrip('/')}/v3/tiktok/profile/videos",
            params=params,
            headers={"x-api-key": key.get_secret_value()},
        )
        page = Page(
            has_more=require_bool(data, "has_more"),
            next_cursor=cursor_string(data.get("max_cursor")),
            warnings=[
                "O feed do TikTok pode omitir posts mesmo após toda a paginação do provedor."
            ],
        )

        def convert(item: dict) -> Video | None:
            if (item.get("image_post_info") or {}).get("images"):
                return None
            if (item.get("author") or {}).get("private_account") is True:
                return None
            if (item.get("status") or {}).get("is_private") is True:
                return None
            video_id = identifier(item["aweme_id"])
            statistics = item.get("statistics") or {}
            covers = (item.get("video") or {}).get("cover") or {}
            urls = covers.get("url_list") or []
            return make_video(
                profile,
                id=video_id,
                title=item.get("desc"),
                url=f"https://www.tiktok.com/@{profile.username}/video/{video_id}",
                views=statistics.get("play_count"),
                likes=statistics.get("digg_count"),
                comments=statistics.get("comment_count"),
                published_at=item["create_time"],
                thumbnail=urls[0] if urls else None,
                language=item.get("desc_language"),
            )

        return parse_items(page, require_list(data, "aweme_list"), convert)
