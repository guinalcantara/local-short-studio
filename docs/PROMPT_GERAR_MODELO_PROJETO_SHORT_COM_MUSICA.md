# Prompt para gerar roteiro, modelo JSON e ZIP de imagens

Copie as instruções abaixo para um chat com geração de imagens. No fim, informe somente o título ou tema do Short. O chat deverá entregar `modelo_projeto.json` e `imagens_cenas.zip` para o Local Short Studio.

> **Compatibilidade:** `scenes[].shots`, `transition_to_next` e `soundtrack` fazem parte do contrato ativo. O catálogo e os MP3s abaixo já estão embutidos no projeto e na imagem Docker; o aplicativo resolve `soundtrack.track_id` automaticamente, sem caminho de arquivo no JSON.

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
- O primeiro plano de cada cena começa no início da fala e **não tem** `start_phrase`. Cada plano seguinte tem `start_phrase`: uma sequência curta e exata de palavras presente **uma única vez** na `narration` da própria cena. Copie o trecho literalmente do texto falado. A sequência deve estar dentro de uma frase, não atravessar duas. Não use segundos estimados.
- `start_phrase` indica o instante da **primeira palavra** em que a imagem deve mudar. Palavras posteriores servem apenas para tornar a âncora única e não atrasam o corte até o fim do trecho. Escolha sempre as primeiras palavras da ideia em que o novo plano deve começar.
- Use de **2 a 4 palavras** por `start_phrase`. Prefira palavras comuns, curtas e fáceis de reconhecer na fala. Não prolongue uma âncora apenas para dar contexto: quanto mais palavras ela tiver, maior será a possibilidade de uma divergência na transcrição do Whisper.
- Evite incluir em `start_phrase` nomes científicos ou próprios, siglas, números, palavras estrangeiras, termos raros e palavras cuja pronúncia ou grafia possa ser ambígua. Esses termos podem continuar na `narration`; escolha palavras comuns próximas como âncora.
- Escolha as frases âncora para que a imagem apareça junto da ideia narrada; evite um plano que antecipe a revelação antes da fala. Preserve a ordem dos planos e das frases âncora. Cada âncora precisa ser curta, contígua, literal e ocorrer uma única vez.
- `image_path` no nível da cena continua obrigatório para compatibilidade e deve ser **idêntico** ao `image_path` de `shots[0]`. Em cenas novas, inclua `shots` com 2 a 4 elementos. `motion` no nível da cena continua no JSON; cada plano pode omitir `motion` para herdar o da cena ou escolher um movimento permitido.
- Gere imagens verticais, preferencialmente 9:16, com margem segura para um eventual corte. Mantenha unidade de estilo, paleta e iluminação, variando enquadramento e escala conforme a fala. Use estilo adulto e cinematográfico, salvo se o assunto pedir outro.
- Descreva concretamente assunto, quantidade, aparência, pose, partes importantes visíveis, posição no quadro, cenário, enquadramento e luz. Para anatomia complexa, use pose simples e legível, sem sobreposição de partes relevantes. Por exemplo, um tiranossauro rex deve ter uma cabeça e mandíbula, um par de braços curtos junto ao peito, duas pernas traseiras e cauda ligada à pelve.
- Não peça texto, legendas, placas legíveis, logotipos ou marcas-d'água nas imagens. Confira cada imagem quanto ao assunto, composição vertical e defeitos evidentes; regenere apenas a imagem problemática.
- Salve PNG, JPG, JPEG ou WebP com nomes simples e únicos, sem diretórios. Use exatamente os mesmos nomes em cada `shots[].image_path` e no ZIP. Exemplo: `cena_01_plano_01.png`, `cena_01_plano_02.png`.
- Se a geração de imagens não estiver disponível, diga isso claramente. Não simule arquivos nem entregue JSON que aponta para imagens inexistentes.

### Transições entre cenas

