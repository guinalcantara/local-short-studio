## 1. OAuth e cliente de consulta

- [x] 1.1 Acrescentar o escopo não monetário `yt-analytics.readonly`, detectar tokens sem ele e preservar o fluxo de upload; verificar com testes de escopo e reconexão.
- [x] 1.2 Implementar clientes autenticados, limitados e testáveis para YouTube Data API e YouTube Analytics API; verificar consultas por conta, paginação e tratamento de erros HTTP simulados.

## 2. Importação e persistência

- [x] 2.1 Evoluir o modelo e as migrações SQLite para registrar origem, conta, instante e métricas importadas sem armazenar respostas brutas ou segredos; verificar migração e reabertura do banco.
- [x] 2.2 Implementar reconciliação por ID do YouTube, criação de snapshots cumulativos e preservação de campos editoriais/snapshots de produção; verificar registros existentes, vídeos novos e métricas parciais.
- [x] 2.3 Mapear somente métricas oficialmente retornadas e manter indisponíveis como desconhecidas; verificar `engagedViews`, inscritos, duração média, percentual médio e ausências.

## 3. Aba e operação do usuário

- [x] 3.1 Reorganizar a interface Streamlit em abas e mover Resultados do canal para uma aba dedicada sem executar pipeline ou upload; verificar abertura sem GPU/OAuth e preservação do fluxo atual de geração.
- [x] 3.2 Adicionar seleção explícita de conta, comando de sincronização, progresso, resumo e mensagens para consentimento insuficiente, cota/rede e dados atrasados; verificar com stubs de serviço.
- [x] 3.3 Exibir origem e hora de coleta no histórico/comparações e manter o cadastro manual como fallback explícito; verificar que não há coleta automática ao abrir, renderizar ou publicar.

## 4. Compatibilidade e validação

- [x] 4.1 Atualizar README e guias de autenticação/publicação com habilitação da YouTube Analytics API, reconexão, métricas, atrasos e limites; verificar que não há promessa de coleta automática ou receita.
- [x] 4.2 Executar toda a suíte no container, `docker compose config`, validação OpenSpec estrita e inspeção manual da aba; registrar limitações da API observadas.
