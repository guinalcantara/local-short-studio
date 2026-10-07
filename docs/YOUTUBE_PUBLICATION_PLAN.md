# Plano de atualização: publicação direta no YouTube

**Estado:** OAuth local por conta, seletor de conta vazio por padrão, upload resumível do MP4 e envio opcional de faixa SRT/VTT foram implementados na branch `youtube-publication-plan`. Agendamento, lote e miniaturas continuam fora do escopo.

## Objetivo

Depois que o MP4 for renderizado localmente, permitir que a pessoa escolha uma conta previamente conectada e publique o arquivo no canal correspondente usando os metadados já existentes em `project.youtube`.

O seletor deve começar sem valor: `Selecione uma conta para publicar`. Não haverá conta padrão, publicação automática nem tentativa de login ao abrir a tela.

## Evidências no contrato atual

O projeto já valida e preserva os campos necessários para a primeira publicação:

- `title`;
- `youtube.description`, `tags`, `category_id` e `default_language`;
- `youtube.status.privacy_status`, `license`, `embeddable`, `public_stats_viewable`, `self_declared_made_for_kids` e `contains_synthetic_media`;
- `youtube.notify_subscribers`;
- `youtube.captions`, que controla o idioma e o formato da faixa fechada enviada depois do MP4.

O exemplo único em `examples/modelo_projeto.json` passou a usar o roteiro real fornecido, incluindo esse bloco `youtube`. O antigo exemplo reduzido de múltiplos planos foi removido para não competir com ele.

## Fluxo proposto

```text
MP4 concluído + project.json válido
        ↓
usuário escolhe uma conta conectada (inicialmente vazia)
        ↓
revisão explícita de destino, título, privacidade e avisos
        ↓
OAuth da conta escolhida, se o token precisar ser renovado
        ↓
videos.insert com snippet + status do bloco youtube
        ↓
captions.insert opcional usando o ID retornado e o SRT/VTT local
        ↓
URL/ID retornado, estado de processamento e registro local da publicação
```

### Comportamento da interface

1. Exibir uma área **Publicar no YouTube** sempre que o app estiver aberto, para conectar e selecionar contas sem depender da renderização; a publicação permanece bloqueada até existir um MP4 válido.
2. Exibir um `selectbox` com `""` como primeira opção e texto `Selecione uma conta para publicar`.
3. Mostrar somente contas concluídas no OAuth, com nome escolhido localmente e título do canal obtido da API; oferecer **Conectar nova conta** e **Desconectar**.
4. Manter **Publicar** desabilitado até existir MP4, `youtube` válido e uma conta selecionada.
5. Antes de enviar, apresentar uma confirmação que mostre canal, título, privacidade e os campos de público infantil e mídia sintética. A confirmação é por publicação; não há envio em segundo plano.
6. Após o envio, mostrar o link do vídeo e o estado de processamento. Falhas devem preservar o MP4 e explicar se o upload não foi iniciado, foi interrompido ou foi aceito e ainda está processando.

## Implementação realizada

1. **Dependências e configuração segura:** bibliotecas oficiais de cliente/OAuth, `input/youtube/` ignorado pelo Git e callback Docker local na porta `8765` (configurável por `YOUTUBE_OAUTH_PORT`).
2. **Contas OAuth:** conexão pelo navegador, identificação de canal, renovação de token, listagem de contas e remoção do token local. O escopo adicional `youtube.readonly` serve somente para identificar o canal na lista; `youtube.upload` autoriza o envio.
3. **Camada de publicação:** mapeamento do JSON para `snippet` e `status` do `videos.insert`, upload resumível do MP4 e `captions.insert` opcional com SRT ou VTT local. O MP4 é registrado antes da legenda para evitar reenvio se a segunda etapa falhar; a tentativa posterior usa o mesmo ID de vídeo.
4. **Interface e confirmações:** seletor inicialmente vazio, revisão de metadados, confirmação obrigatória, aviso sobre processamento e bloqueio contra reenvio do mesmo MP4.
5. **Testes:** cobertura para mapeamento de metadados, armazenamento local de conta, remoção de token, upload resumível, conversão SRT→VTT, envio de legenda e proteção contra duplicidade.

## Próximas etapas opcionais

- consultar o estado de processamento depois do upload;
- avaliar agendamento, thumbnails e publicação em lote somente após revisar o escopo e as políticas da API.

## Decisões de escopo

- A primeira versão publica **um MP4 por ação explícita**, no canal OAuth selecionado.
- O valor padrão de `privacy_status` no modelo continua `private`, adequado para revisão. Projetos de API não verificados podem ser forçados pelo YouTube a permanecer privados.
- Agendamento, publicação em lote, troca automática de conta e miniaturas ficam fora da entrega atual.
- O `youtube` no JSON continua sem credenciais, IDs privados de conta, token ou `publishAt`.
- Os controles locais de música não comprovam direitos autorais; a pessoa que publica continua responsável por licenças, conteúdo e declarações ao YouTube.

Consulte [YOUTUBE_AUTHENTICATION.md](YOUTUBE_AUTHENTICATION.md) para criar o projeto OAuth e entender por que uma chave de API não basta para upload.
