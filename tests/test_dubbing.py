import io
import runpy
import wave
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/gerar-dublagem.py"


@pytest.fixture
def dubbing():
    return runpy.run_path(str(SCRIPT))


def plan(*segments, action="dublar_pt_br"):
    return {
        "versao": 2,
        "trecho": {"duracao_segundos": 4},
        "audio": {"acao": action, "dublagem": {"segmentos": list(segments)}},
    }


def segment(start, end, text="Atenção & ação < GTA!"):
    return {"inicio_segundos": start, "fim_segundos": end, "texto_pt_br": text}


def wav(frames):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as result:
        result.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        result.writeframes(frames)
    return buffer.getvalue()


def test_azure_receives_escaped_text_and_audio_lands_at_output_timestamp(dubbing):
    raw = b"\x20\x10" * 12000

    def handle(request):
        assert request.url.host == "brazilsouth.tts.speech.microsoft.com"
        assert request.headers["Ocp-Apim-Subscription-Key"] == "test-key"
        assert "Atenção &amp; ação &lt; GTA!" in request.content.decode()
        return httpx.Response(200, content=wav(raw))

    duration, segments = dubbing["parse_plan"](plan(segment(1, 2)))
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = dubbing["render"](
            client, "test-key", "brazilsouth", "pt-BR-AntonioNeural", duration, segments
        )
    with wave.open(io.BytesIO(result), "rb") as track:
        assert track.getnframes() == 4 * 24000
        assert track.readframes(24000) == b"\0" * 48000
        assert track.readframes(12000) == raw
        assert track.readframes(60000) == b"\0" * 120000


@pytest.mark.parametrize(
    "payload",
    [
        plan(segment(1, 2), action="preservar"),
        plan(segment(1, 2), segment(1.5, 3)),
        plan(segment(3, 5)),
    ],
)
def test_invalid_or_unrequested_dub_is_rejected_before_synthesis(dubbing, payload):
    with pytest.raises(ValueError):
        dubbing["parse_plan"](payload)


def test_overlong_speech_reports_segment_instead_of_clipping(dubbing):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=wav(b"\x20\x10" * 24000)))
    duration, segments = dubbing["parse_plan"](plan(segment(1, 1.5)))
    with httpx.Client(transport=transport) as client, pytest.raises(ValueError, match="Trecho 1"):
        dubbing["render"](client, "test-key", "eastus", "pt-BR-AntonioNeural", duration, segments)
