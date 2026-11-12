#!/usr/bin/env python3
"""Lab-only: bundle tracked Revival source and pure PyYAML with CPython stdlib.

No proprietary APK, data pack, source tarball, or built asset is added to Git.
This does not start the game engine, serve HTTP, or satisfy offline gameplay.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path

from build_python_probe import verify_archive
from embedded_engine import ROOT, MANIFEST, MAX_FILES, MAX_FILE_SIZE, MAX_TOTAL, validate_relative
from package_stdlib_probe import embed_asset, native_assets, NATIVE_INDEX, NATIVE_PREFIX

PY_YAML_SHA256 = "d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f"
PY_YAML_PREFIX = "pyyaml-6.0.3/lib/yaml/"
TZDATA_SHA256 = "0a10eec6e13ef16b627fabed9a5f2ba61a62b1c67f327305f4e7e412a70b4aec"
TZDATA_LICENSES = {
    "tzdata-2026.6.dist-info/licenses/LICENSE": "vendor/LICENSE-tzdata.txt",
    "tzdata-2026.6.dist-info/licenses/licenses/LICENSE_APACHE":
        "vendor/LICENSE-tzdata-apache.txt",
}
BOOTSTRAP = Path(__file__).with_name("embedded_engine.py")


def git_tracked_engine(repository: Path) -> dict[str, bytes]:
    result = subprocess.run(
        ["git", "-C", str(repository), "ls-files", "-z", "--", "source/server", "ios-server"],
        check=True, stdout=subprocess.PIPE,
    )
    contents = {}
    for item in result.stdout.split(b"\0"):
        if not item:
            continue
        relative = item.decode("utf-8")
        if not (relative.startswith("source/server/") or
                relative.startswith("ios-server/") and relative.endswith(".py")):
            continue
        validate_relative(relative)
        file = repository / relative
        if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_FILE_SIZE:
            raise ValueError("Unsafe tracked Revival engine source: " + relative)
        contents[relative] = file.read_bytes()
    if not {"ios-server/serve.py", "ios-server/certs.py",
            "source/server/capture_server.py"}.issubset(contents):
        raise ValueError("Missing core Revival source files")
    return contents


def pure_yaml(sdist: Path) -> dict[str, bytes]:
    if hashlib.sha256(sdist.read_bytes()).hexdigest() != PY_YAML_SHA256:
        raise ValueError("PyYAML source package SHA-256 mismatch")
    contents = {}
    with tarfile.open(sdist, "r:gz") as source:
        for info in source.getmembers():
            if not info.name.startswith(PY_YAML_PREFIX) or not info.name.endswith(".py"):
                continue
            if not info.isfile() or info.size > MAX_FILE_SIZE:
                raise ValueError("Unsafe PyYAML source entry")
            name = "vendor/yaml/" + info.name.removeprefix(PY_YAML_PREFIX)
            validate_relative(name)
            stream = source.extractfile(info)
            if stream is None:
                raise ValueError("Cannot read PyYAML module")
            contents[name] = stream.read()
        license_member = source.getmember("pyyaml-6.0.3/LICENSE")
        license_stream = source.extractfile(license_member)
        if license_stream is None or license_member.size > 65536:
            raise ValueError("PyYAML license missing")
        contents["vendor/LICENSE-pyyaml.txt"] = license_stream.read()
    if "vendor/yaml/__init__.py" not in contents:
        raise ValueError("Missing pure PyYAML package")
    return contents


def pure_tzdata(wheel: Path) -> dict[str, bytes]:
    """Extract only a pinned, universal tzdata wheel with both license texts."""
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != TZDATA_SHA256:
        raise ValueError("tzdata 2026.6 wheel SHA-256 mismatch")
    if wheel.name != "tzdata-2026.6-py2.py3-none-any.whl":
        raise ValueError("Unexpected tzdata distribution name")
    result = {}
    with zipfile.ZipFile(wheel) as source:
        names = source.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate names in tzdata wheel")
        for entry in source.infolist():
            if entry.is_dir():
                raise ValueError("Directory entry in pinned tzdata wheel")
            if stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFLNK:
                raise ValueError("Symlink in tzdata wheel")
            if entry.filename in TZDATA_LICENSES:
                destination = TZDATA_LICENSES[entry.filename]
            elif entry.filename.startswith("tzdata/"):
                destination = "vendor/" + entry.filename
            else:
                continue
            validate_relative(destination)
            if entry.file_size > MAX_FILE_SIZE:
                raise ValueError("Oversized tzdata file")
            result[destination] = source.read(entry)
    mandatory = {
        "vendor/tzdata/__init__.py",
        "vendor/tzdata/zoneinfo/__init__.py",
        "vendor/tzdata/zoneinfo/America/Sao_Paulo",
        *TZDATA_LICENSES.values(),
    }
    if not mandatory.issubset(result):
        raise ValueError("Incomplete tzdata 2026.6 wheel")
    return result


def package_engine(repository: Path, pyyaml_sdist: Path,
                   original_stdlib: Path, output: Path,
                   tzdata_wheel: Path | None = None) -> dict[str, int]:
    if output.exists():
        raise FileExistsError(output)
    data = git_tracked_engine(repository)
    data.update(pure_yaml(pyyaml_sdist))
    if tzdata_wheel is not None:
        data.update(pure_tzdata(tzdata_wheel))
    if len(data) > MAX_FILES or sum(map(len, data.values())) > MAX_TOTAL:
        raise ValueError("Revival source bundle exceeds limits")
    manifest = {
        "format": 1,
        "files": {name: {"sha256": hashlib.sha256(content).hexdigest(),
                          "size": len(content)}
                  for name, content in sorted(data.items())},
    }
    with zipfile.ZipFile(original_stdlib) as original:
        names = original.namelist()
        if MANIFEST in names or "ffbe_engine_bootstrap.py" in names or any(
            name.startswith(ROOT) for name in names
        ):
            raise ValueError("Engine already present in stdlib ZIP")
        if not {"encodings/__init__.py", "json/__init__.py"}.issubset(names):
            raise ValueError("Expected pinned uncompressed CPython stdlib")
        if any(i.compress_type != zipfile.ZIP_STORED for i in original.infolist()):
            raise ValueError("CPython stdlib must use ZIP_STORED for bootstrap")
        with zipfile.ZipFile(output, "w", allowZip64=True) as dst:
            for info in original.infolist():
                dst.writestr(info, original.read(info.filename))
            extra = {
                "ffbe_engine_bootstrap.py": BOOTSTRAP.read_bytes(),
                MANIFEST: json.dumps(manifest, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8"),
            }
            extra.update({ROOT + name: content for name, content in sorted(data.items())})
            for name, content in extra.items():
                info = zipfile.ZipInfo(name, (2026, 11, 12, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o100644 << 16
                dst.writestr(info, content)
    with zipfile.ZipFile(output) as zf:
        if json.loads(zf.read(MANIFEST)) != manifest:
            raise ValueError("Engine source manifest mismatch")
        if zf.testzip() is not None:
            raise ValueError("Engine stdlib archive corrupt")
    return {"engine_files": len(data), "engine_bytes": sum(map(len, data.values()))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--pyyaml-sdist", type=Path, required=True)
    parser.add_argument("--tzdata-wheel", type=Path, required=True,
                        help="pinned tzdata 2026.6 pure-Python wheel")
    parser.add_argument("--stdlib", type=Path, required=True)
    parser.add_argument("--out-stdlib", type=Path, required=True)
    parser.add_argument("--python-archive", type=Path, required=True)
    parser.add_argument("--python-prefix", type=Path, required=True)
    parser.add_argument("--abi", choices=("arm64-v8a", "x86_64"), required=True)
    parser.add_argument("--original-apk", type=Path, required=True)
    parser.add_argument("--dex-apk", type=Path, required=True)
    parser.add_argument("--out-apk", type=Path, required=True)
    args = parser.parse_args()
    verify_archive(args.python_archive, args.abi)
    result = package_engine(args.repo, args.pyyaml_sdist,
                            args.stdlib, args.out_stdlib, args.tzdata_wheel)
    embed_asset(args.original_apk, args.dex_apk, args.out_apk,
                args.out_stdlib, native_assets(args.python_prefix, args.abi))
    print("Tracked Revival files:", result["engine_files"],
          "bytes:", result["engine_bytes"])
    print("Lab only: import-only probe, not game backend startup")


if __name__ == "__main__":
    main()
