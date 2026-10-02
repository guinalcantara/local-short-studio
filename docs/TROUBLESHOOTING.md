# Solução de problemas

## O botão “Gerar Short” está desativado

Confirme que:

- o JSON foi enviado e é válido;
- cada cena possui `image_path` com extensão PNG, JPG, JPEG ou WebP;
- o ZIP foi enviado;
- cada basename usado pela cena ou por seus `shots` aparece exatamente uma vez no ZIP;
- o primeiro plano repete o `image_path` da cena e as demais âncoras são válidas.

O app mostra a quantidade e os nomes encontrados antes de liberar a geração.

## Imagem ausente ou nome divergente

`image_path` é resolvido por basename, sem caminho. `cena_01.png` não corresponde a `cena-01.png`, a uma pasta adicional ou a outro nome. Corrija o JSON ou renomeie o membro do ZIP.

## Basename duplicado

Não use dois arquivos com o mesmo nome, mesmo em pastas diferentes ou com diferença apenas de maiúsculas/minúsculas. O app bloqueia para evitar que uma cena receba a imagem errada.

## ZIP inválido, protegido ou grande demais

O app rejeita ZIP corrompido, criptografado, com symlink, caminhos absolutos, `..`, mais de uma subpasta, arquivos inesperados e imagens inválidas. Também limita quantidade, tamanho comprimido/descompactado, bytes por imagem e pixels. Ajuste os limites no `.env` somente se entender o impacto de memória.

Imagens extras válidas são ignoradas com aviso; imagens referenciadas ausentes não são ignoradas.

## Frase âncora inválida ou ambígua

Cada `start_phrase` precisa ser uma sequência contígua de palavras dentro de uma única frase da narração e aparecer exatamente uma vez. Pontuação, espaços e maiúsculas/minúsculas não alteram a localização, mas o texto e os acentos das palavras precisam corresponder. Escolha uma frase curta e específica, na ordem em que será falada.

## Whisper não reconheceu uma âncora de plano

Os cortes visuais usam somente palavras realmente reconhecidas, nunca palavras que o sistema interpolou para preservar o texto das legendas. Se a mensagem indicar ausência de alinhamento lexical ou um plano curto demais, ajuste a `start_phrase`, aumente a distância entre âncoras ou simplifique a narração. O pipeline para em vez de trocar a imagem no instante errado.

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

O renderer cria cada plano em alta resolução interna, concatena os planos de uma cena com cortes secos e depois monta as transições entre cenas. Em uma RTX 2060, várias imagens podem levar minutos, especialmente com `motion_render_scale=2`. A barra deve avançar após cada cena. Enquanto houver novos arquivos em `output/<execução>/render_work/`, o processo está ativo; antes de interromper, verifique `docker compose logs --tail=200 app` e `docker compose ps`.

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
## Whisper não carrega ou a barra fica na sincronização

Quando as legendas estão ativas ou o projeto usa `shots`, o Whisper é executado depois da geração do áudio para obter timestamps por palavra. Na primeira execução, o modelo `small` é baixado e pode levar alguns minutos; depois ele é reutilizado a partir de `models/kokoro/`.

Confira os logs antes de interromper:

```powershell
docker compose logs --tail=200 app
docker compose exec app python -c "import torch; print('CUDA:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"
```

As variaveis `WHISPER_MODEL`, `WHISPER_DEVICE` e `WHISPER_COMPUTE_TYPE` ficam no `.env`. Para a RTX 2060, os valores padrao sao `small`, `cuda` e `float16`. Essa etapa e adicional a narracao, entao a primeira geracao com legendas pode demorar mais.
