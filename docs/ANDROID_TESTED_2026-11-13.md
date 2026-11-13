# Android FFBE Revival - baseline funcional (2026-11-13)

## Testes confirmados
- Samsung SM-S942B: atualizacao com adb install -r, sem limpar dados; reinicializacao confirmada.
- Os 19 pacotes foram verificados; Revival HTTP respondeu READY em 127.0.0.1:18080 e HTTP 200.
- Home, Summon e batalha carregados no telefone; usuario concluiu batalha e invocacao.
- 95 testes automatizados de runtime e dados Android passaram na LXC 120.
- Backup real foi confirmado posteriormente no APK experimental separado; restauração ainda NÃO foi implementada/validada. Não atribuir backup ao APK estável.

## APK privado de referencia
- FFBE-Revival-Android-ARM64-stable-20261113.apk (na LXC 120, /srv/ffbe-distribution/releases/). O nome NEXT-RC-CONSISTENT continua apenas como link de compatibilidade.
- SHA256: 2f2bd6e47616cc51031ebcac26d3f175c22816af6883d18270303c8195d79a5e
- Certificado de assinatura SHA256: 1e08a903aef9c3a721510b64ec764d01d3d094eb954161b62544ea8f187b5953
- Base de codigo: integration/android-next-rc (bae3a49), com a correcao de inventario nesta branch.
- Nao publicar APK nem dados proprietarios em GitHub Releases publicas.

## Regras de compilacao e empacotamento
- Unir base.apk, config.arm64_v8a.apk, config.en.apk e config.mdpi.apk via APKEditor 1.4.9; excluir config.fr.apk.
- Ao atualizar o stdlib.zip, atualizar TODOS os arquivos rastreados em source/server, ios-server/*.py, android/data/offline_data.py e data/latest.json do MESMO commit.
- Atualizar ffbe_engine_bootstrap.py a partir de android/runtime/embedded_engine.py e ffbe_local_http.py de android/runtime/local_http.py.
- Regenerar ffbe_engine_manifest.json com SHA256 e tamanhos para cada arquivo; todos devem manter ZIP_STORED.
- Verificar com a implementacao real de embedded_engine.install antes de assinar.
- Validar hashes e tamanhos dos 19 pacotes originais, mantendo o manifesto de download fixado do APK.
- Assinar com uber-apk-signer 1.3.0 e o certificado original citado acima; verificar v1/v2/v3.
- A primeira compilacao falhou por misturar versoes: erro de arquivo inesperado e ImportError de convert_test.
- A checagem de inventario da revisao 9 permite deficit limitado exclusivamente em MST e homeMarquee, apos verificacoes dos arquivos essenciais.

## Recuperacao e pendencias
- Existe FFBE-Revival-RC2-ROLLBACK-ARM64.apk na LXC; a reversao ainda nao foi validada no aparelho e nao deve ser presumida.
- O APK experimental ConfigSync foi pareado no Samsung e enviou o primeiro ZIP real ao ZFS em 13/11/2026, SHA-256 `176f08dc07b23d61cb69e34a1581b5d686c9005f856bfdae83acb0a5e5f47af8`, contendo `campaign.json` e `replay.json`. Integridade ZIP verificada.
- Estado de configuração no experimental: `up_to_date`, sem erros; aplicação de alteração remota após reinício ainda não foi validada.
- Restauração controlada do save não implementada nem testada; tampouco foi testado um segundo snapshot após mudar o progresso ou operação com app fechado.
- O release estável e a variante experimental são builds diferentes: não trocar o estável pelo experimental sem validação específica.
- Prioridades: restaurar com segurança, validar aplicação de configuração, reprodução de build autônoma na LXC e isolar a pesquisa histórica. Consulte `docs/PROJECT_STATUS_AND_NEXT_STEPS.md`.
