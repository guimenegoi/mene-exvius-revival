# mene-exvius-revival — runner Termux de desenvolvimento Android

> **RC2 atual (12/11/2026):** o aplicativo Android único já integra
> CPython e o servidor Revival; o teste Waydroid chegou à Home e ao Vortex.
> Este guia descreve **somente o runner Termux histórico**, que não é mais
> necessário para usar o APK. Acompanhe o [checklist de RC2](../docs/ANDROID_CHECKLIST.md)
> e a [instalação do APK único](distribution/README.md).
> Ainda faltam instalação limpa, batalha/save offline e validação no celular.
>
> **Dados para o aplicativo único:** [instalação integral dos 19 pacotes](data/README.md), com
> SHA-256, atualização incremental e verificação sem internet. O mecanismo
> independente de Termux já está integrado ao instalador da RC2.

> **Somente laboratório:** a entrega final será um único aplicativo FFBE, sem
> instalação de Termux, VPN ou servidor auxiliar. O alvo e os critérios estão em
> [ANDROID_STANDALONE.md](../docs/ANDROID_STANDALONE.md).

O runner descrito abaixo é uma **ferramenta de desenvolvimento para Termux**,
não o APK RC2. O propósito é iniciar o servidor Python original em ambiente
separado, sem alterar o backend do Proxmox. Os status dos comandos Termux
não determinam a prontidão da versão embarcada.

## Requisitos

- Android com [Termux](https://termux.dev/) oficial; testes realizados em Android 13 **x86_64 / Waydroid** com Python 3.14.10.
- Armazenamento para aproximadamente 15 GB de recursos descompactados, com **ao menos 22 GiB livres** para o download inicial, além do aplicativo.
- Código deste fork. Não contém APK, dados do jogo, saves ou chaves privadas.
- Conectividade inicial para instalar dependências e baixar os arquivos disponíveis no manifesto.

Em Android ARM64 físico, ainda é necessário testar bibliotecas, memória e suspensão em segundo plano.

## Instalação no Termux

Extraia o pacote de código (ou faça clone do fork) dentro da área privada do Termux:

~~~sh
pkg install git
git clone https://github.com/guimenegoi/mene-exvius-revival.git
cd mene-exvius-revival
./android/ffbe-termux setup
./android/ffbe-termux doctor
~~~

O diagnóstico deve informar **dados ausentes** enquanto não houver recursos instalados; isso é esperado.

Para instalar os dados originais pela rotina já incluída no Revival:

~~~sh
./android/ffbe-termux fetch-data
./android/ffbe-termux verify
./android/ffbe-termux doctor
~~~

O downloader valida o SHA-256 dos pacotes recebidos e registra a revisão instalada. O comando verify consulta essa revisão, mas **não recalcula o hash de cada arquivo extraído**; o runner também exige tabelas e arquivos nativos essenciais para impedir inicializações com diretórios vazios. Recomenda-se manter mais espaço livre para futuras atualizações.

Se já tiver os arquivos do servidor de referência, é possível importar **um conjunto completo, compatível com data/latest.json** para o diretório de dados sem download adicional. Não copie saves, certificados ou relatórios do servidor funcional.

## Executar e verificar

~~~sh
./android/ffbe-termux start
# Outra sessão do Termux:
./android/ffbe-termux status
./android/ffbe-termux stop
~~~

O servidor utiliza:

| Recurso | Padrão local |
| --- | --- |
| HTTPS | 18443 |
| HTTP | 18080 |
| DNS de teste | 15353/UDP |
| Dados | ~/.local/share/mene-exvius-revival/data |
| Save e certificados | ~/.local/share/mene-exvius-revival/server-root |

As opções Android já comprovadas no servidor externo são aplicadas por variável de ambiente (WIKI_REWARDS=0, IOS_HCA=0 e IOS_HCA_PLAIN=0). Os valores podem ser sobrescritos por ambiente; o código do Revival não é alterado.

**Não remova o diretório server-root sem backup.** Ele contém saves e as chaves privadas geradas para a instância local.

## Limitações da versão experimental

1. **O cliente Android usa as portas originais 80/443.** O Termux sem root não consegue abrir diretamente essas portas (bind em 443 retorna Permission denied). O runner usa portas altas, mas **não faz VPN, DNS global, NAT nem patch do APK**.
2. **Sem jogo offline integrado:** o FFBE ainda não foi testado apontando para o processo local. Não declare jogabilidade offline até validar um ciclo completo de batalha com o Proxmox e a internet indisponíveis.
3. **Suspensão:** o Waydroid congela contêineres quando o Android suspende. O runner não instala serviços persistentes nem impede a suspensão; isso exige uma solução específica, testada em aparelho físico.
4. **Recursos grandes:** o pacote contém apenas código. Não distribua material proprietário do jogo, APK modificado, saves ou certificados privados.
5. **Compatibilidade de recompensas:** WIKI_REWARDS continua desativado provisoriamente até resolver a falha de tabelas Android.
6. **Licenciamento:** o upstream não oferece uma licença explícita na raiz da revisão testada. Antes de distribuir um pacote independente contendo seu código, confirme a autorização necessária. O arquivo gerado por build-package.sh é para avaliação local, não é publicado automaticamente.

## Construir o pacote de desenvolvimento

No desktop com uma cópia **limpa e commitada** do fork:

~~~sh
./android/build-package.sh
./android/tests/smoke.sh
~~~

Isso gera um tar.gz de código fonte e um arquivo SHA-256 em dist/, sem download de dados, sem APK, sem salvar chaves ou criar uma release automaticamente. O arquivo é uma **prévia técnica**, não um instalador de jogo pronto.

## Critérios para uma entrega jogável

- [x] Python, bibliotecas e imports reais do motor no Termux.
- [x] Serviço HTTP Python de demonstração acessível pelo desktop.
- [ ] Motor completo iniciado dentro do Android, respondendo HTTP e HTTPS com dados locais completos.
- [ ] Cliente Android se conecta ao backend local via caminho explícito, seguro e sem root.
- [ ] Ciclo de batalha, recompensas e save com a rede externa desligada.
- [ ] Reinicialização/retomada, armazenamento e processos de fundo testados.
- [ ] ARM64 físico testado antes de chamar de release Android.

Para histórico e arquitetura, veja [docs/ANDROID.md](../docs/ANDROID.md).
