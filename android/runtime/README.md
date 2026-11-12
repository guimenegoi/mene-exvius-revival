# Bootstrap Android — prova de ciclo de vida (somente laboratório)

Este diretório contém uma prova **não jogável** de que o processo do próprio
FFBE Global Android 9.1.0 pode criar um listener HTTP de loopback, sem Termux,
VPN, root ou servidor externo para a prova. **Não implementa o motor Python.**
A porta `18081` é exclusiva do diagnóstico; o transporte de desenvolvimento
para o backend Revival permanece na porta `18080`.

## Entrada e isolamento

- Use apenas o APK base original 9.1.0 cujo SHA-256 é fixado nos scripts de
  `android/network`; os quatro splits originais pertencem ao usuário.
- Primeiro execute `android/network/patch_transport.py`, que reutiliza os
  quatro caminhos Java já identificados. O patch de bootstrap exige esse helper.
- A alteração do cliente fica restrita a `Lapis.onCreate` e `Lapis.onDestroy`,
  e a duas classes de laboratório em `smali_classes3`.
- Nenhuma lógica de batalha, `libgame.so`, APK, certificado ou dado de jogo
  é incorporado ao Git.

## Compilação de desenvolvimento

A partir da raiz do repositório (substitua os caminhos pelos arquivos
pessoais, sem guardá-los no Git):

~~~sh
python3 -m unittest discover -s android/runtime -p 'test_*.py' -v

java -jar apktool_3.0.3.jar d -r --no-assets -o "$TMP/decoded" "$ORIGINAL_BASE_APK"
python3 android/network/patch_transport.py --apk "$ORIGINAL_BASE_APK" --decoded "$TMP/decoded"
python3 android/runtime/patch_bootstrap_probe.py --apk "$ORIGINAL_BASE_APK" --decoded "$TMP/decoded"

java -jar apktool_3.0.3.jar b -o "$TMP/rebuilt.apk" "$TMP/decoded"
python3 android/network/assemble_test_apk.py --apk "$ORIGINAL_BASE_APK" \
  --rebuilt "$TMP/rebuilt.apk" --out "$TMP/unsigned-base.apk"
~~~

O comparador de `assemble_test_apk.py` deve acusar **exatamente** mudanças
em `classes.dex` e `classes3.dex`. Antes de instalar, assine o APK base
gerado e os splits com a **mesma chave** que já assina a instalação de testes.
Compare os certificados; nunca desinstale nem limpe dados como solução a
uma divergência de assinatura.

O protocolo manual de aceitação é: atualizar o aplicativo no Waydroid,
iniciá-lo, conferir `adb logcat` por `FFBE-LocalBootstrap`, executar
`adb forward tcp:18081 tcp:18081`, consultar
`http://127.0.0.1:18081/__exvius/bootstrap` e receber
`FFBE-BOOTSTRAP-READY`. Após `am force-stop`, confirmar ausência
do listener no Android. A resposta em qualquer path é **deliberadamente
apenas uma sonda de laboratório**, não um endpoint do Revival.

## Evidência de 12/11/2026

- Quatro testes unitários do patch de bootstrap passaram.
- APKtool 3.0.3 recompilou a base; `assemble_test_apk.py` confirmou que só
  `classes.dex` e `classes3.dex` foram alterados.
- Atualização via `adb install-multiple -r` preservou os dados e utilizou
  a mesma assinatura de desenvolvimento.
- Waydroid Android 13: `HTTP 200` e corpo `FFBE-BOOTSTRAP-READY`.
- Logcat: inicialização do listener dentro do processo do jogo.
- Após `am force-stop`, `ss -ltn` não mostrou porta 18081 escutando.
  O processo secundário do app pode reiniciar para jobs Android sem executar
  `Lapis.onCreate`; portanto o callback `onDestroy` isolado **ainda não
  foi validado**.

**Próxima etapa:** substituir a sonda pelo bootstrap real com CPython
incorporado no APK, dependências das ABIs x86_64/ARM64, dados privados,
verificação de readiness e ciclo de vida do motor Revival. Não marcar
esse requisito como concluído por causa da sonda.

Estado de acompanhamento: [checklist Android](../../docs/ANDROID_CHECKLIST.md).
