# FFBE Revival — distribuição de laboratório

## Atualização — APK único RC2 ARM64/English (12/11/2026)

O arquivo testado no desktop é
`~/Downloads/FFBE-Revival-RC2-ARM64-English.apk` (assinado DEBUG,
SHA-256 `e761620f97fad6dac495a409ae6daa81f035ec432a5d97fc54eff4d9f3ad594e`).
Ele foi instalado no Waydroid com `adb install -r` sem limpar dados; o
Android retornou apenas um APK em `pm path`, e o FFBE chegou à Home/Vortex
com Revival HTTP local. **Não substitui teste em telefone ARM64 físico**.

A fusão reaproveita o mecanismo oficial do **REAndroid APKEditor v1.4.9**,
sem implementar outro merger. A entrada são exatamente quatro módulos do
RC2 já aprovado: `base.apk`, `split_config.arm64_v8a.apk`,
`split_config.en.apk` e `split_config.mdpi.apk`. **Não incluir
`split_config.fr.apk`.** Recursos multilíngues internos da base original
não são alterados para evitar perda de referências do cliente.

Exemplo de reprodução em ambiente com Java 17:

```bash
# Somente quatro APKs de entrada verificados em input/
# APKEditor-1.4.9.jar: SHA-256
# a9cd40df818845456be6d696de6110c89edf4b0a0580cb83438ed6b25a366e67
java -jar APKEditor-1.4.9.jar m -i input -o merged-unsigned.apk

# Assinar com a MESMA chave de testes dos splits RC2,
# para permitir atualizar sem perder os dados do app.
java -jar uber-apk-signer-1.3.0.jar -a merged-unsigned.apk   --allowResign -o signed

# Conferir antes de instalar: assinatura, CRCs dos quatro DEX,
# ffbe_python/stdlib.zip, oito bibliotecas ARM64 e res.arsc.
adb install -r signed/merged-unsigned-aligned-debugSigned.apk
```

O APK é específico para **ARM64** (não contém x86_64 nativo), tem
certificado DEBUG e **não inclui os 19 pacotes de dados**: uma instalação
limpa precisa baixá-los (~14,65 GB compactados), com SHA-256. O popup
residual de 0 KB não foi removido. Não publicar arquivos proprietários
do cliente ou dos pacotes em Git/releases públicos sem avaliar direitos.

As seções históricas abaixo registram os estágios anteriores à RC2.

Esta pasta documenta uma **cópia privada** dos APKs experimentais e dos
pacotes de instalação no disco externo montado no LXC `workspace` (117):

`/workspace/projects/ffbe-revival-distribution/`

## Variante de primeira execução

O HD externo também mantém `apk/first-run-experimental/`, sem substituir
os cinco splits de `apk/`. Essa variante inclui `DataDownloadActivity`,
o downloader upstream v0.1.30 com manifesto revisão 9 fixado e a ponte
CPython/Revival. O launcher abriu no Waydroid e a sonda AES passou, mas
**ainda não aguarda a prontidão HTTP 18080 antes de abrir o jogo**.
Os 19 pacotes não foram instalados no Android de teste. Seu uso é
**exclusivamente experimental** e não comprova gameplay offline.

A variante posterior `apk/first-run-readiness/` inclui a espera
assíncrona do handler real `127.0.0.1:18080/__exvius/hello`. O caminho
de **falha segura** foi comprovado no Waydroid: sem recursos, a tela
explica que o servidor não iniciou, o JNI/AES funciona e `Lapis` não é
aberto. A transição positiva após instalação dos 19 pacotes reais ainda
não foi comprovada. Ambas as variantes são de laboratório, não releases.

## Ensaio de instalação usando o cache privado do LXC

O laboratório pode testar **a Activity e o instalador Android reais** sem
baixar novamente os 14,65 GB do GitHub. O script
`android/distribution/local_cache_server.py` publica apenas o manifesto
fixado e os 19 ZIPs existentes, com suporte a HTTP Range para retomada.
A origem local é **exclusiva do laboratório**:
`127.0.0.1:18082` no LXC, encaminhada por SSH para o desktop e de lá
por `adb reverse tcp:18082 tcp:18082` para o Waydroid.

`build_local_install_lab.py` valida o SHA-256 do APK unsigned aprovado e
recompila **somente classes4.dex**: a URL do manifesto e o prefixo dos ZIPs
passam a `127.0.0.1:18082`. Para contornar a indisponibilidade do
DownloadManager do Waydroid nessa origem, a consulta pequena do manifesto
reutiliza `DataUpdates.resumableDownload()` já utilizado pelos ZIPs.
Todos os demais arquivos do APK são comparados byte por byte. O resultado
não é um APK de distribuição, depende do túnel ADB/SSH e **jamais deve ser
publicado** com URL de laboratório.

