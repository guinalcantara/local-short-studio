## 1. Prompt editorial

- [x] 1.1 Atualizar `docs/PROMPT_GERAR_SHORTS_RETENCAO.md` para tornar explícita a narrativa padrão de curiosidade (gancho, pistas relacionadas e resposta), preservando idioma, limites de palavras/duração, `speech_speed`, placeholders e contrato JSON; verificar a ausência de promessas de viralização, CTA obrigatória ou fatos inventados.
- [x] 1.2 Acrescentar a exceção para pedido explícito de lista de fatos e revisar o exemplo editorial principal para demonstrar gancho → pistas → descoberta, verificando que nenhum outro formato solicitado foi alterado.

## 2. Regressão de inscrição e preservação

- [x] 2.1 Conferir a montagem atual e manter a ausência de uma etapa que injete animação de inscrição automaticamente; verificar que não foi criado toggle/interface e que os recursos genéricos de edição permanecem disponíveis.
- [x] 2.2 Executar os testes locais pertinentes de esquema, pipeline e renderer no container, sem APIs pagas nem renderização completa, e confirmar que legendas, marca-d’água, trilha, sincronização, duração, tradução e publicação continuam cobertos pelos contratos existentes.

## 3. Validação da especificação

- [x] 3.1 Executar `openspec validate improve-curiosity-storytelling --strict` e revisar os artefatos para confirmar os cenários de descoberta padrão, lista explícita, ausência de inscrição automática e preservação dos fluxos.
