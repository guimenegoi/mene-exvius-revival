# Viabilidade do replay Global desde o lançamento (2016) — auditoria inicial

**Investigação:** 12/11/2026 · branch `research/global-2016-replay`
**Classificação:** diagnóstico funcional. **Não modifica o motor, o APK RC2, a instalação Waydroid ou saves.**

## Resumo

**Viável ajustar o ponto inicial; não viável aprovar fidelidade histórica com os dados atuais.**
O lançamento Global é oficialmente datado de **30/06/2016** pela Square Enix.
O replay do Revival começa por padrão em **16/12/2016** (semana Noctis).
`source/server/replay.py:start_date()` já aceita `EXVIUS_REPLAY_START`;
não é necessário criar uma segunda implementação de cronologia.

O teste isolado de módulos, sem escrever em `state/`, comprovou que as janelas
históricas se deslocam corretamente ao definir `2016-06-30`.
No entanto, o Vortex não recebe nenhum evento datado em junho, julho ou
agosto nessa simulação. A origem de dados histórica ainda é incompleta.

## Fontes e escopo

- Fonte primária: Square Enix, ficha de FFBE, lançamento **30/06/2016**:
  <https://press.na.square-enix.com/FINAL-FANTASY-BRAVE-EXVIUS>.
- Fonte complementar e **não exaustiva** de calendário Global:
  <https://exvius.fandom.com/wiki/Category:Events>.
- Comparar cuidadosamente a seção **Global Update History**, e **não**
  as datas da seção japonesa, em
  <https://exvius.fandom.com/wiki/Update_Schedule>.
- Código inspecionado: `source/server/replay.py`,
  `gacha_rotation.py`, `gacha_archive.py`, `event_archive.py`,
  `history_runs.py`, `ffbe_gacha.py`, `data_paths.py`,
  `ios-server/serve.py`, `ios-server/docker-compose.yml`.
- Dados analisados: `gacha_catalogue.json`, `unit_release.json`,
  `event_archive.json`, `event_history.json`,
  `content/unit_release_global.json`, `content/event_runs.json`,
  `content/event_quest_dates.json`.
- O teste de summons usa apenas os **273 banners de
  `gacha_catalogue.json`**; **não** é a lista integral de
  `ffbe_gacha.all_banners()`. Inicializar esta última no checkout
  isolado requer `mst_decoded/F_TICKET_MST.ndjson`, ausente neste
  ambiente. Não assumir que a simulação prova a tela final ou o pool
  completo do aplicativo.

## Inventário obtido em leitura somente

| Dado | Evidência e ressalva |
| --- | --- |
| Estreia Global | 30/06/2016 (Square Enix) |
| Data atual padrão do replay | 16/12/2016, definida em `replay.py` e `docker-compose.yml` |
| Banners antigos | 19 dos 273 registros **desse catálogo parcial** entre 30/06 e 15/12; primeiro em 08/07 |
| Unidades | 111 IDs anteriores a 16/12 em `unit_release.json` bruto; o cálculo de `replay.unit_dates()` com correções de datas retorna 115 |
| Elenco de lançamento | `content/unit_release_global.json` registra 37 unidades; sete delas ainda são datadas depois da semana inicial (Garland, Cloud of Darkness, Rydia, Terra, Zidane, Vivi, Kuja). Confirmar a fonte e o ID/raridade antes de corrigir |
| Eventos | 766 áreas no catálogo combinado, mas somente **8 áreas distintas** com período registrado entre 30/06 e 15/12, representando **7 nomes** (inclui duas áreas de *The Big Bridge*) |
| Quests | `content/event_quest_dates.json` data apenas uma área permanente antes de 16/12 (`899`); não valida todas as quests e recompensas iniciais |

As áreas com períodos pré-Noctis encontrados pelo código são:
`899` Chamber of the Fallen (permanente); `703` Orbonne Monastery Vaults;
`705` The Giant of Babel; `707` The Crystal Tower; `721` Trial of the Creator;
`709` e `6193` The Big Bridge; `704` The Hanging Edge.

**Lacunas candidatas para confronto com fontes Global:** *Lands of Plenty*,
*Demons Unleashed*, *Into the Abyss*, *Festival of the Autumn Moon* e
*Halloween - Night of the Pumpkin* não possuem áreas correspondentes
pelo nome no catálogo combinado. *Grand Gaia Chronicles* possui áreas
`720` e `913`, mas o início nelas é datado em 2017, apesar de referências
a 2016 na cronologia Global. Não registrar datas ou equivalências sem
validar os eventos e os assets reais; títulos/aliases podem variar.

## Experimentos executados (sem rede, sem salvar estado)

**Base:** `EXVIUS_REPLAY=1`, `EXVIUS_SUMMON_ROTATION=1`,
`EXVIUS_REPLAY_FULL_RUNS=1`, `EXVIUS_REPLAY_START=2016-06-30`.
Testes executados com `PYTHONDONTWRITEBYTECODE=1`, `record=False`
e âncora explícita/injetada em memória (`replay.anchor_week`), sem
`serve.py` nem instalação Android.

