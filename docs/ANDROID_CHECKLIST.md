# Checklist vivo — FFBE Revival Android independente

**Atualizado:** 2026-11-12. Este documento é a fonte de acompanhamento do fork
`mene-exvius-revival`. Só marcar `[x]` com teste verificável; prova isolada
não equivale a APK offline. Versão-alvo: FFBE Global 9.1.0 (`versionCode=9101`).
Entrega: **um único aplicativo**, sem Termux, VPN, root, Proxmox ou outro app.

## Princípios e integração de referência

- [x] Fork próprio com remotos `origin` e `upstream`.
- [x] Cliente abre no Waydroid com Revival remoto e consegue batalha/recompensas.
- [x] Backend Python Revival iniciado no Termux com dados parciais; HTTP/HTTPS e GET MST.
- [x] Transporte de API e CriFsWebInstaller em localhost:18080 com patch Java.
- [x] Prova de bootstrap **dentro do processo do FFBE**: porta 18081 de
      loopback, HTTP 200 e encerramento do listener com `force-stop`.
      Apenas diagnóstico; não há Python nem jogabilidade nesse listener.
- [ ] Testar individualmente Cocos2dxDownloader e FileDownloader em sessão jogável.
- [ ] Comprovar que todos os caminhos necessários (inclusive nativos, se houver)
      deixam de atingir endpoints externos, sem interceptar conexões de outros apps.

## RC2 — APK único ARM64 em inglês (12/11/2026)

**Artefato de teste mais simples:** `~/Downloads/FFBE-Revival-RC2-ARM64-English.apk`,
assinado com certificado DEBUG (310.139.836 bytes, aprox. 296 MiB;
SHA-256 `e761620f97fad6dac495a409ae6daa81f035ec432a5d97fc54eff4d9f3ad594e`).
O arquivo `FFBE-Revival-RC2-ARM64-English.txt` contém instruções e checksum.

- [x] APKEditor 1.4.9 verificado por SHA-256
  (`a9cd40df818845456be6d696de6110c89edf4b0a0580cb83438ed6b25a366e67`)
  fundiu **base + ARM64 + inglês + mdpi**; excluiu `config.fr`.
  Arquivos `assets/cpk/fr` internos da base original foram preservados
  para evitar mudanças funcionais fora do escopo. Não há dependência de SAI.
- [x] Comparação por conteúdo: os quatro DEX e `ffbe_python/stdlib.zip`
  idênticos ao RC2; oito bibliotecas ARM64 idênticas ao split original;
  `resources.arsc` combinado; `res/xml/splits0.xml` retirado.
  Assinatura v1/v2/v3 e zipalign verificados.
- [x] `adb install -r` **sem limpar dados**: Android aceitou somente
  `base.apk` como caminho de instalação (antes eram cinco); versão
  `9101` mantida. Inicialização do CPython 3.14, 19 packs verificados,
  Revival HTTP local na porta 18080, título, Home e entrada Vortex.
- [ ] Instalação limpa e gameplay em Android ARM64 físico ainda não
  verificados; popup residual de download de **0 KB** permanece.
  Certificado DEBUG, portanto **não é release final assinada**.
- [ ] Confirmar compatibilidade de atualizações entre outros certificados;
  nunca desinstalar versões com saves sem backup prévio.

**Reprodução do merge sem criar merger próprio:**
[android/distribution/README.md](../android/distribution/README.md).
Os APKs e recursos proprietários não entram no Git.

## RC2 para teste — 12/11/2026 (substitui RC1)

**Artefato anterior com splits:** `~/Downloads/FFBE-Revival-RC2-2026-11-12.apks`
(323.720.053 bytes, SHA-256:
`a8c3a2703a013667e59bafcba501dcbef01e8c838ce346068466055090bc5e69`).
Cinco APKs assinados com chave DEBUG, reunidos em um .apks. Os cinco
arquivos, instrucoes e hashes individuais estao na pasta homonima em
Downloads. Nao publicar binarios com recursos proprietarios no Git.

- [x] Diagnostico do RC1: as versoes de tabelas/CPKs baixadas pelo proprio
  jogo eram escolhidas como fontes da proxima geracao. Segunda abertura
  recriou versoes e pediu novamente ~224 MB.
- [x] RC2 fixa `Ver329_ZQqB38Ns.dat`, `Ver735_A1L1GlaQ.dat`,
  `Ver436_9Hwur83G.dat`, `Ver611_Fvix6V0n.dat` e
  `Ver461_spdungeon1.cpk` como fontes originais, conferidas contra
  `data-010.zip` e `data-011.zip`; acrescenta hardlink do CPK no overlay
  e nao reprocessa arquivos gerados pelo cliente.
- [x] Android nao antecipa `resources_common.cpk` nem `resources.cpk`
  por causa de ajustes exclusivos do iPhone; apenas o banner pack usa TUTO.
- [x] Instalado com `adb install-multiple -r` sem remover dados:
  servidor Revival e Home abriram. Primeira inicializacao baixou
  `Ver10654_spdungeon1.cpk` (242.483.910 bytes, HTTP 200).
  **Segunda inicializacao: aviso de download de 0 KB**, sem nova transferencia
  desse pacote, e Home alcancada. O popup de 0 KB ainda e incoveniente.
- [x] 76 testes de runtime Android aprovados, incluindo fonte fixa do
  Vortex e preservacao dos arquivos no overlay; `git diff --check` passou.
