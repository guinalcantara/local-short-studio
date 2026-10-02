# Prompt para gerar roteiro, modelo JSON e ZIP de imagens

Copie as instruções abaixo para um chat com geração de imagens. No fim, informe somente o título ou tema do Short. O chat deverá entregar `modelo_projeto.json` e `imagens_cenas.zip` para o Local Short Studio.

> **Contrato futuro:** este prompt usa `scenes[].shots`. O código atual em `main` rejeita esse campo e ainda renderiza uma imagem por cena. Implemente e valide [o guia de desenvolvimento](../docs/IMPLEMENTAR_PLANOS_E_NARRACAO_NATURAL.md) antes de importar o JSON novo. Até lá, use o prompt antigo do histórico do Git para gerar projetos compatíveis; não afirme que o novo formato já funciona.

## Instruções para o chat

Crie um YouTube Short em português brasileiro sobre o tema informado. O usuário fornecerá somente o título ou tema. Gere as imagens no ChatGPT. Não peça informações adicionais; tome decisões editoriais razoáveis.

### Roteiro e narração

- Alvo editorial: 55 a 70 segundos e 125 a 145 palavras faladas no total, contando somente `scenes[].narration`. É uma meta, não um motivo para acelerar artificialmente a voz. Informe a duração como estimativa; a duração real depende do TTS.
- Comece com um gancho claro, desenvolva uma única ideia e termine com uma conclusão memorável ou pergunta curta ligada ao tema. Não peça inscrição ou like.
- Escreva para fala natural em português brasileiro: blocos de pensamento completos, pontuação que indique pausas e variação de frases curtas e médias. Evite períodos longos, frases telegráficas isoladas e reticências em excesso. Não acrescente marcas como `[pausa]`, SSML ou timestamps à narração.
- Divida o roteiro em 6 a 8 cenas coerentes. Cada `narration` é um texto contínuo, com uma ou mais frases relacionadas, para ser sintetizado como **um bloco de voz por cena**. A divisão visual em planos não divide a fala nem repete palavras.
- Use `pf_dora` e `speech_speed: 1.0` como padrão para Kokoro. A interface também oferece Alex e Santa. A voz e a velocidade podem ser ajustadas no aplicativo.
- Evite abreviações e siglas difíceis para TTS. Escreva “tiranossauro rex”, nunca “T. rex”, “T-Rex” ou “T rex”. Escreva números por extenso quando melhorar a pronúncia.
- Para fatos científicos, históricos, religiosos ou atuais, verifique afirmações específicas em fontes confiáveis. Não invente dados; se necessário, cite fontes **fora** dos dois arquivos entregues.

### Planos e imagens

- Cada cena tem **2 planos visuais como padrão**; use 3 ou 4 somente quando houver revelação, comparação ou detalhe relevante. Mantenha **2 a 4 planos por cena** e, como meta prática, até 24 imagens no Short inteiro. Um plano pode durar mais quando a imagem sustentar a fala. Não troque imagem apenas para preencher uma contagem.
- Cada plano corresponde a uma imagem **real e distinta**, gerada separadamente. Não entregue somente prompts, não reutilize imagens e não faça colagens, grades ou folhas de contato. Não planeje ComfyUI ou Stable Diffusion no fluxo padrão.
- O primeiro plano de cada cena começa no início da fala e **não tem** `start_phrase`. Cada plano seguinte tem `start_phrase`: uma sequência curta e exata de palavras presente **uma única vez** na `narration` da própria cena. Copie o trecho literalmente do texto falado. O plano começa quando a primeira palavra dessa sequência é falada. A sequência deve estar dentro de uma frase, não atravessar duas. Não use segundos estimados.
- Escolha as frases âncora para que a imagem apareça junto da ideia narrada; evite um plano que antecipe a revelação antes da fala. Preserve a ordem dos planos e das frases âncora. Prefira âncoras de 3 a 7 palavras que não se repitam.
- `image_path` no nível da cena continua obrigatório para compatibilidade e deve ser **idêntico** ao `image_path` de `shots[0]`. Em cenas novas, inclua `shots` com 2 a 4 elementos. `motion` no nível da cena continua no JSON; cada plano pode omitir `motion` para herdar o da cena ou escolher um movimento permitido.
- Gere imagens verticais, preferencialmente 9:16, com margem segura para um eventual corte. Mantenha unidade de estilo, paleta e iluminação, variando enquadramento e escala conforme a fala. Use estilo adulto e cinematográfico, salvo se o assunto pedir outro.
- Descreva concretamente assunto, quantidade, aparência, pose, partes importantes visíveis, posição no quadro, cenário, enquadramento e luz. Para anatomia complexa, use pose simples e legível, sem sobreposição de partes relevantes. Por exemplo, um tiranossauro rex deve ter uma cabeça e mandíbula, um par de braços curtos junto ao peito, duas pernas traseiras e cauda ligada à pelve.
- Não peça texto, legendas, placas legíveis, logotipos ou marcas-d'água nas imagens. Confira cada imagem quanto ao assunto, composição vertical e defeitos evidentes; regenere apenas a imagem problemática.
- Salve PNG, JPG, JPEG ou WebP com nomes simples e únicos, sem diretórios. Use exatamente os mesmos nomes em cada `shots[].image_path` e no ZIP. Exemplo: `cena_01_plano_01.png`, `cena_01_plano_02.png`.
- Se a geração de imagens não estiver disponível, diga isso claramente. Não simule arquivos nem entregue JSON que aponta para imagens inexistentes.

### Metadados preparados para publicação futura

Preencha o bloco opcional `youtube` no JSON. Ele apenas acompanha o projeto: o aplicativo ainda não usa OAuth, agenda ou API de publicação. Escreva roteiro, narração e metadados de publicação em português brasileiro; `visual_style` é a exceção técnica e fica em inglês, como no modelo atual.

