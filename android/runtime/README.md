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
# Teste atual: mover o JNI para uma thread Java privada, sem mudar o servidor.
python3 android/runtime/patch_async_python.py --apk "$ORIGINAL_BASE_APK" --decoded "$TMP/decoded"

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
**puro** extraído de um sdist, `tzdata` 2026.6, Pillow 13.0.0,
cryptography 50.0.2, cffi 2.1.1 e pycparser 3.12. As wheels nativas
ARM64 foram compiladas no Actions do fork com fontes SHA-256 fixadas.
O helper
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
  --pillow-wheel "$PILLOW_13_CP314_ANDROID_ARM64_WHEEL" \
  --crypto-wheel "$CRYPTO_50_CP314_ANDROID_ARM64_WHEEL" \
  --cffi-wheel "$CFFI_211_CP314_ANDROID_ARM64_WHEEL" \
  --pycparser-wheel "$PYC_PARSER_312_WHEEL" \
  --libffi-sdist "$LIBFFI_352_TARBALL" \
  --stdlib "$TMP/stdlib.zip" --out-stdlib "$TMP/stdlib-with-engine.zip" \
  --python-archive "$PYTHON_ARCHIVE" --python-prefix "$PYTHON_PREFIX" \
  --abi arm64-v8a --original-apk "$ORIGINAL_BASE_APK" \
  --dex-apk "$TMP/dex-only.apk" --out-apk "$TMP/base-with-engine-unsigned.apk"
```

O sdist PyYAML 6.0.3 é obtido do PyPI e tem SHA-256
`d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f`.
A wheel universal `tzdata-2026.6-py2.py3-none-any.whl` tem SHA-256
`0a10eec6e13ef16b627fabed9a5f2ba61a62b1c67f327305f4e7e412a70b4aec`.
As wheels puras são obtidas do PyPI. O `pycparser-3.12-py3-none-any.whl`
tem SHA-256 `a076f3f489b39b43ed13563a1dafe42447445bec2e294154ec5c57fcdda4c85e`;
o tarball `libffi-3.5.2.tar.gz` tem SHA-256
`f3a3082a23b37c293a4fcd1053147b371f2ff91fa7ea1b2a52e335676bac82dc`.
As licenças de todas as dependências (incluindo libffi estática) são
empacotadas. Não são incluídos dados de jogo de terceiros.

A compilação ARM64 de Pillow foi [aprovada no Actions](https://github.com/guimenegoi/mene-exvius-revival/actions/runs/43233327397);
cryptography (com `libpython3.14.so` em `DT_NEEDED`) foi [aprovada aqui](https://github.com/guimenegoi/mene-exvius-revival/actions/runs/43242186148)
e CFFI com libffi estática [aqui](https://github.com/guimenegoi/mene-exvius-revival/actions/runs/43239493938).
As wheels são artefatos temporários, não releases. Assine os dois APKs
experimentais e use os demais splits com o mesmo certificado.

**Prova obtida:** **1.063 arquivos / 93.764.953 bytes** do Revival e
dependências, extraídos com manifesto SHA-256 para o armazenamento privado.
No Waydroid ARM64, o logcat confirmou `PYTHON-REVIVAL-CRYPTO-OK`, após
executar fuso horário, PNG em memória, NIST AES-128-CBC, cifrar/decifrar
com `ffbe_crypto` e importar X.509, `serve` e `capture_server`.
A reabertura repetiu as provas. **Não houve** chamada a `serve.main()`,
HTTP Revival em `18080` ou gravação de saves.

## Worker Java de inicialização — 12/11/2026

O patch incremental `patch_async_python.py` transforma a **mesma** sonda
JNI que já executava `Py_InitializeFromConfig` na thread principal em um
`Runnable` chamado `FFBE-Python`. O `Lapis.onCreate` apenas agenda
`startAsync(Context)`; o worker carrega as mesmas bibliotecas nativas,
extrai/verifica os recursos e importa o backend do Revival.

O patch usa `getApplicationContext()`, flag `synchronized` para impedir
inicialização concorrente no processo e captura de exceções de criação.
Requer que `patch_python_execute.py` já tenha sido aplicado à árvore smali
decodificada. Não altera `libgame.so`, os saves, o transporte nem o JNI.
O `classes.dex` e `classes3.dex` são os únicos DEX modificados.

**Prova Waydroid:**
- `Lapis.onCreate()` retornou na thread principal `8073/8073` às
  **16:11:03.719**, enquanto `async worker started` apareceu em
  `8073/8124` no mesmo instante.
- `PYTHON-REVIVAL-CRYPTO-OK` apareceu em `8073/8124` às
  **16:11:18.444**. A conclusão dos imports/AES não bloqueou a Activity.
- Após `am force-stop`, segundo lançamento: thread UI `8322/8322`;
  worker `8322/8371`; prova AES concluída às **16:12:10.956**.
- Nenhum ANR ou timeout de lançamento foi encontrado nos logs examinados.
  A instalação de referência foi restaurada sem limpar dados.
- **45 testes de runtime** incluem os cinco contratos adicionais do patch;
  os antigos modos e arquivos originais continuam preservados.

**Limite:** isso ainda não é o lifecycle de produção. O worker termina
após a prova; faltam inicialização e encerramento do motor real,
readiness na porta 18080, controle da GIL, tratamento de reinício e
dados completos do jogo.

## Limites e pendências reais

- O Python **importa** os módulos de `ios-server/` e `source/server/`, mas
  **não inicia o servidor**, que ainda precisa ser integrado ao ciclo de vida.
  O listener Java 18081 continua sendo uma sonda, não o backend 18080.
- A stdlib nativa, PyYAML, tzdata, Pillow, cryptography, cffi e pycparser
  foram validados **em ARM64 no Waydroid**. Faltam os builds e testes reais
  em x86_64 e um dispositivo ARM64 físico. X.509 importou, mas a emissão
  de certificados ainda não foi comprovada. O OpenSSL indicou ausência de
  seu *legacy provider*; AES-128-CBC passou no teste.
- A extração da stdlib e dos módulos `.so` ainda confere comprimento, **não
  SHA-256** no dispositivo. Os **1.063 arquivos** do motor e das dependências
  já empacotadas têm SHA-256 e atualização atômica, mas a entrega final precisa
  validar todos os assets e tratar falhas.
- A inicialização/importação foi movida para a thread Java `FFBE-Python`
  **somente no APK de prova**, sem bloquear a abertura. O backend real ainda
  precisa de start/stop/readiness, tratamento da GIL e ciclo de vida robusto.
- Waydroid hospeda o split ARM64; Android ARM64 físico e fluxo x86_64 real
  continuam pendentes.
- Ainda não foram instalados os 19 pacotes completos no Android,
  nem executadas batalha e persistência inteiramente offline.

Estado de acompanhamento: [checklist de entrega Android](../../docs/ANDROID_CHECKLIST.md).