- [ ] Primeiro uso completo em celular ARM64 fisico, partida e recompensa,
  saves persistidos, modo aviao e ausencia de novo popup de 0 KB.
- [ ] Validar que a experiencia Vortex/menus ainda segue o Revival original
  em outros eventos e epocas; testes de Event/Enhance/Special feitos no RC1.
- [ ] Empacotar um APK unico sem splits e assinar com chave de release
  se houver permissao legal para distribui-lo.

O registro RC1 abaixo permanece como historico; nao recomendar RC1 para
instalacao nova porque ele refaz o download de banners ao reiniciar.

## RC1 instalável — 12/11/2026, verificação em Waydroid

**Artefato de teste no desktop:** `~/Downloads/FFBE-Revival-RC1-2026-11-12.apks`
(323.715.957 bytes; SHA-256
`415b11cd61331d62ef457db7a50664d4c90528780767f1c9fb7ca6d527d747ad`).
É um conjunto de cinco APKs assinados com chave DEBUG, não um APK universal.
As cinco partes e o checksum estão em
`~/Downloads/FFBE-Revival-RC1-2026-11-12/`; não publicar binários proprietários.

- [x] RC1 recomposto usando o motor atualizado: 1.075 arquivos verificados
  por SHA-256 (dez fontes ausentes incorporadas, 26 fontes atualizadas).
  `assets/ffbe_python/stdlib.zip` e `classes4.dex` foram os **únicos**
  membros internos alterados em relação à base aprovada de laboratório.
- [x] Installer público compilado com o manifesto da revisão 9 fixado em
  `21aa05a` do fork, URLs dos ZIPs no repositório público de dados e
  downloader resumível existente. Nem manifesto nem ZIPs usam
  `127.0.0.1:18082`; comprovada disponibilidade HTTP 200 do manifesto e
  de dois recursos públicos. **Primeira instalação limpa ainda não testada**.
- [x] `adb install-multiple -r` dos cinco APKs, **sem limpar saves**;
  inicialização do Revival real, porta 18080 e chegada à Home no Waydroid.
- [x] Reativadas de forma seletiva quatro tabelas originais do Revival para
  Vortex Android (sem versões de iPhone e sem alterar áudio Android).
  Quatro downloads HTTP 200; `F_AREA_MST` deu prioridade a 766 áreas.
- [x] CDN serviu o pacote de banners reconstruído
  `Ver3461_spdungeon1.cpk` (242.483.910 bytes, HTTP 200).
  Vortex: telas **Event**, **Enhance** e **Special** abriram sem crash;
  banners The Hanging Edge, The Big Bridge e Cactuar Dunes visíveis.
  Primeira missão de The Hanging Edge abre a lista BGN sem erro.
- [ ] Validar em ARM64 físico: instalação inicial completa de 19 ZIPs,
  controles, batalha, recompensa, save e reabertura **em modo avião**.
- [ ] Validar outras áreas Vortex e demais módulos do Revival (não assumir
  paridade total após este primeiro patch Android).
- [ ] Gerar um APK realmente universal sem splits e retirar certificado
  DEBUG antes de release final. O arquivo `.apks` atual é apenas RC1.

## P0 — APK offline autossuficiente

Estado de laboratório e bloqueadores em
[Auditoria Android — 12/11](ANDROID_AUDIT_2026-11-12.md).


- [x] Implementar instalador de manifesto (19 pacotes, retomada, SHA-256,
      reserva de espaço e verificação local sem rede) em `android/data`.
- [x] Testar layout de compartilhamento nativo/servidor sem duplicações em Linux.
- [x] Preservar os **cinco splits APK de laboratório** assinados no HD externo
      ZFS `storage-media` do LXC 117, com comparação SHA-256 após transferência;
      copiar manifesto e fontes do instalador fora do Git.
- [x] Concluir cache SHA-256 dos **19 ZIPs upstream** no HD externo:
      **14.647.871.919 bytes (14,65 GB)**, conferidos contra o manifesto
      fixado. Isso não substitui a instalação privada no aparelho.
- [x] Integrar **launcher da primeira execução**, com
      `DataDownloadActivity`, `DataUpdates`, `DataPack` e `GameAssets` do
      upstream v0.1.30: tela abriu no Waydroid sem travamento.
      Manifesto de 19 pacotes fixado por commit upstream; `local_http.py`
      aceita recibos Android e cria links nativos apenas após validação.
- [x] Bloquear entrada em `Lapis` até resposta real do handler
      `127.0.0.1:18080/__exvius/hello`, com worker, prazo limitado e tela
      de erro. Falha segura comprovada no Waydroid, inclusive JNI/AES
      inicializados **antes** de `Lapis.onCreate`, sem downloads ou saves.
- [x] Instalar/extrair os 19 pacotes reais no Waydroid, anexar
      `game-assets.apk`, obter readiness **positiva** em `18080`, entrar em
      `Lapis` e chegar ao título, sem re-download dos 14,65 GB em reinício.
      **Pendente:** download complementar de MST, tela principal e gameplay.
- [x] Executar código Python 3.14.10 ARM64 dentro do processo FFBE em laboratório:
      JNI, stdlib privada, `Py_InitializeFromConfig` e `PYTHON-EXECUTED-42`.
