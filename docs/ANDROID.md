# FFBE Revival no Android — estado e desenvolvimento

Este documento descreve **o fork experimental [mene-exvius-revival](https://github.com/guimenegoi/mene-exvius-revival)**. A documentação principal da raiz é mantida do [Exvius Revival para iOS](https://github.com/CreamySeaman6/Exvius-revival-ios); **não** é um guia Android pronto para instalar.

Acompanhe as etapas com evidências no [checklist vivo da entrega Android](ANDROID_CHECKLIST.md).

## Objetivo

**Requisito de entrega:** um único aplicativo Android FFBE, sem depender de Termux,
sing-box, VPN de terceiros, servidor externo ou aplicativos auxiliares. O runner
Termux existente é somente bancada de desenvolvimento. Consulte a
[arquitetura do APK independente](ANDROID_STANDALONE.md) e seus critérios de aceite.

Usar o mesmo motor de jogo `source/server/` do Revival no Android (FFBE Global), inicialmente com um servidor externo de referência e depois **inteiramente no aparelho**, sem depender do Proxmox ou de conexão à internet para jogar.

O fork deve evitar divergências desnecessárias do upstream: ajustes específicos Android devem ficar isolados; correções genéricas devem ser propostas ao projeto original.

## Estado verificado — 12 de novembro de 2026

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
| Imports do backend Revival no Android | **Validados no Termux** | Código compactado (7,5 MB), conferido por SHA-256, compilado no Python 3.14 e imports de `serve`, `certs`, `capture_server`, `cryptography`, `PyYAML`, `Pillow` e `tzdata` sem erros |
| CPython 3.14.10 ARM64 dentro do processo do FFBE | **Validado em laboratório** | JNI, stdlib e 67 módulos `.so` nativos oficiais; `ssl`, `sqlite3`, `zlib`, `hashlib`, `socket` e `zipfile` importados com sucesso no jogo |
| Código do motor Revival no processo FFBE | **Importação e AES validados; motor não iniciado** | 1.063 arquivos: Revival, PyYAML, tzdata, Pillow, cryptography, cffi e pycparser em CPython 3.14 ARM64; Waydroid confirmou PNG, vetor NIST AES-128-CBC, cifrar/decifrar via `ffbe_crypto` e imports X.509 após reabrir. Servidor HTTP não iniciado, saves intactos |
| Inicialização Python fora da thread principal | **Validada em laboratório** | `Lapis.onCreate` retorna imediatamente enquanto `FFBE-Python` executa imports e AES em TID separado; repetido após `force-stop`. Sem ANR/timeout observado. Lifecycle e readiness ainda pendentes |
| Entrada do handler Revival em `127.0.0.1:18080` | **Implementada; bloqueio seguro validado** | Conectada ao motor original com inventário dos 19 pacotes; Waydroid não abriu porta sem recursos e manteve imports/AES. Encaminhamento HTTP validado apenas com handler simulado; requisições reais não testadas |
| Runner Termux `android/ffbe-termux` | **Prévia validada** | Diagnóstico e bloqueio de execução sem dados testados no Waydroid; [comandos e limites](../android/README.md) |
| Motor Revival no Termux (teste) | **Validado com dados parciais** | `ios-server/serve.py` iniciou, HTTPS 200 com CA própria, GET MST 200 e serviço ativo ao abrir o FFBE |
| Transporte Java para localhost (teste) | **API e CRI validados** | APK 9.1.0 com somente dois DEX substituídos; chamada de API e downloads chegam a HTTP local na porta 18080; [detalhes](../android/network/README.md) |
| Recursos completos no Android | **Pendente** | A cópia reduzida causou 404 em localized_texts (depois corrigido) e en/sd/area/Ver461_spdungeon1.cpk |
| Instalador de recursos offline (Android) | **Validado em laboratório** | 19 pacotes preparados pelo mesmo downloader, incluindo client-assets real; verificação sem rede, pré-requisito de armazenamento e testes em [android/data](../android/data/README.md) |
| Aplicativo independente (sem apps auxiliares) | **Pendente** | CPython e imports do motor são provas de laboratório; faltam dependências externas completas, servidor local, recursos reais, lifecycle fora da UI e jogabilidade offline |
| Jogo completamente offline | **Pendente** | Testar funcionamento sem Termux, Proxmox ou internet, com saves locais |

**Cuidado:** a prova de transporte usou Termux somente como laboratório. O
jogo ainda NÃO está offline; só a referência Linux tem todos os dados e o
cliente Android não concluiu a inicialização com o conjunto parcial.

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
- [x] Testar compilação e imports de `ios-server/` e `source/server/` no Termux, sem copiar dados ou saves.
- [x] Disponibilizar CLI Termux com `setup`, `doctor`, `verify`, `fetch-data`, `start`, `stop` e `status`; testar proteção contra dados ausentes.
- [x] Inicializar o motor no Android/Termux com dados mínimos e save independente, sem alterar o servidor de referência.
- [x] Validar comunicação Java de API e CriFsWebInstaller do FFBE com o Revival em localhost usando APK de teste.
- [x] Implementar instalador de dados do Android para 19 pacotes e diagnóstico local, reutilizando o downloader existente.
- [ ] Instalar os 19 pacotes no Android e compartilhar com o cliente sem duplicações.
- [ ] Medir uso de RAM, CPU, armazenamento, estabilidade e operação com tela apagada; testar também Android ARM64 físico.
- [x] Provar mapeamento HTTP local dos principais métodos de rede Java, sem root, VPN, DNS ou patch na biblioteca nativa.
- [x] Compilar ponte JNI ARM64 e executar código CPython isolado dentro do processo FFBE (laboratório, sem servidor).
- [ ] Incorporar o servidor e seu ciclo de vida ao mesmo aplicativo Android; validar os outros dois mecanismos de download.
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
