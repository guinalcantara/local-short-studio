## Context

O prompt normativo atual já orienta uma pergunta ou pequena história, pistas concretas, conclusão clara e a ausência de CTA obrigatória. A inspeção do renderer também não encontrou uma etapa que acrescente animação de inscrição. Em contraste, o ShortGPT de referência usa um exemplo de fatos desconectados e chama uma animação de inscrição em toda renderização.

## Goals / Non-Goals

**Goals:**

- Tornar a narrativa de descoberta o comportamento editorial inequívoco para curiosidades sem formato pedido.
- Manter a possibilidade de uma lista quando ela for a intenção explícita da pessoa.
- Proteger, como contrato, o comportamento atual de não inserir animação de inscrição automaticamente.

**Non-Goals:**

- Alterar geração de voz, pipeline, contrato JSON, velocidade, duração, legendas, música, marca-d’água, tradução ou publicação.
- Criar controles de CTA, novas chamadas de IA, serviços de verificação, testes A/B ou garantia de desempenho/viralização.

## Decisions

- Ajustar somente o prompt editorial e seu exemplo, com uma regra condicional para pedido explícito de lista. Essa abordagem esclarece a intenção sem modificar contratos ou código de geração. A alternativa de introduzir um novo campo JSON ou seletor foi descartada porque ampliaria o contrato sem necessidade.
- Não criar, deslocar nem parametrizar uma animação de inscrição. A implementação fará uma verificação direcionada de que a montagem atual continua sem essa etapa; criar um toggle para um recurso inexistente foi descartado.
- Validar o texto e os contratos existentes por inspeção e testes locais proporcionais. Não haverá teste que tente medir qualidade narrativa ou viralização por palavras-chave.

## Risks / Trade-offs

- [Um modelo externo pode ignorar orientações editoriais.] → O prompt explicita a progressão e inclui um exemplo de descoberta, sem afirmar que a qualidade pode ser validada automaticamente.
- [Uma alteração futura no renderer pode introduzir uma CTA visual.] → A nova exigência e o check direcionado tornam essa regressão visível na revisão.

## Migration Plan

Não há migração de dados, JSONs ou MP4s. A alteração será entregue como atualização de orientação editorial; a reversão consiste em restaurar o texto anterior, sem reprocessar saídas existentes.
