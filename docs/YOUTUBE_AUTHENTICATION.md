# Autenticação do YouTube para publicação

Este documento explica como conectar localmente a conta que publicará os vídeos. O Local Short Studio abre o fluxo OAuth no navegador, armazena o token somente em `input/youtube/` e pede confirmação antes de cada upload.

## Chave de API não publica vídeos

Uma chave de API identifica o projeto e atende requisições públicas, mas não concede acesso a um canal nem autoriza `videos.insert` ou `captions.insert`. Para enviar um Short é obrigatório autenticar o proprietário da conta pelo **OAuth 2.0**. O app pede `youtube.upload` para o MP4, `youtube.readonly` para identificar o canal e `youtube.force-ssl` para enviar a faixa de legenda opcional.

## Preparação no Google Cloud

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/) com a conta que administrará o projeto.
2. Crie ou escolha um projeto exclusivo para o Local Short Studio.
3. Em **APIs e serviços > Biblioteca**, habilite a [YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com).
4. Em **APIs e serviços > Tela de consentimento OAuth**, configure a tela, os dados de contato e os usuários de teste enquanto o projeto estiver em desenvolvimento.
5. Em **APIs e serviços > Credenciais**, crie um ID de cliente OAuth do tipo **Aplicativo para computador**. Baixe o JSON de credenciais somente para uso local.
6. Crie `input/youtube/` e salve o arquivo baixado como `input/youtube/client_secret.json`. Esse diretório já é ignorado pelo Git.
7. Inicie o app com Docker, abra a área **Publicar no YouTube** e clique em **Conectar nova conta**. A área fica disponível antes de gerar um MP4; conclua o login no navegador e repita para cada canal/conta que poderá ser selecionado. Se fechar ou interromper o login, use **Cancelar autorização pendente** antes de iniciar outra.

Se a conta já estava conectada antes do envio de legendas ser habilitado, remova-a localmente e conecte-a outra vez para que o Google apresente e salve o novo consentimento.

Não crie uma chave de API para essa finalidade e não informe senha do Google ao aplicativo. O OAuth mantém a senha fora do app e permite revogar o acesso depois.

## Segurança das credenciais

- Não adicione o JSON do cliente OAuth, tokens de acesso, tokens de atualização, cookies ou chaves ao Git, a `examples/`, ao ZIP de imagens ou ao `project.json`.
- O cliente OAuth, tokens e a lista de contas ficam em `input/youtube/`, com um token separado por conta conectada.
- O seletor de conta deverá exibir somente um apelido e a identificação pública do canal; nunca token, e-mail completo ou segredo.
- Use **Remover conexão local desta conta** para apagar o token deste computador. Para revogar o acesso no Google, use [Conta Google > Segurança > Conexões de terceiros](https://myaccount.google.com/connections).

## Restrições que precisam ser conhecidas

- Projetos de API não verificados criados depois de 28 de julho de 2020 têm uploads pela API restringidos a `private` até passar por auditoria de conformidade. Planeje a primeira publicação como privada e confira o resultado no YouTube Studio.
- A conta e o canal selecionados no OAuth são os únicos autorizados a receber o vídeo. Um seletor visual não pode trocar o destino sem um token conectado daquela conta.
- Uploads usam `videos.insert`; o método aceita metadados de título, descrição, tags, categoria e os campos de status já presentes no bloco `youtube`. O processamento do vídeo pode terminar depois da resposta de upload.
- Quando `youtube.captions.enabled` estiver ativo e a geração tiver produzido o SRT, o app usa `captions.insert` para enviar uma faixa fechada com o idioma e o formato declarados. O VTT é convertido localmente a partir do SRT; nenhuma fala é enviada a um serviço de transcrição externo.
- A indicação `contains_synthetic_media` deverá ser enviada conforme o valor do JSON quando houver conteúdo sintético realista que exija divulgação. A responsabilidade pela veracidade dessa declaração continua sendo de quem publica.

## Referências oficiais

- [OAuth 2.0 para aplicativos de desktop](https://developers.google.com/youtube/v3/guides/auth/installed-apps)
- [Escopos de autorização da YouTube Data API](https://developers.google.com/youtube/v3/guides/authentication)
- [`videos.insert`: upload e metadados permitidos](https://developers.google.com/youtube/v3/docs/videos/insert)
- [`captions.insert`: envio de faixas de legenda](https://developers.google.com/youtube/v3/docs/captions/insert)
- [Recurso de vídeo e `containsSyntheticMedia`](https://developers.google.com/youtube/v3/docs/videos)
- [Cotas e auditorias de conformidade](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits)
