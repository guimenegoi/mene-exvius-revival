# RC3 Events2016 — APK experimental de verificação (18/11/2026)

**Status:** candidata de teste no Samsung; não substitui a RC3 aprovada nem
constitui prova de que todos os eventos de 2016 sejam jogáveis.

## Distribuição privada

`https://proxmox.tailcf6a16.ts.net:8443/candidates/FFBE-Revival-RC3-Manual2016-Events2016-ARM64-TEST-20261118.apk`

**SHA-256:** `5d2b345733787c8e12352f2c765d414284df5c4ab3a789d81629c299093ef5b8`
**Bytes:** 310303676
**Package:** `com.square_enix.android_googleplay.FFBEWW`
**Android:** ARM64-v8a, versionCode 9101, versionName 9.1.0
**Signing cert SHA-256:** `1e08a903aef9c3a721510b64ec764d01d3d094eb954161b62544ea8f187b5953`

A instalação por cima deve preservar os dados; nunca desinstalar ou limpar
dados. **Não reinstalar a RC3 existente se não estiver testando a candidata.**
A tag da release RC3 de campo continua congelada.

## O que mudou frente à APK de campo

No APK externo, somente `assets/ffbe_python/stdlib.zip` difere, além da
assinatura digital atualizada. Dentro do ZIP Python exatamente três itens
mudaram, comparados por SHA-256 entrada por entrada:

- `ffbe_engine/source/server/event_archive.py`: no modo histórico manual,
  eventos sazonais seguem suas datas originais, não o Natal/Halloween do
  calendário real; Dread Frost área 906 abre em dezembro/2016.
- `ffbe_engine/source/server/content/event_runs.json`: encerrar o evento
  jogável de Orbonne em 13/10/2016, sem confundir o prazo de resgate da moeda.
- `ffbe_engine_manifest.json`: atualizado com os tamanhos e hashes de ambos.

Nenhum DEX, biblioteca nativa, mapa, asset, pacote de dados, nome, UID,
certificado, permissão ou outro módulo Python foi alterado.

## Validações concluídas

- 228 testes automatizados aprovados: runtime 109, data 15,
  distribution 13, network 4, backup 87.
- Real engine dry-run de 27 semanas com `FFBE_DATA` estático:
  Orbonne abre desde 29/09; Dread Frost (906) antes da correção não abria
  e agora abre desde 29/12, com as três missões preservadas.
- Cobertura estática de 10 áreas e 40 missões, 19 de exploração e 21 com
  reconstrução/derivação de combate, sem lacunas identificadas nessas fontes.
- Assinaturas Android v1, v2, v3 verificadas, `zipalign -c 4` passou,
  mesmo certificado da RC3, package/version/ABI iguais.
- APK servida via HTTPS privado com HTTP 200 e `Content-Length` exato.
- `git diff --check` limpo; branch separada da release aprovada.

## Check de campo ainda obrigatório

1. Se optar por testar, fazer cópia de segurança do save e instalar **por
   cima** da APK que já funciona, sem limpar os dados.
2. No Web Helper, escolher 29/09–05/10/2016 (sem novo pareamento), reiniciar
   o jogo, abrir Vortex e procurar Orbonne; testar BGN/INT/ADV exploração e
   batalhas até ELT. Verificar retorno ao menu e funcionamento da loja.
3. Escolher 20/10–26/10: Orbonne não deve mais estar aberta. Se houver
   Auracite no save, a loja pode continuar disponível pela regra atual de
   troca retroativa; isso é separado da duração das missões.
4. Escolher 29/12/2016–04/01/2017: Dread Frost (906) deve aparecer;
   verificar abertura de suas três missões, vitória, rewards e retorno.
5. Confirmar que retroceder no tempo não corrompe inventário ou progresso;
   nenhuma dessas validações pôde ser realizada no Samsung remotamente.

### Fora desta correção (dados não confirmados)

Eventuais recompensas específicas das reprises de 2017/2018; versão
original de Grand Gaia Chronicles; raids completos de A Frosty Offensive e
Night of the Pumpkin; Demons Unleashed, Into the Abyss e Lands of Plenty;
e demais trials de 2016 cuja associação completa não foi comprovada.
Não inventar quests nem habilitar `EXVIUS_EVENT_RUN_QUESTS_TABLE` globalmente
sem o teste Android documentado na auditoria.

**Rollback:** a APK anterior `FFBE-Revival-RC3-Manual2016-ARM64-FIELD-20261118.apk`
continua íntegra na distribuição privada, sem modificações.

## Correção de empacotamento: falha ao instalar no Samsung

A primeira candidata `Events2016-ARM64-TEST` falhou ao instalar. O diagnóstico
comparativo identificou que o uso de `zipalign -f 4` (sem `-p`) havia
eliminado o alinhamento de página das bibliotecas `.so` armazenadas sem
compressão. A RC3 aprovada tinha **8/8** bibliotecas com offset múltiplo de
4096 bytes; a candidata falha tinha **0/8**. Isso é uma causa compatível
com a rejeição de instalação, embora o erro exato do PackageInstaller
não tenha sido capturado.

Corrigido reutilizando o APK unsigned byte-pinned e `zipalign -f -p 4`,
seguido de assinatura com a **mesma chave** da RC3. Não houve alterações de
código-fonte, de gameplay, de save ou da APK aprovada nessa correção.

**APK substituta (única a testar):**

`https://proxmox.tailcf6a16.ts.net:8443/candidates/FFBE-Revival-RC3-Manual2016-Events2016-ARM64-PageAligned-TEST-20261118.apk`

**SHA-256:** `1ace63be6cc7f9124921176fc891099313a92667c2e69495e9f307e85dbdfd0c`
**Tamanho:** `310434748` bytes.

### Verificação antes/depois

| Artefato | Bibliotecas .so alinhadas a 4096 B | Resultado |
|---|---:|---|
| RC3 de campo aprovada | 8/8 | Instalou no Samsung |
| Events2016 TEST original | 0/8 | Rejeitada pelo instalador |
| Events2016 PageAligned TEST | 8/8 | Verificações estáticas aprovadas; falta instalação no aparelho |

- `zipalign -c -p 4` passou;
- assinaturas v1/v2/v3 verificadas;
- SHA-256 do certificado: `1e08a903aef9c3a721510b64ec764d01d3d094eb954161b62544ea8f187b5953`, igual ao da RC3;
- package `com.square_enix.android_googleplay.FFBEWW`, versão 9101,
  ABI ARM64 preservados;
- o único payload diferente da RC3 aprovada permanece sendo
  `assets/ffbe_python/stdlib.zip`;
- os **3302 payloads não-META-INF** da APK defeituosa e corrigida são
  idênticos; foram modificados apenas offsets de ZIP e assinatura;
- servidor HTTPS privado retornou HTTP 200 e Content-Length exato.

**Não reinstalar a versão anterior defeituosa.** A versão corrigida ainda
não recebeu confirmação de instalação no Android físico; nunca desinstalar
o aplicativo atual nem limpar dados para testar.
