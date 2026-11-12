# Prova de transporte local — FFBE Global 9.1.0

**Somente desenvolvimento. Não é um APK offline autossuficiente.**

A versão [Exvius Revival Desktop](https://github.com/CreamySeaman6/Exvius-Revival-Desktop) demonstra redirecionamento de HTTP na interface Java/JNI, sem alterar a biblioteca nativa do jogo. Aqui aplicamos o mesmo princípio ao cliente Android real, preservando os quatro mecanismos Java e seus callbacks.

## Entradas verificadas no APK original

O patch é restrito aos métodos:

- classes3.dex: Cocos2dxHttpURLConnection.createHttpURLConnection
- classes3.dex: Cocos2dxDownloader.createTask
- classes.dex: CriFsWebInstaller.Copy
- classes.dex: FileDownloader.downloadFile

Apenas URLs HTTP(S) cujo host seja gumi.sg / exvius.com ou subdomínio de cada um são redirecionadas para http://127.0.0.1:18080 (porta configurável no patch). Caminho e query são preservados. URLs de terceiros permanecem intactas. O código não altera libgame.so, DNS, VPN, certificados, splash, gameplay ou outros aplicativos.

SHA-256 fixado do APK base 9.1.0 original usado no teste:

    0c0edf056e564e689d6fb5d95832d66a06611034045e256c51779b0418bf3735

## Reproduzir em ambiente de desenvolvimento

Requer Python 3, Java e apktool 3.0.3. O arquivo de entrada precisa ser um APK original fornecido pelo próprio usuário. Exemplo:

~~~sh
python3 -m unittest discover -s android/network -p 'test_*.py' -v
java -jar apktool_3.0.3.jar d -r --no-assets -o "$TMP/decoded" "$ORIGINAL_BASE_APK"
python3 android/network/patch_transport.py --apk "$ORIGINAL_BASE_APK" --decoded "$TMP/decoded"
java -jar apktool_3.0.3.jar b -o "$TMP/dex-rebuilt.apk" "$TMP/decoded"
python3 android/network/assemble_test_apk.py --apk "$ORIGINAL_BASE_APK" \
  --rebuilt "$TMP/dex-rebuilt.apk" --out "$TMP/unsigned-test-base.apk"
~~~

O script recompõe o APK base preservando os membros originais e substituindo somente classes.dex e classes3.dex. Ele é intencionalmente **não assinado**. Para teste isolado, assine o APK base e os splits originais com uma mesma chave de desenvolvimento e verifique os certificados antes de instalar. NÃO publique APKs, XAPKs, recursos proprietários nem chaves no fork.

## Resultado obtido em 12/11/2026

- Compilação com apktool 3.0.3: passou.
- Comparação de todas as entradas ZIP do APK base: somente classes.dex e classes3.dex diferem.
- APK assinado com a mesma chave de teste da sessão Waydroid isolada: atualização por cima da instalação anterior, sem limpar dados.
- FFBE 9.1.0 abriu; requisições da API do jogo foram recebidas por servidor Revival no Termux em localhost:18080.
- Downloads do CriFsWebInstaller chegaram ao mesmo servidor com User-Agent do jogo.
- Dados parciais do laboratório geraram 404 para arquivos de localized_texts/en. Após instalar apenas esse diretório, o cliente apresentou uma etapa de download de 36.505 KB e voltou à tela inicial.
- O passo seguinte pediu en/sd/area/Ver461_spdungeon1.cpk e recebeu 404: o arquivo existe no conjunto completo de referência, mas não na cópia reduzida do Android.
- Cocos2dxDownloader e FileDownloader ainda não foram validados individualmente em uma sessão jogável.

**O jogo NÃO está offline nem é autossuficiente.** O Termux foi usado apenas como processo de laboratório. Não é requisito ou componente autorizado na entrega final. Falta incorporar o motor Revival ao próprio aplicativo e instalar/compartilhar o conjunto completo de recursos, evitando cópias redundantes (ver mecanismo FFBE_OVERLAY do projeto Desktop).

## Próximos critérios

1. Importar o conjunto completo de dados uma única vez, com verificação de hash, sem perder o save.
2. Integrar Python e o motor Revival como componentes do próprio APK.
3. Restringir o listener a loopback, iniciar/parar junto com o jogo e verificar consumo.
4. Provar API e todos os downloads locais, sem solicitações à rede externa.
5. Validar ciclo completo de batalha/save/reinício no Android ARM64 e x86_64.
6. Preparar distribuição compatível com os direitos do material original.

Arquitetura do aplicativo único: [docs/ANDROID_STANDALONE.md](../../docs/ANDROID_STANDALONE.md).
