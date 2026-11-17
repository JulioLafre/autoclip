# Fluxo dos bots ClipshortsBr

Use a pasta do projeto em comum nos três bots. No OpenBot, substitua as
instruções permanentes pelo arquivo do papel correspondente. Cada prompt tem
menos de 2.000 caracteres.

- [ANALISTA](analista.md) recebe o vídeo e cria o plano.
- [EDITOR](editor.md) executa o plano, verifica o MP4 e salva o relatório.
- [GERENTE DO CANAL](gerentedocanal.md) monta o pacote para a postagem.

Para iniciar o fluxo com um link enviado pelo Telegram, use o
[prompt do bot de entrada](telegram.md) e permita que ele chame o Analista.

## Habilitar a passagem entre agentes

Cada passagem usa a ferramenta de mensagem entre agentes do OpenBot. O remetente
confere se a ferramenta aceitou o envio.

- Se a sua versão oferece `list_agents` e `send_message`, localize o destinatário
  pelo nome e use `send_message` para iniciar a tarefa dele. Use os nomes reais
  cadastrados no OpenBot.
- Se a sua instalação usa `message_bot` e mostra **Setup → Bots it can ask**,
  permita que o Analista chame o Editor e que o Editor chame o Gerente. Nesse modo,
  o limite padrão de profundidade é 1. No ambiente do **OpenBot**, use
  `BOT_HANDOFF_MAX_DEPTH=2` para começar no Analista ou `BOT_HANDOFF_MAX_DEPTH=3`
  para começar no Telegram e seguir até o Gerente.

[Ferramentas de mensagem entre agentes](https://github.com/nightly-labs/openbot/blob/main/docs/architecture/providers.md#built-in-tool-discovery)
· [Permissões e profundidade no OpenBot](https://github.com/CopilotKit/OpenBot/blob/main/docs/configuration.md#one-bot-handing-work-to-another)

## Iniciar um vídeo

Envie somente ao **ANALISTA**:

```text
Processe media/entrada/SEU-VIDEO.mp4 como trabalho meu-video-01.
Execute o fluxo completo até o Gerente do Canal, com tradução pt-BR
e dublagem Azure quando houver fala em inglês confirmada.
Mantenha o quadro original, com o mesmo tamanho e sem template.
```

O Gerente encerra com o pacote em `media/publicacao/<id>/` ou um relatório de
bloqueio. Quando quiser postar, envie uma instrução separada ao Gerente:

```text
Publique o trabalho meu-video-01 no YouTube pelo Postiz, com visibilidade pública.
Use o MP4 e os metadados do pacote salvo.
```

## Dados que passam entre as etapas

1. **Analista → Editor**. Envie ID, caminho absoluto da entrada, caminho absoluto
   do plano, estado `plano_pronto` ou `bloqueado` e o motivo de eventual bloqueio.
   Se não existir plano ou entrada, marque o caminho ausente como `null`. Inclua
   pedidos explícitos do trabalho, como preservar o áudio.
2. **Editor → Gerente**. Envie o mesmo ID, estado `concluido` ou `bloqueado`,
   caminhos absolutos do plano, relatório, MP4 final quando houver, avisos e
   motivo de bloqueio. Salve o relatório em `media/finalizados/` se concluído ou
   em `media/revisar/` se bloqueado.
3. **Gerente → usuário**. Encerre com `pronto_para_publicar` ou `bloqueado`.
   Salve em `media/publicacao/<id>/` um resumo com o estado e os caminhos do
   pacote ou a causa do bloqueio. Na entrega concluída, inclua MP4, thumbnail
   escolhida, título, descrição, hashtags e tags.

Use caminhos absolutos acessíveis pelos três bots. Mantenha o mesmo ID na
sequência e preserve versões anteriores. Em cada passagem, peça ao destinatário
que **execute** a próxima etapa. Dispare uma vez por estágio e ID. Se a ferramenta
estiver indisponível ou recusar a chamada, reporte o erro e os caminhos salvos.
O envio aceito indica que a próxima etapa foi encaminhada. A conclusão vem no
resultado do destinatário.

## Resolver problemas durante o fluxo

Os bots seguem a [política editorial](politica-editorial.md) e resolvem os
ajustes dentro da função de cada um, sem intercalar pedidos de avaliação ao
usuário. O Editor tem até duas tentativas de correção por trabalho. Se ainda
houver um bloqueio essencial, salve evidências e passe o motivo adiante até o
Gerente. Ele fecha o trabalho com o estado `bloqueado`.
