# Local Short Studio — arquitetura atual

**Estado:** primeira versão operacional baseada em roteiro JSON + ZIP de imagens. A publicação em plataformas e a geração local de imagens permanecem fora do fluxo ativo.

## Objetivo

Receber cenas já ilustradas, gerar narração local em português brasileiro com Kokoro ou Chatterbox, aplicar movimento de câmera simulado, crossfades, legendas opcionais e exportar um MP4 vertical pronto para revisão.

## Fluxo ativo

```text
JSON + imagens_cenas.zip
        ↓
validação de esquema e ZIP seguro
        ↓
Kokoro pt-BR ou Chatterbox PT-BR em CUDA
        ↓
FFmpeg: pan/zoom, transições, legendas opcionais
        ↓
MP4 9:16 + intermediários
```

O app não gera imagens. Cada `image_path` é obrigatório e aponta para um basename no ZIP. O validador aceita imagens na raiz ou em uma única subpasta, bloqueia ZIPs perigosos e mantém o mapeamento cena-imagem sem extrair caminhos controlados pelo arquivo.

## Hardware e serviços

- Windows + Docker Desktop + WSL 2;
- RTX 2060 de 6 GB para os mecanismos de voz/CUDA;
- Ryzen 5 5600G e 16 GB de RAM;
- FFmpeg no container app, com NVENC quando disponível e libx264 como caminho compatível;
- app Streamlit como único serviço necessário no Compose padrão;
- ComfyUI/Stable Diffusion mantido somente em perfil Docker legado opcional.

Os serviços não carregam modelo de imagem no fluxo atual. O cache de Kokoro permanece montado em `models/kokoro/`.

## Contrato de entrada

O modelo ativo preserva título, perfil, voz, velocidade, estilo visual, legendas, música e cenas. Cada cena contém `id`, `narration`, `image_path`, `motion` e o `seed` opcional histórico. `image_prompt` foi removido e chaves desconhecidas são rejeitadas.

O bloco opcional `youtube` contém somente metadados validados e é preservado na exportação. Não há OAuth, upload, publicação, agendamento ou chamadas à API.

## Perfil de saída

`short_vertical` é ativo: 1080×1920, 30 fps, H.264/AAC. `video_landscape` continua configurado e desativado para permitir a evolução futura sem mudar o contrato de cenas.

## Critérios da versão

1. `docker compose up --build -d` inicia o app sem ComfyUI.
2. JSON e ZIP inválidos bloqueiam a geração com mensagens úteis.
3. As imagens referenciadas são copiadas apenas para a pasta da execução.
4. O mecanismo escolhido usa CUDA sequencialmente para todas as falas; Kokoro e Chatterbox não são usados ao mesmo tempo.
5. FFmpeg gera MP4 vertical com movimentos, transições, áudio e legendas opcionais.
6. Metadados `youtube` são aceitos, validados e preservados sem publicação.
7. Testes cobrem esquema, vozes, segurança do ZIP e renderização.

## Próximas etapas, não implementadas

- integração autorizada de publicação após revisão da API oficial;
- reprocessamento seletivo de uma cena;
- ativação do perfil horizontal;
- eventual integração opcional de geração de imagens, sem torná-la dependência do fluxo principal.
# Whisper na sincronizacao

Quando as legendas estao ativas, o fluxo inclui uma etapa de Whisper local entre a narracao e o FFmpeg. Ela extrai timestamps por palavra do WAV final e alimenta os arquivos ASS/SRT e o burn-in progressivo das legendas.
