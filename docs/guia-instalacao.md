# Guia de instalação do GTA Viral Collector e do ClipshortsBr

Este guia leva do projeto recém-copiado ao primeiro vídeo editado e embalado para
publicação. O caminho principal usa Windows x64 e PowerShell. Execute a API e
os agentes na mesma máquina, com acesso à mesma pasta. O backend também roda em
outros sistemas, mas os scripts de ativação de mídia e os prompts atuais foram
preparados para Windows.

## 1. Começar com Codex ou Claude

Abra a raiz do projeto no assistente e envie esta mensagem:

```text
Leia docs/guia-instalacao.md inteiro e me acompanhe do início ao primeiro vídeo
pronto. Primeiro descubra minha pasta do projeto e me pergunte se quero receber
links por Telegram, usar coleta automática por perfis ou usar os dois. Confira o
que já está instalado. Execute o que puder nessa máquina e me guie nas etapas que
exigem uma ação minha. Trabalhe em um bloco do guia por vez, pare nos pontos de
checagem e espere minha confirmação antes de seguir. Não peça chaves no chat.
No fim, teste com um vídeo real por cada caminho que eu escolher, até o pacote
do Gerente do Canal. Não publique durante o teste.
```

**Ao assistente que está conduzindo a instalação.** Descubra o caminho absoluto
da raiz e se o seu terminal roda no computador que vai executar o OpenBot. Se
estiver em um ambiente remoto, entregue os comandos locais de um bloco por vez e
peça apenas o resultado necessário para validar aquele bloco. Preserve arquivos
existentes, especialmente `.env`, `config/creators.json` e `media/`. Para login,
permissões de conta, escolha de plano ou pareamento, indique a tela e espere a
pessoa concluir. Peça confirmação de que a credencial foi salva no local correto,
sem pedir o valor. Registre cada etapa como verificada, pendente ou pulada.

Pergunte antes de instalar integrações:

> Você quer enviar links pelo Telegram, baixar automaticamente por perfis ou
> configurar os dois? Quer habilitar dublagem Azure agora? Pretende publicar pelo
> Postiz ou só receber o pacote final para postar manualmente?

| Escolha | O que configurar |
| --- | --- |
| Telegram | OpenBot Desktop, conta OpenBot e integração Telegram. A API recebe a URL de um vídeo por vez. |
| Coleta automática | Credencial de descoberta da plataforma escolhida e `config/creators.json`. A API procura novos vídeos por perfil. |
| Os dois | Use a mesma API, o mesmo `media/entrada/` e o mesmo histórico. Escolha dois vídeos diferentes para validar os dois caminhos. |
| Dublagem | Um recurso Azure Speech para sintetizar as falas traduzidas. OCR e Whisper executam na máquina. |
| Publicação pelo Gerente | Postiz com o canal conectado. É opcional para gerar e testar o pacote. |

**Pausa 1.** Combine o modo de entrada, a máquina e quais contas serão
configuradas. Mantenha as pausas deste guia no chat de instalação. Os agentes de
produção seguem o fluxo até o Gerente sem pedir aprovação a cada edição.

## 2. Instalar o backend e as ferramentas locais

1. Obtenha o projeto completo e abra PowerShell na raiz, onde estão
   `pyproject.toml`, `.env.example`, `config/`, `scripts/` e `docs/`. Ao compartilhar
   por Git, confira que esses arquivos foram incluídos. Cada instalação tem seus
   próprios ambientes, modelos, mídia e `.env`.
