# Solução de problemas

## O botão “Gerar Short” está desativado

Confirme que:

- o JSON foi enviado e é válido;
- cada cena possui `image_path` com extensão PNG, JPG, JPEG ou WebP;
- o ZIP foi enviado;
- cada basename do JSON aparece exatamente uma vez no ZIP.

O app mostra a quantidade e os nomes encontrados antes de liberar a geração.

## Imagem ausente ou nome divergente

`image_path` é resolvido por basename, sem caminho. `cena_01.png` não corresponde a `cena-01.png`, a uma pasta adicional ou a outro nome. Corrija o JSON ou renomeie o membro do ZIP.

## Basename duplicado

Não use dois arquivos com o mesmo nome, mesmo em pastas diferentes ou com diferença apenas de maiúsculas/minúsculas. O app bloqueia para evitar que uma cena receba a imagem errada.

## ZIP inválido, protegido ou grande demais

O app rejeita ZIP corrompido, criptografado, com symlink, caminhos absolutos, `..`, mais de uma subpasta, arquivos inesperados e imagens inválidas. Também limita quantidade, tamanho comprimido/descompactado, bytes por imagem e pixels. Ajuste os limites no `.env` somente se entender o impacto de memória.

Imagens extras válidas são ignoradas com aviso; imagens referenciadas ausentes não são ignoradas.

## Resolução ou formato incompatível

Use PNG, JPG, JPEG ou WebP válidos. Imagens excessivamente grandes podem exceder `ZIP_MAX_IMAGE_PIXELS` ou `ZIP_MAX_IMAGE_BYTES`; redimensione-as antes de criar o ZIP.

## CUDA/Kokoro não detectado

```powershell
docker compose ps
docker compose logs --tail=200 app
docker compose exec app python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"
```

### Chatterbox não reproduz bem a voz de referência

Use um clipe de 5–10 segundos, com uma única pessoa falando em português brasileiro, sem música, eco ou ruído. A referência deve ser fala contínua e inteligível; gravações muito curtas, silenciosas ou com cortes podem gerar pronúncia instável. A aplicação prepara a referência uma vez por execução e mantém o arquivo somente no diretório local do Short.

Confira o driver NVIDIA no Windows, o backend WSL 2 e se nenhum programa está ocupando toda a VRAM. O CUDA é usado pelo Kokoro; não é necessário instalar driver NVIDIA Linux dentro do container.

## Kokoro não encontra pesos ou voz

A primeira narração pode baixar/cachear pesos em `models/kokoro/`. Mantenha rede disponível nessa primeira execução. Use uma das vozes `pf_dora`, `pm_alex` ou `pm_santa`; códigos inválidos são normalizados para Dora na interface.

## Chatterbox PT-BR não carrega ou demora na primeira execução

O primeiro uso baixa o ajuste dedicado pt-BR e componentes compartilhados do Hugging Face. Isso pode levar alguns gigabytes e alguns minutos; o cache fica em `models/kokoro/`. Verifique:

```powershell
docker compose logs --tail=200 app
docker compose exec app python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"
```

O app não troca automaticamente para Kokoro. Se aparecer erro de dependência, reconstrua com `docker compose up --build -d app`; se aparecer erro de CUDA, confira o driver NVIDIA, WSL 2 e Docker Desktop.

## Barra parada em uma cena de renderização

O renderer cria cada cena em alta resolução interna, aplica pan/zoom e depois monta as transições. Em uma RTX 2060, várias cenas podem levar minutos, especialmente com `motion_render_scale=2`. A barra deve avançar após cada cena. Enquanto houver novos arquivos em `output/<execução>/render_work/`, o processo está ativo; antes de interromper, verifique `docker compose logs --tail=200 app` e `docker compose ps`.

## FFmpeg, fontes ou legendas

O app instala FFmpeg, Inter e fontes sans-serif na imagem. As legendas renderizadas usam ASS com grupos curtos e destaque progressivo por palavra; o SRT continua sendo salvo para download. Se o problema ocorrer apenas com legendas, desligue-as para isolar a montagem; depois confira `docker compose logs app`.

## Docker não inicia

```powershell
docker compose config
docker compose up --build -d
docker compose ps
```

O comando padrão não precisa construir ou iniciar ComfyUI. Portas padrão: `8501` para o app. Para parar e recriar somente o app após alterar o código:

```powershell
docker compose up --build -d app
```

## Publicação futura

O bloco `youtube` é apenas metadado validado e preservado. Nenhuma credencial, OAuth, upload, legenda via API ou agendamento é executado nesta versão.
