# Prompt para gerar roteiro, modelo JSON e ZIP de imagens

Copie este prompt para um chat com geração de imagens. No fim, informe somente o **título ou tema** do Short. O chat deverá entregar `modelo_projeto.json` e `imagens_cenas.zip`, prontos para upload no Local Short Studio.

> **Escopo atual:** o modelo inclui metadados organizados para uma futura integração de publicação, mas o aplicativo ainda não enviará vídeos ao YouTube pela API. Todo roteiro, narração e metadado textual deste modelo deve ficar somente em português brasileiro. A estrutura fica preparada para implementação futura; não simule uma publicação.

> **Compatibilidade:** mantenha todos os campos atuais e seus tipos. Os metadados novos ficam em um bloco opcional `youtube`, separado do formato de renderização atual. O aplicativo deve ser atualizado para aceitar explicitamente esse bloco sem rejeitar o restante do projeto. Os arquivos antigos, sem o bloco, continuam válidos.

---

## Instruções para o chat

Crie um YouTube Short em português brasileiro para o projeto **Local Short Studio**, sobre o tema informado. O usuário fornecerá somente o título ou tema. Gere as imagens no ChatGPT. Não peça informações adicionais; tome decisões editoriais razoáveis.

### Roteiro

- Duração-alvo: **55 a 70 segundos**, com **125 a 145 palavras faladas** no total. Conte somente o texto das narrações das cenas.
- Comece com um gancho claro. Desenvolva uma única ideia com ritmo e termine com uma conclusão memorável ou pergunta curta ligada ao tema; não peça inscrição ou like.
- A narração deve soar natural em português brasileiro na voz Kokoro, velocidade `1.0`. Use `pf_dora` como voz padrão. A interface poderá oferecer Dora (feminina), Alex (masculina) e Santa (masculina), todas em pt-BR.
- Evite abreviações, siglas difíceis e termos que possam confundir o TTS. Por exemplo, nunca escreva “T. rex”, “T-Rex” ou “T rex”; use “tiranossauro rex”. Faça revisão de todas as falas procurando abreviações. Escreva números por extenso quando isso ajudar a pronúncia.
- Divida a narração em **6 a 8 cenas** coerentes. Prefira frases curtas para favorecer a narração e as legendas.
- Para fatos científicos, históricos, religiosos ou atuais, verifique afirmações específicas em fontes confiáveis. Não invente dados. Se fontes forem úteis, cite-as fora dos dois arquivos.

### Imagens geradas no chat

- Gere **uma imagem real para cada cena**, com uma geração separada por cena. Não entregue só prompts, não reutilize imagens e não faça colagens, grades ou folhas de contato.
- As imagens serão a fonte visual exclusiva do projeto. Não planeje geração local por ComfyUI ou Stable Diffusion.
- Gere imagens verticais para Shorts, preferencialmente 9:16. Se a ferramenta só permitir outra proporção vertical, deixe margem segura para o corte para 9:16.
- Mantenha unidade de estilo, paleta e iluminação entre as cenas, variando enquadramento e cenário conforme a narração. Use estilo adulto e cinematográfico, salvo se o tema pedir outro.
- Descreva concretamente o assunto e quantidade, aparência, pose, partes importantes visíveis, posição no quadro, cenário, enquadramento e luz. Em cenas de anatomia complexa, use pose simples e legível, sem partes relevantes cortadas ou sobrepostas.
- Para dinossauros, pessoas, veículos ou máquinas, detalhe positivamente a estrutura que precisa aparecer. Por exemplo, um tiranossauro rex deve ser descrito com uma cabeça e mandíbula, um par de braços curtos junto ao peito, duas pernas traseiras e uma cauda ligada à pelve. Isso melhora a chance de acerto, mas não garante anatomia perfeita.
- Não peça texto, legendas, placas legíveis, logotipos, marcas ou marcas-d'água dentro das imagens.
- Confira cada imagem quanto à correspondência com a cena, composição vertical e defeitos evidentes. Se houver defeito claro, tente gerar novamente aquela cena.
- Salve um PNG ou JPG para cada cena com um nome simples e único. Use o mesmo nome em `image_path`; exemplo: `cena_01_gancho.png`.
- Se a geração de imagens não estiver disponível, diga isso claramente. Não simule arquivos nem entregue um modelo apontando para imagens locais.

### Metadados preparados para publicação futura

Preencha o bloco opcional `youtube` do JSON. Esses dados apenas acompanham o modelo; **nenhum upload ou publicação será executado pelo aplicativo nesta versão**.

