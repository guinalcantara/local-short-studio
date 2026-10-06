# Plano de atualização: publicação direta no YouTube

**Estado:** planejamento aprovado para a branch `youtube-publication-plan`. Nenhum upload, OAuth ou chamada à API foi implementado nesta etapa.

## Objetivo

Depois que o MP4 for renderizado localmente, permitir que a pessoa escolha uma conta previamente conectada e publique o arquivo no canal correspondente usando os metadados já existentes em `project.youtube`.

O seletor deve começar sem valor: `Selecione uma conta para publicar`. Não haverá conta padrão, publicação automática nem tentativa de login ao abrir a tela.

## Evidências no contrato atual

O projeto já valida e preserva os campos necessários para a primeira publicação:

- `title`;
- `youtube.description`, `tags`, `category_id` e `default_language`;
- `youtube.status.privacy_status`, `license`, `embeddable`, `public_stats_viewable`, `self_declared_made_for_kids` e `contains_synthetic_media`;
- `youtube.notify_subscribers`;
- `youtube.captions`, hoje apenas como intenção de uma etapa posterior de envio de legendas.

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
URL/ID retornado, estado de processamento e registro local da publicação
```

### Comportamento da interface

1. Criar uma área **Publicar no YouTube** depois que o vídeo estiver pronto; ela não aparece como etapa obrigatória da renderização local.
2. Exibir um `selectbox` com `""` como primeira opção e texto `Selecione uma conta para publicar`.
3. Mostrar somente contas concluídas no OAuth, com nome escolhido localmente e título do canal obtido da API; oferecer **Conectar nova conta** e **Desconectar**.
4. Manter **Publicar** desabilitado até existir MP4, `youtube` válido e uma conta selecionada.
5. Antes de enviar, apresentar uma confirmação que mostre canal, título, privacidade e os campos de público infantil e mídia sintética. A confirmação é por publicação; não há envio em segundo plano.
6. Após o envio, mostrar o link do vídeo e o estado de processamento. Falhas devem preservar o MP4 e explicar se o upload não foi iniciado, foi interrompido ou foi aceito e ainda está processando.

## Implementação em etapas futuras

1. **Dependências e configuração segura:** adicionar as bibliotecas oficiais de cliente/OAuth, local ignorado pelo Git para credencial do cliente e tokens, e portas de callback explicitamente documentadas para Docker local.
2. **Contas OAuth:** implementar conexão, renovação, listagem de canais da credencial e remoção local/revogação orientada. Usar o escopo mínimo `youtube.upload`; pedir escopos adicionais somente quando uma função futura os exigir.
3. **Camada de publicação:** mapear o JSON para `snippet` e `status` do `videos.insert`, usar upload retomável, validar limites antes da chamada e registrar ID/URL/horário/conta sem registrar tokens.
4. **Interface e confirmações:** implementar o seletor vazio, a revisão explícita e mensagens de progresso/erro acessíveis no Streamlit.
5. **Legendas e processamento:** em uma entrega separada, decidir se o `.srt` local será convertido para VTT e enviado pela API. Isso não bloqueia o primeiro upload do MP4.
6. **Testes:** cobrir o mapeamento de metadados, ausência de conta, token expirado, cancelamento, erros recuperáveis do Google, reenvio seguro e garantia de que segredos não entram em `output/` ou logs.

## Decisões de escopo

- A primeira versão publica **um MP4 por ação explícita**, no canal OAuth selecionado.
- O valor padrão de `privacy_status` no modelo continua `private`, adequado para revisão. Projetos de API não verificados podem ser forçados pelo YouTube a permanecer privados.
- Agendamento, publicação em lote, troca automática de conta, thumbnails e upload de legendas ficam fora da primeira entrega.
- O `youtube` no JSON continua sem credenciais, IDs privados de conta, token ou `publishAt`.
- Os controles locais de música não comprovam direitos autorais; a pessoa que publica continua responsável por licenças, conteúdo e declarações ao YouTube.

Consulte [YOUTUBE_AUTHENTICATION.md](YOUTUBE_AUTHENTICATION.md) para criar o projeto OAuth e entender por que uma chave de API não basta para upload.
