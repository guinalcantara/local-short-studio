# Local Short Studio — arquitetura atual

**Estado:** versão operacional baseada em roteiro JSON + ZIP de imagens, com prévia real do gancho, revisão persistente por cena, reaproveitamento seletivo de artefatos, câmera com foco por plano, transições configuráveis, trilha local opcional e publicação explícita no YouTube por conta OAuth local. A geração local de imagens permanece fora do fluxo ativo.

## Objetivo

Receber cenas já ilustradas, gerar narração local em português brasileiro com Kokoro ou Chatterbox, permitir revisar o gancho e cada cena, aplicar câmera com foco e zoom ou o movimento legado, usar transições narrativas entre cenas, legendas opcionais e exportar um MP4 vertical pronto para revisão.

## Fluxo ativo

```text
JSON + imagens_cenas.zip
        ↓
validação de esquema e ZIP seguro
        ↓
projeto persistente + manifesto de artefatos locais
        ↓
resolução opcional da faixa no catálogo local e verificação do SHA-256
        ↓
Kokoro pt-BR ou Chatterbox PT-BR em CUDA, por cena e de modo sequencial
        ↓
Whisper local por cena quando houver legendas ou múltiplos planos
        ↓
prévia opcional da primeira cena em 540×960 ou 1080×1920
        ↓
timeline e render visual por cena, com reaproveitamento seletivo
        ↓
montagem final: câmera/pan/zoom, transições, legendas, medição LUFS e música
        ↓
MP4 9:16 + intermediários persistentes
        ↓
seleção explícita de conta OAuth + confirmação
        ↓
upload resumível opcional para o YouTube
```

O app não gera imagens. Cada `image_path` é obrigatório e aponta para um basename no ZIP. Cenas podem usar uma imagem ou declarar de 2 a 4 `shots`, com o primeiro plano igual ao `image_path` da cena e os demais ancorados por `start_phrase`. O validador aceita imagens na raiz ou em uma única subpasta, bloqueia ZIPs perigosos e mantém o mapeamento cena-imagem sem extrair caminhos controlados pelo arquivo. Em regra, os planos usam imagens distintas; a mesma imagem só pode ser reutilizada na mesma cena quando as câmeras efetivas dos planos são explícitas e diferentes.

## Hardware e serviços

- Windows + Docker Desktop + WSL 2;
- RTX 2060 de 6 GB para os mecanismos de voz/CUDA;
- Ryzen 5 5600G e 16 GB de RAM;
- FFmpeg no container app, com NVENC quando disponível e libx264 como caminho compatível;
- app Streamlit como único serviço necessário no Compose padrão;
- ComfyUI/Stable Diffusion mantido somente em perfil Docker legado opcional.

Os serviços não carregam modelo de imagem no fluxo atual. O cache de Kokoro permanece montado em `models/kokoro/`.

## Contrato de entrada

O modelo ativo preserva título, perfil, voz, velocidade, estilo visual, legendas, música e cenas. `soundtrack` contém somente um `track_id` seguro e `volume_percent` inteiro de 0 a 12; ele é opcional, vale para o Short inteiro e não pode coexistir com `music_path`. Cada cena contém `id`, `narration`, `image_path`, `motion`, `camera` opcional, o `seed` opcional histórico, `shots` opcional e `transition_to_next` opcional, exceto na última cena. Cada plano contém `image_path`, `start_phrase` opcional, `motion` opcional e `camera` opcional. `image_prompt` foi removido e chaves desconhecidas são rejeitadas.

O bloco `camera` exige `start` e `end` completos quando existir. Cada posição contém `focus_x` e `focus_y` finitos de 0 a 1, na imagem original depois da orientação EXIF, e `zoom` finito de 1.00 a 1.35 relativo ao enquadramento vertical mínimo. `easing` é opcional, assume `quintic` e `quintic` é o único valor aceito. A precedência é câmera do plano, câmera da cena, movimento legado do plano e movimento legado da cena; uma câmera explícita substitui o movimento legado em vez de somar efeitos e continua ativa quando a interface desliga os movimentos legados. Reutilizar uma imagem em dois planos da mesma cena só é válido quando ambos recebem câmeras efetivas, explícitas e diferentes. O arquivo continua único no ZIP.

O catálogo versão 1 e seus MP3s ficam em `assets/music_library/` e são incorporados à imagem em `/workspace/assets/music_library/`. Assim, `soundtrack.track_id` é resolvido automaticamente sem instalação adicional. Se existir, `input/music_library/` funciona como override local intencional; `MUSIC_LIBRARY_DIR` define o fallback da imagem. IDs e caminhos precisam ser únicos; cada MP3 deve ser um arquivo regular confinado a `faixas/`, com tamanho aceitável e hash esperado. Somente `editorial_candidate` pode ser selecionada. O volume declarado pela IA precisa coincidir com a recomendação, salvo zero para silêncio explícito; a interface pode reduzi-lo temporariamente. Metadados `unverified` geram aviso e nunca são convertidos em comprovação de licença.

Depois do TTS, a intensidade integrada da voz é medida. Para música catalogada, o ganho linear é limitado por `min(volume_percent/100, 10**((voice_lufs-20-music_lufs)/20), 10**((-38-music_lufs)/20))`, sem amplificação acima da recomendação. A mixagem usa fades curtos, loop/corte na duração exata e limitador contra clipping. Música manual e `music_path` mantêm o caminho legado.

