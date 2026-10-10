## Context

Veja `proposal.md`. A interface atual é uma página Streamlit única que agrega projeto, render, publicação e gerenciamento OAuth. As contas e tokens já ficam em `input/youtube/`; a lista de uploads de um canal é exposta pela playlist relacionada do canal, e relatórios analíticos aceitam dimensões temporais e de vídeo.

## Goals / Non-Goals

**Goals:**

- Isolar as responsabilidades de interface sem alterar o pipeline de geração.
- Persistir um acervo reproduzível por conta/data que possa servir de insumo a análises futuras de vídeos virais, sem concluir causalidade agora.
- Coletar somente sob comando explícito e com escopos de leitura mínimos, não monetários.

**Non-Goals:**

- Alterar schemas, pipeline, renderer, TTS, Whisper, ZIP, cache, prompt de geração, publicação ou criar pontuação de viralidade nesta mudança.
- Agendar coleta, enviar dados a terceiros, coletar receita ou armazenar segredos.

## Decisions

### Navegação lateral com destinos isolados

O app passa a ter um roteador de interface e três funções de apresentação. O conteúdo atual de geração será movido como unidade, sem alterar chamadas do pipeline ou seus valores. Contas será uma superfície dedicada; Arquivo analítico não importará o pipeline.

Alternativa rejeitada: abas dentro da tela de geração, pois ainda mantém responsabilidades concorrentes no mesmo fluxo.

### Arquivo imutável por coleta

Usar `input/channel_archive/<account-id>/<YYYY>/<MM>/<DD>/<timestamp>/`. Cada diretório contém `manifest.json`, `channel.json`, `videos.jsonl` e, quando suportado, relatórios analíticos normalizados por dia/mês/vídeo. O manifesto carrega hashes e cobertura, não respostas contendo segredos.

Alternativa rejeitada: SQLite único mutável, pois snapshots por dia precisam ser auditáveis para futuras comparações.

### APIs, escopos e limites explícitos

Usar YouTube Data API para metadados de canal/uploads/vídeos e YouTube Analytics API para dados de desempenho que forem autorizados. Solicitar somente escopos de leitura necessários, sem o escopo monetário. Paginar até exaurir os uploads acessíveis, com limite configurável seguro e registro de cobertura.

Alternativa rejeitada: raspar YouTube Studio ou inventar uma classificação de viralidade; ambos seriam instáveis ou fora do escopo.

## Risks / Trade-offs

- [Canais grandes tornam a coleta longa ou consomem cota] → paginação, limite configurável, progresso e manifesto de cobertura.
- [Dados analíticos podem atrasar/variar por relatório] → registrar data, fonte e ausências sem inferência.
- [Reorganização visual pode afetar a sessão] → testes de preservação de session state e nenhuma alteração no pipeline.
- [Arquivos podem acumular dados locais] → documentar retenção e não registrar segredos.

## Migration Plan

1. Adicionar a navegação e manter o destino de edição funcional sem alterar o pipeline.
2. Mover o gerenciamento OAuth para seu destino, preservando `input/youtube/`.
3. Criar o coletor e o arquivo datado com testes simulados de paginação, permissão e falha.
4. Em rollback, remover os destinos novos preserva os arquivos locais e a geração volta ao layout anterior.
