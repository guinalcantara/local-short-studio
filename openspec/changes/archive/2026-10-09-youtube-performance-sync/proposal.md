## Why

O acompanhamento de resultados hoje exige digitação manual e fica junto ao fluxo principal da página. O usuário já conecta contas OAuth ao YouTube e quer consultar online os Shorts do canal, com dados reais trazidos sob demanda para o painel local.

## What Changes

- Criar uma aba Streamlit dedicada a **Resultados do canal**, sem iniciar TTS, Whisper, renderização ou publicação.
- Adicionar sincronização manual sob demanda dos vídeos/Shorts da conta OAuth explicitamente selecionada, usando YouTube Data API e YouTube Analytics API.
- Salvar snapshots importados e sua proveniência localmente, preservando histórico e sem reescrever dados editoriais ou de produção já congelados.
- Ampliar o consentimento OAuth com o escopo mínimo de leitura analítica; contas existentes precisarão ser reconectadas. Nenhuma permissão monetária será solicitada.
- Exibir com transparência atrasos, indisponibilidades e limites da API, sem inventar métricas que a API não retornar.

## Capabilities

### New Capabilities

- `youtube-performance-sync`: descoberta e importação autenticada, manual e auditável de vídeos e métricas não monetárias do canal para o acompanhamento local.

### Modified Capabilities

- `youtube-publication`: a conta OAuth conectada passa a poder conceder leitura de YouTube Analytics, mantendo a seleção explícita de conta e a confirmação obrigatória para cada upload.

## Impact

- `app/youtube.py`, os modelos/SQLite/UI de resultados e a página Streamlit.
- Documentação de OAuth e publicação, pois o usuário terá de reconectar contas e habilitar a YouTube Analytics API no projeto Google Cloud.
- Apenas APIs Google já suportadas pelas dependências instaladas; sem GPU, novos contêiners ou alteração do JSON portátil, ZIP, cache, MP4 ou upload automático.
