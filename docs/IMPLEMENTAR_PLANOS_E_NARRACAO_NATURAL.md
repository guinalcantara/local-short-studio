# Implementar múltiplos planos por cena e narração natural

**Estado:** implementado na branch `feature/planos-narracao-natural`. Este documento permanece como especificação e checklist de regressão do recurso.

Cole este documento como tarefa para o agente no VS Code, na raiz de `local-short-studio`. Implemente o recurso completo, incluindo código, testes e documentação. Leia `AGENTS.md`, `README.md`, `docs/PROJECT_PLAN.md`, `docs/USER_GUIDE.md` e `docs/TROUBLESHOOTING.md` antes de editar. O prompt de produção correspondente está em `ideias/PROMPT_GERAR_MODELO_PROJETO_SHORT.md`.

## Objetivo e limite desta etapa

Implementar as melhorias **1. vários planos visuais por cena** e **2. narração por bloco de pensamento**. O resultado deve aceitar projetos antigos com uma imagem por cena e projetos novos com `shots`, sem alterar os metadados `youtube`. Não incluir nesta etapa o redesenho de transições entre cenas, mixagem/ducking, efeitos sonoros, música automática ou editor de prévia. Esses itens serão tratados depois da validação desta fase.

O contrato com `shots` está ativo. Projetos legados sem esse campo continuam aceitos.

## Comportamento esperado

Uma cena continua sendo uma unidade narrativa: seu `narration` é uma string completa, gerada uma vez pelo mecanismo de voz. Seus 2 a 4 planos mostram imagens diferentes enquanto esse mesmo áudio toca sem cortes. O primeiro plano começa no início da cena. Os demais começam no instante da primeira palavra de uma frase âncora extraída da narração, medido após a geração do WAV. As imagens do ZIP continuam sendo preparadas fora do aplicativo.

Exemplo mínimo ilustrativo (o projeto real ainda precisa dos demais campos obrigatórios):

```json
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
```

### Contrato e compatibilidade

- Em `app/schemas.py`, acrescentar `Shot` estrito (`extra="forbid"`) com `image_path: str`, `start_phrase: str | None` e `motion: Motion | None`. Reutilizar a mesma validação de basename/extensão de `Scene.image_path` para `Shot.image_path`; não aceitar pastas, caminhos absolutos ou campos arbitrários.
- Acrescentar `shots: list[Shot] | None = None` a `Scene`. Ausência de `shots` significa o comportamento antigo: um plano com `scene.image_path` e `scene.motion`. Se `shots` existir, exigir 2 a 4 elementos. O primeiro deve **omitir** `start_phrase`; todos os seguintes exigem uma frase não vazia. `shots[0].image_path` deve ser igual a `scene.image_path` (comparação exata), preservando o campo antigo. Um `shot.motion` ausente herda `scene.motion`. Rejeitar caminhos de imagem repetidos em planos diferentes, inclusive variações de caixa, mas não contar a repetição obrigatória de `scene.image_path` em `shots[0]` como outra imagem.
- Validar cada `start_phrase` como sequência de palavras contígua e única na `narration` da mesma cena, em ordem crescente. Normalizar espaços, maiúsculas e pontuação apenas para localizar palavras; conservar texto original no JSON e na narração. Não permitir âncora que atravessa duas frases ou que aparece duas vezes. A validação de texto deve ocorrer antes do TTS. Reportar cena, índice do plano e frase problemática.
- Preservar `narration` como string e todos os demais campos/tipos atuais, inclusive `seed` histórico e `youtube`. `examples/modelo_projeto.json` antigo deve continuar válido. Não tornar `shots` obrigatório para todo projeto.
- Não alterar a assinatura pública sem adaptar os testes existentes. Se for preciso um objeto de timeline, definir tipos explícitos para cena/plano e manter um caminho de compatibilidade para `render_video` chamado com uma imagem por cena.

### Narração: `app/pipeline.py`, `app/tts.py` e `app/tts_chatterbox.py`

