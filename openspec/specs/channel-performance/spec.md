# channel-performance Specification

## Purpose

Permitir acompanhar localmente o desempenho de Shorts e comparar hipóteses editoriais com snapshots, preservando privacidade, compatibilidade e limites de inferência.

## Requirements

### Requirement: Local video registration and immutable production snapshot
O sistema SHALL permitir cadastrar manualmente um vídeo antigo ou acompanhar explicitamente um Short disponível. Cada registro MUST possuir ID local estável, título e identificador de canal sem e-mail; campos editoriais são opcionais. Uma origem renderizada/publicada MUST congelar somente escolhas efetivas comprovadas da versão, sem caminhos privados, áudio de referência, tokens ou credenciais.

#### Scenario: Cadastro manual de vídeo antigo
- **WHEN** o usuário informa título, canal e características editoriais sem projeto ou MP4 local
- **THEN** o sistema cria um registro persistente mesmo se as pastas de render forem removidas.

#### Scenario: Prevenção de duplicidade
- **WHEN** o usuário tenta salvar outro registro com o mesmo ID de vídeo do YouTube ou vínculo de versão
- **THEN** o sistema rejeita a duplicidade e preserva versões diferentes como itens distintos.

### Requirement: Cumulative performance snapshots
O sistema SHALL permitir diversas medições identificadas e editáveis por vídeo. Cada medição MUST ser um snapshot cumulativo com data/hora e horizonte declarado de 48 horas, 7 dias ou personalizado; campos vazios SHALL significar desconhecido, e não zero.

#### Scenario: Registrar 48 horas e 7 dias
- **WHEN** o usuário salva uma medição de 48 horas e depois uma de 7 dias para o mesmo vídeo
- **THEN** o histórico mostra ambas separadamente e não soma seus valores.

#### Scenario: Corrigir medição existente
- **WHEN** o usuário edita e salva novamente uma medição existente
- **THEN** o sistema atualiza o mesmo ID sem criar outro snapshot.

### Requirement: Metric validation and temporal clarity
Contagens MUST ser inteiras não negativas, tempos MUST ser não negativos, duração informada MUST ser positiva e números MUST ser finitos. Percentual que continuou assistindo MUST ficar entre zero e cem; percentual médio assistido MAY superar cem. O sistema MUST apresentar datas em America/Sao_Paulo e armazenar instantes inequívocos.

#### Scenario: Dados ausentes e percentuais acima de cem
- **WHEN** o usuário deixa uma métrica vazia ou informa percentual médio assistido de 115
- **THEN** o primeiro valor permanece desconhecido e o segundo é aceito.

#### Scenario: Idade real desconhecida
- **WHEN** uma medição não pode ser relacionada a uma publicação válida
- **THEN** o sistema exibe idade real como desconhecida e a exclui de agregações padronizadas.

### Requirement: Comparable result table and group analysis
O sistema SHALL exibir tabela, histórico, filtros por canal, tema, série, gancho, formato e duração, além de comparações por grupo. Cada comparação MUST escolher no máximo uma medição elegível por vídeo usando horizonte, idade real e tolerância visível. Dados ausentes ou fora da tolerância MUST ficar fora das agregações, sem conversão para zero.

#### Scenario: Seleção de snapshot comparável
- **WHEN** o usuário compara resultados de sete dias com tolerância definida
- **THEN** o sistema mostra a medição escolhida por vídeo, sua idade real e o horizonte declarado.

#### Scenario: Medianas com amostras parciais
- **WHEN** um grupo possui valores ausentes em uma métrica
- **THEN** o sistema mostra a cobertura e calcula a mediana somente com valores válidos.

### Requirement: Transparent derived metrics and hypotheses
O sistema SHALL calcular inscritos por mil visualizações engajadas somente como `inscritos_ganhos / visualizacoes_engajadas * 1000` quando ambos existirem e o denominador for maior que zero. O sistema MUST permitir registrar aprendizado, próximo teste, variável principal e como comparar. Sugestões determinísticas MUST informar amostra e valores usados, respeitar um mínimo configurável e declarar dados insuficientes sem alegar causalidade.

#### Scenario: Denominador incompatível
- **WHEN** visualizações engajadas estão ausentes ou são zero
- **THEN** inscritos por mil engajadas aparece sem dados e não usa visualizações totais.

#### Scenario: Evidência insuficiente
- **WHEN** um grupo possui menos vídeos que o mínimo configurado
- **THEN** o sistema informa dados insuficientes e não produz conclusão de superioridade ou score de viralização.

### Requirement: Isolation from production and publication flows
A área de resultados SHALL funcionar sem GPU, modelos de voz, OAuth ou serviços externos. Seus dados MUST permanecer fora do JSON portátil, ZIP, caches de render, registros de publicação e diretórios de credenciais. Uma falha analítica MUST NOT invalidar TTS, Whisper, imagens, renders ou upload concluído.

#### Scenario: Uso sem OAuth ou CUDA
- **WHEN** o usuário abre Resultados do canal sem conta OAuth conectada e sem GPU
- **THEN** consegue cadastrar vídeos, registrar medições e consultar o painel local.

#### Scenario: Falha do armazenamento analítico
- **WHEN** uma operação analítica falha depois que um Short foi renderizado ou publicado
- **THEN** o MP4 e o registro de publicação permanecem inalterados e nenhum envio é disparado.
