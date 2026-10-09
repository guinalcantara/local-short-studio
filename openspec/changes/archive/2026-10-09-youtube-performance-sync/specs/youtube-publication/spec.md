## MODIFIED Requirements

### Requirement: Explicit account and confirmation
O sistema SHALL listar somente contas OAuth conectadas localmente. A conta selecionada MUST ser escolhida explicitamente tanto para uma sincronização online de resultados quanto para publicação. O sistema MUST exigir confirmação do usuário para o hash exato do MP4 antes do upload; sincronizar resultados MUST NOT publicar ou confirmar upload.

#### Scenario: Sem conta ou confirmação
- **WHEN** não há conta selecionada ou a confirmação de publicação não foi marcada
- **THEN** o sistema mantém a publicação desabilitada.

#### Scenario: Conta sem leitura analítica
- **WHEN** o usuário seleciona uma conta conectada sem o consentimento de leitura analítica exigido
- **THEN** o sistema solicita reconexão explícita da conta e não realiza sincronização até a conclusão do novo consentimento.
