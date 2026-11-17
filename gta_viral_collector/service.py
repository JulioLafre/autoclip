import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx

from gta_viral_collector.adapters.base import ProviderError
from gta_viral_collector.adapters.instagram import InstagramAdapter
from gta_viral_collector.adapters.tiktok import TikTokAdapter
from gta_viral_collector.adapters.youtube import YouTubeAdapter
from gta_viral_collector.config import Settings
from gta_viral_collector.models import (
    Issue,
    ProfileRequest,
    ProfileResult,
    Video,
    ViralRequest,
    ViralResponse,
)

logger = logging.getLogger(__name__)
ADAPTERS = {"youtube": YouTubeAdapter, "tiktok": TikTokAdapter, "instagram": InstagramAdapter}


class ViralCollector:
    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    async def collect(self, request: ViralRequest) -> ViralResponse:
        until = datetime.now(UTC)
        semaphore = asyncio.Semaphore(self.settings.max_concurrent_profiles)

        async def collect_one(profile: ProfileRequest) -> ProfileResult:
            async with semaphore:
                return await self.collect_profile(profile, until)

        results = await asyncio.gather(*(collect_one(profile) for profile in request.profiles))
        return ViralResponse(
            collected_at=until, complete=all(r.complete for r in results), profiles=results
        )

    async def collect_profile(self, profile: ProfileRequest, until: datetime) -> ProfileResult:
        since = until - timedelta(days=profile.days)
        adapter = ADAPTERS[profile.platform](self.client, self.settings)
        videos: dict[str, Video] = {}
        errors: list[Issue] = []
        warnings: list[str] = []
        pages_fetched = 0
        cursor = None
        seen_cursors: set[str] = set()
        exhausted = False
        try:
            for _ in range(self.settings.max_pages_per_profile):
                page = await adapter.fetch_page(profile, since, until, cursor)
                pages_fetched += 1
                errors.extend(page.errors)
                warnings.extend(page.warnings)
                if not page.complete:
                    errors.append(
                        Issue(
                            code="provider_partial",
                            message=("O provedor declarou cobertura parcial desta página."),
                        )
                    )
                for video in page.items:
                    if since <= video.published_at <= until:
                        videos.setdefault(video.id, video)
                if not page.has_more:
                    exhausted = True
                    break
                if page.next_cursor is None:
                    raise ProviderError(
                        "missing_cursor", "O provedor indicou mais páginas sem cursor."
                    )
                if page.next_cursor in seen_cursors:
                    raise ProviderError(
                        "pagination_loop", "O provedor repetiu um cursor de paginação."
                    )
                cursor = page.next_cursor
                seen_cursors.add(cursor)
            if not exhausted:
                errors.append(
                    Issue(
                        code="page_limit_reached",
                        message=(
                            "Limite de páginas por perfil atingido; "
                            "o ranking pode estar incompleto."
                        ),
                    )
                )
        except ProviderError as exc:
            errors.append(exc.issue)
        except Exception:
            logger.exception("Erro ao coletar perfil %s/%s", profile.platform, profile.username)
            errors.append(
                Issue(code="collection_error", message="Erro inesperado ao coletar o perfil.")
            )
        if any(video.views is None for video in videos.values()):
            errors.append(
                Issue(
                    code="missing_views",
                    message=(
                        "Há vídeos sem views disponíveis; "
                        "são listados ao final e o ranking é parcial."
                    ),
                )
            )
        ranked = sorted(
            videos.values(),
            key=lambda video: (
                video.views is None,
                -(video.views or 0),
                video.language != "en",
                -video.published_at.timestamp(),
                video.id,
            ),
        )
        complete = exhausted and not errors
        return ProfileResult(
            platform=profile.platform,
            username=profile.username,
            days=profile.days,
            limit=profile.limit,
            since=since,
            until=until,
            complete=complete,
            status="complete" if complete else ("partial" if pages_fetched else "error"),
            pages_fetched=pages_fetched,
            matched_videos=len(ranked),
            videos=ranked[: profile.limit],
            errors=list({(issue.code, issue.message): issue for issue in errors}.values()),
            warnings=list(dict.fromkeys(warnings)),
        )
