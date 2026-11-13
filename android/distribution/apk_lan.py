#!/usr/bin/env python3
"""Temporary local-network download of ONE pinned, private FFBE test APK.

Separate process from the 19-pack lab cache; shares its byte-range sender.
HTTP is limited to an explicit private IPv4 LAN address, with a fresh,
unlogged, expiring capability URL. No public port forwarding.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import re
import secrets
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from local_cache_server import make_handler


def validated_artifact(path: Path, digest: str) -> tuple[Path, int, str]:
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("A pinned SHA-256 is required")
    if (not re.fullmatch(r"[A-Za-z0-9._-]{1,128}\.apk", path.name)
            or path.is_symlink() or not path.is_file()):
        raise ValueError("Only a regular named APK may be served")
    size = path.stat().st_size
    if not 0 < size < (1 << 31):
        raise ValueError("Unexpected APK size")
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(4 << 20), b""):
            result.update(part)
    if result.hexdigest() != digest:
        raise ValueError("APK SHA-256 does not match approved artifact")
    return path, size, digest


def valid_lan_ip(value: str) -> str:
    address = ipaddress.ip_address(value)
    if (address.version != 4 or not address.is_private or address.is_loopback
            or address.is_unspecified or address.is_multicast):
        raise ValueError("Must bind to an explicit private IPv4 LAN address")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--bind", required=True, help="LXC LAN IP, not 0.0.0.0")
    parser.add_argument("--port", type=int, default=18448)
    parser.add_argument("--minutes", type=int, default=30)
    args = parser.parse_args(argv)
    try:
        host = valid_lan_ip(args.bind)
        artifact = validated_artifact(args.apk, args.sha256)
        if not 1 <= args.minutes <= 120 or not 1024 <= args.port <= 65535:
            raise ValueError("Invalid port or expiration")
    except ValueError as exc:
        parser.error(str(exc))
    token = secrets.token_urlsafe(32)
    deadline = time.monotonic() + args.minutes * 60
    server = ThreadingHTTPServer((host, args.port),
        make_handler(b"", {}, apk=artifact, token=token, expires_at=deadline))
    server.daemon_threads = True
    shutdown = threading.Timer(args.minutes * 60, server.shutdown)
    shutdown.daemon = True
    shutdown.start()
    print("PRIVATE APK SOURCE:", flush=True)
    print(f"http://{host}:{args.port}/download/{token}/{artifact[0].name}", flush=True)
    print(f"SHA-256: {artifact[2]}", flush=True)
    print(f"EXPIRES IN: {args.minutes} minutes; URL works only on home LAN", flush=True)
    print("WARNING: temporary HTTP link is not encrypted. Use only on trusted LAN.", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        shutdown.cancel()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
