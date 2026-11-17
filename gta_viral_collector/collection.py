"""Scheduled collection, JSON history and atomic delivery to the bots' input folder."""

import asyncio
import contextlib
import hashlib
import json
import logging
import re
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from filelock import FileLock, Timeout
from pydantic import BaseModel, ConfigDict, Field, model_validator

from gta_viral_collector.config import Settings
from gta_viral_collector.downloads import YtDlpDownloader
from gta_viral_collector.models import ProfileRequest, VideoLink, ViralRequest

logger = logging.getLogger(__name__)


class WatchedProfile(ProfileRequest):
    enabled: bool = True


class CollectionInterval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int = Field(ge=1, le=525600, strict=True)
    unit: Literal["minutes", "hours"]

    @property
    def minutes(self) -> int:
        return self.value * 60 if self.unit == "hours" else self.value

    @model_validator(mode="after")
    def validate_duration(self):
        if self.minutes > 525600:
            raise ValueError("O intervalo máximo é de 365 dias.")
        return self


class CreatorsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    automatic_downloads: bool = Field(default=True, strict=True)
    interval: CollectionInterval | None = None
    interval_minutes: int = Field(default=60, ge=1, le=525600, strict=True)
    run_on_startup: bool = True
    profiles: list[WatchedProfile] = Field(default_factory=list, max_length=100)

    @property
    def effective_interval(self) -> CollectionInterval:
        return self.interval or CollectionInterval(value=self.interval_minutes, unit="minutes")

    def active_profiles(self):
        return [
            ProfileRequest.model_validate(p.model_dump(exclude={"enabled"}))
            for p in self.profiles
            if p.enabled
        ]


def read_object(path: Path):
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"Objeto JSON esperado em {path.name}.")
    return data


