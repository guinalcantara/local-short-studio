## Context

Veja `proposal.md` e as specs desta mudança. A conta OAuth atual já é escolhida explicitamente, mas seus escopos não incluem leitura do YouTube Analytics e a tela de resultados usa somente dados locais manuais.

## Goals / Non-Goals

**Goals:**

- Disponibilizar uma aba independente que sincronize sob demanda vídeos e snapshots de desempenho do canal autorizado.
- Reutilizar o armazenamento local e preservar dados editoriais privados e snapshots de produção existentes.
- Solicitar apenas o escopo não monetário de leitura analítica, exigir reconexão e expor falhas sem afetar publicação.

**Non-Goals:**

- Coleta em segundo plano, agendamento, API de receita, exportação de tokens, upload automático, CSV ou alteração do contrato JSON/ZIP.

## Decisions

### Data API para inventário e Analytics API para desempenho

Listar os vídeos do canal autenticado pela YouTube Data API e consultar snapshots agregados por vídeo na YouTube Analytics API. O primeiro fornece metadados e estatísticas públicas/atuais; o segundo cobre métricas de desempenho como `engagedViews`, `subscribersGained`, `averageViewDuration` e `averageViewPercentage`. A consulta será manual, paginada e limitada, com origem e data registradas.

Alternativa rejeitada: depender apenas de `videos.list`, pois ela não fornece as métricas analíticas necessárias; importar CSV, pois o usuário pediu captura online.

### OAuth incremental com reconexão segura

Adicionar `yt-analytics.readonly` aos escopos locais sem pedir permissão monetária. Tokens que não tenham o novo escopo serão tratados como insuficientes e a interface orientará a reconexão explícita. A confirmação por MP4 continua exclusiva do upload.

Alternativa rejeitada: reutilizar silenciosamente tokens antigos ou ampliar para escopo de receita, por não haver consentimento correspondente.

### Snapshots importados imutáveis e campos locais protegidos

Uma sincronização acrescenta snapshot cumulativo com origem, conta e tempo de coleta, atualizando somente os metadados comprovados do YouTube. A identidade de vídeo do YouTube reconcilia registros; anotações editoriais e dados de produção continuam locais. A persistência analítica não copia respostas brutas, tokens, e-mail ou caminhos privados.

Alternativa rejeitada: sobrescrever o registro inteiro do usuário, pois destruiria hipóteses e comparações locais.

## Risks / Trade-offs

- [Métricas podem ter atraso ou indisponibilidade por tipo de vídeo/período] → mostrar proveniência, instante e indisponibilidade em vez de estimar.
- [Cota ou permissão da API pode falhar] → consultas sob demanda, paginação, mensagens claras e transações locais curtas.
- [Mudou o significado de viewCount do Data API] → distinguir a origem Data API da Analytics API e preferir Analytics para comparações homogêneas.
- [Novo consentimento pode interromper o fluxo esperado] → indicar reconexão antes da sincronização, sem invalidar a publicação já registrada.

## Migration Plan

1. Criar a aba e as migrações analíticas sem modificar dados locais existentes.
2. Solicitar o escopo analítico apenas nas novas conexões; contas antigas continuam listadas, mas precisam reconectar para sincronizar.
3. Validar com respostas simuladas da Data/Analytics API, falhas de permissão e vídeos com métricas parciais.
4. Para rollback, esconder a aba/sincronização preserva SQLite, credenciais e publicações existentes.
