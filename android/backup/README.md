# FFBE Revival — backup privado do save e sincronização de configurações

## Estado verificado em 13/11/2026

**Implementado e validado no APK experimental** `FFBE-ConfigSync-LAB-aligned-debugSigned.apk`:
- Samsung pareado por ADB USB com token privado e certificado TLS fixado; pareamento persistido no aplicativo.
- Primeiro backup real recebido em `ffbe-server` (LXC 120) em 2026-11-13T17:09:32Z.
- Arquivo ZIP: `20261113T170932Z-176f08dc07b2-fa7d79.zip`, 119.257 bytes.
- Arquivos: `state/campaign.json`, `state/replay.json` e `manifest.json`.
- SHA-256 do ZIP confirmado no Samsung e no ZFS:
  `176f08dc07b23d61cb69e34a1581b5d686c9005f856bfdae83acb0a5e5f47af8`.
- Verificação de integridade ZIP/CRC: OK.
- Sincronização de configuração: `up_to_date`, sem `last_error` ao final do teste.
- Receptor TLS corrigido contra bloqueio na aceitação de conexões; teste com cliente TCP silencioso e outra conexão TLS respondeu HTTP 401 em 0,03 s.

**Não validados:** restauração do save, segundo backup após modificação do progresso, aplicação de configuração alterada no painel após reiniciar o jogo, e backup com aplicativo fechado. A confirmação de `up_to_date` foi feita sem alterações remotas de configuração.

**Separação de canais:** o APK estável, `FFBE-Revival-Android-ARM64-stable-20261113.apk`, é a baseline de gameplay validada; **não** contém o cliente experimental de backup/configuração. Não atribuir a ele as funções testadas no APK LAB.

## Servidor

- Host: `ffbe-server` (LXC 120), IP LAN `192.168.15.230`.
- Serviço HTTPS: `ffbe-save-backup.service`, porta 18447, usuário `ffbe-backup`.
- Código instalado fora do worktree Git: `/usr/local/libexec/ffbe-backup/lxc_backup.py`.
- Dados persistentes em mount ZFS dedicado: `/var/lib/ffbe-save-backups`, sem fallback para disco do sistema.
- Token, chave privada e certificado em `/etc/ffbe-backup/`: **nunca** versionar, publicar ou copiar para APK.
- Endpoint privado: `https://proxmox.tailcf6a16.ts.net:18447` (Tailscale TCP proxy para LAN).
- Painel HTTPS: `https://192.168.15.230:18448/`, serviço `ffbe-settings-web.service`.
- A API exige token Bearer, evita redirecionamento de credenciais, restringe o formato ZIP, impede symlinks e limita payloads a 20 MiB; mantém até 30 snapshots por dispositivo.
- A LXC possui configuração DNS com AdGuard `192.168.15.208` e fallback `1.1.1.1` / `8.8.8.8`.

## Cliente Android

- `android/backup/embedded_client.py` é empacotado como `ffbe_backup.py`; o transporte TLS é `ffbe_backup_transport.py`.
- `android/runtime/local_http.py` inicia o worker depois da inicialização real do servidor do jogo em `127.0.0.1:18080`.
- Sem pareamento, o worker não lê nem transmite o save. Com pareamento, verifica alterações do estado privado a cada 20 segundos **enquanto o jogo estiver aberto**.
- Envia arquivos JSON contendo `campaign.json`, confere recibo SHA-256, faz retry mínimo de 120 segundos.
- Configurações são sincronizadas separadamente dos saves, com revisão/CAS e validação de esquema. Mudanças recebidas podem exigir reinício do jogo.
- O processo de inicialização completa do jogo no Samsung pode levar vários minutos; evitar `force-stop` durante diagnósticos.

## Pareamento / diagnóstico

- Script privado no desktop: `~/.local/share/ffbe-revival-test/parear-samsung.py`.
- Prefere ADB USB. No Linux, pode ser necessário desmontar a sessão MTP para liberar a interface ADB, sem excluir dados.
- O script compara a impressão SHA-256 do certificado, obtém o código temporário via `logcat` e solicita o token **somente no terminal local**.
- Para estado, consultar via túnel ADB: `GET /__exvius/backup/status` e `GET /__exvius/config/status`.
- Não repetir pareamento quando `configured: true`; não registrar códigos temporários nem tokens nos logs ou neste documento.

## Testes de código

```bash
python3 -m unittest discover -s android/backup -p 'test_*.py' -q
python3 -m unittest discover -s android/runtime -p 'test_*.py' -q
```

**Próximas validações:** backup após alterar o save, configuração editada no painel e aplicada após reinício, acesso fora da LAN, restauração controlada com cópia anterior e verificação de hash. Não publicar APKs ou dados proprietários.
