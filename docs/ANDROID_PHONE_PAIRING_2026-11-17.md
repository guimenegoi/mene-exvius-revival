# FFBE Revival — conexão do Web Helper somente pelo Samsung (17/11/2026)

## Objetivo

Parear a APK sem ADB, computador, reinstalação ou edição do save. A Web Helper
registra as datas **07/07 a 13/07/2016** na revisão `ddf5b103c3db...`;
a seleção ainda precisa chegar ao cliente.

## Passos no celular

1. Mantenha o aplicativo FFBE Revival aberto. Acesse
   `https://proxmox.tailcf6a16.ts.net:8445/` pelo navegador, autenticado
   e conectado à Tailscale, na seção **Conectar celular**.
2. Gere o código de 24 caracteres, de uso único e válido por 10 minutos.
3. Em outra guia do **mesmo Samsung**, abra
   `http://127.0.0.1:18080/__exvius/config/connect`, cole o código e
   toque **Conectar ao Web Helper**. A página é servida exclusivamente pelo
   servidor embutido do jogo, sem enviar tokens ao browser.
4. Ao receber a confirmação, feche completamente e reabra o FFBE. O primeiro
   cold boot com credenciais privadas habilita GET da revisão da LXC e
   grava uma cópia staged. O segundo cold boot aplica o período selecionado.
   Consulte `http://127.0.0.1:18080/__exvius/config/status` para verificar
   `historical_from=2016-07-07`, `historical_to=2016-07-13`.
5. Os banners limitados de Kefka, Golbez e Chizuru devem aparecer no período.
   Se o navegador suspender o servidor FFBE, mantenha o app ativo em tela
   dividida enquanto usa o Web Helper/página local.

## Segurança e integridade

- O Web Helper usa autenticação, CSRF e política de origem na geração do código.
  A reivindicação HTTPS usa um código aleatório de 96 bits, uso único,
  vida de 600 segundos, limite de tentativas e resposta sem cache/CORS.
- O Python Android verifica a identidade do host Tailscale por TLS com
  raízes públicas ISRG Root X1/X2 explícitas, sem desativar certificados,
  redirecionar ou usar proxies. O TLS foi verificado contra o servidor real.
- A CA e o Bearer do receptor são enviados **somente ao aplicativo**, por
  TLS, e guardados como arquivos privados em `exvius/settings`. Não são
  incluídos na APK nem na página do navegador.
- Não cria `exvius/backup/config.json`: a conexão de settings **não habilita
  envio de saves**. `campaign.json` e `replay.json` não são editados pela
  autorização e continuam preservados.
- A sincronização periódica usa o mecanismo versionado `config_sync`, com
  staged e aplicação somente em novo cold boot.

## Escopo e gates

A página de conexão é parte do servidor HTTP local já utilizado pelo jogo;
não modifica o menu nativo Java/Dex. Uma opção nativa de configurações
poderá ser adicionada futuramente, caso seja exigida, após validar o fluxo.

- Código de produção do Web Helper em `feature/settings-phone-pairing-20261117`,
  implantado na LXC 120 com backup do arquivo anterior para rollback.
- Código Android em `feature/android-phone-pairing-20261117`, partindo da
  base RC3 Manual2016 Pairing/TicketEra com filtros históricos existentes.
- Testes sintéticos de autorização, TLS, gravar credencial e preservação de
  save; assinatura/diff da APK; teste de reabertura real no Samsung pendente.
