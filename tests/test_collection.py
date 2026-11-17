import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest

from gta_viral_collector.collection import CollectionService, CreatorsConfig
from gta_viral_collector.config import Settings
from gta_viral_collector.models import ProfileResult, Video, VideoLink, ViralResponse


def write_config(path, **overrides):
    data = {
        "enabled": True,
        "interval_minutes": 60,
        "run_on_startup": True,
        "profiles": [{"platform": "youtube", "username": "creator", "days": 7, "limit": 2}],
        **overrides,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def config_for(tmp_path):
    config = Settings(
        _env_file=None,
        collection_enabled=False,
        creators_file=tmp_path / "creators.json",
        download_dir=tmp_path / "entrada",
        collection_state_dir=tmp_path / "coleta",
    )
    write_config(config.creators_file)
    return config


class Collector:
    calls = 0

    async def collect(self, payload):
        self.calls += 1
        now = datetime.now(UTC)
        return ViralResponse(
            collected_at=now,
            complete=True,
            profiles=[
                ProfileResult(
                    **p.model_dump(),
                    since=now - timedelta(days=p.days),
                    until=now,
                    status="complete",
                    complete=True,
                    pages_fetched=1,
                    matched_videos=2,
                    videos=[
                        Video(
                            id=i,
                            platform=p.platform,
                            username=p.username,
                            url=f"https://www.youtube.com/watch?v={i}",
                            published_at=now,
                            views=10,
                        )
                        for i in ("first", "second")
                    ],
                )
                for p in payload.profiles
            ],
        )


class Downloader:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    async def download(self, video, staging):
        self.calls.append(video.id)
        if video.id == self.fail:
            raise RuntimeError("download unavailable")
        path = staging / "video.mp4"
        path.write_bytes(b"test media boundary")
        return path


async def test_link_download_can_start_while_profiles_are_being_queried(tmp_path):
    querying = asyncio.Event()
    finish_query = asyncio.Event()

    class SlowCollector(Collector):
        async def collect(self, payload):
            querying.set()
            await finish_query.wait()
            return await super().collect(payload)

    service = CollectionService(SlowCollector(), config_for(tmp_path), downloader=Downloader())
    video = VideoLink(id="manual", platform="youtube", url="https://youtu.be/5FYUzCuF8SM")
    service.request_run()
    try:
        await asyncio.wait_for(querying.wait(), 2)
        record, reused = await asyncio.wait_for(service.download_link(video, lambda: None), 1)
        assert record["state"] == "downloaded"
        assert reused is False
    finally:
        finish_query.set()
        await service.task
    history = json.loads((service.config.collection_state_dir / "history.json").read_text())
    assert set(history["videos"]) == {"youtube:manual", "youtube:first", "youtube:second"}


async def test_waiting_link_download_runs_between_two_profile_downloads(tmp_path):
    first_started = asyncio.Event()
    finish_first = asyncio.Event()
    link_queued = asyncio.Event()

    class SlowDownloader(Downloader):
        async def download(self, video, staging):
            if video.id == "first":
                first_started.set()
                await finish_first.wait()
            return await super().download(video, staging)

    async def send_link():
        link_queued.set()
        return await service.download_link(video, lambda: None)

    downloader = SlowDownloader()
    service = CollectionService(Collector(), config_for(tmp_path), downloader=downloader)
    video = VideoLink(id="manual", platform="youtube", url="https://youtu.be/5FYUzCuF8SM")
    service.request_run()
    try:
        await asyncio.wait_for(first_started.wait(), 2)
        link_task = asyncio.create_task(send_link())
        await asyncio.wait_for(link_queued.wait(), 2)
    finally:
        finish_first.set()
        await service.task
    await asyncio.wait_for(link_task, 2)
    assert downloader.calls == ["first", "manual", "second"]


async def test_downloads_to_input_and_history_prevents_redownload_after_move_and_restart(tmp_path):
    config, downloader = config_for(tmp_path), Downloader()
    collector = Collector()
    service = CollectionService(collector, config, downloader=downloader)
    service.request_run()
    await service.task
    assert service.status()["last_report"]["downloaded"] == 2
    files = list(config.download_dir.glob("*.mp4"))
    assert len(files) == 2
    assert not list(config.download_dir.glob("*.json"))
    metadata = list((config.collection_state_dir / "metadata").glob("*.json"))
    assert len(metadata) == 2
    for item in metadata:
        assert json.loads(item.read_text())["video"]["url"].startswith("https://")
    for file in files:
        file.rename(tmp_path / file.name)
    restarted = CollectionService(collector, config, downloader=downloader)
    restarted.request_run()
    await restarted.task
    assert downloader.calls == ["first", "second"]
    assert restarted.status()["last_report"]["skipped"] == 2


async def test_download_failure_does_not_enter_history_and_is_retried(tmp_path):
    config, downloader = config_for(tmp_path), Downloader(fail="first")
    service = CollectionService(Collector(), config, downloader=downloader)
    service.request_run()
    await service.task
    assert service.status()["status"] == "partial"
    assert service.status()["last_report"]["failed"] == 1
    downloader.fail = None
    service.request_run()
    await service.task
    assert downloader.calls == ["first", "second", "first"]
    assert service.status()["last_report"]["downloaded"] == 1


async def test_scheduler_reloads_config_and_obeys_hour_interval(tmp_path):
    config, collector = config_for(tmp_path), Collector()
    write_config(config.creators_file, profiles=[])
    service = CollectionService(collector, config, downloader=Downloader())
    now = datetime.now(UTC)
    await service.tick(now)
    assert service.task is None
    write_config(config.creators_file)
    await service.tick(now)
    await service.task
    assert collector.calls == 1
    await service.tick(now + timedelta(minutes=59))
    assert collector.calls == 1
    await service.tick(now + timedelta(minutes=60))
    await service.task
    assert collector.calls == 2
    write_config(config.creators_file, enabled=False)
    await service.tick(now + timedelta(minutes=120))
    assert collector.calls == 2


async def test_no_startup_run_waits_one_interval(tmp_path):
    config, collector = config_for(tmp_path), Collector()
    write_config(config.creators_file, run_on_startup=False)
    service = CollectionService(collector, config, downloader=Downloader())
    now = datetime.now(UTC)
    await service.tick(now)
    assert service.task is None
    await service.tick(now + timedelta(minutes=60))
    await service.task
    assert collector.calls == 1


async def test_invalid_edit_keeps_last_schedule_and_valid_edit_updates_next_run(tmp_path):
    config, collector = config_for(tmp_path), Collector()
    write_config(config.creators_file, interval={"value": 2, "unit": "hours"})
    service = CollectionService(collector, config, downloader=Downloader())
    now = datetime.now(UTC)
    await service.tick(now)
    await service.task
    config.creators_file.write_text('{"profiles": [', encoding="utf-8")
    await service.tick(now + timedelta(minutes=119))
    assert service.next_run == now + timedelta(hours=2)
    assert collector.calls == 1
    assert service.status()["using_last_valid_config"] is True
    assert service.status()["config_error"]
    await service.tick(now + timedelta(hours=2))
    await service.task
    assert collector.calls == 2
    assert service.status()["last_report"]["skipped"] == 2
    write_config(
        config.creators_file,
        interval={"value": 5, "unit": "minutes"},
        profiles=[{"platform": "instagram", "username": "novo", "days": 1}],
    )
    await service.tick(now + timedelta(hours=2, minutes=4))
    assert service.next_run == now + timedelta(hours=2, minutes=5)
    assert service.status()["config_error"] is None
    assert service.status()["using_last_valid_config"] is False
    await service.tick(now + timedelta(hours=2, minutes=5))
    await service.task
    assert collector.calls == 3
    assert service.status()["last_report"]["profiles"][0]["username"] == "novo"


async def test_auto_pause_keeps_manual_available_and_resume_does_not_overlap(tmp_path):
    config, collector = config_for(tmp_path), Collector()
    write_config(config.creators_file, automatic_downloads=False)
    service = CollectionService(collector, config, downloader=Downloader())
    now = datetime.now(UTC)
    await service.tick(now)
    assert service.task is None
    assert service.status()["status"] == "automatic_paused"
    service.request_run(now=now)
    task = service.task
    await service.tick(now)
    write_config(config.creators_file, automatic_downloads=True)
    await service.tick(now)
    assert service.task is task
    assert service.status()["status"] == "running"
    await task
    await service.tick(now)
    assert service.next_run == now + timedelta(hours=1)
    assert collector.calls == 1
    await service.tick(now + timedelta(hours=1))
    await service.task
    assert collector.calls == 2


async def test_bad_config_and_corrupt_history_never_reset_successes(tmp_path):
    config, collector = config_for(tmp_path), Collector()
    service = CollectionService(collector, config, downloader=Downloader())
    config.creators_file.write_text("{invalid")
    await service.tick(datetime.now(UTC))
    assert service.status()["status"] == "configuration_error"
    assert collector.calls == 0
    write_config(config.creators_file)
    config.collection_state_dir.mkdir()
    history = config.collection_state_dir / "history.json"
    history.write_text("corrupt")
    service.request_run()
    await service.task
    assert service.status()["status"] == "error"
    assert history.read_text() == "corrupt"
    assert collector.calls == 0


async def test_active_run_rejects_second_trigger(tmp_path):
    config = config_for(tmp_path)
    service = CollectionService(Collector(), config, downloader=Downloader())
    service.request_run()
    with pytest.raises(ValueError, match="andamento"):
        service.request_run()
    await service.task


async def test_failed_history_commit_after_bot_moves_file_does_not_download_twice(
    tmp_path, monkeypatch
):
    from gta_viral_collector import collection

    class OneCollector(Collector):
        async def collect(self, payload):
            response = await super().collect(payload)
            response.profiles[0].videos = response.profiles[0].videos[:1]
            return response

    config, downloader = config_for(tmp_path), Downloader()
    actual_write = collection.write_atomic
    failed = False

    def fail_after_publication(path, data):
        nonlocal failed
        ready = list(config.download_dir.glob("*.mp4"))
        if path.name == "history.json" and ready and not failed:
            ready[0].rename(tmp_path / ready[0].name)
            failed = True
            raise OSError("commit failed after bot consumed video")
        return actual_write(path, data)

    monkeypatch.setattr(collection, "write_atomic", fail_after_publication)
    service = CollectionService(OneCollector(), config, downloader=downloader)
    service.request_run()
    await service.task
    assert failed
    restarted = CollectionService(OneCollector(), config, downloader=downloader)
    restarted.request_run()
    await restarted.task
    assert downloader.calls == ["first"]
    assert restarted.status()["last_report"]["skipped"] == 1


async def test_process_lock_protects_history_and_other_worker_report(tmp_path):
    from filelock import FileLock

    config, collector = config_for(tmp_path), Collector()
    config.collection_state_dir.mkdir()
    report = config.collection_state_dir / "last-run.json"
    report.write_text('{"owner":"other"}', encoding="utf-8")
    service = CollectionService(collector, config, downloader=Downloader())
    with FileLock(config.collection_state_dir / "collection.lock"):
        service.request_run()
        await service.task
    assert service.status()["status"] == "busy"
    assert collector.calls == 0
    assert json.loads(report.read_text()) == {"owner": "other"}


def test_collection_api_runs_in_background_and_reports_configuration_errors(tmp_path):
    from fastapi.testclient import TestClient

    from gta_viral_collector.main import create_app

    config = config_for(tmp_path)
    app = create_app(config)
    with TestClient(app) as client:
        service = app.state.collection
        service.collector = Collector()
        service.downloader = Downloader()
        assert client.post("/api/collection/run").status_code == 202

        async def finish():
            await service.task

        client.portal.call(finish)
        status = client.get("/api/collection/status").json()
        assert status["status"] == "completed"
        assert status["last_report"]["downloaded"] == 2
        write_config(config.creators_file, profiles=[])
        assert client.post("/api/collection/run").status_code == 409
        config.creators_file.write_text("invalid")
        assert client.post("/api/collection/run").status_code == 422


def test_config_filters_disabled_profiles_and_validates_fields():
    config = CreatorsConfig.model_validate(
        {
            "profiles": [
                {"platform": "youtube", "username": "@creator", "days": 7, "limit": 1},
                {"enabled": False, "platform": "instagram", "username": "other", "days": 3},
            ]
        }
    )
    assert len(config.active_profiles()) == 1
    assert config.active_profiles()[0].username == "creator"
    with pytest.raises(ValueError):
        CreatorsConfig.model_validate({"interval_minutes": 0})


async def test_pending_publication_recovers_without_downloading_again(tmp_path, monkeypatch):
    config, downloader = config_for(tmp_path), Downloader()
    service = CollectionService(Collector(), config, downloader=downloader)
    real_publish = service._publish_pending

    def unavailable(*args):
        raise OSError("publication temporarily unavailable")

    monkeypatch.setattr(service, "_publish_pending", unavailable)
    service.request_run()
    await service.task
    assert len(list((config.collection_state_dir / "ready").glob("*.mp4"))) == 2
    assert not list(config.download_dir.glob("*.mp4"))
    monkeypatch.setattr(service, "_publish_pending", real_publish)
    service.request_run()
    await service.task
    assert len(list(config.download_dir.glob("*.mp4"))) == 2
    assert downloader.calls == ["first", "second"]
