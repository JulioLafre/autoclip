# Coleta automática e entrada dos bots

O backend pode consultar os perfis cadastrados e baixar os vídeos públicos
retornados pelo ranking. Requer backend/PC ligados e um único worker Uvicorn.
Não foi criada uma tarefa do Windows; ao encerrar a API, o agendamento para.

## Cadastrar perfis

Edite `config/creators.json` para cadastrar seus criadores e definir a frequência.

```json
{
  "enabled": true,
  "automatic_downloads": true,
  "interval": {"value": 1, "unit": "hours"},
  "run_on_startup": true,
  "profiles": [
    {"enabled": true, "platform": "youtube", "username": "ut_animations1", "days": 7, "limit": 5},
    {"enabled": true, "platform": "tiktok", "username": "SEU_CRIADOR", "days": 7, "limit": 5},
    {"enabled": true, "platform": "instagram", "username": "SEU_CRIADOR", "days": 7, "limit": 5}
  ]
}
```

Use os usernames dos criadores. `enabled: false` em um perfil o desativa.
`days` filtra pela data de publicação e `limit` seleciona os vídeos com mais
views por perfil em cada rodada. O `enabled` do perfil é opcional e vale `true`
por padrão. O `limit` padrão é 10.

- `automatic_downloads: true` liga o agendamento. `false` pausa os próximos
  downloads automáticos e permite continuar usando `POST /api/collection/run`.
- `enabled: false` na raiz pausa as rodadas automáticas e manuais.
- `"interval": {"value": 20, "unit": "minutes"}` roda a cada 20 minutos.
  Use `"unit": "hours"` para informar o intervalo em horas. `value` deve ser um
  número inteiro positivo e o intervalo máximo é de 365 dias.
- Cadastros antigos aceitam `interval_minutes`. Quando `interval` está presente,
  ele tem prioridade. O padrão é uma hora.

O JSON é relido a cada 5 segundos por padrão. Uma rodada em execução termina com
os perfis que carregou ao começar. A próxima usa o cadastro atualizado. Se o JSON
estiver incompleto, inválido ou inacessível, as rodadas automáticas continuam com
a última configuração válida carregada desde que o backend iniciou. O status
mostra `config_error` e `using_last_valid_config`. Assim que uma versão válida é
salva, ela entra em vigor e o erro desaparece. Se o backend iniciar sem ter lido
uma configuração válida, aguarda a correção do arquivo. Uma execução manual
solicitada com o JSON inválido retorna HTTP 422.

Ao cadastrar os primeiros perfis ou reativar a coleta:

- `run_on_startup=true`: faz a primeira coleta logo, depois espera o intervalo.
- `run_on_startup=false`: espera o primeiro intervalo antes de coletar.

Reiniciar o backend reinicia esse relógio. Execução manual também redefine o
próximo horário. O intervalo é contado do início da última tentativa; uma coleta
longa não sobrepõe outra. Não é um disparo fixo em toda virada de hora.

## Credenciais e dependências

Mantenha as credenciais já existentes no `.env`: `YOUTUBE_API_KEY` para YouTube e
as chaves dos provedores TikTok/Instagram. O downloader não substitui o provedor
de descoberta. Se a chave de descoberta falhar, aquele perfil terá erro e nenhum
vídeo fictício será criado. Resultados reais de perfis/páginas bem-sucedidos ainda
podem ser baixados quando a coleta for parcial.

Os downloads usam `yt-dlp[default]`, instalado no mesmo Python da API, e FFmpeg/
ffprobe. A instalação detecta o FFmpeg local em `.tools/ffmpeg`, ou usa o PATH/
`FFMPEG_DIR`. Usa Node.js quando disponível para os desafios JavaScript do YouTube.
Pacote EJS do yt-dlp incluído nas dependências padrão.

Sites podem exigir cookies, impor limites ou indisponibilizar vídeos públicos.
Essas falhas são retornadas, sem marcar download como concluído. Se necessário,
configure `DOWNLOAD_COOKIES_FILE` no `.env` apontando para seu arquivo de cookies
no formato Netscape. Não é feita leitura automática das contas do navegador.

Para atualizar o downloader após mudanças dos sites:

```powershell
.venv\Scripts\python.exe -m pip install --upgrade "yt-dlp[default]"
```

## Executar e acompanhar no Swagger

Inicie a API com o comando habitual:

```powershell
.venv\Scripts\python.exe -m uvicorn gta_viral_collector.main:app --host 127.0.0.1 --port 8000
```

Em `http://127.0.0.1:8000/docs`, use os endpoints da categoria `collection`:

- `POST /api/collection/run`: lê o JSON, inicia trabalho em segundo plano e
  responde HTTP 202. JSON inválido retorna 422; lista vazia, cadastro pausado ou
  tarefa já em andamento retorna 409. Não precisa corpo de requisição.
- `GET /api/collection/status` mostra `running`, `status`, `next_run_at`, o
  `interval` em vigor, `automatic_downloads` conforme o JSON, `config_error`,
  `using_last_valid_config`, os caminhos dos arquivos e `last_report`.

