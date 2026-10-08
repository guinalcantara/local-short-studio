# rendering-output Specification

## Purpose

Produzir um MP4 vertical local com narração pt-BR, imagens fornecidas, cortes sincronizados, transições e legendas opcionais.

## Requirements

### Requirement: Local sequential narration
O sistema SHALL sintetizar cada narração de cena como um bloco contínuo com a voz pt-BR escolhida e MUST usar CUDA quando o mecanismo selecionado a exigir. Kokoro e Chatterbox MUST permanecer mutuamente exclusivos na execução.

#### Scenario: Narração por cena
- **WHEN** o projeto contém várias cenas válidas
- **THEN** o sistema gera ou reaproveita um WAV por cena e preserva as pausas apenas entre cenas.

### Requirement: Timed visual assembly
O sistema SHALL usar Whisper local quando legendas ou múltiplos planos exigirem timestamps por palavra e MUST montar os planos sem cortar o áudio.

#### Scenario: Múltiplos planos com legendas desativadas
- **WHEN** uma cena possui `shots` e as legendas visuais estão desativadas
- **THEN** o sistema ainda alinha a narração para posicionar as trocas de imagem com timestamps observados.

### Requirement: Optional explicit camera
O sistema SHALL aceitar uma câmera opcional por cena ou plano, com foco e zoom inicial/final limitados aos pixels da imagem orientada por EXIF. A câmera do plano MUST prevalecer sobre a câmera da cena e ambas MUST prevalecer sobre `motion` legado.

#### Scenario: Projeto sem câmera
- **WHEN** um projeto existente usa somente `motion`
- **THEN** a renderização conserva o movimento e o resultado do fluxo legado.

#### Scenario: Câmera perto da borda
- **WHEN** o foco explícito aponta para uma borda da imagem
- **THEN** o renderer limita o recorte à área disponível sem criar barras ou pixels fora da imagem.

### Requirement: Vertical final output and sidecars
O sistema SHALL produzir MP4 9:16, aplicar transições configuradas entre cenas, trilha opcional e legendas opcionais. Quando legendas estiverem ativas, MUST salvar os sidecars locais SRT e ASS correspondentes.

#### Scenario: Geração padrão sem workspace
- **WHEN** o usuário clica em Gerar Short sem salvar um workspace ou pedir uma prévia
- **THEN** o sistema usa o pipeline e o layout de saída originais.
