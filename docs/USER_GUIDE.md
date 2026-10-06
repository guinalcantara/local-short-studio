# Guia do usuário

## 1. Preparar os arquivos

Crie um JSON com `title`, `profile`, `voice`, `speech_speed`, `visual_style`, `captions` e `scenes`. Cada cena precisa de:

- `id`: identificador seguro;
- `narration`: texto em português brasileiro;
- `image_path`: basename obrigatório, como `cena_01_gancho.png`;
- `motion`: `slow_push_in`, `slow_pull_out`, `pan_left`, `pan_right`, `pan_up`, `pan_down`, `static` ou `auto`.

O formato legado, sem `shots`, continua usando `image_path` e `motion` como seu único plano. Para mostrar mais de uma imagem durante a mesma fala, acrescente `shots` com 2 a 4 elementos:

- `shots[0].image_path` deve ser exatamente igual ao `image_path` da cena e não usa `start_phrase`;
- cada plano seguinte usa uma imagem distinta e uma `start_phrase` não vazia, contígua e presente uma única vez na narração;
- as âncoras seguem a ordem da narração e não atravessam o fim de uma frase;
- `shot.motion` é opcional; quando ausente, herda o `motion` da cena.

Veja o roteiro real completo em `examples/modelo_projeto.json`.

### Trilha única opcional

Para selecionar uma faixa local para o Short inteiro, acrescente:

```json
"soundtrack": { "track_id": "acting_melodiesinfonie", "volume_percent": 4 }
```

O ID deve existir no catálogo embutido `assets/music_library/catalog.json`, estar marcado como `editorial_candidate` e usar exatamente o volume recomendado; zero é aceito como silêncio explícito. `track_id` aceita apenas letras minúsculas, números e sublinhado; não aceita caminhos. `volume_percent` é inteiro de 0 a 12. Não use `soundtrack` junto com `music_path`.

### Transição para a próxima cena

Em qualquer cena que não seja a última, `transition_to_next` pode escolher:

- `cut`: corte seco; não aceita `duration_seconds`;
- `crossfade`: dissolvência entre as cenas;
- `fade_black`: passagem breve pelo preto, indicada para uma mudança clara de tempo ou assunto.

Para `crossfade` e `fade_black`, `duration_seconds` é opcional e aceita valores de 0,15 a 0,45 segundo. Sem duração, o app usa o valor do perfil; sem o bloco inteiro, mantém a dissolvência legada. Não coloque `transition_to_next` na última cena. A escolha não acrescenta silêncio nem altera `start_phrase`.

O campo `image_prompt` não faz parte do esquema ativo. As imagens já vêm prontas no ZIP. O campo `seed` continua aceito por compatibilidade, mas não é usado para gerar imagens.

Monte `imagens_cenas.zip` com PNG, JPG, JPEG ou WebP. Os arquivos podem estar na raiz ou todos dentro de uma única subpasta. Não use caminhos como `../cena.png` no JSON.

Narrações devem evitar abreviações: escreva “tiranossauro rex”, nunca “T. rex”, “T-Rex” ou “T rex”.

## 2. Iniciar

Na pasta do projeto:

```powershell
docker compose up --build -d
```

Abra `http://localhost:8501`. O serviço padrão é somente o app; ele não depende do ComfyUI nem de checkpoint de Stable Diffusion.

O catálogo já faz parte do projeto e da imagem Docker em `/workspace/assets/music_library/`; não há etapa de instalação. Para testar outra biblioteca sem reconstruir a imagem, crie `input/music_library/` com `catalog.json` e `faixas/`. Quando esse override local existe, ele tem precedência sobre a biblioteca embutida.

## 3. Enviar e validar

Na interface:

1. envie o projeto `.json`;
2. revise o JSON no editor;
3. envie `imagens_cenas.zip`;
4. confira quantidade de cenas e planos, nomes encontrados, imagens ausentes e avisos de imagens extras;
5. só depois escolha a voz e gere.

O ZIP é lido em memória e não é extraído para um caminho controlado pelo arquivo. Caminhos absolutos, `..`, subpastas múltiplas, symlinks, arquivos criptografados, extensões inesperadas, imagens inválidas e limites excedidos bloqueiam a geração.

Projetos com `shots` mostram um aviso de que o Whisper será necessário. Isso ocorre mesmo com as legendas desmarcadas, pois os timestamps reais das palavras determinam as trocas de imagem.

## 4. Mecanismo de voz, música e legendas

No seletor **Mecanismo de narração**, escolha uma alternativa para cada geração. Essa escolha é da interface e não altera o JSON do projeto. A narração completa de cada cena é sintetizada como um bloco contínuo; a pontuação orienta as pausas e não é acrescentada uma pausa fixa entre frases.

### Kokoro pt-BR

O seletor **Voz da narração** oferece somente vozes Kokoro pt-BR:

- Dora — feminina (`pf_dora`);
- Alex — masculina (`pm_alex`);
- Santa — masculina (`pm_santa`).

A voz válida do JSON é selecionada inicialmente; um código inválido volta para Dora. Todas as cenas usam a escolha atual. A velocidade aceita valores de 0.75 a 1.25.

Música é opcional. A interface permite desativá-la, aceitar a faixa do JSON, escolher outro candidato editorial ou enviar um arquivo manual. A opção efetiva é exibida e segue esta precedência: upload selecionado, escolha do catálogo, faixa do JSON, `music_path` legado e sem música. Para uma faixa catalogada, o volume começa na recomendação e só pode ser mantido ou reduzido. A seleção temporária não reescreve `project.json`.

Título, categoria, uso estimado, duração e estado de licença aparecem antes da geração. `license_status: unverified`, URL ausente ou atribuição ausente não comprovam direito de uso; confirme tudo antes de publicar. A renderização local continua disponível para revisão.

