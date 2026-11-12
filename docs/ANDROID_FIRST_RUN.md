# FFBE Android — instalação automática na primeira abertura

## Objetivo

O usuário instala **um único APK com seus splits**, abre o FFBE com internet
na primeira execução e o próprio aplicativo baixa e valida os 19 pacotes
fixados em `data/latest.json`. Depois da instalação, o cliente fala apenas
com o motor Revival em `127.0.0.1:18080`, sem Termux, VPN ou servidor externo.
Atualizações preservam saves e baixam apenas packs alterados.

## Base existente a reutilizar

- **Upstream Android:** `source/memorial/android/.../DataDownloadActivity.java`
  fornece tela de progresso/Retry; `DataUpdates.java` já lida com downloads
  e retomada; `DataPack.java` valida SHA-256 e extrai; `GameAssets.java`
  anexa o APK de recursos à instância original de recursos do Android.
  Referência: `Elvlin/exvius-offline`, branch `main`.
- **Projeto atual:** `android/data/offline_data.py` valida instalação no
  armazenamento privado, compartilha arquivos nativos com o cliente e mantém
  19 registros de instalação e o recibo SHA-256 de `client-assets`.
- **Inicialização:** `android/runtime/local_http.py` não abre a porta
  18080 antes de confirmar inventário, links e recibos. O trabalho Python
  já está em worker separado de `Lapis.onCreate`.

## Integração experimental comprovada em 12/11/2026

O APK privado de laboratório agora incorpora a Activity `DataDownloadActivity`
compilada do upstream **v0.1.30** (SHA-256 fixado no script
`android/runtime/patch_first_run.py`) em `classes4.dex`, sem substituir os
três DEX originais nem `libgame.so`. O manifesto Android move apenas o intent
`MAIN/LAUNCHER` do `Lapis` para a Activity de instalação; os deep links do
jogo permanecem no `Lapis`. A Activity abriu no Waydroid Android 13, sem
travamento ou erros fatais observados. O usuário vê a tela de configuração.

A URL do manifesto do instalador foi fixada no commit upstream
`b0b73648ceb1a3783105ed2104600be651c9c515`, revisão 9 com os mesmos
19 pacotes/hashes de `data/latest.json` no fork. O adaptador Python
`local_http.reconcile_first_run()` aceita os recibos Android
`packs: [{id,sha256,unpackedSize}]`, verifica os 19 hashes e o SHA-256 do
`game-assets.apk`, depois reutiliza `offline_data.android_files_layout()`
para criar somente os cinco links nativos e o recibo do cliente. Não
modifica `installed.json` nem saves. Os testes de contrato com dados
sintéticos passaram; a instalação completa **não foi executada no Android**.

A prova JNI do APK integrado confirmou `PYTHON-REVIVAL-CRYPTO-OK` em worker,
com `REVIVAL-DATA-NOT-READY` e porta 18080 fechada quando faltam dados.
O cliente aprovado foi restaurado após o teste, sem apagar dados.

**Bloqueio restante:** no upstream, `DataDownloadActivity.openGame()` ainda
inicia `Lapis` imediatamente após o download/anexação de assets. O backend
Python demora segundos para ficar pronto; é preciso uma espera assíncrona
com timeout e falha segura antes de liberar o jogo. Não marcar gameplay
offline ou instalação funcional completa como comprovados.

## Diferenças que devem ser conciliadas ANTES da integração

1. **Adaptado e testado sinteticamente:** `DataUpdates.java` escreve
   `installed.json` com lista `packs: [{id,sha256,unpackedSize}]`;
   `local_http.py` agora aceita essa lista e o antigo dicionário `{id:sha}`.
   A reconciliação gera apenas `offline-client-assets.json`, mantendo o
   inventário original, após validar a revisão e os hashes.
2. **Adaptado em testes sintéticos:** `DataPack.java` grava os arquivos
   em `getFilesDir()/{mst,en,common_lang,...}` e o adaptador reutiliza
   `android_files_layout()` para criar os cinco links autorizados em
   `getFilesDir()/exvius/data/native`. Falta testar após download real.
3. O `client-assets` contém `static/client/game-assets.apk`: antes de
   abrir `Lapis`, é necessário anexá-lo ao `AssetManager` pelo mecanismo
   `GameAssets.attach()`. Isso não é opcional para telas e mídia originais.
4. O preflight do servidor e a tela inicial precisam concordar no mesmo
   recibo, sem duas rotinas de download nem criação de saves ao reparar dados.
5. **Validado em laboratório:** launcher `DataDownloadActivity` adicionado,
   mantendo a Activity `Lapis`, seu deep link e os arquivos originais. O
   diff binário preserva todos os membros exceto o manifesto e acrescenta
   somente `classes4.dex`.

## Critério para considerar pronto

- [x] Abrir tela de configuração no Waydroid sem congelar a Activity.
- [ ] Validar espaço livre (recomendação atual: **22 GiB**) e conexão.
- [ ] Baixar sequencialmente os 19 pacotes (~14,65 GB), com progresso,
      retomada, checksum SHA-256 e exclusão dos ZIPs após instalação.
- [ ] Instalar dados compartilhados sem duplicação e sem mexer em saves.
- [ ] Anexar `game-assets.apk`, concluir recibos e iniciar o servidor real.
- [ ] Aguardar readiness da porta 18080 antes de entrar no jogo.
- [ ] Reiniciar sem redownload; verificar download interrompido e reparação.
- [ ] Desligar internet e testar login, batalha, recompensa e save/reabertura.

## Cópia privada no HD externo do servidor

`/workspace/projects/ffbe-revival-distribution/` no LXC 117
(`storage-media`), com APK experimental, manifesto, fontes do instalador
e cache SHA-256 dos arquivos de origem. Esse cache não equivale à instalação
dos dados no aparelho; serve para preservação e testes de distribuição.
Nenhum APK/asset proprietário é enviado ao repositório Git.