- [x] Importar extensões oficiais nativas (67 módulos do CPython) no FFBE:
      `ssl`, `zlib`, `sqlite3`, `socket`, `hashlib` e `zipfile`.
- [x] Importar `yaml`, `serve` e `capture_server` **do Revival real** dentro
      do FFBE com 172 fontes/recursos do Git e PyYAML puro, SHA-256 validado.
- [x] Incorporar `tzdata` 2026.6 e validar `zoneinfo` de
      `America/Sao_Paulo` **com dados internos do APK**, inclusive após reabrir.
- [x] Compilar **Pillow 13.0.0** para CPython 3.14 / Android ARM64;
      verificar wheel e ELF; incorporar ao APK e confirmar PNG gerado/reaberto
      em memória no processo FFBE, inclusive após reinício.
- [x] Compilar **cryptography 50.0.2**, **cffi 2.1.1** (libffi 3.5.2
      estática) e empacotar pycparser 3.12 para Android ARM64/CPython 3.14.
      Validar NIST AES-128-CBC, o cifrador real `ffbe_crypto` e imports de
      X.509 **no processo FFBE, também após reabrir**. Pacote atual:
      **1.065 arquivos** na variante com instalador (Revival, dependências
      e integração de dados), com SHA-256.
      **Servidor real iniciado no Android; jogo offline ainda não validado.**
- [x] Instalar e verificar os recibos dos 19 pacotes **reais** no Waydroid.
- [x] Corrigir acesso a `F_BANNER_MST` (`Ver595_oB0YVw67.dat`):
      o 404 da fase inicial foi resolvido com o mapeamento dos arquivos
      nativos preservados, conforme as validações RC1/RC2 acima.
- [ ] Validar os demais recursos exigidos durante gameplay completo,
      além dos fluxos de título, Home e Vortex já examinados.
- [ ] Verificar escrita, atualização e preservação de saves no layout real ARM64.
- [ ] Empacotar runtime CPython incorporado, stdlib e dependências
      `cryptography`, `Pillow`, `PyYAML`, `tzdata` para x86_64 e ARM64.
      **Já validados em ARM64 no Waydroid:** CPython, stdlib, PyYAML,
      tzdata, Pillow, cryptography, cffi e pycparser.
      **Pendentes:** build e execução nativa x86_64, Android ARM64 físico
      e validação completa da partida. Servidor real já iniciou no Waydroid.
- [x] Criar entrada guardada do **handler HTTP real** em
      `127.0.0.1:18080`: validar o manifesto fixado de 19 pacotes, recibos,
      SHA-256 do cliente, links nativos e inventário antes de importar/iniciar
      o servidor. Validar recusa sem dados no Waydroid, sem abrir `18080`.
- [x] Iniciar o **motor Revival real** com 19 pacotes no Waydroid e
      atender GameSetting, Initialize, GetUserInfo e recursos CDN via HTTP.
- [ ] Completar parada limpa/ciclo de vida e comprovar gameplay offline.
- [x] Tirar extração/importações da thread principal da Activity **na prova
      de laboratório**: worker Java `FFBE-Python`, usando o Context da
      aplicação e guarda de inicialização única; início e imports confirmados
      em TID diferente da UI, incluindo AES após reiniciar, sem timeout no log.
      **Pendente para produção:** ciclo de vida/stop e estabilidade.
- [x] Integrar o instalador ao mesmo APK: primeiro uso real instalou os
      19 pacotes no Waydroid usando cache privado somente em laboratório.
- [x] Produzir APK de laboratório assinado com cliente, runtime,
      instalador e gate HTTP integrados, com diff verificado. Ainda não é release.
- [ ] Passar pelo menos uma batalha, receber recompensa e persistir save com
      Wi-Fi/dados desligados e sem servidor externo; reabrir o jogo e conferir save.

## P1 — cobertura funcional e estabilidade

- [ ] **Backup de save na LXC 117**, implementado e validado em
      **branch independente**: exportar somente os arquivos de progresso
      necessários de `exvius/server-root/state` (não os 19 pacotes nem
      chaves privadas); envio autenticado e criptografado pela rede local,
      com consentimento explícito, execução após save íntegro, checksum,
      retenção de versões e indicação da última cópia bem-sucedida.
      O modo avião e o gameplay offline não podem depender da LXC.
      Implementar restauração separadamente, com prévia, escolha de versão,
      confirmação e cópia local de segurança; nunca sobrescrever
      automaticamente o save. Validar perda de rede, reinício e integridade
      no aparelho ARM64 real antes de ativar por padrão.
- [ ] World Map, exploração/encontros aleatórios, summons, inventário e quests,
      incluindo regressão de recompensas.
- [ ] Investigar incompatibilidade de `EXVIUS_WIKI_REWARDS=1`; atualmente o
      ambiente Android usa `0` como contorno provisório.
- [ ] Validar x86_64 e dispositivo Android ARM64 físico.
- [ ] Medir RAM/CPU/bateria, tela apagada, alternância de apps e reinício.
- [ ] Downloads apenas na configuração/atualização; zero dependência de rede
      durante a partida; preservação de saves em atualizações.

## P2 — entregável e pós-estabilização

