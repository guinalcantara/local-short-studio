# Solicitação: adicionar Chatterbox PT-BR como alternativa de narração

Analise o estado atual do projeto antes de alterar qualquer arquivo. O projeto já recebeu atualizações recentes; use o código e a documentação atuais como fonte de verdade. Preserve as alterações existentes e adapte a implementação ao fluxo e à arquitetura que encontrar.

## Objetivo

Adicionar o Chatterbox com suporte a português brasileiro como alternativa local ao mecanismo de narração já existente, mantendo a opção atual. Durante a configuração de cada geração de vídeo, o usuário deve poder escolher qual mecanismo de voz será usado.

## Requisitos

- Manter o mecanismo de narração atual funcionando como está para quem o selecionar.
- Incluir uma opção clara para escolher entre o mecanismo atual e o Chatterbox PT-BR no fluxo de geração.
- Fazer com que a seleção escolhida naquela geração seja respeitada por todo o processamento do áudio.
- Exibir ou habilitar somente os controles de voz compatíveis com o mecanismo selecionado, reaproveitando os controles existentes quando fizer sentido.
- Executar a geração localmente com CUDA, integrada ao ambiente atual do projeto. Verifique a compatibilidade real das dependências, da versão do Python, do PyTorch e da configuração Docker antes de definir a implementação.
- Baixar ou carregar os modelos localmente e reutilizá-los entre gerações; não baixar pesos novamente a cada vídeo.
- Não trocar silenciosamente para outro mecanismo se houver erro. Apresentar uma mensagem clara com o motivo e instruções úteis para corrigir.
- Manter a geração de vídeo, roteiro, imagens, legendas e demais etapas atuais sem mudanças de comportamento.
- Atualizar somente a documentação necessária para instalar, configurar e usar a nova alternativa, seguindo o padrão e a estrutura atuais do projeto.

## Cuidados de implementação

1. Primeiro localize e entenda o fluxo atual de seleção de voz, geração de áudio, configuração CUDA/Docker e documentação relacionada.
2. Faça a menor alteração que se encaixe na arquitetura existente. Não reescreva partes não relacionadas nem remova funcionalidades.
3. Confira os requisitos oficiais e atuais do Chatterbox PT-BR e valide que o checkpoint escolhido corresponde a português brasileiro.
4. Se a configuração atual não comportar os dois mecanismos com segurança, explique o bloqueio e proponha uma solução compatível antes de fazer uma mudança estrutural ampla.
5. Não presuma caminhos, nomes de arquivos, telas, variáveis ou tecnologias que não existam no projeto atual.

## Critérios de aceite

- O usuário consegue escolher o mecanismo de voz no momento de gerar cada vídeo.
- Uma geração selecionada para usar o mecanismo atual continua funcionando.
- Uma geração selecionada para usar o Chatterbox produz áudio em português brasileiro usando CUDA, quando o ambiente e os pesos estiverem disponíveis.
- Erros de instalação, modelo ausente, CUDA ou geração são informados com clareza, sem troca automática de mecanismo.
- Os outros passos e resultados da geração permanecem compatíveis com o fluxo atual.
- A documentação explica os requisitos, a configuração local e como selecionar cada opção.
- Ao concluir, informe os arquivos alterados, decisões importantes e o teste executado para cada mecanismo. Se algum teste depender de pesos ou hardware indisponível no ambiente de desenvolvimento, declare isso claramente e forneça o comando de validação local.
