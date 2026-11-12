# Auditoria de integração Android — 12/11/2026

## Decisão de escopo

**O motor e a progressão histórica do Revival são a base.** Não criar nova
cronologia, reimplementar gameplay ou substituir o backend pelo
`LocalGameBridge` oficial. O cliente FFBE 9.1.0 + instalador upstream
v0.1.30 constituem apenas a adaptação Android. Prioridade: título, tela
principal, batalha, recompensa, save e reabertura **sem internet**.

## Estado confirmado por evidência

| Área | Prova | Estado |
| --- | --- | --- |
| 19 ZIPs de recursos | 14.647.871.919 bytes com SHA-256 no LXC 117 | Preservados |
| Instalação Android | 19 recibos verificados pelo preflight, assets e tabelas | Concluída no Waydroid |
| Runtime | CPython 3.14 ARM64, criptografia, AES, imports Revival | Confirmado |
| Servidor | `FFBE-RevivalHTTP READY 127.0.0.1:18080` e HTTP 200 hello | Confirmado |
| Ponte FFBE → Revival | Inicialização e GetUserInfo atendidos pelo servidor real | Confirmado |
| Launcher | Sem atualização pendente; após corrigir o sentinela abriu `Lapis` normalmente | Confirmado |
| Título | FFBE original exibido; TAP TO START processado | Confirmado |
| Download complementar | Respostas CDN 200 para vários recursos, 404 para um MST | **Bloqueado** |
| Tela principal, batalha, save | Ainda não alcançados/testados | **Pendente** |
| Celular ARM64, modo avião | Ainda não testados | **Pendente** |

O cliente usou o servidor do próprio processo. O cache HTTP em
`127.0.0.1:18082`, SSH e `adb reverse` foram **exclusivamente** para
alimentar a primeira instalação no Waydroid; não são dependências de jogo.

## Diagnóstico objetivo: instalador

`DataUpdates.ready()` upstream tinha cinco critérios. A instrumentação do
Waydroid mostrou: pending=false, recibos=true, client-assets=true,
F_UNIT_MST=true e o sentinela de arquivo
`mst/Ver9001_YW9MUm2H.dat`=false. Essa versão **não faz parte** do
manifesto revisão 9. A correção mínima troca somente essa última checagem
por **existência do diretório nativo `mst/`**. O manifesto de 19 pacotes,
os recibos, o SHA-256 do cliente e o preflight do servidor continuam
obrigatórios. Um APK reconstruído com esse ajuste passou diretamente
da Activity de instalação para `Lapis`, com servidor real pronto.

## Diagnóstico objetivo: download complementar

Após TAP TO START, `InitializeRequest`, `GetUserInfoRequest` e
outros endpoints foram respondidos pelo Revival. A resposta Android
anunciou 364 versões nativas, evitando os aumentos exclusivos do iOS.

O cliente então solicitou arquivos via `CriFsWebInstaller`.
`Ver611_Fvix6V0n.dat`, `Ver404_7FGj2bCh.dat` e outros receberam
HTTP 200 (inclusive por fallback de token). Porém:

```text
GET /mst/Ver595_oB0YVw67.dat?v=0 -> 404 (not in the CDN root)
```

**Não é arquivo inexistente na distribuição:** `data-010.zip`, fixado
pelo manifesto original e preservado no LXC, contém
`native/mst/Ver595_oB0YVw67.dat` (**221.776 bytes**), além das
versões 593 e 594. `gamedata.xml` vincula versão 595 a
`F_BANNER_MST`. A tela do cliente mostrou "Unable to load local game
data". Não criar uma resposta fictícia nem mudar o número da versão
para esconder a falha.

Causa ainda não fechada: comparar o layout extraído no armazenamento
privado do Android e `State.cdn_root` do servidor. `run-as` é
inoperante no Waydroid atual (`setegid(AID_PACKAGE_INFO) failed`), mesmo
na variante com `debuggable=true`. Essa variante foi **restaurada** por
`adb install-multiple -r`, sem desinstalar/limpar dados. Até haver prova,
não afirmar que o arquivo foi apagado ou que há defeito em `DataPack`.

## Higienização e limites

1. **Motor Revival:** manter o backend existente. O perfil condicional
   `FFBE_ANDROID_EMBEDDED` desativa apenas a transformação de tabelas
   iOS e usa versões nativas; fora do Android, manter comportamento iOS.
2. **Instalador:** reutilizar `DataUpdates`, `DataPack` e
   `GameAssets`. Não criar segundo instalador nem duplicar os ZIPs.
3. **Readiness:** reaproveitar o endpoint real `/__exvius/hello` e
   `LocalPythonProbe`, nunca um listener artificial ou sucesso simulado.
4. **Laboratório:** `local_cache_server.py` e
   `build_local_install_lab.py` são ferramentas privadas, vinculadas
   a hashes e `adb reverse`. Não distribuir APK de laboratório com
   `127.0.0.1:18082`.
5. **Controle de mudanças:** separar commits funcionais e de
   documentação/ferramentas; manter APKs proprietários, ZIPs, saves e
   chaves fora do Git. Guardar diff anterior em
   `/tmp/ffbe-audit-precleanup-20261112.patch` no desktop.
6. **Waydroid:** houve um SIGSEGV anterior em libhoudini/ART ao abrir
   diretamente `Lapis`. A última passagem via launcher não o repetiu,
   mas a validação ARM64 física ainda é necessária.

## Próxima execução, sem novos patches especulativos

- [ ] Demonstrar, no próprio processo Android, a existência/ausência
      de `files/mst/Ver595_oB0YVw67.dat` e o destino real do symlink
      `exvius/data/native/mst`; confirmar se o CDN olha o mesmo local.
- [ ] Se ausente, revalidar **apenas** a extração de `data-010.zip`
      com o mecanismo `DataPack`, sem apagar recibos ou saves às cegas.
      Se presente, corrigir o mapeamento do `CDN_ROOT`.
- [ ] Testar download complementar até a tela inicial, uma batalha,
      recompensa, save, reinício e modo avião.
- [ ] Gerar APK de teste **sem túnel de laboratório**, checar assinatura,
      SHA-256, diff dos DEX e instalar em Android ARM64 real.

**Não marcar o projeto como release jogável antes dessas provas.**
