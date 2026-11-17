"""Experimental CPU inpainting. Run with .tools/ocr-venv/Scripts/python.exe."""

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def find_binary(name):
    installed = shutil.which(name)
    if installed:
        return installed
    candidates = sorted((ROOT / ".tools/ffmpeg").glob(f"**/{name}.exe"))
    if not candidates:
        raise ValueError(f"{name} não encontrado. Execute scripts/activate-media.ps1.")
    return str(candidates[0])


def validate_regions(regions, width, height):
    if not isinstance(regions, list) or not regions:
        raise ValueError("A lista de regiões não pode estar vazia.")
    for r in regions:
        values = [r[k] for k in ("x", "y", "width", "height")]
        if any(type(value) is not int for value in values):
            raise ValueError("Coordenadas devem ser inteiros em pixels.")
        x, y, w, h = values
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
            raise ValueError("Região fora dos limites do vídeo original.")
        start, end = r.get("start", 0), r.get("end", math.inf)
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            raise ValueError("Tempos das regiões devem ser números.")
        if not math.isfinite(start) or start < 0 or math.isnan(end) or end <= start:
            raise ValueError("Intervalo de região inválido: use 0 <= start < end.")


def region_mask(regions, width, height, source_time, dilation):
    mask = np.zeros((height, width), dtype=np.uint8)
    for r in regions:
        if r.get("start", 0) <= source_time < r.get("end", math.inf):
            x, y, w, h = (r[k] for k in ("x", "y", "width", "height"))
            mask[y : y + h, x : x + w] = 255
    return dilate(mask, dilation)


def dilate(mask, pixels):
    if not pixels:
        return mask
    return cv2.dilate(mask, np.ones((pixels * 2 + 1, pixels * 2 + 1), dtype=np.uint8))


def probe(path):
    data = json.loads(
        subprocess.check_output(
            [
                find_binary("ffprobe"),
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ]
        )
    )
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    return data, video


def read_frame(stream, size):
    data = bytearray()
    while len(data) < size:
        block = stream.read(size - len(data))
        if not block:
            break
        data.extend(block)
    if data and len(data) != size:
        raise ValueError("Frame incompleto recebido do FFmpeg.")
    return data


