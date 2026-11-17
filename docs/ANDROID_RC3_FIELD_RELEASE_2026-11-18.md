# Android RC3 — Manual2016 Field Preview (18/11/2026)

**Status:** release candidate de campo, **não** versão estável definitiva.
**Tag:** `android-rc3-manual2016-field-20261118`
**Branch de manutenção:** `release/android-rc3-manual2016-field-20261118`
**Android package:** `com.square_enix.android_googleplay.FFBEWW`, 9.1.0 / 9101, ARM64.

## APK imutável aprovado

Distribuição privada Tailscale (não publicar APK nem dados proprietários no GitHub):

`https://proxmox.tailcf6a16.ts.net:8443/candidates/FFBE-Revival-RC3-Manual2016-ARM64-FIELD-20261118.apk`

SHA-256:
`a93577f223c0525a8cd35cab8f0b06f87a0abb7560492874e6be703c58173d5a`

A release é uma **cópia byte a byte**, sem novo build, da candidata
`FFBE-Revival-RC3-Manual2016-PhonePair-Origin-ARM64-TEST-20261117.apk`.
O certificado de assinatura Android (SHA-256) permanece
`1e08a903aef9c3a721510b64ec764d01d3d094eb954161b62544ea8f187b5953`.
Não reinstalar no aparelho que já funciona. Em atualizações futuras,
instalar por cima com dados preservados; jamais desinstalar/limpar dados
como etapa de upgrade. Conservar backup válido de save antes de mexer.

## Aprovação de campo relatada pelo usuário (17/11)

- FFBE iniciou normalmente no Samsung com o backend local em
  `127.0.0.1:18080` (diagnóstico `Reachable`).
- Pareamento **sem computador/ADB** foi autorizado com código temporário
  de uso único gerado no Web Helper da LXC 120.
- `GET /__exvius/config/status` confirmou `paired=true`, o staging da
  revisão `ddf5b103c3db...` e `pending_restart` antes do cold boot.
- Usuário confirmou que reiniciar aplicou a cronologia e que o banner
  limitado de 08/07/2016 passou a aparecer.
- O início continua 30/06/2016, com `EXVIUS_REPLAY_MANUAL_WEEK=1`
  (07/07 a 13/07/2016) atualmente armazenado no Web Helper.

Essas verificações são de campo, não testes completos de gameplay.
O Web Helper continua no servidor; a APK é offline-first depois do sync.

## Código consolidado

- Linha Android de `fix/phone-pair-origin-policy-20261117`:
  cronologia manual, filtros de tickets futuros, endpoint local de pareamento,
  correção HTTP 501 e aceitação segura da origem do Chrome.
- Incorporação seletiva da branch `feature/settings-phone-pairing-20261117`:
  `settings_web.py`, `phone_pairing.py`, `config_service.py`, `config_sync`
  tests, UI tests, serviços systemd e documentação.
- `lxc_backup.py` e `diagnostics_transport.py` foram congelados do código
  **efetivamente executado na LXC 120**, preservando tanto o endpoint
  `/v1/configs` quanto o `/v1/diagnostics`, além do isolamento do handshake TLS.
- As credenciais não entram na APK, no Git, no pacote público, nos testes
  nem neste documento. A autorização de settings não habilita o backup de saves.
- A mesclagem completa da branch de settings foi **abortada** porque
  introduzia conflitos com a inicialização Android e inventários de 19/20
  pacotes; nenhum desses arquivos Android foi modificado na consolidação.

## Gates de release

- `python3 -m unittest discover -s android/runtime -p 'test_*.py' -q` — **105**.
- `android/data` — **15**, `android/distribution` — **13**,
  `android/network` — **4**, `android/backup` — **79**.
- **Total: 216 testes aprovados**. `git diff --check` sem erros.
- SHA-256 do APK canônico idêntico ao teste de campo; verificar HTTPS 200,
  `Content-Length`, ZIP íntegro e assinatura/identidade Android.
- Web Helper e receptor de backup da LXC 120 permaneceram ativos,
  sem restart/redeploy e sem alterar a revisão salva.

## Ainda pendente (fora desta release)

- Testar avanço e retrocesso no tempo mantendo units/itens, campanhas e save.
- Validar outros banners, eventos e loja em períodos posteriores a julho/2016.
- Revisar cutscene repetida do totem em Mitra, Arena, Coliseum e menus.
- Testar restore e estabilidade do backup automático no Samsung real.
- Sincronização refletida visualmente no Web Helper ainda carece de confirmação
  explícita de período aplicado no Android.
- Integração com upstream e testes de gameplay mais abrangentes antes de
  declarar uma versão estável.

## Rollback

Não substituir nem remover as candidatas existentes. A mesma APK assinada
permanece disponível com o nome `PhonePair-Origin`, e o estado da LXC 120
não foi modificado. Qualquer atualização futura que mexa no ciclo de vida
Android exige novo diff/teste específico; não editar esta tag imutável.