As fronteiras visuais aceitam corte seco, dissolvência ou passagem pelo preto. Fades usam duração entre 0,15 e 0,45 segundo ou o padrão do perfil; projetos sem configuração preservam a dissolvência legada. A duração é convertida em frames e o renderer protege ao menos três frames do primeiro plano da cena de entrada depois do efeito. O áudio não recebe fade nem pausa adicional.

A narração completa de cada cena é gerada em uma única chamada normal do mecanismo de voz, sem pausa fixa inserida entre frases. O padding curto continua existindo somente entre cenas. Áudio, alinhamento lexical local, timeline e render visual são artefatos por cena; a montagem desloca os timestamps locais conforme a duração acumulada atual. Quando há `shots`, o Whisper roda mesmo sem legendas visuais; somente correspondências lexicais realmente observadas podem determinar um corte. As legendas opcionais usam Montserrat ExtraBold em maiúsculas, até três palavras por bloco, entrada em pop e posição/tamanho ajustáveis pela interface sem alterar o JSON.

A prévia do gancho processa apenas a primeira cena e usa voz, imagens, câmera, música e legendas reais. Ela não recebe transição para a segunda cena, não entra no seletor de publicação e pode reaproveitar seu áudio e alinhamento na geração final. O projeto e seu manifesto versionado permanecem em volume local persistente; o cache é validado por hashes e dependências reais antes de reutilização. Alterar texto ou voz invalida a cena correspondente; alterar imagem, câmera, âncora, transição, legenda ou música preserva o TTS quando possível. Configurações de execução e referências vocais locais não entram no JSON portátil ou no ZIP exportado.

O bloco opcional `youtube` contém os metadados validados para a publicação. Depois de renderizar um MP4, a interface lista apenas contas OAuth conectadas localmente, começa sem conta selecionada e exige confirmação explícita antes do upload. O token e o JSON do cliente OAuth ficam em `input/youtube/`, fora do Git; o registro de publicação salvo na execução contém apenas ID, URL, canal, horário e hash do MP4. Quando `youtube.captions.enabled` estiver ativo e houver SRT local, a faixa fechada é enviada em SRT ou convertida para VTT. Agendamento, miniatura e publicação em lote continuam fora do escopo.

## Perfil de saída

`short_vertical` é ativo: 1080×1920, 30 fps, H.264/AAC. `video_landscape` continua configurado e desativado para permitir a evolução futura sem mudar o contrato de cenas.

## Resultados locais do canal

O painel **Resultados do canal** é uma aba separada da produção. Ele armazena em `input/analytics/performance.sqlite3` cadastros locais, snapshots cumulativos e hipóteses editoriais, podendo sincronizar sob demanda dados não monetários do canal OAuth explicitamente escolhido. Não altera `VideoProject`, ZIP, cache, MP4 ou registros de publicação; uma falha no painel não bloqueia a renderização nem dispara upload.

As comparações usam uma medição por Short, horizonte declarado e idade real calculada a partir da publicação. Medianas e tamanho de amostra permanecem visíveis, e sugestões são somente descritivas: o produto não promete viralização nem atribui causalidade.

## Critérios da versão

1. `docker compose up --build -d` inicia o app sem ComfyUI.
2. JSON e ZIP inválidos bloqueiam a geração com mensagens úteis.
3. Todas as imagens referenciadas pelos planos são validadas antes da voz e copiadas apenas para a pasta da execução.
4. O mecanismo escolhido usa CUDA sequencialmente para todas as falas; Kokoro e Chatterbox não são usados ao mesmo tempo.
5. `camera` preserva projetos legados, aplica foco/zoom limitado às bordas e respeita sua precedência sobre `motion`.
6. FFmpeg gera MP4 vertical com cortes secos entre planos e transições `cut`, `crossfade` ou `fade_black` entre cenas, preservando câmera/movimentos, áudio e legendas opcionais configuráveis.
7. A prévia do gancho é um vídeo real, não publica, e a geração final reutiliza seu áudio e alinhamento válidos.
8. A revisão por cena persiste projeto e configurações; alterações invalidam somente artefatos dependentes e recalculam offsets globais na montagem.
9. Metadados `youtube` são aceitos, validados, preservados e mapeados para upload opcional por conta OAuth selecionada, inclusive legenda fechada quando solicitada.
10. Uma faixa catalogada é resolvida antes do TTS, não altera os tempos visuais ou da voz e gera `soundtrack_used.json` sem caminhos do host.
11. Testes cobrem esquema, câmera, cache/invalidação, prévia, catálogo, ganho LUFS, voz por bloco, alinhamento lexical, segurança do ZIP, transições mistas e renderização da timeline.

## Próximas etapas, não implementadas

- ativação do perfil horizontal;
- eventual integração opcional de geração de imagens, sem torná-la dependência do fluxo principal.
## Whisper na sincronização

Quando as legendas estão ativas ou há múltiplos planos, o fluxo inclui uma etapa de Whisper local por cena entre a narração e o FFmpeg. As transcrições extraem timestamps locais por palavra, alimentam cortes visuais e são deslocadas somente na montagem final para formar ASS/SRT e o burn-in progressivo das legendas.
