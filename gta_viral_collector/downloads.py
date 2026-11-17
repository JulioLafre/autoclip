"""Real downloads through yt-dlp, isolated in cancellable subprocesses."""

import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from gta_viral_collector.config import Settings
from gta_viral_collector.models import Video, VideoLink


class DownloadError(Exception):
    pass


def find_ffmpeg(config: Settings) -> Path:
    if config.ffmpeg_dir:
        directory = config.ffmpeg_dir.resolve()
    elif shutil.which("ffmpeg"):
        directory = Path(shutil.which("ffmpeg")).parent
    else:
        root = Path(__file__).resolve().parents[1] / ".tools/ffmpeg"
        binary = next(root.glob("**/ffmpeg.exe"), None)
        if binary is None:
            raise DownloadError("FFmpeg não encontrado; configure FFMPEG_DIR.")
        directory = binary.parent
    extension = ".exe" if os.name == "nt" else ""
    if not all((directory / (name + extension)).is_file() for name in ("ffmpeg", "ffprobe")):
        raise DownloadError("FFMPEG_DIR deve conter ffmpeg e ffprobe.")
    return directory


async def stop_process(process):
    if process.returncode is not None:
        return
    if os.name == "nt":
        killer = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(process.pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await killer.wait()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    await process.wait()


async def run_process(command: list[str], timeout_seconds: float):
    options = (
        {"creationflags": subprocess.CREATE_NO_WINDOW}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **options
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except (TimeoutError, asyncio.CancelledError):
        await stop_process(process)
        raise
    if process.returncode:
        # Log only a short diagnostic; credentials/URLs are not echoed into the API.
        message = stderr.decode("utf-8", errors="replace").strip()
        lowered = message.lower()
        if "sign in" in lowered or "login" in lowered or "cookies" in lowered:
            raise DownloadError("O site exige autenticação/cookies para este download.")
        if "403" in lowered or "forbidden" in lowered:
            raise DownloadError("O site recusou o download (HTTP 403).")
        if "404" in lowered or "not available" in lowered or "unavailable" in lowered:
            raise DownloadError("Vídeo indisponível para download.")
        raise DownloadError(f"A ferramenta de download terminou com código {process.returncode}.")
    return stdout


class YtDlpDownloader:
    def __init__(self, config: Settings):
        self.config = config

    async def download(self, video: VideoLink, staging: Path) -> Path:
        ffmpeg = find_ffmpeg(self.config)
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--ignore-config",
            "--no-playlist",
            "--no-progress",
            "--quiet",
            "--no-overwrites",
            "--no-mtime",
            "--abort-on-unavailable-fragments",
            "--socket-timeout",
            "20",
            "--retries",
            "2",
            "--fragment-retries",
            "2",
            "--ffmpeg-location",
            str(ffmpeg),
            "--format",
            "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
            "--merge-output-format",
            "mp4",
            "--remux-video",
            "mp4",
            "--output",
            str(staging / "video.%(ext)s"),
            "--print",
            "after_move:filepath",
        ]
        if not isinstance(video, Video):
            command += ["--playlist-items", "1"]
        if shutil.which("node"):
            command += ["--js-runtimes", f"node:{shutil.which('node')}"]
        if self.config.download_cookies_file:
            cookies = self.config.download_cookies_file.resolve()
            if not cookies.is_file():
                raise DownloadError("DOWNLOAD_COOKIES_FILE não foi encontrado.")
            command += ["--cookies", str(cookies)]
        command += ["--", str(video.url)]
        try:
            await run_process(command, self.config.download_timeout_seconds)
            result = staging / "video.mp4"
            if not result.is_file() or result.stat().st_size == 0:
                raise DownloadError("yt-dlp não produziu um MP4 completo.")
            probe = ffmpeg / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
            raw = await run_process(
                [
                    str(probe),
                    "-v",
                    "error",
                    "-show_streams",
                    "-of",
                    "json",
                    str(result),
                ],
                30,
            )
            streams = json.loads(raw).get("streams", [])
            if not any(s.get("codec_type") == "video" for s in streams):
                raise DownloadError("O arquivo baixado não contém vídeo válido.")
            return result
        except TimeoutError as exc:
            raise DownloadError("Tempo limite do download/validação atingido.") from exc
