# Android RC3 — consolidação experimental da cronologia manual (17/11/2026)

## Base comprovada e objetivo

- Referência de inicialização/reabertura no Samsung: RC3 **HardlinkPermission**, código `8b98818` e APK privada `FFBE-Revival-RC3-HardlinkPermission-ARM64-TEST-20261116.apk`, SHA-256 `4bd83f73eadfc7f779e06801db15bdd19d09020e3dbe5a5ba041c0de324c795f`.
- Objetivo solicitado: início Global **30/06/2016**, semana histórica **0**, sem progressão no calendário real. Avanço manual em blocos de sete dias. A âncora anterior em `state/replay.json` e `campaign.json` ficam intocadas.
- O upstream `CreamySeaman6/Exvius-revival-ios` manteve `main` em `d6e8858` (13/11) na consulta de 17/11; sem novo merge funcional necessário. Branches de pesquisa anteriores não foram integradas em bloco.

## Integração sobre a APK funcional

- Mecanismo existente `source/server/replay.py` recebe janela virtual manual; `gacha_rotation.py` impede seleção sazonal pelo calendário real nesse modo.
- `android/runtime/manual_history.py` aplica as configurações locais versionadas **antes** de importar `serve`/`capture_server`. A APK experimental inicia em modo manual 2016 por padrão; `EXVIUS_VORTEX_EXTRA=0` desliga eventos aleatórios sem data, `EXVIUS_REPLAY_NOTICE_WEEKS=1` evita notícias de semanas anteriores.
- O `config_model` seguro da branch de settings é consumido sem substituir o backend `lxc_backup.py` da RC3. Mudanças remotas são apenas staged e aplicadas no próximo cold boot, se compatíveis. Um poll de 120 segundos é opt-in e só inicia se houver credenciais de backup privadas já provisionadas; não há nova autenticação embutida nem conexão obrigatória para jogar.
- Modo automático pode ser recuperado sem reescrever a âncora original, definindo a configuração explícita de modo `automatic`. O início padrão de retorno é `2016-12-16` caso não haja data inicial customizada.
- UI do painel Web Helper foi ajustada somente na branch experimental `feature/settings-manual-historical-2016` (`c558b39`): não implantada no servidor de produção.

## Verificações concluídas

- Suítes na integração Android: **149** testes (runtime 92, dados 15, distribuição 13, rede 4, backup 25), todos passaram.
- Suítes específicas no ramo experimental do painel: **22 testes da interface** e **22 de config_sync**, passaram.
- Em ambiente sintético: modo manual mantém a mesma semana ao passar o calendário real; avançar `0→1→2` altera sete dias por passo; retornar a automático e recusar uma configuração staged incompatível preservam `replay.json` byte a byte.
- Consulta de leitura aos dados locais, com 1.323 banners no catálogo completo: semana 0 (30/06–06/07/2016) **zero banners destacados e sete permanentes**; semana 1 (07–13/07) tem registro datado de 08/07. Não forçar banners de datas futuras para preencher a primeira semana.
- APK derivada exclusivamente da RC3 HardlinkPermission: diferença de membros **somente** `assets/ffbe_python/stdlib.zip`; manifesto de **1.088** arquivos do motor com SHA-256 validado, primeira instalação sintética extrai 1.088 e a segunda zero.
- APK `FFBE-Revival-RC3-Manual2016-ARM64-LAB-20261117.apk` no diretório privado `releases/candidates/`, SHA-256 `0728c85b75c4b2e1dc2446eeb2da51b20f7220dbd25bff7b865cddae20dc713d`. Android ARM64, package original `FFBEWW`, versionCode `9101`, assinatura **DEBUG original v1/v2/v3**, zipalign validado; endpoint privado HTTP 200.
- Binário do cliente, Java, DEX, bibliotecas nativas, recursos e packs inalterados. Saves reais e APK instalada não foram acessados para modificação.

## Limitações e gates abertos

1. **Não promover ou instalar como estável ainda.** Waydroid/ADB não estava disponível no workspace nesta execução; não houve primeira/segunda abertura em Android isolado com save sintético nem prova do polling HTTPS real do Samsung.
2. O painel Web Helper de produção permanece na versão anterior. Validar num ambiente isolado a revisão proposta via painel, o estado staged, a aplicação após reiniciar e a reversão, sem habilitar um backend incompatível.
3. A primeira semana Global pode ser vazia em banners destacados. Verificar fidelidade de permanent Vortex, conteúdos de lançamento, recompensas e lojas: certas câmaras permanentes da base moderna podem existir no catálogo sem data histórica. Não inventar lançamentos nem apagar conteúdo sem mapeamento.
4. Antes de experimentar in-place no Samsung: validar snapshot/backup do save ativo, obter aceite explícito para instalar a candidata, conferir pelo menos duas reaberturas, batalha, persistência e retorno à cronologia automática sem perda de progresso.
5. Documentar o fluxo de rollback; o downgrade entre APKs assinadas com mesmo `versionCode` e código nativo preservado ainda depende de validação em dispositivo, sem desinstalar ou limpar dados.

**Política:** preservar a RC3 HardlinkPermission e a `main` sem modificações. O código experimental está segregado; não publicar APKs nem chaves proprietárias no GitHub.
