# Guia do usuário

## 1. Preparar a máquina

O Docker Desktop no Windows encaminha GPU NVIDIA aos containers através de WSL 2. Atualize o driver NVIDIA para uma versão que suporte CUDA 13 e mantenha o kernel WSL atualizado. No PowerShell, se necessário:

```powershell
wsl --update
```

Confirme em Docker Desktop que o backend WSL 2 está ativo. Atualize o `.env.example` para `.env` e configure o nome do checkpoint.

## 2. Obter um checkpoint

O projeto não empacota pesos de imagem. Escolha um checkpoint SD 1.5 em `.safetensors` cuja licença permita seu uso pretendido e coloque-o em:

```text
models/checkpoints/
```

No `.env`, `CHECKPOINT_NAME` deve ser exatamente o nome do arquivo. O modelo pode ser obtido do repositório oficial de um checkpoint público compatível com ComfyUI. Leia e aceite os termos/licença desse modelo antes de usá-lo.

## 3. Iniciar os containers

Na pasta do projeto:

```powershell
docker compose up --build -d
```

Na primeira vez, o Docker baixa as imagens base CUDA e constrói os serviços; a imagem ComfyUI usa PyTorch 2.14/CUDA 13.0 e fica fixada na versão v0.38.0. O app de narração usa um ambiente PyTorch/CUDA separado. O cache do Kokoro é salvo em `models/kokoro/`. Acesse:

- Aplicação: `http://localhost:8501`
- ComfyUI para diagnóstico: `http://localhost:8188`

Para consultar logs:

```powershell
docker compose logs -f app
docker compose logs -f comfyui
```

## 4. Preparar cenas

Baixe o arquivo de modelo no app ou use `examples/modelo_projeto.json`. Um projeto contém:

- `title`: nome usado na pasta e no MP4.
- `profile`: `short_vertical` na primeira entrega.
- `voice`: ID da voz Kokoro, por padrão `pf_dora`.
- `speech_speed`: entre 0.75 e 1.25.
- `visual_style`: direção de arte comum a todas as imagens para manter consistência.
- `captions.enabled`: legenda desligada ou ligada.
- `scenes`: lista de cenas com `id`, `narration`, `image_prompt`, `motion`, `seed` opcional e `image_path` opcional.

Movimentos aceitos: `slow_push_in`, `slow_pull_out`, `pan_left`, `pan_right`, `pan_up`, `pan_down`, `static` ou `auto`. `auto` alterna movimento entre cenas.

Para usar uma imagem que você já tem, copie-a para `input/` e informe um caminho relativo, como `imagens/cena01.png`. Se `image_path` for preenchido, ComfyUI não gera imagem para aquela cena.

## 5. Legendas e estilo

Desative **Adicionar legendas modernas** para exportar sem texto queimado e sem `.srt`. Ative a opção para salvar um `.srt` e queimar as frases no vídeo. O tema inicial usa Inter semibold/branco, caixa translúcida escura, destaque azul e margens seguras para celular.

Os cues de legenda usam as frases enviadas ao Kokoro e a duração de cada segmento sintetizado. Frases curtas melhoram leitura e sincronização. Fontes ficam disponíveis no container via pacote `fonts-inter`; fontes extras podem ser montadas em `assets/fonts/`.

## 6. Música

É possível enviar MP3, WAV, M4A ou AAC. A música será misturada a volume baixo. Use somente áudio que tenha autorização/licença de uso; sem arquivo enviado, o Short leva apenas a narração.

## 7. Gerar e encontrar o resultado

Clique **Gerar Short**. Imagens são criadas em sequência; o projeto pede a ComfyUI para descarregar o checkpoint; Kokoro sintetiza a narração na GPU; então o FFmpeg aplica os movimentos/crossfades e exporta.

Cada execução cria uma pasta em `output/<titulo>_<data>/` com:

- `<titulo>.mp4`: Short final.
- `project.json`: parâmetros usados para reproduzir/ajustar o projeto.
- `narration.txt`: texto limpo da voz.
- `images/`: imagens por cena.
- `audio/`: WAV de cada cena e faixa completa.
- `<titulo>.srt`: somente quando legendas estão ativas.

## 8. Personalização e vídeos horizontais futuros

Os perfis ficam em `config/render_profiles.json`. `short_vertical` controla dimensões 9:16, FPS, crossfade, pausa final, fonte e bitrate/qualidade. `video_landscape` já exemplifica 16:9; na fase seguinte, habilite o perfil e atualize a interface para exibi-lo.

Não fixe dimensões em cenas ou no JSON: o renderer recebe tudo pelo perfil. Isso permite reutilizar um roteiro/cena em outro enquadramento, com prompts e recortes próprios.

## 9. Encerrar e atualizar

Parar containers mantendo modelos e resultados:

```powershell
docker compose down
```

Reconstruir depois de alterações no projeto:

```powershell
docker compose up --build -d
```

Para apagar pesos/cache, remova os arquivos de `models/` manualmente. Isso fará novos downloads na próxima execução.