1. Em `_build_voice_track`, gerar `scene.narration.strip()` **uma vez por cena**, sem `split_sentences` e sem adicionar silêncio fixo de `0.12 s` após cada frase. A pontuação do próprio texto orienta o TTS. Manter o pequeno `audio_padding_seconds` **entre cenas** e o hold final já configurados.
2. Introduzir uma operação com nome coerente (`generate_block` ou equivalente) nos dois mecanismos, reaproveitando as chamadas de TTS existentes. Kokoro deve receber voz e velocidade já selecionadas. Chatterbox deve manter referência de voz e parâmetros atuais; o método atual descarta `speed`, então não anunciar controle de velocidade para ele. Se um mecanismo exigir divisão por limite real do modelo, dividir apenas em fronteiras semânticas justificadas, sem pausa fixa após cada frase e sem repetir/omitir texto. Registrar esse caso nos testes.
3. Escrever um WAV por cena e `narration.wav` como hoje. Criar cue de legenda para o bloco inteiro da cena, com início/fim medidos pelos samples; o agrupamento curto e as palavras continuam responsabilidade de `app/captions.py` e do alinhamento. Não gerar legenda durante o padding entre cenas. Preservar liberação do modelo após a síntese para caber na RTX 2060 de 6 GB.
4. Não presumir que 125 a 145 palavras equivalem exatamente a 55 a 70 segundos. O áudio gerado define a duração real do vídeo.

### Sincronização dos planos: `app/whisper_alignment.py` e pipeline

1. Depois de gerar `narration.wav`, obter timestamps por palavra sempre que houver qualquer cena com `shots`, **mesmo com legendas visuais desativadas**. Se as legendas estiverem ativas, reutilizar a mesma transcrição; não carregar/transcrever o Whisper duas vezes. Projetos antigos sem legendas e sem `shots` não precisam de Whisper. O download inicial do modelo `small` também passa a ocorrer em projetos novos sem legendas.
2. Usar o texto original da narração como referência para casar cada `start_phrase` com palavras observadas. **Não usar diretamente `align_caption_cues(...).words` como prova do corte:** essa função atribui tempos também a palavras substituídas ou interpoladas para preservar legendas, como `tests/test_whisper_alignment.py` demonstra com “rex”/“Hex”. Para o corte, manter o mapeamento entre tokens esperados e tokens realmente reconhecidos; exigir correspondência lexical da âncora e timestamps observados coerentes, ou falhar de forma explícita. A frase âncora determina o início do plano pela primeira palavra, não pelo fim da frase.
3. Trabalhar com tempos absolutos do WAV e limites de cada cena. Verificar que os tempos dos planos são estritamente crescentes e ficam dentro da cena; a duração de um plano vai até a próxima âncora ou até o fim da cena. O padding entre cenas pertence ao último plano da cena anterior. Se uma âncora não tiver alinhamento confiável ou produzir plano de duração menor que alguns frames, falhar com mensagem que indique cena/frase e peça ajuste do roteiro, em vez de cortar no tempo errado ou dividir por porcentagem.
4. Se a transcrição falhar, manter o erro visível. Não retornar silenciosamente ao vídeo de uma imagem nem usar duração estimada para fingir sincronização.

### ZIP, UI e renderizador

- Em `app/pipeline.py` e `app/ui.py`, montar a lista de **todos os** `shots[].image_path`; para cenas antigas, usar `scene.image_path`. Não acrescentar `scene.image_path` pela segunda vez nas cenas novas: ele é o mesmo arquivo que `shots[0]`. Passar essa lista a `validate_image_zip` antes de liberar a geração. Copiar cada imagem usada para a pasta da execução com nome que não colida entre planos/cenas (por exemplo, ID da cena mais índice do plano), sem extrair caminhos do ZIP. Preservar limites, detecção de duplicatas e demais verificações de `app/image_archive.py`. Para projetos antigos, manter a convenção atual `images/<scene.id>.<ext>` se possível.
- Mostrar na interface quantidade de cenas e planos, nomes ausentes e indicação clara de que o alinhamento por Whisper será necessário em projetos com `shots`. Desativar a geração quando o JSON/ZIP não satisfizer o contrato. `image_path` repetido em `scene` e `shots[0]` é uma referência à mesma imagem, não dois arquivos distintos.
- Em `app/renderer.py`, a API atual recebe listas de imagens e durações do **mesmo tamanho**, uma entrada por cena. Adicionar uma estrutura explícita de planos/durações por cena e adaptar o pipeline sem achatar as durações por imagem. Montar cada plano com seu movimento (ou o herdado), respeitando a duração real calculada pelo áudio. Juntar os planos de uma mesma cena com cortes internos simples; manter o crossfade **atual entre cenas**, sem aplicar fade em toda troca de plano. Uma estratégia é renderizar os planos no mesmo FPS/formato, concatená-los em um clipe por cena e passar esses clipes à lógica de `xfade` existente. O caminho antigo de uma imagem por cena deve continuar coberto por `tests/test_pipeline_zip.py` e `tests/test_renderer_smoke.py`.
- Arredondar durações para frames de forma que a soma dos planos cubra exatamente a cena. Aplicar ao último plano a extensão de transição/hold usada hoje, sem deslocar áudio ou legendas. A duração final deve continuar próxima de `sum(scene_audio_durations) + scene_hold_seconds`, tolerando um frame de arredondamento.
- Preservar controle global de movimentos, música e legendas existentes. Com movimentos desativados, todos os planos ficam estáticos, mas continuam trocando nos instantes alinhados.

