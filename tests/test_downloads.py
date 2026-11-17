import asyncio
import functools
import http.server
import subprocess
import sys
import threading
from datetime import UTC, datetime

import pytest

from gta_viral_collector.config import Settings
from gta_viral_collector.downloads import YtDlpDownloader, find_ffmpeg, run_process
from gta_viral_collector.models import Video, VideoLink


async def test_subprocess_timeout_terminates_download():
    with pytest.raises(TimeoutError):
        await run_process([sys.executable, "-c", "import time; time.sleep(60)"], 0.15)


@pytest.mark.parametrize("from_profile", [False, True])
async def test_real_ytdlp_download_validates_mp4_from_local_http(
    tmp_path, monkeypatch, from_profile
):
    from gta_viral_collector import downloads

    commands = []
    real_run = downloads.run_process

    async def capture(command, timeout_seconds):
        commands.append(command)
        return await real_run(command, timeout_seconds)

    monkeypatch.setattr(downloads, "run_process", capture)
    config = Settings(_env_file=None, collection_enabled=False, download_timeout_seconds=60)
    try:
        ffmpeg = find_ffmpeg(config)
    except Exception:
        pytest.skip("FFmpeg não instalado neste ambiente")
    binary = ffmpeg / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    source = tmp_path / "source.mp4"
    await asyncio.to_thread(
        subprocess.run,
        [
            str(binary),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=blue:s=64x48:d=0.5",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
    )
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        video = VideoLink(
            id="local",
            platform="youtube",
            url=f"http://127.0.0.1:{port}/source.mp4",
        )
        if from_profile:
            video = Video(**video.model_dump(), username="test", published_at=datetime.now(UTC))
        staging = tmp_path / "staging"
        staging.mkdir()
        result = await YtDlpDownloader(config).download(video, staging)
        assert result.name == "video.mp4"
        assert result.stat().st_size > 0
        assert result.read_bytes() == source.read_bytes()
        assert "--abort-on-unavailable-fragments" in commands[0]
        assert ("--playlist-items" in commands[0]) is not from_profile
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join()
