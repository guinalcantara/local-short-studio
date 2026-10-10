## Purpose

Concentrar o ciclo de vida das contas OAuth do YouTube em um destino dedicado, sem misturá-lo à edição ou publicação de Shorts.

## ADDED Requirements

### Requirement: Dedicated local account management
O sistema SHALL permitir listar, iniciar conexão, concluir reconexão e remover contas OAuth somente no destino Contas do YouTube. A lista MUST exibir apenas apelido local e identificação não sensível do canal, sem e-mail ou tokens.

#### Scenario: Conectar uma conta
- **WHEN** o usuário inicia e conclui a autorização OAuth no destino de contas
- **THEN** a conta passa a estar disponível para publicação e arquivo analítico conforme seus escopos concedidos.

#### Scenario: Remover uma conta
- **WHEN** o usuário confirma a remoção de uma conta local
- **THEN** o sistema remove somente o token e cadastro locais da conta, sem apagar arquivos analíticos históricos.
