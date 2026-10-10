## Purpose

Consultar métricas não monetárias por vídeo e dia com relatórios suportados, preservando cobertura auditável no arquivo local do canal.

## ADDED Requirements

### Requirement: Supported daily analytics per accessible video
O sistema SHALL consultar métricas analíticas não monetárias por dia para cada vídeo acessível usando somente combinações de relatório suportadas pela YouTube Analytics API. A consulta MUST identificar cada linha pelo vídeo correspondente sem enviar uma combinação de dimensões não suportada.

#### Scenario: Relatório diário por vídeo suportado
- **WHEN** a coleta tiver vídeos acessíveis e a Analytics API aceitar os relatórios daquele canal
- **THEN** o sistema salva as métricas retornadas identificadas por vídeo e dia sem enviar uma combinação de dimensões não suportada.

### Requirement: Honest per-video analytics coverage
O sistema MUST registrar dados ausentes ou falha de relatório por vídeo como cobertura incompleta, sem fabricar métricas e sem confundir uma consulta incompatível com falha de OAuth. Falhas MUST NOT modificar JSON/ZIP do projeto, cache, MP4, publicações ou credenciais existentes.

#### Scenario: Consulta analítica incompatível
- **WHEN** a Analytics API rejeitar uma combinação de relatório não suportada
- **THEN** o sistema informa que a consulta analítica precisa de ajuste, sem atribuir a falha incorretamente ao OAuth nem criar snapshot final.

#### Scenario: Vídeo sem linha analítica
- **WHEN** a consulta válida de um vídeo não retornar linhas para o período
- **THEN** o manifesto registra a ausência observada e o snapshot não inventa valores para esse vídeo.
