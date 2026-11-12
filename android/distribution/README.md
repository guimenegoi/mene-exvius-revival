# FFBE Revival — distribuição de laboratório

Esta pasta documenta uma **cópia privada** dos APKs experimentais e dos
pacotes de instalação no disco externo montado no LXC `workspace` (117):

`/workspace/projects/ffbe-revival-distribution/`

## Variante de primeira execução

O HD externo também mantém `apk/first-run-experimental/`, sem substituir
os cinco splits de `apk/`. Essa variante inclui `DataDownloadActivity`,
o downloader upstream v0.1.30 com manifesto revisão 9 fixado e a ponte
CPython/Revival. O launcher abriu no Waydroid e a sonda AES passou, mas
**ainda não aguarda a prontidão HTTP 18080 antes de abrir o jogo**.
Os 19 pacotes não foram instalados no Android de teste. Seu uso é
**exclusivamente experimental** e não comprova gameplay offline.

## Estrutura

- `apk/`: cinco splits Android **assinados com certificado de teste**, da
  variante FFBE 9.1.0 com CPython 3.14 ARM64, Revival e verificação de dados.
- `packs/`: ZIPs upstream, um por ID de `data/latest.json`; nenhum arquivo
  é alterado ou extraído, com SHA-256 conferido após download.
- `installer/`: cópia das fontes de instalação e manifesto fixado.
- `install_debug_split.sh`: atualiza via ADB os cinco APKs **sem desinstalar**
  nem limpar dados. Execute após copiar a pasta para um computador com ADB.

### Cache dos arquivos originais (LXC ou desktop)

```bash
python3 installer/android/distribution/cache_packs.py \
  --manifest installer/data/latest.json --destination packs

# Apenas validação, sem rede:
python3 installer/android/distribution/cache_packs.py \
  --manifest installer/data/latest.json --destination packs --verify-only
```

O script reutiliza o downloader de `ios-server/fetch_data.py`, com retomada
por HTTP Range; os 19 ZIPs totalizam aproximadamente **14,65 GB**.
Downloads incompletos permanecem como `.part` para retomada.

**Importante:** esse cache do HD externo serve como backup/distribuição de
laboratório. O APK experimental atual **não instala os dados automaticamente
na primeira execução**; ele evita iniciar o servidor enquanto os 19 pacotes
não estão presentes no seu armazenamento privado. Para concluir a experiência
de primeiro uso ainda são necessários a UI Android, o instalador interno
de recursos e o gerenciamento de prontidão. O cache no LXC não é acessível
automaticamente pelo Android.

O código original `android/data/offline_data.py` é a implementação de
instalação e verificação que será reutilizada no primeiro uso do APK.
A instalação exige **pelo menos 22 GiB livres** no dispositivo, conforme
estimativa conservadora do projeto.

Não publicar APK, recursos de jogo, saves ou chaves em releases públicos.
O cliente e os assets originais pertencem aos seus respectivos titulares.
