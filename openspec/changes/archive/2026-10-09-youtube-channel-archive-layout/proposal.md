## Why

A página de geração concentra configurações de render, publicação e gestão de contas, o que dificulta o uso. Além disso, o canal ainda não possui um acervo local de dados online que permita distinguir padrões de desempenho e orientar futuras melhorias do prompt.

## What Changes

- Reorganizar o Streamlit em um menu lateral com três destinos: **Editar e publicar**, **Contas do YouTube** e **Arquivo analítico do canal**.
- Manter a tela de edição/publicação limitada a listar e selecionar contas conectadas para o upload; conectar ou excluir contas passa a ser responsabilidade exclusiva do destino de contas.
- Adicionar um destino analítico separado, no qual o usuário seleciona uma conta e solicita explicitamente uma coleta completa dos metadados e dados não monetários que as APIs do YouTube disponibilizarem.
- Persistir um mapeamento por conta, ano/mês/dia em diretório local do projeto, com manifestos de coleta, dados normalizados e respostas brutas sanitizadas quando apropriado para auditoria e análise futura.
- Preservar integralmente a lógica, o contrato e o código de geração de Shorts; a nova lógica permitida fica restrita ao destino de arquivo analítico e ao cliente de leitura do YouTube.

## Capabilities

### New Capabilities

- `studio-navigation`: navegação lateral que separa edição/publicação, administração de contas e análise sem alterar a geração.
- `youtube-account-management`: conexão, reconexão e remoção de contas OAuth locais em um destino dedicado.
- `youtube-channel-archive`: coleta sob demanda e arquivo local estruturado dos metadados e dados não monetários do canal/vídeos autorizados.

### Modified Capabilities

- Nenhuma. A confirmação por MP4, o contrato JSON/ZIP e a geração de Shorts permanecem inalterados.

## Impact

- `app/ui.py` será dividido apenas para apresentação/navegação; pipeline, renderer, schemas, ZIP e TTS não serão alterados.
- `app/youtube.py` poderá receber cliente de leitura e escopo analítico mínimo; tokens permanecem em `input/youtube/`.
- Novo armazenamento persistente local, por exemplo `input/channel_archive/<conta>/<ano>/<mês>/<dia>/`, sem credenciais, e nova documentação de permissões, limites e atrasos da API.
