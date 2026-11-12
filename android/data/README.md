# Instalação completa dos dados — FFBE Android

**Implementação de preparação de dados. Ainda não é um APK offline autossuficiente.**

O cliente FFBE Global 9.1.0 deve receber **todos os recursos antes da primeira
partida offline**. O manifesto atual em [data/latest.json](../../data/latest.json)
contém 19 pacotes: 18 para os arquivos nativos e tabelas do Revival e um
`client-assets` que contém `static/client/game-assets.apk`.

A versão de referência declara ~14,65 GB de downloads e ~14,95 GB extraídos.
A instalação inicial recomenda **22 GiB livres** para manter o maior ZIP
temporário e uma reserva. O download é sequencial, com retomada, e as
atualizações reutilizam o registro dos pacotes já instalados.

## Comandos de desenvolvimento

Os dados ficam numa pasta privada e canônica, compartilhada por cliente e
servidor **quando ambos estiverem integrados ao mesmo APK**:

~~~sh
DATA="$HOME/ffbe-android-data"
python3 android/data/offline_data.py plan    --data "$DATA"
python3 android/data/offline_data.py install --data "$DATA"
python3 android/data/offline_data.py verify  --data "$DATA"
~~~

O instalador **reutiliza** `ios-server/fetch_data.py` para todos os 18 pacotes
do motor e sua verificação SHA-256, sem modificar o fluxo Linux. Só a etapa
`client-assets` é adicionada; ela reutiliza o mesmo download com retomada,
SHA-256 e extração segura. Nenhuma parte do ZIP é colocada no Git.

A estrutura preparada contém:

~~~text
data/
  installed.json                  hashes dos 19 pacotes
  offline-client-assets.json      hash do APK de recursos extraído
  registry.json                   registro incluído nos pacotes
  static/
    mst_decoded/                  tabelas para o Revival
    text_decoded/                 textos decodificados
    cpk_extract/                  mídia preparada pelo motor
    client/shared_prefs/          registros de versão
    client/game-assets.apk        pacote original de recursos do cliente
  native/
    mst/                          tabelas de instalação do jogo
    localized_texts/
    common_lang/
    en/
    homeMarquee/
~~~

`verify` **não utiliza rede**: confere os hashes registrados dos 19 pacotes,
o hash real de `game-assets.apk`, arquivos e grupos críticos e a contagem
mínima de arquivos declarada no manifesto. Os hashes de todos os outros
arquivos extraídos não são recalculados individualmente nesse diagnóstico;
a procedência é verificada pelo SHA-256 de cada ZIP na instalação. Uma
verificação bem-sucedida não prova, por si só, jogabilidade offline.

## Reutilização de dados sem duplicação

O servidor lê `static/` e serve `native/` do mesmo diretório. O Android
original normalmente baixa as respostas HTTP e grava novos arquivos na
pasta privada do jogo. **Ainda precisamos conectar esses caminhos**, para
que o cliente use os dados instalados sem gerar uma segunda cópia de ~13 GB.

A versão PC usa um overlay de filesystem no runner ARM64 emulado. O Android
nativo não possui esse runner; portanto, a integração precisará mapear
os arquivos do cliente para `native/` por um mecanismo apropriado ao
Android, com proteção contra sobrescrita, sem VPN nem root. Isso permanece
pendente, assim como o Python integrado no APK.

O instalador deixa saves e arquivos do cliente fora da árvore de dados
canônica. Em nenhuma hipótese limpe dados do aplicativo para atualizar os
pacotes; preserve os saves separados.

## Critérios de aceite

- [x] Manifesto de 19 pacotes, com download incremental e SHA-256.
- [x] Cliente-assets real (71.997.144 bytes) extraído e hash conferido.
- [x] Reinstalação do cliente sem rebaixar pacotes do servidor.
- [x] Diagnóstico sem rede, verificação de arquivos críticos/contagem,
      correção de corrupção de client-assets e reserva de espaço.
- [ ] Instalação completa no Android de teste com os 19 pacotes.
- [ ] Mapeamento físico de dados entre servidor e cliente sem duplicação.
- [ ] Python Revival inicializado pelo próprio aplicativo.
- [ ] Partida, batalha, mapa, summons e save com rede desligada em Android ARM64.
- [ ] Instalação do APK final em aparelho limpo, sem Termux ou apps auxiliares.

O diagnóstico deve bloquear o modo offline quando falhar. O jogo não deve
fazer downloads de recursos enquanto a partida estiver em andamento.

## Testes

~~~sh
python3 -m unittest discover -s android/data -p 'test_*.py' -v
~~~

Os testes usam arquivos ZIP pequenos, sintetizados localmente, e não
baixam material proprietário. Eles exercitam instalação, retomada lógica
de pacotes, alterações, falta de arquivos, recusa de ZIP inseguro,
corrupção de recursos e falta de espaço.
