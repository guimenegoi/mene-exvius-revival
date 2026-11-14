#!/usr/bin/env python3
"""Cache the pinned revision-9 or revision-10 FFBE data ZIPs without unpacking or altering saves.

Uses the existing Revival downloader, Range-resume and SHA-256 implementation.
Output is an external-disk backup, NOT a completed first-run APK installer.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ios-server"))
import fetch_data  # noqa: E402

PACKS_BY_REVISION = {9: 19, 10: 20}


def read_packs(manifest: Path) -> list[dict]:
    body = json.loads(manifest.read_text(encoding="utf-8"))
    packs = body.get("packs")
    if (body.get("schema") != 1 or not isinstance(packs, list)
            or len(packs) != PACKS_BY_REVISION.get(body.get("revision"))):
        raise ValueError("Expected pinned revision-9/19 or revision-10/20 manifest")
    ids: set[str] = set()
    for pack in packs:
        if not isinstance(pack, dict):
            raise ValueError("Invalid data pack entry")
        name, sha, size, url = (pack.get(k) for k in ("id", "sha256", "size", "url"))
        if (not isinstance(name, str) or not re.fullmatch(r"[a-z0-9-]+", name)
                or name in ids or not isinstance(sha, str)
                or not re.fullmatch(r"[0-9a-f]{64}", sha)
                or type(size) is not int or size <= 0
                or not isinstance(url, str) or urlparse(url).scheme != "https"
                or urlparse(url).hostname != "github.com"):
            raise ValueError(f"Unsafe manifest entry: {name!r}")
        ids.add(name)
    if "client-assets" not in ids:
        raise ValueError("client-assets missing from pack manifest")
    return packs


def cache_pack(pack: dict, destination: Path, *, verify_only: bool) -> bool:
    archive = destination / (pack["id"] + ".zip")
    if archive.is_symlink() or archive.with_suffix(".part").is_symlink():
        raise ValueError("Refusing symlink cache entry: " + pack["id"])
    if archive.is_file():
        if archive.stat().st_size == pack["size"] and fetch_data.sha256(archive) == pack["sha256"]:
            print(f"VERIFIED {pack['id']} ({pack['size']} bytes)", flush=True)
            return True
        if verify_only:
            print(f"INVALID {pack['id']}: hash or size mismatch", flush=True)
            return False
        archive.unlink()
    if verify_only:
        print(f"MISSING {pack['id']}", flush=True)
        return False
    fetch_data.download(pack["url"], archive, pack["size"])
    if archive.stat().st_size != pack["size"] or fetch_data.sha256(archive) != pack["sha256"]:
        archive.unlink(missing_ok=True)
        raise ValueError(f"Hash or size mismatch after downloading {pack['id']}")
    print(f"VERIFIED {pack['id']} ({pack['size']} bytes)", flush=True)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--only", action="append", default=[],
                        help="One pack ID; may be repeated. Default: all manifest packs.")
    args = parser.parse_args(argv)
    packs = read_packs(args.manifest)
    known = {p["id"] for p in packs}
    if not set(args.only).issubset(known):
        parser.error("Unknown pack ID: " + ", ".join(sorted(set(args.only) - known)))
    if not args.verify_only:
        args.destination.mkdir(parents=True, exist_ok=True)
    if args.destination.is_symlink() or not args.destination.is_dir():
        parser.error("Cache destination is not an existing regular directory")
    selected = [p for p in packs if not args.only or p["id"] in args.only]
    ok = sum(cache_pack(p, args.destination, verify_only=args.verify_only) for p in selected)
    print(f"Cache verified: {ok}/{len(selected)} packs", flush=True)
    return 0 if ok == len(selected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
