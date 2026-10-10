## Why

A coleta analítica solicita uma combinação `day,video` que a YouTube Analytics API não oferece para relatórios de canal. Com a API e o OAuth corretos, a coleta falha com HTTP 400 e não produz o arquivo local esperado.

## What Changes

- Substituir a consulta incompatível por consultas suportadas, uma para cada vídeo acessível, usando `day` como dimensão e `video==<id>` como filtro.
- Preservar os dados por dia/vídeo no snapshot, com manifesto que registra a cobertura e os vídeos cujas métricas não foram devolvidas.
- Melhorar a mensagem para uma consulta incompatível, sem confundi-la com problema de OAuth ou API desativada.

## Capabilities

### New Capabilities

- `youtube-analytics-video-query`: consultas Analytics por vídeo compatíveis com a matriz de relatórios do YouTube e com cobertura local explícita.

### Modified Capabilities

- Nenhuma.

## Impact

- `app/youtube_archive.py` e seus testes de mocks da Analytics API.
- Documentação de cobertura/limites do arquivo analítico.
- Não afeta geração de Shorts, JSON, ZIP, renderização, OAuth de publicação ou upload.
