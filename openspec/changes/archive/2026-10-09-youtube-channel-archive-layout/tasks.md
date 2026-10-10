## 1. Navegação e gerenciamento de contas

- [x] 1.1 Reorganizar somente a apresentação em `app/ui.py` com o menu lateral e os três destinos, preservando estado de projeto e MP4; verificar por teste de interface/mocks que nenhuma chamada, parâmetro ou controle do pipeline de geração foi alterado.
- [x] 1.2 Restringir Editar e publicar à listagem/seleção de contas já conectadas e mover conectar, reconectar e remover para Contas do YouTube; verificar com testes de UI simulados que a confirmação por hash e o upload existente continuam iguais.
- [x] 1.3 Exibir no destino de contas somente identificadores não sensíveis e preservar a remoção limitada a token/cadastro local; verificar com testes que nenhum e-mail completo, token ou arquivo do arquivo analítico é exposto ou apagado.

## 2. Coleta e arquivo analítico do canal

- [x] 2.1 Estender o cliente do YouTube exclusivamente com os escopos e operações de leitura não monetária necessários para canal, playlist de uploads, vídeos e Analytics; verificar com mocks que renovação OAuth, permissões insuficientes e respostas sem campos têm comportamento explícito e não alteram publicação.
- [x] 2.2 Implementar a coleta sob comando explícito com paginação dos uploads acessíveis, obtenção dos metadados/estatísticas disponíveis e relatórios analíticos suportados; verificar com testes que todas as páginas são processadas, o limite seguro e a cobertura ficam registrados e nenhuma consulta ocorre ao abrir a tela.
- [x] 2.3 Persistir snapshots imutáveis em `input/channel_archive/<conta>/<ano>/<mês>/<dia>/<instante>/`, com manifesto, dados normalizados e somente respostas sanitizadas; verificar com testes que duas coletas no mesmo dia não se sobrescrevem e que segredos, e-mails completos e cookies não são gravados.
- [x] 2.4 Criar o destino Arquivo analítico do canal com seleção explícita de conta, confirmação de coleta, progresso, resumo e mensagens de cota/rede/escopo; verificar com testes de UI que a falha não cria arquivo parcial enganoso nem modifica JSON, ZIP, cache, MP4 ou publicação.

## 3. Documentação e validação de compatibilidade

- [x] 3.1 Documentar a navegação, a gestão de contas, os escopos solicitados, o layout do arquivo e limites/atrasos da API; verificar que a documentação não instrui a versionar credenciais ou dados gerados.
- [x] 3.2 Executar a suíte completa no container, incluindo mocks de YouTube e regressões de schemas, ZIP, pipeline, renderer e publicação; verificar também `docker compose config` e que não houve alteração em `app/pipeline.py`, `app/renderer.py`, `app/schemas.py` ou no comportamento de geração.
