# Dublagem do ClipshortsBr com Azure Speech

O Analista transcreve a fala com Whisper, confirma o conteúdo e escreve uma
tradução curta em pt-BR para cada intervalo. O Editor chama `scripts/gerar-dublagem.py`
no PowerShell para sintetizar e alinhar uma faixa WAV. Cada chamada ao Azure
envia o texto traduzido de um trecho. A chave e a região são lidas do `.env` local.

## Testar a voz

O projeto usa `AZURE_SPEECH_KEY` e `AZURE_SPEECH_REGION`. A região deve ser o
código do recurso, como `brazilsouth` ou `eastus`. Na raiz do projeto, execute o
exemplo com um nome de saída ainda livre.

```powershell
.venv\Scripts\python.exe scripts/gerar-dublagem.py `
  --plan examples/plano-dublagem.json `
  --output media/revisar/dublagem-exemplo.wav
```

A voz padrão é `pt-BR-AntonioNeural`. Para experimentar uma voz feminina,
adicione `--voice pt-BR-FranciscaNeural`. O WAV de prévia tem 6 s no exemplo.

## Usar em um trabalho

1. O Analista planeja dublagem quando houver fala em inglês confirmada, conforme
   a política editorial. Ele traduz para pt-BR e inclui no plano
   `audio.acao = "dublar_pt_br"`.
   O [JSON de exemplo](../examples/plano-dublagem.json) mostra o bloco mínimo
   que o script lê. O plano de edição completo continua seguindo sua política.
2. O Editor executa o mesmo comando com `--plan` apontando para o plano do
   trabalho, e um WAV próprio em `media/revisar/`. Configure as instruções
   atualizadas no OpenBot para que ele saiba quando chamar o script.
3. O Editor confere a voz e o encaixe antes de compor o MP4. O WAV começa no tempo zero
   do trecho editado e tem a duração de `trecho.duracao_segundos`. Há silêncio
   fora das falas. O Editor deve alinhar o WAV com o trecho de vídeo selecionado.
   Na montagem, preserve o tempo zero da faixa dublada e as dimensões da imagem.

Campos de cada item em `audio.dublagem.segmentos`

| Campo | Formato |
| --- | --- |
| `inicio_segundos` | Início da fala em segundos, relativo à saída |
| `fim_segundos` | Fim do espaço disponível, relativo à saída |
| `texto_pt_br` | Fala traduzida e revisada para dizer nesse intervalo |

Ordene por início e reserve intervalos sem sobreposição. Se uma fala sintetizada
ultrapassar o tempo disponível, o comando informa qual trecho encurtar e encerra
sem gravar o WAV. Escolha um novo nome para cada tentativa já renderizada.

## Mixagem e OpenBot

Se o original contiver principalmente narração, use o WAV como faixa principal.
Se houver música ou efeitos em uma faixa independente, misture essa faixa com a
voz. Quando tudo estiver numa faixa só, substituir ou baixar o áudio original
também afeta a trilha e os efeitos. Registre essa escolha no plano para o Editor
executar. Os tempos alinham o início das falas, sem alterar o movimento labial.

O Editor usa o ambiente Python `.venv` pelo terminal, a partir da pasta do
projeto. A execução é independente da API de coleta. A chamada de dublagem usa
o plano local e a API REST de síntese de voz. No F0, trate uma resposta HTTP 429
como uma falha a conferir antes de tentar novamente. Cada trecho é uma requisição.

[Referência da API REST do Azure Speech](https://learn.microsoft.com/pt-br/azure/ai-services/speech-service/rest-text-to-speech)