Também pode chamar pelo PowerShell:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/collection/run
Invoke-RestMethod http://127.0.0.1:8000/api/collection/status | ConvertTo-Json -Depth 30
```

`last_report` contém `downloaded`, `skipped`, `failed`, `downloads` por vídeo e
`profiles` com os erros originais de descoberta. `collection_complete` se refere
à coleta do feed. `completed` significa coleta completa sem falhas de download;
`partial` indica coleta incompleta ou falha em algum download. Lista de resultados
vazia pode ser válida. `no_profiles` significa que não há perfis ativos.

O POST `/api/videos/viral` mantém o comportamento anterior: consulta metadados,
sem criar arquivos.

## Baixar um vídeo por link

Use `POST /api/videos/download` no Swagger ou pelo terminal. Aceita vídeos e
Shorts do YouTube, Reels e posts de vídeo do Instagram, e vídeos do TikTok.
Links curtos reconhecidos precisam redirecionar para um vídeo da mesma plataforma.
Esse endpoint funciona independentemente do cadastro de criadores e das chaves
dos provedores de descoberta. Ele usa as configurações de download do `.env`.

```powershell
$api = 'http://127.0.0.1:8000'
$body = @{ url = 'https://youtu.be/5FYUzCuF8SM' } | ConvertTo-Json
$job = Invoke-RestMethod -Method Post -Uri "$api/api/videos/download" `
    -ContentType 'application/json' -Body $body
do {
    Start-Sleep -Seconds 2
    $result = Invoke-RestMethod -Uri "$api$($job.status_url)"
} while ($result.status -in 'queued', 'downloading')
$result | ConvertTo-Json
```

O POST responde HTTP 202 com `id` e `status_url`. O GET retorna o estado do trabalho.

| `status` | Ação do bot |
| --- | --- |
| `queued` | Consulte de novo. `queue_reason` indica `resolving_link` (abrindo o link curto) ou `waiting_for_slot` (aguardando a vez de baixar). |
| `downloading` | A API está obtendo ou validando o arquivo. Continue consultando. |
| `ready` | Use o `path` absoluto do MP4 e o `work_id` para chamar o Analista. Se `reused` for `true`, a API usou o arquivo já baixado. |
| `failed` | Informe o campo `error`. |
| `already_processed` | O histórico registra o download, mas o MP4 já saiu da pasta de entrada. Informe o `work_id` para localizar o trabalho. |

Perfis, playlists e URLs incompatíveis retornam HTTP 422. Se os 32 lugares da
fila estiverem ocupados, o POST retorna HTTP 429. A API retém até 256 status
em memória. Após reinício ou HTTP 404, reenvie o link. O histórico em disco
continua evitando downloads repetidos.

Quando a coleta automática está baixando um vídeo, o link avulso já na fila
pode entrar antes do próximo vídeo da rodada. Consultar perfis acontece fora
da fila de downloads.

Se OpenBot rodar na mesma máquina e conseguir acessar o backend e a pasta do
projeto, use o [prompt do bot do Telegram](bots/telegram.md). Ele passa o vídeo
pronto para o Analista e o fluxo continua até o Gerente do Canal.

## Arquivos e duplicatas

```text
media/
  entrada/                  # somente MP4s completos para o Analista
    youtube_ID_HASH.mp4
  coleta/
    history.json            # plataforma+ID já baixados
    last-run.json           # relatório da última rodada
    collection.lock         # lock entre processos
    metadata/               # origem, views, idioma, data e SHA256 por vídeo
    staging/                # downloads temporários, não consumir nos bots
    ready/                  # MP4s validados aguardando publicação recuperável
```

O vídeo é baixado e convertido para contêiner MP4 em staging. Só é publicado
em entrada depois de ffprobe confirmar um stream de vídeo. A mesclagem/remux
não significa necessariamente codec H.264; a edição posterior faz a exportação.
Não há melhoria artificial da resolução ou remoção de legendas nesta etapa.

O histórico usa plataforma+ID, e não o nome do perfil ou título. Mover/renomear
um arquivo após processá-lo não faz a API baixá-lo novamente. Arquivos parciais
e falhas não entram no histórico. Downloads são sequenciais, com limite de tempo
de 300 segundos por vídeo por padrão; falhas podem ser tentadas na próxima rodada.

Antes de publicar, um registro `pending` é persistido no histórico e o MP4 fica
em `ready/`. Depois da publicação, o registro vira `downloaded`. Se o backend
parar nessa transição, a próxima rodada reconcilia o registro sem baixar de novo,
mesmo quando o bot já moveu o vídeo. Não remova manualmente arquivos de `ready/`:
eles fazem parte desse controle de recuperação. Fragmentos ausentes interrompem
o download; um MP4 parcialmente obtido não é aceito como sucesso.

`limit` é aplicado ao ranking antes da deduplicação: se os 5 mais vistos já foram
baixados, uma rodada com `limit=5` pode não gerar arquivo novo. Aumente o limite/
janela conforme sua necessidade. Não há download de todo o histórico por padrão.

Não apague o histórico para uma nova rodada. Para baixar novamente um vídeo
intencionalmente, pare a coleta e remova somente a entrada correspondente em
`history.json`, além de decidir o que fazer com o arquivo anterior. Históricos
inválidos são preservados e bloqueiam a rodada, evitando duplicação silenciosa.

## Variáveis opcionais

| Variável | Padrão |
| --- | --- |
| `COLLECTION_ENABLED` | true, controla somente o scheduler; endpoint manual continua disponível |
| `CREATORS_FILE` | config/creators.json na raiz do projeto |
| `DOWNLOAD_DIR` | media/entrada |
| `COLLECTION_STATE_DIR` | media/coleta |
| `COLLECTION_POLL_SECONDS` | 5 |
| `DOWNLOAD_TIMEOUT_SECONDS` | 300 |
| `FFMPEG_DIR` | detectar ferramentas instaladas |
| `DOWNLOAD_COOKIES_FILE` | não definido |

Alterações do JSON não exigem reinício. Alterações das variáveis de ambiente
exigem reiniciar o backend. Use um worker; o lock evita sobreposição entre
processos, mas múltiplos schedulers não são necessários neste uso local.