- [ ] **Distribuição privada de APKs diretamente pela LXC 117**:
      permitir baixar no navegador do celular um APK aprovado via LAN,
      sem cabo USB ou app auxiliar; não expor repositório, arquivos
      proprietários ou outros diretórios; exigir autenticação/acesso
      temporário, acesso local, checksum SHA-256, cabeçalhos seguros e
      suporte a retomada HTTP Range. Conferir assinatura, compatibilidade
      de atualização `adb install -r` e preservação dos saves. Não publicar
      binários em GitHub ou na internet sem revisão de direitos.
- [ ] Permitir usar **opcionalmente a LXC 117 como origem dos 19 pacotes
      (~14,65 GB)** na instalação inicial ou em atualizações quando o
      celular estiver na rede doméstica. Reutilizar o cache e o servidor
      HTTP Range existentes em `android/distribution`, sem depender de
      túnel ADB/SSH; oferecer configuração/seleção segura da origem local,
      com fallback para os releases públicos do GitHub. Preservar os
      mesmos IDs, tamanhos e SHA-256 do manifesto fixado, com retomada
      de downloads; validar instalação em celular real dentro e fora da
      rede doméstica. **Não tornar a LXC obrigatória para jogar offline.**
- [ ] Instalação em aparelho limpo sem apps auxiliares; backup, recuperação,
      logs úteis e CI/release de build reproduzível.
- [ ] Rever direitos de redistribuição do upstream e dos recursos proprietários;
      não publicar APK original, recursos de jogo, saves ou chaves no Git.
- [ ] **Investigar em branch isolada a viabilidade de iniciar o replay no
      lançamento Global (junho de 2016), antes de Noctis (16/12/2016)**:
      inventariar banners, unidades, eventos/Vortex, quests, recompensas,
      lojas e datas de junho a dezembro; comparar os registros existentes
      com uma cronologia confiável do Global, identificando ausências e
      aproximações. Exercitar `EXVIUS_REPLAY_START` com estado de teste
      separado, sem apagar/reancorar saves nem modificar a RC2 aprovada.
      Registrar o que já funciona, as lacunas e uma estratégia de migração
      da âncora histórica sem afetar progressos; só integrar após validar
      a versão offline no aparelho. Branch de investigação independente.

## Registro de execução

### 2026-11-13 — provas TLS na LXC e recuperação do Waydroid

- **Backup do save — protótipo, não integrado ao aplicativo:**
  branch `feature/lxc-save-backup`, commits `dbd7e1c` e `bf4dd0d`.
  O último corrigiu a leitura concorrente de arquivos `.json.tmp` que
  `PlayerState.save()` utiliza; teste de regressão falhou antes e passou
  depois (10 testes de backup + 105 existentes). Uma prova de ponta a
  ponta enviou **três JSONs sintéticos** por HTTPS do Mene-Desktop à LXC
  117, verificou o SHA-256 do recibo e do ZIP armazenado (0600) e a
  listagem autenticada. Nenhum save real foi copiado. Token, certificado,
  snapshot e serviço temporários foram removidos. **Pendentes:** evento
  de backup após o save íntegro, configuração de confiança no Android,
  política de retenção implantada e restauração confirmada.
- **Distribuição privada de APK — protótipo, sem binário real servido:**
  branch `feature/lxc-apk-download`, commits `59bbf95` e `003cf11`.
  O último tornou TLS com certificado e chave 0600 obrigatórios.
  Prova de HTTPS com SAN do IP `192.168.15.209`, link temporário,
  SHA-256, download completo, retomada por Range e negação de HTTP
  simples, certificado não confiável e token inválido: **aprovada** com
  APK sintético. Suíte Android: 112 testes. Serviço e artefato de teste
  removidos; o cache `127.0.0.1:18082` permaneceu isolado.
  **Pendente:** certificado confiável no celular, publicação privada
  de APK aprovado e verificação de atualização/assinatura no aparelho.
- **Waydroid — falha de infraestrutura isolada:** os tombstones mostram
  abort de `hwcomposer.waydroid.so` seguido de `SurfaceFlinger`;
  o socket `wayland-ffbe-test` estava ausente. Weston headless foi
  reiniciado e a sessão Waydroid foi restaurada sem limpar dados:
  `package`, `activity` e `SurfaceFlinger` responderam novamente.
  A instalação atual é FFBE histórico **1.2.0/x86 (`versionCode 32`)**,
  não a RC2 ARM64. **Não sobrescrever esse cliente com a RC3.**
- **Candidata RC3 não aprovada:** branch
  `integration/android-next-rc` contém patches Samsung + upstream
  `61c6409`; 110 testes passaram. APK privado foi gerado/assinado
  (SHA-256 `71546043d77cacfc0bf96268635be9abe3bb4a473771e251e4189990e7ef54c2`);
  manifestou e extraiu 1.077 arquivos verificados. Tentativa no
  Waydroid falhou durante a crise gráfica, logo **não há aprovação
  Android da RC3**. O Samsung não foi alterado. Testar somente em
  ambiente ARM64 isolado, preservando a instalação histórica do Waydroid.

### 2026-11-12 — relato de jogo offline no Samsung e upstream recente

- **Relato do teste em aparelho físico:** batalha em modo avião concluída
  e summon realizado com sucesso. Ainda pendente comprovar, após fechar
  e reabrir, a persistência do save, das recompensas e da unidade invocada;
  não considerar gameplay completo validado somente com essas duas ações.
