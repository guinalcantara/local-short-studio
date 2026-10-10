## 1. Consultas Analytics compatíveis

- [x] 1.1 Substituir a consulta `day,video` por consultas por vídeo com filtro e dimensão temporal compatíveis; verificar com mocks que cada ID acessível gera a requisição Analytics esperada.
- [x] 1.2 Registrar linhas retornadas com identificador de vídeo e dia, além da cobertura e falhas por vídeo no manifesto; verificar com testes que ausência de linhas não é tratada como valor inventado.
- [x] 1.3 Diferenciar erro de relatório incompatível de erro de OAuth/API desativada na mensagem ao usuário; verificar com mocks de HTTP 400, 401/403 e 429.

## 2. Compatibilidade e validação

- [x] 2.1 Atualizar a documentação do arquivo analítico para explicar a coleta por vídeo e a cobertura parcial; verificar que não há mudança no fluxo de geração ou publicação.
- [x] 2.2 Reconstruir o container e executar a suíte completa, incluindo a consulta Analytics corrigida; verificar `docker compose config`, OpenSpec estrita e ausência de alterações em pipeline, renderer e schemas.
