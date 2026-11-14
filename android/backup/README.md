# FFBE Revival - backup privado de save (LXC 120)

## Estado em 2026-11-13

- Branch: feature/lxc-save-backup. O cliente Android ainda NAO foi integrado e nenhum save real foi enviado.
- Servidor receptor HTTPS implantado e iniciado automaticamente no LXC 120 (ffbe-revival-test; 192.168.15.230).
- Unit: ffbe-save-backup.service (active e enabled, usuario isolado ffbe-backup).
- Origem do servidor: /opt/mene-exvius-revival-backup/android/backup/lxc_backup.py.
- Endpoint HTTPS interno: https://192.168.15.230:18447/v1/backups/<device>.
- Endpoint Tailscale Serve privado: https://proxmox.tailcf6a16.ts.net:8444/v1/backups/<device> (tailnet only, nao Funnel).
- Proxmox serve TLS publico para a tailnet e encaminha para TLS privado do LXC.
- Segredos e certificado: /etc/ffbe-backup/ (0700; token e chave TLS 0600). NUNCA enviar segredo para Git.
- Backups em /var/lib/ffbe-save-backups (0700, ffbe-backup), mp1 ZFS do host /storage-media/dev-projects/ffbe-revival-distribution/save-backups; cerca de 2,6 TB livres na montagem.
- Protecao verificada: requisicoes GET e POST sem token retornam HTTP 401; a unidade continuou ativa apos reboot do LXC.
- Testes sinteticos do protocolo: 20 testes aprovados. Envio autenticado ao servico implantado e restore real AINDA NAO testados.

## Contrato de seguranca

- Fonte: somente arquivos JSON regulares de getFilesDir()/exvius/server-root/state/, inclusive campaign.json.
- Excluidos: APKs, saves de outros apps, pacotes de dados, certificados, requests, downloads e segredos.
- Snapshot rejeita symlinks, hardlinks, arquivos concorrentes, ZIP traversal, manifestos grandes e payloads maiores que 20 MiB.
- TLS verificado pelo cliente, Bearer token >= 32 caracteres, SHA-256 integral em pedido/resposta, sem redirecionamentos.
- POST /v1/backups/<device> cria snapshot privado 0600; GET autenticado lista metadados. Retencao: 30 por dispositivo.
- Nenhum endpoint para restaurar, sobrescrever ou apagar dados remotos; jamais restaurar com motor em execucao.
- Nao embutir token administrativo em APK distribuido; implantar pareamento e config privada no Android antes de habilitar backups automaticos.
- A API permanece desativada para o cliente Android ate concluir o emparelhamento; o servidor nao chama o aplicativo.

## Verificacoes em servidor

ssh proxmox
pct exec 120 -- systemctl status ffbe-save-backup.service
pct exec 120 -- df -h /var/lib/ffbe-save-backups
pct exec 120 -- journalctl -u ffbe-save-backup.service -n 30 --no-pager
tailscale serve status

Teste autorizado sem acessar token: um GET nao autenticado a /v1/backups/phone deve retornar HTTP 401.
Teste unitario (na copia do branch):
python3 -m unittest discover -s android/backup -p 'test_*.py' -v

## Pendencias

1. Enrolar um cliente por aparelho sem publicar o token; adicionar rotina Android opt-in, HTTPS verificado e retry sem afetar gameplay.
2. Provar pelo menos um snapshot REAL da campaign.json no diretorio privado do servidor, com hash valido e reapertura do jogo.
3. Implementar restore separado com aviso/confirmacao explicita, backup local anterior e motor parado; executar ensaio em dispositivo de teste.
4. Documentar a politica de rotacao do token e do certificado TLS, que expira em novembro de 2027.

Este documento registra um receptor implantado, nao uma promessa de backup automatico ja operacional.

## Integração Android experimental — 14/11/2026

A branch `integration/android-diagnostics-backup-20261114` inclui o transporte
HTTPS existente no bundle do motor e agenda um snapshot em thread daemon após
`PlayerState.save()` concluir `os.replace()` de `state/campaign.json`. O envio
não bloqueia a resposta da partida; tentativas são limitadas a uma por cinco
minutos, não há envio simultâneo nem restauração automática.

**Desativado por padrão.** Nenhuma chave ou token é compilado no APK. Um
pareamento privado deverá provisionar, sob `getFilesDir()/exvius/backup/`,
`config.json` com permissão `0600` e os arquivos `token_file` (`0600`) e
`ca_file` indicados na configuração. Formato (valores ilustrativos):

```json
{
  "enabled": true,
  "url": "https://servidor-exemplo.invalid:18447",
  "device": "aparelho-exemplo",
  "token_file": "/caminho-privado/token",
  "ca_file": "/caminho-privado/ca.pem"
}
```

O token deve ter ao menos 32 caracteres, ser exclusivo do aparelho e não deve
ser colocado em arquivos versionados ou em logs. O caminho de configuração
não é criado pelo aplicativo: **pareamento e administração de credenciais
continuam pendentes**. Rede indisponível ou configuração incorreta não afeta
o save local, e o backup não é exigido para jogar em modo avião.

A telemetria existente de `client_reports.py` também fica desativada por
padrão no Android. Somente `getFilesDir()/exvius/diagnostics.json`, com modo
`0600` e conteúdo `{"client_reports": true}`, habilita a solicitação de logs
do cliente. O servidor então recebe no máximo uma solicitação por abertura,
com deduplicação e retenção já implementadas no Revival. Essa configuração
também exige provisionamento privado; não há interface de usuário ainda.

Testes são **sintéticos**; ainda faltam teste em APK ARM64 real, pareamento
seguro, comprovação de upload com save real, política de reconexão, restauração
com confirmação e integração na release aprovada. Não colocar credenciais,
backups reais ou APKs proprietários no Git.
