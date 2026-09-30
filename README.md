# Local Short Studio

Gere imagens e narração localmente e monte um Short vertical com movimentos simulados de câmera, transições suaves e legendas opcionais. A aplicação foi planejada para Windows + Docker Desktop/WSL 2 + NVIDIA CUDA.

> Leia [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) para a arquitetura e os critérios definidos antes da implementação. Para instalar, siga [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md).

## O que o projeto automatiza

1. Lê um projeto JSON com cenas, textos de narração e prompts visuais.
2. Gera as imagens pelo ComfyUI com um checkpoint Stable Diffusion 1.5 escolhido por você.
3. Descarrega o checkpoint e gera narração pt-BR com Kokoro em CUDA.
4. Aplica movimentos lentos e alternados, crossfades e, opcionalmente, legendas com estilo Inter.
5. Exporta MP4 9:16 e guarda JSON, TXT, WAV, imagens e SRT (quando legendas são ativadas).

O fluxo cria movimento de câmera sobre imagens estáticas; não sintetiza movimento novo dentro dos objetos da imagem.

## Requisitos

- Docker Desktop com backend WSL 2 e Docker Compose.
- Driver NVIDIA para Windows compatível com CUDA 13.0 e GPU CUDA visível nos containers.
- RTX 2060 6 GB ou GPU NVIDIA compatível; o workflow usa resolução de trabalho 512×896 e poucos passos como ponto de partida.
- 16 GB de RAM recomendados; feche jogos e aplicações que ocupem VRAM durante a geração.
- Um checkpoint `.safetensors` de Stable Diffusion 1.5 que você tenha direito de usar.
- Espaço para imagens Docker, cache Kokoro, checkpoint e renders.

## Instalação rápida

1. Copie `.env.example` para `.env`.
2. Coloque o checkpoint em `models/checkpoints/` e configure `CHECKPOINT_NAME` no `.env`.
3. Abra Docker Desktop e confirme que WSL 2 está habilitado.
4. Na pasta do projeto, rode:

   ```powershell
   docker compose up --build -d
   ```

5. Acesse `http://localhost:8501`. ComfyUI também fica em `http://localhost:8188` para diagnóstico local.
6. Importe `examples/modelo_projeto.json`, ajuste roteiro/prompts/legenda/voz e clique **Gerar Short**.

Na primeira compilação e execução, Docker/Python e Kokoro baixam dependências/pesos. As gerações usam os arquivos locais depois do download.

## Perfil de saída

Ativo: `short_vertical` — 1080×1920, 30 fps, MP4 H.264/AAC. O perfil `video_landscape` já está configurado em `config/render_profiles.json`, mas fica desativado na primeira entrega. Futuramente, habilite-o para 16:9 sem alterar o formato JSON das cenas.

## Pastas importantes

- `input/`: imagens ou áudio que você escolher fornecer.
- `models/checkpoints/`: checkpoint Stable Diffusion para ComfyUI.
- `models/kokoro/`: cache persistente de pesos do Kokoro.
- `output/`: cada render tem pasta própria com imagens, áudio, JSON, TXT, MP4 e SRT opcional.
- `workflows/`: workflow ComfyUI usado para uma imagem por cena.
- `docs/`: arquitetura, guia de usuário e solução de problemas.

## Testes e limites deste pacote

- `python -m compileall app` valida sintaxe Python.
- `python -m unittest discover -s tests` verifica formatos e perfil de legenda.
- ComfyUI está fixado em v0.38.0 e usa PyTorch 2.14/CUDA 13.0; a inferência CUDA real precisa ser validada no computador do usuário. O pacote não contém os pesos do checkpoint.