def _process(args):
    source, output = args.input.resolve(), args.output.resolve()
    if not source.is_file():
        raise ValueError(f"Vídeo não encontrado: {source}")
    if source == output or output.suffix.lower() != ".mp4":
        raise ValueError("A saída deve ser um novo arquivo MP4, diferente da entrada.")
    report_path = output.with_suffix(".inpaint.json")
    mask_path = output.with_suffix(".mask.png")
    comparison_path = output.with_suffix(".comparison.jpg")
    for path in (output, report_path, mask_path, comparison_path):
        if path.exists():
            raise ValueError(f"Arquivo já existe; escolha outra saída: {path}")
    if not math.isfinite(args.start) or args.start < 0:
        raise ValueError("--start deve ser finito e não negativo.")
    if not math.isfinite(args.duration) or args.duration <= 0:
        raise ValueError("--duration deve ser finito e positivo.")
    if not math.isfinite(args.radius) or args.radius <= 0 or not 0 <= args.dilate <= 100:
        raise ValueError("Use radius > 0 e dilate entre 0 e 100 pixels.")
    metadata, video = probe(source)
    rotation = next(
        (s.get("rotation", 0) for s in video.get("side_data_list", []) if "rotation" in s), 0
    )
    if rotation:
        raise ValueError("Vídeo com rotação de metadata: normalize a orientação antes de mascarar.")
    if video.get("sample_aspect_ratio", "1:1") not in ("1:1", "N/A"):
        raise ValueError("Normalize o vídeo para pixels quadrados antes de mascarar.")
    width, height = video["width"], video["height"]
    if width % 2 or height % 2:
        raise ValueError("Para yuv420p, normalize o vídeo para dimensões pares.")
    fps = Fraction(video.get("avg_frame_rate") or video["r_frame_rate"])
    if fps <= 0:
        raise ValueError("FPS inválido.")
    total = float(video.get("duration") or metadata["format"]["duration"])
    duration = min(args.duration, total - args.start)
    if duration <= 0:
        raise ValueError("O início deve estar dentro da duração do vídeo.")
    regions, fixed_mask = [], None
    if args.mask:
        fixed_mask = cv2.imread(str(args.mask.resolve()), cv2.IMREAD_GRAYSCALE)
        if fixed_mask is None or fixed_mask.shape != (height, width):
            raise ValueError("A máscara deve ser legível e ter as dimensões exatas da entrada.")
        fixed_mask = dilate(np.where(fixed_mask > 0, 255, 0).astype(np.uint8), args.dilate)
        if not fixed_mask.any():
            raise ValueError("Máscara vazia: marque os pixels a remover em branco.")
    else:
        regions = (
            json.loads(args.regions_json.read_text(encoding="utf-8-sig"))
            if args.regions_json
            else [dict(zip(("x", "y", "width", "height"), r, strict=True)) for r in args.region]
        )
        validate_regions(regions, width, height)
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_binary("ffmpeg")
    common = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin"]
    decoder_command = common + [
        "-ss",
        str(args.start),
        "-i",
        str(source),
        "-t",
        str(duration),
        "-map",
        "0:v:0",
        "-vf",
        f"fps={fps}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "pipe:1",
    ]
    frames = modified = 0
    sample = None
    with tempfile.TemporaryDirectory(prefix="inpaint-", dir=output.parent) as work:
        temporary = Path(work) / "preview.mp4"
        encoder_command = common + [
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-video_size",
            f"{width}x{height}",
            "-framerate",
            str(fps),
            "-i",
            "pipe:0",
            "-ss",
            str(args.start),
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0?",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "fast",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "setsar=1",
            "-c:a",
            "aac",
            "-af",
            "aresample=async=1:first_pts=0",
            "-t",
            str(duration),
            "-movflags",
            "+faststart",
            "-n",
            str(temporary),
        ]
        with (
            (Path(work) / "decode.log").open("w+b") as dlog,
            (Path(work) / "encode.log").open("w+b") as elog,
        ):
            decoder = subprocess.Popen(decoder_command, stdout=subprocess.PIPE, stderr=dlog)
            encoder = None
            try:
                encoder = subprocess.Popen(encoder_command, stdin=subprocess.PIPE, stderr=elog)
                while data := read_frame(decoder.stdout, width * height * 3):
                    frame = np.frombuffer(data, dtype=np.uint8).reshape(height, width, 3)
                    time = args.start + frames / float(fps)
                    mask = (
                        fixed_mask
                        if fixed_mask is not None
                        else region_mask(regions, width, height, time, args.dilate)
                    )
                    if mask.any():
                        cleaned = cv2.inpaint(
                            frame,
                            mask,
                            args.radius,
                            (cv2.INPAINT_TELEA if args.method == "telea" else cv2.INPAINT_NS),
                        )
                        modified += 1
                        if sample is None:
                            sample = (mask.copy(), np.concatenate((frame, cleaned), axis=1), time)
                    else:
                        cleaned = frame
                    encoder.stdin.write(cleaned.tobytes())
                    frames += 1
                encoder.stdin.close()
                if decoder.wait() != 0 or encoder.wait() != 0:
                    raise ValueError("FFmpeg retornou erro.")
            except Exception as exc:
                dlog.seek(0)
                elog.seek(0)
                details = (dlog.read() + elog.read()).decode("utf-8", errors="replace")
                raise ValueError(f"Falha no processamento: {exc}\n{details[-3000:]}") from exc
            finally:
                decoder.stdout.close()
                for child in (decoder, encoder):
                    if child is not None and child.poll() is None:
                        child.terminate()
                        child.wait()
        if not frames or not modified:
            raise ValueError("Nenhum frame foi modificado: confira máscara e intervalos.")
        result_metadata, result_video = probe(temporary)
        if not cv2.imwrite(str(mask_path), sample[0]) or not cv2.imwrite(
            str(comparison_path), sample[1]
        ):
            raise ValueError("Não foi possível salvar evidências visuais.")
        report = {
            "status": "preview_generated",
            "requires_visual_review": True,
            "input": str(source),
            "output": str(output),
            "method": args.method,
            "radius": args.radius,
            "dilation": args.dilate,
            "start": args.start,
            "duration_requested": duration,
            "duration_output": result_video.get("duration"),
            "fps_output": str(fps),
            "frames_processed": frames,
            "frames_modified": modified,
            "regions_source_pixels": regions,
            "mask_input": str(args.mask) if args.mask else None,
            "mask_sample": str(mask_path),
            "comparison": str(comparison_path),
            "comparison_source_time": sample[2],
            "audio_present_output": any(
                s["codec_type"] == "audio" for s in result_metadata["streams"]
            ),
            "limitations": [
                "Inpainting por frame, sem consistência temporal garantida.",
                "Não recupera necessariamente os pixels originais escondidos.",
                "Saída CFR; vídeos VFR têm frames amostrados no FPS médio.",
                "A comparação mostra somente o primeiro frame alterado.",
            ],
            "commands": {"decoder": decoder_command, "encoder": encoder_command},
        }
        temporary.rename(output)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def process(args):
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.with_suffix(".inpaint.lock")
    try:
        with lock.open("x", encoding="utf-8") as handle:
            handle.write("Destino reservado por inpaint-video.py")
    except FileExistsError as exc:
        raise ValueError(f"Destino reservado por outro processamento: {lock}") from exc
    try:
        return _process(args)
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    masks = parser.add_mutually_exclusive_group(required=True)
    masks.add_argument("--region", type=int, nargs=4, action="append", metavar=("X", "Y", "W", "H"))
    masks.add_argument("--mask", type=Path)
    masks.add_argument("--regions-json", type=Path)
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--duration", type=float, default=3, help="Prévia de 3 segundos por padrão")
    parser.add_argument("--method", choices=("telea", "ns"), default="telea")
    parser.add_argument("--radius", type=float, default=3)
    parser.add_argument("--dilate", type=int, default=2, help="Expansão da máscara em pixels")
    args = parser.parse_args()
    try:
        print(f"Prévia gerada. Relatório: {process(args)}")
    except (ValueError, OSError, KeyError, StopIteration, subprocess.SubprocessError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
