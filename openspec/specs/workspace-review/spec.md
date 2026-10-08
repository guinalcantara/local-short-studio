# workspace-review Specification

## Purpose

Permitir revisão persistente e reprocessamento seletivo sem alterar o fluxo de geração original quando esse recurso não for escolhido.

## Requirements

### Requirement: Explicit persistent workspace
O sistema SHALL criar um workspace persistente somente quando o usuário salvar o projeto para revisão, abrir um projeto salvo ou solicitar uma prévia. O manifesto MUST preservar projeto efetivo, imagens usadas, configurações de execução e hashes de artefatos sem exportar segredos.

#### Scenario: Retomar revisão
- **WHEN** o usuário abre um workspace salvo após reiniciar a interface ou o container
- **THEN** o sistema restaura o JSON efetivo e recria um ZIP somente com as imagens referenciadas.

### Requirement: Selective artifact reuse
O sistema SHALL validar os artefatos por hash e MUST reutilizar áudio, alinhamento e render visual que permaneçam válidos após uma edição.

#### Scenario: Alteração apenas de texto
- **WHEN** a narração de uma única cena é alterada
- **THEN** o sistema refaz o áudio e as dependências dessa cena, preservando os artefatos válidos das demais.

#### Scenario: Alteração apenas de imagem ou câmera
- **WHEN** o usuário altera imagem, enquadramento, âncora, transição, legenda ou música
- **THEN** o sistema preserva a voz válida sempre que a alteração não mudar sua dependência.

### Requirement: Real hook preview
O sistema SHALL oferecer uma prévia real da primeira cena em 540×960 ou 1080×1920, usando a voz, imagens, câmera, música e legendas efetivas. A prévia MUST permanecer fora do fluxo de publicação.

#### Scenario: Prévia seguida de geração final
- **WHEN** o usuário gera uma prévia e depois o Short completo sem alterar a primeira cena
- **THEN** o sistema reaproveita o áudio e o alinhamento válidos da primeira cena.
