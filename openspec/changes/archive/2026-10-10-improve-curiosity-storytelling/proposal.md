## Why

O ShortGPT de referência une fatos desconectados e injeta uma animação de inscrição; a conferência do Local Short Studio mostra que o prompt já privilegia descoberta e o renderer não injeta essa animação. Esta mudança torna esses comportamentos explícitos e acrescenta a exceção para pedidos intencionais de listas, evitando regressões sem alterar o fluxo de geração.

## What Changes

- Consolidar no prompt editorial a estrutura padrão de curiosidade como uma pergunta, contraste ou descoberta respondida progressivamente, com exemplos coerentes.
- Preservar o formato de lista de fatos quando ele for pedido de modo explícito, sem estender a estrutura narrativa a outros formatos editoriais.
- Formalizar que novos Shorts não recebem animação de inscrição automaticamente e que recursos de edição, legendas, marca-d’água, trilha, sincronização, duração e publicação permanecem inalterados.

## Capabilities

### New Capabilities

_Nenhuma._

### Modified Capabilities

- `content-authoring`: definir a narrativa-padrão de curiosidade e a exceção explícita para listas de fatos.
- `rendering-output`: garantir a ausência de uma animação de inscrição inserida automaticamente no MP4.

## Impact

- Documentação: `docs/PROMPT_GERAR_SHORTS_RETENCAO.md` e as especificações OpenSpec afetadas.
- Geração, JSON, ZIP, velocidade de voz, saídas, cache e confirmação de publicação: preservados.
- Implementação atual: não há animação de inscrição a remover; a aplicação deverá verificar essa ausência e não introduzir uma interface nova.