1. **Ritmo padrão 3:1:** janelas iniciais
   30/06–20/07; 21/07–10/08; 11/08–31/08; 01/09–21/09;
   as quatro primeiras janelas **não têm evento temporário datado**.
   O catálogo parcial retorna respectivamente 1, 3, 3 e 5 conjuntos
   de summons em oferta (inclui anúncios de períodos sobrepostos).
2. **Padrão `EXVIUS_VORTEX_EXTRA=2`:** durante essas janelas vazias,
   `event_archive.weekly_events()` mostra eventos sem data como
   *Challenge of the Brave*, *Monthly Fortune Hunt* e
   *Series Boss Battle*: **anacronismo** para replay rigoroso.
3. **Padrão de feriados:** `EXVIUS_ROTATION_HOLIDAYS=1` pode
   introduzir o banner de Natal de 23/12/2016 e o evento
   *Dread Frost Arrives* enquanto a janela histórica ainda está
   em outubro/novembro, pois o sistema liga feriados ao calendário
   **real**. Funcionalidade deliberada do Revival, incompatível com
   fidelidade cronológica estrita.
4. **Experimento estrito, `EXVIUS_REPLAY_PACE=1`,
   `EXVIUS_ROTATION_HOLIDAYS=0`, `EXVIUS_VORTEX_EXTRA=0`:**
   a janela 30/06–06/07 tem **zero** conjuntos do catálogo parcial
   e **zero** eventos temporários datados. A janela 07/07–13/07
   contém o banner de 08/07, mas ainda nenhum evento datado.
   O evento *Orbonne Monastery Vaults* só aparece a partir
   do bloco de 30/09, e o primeiro conjunto de 2016 precisa
   ser reconstruído com fontes Global.

Para simular cálculo puro das janelas, sem tocar no estado:

```sh
cd ~/Projetos/mene-exvius-revival-history
PYTHONDONTWRITEBYTECODE=1 EXVIUS_REPLAY_START=2016-06-30 \
  EXVIUS_REPLAY_PACE=1 python3 - <<'PY'
import sys
sys.path.insert(0, 'source/server')
import replay
for week in range(3):
    print(week, replay.historical_start(week),
          replay.historical_start(week + 1))
PY
```

**Limite:** a simulação desabilitou temporariamente, **somente no processo
de teste**, a filtragem de quests que lê MST decodificado, e injetou o
catálogo parcial em `ffbe_gacha.all_banners()`. Isso **não** comprova
batalhas, tickets, recompensas, downloads de arte ou save no cliente.

## Riscos de estado e arquitetura

- `source/server/replay.py:anchor_week()` grava o índice inicial em
  `state/replay.json`. O campo `start` registrado ali **não** é
  consultado por `window()` depois: alterar a variável
  `EXVIUS_REPLAY_START` num save já iniciado recalcula o período
  histórico em torno da mesma âncora, mudando abruptamente os banners
  sem migração explícita. Não apagar `replay.json`, pois o save e sua
  época de replay precisam de tratamento separado e reversível.
- No Android embarcado, `ios-server/serve.py` define os defaults
  de replay, mas `android/runtime/local_http.py` **não** define uma
  opção de início de replay. É necessário definir contrato
 /configuração antes do bootstrap, sem repetir o motor.
- Mesmo com datas corrigidas, o cliente Android 9.1.0 mantém UI moderna;
  o replay garante calendário de conteúdos, **não** as telas antigas.
- Prioridades de integração: não modificar artefato RC2, recursos
  proprietários, `data/latest.json` ou saves; usar branch e testes
  de dados antes de qualquer APK novo.

## Próximos passos antes de considerar viável uma versão inicial fiel

1. Construir matriz **Global 30/06–15/12/2016** com fontes e
   grau de confiança: banners, units/rarities, Vortex, trials,
   missões, lojas, moeda/trocas, recompensas e arte do evento.
2. Mapear eventos ausentes por nome **e área/quest ID**;
   verificar se os estágios ainda existem nos 19 packs e se há
   dados suficientes para execução, não apenas uma imagem de banner.
3. Confirmar as **sete unidades** do elenco de lançamento com datas
   tardias; corrigir sem incluir personagens/raridades futuras.
4. Definir política de feriados e extras para replay estrito
   (não abrir conteúdo futuro), com testes de semanas limítrofes
   30/06, 07/07, 30/09, 31/10, 24/11 e 16/12.
5. Criar estratégia versionada de âncora por save,
   migração/reinício **opcional**, sem exclusão de estado;
   conferir compatibilidade de progresso e itens já adquiridos.
6. Validar (com MST completo em **bancada isolada**) summons,
   pools, Event/Enhance/Special, abertura das quests e recompensas;
   depois gerar artefato próprio **somente após RC2 offline validada**.

**Decisão provisória:** manter `EXVIUS_REPLAY_START=2016-12-16` no APK
aprovado para teste. A pesquisa não comprova paridade histórica pré-Noctis.
