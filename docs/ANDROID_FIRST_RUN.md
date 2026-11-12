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

## Diferenças que devem ser conciliadas ANTES da integração

1. O `DataUpdates.java` upstream escreve `installed.json` com uma lista
   `packs: [{id, sha256, unpackedSize}]`; o backend Revival atual espera
   `{id: sha256}` e um `offline-client-assets.json` próprio.
   Não instalar ambos os formatos nem marcar dados prontos prematuramente.
2. O `DataPack.java` upstream escreve recursos nativos diretamente em
   `getFilesDir()/{mst,en,common_lang,...}`. O motor precisa dos cinco
   links controlados em `getFilesDir()/exvius/data/native`.
3. O `client-assets` contém `static/client/game-assets.apk`: antes de
   abrir `Lapis`, é necessário anexá-lo ao `AssetManager` pelo mecanismo
   `GameAssets.attach()`. Isso não é opcional para telas e mídia originais.
4. O preflight do servidor e a tela inicial precisam concordar no mesmo
   recibo, sem duas rotinas de download nem criação de saves ao reparar dados.
5. O launcher do APK ainda deve receber a Activity de download, mantendo
   a entrada de `Lapis` e todos os conteúdos originais fora do escopo do
   patch. Revisar manifesto e DEX antes/depois, com teste no Waydroid.

## Critério para considerar pronto

- [ ] Abrir tela de configuração sem congelar a Activity.
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
