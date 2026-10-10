## Purpose

Separar as responsabilidades da interface local sem mudar o fluxo que gera Shorts, tornando edição, contas e consulta analítica destinos claros.

## ADDED Requirements

### Requirement: Three-destination lateral navigation
O sistema SHALL apresentar um menu lateral com os destinos **Editar e publicar**, **Contas do YouTube** e **Arquivo analítico do canal**. A navegação MUST manter o estado local do projeto e do MP4 da sessão quando o usuário alternar entre destinos.

#### Scenario: Alternar entre destinos
- **WHEN** o usuário seleciona um destino no menu lateral
- **THEN** o sistema mostra somente os controles daquela responsabilidade sem descartar o projeto ou MP4 atual da sessão.

### Requirement: Generation flow remains behaviorally unchanged
O destino Editar e publicar SHALL preservar a lógica e os controles de geração existentes. Ele MUST apenas listar e permitir selecionar contas já conectadas para a publicação explícita; MUST NOT oferecer conexão, reconexão ou exclusão de contas.

#### Scenario: Publicar com conta existente
- **WHEN** o usuário gera um MP4 e seleciona uma conta previamente conectada
- **THEN** a confirmação por hash do MP4 e o upload mantêm o comportamento vigente.
