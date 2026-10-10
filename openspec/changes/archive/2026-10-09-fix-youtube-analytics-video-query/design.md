## Context

Veja `proposal.md`. O coletor atual usa `day,video` como dimensões em uma única consulta de canal, mas a documentação da Analytics API aceita `video` como filtro nesses relatórios. O arquivo precisa manter métricas por vídeo/dia e snapshots imutáveis.

## Goals / Non-Goals

**Goals:**

- Consultar combinações Analytics aceitas para cada vídeo acessível e conservar a associação vídeo/dia.
- Registrar cobertura por vídeo e falhas de relatório de modo honesto.
- Manter metadados, armazenamento local e publicação inalterados.

**Non-Goals:**

- Adicionar métricas de receita, alterar escopos OAuth, fazer sincronização automática ou modificar a geração de Shorts.

## Decisions

### Consulta por vídeo com filtro e dimensão `day`

Para cada ID recuperado da playlist, consultar `reports.query` com `ids=channel==MINE`, `filters=video==<id>`, `dimensions=day` e o conjunto de métricas não monetárias compatível. Cada resposta recebe o ID do vídeo antes de ser persistida.

Alternativa rejeitada: usar `video` como dimensão; a API devolve HTTP 400 para essa combinação em relatórios de canal.

### Cobertura parcial explícita

Uma resposta válida sem linhas representa ausência de dados, não erro. Uma falha de API em um vídeo deve ficar registrada no manifesto e tornar a cobertura analítica incompleta, sem falsificar métricas dos demais vídeos. Falhas que impedirem a consulta inicial do canal continuam abortando o snapshot sem diretório final.

Alternativa rejeitada: abortar toda coleta para um único vídeo; isso descarta dados válidos e não melhora a recuperação.

## Risks / Trade-offs

- [Mais chamadas para canais grandes] → progresso por vídeo, limite existente de páginas e cobertura registrada no manifesto.
- [Métrica indisponível para um vídeo/período] → tratar como ausência documentada, sem estimativa.
- [Mudança futura na matriz de relatórios] → testes de requisição suportada e mensagem de erro específica.

## Migration Plan

1. Corrigir as consultas e os testes simulados.
2. Reconstruir o container e executar a suíte.
3. Snapshots que falharam antes não precisam de migração; uma nova coleta cria um snapshot correto. Em rollback, restaurar a consulta anterior não altera snapshots existentes.
