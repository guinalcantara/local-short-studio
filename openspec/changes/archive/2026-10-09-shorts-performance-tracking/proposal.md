## Why

Hoje o Local Short Studio registra como um Short foi produzido, mas não oferece um local para relacionar escolhas editoriais a resultados reais coletados no YouTube Studio. Um acompanhamento local e manual permite comparar hipóteses com dados sem adicionar credenciais, APIs externas, GPU ou promessas de causalidade.

## What Changes

- Adicionar uma área **Resultados do canal** no Streamlit para cadastrar Shorts manualmente ou iniciar um acompanhamento a partir de um MP4 já renderizado/publicado.
- Persistir vídeos, snapshots cumulativos de métricas, hipóteses e próximos testes em SQLite local versionado sob o volume `input/analytics/`.
- Capturar um snapshot imutável das escolhas de produção comprovadas para uma versão de MP4, sem copiar referências vocais, caminhos privados, tokens ou credenciais.
- Permitir editar medições por identidade estável, consultar histórico, filtrar vídeos e comparar grupos por horizonte declarado e idade real com tolerância explícita.
- Calcular apenas métricas derivadas com denominadores compatíveis, incluindo inscritos por mil visualizações engajadas, e fornecer sugestões determinísticas transparentes apenas quando houver amostra suficiente.
- Documentar a operação manual, a origem dos campos no YouTube Studio, as regras de comparabilidade e os limites analíticos.

## Capabilities

### New Capabilities

- `channel-performance`: cadastro local de resultados, snapshots de métricas, comparações e hipóteses editoriais sem integração externa.

### Modified Capabilities

- Nenhuma. O contrato portátil do projeto, o cache de renderização, as saídas existentes e a publicação OAuth permanecem inalterados; a nova área apenas pode ler artefatos já disponíveis para pré-preenchimento comprovado.

## Impact

- Novos módulos previstos para modelos/validação, repositório SQLite, cálculos de comparação e componentes da interface.
- `app/ui.py` recebe uma nova seção, sem criar outro aplicativo ou exigir CUDA/OAuth para usá-la.
- `docker-compose.yml` já monta `input/`, portanto não requer novo volume ou dependência Python pesada.
- Nenhum campo será adicionado a `VideoProject`, ao ZIP de imagens, ao manifesto/cache de renderização ou aos registros de upload. Falhas de analytics não podem alterar renderização nem reabrir/publicar uploads.
