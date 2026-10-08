# project-input Specification

## Purpose

Definir o contrato portátil do roteiro e a ingestão segura das imagens necessárias para produzir um Short local.

## Requirements

### Requirement: Strict portable project contract
O sistema SHALL aceitar projetos JSON estritos com título, perfil vertical ativo, configuração de voz, cenas e metadados opcionais já suportados. Campos desconhecidos ou formatos inválidos MUST ser rejeitados antes da geração.

#### Scenario: Projeto legado válido
- **WHEN** o usuário envia um JSON válido sem os campos opcionais mais recentes
- **THEN** o sistema o valida e mantém o fluxo de geração original compatível.

#### Scenario: Campo desconhecido
- **WHEN** o JSON contém uma chave que não faz parte do contrato ativo
- **THEN** o sistema informa o erro e não inicia voz, Whisper ou renderização.

### Requirement: Visual scenes and shot timing contract
Cada cena SHALL possuir `image_path` com basename seguro. Cenas podem declarar de dois a quatro `shots`; o primeiro MUST repetir a imagem da cena e os demais MUST usar âncoras literais, únicas e ordenadas na narração.

#### Scenario: Plano adicional ancorado
- **WHEN** uma cena possui dois planos e a segunda âncora ocorre uma única vez na narração
- **THEN** o sistema aceita o projeto e usa o timestamp observado da primeira palavra para a troca visual.

#### Scenario: Reuso visual com câmera
- **WHEN** dois planos da mesma cena reutilizam uma imagem e têm câmeras efetivas explícitas diferentes
- **THEN** o sistema aceita o reuso como exceção e mantém um único arquivo no ZIP.

### Requirement: Secure image archive intake
O sistema SHALL aceitar apenas PNG, JPG, JPEG e WebP na raiz ou em uma única subpasta do ZIP. Ele MUST bloquear caminhos absolutos, `..`, symlinks, criptografia, basenames duplicados, limites de tamanho/contagem/resolução e bytes inválidos.

#### Scenario: ZIP seguro e completo
- **WHEN** o ZIP contém todas as imagens referenciadas com basenames seguros e bytes válidos
- **THEN** o sistema valida o mapeamento e copia somente os arquivos efetivamente referenciados.

#### Scenario: ZIP perigoso
- **WHEN** o ZIP contém um symlink, caminho ascendente ou basename duplicado
- **THEN** o sistema o rejeita sem extrair arquivos controlados pelo arquivo.
