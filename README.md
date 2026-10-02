# Local Short Studio

Com legendas ativas, o audio final e transcrito localmente com Whisper depois da narracao. O modelo `small` gera timestamps reais por palavra e fica em cache no volume `models/kokoro/`; a primeira geracao com legendas pode baixar os pesos.

Gere Shorts verticais localmente a partir de um roteiro JSON e de um ZIP com uma imagem por cena. As imagens são preparadas previamente no ChatGPT ou em outra ferramenta; o projeto local faz a narração pt-BR com Kokoro, aplica movimentos/transições e exporta o MP4 com FFmpeg.

## Fluxo da primeira versão

1. Prepare `modelo_projeto.json` com uma cena por imagem.
2. Prepare `imagens_cenas.zip` com os arquivos referenciados em `image_path`.
3. Abra o Streamlit, envie os dois arquivos e corrija qualquer aviso de nomes, formatos ou arquivos ausentes.
4. Escolha Kokoro ou Chatterbox PT-BR, configure os controles compatíveis, música e legendas, e clique em **Gerar Short**.

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

```powershell
docker compose up --build -d
```

Abra:

- App: `http://localhost:8501`
- Diagnóstico de containers: `docker compose ps`

O comando padrão constrói e inicia somente o app. Não exige checkpoint, ComfyUI ou Stable Diffusion.

## Modelo JSON e ZIP

Use [`examples/modelo_projeto.json`](examples/modelo_projeto.json) como base. `image_path` é obrigatório e deve ser somente o nome do arquivo, sem pastas. O ZIP pode conter as imagens na raiz ou em uma única subpasta; o app resolve por basename, valida bytes e copia apenas as imagens usadas para a execução.

O bloco opcional `youtube` é apenas metadado preparado para uma integração futura. Ele é validado e preservado no `project.json`, mas não há OAuth, upload, agendamento ou chamada à API nesta versão.

O seletor de mecanismo de narração fica fora do JSON para preservar o contrato do projeto. Kokoro oferece Dora, Alex, Santa e velocidade; Chatterbox usa o pacote dedicado pt-BR e oferece expressividade, controle de ritmo e variação.

No Chatterbox, também é possível enviar um áudio de referência de 5 a 10 segundos. Use uma gravação limpa em português brasileiro, sem música, eco ou outras pessoas. O arquivo é usado localmente e salvo somente em `output/<execução>/audio/`; ele não altera o JSON.

Narrações devem escrever nomes completos para melhorar a pronúncia: use **“tiranossauro rex”**, nunca “T. rex”, “T-Rex” ou “T rex”.

## Saídas e testes

Cada execução cria `output/<titulo>_<data>/` com JSON, texto, imagens usadas, WAVs, MP4 e arquivos SRT/ASS quando as legendas estão ativas.

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
