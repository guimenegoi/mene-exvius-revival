# FFBE Revival — painel web de configurações

O painel edita somente server-config.json do dispositivo samsung-android, sem modificar diretamente saves, executar jogo ou alterar APKs.

## Endereço e proteção
- URL privada na Tailnet: https://proxmox.tailcf6a16.ts.net:8445/
- Proxmox Tailscale Serve: HTTPS 8445 encaminha ao HTTPS interno 192.168.15.230:18448; o salto na LAN também é criptografado por TLS.
- Não ativar Tailscale Funnel nem publicar portas no roteador.
- Login independente do token de backup, com senha aleatória e PBKDF2-HMAC-SHA256, salt aleatório, cookies Secure/HttpOnly/SameSite=Strict, sessão de 8 h, proteção CSRF/Origin e limitação de tentativas.
- Nenhum JavaScript externo, CDN ou token de backup enviado ao navegador.
- Serviço roda como ffbe-backup, usuário não privilegiado que administra configurações do ZFS.

## Armazenamento e serviço
- Código estável: /usr/local/libexec/ffbe-settings/settings_web.py, com config_model.py e config_service.py.
- Unit ffbe-settings-web.service exige montagem real de /var/lib/ffbe-save-backups para evitar fallback ao disco interno.
- Senha web em /etc/ffbe-settings-web/auth.json, fora do Git. Senha inicial fica em initial-password.txt, root-only (0600).
- Revisões em /var/lib/ffbe-save-backups/configs/ e config-history/, independentes dos saves.

## Primeiro acesso
Senha inicial para administrador do Proxmox (não exibir nos logs do painel):
    pct exec 120 -- cat /etc/ffbe-settings-web/initial-password.txt
Depois de salvá-la no gerenciador de senhas, apague a cópia temporária:
    pct exec 120 -- rm /etc/ffbe-settings-web/initial-password.txt

## Operações do painel
- Edita somente as opções permitidas pelo config_model.py; campos em branco mantêm o comportamento original.
- Mostra revisão atual e histórico de revisões; compare-and-swap impede sobreposição de mudanças concorrentes.
- Exige confirmação explícita para mudanças em data inicial e ritmo de replay.
- Não altera campaign.json, replay.json nem reinicia o Android.
- O Android só aplicará a nova revisão depois do pareamento seguro, sincronização e reinício do motor; mudanças de cronologia incompatíveis ficam staged.

## Testes
    python3 -m unittest android/backup/test_settings_web.py -v
    python3 -m unittest discover -s android/backup -p 'test_*.py' -q

O painel no servidor não significa que a sincronização real com o telefone esteja concluída. Nenhum backup real foi pareado até agora.