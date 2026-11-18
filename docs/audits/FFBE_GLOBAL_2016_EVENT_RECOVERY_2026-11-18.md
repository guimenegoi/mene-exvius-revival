# FFBE Global 2016 — recuperação de eventos (diagnóstico, 2026-11-18)

**Estado:** investigação reproduzida; nenhuma mudança na APK, nos gates, na LXC ou no save.
**Base auditada:** RC3 Manual2016 aprovada (tag `android-rc3-manual2016-field-20261118`), branch de prévia histórica até `6f673a6`.
**Cronologia de referência:** vault pessoal `B04 INTERESSES/REGISTROS/Jogos/Anotações/notas-ffbe-global-cronologia-de-eventos-e-banners-2016.md`.

## Correções ao diagnóstico anterior

A presença em `event_archive.json` **não é** o catálogo completo. O módulo
`event_archive.document()` acrescenta nove eventos de `event_history.json`,
entre eles **Orbonne Monastery Vaults, área 703**, de 2016-09-30.
A área 703 foi incorretamente classificada como ausente ao consultar apenas
`event_archive.json`. `event_history.json` também associa estreias originais
de 2016 a áreas com `release` de reprises posteriores. Há conteúdo adicional
em `event_art.json`, `content/exploration_wiki.json`, nas MST e na derivação
de batalhas, mesmo sem entrada em `event_encounters.json`.

## Orbonne Monastery Vaults: evidências reproduzidas

- `event_history.json`: área `703`, masmorra `70301`, oito missões, estreia
  Global `2016-09-30`, reprise `2018-07-20`.
- `content/event_runs.json`: `2016-09-30`–`2016-10-19` e `2018-07-20`–`2018-08-09`.
- `F_MISSION_MST.ndjson` do pacote preservado (lido de
  `runtime-data/static/mst_decoded`): todas as oito missões existem; três
  explorações sem ondas de batalha direta, cinco batalhas com 3/3/4/5/6 ondas.
- `content/exploration_encounters.json`: três explorações com listas de
  inimigos e zonas (`7030101`, `7030102`, `7030103`, `missing=[]`).
- **Derivação do combate:** `battle_content.derive_mission(mid, IndexSource(),
  break_status={}, roll_all=False)` produziu grupos, inimigos e fases nas
  cinco missões de batalha. Esse ensaio é **sem abrir o cliente e sem executar
  vitória**, não valida AI, efeitos gráficos, softlocks ou recompensas.
- `content/global_drops.json`: moeda `20:106300100` (Auracite Shard) com
  regras para **as oito missões**, incluindo inimigos de batalha e exploração.
- `content/event_exchanges.json`: troca `900105`, quinze linhas, primeira
  disponibilidade `2016-09-30`, vínculo explícito com área 703 e Auracite Shard.
- `content/event_quest_dates.json`: nenhuma das oito missões tem data de
  introdução individual. As datas de cada fase em 2016 versus 2018 ainda
  não foram comprovadas independentemente, embora as oito existam no pacote.
- **Dry-run do runtime:** com FFBE_DATA apontando ao pacote estático,
  EXVIUS_REPLAY=1, EXVIUS_SUMMON_ROTATION=1, EXVIUS_REPLAY_MODE=manual,
  EXVIUS_REPLAY_START=2016-06-30, EXVIUS_REPLAY_MANUAL_WEEK=13 e
  EXVIUS_EVENT_ARCHIVE=1, `event_archive.weekly_events()` **incluiu a área
  703 e as oito missões** na semana 2016-09-29–2016-10-06.
- Os dez arquivos principais de eventos, batalhas, encontros e datas foram
  comparados anteriormente por SHA-256 com `assets/ffbe_python/stdlib.zip`
  da RC3: todos coincidem byte a byte.

| Missão | Tipo no cliente | Ondas declaradas | Fonte complementar verificada |
|---|---|---:|---|
| 7030101 | Vault Exploration BGN | 0 | `exploration_encounters`; drop Auracite |
| 7030102 | Vault Exploration INT | 0 | `exploration_encounters`; drop Auracite |
| 7030103 | Vault Exploration ADV | 0 | `exploration_encounters`; drop Auracite |
| 7030111 | Battle in the Vaults BGN | 3 | `battle_content.derive_mission`; drop Auracite |
| 7030112 | Battle in the Vaults INT | 3 | `battle_content.derive_mission`; drop Auracite |
| 7030113 | Battle in the Vaults ADV | 4 | `battle_content.derive_mission`; drop Auracite |
| 7030114 | Battle in the Vaults PRO | 5 | `battle_content.derive_mission`; drop Auracite |
| 7030115 | Battle in the Vaults ELT | 6 | `battle_content.derive_mission`; drop Auracite |

