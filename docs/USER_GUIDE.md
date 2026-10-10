# Guia do usuário

## 1. Preparar os arquivos

Crie um JSON com `title`, `profile`, `voice`, `speech_speed`, `visual_style`, `captions` e `scenes`. Cada cena precisa de:

- `id`: identificador seguro;
- `narration`: texto em português brasileiro;
- `image_path`: basename obrigatório, como `cena_01_gancho.png`;
- `motion` opcional legado: `slow_push_in`, `slow_pull_out`, `pan_left`, `pan_right`, `pan_up`, `pan_down`, `static` ou `auto`;
- `camera` opcional, quando o enquadramento precisar de foco e zoom controlados.

O formato legado, sem `shots`, continua usando `image_path` e `motion` como seu único plano. Para mostrar mais de uma imagem durante a mesma fala, acrescente `shots` com 2 a 4 elementos:

- `shots[0].image_path` deve ser exatamente igual ao `image_path` da cena e não usa `start_phrase`;
- cada plano seguinte usa uma `start_phrase` não vazia, contígua e presente uma única vez na narração;
- as âncoras seguem a ordem da narração e não atravessam o fim de uma frase;
- `shot.motion` é opcional; quando ausente, herda o `motion` da cena;
- em regra, cada plano usa uma imagem distinta. A mesma imagem pode ser reutilizada somente dentro da mesma cena, quando os dois planos tiverem câmeras efetivas explícitas e diferentes. Nesse caso, o arquivo ainda aparece uma única vez no ZIP.

### Câmera por cena e por plano

O bloco `camera` pode ficar na cena, para servir como padrão dos planos, ou em um `shot`, para sobrescrever apenas aquele plano. A precedência é:

1. `shot.camera`;
2. `scene.camera`;
3. `shot.motion` legado;
4. `scene.motion` legado.

Uma câmera explícita substitui o movimento legado; o renderer não soma dois movimentos. Use `camera` inteiro, sem valores parciais:

```json
{
  "camera": {
    "start": { "focus_x": 0.50, "focus_y": 0.50, "zoom": 1.00 },
    "end": { "focus_x": 0.62, "focus_y": 0.38, "zoom": 1.12 },
    "easing": "quintic"
  }
}
```

`start` e `end` são obrigatórios quando houver `camera`. Em ambos, `focus_x` e `focus_y` são números finitos entre 0 e 1, medidos na imagem original depois da orientação EXIF (esquerda/topo = 0; direita/base = 1); `zoom` é finito entre 1.00 e 1.35 e é relativo ao menor recorte que preenche o quadro vertical. `easing` é opcional, assume `quintic` e `quintic` é o único valor aceito.

Pontos iguais em `start` e `end` produzem um quadro estático. Próximo às bordas, o app limita o recorte aos pixels existentes; a prévia mostra o enquadramento efetivo. A câmera não altera duração da fala, âncoras, cortes, transições ou timestamps de legenda. O controle da interface para desligar movimentos desativa somente os movimentos legados de `motion`: uma `camera` explícita continua definindo o enquadramento.

Para reutilizar a mesma imagem em dois planos, cada plano deve receber uma câmera efetiva explícita — declarada nele ou herdada da cena — e essas câmeras devem ser diferentes. Apenas trocar `motion`, repetir a mesma câmera ou declarar câmera em somente um plano não permite a repetição.

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

### Prévia do gancho e revisão por cena

Depois de validar o JSON e o ZIP, use **Prévia do gancho** para renderizar um vídeo real da primeira cena com a voz, as imagens, a câmera, a música e as legendas efetivas. A prévia pode usar 540×960 para revisão rápida ou 1080×1920 para inspeção final; mantém proporção, taxa de quadros e enquadramento do Short final. Ela não aplica a transição para a segunda cena nem acrescenta cauda artificial.

A prévia usa a narração inteira da primeira cena. Se ela passar de aproximadamente seis segundos, a interface mostra a duração e sugere revisar o gancho, sem cortar a fala. O vídeo de prévia é identificado como tal, pode ser baixado e nunca aparece como candidato de publicação no YouTube.

O projeto salvo pode ser retomado depois de reiniciar o app ou o container. Na revisão por cena, altere texto, planos, imagens, âncoras, câmera, transição, legendas ou música e gere novamente o resultado. O app reaproveita áudio, alinhamento e renders válidos sempre que a alteração não os invalida: trocar imagem, câmera, âncora, transição, legenda ou música não deve sintetizar novamente a voz; editar texto, voz ou velocidade da cena refaz somente seu áudio e suas dependências. Uma regeneração voluntária de voz cria uma nova realização para a cena escolhida.

Antes de renderizar, qualquer edição de texto que torne uma `start_phrase` ausente, ambígua ou fora de ordem precisa ser corrigida. A interface não desloca cortes para tempos estimados.

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

Legendas são opcionais: quando ligadas, o vídeo recebe burn-in com Montserrat ExtraBold em maiúsculas, contorno escuro, até três palavras por bloco, entrada em pop e destaque progressivo por palavra. Os controles **Tamanho da fonte da legenda** e **Altura da legenda na tela** são aplicados apenas à geração atual. Na altura, 0% representa a base, 50% o centro e valores maiores movem o texto para cima. Os arquivos `.srt` e `.ass` também são salvos junto para inspeção. O SRT é a base da faixa fechada enviada ao YouTube quando o bloco `youtube.captions` estiver ativo; para `format: "vtt"`, o app gera o VTT a partir dele no momento da publicação.

