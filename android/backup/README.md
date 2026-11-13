# FFBE: protótipo isolado de backup de save para LXC 117

**Branch:** `feature/lxc-save-backup` (não integrado ao APK e não ativo no servidor).
**Estado:** protocolo e testes sintéticos HTTPS; nenhuma cópia do save real.

## Escopo e segurança

- Fonte: apenas os arquivos JSON regulares diretamente em
  `getFilesDir()/exvius/server-root/state/` (necessariamente
  `campaign.json`, mais `replay.json`, `summon_rotation.json`
  e outros JSON top-level). Nunca `requests/`, `backups/`, certificados,
  APKs, pacotes, dados nativos ou chaves.
- O snapshot recusa hardlinks de JSON, impedindo que um arquivo externo
  ao diretório de state seja incluído por alias de inode.
- O Revival já escreve o save com `os.replace` em `PlayerState.save`;
  o snapshot lê um arquivo inteiro sem modificá-lo e recusa leituras
  simultâneas à troca do arquivo. **Ainda não há consistência transacional
  de múltiplos JSON nem evento pós-save conectado ao motor Android.**
- O cliente recusa redirecionamentos HTTP 3xx, impedindo o encaminhamento
  acidental do token Bearer ou do payload de backup a outra origem.
- O comando `push` também exige token local em arquivo regular privado
  (modo 0600), sem symlink, com pelo menos 32 caracteres; recusa a
  operação antes de ler qualquer save quando essas condições falham.
- Transporte **HTTPS com validação da CA/certificado**, token Bearer
  de no mínimo 32 caracteres no servidor, SHA-256 na requisição e
  confirmação SHA-256 na resposta, com recibo limitado a 8 KiB para
  impedir consumo ilimitado de memória no cliente. Nenhum HTTP simples em produção.
- Servidor aceita apenas `POST /v1/backups/<device>` e
  `GET /v1/backups/<device>` autenticados; bloqueia nomes e ZIPs
  arbitrários, symlinks, travessia, manifestos maiores que 8 KiB
  (recusados antes da leitura) e payloads maiores que 20 MiB.
  Armazena arquivos de modo 0600 em diretórios 0700, em
  `storage-media` na LXC. Retém as últimas 30 cópias por dispositivo.
  **Não implementa endpoint de remoção ou restauração automática.**
- Nenhuma dependência de servidor para rodar o jogo; backup opcional
  e desligado até existir configuração explícita e implantação segura.

## Prova local

```sh
python3 -m unittest discover -s android/backup -p 'test_*.py' -v
```

O teste HTTPS gera certificado temporário em diretório descartável e
usa somente saves sintéticos. Não ativa portas da LXC.

## Contrato futuro de implantação (não executado)

A LXC tem IP LAN `192.168.15.209` e ZFS `storage-media`;
é preciso definir certificado com SAN para esse IP, **chave TLS e
segredo Bearer ambos em modo 0600** fora de Git/Syncthing e diretório de destino em
`/workspace/projects/ffbe-revival-distribution/save-backups/`.
**Não iniciar o serviço nem entregar certificado/segredo em repositório.**
A configuração de Wi-Fi e a autorização do usuário vêm antes
da primeira tentativa de envio; depois será necessário conectar
o transportador a um evento pós-save sem bloquear o jogo.

A restauração deve ter fluxo separado: listar snapshots, validar hash,
mostrar data/slot e diferenças, fazer cópia local de segurança e pedir
confirmação explícita **com o motor parado**. Nenhuma rotina de
restauração foi implementada.

## Comandos de bancada (sem conectar ao telefone)

O script oferece `serve --bind --store --cert --key --token-file` e
`push --state --url --device --ca --token-file`.
Os testes exercitam o protocolo; não usar dados reais até concluir
a autorização, o canal TLS na LAN e a integração do save no Android.
