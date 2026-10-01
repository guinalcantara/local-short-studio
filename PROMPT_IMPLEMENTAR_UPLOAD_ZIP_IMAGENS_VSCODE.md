# Tarefa para o Codex no VS Code — imagens do chat e metadados preparados

Trabalhe no repositório **Local Short Studio** aberto no VS Code. Implemente diretamente a mudança atual descrita em **Objetivo atual**, inspecione o projeto, rode os testes e atualize a documentação. Não pare após propor um plano e não faça perguntas; os requisitos e decisões desta tarefa estão definidos aqui.

> **Importante:** implemente agora somente o escopo de imagens por upload ZIP e escolhas de voz pt-BR descrito em Objetivo atual. As exigências identificadas como **V2 futura — não implementar nesta tarefa** devem ser documentadas como planejamento, sem alterar código, esquema ativo, telas ou configuração atual para executá-las.

## Objetivo atual

O fluxo atual deixa de gerar imagens localmente. As imagens serão criadas previamente no ChatGPT e importadas com o roteiro: upload de `modelo_projeto.json` e `imagens_cenas.zip`, contendo uma imagem por cena. O aplicativo permanece local para narração Kokoro em CUDA, movimentos/transições e MP4 com FFmpeg. Na hora de gerar, o usuário pode escolher uma voz feminina ou masculina em português brasileiro.

Mantenha o fluxo padrão exclusivamente baseado nas imagens enviadas. Não faça fallback automático para ComfyUI/Stable Diffusion se um arquivo estiver ausente. A integração antiga pode permanecer no repositório como caminho futuro opcional, mas não pode ser obrigatória, executada ou exibida no fluxo padrão. `docker compose up -d` deve iniciar o app sem exigir serviço ComfyUI ativo.

## Antes de editar

1. Leia o código, os testes e toda a documentação atual.
2. Procure no repositório referências antigas com `rg` (por exemplo `ComfyUI`, `Stable Diffusion`, `image_prompt`, `CHECKPOINT_NAME`, “gerando imagens localmente”).
3. Preserve recursos fora do escopo: Kokoro, CUDA para voz, legendas opcionais, renderização vertical, movimentos, transições e exportação MP4.

## Formato atual do modelo e campos opcionais de publicação

A chave `image_path` contém somente o nome do arquivo, por exemplo `cena_01_gancho.png`, e é obrigatória. Remova `image_prompt` do esquema ativo: as imagens já são geradas no chat. Preserve os campos atuais e seus tipos. Aceite também, como bloco opcional fechado e validado, os metadados `youtube` mostrados no exemplo. Não implemente upload/publicação pela API nesta tarefa.

```json
{
  "title": "Título do Short em português",
  "profile": "short_vertical",
  "voice": "pf_dora",
  "speech_speed": 1.0,
  "visual_style": "cinematic digital illustration, mature visual tone, cohesive color palette",
  "captions": {"enabled": false, "theme": "modern_blue"},
  "scenes": [
    {
      "id": "cena_01_gancho",
      "narration": "Texto falado nesta cena em português brasileiro.",
      "image_path": "cena_01_gancho.png",
      "motion": "slow_push_in"
    }
  ],
  "youtube": {
    "default_language": "pt-BR",
    "description": "Descrição específica em português.",
    "tags": ["dinossauros", "paleontologia"],
    "category_id": "27",
    "status": {
      "privacy_status": "private",
      "license": "youtube",
      "embeddable": true,
      "public_stats_viewable": true,
      "self_declared_made_for_kids": false,
      "contains_synthetic_media": true
    },
    "notify_subscribers": true,
    "captions": {"enabled": true, "language": "pt-BR", "format": "vtt"}
  }
}
```

Mantenha em `app/schemas.py`, `example_project()` e `examples/modelo_projeto.json` os campos atuais obrigatórios com os mesmos nomes e tipos. Acrescente suporte explícito ao bloco opcional `youtube` e aos seus subcampos permitidos; rejeite chaves desconhecidas fora da lista permitida. JSONs antigos sem `youtube` devem continuar válidos. O carregamento, edição e exportação devem preservar esse bloco, mas a geração atual do MP4 deve ignorá-lo com segurança. Teste o modelo antigo e o modelo com `youtube`.

`youtube` contém somente metadados preparados para implementação futura. Não crie conexão OAuth, upload de vídeo/legenda, agendamento de publicação ou chamada à API nesta tarefa. Não inclua campo de idioma adicional, narração em outro idioma, tradução de título/descrição nem geração de outro áudio.

## Uploads e validação na interface

Na interface Streamlit:

1. Mantenha upload do projeto `.json` e adicione upload obrigatório de `.zip` para as imagens.
2. Não habilite “Gerar Short” até o JSON ser válido, o ZIP estar disponível e todas as imagens referenciadas serem validadas.
3. Mostre quantidade de cenas/imagens e nomes encontrados. Explique nomes ausentes, duplicados ou formatos inválidos antes da geração.
4. Remova edição do campo `image_prompt` e mensagens dizendo que o app gera imagens localmente.
5. Atualize rótulos, textos de ajuda e progresso para: modelo + ZIP → validação → narração Kokoro → montagem/renderização.
6. Preserve seleção de velocidade, música e legendas opcionais. Use um seletor “Voz da narração” com as opções Kokoro pt-BR:
   - Dora — feminina (`pf_dora`)
   - Alex — masculina (`pm_alex`)
   - Santa — masculina (`pm_santa`)
   Inicialize pela voz do JSON quando válida; caso contrário, Dora. Passe a seleção para `project.voice` antes de executar o pipeline. Todas as falas usam a voz escolhida. Não ofereça opções de outros idiomas na versão atual.