def write_atomic(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(data, handle, ensure_ascii=False, indent=2)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def file_hash(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read_history(path):
    history = read_object(path) if path.exists() else {"version": 1, "videos": {}}
    if history.get("version") != 1 or not isinstance(history.get("videos"), dict):
        raise ValueError("Histórico inválido; arquivo preservado para revisão.")
    if any(not isinstance(item, dict) for item in history["videos"].values()):
        raise ValueError("Registros de histórico inválidos; arquivo preservado.")
    return history


def history_identity(video: VideoLink, records: dict) -> str:
    identity = f"{video.platform}:{video.id}"
    if identity in records or video.platform != "instagram":
        return identity
    # The profile provider can append the account ID to the numeric media ID.
    media_id = f"instagram:{video.id.split('_', 1)[0]}"
    if media_id in records:
        return media_id
    return next((key for key in records if key.startswith(media_id + "_")), identity)


class CollectionService:
    def __init__(self, collector, config: Settings, *, downloader=None):
        self.collector, self.config = collector, config
        self.downloader = downloader or YtDlpDownloader(config)
        self.download_lock = asyncio.Lock()
        self.task = None
        self.scheduler = None
        self.last_attempt = None
        self.next_run = None
        self.last_valid_config: CreatorsConfig | None = None
        self.config_error: str | None = None
        self.state = {
            "status": "idle",
            "running": False,
            "last_report": None,
            "last_started_at": None,
            "last_finished_at": None,
            "error": None,
        }
        previous = config.collection_state_dir / "last-run.json"
        if previous.is_file():
            try:
                self.state["last_report"] = read_object(previous)
            except (ValueError, OSError):
                self.state["error"] = "Não foi possível ler o relatório anterior."

    def status(self):
        creators = self.last_valid_config
        return {
            **self.state,
            "next_run_at": self.next_run.isoformat() if self.next_run else None,
            "config_file": str(self.config.creators_file.resolve()),
            "download_dir": str(self.config.download_dir.resolve()),
            "history_file": str((self.config.collection_state_dir / "history.json").resolve()),
            "scheduler_enabled": self.config.collection_enabled,
            "automatic_downloads": (
                creators.enabled and creators.automatic_downloads if creators else None
            ),
            "interval": creators.effective_interval.model_dump() if creators else None,
            "config_error": self.config_error,
            "using_last_valid_config": self.config_error is not None and creators is not None,
        }

    def read_config(self):
        try:
            creators = CreatorsConfig.model_validate(read_object(self.config.creators_file))
        except (ValueError, OSError) as exc:
            self.config_error = str(exc)
            raise
        self.last_valid_config = creators
        self.config_error = None
        return creators

    def request_run(self, creators=None, now=None):
        if self.task is not None and not self.task.done():
            raise ValueError("Já existe uma coleta em andamento.")
        creators = creators or self.read_config()
        if not creators.enabled:
            raise ValueError("A coleta está desativada em creators.json.")
        if not creators.active_profiles():
            raise ValueError("Cadastre pelo menos um perfil ativo em creators.json.")
        now = now or datetime.now(UTC)
        self.last_attempt = now
        self.next_run = (
            now + timedelta(minutes=creators.effective_interval.minutes)
            if creators.automatic_downloads
            else None
        )
        self.state.update(
            status="running", running=True, error=None, last_started_at=now.isoformat()
        )
        self.task = asyncio.create_task(self._execute(creators), name="viral-collection")

    async def tick(self, now):
        try:
            creators = self.read_config()
        except (ValueError, OSError):
            creators = self.last_valid_config
        if creators is None:
            if not self.state["running"]:
                self.state.update(status="configuration_error", error=self.config_error)
            self.next_run = None
            return

        pause_reason = None
        if not creators.enabled:
            pause_reason = "disabled"
        elif not creators.automatic_downloads:
            pause_reason = "automatic_paused"
        elif not any(profile.enabled for profile in creators.profiles):
            pause_reason = "no_profiles"
        if pause_reason:
            if not self.state["running"]:
                self.state.update(status=pause_reason, error=None)
                self.last_attempt = None
            self.next_run = None
            return

        if self.state["status"] in {
            "configuration_error",
            "disabled",
            "automatic_paused",
            "no_profiles",
        }:
            self.state.update(status="idle", error=None)
        if self.last_attempt is None:
            if creators.run_on_startup:
                self.request_run(creators, now)
                return
            self.last_attempt = now
        self.next_run = self.last_attempt + timedelta(minutes=creators.effective_interval.minutes)
        if now >= self.next_run and not self.state["running"]:
            self.request_run(creators, now)

    def start(self):
        if self.config.collection_enabled:
            self.scheduler = asyncio.create_task(self._watch(), name="collection-scheduler")

    async def _watch(self):
        while True:
            await self.tick(datetime.now(UTC))
            await asyncio.sleep(self.config.collection_poll_seconds)

    async def stop(self):
        for task in (self.scheduler, self.task):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    @contextlib.asynccontextmanager
    async def _download_slot(self):
        root = self.config.collection_state_dir
        async with self.download_lock:
            root.mkdir(parents=True, exist_ok=True)
            lock = FileLock(root / "downloads.lock")
            while True:
                try:
                    lock.acquire(timeout=0)
                    break
                except Timeout:
                    await asyncio.sleep(0.25)
            try:
                yield
            finally:
                lock.release()

    async def download_link(self, video: VideoLink, on_start: Callable[[], None]):
        async with self._download_slot():
            on_start()
            record, reused = await self._find_or_download(video)
            if reused:
                await asyncio.to_thread(self._check_existing_download, record)
            return record, reused

    async def _find_or_download(self, video: VideoLink):
        root = self.config.collection_state_dir
        history_path = root / "history.json"
        history = read_history(history_path)
        identity = history_identity(video, history["videos"])
        record = history["videos"].get(identity)
        reused = record is not None
        if record is None:
            record = await self._download_one(video, identity, root, history, history_path)
        elif record.get("state") == "pending":
            record = self._publish_pending(identity, record, history, history_path)
        return {**record, "identity": identity}, reused

    @staticmethod
    def _check_existing_download(record):
        try:
            actual = file_hash(Path(record["path"]))
        except FileNotFoundError:
            return  # The file has already left the input folder.
        expected = record.get("sha256") or read_object(Path(record["metadata"]))["sha256"]
        if actual != expected:
            raise ValueError("O arquivo na pasta de entrada foi alterado e foi preservado.")

    async def _execute(self, creators):
        root = self.config.collection_state_dir
        report = {
            "started_at": self.state["last_started_at"],
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
            "downloads": [],
            "profiles": [],
            "errors": [],
        }
        lock = None
        try:
            root.mkdir(parents=True, exist_ok=True)
            lock = FileLock(root / "collection.lock")
            lock.acquire(timeout=0)
            async with self._download_slot():
                history_path = root / "history.json"
                history = read_history(history_path)
                for identity, record in list(history["videos"].items()):
                    if record.get("state") == "pending":
                        self._publish_pending(identity, record, history, history_path)
            response = await self.collector.collect(
                ViralRequest(profiles=creators.active_profiles())
            )
            report["profiles"] = response.model_dump(mode="json")["profiles"]
            report["collection_complete"] = response.complete
            for profile in response.profiles:
                for video in profile.videos:
                    try:
                        async with self._download_slot():
                            record, reused = await self._find_or_download(video)
                        if reused:
                            report["skipped"] += 1
                            record["status"] = "already_downloaded"
                        else:
                            report["downloaded"] += 1
                            record["status"] = "downloaded"
                    except Exception as exc:
                        identity = f"{video.platform}:{video.id}"
                        report["failed"] += 1
                        record = {"identity": identity, "status": "failed", "error": str(exc)}
                        logger.warning("Falha no download %s: %s", identity, exc)
                    report["downloads"].append(record)
            status = "completed" if response.complete and not report["failed"] else "partial"
            self.state["status"] = status
        except Timeout:
            self.state.update(status="busy", error="Outra instância está coletando os vídeos.")
            report["errors"].append(self.state["error"])
        except asyncio.CancelledError:
            self.state["status"] = "cancelled"
            report["errors"].append("Coleta interrompida no encerramento do backend.")
            raise
        except Exception as exc:
            self.state.update(status="error", error=str(exc))
            report["errors"].append(str(exc))
            logger.exception("Falha na coleta agendada")
        finally:
            report["finished_at"] = datetime.now(UTC).isoformat()
            report["status"] = self.state["status"]
            self.state.update(
                running=False, last_finished_at=report["finished_at"], last_report=report
            )
            try:
                # Never overwrite another worker's report while it owns the lock.
                if lock is not None and lock.is_locked:
                    write_atomic(root / "last-run.json", report)
            except OSError:
                logger.exception("Não foi possível salvar relatório de coleta")
            finally:
                if lock is not None and lock.is_locked:
                    lock.release()

    def _publish_pending(self, identity, record, history, history_path):
        ready, destination = Path(record["ready_path"]), Path(record["path"])
        if destination.exists():
            if file_hash(destination) != record["sha256"]:
                raise ValueError("Arquivo de destino divergente durante recuperação; preservado.")
            ready.unlink(missing_ok=True)
        elif ready.exists():
            if file_hash(ready) != record["sha256"]:
                raise ValueError("Arquivo preparado divergente durante recuperação; preservado.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            ready.replace(destination)
        # No ready file means the atomic move already happened, even if a bot
        # subsequently consumed the MP4. Do not redownload after a lost commit.
        completed = {**record, "state": "downloaded"}
        history["videos"][identity] = completed
        write_atomic(history_path, history)
        return completed

    async def _download_one(self, video, identity, root, history, history_path):
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", video.id)[:64]
        digest = hashlib.sha256(identity.encode()).hexdigest()[:12]
        stem = f"{video.platform}_{slug}_{digest}"
        destination = (self.config.download_dir / f"{stem}.mp4").resolve()
        sidecar = root / "metadata" / f"{stem}.json"
        if destination.exists():
            saved = read_object(sidecar) if sidecar.exists() else {}
            if saved.get("identity") != identity or saved.get("sha256") != file_hash(destination):
                raise ValueError("Destino existente sem metadados válidos; arquivo preservado.")
            record = {
                "path": str(destination),
                "metadata": str(sidecar.resolve()),
                "downloaded_at": saved["downloaded_at"],
                "state": "downloaded",
            }
            history["videos"][identity] = record
            write_atomic(history_path, history)
            return record
        ready = (root / "ready" / f"{stem}.mp4").resolve()
        if ready.exists():
            metadata = read_object(sidecar)
            if metadata.get("identity") != identity or metadata.get("sha256") != file_hash(ready):
                raise ValueError("Arquivo preparado sem metadados válidos; preservado.")
        else:
            metadata = await self._prepare(video, identity, root, stem, ready, destination, sidecar)
        pending = {
            "identity": identity,
            "path": str(destination),
            "metadata": str(sidecar.resolve()),
            "downloaded_at": metadata["downloaded_at"],
            "sha256": metadata["sha256"],
            "state": "pending",
            "ready_path": str(ready),
        }
        # Persist intent while the file is still in a durable, unwatched folder.
        history["videos"][identity] = pending
        write_atomic(history_path, history)
        return self._publish_pending(identity, pending, history, history_path)

    async def _prepare(self, video, identity, root, stem, ready, destination, sidecar):
        staging_root = root / "staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=stem + "-", dir=staging_root) as temporary:
            path = await self.downloader.download(video, Path(temporary))
            downloaded_at = datetime.now(UTC).isoformat()
            metadata = {
                "identity": identity,
                "downloaded_at": downloaded_at,
                "path": str(destination),
                "sha256": file_hash(path),
                "video": video.model_dump(mode="json"),
            }
            write_atomic(sidecar, metadata)
            ready.parent.mkdir(parents=True, exist_ok=True)
            path.replace(ready)
        return metadata
