# Autenticação do YouTube para publicação futura

Este documento prepara o acesso à conta que publicará os vídeos quando a integração for implementada. A versão atual do Local Short Studio **não faz login nem publica vídeos**.

## Chave de API não publica vídeos

Uma chave de API identifica o projeto e atende requisições públicas, mas não concede acesso a um canal nem autoriza `videos.insert`. Para enviar um Short é obrigatório autenticar o proprietário da conta pelo **OAuth 2.0** e obter consentimento para o escopo mínimo `https://www.googleapis.com/auth/youtube.upload`.

## Preparação no Google Cloud

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/) com a conta que administrará o projeto.
2. Crie ou escolha um projeto exclusivo para o Local Short Studio.
3. Em **APIs e serviços > Biblioteca**, habilite a [YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com).
4. Em **APIs e serviços > Tela de consentimento OAuth**, configure a tela, os dados de contato e os usuários de teste enquanto o projeto estiver em desenvolvimento.
5. Em **APIs e serviços > Credenciais**, crie um ID de cliente OAuth do tipo **Aplicativo para computador**. Baixe o JSON de credenciais somente para uso local.
6. Quando a futura interface solicitar, conecte uma conta: ela abrirá o navegador para login e consentimento. Repita o processo para cada canal/conta que puder ser selecionado na aplicação.

Não crie uma chave de API para essa finalidade e não informe senha do Google ao aplicativo. O OAuth mantém a senha fora do app e permite revogar o acesso depois.

## Segurança das credenciais

- Não adicione o JSON do cliente OAuth, tokens de acesso, tokens de atualização, cookies ou chaves ao Git, a `examples/`, ao ZIP de imagens ou ao `project.json`.
- Na implementação futura, esses arquivos deverão ficar em diretório local ignorado pelo Git (por exemplo, em `input/youtube/`) e com uma entrada separada por conta conectada.
- O seletor de conta deverá exibir somente um apelido e a identificação pública do canal; nunca token, e-mail completo ou segredo.
- Revogue uma conexão em [Conta Google > Segurança > Conexões de terceiros](https://myaccount.google.com/connections) ou remova a credencial/token local pela futura tela de contas.

## Restrições que precisam ser conhecidas

- Projetos de API não verificados criados depois de 28 de julho de 2020 têm uploads pela API restringidos a `private` até passar por auditoria de conformidade. Planeje a primeira publicação como privada e confira o resultado no YouTube Studio.
- A conta e o canal selecionados no OAuth são os únicos autorizados a receber o vídeo. Um seletor visual não pode trocar o destino sem um token conectado daquela conta.
- Uploads usam `videos.insert`; o método aceita metadados de título, descrição, tags, categoria e os campos de status já presentes no bloco `youtube`. O processamento do vídeo pode terminar depois da resposta de upload.
- A indicação `contains_synthetic_media` deverá ser enviada conforme o valor do JSON quando houver conteúdo sintético realista que exija divulgação. A responsabilidade pela veracidade dessa declaração continua sendo de quem publica.

## Referências oficiais

- [OAuth 2.0 para aplicativos de desktop](https://developers.google.com/youtube/v3/guides/auth/installed-apps)
- [Escopos de autorização da YouTube Data API](https://developers.google.com/youtube/v3/guides/authentication)
- [`videos.insert`: upload e metadados permitidos](https://developers.google.com/youtube/v3/docs/videos/insert)
- [Recurso de vídeo e `containsSyntheticMedia`](https://developers.google.com/youtube/v3/docs/videos)
- [Cotas e auditorias de conformidade](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits)
