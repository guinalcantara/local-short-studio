# content-authoring Specification

## Purpose

Manter um prompt normativo para gerar roteiros e imagens compatíveis com o Local Short Studio, preservando o padrão editorial já adotado.

## Requirements

### Requirement: Default editorial target
Quando o usuário informar somente um tema, o prompt SHALL orientar roteiros de 55 a 70 segundos, 125 a 145 palavras faladas, seis a oito cenas e dois planos visuais por cena como padrão.

#### Scenario: Tema sem duração
- **WHEN** o usuário informa apenas o título ou tema de um Short
- **THEN** a resposta final usa o alvo editorial padrão e informa a duração apenas como estimativa.

#### Scenario: Pedido editorial explícito
- **WHEN** o usuário pede uma duração ou formato diferente
- **THEN** o prompt permite adaptar cenas, palavras e duração sem alterar o padrão para pedidos futuros.

### Requirement: Portable deliverables
O prompt SHALL solicitar exatamente `modelo_projeto.json` e `imagens_cenas.zip`, com imagens reais referenciadas por basenames seguros e sem campos fora do contrato ativo.

#### Scenario: Entrega pronta para upload
- **WHEN** o gerador consegue produzir os arquivos
- **THEN** o JSON e o ZIP podem ser enviados diretamente à interface e passam pelas regras de contrato aplicáveis.

### Requirement: Optional improvements preserve defaults
O prompt MAY orientar câmera explícita, prévia, reutilização excepcional de imagem ou formatos editoriais alternativos, mas MUST tratá-los como extensões opcionais e não mudar os padrões legados de duração, planos ou legendas.

#### Scenario: Câmera não solicitada
- **WHEN** o tema não exige enquadramento controlado
- **THEN** o prompt pode usar o movimento legado e não precisa incluir um bloco `camera`.

### Requirement: Coherent curiosity storytelling with an explicit list exception
Para uma curiosidade solicitada sem formato explícito, o prompt SHALL orientar um roteiro em torno de uma única pergunta, contraste ou descoberta. O gancho MUST ser específico, curto e honesto; o desenvolvimento MUST trazer cedo uma pista ou explicação concreta e fazer cada trecho acrescentar evidência, causa, comparação ou consequência; o encerramento MUST responder claramente à promessa, sem pedido obrigatório de inscrição ou like. O prompt MUST preservar limites vigentes de idioma, palavras, duração estimada, velocidade de voz, formato de saída, placeholders e contrato JSON, e não pode prometer viralização nem inventar fatos, números ou fontes.

#### Scenario: Curiosidade padrão desenvolvida como descoberta
- **WHEN** o usuário fornece somente um tema de curiosidade sem pedir uma lista
- **THEN** o roteiro abre com a pergunta ou contraste pertinente, progride por pistas ou evidências relacionadas e termina com uma resposta clara para a abertura.

#### Scenario: Lista de fatos solicitada explicitamente
- **WHEN** o usuário pede explicitamente uma lista de fatos
- **THEN** o prompt preserva o formato de lista solicitado em vez de forçar uma pergunta central, mantendo os demais limites editoriais e do contrato.