## Processamento seguro do ZIP

Implemente componente pequeno e testável:

- Aceite imagens na raiz do ZIP ou em uma única subpasta, resolvendo por basename. Não extraia caminhos do ZIP diretamente.
- Aceite PNG, JPG, JPEG e WebP. Ignore apenas metadados comuns (`__MACOSX/`, `.DS_Store`); rejeite itens inesperados que possam ser confundidos com imagens.
- Cada `image_path` deve corresponder a exatamente um membro. Ausências e basenames duplicados bloqueiam geração com mensagem clara. Imagens extras podem ser ignoradas com aviso.
- Bloqueie caminhos absolutos, `..`, diretórios maliciosos, links simbólicos, arquivos criptografados e extensões incompatíveis.
- Aplique limites configuráveis de tamanho comprimido/descompactado e quantidade de arquivos para prevenir ZIP bombs.
- Use bytes validados ou diretório temporário exclusivo por execução. Copie somente imagens usadas para `output/<execução>/images/` e limpe temporários inclusive após erro.
- O pipeline resolve cada basename somente entre membros validados e preserva o mapeamento cena-imagem.

## Pipeline e serviços locais

- Remova do caminho padrão em `app/pipeline.py` geração ComfyUI, health check obrigatório, configuração de checkpoint e liberação de VRAM do modelo de imagem.
- Mantenha CUDA e liberação de recursos para Kokoro. Não carregue modelo de imagem local no fluxo padrão.
- Remova dependência obrigatória `depends_on: comfyui` do app em `docker-compose.yml`. Se o serviço continuar, deixe-o em perfil opcional e desativado por padrão; `docker compose up -d` deve funcionar sem construí-lo ou iniciá-lo.
- Retire consultas/avisos de ComfyUI da interface inicial. Indicador CUDA se refere à geração de voz.
- Atualize dependências e configurações antigas de geração local não usadas; preserve as relacionadas à CUDA/Kokoro.

## Documentação e testes da mudança atual

Atualize a documentação do repositório sobre a operação por JSON + ZIP e escolha de voz, incluindo `README.md`, `docs/USER_GUIDE.md`, `docs/TROUBLESHOOTING.md`, `docs/PROJECT_PLAN.md`, exemplo JSON e configuração de ambiente. Explique que narrações devem evitar abreviações: usar “tiranossauro rex”, nunca “T. rex”, “T-Rex” ou “T rex”. Remova instruções ativas para baixar checkpoints/ComfyUI e geração local de imagem; mantenha esses recursos como inativos/opcionais apenas quando necessários como histórico. Atualize requisitos de hardware para explicar que a RTX 2060/CUDA continua usada pelo Kokoro e que imagens são fornecidas no ZIP.

Documente diagnóstico de imagem ausente, nomes duplicados/divergentes, ZIP inválido/protegido/grande, formatos/resoluções incompatíveis, CUDA/Kokoro, FFmpeg e renderização.

Atualize e execute testes significativos para: esquema sem `image_prompt`, preservando todos os campos atuais e validando o bloco opcional `youtube`; JSONs antigos sem `youtube` continuam aceitos; `image_path` seguro/obrigatório; seleção das três vozes e passagem ao Kokoro; ZIP seguro e mapeamento imagem-cena; arquivos ausentes/duplicados/maliciosos e limites; pipeline sem ComfyUI; legendas opcionais, áudio e renderização. Valide o JSON e Docker Compose. No final, relate arquivos alterados, testes e como iniciar o app e enviar os dois arquivos.

## Integração futura de publicação — não implementar nesta tarefa

Esta seção apenas registra a próxima etapa. Nesta tarefa, atualize o esquema para aceitar e preservar o bloco opcional `youtube`, mas não altere o app para fazer upload ou publicar vídeos.

- Em uma tarefa futura autorizada pelo usuário, revisar a documentação oficial atual do YouTube Data API e implementar OAuth 2.0, armazenamento local seguro de credenciais e upload retomável.
- Usar `videos.insert` para enviar MP4 e metadados suportados pela API. Gerar legendas temporizadas após a narração final e, após obter o ID do vídeo, usar `captions.insert` para enviá-las.
- Usar os metadados em português presentes em `youtube`: título raiz, descrição, tags, categoria, idioma padrão, privacidade/licença, declarações de público e conteúdo sintético, notificação a inscritos e opção/formato de legenda.
- A data, hora e fuso de agendamento serão escolhidos exclusivamente na interface e nunca armazenados no JSON do modelo. Não colocar credenciais ou tokens no JSON.
- Implementar estados de envio, processamento, sucesso/erro, retries seguros e link final do vídeo. Começar com status privado para revisão.
- Até existir endpoint público documentado para as funções futuras necessárias, não usar endpoints privados nem automação de navegador e não afirmar que qualquer recurso foi enviado automaticamente.
- Novos projetos de API podem sofrer restrição a uploads privados até passarem pela auditoria exigida pelo YouTube. Revalidar esta limitação quando a integração for implementada.
- Referências oficiais para revalidar: `https://developers.google.com/youtube/v3/docs/videos/insert` e `https://developers.google.com/youtube/v3/docs/captions/insert`.
