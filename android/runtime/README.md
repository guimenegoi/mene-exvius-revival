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
`.py`) corrigiu a inicialização. O empacotador de laboratório agora acrescenta
as 67 extensões oficiais de `lib-dynload` como assets e três bibliotecas
auxiliares ao split ABI. O tamanho e os mecanismos de integridade ainda
precisam ser refinados para produção.

## Extensões nativas e código real do Revival — 12/11/2026

A prova adicional verificou dentro do FFBE Android ARM64 os imports de
`ssl`, `sqlite3`, `zlib`, `socket`, `hashlib` e `zipfile` (`PYTHON-NATIVE-IMPORTS-OK`).
A biblioteca padrão permanece no ZIP de bootstrap; os 67 módulos nativos
oficiais são extraídos para uma pasta privada com nomes restritos e
permissão somente leitura. `libcrypto_python.so`, `libssl_python.so` e
`libsqlite3_python.so` são incluídas no split ARM64 sem alterar `libgame.so`.

O novo empacotador `package_engine_probe.py` acrescenta ao ZIP a árvore
**versionada** de `ios-server/` e `source/server/`, junto do PyYAML 6.0.3
**puro** extraído de um sdist e do `tzdata` 2026.6 (wheel universal),
ambos verificados por SHA-256. O helper
`ffbe_engine_bootstrap.py` instala arquivos na pasta privada usando manifesto
SHA-256, arquivos temporários e substituição atômica, sem utilizar o diretório
de saves. Foi validada a instalação incremental: uma segunda execução não
reinstalou nenhum arquivo íntegro.

Reprodução adicional (continuando após a geração do `stdlib.zip` e do
`base-dex-unsigned.apk` descritos acima):

```bash
python3 android/runtime/build_python_probe.py --abi arm64-v8a \
  --python-archive "$PYTHON_ARCHIVE" --python-prefix "$PYTHON_PREFIX" \
  --ndk "$ANDROID_NDK" --original-split "$ORIGINAL_ARM64_SPLIT" \
  --output-split "$TMP/arm64-with-native-unsigned.apk" \
  --output-so "$TMP/libffbe_python_probe.so" --extra-native-libs

python3 android/runtime/package_engine_probe.py --repo "$PWD" \
  --pyyaml-sdist "$PY_YAML_603_TARBALL" \
  --tzdata-wheel "$TZDATA_2026_6_WHEEL" \
  --stdlib "$TMP/stdlib.zip" --out-stdlib "$TMP/stdlib-with-engine.zip" \
  --python-archive "$PYTHON_ARCHIVE" --python-prefix "$PYTHON_PREFIX" \
  --abi arm64-v8a --original-apk "$ORIGINAL_BASE_APK" \
  --dex-apk "$TMP/dex-only.apk" --out-apk "$TMP/base-with-engine-unsigned.apk"
```

O sdist PyYAML 6.0.3 é obtido do PyPI e tem SHA-256
`d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f`.
A wheel universal `tzdata-2026.6-py2.py3-none-any.whl` tem SHA-256
`0a10eec6e13ef16b627fabed9a5f2ba61a62b1c67f327305f4e7e412a70b4aec`.
Ambos os pacotes são obtidos do PyPI e suas licenças são incorporadas.
Não são incluídos dados de jogo de terceiros.
Assine os dois APKs e use os demais splits de teste com o mesmo certificado.
No Waydroid, o logcat deve registrar `PYTHON-REVIVAL-TZDATA-OK`.

**Prova obtida:** 801 arquivos do Revival + PyYAML + `tzdata` importados
no processo do FFBE, após extração com SHA-256. Incluem `yaml`, `tzdata`,
`zoneinfo`, `serve` e `capture_server`. Foi validado o fuso
`America/Sao_Paulo` usando os dados empacotados, sem a base do Android.
A reabertura do jogo repetiu os imports. **Não houve**
chamada a `serve.main()`, HTTP em `18080` ou acesso aos saves.

## Limites e pendências reais

- O Python **importa** os módulos de `ios-server/` e `source/server/`, mas
  **não inicia o servidor**, que ainda precisa ser integrado ao ciclo de vida.
  O listener Java 18081 continua sendo uma sonda, não o backend 18080.
- A stdlib nativa, PyYAML e `tzdata` foram validados; `cryptography` e
  `Pillow` exigem builds Android compatíveis com **CPython 3.14**. O índice
  Chaquopy consultado em 12/11/2026 oferece wheels dessas bibliotecas para
  CPython até 3.13, mas não 3.14; wheels Linux/3.13 não são substitutos.
- A extração da stdlib e dos módulos `.so` ainda confere comprimento, **não
  SHA-256** no dispositivo. Os 801 arquivos do motor e das dependências
  puras têm SHA-256 e atualização atômica, mas a entrega final precisa
  validar todos os assets e tratar falhas.
- A inicialização/importação ocorre na thread da Activity e levou vários
  segundos, inclusive com timeout visual na primeira abertura. O backend real
  precisa iniciar em thread/serviço próprio, com start/stop/readiness seguros.
- Waydroid hospeda o split ARM64; Android ARM64 físico e fluxo x86_64 real
  continuam pendentes.
- Ainda não foram instalados os 19 pacotes completos no Android,
  nem executadas batalha e persistência inteiramente offline.

Estado de acompanhamento: [checklist de entrega Android](../../docs/ANDROID_CHECKLIST.md).
