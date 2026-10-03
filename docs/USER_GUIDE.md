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

Veja os dois contratos em `examples/modelo_projeto.json` e `examples/modelo_projeto_multiplos_planos.json`.

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

Música é opcional e deve ter licença de uso. Legendas são opcionais: quando ligadas, o vídeo recebe burn-in com fonte Inter, no máximo duas linhas e destaque progressivo por palavra. Os arquivos `.srt` e `.ass` também são salvos junto para inspeção.

### Chatterbox PT-BR

Chatterbox usa o ajuste dedicado `ResembleAI/Chatterbox-Multilingual-pt-br`, com o idioma `pt`, em CUDA. O primeiro uso baixa os pesos e os componentes compartilhados do Hugging Face; o cache é persistido em `models/kokoro/`, portanto as gerações seguintes não baixam tudo novamente.

Em vez de voz e velocidade do Kokoro, a interface mostra **Expressividade**, **Controle de ritmo** e **Variação**, que são os controles compatíveis com Chatterbox. Se o download, o modelo ou a CUDA falharem, a geração é interrompida com erro; não há troca automática para Kokoro.

O campo **Áudio de referência da sua voz** é opcional. Para reproduzir a identidade vocal, envie um arquivo WAV, MP3, FLAC ou OGG com aproximadamente 5–10 segundos de fala limpa em português brasileiro. Evite música, eco, ruído e outras pessoas no mesmo áudio. A referência é preparada uma vez por geração; o arquivo fica na pasta de áudio da execução e não entra no JSON.

## 5. Saída

O pipeline valida o ZIP, copia somente as imagens usadas para `output/<execução>/images/`, gera um WAV por cena com o mecanismo escolhido em CUDA e então monta o MP4 vertical 1080×1920 a 30 fps com FFmpeg. Planos da mesma cena usam cortes secos nos instantes alinhados; entre cenas, o JSON pode escolher corte seco, dissolvência ou passagem pelo preto. Durante a montagem, a barra informa a cena atual, a quantidade de planos, as cenas concluídas e a etapa final de transições/áudio.

A duração visual do fade é arredondada para frames. Se uma duração explicitamente informada ocupar quase todo o primeiro plano da cena seguinte, a geração para com uma mensagem da fronteira problemática. Em projetos legados, o app pode encurtar a dissolvência implícita ou usar corte seco para preservar o plano.

O arquivo `project.json` preserva o bloco `youtube`, se existir. Esse bloco é somente preparação para uma tarefa futura; esta versão não publica nada.

## 6. Limites configuráveis

Os limites do ZIP ficam em `.env` ou `config/settings.example.env`:

- `ZIP_MAX_FILES`;
- `ZIP_MAX_COMPRESSED_BYTES`;
- `ZIP_MAX_UNCOMPRESSED_BYTES`;
- `ZIP_MAX_IMAGE_BYTES`;
- `ZIP_MAX_IMAGE_PIXELS`.

## 7. Serviço legado opcional

ComfyUI/Stable Diffusion não participa da operação normal. Se for necessário investigá-lo em uma tarefa futura, ele está no perfil `legacy-image`:

```powershell
docker compose --profile legacy-image up -d comfyui
```

Esse perfil não é necessário para enviar JSON + ZIP ou gerar o Short.
## Sincronização por Whisper

Com legendas ativas ou múltiplos planos, o áudio final é transcrito localmente com Whisper depois da narração. Os timestamps reais por palavra alimentam as trocas de plano e, quando solicitadas, as legendas com fonte Inter, no máximo duas linhas e destaque progressivo por palavra. A mesma transcrição é reutilizada para os dois recursos. Na primeira geração, o modelo `small` pode ser baixado automaticamente; o cache fica em `models/kokoro/`.

O tamanho do modelo, dispositivo e tipo de calculo podem ser ajustados no `.env` com `WHISPER_MODEL`, `WHISPER_DEVICE` e `WHISPER_COMPUTE_TYPE`.
