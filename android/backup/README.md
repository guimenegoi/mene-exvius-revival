# FFBE Revival: backup do save (experimental)

## Status
- O receptor HTTPS ja esta implantado na LXC 120 e inicia com systemd.
- O APK estavel android-tested-2026-11-13 continua intocado.
- O cliente Android nesta branch nao foi instalado no Samsung e nao fez backup real.
- Nao ha restauracao implementada nem validada.

## Servidor
- Unit: ffbe-save-backup.service; usuario: ffbe-backup.
- Execucao remodelada: /usr/local/libexec/ffbe-backup/lxc_backup.py, fora dos worktrees Git.
- A unit exige RequiresMountsFor e ExecStartPre mountpoint -q /var/lib/ffbe-save-backups, impedindo gravação silenciosa no disco interno se o ZFS nao montar.
- Dados: /var/lib/ffbe-save-backups (ZFS dedicado, diretorio 0700; arquivos 0600).
- Credenciais e TLS: /etc/ffbe-backup/ (fora de Git e da distribuicao de APK).
- Endereco Tailscale privado com TLS direto: https://proxmox.tailcf6a16.ts.net:18447
- O certificado da LXC possui SAN para proxmox.tailcf6a16.ts.net e 192.168.15.230.
- Endpoint autenticado: POST e GET /v1/backups/<device>.
- Rejeita requests sem token, redirects, ZIPs malformados, symlinks e payloads >20 MiB.
- Limite de 30 snapshots por aparelho; sem endpoint de exclusao/restauracao.

## Cliente (somente experimental)
- android/backup/embedded_client.py vira ffbe_backup.py no Python embarcado.
- android/backup/lxc_backup.py vira ffbe_backup_transport.py.
- O adaptador android/runtime/local_http.py inicia um worker isolado apos o jogo carregar.
- SEM pareamento, nao le e nao transmite saves.
- COM pareamento, verifica saves JSON a cada 20 segundos quando o jogo estiver aberto.
- A origem e o state privado exvius/server-root/state e inclui obrigatoriamente campaign.json.
- Envio HTTPS com certificado CA fixado, token privado, recibo SHA-256 e retry minimo de 120 s.
- A thread nao bloqueia respostas de combate, summon ou recursos.
- Isso NAO equivale a backup periodico com o aplicativo fechado.

## Pareamento futuro pelo ADB
1. Iniciar o APK experimental e obter codigo temporario FFBE-BACKUP-PAIR no logcat.
2. Usando SOMENTE o tunel ADB e 127.0.0.1:18080, POST /__exvius/backup/pair.
3. Cabecalho X-FFBE-Pair-Code com codigo de 10 min/ate 6 tentativas.
4. JSON contem endpoint https://proxmox.tailcf6a16.ts.net:18447, token privado,
   identificador do aparelho e certificado publico ca_pem.
5. Config fica em arquivos privados do APK (0600), nunca embutida no APK distribuido.
6. GET /__exvius/backup/status exibe apenas estado, sem tokens ou endpoints.
7. Pareamento e backup real ainda NAO foram executados.

## Testes
python3 -m unittest discover -s android/backup -p 'test_*.py' -q
python3 -m unittest discover -s android/runtime -p 'test_*.py' -q

Reempacotamento sem misturar revisoes:
python3 android/distribution/repack_next_rc.py --repo <repo> --base <merged.apk> --out <unsigned.apk> --experimental-backup

Assinar com a chave debug original (uber-apk-signer 1.3.0).
Nao instalar sobre o Samsung ate concluir testes de empacotamento e restauracao.

## Pendencias
- Pareamento opt-in real (sem exibir credenciais nos logs/comandos).
- Backup real com hash confirmado na LXC; teste de save novo e reinicio.
- Restauracao independente com o jogo fechado, pre-backup, confirmacao e hash.
- Revisao de seguranca, expiracao de certificado e teste via Tailscale fora da LAN.

## Auditoria da remodelacao de LXC 120 (2026-11-13)
- IP 192.168.15.230, LXC unprivileged e onboot preservados.
- mp0 e mp1 presentes; ZFS com cerca de 2,6 TB livres; rootfs interno 10% utilizado.
- Receptor ativo e habilitado; fonte implantada tem o mesmo SHA-256 do codigo testado em android/backup/lxc_backup.py.
- Escrita real de ZIP sintetico pelo usuario ffbe-backup no ZFS: permissao 0600, integridade SHA-256 verificada e fixture apagada.
- Suite de 31 testes de backup aprovada; sem snapshots de save real registrados.
- O Samsung alcancou o Proxmox atraves da VPN Tailscale, mas ainda nao foi pareado com o receptor.
- Nunca incluir o token ou chave TLS no codigo, nas notas ou no APK.
