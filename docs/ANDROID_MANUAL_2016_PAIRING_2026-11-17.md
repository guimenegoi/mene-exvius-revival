# FFBE Manual2016 — pareamento seguro para sincronizar o Web Helper

## Diagnóstico no Samsung

- O Web Helper gravou a revisão `ddf5b103c3db...` contendo `manual`, início
  `2016-06-30` e período `07/07 a 13/07/2016`.
- A APK TicketEra já continha `config_sync.py`, porém `local_http.py` só ativava
  o sincronizador se houvesse `exvius/backup/config.json` privado. Essa APK
  não oferecia o endpoint de pareamento; logo nenhuma configuração pôde ser
  entregue ao Samsung sem provisionamento separado.

## Correção candidata

- `ffbe_history_pairing.py`: rota local `POST /__exvius/config/pair`
  restrita a `127.0.0.1`, código temporário de **600 s**, uso único,
  máximo de seis tentativas, TLS endpoint fixo, certificado CA validado,
  token não embutido e arquivos `0600`.
- `GET /__exvius/config/status` retorna apenas se está pareado, estado do
  sincronizador e intervalo **realmente carregado no processo**. Nenhum
  token, certificado, conteúdo do save ou caminho privado é exposto.
- Depois de parear, reiniciar o aplicativo permite `start_sync` conectar
  usando o mecanismo `config_sync` existente. A revisão remota entra em
  `staged-config.json` e só é aplicada após **outro** reinício. A campanha,
  inventário e `replay.json` não são alterados diretamente.
- Não inserir credenciais no Web Helper ou na APK. O operador autorizado deve
  usar uma conexão ADB aprovada e encaminhamento de `tcp:18080` para o
  servidor local do Android, recuperar o desafio temporário do logcat e
  transportar o Bearer+CA por canal privado. Não registrar comandos com o
  token em logs do shell nem guardar um ZIP de pareamento na pasta pública.
- O status `paired: true` significa apenas credenciais locais presentes;
  `state: pending_restart` confirma revisão recebida mas não aplicada.
  Conferir também `historical_from` e `historical_to` após o cold boot.

## Gates de release

- Testes sintéticos do endpoint: autorização, recusa, persistência e
  preservação das rotas FFBE normais; regressão runtime, dados,
  distribuição, rede e backup.
- Verificar que o APK assinado difere da TicketEra somente no
  `assets/ffbe_python/stdlib.zip`, com os arquivos de pareamento e bootstrap
  individualmente verificáveis e SHA-256 consistente.
- **Pendente de Samsung real:** parear via ADB autorizado, confirmar que
  recebe `ddf5b103c3db...`, reabrir, constatar
  `historical_from=2016-07-07`, e verificar banners de Kefka/Golbez/Chizuru
  sem perder o save. Não aplicar segredo remotamente sem a ação de pareamento.

A APK anterior e os saves existentes continuam sendo a referência de rollback.
