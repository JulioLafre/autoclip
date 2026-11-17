# Política editorial — ClipshortsBr

Esta é a regra compartilhada pelo Analista, Editor e Gerente do Canal. Siga o
[fluxo entre os três bots](README.md). Instruções explícitas do usuário para um
trabalho específico prevalecem sobre estes padrões.

## Padrões do canal

- Idioma editorial: português do Brasil.
- Preserve a largura, a altura, a proporção, a orientação e o quadro inteiro do
  vídeo original. Exporte sem template, bordas adicionadas, recorte de imagem
  ou redimensionamento. A seleção temporal continua em até 30 s por padrão.
- Manter nomes próprios, marcas, usernames e títulos de jogos. Inglês incidental
  do cenário, placas e interfaces não precisa ser apagado. Textos de meme,
  títulos e legendas editoriais precisam ter tratamento definido em pt-BR.
- Preservar sentido, contexto e humor; não inventar acontecimentos ou falas.
- Dublar falas relevantes em inglês quando o Whisper e a análise confirmarem seu
  conteúdo. Use traduções curtas em pt-BR e o Azure Speech. Preserve o original
  quando o trabalho pedir ou quando o áudio for só música, ruído ou silêncio.
- Se houver fala compreensível que não dê para dublar, use legendas em pt-BR
  com o áudio original quando a dublagem não for exigência expressa do trabalho.
  Se uma fala essencial não puder ser compreendida, registre o bloqueio.
- Toda edição parte do arquivo original. Use sufixos para preservar originais,
  planos anteriores e renderizações anteriores.
- O Gerente prepara o pacote ao fim do fluxo. Postagem via Postiz exige uma
  instrução do usuário para o vídeo daquele trabalho.

## Como tratar texto

| Caso | Ação padrão |
| --- | --- |
| Sem texto editorial | Manter imagem; não adicionar frases sem necessidade |
| Texto editorial em português | Preservar, se legível e bem posicionado |
| Texto estrangeiro sobre faixa sólida separada da cena | Cobrir toda a escrita original e inserir a tradução na faixa, dentro do quadro original |
| Texto sobre a cena em área não essencial | Avaliar painel opaco com tradução, sem encobrir ação, rostos ou informações relevantes |
| Texto sobre rosto, mãos ou ação importante | Procurar outra posição para a tradução dentro do quadro e registrar bloqueio se não houver tratamento seguro para o texto original |
| Legenda selecionável separada | Selecionar, omitir ou substituir a faixa conforme o plano; conferir também texto embutido |
| Texto variável ou em movimento | Mapear intervalos e posições; não usar uma caixa fixa baseada em um único frame |
| Texto ilegível ou tradução ambígua essencial | Usar outro trecho coerente ou registrar bloqueio |

Não basta adicionar português por cima mantendo a escrita inglesa visível.
Não basta detectar o idioma e preservá-lo por inércia. Cada texto editorial tem
uma ação explícita: `manter`, `substituir`, `reposicionar` ou `revisar`.
Ao reposicionar uma tradução, trate também o texto original visível.
Evitar blur/delogo para substituir frases: pode borrar a
cena e ainda deixar letras perceptíveis. Há uma ferramenta experimental de
inpainting OpenCV por frame em `scripts/inpaint-video.py`. Consulte
`docs/inpainting.md`. O Editor gera a prévia e verifica a continuidade por conta
própria. Se a verificação falhar, use cobertura ou painel quando couber no
quadro. Se nenhum método preservar a ação e a mensagem, registre o bloqueio.

## Geometria e áudio

- Medir a abertura central real no alpha do PNG e escalá-la para a saída.
  Descartar transparência decorativa nas bordas ao localizar essa abertura.
- Use o quadro original como área de edição. Posicione textos e legendas dentro
  dos seus limites. Preserve o vídeo sem filtros de escala, recorte, zoom ou padding.
- Compare largura, altura, proporção de pixels e orientação na entrada e na
  saída com ffprobe. Preserve o formato de pixels compatível com as dimensões.
