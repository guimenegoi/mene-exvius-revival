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

## P0 — APK offline autossuficiente

- [x] Implementar instalador de manifesto (19 pacotes, retomada, SHA-256,
      reserva de espaço e verificação local sem rede) em `android/data`.
- [x] Testar layout de compartilhamento nativo/servidor sem duplicações em Linux.
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
      em memória no processo FFBE, inclusive após reinício. Pacote atual:
      **912 arquivos** (Revival, PyYAML, tzdata e Pillow), com SHA-256.
      **Somente importação**: backend e runtime final ainda não iniciam.
- [ ] Instalar/verificar os 19 pacotes **reais** no Android; confirmar os arquivos
      de tutorial, mapa, áudio e combate no armazenamento privado do cliente.
- [ ] Verificar escrita, atualização e preservação de saves no layout real ARM64.
- [ ] Empacotar runtime CPython incorporado, stdlib e dependências
      `cryptography`, `Pillow`, `PyYAML`, `tzdata` para x86_64 e ARM64.
      **Já validados em ARM64:** CPython, stdlib, PyYAML, tzdata e Pillow.
      **Bloqueadores:** build Android CPython 3.14 de `cryptography` e
      execução da pilha inteira em x86_64 e Android ARM64 físico.
- [ ] Integrar inicialização/desligamento do **motor Revival real** ao ciclo de
      vida do FFBE, com diagnóstico de readiness e falha segura.
- [ ] Tirar extração/importações da thread principal da Activity; no teste
      de laboratório a abertura ficou lenta e houve aviso de timeout Android.
- [ ] Integrar o instalador de dados ao mesmo APK (sem acesso ao armazenamento
      privado por outro app).
- [ ] Produzir APK assinado para testes com cliente, runtime e instalador
      integrados, usando patch mínimo e reprodutível.
- [ ] Passar pelo menos uma batalha, receber recompensa e persistir save com
      Wi-Fi/dados desligados e sem servidor externo; reabrir o jogo e conferir save.

## P1 — cobertura funcional e estabilidade

- [ ] World Map, exploração/encontros aleatórios, summons, inventário e quests,
      incluindo regressão de recompensas.
- [ ] Investigar incompatibilidade de `EXVIUS_WIKI_REWARDS=1`; atualmente o
      ambiente Android usa `0` como contorno provisório.
- [ ] Validar x86_64 e dispositivo Android ARM64 físico.
- [ ] Medir RAM/CPU/bateria, tela apagada, alternância de apps e reinício.
- [ ] Downloads apenas na configuração/atualização; zero dependência de rede
      durante a partida; preservação de saves em atualizações.

## P2 — entregável e pós-estabilização

- [ ] Instalação em aparelho limpo sem apps auxiliares; backup, recuperação,
      logs úteis e CI/release de build reproduzível.
- [ ] Rever direitos de redistribuição do upstream e dos recursos proprietários;
      não publicar APK original, recursos de jogo, saves ou chaves no Git.
- [ ] Retomar fidelidade histórica mais estrita (incluindo junho de 2016) só
      depois do primeiro APK offline realmente jogável.

## Registro de execução

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