2. Instale [Python 3.12 x64](https://www.python.org/downloads/windows/) e confira
   `py -3.12 --version`. Instale [Git para Windows](https://git-scm.com/install/windows)
   se for clonar o projeto ou usar Claude Code. Para downloads do YouTube, instale
   [Node.js LTS](https://nodejs.org/en/download) versão 22 ou superior. No novo
   terminal, confira `node --version`. O downloader usa Node quando o encontra no
   `PATH`. Veja os [requisitos do yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/ejs).
3. Crie os ambientes que estiverem faltando. O backend e as duas ferramentas
   de mídia usam Pythons separados. PaddleOCR e faster-whisper podem ter conflito
   de DLL quando importados no mesmo processo em Windows.

```powershell
if (-not (Test-Path .venv\Scripts\python.exe)) { py -3.12 -m venv .venv }
.venv\Scripts\python.exe -m pip install -e '.[dev]'
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
New-Item -ItemType Directory -Force .tools, media/entrada, media/revisar | Out-Null
if (-not (Test-Path .tools\ocr-venv\Scripts\python.exe)) {
    py -3.12 -m venv .tools/ocr-venv
}
if (-not (Test-Path .tools\whisper-venv\Scripts\python.exe)) {
    py -3.12 -m venv .tools/whisper-venv
}
.tools\ocr-venv\Scripts\python.exe -m pip install -r requirements-ocr.lock.txt
.tools\whisper-venv\Scripts\python.exe -m pip install -r requirements-whisper.lock.txt
```

4. Na [página de downloads do FFmpeg](https://ffmpeg.org/download.html), abra
   **Windows EXE Files** e escolha um build x64 em ZIP. Extraia em `.tools/ffmpeg`,
   de modo que `ffmpeg.exe` e `ffprobe.exe` fiquem na mesma subpasta `bin`. O
   script de ativação procura o executável nessa árvore. Na raiz, rode:

```powershell
. .\scripts\activate-media.ps1
ffmpeg -version
ffprobe -version
.venv\Scripts\python.exe -m yt_dlp --version
& $env:CLIPSHORTS_OCR_PYTHON -c "import cv2, paddle, paddleocr; print('OCR e OpenCV OK')"
& $env:CLIPSHORTS_WHISPER_PYTHON -c "import os; from faster_whisper.utils import download_model; download_model('base', output_dir=os.environ['CLIPSHORTS_WHISPER_MODEL'])"
& $env:CLIPSHORTS_WHISPER_PYTHON -c "import os; from faster_whisper import WhisperModel; WhisperModel(os.environ['CLIPSHORTS_WHISPER_MODEL'], device='cpu', compute_type='int8', local_files_only=True); print('Whisper OK')"
```

O primeiro uso dos modelos de OCR baixa os pesos. Use o exemplo de
[ferramentas de mídia](media-tools.md) com um frame real para confirmar que há
inferência. Se `faster-whisper` falhar ao abrir o MP4 com PyAV, extraia PCM mono
de 16 kHz, substituindo `video.mp4` e usando um nome de saída livre:

```powershell
ffmpeg -n -i 'media/entrada/video.mp4' -map 0:a:0 -ac 1 -ar 16000 `
  -f f32le 'media/revisar/transcricao-guia.f32'
```

No Python do Whisper, carregue esse arquivo com
`numpy.fromfile('media/revisar/transcricao-guia.f32', dtype='<f4')` e passe o
array a `model.transcribe(...)`. O script de inpainting usa o Python do OCR
e tem um [guia de prévia e validação](inpainting.md).
Os clones listados em [repos/README.md](../repos/README.md) são opcionais para
consulta. Os arquivos de dependências já instalam os pacotes usados em execução.

**Pausa 2.** Confirme que FFmpeg, ffprobe, yt-dlp, OCR e Whisper funcionam na
máquina do OpenBot. Resolva erro de instalação antes de criar os agentes.

## 3. Configurar credenciais e subir a API

### Descoberta por perfis

Configure somente as plataformas que a pessoa deseja pesquisar. Os downloads
diretos por link usam yt-dlp e dispensam as chaves de descoberta abaixo.

- **YouTube.** Crie ou selecione um projeto no Google Cloud Console. Em
  **APIs e serviços → Biblioteca**, habilite **YouTube Data API v3**. Em
  **Credenciais → Criar credenciais → Chave de API**, gere uma chave e salve como
  `YOUTUBE_API_KEY` no `.env` da raiz. Use uma chave de leitura de dados públicos.
  [Documentação do Google](https://developers.google.com/youtube/data/guides/authentication)
- **TikTok e Instagram.** Crie uma conta no ScrapeCreators, gere a chave no painel
  e salve em `SCRAPECREATORS_API_KEY`. Mantenha `TIKTOK_PROVIDER=scrapecreators` e
  `INSTAGRAM_PROVIDER=scrapecreators`. `TIKTOK_API_KEY` e `INSTAGRAM_API_KEY` podem
  sobrescrever a chave compartilhada para cada plataforma. Consulte os créditos
  antes de habilitar muitas contas. Outro provedor pode usar o adaptador HTTP
  conforme o [contrato no README](../README.md#outro-provedor-http-configurável).
  [Documentação do ScrapeCreators](https://docs.scrapecreators.com/)

### Dublagem com Azure Speech

1. Entre no [Azure Portal](https://portal.azure.com/) com uma conta que tenha
   acesso à assinatura. Se houver erro `AADSTS50020`, selecione o diretório da
   assinatura na troca de diretórios e confirme a conta que tem acesso a ele.
   [Diagnóstico da Microsoft](https://learn.microsoft.com/en-us/troubleshoot/entra/entra-id/app-integration/error-code-aadsts50020-user-account-identity-provider-does-not-exist)
2. Procure **Serviços de fala** e crie um recurso **Speech**. Selecione assinatura,
   grupo de recursos, região e nome. Use **Free F0** quando o portal oferecer
   essa opção para a assinatura. Pode escolher **Brazil South** se disponível
   para o recurso, ou **East US** conforme a disponibilidade. Confira a oferta
   e as cotas no portal antes de criar um recurso pago. A região serve para
   localizar o recurso, enquanto `pt-BR` é definido pela voz.
3. Depois da implantação, abra **Ir para o recurso → Chaves e Ponto de Extremidade**.
   No `.env`, coloque uma das chaves em `AZURE_SPEECH_KEY` e o código da região
   **do próprio recurso** em `AZURE_SPEECH_REGION`, por exemplo `brazilsouth` ou
   `eastus`. Salve sem mostrar a chave no chat ou nos prompts.
4. Gere uma prévia. Escolha um novo nome se o WAV já existir.

```powershell
.venv\Scripts\python.exe scripts/gerar-dublagem.py `
  --plan examples/plano-dublagem.json `
  --output media/revisar/dublagem-guia.wav
ffprobe -v error -show_entries format=duration media/revisar/dublagem-guia.wav
```

O WAV de exemplo dura 6 segundos. Escute-o e confira a voz em pt-BR. No fluxo
real, o Analista transcreve e traduz cada fala com tempos, e o Editor executa o
mesmo script a partir do plano. A integração com o OpenBot é a chamada desse
comando local pelo Editor. O script envia ao Azure o texto traduzido de cada
trecho. Veja [Dublagem](dublagem.md), [criação do recurso Microsoft](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/get-started-text-to-speech?tabs=windowsinstall)
e [regiões do Speech](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/regions).

### Ligar o backend

Para testar Telegram primeiro, deixe `enabled: false` na raiz de
`config/creators.json`. Para preparar coleta por perfis sem disparar imediatamente,
use `enabled: true` e `automatic_downloads: false`. Edite as propriedades
existentes, conservando os perfis cadastrados. Na raiz do projeto, abra um
terminal local e deixe o Uvicorn rodando:

```powershell
.venv\Scripts\python.exe -m uvicorn gta_viral_collector.main:app --host 127.0.0.1 --port 8000
```

Em outro terminal, confirme que o Swagger abre em <http://127.0.0.1:8000/docs> e
que `Invoke-RestMethod http://127.0.0.1:8000/api/collection/status` responde. Use
um único worker. Para encerrar, pressione `Ctrl+C` no terminal do Uvicorn.
Reinicie após editar o `.env` do backend. Alterações no JSON de criadores entram
em vigor com o backend ligado, normalmente em cerca de 5 segundos.

**Pausa 3.** Espere a pessoa confirmar as credenciais que escolheu, a resposta
da API e o WAV se habilitou dublagem. Se o teste de voz falhar, registre o erro
sem imprimir as credenciais e corrija a chave, região ou quota antes do teste
de dublagem de ponta a ponta.

## 4. Instalar o OpenBot e cadastrar os agentes

1. Baixe o instalador **Windows x64** da edição **Nightly Labs OpenBot Desktop**
   nas [releases oficiais](https://github.com/nightly-labs/openbot/releases). Abra
   o OpenBot depois de instalar. Essa edição fornece a integração Telegram
   descrita na próxima etapa.
2. Escolha **Codex** ou **Claude Code** e instale o CLI do provedor no mesmo
   Windows. Para Codex, use `npm install -g @openai/codex` se já tiver Node.js,
   ou siga a opção Windows da documentação. Para Claude Code, uma opção é
   `winget install Anthropic.ClaudeCode`. Confirme `codex --version` ou
   `claude --version` em um novo PowerShell. Abra `codex` ou `claude` no terminal,
   conclua o login e reabra o OpenBot para que ele encontre o provedor. Abra
   uma conversa e peça uma resposta curta para verificar o modelo.
   [Codex CLI](https://developers.openai.com/codex/cli)
   · [Instalação do Claude Code](https://code.claude.com/docs/en/setup)
   · [Provedores do OpenBot Desktop](https://github.com/nightly-labs/openbot#agent-setup)
3. Crie três agentes com nomes distintos. Nas configurações de cada agente,
   copie apenas o texto do arquivo correspondente para as instruções permanentes.
   Substitua o caminho do autor na primeira linha pelo caminho absoluto desta
   instalação. Use o mesmo caminho em todos os agentes. Se alterar os nomes,
   ajuste os destinatários nos prompts. Conte os caracteres depois de editar
   se a sua edição limitar o campo a 2.000. Esses prompts já incluem o fluxo
   em dimensões originais, sem moldura, e a chamada opcional ao Azure.

| Agente | Arquivo para copiar | Resultado |
| --- | --- | --- |
| ANALISTA | [docs/bots/analista.md](bots/analista.md) | Plano em `media/planos/<id>.json` com enquadramento, texto e áudio. |
| EDITOR | [docs/bots/editor.md](bots/editor.md) | MP4 verificado e relatório em `media/finalizados/`, ou bloqueio em `media/revisar/`. |
| GERENTE DO CANAL | [docs/bots/gerentedocanal.md](bots/gerentedocanal.md) | Pacote em `media/publicacao/<id>/` com thumbnail e metadados. |
| TELEGRAM, se escolhido | [docs/bots/telegram.md](bots/telegram.md) | Recebe link, consulta a API e envia o MP4 pronto ao Analista. |

4. Confirme que cada agente dispõe de terminal e consegue ler `pyproject.toml`
   a partir da pasta compartilhada do projeto. Peça a um agente para executar
   `Invoke-RestMethod http://127.0.0.1:8000/api/collection/status` e para localizar
   os destinatários via `list_agents`. Use `send_message` para os repasses.
   Se a instalação oferece `message_bot` e **Setup → Bots it can ask**, configure
   as permissões de cada par e o limite de repasses de acordo com
   [o guia dos bots](bots/README.md). Os ambientes da API e do OpenBot são separados.
5. Se o OpenBot estiver em outro computador ou em um contêiner, `127.0.0.1`
   aponta para o próprio ambiente do agente. Prefira rodar ambos no mesmo
   Windows para o teste. Uma implantação separada precisa de endereço de API
   acessível a partir do agente, arquivos compartilhados e caminhos absolutos
   que todos os agentes consigam abrir, incluindo o `path` devolvido pela API.

**Pausa 4.** Confirme os modelos, a pasta e os repasses Analista → Editor →
Gerente. Se faltar um destinatário, corrija o nome ou a permissão antes de
testar o vídeo. A política de edição e as saídas esperadas estão em
[docs/bots/politica-editorial.md](bots/politica-editorial.md).

## 5. Conectar o caminho que a pessoa escolheu

### Telegram pelo OpenBot Desktop

1. Entre na conta OpenBot e dê um nome à máquina em **Server settings**. Abra
   **Marketplace → Apps → Telegram**. Escolha conversar diretamente ou adicionar
   a integração a um grupo. Conclua o pareamento no Telegram pelo link gerado.
2. No OpenBot, escolha o modelo e adicione o **Telegram Orchestrator**. Ele
   aparece em **Integrations**. Coloque nele o [prompt de entrada](bots/telegram.md)
   com o caminho local correto. Confira que ele consegue localizar e chamar o
   Analista. Em grupo, mencione o bot ou responda a uma mensagem dele.
3. A integração nativa usa o bot do próprio OpenBot. Se a pessoa já tem um bot
   criado por `/newbot` no BotFather, conectar esse token exige um conector que
   aceite bot próprio. Verifique o que a edição instalada oferece. Este projeto
   fornece a API HTTP, que esse conector pode chamar, e o caminho recomendado
   acima usa o Orchestrator nativo. Guarde o token no conector escolhido.
   [Telegram no OpenBot](https://github.com/nightly-labs/openbot/blob/main/docs/messaging.md#connect-telegram)
   · [BotFather](https://core.telegram.org/bots/tutorial)

O bot envia `POST /api/videos/download` com `{"url":"URL_DO_VIDEO"}` e recebe
HTTP 202. Ele consulta o `status_url` até `ready` e entrega o `path` e o `work_id`
ao Analista. Em `queued`, `queue_reason` distingue resolução de link curto de
espera pelo baixador. Em `failed`, leia `error`. Veja [contrato e exemplo pelo
PowerShell](coleta-automatica.md#baixar-um-vídeo-por-link). O backend continua
acessível só na porta local para o fluxo nativo, sem webhook público na FastAPI.

### Coleta automática por perfis

Mantenha `COLLECTION_ENABLED=true` no `.env` ou use seu valor padrão. Configure
um perfil público que publicou recentemente. Para começar, use um perfil,
`limit: 1` e uma janela suficiente para encontrar pelo menos um vídeo ainda
ausente do histórico. Preserve os outros registros do usuário ao editar:

```json
{
  "enabled": true,
  "automatic_downloads": true,
  "interval": {"value": 1, "unit": "hours"},
  "run_on_startup": true,
  "profiles": [
    {"platform": "youtube", "username": "SUBSTITUA_PELO_HANDLE", "days": 14, "limit": 1}
  ]
}
```

Use `youtube`, `tiktok` ou `instagram` em `platform`. Use o handle ou ID
aceito pelo provedor no campo `username`. A frequência aceita `minutes` ou
`hours`. `run_on_startup: true` permite uma primeira coleta logo, inclusive
quando se reativa uma coleta antes pausada. Alterne os modos pelo JSON:

| `enabled` | `automatic_downloads` | Perfis |
| --- | --- | --- |
| `false` | qualquer | Pausados. Os links via Telegram continuam disponíveis. |
| `true` | `false` | Apenas rodadas disparadas manualmente em `POST /api/collection/run`. |
| `true` | `true` | Rodadas no intervalo definido. |

A coleta baixa e entrega o MP4 em `media/entrada/`. Para começar, passe o caminho
exato ao Analista. Para automatizar também essa passagem, se a edição tiver
**Routines**, cadastre uma rotina no Analista para procurar MP4s completos em
`media/entrada/`, processar um por execução com o nome do arquivo sem extensão
como ID e seguir os repasses definidos. Reuse o mesmo ID do Telegram e pule
arquivos com plano, saída, bloqueio ou pacote já registrado. Não rode o mesmo
arquivo por dois gatilhos enquanto o primeiro fluxo está em andamento. Teste a
rotina manualmente no OpenBot antes de ativar a agenda.
[Coleta e arquivos](coleta-automatica.md) · [Rotinas no OpenBot](https://github.com/nightly-labs/openbot/blob/main/docs/automation.md)

**Pausa 5.** Pergunte se a pessoa quer testar agora por Telegram, por coleta
automática ou pelos dois. Valide o caminho escolhido antes de ativar o segundo.

## 6. Rodar os testes de ponta a ponta

Use vídeos públicos que você tem permissão para baixar e editar. Escolha vídeos
curtos e ainda ausentes do histórico para este teste. Escolha um com fala clara
em inglês se quiser verificar dublagem durante a edição, além do WAV da etapa 3.

### Teste A. Vídeo vindo de coleta automática

1. Se estiver diagnosticando a descoberta, use `POST /api/videos/viral` no
   Swagger com o perfil escolhido e confira se retorna vídeos. Esse endpoint
   consulta metadados. Se estiver pronto, habilite a coleta com o JSON acima.
2. Aguarde uma rodada **agendada** com `run_on_startup: true` ou o horário em
   `next_run_at`. Consulte `GET /api/collection/status`. Anote `last_started_at`,
   `last_report.downloaded` e o `path` de um item com `status: downloaded` em
   `last_report.downloads`. Confirme que o MP4 existe. Rodada `partial` pode ter
   baixado um vídeo válido. Use `POST /api/collection/run` para diagnóstico,
   mas registre a execução como manual se esse foi o disparo usado.
3. Se não houver rotina de entrada, envie ao Analista a instrução abaixo,
   substituindo os dois marcadores pelo caminho e pelo nome do arquivo sem
   extensão. Se houver rotina, confirme que ela tomou esse trabalho.

```text
Processe <CAMINHO_ABSOLUTO_DO_MP4> como trabalho <ID_DO_ARQUIVO>.
Execute o fluxo completo até o Gerente do Canal. Preserve o quadro e o tamanho
originais. Siga a política de tradução e dublagem do projeto.
```

### Teste B. Vídeo vindo do Telegram

1. Com o backend e o OpenBot ligados, envie um link de vídeo individual ao bot
   no Telegram. Use um vídeo diferente do teste A se fizer os dois. Se estiver
   num grupo, enderece a mensagem ao bot.
2. Confira se o bot obteve o ID do download, esperou `ready` e enviou o `path`
   com `work_id` ao Analista. Consulte o `status_url` se o progresso estiver
   indefinido. HTTP 202 confirma o recebimento. A entrada só fica pronta ao
   concluir o download e a validação de vídeo.
3. Acompanhe o mesmo ID do Analista ao Gerente nas conversas do OpenBot. A
   confirmação de repasse do Telegram significa que o próximo agente foi
   acionado. A conclusão do pacote aparece no Gerente.

### Verificar a entrega de cada vídeo

- Plano em `media/planos/<id>.json` e relatório de edição com os caminhos e o
  que foi conferido por imagem, áudio e metadados.
- MP4 em `media/finalizados/<id>-clipshortsbr.mp4`. Confira dimensões, proporção,
  orientação e áudio com `ffprobe` e reproduza o início, meio e fim. Se havia
  fala em inglês confirmada e o Azure foi escolhido, confira também o encaixe
  da voz em pt-BR.
- Pacote em `media/publicacao/<id>/`, com estado `pronto_para_publicar`, caminho
  do MP4, thumbnail escolhida, título, descrição, hashtags e tags. Em `bloqueado`,
  use o motivo e as evidências para corrigir a etapa e retestar.

**Pausa 6.** Mostre os IDs, os caminhos dos MP4s e dos pacotes à pessoa. Marque
cada teste como concluído, bloqueado ou fora do modo escolhido. Confirme com a
pessoa quais modos deseja deixar ativos após os testes.

## 7. Opcional. Conectar o Postiz para publicar

O fluxo de teste termina no pacote local. Para publicar com o Gerente, abra
o Postiz, adicione a integração **YouTube** e autorize o canal correto na conta
Google. Em Postiz self-hosted, siga o guia para cadastrar as credenciais OAuth
no próprio servidor Postiz. A chave pública do YouTube usada para descoberta
pertence ao backend e tem finalidade de leitura.
[YouTube no Postiz self-hosted](https://github.com/gitroomhq/postiz-docs/blob/main/self-host/providers/youtube.mdx)

Disponibilize o Postiz ao provedor do Gerente via MCP com OAuth ou via CLI com
login/chave. Siga as instruções do fornecedor para o cliente escolhido e
confira no contexto do Gerente que ele consegue **listar as integrações** e
identificar o canal certo. Configure as credenciais no Postiz ou no ambiente da
ferramenta do Gerente. O tutorial oficial do Codex inclui as opções MCP e CLI.
[Integração Postiz com Codex](https://postiz.com/codex/youtube) · [API do Postiz](https://docs.postiz.com/public-api/introduction)

Depois de decidir postar, a pessoa pode pedir ao Gerente para publicar um ID
específico e indicar canal, visibilidade e destino. O pedido de publicação é
feito em separado, depois de conferir o pacote local.

## Problemas comuns

| Sintoma | O que conferir |
| --- | --- |
| Swagger indisponível | Terminal do Uvicorn, porta `8000`, diretório do projeto e endereço visto pelo agente. |
| Perfil com `not_configured` | O `.env` do backend, o provedor selecionado e se o servidor foi reiniciado. Para YouTube, confira se a API v3 está habilitada no mesmo projeto da chave. |
| Nenhum MP4 novo na coleta | Status e erros por perfil, janela `days`, ranking de `limit` e histórico. Se o ranking só contém vídeos já baixados, amplie `limit` ou escolha outro perfil com publicação recente. |
| Link em `queued` | Abra `status_url`. `resolving_link` indica abertura de link curto. `waiting_for_slot` indica que outro vídeo pode ocupar o baixador. Para testar só Telegram, pause os perfis pelo JSON. |
| Link falhou com login ou HTTP 403 | A plataforma recusou o download. Teste com outro vídeo público acessível. Se tiver acesso autorizado e precisar configurar cookies, use `DOWNLOAD_COOKIES_FILE` conforme o [guia de coleta](coleta-automatica.md#credenciais-e-dependências). |
| `already_processed` ou HTTP 404 no status | `already_processed` indica que o histórico tem o vídeo e o MP4 saiu da entrada. Use `work_id` para procurar as saídas. Após reinício ou expiração de um status, reenviar o link consulta o histórico existente. |
| Azure falhou | Confirme a chave e a região do mesmo recurso. HTTP 429 pede conferir quota ou capacidade. Valide novamente com o WAV de exemplo. |
| O Gerente nunca recebeu o vídeo | Confira se houve repasse para cada destinatário, se todos veem a mesma pasta e se a mensagem levou o ID e os caminhos absolutos. |
