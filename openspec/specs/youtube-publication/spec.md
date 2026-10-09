# youtube-publication Specification

## Purpose

Publicar opcionalmente um MP4 final no YouTube por OAuth local de modo explícito, recuperável e sem expor credenciais.

## Requirements

### Requirement: Explicit account and confirmation
O sistema SHALL listar somente contas OAuth conectadas localmente. A conta selecionada MUST ser escolhida explicitamente tanto para uma sincronização online de resultados quanto para publicação. O sistema MUST exigir confirmação do usuário para o hash exato do MP4 antes do upload; sincronizar resultados MUST NOT publicar ou confirmar upload.

#### Scenario: Sem conta ou confirmação
- **WHEN** não há conta selecionada ou a confirmação não foi marcada
- **THEN** o sistema mantém a publicação desabilitada.

#### Scenario: Conta sem leitura analítica
- **WHEN** o usuário seleciona uma conta conectada sem o consentimento de leitura analítica exigido
- **THEN** o sistema solicita reconexão explícita da conta e não realiza sincronização até a conclusão do novo consentimento.

### Requirement: Local credential confinement
Credenciais OAuth, tokens, refresh tokens, cookies e e-mails completos MUST permanecer exclusivamente em `input/youtube/` e nunca ser copiados para a saída, exportações ou Git.

#### Scenario: Exportação do projeto
- **WHEN** o usuário exporta JSON e ZIP de um workspace
- **THEN** os arquivos não incluem credenciais, tokens ou referência vocal privada.

### Requirement: Resumable variant-safe publication
O sistema SHALL usar upload resumível, impedir reenvio do mesmo MP4 e permitir recuperar uma legenda pendente sem reenviar o vídeo. Registros por hash de MP4 MUST coexistir com o arquivo legado `youtube_publication.json` atualizado para compatibilidade.

#### Scenario: Nova variante final
- **WHEN** um novo MP4 com conteúdo diferente é gerado no mesmo workspace
- **THEN** o sistema exige nova confirmação e preserva o registro da variante anterior.

#### Scenario: Falha na legenda após upload
- **WHEN** o MP4 foi publicado e a faixa de legenda falha
- **THEN** o sistema registra o vídeo e permite uma nova tentativa explícita somente da legenda.