- Em cada cena, exceto a última, escolha `transition_to_next` pela função narrativa. Use `cut` em ganchos, revelações, respostas e mudanças rápidas; use `crossfade` quando lugar ou ideia continuam; use `fade_black` raramente, apenas para uma mudança clara de tempo ou assunto.
- Prefira `cut` e `crossfade` ao longo do Short. Não use duas passagens pelo preto seguidas e não alterne efeitos mecanicamente.
- Não marque tempos na narração nem nos planos. Em geral, omita `duration_seconds` para usar o padrão do app. Se houver uma justificativa editorial, `crossfade` e `fade_black` aceitam de 0.15 a 0.45 segundo; `cut` nunca aceita duração.
- A última cena deve omitir `transition_to_next`. As transições são somente visuais e não criam pausas ou fades no áudio.

### Trilha única do Short

- Escolha **uma única** faixa para o Short inteiro no catálogo abaixo, considerando o tom predominante do roteiro e o espaço necessário para a voz. Não troque de música por cena, não repita o nome da faixa em `scenes` e não use efeitos sonoros nesta etapa.
- No JSON, escreva `soundtrack` com `track_id` e `volume_percent`. O ID deve aparecer exatamente na tabela; copie o volume indicado para ele, sem alterar. O volume será um teto conservador: o aplicativo poderá diminuí-lo ainda mais depois de medir a narração real. Não acrescente `music_path` ou caminho de arquivo inventado.
- Para assuntos sérios, prefira música contida; para mistérios, uma trilha intrigante sem se sobrepor à explicação; para ação, uma trilha grandiosa sem picos dominantes. Considere o Short completo, inclusive gancho e conclusão.
- As descrições de clima são **estimativas editoriais** baseadas em nomes, metadados e medições dos áudios; não houve revisão auditiva humana. Não afirme que a faixa é instrumental, licenciada ou livre de reivindicação. Autor, licença, URL de origem e atribuição precisam ser verificados antes da publicação. Não crie crédito fictício na descrição do YouTube.
- Os arquivos `faixas/revisar_*` no pacote foram mantidos para conferência, mas **não são candidatos** para seleção: incluem três marcados como preview, uma faixa com provável voz, um efeito curto e uma duplicata exata.

