from datetime import datetime

from gta_viral_collector.models import Issue, ProfileRequest, Video

from .base import (
    Adapter,
    Page,
    ProviderError,
    cursor_string,
    identifier,
    make_video,
    parse_items,
    require_list,
)


class YouTubeAdapter(Adapter):
    uploads_playlist: str | None = None

    async def youtube_get(self, resource: str, **params) -> dict:
        key = self.settings.youtube_api_key
        if not key or not key.get_secret_value():
            raise ProviderError("not_configured", "Configure YOUTUBE_API_KEY.")
        return await self.get_json(
            f"{self.settings.youtube_api_base_url.rstrip('/')}/{resource}",
            params={"key": key.get_secret_value(), **params},
        )

    async def fetch_page(
        self, profile: ProfileRequest, since: datetime, until: datetime, cursor: str | None
    ) -> Page:
        if self.uploads_playlist is None:
            identity = (
                {"id": profile.username}
                if (profile.username.startswith("UC") and len(profile.username) == 24)
                else {"forHandle": f"@{profile.username}"}
            )
            channels = require_list(
                await self.youtube_get("channels", part="contentDetails", **identity), "items"
            )
            if not channels:
                raise ProviderError("profile_not_found", "Canal do YouTube não encontrado.")
            try:
                self.uploads_playlist = channels[0]["contentDetails"]["relatedPlaylists"]["uploads"]
            except (KeyError, TypeError) as exc:
                raise ProviderError(
                    "invalid_provider_response", "Playlist de uploads ausente."
                ) from exc
        params = {"part": "contentDetails", "playlistId": self.uploads_playlist, "maxResults": 50}
        if cursor is not None:
            params["pageToken"] = cursor
        data = await self.youtube_get("playlistItems", **params)
        next_cursor = cursor_string(data.get("nextPageToken"))
        page = Page(has_more=next_cursor is not None, next_cursor=next_cursor)
        ids = []
        for item in require_list(data, "items"):
            try:
                ids.append(identifier(item["contentDetails"]["videoId"]))
            except (KeyError, TypeError, ValueError):
                page.errors.append(
                    Issue(code="invalid_video", message="ID de upload ausente ou inválido.")
                )
        if not ids:
            return page
        details = await self.youtube_get(
            "videos", part="snippet,statistics,status", id=",".join(ids)
        )

        def convert(item: dict) -> Video | None:
            if item["status"]["privacyStatus"] != "public":
                return None
            snippet = item["snippet"]
            statistics = item.get("statistics") or {}
            thumbnails = snippet.get("thumbnails") or {}
            thumbnail = next(
                (
                    thumbnails[k]["url"]
                    for k in ("maxres", "standard", "high", "medium", "default")
                    if k in thumbnails
                ),
                None,
            )
            return make_video(
                profile,
                id=item["id"],
                title=snippet.get("title"),
                url=f"https://www.youtube.com/watch?v={item['id']}",
                views=statistics.get("viewCount"),
                likes=statistics.get("likeCount"),
                comments=statistics.get("commentCount"),
                published_at=snippet["publishedAt"],
                thumbnail=thumbnail,
                language=snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage"),
            )

        return parse_items(page, require_list(details, "items"), convert)
