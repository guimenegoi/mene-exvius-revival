# FFBE Android — replay manual de 2016 (experimento, não implantado)

## Objetivo confirmado

A cronologia começa em **30/06/2016**, lançamento de FFBE Global, e não
avança com o calendário real. `EXVIUS_REPLAY_MANUAL_WEEK=0` cobre
30/06–06/07/2016, `1` cobre 07–13/07/2016, e assim por diante.
Em modo manual, banners sazonais não são injetados pela data real.
O acervo não promete banners de todas as semanas do lançamento; uma semana
vazia é preferível a mostrar unidades futuras sem fundamentação histórica.

## Projeto de migração virtual e reversão

1. **Antes:** registrar o SHA-256, schema e caminho do `state/replay.json` e
   efetuar backup externo validado do estado. Não ler/gravar saves do Samsung
   durante o desenvolvimento e não apagar `replay.json` para reiniciar.
2. **Prévia sem escrita:** comparar a janela automática atual com a proposta
   manual `EXVIUS_REPLAY_MODE=manual`, `EXVIUS_REPLAY_START=2016-06-30`,
   `EXVIUS_REPLAY_MANUAL_WEEK=0`.
3. **Configuração versionada:** o painel exige confirmação de mudança histórica,
   registra revisão e permite selecionar modo e semana. `config_model` valida
   o intervalo; o Android deve sincronizar somente com pareamento autorizado.
4. **Aplicação em cold boot:** `config_model.apply_on_boot` é chamado antes da
   importação do motor (integração **ainda não portada à APK funcional**).
   O motor usa apenas o recorte virtual e não altera a âncora, campanha nem
   estado de progresso; aplicações parciais permanecem staged.
5. **Avanço manual:** editar o número da semana, confirmar no painel, aguardar
   a sincronização e reiniciar o motor. Não realizar mudanças na sessão ativa.
6. **Reversão:** remover o override manual na configuração e reiniciar;
   preservar exatamente os bytes do `replay.json` original.

## Gates pendentes para distribuição

- [x] Testes unitários da janela congelada, avanço, validação, recusa de dados
      inválidos e retorno automático sem escrita no replay.
- [x] Testes de configuração versionada, confirmação explícita e migração
      virtual com `replay.json` sintético preservado byte a byte.
- [ ] Integrar ao bundle Android baseado na **RC3 HardlinkPermission**, sem
      substituir JNI, o bootstrap, preflight nem os patches de reconexão.
- [ ] Confirmar a configuração da revisão na APK em Waydroid com save sintético,
      primeiro/segundo boot, derrota de conexão e rollback.
- [ ] Revisar a cobertura de banners de junho–dezembro de 2016; nenhuma
      criação artificial de conteúdo adiantado.
- [ ] Fazer backup validado do save real e obter aceite para atualizar a APK.
- [ ] Verificar no Samsung o intervalo fixo, avanço manual, persistência e
      reabertura. Só depois promover a release.

**Importante:** este código não foi implantado na LXC, no painel de produção,
no Samsung nem na APK existente. Branch experimental isolada.
