import asyncio
import logging
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field

from gta_viral_collector.collection import CollectionService
from gta_viral_collector.downloads import DownloadError
from gta_viral_collector.models import Platform, VideoLink
from gta_viral_collector.video_links import resolve_link

logger = logging.getLogger(__name__)


class DownloadRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"example": {"url": "https://youtu.be/5FYUzCuF8SM"}}
    )

    url: str = Field(min_length=1, max_length=2048)


class DownloadJob(BaseModel):
    id: str
    status_url: str
    status: Literal["queued", "downloading", "ready", "failed", "already_processed"] = "queued"
    queue_reason: Literal["resolving_link", "waiting_for_slot"] | None = None
    platform: Platform
    work_id: str | None = None
    path: str | None = None
    reused: bool = False
    error: str | None = None


class DownloadQueueFull(Exception):
    pass


class LinkDownloads:
    def __init__(self, client: httpx.AsyncClient, collection: CollectionService):
        self.client = client
        self.collection = collection
        self.jobs: dict[str, DownloadJob] = {}
        self.tasks: dict[str, asyncio.Task] = {}

    def submit(self, link: VideoLink | tuple[Platform, str]) -> DownloadJob:
        if len(self.tasks) >= 32:
            raise DownloadQueueFull
        if len(self.jobs) >= 256:
            oldest_finished = next(key for key in self.jobs if key not in self.tasks)
            del self.jobs[oldest_finished]
        job_id = uuid4().hex
        job = DownloadJob(
            id=job_id,
            platform=link.platform if isinstance(link, VideoLink) else link[0],
            status_url=f"/api/videos/download/{job_id}",
            queue_reason="waiting_for_slot" if isinstance(link, VideoLink) else "resolving_link",
        )
        self.jobs[job_id] = job
        self.tasks[job_id] = asyncio.create_task(self._run(job, link), name=f"link-{job_id}")
        return job

    def get(self, job_id: str) -> DownloadJob | None:
        job = self.jobs.get(job_id)
        if job is not None and job.path and not Path(job.path).is_file():
            job.status = "already_processed"
            job.path = None
        return job

    async def stop(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self, job: DownloadJob, link: VideoLink | tuple[Platform, str]):
        def mark_downloading():
            job.status = "downloading"
            job.queue_reason = None

        try:
            video = await resolve_link(self.client, link)
            job.queue_reason = "waiting_for_slot"
            record, job.reused = await self.collection.download_link(video, mark_downloading)
            path = Path(record["path"])
            job.work_id = path.stem
            if await asyncio.to_thread(path.is_file):
                job.path = str(path)
                job.status = "ready"
            else:
                job.status = "already_processed"
        except (DownloadError, ValueError) as exc:
            job.status = "failed"
            job.error = str(exc)
        except Exception:
            job.status = "failed"
            job.error = "Falha interna ao preparar o download. Consulte o log do backend."
            logger.exception("Falha no download por link %s", job.id)
        finally:
            job.queue_reason = None
            self.tasks.pop(job.id, None)
