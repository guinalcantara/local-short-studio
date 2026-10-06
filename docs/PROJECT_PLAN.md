# Local Short Studio — arquitetura atual

**Estado:** versão operacional baseada em roteiro JSON + ZIP de imagens, com compatibilidade para uma imagem por cena, múltiplos planos sincronizados, transições configuráveis e uma trilha local opcional por Short. A publicação em plataformas e a geração local de imagens permanecem fora do fluxo ativo.

## Objetivo

Receber cenas já ilustradas, gerar narração local em português brasileiro com Kokoro ou Chatterbox, aplicar movimento de câmera simulado, transições narrativas entre cenas, legendas opcionais e exportar um MP4 vertical pronto para revisão.

## Fluxo ativo

```text
JSON + imagens_cenas.zip
        ↓
validação de esquema e ZIP seguro
        ↓
resolução opcional da faixa no catálogo local e verificação do SHA-256
        ↓
Kokoro pt-BR ou Chatterbox PT-BR em CUDA (um bloco por cena)
        ↓
medição LUFS da narração e ganho conservador da faixa catalogada
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

O modelo ativo preserva título, perfil, voz, velocidade, estilo visual, legendas, música e cenas. `soundtrack` contém somente um `track_id` seguro e `volume_percent` inteiro de 0 a 12; ele é opcional, vale para o Short inteiro e não pode coexistir com `music_path`. Cada cena contém `id`, `narration`, `image_path`, `motion`, o `seed` opcional histórico, `shots` opcional e `transition_to_next` opcional, exceto na última cena. Cada plano contém apenas `image_path`, `start_phrase` opcional e `motion` opcional. `image_prompt` foi removido e chaves desconhecidas são rejeitadas.

O catálogo versão 1 e seus MP3s ficam em `assets/music_library/` e são incorporados à imagem em `/workspace/assets/music_library/`. Assim, `soundtrack.track_id` é resolvido automaticamente sem instalação adicional. Se existir, `input/music_library/` funciona como override local intencional; `MUSIC_LIBRARY_DIR` define o fallback da imagem. IDs e caminhos precisam ser únicos; cada MP3 deve ser um arquivo regular confinado a `faixas/`, com tamanho aceitável e hash esperado. Somente `editorial_candidate` pode ser selecionada. O volume declarado pela IA precisa coincidir com a recomendação, salvo zero para silêncio explícito; a interface pode reduzi-lo temporariamente. Metadados `unverified` geram aviso e nunca são convertidos em comprovação de licença.

Depois do TTS, a intensidade integrada da voz é medida. Para música catalogada, o ganho linear é limitado por `min(volume_percent/100, 10**((voice_lufs-20-music_lufs)/20), 10**((-38-music_lufs)/20))`, sem amplificação acima da recomendação. A mixagem usa fades curtos, loop/corte na duração exata e limitador contra clipping. Música manual e `music_path` mantêm o caminho legado.

As fronteiras visuais aceitam corte seco, dissolvência ou passagem pelo preto. Fades usam duração entre 0,15 e 0,45 segundo ou o padrão do perfil; projetos sem configuração preservam a dissolvência legada. A duração é convertida em frames e o renderer protege ao menos três frames do primeiro plano da cena de entrada depois do efeito. O áudio não recebe fade nem pausa adicional.

A narração completa de cada cena é gerada em uma única chamada normal do mecanismo de voz, sem pausa fixa inserida entre frases. O padding curto continua existindo somente entre cenas. Quando há `shots`, o Whisper roda mesmo sem legendas visuais; somente correspondências lexicais realmente observadas podem determinar um corte. As legendas opcionais usam Montserrat ExtraBold em maiúsculas, até três palavras por bloco, entrada em pop e posição/tamanho ajustáveis pela interface sem alterar o JSON.

O bloco opcional `youtube` contém somente metadados validados e é preservado na exportação. Não há OAuth, upload, publicação, agendamento ou chamadas à API.

## Perfil de saída

`short_vertical` é ativo: 1080×1920, 30 fps, H.264/AAC. `video_landscape` continua configurado e desativado para permitir a evolução futura sem mudar o contrato de cenas.

## Critérios da versão

1. `docker compose up --build -d` inicia o app sem ComfyUI.
2. JSON e ZIP inválidos bloqueiam a geração com mensagens úteis.
3. Todas as imagens referenciadas pelos planos são validadas antes da voz e copiadas apenas para a pasta da execução.
4. O mecanismo escolhido usa CUDA sequencialmente para todas as falas; Kokoro e Chatterbox não são usados ao mesmo tempo.
5. FFmpeg gera MP4 vertical com cortes secos entre planos e transições `cut`, `crossfade` ou `fade_black` entre cenas, preservando movimentos, áudio e legendas opcionais configuráveis.
6. Metadados `youtube` são aceitos, validados e preservados sem publicação.
7. Uma faixa catalogada é resolvida antes do TTS, não altera os tempos visuais ou da voz e gera `soundtrack_used.json` sem caminhos do host.
8. Testes cobrem esquema, catálogo, ganho LUFS, voz por bloco, alinhamento lexical, segurança do ZIP, transições mistas e renderização da timeline.

## Próximas etapas, não implementadas

- integração autorizada de publicação após revisão da API oficial;
- reprocessamento seletivo de uma cena;
- ativação do perfil horizontal;
- eventual integração opcional de geração de imagens, sem torná-la dependência do fluxo principal.
## Whisper na sincronização

Quando as legendas estão ativas ou há múltiplos planos, o fluxo inclui uma etapa de Whisper local entre a narração e o FFmpeg. Uma única transcrição extrai timestamps por palavra do WAV final e alimenta tanto os cortes visuais quanto os arquivos ASS/SRT e o burn-in progressivo das legendas.