Depois da narração, o app mede a voz e pode reduzir a faixa para preservar ao menos vinte LU de distância e um teto aproximado de −38 LUFS durante a fala. A música entra em cerca de 0,5 segundo, sai em cerca de 0,8 segundo e termina junto com o vídeo. Upload manual e `music_path` usam o comportamento legado de volume estático.

Legendas são opcionais: quando ligadas, o vídeo recebe burn-in com Montserrat ExtraBold em maiúsculas, contorno escuro, até três palavras por bloco, entrada em pop e destaque progressivo por palavra. Os controles **Tamanho da fonte da legenda** e **Altura da legenda na tela** são aplicados apenas à geração atual. Na altura, 0% representa a base, 50% o centro e valores maiores movem o texto para cima. Os arquivos `.srt` e `.ass` também são salvos junto para inspeção.

### Chatterbox PT-BR

Chatterbox usa o ajuste dedicado `ResembleAI/Chatterbox-Multilingual-pt-br`, com o idioma `pt`, em CUDA. O primeiro uso baixa os pesos e os componentes compartilhados do Hugging Face; o cache é persistido em `models/kokoro/`, portanto as gerações seguintes não baixam tudo novamente.

Em vez de voz e velocidade do Kokoro, a interface mostra **Expressividade**, **Controle de ritmo** e **Variação**, que são os controles compatíveis com Chatterbox. Se o download, o modelo ou a CUDA falharem, a geração é interrompida com erro; não há troca automática para Kokoro.

O campo **Áudio de referência da sua voz** é opcional. Para reproduzir a identidade vocal, envie um arquivo WAV, MP3, FLAC ou OGG com aproximadamente 5–10 segundos de fala limpa em português brasileiro. Evite música, eco, ruído e outras pessoas no mesmo áudio. A referência é preparada uma vez por geração; o arquivo fica na pasta de áudio da execução e não entra no JSON.

## 5. Saída

O pipeline valida o ZIP, copia somente as imagens usadas para `output/<execução>/images/`, gera um WAV por cena com o mecanismo escolhido em CUDA e então monta o MP4 vertical 1080×1920 a 30 fps com FFmpeg. Planos da mesma cena usam cortes secos nos instantes alinhados; entre cenas, o JSON pode escolher corte seco, dissolvência ou passagem pelo preto. Durante a montagem, a barra informa a cena atual, a quantidade de planos, as cenas concluídas e a etapa final de transições/áudio.

A duração visual do fade é arredondada para frames. Se uma duração explicitamente informada ocupar quase todo o primeiro plano da cena seguinte, a geração para com uma mensagem da fronteira problemática. Em projetos legados, o app pode encurtar a dissolvência implícita ou usar corte seco para preservar o plano.

O arquivo `project.json` preserva os blocos `soundtrack` e `youtube`, se existirem. A escolha de música realmente usada fica em `soundtrack_used.json`, com ganho, LUFS e metadados disponíveis, sem caminho do host. Quando um MP4 é publicado, `youtube_publication.json` registra o ID, URL, canal, horário e hash do vídeo, sem credenciais.

## 6. Publicar no YouTube

A seção **Publicar no YouTube** fica disponível antes mesmo da geração para conectar e selecionar contas. Primeiro siga [`YOUTUBE_AUTHENTICATION.md`](YOUTUBE_AUTHENTICATION.md) para salvar o JSON do cliente OAuth em `input/youtube/client_secret.json` e conectar cada conta desejada. O upload só é liberado depois que um MP4 for gerado.

O seletor **Conta para publicar** começa vazio e não escolhe canal automaticamente. Se uma conexão for interrompida, use **Cancelar autorização pendente** antes de iniciar outra. Selecione uma conta conectada, revise título, descrição, privacidade, público infantil e mídia sintética, marque a confirmação e clique em **Publicar MP4 no YouTube**. O app envia somente o MP4, mostra o progresso e salva `youtube_publication.json` com o link retornado. O mesmo arquivo não pode ser enviado novamente por engano.

O YouTube pode continuar processando o vídeo depois do upload. Legendas SRT/VTT, agendamento, miniatura e publicação em lote ainda não são enviados pela API.

## 7. Limites configuráveis

Os limites do ZIP ficam em `.env` ou `config/settings.example.env`:

- `ZIP_MAX_FILES`;
- `ZIP_MAX_COMPRESSED_BYTES`;
- `ZIP_MAX_UNCOMPRESSED_BYTES`;
- `ZIP_MAX_IMAGE_BYTES`;
- `ZIP_MAX_IMAGE_PIXELS`;
- `MUSIC_MAX_CATALOG_BYTES`;
- `MUSIC_MAX_TRACK_BYTES`.

## 8. Serviço legado opcional

ComfyUI/Stable Diffusion não participa da operação normal. Se for necessário investigá-lo em uma tarefa futura, ele está no perfil `legacy-image`:

```powershell
docker compose --profile legacy-image up -d comfyui
```

Esse perfil não é necessário para enviar JSON + ZIP ou gerar o Short.
## Sincronização por Whisper

Com legendas ativas ou múltiplos planos, o áudio final é transcrito localmente com Whisper depois da narração. Os timestamps reais por palavra alimentam as trocas de plano e, quando solicitadas, as legendas em maiúsculas, em blocos de até três palavras, com entrada em pop e destaque progressivo. A mesma transcrição é reutilizada para os dois recursos. Na primeira geração, o modelo `small` pode ser baixado automaticamente; o cache fica em `models/kokoro/`.

O tamanho do modelo, dispositivo e tipo de calculo podem ser ajustados no `.env` com `WHISPER_MODEL`, `WHISPER_DEVICE` e `WHISPER_COMPUTE_TYPE`.
