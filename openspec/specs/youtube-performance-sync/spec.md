# youtube-performance-sync Specification

## Purpose

Permitir importar sob demanda dados online e não monetários de vídeos do canal para o acompanhamento local, sem automação oculta ou impacto na produção de Shorts.

## Requirements

### Requirement: Dedicated results workspace and explicit online synchronization
O sistema SHALL oferecer Resultados do canal em uma aba Streamlit própria. A aba MUST listar contas OAuth locais, exigir uma conta selecionada e uma ação explícita de sincronização antes de acessar serviços Google. Abrir a aba, gerar, revisar ou publicar um Short MUST NOT iniciar coleta automática.

#### Scenario: Abertura sem sincronização
- **WHEN** o usuário abre a aba Resultados do canal
- **THEN** o sistema mostra os dados locais existentes e não realiza requisição externa até o comando de sincronização.

#### Scenario: Sincronização com conta selecionada
- **WHEN** o usuário escolhe uma conta conectada e confirma a sincronização
- **THEN** o sistema consulta somente o canal autorizado por aquela conta e apresenta o progresso e o resultado da operação.

### Requirement: Online video discovery and imported metric snapshots
O sistema SHALL descobrir vídeos pertencentes ao canal autorizado e importar metadados comprovados e métricas não monetárias que as APIs retornarem. Cada sincronização MUST criar ou atualizar um snapshot cumulativo com instante, conta de origem e proveniência; valores indisponíveis MUST permanecer desconhecidos. O sistema MUST preservar campos editoriais locais e snapshots de produção congelados.

#### Scenario: Métricas disponíveis
- **WHEN** o YouTube retorna visualizações, visualizações engajadas, inscritos ganhos, duração média ou percentual médio assistido para um vídeo
- **THEN** o sistema grava um snapshot local auditável sem converter métricas ausentes em zero.

#### Scenario: Vídeo existente com anotações locais
- **WHEN** a sincronização encontra um vídeo já acompanhado pelo mesmo ID do YouTube
- **THEN** o sistema atualiza somente os dados comprovados pela origem e preserva tema, gancho, hipóteses e demais anotações locais.

### Requirement: Honest availability, failure and privacy boundaries
O sistema MUST informar quando uma métrica não estiver disponível, atrasada ou não puder ser consultada pela conta autorizada. Falhas de API, permissão, cota ou rede SHALL deixar os snapshots já persistidos inalterados e MUST NOT disparar upload, renderização ou alteração de credenciais. Tokens, refresh tokens, e-mails e respostas brutas sensíveis MUST permanecer em `input/youtube/` ou fora da persistência analítica.

#### Scenario: API indisponível
- **WHEN** a API do YouTube retorna erro de permissão, cota ou rede
- **THEN** a aba mostra uma mensagem acionável, mantém o histórico local e não inicia publicação.

#### Scenario: Métrica de retenção não retornada
- **WHEN** a API não fornecer uma métrica solicitada para aquele vídeo ou período
- **THEN** a interface a identifica como indisponível, sem estimá-la ou alegar causalidade.
