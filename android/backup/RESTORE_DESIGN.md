# Restauração de save — núcleo offline (P0, experimental)

Implementação: android/backup/save_restore.py. Testes: android/backup/test_save_restore.py.

**Estado:** núcleo de restauração implementado e testado em Python na LXC 120.
Não faz parte do APK instalado, da release estável, do servidor HTTPS nem do
painel. Nenhum save real foi restaurado.

## Contrato de segurança

1. O controlador Android confiável interrompe o motor Revival e garante
   acesso exclusivo ao diretório de estado. Sem isso, a API recusa a operação.
2. A interface mostra o identificador do snapshot e seu SHA-256 completo,
   obtido do backup privado. O usuário confirma explicitamente a frase
   RESTAURAR seguida dos 12 primeiros caracteres do SHA-256.
3. inspect_archive confere hash do ZIP, manifesto, hashes de cada JSON,
   nomes permitidos, limites e recusa travessia, compressão, symlinks,
   entradas duplicadas ou inesperadas.
4. restore_offline grava pré-backup integral privado do save atual em
   diretório irmão do state (modo 0600), antes de qualquer alteração ativa.
5. Persiste pending-restore.json e sincroniza em disco. Prepara novos
   arquivos no mesmo filesystem e usa os.replace para a troca.
6. Confere o estado restaurado. Em falha normal, reverte imediatamente
   pelo checkpoint anterior.
7. Em morte abrupta do processo, o diário persiste. O controlador deve
   obrigatoriamente executar recover_pending com o motor parado antes
   da próxima inicialização. Checkpoint adulterado bloqueia a operação.
8. O pré-backup permanece após o sucesso. Não existe restauração automática
   pela rede, exclusão de snapshots ou endpoint HTTP de restore.

A troca de múltiplos arquivos não é uma transação atômica do filesystem.
A segurança contra crashes depende do diário e do controlador de startup.
Sem integração do ciclo de vida Android, não conectar ao jogo real.

## Limites intencionais

- A confirmação de motor parado é callback obrigatório; a implementação
  Android desse controlador ainda não existe.
- Não é possível restaurar um save da aplicação em uso via painel.
  O servidor armazena snapshots; o Android deve restaurá-los localmente.
- O backup do Samsung no ZFS não é tocado. Todos os testes usam
  tempfile.TemporaryDirectory.
- A retenção de checkpoints pré-restauração ainda precisa ser definida
  antes da integração, para impedir acúmulo indefinido.

## Validação na LXC 120 em 13/11/2026

- 13 testes específicos da restauração: OK
- 84 testes da suíte de backup/configurações: OK
- 80 testes do runtime Android: OK

Cenários: pré-backup, remoção de arquivos extras, negação com jogo ativo,
SHA ou confirmação incorretos, symlink/hardlink, falha durante escrita,
interrupção simulada, recuperação por diário e checkpoint adulterado.

## Próximos passos para uso real

1. Implementar controle confiável de parada e inicialização do motor Android.
2. Empacotar esta biblioteca sem abrir endpoint novo ou alterar defaults.
3. Criar interface de seleção e confirmação do snapshot.
4. Testar em aparelho isolado com dados sintéticos, inclusive morte de
   processo entre mudanças de arquivos.
5. Somente depois realizar restauração do save real com aprovação específica
   e cópias adicionais verificadas.

## Marco seguinte — guarda de recuperação antes do motor (13/11/2026)

- android/runtime/restore_startup.py passa a ser empacotado como
  ffbe_restore_startup.py apenas com a flag --experimental-restore,
  obrigatoriamente acompanhada por --experimental-backup.
- android/backup/save_restore.py vira ffbe_save_restore.py no APK LAB.
- android/runtime/local_http.py chama recover_before_engine() antes de
  importar serve/capture_server e antes de aplicar configuracoes do jogo.
- Sem diretorio de recuperacao ou diario pendente: segue normalmente,
  sem ler ou alterar o save. Com diario: so tenta recuperacao se o motor
  ainda nao foi importado e a porta local 18080 nao estiver aberta.
- Se o diario ou o checkpoint estiver incorreto, ou se o motor aparentar
  estar em execucao, a inicializacao falha fechada. Nunca ignora erro.
- Essa etapa e guarda de startup, NAO interface de escolha de snapshot
  nem autorizacao de restauracao durante uma sessao ativa.
- O APK gerado em build-cache/restore-boot-lab/ e apenas arquivo de
  laboratorio NAO ASSINADO, nao instalavel como upgrade. O APK estavel
  distribuido e o APK experimental instalado no Samsung nao foram tocados.

Teste automatizado: 10 novos testes de restore_startup, teste de ordem
no local_http e 3 novos testes de contrato de empacotamento. Teste
real de reinicio Android e interface de confirmacao permanecem pendentes.

## Marco de preparo do restore e interface Android (13/11/2026)

Foi adicionado restore_request.py ao empacotamento experimental, sob o nome
ffbe_restore_request.py. A UI futura cria restore-request.json e o ZIP local
request-<SHA256>.zip na pasta privada restore-private. O pedido inclui schema=1,
arquivo, SHA-256 completo e a frase de confirmação; a gravação é atômica.

- O pedido agendado não altera o save durante o gameplay.
- No próximo início, antes do motor, restore_startup valida o ZIP e o pedido,
  renomeia-o para restore-processing.json e inicia restore_offline().
- Após uma falha, recover_pending() desfaz a restauração interrompida.
  O marcador processing impede reexecutar automaticamente o mesmo pedido.
- Se uma transação antiga foi recuperada, NÃO se executa outro pedido
  aguardando na mesma inicialização.
- Pedido inválido bloqueia a inicialização até ser cancelado ou corrigido.
- Java de laboratório para a tela e o protocolo privado está em
  android/native-ui; ainda não foi compilado/injetado em DEX Android.
  Consulte android/native-ui/README.md.
- Os testes são sintéticos e não tocam nenhum snapshot real ou APK instalado.
