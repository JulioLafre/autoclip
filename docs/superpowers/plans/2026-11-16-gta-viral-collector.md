# GTA Viral Collector Implementation Plan

**Goal:** Implementar o contrato solicitado em `POST /api/videos/viral`.
**Architecture:** FastAPI assíncrono, modelos Pydantic, adaptadores independentes e
serviço comum para filtrar datas, deduplicar, ordenar e limitar após a coleta.
YouTube Data API oficial; TikTok e Instagram com ScrapeCreators ou HTTP normalizado.
**Tech Stack:** Python 3.11+, FastAPI, httpx, Pydantic, pydantic-settings, langdetect.
**Spec:** Requisitos da solicitação do usuário, reproduzidos abaixo.

## Global Constraints

- Sem interface, banco, downloads, templates ou edição de vídeos.
- Dados exclusivamente dos provedores; falhas nunca produzem vídeos fictícios.
- Credenciais por ambiente, Swagger e exemplo JSON executável localmente.
- Período por perfil, vídeos públicos, estatísticas e idioma estimado.

## Decisions

- Corpo `{ "profiles": [...] }`, com plataforma, username, days e limit por perfil.
- Ranking por views decrescentes; inglês desempata. Idioma sem confiança: unknown.
- Janela inclusiva em UTC, fixada no início da requisição.
- Paginação não termina por atingir limit nem por encontrar um post antigo isolado.
- Complete significa cobertura concluída do feed do provedor; avisos expõem limitações.
- Erros de configuração, rede, quota, dados e paginação são isolados por perfil.

## Review Focus

- Vídeo mais popular apenas na segunda página; limit aplicado ao final.
- Posts fixados antigos, páginas vazias e cursores repetidos.
- Estatísticas ausentes não se convertem em zero; views desconhecidas tornam ranking parcial.
- Falha após página válida preserva vídeos; resposta malformada não vira feed vazio.
- Credenciais ausentes não impedem startup ou outros perfis.

## Tasks

- [x] 1. Escrever testes de API/coleta e contratos HTTP; confirmar falha antes da implementação.
- [x] 2. Implementar modelos, configuração, idioma, adaptadores e serviço; passar testes.
- [x] 3. Documentar setup, provedores, semântica de completude e exemplo JSON.
- [x] 4. Rodar suíte completa, lint, smoke test local e revisar requisitos.

## Verification

- Pacote instalado em modo editável com dependências de desenvolvimento.
- `python -m pytest -q`: 28 testes passaram (1 aviso de depreciação do TestClient
  upstream sobre a transição futura de httpx para httpx2).
- `python -m ruff check .` e `python -m ruff format --check .`: passaram.
- Uvicorn real: Swagger e OpenAPI HTTP 200; POST de três perfis sem credenciais
  HTTP 200 com `not_configured` individual e listas vazias.
- Revisão independente: IDs nulos e perda de uploads válidos na mesma página
  YouTube corrigidos; três casos de regressão falharam antes e passaram após o fix.
- Coleta autenticada ao vivo não executada: credenciais não fornecidas.
