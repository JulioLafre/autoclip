import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("cv2", reason="Inpainting requer o ambiente de mídia/OpenCV")

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inpaint-video.py"


def load_tool():
    assert SCRIPT.is_file(), "Ferramenta de inpainting ainda não implementada"
    spec = importlib.util.spec_from_file_location("inpaint_video", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_regions_follow_source_time_and_dilate_without_touching_other_pixels():
    tool = load_tool()
    regions = [{"x": 10, "y": 10, "width": 10, "height": 8, "start": 2, "end": 3}]
    tool.validate_regions(regions, 64, 48)
    assert not tool.region_mask(regions, 64, 48, 1.9, 2).any()
    mask = tool.region_mask(regions, 64, 48, 2, 2)
    assert mask[8, 8] == 255 and mask[19, 21] == 255
    assert mask[7, 7] == 0 and mask[30, 30] == 0
    assert not tool.region_mask(regions, 64, 48, 3, 2).any()


@pytest.mark.parametrize(
    "region",
    [
        {"x": -1, "y": 0, "width": 10, "height": 10},
        {"x": 60, "y": 0, "width": 10, "height": 10},
        {"x": 0, "y": 0, "width": 0, "height": 10},
        {"x": 0, "y": 0, "width": 10, "height": 10, "start": 3, "end": 2},
    ],
)
def test_rejects_invalid_regions_instead_of_silently_clipping(region):
    tool = load_tool()
    with pytest.raises(ValueError):
        tool.validate_regions([region], 64, 48)


@pytest.mark.parametrize("mask_mode", ["region", "mask", "timed"])
def test_real_cli_removes_mark_keeps_audio_and_refuses_overwrite(tmp_path, mask_mode):
    tool = load_tool()
    ffmpeg = tool.find_binary("ffmpeg")
    ffprobe = tool.find_binary("ffprobe")
    source, output = tmp_path / "source.mp4", tmp_path / "clean.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=white:s=64x48:r=10:d=2,drawbox=x=20:y=16:w=12:h=10:color=black:t=fill",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    mask_args = ["--region", "19", "15", "14", "12"]
    if mask_mode == "mask":
        import cv2
        import numpy as np

        mask = np.zeros((48, 64), dtype=np.uint8)
        mask[15:27, 19:33] = 255
        mask_path = tmp_path / "mask.png"
        assert cv2.imwrite(str(mask_path), mask)
        mask_args = ["--mask", str(mask_path)]
    elif mask_mode == "timed":
        path = tmp_path / "regions.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "x": 19,
                        "y": 15,
                        "width": 14,
                        "height": 12,
                        "start": 0.5,
                        "end": 1.5,
                    }
                ]
            ),
            encoding="utf-8",
        )
        mask_args = ["--regions-json", str(path)]
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(source),
            "--output",
            str(output),
            *mask_args,
            "--start",
            "0.5",
            "--duration",
            "1",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output.with_suffix(".inpaint.json").read_text(encoding="utf-8"))
    assert report["frames_processed"] == 10
    assert report["frames_modified"] == 10
    assert report["requires_visual_review"] is True
    probe = json.loads(
        subprocess.check_output(
            [
                ffprobe,
                "-v",
                "error",
                "-show_streams",
                "-of",
                "json",
                str(output),
            ]
        )
    )
    assert {s["codec_type"] for s in probe["streams"]} == {"video", "audio"}
    assert abs(float(probe["streams"][0]["duration"]) - 1) < 0.11
    import cv2

    capture = cv2.VideoCapture(str(output))
    ok, frame = capture.read()
    capture.release()
    assert ok and frame[20, 25].mean() > 220
    assert frame[5, 5].mean() > 220
    original_bytes = output.read_bytes()
    again = subprocess.run(result.args, capture_output=True, text=True)
    assert again.returncode != 0
    assert output.read_bytes() == original_bytes


def test_refuses_output_reserved_by_another_worker(tmp_path):
    tool = load_tool()
    output = tmp_path / "reserved.mp4"
    lock = output.with_suffix(".inpaint.lock")
    lock.write_text("another-worker", encoding="utf-8")
    with pytest.raises(ValueError, match="reservad"):
        tool.process(argparse.Namespace(input=tmp_path / "input.mp4", output=output))
    assert lock.read_text(encoding="utf-8") == "another-worker"


def test_keeps_initial_audio_delay(tmp_path):
    import numpy as np

    tool = load_tool()
    source, output = tmp_path / "delayed.mp4", tmp_path / "preview.mp4"
    ffmpeg = tool.find_binary("ffmpeg")
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=white:s=64x48:r=10:d=2",
            "-itsoffset",
            "1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(source),
            "--output",
            str(output),
            "--region",
            "20",
            "16",
            "12",
            "10",
            "--duration",
            "2",
        ],
        check=True,
        capture_output=True,
    )
    audio = np.frombuffer(
        subprocess.check_output(
            [
                ffmpeg,
                "-v",
                "error",
                "-i",
                str(output),
                "-map",
                "0:a:0",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "f32le",
                "pipe:1",
            ]
        ),
        dtype=np.float32,
    )
    assert np.sqrt(np.mean(audio[:8000] ** 2)) < 0.001
    assert np.sqrt(np.mean(audio[24000:28000] ** 2)) > 0.01


def test_video_without_audio_is_supported(tmp_path):
    tool = load_tool()
    source, output = tmp_path / "silent.mp4", tmp_path / "preview.mp4"
    subprocess.run(
        [
            tool.find_binary("ffmpeg"),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=white:s=64x48:r=10:d=1",
            "-c:v",
            "libx264",
            str(source),
        ],
        check=True,
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(source),
            "--output",
            str(output),
            "--region",
            "20",
            "16",
            "12",
            "10",
            "--duration",
            "1",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output.with_suffix(".inpaint.json").read_text(encoding="utf-8"))
    assert report["audio_present_output"] is False
    assert report["frames_processed"] == 10
