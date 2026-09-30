# Solução de problemas

## A aplicação diz que CUDA não foi detectada

1. Confira se o driver NVIDIA do Windows suporta CUDA 13; atualize-o e reinicie o computador se necessário.
2. Atualize WSL: `wsl --update`.
3. Verifique o backend WSL 2 em Docker Desktop.
4. Reinicie Docker Desktop e confira no app o nome da GPU.
5. Veja `docker compose logs app comfyui`.

O suporte GPU do Docker Desktop para Windows depende do backend WSL 2 e de driver/kernel compatíveis. ComfyUI usa CUDA 13.0 (RTX 2060/Turing é compatível); não instale um driver Linux NVIDIA dentro do container: o host Windows fornece o driver.

## ComfyUI abre, mas não gera

- Confirme que o checkpoint existe em `models/checkpoints/`.
- Verifique `CHECKPOINT_NAME` no `.env`; diferencia maiúsculas e extensão.
- Abra `http://localhost:8188` e leia o erro no terminal/log do serviço.
- Faça o primeiro teste com 512×896, 18 passos e uma cena.
- Evite carregar outros modelos pesados na GPU durante o Short.

## Erro de memória CUDA

- O projeto pede ao ComfyUI para descarregar modelos antes do Kokoro. Se outra aplicação reservou a VRAM, feche-a e rode novamente.
- Mantenha uma cena por amostra; reduza `IMAGE_STEPS` para 14 e a resolução para 512×768 se o checkpoint exceder 6 GB.
- A RTX 2060 tem 6 GB físicos; configurações de 768×1365 ou vários lotes não são o alvo inicial.
- Se a memória do sistema for pressionada, feche jogos e ajuste os recursos do WSL/Docker Desktop.

## Kokoro não encontra a voz ou falha ao carregar

- Use `TTS_VOICE=pf_dora` como primeira configuração pt-BR.
- Confira o valor do campo Voz Kokoro na interface.
- A primeira execução precisa baixar pesos/cache; mantenha a rede disponível até o download completar.
- Confirme que o container `app` vê CUDA e rode `docker compose logs app`.

## FFmpeg acusa fonte ou legendas

- A imagem inclui `fonts-inter` e `fonts-dejavu-core`; reconstruir com `docker compose up --build -d` instala as fontes.
- Se necessário, desligue legendas e gere o MP4 sem `.srt`.
- Evite aspas ou caracteres de controle no título/nome do arquivo. O nome do vídeo é convertido para slug seguro.

## FFmpeg não encontra NVENC

Defina `VIDEO_ENCODER=libx264` em `.env`, que usa CPU para codificar. A geração de imagens/voz continua em CUDA. `VIDEO_ENCODER=auto` escolhe NVENC quando ele aparece na lista do FFmpeg.

## Docker não inicia os containers

- Confirme que o Docker Desktop está iniciado e que `docker compose version` funciona no PowerShell.
- Rode `docker compose logs --tail=200 app comfyui`.
- Pare stacks antigos que usem as portas 8501/8188 ou mude `APP_PORT`/`COMFYUI_PORT` no `.env`.
- Se uma build parcial deixou recursos desatualizados, rode `docker compose down` e novamente `docker compose up --build -d`.

## Gerar uma cena novamente

Cada execução salva seus resultados em uma pasta nova. Use o projeto JSON e seed da cena para reproduzir a saída; para gerar outra variação, troque o seed e execute de novo. A regeneração de uma cena isolada será adicionada à interface numa iteração futura.