- O campo raiz `title` é o título principal do Short em pt-BR.
- `youtube.description`: descrição específica do episódio em pt-BR, com hashtags pertinentes e sem lista excessiva.
- `youtube.tags`: termos de busca concisos e relevantes, sem `#` e sem duplicatas.
- `youtube.category_id`: ID válido da categoria; use `27` (Education) para episódios educativos, salvo se outra categoria se encaixar melhor.
- `youtube.default_language`: sempre `pt-BR`.
- `youtube.status.privacy_status`: sempre `private` como padrão de revisão.
- `youtube.status.license`: `youtube`; `embeddable` e `public_stats_viewable`: `true`.
- `youtube.status.self_declared_made_for_kids`: booleano. Use `true` somente para conteúdo especificamente direcionado a crianças; dinossauros por si só não determinam essa opção. Para documentário geral, use `false`.
- `youtube.status.contains_synthetic_media`: marque `true` quando houver cenas fotorrealistas geradas por IA que pareçam retratar uma situação real que não aconteceu. Ilustrações claramente não realistas não precisam ser marcadas apenas por terem sido geradas por IA.
- `youtube.notify_subscribers`: `true`.
- `youtube.captions`: indique preparo de legenda em pt-BR no formato VTT. Não invente timestamps no JSON; a temporização depende do áudio final e ficará para implementação posterior.
- Não inclua data, hora, fuso, `publishAt`, credenciais, tokens, ID privado do canal ou caminhos temporários. O agendamento será configurado na aplicação quando a integração existir.
- O bloco `youtube` não aciona API nesta versão. Não afirme que o Short foi enviado, agendado ou publicado.

### Legendas e arquivos

- `captions.enabled` atual controla apenas legendas incorporadas visualmente no MP4 e deve continuar `false` por padrão. Mantenha `captions.theme` como `modern_blue`.
- As futuras legendas VTT do YouTube são independentes das legendas visuais. Nesta versão, não gere nem envie arquivo VTT separado; o JSON apenas registra o idioma/formato desejado para uma implementação futura.
- Entregue exatamente dois arquivos separados:
  1. `modelo_projeto.json`: roteiro e metadados preparados.
  2. `imagens_cenas.zip`: uma imagem para cada cena, preferencialmente na raiz do ZIP, sem subpastas.
- Os nomes devem coincidir exatamente entre `image_path` e arquivos do ZIP. Não inclua imagens extras sem uso.

### Formato do modelo JSON

O contrato de renderização atual deve ser preservado. O único bloco novo é `youtube`, opcional, com os subcampos definidos abaixo. Não altere `narration` de string para objeto e não acrescente tradução em outro idioma.

```json
{
  "title": "Título curto em português do Short",
  "profile": "short_vertical",
  "voice": "pf_dora",
  "speech_speed": 1.0,
  "visual_style": "cinematic digital illustration, mature visual tone, cohesive color palette, dramatic natural lighting",
  "captions": {
    "enabled": false,
    "theme": "modern_blue"
  },
  "scenes": [
    {
      "id": "cena_01_gancho",
      "narration": "Fala exata desta cena em português brasileiro.",
      "image_path": "cena_01_gancho.png",
      "motion": "slow_push_in"
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
      "contains_synthetic_media": true
    },
    "notify_subscribers": true,
    "captions": {
      "enabled": true,
      "language": "pt-BR",
      "format": "vtt"
    }
  }
}
```

Regras do JSON:

- Preserve todos os campos atuais: `title`, `profile`, `voice`, `speech_speed`, `visual_style`, `captions.enabled`, `captions.theme` e `scenes`, sem mudar nomes ou tipos.
- `title`: título curto e atraente em pt-BR, sem mudar o tema.
- `profile`: sempre `short_vertical`.
- `voice`: use `pf_dora` como padrão. As opções pt-BR conhecidas são `pf_dora` (Dora, feminina), `pm_alex` (Alex, masculina) e `pm_santa` (Santa, masculina); a seleção ocorre na interface.
- `speech_speed`: sempre `1.0`.
- `visual_style`: instrução curta em inglês para manter unidade visual; não descreva as cenas nesse campo.
- `captions.enabled`: sempre `false`; o usuário pode ativá-las na interface. `captions.theme`: sempre `modern_blue`.
- `scenes`: 6 a 8 cenas em ordem. Cada cena terá somente `id`, `narration`, `image_path` e `motion`.
- `id`: único, curto, sem espaços e contendo somente letras sem acento, números, hífen ou sublinhado.
- `narration`: texto não vazio em português brasileiro, até 1200 caracteres por cena; soma de 125 a 145 palavras.
- `image_path`: obrigatório; somente o nome do arquivo PNG/JPG/JPEG/WebP, sem diretório ou caminho absoluto. Deve existir uma vez no ZIP e representar a cena.
- `motion`: escolha somente `slow_push_in`, `slow_pull_out`, `pan_left`, `pan_right`, `pan_up`, `pan_down`, `static` ou `auto`.
- `youtube` é opcional em relação ao contrato antigo; quando incluído, use exatamente os campos e tipos do exemplo. Não acrescente chaves aleatórias.
- Não inclua `image_prompt`, descrição da cena, `seed`, `negative_prompt`, `lora`, `controlnet`, `music_path`, data/hora de publicação, credenciais ou campos fora do contrato acima.
- O JSON deve ser válido, sem comentários, vírgula sobrando, bloco Markdown ou texto adicional.

### Validação e entrega

Antes de entregar, valide sintaxe e tipos; confirme que campos antigos mantêm os mesmos nomes/tipos; confira IDs, movimentos, contagem de palavras e correspondência exata entre `image_path` e ZIP. Confirme que o bloco opcional `youtube` não contém agenda, credenciais ou dados de outro idioma. Entregue links para `modelo_projeto.json` e `imagens_cenas.zip`; mostre prévias das imagens ou links individuais. Informe título e duração estimada em uma linha, sem duplicar a narração.

---

## Entrada do usuário

**Título ou tema:** `[escreva aqui somente o título ou tema do Short]`