Essa variante **não altera os 19 hashes**, o inventário, os saves nem
os arquivos ZIP originais; o instalador Android continua responsável
por verificar SHA-256, extrair, fazer journaling e remover os temporários.
É um teste da instalação automática original, não um segundo instalador.

## Estrutura

- `apk/`: cinco splits Android **assinados com certificado de teste**, da
  variante FFBE 9.1.0 com CPython 3.14 ARM64, Revival e verificação de dados.
- `packs/`: ZIPs upstream, um por ID de `data/latest.json`; nenhum arquivo
  é alterado ou extraído, com SHA-256 conferido após download.
- `installer/`: cópia das fontes de instalação e manifesto fixado.
- `install_debug_split.sh`: atualiza via ADB os cinco APKs **sem desinstalar**
  nem limpar dados. Execute após copiar a pasta para um computador com ADB.

### Cache dos arquivos originais (LXC ou desktop)

```bash
python3 installer/android/distribution/cache_packs.py \
  --manifest installer/data/latest.json --destination packs

# Apenas validação, sem rede:
python3 installer/android/distribution/cache_packs.py \
  --manifest installer/data/latest.json --destination packs --verify-only
```

O script reutiliza o downloader de `ios-server/fetch_data.py`, com retomada
por HTTP Range; os 19 ZIPs totalizam aproximadamente **14,65 GB**.
Downloads incompletos permanecem como `.part` para retomada.

**Estado verificado em 12/11:** o APK experimental **instalou os 19 pacotes
reais automaticamente no Waydroid**, usando o cache do LXC por um túnel
**exclusivo de laboratório**. O motor Revival entrou em `127.0.0.1:18080`
e abriu o título. Ainda falha um download complementar da tabela
`F_BANNER_MST`; portanto, o APK **não é uma release jogável**.
A variante com URL `127.0.0.1:18082` não deve sair do laboratório;
para distribuição, usar os endereços upstream fixados e validar em Android
ARM64 real. Ver [auditoria](../../docs/ANDROID_AUDIT_2026-11-12.md).

O código `android/data/offline_data.py` permanece como verificador e
adaptador de recibos; o próprio `DataUpdates` upstream faz a instalação.
A instalação exige **pelo menos 22 GiB livres** no dispositivo, conforme
estimativa conservadora do projeto.

Não publicar APK, recursos de jogo, saves ou chaves em releases públicos.
O cliente e os assets originais pertencem aos seus respectivos titulares.

## Download privado de APK diretamente da LXC (branch experimental)

O protótipo `android/distribution/apk_lan.py` reaproveita o mesmo
`make_handler` HTTP Range do cache, mas executa **em processo separado**,
numa porta exclusiva para servir **um único APK**, com nome e SHA-256
exatos. O serviço do instalador que só escuta `127.0.0.1:18082` não
é modificado nem exposto à LAN.

Exemplo para **bancada controlada**, depois de copiar um APK aprovado
para a LXC (sem enviá-lo ao Git e sem usar o diretório de saves):

```bash
python3 android/distribution/apk_lan.py \
  --apk /workspace/projects/ffbe-revival-distribution/apk/private/FFBE-Approved.apk \
  --sha256 <sha256-confirmado-do-apk> \
  --bind 192.168.15.209 --port 18448 --minutes 30
```

O comando verifica o arquivo inteiro antes de abrir a porta. Ele imprime
um **link temporário com token criptograficamente aleatório**, acessível
pelo navegador do celular na mesma rede Wi-Fi. Suporta `GET`, `HEAD`
e `Range: bytes=N-`; após expirar, encerra o listener. Sem listagem
de diretórios, sem rotas de dados/ZIPs e sem acesso público configurado.

**Limite de segurança:** o link atual é HTTP simples; o token e o APK
não estão criptografados na rede. Usar apenas em LAN confiável, jamais
com port forwarding ou exposição à internet. Não guardar/compartilhar
o link, e verificar assinatura e SHA-256 antes de instalar. Para uso
frequente, preferir TLS com certificado confiável e autenticação.

**Estado:** ferramenta de prova em branch; não é um serviço permanente
nem foi configurada no celular. Nenhum arquivo de jogo será entregue
automaticamente sem um comando explícito.
