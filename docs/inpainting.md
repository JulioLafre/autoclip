# Inpainting experimental de vídeo com OpenCV

Ferramenta local CPU: `scripts/inpaint-video.py`. Usa o OpenCV já instalado no
ambiente OCR. Não baixa modelos e não faz chamadas a serviços pagos. Não utiliza
ProPainter ou preenchimento generativo. Não precisa reiniciar o backend.

## Preparar

Na raiz do projeto:

```powershell
. .\scripts\activate-media.ps1
& $env:CLIPSHORTS_OCR_PYTHON scripts/inpaint-video.py --help
```

Use esta ferramenta **antes de inserir a tradução**. Todas as
coordenadas se referem ao arquivo passado em `--input`, em pixels, com origem no
canto superior esquerdo. Não use coordenadas do vídeo final para processar o original.

## Região retangular fixa

Sintaxe (as coordenadas abaixo são apenas exemplo; medir em cada vídeo):

```powershell
& $env:CLIPSHORTS_OCR_PYTHON scripts/inpaint-video.py `
  --input media/entrada/video.mp4 `
  --output media/revisar/video-inpaint-preview.mp4 `
  --region 30 146 300 82 --start 0 --duration 3
```

`--region X Y LARGURA ALTURA` pode ser repetido. Retângulos removem a região
inteira, incluindo conteúdo entre as letras. Prefira máscara precisa quando
houver detalhes importantes no fundo.

## Máscara PNG precisa

Prepare uma imagem de máscara com a mesma largura e altura do vídeo de entrada:
preto = preservar; branco = reconstruir. A máscara é lida em tons de cinza, sem
usar transparência; qualquer valor acima de zero será tratado como branco.
Para legenda, inclua letras, contornos e sombras. Não use uma captura com a
legenda desenhada como máscara sem convertê-la explicitamente para esse formato.

```powershell
& $env:CLIPSHORTS_OCR_PYTHON scripts/inpaint-video.py `
  --input media/entrada/video.mp4 `
  --output media/revisar/video-mask-preview.mp4 `
  --mask media/planos/video-mask.png --start 0 --duration 3
```

Não há geração automática de máscara por OCR nesta ferramenta. O analista/editor
deve fornecê-la ou usar retângulos. OCR detecta a região, mas a caixa detectada
não é necessariamente uma máscara precisa dos pixels das letras.

## Regiões por intervalo

`--regions-json` recebe um arquivo UTF-8 com uma lista:

```json
[
  {"x": 30, "y": 146, "width": 300, "height": 82, "start": 0, "end": 1.5},
  {"x": 40, "y": 160, "width": 280, "height": 75, "start": 1.5, "end": 3}
]
```

Os números são exemplos. `start`/`end` são segundos **no vídeo de entrada**,
independentemente de `--start`. Início inclusivo, fim exclusivo. Sem esses campos,
uma região vale por todo o trecho. Não há tracking ou interpolação automática:
texto em movimento exige regiões/máscaras adequadas, ou deve seguir para revisão.

```powershell
& $env:CLIPSHORTS_OCR_PYTHON scripts/inpaint-video.py `
  --input media/entrada/video.mp4 `
  --output media/revisar/video-timed-preview.mp4 `
  --regions-json media/planos/video-regions.json --start 0 --duration 3
```

## Parâmetros e resultado

- `--start`: começo da prévia no original; padrão 0.
- `--duration`: duração em segundos; padrão 3. Para o vídeo inteiro, informe sua
  duração, obtida no ffprobe. Se ultrapassar o fim, é limitada ao conteúdo disponível.
- `--method telea|ns`: método OpenCV; padrão `telea`.
- `--radius`: vizinhança para reconstrução; padrão 3, maior não significa melhor.
- `--dilate`: expansão da máscara em pixels; padrão 2, use 0 para desativar.
- Escolha somente uma modalidade: `--region`, `--mask` ou `--regions-json`.

Para `video-preview.mp4`, são gerados:

- `video-preview.mp4`: trecho em resolução original, H.264/yuv420p, áudio AAC
  quando existir (primeira faixa). O áudio é recortado do original e recodificado;
  não é dublado nem substituído.
- `video-preview.mask.png`: máscara do primeiro frame alterado.
- `video-preview.comparison.jpg`: antes à esquerda, depois à direita, desse frame.
- `video-preview.inpaint.json`: parâmetros, contagens, presença de áudio e limitações.

Arquivos existentes não são sobrescritos. Use outro nome para cada tentativa.
Um arquivo `.inpaint.lock` reserva o destino enquanto a tarefa está em execução.
Se o processo for encerrado à força, remova esse lock somente depois de confirmar
que não há outra tarefa usando o destino.
O relatório sempre marca `requires_visual_review=true`: execução técnica bem
sucedida não equivale a remoção visual aprovada.

## Limites e revisão pelos bots

Este é inpainting **independente por frame**, com pixels vizinhos. Pode borrar
texturas, deformar detalhes e causar cintilação. Não recupera os pixels originais
com garantia e não é indicado para grandes áreas ou texto sobre rostos/mãos.

Primeiro gere 2–3 segundos. Veja a máscara, compare frames e examine o vídeo em
movimento. Uma imagem de comparação sozinha não valida consistência temporal.
Se aprovado, processe o trecho desejado e aplique a tradução no quadro original.
Se a prévia mostrar defeitos, tente outra máscara ou use a alternativa prevista
na política editorial.

A saída usa FPS constante baseado no FPS médio informado. Entradas com FPS
variável são reamostradas. Vídeos com rotação em metadata, dimensões ímpares ou
pixels não quadrados precisam ser normalizados antes e ter suas máscaras medidas
depois da normalização. No fluxo ClipshortsBr, escolha outro método se preparar
o arquivo exigir alteração de tamanho, enquadramento ou proporção. Não há
preservação de HDR ou de faixas de legenda.

### Texto curto para o conhecimento dos bots

```text
Há inpainting experimental OpenCV em scripts/inpaint-video.py. Leia
docs/inpainting.md. Ative scripts/activate-media.ps1 e execute com
$env:CLIPSHORTS_OCR_PYTHON. Aceita --region X Y W H (repetível), --mask PNG ou
--regions-json, além de --start/--duration (padrão 3 s). Coordenadas e tempos
referem-se ao vídeo de entrada. Use antes de inserir a tradução. Gere uma
prévia em media/revisar/, verifique a máscara e o resultado em movimento antes
de processar o trecho inteiro. É preenchimento por frame, sem garantia temporal.
Não é inpainting generativo. Textos em faixa sólida continuam usando cobertura.
```

## Verificação técnica

Os testes de mídia precisam de OpenCV e pytest no Python usado:

```powershell
.tools/ocr-venv/Scripts/python.exe -m pytest tests/test_inpaint_video.py -q
```

Eles executam FFmpeg/OpenCV reais para conferir remoção em fundo simples,
regiões/PNG/intervalos, áudio, duração e proteção de arquivos existentes.
Isso não substitui a avaliação visual do conteúdo real.