| ID | Clima e uso sugerido | Volume |
| --- | --- | ---: |
| `american_frontiers_aaron_kenny` | Aventura/viagem — cowboys, viagens, história | 11% |
| `enchante_vendredi` | Aventura/viagem — viagem, curiosidade descontraída | 5% |
| `flying_high_nao_identificado` | Aventura/viagem — exploração, realização | 5% |
| `let_go_tubebackr` | Aventura/viagem — viagem, descoberta otimista | 7% |
| `lights_roa` | Aventura/viagem — paisagens, descoberta | 5% |
| `lioness_dayfox` | Aventura/viagem — aventura, energia positiva | 4% |
| `mamacita_mike_leite` | Aventura/viagem — viagem, festa, verão | 5% |
| `paradise_ikson` | Aventura/viagem — viagem, paisagens | 3% |
| `rebirth_peyruis` | Aventura/viagem — recomeço, descoberta | 4% |
| `wakanda_mona_wonderlick` | Aventura/viagem — viagem, exploração | 7% |
| `wake_up_instrumental_wataboi` | Aventura/viagem — ritmo rápido, superação | 6% |
| `dramatic_orchestral_jp_bianchini` | Épico/cinematográfico — virada grande, batalha, dinossauros | 4% |
| `imperial_forces_aaron_kenny` | Épico/cinematográfico — impérios, guerra, clímax | 6% |
| `legionnaire_scott_buckley` | Épico/cinematográfico — Roma, guerra antiga, narrativa épica | 4% |
| `saving_the_world_aaron_kenny` | Épico/cinematográfico — resgate, aventura, clímax | 4% |
| `be_happy_dj_quads` | Leve/otimista — curiosidades simpáticas, cotidiano | 7% |
| `good_starts_jingle_punks` | Leve/otimista — gancho simpático, curiosidades | 7% |
| `good_vibes_nao_identificado` | Leve/otimista — conteúdo leve, entretenimento | 5% |
| `picnic_ashamaluevmusic` | Leve/otimista — curiosidades leves, natureza, rotina | 4% |
| `sophomore_makeout_silent_partner` | Leve/otimista — humor, nostalgia leve | 4% |
| `spring_in_my_step_silent_partner` | Leve/otimista — curiosidade divertida | 3% |
| `springtime_stroll_secret_crates` | Leve/otimista — natureza, curiosidade positiva | 4% |
| `venice_beach_topher_mohr_and_alex_elena` | Leve/otimista — viagem, cotidiano, humor | 4% |
| `whistling_down_the_road_silent_partner` | Leve/otimista — cowboys leves, viagem | 4% |
| `you_re_no_help_silent_partner` | Leve/otimista — comédia, cultura pop | 3% |
| `better_days_lakey_inspired` | Nostálgico/reflexivo — superação, encerramento caloroso | 5% |
| `fade_knowmadic` | Nostálgico/reflexivo — memória, contemplação | 5% |
| `far_away_tomppabeats` | Nostálgico/reflexivo — memória, solidão | 6% |
| `longing_joakim_karud` | Nostálgico/reflexivo — lembrança, emoção sutil | 4% |
| `no_10_a_new_beginning_esther_abrami` | Nostálgico/reflexivo — descoberta, esperança | 7% |
| `remember_roa` | Nostálgico/reflexivo — memória, história pessoal | 9% |
| `warm_nights_lakey_inspired` | Nostálgico/reflexivo — lembranças, reflexão suave | 5% |
| `wondering_atch` | Nostálgico/reflexivo — descoberta, nostalgia | 4% |
| `acting_melodiesinfonie` | Suspense/mistério — pistas, investigação leve | 4% |
| `clocks_smith_the_mister` | Suspense/mistério — contagem, descoberta, mistério leve | 7% |
| `dystopia_luke_hall` | Suspense/mistério — ameaça, distopia, predadores | 4% |
| `midsommar_scott_buckley` | Suspense/mistério — lenda, natureza misteriosa | 7% |
| `nomad_saiko` | Suspense/mistério — exploração solitária, mistério | 5% |
| `canals_joakim_karud` | Urbano/lo-fi — curiosidade urbana, rotina | 4% |
| `chill_day_lakey_inspired` | Urbano/lo-fi — explicação leve, cotidiano | 4% |
| `chill_funky_jazzy_lofi_hip_hop_nao_identificado` | Urbano/lo-fi — listas leves, cultura pop | 11% |
| `chill_jazzy_lofi_hip_hop_nao_identificado` | Urbano/lo-fi — explicações tranquilas | 6% |
| `ice_tea_not_the_king` | Urbano/lo-fi — humor, cotidiano, games | 4% |
| `know_myself_patrick_patrikios` | Urbano/lo-fi — cultura pop, humor leve | 4% |
| `mood_peyruis` | Urbano/lo-fi — explicação leve e urbana | 5% |

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
- Entregue exatamente dois arquivos: `modelo_projeto.json` (roteiro, metadados e ID da trilha) e `imagens_cenas.zip` (todas as imagens usadas, preferencialmente na raiz). A música é resolvida automaticamente pelo catálogo embutido no aplicativo; não inclua MP3 no ZIP de imagens.
- As legendas VTT futuras do YouTube são independentes das legendas incorporadas no MP4. Não gere arquivo VTT separado.

### Formato do JSON

Use os campos e tipos abaixo. O exemplo mostra somente duas cenas para explicar o formato; a entrega real deve conter 6 a 8 cenas e o total de palavras solicitado. `start_phrase` é texto copiado literalmente de `narration`, sem aspas adicionais. A primeira imagem da cena aparece em `image_path` e novamente em `shots[0].image_path` por compatibilidade.

