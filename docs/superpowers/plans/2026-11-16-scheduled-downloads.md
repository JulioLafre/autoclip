# Coleta agendada e downloads

**Goal:** Consultar perfis em JSON de hora em hora e salvar vídeos em media/entrada.
**Architecture:** Scheduler no lifespan FastAPI, coletor existente, subprocessos
yt-dlp e FFmpeg, estado JSON persistido sem banco. Configuração relida em runtime.
**Tech Stack:** asyncio, Pydantic, yt-dlp, filelock, FastAPI.

## Decisões

- `config/creators.json`: enabled, interval_minutes=60, run_on_startup e profiles.
- Lista inicialmente vazia para o usuário cadastrar os criadores desejados.
- Cada perfil permite enabled, platform, username, days e limit.
- `POST /api/collection/run` inicia trabalho e responde 202; `GET /api/collection/status`
  informa progresso e último relatório. O POST /api/videos/viral mantém seu contrato.
- Download dos candidatos retornados pelo ranking; MP4 só aparece em entrada após
  download finalizado e validado por ffprobe. Áudio e vídeo mesclados pelo FFmpeg.
- Histórico por plataforma+ID evita repetição inclusive se o bot mover o arquivo.
- Falhas não viram sucesso, não entram no histórico e podem ser tentadas na rodada seguinte.
- Relatórios e metadados ficam fora de entrada; lock impede dois workers concorrentes.
- O agendamento funciona com backend/PC ligados; não há tarefa Windows ou serviço novo.

## Entregas

- [x] Testes de configuração, deduplicação, downloads reais locais e falhas.
- [x] Downloader com timeout, validação, staging e publicação atômica.
- [x] Scheduler e controle FastAPI, JSON pronto para cadastro.
- [x] Documentação, dependências e reinício com verificação de status.

## Evidências

- 41 testes passaram; 1 módulo de mídia ignorado no ambiente sem OpenCV.
- Ruff aprovado. yt-dlp executado contra HTTP local real, com FFmpeg/ffprobe.
- Revisão independente: ausência de fragmentos agora aborta o download; journal
  pending/ready protege contra duplicatas na transição entre publicação e histórico.
- Testes reproduziram ambos os achados antes das correções e passaram depois.
- Backend reiniciado na porta 8000: status HTTP 200, scheduler ativo/no_profiles,
  Swagger com novos endpoints e execução manual vazia HTTP 409.
- Nenhuma coleta autenticada em redes sociais executada; cadastro inicial vazio.
