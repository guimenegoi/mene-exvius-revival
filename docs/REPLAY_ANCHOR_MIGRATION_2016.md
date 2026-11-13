# Migração de âncora histórica — 16/12/2016 → 11/11/2016

**Marco de 13/11/2026. Branch experimental: feature/replay-2016-migration.**

Objetivo: testar o calendário Global da colaboração Brave Frontier sem perder
o progresso atual nem mudar as temporadas e os feriados.

## Situação

O Samsung tem dois backups reais íntegros, cujo replay.json informa
anchor_week=44 e start=2016-12-16. No servidor, ainda NÃO há uma revisão
remota de settings persistida para o dispositivo. A alteração direta de
EXVIUS_REPLAY_START para 2016-11-11 é recusada pelo cliente atual,
por proteção à âncora de replay. Não enviar o setting esperando que
seja aplicado automaticamente.

Foi implementado um módulo de pré-validação em
android/backup/replay_anchor_migration.py:

- Exige replay.json ancorado em 2016-12-16, com anchor_week válido e
  esquema conhecido, e arquivo campaign.json válido.
- Exige staged-config.json privado já recebido e validado, contendo
  EXVIUS_REPLAY_START=2016-11-11.
- Rejeita mudanças concomitantes no ritmo histórico, no arquivo de
  eventos, em summons, no marquee ou em qualquer outro setting.
- Verifica que o setting ativo corresponde à âncora antiga.
- Cria um **snapshot candidato só em memória**, alterando apenas
  replay.json. O snapshot não substitui arquivo do jogo nem é enfileirado.
- Revalida o ZIP e os hashes e confere que campaign.json é byte a byte
  idêntico e que anchor_week não foi alterado.
- Expõe identificador SHA-256 e uma frase de confirmação específica
  para eventual interface de migração, que ainda NÃO está implementada.

**O módulo é um planejador somente de leitura, não um executor.**
A fila genérica de restauração não pode receber um snapshot migrado
sem verificar os settings no instante exato da aplicação; por isso
não foi ligada à migração.

## Validações com dados sintéticos

14 testes específicos aprovados. O teste de integração usa apenas
TemporaryDirectory para simular a passagem:
snapshot original → snapshot candidato → restore_offline com pre-backup
e diário → apply_on_boot da revisão histórica pendente.

Há também teste de erro de escrita, comprovando rollback do save
simulado e manutenção do setting em staged, sem aplicação parcial.

Comandos:

    python3 -m unittest discover -s android/backup -p 'test_replay_anchor_migration.py' -v
    python3 -m unittest discover -s android/backup -p 'test_*.py' -q
    python3 -m unittest discover -s android/runtime -p 'test_*.py' -q
    python3 ios-server/devtools/verify_2016_history_seasonal.py \
      --mst-dir /srv/ffbe-distribution/runtime-data/static/mst_decoded \
      --text-dir /srv/ffbe-distribution/runtime-data/static/text_decoded

O teste sazonal compara datas de banners de Natal e Halloween e áreas
de Halloween usando um estado temporário e catálogos da LXC.

## Ressalva sazonal

A simulação de Natal de 2026 selecionou banners históricos de Natal
de 2017, mas não há áreas natalinas listadas no Vortex em nenhuma das
duas âncoras. O catálogo de Vortex dispõe de lançamentos natalinos
registrados em 2016, 2018, 2019, 2020, 2021 e 2022, sem entrada
natalina de 2017. Portanto o vazio é uma lacuna de cobertura do acervo,
não evidência de que a migração quebrou o calendário. Não inventar
uma repetição de evento de 2017 sem registro de primeira fonte.

## Para liberar a migração em aparelho

1. Desenvolver um protocolo de pedido de **migração**, separado da
   fila genérica de restore, com confirmação explícita e revisão dos
   settings fixada no pedido.
2. No cold start: bloquear o motor, verificar a mesma revisão staged,
   revalidar o arquivo de replay e o hash do save, criar pre-backup
   durável, registrar journal e executar a troca com rollback.
3. Após aplicar replay, promover o setting de forma controlada.
   Crashes antes da conclusão devem recuperar replay/config juntos
   ou bloquear o boot até a recuperação; não deixar histórico e
   configuração incompatíveis.
4. Fazer testes de falha entre etapas, startup real, feriados,
   Vortex/summons e continuidade da campanha em APK isolado.
5. Somente então executar no Samsung, mediante confirmação explícita,
   sem limpar dados nem desinstalar o aplicativo.

Nenhuma modificação foi realizada nos backups reais, no APK estável,
no experimental instalado ou na configuração privada do Samsung.
