# GTA Viral Collector

API interna em Python/FastAPI para consultar os vídeos públicos mais visualizados
de perfis do YouTube, TikTok e Instagram, com coleta agendada e download automático
para os bots. Sem interface ou banco de dados. Toda coleta usa HTTP real; falhas nunca geram vídeos
de demonstração.

Para instalar do zero com auxílio de Codex ou Claude, conectar o OpenBot,
configurar Azure e testar por Telegram ou por perfis, siga o
[guia completo de instalação](docs/guia-instalacao.md).

## Executar localmente

Requer Python 3.11 ou superior. No PowerShell, na raiz do projeto:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
# Preencha as credenciais no arquivo .env.
.venv\Scripts\python.exe -m uvicorn gta_viral_collector.main:app --host 127.0.0.1 --port 8000
```

Linux/macOS: substitua `.venv\Scripts\python.exe` por `.venv/bin/python` e use
`cp .env.example .env`. Para instalar apenas as dependências de execução, use
`python -m pip install -e .`.

- Swagger: <http://127.0.0.1:8000/docs>
- Esquema OpenAPI: <http://127.0.0.1:8000/openapi.json>
- Endpoint: `POST http://127.0.0.1:8000/api/videos/viral`

Credenciais ausentes não impedem a inicialização. Cada perfil sem configuração
retorna `not_configured`; os outros continuam sendo processados.

## Coleta de hora em hora e downloads

Edite [config/creators.json](config/creators.json) e preencha a lista `profiles`.
O arquivo inicial tem a lista vazia; há um exemplo preenchido em
[examples/creators.json](examples/creators.json).

Com o backend ligado, altere `automatic_downloads` para ligar ou pausar as rodadas
automáticas e use `interval` com `value` e `unit` (`minutes` ou `hours`). O backend
aplica alterações válidas sem reinício. Enquanto o JSON estiver inválido, usa a
última configuração válida carregada nesta execução e exibe o erro no status.
Os MP4s completos vão para `media/entrada/`. Seus metadados e histórico ficam em
`media/coleta/` e impedem downloads repetidos mesmo depois que os bots movem o MP4.

- `POST /api/collection/run`: iniciar coleta/download agora, HTTP 202.
- `GET /api/collection/status`: acompanhar a rodada e os erros.
- `POST /api/videos/viral`: continua sendo a consulta de metadados, sem download.

Veja [docs/coleta-automatica.md](docs/coleta-automatica.md) para configuração,
pausa, execução manual, cookies e limites operacionais.

## Baixar por link

