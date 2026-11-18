# Encerramento do FFBE Revival — 19/11/2026

## Decisão

Desenvolvimento e distribuição próprios descontinuados por sobreposição com
[FFBE-Forever](https://gitlab.com/clbng28/ffbe-forever/-/releases), que possui
progressão cronológica, Vortex, Orbonne/FFT e atualizações próprias. Essa
preferência não declara que o Forever esteja completo ou que os saves sejam
compatíveis. Nenhuma transferência de código, saves ou credenciais ocorreu.

## Estado congelado

- A RC3 de campo instalava e iniciou no Samsung, mas a exibição de FFT
  (semana histórica 2016-09-29–2016-10-05) não foi confirmada; o diagnóstico
  local do aplicativo retornou `up_to_date`, `paired=true`, `has_pending=false`.
- A RC3 Events2016 incorpora a correção do calendário de Orbonne e Dread Frost.
  A primeira candidata não instalava por alinhamento incorreto das bibliotecas;
  a candidata PageAligned passou verificação estática, mas não foi testada
  no dispositivo.
- Relatórios históricos: `docs/audits/FFBE_GLOBAL_2016_EVENT_RECOVERY_2026-11-18.md`
  e `docs/audits/FFBE_2016_EVENTS_RC3_CANDIDATE_2026-11-18.md`.
- O código em `main` foi consolidado com a branch de correções finais e a
  documentação do ramo principal existente antes de arquivar.

## Recuperação privada (sem arquivos proprietários no Git)

- LXC Proxmox **CT 120 `ffbe-server`**: rootfs recuperável via backup
  `vzdump-lxc-120-*.tar.zst` no armazenamento de manutenção;
  backup verificado com `zstd -t` antes do desligamento.
- Dados volumosos e instaladores: montagem ZFS externa
  `/storage-media/dev-projects/ffbe-revival-distribution`; arquivos de
  saves em `save-backups/` e dados do runtime mantidos com permissões
  privadas. A política original está em `STORAGE_LAYOUT.md` desse diretório.
- APK RC3 e candidata PageAligned, manifestos e originais preservados no
  diretório externo privado `releases/`/`archive/`; nunca anexados ao GitHub.
- Serviços `ffbe-settings-web`, `ffbe-save-backup` e respectivo Tailscale
  Serve são exclusivos deste projeto, desligados no arquivamento.
- A CT 120 deve permanecer desligada, sem `onboot`, até reativação explícita.
  Os timers de backup próprios do FFBE são desabilitados após o backup final.

## Se o projeto precisar ser recuperado

1. Desarquivar o repositório no GitHub apenas se houver intenção explícita
   de retomar desenvolvimento; histórico de commits, branches e tags retido.
2. Verificar existência e integridade do backup da CT 120 e os dois mounts
   `mp0` e `mp1` antes de iniciar a LXC.
3. Conferir certificados privados, arquivos de configuração e saves no
   Proxmox; nunca incluí-los em commits ou anexos públicos.
4. Revalidar o serviço local e as versões Android antes de usar qualquer
   APK ou sincronização histórica. Não importar saves no FFBE-Forever sem
   backup e prova de compatibilidade.

**Motivo do arquivamento:** redução de manutenção duplicada, não conclusão
integral da recuperação histórica.
