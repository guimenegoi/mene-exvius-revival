# Android — seleção e confirmação de restore (LAB, não distribuído)

Código-fonte nativo experimental em src/com/mene/exvius:

- RestoreActivity.java: tela Android simples, com seletor nativo de arquivo ZIP
  (Storage Access Framework), hash SHA-256 completo, frase de confirmação
  digitada e opções de agendar/cancelar.
- RestoreRequestCodec.java: copia o ZIP para uma área privada com limite de
  20 MiB, SHA-256 e gravação atômica + fsync. Gera restore-request.json
  COMPATÍVEL com android/backup/restore_request.py. Não lê nem escreve
  campaign.json nem replay.json; somente verifica se campaign.json existe.
- RestoreRequestCodecTest.java: testes sintéticos Java sem dependência do
  runtime Android, executados com javac/java num ambiente de desenvolvimento.
- patch_restore_manifest.py: helper somente para manifesto XML DECODIFICADO,
  acrescentando uma segunda entrada no launcher ("Restaurar save (LAB)").
  Nunca altera sozinho o APK existente, nem instala versão alguma.

## Fluxo previsto

1. No APK **LAB separado**, abrir a segunda entrada do launcher.
2. Selecionar ZIP local obtido por um canal privado e conferir SHA-256.
3. Digitar exatamente RESTAURAR + espaço + os 12 primeiros caracteres do SHA.
4. O Android grava ZIP + metadados em files/exvius/server-root/restore-private.
   Não há restauração durante a execução do jogo.
5. Após fechar completamente e reabrir o aplicativo, ffbe_restore_startup
   valida o pedido e executa a restauração antes de carregar o motor; gera
   pré-backup e mantém mecanismo de recuperação após falha.
6. Em caso de cancelamento ANTES da execução, remove a solicitação e os
   ZIPs temporários com nomes de staging. Nunca apaga pré-backups.

## Situação e limites

- A classe Java foi compilada sintaticamente com stubs compatíveis da API
  Android e o codec foi exercitado com testes Java em ambiente isolado.
  Isso **não substitui** compilação real com android.jar, conversão DEX,
  verificação do Manifest binário nem testes em aparelho.
- A LXC 120 tem APKTool e Smali, mas ainda não tem compilador Java+ferramenta
  D8/dx e o SDK Android completos. NÃO forçar instalação de novas ferramentas
  na LXC de produção sem um pipeline controlado.
- A segunda entrada de launcher é um recurso de laboratório, não uma mudança
  na experiência estável. NENHUMA dessas classes está no APK instalado.
- O seletor importa ZIPs locais. Não existe ainda um endpoint autorizado
  para baixar snapshots do ZFS para o aparelho; não expor saves por URL sem
  uma revisão específica de autenticação e privacidade.
- A restauração real permanece bloqueada até revisão de ciclo de vida,
  teste em aparelho isolado e confirmação explícita do proprietário.

## Testes locais

    python3 -m unittest discover -s android/native-ui -p 'test_*.py' -q

O Java puro é compilável com JDK 8+ em um ambiente separado; a compilação
Android real será incorporada a uma etapa reprodutível de LAB após dispor do SDK.
