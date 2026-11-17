# Ferramentas locais do ClipshortsBr

Instaladas em Windows com Python 3.12, usando CPU. A análise visual será feita
pelo Codex. Não foi adicionada integração Gemini nem credencial OpenAI API.
O Codex CLI já estava instalado (`codex-cli 0.169.0`).

## Pastas

- `repos/PaddleOCR`: clone do projeto oficial, referência e código-fonte.
- `repos/faster-whisper`: clone do projeto oficial, referência e código-fonte.
- `.tools/ffmpeg`: executáveis FFmpeg/ffprobe para Windows.
- `.tools/ocr-venv`: PaddlePaddle 3.3.1 e PaddleOCR 3.7.0.
- `.tools/whisper-venv`: faster-whisper 1.2.1.
- `.tools/models`: modelos baixados para inferência local.

Os pacotes executados vêm das versões publicadas no PyPI; os clones são para
consulta, não instalações editáveis. Não importar Paddle e CTranslate2 no mesmo
processo: foi reproduzido conflito de DLL no Windows. Cada tarefa usa seu Python.
O ambiente `.venv` do backend é independente.

Repositórios, executáveis, modelos e ambientes estão ignorados pelo Git.
Versões diretas estão em `requirements-media.txt`; dependências completas de cada
ambiente estão em `requirements-ocr.lock.txt` e `requirements-whisper.lock.txt`.

## Usar no PowerShell

Na raiz do projeto:

```powershell
. .\scripts\activate-media.ps1
ffmpeg -version
ffprobe -v error -show_format -show_streams -of json 'caminho/video.mp4'
```

O script ajusta somente a sessão atual, sem alterar PATH global. Também exporta
os caminhos dos Pythons e dos caches de modelos. Para processos iniciados em
outro terminal, execute novamente o script ou use os caminhos absolutos.

### Extrair frames para o Codex analisar

```powershell
New-Item -ItemType Directory -Force media/frames | Out-Null
ffmpeg -i 'caminho/video.mp4' -vf 'fps=1' media/frames/frame-%04d.jpg
```

O Codex pode inspecionar os frames e os resultados de OCR/transcrição e preparar
um plano de edição. Esta instalação não cria agentes, agendamentos ou servidor MCP.

### OCR local

Use `$env:CLIPSHORTS_OCR_PYTHON` para executar este Python:

```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(
    text_detection_model_name="PP-OCRv5_mobile_det",
    text_recognition_model_name="latin_PP-OCRv5_mobile_rec",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    device="cpu",
    enable_mkldnn=False,
)
for result in ocr.predict("assets/clipshortsbr/moldura-amarela.png"):
    print(result["rec_texts"])
    # rec_polys e rec_scores fornecem polígonos e confiança por texto.
```

`enable_mkldnn=False` é necessário nesta instalação: a execução com oneDNN ativado
falhou com `ConvertPirAttribute2RuntimeAttribute`. Os modelos mobile escolhidos
fazem detecção e reconhecimento de textos latinos, incluindo português.

### Transcrição local

Use `$env:CLIPSHORTS_WHISPER_PYTHON` para executar este Python:

```python
import os
from faster_whisper import WhisperModel

model = WhisperModel(
    os.environ["CLIPSHORTS_WHISPER_MODEL"],
    device="cpu", compute_type="int8", local_files_only=True,
)
segments, info = model.transcribe("caminho/video.mp4")
for segment in segments:
    print(segment.start, segment.end, segment.text)
```

O modelo base é multilíngue. Seus pesos ficam em `.tools/models/whisper-base`;
com os arquivos instalados, o exemplo funciona sem baixar novamente ou usar API.

## Inpainting experimental

Disponível em `scripts/inpaint-video.py`, executado com o Python do OCR.
Aceita retângulos, máscara PNG e regiões por intervalo. Veja os comandos e os
limites em [docs/inpainting.md](inpainting.md). Não usa modelos generativos;
todo resultado exige revisão visual e temporal.

## Dublagem

O Editor pode chamar `scripts/gerar-dublagem.py` para gerar um WAV a partir da
tradução e dos tempos do Analista. O script usa a chave e a região do Azure
Speech no `.env` local. Veja o [comando e o formato do plano](dublagem.md).

## Fontes e licenças

- FFmpeg: https://ffmpeg.org/download.html; binários Windows de
  https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2.
- PaddleOCR: https://github.com/PaddlePaddle/PaddleOCR (Apache 2.0).
- faster-whisper: https://github.com/SYSTRAN/faster-whisper (MIT).
- ProPainter não foi instalado devido à restrição de uso não comercial.

Sem cobrança por chamada das ferramentas locais; usam os recursos da máquina.
O consumo do Codex segue a conta e o plano usados para executá-lo.

## Verificação desta instalação

- FFmpeg 9.0.2 gerou um MP4 H.264; ffprobe confirmou duração e resolução.
- ZIP do FFmpeg conferido com SHA256 informado no release oficial do GitHub.
- PaddleOCR reconheceu `ClipshortsBr` e `OS MELHORES CLIPES` na moldura do canal.
- Whisper base carregou os pesos locais em CPU/int8 e executou inferência em
  áudio de silêncio. Transcrição de fala real ainda não foi avaliada.
- SHA256 dos pesos Whisper conferido com o metadado do repositório do modelo:
  `d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9`.
- Dependências dos dois ambientes passaram pela verificação de compatibilidade
  `uv pip check`.
