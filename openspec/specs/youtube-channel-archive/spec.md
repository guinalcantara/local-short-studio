# youtube-channel-archive Specification

## Purpose

Construir um arquivo local, auditável e organizado por data dos metadados e dados não monetários que a conta autorizada do YouTube disponibiliza para o canal e seus vídeos.

## Requirements

### Requirement: Explicit per-account channel collection
O sistema SHALL permitir selecionar uma conta conectada e iniciar explicitamente uma coleta do canal. A coleta MUST buscar todos os uploads acessíveis por paginação e os metadados/estatísticas não monetários disponíveis para o canal e cada vídeo; abrir a tela MUST NOT iniciar acesso externo.

#### Scenario: Coleta solicitada pelo usuário
- **WHEN** o usuário seleciona uma conta e confirma a coleta
- **THEN** o sistema consulta somente os recursos autorizados daquela conta, informa progresso e apresenta um resumo da coleta concluída.

### Requirement: Dated local archive with provenance
Cada coleta SHALL gerar um mapeamento persistente sob uma raiz de arquivo analítico do projeto, segregado por identificador seguro de conta e ano/mês/dia. O arquivo MUST conter manifesto com origem, instante, versão de esquema, limites/paginação e cobertura, além de dados normalizados de canal e vídeos. Tokens, refresh tokens, cookies, e-mails completos e segredos MUST NOT ser arquivados.

#### Scenario: Nova coleta no mesmo dia
- **WHEN** o usuário executa mais de uma coleta para a mesma conta no mesmo dia
- **THEN** o sistema preserva snapshots distintos e identificáveis sem sobrescrever a evidência anterior.

### Requirement: Honest API coverage and safe failures
O sistema MUST registrar como indisponível todo campo que a API não retornar e informar permissão insuficiente, cota, atraso ou falha de rede sem fabricar dados. Falhas MUST NOT modificar JSON/ZIP do projeto, cache, MP4, publicações ou credenciais existentes.

#### Scenario: Conta sem escopo analítico
- **WHEN** a conta selecionada não tiver a permissão de leitura necessária
- **THEN** o sistema explica a reconexão exigida e não cria arquivo parcial enganoso.

#### Scenario: Dados com atraso
- **WHEN** o YouTube não retornar dados completos para o período ou vídeo
- **THEN** o manifesto registra a cobertura observada e os campos ausentes permanecem desconhecidos.