- **Correção pontual testada no Samsung:** `d48563b` na branch
  `fix/android-preflight-diagnostics`, com ajuste de alias
  `/data/user/0` vs. `/data/data` e fallback de hardlinks proibidos.
  APK atualizado sem limpeza de dados; 19 pacotes verificados, porta 18080,
  Activity Lapis e requests atendidos. **Pendente integrar em main**.
- **Upstream a avaliar em branch de integração:** `25f1226` corrige
  download de arte na tela de summons; `61c6409` impede repetição de
  quests concluídas e preenche o Quest Report. O fork ainda está em
  `2ae0d99` e não incorpora esses dois commits.

### 2026-11-12 — gate de readiness real antes de abrir Lapis

- `first_run_readiness.py` reutiliza `LocalPythonProbe.probe()` e
  `startAsync()`, agora chamados pelo launcher em worker, **antes** de
  `Lapis.onCreate`. Sonda o handler real `/__exvius/hello` em loopback
  sem bloquear a UI e só entrega o Intent ao `Lapis` após HTTP 200
  com resposta esperada. Timeout e falha mantêm `Lapis` fechado.
- O teste isolado no Waydroid descobriu a dependência de carga do JNI
  previamente feita por `Lapis`; após conectar a chamada existente
  `probe()`, a segunda prova passou: CPython/AES, Activity de instalação,
  erro de prontidão, porta 18080 fechada e nenhum lançamento de `Lapis`.
- A variante completa abriu o launcher sem erro de classes ou crash;
  ainda não instalamos os 19 ZIPs no Android nem observamos prontidão
  positiva. O cliente aprovado foi restaurado com `install-multiple -r`,
  sem desinstalar ou limpar dados.

### 2026-11-12 — launcher Android de primeira execução e compatibilidade

- APK upstream público v0.1.30 (9/11/2026) auditado como referência de
  laboratório; componentes do instalador isolados em `classes6.dex`.
  `patch_first_run.py` recompila essa classe com URL do manifesto de
  revisão 9 fixada no commit upstream `b0b73648ceb1a3783105ed2104600be651c9c515`,
  acrescentando-a como `classes4.dex` sem mudar as classes do cliente.
- Manifesto recompilado altera apenas a entrada `MAIN/LAUNCHER`,
  preservando deep links e package original. A tela de download foi
  exibida no Waydroid, sem ANR observado. A execução JNI direta
  confirmou `PYTHON-REVIVAL-CRYPTO-OK` com porta 18080 fechada sem dados.
- O adaptador de recibos aceita tanto a lista do Java quanto o
  dicionário Python, verifica hashes dos 19 packs e do cliente,
  cria os cinco links nativos reutilizando `offline_data` e mantém
  saves e `installed.json` intactos. Coberto por testes sintéticos.
- **Pendente:** primeira instalação real de 14,65 GB no Android,
  espera de readiness em `18080`, reinício seguro e jogo desconectado.
  A Activity upstream ainda abre Lapis antes de aguardar o Python.

### 2026-11-12 — cópia privada no armazenamento externo e instalação inicial

- Armazenamento identificado no LXC `workspace` 117: ZFS `storage-media`
  (disco externo EC-7352), em `/workspace/projects/ffbe-revival-distribution`.
  Espaço disponível na preparação: cerca de 2,7 TB. Não usa a pasta
  sincronizada `dev-exchange`, evitando sincronizar os recursos pesados.
- Os cinco splits Android foram copiados por SSH/rsync, cada um comparado
  por SHA-256 no destino, com nomes padronizados em `apk/`. O certificado
  é de **teste**, e o aplicativo continua experimental.
- `installer/` contém o manifesto atual de 19 pacotes, os programas
  `offline_data.py` e `fetch_data.py` e o wrapper de cache no LXC.
  `android/distribution/cache_packs.py` reutiliza o downloader do Revival
  e valida tamanho + SHA-256 sem extração; **5 testes sem rede aprovados**.
- Diagnóstico do primeiro uso em [ANDROID_FIRST_RUN.md](ANDROID_FIRST_RUN.md):
  o upstream tem Activity de progresso e downloader prontos, mas produz
  `installed.json` com lista, enquanto o backend atual exige `{id: sha}`
  e recibo próprio do cliente. Adaptar esses contratos antes de ligar a UI.
- **Cache dos 19 ZIPs concluído** no armazenamento externo, com cada arquivo
  verificado por tamanho e SHA-256 da revisão do manifesto. Total:
  **14.647.871.919 bytes**, além dos cinco splits APK e das fontes do instalador.
  A **instalação automática no APK ainda está pendente**: o cache no LXC
  não é acessível automaticamente pelo Android nem prova gameplay offline.

### 2026-11-12 — handler Revival loopback com bloqueio por inventário

- `android/runtime/local_http.py` conecta `serve.configure_engine()`,
  `serve.start_engine()`, `serve.make_handler()` e `serve.Server` **existentes**
  ao listener `127.0.0.1:18080`, sem TLS, DNS nem serviço externo.
  O servidor só escuta depois de validar o conjunto e inicializar o motor.
- O manifesto `data/latest.json` da revisão de **19 pacotes** acompanha o
  ZIP Python dentro do APK. A verificação privada exige registros dos
  19 pacotes em `installed.json`, recibo e SHA-256 do cliente,
  arquivos MST e texto, dados nativos compartilhados por symlinks corretos
  e contagem mínima do inventário. A integridade integral dos pacotes foi
  conferida pelo instalador no download; o preflight não rehash os 15 GB
  em cada abertura. Falhas não criam saves nem listener.
