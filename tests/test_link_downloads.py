import asyncio
import hashlib
import json
from pathlib import Path
from threading import Event
from time import monotonic, sleep

import httpx
import pytest
from fastapi.testclient import TestClient

from gta_viral_collector.config import Settings
from gta_viral_collector.downloads import DownloadError, YtDlpDownloader
from gta_viral_collector.main import create_app

VIDEO_ID = "5FYUzCuF8SM"
SHORTS_URL = f"https://www.youtube.com/shorts/{VIDEO_ID}?si=shared"


def app_for(tmp_path, transport=None):
    return create_app(
        Settings(
            _env_file=None,
            collection_enabled=False,
            creators_file=tmp_path / "missing-creators.json",
            download_dir=tmp_path / "entrada",
            collection_state_dir=tmp_path / "coleta",
        ),
        transport=transport,
    )


def submit(client, url):
    response = client.post("/api/videos/download", json={"url": url})
    assert response.status_code == 202, response.text
    return response.json()


def finished(client, job):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        current = client.get(job["status_url"]).json()
        if current["status"] not in {"queued", "downloading"}:
            return current
        sleep(0.02)
    pytest.fail(f"Download não terminou: {current}")


def test_download_waits_for_ready_and_reuses_canonical_video(tmp_path, monkeypatch):
    release = Event()
    calls = []

    async def download(self, video, staging):
        calls.append(str(video.url))
        assert await asyncio.to_thread(release.wait, 4)
        path = staging / "video.mp4"
        path.write_bytes(b"validated at the download boundary")
        return path

    monkeypatch.setattr(YtDlpDownloader, "download", download)
    with TestClient(app_for(tmp_path)) as client:
        job = submit(client, SHORTS_URL)
        assert job["status"] == "queued"
        assert job["queue_reason"] == "waiting_for_slot"
        assert job["path"] is None
        assert client.get(job["status_url"]).json()["path"] is None
        assert not list((tmp_path / "entrada").glob("*.mp4"))
        duplicate = submit(client, f"https://youtu.be/{VIDEO_ID}?t=2")
        release.set()
        ready = finished(client, job)
        path = Path(ready["path"])
        assert ready["status"] == "ready"
        assert ready["queue_reason"] is None
        assert ready["work_id"] == path.stem
        assert path.parent == tmp_path / "entrada"
        assert path.is_file()
        reused = finished(client, duplicate)
        assert reused["path"] == ready["path"]
        assert reused["reused"] is True
    with TestClient(app_for(tmp_path)) as client:
        assert client.get(job["status_url"]).status_code == 404
        assert finished(client, submit(client, SHORTS_URL))["reused"] is True
        path.rename(tmp_path / path.name)
        consumed = finished(client, submit(client, SHORTS_URL))
        assert consumed["status"] == "already_processed"
        assert consumed["path"] is None
    assert calls == [f"https://www.youtube.com/watch?v={VIDEO_ID}"]


def test_instagram_reel_reuses_scheduled_download_with_compound_id(tmp_path, monkeypatch):
    async def unexpected_download(self, video, staging):
        pytest.fail("O vídeo já deveria estar no histórico da coleta por perfil.")

    monkeypatch.setattr(YtDlpDownloader, "download", unexpected_download)
    saved = tmp_path / "entrada" / "instagram_feed_video.mp4"
    saved.parent.mkdir()
    data = b"MP4 registrado pela coleta"
    saved.write_bytes(data)
    history = tmp_path / "coleta" / "history.json"
    history.parent.mkdir()
    history.write_text(
        json.dumps(
            {
                "version": 1,
                "videos": {
                    "instagram:482584233761418119_112345": {
                        "state": "downloaded",
                        "path": str(saved),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with TestClient(app_for(tmp_path)) as client:
        job = submit(client, "https://www.instagram.com/reel/aye83DjauH/?igsh=shared")
        result = finished(client, job)
        assert result["status"] == "ready"
        assert Path(result["path"]) == saved
        assert result["reused"] is True


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/@creator",
        "https://www.youtube.com/playlist?list=123",
        "https://www.tiktok.com/@creator/photo/1234567890",
        "http://127.0.0.1/video.mp4",
        "https://www.instagram.com@localhost/reel/ABCDEFG/",
    ],
)
def test_download_rejects_profiles_playlists_and_other_hosts(tmp_path, url):
    with TestClient(app_for(tmp_path)) as client:
        response = client.post("/api/videos/download", json={"url": url})
        assert response.status_code == 422


@pytest.mark.parametrize(
    "location", ["https://www.tiktok.com/@creator/video/1234", "http://localhost/"]
)
def test_share_link_redirect_is_validated_and_failure_has_no_path(tmp_path, monkeypatch, location):
    requests, downloads = [], []

    def redirect(request):
        requests.append(str(request.url))
        return httpx.Response(302, headers={"Location": location})

    async def download(self, video, staging):
        downloads.append(str(video.url))
        raise DownloadError("Vídeo indisponível para download.")

    monkeypatch.setattr(YtDlpDownloader, "download", download)
    with TestClient(app_for(tmp_path, httpx.MockTransport(redirect))) as client:
        job = submit(client, "https://vm.tiktok.com/Zshare/")
        assert job["queue_reason"] == "resolving_link"
        state = finished(client, job)
        assert state["status"] == "failed"
        assert state["path"] is None
        assert state["error"]
    assert requests == ["https://vm.tiktok.com/Zshare/"]
    assert downloads == ([location] if "tiktok.com" in location else [])