**Pesquisa contemporânea:** a discussão do Global iniciada em 30/09/2016
confirma exatamente a estrutura de 3 explorações e 5 batalhas, com inimigos
e drops de Auracite, mas informa duração jogável até **14/10** e prazo para
resgate até **18/10**. O índice local, que marca a atividade até **19/10**,
deve ser confrontado com o anúncio original antes de uma correção de datas.
Fonte: https://www.reddit.com/r/FFBraveExvius/comments/556xad/global_event_megathread_orbonne_monastery_vaults/

**Risco da reprise:** em 20/07/2018 jogadores registraram a adição de
recompensas de conclusão à reprise. Não presumir que as recompensas de
primeira conclusão na MST de fim de serviço existiam em 2016.
Fonte: https://www.reddit.com/r/FFBraveExvius/comments/90ed03/osborne_monastery_lapis_completion_rewards_added/

## Outros eventos de 2016 — triagem de recursos

| Evento | Área e evidência | Pendência |
|---|---|---|
| Demons Unleashed (01/08) | Sem área identificada no catálogo agregado | Localizar missão e pacote histórico |
| Into the Abyss (19/08) | `content/exploration_wiki.json`, `exploration_encounters.json` e `collection_points.json` preservam referências | Resolver ID da missão Vortex e cenário |
| Festival of the Autumn Moon (01/09) | Nome presente em campanha/banner de 2017 | Nenhuma missão original comprovada |
| Lands of Plenty (18/09) | Sem área identificada no catálogo agregado | Localizar missão e pacote histórico |
| Orbonne Monastery Vaults (30/09) | **703; 8 missões; 3 explorações; 5 batalhas deriváveis; moeda e loja** | Testar ponta a ponta, reconciliar duração e rewards da reprise |
| The Giant of Babel (14/10) | **705**, cinco missões de exploração com fonte complementar e início de 2016 em `event_runs.json` | Confrontar a edição original com a reprise de 2017 |
| Halloween – Night of the Pumpkin (21/10) | `event_art.json` preserva `90002`–`90004` e desafios da família 902–904 | Não extrapolar para o evento King Mog inteiro |
| The Crystal Tower (04/11) | **707**, cinco missões de exploração e data original | Reprise de 2017 registra missões adicionais; isolar edição inicial |
| Grand Gaia Chronicles (11/11) | **720/913**, três encontros por área | Primeira execução de 2016 não associada a essas áreas no índice de runs |
| Trial of the Creator (18/11) | **721**, dois encontros, início de 2016 | Testar fidelidade das missões de 2017 |
| The Big Bridge (24/11) | **709/6193**, seis missões no total com dados de exploração e início de 2016 | Comparar edições de 2016/2017 |
| The Hanging Edge (02/12) | **704**, cinco missões com `event_battles` e início de 2016 | Comparar recompensas e versão de 2018 |
| A Frosty Offensive (23/12) | Dungeon `90005`, área permanente **905**, quatro missões `9000402`–`9000405` datadas de 2016 e com encontros | Confirmar alcance do raid original versus Chamber of Challenges |
| Dread Frost Arrives (30/12) | **906**, três missões com encontros e período histórico desde 2016 | Validar tela, ondas, recompensas e desbloqueio |

**Trials:** `event_quest_dates.json` associa as primeiras missões `8991101`–
`8991104` aos lançamentos de 25/08, 27/10, 24/11 e 08/12/2016; cada uma
possui dados de batalha. Demon Chimera e Brachiosaur ainda precisam de
mapeamento distinto das batalhas posteriores com rótulo *Scorn*.

## Próximos gates necessários

1. Observar área 703 no Android com seleção de 29/09–05/10: renderização,
   acesso às três explorações e cinco batalhas, conclusão/volta ao menu.
2. Conferir Auracite real obtida, loja 900105, estoque, resgate, NRG e
   recompensas **antes e depois** da conclusão em save descartável.
3. Obter referência de recompensas especificamente de 2016 para remover
   qualquer primeiro-clear da reprise de 2018 sem alterar recompensas corretas.
4. Verificar limite de evento versus prazo de resgate; corrigir datas somente
   após fonte inequívoca e teste de bordas.
5. Só então repetir o mesmo procedimento nas áreas 705, 707, 709, 6193,
   721, 704, 906, além de trials e sazonais.

**Proteção de escopo:** nenhuma dessas descobertas autoriza liberar todos
os eventos de 2016, substituir originais por reprises ou alterar a RC3
aprovada sem testes de compatibilidade e um patch de diff mínimo.