- JNI da thread `FFBE-Python` consulta o preflight **antes de importar o
  servidor**. Sem recursos, mantém somente os imports/AES já validados;
  com recursos, chama o motor real e permanece no `serve_forever()`.
  O encerramento de produção e a sincronização de readiness com a UI ainda
  precisam ser implementados e testados.
- Testes de contrato: socket HTTP loopback com handler simulado, recusa de
  pacotes incompletos, cliente adulterado, inventário insuficiente e
  symlink indevido. **O handler simulado não comprova gameplay.**
- **Waydroid, primeira abertura**: `REVIVAL-DATA-NOT-READY: private data
  root missing/unsafe`; porta 18080 fechada; `PYTHON-REVIVAL-CRYPTO-OK`
  apareceu na thread separada. **Segunda abertura** repetiu o resultado.
  O APK anterior foi restaurado com `install-multiple -r`, sem limpar dados.
- O cliente original conserva `libgame.so` e todas as demais entradas,
  exceto os dois DEX aprovados e os assets Python acrescentados.
- **Pendentes:** instalar os dados reais (≈14,95 GB extraídos), inicialização
  do engine/HTTP real no Android, checagem de readiness na UI e gameplay
  sem rede. Não marcar esses itens como concluídos.

### 2026-11-12 — inicialização CPython fora da thread da Activity

- Patch incremental `android/runtime/patch_async_python.py` reaproveita a
  ponte JNI aprovada; troca somente `runDemo(Context)` síncrono por
  `startAsync(Context)` em `Lapis.onCreate`, cria `LocalPythonWorker.smali`
  com `Runnable` e usa `getApplicationContext()` para não reter a Activity.
- O agendamento é `synchronized`, protegido por flag de execução única no
  processo; se a criação da thread falhar, a flag é restaurada. A execução
  de Python e de criptografia continua dentro da biblioteca JNI existente.
- Waydroid: `Lapis.onCreate()` no PID/TID `8073/8073` às 16:11:03.719;
  o worker iniciou em `8073/8124` no mesmo instante; imports concluídos
  às 16:11:18.444 com `PYTHON-REVIVAL-CRYPTO-OK`. **Não bloqueou a Activity.**
- Segundo lançamento após `force-stop`: Activity `8322/8322` e worker
  `8322/8371` às 16:12:00.654, com `PYTHON-REVIVAL-CRYPTO-OK` às
  16:12:10.956. Sem ANR ou timeout de lançamento no log inspecionado.
- APK recomposto com **apenas `classes.dex` e `classes3.dex` alterados**,
  mais os 69 assets de Python; comparação de preservação aprovada,
  `libgame.so` intocada e assinatura de teste verificada.
- **45 testes de runtime** aprovados, inclusive os 5 contratos novos de
  thread, contexto, guarda duplicada e preservação do patch aprovado.
- Cliente de transporte de laboratório restaurado após o teste, usando
  `install-multiple -r` sem limpar dados. **Ainda não** há servidor real
  em 18080, lifecycle de produção, 19 pacotes completos ou jogo offline.

### 2026-11-12 — cryptography e CFFI ARM64 importados dentro do FFBE