## Sequência sugerida para desenvolver no VS Code

1. Criar o esquema `Shot`, os validadores e testes do JSON antigo/novo.
2. Mudar a síntese para um bloco por cena e provar com teste de TTS falso que uma cena com duas frases chama o mecanismo uma vez e não injeta pausas internas.
3. Calcular inícios de planos a partir das palavras *observadas* alinhadas; testar com timestamps controlados, inclusive legenda desligada, frase repetida/ausente, pontuação, acentos, transcrição errada que antes seria interpolada e âncoras próximas.
4. Expandir validação/cópia do ZIP e feedback da interface para todos os planos.
5. Renderizar a timeline visual, preservando o áudio contínuo, o hold e o crossfade entre cenas.
6. Atualizar `README.md`, `docs/PROJECT_PLAN.md`, `docs/USER_GUIDE.md`, `docs/TROUBLESHOOTING.md` e um exemplo real em `examples/` para descrever os dois contratos. Só então remover do prompt o aviso de que `shots` ainda não está implementado.

## Critérios de aceite

- Um projeto antigo, com uma imagem por cena, gera o mesmo tipo de MP4 e não aciona Whisper quando legendas estão desligadas.
- Um projeto com duas imagens na mesma cena mantém uma narração contínua; a segunda aparece quando a frase âncora começa. O corte funciona com legendas ligadas e desligadas.
- Uma cena com duas frases chama o TTS uma vez no caso normal e não ganha `0.12 s` após cada frase ou ao final da cena. O padding entre cenas permanece.
- O ZIP é validado antes de gerar voz para todas as imagens usadas; caminhos perigosos, basenames duplicados, imagem ausente e limites continuam bloqueados. O primeiro plano não duplica o arquivo por aparecer também em `scene.image_path`.
- Falhas de frase ambígua, ausência de timestamp e duração visual inviável trazem erro específico. O render não gera vídeo aparentemente válido com imagem ou palavra errada.
- Um smoke test com duas imagens de cores distintas confere frames imediatamente antes e depois do instante de âncora, além de verificar streams e duração com `ffprobe`. O MP4 vertical mantém áudio, movimentos opcionais, legendas sincronizadas quando ativadas, música opcional e crossfade atual entre cenas. Nenhuma publicação é acionada pelo bloco `youtube`.

## Validação

Rode, no ambiente que contém as dependências, a suíte completa e a configuração do Compose. No Windows, use preferencialmente o container conforme `AGENTS.md`:

```powershell
docker compose config
docker compose config --services
docker compose up --build -d
docker compose run --rm --no-deps -v "${PWD}/tests:/workspace/tests:ro" app python -B -m unittest discover -s /workspace/tests -v
```

`docker compose config --services` deve listar só `app` no perfil padrão. Para teste manual, gere um Short curto com dois planos na primeira cena, sem legendas, e outro com legendas; escute a continuidade entre frases e confira por amostragem o instante do corte, a duração final e as legendas. Registre qualquer diferença de comportamento entre Kokoro e Chatterbox. Os testes de render podem usar FFmpeg/libx264 e imagens pequenas; não exigem baixar modelos para provar a lógica da timeline.

## Resultado esperado da tarefa

Entregar código, testes pertinentes, exemplo atualizado e documentação coerente, com resumo das mudanças e dos comandos realmente executados. Não dar esta fase como concluída somente porque o JSON novo passa na validação: é preciso verificar voz, alinhamento e troca de imagens no MP4.
