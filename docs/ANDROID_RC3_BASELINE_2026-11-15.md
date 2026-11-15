# Android RC3 — marco de inicialização no aparelho (2026-11-15)

## Aceite e escopo

- **Relato do usuário:** após a atualização para a candidata
  `FFBE-Revival-RC3-MutableInventory-ARM64-TEST-20261115.apk`,
  a inicialização do jogo/servidor local funcionou no Samsung ARM64.
- **Aceite restrito:** instalação incremental da revisão 10 e chegada à
  inicialização funcional. Não há prova ainda de gameplay, persistência,
  backup/restauração ou funcionamento com rede desligada.
- Não confundir este aceite com uma release estável ou com validação de
  todas as rotas do servidor HTTP.

## Proveniência imutável da APK testada

- APK: `FFBE-Revival-RC3-MutableInventory-ARM64-TEST-20261115.apk`
- Distribuição privada: `releases/candidates/` (fora do Git; sem binários
  proprietários neste repositório).
- SHA-256: `7230bfcf63fd6a303b84b2a97e979048d8d7a23561a930c9d12f945422079f18`
- Package: `com.square_enix.android_googleplay.FFBEWW`
- VersionCode: `9101`; versão `9.1.0`; arquitetura `arm64-v8a`.
- Certificado de teste SHA-256:
  `1e08a903aef9c3a721510b64ec764d01d3d094eb954161b62544ea8f187b5953`.
- Conteúdo testado: `7fd7715` e ancestrais diretos até `75e85a8`.
- Assinatura Android v1/v2/v3 e zipalign verificados; não reutilizar a
  nomenclatura *stable* para este artefato.

## Cadeia de correções aplicada

| Commit | Motivo | Limite da alteração |
| --- | --- | --- |
| `7a181c4` | Exigir recibo rev10/20 pacotes no instalador Java | Gate do instalador |
| `9a0867b` | Aceitar URLs `CreamySeaman6/Data` no manifesto rev10 | Validação do pack |
| `023d5c4` | Atualizar bootstrap e expor contagem por grupo | Bundle Python |
| `7fd7715` | Não exigir contagem imutável do cache nativo | Preflight Python |

A última correção mantém recebimentos dos 20 packs, hashes do cliente,
raízes/symlinks privados, arquivos essenciais e mínimos de recursos estáveis.
Nenhuma das quatro etapas exigiu limpar saves ou repetir o download integral.

## Testes e limites de evidência

- 139 testes automatizados no repositório, com teste de regressão das
  contagens observadas no Samsung e rejeição de recursos essenciais ausentes.
- A diferença de conteúdo da última APK frente à candidata imediatamente
  anterior é exclusivamente `assets/ffbe_python/stdlib.zip`.
- A `main` tinha uma alteração documental paralela e não é ancestral
  direto da linha RC3. Evitar promoção por force-push ou merge não auditado.
- RC2, stable anterior e candidatas de diagnóstico são preservadas para
  rollback; não mover aliases de produção sem novo aceite.

## Pendências que devem continuar abertas

1. Caminho real de título/Home, exploração e batalha no Samsung; erros de
   cache, recursos ou protocolo apenas com reprodução objetiva.
2. Save antes/depois de fechar e reabrir, sem alterar dados da instalação.
3. Telemetria de logs opt-in e backup remoto/recuperação, verificando permissões.
4. Funcionamento sem rede (após packs já instalados), ciclo de vida do serviço
   Android, interrupção e retomada após fechar app/reiniciar o celular.
5. Auditoria das atualizações de upstream e regressões do protocolo antes de
   nova integração funcional.
6. Teste de instalação limpa em outro perfil/aparelho, sem apagar este save.

**Política:** APK validada de inicialização = referência congelada. Nova
alteração funcional cria nova candidata com novo checksum, sem sobrescrever
este artefato.
