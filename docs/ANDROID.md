# FFBE Revival no Android — estado e desenvolvimento

Este documento descreve **o fork experimental [mene-exvius-revival](https://github.com/guimenegoi/mene-exvius-revival)**. A documentação principal da raiz é mantida do [Exvius Revival para iOS](https://github.com/CreamySeaman6/Exvius-revival-ios); **não** é um guia Android pronto para instalar.

## Objetivo

Usar o mesmo motor de jogo `source/server/` do Revival no Android (FFBE Global), inicialmente com um servidor externo de referência e depois **inteiramente no aparelho**, sem depender do Proxmox ou de conexão à internet para jogar.

O fork deve evitar divergências desnecessárias do upstream: ajustes específicos Android devem ficar isolados; correções genéricas devem ser propostas ao projeto original.

## Estado verificado — 11 de novembro de 2026

| Verificação | Estado | Evidência / restrição |
| --- | --- | --- |
| Cliente FFBE Global Android 9.1.0 (versionCode 9101) | **Validado parcialmente** | Executa no Waydroid Android 13 com a configuração de confiança TLS adaptada |
| DNS e HTTPS até o Revival externo | **Validado** | Requisições autenticadas, download de recursos e login |
| Batalha no World Map | **Validada** | Combate, vitória, recompensas e retorno ao mapa confirmados no cliente |
| Persistência de progresso | **Validada no backend** | Save de referência com missões `1110100` e `1110101`, rank 2, conferido contra backup |
| Exploração e encontros aleatórios | **Pendente** | Sem teste conclusivo |
| Summons e inventário | **Pendente** | Sem teste conclusivo |
| Tabelas de recompensas da wiki | **Compatibilidade pendente** | `EXVIUS_WIKI_REWARDS=0` no ambiente de referência |
| Python dentro do Android | **Validado** | Python 3.14.10 no Termux x86_64 (Waydroid) |
| Servidor HTTP Python dentro do Android | **Validado** | `python -m http.server 18443`, acessado por outro dispositivo com HTTP 200 |
| Motor Revival completo dentro do Android | **Pendente** | Dependências, dados, certificados e inicialização não validados |
| Jogo usando o backend local e sem internet | **Pendente** | Portas, DNS/encaminhamento e execução em segundo plano por resolver |

**Cuidado:** executar um servidor Python de demonstração **não** significa que o jogo esteja offline. O backend funcional permanece no servidor Linux de referência.

## Arquitetura

```text
                         ETAPA VALIDADA
FFBE Global 9.1.0 (Waydroid isolado)
  └── DNS dos domínios do jogo → Revival no servidor Linux/Proxmox
       ├── ios-server/serve.py (HTTP/HTTPS, TLS, DNS)
       ├── source/server/      (motor FFBE)
       ├── data/static, data/native (recursos preservados)
       └── server-root/state   (save e certificados, fora do Git)

                           META
FFBE Global Android no próprio aparelho
  └── redirecionamento local a resolver
       └── mesmo backend Python Revival em runtime Android
            ├── dados locais com armazenamento controlado
            ├── save local independente do de referência
            └── inicialização/parada e uso com tela apagada
```

O teste atual não envolve Docker no Android. O servidor de referência usa um LXC Linux. **Não mover os dados nem o save de referência enquanto o protótipo local não passar nos testes.**

## Ajustes necessários à integração Android com o Revival externo

1. **Cliente:** somente `res/xml/network_security_config.xml` do APK base foi alterado para aceitar certificados de autoridades instaladas pelo usuário. O APK base e seus quatro splits foram assinados de forma consistente com uma chave de teste. Não houve alteração das bibliotecas nativas ou do motor de combate. Os APKs alterados **não** fazem parte do repositório.
2. **DNS:** a sessão isolada de Waydroid resolve os domínios originais do FFBE para o servidor de referência. É uma configuração externa ao código do Revival.
3. **Configuração do backend para Android:** desativar transformações de bancos HCA específicas do iOS e manter temporariamente as tabelas originais de recompensas:

   ```ini
   EXVIUS_WIKI_REWARDS=0
   EXVIUS_IOS_HCA=0
   EXVIUS_IOS_HCA_PLAIN=0
   EXVIUS_TABLE_VERSION_OFFSET=201000
   ```

   Esses valores pertencem ao **ambiente de testes Android** e não devem substituir os padrões do servidor iOS. O offset maior obrigou o cliente de teste a buscar tabelas novas depois da correção. O bloqueio das recompensas de wiki é **provisório**, não um conserto final.
4. **Cache:** após corrigir a transformação iOS de áudio, foi necessário limpar **somente os dados locais da instalação de teste** para eliminar tabelas antigas. Não automatizar limpeza de cache/save ou repetir isso em aparelhos com progresso real.

### Por que o servidor local ainda não pode ser apontado pelo DNS

No Android sem root, processos comuns não podem escutar diretamente as portas privilegiadas 80/443; o teste de bind na porta 443 resultou em `Permission denied`. O Revival permite configurar `FFBE_HTTP_PORT`, `FFBE_HTTPS_PORT` e `FFBE_DNS_PORT`, mas **mudar essas portas não muda automaticamente as URLs embutidas no cliente**. Será necessário comprovar um encaminhamento local ou uma adaptação mínima do cliente, com teste de TLS e sem afetar outras conexões do dispositivo.

O teste com Termux/Waydroid também mostrou suspensão do contêiner por inatividade (`suspend_action=freeze`), distinta de falha no Python. O tempo de desligamento de tela foi alterado apenas durante o teste e restaurado ao valor original ao final.

## Operação do servidor de referência

O teste de servidor está no **CT 120** do Proxmox. Os caminhos abaixo são do **servidor Linux**, e não do checkout de desenvolvimento:

- Código: `/opt/exvius-revival-ios`
- Dados: `/srv/ffbe/data`
- Estado e certificados: `/srv/ffbe/server-root`
- Overrides Android: `/etc/systemd/system/ffbe-revival-test.service.d/20-android-compat.conf`
- Backups: `/srv/ffbe/backups`
- Serviço: `ffbe-revival-test.service`

O host Proxmox possui um comando de manutenção **instalado localmente, ainda não versionado neste fork**:

```bash
ffbe-revival status
ffbe-revival check
ffbe-revival backup
ffbe-revival update
```

O `update` aceita alterações de código por fast-forward, cria backup consistente e valida a saúde do serviço. Se houver novos pacotes grandes de dados, bloqueia a atualização até que exista snapshot do CT e plano de recuperação. Nunca tratar a atualização de dados como um simples `git pull`.

## Próximas etapas (com provas independentes)

- [x] Clonar o fork e configurar os remotos `origin` e `upstream`.
- [x] Validar batalha, recompensas e persistência no backend Linux.
- [x] Instalar Termux e Python; servir uma página HTTP em porta alta no Android.
- [ ] Testar as dependências reais de `ios-server/` e `source/server/` no Android/Termux, com dados mínimos e sem alterar o servidor de referência.
- [ ] Iniciar uma instância independente do motor Revival no Android, usando portas altas e estado de teste descartável.
- [ ] Medir uso de RAM, CPU, armazenamento, estabilidade e operação com tela apagada; testar também Android ARM64 físico.
- [ ] Resolver o mapeamento do cliente para o servidor local e a confiança TLS sem exigir root.
- [ ] Passar uma batalha e persistir o save **sem nenhuma requisição ao Proxmox nem à internet**.
- [ ] Verificar exploração/encontros aleatórios, summons, inventário e demais telas essenciais.
- [ ] Investigar objetivamente a incompatibilidade das tabelas `EXVIUS_WIKI_REWARDS=1` e recuperar as funcionalidades sem quebrar Android.

## Atualização do fork

O fork foi criado diretamente a partir do Revival. Os remotos recomendados são:

```bash
git remote -v
# origin   https://github.com/guimenegoi/mene-exvius-revival.git
# upstream https://github.com/CreamySeaman6/Exvius-revival-ios.git
git fetch upstream
git status
```

Para atualizar, revisar os commits do upstream e integrar com merge/rebase controlado; **não usar `git reset --hard` ou sobrescrever trabalho do fork**. Quando a árvore não divergiu, `git merge --ff-only upstream/main` é a opção mais simples. Depois testar os dois perfis (iOS original e Android) antes de publicar uma versão.

## Limites de distribuição e segurança

- Não incluir APKs, XAPKs, conteúdo proprietário do FFBE, saves, relatórios pessoais, chaves privadas, certificados de servidor ou dados completos de jogo no Git.
- O repositório upstream não apresenta um arquivo `LICENSE` na raiz no estado auditado. **Não presumir permissão ampla para redistribuição fora das condições permitidas**, nem acrescentar licença que pretenda cobrir código upstream.
- O projeto é não oficial; Square Enix e gumi detêm os direitos sobre FFBE.
- Toda mudança em código exige leitura do arquivo atual, diff mínimo, teste e registro do commit. Mantenha a instalação Linux conhecida como funcional até haver uma versão Android reproduzível.
