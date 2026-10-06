# Local Short Studio

Com legendas ativas ou cenas com múltiplos planos, o áudio final é transcrito localmente com Whisper depois da narração. O modelo `small` gera timestamps reais por palavra e fica em cache no volume `models/kokoro/`; a primeira geração que exigir alinhamento pode baixar os pesos.

Gere Shorts verticais localmente a partir de um roteiro JSON e de um ZIP com uma ou mais imagens por cena. As imagens são preparadas previamente no ChatGPT ou em outra ferramenta; o projeto local faz a narração pt-BR com Kokoro ou Chatterbox, aplica movimentos/transições e exporta o MP4 com FFmpeg.

## Fluxo da primeira versão

1. Prepare `modelo_projeto.json`; cenas podem usar uma imagem ou de 2 a 4 `shots`.
2. Prepare `imagens_cenas.zip` com os arquivos referenciados em `image_path`.
3. Abra o Streamlit, envie os dois arquivos e corrija qualquer aviso de nomes, formatos ou arquivos ausentes.
4. Opcionalmente, declare uma única `soundtrack` do catálogo embutido para o Short inteiro.
5. Escolha Kokoro ou Chatterbox PT-BR, confirme a música efetiva, configure as legendas e clique em **Gerar Short**.

O app não gera imagens e não usa ComfyUI no fluxo padrão. O serviço ComfyUI antigo permanece somente como perfil Docker opcional para referência futura.

## Requisitos

- Windows com Docker Desktop usando backend WSL 2.
- Driver NVIDIA atualizado e GPU visível ao Docker; a RTX 2060 de 6 GB é o alvo desta versão.
- Ryzen 5 5600G, 16 GB de RAM e espaço para imagens, cache Kokoro e renders.
- CUDA continua sendo usada pelo mecanismo de voz escolhido; o Toolkit instalado no Windows não substitui o driver encaminhado ao container.
- Chatterbox PT-BR é uma alternativa local; o primeiro uso baixa os pesos oficiais e reutiliza o cache em `models/kokoro/`.
- PNG, JPG, JPEG ou WebP para as imagens das cenas.

## Instalação e execução

Copie `.env.example` para `.env` se ainda não existir. Os limites de segurança do ZIP e as configurações de Kokoro já têm valores adequados para começar.

As faixas e o catálogo ficam versionados em `assets/music_library/` e são copiados para `/workspace/assets/music_library/` durante o build. Não é necessário extrair um ZIP ou montar uma pasta adicional para resolver `soundtrack.track_id`. Um diretório `input/music_library/` ainda pode ser usado como override local explícito para testes. O catálogo não comprova licença: confirme origem, direitos e atribuição antes de publicar.

O prompt normativo para gerar o roteiro, JSON e ZIP de imagens está em [`docs/PROMPT_GERAR_MODELO_PROJETO_SHORT_COM_MUSICA.md`](docs/PROMPT_GERAR_MODELO_PROJETO_SHORT_COM_MUSICA.md), e a visão humana das faixas está em [`docs/CATALOGO_MUSICAS.md`](docs/CATALOGO_MUSICAS.md).

```powershell
docker compose up --build -d
```

Abra:

- App: `http://localhost:8501`
- Diagnóstico de containers: `docker compose ps`

O comando padrão constrói e inicia somente o app. Não exige checkpoint, ComfyUI ou Stable Diffusion.

## Modelo JSON e ZIP

Use [`examples/modelo_projeto.json`](examples/modelo_projeto.json), um roteiro real completo com múltiplos planos e metadados de YouTube. `image_path` continua obrigatório e deve ser somente o nome do arquivo, sem pastas. O ZIP pode conter as imagens na raiz ou em uma única subpasta; o app resolve por basename, valida bytes e copia apenas as imagens usadas para a execução.

Em uma cena com `shots`, o primeiro plano repete exatamente `scene.image_path` e começa junto com a cena. Cada plano seguinte usa uma imagem distinta e uma `start_phrase` única da narração. A troca acontece no início dessa frase, usando timestamps de palavras realmente reconhecidas pelo Whisper; não há corte no áudio nem transição entre os planos da mesma cena.