- [Build cryptography ARM64 + Python.h](https://github.com/guimenegoi/mene-exvius-revival/actions/runs/43237677799)
  e [build cffi ARM64 com libffi estática](https://github.com/guimenegoi/mene-exvius-revival/actions/runs/43239493938)
  passaram para CPython 3.14; libffi 3.5.2, cffi 2.1.1 e cryptography 50.0.2
  foram fixados por versão e fonte SHA-256 no workflow manual.
- A primeira wheel Rust falhou no Android com `PyExc_ValueError` indefinido:
  não continha `libpython3.14.so` em `DT_NEEDED`. Corrigidas as flags
  específicas de linkedição Cargo. O [build ARM64 corrigido](https://github.com/guimenegoi/mene-exvius-revival/actions/runs/43242186148)
  passou e `llvm-readelf` confirmou `libpython3.14.so`, `libssl_python.so`
  e `libcrypto_python.so` declaradas na extensão Rust.
- Empacotadas também a wheel pura pycparser 3.12 e as licenças
  cryptography, CFFI, libffi e pycparser. Pacote completo:
  **1.063 arquivos, 93.764.953 bytes** sob manifesto SHA-256, instalado na
  pasta privada do FFBE. Primeira extração e segunda passagem incremental
  passaram no teste Linux; o arquivo original `libgame.so` não foi alterado.
- **Waydroid Android 13:** `PYTHON-REVIVAL-CRYPTO-OK` apareceu no
  processo FFBE após cálculo AES-128-CBC contra o vetor NIST SP 800-38A,
  cifrar/decifrar via `ffbe_crypto` com backend `cryptography`, imports
  de CFFI, pycparser, X.509, Pillow PNG e módulos Revival. Segunda abertura
  repetiu a prova, sem instalar novamente o aplicativo.
- **40 testes de runtime** aprovados; regressões de transporte, dados
  e smoke test precisam ser reexecutadas no fechamento desta alteração.
- O OpenSSL emitiu aviso de indisponibilidade do *legacy provider*;
  AES-128-CBC passou, mas o uso de algoritmos legados precisa de auditoria.
  **X.509 foi importado, mas emissão de certificados ainda não testada.**
- A inicialização continua na thread da Activity e disparou aviso de timeout.
  O HTTP Revival real em `18080` **não** foi iniciado, assim como os 19 pacotes
  completos não foram testados em gameplay offline. Cliente de laboratório
  anterior restaurado no Waydroid sem limpar dados.
- O gate CI de `DT_NEEDED libpython3.14.so` foi testado contra a wheel
  antiga (rejeitada) e a corrigida (aceita), impedindo regressões futuras.

### 2026-11-12 — build verificável de wheels nativas Android (em validação)

- Criado workflow manual `.github/workflows/android-wheels.yml` no fork, com
  escolha de dependência (`Pillow` ou `cryptography`) e arquitetura
  (ARM64 ou x86_64). Fontes fixadas por versão e SHA-256; artefatos têm
  retenção curta e não são publicados em releases.
- Criado `android/runtime/verify_dependency_wheel.py`, que verifica tags
  Android/CPython 3.14 ou `abi3`, arquitetura ELF da extensão nativa,
  pacote esperado e nomes de membros sem traversal/duplicação.
- **36 testes de runtime** aprovados, incluindo os contratos do
  verificador de wheel e empacotamento nativo do Pillow. Importações ARM64
  e processamento PNG foram validados **separadamente no Waydroid**.
- **Pillow 13.0.0 ARM64 concluído:** cross-build cp314 aprovado após
  diagnóstico do SDK, seleção ABI, zlib e libjpeg. `libjpeg-turbo 3.2.1`
  compilada estaticamente com fonte SHA-256 fixado; wheel resultante
  `pillow-13.0.0-cp314-cp314-android_24_arm64_v8a.whl` validada no CI e
  na bancada (módulo `_imaging` e arquitetura ELF ARM64).
- A wheel adiciona PIL ao empacotador e ao instalador privado existentes;
  manifesto SHA-256 cobre **912 arquivos / 85,36 MB**. Os `.so` instalados
  ficam somente leitura, e nenhum arquivo original do cliente foi alterado
  fora dos DEX e assets previstos.
- **Waydroid Android 13:** `PYTHON-REVIVAL-PILLOW-OK` comprovado no PID
  do FFBE após `Image.new`, exportar PNG em `BytesIO`, abrir novamente e
  verificar pixel/cor; a reabertura do app repetiu o teste.
- [Build Pillow ARM64 aprovado no Actions](https://github.com/guimenegoi/mene-exvius-revival/actions/runs/43233327397),
  artefato temporário no Actions (não publicado em release). Cliente
  anterior restaurado no Waydroid sem limpar dados.
- `cryptography 50.0.2`: cross-build Rust/CFFI foi iniciado em ARM64,
  mas falhou porque `Python.h` não estava no include path do `cc-rs`;
  diagnóstico disponível, sem wheel válida até aqui.
- Execuções diagnósticas: [Pillow/zlib-JPEG](https://github.com/guimenegoi/mene-exvius-revival/actions/runs/43232233013),
  [cryptography/Python.h](https://github.com/guimenegoi/mene-exvius-revival/actions/runs/43232294795).
- **Critério restante:** wheel Android de `cryptography` com ABI e imports
  testados no FFBE; repetir as dependências em x86_64, migrar inicialização
  para thread própria e integrar servidor real. O sucesso de Pillow não
  equivale a um jogo offline.

### 2026-11-12 — tzdata 2026.6 integrado e incompatibilidade de wheels mapeada

- Wheel universal oficial PyPI, SHA-256
  `0a10eec6e13ef16b627fabed9a5f2ba61a62b1c67f327305f4e7e412a70b4aec`.
  Empacotados **629 arquivos** úteis de `tzdata` com licenças e fuso
  `America/Sao_Paulo`. Arquivo binário do zoneinfo tem hash verificado.
- Pacote completo do motor agora tem **801 arquivos / 80,94 MB**; instalação
  em pasta privada, manifesto SHA-256 e atualização incremental sem reescrever
  arquivos íntegros. Repetição comprovada no teste Linux.
- **Waydroid Android 13:** imports de `yaml`, `tzdata`, `zoneinfo`, `serve`
  e `capture_server`, cálculo do fuso Brasil com base **empacotada** e logcat
  `PYTHON-REVIVAL-TZDATA-OK`. Reabertura do app repetiu a prova.
- APK-base de laboratório: apenas `classes.dex`, `classes3.dex` e assets de
  Python alterados/acrescentados; `libgame.so` intacta, assinatura validada.
  Cliente de referência restaurado sem limpar dados.
- **29 testes de runtime**, **4 de transporte**, **14 de dados** e
  smoke test aprovados; compilação Python e `git diff --check` também passaram.
- Auditados os índices PyPI/Chaquopy: em 12/11/2026 não há wheel Android
  `cp314` pronta de `cryptography` ou `Pillow`. Não reutilizar ABI de
  Python 3.13 nem wheel Linux: é necessária compilação Android compatível.
- **Próxima prova de dependências:** produzir wheels Android `cp314`
  ARM64 para `cryptography` e `Pillow` (via cross-build/cibuildwheel),
  verificar ABI e importar no PID do jogo; depois repetir em x86_64.
- Persistem a inicialização na thread da Activity (lenta), servidor real,
  dependências nativas, 19 pacotes de dados e gameplay offline.

### 2026-11-12 — extensões Python e imports do Revival dentro do FFBE

- Empacotados **67 módulos `.so` oficiais** do CPython Android em assets,
  extraídos com nomes controlados para pasta privada de somente leitura.
  Dependências SSL/crypto/SQLite ligadas no split ARM64 original; `libgame.so`
  preservada sem modificações.
- Waydroid Android 13: logcat verificou `PYTHON-NATIVE-IMPORTS-OK` após
  importações de `zlib`, `ssl`, `sqlite3`, `socket`, `hashlib` e `zipfile`.
- Código versionado do Revival + PyYAML puro do sdist 6.0.3 (SHA-256 fixado)
  empacotados em **172 arquivos / 80,4 MB**, com manifesto SHA-256 e
  extração atômica sem tocar saves ou iniciar o servidor.
- Waydroid: logcat confirmou `PYTHON-REVIVAL-IMPORTS-OK` e importação dos
  módulos **reais** `yaml`, `serve`, `capture_server`; mesma prova na reabertura.
- x86_64: ponte JNI compilada e 67 extensões verificadas por arquitetura,
  **sem teste de execução no cliente Android x86_64**.
- Testes automatizados: **26** de runtime, **4** de rede, **14** de dados
  e smoke test; diffs do APK e split conferidos, assinatura de teste verificada.
- A instalação/importação ainda ocorre na Activity principal e pode gerar
  aviso de timeout de inicialização; exige thread/serviço próprio antes do uso.
- **Pendente à época desta prova:** servidor real em `127.0.0.1:18080`,
  `cryptography`/`Pillow`/`tzdata`, 19 pacotes e jogo offline. A prova de
  `tzdata` está registrada acima como etapa posterior.
- APK de laboratório revertido no Waydroid; instalação anterior preservada,
  sem limpar dados. Binários não são versionados no Git.

### 2026-11-12 — CPython ARM64 executado no processo FFBE

- Distribuições oficiais Python 3.14.10 aarch64 e x86_64 baixadas com SHA-256
  coincidente com python.org; NDK r27d instalado somente na bancada.
- Ponte JNI compilada para ARM64, `libpython3.14.so` e ponte adicionadas ao
  split `config.arm64_v8a.apk` de teste, sem modificar `libgame.so`.
- Na base, somente `classes.dex`, `classes3.dex` e o novo asset
  `assets/ffbe_python/stdlib.zip` foram adicionados/alterados.
- O `Py_GetVersion` retornou `3.14.10` no PID do FFBE.
- Primeira inicialização falhou por `encodings`: ZIP DEFLATED precisava da
  extensão `zlib` indisponível no bootstrap. Com ZIP_STORED, a segunda
  tentativa passou, sem crash do jogo.
- Waydroid Android 13: logcat comprovou `CPython 3.14.10 initialized;
  code executed` e `PYTHON-EXECUTED-42` após executar `assert 6*7==42`.
- Reinicialização do app repetiu o resultado sem baixar a stdlib; após
  `am force-stop` e estabilização do processo, listener 18081 foi fechado.
- Ponte JNI x86_64 compilada e arquitetura ELF validada em bancada;
  ainda **não** houve teste desse binário em cliente Android x86_64.
- Persistem pendentes bibliotecas dinâmicas/dependências, servidor Revival,
  lifecycle de produção, dados completos, Android ARM64 físico e gameplay offline.
- Código-fonte e reprodução em [android/runtime](../android/runtime/README.md);
  binários, APKs, NDK e recursos proprietários permanecem fora do Git.

### 2026-11-12 — bootstrap interno de laboratório

- Arquivos: `android/runtime/patch_bootstrap_probe.py`,
  `android/runtime/test_bootstrap_probe.py`, `android/runtime/README.md`.
- Testes: 4/4 unitários do bootstrap e 4/4 de transporte; compilação APKtool 3.0.3.
- Comparação do APK: somente `classes.dex` e `classes3.dex` alterados.
- Instalação Waydroid Android 13 via atualização do APK base e splits com a
  mesma assinatura; sem apagar os dados da instalação anterior.
- `Lapis.onCreate` iniciou a sonda HTTP em `127.0.0.1:18081`.
  Requisição local retornou **HTTP 200** e `FFBE-BOOTSTRAP-READY`.
- Após `am force-stop`, `ss -ltn` não mostrou listener na porta.
  `onDestroy` individualmente não foi demonstrado.
- **Status:** subetapa de infraestrutura validada. O bootstrap
  **não** é o runtime Python e **não fecha** nenhum item P0 de jogabilidade.
- **Próxima execução:** integrar CPython ao processo do jogo, preservando
  o patch mínimo do cliente e o mesmo motor de servidor do Revival.

### 2026-11-12 — recursos e transporte previamente validados

- `data/latest.json` declara 19 pacotes, cerca de 14,65 GB de download
  e 14,95 GB instalados; 22 GiB livres recomendados.
- Instalador e compartilhamento testados com arquivos sintéticos no Linux.
- A cópia parcial no Android anterior provocou 404 de arquivos de recurso.
  **Não** afirmar instalação completa no Android.

Documentação técnica: [Android](ANDROID.md),
[arquitetura de APK único](ANDROID_STANDALONE.md) e
[bootstrap de laboratório](../android/runtime/README.md).