```json
{
  "title": "Título curto do Short",
  "profile": "short_vertical",
  "voice": "pf_dora",
  "speech_speed": 1.0,
  "visual_style": "cinematic digital illustration, mature visual tone, cohesive color palette, dramatic natural lighting",
  "captions": { "enabled": false, "theme": "modern_blue" },
  "soundtrack": { "track_id": "acting_melodiesinfonie", "volume_percent": 4 },
  "scenes": [
    {
      "id": "cena_01_gancho",
      "narration": "Os braços do tiranossauro rex parecem inúteis. Mas os fósseis contam uma história mais interessante.",
      "image_path": "cena_01_plano_01.png",
      "motion": "slow_push_in",
      "shots": [
        { "image_path": "cena_01_plano_01.png" },
        { "image_path": "cena_01_plano_02.png", "start_phrase": "Mas os fósseis contam" }
      ],
      "transition_to_next": { "type": "crossfade" }
    },
    {
      "id": "cena_02_contexto",
      "narration": "Esses membros tinham músculos e articulações funcionais. Eles poderiam ajudar a segurar uma presa perto do peito.",
      "image_path": "cena_02_plano_01.png",
      "motion": "slow_pull_out",
      "shots": [
        { "image_path": "cena_02_plano_01.png" },
        { "image_path": "cena_02_plano_02.png", "start_phrase": "Eles poderiam ajudar" }
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

- Preserve os nomes e tipos de `title`, `profile`, `voice`, `speech_speed`, `visual_style`, `captions`, `scenes`, `id`, `narration`, `image_path`, `motion` e do bloco `youtube` já aceitos. As extensões visuais são `scenes[].shots` e `scenes[].transition_to_next`; `soundtrack` é a extensão de áudio ativa para uma única faixa no Short inteiro. JSONs antigos continuam válidos. `visual_style` descreve apenas a unidade visual em inglês; não inclua descrições de planos nesse campo.
- `id` é único e contém apenas letras sem acento, números, hífen ou sublinhado. `narration` tem até 1200 caracteres por cena. `image_path` é somente basename de uma imagem suportada. `motion` pertence a `slow_push_in`, `slow_pull_out`, `pan_left`, `pan_right`, `pan_up`, `pan_down`, `static` ou `auto`.
- Não inclua `image_prompt`, descrição visual, `seed`, `negative_prompt`, `lora`, `controlnet`, `music_path`, um segundo campo de música, duração ou timestamp por plano, campos de efeito sonoro ou chaves fora do contrato.
- O arquivo JSON deve ser válido, sem comentários, vírgulas sobrando, bloco Markdown ou texto adicional.

### Validação e entrega

Antes de entregar, valide o JSON e conte as palavras faladas. Confirme que cada cena tem 2 a 4 planos, que `shots[0].image_path == scene.image_path`, que cada `start_phrase` tem de 2 a 4 palavras, ocorre exatamente uma vez na fala da cena, começa exatamente no ponto desejado para a troca e evita termos difíceis para reconhecimento de voz. Confirme também que as âncoras estão em ordem. Confira `transition_to_next` em todas as cenas menos a última, sem duração em `cut` e sem passagens pelo preto consecutivas. Confira correspondência exata, sem duplicatas, entre todos os arquivos referenciados nos planos e as imagens do ZIP; a referência duplicada entre `scene.image_path` e `shots[0].image_path` aponta para **um único arquivo**. Confirme que existe exatamente um `soundtrack.track_id` da tabela e que `volume_percent` coincide com seu volume indicado. Confira também o bloco `youtube` e a ausência de dados de agendamento ou credenciais.

Entregue links para `modelo_projeto.json` e `imagens_cenas.zip`, com prévias ou links individuais das imagens. Informe título, faixa selecionada, volume e duração estimada em uma linha, sem duplicar a narração.

## Entrada do usuário

Título ou tema:

[escreva aqui somente o título ou tema do Short]
