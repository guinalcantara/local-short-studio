## 1. Modelos e persistência local

- [x] 1.1 Criar modelos e validadores para vídeo, snapshot de produção, medição, horizonte, hipótese e filtros; verificar testes de campos ausentes, inteiros/tempos não negativos, finitude, percentuais e IDs estáveis.
- [x] 1.2 Implementar repositório SQLite versionado em `input/analytics/` com migração transacional, queries parametrizadas e operações criar/editar/listar; verificar reabertura do banco e atualização idempotente de medições.
- [x] 1.3 Implementar regras de unicidade por ID YouTube e vínculo de versão/hash, preservando versões distintas; verificar testes de duplicidade e cadastro manual sem MP4.

## 2. Cálculos e comparabilidade

- [x] 2.1 Implementar conversão e persistência de datas com America/Sao_Paulo e cálculo de idade real apenas quando aplicável; verificar timezone, datas inválidas e idade desconhecida.
- [x] 2.2 Implementar seleção de uma medição por vídeo por horizonte/alvo/tolerância e agregações por grupo com medianas e cobertura por métrica; verificar exclusões por idade, dados ausentes e empate documentado.
- [x] 2.3 Implementar inscritos por mil visualizações engajadas e sugestões determinísticas conservadoras; verificar denominador zero/ausente, amostra insuficiente e ausência de score/alegação causal.

## 3. Integração com resultados existentes e UI

- [x] 3.1 Criar snapshot seguro de produção a partir de resultado final disponível, distinguindo configurações efetivas de JSON e de interface; verificar que não persiste áudio de referência, caminhos privados, tokens ou credenciais.
- [x] 3.2 Adicionar a seção Streamlit **Resultados do canal** com painel vazio, cadastro manual, edição de vídeo, formulários de medição/histórico e orientação de cópia dos campos do YouTube Studio; verificar navegação sem CUDA, TTS ou OAuth.
- [x] 3.3 Adicionar o fluxo explícito **Acompanhar este Short** para resultado final em sessão e filtros/tabela/detalhe de vídeo; verificar que abrir/revisar/renderizar não cadastra automaticamente e que versões distintas podem ser acompanhadas.
- [x] 3.4 Adicionar comparação de grupos, seleção de horizonte/tolerância e edição de hipóteses/próximos testes; verificar gráficos simples, amostra visível, métricas sem dados e exclusão de comparações não compatíveis.

## 4. Compatibilidade, documentação e validação

- [x] 4.1 Garantir que analytics não altera `VideoProject`, ZIP, caches, pipeline, registro de publicação ou OAuth; verificar testes de isolamento e que uma falha analítica não dispara upload.
- [x] 4.2 Atualizar README.md, docs/PROJECT_PLAN.md e docs/USER_GUIDE.md com cadastro, métricas, comparabilidade, limites e persistência local; verificar que não há promessa de viralização ou coleta automática.
- [x] 4.3 Executar testes novos e existentes no container, validar `docker compose config`, validar os artefatos OpenSpec e verificar manualmente o painel sem dados; registrar qualquer limitação real encontrada.