`POST /api/videos/download` recebe `{"url":"https://youtu.be/5FYUzCuF8SM"}`
e responde HTTP 202. Consulte `GET /api/videos/download/{id}` até o resultado
ficar `ready`. O campo `path` contém o caminho absoluto do MP4 em `media/entrada/`.
Veja o [contrato da API](docs/coleta-automatica.md#baixar-um-vídeo-por-link)
e o [prompt do bot do Telegram](docs/bots/telegram.md).

## Requisição

```json
{
  "profiles": [
    {"platform": "youtube", "username": "RockstarGames", "days": 30, "limit": 5},
    {"platform": "tiktok", "username": "rockstargames", "days": 7, "limit": 10},
    {"platform": "instagram", "username": "rockstargames", "days": 14, "limit": 5}
  ]
}
```

O arquivo [examples/request.json](examples/request.json) contém esse exemplo.
Envie-o no PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/videos/viral `
  -ContentType application/json -Body (Get-Content examples/request.json -Raw) |
  ConvertTo-Json -Depth 20
```

Ou com curl:

```sh
curl -X POST http://127.0.0.1:8000/api/videos/viral \
  -H "Content-Type: application/json" --data-binary @examples/request.json
```

`platform`, `username` e `days` são obrigatórios por perfil. `limit` é opcional
(padrão 10, entre 1 e 1000). Aceita de 1 a 100 perfis; `days` vai de 1 a 36500.
Use o username com ou sem `@`, nunca a URL. No YouTube, também aceita ID `UC...`
de 24 caracteres. O nome do projeto não impõe filtro de assunto GTA.

## Resposta e ranking

O HTTP 200 contém `collected_at`, `complete` e `profiles`, na ordem dos perfis
enviados. Cada perfil contém:

| Campo | Significado |
| --- | --- |
| `platform`, `username`, `days`, `limit` | Parâmetros normalizados |
| `since`, `until` | Janela inclusiva em UTC, fixada no início da requisição |
| `status` | `complete`, `partial` ou `error` |
| `complete` | Coleta concluída sem perda conhecida |
| `pages_fetched` | Páginas coletadas e interpretadas |
| `matched_videos` | Vídeos únicos no período antes de aplicar `limit` |
| `videos` | Ranking por perfil, limitado ao número solicitado |
| `errors` | Lista de objetos `{code, message}` |
| `warnings` | Limitações e observações da fonte |

Cada vídeo retorna `id`, `platform`, `username`, `title`, `url`, `views`, `likes`,
`comments`, `published_at`, `thumbnail`, `language` e `language_source`.
Título, thumbnail e métricas indisponíveis são `null`, sem inventar valores.
URL aponta para a publicação, não para um arquivo para download.

Ordenação: views decrescentes; em empate, inglês primeiro, depois publicação mais
recente e ID. Vídeos sem views ficam ao final e tornam o ranking parcial. Inglês
não exclui outros idiomas nem ultrapassa vídeos com mais views.

Idioma: metadado do vídeo fornecido pela fonte tem prioridade. Na ausência dele,
o `langdetect` estima a partir do título/legenda, com semente fixa e limiar de
confiança de 90%. Texto com menos de 25 letras após remover URLs, hashtags e
menções resulta em `unknown`. `language_source` é `provider`, `text` ou `unknown`.
A estimativa textual não analisa o áudio e pode divergir do idioma falado.

### Completude e erros

- `complete`: o feed paginado do provedor foi esgotado sem erro conhecido.
- `partial`: houve alguma página válida, mas a coleta não terminou, contém
  registros inválidos, views ausentes ou o provedor declarou cobertura parcial.
- `error`: nenhuma página válida foi obtida. `videos` fica vazio.

`complete` global só é `true` quando todos os perfis estão completos. Um feed
vazio válido pode estar completo. Atingir `limit` não interrompe a coleta: a API
ordena todos os candidatos coletados e só depois seleciona os melhores.

Para evitar perder vídeos em feeds com posts fixados ou ordem não garantida,
a API percorre as páginas até o final do feed ou `MAX_PAGES_PER_PROFILE` e filtra
a janela localmente. O provedor HTTP também recebe `since`/`until` para poder
restringir a consulta na origem. Canais com histórico longo podem atingir o
limite de páginas mesmo em janelas curtas; nesse caso o ranking é parcial.
Essa estratégia privilegia correção e pode consumir mais chamadas/créditos.
Não há retentativas automáticas; um timeout encerra a coleta apenas desse perfil.

Cursores repetidos, cursores ausentes com `has_more`, quota, HTTP 429, HTTP 4xx/5xx,
timeout e JSON inválido aparecem em `errors`, preservando os vídeos válidos já
coletados. Páginas vazias com continuação não encerram a paginação. Vídeos são
deduplicados por ID dentro de cada perfil. Publicações futuras são excluídas.

Códigos principais: `not_configured`, `profile_not_found`, `private_profile`,
`provider_unauthorized`, `provider_forbidden`, `rate_limited`, `quota_exceeded`,
`provider_timeout`, `provider_unavailable`, `provider_error`,
`invalid_provider_response`, `invalid_video`, `provider_partial`, `missing_views`,
`missing_cursor`, `pagination_loop`, `page_limit_reached` e `collection_error`.
Corpo de requisição inválido retorna HTTP 422 antes da coleta.

Completude refere-se ao feed exposto pelo provedor, não a uma garantia de que a
plataforma expõe todos os seus vídeos. Estatísticas podem mudar durante a consulta;
`collected_at` fixa a janela, não representa um snapshot atômico.

## Provedores e configuração

Configuração carregada do `.env` na raiz ou das variáveis do processo, que têm
prioridade. Reinicie a aplicação após alterar as variáveis.

### YouTube Data API v3

Preencha `YOUTUBE_API_KEY` com uma chave de projeto Google Cloud com YouTube Data
API v3 habilitada. O adaptador resolve o canal via `channels.list` (`forHandle`
ou `id`), pagina a playlist de uploads com `playlistItems.list` e busca detalhes
e estatísticas em lotes de até 50 usando `videos.list`. Apenas
`status.privacyStatus=public` é aceito. Inclui Shorts e vídeos públicos presentes
nos uploads; vídeos privados/removidos não expostos pela API não são retornados.
Likes ou comentários desabilitados/ocultos permanecem `null`.

Documentação oficial: [uploads e estatísticas](https://developers.google.com/youtube/v3/guides/implementation/videos),
[channels.list](https://developers.google.com/youtube/v3/docs/channels/list),
[playlistItems.list](https://developers.google.com/youtube/v3/docs/playlistItems/list),
[videos.list](https://developers.google.com/youtube/v3/docs/videos/list).

### TikTok e Instagram com ScrapeCreators

Padrão: `TIKTOK_PROVIDER=scrapecreators` e `INSTAGRAM_PROVIDER=scrapecreators`.
Preencha `SCRAPECREATORS_API_KEY`. Chaves opcionais `TIKTOK_API_KEY` e
`INSTAGRAM_API_KEY` têm prioridade sobre a chave compartilhada na respectiva
plataforma. Autenticação enviada no cabeçalho `x-api-key`.

- TikTok: `GET /v3/tiktok/profile/videos`, com `handle`, `sort_by=latest`,
  `include_pinned=true` e paginação `max_cursor`/`has_more`. Lê `aweme_list`;
  mapeia `statistics.play_count`, `digg_count` e `comment_count`. Ignora slideshows.
- Instagram: `GET /v2/instagram/user/posts`, paginação `next_max_id` e
  `more_available`. Filtra `media_type=2`, incluindo vídeos/Reels do feed;
  ignora fotos e carrosséis sem métrica de vídeo individual. Usa a legenda como
  título e `play_count` como views. Perfis declarados privados retornam erro.

O TikTok pode omitir posts mesmo com paginação esgotada. No Instagram, as métricas
podem ser imprecisas e não incluem reproduções do Facebook. Essas limitações são
expostas em `warnings`. Publicações inacessíveis à fonte não podem ser recuperadas
pela API. Não há mudança automática de provedor nem fallback para dados locais.

Contratos consultados: [TikTok](https://docs.scrapecreators.com/v3/tiktok/profile/videos/),
[Instagram Posts](https://docs.scrapecreators.com/v2/instagram/user/posts/).

### Outro provedor HTTP configurável

Selecione `TIKTOK_PROVIDER=http` ou `INSTAGRAM_PROVIDER=http` e configure a
respectiva `*_API_URL`. O endpoint configurado deve implementar o contrato
normalizado abaixo, diretamente ou através de um gateway seu. Apontar para uma
API de formato diferente exige adaptar o mapeamento; não há adivinhação de campos.

Variáveis de autenticação: `*_API_KEY`, `*_API_KEY_HEADER` (padrão
`Authorization`) e `*_API_KEY_PREFIX` (padrão `"Bearer "`, incluindo o espaço).
Para `x-api-key`, defina o nome do cabeçalho e prefixo vazio. Chave é opcional
quando o endpoint não requer autenticação.

O adaptador faz GET na URL configurada com os parâmetros `platform`, `username`,
`since`, `until`, `page_size=50` e, a partir da segunda página, `cursor`.
Não envia o limite final, que não representa o tamanho total da coleta.

O provedor deve retornar este **contrato de integração**, com dados reais:

```json
{
  "items": [
    {
      "id": "id-real-do-video",
      "title": null,
      "url": "https://www.instagram.com/p/shortcode-real/",
      "views": null,
      "likes": null,
      "comments": null,
      "published_at": "2026-11-15T12:00:00Z",
      "thumbnail": null,
      "language": null,
      "is_public": true
    }
  ],
  "has_more": false,
  "next_cursor": null,
  "complete": true
}
```

`items`, `has_more`, ID, URL, data com fuso e `is_public` são obrigatórios.
`next_cursor` é obrigatório quando `has_more=true`. `complete` é opcional
(padrão `true`); use `false` quando o provedor souber de alguma truncagem.
`is_public=false` é descartado. `items=[]` com `has_more=false` representa um
feed esgotado. JSON sem o contrato esperado retorna erro, nunca sucesso vazio.

### Variáveis operacionais

| Variável | Padrão | Efeito |
| --- | --- | --- |
| `REQUEST_TIMEOUT_SECONDS` | 30 | Timeout HTTP por operação |
| `MAX_PAGES_PER_PROFILE` | 100 | Limite de páginas por perfil, com resposta parcial ao atingir |
| `MAX_CONCURRENT_PROFILES` | 4 | Perfis simultâneos em cada requisição |
| `YOUTUBE_API_BASE_URL` | `https://www.googleapis.com/youtube/v3` | Base do YouTube |
| `SCRAPECREATORS_BASE_URL` | `https://api.scrapecreators.com` | Base do ScrapeCreators |

## Estrutura e verificação

```text
gta_viral_collector/
  main.py                  # FastAPI, lifespan do cliente httpx e endpoint
  config.py                # Variáveis de ambiente
  models.py                # Contratos de entrada e saída
  language.py              # Estimativa de idioma
  service.py               # Paginação, datas, ranking e erros por perfil
  adapters/
    base.py                # Interface, páginas e erros HTTP
    youtube.py             # YouTube Data API v3
    tiktok.py              # TikTok
    instagram.py           # Instagram
    http_provider.py       # Contrato HTTP alternativo
tests/                     # Testes com transporte HTTP controlado
examples/request.json
```

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
```

Os testes interceptam apenas as chamadas externas com `httpx.MockTransport` e
exercitam endpoint, adaptadores e ranking reais. Não exigem credenciais nem
consomem quota. Validar uma coleta ao vivo exige configurar suas chaves; o
aplicativo não contém dados de teste ou modo de simulação em execução.

## Ferramentas locais de vídeo

Para edição, OCR e transcrição com análise pelo Codex, consulte
[docs/media-tools.md](docs/media-tools.md). Repositórios de referência em `repos/`.