- `title`: título principal curto e específico em pt-BR.
- `youtube.description`: descrição específica, com hashtags pertinentes e sem lista excessiva. `youtube.tags`: termos concisos sem `#` e sem duplicatas.
- `youtube.category_id`: `27` para episódios educativos, salvo se outra categoria servir melhor. `youtube.default_language`: `pt-BR`.
- `youtube.status.privacy_status`: `private` para revisão. `license`: `youtube`. `embeddable` e `public_stats_viewable`: `true`.
- `self_declared_made_for_kids`: `true` somente para conteúdo especificamente direcionado a crianças. Dinossauros, por si sós, não determinam a opção.
- `contains_synthetic_media`: avalie se cenas fotorrealistas geradas por IA parecem retratar uma situação real que não aconteceu. Ilustrações claramente não realistas não exigem `true` apenas por terem sido geradas por IA.
- `notify_subscribers`: `true`. `youtube.captions`: preparo futuro em `pt-BR`, formato `vtt`. Não invente timestamps ou um VTT nesta etapa.
- Não inclua agendamento, `publishAt`, credenciais, tokens ou identificadores privados. Não afirme que o Short foi publicado.

### Legendas e arquivos

- `captions.enabled`: `false` no JSON por padrão; o usuário pode ativar legendas visuais na interface. `captions.theme`: `modern_blue`.
- Entregue exatamente dois arquivos: `modelo_projeto.json` (roteiro e metadados) e `imagens_cenas.zip` (todas as imagens usadas, preferencialmente na raiz). Não inclua imagens extras no ZIP.
- As legendas VTT futuras do YouTube são independentes das legendas incorporadas no MP4. Não gere arquivo VTT separado.

### Formato do JSON

Use os campos e tipos abaixo. O exemplo mostra somente uma cena para explicar o formato; a entrega real deve conter 6 a 8 cenas e o total de palavras solicitado. `start_phrase` é texto copiado literalmente de `narration`, sem aspas adicionais. A primeira imagem da cena aparece em `image_path` e novamente em `shots[0].image_path` por compatibilidade.

```json
{
  "title": "Título curto do Short",
  "profile": "short_vertical",
  "voice": "pf_dora",
  "speech_speed": 1.0,
  "visual_style": "cinematic digital illustration, mature visual tone, cohesive color palette, dramatic natural lighting",
  "captions": { "enabled": false, "theme": "modern_blue" },
  "scenes": [
    {
      "id": "cena_01_gancho",
      "narration": "Os braços do tiranossauro rex parecem inúteis. Mas os fósseis contam uma história mais interessante.",
      "image_path": "cena_01_plano_01.png",
      "motion": "slow_push_in",
      "shots": [
        { "image_path": "cena_01_plano_01.png" },
        { "image_path": "cena_01_plano_02.png", "start_phrase": "Mas os fósseis contam" }
      ]
    }
  ],
  "youtube": {
    "default_language": "pt-BR",
    "description": "Descrição específica em português. #Dinossauros #Paleontologia",
    "tags": ["dinossauros", "paleontologia", "fósseis"],
    "category_id": "27",
    "status": {
      "privacy_status": "private",
      "license": "youtube",
      "embeddable": true,
      "public_stats_viewable": true,
      "self_declared_made_for_kids": false,
      "contains_synthetic_media": false
    },
    "notify_subscribers": true,
    "captions": { "enabled": true, "language": "pt-BR", "format": "vtt" }
  }
}
```

Regras adicionais:

- Preserve os nomes e tipos de `title`, `profile`, `voice`, `speech_speed`, `visual_style`, `captions`, `scenes`, `id`, `narration`, `image_path`, `motion` e do bloco `youtube` já aceitos. A única extensão de renderização nesta etapa é `scenes[].shots`. Os JSON antigos, sem `shots`, devem continuar válidos após a implementação. `visual_style` descreve apenas a unidade visual em inglês; não inclua descrições de planos nesse campo.
- `id` é único e contém apenas letras sem acento, números, hífen ou sublinhado. `narration` tem até 1200 caracteres por cena. `image_path` é somente basename de uma imagem suportada. `motion` pertence a `slow_push_in`, `slow_pull_out`, `pan_left`, `pan_right`, `pan_up`, `pan_down`, `static` ou `auto`.
- Não inclua `image_prompt`, descrição visual, `seed`, `negative_prompt`, `lora`, `controlnet`, `music_path`, duração ou timestamp por plano, campos de efeito sonoro ou chaves fora do contrato.
- O arquivo JSON deve ser válido, sem comentários, vírgulas sobrando, bloco Markdown ou texto adicional.

### Validação e entrega

Antes de entregar, valide o JSON e conte as palavras faladas. Confirme que cada cena tem 2 a 4 planos, que `shots[0].image_path == scene.image_path`, que cada `start_phrase` ocorre exatamente uma vez na fala da cena e que as âncoras estão em ordem. Confira correspondência exata, sem duplicatas, entre todos os arquivos referenciados nos planos e as imagens do ZIP; a referência duplicada entre `scene.image_path` e `shots[0].image_path` aponta para **um único arquivo**. Confira também o bloco `youtube` e a ausência de dados de agendamento ou credenciais.

Entregue links para `modelo_projeto.json` e `imagens_cenas.zip`, com prévias ou links individuais das imagens. Informe título e duração estimada em uma linha, sem duplicar a narração. Avise que o modelo com `shots` exige a implementação do guia mencionado no início.

## Entrada do usuário

Título ou tema:

[escreva aqui somente o título ou tema do Short]
