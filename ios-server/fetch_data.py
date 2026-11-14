#!/usr/bin/env python3
"""Download and unpack the Exvius Offline game data (about 14.9 GB) into /srv/ffbe/data.

Uses the data manifest bundled with this build (data/latest.json from the repository), so the data
always matches the server code. Each pack is downloaded (resuming if interrupted), checked against
its SHA-256, unpacked, and deleted. Running it again only fetches packs that changed; when a pack
changes, every pack after it is unpacked again too, because later packs overwrite earlier files.

    docker compose run --rm server fetch-data            # first install, or after an update
    docker compose run --rm server fetch-data --verify   # just report what is installed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

DATA = Path(os.environ.get('FFBE_DATA_DIR', '/srv/ffbe/data'))
MANIFEST = Path(os.environ.get('FFBE_MANIFEST', Path(__file__).resolve().parent / 'latest.json'))
SKIP = {'client-assets'}  # Android app resources only; the iPhone app has its own
NATIVE_TOPS = {'mst', 'localized_texts', 'common_lang', 'en', 'homeMarquee'}


def log(message: str) -> None:
    print('[fetch-data] ' + message, flush=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, target: Path, size: int) -> None:
    partial = target.with_suffix('.part')
    for attempt in range(1, 8):
        have = partial.stat().st_size if partial.exists() else 0
        if have >= size:
            break
        request = urllib.request.Request(url, headers={'Range': f'bytes={have}-'} if have else {})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                if have and response.status != 206:
                    have = 0  # server ignored the range: start over
                mode = 'ab' if have else 'wb'
                shown, started = -1, time.time()
                with partial.open(mode) as out:
                    while True:
                        block = response.read(4 << 20)
                        if not block:
                            break
                        out.write(block)
                        have += len(block)
                        percent = int(have * 100 / size)
                        if percent // 10 != shown // 10:
                            shown = percent
                            rate = have / max(1.0, time.time() - started) / 1e6
                            log(f'  {target.name}: {percent}% ({have / 1e9:.2f} of {size / 1e9:.2f} GB, {rate:.0f} MB/s)')
        except OSError as exc:
            log(f'  download interrupted ({exc}); retrying ({attempt}/7)')
            time.sleep(min(60, 5 * attempt))
    if not partial.exists() or partial.stat().st_size != size:
        raise SystemExit(f'could not download {url}')
    partial.replace(target)


def destination(name: str) -> Path | None:
    """Where a pack entry goes: the same mapping as the Android app's DataPack.destination."""
    if '\\' in name or name.startswith('/') or '..' in name.split('/'):
        raise ValueError('unsafe path in data pack: ' + name)
    if name.endswith('/'):
        return None
    if name.startswith('static/'):
        return DATA / name
    if name.startswith('native/'):
        relative = name[len('native/'):]
        if relative.split('/', 1)[0] not in NATIVE_TOPS:
            raise ValueError('unexpected game data path: ' + name)
        return DATA / name
    if name == 'metadata/registry.json':
        return DATA / 'registry.json'
    raise ValueError('unexpected data pack entry: ' + name)


def unpack(archive: Path) -> int:
    count = 0
    with zipfile.ZipFile(archive) as zf:
        for entry in zf.infolist():
            target = destination(entry.filename)
            if target is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + '.installing')
            with zf.open(entry) as source, tmp.open('wb') as out:
                while True:
                    block = source.read(8 << 20)
                    if not block:
                        break
                    out.write(block)
            tmp.replace(target)
            count += 1
    return count


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--verify', action='store_true', help='report what is installed and stop')
    parser.add_argument('--manifest', default=str(MANIFEST), help='a data manifest path or URL')
    args = parser.parse_args(argv)
    if args.manifest.startswith('http'):
        with urllib.request.urlopen(args.manifest, timeout=60) as response:
            manifest = json.load(response)
    else:
        manifest = json.loads(Path(args.manifest).read_text())
    packs = [pack for pack in manifest['packs'] if pack['id'] not in SKIP]
    DATA.mkdir(parents=True, exist_ok=True)
    record_path = DATA / 'installed.json'
    installed = json.loads(record_path.read_text()) if record_path.exists() else {}
    first_change = next((i for i, pack in enumerate(packs) if installed.get(pack['id']) != pack['sha256']), None)
    total = sum(pack['size'] for pack in packs[first_change:]) if first_change is not None else 0
    log(f"data revision {manifest.get('revision')} ({manifest.get('version')}), {len(packs)} packs")
    if first_change is None:
        log('everything is installed and current')
        return 0
    log(f'{len(packs) - first_change} pack(s) to install, {total / 1e9:.1f} GB to download')
    if args.verify:
        return 1
    downloads = DATA / '.downloads'
    downloads.mkdir(exist_ok=True)
    for pack in packs[first_change:]:
        archive = downloads / (pack['id'] + '.zip')
        if not archive.exists() or archive.stat().st_size != pack['size']:
            log(f"downloading {pack['id']} ({pack['size'] / 1e9:.2f} GB)")
            download(pack['url'], archive, pack['size'])
        log(f"checking {pack['id']}")
        if sha256(archive) != pack['sha256']:
            archive.unlink()
            raise SystemExit(f"{pack['id']}: checksum mismatch; run fetch-data again to re-download it")
        installed.pop(pack['id'], None)
        record_path.write_text(json.dumps(installed, indent=1))
        count = unpack(archive)
        archive.unlink()
        installed[pack['id']] = pack['sha256']
        record_path.write_text(json.dumps(installed, indent=1))
        log(f"installed {pack['id']} ({count} files)")
    try:
        downloads.rmdir()
    except OSError:
        pass
    log('done. Start the server with:  docker compose up -d')
    return 0


if __name__ == '__main__':
    sys.exit(main())
