# FFBE Revival — estado e plano de trabalho

**Atualizado:** 13/11/2026  
**Fonte de verdade:** repositório `guimenegoi/mene-exvius-revival` e artefatos privados no ZFS do Proxmox.  
**Regra:** não misturar baseline estável, experimentos Android, integração upstream e pesquisa histórica na mesma release.

## Concluído / confirmado

- Gameplay Android ARM64 (Samsung SM-S942B): 19 pacotes verificados, HTTP Revival local `READY`, Home, Summon e batalha validados.
- Baseline estável privado: `/srv/ffbe-distribution/releases/FFBE-Revival-Android-ARM64-stable-20261113.apk`; SHA-256 `2f2bd6e47616cc51031ebcac26d3f175c22816af6883d18270303c8195d79a5e`. Link com nome antigo mantido para compatibilidade.
- Experimento de backup/configuração: `/srv/ffbe-distribution/build-cache/config-sync-signed/FFBE-ConfigSync-LAB-aligned-debugSigned.apk`; **não é a release estável**.
- Receptor HTTPS na LXC 120: TLS protegido contra clientes com handshake incompleto, serviços de backup e configurações ativos, ZFS obrigatório para escrita.
- Primeiro backup real do Samsung recebido em 13/11/2026 às 17:09:32 UTC, ZIP 119.257 bytes, `campaign.json` + `replay.json`, hash e CRC conferidos.
- Configuração no Android: estado `up_to_date`, sem erro após recuperação de tentativas de rede.
- Organização de arquivos: originais Android privados arquivados no ZFS com manifesto de 10 hashes SHA-256 conferidos; APKs duplicados removidos do desktop; builds rejeitados e intermediários descartados; recursos dos 19 pacotes e saves preservados.

## P0 — Segurança do save e validação funcional

| Ação | Pronto quando |
|---|---|
| **Restauração controlada** | Núcleo offline testado; guarda de recuperação pré-motor e empacotamento opt-in implementados em LAB; faltam UI Android, controle do ciclo de vida para restauração solicitada, teste em aparelho e aprovação do save real |
| **Segundo backup real** | Após alterar o progresso, surge outro snapshot no ZFS; manifesto, integridade, SHA-256 e versão do save conferidos |
| **Aplicação de configuração remota** | Uma alteração reversível feita no painel é recebida como `pending_restart`, aplicada no próximo início e confirmada no jogo; depois é revertida |
| **Conectividade externa e retries** | Backup/configuração testados fora da LAN via Tailscale; falha transitória não corrompe save e retry se recupera |
| **Política de execução** | Comportamento quando jogo fecha/volta é documentado; não declarar backup contínuo em segundo plano sem implementar e comprovar |

**Restrição:** não reinstalar ou limpar os dados do Samsung para testar restauração. Sempre preservar snapshot validado e confirmar antes de sobrescrever o save.

## P1 — Produto Android e distribuição

| Ação | Pronto quando |
|---|---|
| **Reduzir inicialização lenta** | Identificar custo de verificação dos 19 pacotes, extração/instalação do motor e tempo até `READY`; corrigir sem perder verificações de integridade |
| **Empacotamento reproduzível na LXC 120** | Um script produz APK assinado consistente, com todo o inventário na mesma revisão, testes e certificado conferido |
| **Teste de instalação limpa e offline** | Nova instalação em ambiente isolado, primeira carga, título, Home, batalha e persistência testados sem depender do servidor externo depois dos recursos |
| **Promoção de release** | Versão com backup/configurações só recebe nome estável após P0; preservar baseline e rollback testáveis |
| **Higiene operacional** | Retenção de caches, worktrees e logs documentada; não alterar LXC 111 ou storage crítico durante testes do FFBE |

## P2 — Fidelidade histórica (branch de pesquisa independente)

- Consolidar cronologia de lançamento Global, com **datas de início** como regra para banners, eventos, lojas, itens e awakenings; conteúdos antigos permanecem acessíveis no arquivo.
- Definir snapshots de experiência histórica, começando por junho de 2016, usando referências da UI original; distinguir limitações do cliente 9.1.0 das alterações de servidor.
- Auditar Home, Arena, Coliseum, Vortex, lojas e summons (incluindo botão Vision Card e recursos posteriores ao período). Separar bundles da loja paga das lojas de cidades.
- Produzir APK de investigação separado; não alterar a baseline estável até haver matriz de testes visuais e funcionais.

## P3 — Consolidação e manutenção

- Revisar merge do upstream sem sobrescrever correções Android e sem misturar dados de snapshots.
- Documentar instalação, upgrade sem limpeza de dados, backup, restauração, rollback e testes de regressão.
- Publicar **apenas código autorizado** no GitHub; manter APKs, recursos proprietários, saves, certificados privados e tokens exclusivamente nos armazenamentos privados.
- Revisar os worktrees Git e eliminar apenas branches/instalações comprovadamente obsoletas, após confirmar remotes e referências ativas.

## Topologia atual e proteção

- `ffbe-server`: LXC 120, endereço LAN `192.168.15.230`; API backup TLS porta 18447; painel HTTPS porta 18448.
- `/srv/ffbe-distribution/releases/`: APK estável e rollback (distribuição Tailscale).
- `/srv/ffbe-distribution/build-cache/config-sync-signed/`: APK experimental atual; worktrees mantidos no cache de desenvolvimento.
- `/srv/ffbe-distribution/archive/original-android-client-20261113/`: APKs e XAPK originais, splits e client assets privados com `ORIGINALS-SHA256SUMS-20261113.txt`.
- `/var/lib/ffbe-save-backups/`: ZFS dedicado para snapshots, mount obrigatório e acesso restrito.
- Desktop: repositórios e ferramentas de desenvolvimento, Waydroid, ADB e script de pareamento; **sem cópias duplicadas dos APKs de distribuição e dos originais arquivados**.
- Regra de segurança: nenhuma rotina de limpeza toca recursos de runtime, ZFS do save, instalações Git ativas, chaves ou certificados sem inventário e validação prévios.

**Próxima sessão recomendada:** começar pelo teste de alteração de configuração/reinício e pelo segundo snapshot; depois implementar a restauração de forma transacional. Atualizar este documento após cada marco.
