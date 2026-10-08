# Instruções do repositório — Local Short Studio

## Objetivo atual

O projeto gera Shorts verticais localmente a partir de:

1. um projeto JSON com roteiro e uma ou mais imagens por cena;
2. um ZIP enviado pelo usuário com as imagens referenciadas por `image_path`.

O app local gera narração em português brasileiro com Kokoro/CUDA, aplica movimentos de câmera simulados, transições, legendas opcionais e exporta MP4 com FFmpeg. Depois da renderização, o usuário pode publicar o MP4 explicitamente no YouTube por uma conta OAuth local escolhida na interface.

## Regras importantes

- O fluxo padrão não gera imagens e não depende de ComfyUI, Stable Diffusion ou checkpoint.
- `image_prompt` não pertence ao esquema ativo. Cada cena precisa de `image_path` contendo somente um basename seguro e pode declarar de 2 a 4 `shots` seguros.
- O ZIP aceita PNG, JPG, JPEG e WebP na raiz ou em uma única subpasta.
- Nunca extraia caminhos do ZIP diretamente. Preserve as validações de tamanho, extensão, symlink, criptografia, `..`, caminhos absolutos e duplicidade.
- Copie para a execução somente as imagens referenciadas pelas cenas e seus planos.
- As vozes atuais são exclusivamente `pf_dora`, `pm_alex` e `pm_santa`.
- O bloco opcional `youtube` é validado, preservado e mapeado para o upload opcional de MP4 e, quando solicitado, da faixa SRT/VTT gerada localmente pelo YouTube Data API. Não há conta padrão, publicação automática, lote, agendamento ou miniatura.
- Publicações exigem uma conta OAuth conectada, selecionada explicitamente e confirmação do usuário para cada MP4. Chave de API não autoriza upload.
- O cliente OAuth, tokens e a lista local de contas ficam exclusivamente em `input/youtube/`. Nunca registre, exponha, copie para `output/` ou versione `client_secret.json`, tokens, refresh tokens, cookies, e-mails completos ou outros segredos.
- Preserve upload resumível do MP4, renovação de token, bloqueio contra reenvio, recuperação segura de legenda pendente e a possibilidade de cancelar uma autorização OAuth pendente. O envio de legendas exige o escopo OAuth `youtube.force-ssl`.
- `video_landscape` existe como perfil futuro, mas permanece desativado.
- Não inclua pesos de modelos, tokens, credenciais ou arquivos gerados no Git.

## Arquivos principais

- `app/schemas.py`: contrato estrito do JSON, cenas, planos e metadados do YouTube.
- `app/image_archive.py`: validação e mapeamento seguro do ZIP.
- `app/voices.py`: catálogo de vozes Kokoro pt-BR.
- `app/ui.py`: upload JSON/ZIP, validação, controles de voz, música, legendas e publicação explícita no YouTube.
- `app/youtube.py`: OAuth local, contas conectadas, upload resumível do MP4, envio de faixa de legenda e registro não sensível da publicação.
- `app/pipeline.py`: ZIP → Kokoro/Chatterbox → Whisper quando necessário → FFmpeg; não adicionar ComfyUI ao caminho padrão.
- `app/renderer.py`: pan/zoom, cortes, dissolvências, passagem pelo preto, legendas e MP4.
- `docker-compose.yml`: o serviço padrão é somente `app`; ComfyUI fica no perfil legado `legacy-image`.
- `docs/PROJECT_PLAN.md`, `docs/USER_GUIDE.md`, `docs/TROUBLESHOOTING.md`, `docs/YOUTUBE_AUTHENTICATION.md` e `docs/YOUTUBE_PUBLICATION_PLAN.md`: documentação normativa do fluxo atual.

## Antes de alterar

Leia `README.md`, `docs/PROJECT_PLAN.md`, `docs/USER_GUIDE.md` e `docs/TROUBLESHOOTING.md`. Procure referências relacionadas com `rg` antes de remover ou reativar comportamentos antigos. Preserve mudanças do usuário, especialmente o diretório não relacionado `ideias/`.

Use `apply_patch` para editar arquivos. Não faça `git reset --hard`, checkout destrutivo ou remoção ampla de arquivos.

## OpenSpec

As especificações vigentes ficam em `openspec/specs/` e descrevem o comportamento de referência do projeto. Antes de propor uma feature ou correção, consulte as specs relacionadas e use o fluxo OpenSpec (`$openspec-propose`) para criar os artefatos da mudança. Não altere os padrões legados de duração, fluxo de geração, saída ou publicação sem uma especificação explícita de compatibilidade.

## Validação

O host Windows pode não ter Python instalado. Prefira validar no container Docker:

```powershell
docker compose config
docker compose up --build -d
docker compose ps
docker compose run --rm --no-deps -v "${PWD}/tests:/workspace/tests:ro" app python -B -m unittest discover -s /workspace/tests -v
docker compose exec app python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"
```

O Compose padrão deve listar somente `app` em `docker compose config --services`. O perfil legado só deve ser ativado explicitamente.

Ao alterar Python, execute a suíte completa, incluindo testes de esquema, ZIP, pipeline sem ComfyUI, renderer e YouTube com mocks. Ao alterar JSON/Compose, valide `examples/modelo_projeto.json` e `docker compose config`.

## Documentação e conteúdo

Atualize a documentação quando o contrato ou o fluxo mudar. Narrações devem preferir nomes completos para pronúncia: escrever “tiranossauro rex”, nunca “T. rex”, “T-Rex” ou “T rex”. Não reintroduza instruções para baixar checkpoint como requisito da primeira versão.

Mantenha `.env` local fora do Git. Configurações exemplares devem ficar em `.env.example` ou `config/settings.example.env`. Diretórios `input/`, `output/` e `models/` são persistentes locais e não devem receber artefatos versionados. Ao atualizar o prompt de roteiro, prefira `start_phrase` de duas ou três palavras de conteúdo e não inicie âncoras com artigos ou conectores que o Whisper possa omitir.
