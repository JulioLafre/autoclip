# Execute com dot sourcing: . .\scripts\activate-media.ps1
$mediaRoot = Split-Path -Parent $PSScriptRoot
$mediaBin = Get-ChildItem -LiteralPath (Join-Path $mediaRoot '.tools/ffmpeg') -Filter ffmpeg.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $mediaBin) {
    throw 'FFmpeg não encontrado em .tools/ffmpeg.'
}
$env:PATH = "$($mediaBin.DirectoryName);$env:PATH"
$env:CLIPSHORTS_OCR_PYTHON = Join-Path $mediaRoot '.tools/ocr-venv/Scripts/python.exe'
$env:CLIPSHORTS_WHISPER_PYTHON = Join-Path $mediaRoot '.tools/whisper-venv/Scripts/python.exe'
$env:PADDLE_PDX_CACHE_HOME = Join-Path $mediaRoot '.tools/models/paddlex'
$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK = 'True'
$env:HF_HOME = Join-Path $mediaRoot '.tools/models/huggingface'
$env:HF_HUB_DISABLE_XET = '1'
$env:CLIPSHORTS_WHISPER_MODEL = Join-Path $mediaRoot '.tools/models/whisper-base'
Write-Host 'FFmpeg e ffprobe disponíveis nesta sessão.'
Write-Host 'OCR: $env:CLIPSHORTS_OCR_PYTHON | Transcrição: $env:CLIPSHORTS_WHISPER_PYTHON'
