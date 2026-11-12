# FFBE Android — bootstrap e CPython incorporado (laboratório)

Este diretório mantém **provas isoladas**, não um APK offline jogável. O
objetivo continua sendo **um único FFBE Android**, sem instalação de Termux,
VPN, root, Proxmox ou serviço auxiliar. O cliente e os recursos proprietários
não são versionados.

## Provas verificadas (12/11/2026)

1. **Bootstrap Java:** `Lapis.onCreate` inicia, dentro do processo do jogo,
   uma sonda em `127.0.0.1:18081`. HTTP 200 e fechamento após
   `am force-stop`. A porta 18080 permanece reservada ao backend Revival.
2. **Carregamento nativo:** o split `arm64-v8a` passou a conter
   `libpython3.14.so` da distribuição oficial e a ponte JNI
   `libffbe_python_probe.so`. `Py_GetVersion()` retornou `3.14.10`
   diretamente do processo FFBE no Waydroid Android 13.
3. **Execução de Python:** o APK de teste carrega a stdlib de um asset privado
   e utiliza `Py_InitializeFromConfig` em modo isolado. Executou o código
   `assert 6 * 7 == 42` e o log exibiu **`PYTHON-EXECUTED-42`**.
   Essa execução ocorre somente durante o teste; não inicia o servidor.
   A segunda abertura do FFBE após `force-stop` repetiu o resultado, sem
   reinstalar o asset. A ponte x86_64 também compila com a ABI correta,
   mas ainda não foi testada dentro do cliente.

O cliente preserva `libgame.so` original. A base só recebe alterações
em `classes.dex`, `classes3.dex` e, na terceira prova, o asset
`assets/ffbe_python/stdlib.zip`. O split ARM64 recebe somente duas
bibliotecas novas. Os comparadores conferem que os demais membros originais
não mudaram. Os APKs são assinados **fora do Git** com a mesma chave de testes.

## Origem do runtime

- CPython oficial **3.14.10**:
  <https://www.python.org/downloads/release/python-31410/>
- Android NDK **r27d** (`27.3.13750724`), usado na compilação JNI.
- Hash SHA-256 Android aarch64:
  `423c80b957330cf0ebb92b9b20f2294c292144a441bdb0ceb8c69d14928e569b`
- Hash SHA-256 Android x86_64:
  `6ebda1fc3f28efc5861cad397254e8ce5d81ba4f83a3cb6a0c124c3826a0e14c`

Os scripts conferem esses hashes. **Não** acrescentar tarballs, SDK/NDK,
bibliotecas compiladas, APKs, splits, saves ou chaves ao repositório.

## Reprodução (bancada e APKs fornecidos pelo usuário)

Use `$TMP` em uma pasta descartável, sem apagar a instalação existente. Os
arquivos originais do FFBE são a base e os quatro splits 9.1.0, da mesma
revisão. O SHA do APK base é fixado em `android/network/patch_transport.py`.

```bash
python3 -m unittest discover -s android/runtime -p 'test_*.py' -v

java -jar apktool_3.0.3.jar d -r --no-assets -o "$TMP/decoded" "$ORIGINAL_BASE_APK"
python3 android/network/patch_transport.py --apk "$ORIGINAL_BASE_APK" --decoded "$TMP/decoded"
python3 android/runtime/patch_bootstrap_probe.py --apk "$ORIGINAL_BASE_APK" --decoded "$TMP/decoded"
python3 android/runtime/patch_python_probe.py --apk "$ORIGINAL_BASE_APK" --decoded "$TMP/decoded"
python3 android/runtime/patch_python_execute.py --apk "$ORIGINAL_BASE_APK" --decoded "$TMP/decoded"

java -jar apktool_3.0.3.jar b -o "$TMP/rebuilt.apk" "$TMP/decoded"
python3 android/network/assemble_test_apk.py --apk "$ORIGINAL_BASE_APK" \
  --rebuilt "$TMP/rebuilt.apk" --out "$TMP/dex-only.apk"

python3 android/runtime/build_python_probe.py \
  --abi arm64-v8a --python-archive "$PYTHON_ARCHIVE" \
  --python-prefix "$PYTHON_PREFIX" --ndk "$ANDROID_NDK" \
  --original-split "$ORIGINAL_ARM64_SPLIT" \
  --output-split "$TMP/arm64-unsigned.apk" \
  --output-so "$TMP/libffbe_python_probe.so"

python3 android/runtime/package_stdlib_probe.py \
  --abi arm64-v8a --python-archive "$PYTHON_ARCHIVE" \
  --python-prefix "$PYTHON_PREFIX" --original-apk "$ORIGINAL_BASE_APK" \
  --dex-apk "$TMP/dex-only.apk" --out-apk "$TMP/base-unsigned.apk" \
  --out-stdlib "$TMP/stdlib.zip"
```

- `$PYTHON_ARCHIVE` é o `python-3.14.10-aarch64-linux-android.tar.gz`
  oficial. `$PYTHON_PREFIX` é sua pasta extraída `prefix/`.
- `$ANDROID_NDK` é a raiz do NDK r27d, com `toolchains/llvm/`.
- Os dois APKs gerados são **não assinados**. Assine a base e o split
  modificado com a mesma chave de desenvolvimento; os demais splits
  continuam os originais assinados para o teste. Verifique a assinatura e
  faça `adb install-multiple -r`, **sem limpar dados**.
- Confirme o log `FFBE-EmbeddedPython: PYTHON-EXECUTED-42` no PID do FFBE.
  Este teste não usa o listener HTTP para executar Python. A porta 18081
  continua sendo apenas a sonda Java de bootstrap.

### Por que a stdlib não está comprimida no ZIP interno?

A primeira tentativa com `ZIP_DEFLATED` falhou ao importar
`encodings`, pois `zipimport` precisa de `zlib` para descompactar os
módulos, e essa extensão nativa ainda não está disponível durante o startup.
O ZIP **armazenado sem compressão** (cerca de 37,3 MB, 1.873 arquivos
`.py`) corrigiu a inicialização. O tamanho é provisório; a integração
completa deverá empacotar e carregar `lib-dynload` corretamente, com
verificação de integridade, antes de otimizar o formato.

## Limites e pendências reais

- O Python executou código dentro do FFBE, mas **não** roda
  `ios-server/serve.py` nem `source/server/`. O listener 18081 não é o
  backend Revival em 18080.
- Falta incorporar os módulos de extensão e dependências do backend
  (`cryptography`, `Pillow`, `PyYAML`, `tzdata`) com suas ABIs.
- A extração da stdlib é de laboratório: confere comprimento do asset, mas
  **ainda não verifica SHA-256 dentro do dispositivo**. O fluxo final exige
  atualização atômica, integridade, isolamento de saves e recuperação.
- O teste de inicialização ocorre no thread da Activity e mantém o
  interpretador ativo até o processo encerrar. O backend real precisará
  serviço/lifecycle próprio e start/stop/readiness seguros.
- Waydroid hospeda o split ARM64; Android ARM64 físico e fluxo x86_64 real
  continuam pendentes.
- Ainda não foram instalados os 19 pacotes completos no Android,
  nem executadas batalha e persistência inteiramente offline.

Estado de acompanhamento: [checklist de entrega Android](../../docs/ANDROID_CHECKLIST.md).
