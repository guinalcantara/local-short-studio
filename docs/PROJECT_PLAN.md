# Local Short Studio — arquitetura atual

**Estado:** versão operacional baseada em roteiro JSON + ZIP de imagens, com compatibilidade para uma imagem por cena e suporte a múltiplos planos sincronizados. A publicação em plataformas e a geração local de imagens permanecem fora do fluxo ativo.

## Objetivo

Receber cenas já ilustradas, gerar narração local em português brasileiro com Kokoro ou Chatterbox, aplicar movimento de câmera simulado, crossfades, legendas opcionais e exportar um MP4 vertical pronto para revisão.

## Fluxo ativo

```text
JSON + imagens_cenas.zip
        ↓
validação de esquema e ZIP seguro
        ↓
Kokoro pt-BR ou Chatterbox PT-BR em CUDA (um bloco por cena)
        ↓
Whisper quando houver legendas ou múltiplos planos
        ↓
FFmpeg: cortes entre planos, pan/zoom, transições entre cenas, legendas opcionais
        ↓
MP4 9:16 + intermediários
```

O app não gera imagens. Cada `image_path` é obrigatório e aponta para um basename no ZIP. Cenas antigas usam uma imagem; cenas novas podem declarar de 2 a 4 `shots`, com o primeiro plano igual ao `image_path` da cena e os demais ancorados por `start_phrase`. O validador aceita imagens na raiz ou em uma única subpasta, bloqueia ZIPs perigosos e mantém o mapeamento cena-imagem sem extrair caminhos controlados pelo arquivo.

## Hardware e serviços

- Windows + Docker Desktop + WSL 2;
- RTX 2060 de 6 GB para os mecanismos de voz/CUDA;
- Ryzen 5 5600G e 16 GB de RAM;
- FFmpeg no container app, com NVENC quando disponível e libx264 como caminho compatível;
- app Streamlit como único serviço necessário no Compose padrão;
- ComfyUI/Stable Diffusion mantido somente em perfil Docker legado opcional.

Os serviços não carregam modelo de imagem no fluxo atual. O cache de Kokoro permanece montado em `models/kokoro/`.

## Contrato de entrada

O modelo ativo preserva título, perfil, voz, velocidade, estilo visual, legendas, música e cenas. Cada cena contém `id`, `narration`, `image_path`, `motion`, o `seed` opcional histórico e `shots` opcional. Cada plano contém apenas `image_path`, `start_phrase` opcional e `motion` opcional. `image_prompt` foi removido e chaves desconhecidas são rejeitadas.

A narração completa de cada cena é gerada em uma única chamada normal do mecanismo de voz, sem pausa fixa inserida entre frases. O padding curto continua existindo somente entre cenas. Quando há `shots`, o Whisper roda mesmo sem legendas visuais; somente correspondências lexicais realmente observadas podem determinar um corte.

O bloco opcional `youtube` contém somente metadados validados e é preservado na exportação. Não há OAuth, upload, publicação, agendamento ou chamadas à API.

## Perfil de saída

`short_vertical` é ativo: 1080×1920, 30 fps, H.264/AAC. `video_landscape` continua configurado e desativado para permitir a evolução futura sem mudar o contrato de cenas.

## Critérios da versão

1. `docker compose up --build -d` inicia o app sem ComfyUI.
2. JSON e ZIP inválidos bloqueiam a geração com mensagens úteis.
3. Todas as imagens referenciadas pelos planos são validadas antes da voz e copiadas apenas para a pasta da execução.
4. O mecanismo escolhido usa CUDA sequencialmente para todas as falas; Kokoro e Chatterbox não são usados ao mesmo tempo.
5. FFmpeg gera MP4 vertical com cortes secos entre planos, crossfade somente entre cenas, movimentos, áudio e legendas opcionais.
6. Metadados `youtube` são aceitos, validados e preservados sem publicação.
7. Testes cobrem esquema, voz por bloco, alinhamento lexical, segurança do ZIP e renderização da timeline.

## Próximas etapas, não implementadas

- integração autorizada de publicação após revisão da API oficial;
- reprocessamento seletivo de uma cena;
- ativação do perfil horizontal;
- eventual integração opcional de geração de imagens, sem torná-la dependência do fluxo principal.
## Whisper na sincronização

Quando as legendas estão ativas ou há múltiplos planos, o fluxo inclui uma etapa de Whisper local entre a narração e o FFmpeg. Uma única transcrição extrai timestamps por palavra do WAV final e alimenta tanto os cortes visuais quanto os arquivos ASS/SRT e o burn-in progressivo das legendas.