Cada cena, exceto a última, pode declarar `transition_to_next` com `cut`, `crossfade` ou `fade_black`. A duração opcional de fades aceita de 0,15 a 0,45 segundo; quando omitida, usa o padrão do perfil. Projetos antigos continuam usando a dissolvência padrão. As transições afetam somente o vídeo: narração, padding entre cenas, âncoras dos planos e legendas mantêm seus tempos originais.

O bloco opcional `youtube` contém os metadados usados na publicação direta. Depois de renderizar o MP4, a interface permite escolher explicitamente uma conta conectada, revisar os dados e confirmar um upload resumível pela YouTube Data API. Não há conta padrão, agendamento, publicação em lote ou upload de legendas pela API nesta versão.

O plano da futura publicação direta está em [`docs/YOUTUBE_PUBLICATION_PLAN.md`](docs/YOUTUBE_PUBLICATION_PLAN.md). Para preparar uma conta localmente quando a integração for implementada, veja [`docs/YOUTUBE_AUTHENTICATION.md`](docs/YOUTUBE_AUTHENTICATION.md): upload exige OAuth 2.0, não uma chave de API.

Uma trilha catalogada é opcional e vale para o Short inteiro:

```json
"soundtrack": { "track_id": "acting_melodiesinfonie", "volume_percent": 4 }
```

O ID precisa existir como candidato editorial e o volume do JSON deve coincidir com a recomendação do catálogo; zero é a exceção para silêncio explícito. `soundtrack` e o `music_path` legado são mutuamente exclusivos. Na interface, a precedência explícita é: upload manual selecionado, faixa escolhida no catálogo, faixa do JSON, `music_path` legado e sem música. A escolha temporária não altera silenciosamente o JSON exportado.

Para faixas catalogadas, o app verifica o SHA-256 antes do TTS, mede a narração e limita o ganho ao menor valor entre o pedido, vinte LU abaixo da voz e aproximadamente −38 LUFS para a música. A faixa recebe entrada e saída suaves, repete ou é cortada na duração do Short e nunca acrescenta cauda ao vídeo. Upload e `music_path` continuam no caminho legado de volume estático.

O seletor de mecanismo de narração fica fora do JSON para preservar o contrato do projeto. Kokoro oferece Dora, Alex, Santa e velocidade; Chatterbox usa o pacote dedicado pt-BR e oferece expressividade, controle de ritmo e variação.

No Chatterbox, também é possível enviar um áudio de referência de 5 a 10 segundos. Use uma gravação limpa em português brasileiro, sem música, eco ou outras pessoas. O arquivo é usado localmente e salvo somente em `output/<execução>/audio/`; ele não altera o JSON.

Cada `scene.narration` é sintetizada como um bloco contínuo, preservando as pausas indicadas pela pontuação. Narrações devem escrever nomes completos para melhorar a pronúncia: use **“tiranossauro rex”**, nunca “T. rex”, “T-Rex” ou “T rex”.

Quando ativadas, as legendas usam Montserrat ExtraBold em maiúsculas, com contorno escuro e no máximo três palavras por bloco. Cada bloco entra com um pop curto de escala/opacidade para receber foco visual. A interface permite ajustar o tamanho da fonte e a altura na tela para cada geração; 50% corresponde ao centro vertical.

## Saídas e testes

Cada execução cria `output/<titulo>_<data>/` com JSON, texto, imagens usadas, WAVs, MP4 e arquivos SRT/ASS quando as legendas estão ativas. Quando há música, `soundtrack_used.json` registra a fonte efetiva, ganho, medições e metadados disponíveis sem gravar caminhos do host nem afirmar direitos de uso.

```powershell
python -m compileall app
python -m unittest discover -s tests
docker compose config
```

Para parar os serviços mantendo arquivos e cache:

```powershell
docker compose down
```

Veja [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) e [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) para operação detalhada.