### Chatterbox PT-BR

Chatterbox usa o ajuste dedicado `ResembleAI/Chatterbox-Multilingual-pt-br`, com o idioma `pt`, em CUDA. O primeiro uso baixa os pesos e os componentes compartilhados do Hugging Face; o cache é persistido em `models/kokoro/`, portanto as gerações seguintes não baixam tudo novamente.

Em vez de voz e velocidade do Kokoro, a interface mostra **Expressividade**, **Controle de ritmo** e **Variação**, que são os controles compatíveis com Chatterbox. Se o download, o modelo ou a CUDA falharem, a geração é interrompida com erro; não há troca automática para Kokoro.

O campo **Áudio de referência da sua voz** é opcional. Para reproduzir a identidade vocal, envie um arquivo WAV, MP3, FLAC ou OGG com aproximadamente 5–10 segundos de fala limpa em português brasileiro. Evite música, eco, ruído e outras pessoas no mesmo áudio. A referência é preparada uma vez por geração; o arquivo fica na pasta de áudio da execução e não entra no JSON.

## 5. Saída

O pipeline valida o ZIP, copia somente as imagens usadas para o projeto salvo, gera ou reaproveita um WAV por cena com o mecanismo escolhido em CUDA e então monta o MP4 vertical 1080×1920 a 30 fps com FFmpeg. Planos da mesma cena usam cortes secos nos instantes alinhados; entre cenas, o JSON pode escolher corte seco, dissolvência ou passagem pelo preto. Durante a montagem, a barra informa a cena atual, a quantidade de planos, as cenas concluídas e a etapa final de transições/áudio.

A duração visual do fade é arredondada para frames. Se uma duração explicitamente informada ocupar quase todo o primeiro plano da cena seguinte, a geração para com uma mensagem da fronteira problemática. Em projetos legados, o app pode encurtar a dissolvência implícita ou usar corte seco para preservar o plano.

O arquivo `project.json` preserva os blocos `soundtrack`, `youtube` e as câmeras efetivamente editadas. A exportação também oferece um ZIP reconstruído somente com as imagens referenciadas pelo projeto efetivo. Configurações de execução, cache, hash de referência vocal e outros dados locais ficam no manifesto persistente, não no ZIP nem no JSON portátil; caminhos privados, áudios pessoais, credenciais e tokens nunca são exportados.

A escolha de música realmente usada fica em `soundtrack_used.json`, com ganho, LUFS e metadados disponíveis, sem caminho do host. Quando um MP4 é publicado, `youtube_publication.json` registra o ID, URL, canal, horário, hash do vídeo e, se houver, somente o ID, idioma, formato e hash da faixa de legenda — nunca credenciais. Ao gerar um MP4 novo, a interface exige nova revisão e confirmação antes de qualquer publicação; uma prévia ou variante não reutiliza a confirmação de outro arquivo.

## 6. YouTube: publicar, contas e arquivo analítico

O menu lateral separa três responsabilidades: **Editar e publicar** mantém todo o fluxo do Short e permite apenas selecionar uma conta conectada para enviar o MP4; **Contas do YouTube** conecta, reconecta ou remove tokens locais; e **Arquivo analítico do canal** cria snapshots locais dos dados online de uma conta escolhida. Primeiro siga [`YOUTUBE_AUTHENTICATION.md`](YOUTUBE_AUTHENTICATION.md) para salvar o JSON do cliente OAuth em `input/youtube/client_secret.json` e conectar cada conta desejada. O upload só é liberado depois que um MP4 for gerado.

O seletor **Conta para publicar** começa vazio e não escolhe canal automaticamente. Selecione uma conta conectada, revise título, descrição, privacidade, público infantil e mídia sintética, marque a confirmação e clique em **Publicar MP4 e legenda no YouTube** quando `youtube.captions.enabled` estiver ativo. Nesse caso, a geração também precisa ter produzido o SRT: mantenha as legendas locais ativas ao renderizar. O app envia primeiro o MP4 e, depois que ele receber um ID, envia a faixa SRT ou VTT. Se a segunda etapa falhar, o MP4 fica registrado e a tela libera uma tentativa explícita somente da legenda, sem reenviar o vídeo.

No destino **Arquivo analítico do canal**, escolha uma conta, confirme a coleta e clique em **Baixar e salvar dados do canal**. O app lê todos os uploads acessíveis por paginação, metadados/estatísticas não monetários de canal e vídeos, e relatórios analíticos disponíveis por dia para cada vídeo. Cada execução cria um snapshot novo em `input/channel_archive/<conta>/<ano>/<mês>/<dia>/<instante>/`; `manifest.json` registra origem, horário, cobertura, limites, vídeos sem linhas e campos ausentes. O YouTube pode atrasar ou omitir dados, e esses campos não são estimados. A coleta não publica vídeos, não modifica o projeto, ZIP, cache ou MP4 e não é automática.

O YouTube pode continuar processando o vídeo e a faixa de legendas depois do upload. Contas conectadas antes desta atualização precisam ser removidas e conectadas novamente para conceder os escopos de legendas e análise. Agendamento, miniatura e publicação em lote continuam fora do escopo.

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
