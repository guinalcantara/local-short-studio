## Context

Veja `proposal.md` para a motivação e `specs/channel-performance/spec.md` para o contrato. O app é Streamlit em um único serviço Docker e já monta `input/` e `output/` como volumes persistentes. Hoje o estado de render e upload pode ser lido em `app/ui.py`, workspaces e registros de publicação, mas não há repositório para resultados editoriais.

## Goals / Non-Goals

**Goals:**

- Persistir resultados manuais localmente sem dependência externa, GPU ou OAuth.
- Separar validação/modelos, SQLite, cálculos de comparação e apresentação Streamlit.
- Pré-preencher o acompanhamento de um resultado disponível apenas com evidências locais verificáveis.
- Tornar seleção temporal, denominadores e tamanho de amostra auditáveis na interface.

**Non-Goals:**

- Consumir YouTube Analytics API, modificar OAuth, importar CSV, coletar automaticamente ou agendar lembretes.
- Alterar `VideoProject`, ZIP, cache de renderização, duração padrão, mecanismos de voz ou fluxo de upload.
- Inferir tema, série, formato ou causalidade com IA; sugerir viralização ou localizar quedas por cena.

## Decisions

### SQLite local versionado em `input/analytics/`

Usar `sqlite3` da biblioteca padrão em `input/analytics/performance.sqlite3`, com criação/migração transacional controlada por versão de schema. O diretório já é persistente no Compose, não pertence a `input/youtube/` e não deve ser versionado. Consultas usarão parâmetros e conexões curtas por operação.

Alternativas consideradas: JSON no workspace (dificulta filtros, integridade e uso por vídeos antigos) e dependência ORM/serviço externo (aumentam peso e fogem do MVP).

### Domínios separados e snapshots imutáveis

Criar módulos dedicados para modelos/validação, armazenamento e análise, deixando `app/ui.py` como orquestrador da seção. As entidades principais serão vídeo, snapshot de produção, medição e hipótese/teste. O snapshot guarda campos editoriais e evidências de versão serializados no registro analítico; não retém caminho privado, áudio de referência ou credenciais.

Alternativa considerada: adicionar campos analíticos ao `VideoProject`. Foi rejeitada porque o JSON precisa permanecer portátil e orientado à produção, não ao histórico de canal.

### Datas inequívocas e política explícita de comparabilidade

Entradas serão apresentadas em America/Sao_Paulo e convertidas para ISO 8601 com offset antes de persistir. A idade real é `coleta - publicação` quando ambas existem. Para comparações de 48h, 7d ou horizonte personalizado com alvo em horas, selecionar uma única medição por vídeo: a mais próxima do alvo dentro da tolerância configurada; em empate, a coleta mais recente. Medições sem idade ou fora da tolerância aparecem no histórico, mas não nos agregados. O painel mostra a tolerância e a medição escolhida.

Alternativa considerada: usar somente o rótulo declarado do horizonte. Foi rejeitada porque um snapshot coletado após doze dias não é comparável a uma observação de sete dias.

### Agregações conservadoras e sugestões determinísticas

Os cálculos recebem apenas valores válidos e usam mediana por grupo, acompanhada pela contagem específica de cada métrica. `inscritos_por_1000_visualizacoes_engajadas` é nulo sem numerador/denominador válidos. Sugestões usam diferenças descritivas entre grupos comparáveis e uma barreira configurável de amostra; apresentam valores e não afirmam significância, causalidade ou probabilidade individual.

Alternativa considerada: score composto de viralização. Foi rejeitada por esconder denominadores, misturar métricas e induzir interpretação causal.

### Integração UI sem acoplamento à geração

Adicionar uma seção dedicada na página Streamlit, disponível antes ou depois da geração. O botão **Acompanhar este Short** aparece somente para um resultado final presente na sessão e cria um formulário com dados comprovados do MP4/projeto/configuração efetiva atual. O cadastro manual continua independente. A seção nunca instancia `ShortPipeline`, `WorkspacePipeline`, TTS, Whisper ou APIs do YouTube.

Alternativa considerada: cadastrar automaticamente todo render. Foi rejeitada para evitar duplicatas e histórico não consentido.

## Risks / Trade-offs

- [Dados manuais podem estar incompletos ou inconsistentes] → validação distingue desconhecido de zero, preserva observações manuais e mostra cobertura da amostra.
- [SQLite pode falhar ou o volume ser removido] → transações, erros claros e isolamento: nenhuma operação analítica participa do caminho de render/upload.
- [Medições com idades distintas podem gerar comparação enganosa] → horizonte, idade e tolerância são visíveis e exclusões não são silenciosas.
- [Pré-preenchimento pode capturar informação não efetiva] → incluir somente evidências disponíveis no resultado/manifesto/configuração atual e permitir edição de campos editoriais pelo usuário.

## Migration Plan

1. Criar o banco vazio e o schema inicial sob demanda, sem fixtures reais.
2. Exibir painel vazio e cadastro manual mesmo sem render, GPU ou OAuth.
3. Adicionar integração opcional com resultado da sessão sem mudar JSON, ZIP, cache ou arquivos de publicação.
4. Para rollback, remover a área da UI preserva o banco local; não há migração destrutiva nem impacto em renders existentes.
