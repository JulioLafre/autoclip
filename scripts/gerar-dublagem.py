"""Gera uma faixa WAV sincronizada com falas traduzidas no plano do Editor."""

import argparse
import io
import json
import os
import re
import sys
import wave
from pathlib import Path
from typing import Annotated, Literal
from xml.sax.saxutils import escape

import httpx
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_VOICE = "pt-BR-AntonioNeural"
SAMPLE_RATE = 24000
SAMPLE_BYTES = 2
Seconds = Annotated[float, Field(strict=True, ge=0, le=600, allow_inf_nan=False)]
SpeechText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inicio_segundos: Seconds
    fim_segundos: Seconds
    texto_pt_br: SpeechText


class Timeline(BaseModel):
    duracao_segundos: Seconds


class Dub(BaseModel):
    segmentos: list[Segment] = Field(min_length=1)


class AudioPlan(BaseModel):
    acao: Literal["dublar_pt_br"]
    dublagem: Dub


class Plan(BaseModel):
    versao: Literal[2]
    trecho: Timeline
    audio: AudioPlan


def sample_at(seconds: float) -> int:
    return round(seconds * SAMPLE_RATE)


def parse_plan(payload: object) -> tuple[float, list[Segment]]:
    plan = Plan.model_validate(payload)
    duration = plan.trecho.duracao_segundos
    segments = plan.audio.dublagem.segmentos
    previous_end = 0.0
    for index, segment in enumerate(segments, start=1):
        start, end = segment.inicio_segundos, segment.fim_segundos
        if start < previous_end or end > duration or sample_at(end) <= sample_at(start):
            raise ValueError(
                f"Trecho {index}: tempos devem estar em ordem, sem sobreposição e dentro da saída."
            )
        previous_end = end
    return duration, segments


def synthesize(client: httpx.Client, key: str, region: str, voice: str, text: str) -> bytes:
    ssml = (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="pt-BR">'
        f'<voice name="{voice}">{escape(text)}</voice></speak>'
    )
    response = client.post(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
            "User-Agent": "ClipshortsBr",
        },
        content=ssml.encode("utf-8"),
    )
    if not response.is_success:
        detail = {
            401: "confira a chave e a região do recurso",
            403: "confira o acesso e a cota do recurso",
            429: "aguarde e confira o limite de requisições e a cota do recurso",
        }.get(response.status_code, "confira a configuração do recurso e a voz")
        raise ValueError(f"Azure Speech respondeu HTTP {response.status_code}. {detail}.")
    try:
        with wave.open(io.BytesIO(response.content), "rb") as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (
                1,
                SAMPLE_BYTES,
                SAMPLE_RATE,
            ):
                raise ValueError("Azure retornou um WAV fora do formato solicitado.")
            frames = audio.getnframes()
            raw = audio.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise ValueError("Azure retornou um WAV inválido.") from exc
    if not raw or len(raw) != frames * SAMPLE_BYTES:
        raise ValueError("Azure retornou áudio vazio ou incompleto.")
    return raw


def render(
    client: httpx.Client,
    key: str,
    region: str,
    voice: str,
    duration: float,
    segments: list[Segment],
) -> bytes:
    if not re.fullmatch(r"[a-z][a-z0-9]*", region):
        raise ValueError("Use o código da região Azure, como brazilsouth ou eastus.")
    if not re.fullmatch(r"pt-BR-[a-zA-Z0-9]+(?:[-:][a-zA-Z0-9]+)*", voice):
        raise ValueError("Use uma voz Azure com código pt-BR.")

    track = bytearray(sample_at(duration) * SAMPLE_BYTES)
    for index, segment in enumerate(segments, start=1):
        start = sample_at(segment.inicio_segundos) * SAMPLE_BYTES
        end = sample_at(segment.fim_segundos) * SAMPLE_BYTES
        raw = synthesize(client, key, region, voice, segment.texto_pt_br)
        seconds = len(raw) / (SAMPLE_RATE * SAMPLE_BYTES)
        if len(raw) > end - start:
            available = segment.fim_segundos - segment.inicio_segundos
            raise ValueError(
                f"Trecho {index} ({segment.inicio_segundos:.2f}–{segment.fim_segundos:.2f} s) "
                f"gerou {seconds:.2f} s para {available:.2f} s disponíveis. "
                "Encurte o texto em pt-BR."
            )
        track[start : start + len(raw)] = raw
    result = io.BytesIO()
    with wave.open(result, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(SAMPLE_BYTES)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(track)
    return result.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True, help="Plano JSON versão 2.")
    parser.add_argument("--output", type=Path, required=True, help="Caminho de um novo WAV.")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="Voz Azure em português do Brasil.")
    args = parser.parse_args()
    try:
        output = args.output.resolve()
        if output.suffix.lower() != ".wav" or output.exists():
            raise ValueError("Informe um caminho de saída .wav que ainda não exista.")
        payload = json.loads(args.plan.read_text(encoding="utf-8-sig"))
        duration, segments = parse_plan(payload)

        env = dotenv_values(PROJECT / ".env", encoding="utf-8-sig", interpolate=False)
        key = (os.environ.get("AZURE_SPEECH_KEY", env.get("AZURE_SPEECH_KEY")) or "").strip()
        region = os.environ.get("AZURE_SPEECH_REGION", env.get("AZURE_SPEECH_REGION")) or ""
        region = region.strip().lower()
        if not key or not region:
            raise ValueError("Configure AZURE_SPEECH_KEY e AZURE_SPEECH_REGION no .env.")

        output.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=30) as client:
            audio = render(client, key, region, args.voice, duration, segments)
        with output.open("xb") as handle:
            handle.write(audio)
    except httpx.RequestError:
        print(
            "Não foi possível conectar ao Azure Speech. Confira a rede e a região.", file=sys.stderr
        )
        return 1
    except (ValueError, OSError) as exc:
        print(f"Erro na dublagem: {exc}", file=sys.stderr)
        return 1

    print(f"WAV gerado em {output} ({len(segments)} trecho(s), {duration:.2f} s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
