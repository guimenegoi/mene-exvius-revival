#!/usr/bin/env python3
"""Lab-only, reproducible RC3 manual-history bundle graft (UNSIGNED output).

Keep all client, Java, native and data members intact. The source APK is a
locally provided, signed and verified proprietary RC3; NEVER commit its bytes.
Signing and publication are separate explicit review gates.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

PINNED_BASE = '4bd83f73eadfc7f779e06801db15bdd19d09020e3dbe5a5ba041c0de324c795f'
STDLIB = 'assets/ffbe_python/stdlib.zip'
UPDATED = {
    'ffbe_local_http.py': 'android/runtime/local_http.py',
    'ffbe_engine/source/server/replay.py': 'source/server/replay.py',
    'ffbe_engine/source/server/gacha_rotation.py': 'source/server/gacha_rotation.py',
    'config_model.py': 'android/backup/config_model.py',
    'config_sync.py': 'android/backup/config_sync.py',
}
ADDED = {'ffbe_manual_history.py': 'android/runtime/manual_history.py'}
MANIFEST = 'ffbe_engine_manifest.json'
SIGNATURE_SUFFIXES = ('.RSA', '.SF', '.EC', '.DSA')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unsigned_apk(source: Path, repository: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(output)
    if digest(source.read_bytes()) != PINNED_BASE:
        raise ValueError('Wrong RC3 base APK; refuse bundle graft')
    updates = {name: (repository / relative).read_bytes()
               for name, relative in UPDATED.items()}
    updates.update({name: (repository / relative).read_bytes()
                    for name, relative in ADDED.items()})
    with zipfile.ZipFile(source) as apk:
        original_stdlib = apk.read(STDLIB)
        with zipfile.ZipFile(io.BytesIO(original_stdlib)) as frozen:
            assert frozen.testzip() is None
            names = frozen.namelist()
            if len(names) != len(set(names)) or not set(UPDATED).issubset(names):
                raise ValueError('Unexpected RC3 Python archive layout')
            if any(name in names for name in ADDED):
                raise ValueError('Manual settings already embedded')
            manifest = json.loads(frozen.read(MANIFEST))
            for name in ('source/server/replay.py', 'source/server/gacha_rotation.py'):
                body = updates['ffbe_engine/' + name]
                if name not in manifest['files']:
                    raise ValueError('Missing engine member in signed manifest')
                manifest['files'][name] = {'size': len(body), 'sha256': digest(body)}
            updates[MANIFEST] = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
            with io.BytesIO() as new_io:
                with zipfile.ZipFile(new_io, 'w', allowZip64=True) as out:
                    for member in frozen.infolist():
                        out.writestr(member, updates.get(member.filename,
                                                       frozen.read(member.filename)))
                    for name in ADDED:
                        out.writestr(name, updates[name], compress_type=zipfile.ZIP_STORED)
                new_stdlib = new_io.getvalue()
        with zipfile.ZipFile(io.BytesIO(new_stdlib)) as check:
            if check.testzip() is not None:
                raise ValueError('Generated Python archive CRC failure')
            for name, data in updates.items():
                if check.read(name) != data:
                    raise ValueError('Python archive mismatch: ' + name)
        with zipfile.ZipFile(output, 'w', allowZip64=True) as out:
            for member in apk.infolist():
                name = member.filename
                if name.startswith('META-INF/') and (name.endswith(SIGNATURE_SUFFIXES)
                                                       or name == 'META-INF/MANIFEST.MF'):
                    continue
                out.writestr(member, new_stdlib if name == STDLIB else apk.read(name))
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(output) as new:
        unsigned_names = {name for name in old.namelist() if not
                          (name.startswith('META-INF/') and (name.endswith(SIGNATURE_SUFFIXES)
                                                        or name == 'META-INF/MANIFEST.MF'))}
        if new.testzip() is not None or set(new.namelist()) != unsigned_names:
            raise ValueError('APK layout changed unexpectedly')
        changed = [name for name in new.namelist()
                   if digest(new.read(name)) != digest(old.read(name))]
        if changed != [STDLIB]:
            raise ValueError('Unsigned APK unexpectedly modified ' + repr(changed))
    return {'changed_apk_members': changed, 'stdlib_sha256': digest(new_stdlib),
            'unsigned_sha256': digest(output.read_bytes()), 'engine_files': len(manifest['files'])}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(unsigned_apk(args.base, args.repo, args.output), indent=2))


if __name__ == '__main__':
    main()
