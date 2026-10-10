## ADDED Requirements

### Requirement: No automatic subscription animation
O sistema SHALL gerar novos Shorts sem inserir automaticamente uma animação de inscrição. A ausência dessa inserção MUST preservar os recursos genéricos de edição que outros fluxos utilizem e não pode alterar legendas, marca-d’água, trilha, sincronização, duração, tradução, publicação ou MP4s já exportados.

#### Scenario: Novo Short sem inscrição automática
- **WHEN** o usuário gera um novo Short pelo fluxo padrão
- **THEN** o MP4 resultante não contém uma animação de inscrição acrescentada automaticamente pelo sistema.

#### Scenario: Fluxos existentes preservados
- **WHEN** o usuário gera um Short com os recursos já suportados de imagens, narração, legendas, trilha, marca-d’água ou publicação opcional
- **THEN** esses recursos mantêm seus contratos e comportamentos existentes, sem uma nova configuração ou interface de inscrição.
