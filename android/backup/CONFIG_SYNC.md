# FFBE Revival — configuração persistente sincronizável (protótipo)

**Escopo:** somente a branch `feature/config-sync-model`. Não é a release
Android aprovada; a instalação estável e os saves reais não são modificados.

## Arquitetura

- O motor do FFBE continua embarcado no APK e não precisa do Proxmox.
- O Android guarda o último documento aprovado em
  `getFilesDir()/ffbe_python/private-config/server-config.json`.
- Alterações remotas entram em `staged-config.json`; **não alteram
  um servidor já em execução**.
- Na próxima inicialização, `android/runtime/local_http.py` carrega o
  documento ANTES da importação de `serve` e `capture_server`.
- `campaign.json` e `replay.json` **nunca** são sobrescritos pelo sync.
- Sem documento ou sem conexão, o motor usa os valores existentes.
- A LXC 120 guarda configurações em
  `/var/lib/ffbe-save-backups/configs/<device>.json` e revisões anteriores
  em `config-history/<device>/` (o mesmo ZFS externo, não o disco interno).
- Receptor HTTPS em `proxmox.tailcf6a16.ts.net:18447`, no Tailscale.
  GET e PUT `/v1/configs/<device>` exigem o Bearer já usado pelo
  backup; o conteúdo tem hash SHA-256 e revisão.
- A operação PUT exige `If-Match` e rejeita divergência com HTTP 409.
  A revisão `0` representa ausência de documento remoto.
- O cliente usa o último ancestral comum para distinguir edição remota,
  edição local e conflito; **nunca** sobrescreve alterações simultâneas.
- O cliente só sincroniza depois do pareamento HTTPS existente e a cada
  dois minutos, quando o jogo estiver aberto. Funciona offline.

## Esquema v1

Documento: `{"schema":1,"settings":{"EXVIUS_REPLAY_START":"2016-12-16"}}`.

Somente variáveis estritamente permitidas podem ser alteradas:
- Replay: `EXVIUS_REPLAY`, `EXVIUS_REPLAY_START`,
  `EXVIUS_REPLAY_PACE`, `EXVIUS_REPLAY_FULL_RUNS`,
  `EXVIUS_REPLAY_NOTICES`, `EXVIUS_REPLAY_MARQUEE`,
  `EXVIUS_REPLAY_NOTICE_WEEKS`.
- Eventos/summons: `EXVIUS_EVENT_ARCHIVE`, `EXVIUS_SUMMON_ARCHIVE`,
  `MARQUEE_FLAG`.
- Economia e Trust: `EXVIUS_LAPIS_MULTIPLIER`,
  `EXVIUS_DAILY_QUEST_LAPIS`, `EXVIUS_QUEST_TRUST`,
  `EXVIUS_QUEST_TRUST_CHANCE`, `EXVIUS_QUEST_TRUST_POINTS`,
  `EXVIUS_QUEST_TRUST_BIG_CHANCE`,
  `EXVIUS_QUEST_TRUST_BIG_POINTS`.

Booleanos são `true/false`, números têm limites e datas históricas são
restritas a 30/06/2016–30/10/2024. Nada de variáveis arbitrárias,
comandos, caminhos, segredos ou conteúdo do save.

### Migração de cronologia

A âncora histórica existente em `state/replay.json` é protegida:
- Alterar `EXVIUS_REPLAY_START` para data divergente da âncora é
  **recusado** até existir procedimento explícito de migração.
- Alterar `EXVIUS_REPLAY_PACE` quando já existe âncora histórica
  também exige migração. A revisão divergente permanece staged.
- `campaign.json` é preservado. **Jamais apagar replay.json
  automaticamente.**

## Operações na LXC (sem acesso ao token)

Com o usuário `ffbe-backup` e os scripts instalados em
`/usr/local/libexec/ffbe-backup`:

```bash
python3 /usr/local/libexec/ffbe-backup/configctl.py --device samsung-android show
python3 /usr/local/libexec/ffbe-backup/configctl.py --device samsung-android set EXVIUS_REPLAY_NOTICES true
python3 /usr/local/libexec/ffbe-backup/configctl.py --device samsung-android set EXVIUS_REPLAY_PACE '3,2@2020-08-20'
```

Um comando `set` persiste a revisão no ZFS e **não modifica**
a campanha Android imediatamente. Se o aparelho estiver pareado, poderá
buscar a revisão e aplicá-la apenas no próximo arranque, sujeito às
proteções históricas. Este protótipo não tem ainda uma interface gráfica.

## Estado e limites atuais

- Receptor de backup pré-existente permanece separado em
  `/v1/backups/<device>`.
- Ainda falta testar num APK real desta branch, atualizar e parear o
  telefone sem expor credenciais, validar troca de configuração via
  Tailscale e demonstrar que a campanha permanece intacta.
- Não declarar sync operacional no Android antes de prova de ponta a ponta.
- A revisão de configuração **não inclui** o binário do APK, plugins,
  saves nem o estado transitório da partida.
- Por enquanto o Bearer é compartilhado entre backup e configuração.
  Escopos separados por capacidade e uma UI de aprovação de migração
  são melhorias posteriores.
