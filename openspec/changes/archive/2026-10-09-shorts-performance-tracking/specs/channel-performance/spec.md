## Purpose

Permitir acompanhar localmente o desempenho de Shorts e comparar hipóteses editoriais com snapshots manuais, preservando privacidade, compatibilidade e limites de inferência.

## ADDED Requirements

### Requirement: Local video registration and immutable production snapshot
O sistema SHALL permitir cadastrar manualmente um vídeo antigo ou acompanhar explicitamente um Short disponível na interface. Cada registro MUST possuir um ID local estável, título e identificador de canal sem e-mail; os demais metadados editoriais são opcionais. Quando houver origem renderizada/publicada, o sistema MUST congelar apenas escolhas efetivas comprovadas daquela versão, sem reescrever o snapshot após edições posteriores do projeto.

#### Scenario: Cadastro manual de vídeo antigo
- **WHEN** o usuário informa título, canal e características editoriais sem projeto nem MP4 local
- **THEN** o sistema cria um registro persistente que continua utilizável se pastas de render forem removidas.

#### Scenario: Acompanhar resultado disponível
- **WHEN** o usuário escolhe acompanhar um MP4 final disponível na interface
- **THEN** o sistema pré-preenche somente dados comprovados, registra o hash ou vínculo disponível e não copia áudio de referência, caminhos privados, tokens ou credenciais.

#### Scenario: Prevenção de duplicidade
- **WHEN** o usuário tenta salvar outro registro com o mesmo ID de vídeo do YouTube ou com o mesmo vínculo de versão aplicável
- **THEN** o sistema rejeita a duplicidade e preserva registros de versões diferentes como itens distintos.

### Requirement: Manual cumulative performance snapshots
O sistema SHALL permitir várias medições identificadas e editáveis por vídeo. Cada medição MUST representar um snapshot cumulativo na data/hora de coleta e registrar horizonte declarado de 48 horas, 7 dias ou personalizado.

#### Scenario: Registrar 48 horas e 7 dias
- **WHEN** o usuário salva uma medição de 48 horas e depois uma de 7 dias para o mesmo vídeo
- **THEN** o histórico mostra ambas separadamente e não soma seus valores para calcular resultado do vídeo.

#### Scenario: Corrigir medição existente
- **WHEN** o usuário edita e salva novamente uma medição existente
- **THEN** o sistema atualiza o mesmo ID sem criar outro snapshot.

### Requirement: Metric validation and temporal clarity
Campos vazios SHALL significar dado desconhecido, não zero. Contagens MUST ser inteiras não negativas, tempos MUST ser não negativos, duração do vídeo MUST ser positiva quando informada e valores numéricos MUST ser finitos. Percentual que continuou assistindo MUST ficar entre zero e cem; percentual médio assistido MAY superar cem. O sistema MUST apresentar e receber datas em America/Sao_Paulo por padrão e armazenar instantes inequivocamente.

#### Scenario: Dados ausentes e percentuais acima de cem
- **WHEN** o usuário deixa uma métrica vazia ou informa percentual médio assistido de 115
- **THEN** o primeiro valor permanece desconhecido e o segundo é aceito sem ser limitado a cem.

#### Scenario: Idade real desconhecida
- **WHEN** uma medição não pode ser relacionada a uma data/hora de publicação válida
- **THEN** o sistema exibe idade real como desconhecida e não a apresenta como uma coleta exata de 48 horas ou 7 dias.

### Requirement: Comparable result table and group analysis
O sistema SHALL exibir tabela, detalhe histórico, filtros por canal, tema, série, tipo de gancho, formato e faixa de duração, além de comparações por grupo. Cada comparação MUST escolher no máximo uma medição elegível por vídeo usando horizonte declarado, idade real e tolerância temporal visível. Dados ausentes ou fora da tolerância MUST ficar fora de agregações padronizadas, sem serem convertidos em zero.

#### Scenario: Seleção de snapshot comparável
- **WHEN** o usuário compara resultados de sete dias com uma tolerância temporal definida
- **THEN** o sistema mostra a medição escolhida por vídeo, sua idade real, horizonte declarado e exclui medições sem idade ou fora da tolerância.

#### Scenario: Medianas com amostras parciais
- **WHEN** um grupo possui valores ausentes em uma das métricas
- **THEN** o sistema mostra a quantidade de vídeos que contribuiu para aquela métrica e calcula a mediana somente com valores válidos.

### Requirement: Transparent derived metrics and hypotheses
O sistema SHALL calcular inscritos por mil visualizações engajadas somente como `inscritos_ganhos / visualizacoes_engajadas * 1000` quando ambos os campos existirem e o denominador for maior que zero. O sistema MUST permitir registrar o que foi aprendido, próximo teste, variável principal e como comparar. Sugestões determinísticas MUST identificar amostra e valores usados, respeitar mínimo configurável e declarar dados insuficientes em vez de alegar que um formato é melhor.

#### Scenario: Denominador incompatível
- **WHEN** visualizações engajadas estão ausentes ou são zero
- **THEN** inscritos por mil visualizações engajadas aparece como sem dados e não usa visualizações totais como substituto.

#### Scenario: Evidência insuficiente
- **WHEN** um grupo possui menos vídeos que o mínimo configurado
- **THEN** o sistema informa dados insuficientes e não produz conclusão de superioridade ou score de viralização.

### Requirement: Isolation from production and publication flows
A área de resultados SHALL funcionar sem GPU, modelos de voz, OAuth ou serviços externos. Seus dados MUST permanecer fora do JSON portátil, ZIP de imagens, caches de render, registros de publicação e diretórios de credenciais. Uma falha ao salvar ou consultar resultados MUST não invalidar TTS, Whisper, imagens, renders nem alterar um upload já concluído.

#### Scenario: Uso sem OAuth ou CUDA
- **WHEN** o usuário abre Resultados do canal em um ambiente sem conta OAuth conectada e sem GPU disponível
- **THEN** consegue cadastrar vídeos, registrar medições e consultar o painel local.

#### Scenario: Falha do armazenamento analítico
- **WHEN** uma operação de analytics falha depois que um Short foi renderizado ou publicado
- **THEN** o MP4 e o registro de publicação existentes permanecem inalterados e nenhum novo envio é disparado.
