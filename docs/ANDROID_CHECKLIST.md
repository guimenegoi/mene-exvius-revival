# Checklist vivo — FFBE Revival Android independente

**Atualizado:** 2026-11-12. Este documento é a fonte de acompanhamento do fork
`mene-exvius-revival`. Só marcar `[x]` com teste verificável; prova isolada
não equivale a APK offline. Versão-alvo: FFBE Global 9.1.0 (`versionCode=9101`).
Entrega: **um único aplicativo**, sem Termux, VPN, root, Proxmox ou outro app.

## Princípios e integração de referência

- [x] Fork próprio com remotos `origin` e `upstream`.
- [x] Cliente abre no Waydroid com Revival remoto e consegue batalha/recompensas.
- [x] Backend Python Revival iniciado no Termux com dados parciais; HTTP/HTTPS e GET MST.
- [x] Transporte de API e CriFsWebInstaller em localhost:18080 com patch Java.
- [x] Prova de bootstrap **dentro do processo do FFBE**: porta 18081 de
      loopback, HTTP 200 e encerramento do listener com `force-stop`.
      Apenas diagnóstico; não há Python nem jogabilidade nesse listener.
- [ ] Testar individualmente Cocos2dxDownloader e FileDownloader em sessão jogável.
- [ ] Comprovar que todos os caminhos necessários (inclusive nativos, se houver)
      deixam de atingir endpoints externos, sem interceptar conexões de outros apps.

## P0 — APK offline autossuficiente

- [x] Implementar instalador de manifesto (19 pacotes, retomada, SHA-256,
      reserva de espaço e verificação local sem rede) em `android/data`.
- [x] Testar layout de compartilhamento nativo/servidor sem duplicações em Linux.
- [ ] Instalar/verificar os 19 pacotes **reais** no Android; confirmar os arquivos
      de tutorial, mapa, áudio e combate no armazenamento privado do cliente.
- [ ] Verificar escrita, atualização e preservação de saves no layout real ARM64.
- [ ] Empacotar runtime CPython incorporado, stdlib e dependências
      `cryptography`, `Pillow`, `PyYAML`, `tzdata` para x86_64 e ARM64.
- [ ] Integrar inicialização/desligamento do **motor Revival real** ao ciclo de
      vida do FFBE, com diagnóstico de readiness e falha segura.
- [ ] Integrar o instalador de dados ao mesmo APK (sem acesso ao armazenamento
      privado por outro app).
- [ ] Produzir APK assinado para testes com cliente, runtime e instalador
      integrados, usando patch mínimo e reprodutível.
- [ ] Passar pelo menos uma batalha, receber recompensa e persistir save com
      Wi-Fi/dados desligados e sem servidor externo; reabrir o jogo e conferir save.

## P1 — cobertura funcional e estabilidade

- [ ] World Map, exploração/encontros aleatórios, summons, inventário e quests,
      incluindo regressão de recompensas.
- [ ] Investigar incompatibilidade de `EXVIUS_WIKI_REWARDS=1`; atualmente o
      ambiente Android usa `0` como contorno provisório.
- [ ] Validar x86_64 e dispositivo Android ARM64 físico.
- [ ] Medir RAM/CPU/bateria, tela apagada, alternância de apps e reinício.
- [ ] Downloads apenas na configuração/atualização; zero dependência de rede
      durante a partida; preservação de saves em atualizações.

## P2 — entregável e pós-estabilização

- [ ] Instalação em aparelho limpo sem apps auxiliares; backup, recuperação,
      logs úteis e CI/release de build reproduzível.
- [ ] Rever direitos de redistribuição do upstream e dos recursos proprietários;
      não publicar APK original, recursos de jogo, saves ou chaves no Git.
- [ ] Retomar fidelidade histórica mais estrita (incluindo junho de 2016) só
      depois do primeiro APK offline realmente jogável.

## Registro de execução

### 2026-11-12 — bootstrap interno de laboratório

- Arquivos: `android/runtime/patch_bootstrap_probe.py`,
  `android/runtime/test_bootstrap_probe.py`, `android/runtime/README.md`.
- Testes: 4/4 unitários do bootstrap e 4/4 de transporte; compilação APKtool 3.0.3.
- Comparação do APK: somente `classes.dex` e `classes3.dex` alterados.
- Instalação Waydroid Android 13 via atualização do APK base e splits com a
  mesma assinatura; sem apagar os dados da instalação anterior.
- `Lapis.onCreate` iniciou a sonda HTTP em `127.0.0.1:18081`.
  Requisição local retornou **HTTP 200** e `FFBE-BOOTSTRAP-READY`.
- Após `am force-stop`, `ss -ltn` não mostrou listener na porta.
  `onDestroy` individualmente não foi demonstrado.
- **Status:** subetapa de infraestrutura validada. O bootstrap
  **não** é o runtime Python e **não fecha** nenhum item P0 de jogabilidade.
- **Próxima execução:** integrar CPython ao processo do jogo, preservando
  o patch mínimo do cliente e o mesmo motor de servidor do Revival.

### 2026-11-12 — recursos e transporte previamente validados

- `data/latest.json` declara 19 pacotes, cerca de 14,65 GB de download
  e 14,95 GB instalados; 22 GiB livres recomendados.
- Instalador e compartilhamento testados com arquivos sintéticos no Linux.
- A cópia parcial no Android anterior provocou 404 de arquivos de recurso.
  **Não** afirmar instalação completa no Android.

Documentação técnica: [Android](ANDROID.md),
[arquitetura de APK único](ANDROID_STANDALONE.md) e
[bootstrap de laboratório](../android/runtime/README.md).
