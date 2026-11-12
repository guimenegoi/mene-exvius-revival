# FFBE Android — entrega em aplicativo único

Acompanhamento por prova e pendências: [checklist vivo](ANDROID_CHECKLIST.md).

## Requisito fechado

A entrega para uso cotidiano deve instalar **somente o FFBE**. O jogador não deve
precisar instalar ou executar Termux, sing-box, VPN de terceiros, um servidor Linux,
Proxmox ou uma segunda aplicação auxiliar.

A fase de desenvolvimento pode usar Termux/Waydroid como bancada de testes.
O runner `android/ffbe-termux` continua disponível apenas para testes e não integra
a experiência ou a lista de requisitos da versão final.

**Status em 12/11/2026: transporte Java, instalador de dados e CPython 3.14.10 ARM64 com Revival, PyYAML, tzdata, Pillow, cryptography, cffi e pycparser dentro do FFBE comprovados (PNG e AES-CBC do FFBE). Inicialização Python fora da thread principal **validada apenas em laboratório**; lifecycle de produção, geração de certificados, entrada HTTP Revival guardada por inventário de 19 pacotes (falha segura comprovada no Waydroid); servidor **real** ainda não iniciado com dados completos, testes x86_64/ARM64 físico e APK offline independente ainda NÃO concluídos.**
O pacote `mene-exvius-revival-termux-5a1afdc9.tar.gz` é um artefato de desenvolvimento,
não é o instalador offline prometido.

## Constatações verificadas

- O FFBE Global original é versão 9.1.0, `versionCode=9101`, com APK base e quatro splits.
- `libgame.so` (`config.arm64_v8a.apk`) contém o hostname `v910-lapis.gumi.sg`; a
  maneira como ele escolhe porta e endpoint **ainda não foi diagnosticada**.
- A alteração de confiança TLS no cliente funciona quando o backend é remoto.
- O mesmo `ios-server/serve.py` iniciou no Android/Termux com tabelas e MST importados,
  sem copiar todos os recursos de áudio, gerou certificados e respondeu HTTP 200,
  HTTPS 200 validado contra CA local e GET de arquivo MST.
- O motor continuou respondendo após 72 segundos com o cliente de jogo em primeiro plano.
- O patch em [android/network](../android/network/README.md) foi compilado em duas DEX,
  instalado no Waydroid isolado e recebeu API e downloads do CriFsWebInstaller
  em HTTP local (127.0.0.1:18080), sem tocar em libgame.so.
- Os dados locais incompletos causaram 404, primeiro em localized_texts e depois
  em en/sd/area/Ver461_spdungeon1.cpk. O arquivo CPK existe na referência Linux.
- **Ainda não** há integração completa, jogo offline ou teste com a tela apagada.
- O fork tem backend Python, mas **não** possui fontes Android originais, módulo Gradle ou
  `AndroidManifest.xml` do cliente, portanto adicionar um `Service` via Gradle não é
  uma operação direta no aplicativo existente.

## Instalação inicial de recursos

O primeiro uso deve instalar os **19 pacotes** do manifesto em uma árvore
única: 18 de dados do motor e um `client-assets` com os recursos específicos do
cliente. Os hashes de download e o inventário são conferidos antes de liberar
o modo offline. Ver [instalador Android de dados](../android/data/README.md).

O instalador separado já foi implementado e testado, mas a ligação ao cliente
e ao runtime incorporado ainda não. O Android original permite uma solução
mais simples que o overlay do PC: instalar os arquivos nativos diretamente no
diretório privado do jogo e expor ao servidor apenas cinco vínculos permitidos
(`mst`, `localized_texts`, `common_lang`, `en`, `homeMarquee`).
Os testes de layout provam que as duas visões usam os mesmos arquivos físicos;
a integração e os testes de escrita em Android real continuam pendentes.

## Arquitetura-alvo

```text
FFBE Global 9.1.0 — um aplicativo instalado
  ├─ cliente do jogo existente
  ├─ bootstrap Android incorporado (ciclo de vida do backend)
  ├─ Python nativo embarcado (libpython + biblioteca padrão + dependências)
  ├─ motor do Revival, sem fork paralelo de lógica
  ├─ comunicação interna cliente ↔ backend via loopback
  └─ dados e saves privados do aplicativo
       ├─ dados baixados/verificados no primeiro uso
       └─ saves protegidos, backup e atualização incremental
```

O uso do Python incorporado está documentado oficialmente pelo CPython
(<https://docs.python.org/3.14/using/android.html>) e seus pacotes para Android
(<https://www.python.org/downloads/android/>). O runtime deve ser empacotado **no
mesmo aplicativo**, sem instalação separada. Dependências Python nativas precisam
ser disponibilizadas nas ABIs necessárias, incluindo ARM64 para aparelho físico.

O código não deve depender das pastas privadas do Termux nem de binários auxiliares
disponíveis somente em Linux desktop. Os dados grandes podem ser baixados
durante a configuração inicial, mas o jogo deve funcionar sem internet depois disso.

### Redirecionamento sem aplicativo externo

A comunicação original usa nomes/portas de produção. No Android sem root, um
servidor dentro de uma aplicação não pode abrir diretamente a porta 443.

A prioridade é **adaptar o próprio cliente do jogo**, no pacote gerado localmente,
para falar com o backend incorporado via loopback e porta alta, preservando TLS
ou outro mecanismo local com autenticação equivalente. Antes de qualquer patch,
determinar objetivamente os pontos de construção de URL, DNS, porta e verificação
de certificados de `libgame.so` e componentes Java.

Não instalar um cliente VPN, DNS ou proxy separado. Não atribuir a um
`VpnService` interno a condição de solução até haver testes e aprovação
explícita desse mecanismo; ele também envolve uma permissão especial do Android.

### Distribuição e propriedade intelectual

A compilação de desenvolvimento pode solicitar ao usuário os APKs originais
que ele já possui e gerar uma cópia adaptada localmente. Não colocar APKs
proprietários, código fechado redistribuído, recursos do jogo, saves, certificados
privados ou chaves de assinatura no Git/release pública.

O upstream Revival não tem licença explícita de redistribuição identificada
na revisão auditada. Antes de disponibilizar um artefato público contendo
seu código, confirmar as permissões correspondentes.

## Gates de teste antes de chamar o pacote de jogável

1. **Cliente:** identificar e isolar patch mínimo, reproduzível e reversível de
   endpoint/porta/certificado, com diff binário e sem tocar na lógica do jogo.
2. **Runtime incorporado:** inicializar/desligar o mesmo Revival de dentro do
   aplicativo, nas ABIs x86_64 (teste) e ARM64 (entrega), com isolamento de save.
3. **Dados:** instalar e verificar os recursos da revisão, incluindo arquivos
   necessários de tutorial, mapa, áudio e combate, sem downloads de produção durante o jogo.
4. **Rede:** provar que todas as requisições do cliente permanecem dentro do
   aplicativo ou no loopback e não atingem o Proxmox nem internet externa.
5. **Gameplay:** login local, World Map, batalha e recompensa, exploração,
   encontros aleatórios, summons, inventário e save após reinício.
6. **Android real:** gerenciamento de serviço, consumo de memória/bateria e
   recuperação após fechamento, troca de app, tela desligada e reinício.
7. **Release:** pacote assinado e instalação testada em dispositivo limpo,
   sem Termux, sing-box, VPN ou outro aplicativo auxiliar.

Enquanto qualquer gate não passar, o artefato deve ser identificado como
**prévia técnica**, nunca como APK offline pronto.
