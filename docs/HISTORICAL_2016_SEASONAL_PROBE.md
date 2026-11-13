# FFBE Global — experimento histórico pré-dezembro de 2016

Data: 13/11/2026. Branch: feature/historical-2016-seasonal.

## Proposta

Candidato: **2016-11-11**, em lugar de 2016-12-16 (âncora atual do Samsung).
Em 11/11/2016 começou a edição Global de Grand Gaia Chronicles (Brave
Frontier), até 24/11/2016. Trial of the Creator começou em 18/11/2016.

Referências:
- https://novacrystallis.com/2016/11/final-fantasy-brave-exvius-adds-brave-frontier-crossover-event-pvp-mode/
- https://www.reddit.com/r/FFBraveExvius/comments/5cdfih/global_event_megathread_grand_gaia_chronicles/
- https://finalfantasy.fandom.com/wiki/Event_%28Brave_Exvius%29

## Lacuna corrigida no catálogo

O event_archive.json tinha Grand Gaia Chronicles apenas em 2017-06-16.
Foi acrescentada a primeira passagem Global 2016-11-11 em event_history.json
**somente para a área 720**, a qual apareceu no Vortex durante o smoke test.
A área 913 permaneceu em 2017: não comprovamos que a variante 913 existia
na primeira execução de 2016. Trial of the Creator (área 721, 2016-11-18)
já estava corretamente registrado e também apareceu no teste.

Isso demonstra que os eventos são listados; não confirma todas as batalhas,
recompensas nem fidelidade visual de 2016.

## Proteção de conteúdo sazonal

A progressão histórica usa EXVIUS_REPLAY_START, mas os feriados são acionados
pelo calendário REAL em gacha_rotation.HOLIDAYS e event_archive.HOLIDAY_EVENTS.
SEASON é outro mecanismo, independente, para temporadas autorais.

NÃO alteramos EXVIUS_ROTATION_HOLIDAYS, SEASON, EXVIUS_EVENT_ARCHIVE,
EXVIUS_SUMMON_ARCHIVE, EXVIUS_REPLAY_PACE nem as regras de calendário.

Teste comparativo de replay com 1.324 banners, ritmo padrão e estado
sintético, em dados MST/locale reais de leitura do ZFS:

- Início padrão em 16/12/2016: janela histórica de 16/12 a 05/01/2017;
  sem Grand Gaia ou Trial of the Creator nessa primeira janela.
- Início proposto em 11/11/2016: janela de 11/11 a 01/12/2016;
  Grand Gaia no Vortex (área 720), Trial of the Creator (área 721).
- Natal real de 2026: os mesmos banners sazonais de 2017-12-22
  e 2017-12-29 nas duas âncoras.
- Halloween real de 2027: os mesmos banners sazonais de 2018-10-19,
  2019-10-24 e 2019-10-28 e as mesmas quatro áreas de Vortex:
  919, 921, 983 e 986.
- Na semana simulada de 13/11/2026, nenhuma seleção de banner sazonal
  foi indevidamente aberta fora do feriado.

**Limitação pré-existente:** no Natal real de 2026, o Vortex retornou
zero áreas sazonais de Natal tanto na âncora padrão quanto na nova.
Banners de Natal estavam presentes. Isso NÃO é regressão provocada
pelo novo início histórico, mas precisa ser auditado antes de declarar
os sazonais completos.

Reexecutar a prova com:

    python3 ios-server/devtools/verify_2016_history_seasonal.py \
      --mst-dir /srv/ffbe-distribution/runtime-data/static/mst_decoded \
      --text-dir /srv/ffbe-distribution/runtime-data/static/text_decoded

O script falha se os eventos de 2016 não aparecerem, se mudarem as datas
dos banners sazonais ou se áreas de Halloween sumirem.

## Por que não enviar EXVIUS_REPLAY_START imediatamente

Os dois ZIPs reais arquivados do Samsung contêm replay.json ancorado em
2016-12-16, anchor_week=44. Não há configuração remota persistida.
O cliente recebe uma data diferente pelo HTTPS mas recusa aplicá-la
ao save existente sem migração explícita; ela ficaria apenas pendente.

Não apagamos ou alteramos replay.json, campaign.json, backups, settings nem
o APK do telefone. Não houve envio de configuração ao Samsung.

## Próximo passo de implementação

- Implementar migração transacional e explicitamente confirmada da âncora
  de replay, antes de iniciar o motor, com pré-backup verificável e rollback.
- Jamais modificar campaign.json, apagar replay.json automaticamente ou
  alterar a lógica de calendário sazonal ao migrar o início histórico.
- Testar migração e rollback com arquivos sintéticos, depois no Android
  de laboratório. Validar ausência de regressão dos sazonais e confirmar
  no telefone antes de efetivar uma migração real.
- Auditar separadamente o problema preexistente do Vortex de Natal.

Estado: **replay de 11/11/2016 validado em simulação; aplicação real
no Samsung pendente de migração segura do replay**.
