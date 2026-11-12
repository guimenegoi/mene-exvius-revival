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
sintéticos passaram. Posteriormente, os **19 pacotes reais foram instalados**
no Waydroid com download a partir do LXC e preflight positivo.

A prova JNI do APK integrado confirmou `PYTHON-REVIVAL-CRYPTO-OK` em worker,
com `REVIVAL-DATA-NOT-READY` e porta 18080 fechada quando faltam dados.
O cliente aprovado foi restaurado após o teste, sem apagar dados.

**Gate de prontidão implementado e provado em falha segura:**
`first_run_readiness.py` altera somente o ponto de abertura de `Lapis` em
`DataDownloadActivity.openGame()`. Após `GameAssets.attach()`, reaproveita
`LocalPythonProbe.probe()` (carregamento de `libpython3.14` e JNI) e
`startAsync()` fora da thread de UI. Um worker consulta apenas
`http://127.0.0.1:18080/__exvius/hello`, exigindo HTTP 200 e o corpo
esperado do handler **real** de `serve.py`. O número de consultas é limitado;
na falha, mantém o jogo fechado e mostra o erro na mesma tela do upstream,
sem oferecer Retry enganoso do downloader. Não introduz listener novo.

**Prova Waydroid sem recursos:** uma variante temporária de teste, não
publicada, invocou o gate diretamente com prazo reduzido (três consultas).
Na primeira tentativa, o runtime mostrou `UnsatisfiedLinkError` porque
`probe()` era chamado somente por `Lapis.onCreate()`. O diagnóstico orientou
um patch mínimo: `probe()` **antes** de `startAsync()` no próprio worker do
gate. Repetido o teste, o Android confirmou o carregamento JNI, os imports
AES (`PYTHON-REVIVAL-CRYPTO-OK`), `REVIVAL-DATA-NOT-READY`, Activity do
instalador ainda em primeiro plano e a mensagem de timeout, sem listener
na porta 18080 e sem abrir `Lapis`. O APK de distribuição mantém o prazo
normal (240 consultas) e não contém o bypass de teste.

**Comprovado posteriormente:** extração de 19 pacotes reais, readiness
positiva do servidor, entrada em `Lapis`, tela de título e requisições
GameSetting/Initialize/GetUserInfo. **Pendente:** download complementar
de `F_BANNER_MST` (404), tela principal, batalha, save e modo avião.
O ciclo de vida/start-stop do motor também continua pendente.
Ver [auditoria de 12/11](ANDROID_AUDIT_2026-11-12.md).

## Diferenças de arquitetura e suas validações

1. **Adaptado e testado sinteticamente:** `DataUpdates.java` escreve
   `installed.json` com lista `packs: [{id,sha256,unpackedSize}]`;
   `local_http.py` agora aceita essa lista e o antigo dicionário `{id:sha}`.
   A reconciliação gera apenas `offline-client-assets.json`, mantendo o
   inventário original, após validar a revisão e os hashes.
2. **Integrado:** `DataPack.java` grava os arquivos em
   `getFilesDir()/{mst,en,common_lang,...}` e o adaptador reutiliza
   `android_files_layout()` para criar os cinco links autorizados em
   `getFilesDir()/exvius/data/native`. O servidor iniciou com dados reais;
   falta auditar uma tabela nativa que retornou 404.
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
- [x] Instalar os 19 pacotes reais (~14,65 GB) no Waydroid com o
      instalador upstream e recibos SHA-256, usando cache local em laboratório.
- [ ] Confirmar retomada após interrupção real e limpeza de temporários.
- [x] Instalar dados com recibos válidos e sem limpar os saves no Waydroid.
- [ ] Auditar a disponibilidade individual de `F_BANNER_MST` no CDN.
- [x] Anexar `game-assets.apk`, concluir recibos e iniciar o servidor real.
- [x] Implementar espera assíncrona de `18080/__exvius/hello`, com prazo
      limitado e falha segura, e confirmar a recusa no Waydroid sem dados.
- [x] Com os 19 pacotes reais instalados, provar transição por readiness
      positiva do servidor Revival para `Lapis` e título original.
- [ ] Reiniciar sem redownload; verificar download interrompido e reparação.
- [ ] Desligar internet e testar login, batalha, recompensa e save/reabertura.

## Cópia privada no HD externo do servidor

`/workspace/projects/ffbe-revival-distribution/` no LXC 117
(`storage-media`), com APK experimental, manifesto, fontes do instalador
e cache SHA-256 dos arquivos de origem. Esse cache não equivale à instalação
dos dados no aparelho; serve para preservação e testes de distribuição.
Nenhum APK/asset proprietário é enviado ao repositório Git.
