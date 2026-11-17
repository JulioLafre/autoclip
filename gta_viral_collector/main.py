from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, Response

from gta_viral_collector.collection import CollectionService
from gta_viral_collector.config import Settings
from gta_viral_collector.link_downloads import (
    DownloadJob,
    DownloadQueueFull,
    DownloadRequest,
    LinkDownloads,
)
from gta_viral_collector.models import ViralRequest, ViralResponse
from gta_viral_collector.service import ViralCollector
from gta_viral_collector.video_links import parse_link


def create_app(
    settings: Settings | None = None, *, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(
            timeout=config.request_timeout_seconds, transport=transport
        ) as client:
            app.state.collector = ViralCollector(client, config)
            app.state.collection = CollectionService(app.state.collector, config)
            app.state.link_downloads = LinkDownloads(client, app.state.collection)
            app.state.collection.start()
            try:
                yield
            finally:
                await app.state.link_downloads.stop()
                await app.state.collection.stop()

    app = FastAPI(
        title="GTA Viral Collector",
        version="0.1.0",
        lifespan=lifespan,
        description=(
            "Coleta vídeos públicos por perfil, filtra o período em UTC e ordena por views. "
            "Inglês tem prioridade em empates. Falhas são retornadas por perfil, sem "
            "resultados simulados. Métricas indisponíveis são null."
        ),
    )

    @app.post(
        "/api/videos/viral",
        response_model=ViralResponse,
        tags=["videos"],
        summary="Vídeos públicos mais visualizados por perfil",
    )
    async def viral_videos(payload: ViralRequest, request: Request) -> ViralResponse:
        return await request.app.state.collector.collect(payload)

    @app.post(
        "/api/videos/download",
        status_code=202,
        tags=["videos"],
        summary="Baixar um vídeo público por link",
    )
    async def download_video(
        payload: DownloadRequest, request: Request, response: Response
    ) -> DownloadJob:
        try:
            link = parse_link(payload.url)
            job = request.app.state.link_downloads.submit(link)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except DownloadQueueFull as exc:
            raise HTTPException(status_code=429, detail="Fila cheia. Tente novamente.") from exc
        response.headers["Location"] = job.status_url
        return job

    @app.get(
        "/api/videos/download/{job_id}",
        tags=["videos"],
        summary="Consultar estado e caminho do vídeo baixado",
    )
    async def download_status(job_id: str, request: Request) -> DownloadJob:
        job = request.app.state.link_downloads.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Download não encontrado.")
        return job

    @app.get(
        "/api/collection/status",
        tags=["collection"],
        summary="Status da coleta automática e relatório da última execução",
    )
    async def collection_status(request: Request) -> dict:
        return request.app.state.collection.status()

    @app.post(
        "/api/collection/run",
        status_code=202,
        tags=["collection"],
        summary="Coletar e baixar agora os perfis do JSON",
    )
    async def collection_run(request: Request) -> dict:
        service = request.app.state.collection
        try:
            creators = service.read_config()
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail=f"Configuração inválida: {exc}") from exc
        try:
            service.request_run(creators)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return service.status()

    return app


app = create_app()
