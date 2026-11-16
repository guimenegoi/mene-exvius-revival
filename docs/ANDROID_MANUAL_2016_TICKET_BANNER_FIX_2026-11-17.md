# RC3 Manual2016 — invocações por tickets fora do período

Captura Samsung 17/11: aba Limited Time exibia **Guaranteed NV Summon**
(lançamento **21/01/2021**) enquanto o replay manual estava no período
**30/06 a 06/07/2016**.

## Diagnóstico e solução

- `gacha_rotation.plan` selecionava corretamente o período de 2016, mas
  `gacha_archive.visible_banners` adicionava `held_ticket_ids` depois da
  rotação sem checagem de data. Um item de ticket obtido em outro período
  liberava invocações futuras, mesmo com o replay congelado.
- `held_ticket_ids` agora exige data de lançamento conhecida, anterior ao
  fim da janela histórica, e disponibilidade do banner durante a janela.
  Não apaga tickets; apenas oculta ofertas fora do período. O comportamento
  fora do replay permanece inalterado.
- A base tem **zero banners destacados datados de 30/06 a 06/07/2016**.
  O primeiro lançamento encontrado no catálogo é de **08/07/2016**
  (Kefka, Golbez, Chizuru), exibido em **07/07 a 13/07/2016**. Não
  preencher a semana inaugural com banners do futuro.

## Validação e distribuição

- 153 testes automatizados aprovados: runtime 96, data 15,
  distribution 13, network 4, backup 25; quatro novos testes cobrem
  tickets futuros, desbloqueio no período correto, comportamento fora
  do replay e visibilidade final.
- Execução com catálogo completo de 1.323 banners e inventário sintético
  contendo todos os tickets: nenhum Guaranteed NV de 2021 durante as quatro
  primeiras janelas de julho de 2016. Primeiro conjunto datado em 08/07.
- APK candidata **FFBE-Revival-RC3-Manual2016-TicketEra-ARM64-TEST-20261117.apk**;
  SHA-256 `ef7d96ffc2b335d3ddcf0e1e3a5956a52210e1886e553a33275727537fc38559`.
- Assinatura Android v1/v2/v3 válida, mesmo certificado da RC3 anterior,
  zipalign correto e HTTP 200 na distribuição privada.
- Diff contra RC3 Manual2016: **somente** `assets/ffbe_python/stdlib.zip`;
  dentro dele, **somente** `source/server/gacha_archive.py` e o manifesto
  SHA-256 mudaram. Cliente nativo, saves e código Java preservados.
- Falta conferir no Samsung a ausência da oferta de 2021 após atualizar
  por cima sem apagar dados e depois de uma reabertura. Sem pareamento
  validado, o Web Helper não garante aplicação remota de outro período.
