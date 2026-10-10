## ADDED Requirements

### Requirement: Coherent curiosity storytelling with an explicit list exception
Para uma curiosidade solicitada sem formato explícito, o prompt SHALL orientar um roteiro em torno de uma única pergunta, contraste ou descoberta. O gancho MUST ser específico, curto e honesto; o desenvolvimento MUST trazer cedo uma pista ou explicação concreta e fazer cada trecho acrescentar evidência, causa, comparação ou consequência; o encerramento MUST responder claramente à promessa, sem pedido obrigatório de inscrição ou like. O prompt MUST preservar limites vigentes de idioma, palavras, duração estimada, velocidade de voz, formato de saída, placeholders e contrato JSON, e não pode prometer viralização nem inventar fatos, números ou fontes.

#### Scenario: Curiosidade padrão desenvolvida como descoberta
- **WHEN** o usuário fornece somente um tema de curiosidade sem pedir uma lista
- **THEN** o roteiro abre com a pergunta ou contraste pertinente, progride por pistas ou evidências relacionadas e termina com uma resposta clara para a abertura.

#### Scenario: Lista de fatos solicitada explicitamente
- **WHEN** o usuário pede explicitamente uma lista de fatos
- **THEN** o prompt preserva o formato de lista solicitado em vez de forçar uma pergunta central, mantendo os demais limites editoriais e do contrato.