- Planos antigos podem conter moldura, escala ou posições calculadas para outro
  quadro. Recalcule as regiões afetadas nos pixels da entrada e salve a revisão
  antes de renderizar. O contrato de dublagem continua na versão 2.
- Fonte com suporte a acentos, tamanho legível, margens e quebras de linha
  medidas. Coordenadas de entrada e saída precisam estar claramente separadas.
- Manter sincronismo; não presumir que imagem e áudio têm a mesma duração.
- Na dublagem, conferir a prévia de áudio e definir no plano como substituir a
  fala original. Se houver uma faixa separada de música/efeitos, ela pode ser
  mantida na mixagem. Se a fala estiver misturada aos efeitos, registrar o
  impacto no plano antes de finalizar. Consulte [Dublagem](../dublagem.md).
- Se o Azure falhar, o Editor pode ajustar uma frase longa preservando o sentido
  ou corrigir a configuração acessível. Registre o ajuste numa versão do plano.
  Se ainda falhar, use legendas para falas confirmadas quando a dublagem for
  opcional. Se ela for obrigatória, encaminhe o bloqueio ao Gerente.
- Fazer amostragem adicional nas mudanças de texto/cena, sem afirmar inspeção
  completa quando apenas frames foram examinados.

## Decisões

- `aprovado`: plano executável, sem pendências bloqueadoras.
- `aprovado_com_avisos`: pode executar; limitações não bloqueadoras listadas.
- `bloqueado`: há uma etapa essencial sem solução que possa ser executada.
- `inviavel`: arquivo corrompido/ilegível ou edição impossível com o material.

Baixa resolução ou ausência de um desfecho podem virar avisos se o vídeo ainda
comunicar a ideia. Corrija problemas que tiverem solução sem consultar o usuário.
Se não houver alternativa viável, encaminhe ao próximo bot com o motivo e a
evidência. Para planos anteriores, trate `precisa_revisao_humana` como bloqueio
até que o problema específico possa ser resolvido com as evidências disponíveis.

## Contrato do plano JSON — versão 2

O Analista cria o plano; o Editor o executa. Campos obrigatórios:

- `versao`: 2; `id`: identificador simples do trabalho.
- `entrada`: caminho absoluto do vídeo original e seu SHA256 em `sha256_entrada`.
- `metadados`: dimensões, duração, FPS, streams e informações do áudio.
- `classificacao`: tipo (gameplay, animação, meme, diálogo, montagem ou outro),
  idiomas de texto e áudio, presença de fala/música e resumo do que foi observado.
- `trecho`: início e duração em segundos; justificativa.
- `saida`: largura, altura, proporção e orientação da entrada, FPS e caminho
  absoluto de saída proposto.
- `enquadramento`: `modo: "original"` e referência explícita aos pixels da entrada.
- `textos`: um item por texto editorial/segmento, com original, idioma,
  tradução pt-BR quando aplicável, ação, método, intervalo, região original,
  região de cobertura e região de renderização. Coordenadas sempre em pixels,
  com o espaço (`entrada` ou `saida`) explícito. Incluir fundo, fonte local,
  tamanho, cor, margens, entrelinha e quebras de linha exatas para substituições.
- `legendas_fala`: segmentos pt-BR e seus tempos, ou lista vazia; indicar a
  confiança e as evidências da transcrição/tradução quando houver segmentos.
- `audio`: ação, sincronização e intervalo. Usar `acao: "dublar_pt_br"` para
  a dublagem planejada e incluir `dublagem.segmentos`. Cada item tem
  `inicio_segundos`, `fim_segundos` relativos à saída e `texto_pt_br` confirmado.
  Os intervalos devem estar ordenados, dentro da duração de `trecho` e sem
  sobreposição. Para outros casos, definir o tratamento de áudio no plano.
- `decisao`: status, `prosseguir_automaticamente`, bloqueios e avisos separados.
- `evidencias`: caminhos dos frames, OCR, transcrição e medições; limitações.
- `verificacao`: critérios específicos para texto, geometria original e áudio.

Tempos dos textos devem indicar se são relativos à entrada ou ao trecho de
saída. Para renderização, fornecer também início/fim relativos à saída.
Não preencher valores faltantes com coordenadas ou textos fictícios.
