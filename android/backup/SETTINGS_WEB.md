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
## Avanço manual por datas (17/11/2026)

Na seção **Cronologia**, o campo **Período histórico** mostra intervalos
reais, por exemplo **30/06 a 06/07/2016** e **07/07 a 13/07/2016**.
Os índices de sete dias (`EXVIUS_REPLAY_MANUAL_WEEK`) continuam somente
no protocolo de configuração, ocultos do texto exibido ao usuário.
Escolha o período, confirme a mudança histórica e salve; o servidor
registra uma revisão e **não reinicia** o FFBE. Com pareamento de backup
válido, o Android da RC3 Manual2016 busca a revisão em background e a
aplica apenas na próxima inicialização. Sem pareamento, não há sincronização
automática nem confirmação de aplicação no aparelho.

A página permanece sem JavaScript, seguindo CSP `default-src 'none'`.
Validar pelo menos uma sincronização e reinicialização reais no Samsung
antes de marcar o status do dispositivo como conectado/atualizado.

## Rótulos claros (17/11/2026)

Os campos visíveis mostram a finalidade prática: **Restringir conteúdo à
época escolhida**, **Como a cronologia avança** e **Datas que aparecem no
jogo**. A velocidade é identificada explicitamente como exclusiva do modo
automático. Os demais controles descrevem os efeitos sobre invocações,
notícias, Home, Lapis e Trust; exemplos de porcentagem explicam a escala
de décimos de ponto percentual.

Os nomes de protocolo, valores, intervalos permitidos e autenticação
permanecem iguais. O painel nunca confirma que a revisão chegou ao Android
sem evidência do pareamento/sincronização, e salvar não reinicia o jogo.

## Pareamento pelo próprio celular — Web Helper (17/11/2026)

O Web Helper autenticado dispõe de **Conectar celular**. O botão gera um
código aleatório de 24 caracteres hexadecimais (96 bits), válido por
**10 minutos e uma única utilização**, guardado somente na memória do
processo. Login, CSRF, sessão e proteção de origem continuam obrigatórios.
O painel não exibe o token de backup nem o certificado do receptor.

Na APK compatível, o usuário abre no navegador do **mesmo aparelho**
`http://127.0.0.1:18080/__exvius/config/connect` enquanto o FFBE está
em execução, cola o código e confirma. O próprio aplicativo faz uma chamada
HTTPS autenticada **pelo código**, com verificação da cadeia de certificados,
para `https://proxmox.tailcf6a16.ts.net:8445/pair/claim`.
O código é invalidado imediatamente. O receptor retorna as credenciais
**somente ao aplicativo**, e elas ficam em arquivos privados `0600` dentro de
`exvius/settings`, nunca no Web Helper, navegador, save ou APK.

Após parear, a **primeira reabertura** do FFBE ativa a sincronização e recebe
a revisão do Web Helper em `staged-config.json`. A **segunda reabertura**
aplica o período histórico à execução. Esse fluxo **não habilita backup de
saves**: o arquivo independente `exvius/backup/config.json` não é criado.

O endpoint `/pair/claim` não aceita sessão de navegador em substituição ao
código; não suporta redirecionamento, CORS nem exibe o Bearer em erros/logs.
Há limites por origem e por código. A opção é exclusiva da tailnet.

## Prévia de banners e eventos por período — 18/11/2026

A seção **Cronologia**, sob o campo **Datas que aparecem no jogo**, inclui
uma prévia instantânea que muda ao selecionar outro período. Exibe até seis
banners e seis eventos temporários, com totais e indicação de duração
estimada. Não precisa tocar em **Salvar alterações** para consultar, não
modifica a configuração da LXC e não acessa o save do celular.

O arquivo `history_preview_index.json` é gerado offline com:

```
python3 android/backup/build_history_preview.py source/server android/backup/history_preview_index.json
```

A geração usa `history_runs.banner_run()` e `history_runs.event_runs()`
com as fontes `gacha_*.json`, `event_archive.json`, `event_history.json` e
`content/*_runs.json`. Não há lista manual paralela. O índice é pequeno,
contém apenas nomes e intervalos (sem rates, saves ou credenciais) e é
carregado uma vez na inicialização do Web Helper. Atualizá-lo exige novo
build e redistribuição do índice, não alteração do Android.

A consulta é um GET autenticado no mesmo site:
`/history-preview?start=2016-06-30&week=1`. Responde JSON sem cache.
O formulário JavaScript usa somente `textContent`, sob hash SHA-256 na CSP.
Nenhum nome do índice é interpolado como HTML. Selecionar uma data apenas
consulta; aplicar ao FFBE continua exigindo **Salvar alterações** e sync.

Esta é uma **prévia do calendário Global**, não um espelho exato do runtime:
exclui eventos permanentes, pode contar campanhas históricas que o jogo
filtrará pelo save ou outros switches e usa duração padrão quando falta uma
data de encerramento confirmada. Essas estimativas são identificadas na UI.
Em caso de índice ausente ou inválido, o seletor de datas continua funcional.

A RC3 Android `android-rc3-manual2016-field-20261118` não é modificada.

## Diferença entre cronologia Global e eventos recuperados (18/11/2026)

A prévia apresenta separadamente:

- **Estreias no calendário Global:** somente eventos e trials com data de
  início publicada na anotação anual da vault. A nota de 2016 é
  `B04 INTERESSES/REGISTROS/Jogos/Anotações/notas-ffbe-global-cronologia-de-eventos-e-banners-2016.md`.
  A data de estreia **não garante atividade durante toda a semana** e
  tampouco garante que o conteúdo esteja disponível na APK. Quando a nota
  inclui uma correspondência de disponibilidade, o texto é exibido sem
  promovê-la à categoria de evento jogável.
- **Eventos no acervo Revival:** períodos de eventos temporários recuperados
  em `event_archive.json` e `history_runs`, sem provas de funcionamento de
  cada missão no cliente Android.

A cronologia de 2016 informa 20 estreias de eventos/trials que o índice
anterior não exibiu como parte do calendário original, incluindo Demon
Chimera (14/07), Demons Unleashed (01/08), Into the Abyss (19/08) e
Orbonne Monastery Vaults (30/09). A nota original explicita que alguns
não foram localizados no catálogo preservado ou existem apenas como reprises.

O gerador lê a nota **apenas ao construir** o índice e incorpora somente
nome, data, categoria e a descrição já registrada de disponibilidade:

```
python3 android/backup/build_history_preview.py source/server \
  android/backup/history_preview_index.json \
  '/workspace/vaults/obsidian-pessoal/B04 INTERESSES/REGISTROS/Jogos/Anotações/notas-ffbe-global-cronologia-de-eventos-e-banners-2016.md'
```

A nota da vault não é editada nem disponibilizada na web; a página recebe
somente a seleção limitada à semana via endpoint autenticado. Os demais
anos continuam dependentes do catálogo do projeto até suas respectivas
anotações serem reconciliadas. A release Android congelada não muda.
